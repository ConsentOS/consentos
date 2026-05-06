"""Celery application and task definitions for the CMP API.

Provides async-compatible scan scheduling via Celery with Redis as the
broker and result backend.
"""

import ssl

from celery import Celery
from celery.schedules import crontab

from src.config.settings import get_settings

settings = get_settings()

# Named `app` by Celery convention — the CLI finds it via -A src.celery_app
app = Celery(
    "cmp",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# When using rediss:// (TLS) — e.g. Upstash — Celery requires explicit
# SSL certificate verification settings for both broker and backend.
_conf: dict = {
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    "task_track_started": True,
    "task_acks_late": True,
    "worker_prefetch_multiplier": 1,
}

if settings.redis_url.startswith("rediss://"):
    _conf["broker_use_ssl"] = {"ssl_cert_reqs": ssl.CERT_NONE}
    _conf["redis_backend_use_ssl"] = {"ssl_cert_reqs": ssl.CERT_NONE}

app.conf.update(**_conf)


# ── Beat schedule (periodic tasks) ──────────────────────────────────

app.conf.beat_schedule = {
    "check-scheduled-scans": {
        "task": "src.tasks.scanner.check_scheduled_scans",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
    },
    "recover-stale-scans": {
        "task": "src.tasks.scanner.recover_stale_scans",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
    "purge-expired-consent-records": {
        "task": "src.tasks.retention.purge_expired_consent_records",
        "schedule": crontab(hour="1", minute="0"),  # Daily at 01:00 UTC
    },
    "telemetry-heartbeat": {
        "task": "src.tasks.telemetry.send_heartbeat",
        "schedule": crontab(hour="2", minute="30"),  # Daily at 02:30 UTC
    },
    "iab-gvl-refresh": {
        "task": "src.tasks.iab_gvl.refresh_gvl",
        "schedule": crontab(hour="3", minute="15"),  # Daily at 03:15 UTC
    },
}

# ── Explicit task imports ───────────────────────────────────────────
# Must be at the bottom to avoid circular imports. These ensure the
# worker process registers all @app.task definitions on startup.
import src.tasks.iab_gvl  # noqa: E402
import src.tasks.retention  # noqa: E402
import src.tasks.scanner  # noqa: E402
import src.tasks.telemetry  # noqa: E402, F401

try:
    import ee.api.src.tasks.compliance_scanner
    import ee.api.src.tasks.compliance_scoring
    import ee.api.src.tasks.retention  # noqa: F401

    app.conf.beat_schedule.update(
        {
            "check-scheduled-compliance-scans": {
                "task": "src.tasks.compliance_scanner.check_scheduled_compliance_scans",
                "schedule": crontab(hour="3", minute="0"),
            },
            "compute-daily-compliance-scores": {
                "task": "src.tasks.compliance_scoring.compute_daily_scores",
                "schedule": crontab(hour="4", minute="0"),
            },
            "run-retention-purge": {
                "task": "src.tasks.retention.run_retention_purge",
                "schedule": crontab(hour="2", minute="0"),
            },
        }
    )
except ImportError:
    pass
