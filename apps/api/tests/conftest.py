"""Shared test fixtures for the CMP API test suite.

Provides two modes:
  - Unit tests: use `app` and `client` fixtures (no database required)
  - Integration tests: use `db_client` fixture (requires PostgreSQL)

Integration tests are automatically skipped when no database is available.
"""

import os

# Disable rate limiting for the test suite. Many tests make dozens of
# requests from the same loopback address in rapid succession and the
# middleware would legitimately reject them as a DoS; the middleware
# has its own dedicated test module.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "test")

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.main import create_app
from src.models.base import Base

# ── Detect whether a test database is available ──────────────────────

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get("DATABASE_URL", ""),
)

_HAS_DB = bool(_TEST_DB_URL) and "localhost" in _TEST_DB_URL


def _requires_db(fn):
    """Mark a test as requiring a live database.

    Also pins the event loop to session scope so that fixtures sharing the
    session-scoped engine don't get 'Future attached to a different loop'.
    """
    fn = pytest.mark.asyncio(loop_scope="session")(fn)
    fn = pytest.mark.skipif(not _HAS_DB, reason="No test database available")(fn)
    return fn


requires_db = _requires_db


# ── Unit test fixtures (no database) ─────────────────────────────────


@pytest.fixture
def app():
    """Create a fresh FastAPI application instance."""
    return create_app()


@pytest.fixture
async def client(app):
    """Async HTTP client for unit tests (no database)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Integration test fixtures (with database) ────────────────────────


@pytest.fixture(scope="session")
def _test_engine():
    """Create a test database engine (session-scoped)."""
    if not _HAS_DB:
        pytest.skip("No test database available")
    return create_async_engine(_TEST_DB_URL, echo=False)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _setup_db(_test_engine):
    """Create all tables once per test session, then seed fixture data.

    Tests that depend on the cookie-category seed (normally applied by
    the ``0001_initial_schema`` alembic migration) get the same rows
    here so they can run without invoking alembic.
    """
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _seed_cookie_categories(conn)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _seed_cookie_categories(conn) -> None:
    """Insert the default cookie categories. Mirrors migration 0001."""
    import uuid as _uuid

    from sqlalchemy import text

    rows = [
        ("10000000-0000-0000-0000-000000000001", "Necessary", "necessary", True, 0),
        ("10000000-0000-0000-0000-000000000002", "Functional", "functional", False, 1),
        ("10000000-0000-0000-0000-000000000003", "Analytics", "analytics", False, 2),
        ("10000000-0000-0000-0000-000000000004", "Marketing", "marketing", False, 3),
        ("10000000-0000-0000-0000-000000000005", "Personalisation", "personalisation", False, 4),
    ]
    stmt = text(
        """
        INSERT INTO cookie_categories
            (id, name, slug, description, is_essential, display_order)
        VALUES (:id, :name, :slug, :description, :is_essential, :display_order)
        ON CONFLICT (slug) DO NOTHING
        """,
    )
    for row_id, name, slug, is_essential, order in rows:
        await conn.execute(
            stmt,
            {
                "id": _uuid.UUID(row_id),
                "name": name,
                "slug": slug,
                "description": f"{name} cookies",
                "is_essential": is_essential,
                "display_order": order,
            },
        )


@pytest_asyncio.fixture(loop_scope="session")
async def db_client(_test_engine, _setup_db):
    """Async HTTP client where each route handler gets its own DB session.

    Each request gets an independent session/connection so there are no
    'another operation is in progress' errors from asyncpg.
    """
    from src.db import get_db

    app = create_app()

    async def _override_get_db():
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Auth helper fixtures ─────────────────────────────────────────────


@pytest_asyncio.fixture(loop_scope="session")
async def test_org(_test_engine, _setup_db):
    """Create a test organisation in the database."""
    from src.models.organisation import Organisation

    async with AsyncSession(_test_engine, expire_on_commit=False) as session:
        org = Organisation(
            id=uuid.uuid4(),
            name="Test Organisation",
            slug=f"test-org-{uuid.uuid4().hex[:8]}",
        )
        session.add(org)
        await session.commit()
        return org


@pytest_asyncio.fixture(loop_scope="session")
async def test_user(_test_engine, _setup_db, test_org):
    """Create a test user (owner role) with a known password."""
    from src.models.user import User
    from src.services.auth import hash_password

    async with AsyncSession(_test_engine, expire_on_commit=False) as session:
        user = User(
            id=uuid.uuid4(),
            email=f"admin-{uuid.uuid4().hex[:8]}@test.com",
            password_hash=hash_password("TestPassword123"),
            full_name="Test Admin",
            role="owner",
            organisation_id=test_org.id,
        )
        session.add(user)
        await session.commit()
        return user


@pytest_asyncio.fixture(loop_scope="session")
async def auth_token(test_user):
    """Generate a valid JWT token for the test user."""
    from src.services.auth import create_access_token

    return create_access_token(
        user_id=str(test_user.id),
        organisation_id=str(test_user.organisation_id),
        role=test_user.role,
        email=test_user.email,
    )


@pytest_asyncio.fixture(loop_scope="session")
async def auth_headers(auth_token):
    """HTTP headers with a valid Bearer token."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture(loop_scope="session")
