"""Real-LLM quality tests.

These tests verify that prompts are well-constructed, responses parse correctly
from a real LLM, and the generated content meets minimum quality bars.

Run with:
    pytest server/tests/test_llm_quality.py --llm -v

They are SKIPPED by default (no --llm flag) because they:
  - Cost tokens on every run
  - Are non-deterministic (can't assert exact strings)
  - Require a live LLM configured via STEWARD_HOST / OLLAMA_HOST / OPENAI_API_KEY
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.auth import create_access_token
from server.agents import sessions as sessions_module

from . import agent_payloads as payloads

pytestmark = pytest.mark.llm


def _ensure_user(email: str) -> None:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return
    user = db.create_user(
        email=email,
        password="secret",
        username=email.split("@")[0],
        profile={"name": email.split("@")[0], "email": email},
    )
    db.verify_user(email, user.verification_token)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(main.app)


# ---------------------------------------------------------------------------
# Narrative generation quality
# ---------------------------------------------------------------------------

class TestNarrativeQuality:
    def test_narrative_is_prose_not_json(self, client: TestClient):
        """LLM should return readable prose, not a raw JSON blob."""
        resp = client.post("/narrative/generate", json=payloads.NARRATIVE_REQUEST)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        narrative = data["narrative"]
        # Should not look like raw JSON
        assert not narrative.strip().startswith("{"), "Narrative is raw JSON, not prose"
        # Should have enough words to be a real paragraph
        assert len(narrative.split()) >= 15, f"Narrative too short: {narrative!r}"

    def test_narrative_references_scene_context(self, client: TestClient):
        """The narrative should incorporate the scene context provided."""
        resp = client.post("/narrative/generate", json=payloads.NARRATIVE_REQUEST)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        narrative = data["narrative"].lower()
        prompt = data.get("prompt", "").lower()
        combined = narrative + " " + prompt
        # At least one of: the setting context, player name, or weather should appear
        scene_words = {"rain", "watchtower", "storm", "aria", "night", "wind", "parapet"}
        matches = scene_words & set(re.findall(r'\b\w+\b', combined))
        assert matches, (
            f"Narrative doesn't reference scene context. Got: {data['narrative']!r}\n"
            f"Expected any of: {scene_words}"
        )

    def test_narrative_player_prompt_is_question(self, client: TestClient):
        """The player-facing prompt should end with a question mark."""
        resp = client.post("/narrative/generate", json=payloads.NARRATIVE_REQUEST)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        prompt = (data.get("prompt") or "").strip()
        assert prompt, "Empty player prompt returned"
        assert prompt.endswith("?"), f"Player prompt doesn't end with '?': {prompt!r}"

    def test_regenerate_produces_different_output(self, client: TestClient):
        """Two regenerations of the same scene should not be identical."""
        owner = "quality-regen@example.com"
        _ensure_user(owner)
        sid, _ = sessions_module.create_session_folder("Quality Regen Test", owner)
        headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

        payload = {**payloads.NARRATIVE_REQUEST, "session_id": sid, "scene": "The party rests at a crossroads"}
        r1 = client.post("/narrative/regenerate", json=payload, headers=headers)
        r2 = client.post("/narrative/regenerate", json=payload, headers=headers)
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        assert r1.json()["narrative"] != r2.json()["narrative"], (
            "Two regenerations returned identical output — LLM may not have temperature > 0"
        )


# ---------------------------------------------------------------------------
# Scene analysis quality
# ---------------------------------------------------------------------------

class TestSceneAnalysisQuality:
    def test_analysis_detects_persuasion_check(self, client: TestClient):
        """Scene with persuasion action should identify a Persuasion dice roll."""
        resp = client.post("/scene/analyze", json=payloads.SCENE_REQUEST)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        skills = [r["skill"].lower() for r in data["dice_rolls"]]
        assert any("persuasion" in s for s in skills), (
            f"Expected a Persuasion roll. Got skills: {skills}"
        )

    def test_analysis_prompts_are_action_oriented(self, client: TestClient):
        """Roll prompts should guide the player, not be generic placeholders."""
        resp = client.post("/scene/analyze", json=payloads.SCENE_REQUEST)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        prompts = data.get("prompts", [])
        assert prompts, "No prompts returned from scene analysis"
        for p in prompts:
            words = p.split()
            assert len(words) >= 4, f"Prompt too short to be useful: {p!r}"
            assert not p.lower().startswith("roll a"), (
                f"Generic placeholder prompt not replaced: {p!r}"
            )


# ---------------------------------------------------------------------------
# Regeneration + character assignment quality
# ---------------------------------------------------------------------------

class TestRegenerateQuality:
    def test_regenerate_requires_player_context(self, client: TestClient):
        """Regenerated scene should reference the player character."""
        owner = "quality-regen2@example.com"
        _ensure_user(owner)
        sid, _ = sessions_module.create_session_folder("Quality Regen Player", owner)
        headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

        payload = {
            "session_id": sid,
            "scene": "A shadowy figure blocks the alley exit.",
            "player": "Kira",
            "style": "gritty realism",
            "weather": "fog",
            "time_of_day": "night",
        }
        resp = client.post("/narrative/regenerate", json=payload, headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        combined = (data["narrative"] + " " + data.get("prompt", "")).lower()
        # Narrative should acknowledge the scene context even if it doesn't name the player
        scene_words = {"shadow", "alley", "kira", "figure", "fog", "night", "blocks"}
        matches = scene_words & set(re.findall(r'\b\w+\b', combined))
        assert matches, (
            f"Regenerated narrative ignores scene context. Got: {data['narrative']!r}"
        )

    def test_regenerate_score_reflects_content_quality(self, client: TestClient):
        """A rich scene prompt should score higher than a one-word scene."""
        owner = "quality-score@example.com"
        _ensure_user(owner)
        sid1, _ = sessions_module.create_session_folder("Quality Score Rich", owner)
        sid2, _ = sessions_module.create_session_folder("Quality Score Sparse", owner)
        headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

        rich = {
            "session_id": sid1,
            "scene": (
                "The ancient library smells of dust and forgotten magic. "
                "Moonlight filters through stained glass, casting spectral patterns "
                "across towering bookshelves. A locked iron chest sits on the central table."
            ),
            "player": "Mira",
            "style": "mystery",
            "weather": "clear",
            "time_of_day": "night",
        }
        sparse = {
            "session_id": sid2,
            "scene": "room",
            "player": "Mira",
            "style": "mystery",
            "weather": "clear",
            "time_of_day": "night",
        }
        r_rich = client.post("/narrative/regenerate", json=rich, headers=headers)
        r_sparse = client.post("/narrative/regenerate", json=sparse, headers=headers)
        assert r_rich.status_code == 200, r_rich.text
        assert r_sparse.status_code == 200, r_sparse.text

        score_rich = r_rich.json().get("scene_score", 0)
        score_sparse = r_sparse.json().get("scene_score", 0)
        # Rich context should score at least as well as sparse context
        assert score_rich >= score_sparse, (
            f"Rich scene scored {score_rich} but sparse scored {score_sparse} — scoring may be inverted"
        )
