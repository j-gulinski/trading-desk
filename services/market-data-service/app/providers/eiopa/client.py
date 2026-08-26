import re
import urllib.parse

from app.providers.base import ProviderClient, ProviderDataError
from app.config import EIOPA_TIMEOUT_SECONDS
from shared.providers import EIOPA

RELEASE_PAGE = "/tools-and-data/risk-free-interest-rate-term-structures_en"
RELEASE_LINK = re.compile(r'href="([^"]*EIOPA_RFR_(\d{8})[^"]*\.zip)"')


class Archive:
    """Stringifies to its size: request logging must never render the archive bytes."""

    def __init__(self, body):
        self.body = body

    def __str__(self):
        return f"<zip archive, {len(self.body)} bytes>"


class EiopaClient(ProviderClient):
    provider = EIOPA
    base_url = "https://www.eiopa.europa.eu"
    timeout_seconds = EIOPA_TIMEOUT_SECONDS

    def __init__(self, api_key=None):
        super().__init__(api_key)
        self._held = None

    def decode_body(self, body):
        if body[:2] == b"PK":
            return {"format": "zip", "archive": Archive(body)}
        text = body.decode("utf-8", errors="replace")
        releases = [
            {"as_of": match.group(2), "href": match.group(1)}
            for match in RELEASE_LINK.finditer(text)
        ]
        return {
            "format": "html",
            "releases": sorted(releases, key=lambda r: r["as_of"])[-1:],
        }

    def classify_body(self, payload):
        if payload["format"] == "html" and not payload["releases"]:
            raise ProviderDataError(
                self.provider, "release page lists no monthly term-structure file"
            )

    def latest_release(self):
        return self.get(RELEASE_PAGE)["releases"][0]

    def monthly_archive(self, href):
        """Returns (archive bytes, fetched) — one release serves every currency."""
        if self._held is not None and self._held[0] == href:
            return self._held[1], False
        parts = urllib.parse.urlsplit(href)
        params = dict(urllib.parse.parse_qsl(parts.query))
        body = self.get(parts.path, params)["archive"].body
        self._held = (href, body)
        return body, True