async def other_org_headers(_test_engine, _setup_db):
    """Auth headers for an owner in a second, unrelated organisation."""
    from src.models.organisation import Organisation
    from src.models.user import User
    from src.services.auth import create_access_token, hash_password

    async with AsyncSession(_test_engine, expire_on_commit=False) as session:
        org = Organisation(
            id=uuid.uuid4(),
            name="Other Organisation",
            slug=f"other-org-{uuid.uuid4().hex[:8]}",
        )
        session.add(org)
        await session.flush()
        user = User(
            id=uuid.uuid4(),
            email=f"other-{uuid.uuid4().hex[:8]}@test.com",
            password_hash=hash_password("TestPassword123"),
            full_name="Other Owner",
            role="owner",
            organisation_id=org.id,
        )
        session.add(user)
        await session.commit()

    token = create_access_token(
        user_id=str(user.id),
        organisation_id=str(org.id),
        role=user.role,
        email=user.email,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(loop_scope="session")
async def superuser_headers(_test_engine, _setup_db, test_org):
    """HTTP headers for an owner who is also a platform admin."""
    from src.models.user import User
    from src.services.auth import create_access_token, hash_password

    async with AsyncSession(_test_engine, expire_on_commit=False) as session:
        user = User(
            id=uuid.uuid4(),
            email=f"platform-{uuid.uuid4().hex[:8]}@test.com",
            password_hash=hash_password("TestPassword123"),
            full_name="Platform Admin",
            role="owner",
            organisation_id=test_org.id,
            is_superuser=True,
        )
        session.add(user)
        await session.commit()

    token = create_access_token(
        user_id=str(user.id),
        organisation_id=str(user.organisation_id),
        role=user.role,
        email=user.email,
    )
    return {"Authorization": f"Bearer {token}"}


# ── Shared helper for creating sites in integration tests ────────────


async def create_test_site(
    client: AsyncClient,
    headers: dict,
    *,
    domain_prefix: str = "test",
    display_name: str = "Test Site",
) -> str:
    """Create a site via the API and return its ID.

    This is a helper function (not a fixture) so it can be called
    inline within each test, avoiding async fixture event-loop issues.
    """
    resp = await client.post(
        "/api/v1/sites/",
        json={
            "domain": f"{domain_prefix}-{uuid.uuid4().hex[:8]}.com",
            "display_name": display_name,
        },
        headers=headers,
    )
    assert resp.status_code == 201, f"Failed to create test site: {resp.text}"
    return resp.json()["id"]
