"""First-run bootstrap of an organisation and owner user.

Runs once on API startup. If ``INITIAL_ADMIN_EMAIL`` and
``INITIAL_ADMIN_PASSWORD`` are set and the ``users`` table is empty,
creates an organisation and a single owner user so the operator can log
in to the admin UI for the first time. That user is also made a platform
admin. Idempotent: once any user exists, this is a no-op, so the
environment variables can safely remain set across restarts. Complements
``ADMIN_BOOTSTRAP_TOKEN``, which gates runtime org creation; this creates
the *initial* org + owner without requiring a second round-trip.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import Settings
from src.db.session import async_session_factory
from src.models.organisation import Organisation
from src.models.user import User
from src.services.auth import hash_password

logger = logging.getLogger(__name__)


async def bootstrap_initial_admin(settings: Settings) -> None:
    """Create the first organisation and owner user if none exist.

    No-op when either credential env var is unset or when the database
    already contains at least one user. Unexpected errors are logged
    and swallowed — a failed bootstrap must not prevent the API from
    starting, since operators can always fall back to manual provisioning.
    """
    if not settings.initial_admin_email or not settings.initial_admin_password:
        logger.debug("Initial admin bootstrap skipped: credentials not configured")
        return

    try:
        async with async_session_factory() as session:
            await _bootstrap(session, settings)
    except Exception:  # pragma: no cover — defensive, logged
        logger.exception("Initial admin bootstrap failed")


async def _bootstrap(session: AsyncSession, settings: Settings) -> None:
    existing_users = await session.scalar(select(func.count()).select_from(User))
    if existing_users:
        logger.debug("Initial admin bootstrap skipped: %d user(s) already exist", existing_users)
        return

    org = await session.scalar(
        select(Organisation).where(Organisation.slug == settings.initial_org_slug)
    )
    if org is None:
        org = Organisation(
            name=settings.initial_org_name,
            slug=settings.initial_org_slug,
            contact_email=settings.initial_admin_email,
        )
        session.add(org)
        await session.flush()

    user = User(
        organisation_id=org.id,
        email=settings.initial_admin_email,
        password_hash=hash_password(settings.initial_admin_password),
        full_name=settings.initial_admin_full_name,
        role="owner",
        is_superuser=True,
    )
    session.add(user)
    await session.commit()

    logger.warning(
        "Initial admin bootstrap created owner %s in organisation '%s'. "
        "Rotate the password via the admin UI as soon as possible.",
        settings.initial_admin_email,
        org.slug,
    )
