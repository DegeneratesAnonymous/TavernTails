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
        # Asking for the questions starts preparing them; let that save land before editing the meta here.
        assert _wait_for(lambda: client.get(f"/sessions/{session_id}/start-status", headers=headers).json()["setup"]["state"] == "ready")

        # once the questions are answered but nothing has started, the client is told to start it
        meta_path = sessions.BASE / session_id / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["opening_setup"]["completed"] = True
        meta_path.write_text(json.dumps(meta))
        assert client.get(f"/sessions/{session_id}/start-status", headers=headers).json()["state"] == "idle"


def _wait_for(predicate, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_opening_questions_are_prepared_in_the_background_once(monkeypatch):
    """The "Continue setup" button used to build the questions inside its own request, which takes minutes
    on the local model; now the status poll starts one shared build and the button opens a finished one."""
    import threading

    real_build = sessions._build_opening_setup_questionnaire
    release = threading.Event()
    builds: list[str] = []

    def slow_build(folder, meta, setup=None):
        builds.append(folder.name)
        release.wait(5)
        return real_build(folder, meta, setup)

    monkeypatch.setattr(sessions, "_build_opening_setup_questionnaire", slow_build)
    with TestClient(main.app) as client:
        session_id, headers = _session(client, "setup-prep@example.com")
        sessions._START_STATUS.pop(session_id, None)
        first = client.get(f"/sessions/{session_id}/start-status", headers=headers).json()
        assert first["state"] == "needs_setup"
        assert first["setup"]["state"] == "preparing"
        assert client.get(f"/sessions/{session_id}/start-status", headers=headers).json()["setup"]["state"] == "preparing"

        # Opening the questions while they are being prepared joins that build instead of starting a second.
        with ThreadPoolExecutor(max_workers=1) as pool:
            opened = pool.submit(client.get, f"/sessions/{session_id}/opening-setup", headers=headers)
            time.sleep(0.2)
            release.set()
            body = opened.result().json()
        assert body["questionnaire"]["questions"]
        assert builds == [session_id]
        assert _wait_for(lambda: client.get(f"/sessions/{session_id}/start-status", headers=headers).json()["setup"]["state"] == "ready")
        saved = json.loads((sessions.BASE / session_id / "meta.json").read_text())["opening_setup"]
        assert saved["questionnaire_id"] == body["questionnaire"]["questionnaire_id"]
        assert builds == [session_id]


def test_questions_that_fail_to_prepare_are_reported_and_can_be_retried(monkeypatch):
    real_build = sessions._build_opening_setup_questionnaire
    attempts = {"n": 0}

    def flaky_build(folder, meta, setup=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("model unavailable")
        return real_build(folder, meta, setup)

    monkeypatch.setattr(sessions, "_build_opening_setup_questionnaire", flaky_build)
    with TestClient(main.app) as client:
        session_id, headers = _session(client, "setup-prep-fail@example.com")
        sessions._START_STATUS.pop(session_id, None)
        status_url = f"/sessions/{session_id}/start-status"
        client.get(status_url, headers=headers)
        assert _wait_for(lambda: client.get(status_url, headers=headers).json()["setup"]["state"] == "failed")
        failed = client.get(status_url, headers=headers).json()["setup"]
        assert "model unavailable" in failed["error"]
        assert attempts["n"] == 1, "a failed build is not retried behind the player's back"

        retried = client.post(f"/sessions/{session_id}/opening-setup/prepare", headers=headers)
        assert retried.status_code == 200 and retried.json()["state"] in ("preparing", "ready")
        assert _wait_for(lambda: client.get(status_url, headers=headers).json()["setup"]["state"] == "ready")
        assert client.get(f"/sessions/{session_id}/opening-setup", headers=headers).json()["questionnaire"]["questions"]


def test_a_request_waiting_on_a_failing_build_shares_the_failure_instead_of_rebuilding(monkeypatch):
    import threading

    release = threading.Event()
    builds: list[str] = []

    def failing_build(folder, meta, setup=None):
        builds.append(folder.name)
        release.wait(5)
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(sessions, "_build_opening_setup_questionnaire", failing_build)
    with TestClient(main.app) as client:
        session_id, headers = _session(client, "setup-prep-shared-fail@example.com")
        sessions._START_STATUS.pop(session_id, None)
        status_url = f"/sessions/{session_id}/start-status"
        client.get(status_url, headers=headers)  # starts the background build, which blocks in failing_build
        assert _wait_for(lambda: builds == [session_id])

        # The player presses the button while the build is still running; that request waits on the build.
        with ThreadPoolExecutor(max_workers=1) as pool:
            waiting = pool.submit(client.get, f"/sessions/{session_id}/opening-setup", headers=headers)
            time.sleep(0.2)
            release.set()
            response = waiting.result()
        assert response.status_code == 503 and "model unavailable" in response.json()["detail"]
        assert builds == [session_id], "the waiter must share the failure, not run the build again"
        assert client.get(status_url, headers=headers).json()["setup"]["state"] == "failed"

        # Only an explicit retry clears the failure and builds again.
        monkeypatch.setattr(sessions, "_build_opening_setup_questionnaire", lambda folder, meta, setup=None: {"questionnaire_id": "q", "questions": [], "campaign_brief": {}})
        assert client.post(f"/sessions/{session_id}/opening-setup/prepare", headers=headers).status_code == 200
        assert _wait_for(lambda: client.get(status_url, headers=headers).json()["setup"]["state"] == "ready")


def test_background_preparation_uses_bounded_daemon_workers_not_a_thread_per_session(monkeypatch):
    import threading

    release = threading.Event()
    started: list[str] = []

    def blocked_build(folder, meta, setup=None):
        started.append(folder.name)
        release.wait(5)
        return {"questionnaire_id": "q", "questions": [], "campaign_brief": {}}

    monkeypatch.setattr(sessions, "_build_opening_setup_questionnaire", blocked_build)
    monkeypatch.setattr(sessions, "_SETUP_PREP_QUEUE", None)
    monkeypatch.setattr(sessions, "_SETUP_PREP_WORKERS", 1)
    with TestClient(main.app) as client:
        first, headers = _session(client, "setup-pool-a@example.com")
        second, headers2 = _session(client, "setup-pool-b@example.com")
        for sid in (first, second):
            sessions._START_STATUS.pop(sid, None)
        before = threading.active_count()
        assert client.get(f"/sessions/{first}/start-status", headers=headers).json()["setup"]["state"] == "preparing"
        assert client.get(f"/sessions/{second}/start-status", headers=headers2).json()["setup"]["state"] == "preparing"
        assert _wait_for(lambda: len(started) >= 1)
        time.sleep(0.2)
        assert started == [first], "with one worker the second session waits its turn"
        assert threading.active_count() <= before + 1
        assert all(t.daemon for t in threading.enumerate() if t.name.startswith("opening-setup")), "workers must not block shutdown"
        release.set()
        assert _wait_for(lambda: client.get(f"/sessions/{second}/start-status", headers=headers2).json()["setup"]["state"] == "ready")
        assert started == [first, second]


def test_questions_prepared_before_a_character_is_chosen_are_rebuilt_for_the_character(monkeypatch):
    """Preparing starts as soon as the questions are owed, which can be before a character is seated; the
    generic "the party" questions must not stay in place once one is."""
    from server import db
    from server.tests.test_opening_setup import _ensure_user

    real_build = sessions._build_opening_setup_questionnaire
    seen: list[tuple[str, dict | None]] = []

    def recording_build(folder, meta, setup=None):
        seen.append((sessions._selected_character_from_meta(meta).get("name", ""), dict((setup or {}).get("seed") or {}) or None))
        return real_build(folder, meta, setup)

    monkeypatch.setattr(sessions, "_build_opening_setup_questionnaire", recording_build)
    with TestClient(main.app) as client:
        session_id, headers = _session(client, "setup-prep-character@example.com")
        status_url = f"/sessions/{session_id}/start-status"
        meta_path = sessions.BASE / session_id / "meta.json"
        meta = json.loads(meta_path.read_text())
        original_members = meta["members"]
        meta["members"] = [{**m, "character_id": None, "character_name": None} for m in original_members]  # nobody seated yet
        meta_path.write_text(json.dumps(meta))
        sessions._START_STATUS.pop(session_id, None)
        sessions._SETUP_PREP.pop(session_id, None)

        client.get(status_url, headers=headers)
        assert _wait_for(lambda: client.get(status_url, headers=headers).json()["setup"]["state"] == "ready")
        first_call = len(seen)
        assert first_call == 1 and seen[0][0] == "the party"

        # Seating a character makes the prepared questions stale: the next status poll rebuilds them.
        user = _ensure_user("setup-prep-character@example.com")
        character = db.create_character(owner_id=user.id, name="Late Arrival", level=2, class_name="Bard", sheet={})
        assert client.post(f"/sessions/{session_id}/character", headers=headers, json={"character_id": character.id}).status_code == 200
        polled = client.get(status_url, headers=headers).json()["setup"]
        assert polled["state"] == "preparing"
        assert _wait_for(lambda: client.get(status_url, headers=headers).json()["setup"]["state"] == "ready")
        assert len(seen) == 2 and seen[1][0] == "Late Arrival"
        assert seen[1][1] == (json.loads(meta_path.read_text())["opening_setup"].get("seed") or None), "the chosen opening is kept, not redrawn"

        # Nothing changed since: no further rebuilds.
        client.get(status_url, headers=headers)
        client.get(f"/sessions/{session_id}/opening-setup", headers=headers)
        assert len(seen) == 2


def test_player_run_tables_do_not_start_preparing_questions_on_their_own(monkeypatch):
    from server import db

    builds: list[str] = []
    monkeypatch.setattr(sessions, "_build_opening_setup_questionnaire", lambda folder, meta, setup=None: builds.append(folder.name) or {"questionnaire_id": "q", "questions": [], "campaign_brief": {}})
    with TestClient(main.app) as client:
        session_id, headers = _session(client, "setup-prep-player-run@example.com")
        meta = json.loads((sessions.BASE / session_id / "meta.json").read_text())
        campaign = db.get_campaign_by_id(str(meta["campaign_id"]))
        db.set_campaign_settings(campaign.id, campaign.owner_id, {"player_run_mode": True})
        sessions._START_STATUS.pop(session_id, None)
        sessions._SETUP_PREP.pop(session_id, None)

        status = client.get(f"/sessions/{session_id}/start-status", headers=headers).json()
        assert status["state"] == "needs_setup" and status["setup"]["state"] == "ready"
        time.sleep(0.3)
        assert builds == [], "opening a human-GM table must not queue model work"


def test_questions_prepared_for_one_player_are_rebuilt_when_another_joins(monkeypatch):
    real_build = sessions._build_opening_setup_questionnaire
    party_modes: list[bool] = []

    def recording_build(folder, meta, setup=None):
        party_modes.append(len(sessions._session_player_names(folder, meta)) > 1)
        return real_build(folder, meta, setup)

    monkeypatch.setattr(sessions, "_build_opening_setup_questionnaire", recording_build)
    with TestClient(main.app) as client:
        session_id, headers = _session(client, "setup-prep-join@example.com")
        status_url = f"/sessions/{session_id}/start-status"
        sessions._START_STATUS.pop(session_id, None)
        sessions._SETUP_PREP.pop(session_id, None)
        client.get(status_url, headers=headers)
        assert _wait_for(lambda: client.get(status_url, headers=headers).json()["setup"]["state"] == "ready")
        assert party_modes == [False]

        meta_path = sessions.BASE / session_id / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["members"].append({"email": "second-player@example.com", "character_id": 987654, "character_name": "Second Player", "role": "member"})
        meta_path.write_text(json.dumps(meta))
        assert client.get(status_url, headers=headers).json()["setup"]["state"] == "preparing"
        assert _wait_for(lambda: client.get(status_url, headers=headers).json()["setup"]["state"] == "ready")
        assert party_modes == [False, True], "the second player turns the table into a party, so the questions are rebuilt"


def test_a_failed_on_demand_build_at_a_player_run_table_is_reported_so_it_can_be_retried(monkeypatch):
    from server import db

    def failing_build(folder, meta, setup=None):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(sessions, "_build_opening_setup_questionnaire", failing_build)
    with TestClient(main.app) as client:
        session_id, headers = _session(client, "setup-prep-player-run-fail@example.com")
        meta = json.loads((sessions.BASE / session_id / "meta.json").read_text())
        campaign = db.get_campaign_by_id(str(meta["campaign_id"]))
        db.set_campaign_settings(campaign.id, campaign.owner_id, {"player_run_mode": True})
        sessions._START_STATUS.pop(session_id, None)
        sessions._SETUP_PREP.pop(session_id, None)
        status_url = f"/sessions/{session_id}/start-status"

        assert client.get(status_url, headers=headers).json()["setup"]["state"] == "ready"
        assert client.get(f"/sessions/{session_id}/opening-setup", headers=headers).status_code == 503
        failed = client.get(status_url, headers=headers).json()["setup"]
        assert failed["state"] == "failed" and "model unavailable" in failed["error"]
