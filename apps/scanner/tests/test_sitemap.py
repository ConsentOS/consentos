"""Tests for sitemap URL discovery — CMP-21."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.sitemap import _fetch_sitemap, _find_sitemap_in_robots, discover_urls

# ── Helpers ─────────────────────────────────────────────────────────────


def _make_response(status_code: int = 200, text: str = "") -> httpx.Response:
    """Build a fake httpx.Response."""
    return httpx.Response(
        status_code=status_code, text=text, request=httpx.Request("GET", "http://x")
    )


SITEMAP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
  <url><loc>https://example.com/page3</loc></url>
</urlset>
"""

SITEMAP_INDEX_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-main.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-blog.xml</loc></sitemap>
</sitemapindex>
"""

CHILD_SITEMAP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/blog/post1</loc></url>
  <url><loc>https://example.com/blog/post2</loc></url>
</urlset>
"""

ROBOTS_TXT_WITH_SITEMAP = """\
User-agent: *
Disallow: /admin/
Sitemap: https://example.com/custom-sitemap.xml
"""

ROBOTS_TXT_NO_SITEMAP = """\
User-agent: *
Disallow: /admin/
"""


# ── _fetch_sitemap ─────────────────────────────────────────────────────


class TestFetchSitemap:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_parses_regular_sitemap(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_make_response(200, SITEMAP_XML))

        urls = await _fetch_sitemap(client, "https://example.com/sitemap.xml", 50)

        assert urls == [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
        ]

    @pytest.mark.asyncio(loop_scope="session")
    async def test_respects_max_urls(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_make_response(200, SITEMAP_XML))

        urls = await _fetch_sitemap(client, "https://example.com/sitemap.xml", 2)

        assert len(urls) == 2

    @pytest.mark.asyncio(loop_scope="session")
    async def test_handles_sitemap_index(self):
        """Sitemap index should recursively fetch child sitemaps."""
        responses = {
            "https://example.com/sitemap.xml": _make_response(200, SITEMAP_INDEX_XML),
            "https://example.com/sitemap-main.xml": _make_response(200, SITEMAP_XML),
            "https://example.com/sitemap-blog.xml": _make_response(200, CHILD_SITEMAP_XML),
        }

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=lambda url: responses[url])

        urls = await _fetch_sitemap(client, "https://example.com/sitemap.xml", 50)

        assert len(urls) == 5
        assert "https://example.com/page1" in urls
        assert "https://example.com/blog/post1" in urls

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sitemap_index_respects_max_urls(self):
        """Should stop fetching child sitemaps once max_urls is reached."""
        responses = {
            "https://example.com/sitemap.xml": _make_response(200, SITEMAP_INDEX_XML),
            "https://example.com/sitemap-main.xml": _make_response(200, SITEMAP_XML),
            "https://example.com/sitemap-blog.xml": _make_response(200, CHILD_SITEMAP_XML),
        }

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=lambda url: responses[url])

        urls = await _fetch_sitemap(client, "https://example.com/sitemap.xml", 3)

        assert len(urls) == 3

    @pytest.mark.asyncio(loop_scope="session")
    async def test_returns_empty_on_404(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_make_response(404))

        urls = await _fetch_sitemap(client, "https://example.com/sitemap.xml", 50)

        assert urls == []

    @pytest.mark.asyncio(loop_scope="session")
    async def test_returns_empty_on_invalid_xml(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_make_response(200, "not xml at all"))

        urls = await _fetch_sitemap(client, "https://example.com/sitemap.xml", 50)

        assert urls == []

    @pytest.mark.asyncio(loop_scope="session")
    async def test_returns_empty_on_network_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        urls = await _fetch_sitemap(client, "https://example.com/sitemap.xml", 50)

        assert urls == []

    @pytest.mark.asyncio(loop_scope="session")
    async def test_empty_urlset(self):
        empty_sitemap = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
