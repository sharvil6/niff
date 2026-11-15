"""Minimal YNAB API client: plans and accounts, with delta requests.

Errors never include the token, response bodies or validation details, since those can contain
financial data. See https://api.ynab.com for the API reference.
"""

from dataclasses import dataclass
from types import TracebackType
from typing import Self
from urllib.parse import quote

import httpx2
from pydantic import BaseModel, ValidationError

from niff.store import Account

BASE_URL = "https://api.ynab.com/v1"


class YnabError(Exception):
    def __init__(self, status: int, name: str) -> None:
        super().__init__(f"YNAB request failed: {status} {name}")
        self.status = status
        self.name = name


class YnabRateLimited(YnabError):
    """429: over YNAB's 200 requests per hour. Wait for the next scheduled run."""


@dataclass(frozen=True)
class Plan:
    id: str
    name: str


@dataclass(frozen=True)
class AccountsDelta:
    accounts: list[Account]
    server_knowledge: int


# Response shapes. Fields we don't use are ignored.
class _Plan(BaseModel):
    id: str
    name: str


class _PlansData(BaseModel):
    plans: list[_Plan]


class _PlansResponse(BaseModel):
    data: _PlansData


class _Account(BaseModel):
    id: str
    name: str
    type: str
    on_budget: bool
    closed: bool
    deleted: bool = False
    balance: int  # milliunits


class _AccountsData(BaseModel):
    accounts: list[_Account]
    server_knowledge: int


class _AccountsResponse(BaseModel):
    data: _AccountsData


class _ErrorDetail(BaseModel):
    name: str


class _ErrorResponse(BaseModel):
    error: _ErrorDetail


class YnabClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = BASE_URL,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._http = httpx2.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def list_plans(self) -> list[Plan]:
        body = self._get("/plans")
        data = _parse(_PlansResponse, body).data
        return [Plan(id=p.id, name=p.name) for p in data.plans]

    def get_accounts(self, plan_id: str, last_knowledge: int | None) -> AccountsDelta:
        """All accounts when ``last_knowledge`` is None, otherwise only those changed since."""
        params = {} if last_knowledge is None else {"last_knowledge_of_server": last_knowledge}
        body = self._get(f"/plans/{quote(plan_id, safe='')}/accounts", params)
        data = _parse(_AccountsResponse, body).data
        return AccountsDelta(
            accounts=[
                Account(
                    ynab_account_id=a.id,
                    name=a.name,
                    type=a.type,
                    on_budget=a.on_budget,
                    closed=a.closed,
                    deleted=a.deleted,
                    balance=a.balance,
                )
                for a in data.accounts
            ],
            server_knowledge=data.server_knowledge,
        )

    def _get(self, path: str, params: dict[str, int] | None = None) -> bytes:
        try:
            response = self._http.get(path, params=params)
        except httpx2.HTTPError as exc:
            raise YnabError(0, type(exc).__name__) from None
        if response.status_code == 429:
            raise YnabRateLimited(429, "too_many_requests")
        if not response.is_success:
            raise YnabError(response.status_code, _error_name(response.content))
        return response.content


def _parse[M: BaseModel](model: type[M], body: bytes) -> M:
    try:
        return model.model_validate_json(body)
    except ValidationError:
        # Validation messages echo input values, so don't chain or repeat them.
        raise YnabError(200, "invalid_response") from None


def _error_name(body: bytes) -> str:
    """YNAB errors look like {"error": {"id", "name", "detail"}}; keep only the name."""
    try:
        return _ErrorResponse.model_validate_json(body).error.name
    except ValidationError:
        return "unknown"
