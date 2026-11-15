import httpx2
import pytest

from niff.ynab import Plan, YnabError, YnabRateLimited
from tests.fakes import FAKE_TOKEN, FakeYnab


def test_list_plans_sends_token_and_parses(fake_ynab: FakeYnab) -> None:
    fake_ynab.respond(200, "plans.json")

    with fake_ynab.client() as client:
        plans = client.list_plans()

    assert plans == [Plan(id="fake-plan-id", name="Example Household")]
    request = fake_ynab.requests[0]
    assert request.url.path == "/v1/plans"
    assert request.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"


def test_get_accounts_without_cursor_is_a_full_fetch(fake_ynab: FakeYnab) -> None:
    fake_ynab.respond(200, "accounts_full.json")

    with fake_ynab.client() as client:
        delta = client.get_accounts("fake-plan-id", None)

    assert [a.name for a in delta.accounts] == ["Everyday Checking", "Rewards Card"]
    assert delta.accounts[1].balance == -45_000
    assert delta.server_knowledge == 100
    request = fake_ynab.requests[0]
    assert request.url.path == "/v1/plans/fake-plan-id/accounts"
    assert "last_knowledge_of_server" not in request.url.params


def test_get_accounts_with_cursor_requests_a_delta(fake_ynab: FakeYnab) -> None:
    fake_ynab.respond(200, "accounts_delta.json")

    with fake_ynab.client() as client:
        delta = client.get_accounts("fake-plan-id", 100)

    assert fake_ynab.requests[0].url.params["last_knowledge_of_server"] == "100"
    assert delta.accounts[1].deleted is True
    assert delta.server_knowledge == 105


def test_http_error_raises_ynab_error_with_name_only(fake_ynab: FakeYnab) -> None:
    fake_ynab.respond(401, "error_401.json")

    with fake_ynab.client() as client, pytest.raises(YnabError) as caught:
        client.list_plans()

    assert (caught.value.status, caught.value.name) == (401, "unauthorized")
    assert FAKE_TOKEN not in str(caught.value)


def test_rate_limit_raises_rate_limited(fake_ynab: FakeYnab) -> None:
    fake_ynab.respond_raw(429, b'{"error": {"id": "429", "name": "too_many_requests"}}')

    with fake_ynab.client() as client, pytest.raises(YnabRateLimited):
        client.get_accounts("fake-plan-id", None)


def test_unexpected_response_shape_does_not_echo_data(fake_ynab: FakeYnab) -> None:
    fake_ynab.respond_raw(200, b'{"data": {"accounts": [{"name": "Secret Savings"}]}}')

    with fake_ynab.client() as client, pytest.raises(YnabError) as caught:
        client.get_accounts("fake-plan-id", None)

    assert caught.value.name == "invalid_response"
    assert "Secret Savings" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


def test_network_error_raises_ynab_error(fake_ynab: FakeYnab) -> None:
    fake_ynab.fail(httpx2.ConnectError("connection refused"))

    with fake_ynab.client() as client, pytest.raises(YnabError) as caught:
        client.list_plans()

    assert (caught.value.status, caught.value.name) == (0, "ConnectError")
