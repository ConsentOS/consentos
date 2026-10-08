"""Tests for the platform admin flag: dependency, CLI and schema exposure."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cli import platform_admin
from src.models.user import User
from src.schemas.auth import CurrentUser, UpdateProfileRequest
from src.schemas.user import UserCreate, UserUpdate
from src.services.dependencies import require_superuser
from tests.conftest import requires_db


def _current_user() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        organisation_id=uuid.uuid4(),
        email="owner@example.com",
        role="owner",
    )


class TestRequireSuperuser:
    async def test_allows_platform_admin(self):
        user = _current_user()
        db = AsyncMock()
        db.scalar.return_value = True
        assert await require_superuser(current_user=user, db=db) is user

    @pytest.mark.parametrize("flag", [False, None])
    async def test_rejects_everyone_else(self, flag):
        db = AsyncMock()
        db.scalar.return_value = flag
        with pytest.raises(HTTPException) as exc_info:
            await require_superuser(current_user=_current_user(), db=db)
        assert exc_info.value.status_code == 403


class TestSchemasDoNotExposeFlag:
    @pytest.mark.parametrize(
        "schema, data",
        [
            (
                UserCreate,
                {"email": "a@example.com", "password": "Password123", "full_name": "A"},
            ),
            (UserUpdate, {"full_name": "A"}),
            (UpdateProfileRequest, {"full_name": "A"}),
        ],
    )
    def test_flag_is_ignored(self, schema, data):
        model = schema(**data, is_superuser=True)
        assert "is_superuser" not in model.model_dump()


def _summary(*, is_superuser: bool = False) -> platform_admin.UserSummary:
    return platform_admin.UserSummary(
        id=uuid.uuid4(),
        email="ops@example.com",
        full_name="Ops Person",
        organisation_name="Acme Ltd",
        is_superuser=is_superuser,
    )


class TestCli:
    def test_grant_shows_user_and_organisation_then_confirms(self, capsys):
        user = _summary()
        with (
            patch.object(platform_admin, "find_user", return_value=user),
            patch.object(platform_admin, "set_platform_admin", return_value=True) as setter,
            patch("builtins.input", return_value="y") as prompt,
        ):
            platform_admin.main(["--email", "ops@example.com"])
        prompt.assert_called_once()
        setter.assert_called_once_with(user.id, enabled=True)
        out = capsys.readouterr().out
        assert "Ops Person <ops@example.com>" in out
        assert "Acme Ltd" in out
        assert "granted to ops@example.com" in out

    @pytest.mark.parametrize("answer", ["", "n", "no", "anything"])
    def test_declining_changes_nothing(self, answer, capsys):
        with (
            patch.object(platform_admin, "find_user", return_value=_summary()),
            patch.object(platform_admin, "set_platform_admin") as setter,
            patch("builtins.input", return_value=answer),
            pytest.raises(SystemExit) as exc_info,
        ):
            platform_admin.main(["--email", "ops@example.com"])
        assert exc_info.value.code == 1
        setter.assert_not_called()
        assert "Aborted" in capsys.readouterr().err

    def test_no_input_available_changes_nothing(self):
        with (
            patch.object(platform_admin, "find_user", return_value=_summary()),
            patch.object(platform_admin, "set_platform_admin") as setter,
            patch("builtins.input", side_effect=EOFError),
            pytest.raises(SystemExit),
        ):
            platform_admin.main(["--email", "ops@example.com"])
        setter.assert_not_called()

    def test_yes_skips_the_prompt(self):
        user = _summary(is_superuser=True)
        with (
            patch.object(platform_admin, "find_user", return_value=user),
            patch.object(platform_admin, "set_platform_admin", return_value=True) as setter,
            patch("builtins.input") as prompt,
        ):
            platform_admin.main(["--email", "ops@example.com", "--revoke", "--yes"])
        prompt.assert_not_called()
        setter.assert_called_once_with(user.id, enabled=False)

    def test_already_in_requested_state(self, capsys):
        with (
            patch.object(platform_admin, "find_user", return_value=_summary(is_superuser=True)),
            patch.object(platform_admin, "set_platform_admin") as setter,
        ):
            platform_admin.main(["--email", "ops@example.com"])
        setter.assert_not_called()
        assert "No change needed" in capsys.readouterr().out

    def test_unknown_user_exits_non_zero(self, capsys):
        with (
            patch.object(platform_admin, "find_user", return_value=None),
            pytest.raises(SystemExit) as exc_info,
        ):
            platform_admin.main(["--email", "nobody@example.com"])
        assert exc_info.value.code == 1
        assert "no active user" in capsys.readouterr().err


@requires_db
class TestCliWithDatabase:
    async def test_find_and_set(self, _test_engine, test_user):
        async def _flag() -> bool:
            async with AsyncSession(_test_engine) as session:
                return await session.scalar(
                    select(User.is_superuser).where(User.id == test_user.id)
                )

        found = platform_admin.find_user(test_user.email)
        assert found is not None
        assert found.id == test_user.id
        assert found.organisation_name
        assert found.is_superuser is False

        assert platform_admin.set_platform_admin(found.id, enabled=True) is True
        assert await _flag() is True

        assert platform_admin.set_platform_admin(found.id, enabled=False) is True
        assert await _flag() is False

    async def test_unknown_user(self, _setup_db):
        assert platform_admin.find_user("missing@example.com") is None
        assert platform_admin.set_platform_admin(uuid.uuid4(), enabled=True) is False
