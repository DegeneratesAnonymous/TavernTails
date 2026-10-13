"""A Steward restart (nginx 502/504, refused connection) must not turn into a failed model call."""
import httpx
import pytest

from server import steward_llm


class FakeResponse:
    def __init__(self, status):
        self.status_code = status


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def post(self, url, json=None, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


def _post(client):
    return steward_llm._post_riding_out_restarts(client, "http://x/ai", json={}, timeout=5, sleep=lambda s: None)


def test_a_502_during_a_restart_is_retried_until_steward_answers():
    client = FakeClient([502, 502, httpx.ConnectError("refused"), 200])
    assert _post(client).status_code == 200 and client.calls == 4


def test_a_genuine_model_failure_503_is_not_retried():
    client = FakeClient([503])
    assert _post(client).status_code == 503 and client.calls == 1


def test_it_gives_up_after_the_backoff_budget_and_returns_the_last_answer():
    client = FakeClient([502] * 10)
    assert _post(client).status_code == 502
    assert client.calls == 1 + len(steward_llm._RESTART_BACKOFF_SECONDS)


def test_a_connection_that_never_comes_back_raises_the_connection_error():
    client = FakeClient([httpx.ConnectError("refused")] * 10)
    with pytest.raises(httpx.ConnectError):
        _post(client)


def test_the_total_wait_stays_under_about_forty_seconds():
    assert sum(steward_llm._RESTART_BACKOFF_SECONDS) <= 40.0
