"""Migration 0015 marks sites published before the upgrade as set up.

Runs inside a transaction that is rolled back, so the update only sees
the sites the test creates.
"""

import importlib.util
import uuid
from pathlib import Path

import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.organisation import Organisation
from src.models.site import Site
from src.models.site_config import SiteConfig
from tests.conftest import requires_db

_VERSIONS = Path(__file__).parents[1] / "alembic" / "versions"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration_0013 = _load("0013_site_config_revisions")
migration_0015 = _load("0015_site_setup")


@pytest_asyncio.fixture(loop_scope="session")
async def session(_test_engine, _setup_db):
    async with _test_engine.connect() as conn:
        transaction = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()


async def _site(db: AsyncSession, org: Organisation) -> Site:
    site = Site(organisation_id=org.id, domain=f"m15-{uuid.uuid4().hex[:8]}.com", display_name="M")
    db.add(site)
    await db.flush()
    db.add(SiteConfig(site_id=site.id))
    await db.flush()
    return site


@requires_db
async def test_published_sites_are_marked_set_up(session: AsyncSession):
    org = Organisation(name="Migration 0015", slug=f"m15-{uuid.uuid4().hex[:8]}")
    session.add(org)
    await session.flush()
    published = await _site(session, org)
    conn = await session.connection()
    # Publishes v1 for every site with a config, as 0013 did on upgrade.
    await conn.run_sync(migration_0013.backfill_initial_revisions)
    unpublished = await _site(session, org)

    await session.execute(text(migration_0015.MARK_PUBLISHED_SITES_SET_UP))

    rows = await session.execute(
        select(Site.id, Site.banner_confirmed_at, Site.setup_dismissed_at)
        .where(Site.id.in_([published.id, unpublished.id]))
        .execution_options(populate_existing=True)
    )
    marks = {row.id: (row.banner_confirmed_at, row.setup_dismissed_at) for row in rows}
    assert all(value is not None for value in marks[published.id])
    assert marks[unpublished.id] == (None, None)
