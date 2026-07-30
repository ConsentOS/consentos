"""Integration tests for the per-site consent dashboard API (requires database)."""

import uuid

from httpx import AsyncClient

from tests.conftest import create_test_site, requires_db


async def _record(
    client: AsyncClient,
    site_id: str,
    action: str,
    accepted: list[str],
    rejected: list[str],
) -> None:
    resp = await client.post(
        "/api/v1/consent/",
        json={
            "site_id": site_id,
            "visitor_id": str(uuid.uuid4()),
            "action": action,
            "categories_accepted": accepted,
            "categories_rejected": rejected,
        },
    )
    assert resp.status_code == 201, resp.text


async def _seed_mix(client: AsyncClient, site_id: str) -> None:
    """Two accepts, one partial, one decline, one withdrawal."""
    await _record(client, site_id, "accept_all", ["necessary", "analytics", "marketing"], [])
    await _record(client, site_id, "accept_all", ["necessary", "analytics", "marketing"], [])
    await _record(client, site_id, "custom", ["necessary", "analytics"], ["marketing"])
    await _record(client, site_id, "reject_all", ["necessary"], ["analytics", "marketing"])
    await _record(client, site_id, "withdraw", [], ["necessary", "analytics", "marketing"])


@requires_db
class TestConsentRates:
    async def test_breakdown_counts(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="an-rates")
        await _seed_mix(db_client, site_id)

        resp = await db_client.get(f"/api/v1/sites/{site_id}/consent-rates", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["total_records"] == 5
        assert data["action_breakdown"] == {
            "accept_all": 2,
            "reject_all": 1,
            "custom": 1,
            "withdraw": 1,
        }
        # (accept_all + custom) / (accept + reject + custom) = 3/4, withdraw excluded
        assert data["consent_rate"] == 0.75

    async def test_rate_is_evidence_based_not_action_based(self, db_client, auth_headers):
        """A custom decision accepting only necessary is not a grant."""
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="an-ev")
        await _record(db_client, site_id, "accept_all", ["necessary", "analytics"], [])
        # 'custom' but only necessary accepted → effectively a decline
        await _record(db_client, site_id, "custom", ["necessary"], ["analytics", "marketing"])

        resp = await db_client.get(f"/api/v1/sites/{site_id}/consent-rates", headers=auth_headers)
        # 2 decisions, only the accept_all granted a non-essential → 1/2
        assert resp.json()["consent_rate"] == 0.5

    async def test_category_rates(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="an-cat")
        await _seed_mix(db_client, site_id)

        resp = await db_client.get(f"/api/v1/sites/{site_id}/consent-rates", headers=auth_headers)
        rates = {c["category"]: c for c in resp.json()["category_rates"]}

        # withdrawals are excluded from category rates.
        # analytics: accepted in 3 (2 accept_all + 1 custom), rejected in 1
        # (reject_all) → 3/4
        assert rates["analytics"]["accepted"] == 3
        assert rates["analytics"]["rejected"] == 1
        assert rates["analytics"]["rate"] == 0.75
        # marketing: accepted in 2 (accept_all x2), rejected in 2
        # (custom + reject_all) → 2/4
        assert rates["marketing"]["accepted"] == 2
        assert rates["marketing"]["rejected"] == 2
        assert rates["marketing"]["rate"] == 0.5

    async def test_empty_site_returns_zeroes(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="an-empty")
        resp = await db_client.get(f"/api/v1/sites/{site_id}/consent-rates", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_records"] == 0
        assert data["consent_rate"] == 0.0
        assert data["category_rates"] == []

    async def test_requires_auth(self, db_client):
        resp = await db_client.get(f"/api/v1/sites/{uuid.uuid4()}/consent-rates")
        assert resp.status_code in (401, 403)

    async def test_unknown_site_is_404(self, db_client, auth_headers):
        resp = await db_client.get(
            f"/api/v1/sites/{uuid.uuid4()}/consent-rates", headers=auth_headers
        )
        assert resp.status_code == 404


@requires_db
class TestConsentTrends:
    async def test_trend_buckets(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="an-trend")
        await _seed_mix(db_client, site_id)

        resp = await db_client.get(
            f"/api/v1/sites/{site_id}/consent-trends",
            params={"granularity": "day", "days": 30},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["granularity"] == "day"
        # all records were created "today" → a single bucket holding the full mix
        assert len(data["data"]) == 1
        point = data["data"][0]
        assert point["total"] == 5
        assert point["accept_all"] == 2
        assert point["custom"] == 1
        assert point["reject_all"] == 1
        assert point["consent_rate"] == 0.75

    async def test_invalid_granularity_is_422(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="an-bad")
        resp = await db_client.get(
            f"/api/v1/sites/{site_id}/consent-trends",
            params={"granularity": "fortnight"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
