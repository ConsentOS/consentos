"""Who may do what with drafts and revisions (mocked database).

Editors and viewers can see the draft, the diff and the history; only
owners and admins can publish, bulk publish, roll back, discard or make
a preview link.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.db import get_db
from src.main import create_app
from src.services.auth import create_access_token

SITE = uuid.uuid4()
REVISION = uuid.uuid4()
HASH = "0" * 64

WRITES = [
    ("POST", f"/api/v1/config/sites/{SITE}/publish", {"expected_content_hash": HASH}),
    ("POST", f"/api/v1/config/sites/{SITE}/revisions/{REVISION}/rollback", {}),
    ("POST", f"/api/v1/config/sites/{SITE}/discard", None),
    ("POST", f"/api/v1/config/sites/{SITE}/preview", None),
    (
        "POST",
        "/api/v1/config/bulk-publish",
        {"sites": [{"site_id": str(SITE), "expected_content_hash": HASH}]},
    ),
]
READS = [
    ("GET", f"/api/v1/config/sites/{SITE}/draft", None),
    ("GET", f"/api/v1/config/sites/{SITE}/diff", None),
    ("GET", f"/api/v1/config/sites/{SITE}/revisions", None),
    ("GET", f"/api/v1/config/sites/{SITE}/revisions/{REVISION}", None),
    ("GET", "/api/v1/config/affected-sites", None),
]


def _headers(role: str) -> dict:
    token = create_access_token(
        user_id=uuid.uuid4(), organisation_id=uuid.uuid4(), role=role, email="u@test.com"
    )
    return {"Authorization": f"Bearer {token}"}


async def _request(role: str, method: str, url: str, body) -> int:
    app = create_app()
    # Every lookup finds nothing, so an allowed request stops at "not
    # found" (or an empty result) rather than touching real data.
    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    empty.scalars.return_value.all.return_value = []
    empty.scalars.return_value.__iter__.return_value = iter(())
    session = AsyncMock()
    session.execute = AsyncMock(return_value=empty)
    session.get = AsyncMock(return_value=None)

    async def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.request(method, url, headers=_headers(role), json=body)
    return resp.status_code


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "admin"])
@pytest.mark.parametrize(("method", "url", "body"), WRITES)
async def test_owners_and_admins_can_change_what_is_live(role, method, url, body):
    assert await _request(role, method, url, body) != 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["editor", "viewer"])
@pytest.mark.parametrize(("method", "url", "body"), WRITES)
async def test_editors_and_viewers_cannot(role, method, url, body):
    assert await _request(role, method, url, body) == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "admin", "editor", "viewer"])
@pytest.mark.parametrize(("method", "url", "body"), READS)
async def test_everyone_can_see_drafts_and_history(role, method, url, body):
    assert await _request(role, method, url, body) != 403
