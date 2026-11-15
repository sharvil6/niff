"""Test doubles shared across test modules."""

from pathlib import Path

import httpx2

from niff.ynab import YnabClient

FIXTURES = Path(__file__).parent / "fixtures" / "ynab"
FAKE_TOKEN = "fake-token-must-never-appear-in-output"


class FakeYnab:
    """Stands in for the YNAB API: replays queued fixture responses and records requests."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self._responses: list[httpx2.Response | Exception] = []

    def respond(self, status: int, fixture: str) -> None:
        self._responses.append(httpx2.Response(status, content=(FIXTURES / fixture).read_bytes()))

    def respond_raw(self, status: int, content: bytes) -> None:
        self._responses.append(httpx2.Response(status, content=content))

    def fail(self, exc: Exception) -> None:
        self._responses.append(exc)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def client(self) -> YnabClient:
        return YnabClient(FAKE_TOKEN, transport=httpx2.MockTransport(self._handle))
