"""Tests for the anonymous telemetry heartbeat.

Pure unit tests cover bucketing, payload assembly, and the activation
gate. Integration tests (skipped without a test DB) cover instance ID
idempotency and end-to-end collection with a mocked HTTP transport.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import Settings
from src.services import telemetry
from tests.conftest import requires_db

# ── Pure unit tests ──────────────────────────────────────────────────


def test_bucket_zero():
    assert telemetry.bucket(0) == "0"


def test_bucket_negative_treated_as_zero():
    assert telemetry.bucket(-5) == "0"


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (1, "1-10"),
        (9, "1-10"),
        (10, "10-100"),
        (99, "10-100"),
        (100, "100-1k"),
        (999, "100-1k"),
        (1_000, "1k-10k"),
        (9_999, "1k-10k"),
        (10_000, "10k+"),
        (1_000_000, "10k+"),
    ],
)
def test_bucket_boundaries(count: int, expected: str):
    assert telemetry.bucket(count) == expected


def test_detect_deployment_default(monkeypatch):
    monkeypatch.delenv("CONSENTOS_DEPLOYMENT", raising=False)
    assert telemetry.detect_deployment() == "unknown"


def test_detect_deployment_from_env(monkeypatch):
    monkeypatch.setenv("CONSENTOS_DEPLOYMENT", "helm")
    assert telemetry.detect_deployment() == "helm"


def test_telemetry_active_off_in_test_env():
    settings = Settings(environment="test", jwt_secret_key="x")
    assert settings.telemetry_enabled is True
    assert settings.telemetry_active is False


def test_telemetry_active_off_in_dev():
    settings = Settings(environment="development", jwt_secret_key="x")
    assert settings.telemetry_active is False


def test_telemetry_active_on_in_production():
    settings = Settings(
        environment="production",
        jwt_secret_key="strong-secret",
        allowed_origins="https://example.com",
    )
    assert settings.telemetry_active is True


def test_telemetry_active_respects_explicit_opt_out():
    settings = Settings(
        environment="production",
        jwt_secret_key="strong-secret",
        allowed_origins="https://example.com",
        telemetry_enabled=False,
    )
    assert settings.telemetry_active is False


def test_build_payload_shape():
    settings = Settings(environment="test", jwt_secret_key="x")
    payload = telemetry.build_payload(
        instance_id="abc-123",
        settings=settings,
        counts={"orgs": "1-10", "sites": "10-100"},
        features={"tcf_v22_sites": "0", "rate_limit_enabled": True},
        postgres_version="16.2",
    )

    assert payload["telemetry_schema"] == telemetry.TELEMETRY_SCHEMA_VERSION
    assert payload["instance_id"] == "abc-123"
    assert payload["counts"] == {"orgs": "1-10", "sites": "10-100"}
    assert payload["features"]["rate_limit_enabled"] is True
    assert payload["stack"]["postgres_version"] == "16.2"
    # JSON-serialisable — anything we send must round-trip cleanly
    assert json.loads(json.dumps(payload)) == payload


# ── send_heartbeat gating ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_heartbeat_skipped_when_disabled():
    settings = Settings(environment="test", jwt_secret_key="x")
    # ``session`` is never used because the disabled branch returns first
    result = await telemetry.send_heartbeat(session=None, settings=settings)  # type: ignore[arg-type]
    assert result == {"sent": False, "reason": "disabled"}


# ── Integration tests (live DB) ──────────────────────────────────────


@requires_db
async def test_get_or_create_instance_is_idempotent(_test_engine, _setup_db):
    async with AsyncSession(_test_engine, expire_on_commit=False) as session:
        first = await telemetry.get_or_create_instance(session)
        await session.commit()
        second = await telemetry.get_or_create_instance(session)
        assert first.id == second.id


@requires_db
async def test_collect_payload_uses_buckets(_test_engine, _setup_db):
    settings = Settings(environment="test", jwt_secret_key="x")
    async with AsyncSession(_test_engine, expire_on_commit=False) as session:
        payload = await telemetry.collect_payload(session, settings)
        await session.commit()

    # Counts must always be bucket strings, never raw integers
    for value in payload["counts"].values():
        assert value in {"0", "1-10", "10-100", "100-1k", "1k-10k", "10k+"}
    assert "instance_id" in payload
    assert payload["edition"] in {"ce", "ee"}


@requires_db
async def test_send_heartbeat_posts_payload_and_records_timestamp(
    _test_engine,
    _setup_db,
    monkeypatch,
    caplog,
):
    settings = Settings(
        environment="production",
        jwt_secret_key="strong-secret",
        allowed_origins="https://example.com",
        telemetry_endpoint="https://telemetry.example/v1/heartbeat",
    )
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(202)

    transport = httpx.MockTransport(handler)

    class _PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    with (
        patch("src.services.telemetry.httpx.AsyncClient", _PatchedAsyncClient),
        caplog.at_level(logging.INFO, logger="src.services.telemetry"),
    ):
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            result = await telemetry.send_heartbeat(session, settings)

    assert result["sent"] is True
    assert captured["url"] == "https://telemetry.example/v1/heartbeat"
    assert captured["body"]["telemetry_schema"] == 1
    # Audit log: every send must record the payload locally
    assert any("telemetry.payload" in r.message for r in caplog.records)


@requires_db
async def test_send_heartbeat_swallows_network_errors(_test_engine, _setup_db):
    settings = Settings(
        environment="production",
        jwt_secret_key="strong-secret",
        allowed_origins="https://example.com",
        telemetry_endpoint="https://telemetry.example/v1/heartbeat",
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network failure")

    transport = httpx.MockTransport(handler)

    class _PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    with patch("src.services.telemetry.httpx.AsyncClient", _PatchedAsyncClient):
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            result = await telemetry.send_heartbeat(session, settings)

    assert result == {"sent": False, "reason": "network_error"}
