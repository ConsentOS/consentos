# Anonymous telemetry

Self-hosted ConsentOS sends a single anonymous heartbeat once a day so
the project can answer one question: **is anyone running this?** The
heartbeat carries deployment metadata and bucketed scale numbers — no
consent records, no domains, no user data of any kind.

This page documents exactly what is sent, why, and how to disable it.

## What is sent

Every payload looks like this:

```json
{
  "telemetry_schema": 1,
  "instance_id": "0a0b3a8a-7e62-4a4e-9b6f-1a4e2d2dfd99",
  "sent_at": "2026-05-02T02:30:00+00:00",
  "version": "0.1.0",
  "edition": "ce",
  "python_version": "3.12.7",
  "platform": "linux",
  "deployment": "docker-compose",
  "counts": {
    "orgs": "1-10",
    "sites": "10-100",
    "users": "1-10",
    "scans_last_24h": "10-100",
    "consents_last_24h": "100-1k"
  },
  "features": {
    "tcf_v22_sites": "1-10",
    "auto_blocking_sites": "10-100",
    "scanner_scheduled_sites": "1-10",
    "geoip_header_configured": true,
    "geoip_maxmind_configured": false,
    "rate_limit_enabled": true,
    "compliance_ee": false
  },
  "stack": {
    "postgres_version": "16.2",
    "redis_present": true
  }
}
```

### Field reference

| Field | Purpose |
| --- | --- |
| `telemetry_schema` | Integer schema version. Bumped on breaking changes. |
| `instance_id` | Random UUID generated locally on first boot, stored in the `instance` table. Identifies the install, never a person. Wipe the row to rotate. |
| `sent_at` | ISO 8601 UTC timestamp of the send. |
| `version` | ConsentOS API version (`app_version`). |
| `edition` | `"ce"` (community) or `"ee"` (enterprise). |
| `python_version` | Runtime Python version, e.g. `3.12.7`. |
| `platform` | `sys.platform` — `linux`, `darwin`, etc. |
| `deployment` | Operator-supplied label from `CONSENTOS_DEPLOYMENT`. Defaults to `unknown`. |
| `counts.*` | Bucketed entity counts. Buckets are `0`, `1-10`, `10-100`, `100-1k`, `1k-10k`, `10k+`. |
| `features.*` | Feature toggles or bucketed counts of sites using each feature. Booleans are exact; counts are bucketed. |
| `stack.postgres_version` | Postgres `version()` major.minor, e.g. `16.2`. |
| `stack.redis_present` | Always `true` when telemetry sends — Celery beat must be running for the heartbeat to fire at all. |

### What is **not** sent

Categorically, none of the following ever appear in a heartbeat:

- consent records, TC strings or any per-user data
- cookie names, scan results or compliance findings
- site domains or organisation names
- user emails, IDs, hashes or counts that could identify individuals
- IP addresses, request headers or geographic data
- banner copy, translations or any operator-authored content
- secrets, API keys or environment variables

If you find data in the payload that you did not expect, please open an
issue — we treat that as a bug.

## Why we collect it

The project is source-available and self-hosted. Without a heartbeat we
have no idea which versions are still running, which features matter,
or whether the install graph is growing. The heartbeat lets us:

- decide which versions to support and when to deprecate
- prioritise features that are actually being used
- estimate the active install base when planning roadmap

## How to audit what was sent

Every successful send writes the payload to the application log at
`INFO` level with the event name `telemetry.payload`. To inspect the
last few sends:

```bash
docker compose logs api | grep telemetry.payload
```

In Kubernetes, look for `telemetry.payload` in the API pod logs. The
logged JSON is bit-for-bit what was POSTed.

The `instance.last_telemetry_at` column in Postgres records the most
recent successful send.

## How to disable

Set one environment variable on the API container and restart:

```bash
TELEMETRY_ENABLED=false
```

Telemetry is also automatically disabled when `ENVIRONMENT` is
`development`, `dev`, `local` or `test`, so local runs and CI never
phone home.

### docker-compose

```yaml
services:
  api:
    environment:
      TELEMETRY_ENABLED: "false"
```

### Helm

```yaml
api:
  env:
    TELEMETRY_ENABLED: "false"
```

## Endpoint and transport

By default the heartbeat is POSTed to:

```
https://telemetry.consentos.dev/v1/heartbeat
```

Override with `TELEMETRY_ENDPOINT=<url>` to point at your own
collector. Network failures are logged and swallowed — telemetry
must never break the worker.

The send timeout is 10 seconds by default; tune with
`TELEMETRY_TIMEOUT_SECONDS`.

## Schedule

The heartbeat runs daily at 02:30 UTC via Celery beat
(`telemetry-heartbeat` in `src/celery_app.py`). It is independent of
all other scheduled jobs and a failure in one never affects the other.