</urlset>
"""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_make_response(200, empty_sitemap))

        urls = await _fetch_sitemap(client, "https://example.com/sitemap.xml", 50)

        assert urls == []


# ── _find_sitemap_in_robots ────────────────────────────────────────────


class TestFindSitemapInRobots:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_finds_sitemap_directive(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_make_response(200, ROBOTS_TXT_WITH_SITEMAP))

        url = await _find_sitemap_in_robots(client, "https://example.com/robots.txt")

        assert url == "https://example.com/custom-sitemap.xml"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_returns_none_when_no_directive(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_make_response(200, ROBOTS_TXT_NO_SITEMAP))

        url = await _find_sitemap_in_robots(client, "https://example.com/robots.txt")

        assert url is None

    @pytest.mark.asyncio(loop_scope="session")
    async def test_returns_none_on_404(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_make_response(404))

        url = await _find_sitemap_in_robots(client, "https://example.com/robots.txt")

        assert url is None

    @pytest.mark.asyncio(loop_scope="session")
    async def test_returns_none_on_network_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        url = await _find_sitemap_in_robots(client, "https://example.com/robots.txt")

        assert url is None

    @pytest.mark.asyncio(loop_scope="session")
    async def test_case_insensitive_directive(self):
        robots = "User-agent: *\nsITEMAP: https://example.com/sm.xml\n"
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_make_response(200, robots))

        url = await _find_sitemap_in_robots(client, "https://example.com/robots.txt")

        assert url == "https://example.com/sm.xml"


# ── discover_urls ──────────────────────────────────────────────────────


class TestDiscoverUrls:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("src.sitemap._fetch_sitemap")
    @patch("src.sitemap._find_sitemap_in_robots")
    async def test_returns_sitemap_urls(self, mock_robots, mock_sitemap):
        """Should return URLs from /sitemap.xml when available."""
        mock_sitemap.return_value = [
            "https://example.com/page1",
            "https://example.com/page2",
        ]

        urls = await discover_urls("example.com")

        assert urls == ["https://example.com/page1", "https://example.com/page2"]
        mock_robots.assert_not_called()

    @pytest.mark.asyncio(loop_scope="session")
    @patch("src.sitemap._fetch_sitemap")
    @patch("src.sitemap._find_sitemap_in_robots")
    async def test_falls_back_to_robots_txt(self, mock_robots, mock_sitemap):
        """When sitemap.xml returns nothing, should try robots.txt."""
        mock_sitemap.side_effect = [[], ["https://example.com/from-robots"]]
        mock_robots.return_value = "https://example.com/alt-sitemap.xml"

        urls = await discover_urls("example.com")

        assert urls == ["https://example.com/from-robots"]

    @pytest.mark.asyncio(loop_scope="session")
    @patch("src.sitemap._fetch_sitemap")
    @patch("src.sitemap._find_sitemap_in_robots")
    async def test_falls_back_to_default_paths(self, mock_robots, mock_sitemap):
        """When no sitemap exists, should return default paths."""
        mock_sitemap.return_value = []
        mock_robots.return_value = None

        urls = await discover_urls("example.com")

        assert "https://example.com/" in urls
        assert "https://example.com/privacy" in urls
        assert "https://example.com/cookie-policy" in urls

    @pytest.mark.asyncio(loop_scope="session")
    @patch("src.sitemap._fetch_sitemap")
    @patch("src.sitemap._find_sitemap_in_robots")
    async def test_respects_max_urls(self, mock_robots, mock_sitemap):
        many_urls = [f"https://example.com/page{i}" for i in range(100)]
        mock_sitemap.return_value = many_urls

        urls = await discover_urls("example.com", max_urls=5)

        assert len(urls) == 5

    @pytest.mark.asyncio(loop_scope="session")
    @patch("src.sitemap._fetch_sitemap")
    @patch("src.sitemap._find_sitemap_in_robots")
    async def test_default_paths_respect_max_urls(self, mock_robots, mock_sitemap):
        mock_sitemap.return_value = []
        mock_robots.return_value = None

        urls = await discover_urls("example.com", max_urls=3)

        assert len(urls) == 3


# ── Domain filtering ───────────────────────────────────────────────────

MIXED_SITEMAP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>http://169.254.169.254/page</loc></url>
  <url><loc>https://blog.example.com/post</loc></url>
  <url><loc>https://other.org/page</loc></url>
  <url><loc>file:///etc/hosts</loc></url>
</urlset>
"""

MIXED_INDEX_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>http://localhost:8080/sitemap.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-blog.xml</loc></sitemap>
</sitemapindex>
"""


class TestSitemapDomainFiltering:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_drops_urls_outside_site_domains(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_make_response(200, MIXED_SITEMAP_XML))

        urls = await _fetch_sitemap(client, "https://example.com/sitemap.xml", 50, ["example.com"])

        assert urls == ["https://example.com/page1", "https://blog.example.com/post"]

    @pytest.mark.asyncio(loop_scope="session")
    async def test_skips_child_sitemaps_outside_site_domains(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(
            side_effect=[
                _make_response(200, MIXED_INDEX_XML),
                _make_response(200, CHILD_SITEMAP_XML),
            ]
        )

        urls = await _fetch_sitemap(client, "https://example.com/sitemap.xml", 50, ["example.com"])

        assert urls == ["https://example.com/blog/post1", "https://example.com/blog/post2"]
        fetched = [call.args[0] for call in client.get.call_args_list]
        assert "http://localhost:8080/sitemap.xml" not in fetched

    @pytest.mark.asyncio(loop_scope="session")
    @patch("src.sitemap._fetch_sitemap")
    @patch("src.sitemap._find_sitemap_in_robots")
    async def test_ignores_robots_sitemap_on_other_domain(self, mock_robots, mock_sitemap):
        mock_sitemap.return_value = []
        mock_robots.return_value = "http://10.0.0.1/sitemap.xml"

        urls = await discover_urls("www.example.com")

        assert mock_sitemap.call_count == 1
        assert urls[0] == "https://www.example.com/"

    @pytest.mark.asyncio(loop_scope="session")
    @patch("src.sitemap._fetch_sitemap")
    @patch("src.sitemap._find_sitemap_in_robots")
    async def test_robots_sitemap_on_additional_domain(self, mock_robots, mock_sitemap):
        mock_sitemap.side_effect = [[], ["https://shop.example.org/a"]]
        mock_robots.return_value = "https://shop.example.org/sitemap.xml"

        urls = await discover_urls("example.com", additional_domains=["shop.example.org"])

        assert urls == ["https://shop.example.org/a"]
        assert mock_sitemap.call_args.args[3] == ["example.com", "shop.example.org"]
