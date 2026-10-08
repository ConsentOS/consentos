"""Unit tests for site domain matching."""

import logging
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.services.site_domains import (
    host_matches_site,
    normalise_host,
    request_source_url,
    require_host_on_site,
    require_request_from_site,
    site_domains,
    url_host,
)


def _site(domain="example.com", additional_domains=None):
    return SimpleNamespace(id=uuid.uuid4(), domain=domain, additional_domains=additional_domains)


def _request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw})


class TestUrlHost:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://Example.COM:8443/path", "example.com"),
            ("http://shop.example.com", "shop.example.com"),
            ("null", None),
            ("", None),
            (None, None),
            ("http://[::1", None),
        ],
    )
    def test_url_host(self, url, expected):
        assert url_host(url) == expected


class TestSiteDomains:
    def test_normalises_primary_and_additional(self):
        site = _site(
            "WWW.Example.com",
            ["https://example.org/", ".cdn.example.net", "", "  "],
        )
        assert site_domains(site) == {"example.com", "example.org", "cdn.example.net"}

    def test_handles_missing_additional_domains(self):
        assert site_domains(_site()) == {"example.com"}


class TestHostMatchesSite:
    @pytest.mark.parametrize(
        "host",
        [
            "example.com",
            "EXAMPLE.com",
            "www.example.com",
            "a.b.example.com",
            ".example.com",
            "example.org",
            "shop.example.org",
        ],
    )
    def test_matches(self, host):
        assert host_matches_site(host, _site(additional_domains=["example.org"]))

    @pytest.mark.parametrize(
        "host",
        [None, "", ".", "other.test", "notexample.com", "example.com.other.test", "com"],
    )
    def test_does_not_match(self, host):
        assert not host_matches_site(host, _site(additional_domains=["example.org"]))

    def test_www_registered_domain_covers_apex(self):
        assert host_matches_site("example.com", _site("www.example.com"))


class TestNormalisation:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Example.COM", "example.com"),
            ("localhost:3000", "localhost"),
            ("example.com/shop?x=1", "example.com"),
            ("https://example.com:8443/path", "example.com"),
            ("example.com.", "example.com"),
            ("bücher.de", "xn--bcher-kva.de"),
            ("xn--bcher-kva.de", "xn--bcher-kva.de"),
            ("a..b", ""),
            (f"{'a' * 64}.com", ""),
            (None, ""),
        ],
    )
    def test_normalise_host(self, value, expected):
        assert normalise_host(value) == expected

    def test_invalid_registered_domain_skipped(self):
        assert site_domains(_site("example.com", [f"{'a' * 64}.com"])) == {"example.com"}

    @pytest.mark.parametrize(
        ("registered", "host"),
        [
            ("localhost:3000", url_host("http://localhost:3000")),
            ("example.com/shop", "example.com"),
            ("example.com.", "shop.example.com"),
            ("bücher.de", "xn--bcher-kva.de"),
            ("xn--bcher-kva.de", "bücher.de"),
            ("bücher.de", "shop.bücher.de"),
        ],
    )
    def test_registered_and_request_hosts_normalised(self, registered, host):
        assert host_matches_site(host, _site(registered))


class TestRequestSourceUrl:
    def test_no_headers(self):
        assert request_source_url(_request({})) is None

    def test_origin_preferred(self):
        headers = {"Origin": "https://example.com", "Referer": "https://other.test/"}
        assert request_source_url(_request(headers)) == "https://example.com"

    def test_referer_without_origin(self):
        assert request_source_url(_request({"Referer": "https://x.test/p"})) == "https://x.test/p"

    @pytest.mark.parametrize("origin", ["null", "NULL", " null "])
    def test_null_origin_treated_as_absent(self, origin):
        assert request_source_url(_request({"Origin": origin})) is None
        assert (
            request_source_url(_request({"Origin": origin, "Referer": "https://x.test/"}))
            == "https://x.test/"
        )


class TestRequireRequestFromSite:
    def test_no_headers_accepted(self):
        require_request_from_site(_request({}), _site())

    def test_null_origin_without_referer_accepted(self):
        require_request_from_site(_request({"Origin": "null"}), _site())

    @pytest.mark.parametrize(
        "headers",
        [
            {"Origin": "https://example.com"},
            {"Referer": "https://www.example.com/page"},
            {"Origin": "null", "Referer": "https://example.com/page"},
        ],
    )
    def test_matching_accepted(self, headers):
        require_request_from_site(_request(headers), _site())

    @pytest.mark.parametrize(
        "headers",
        [
            {"Origin": "https://other.test"},
            {"Referer": "https://other.test/page"},
            {"Origin": "null", "Referer": "https://other.test/page"},
            {"Origin": "not a url"},
        ],
    )
    def test_mismatch_rejected(self, headers):
        with pytest.raises(HTTPException) as exc:
            require_request_from_site(_request(headers), _site())
        assert exc.value.status_code == 403

    @pytest.mark.parametrize(
        "headers",
        [
            {"Host": "cmp.example.net", "Origin": "https://cmp.example.net"},
            {"Host": "cmp.example.net:8000", "Origin": "http://cmp.example.net:8000"},
            {"Host": "CMP.example.net", "Referer": "https://cmp.example.net/c/1/cookies"},
        ],
    )
    def test_own_host_accepted(self, headers):
        require_request_from_site(_request(headers), _site())

    def test_other_host_still_rejected_when_host_header_present(self):
        headers = {"Host": "cmp.example.net", "Origin": "https://other.test"}
        with pytest.raises(HTTPException) as exc:
            require_request_from_site(_request(headers), _site())
        assert exc.value.status_code == 403

    def test_rejection_logged_with_site_and_host_only(self, caplog):
        site = _site()
        request = _request({"Origin": "https://other.test", "Referer": "https://other.test/a?b=c"})
        with (
            caplog.at_level(logging.WARNING, logger="src.services.site_domains"),
            pytest.raises(HTTPException),
        ):
            require_request_from_site(request, site)
        [record] = caplog.records
        assert record.levelno == logging.WARNING
        message = record.getMessage()
        assert str(site.id) in message
        assert "other.test" in message
        assert "https://" not in message


class TestRequireHostOnSite:
    def test_match_accepted(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.services.site_domains"):
            require_host_on_site("shop.example.com", _site(), detail="Page URL does not match site")
        assert caplog.records == []

    def test_mismatch_rejected_and_logged(self, caplog):
        site = _site()
        with (
            caplog.at_level(logging.WARNING, logger="src.services.site_domains"),
            pytest.raises(HTTPException) as exc,
        ):
            require_host_on_site("other.test", site, detail="Page URL does not match site")
        assert exc.value.status_code == 403
        assert exc.value.detail == "Page URL does not match site"
        [record] = caplog.records
        assert record.levelno == logging.WARNING
        assert str(site.id) in record.getMessage()
        assert "other.test" in record.getMessage()
