"""Conservative, allowlisted SEC HTTP client. No authentication or paid API."""
from __future__ import annotations

import re
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener

SEC_HOSTS = frozenset({"www.sec.gov", "sec.gov", "efts.sec.gov", "data.sec.gov"})
UA_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


class SECRequestError(RuntimeError):
    def __init__(self, url: str, status: str, message: str):
        self.url = url
        self.status = status
        super().__init__(f"{status}: {message}: {url}")


def validate_sec_url(url: str) -> None:
    parts = urlparse(url)
    if parts.scheme != "https" or parts.hostname not in SEC_HOSTS or parts.username or parts.password or parts.port:
        raise ValueError(f"SEC URL not allowlisted: {url}")


def validate_user_agent(user_agent: str) -> None:
    # SEC asks automated clients to identify a responsible contact.
    if len(user_agent.strip()) < 10 or not UA_EMAIL_RE.search(user_agent):
        raise ValueError("Provide a descriptive --user-agent with a real contact email; no fabricated default")


class _AllowlistedRedirect(HTTPRedirectHandler):
    """Prevent even the first HTTP request to a redirect outside SEC's domains."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_sec_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class SECClient:
    def __init__(self, user_agent: str, requests_per_second: float = 1.0,
                 retries: int = 2, max_bytes: int = 30_000_000,
                 timeout: float = 25.0, sleep=time.sleep, clock=time.monotonic):
        validate_user_agent(user_agent)
        if not 0 < requests_per_second <= 5.0:
            raise ValueError("For this research tool, requests_per_second must be in (0,5]")
        if max_bytes < 10_000:
            raise ValueError("max_bytes too small")
        self.user_agent = user_agent
        self.interval = 1.0 / requests_per_second
        self.retries = retries
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.sleep = sleep
        self.clock = clock
        self._last_request = None
        self._opener = build_opener(_AllowlistedRedirect())

    def _pace(self):
        if self._last_request is not None:
            pause = self.interval - (self.clock() - self._last_request)
            if pause > 0:
                self.sleep(pause)
        self._last_request = self.clock()

    def fetch(self, url: str) -> bytes:
        validate_sec_url(url)
        for attempt in range(self.retries + 1):
            self._pace()
            req = Request(url, headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/json,text/plain,application/pdf,*/*;q=0.8",
            })
            try:
                with self._opener.open(req, timeout=self.timeout) as resp:
                    final_url = resp.geturl()
                    validate_sec_url(final_url)  # Reject a redirect to an unexpected host.
                    data = resp.read(self.max_bytes + 1)
                    if len(data) > self.max_bytes:
                        raise SECRequestError(url, "TOO_LARGE", f"Document exceeds {self.max_bytes} bytes")
                    return data
            except HTTPError as err:
                status = err.code
                # Do not retry access-denied pages or attempt evasion.
                if status not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise SECRequestError(url, f"HTTP_{status}", str(err)) from err
                retry_after = err.headers.get("Retry-After", "")
                delay = min(60, 2 ** attempt)
                if retry_after.isdigit():
                    delay = max(delay, min(60, int(retry_after)))
                else:
                    try:
                        delay = max(delay, min(60, (parsedate_to_datetime(retry_after) - datetime.now(parsedate_to_datetime(retry_after).tzinfo)).total_seconds()))
                    except (ValueError, TypeError, OverflowError, AttributeError):
                        pass
                self.sleep(delay)
            except URLError as err:
                if attempt == self.retries:
                    raise SECRequestError(url, "NETWORK", str(err)) from err
                self.sleep(min(60, 2 ** attempt))
        raise AssertionError("Unreachable")
