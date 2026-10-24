"""Finding the banner's loader tag and checking an install."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.install_check import (
    ConfigRequest,
    InstallCheckResult,
    LoaderTag,
    find_loader,
    is_config_request,
)
from src.worker import create_app

LOADER = (
    '<script src="https://cmp.example.net/consent-loader.js" data-site-id="site-1" '
    'data-api-base="https://cmp.example.net"></script>'
)


def page(head: str, body: str = "") -> str:
    return f"<!doctype html><html><head>{head}</head><body>{body}</body></html>"


class TestFindLoader:
    def test_reads_the_loader_attributes(self):
        loader = find_loader(page(LOADER))
        assert loader == LoaderTag(
            src="https://cmp.example.net/consent-loader.js",
            site_id="site-1",
            api_base="https://cmp.example.net",
            cdn_base=None,
            is_async=False,
            is_defer=False,
            in_head=True,
            first_script=True,
        )

    def test_reads_the_cdn_base(self):
        tag = LOADER.replace("></script>", ' data-cdn-base="https://cdn.example.net"></script>')
        assert find_loader(page(tag)).cdn_base == "https://cdn.example.net"

    def test_no_loader(self):
        assert find_loader(page('<script src="/app.js"></script>')) is None

    def test_ignores_files_that_only_look_similar(self):
        assert find_loader(page('<script src="/my-consent-loader.js.map"></script>')) is None

    @pytest.mark.parametrize("attribute", ["async", "defer"])
    def test_spots_async_and_defer(self, attribute):
        loader = find_loader(page(LOADER.replace("<script ", f"<script {attribute} ")))
        assert getattr(loader, f"is_{attribute}") is True

    def test_a_script_before_it_means_it_is_not_first(self):
        loader = find_loader(page('<script src="/analytics.js"></script>' + LOADER))
        assert loader.first_script is False

    def test_inline_scripts_before_it_count(self):
        loader = find_loader(page("<script>window.dataLayer = [];</script>" + LOADER))
        assert loader.first_script is False

    def test_scripts_that_do_not_run_do_not_count(self):
        head = (
            '<script type="application/ld+json">{}</script>'
            '<script type="text/plain" data-category="analytics" src="/ga.js"></script>' + LOADER
        )
        assert find_loader(page(head)).first_script is True

    def test_spots_a_loader_in_the_body(self):
        loader = find_loader(page("", body=LOADER))
        assert loader.in_head is False


def test_is_config_request():
    assert is_config_request(
        "https://cmp.example.net/api/v1/config/sites/s1/geo-resolved?locale=en"
    )
    assert not is_config_request("https://cmp.example.net/api/v1/consent/")


# ── Endpoint ─────────────────────────────────────────────────────────


@pytest.fixture
def client():
    return TestClient(create_app())


@patch("src.navigation.NavigationPolicy.is_allowed", new_callable=AsyncMock, return_value=True)
@patch("src.install_check.check_install", new_callable=AsyncMock)
def test_check_install_reports_what_it_found(mock_check, _allowed, client):
    mock_check.return_value = InstallCheckResult(
        url="https://example.com/",
        final_url="https://www.example.com/",
        reachable=True,
        loader=find_loader(page(LOADER)),
        config_requests=[ConfigRequest(url="https://cmp.example.net/x/geo-resolved", status=200)],
        banner_rendered=True,
    )

    resp = client.post("/check-install", json={"url": "https://example.com/"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["final_url"] == "https://www.example.com/"
    assert data["loader"]["site_id"] == "site-1"
    assert data["config_requests"] == [
        {"url": "https://cmp.example.net/x/geo-resolved", "status": 200}
    ]
    assert data["banner_rendered"] is True


def test_check_install_rejects_other_schemes(client):
    resp = client.post("/check-install", json={"url": "file:///etc/passwd"})
    assert resp.status_code == 400


def test_check_install_rejects_private_hosts(client):
    resp = client.post("/check-install", json={"url": "http://127.0.0.1/"})
    assert resp.status_code == 400
