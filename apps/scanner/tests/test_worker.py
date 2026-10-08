"""Tests for the scanner HTTP service."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.worker import create_app


@pytest.fixture
def client():
    """Create a test client for the scanner app."""
    app = create_app()
    return TestClient(app)


def test_health_endpoint(client):
    """Health endpoint returns ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@patch("src.sitemap.discover_urls", new_callable=AsyncMock)
@patch("src.crawler.CookieCrawler.crawl_site", new_callable=AsyncMock)
def test_scan_endpoint_with_domain(mock_crawl, mock_discover, client):
    """POST /scan with just a domain discovers URLs and crawls."""
    from src.crawler import CrawlResult, DiscoveredCookie, SiteCrawlResult

    mock_discover.return_value = ["https://example.com/"]
    mock_crawl.return_value = SiteCrawlResult(
        domain="example.com",
        pages=[
            CrawlResult(
                url="https://example.com/",
                cookies=[
                    DiscoveredCookie(
                        name="_ga",
                        domain=".example.com",
                        storage_type="cookie",
                        page_url="https://example.com/",
                        value_length=30,
                    ),
                    DiscoveredCookie(
                        name="session_id",
                        domain="example.com",
                        storage_type="cookie",
                        page_url="https://example.com/",
                        value_length=36,
                        http_only=True,
                        secure=True,
                    ),
                ],
            ),
        ],
        total_cookies_found=2,
    )

    resp = client.post("/scan", json={"domain": "example.com", "max_pages": 5})
    assert resp.status_code == 200
    data = resp.json()

    assert data["domain"] == "example.com"
    assert data["pages_crawled"] == 1
    assert data["total_cookies"] == 2
    assert len(data["cookies"]) == 2
    assert data["cookies"][0]["name"] == "_ga"
    assert data["cookies"][1]["name"] == "session_id"
    assert data["cookies"][1]["secure"] is True


