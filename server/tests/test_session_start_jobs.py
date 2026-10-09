"""One start pipeline per session; concurrent /start calls join it, and progress is visible."""
from __future__ import annotations

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from server import main
from server.agents import sessions
from server.tests.test_opening_setup import _auth, _create_campaign_session


def _session(client: TestClient, email: str) -> tuple[str, dict]:
    session_id, _ = _create_campaign_session(client, email, "Job Scout")
    return session_id, _auth(email)


def test_concurrent_starts_share_one_pipeline_and_report_progress(monkeypatch):
    calls: list[str] = []

    async def slow_start(session_id, payload, current_user):
        calls.append(session_id)
        sessions._start_progress(session_id, "writing")
        await asyncio.sleep(0.8)
        return {"ok": True, "scene": {"id": "opening", "narrative_body": "x"}}

    monkeypatch.setattr(sessions, "_start_session_impl", slow_start)
    with TestClient(main.app) as client:
        session_id, headers = _session(client, "start-jobs@example.com")
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(client.post, f"/sessions/{session_id}/start", headers=headers, json={}) for _ in range(3)]
            time.sleep(0.3)
            running = client.get(f"/sessions/{session_id}/start-status", headers=headers).json()
            responses = [f.result() for f in futures]
        assert [r.status_code for r in responses] == [200, 200, 200]
        assert all(r.json()["ok"] for r in responses)
        assert calls == [session_id], "three concurrent /start calls must run one pipeline"
        assert running["state"] == "running" and running["stage"] == "writing"
        assert [s["id"] for s in running["stages"]] == [s[0] for s in sessions.START_STAGES]
        assert client.get(f"/sessions/{session_id}/start-status", headers=headers).json()["state"] == "done"

        # a later start (a retry) is a fresh pipeline
        client.post(f"/sessions/{session_id}/start", headers=headers, json={})
        assert len(calls) == 2


def test_a_failed_start_is_reported_and_can_be_retried(monkeypatch):
    attempts = {"n": 0}

    async def flaky(session_id, payload, current_user):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise sessions.HTTPException(status_code=502, detail="model unavailable")
        return {"ok": True, "scene": {"id": "opening"}}

    monkeypatch.setattr(sessions, "_start_session_impl", flaky)
    with TestClient(main.app) as client:
        session_id, headers = _session(client, "start-fail@example.com")
        assert client.post(f"/sessions/{session_id}/start", headers=headers, json={}).status_code == 502
        status = client.get(f"/sessions/{session_id}/start-status", headers=headers).json()
        assert status["state"] == "failed" and "model unavailable" in status["error"]
        assert client.post(f"/sessions/{session_id}/start", headers=headers, json={}).status_code == 200
        assert client.get(f"/sessions/{session_id}/start-status", headers=headers).json()["state"] == "done"


def test_status_is_idle_without_a_scene_and_done_once_one_exists_after_a_restart():
    with TestClient(main.app) as client:
        session_id, headers = _session(client, "start-idle@example.com")
        sessions._START_STATUS.pop(session_id, None)
        meta_path = sessions.BASE / session_id / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["opening_setup"]["completed"] = True  # the questions are answered, so only the start is missing
        meta_path.write_text(json.dumps(meta))
        scene_path = sessions.BASE / session_id / "scene.json"
        scene_path.unlink(missing_ok=True)
        idle = client.get(f"/sessions/{session_id}/start-status", headers=headers).json()
        assert idle["state"] == "idle" and idle["scene_ready"] is False
        scene_path.write_text(json.dumps({"id": "opening", "narrative_body": "The road is quiet."}))
        assert client.get(f"/sessions/{session_id}/start-status", headers=headers).json() == {
            **idle, "state": "done", "scene_ready": True,
        }


def test_start_status_requires_session_membership():
    with TestClient(main.app) as client:
        session_id, _ = _session(client, "start-member@example.com")
        outsider = _auth("not-a-member@example.com")
        assert client.get(f"/sessions/{session_id}/start-status", headers=outsider).status_code in (401, 403)


def test_the_setup_pending_placeholder_is_not_a_ready_scene_and_asks_for_the_questions():
    """A new session's placeholder scene already has narration text; it must not read as 'ready'."""
    with TestClient(main.app) as client:
        session_id, headers = _session(client, "start-placeholder@example.com")
        sessions._START_STATUS.pop(session_id, None)
        scene = json.loads((sessions.BASE / session_id / "scene.json").read_text())
        assert scene.get("setup_pending") and scene.get("narrative_body"), "fixture assumption: the placeholder has text"
        status = client.get(f"/sessions/{session_id}/start-status", headers=headers).json()
        assert status["scene_ready"] is False and status["state"] == "needs_setup"

        # once the questions are answered but nothing has started, the client is told to start it
        meta_path = sessions.BASE / session_id / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["opening_setup"]["completed"] = True
        meta_path.write_text(json.dumps(meta))
        assert client.get(f"/sessions/{session_id}/start-status", headers=headers).json()["state"] == "idle"
