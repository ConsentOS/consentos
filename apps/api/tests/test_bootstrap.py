"""Tests for the initial admin bootstrap service."""

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import Settings
from src.models.organisation import Organisation
from src.models.user import User
from src.services.auth import verify_password
from src.services.bootstrap import bootstrap_initial_admin
from tests.conftest import requires_db


def _settings(**overrides) -> Settings:
    base: dict = dict(
        environment="test",
        initial_admin_email=None,
        initial_admin_password=None,
        initial_admin_full_name="Administrator",
        initial_org_name="Default Organisation",
        initial_org_slug="default",
    )
    base.update(overrides)
    return Settings(**base)


class TestBootstrapNoOp:
    """Pure unit tests — bootstrap must short-circuit before touching the DB."""

    async def test_noop_when_email_unset(self):
        settings = _settings(initial_admin_password="pw")
        with patch("src.services.bootstrap.async_session_factory") as factory:
            await bootstrap_initial_admin(settings)
        factory.assert_not_called()

    async def test_noop_when_password_unset(self):
        settings = _settings(initial_admin_email="admin@example.com")
        with patch("src.services.bootstrap.async_session_factory") as factory:
            await bootstrap_initial_admin(settings)
        factory.assert_not_called()


@requires_db
class TestBootstrapWithDatabase:
    """Integration tests — exercise the real SQL path."""

    @pytest_asyncio.fixture(loop_scope="session")
    async def clean_db(self, _test_engine, _setup_db):
        """Strip users and orgs so bootstrap sees an empty table."""
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            await session.execute(User.__table__.delete())
            await session.execute(Organisation.__table__.delete())
            await session.commit()
        yield
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            await session.execute(User.__table__.delete())
            await session.execute(Organisation.__table__.delete())
            await session.commit()

    async def test_creates_org_and_owner_when_empty(self, _test_engine, clean_db):
        email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
        slug = f"bootstrap-{uuid.uuid4().hex[:8]}"
        settings = _settings(
            initial_admin_email=email,
            initial_admin_password="SuperSecret123",
            initial_org_slug=slug,
            initial_org_name="Bootstrapped Org",
        )

        def _factory():
            return AsyncSession(_test_engine, expire_on_commit=False)

        with patch("src.services.bootstrap.async_session_factory", _factory):
            await bootstrap_initial_admin(settings)

        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            user = (await session.execute(select(User).where(User.email == email))).scalar_one()
            org = (
                await session.execute(select(Organisation).where(Organisation.slug == slug))
            ).scalar_one()

        assert user.role == "owner"
        assert user.is_superuser is True
        assert user.organisation_id == org.id
        assert user.full_name == "Administrator"
        assert verify_password("SuperSecret123", user.password_hash)
        assert org.name == "Bootstrapped Org"
        assert org.contact_email == email

    async def test_idempotent_when_user_exists(self, _test_engine, clean_db):
        """A second invocation must not create a second user."""
        email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
        slug = f"bootstrap-{uuid.uuid4().hex[:8]}"
        settings = _settings(
            initial_admin_email=email,
            initial_admin_password="SuperSecret123",
            initial_org_slug=slug,
        )

        def _factory():
            return AsyncSession(_test_engine, expire_on_commit=False)

        with patch("src.services.bootstrap.async_session_factory", _factory):
            await bootstrap_initial_admin(settings)
            await bootstrap_initial_admin(
                _settings(
                    initial_admin_email="someone-else@example.com",
                    initial_admin_password="Different123",
                    initial_org_slug=slug,
                )
            )

        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            users = (await session.execute(select(User))).scalars().all()

        assert len(users) == 1
        assert users[0].email == email


pytestmark = pytest.mark.asyncio(loop_scope="session")