@patch("src.crawler.CookieCrawler.crawl_site", new_callable=AsyncMock)
def test_scan_endpoint_with_urls(mock_crawl, client):
    """POST /scan with explicit URLs skips URL discovery."""
    from src.crawler import CrawlResult, SiteCrawlResult

    mock_crawl.return_value = SiteCrawlResult(
        domain="example.com",
        pages=[CrawlResult(url="https://example.com/about", cookies=[])],
        total_cookies_found=0,
    )

    resp = client.post(
        "/scan",
        json={
            "domain": "example.com",
            "urls": ["https://example.com/about"],
            "max_pages": 1,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["pages_crawled"] == 1
    assert data["cookies"] == []


@patch("src.sitemap.discover_urls", new_callable=AsyncMock)
@patch("src.crawler.CookieCrawler.crawl_site", new_callable=AsyncMock)
def test_scan_endpoint_with_errors(mock_crawl, mock_discover, client):
    """Scan results include page errors."""
    from src.crawler import CrawlResult, SiteCrawlResult

    mock_discover.return_value = ["https://example.com/"]
    mock_crawl.return_value = SiteCrawlResult(
        domain="example.com",
        pages=[
            CrawlResult(url="https://example.com/", cookies=[], error="Timeout"),
        ],
        total_cookies_found=0,
    )

    resp = client.post("/scan", json={"domain": "example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["errors"] == ["Timeout"]


def test_scan_request_validation(client):
    """Missing domain returns 422."""
    resp = client.post("/scan", json={})
    assert resp.status_code == 422


@pytest.mark.parametrize("domain", ["https://example.com", "example.com/x", "a@127.0.0.1", ""])
def test_scan_rejects_invalid_domain(client, domain):
    """Domains must be bare hostnames."""
    resp = client.post("/scan", json={"domain": domain})
    assert resp.status_code == 400


@patch("src.crawler.CookieCrawler.crawl_site", new_callable=AsyncMock)
def test_scan_only_crawls_urls_on_site_domains(mock_crawl, client):
    """Explicit URLs outside the site's domains are dropped."""
    from src.crawler import SiteCrawlResult

    mock_crawl.return_value = SiteCrawlResult(domain="example.com")

    resp = client.post(
        "/scan",
        json={
            "domain": "www.example.com",
            "additional_domains": ["example.org"],
            "urls": [
                "https://example.com/a",
                "https://shop.example.org/b",
                "http://169.254.169.254/",
                "https://other.net/",
            ],
        },
    )
    assert resp.status_code == 200
    assert mock_crawl.call_args.args[0] == ["https://example.com/a", "https://shop.example.org/b"]


def test_scan_rejects_port_by_default(client):
    """Ports are only accepted when private networks are allowed."""
    resp = client.post("/scan", json={"domain": "localhost:3000"})
    assert resp.status_code == 400


def test_scan_accepts_port_when_private_networks_allowed(monkeypatch):
    """A local development server can be scanned by host and port."""
    from src.crawler import SiteCrawlResult

    monkeypatch.setenv("SCANNER_ALLOW_PRIVATE_NETWORKS", "true")
    with patch("src.crawler.CookieCrawler.crawl_site", new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = SiteCrawlResult(domain="localhost:3000")
        resp = TestClient(create_app()).post(
            "/scan",
            json={"domain": "localhost:3000", "urls": ["http://localhost:3000/about"]},
        )

    assert resp.status_code == 200
    assert mock_crawl.call_args.args[0] == ["http://localhost:3000/about"]


def test_scan_with_only_foreign_urls_is_rejected(client):
    """If no explicit URL is on the site's domains there is nothing to scan."""
    resp = client.post("/scan", json={"domain": "example.com", "urls": ["http://localhost:8080/"]})
    assert resp.status_code == 400


@pytest.mark.parametrize("opt_out", [False, True])
def test_scan_passes_navigation_setting_to_crawler(monkeypatch, opt_out):
    """SCANNER_ALLOW_PRIVATE_NETWORKS reaches the crawler's policy."""
    from src.crawler import SiteCrawlResult

    monkeypatch.setenv("SCANNER_ALLOW_PRIVATE_NETWORKS", str(opt_out).lower())
    captured = {}

    class FakeCrawler:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def crawl_site(self, urls, *, max_pages):
            return SiteCrawlResult(domain="example.com")

    with patch("src.crawler.CookieCrawler", FakeCrawler):
        resp = TestClient(create_app()).post(
            "/scan", json={"domain": "example.com", "urls": ["https://example.com/"]}
        )

    assert resp.status_code == 200
    assert captured["navigation_policy"].allow_private_networks is opt_out


def test_validate_rejects_non_http_url(client):
    """Only http(s) URLs can be validated."""
    resp = client.post("/validate", json={"url": "file:///tmp/page.html"})
    assert resp.status_code == 400


def _mock_playwright(context):
    """Build an ``async_playwright()`` stand-in yielding *context*.

    Returns the stand-in and the mock browser that creates *context*.
    """
    from unittest.mock import MagicMock

    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    pw = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=pw)
    manager.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=manager), browser


@pytest.mark.parametrize("opt_out", [False, True])
def test_validate_applies_navigation_policy(monkeypatch, opt_out):
    """The validation browser context gets the route guard unless opted out."""
    from unittest.mock import MagicMock

    from src.dark_pattern_detector import DarkPatternResult

    monkeypatch.setenv("SCANNER_ALLOW_PRIVATE_NETWORKS", str(opt_out).lower())
    page = AsyncMock()
    page.on = MagicMock()
    locator = MagicMock()
    locator.first.is_visible = AsyncMock(return_value=True)
    locator.first.click = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    playwright_factory, browser = _mock_playwright(context)

    with (
        patch("playwright.async_api.async_playwright", playwright_factory),
        patch("src.consent_validator.validate_pre_consent", AsyncMock(return_value=[])),
        patch("src.consent_validator.validate_post_accept", AsyncMock(return_value=[])),
        patch("src.consent_validator.validate_post_reject", AsyncMock(return_value=[])),
        patch(
            "src.dark_pattern_detector.detect_dark_patterns",
            AsyncMock(
                return_value=DarkPatternResult(url="https://example.com/", banner_found=True)
            ),
        ),
    ):
        resp = TestClient(create_app()).post("/validate", json={"url": "https://example.com/"})

    assert resp.status_code == 200
    assert resp.json()["errors"] == []
    assert resp.json()["banner_found"] is True
    assert context.route.called is not opt_out
    assert browser.new_context.await_args.kwargs["service_workers"] == "block"
