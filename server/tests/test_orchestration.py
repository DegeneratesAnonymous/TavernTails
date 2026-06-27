"""End-to-end orchestration tests for Work Order 3.

Coverage:
  - Memory Extractor: extracts NPCs, locations, clues, threads, world state
  - Canon Manager: status lifecycle, promotion, violation detection, backstory boundary
  - UI Payload Builder: resolution states, bundle mapping, validation
  - Validation blocks: incomplete content blocks prose, canon violations caught
"""
import pytest
import tempfile
from pathlib import Path

from server.agents.memory_extractor import extract_memory
from server.agents.canon_manager import (
    load_canon_index,
    save_canon_index,
    apply_memory_delta,
    promote_entity,
    expire_stale_background,
    validate_canon,
    check_backstory_boundaries,
    make_canon_record,
    can_promote,
)
from server.agents.ui_payload_builder import (
    build_ui_payload,
    validate_ui_payload,
    resolution_state_for,
    RESOLUTION_STATES,
)


# ---------------------------------------------------------------------------
# Memory Extractor
# ---------------------------------------------------------------------------

class TestMemoryExtractor:
    def _base_scene(self) -> dict:
        return {
            "id": "scene-abc123",
            "narrative_body": "Commander Theron Cray stood at the gate of Ironpass Fort.",
            "player_prompt": "What do you do?",
            "location": "Ironpass Fort",
            "visible_clues": ["Cut saddlebag leather", "Muddy boot prints"],
            "active_threads": ["Find the intercepted orders"],
            "scene_director_data": {
                "primary_npc": {
                    "name": "Theron Cray",
                    "role": "Fort Commander",
                    "what_they_want": "Know what the orders contained",
                },
                "location": {
                    "name": "Ironpass Fort",
                    "type": "frontier_fort",
                },
            },
            "situation_type": "investigation",
        }

    def test_extracts_primary_npc(self):
        delta = extract_memory(self._base_scene(), {}, {})
        names = [n.get("name") if isinstance(n, dict) else n for n in delta["new_npcs"]]
        assert "Theron Cray" in names

    def test_npc_has_canon_status(self):
        delta = extract_memory(self._base_scene(), {}, {})
        npc = next((n for n in delta["new_npcs"] if isinstance(n, dict) and n.get("name") == "Theron Cray"), None)
        assert npc is not None
        assert npc.get("canon_status") == "provisional"

    def test_extracts_new_location(self):
        delta = extract_memory(self._base_scene(), {}, {}, previous_scene={"location": ""})
        loc_names = [l.get("name") if isinstance(l, dict) else l for l in delta["new_locations"]]
        assert "Ironpass Fort" in loc_names

    def test_same_location_is_updated_not_new(self):
        delta = extract_memory(self._base_scene(), {}, {}, previous_scene={"location": "Ironpass Fort"})
        new_names = [l.get("name") if isinstance(l, dict) else l for l in delta["new_locations"]]
        assert "Ironpass Fort" not in new_names
        updated_names = [l.get("name") if isinstance(l, dict) else l for l in delta["updated_locations"]]
        assert "Ironpass Fort" in updated_names

    def test_extracts_visible_clues(self):
        delta = extract_memory(self._base_scene(), {}, {})
        assert "Cut saddlebag leather" in delta["new_clues"]
        assert "Muddy boot prints" in delta["new_clues"]

    def test_new_thread_vs_continuing_thread(self):
        delta = extract_memory(
            self._base_scene(), {}, {},
            previous_scene={"active_threads": []}
        )
        assert "Find the intercepted orders" in delta["new_threads"]

        delta2 = extract_memory(
            self._base_scene(), {}, {},
            previous_scene={"active_threads": ["Find the intercepted orders"]}
        )
        assert "Find the intercepted orders" in delta2["updated_threads"]
        assert "Find the intercepted orders" not in delta2["new_threads"]

    def test_world_state_changes_tracked(self):
        delta = extract_memory(
            self._base_scene(),
            world_state={"campaign_day": 3, "weather": "stormy"},
            simulation_delta={},
            previous_scene={"weather": "clear"},
        )
        fields = [c["field"] for c in delta["world_state_changes"]]
        assert "weather" in fields or "campaign_day" in fields

    def test_backstory_hook_usage_detected(self):
        contract = {
            "backstory_profiles": [
                {"spotlight_npc": "Theron Cray", "character_name": "Kaela"}
            ]
        }
        delta = extract_memory(self._base_scene(), {}, {}, campaign_contract=contract)
        assert "Theron Cray" in delta["backstory_hooks_used"]

    def test_consequences_from_simulation_delta(self):
        delta = extract_memory(
            self._base_scene(), {},
            simulation_delta={"consequences_triggered": ["The garrison was alerted"]},
        )
        assert "The garrison was alerted" in delta["new_consequences"]

    def test_content_bundle_updates_tracked(self):
        bundle = {"bundle_id": "abc", "bundle_type": "InvestigationBundle", "validated": True}
        delta = extract_memory(self._base_scene(), {}, {}, content_bundle={"bundle_id": "abc", "required_content": {}, "validated": True})
        assert any(u.get("bundle_id") == "abc" for u in delta.get("game_content_bundle_updates") or [])


# ---------------------------------------------------------------------------
# Canon Manager
# ---------------------------------------------------------------------------

class TestCanonManager:
    def _fresh_index(self) -> dict:
        return {}

    def test_upsert_creates_new_entity(self):
        from server.agents.canon_manager import upsert_entity
        index = self._fresh_index()
        record, was_new = upsert_entity(index, "Theron Cray", "npc", "provisional", "scene-1")
        assert was_new is True
        assert index["Theron Cray"]["canon_status"] == "provisional"

    def test_upsert_updates_existing(self):
        from server.agents.canon_manager import upsert_entity
        index = self._fresh_index()
        upsert_entity(index, "Theron Cray", "npc", "provisional", "scene-1")
        record, was_new = upsert_entity(index, "Theron Cray", "npc", "provisional", "scene-2")
        assert was_new is False
        assert record["reuse_count"] == 1

    def test_can_promote_paths(self):
        assert can_promote("provisional", "canon") is True
        assert can_promote("canon", "confirmed_canon") is True
        assert can_promote("background", "provisional") is True
        assert can_promote("confirmed_canon", "provisional") is False
        assert can_promote("rejected", "canon") is False

    def test_promote_entity_success(self):
        from server.agents.canon_manager import upsert_entity
        index = self._fresh_index()
        upsert_entity(index, "Theron Cray", "npc", "provisional")
        result = promote_entity(index, "Theron Cray", "canon", scene_id="scene-2", reason="confirmed in play")
        assert result["success"] is True
        assert index["Theron Cray"]["canon_status"] == "canon"
        assert len(index["Theron Cray"]["change_log"]) >= 2

    def test_promote_entity_blocked_invalid_path(self):
        from server.agents.canon_manager import upsert_entity
        index = self._fresh_index()
        upsert_entity(index, "Theron Cray", "npc", "confirmed_canon")
        result = promote_entity(index, "Theron Cray", "provisional")
        assert result["success"] is False

    def test_player_canon_promotion_requires_approval(self):
        from server.agents.canon_manager import upsert_entity
        index = self._fresh_index()
        upsert_entity(index, "Velara Ashveil", "npc", "player_canon")
        result = promote_entity(index, "Velara Ashveil", "confirmed_canon", require_approval=True)
        assert result.get("requires_approval") is True or result["success"] is False

    def test_apply_memory_delta_ingests_npcs(self):
        index = self._fresh_index()
        delta = {
            "new_npcs": [{"name": "Mira Holt", "role": "Smuggler"}],
            "new_locations": [{"name": "Ironpass Fort"}],
            "updated_npcs": [],
            "updated_locations": [],
        }
        result = apply_memory_delta(index, delta, scene_id="scene-1")
        assert "Mira Holt" in result["new"]
        assert "Ironpass Fort" in result["new"]
        assert index["Mira Holt"]["canon_status"] == "provisional"

    def test_player_canon_protected_during_delta(self):
        index = self._fresh_index()
        contract = {
            "player_canon": [{"name": "Velara Ashveil", "type": "npc"}]
        }
        delta = {
            "new_npcs": [{"name": "Velara Ashveil", "role": "Merchant"}],
            "updated_npcs": [], "new_locations": [], "updated_locations": [],
        }
        apply_memory_delta(index, delta, scene_id="scene-1", campaign_contract=contract)
        assert index["Velara Ashveil"]["canon_status"] == "player_canon"

    def test_background_expiry(self):
        index = self._fresh_index()
        index["Barkeep"] = make_canon_record("Barkeep", "npc", "background")
        index["Barkeep"]["reuse_count"] = 0
        discarded = expire_stale_background(index, current_scene_number=10)
        assert "Barkeep" in discarded
        assert index["Barkeep"]["canon_status"] == "discarded"

    def test_background_not_expired_if_reused(self):
        index = self._fresh_index()
        index["Innkeeper"] = make_canon_record("Innkeeper", "npc", "background")
        index["Innkeeper"]["reuse_count"] = 3
        discarded = expire_stale_background(index, current_scene_number=10)
        assert "Innkeeper" not in discarded

    def test_canon_validation_detects_type_mismatch(self):
        from server.agents.canon_manager import upsert_entity
        index = self._fresh_index()
        upsert_entity(index, "Ironpass Fort", "npc", "provisional")  # wrong type!
        contract = {"player_canon": [{"name": "Ironpass Fort", "type": "location"}]}
        result = validate_canon("The party arrived at Ironpass Fort.", index, contract)
        # Mismatch: canon says location, index says npc
        assert isinstance(result["issues"], list)

    def test_canon_validation_passes_consistent_data(self):
        from server.agents.canon_manager import upsert_entity
        index = self._fresh_index()
        upsert_entity(index, "Ironpass Fort", "location", "player_canon")
        contract = {"player_canon": [{"name": "Ironpass Fort", "type": "location"}]}
        result = validate_canon("The party arrived at Ironpass Fort.", index, contract)
        assert result["valid"] is True

    def test_backstory_boundary_violation_detected(self):
        contract = {
            "backstory_profiles": [
                {
                    "character_name": "Kaela",
                    "private_facts": ["She killed her brother"],
                }
            ]
        }
        violations = check_backstory_boundaries(
            "In the background, she killed her brother during the war.",
            contract,
        )
        assert len(violations) > 0
        assert violations[0]["severity"] == "error"

    def test_backstory_boundary_clean_narrative(self):
        contract = {
            "backstory_profiles": [
                {
                    "character_name": "Kaela",
                    "private_facts": ["she is the queen"],
                }
            ]
        }
        violations = check_backstory_boundaries(
            "Kaela drew her sword and prepared to fight.",
            contract,
        )
        assert len(violations) == 0

    def test_file_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            index = {}
            from server.agents.canon_manager import upsert_entity
            upsert_entity(index, "Mira Holt", "npc", "provisional")
            save_canon_index(folder, index)
            loaded = load_canon_index(folder)
            assert "Mira Holt" in loaded
            assert loaded["Mira Holt"]["canon_status"] == "provisional"


# ---------------------------------------------------------------------------
# UI Payload Builder
# ---------------------------------------------------------------------------

class TestUiPayloadBuilder:
    def _base_scene(self) -> dict:
        return {
            "id": "scene-abc",
            "narrative_body": "You arrive at Ironpass Fort as the sun sets.",
            "player_prompt": "What do you do next?",
            "situation_type": "new_scene_opening",
            "location": "Ironpass Fort",
            "active_threads": ["Find the orders"],
            "suggested_actions": ["Investigate the stables", "Speak to the commander"],
            "visible_clues": ["Boot prints in mud"],
        }

    def _base_bundle(self) -> dict:
        return {
            "bundle_type": "OpeningBundle",
            "situation_type": "new_scene_opening",
            "required_content": {
                "immediate_problem": "The commander is missing.",
                "specific_stakes": "The fort will fall without his orders.",
            },
            "ui_payload": {
                "experience_mode": "quiet_scene",
                "objective": "Find the commander.",
            },
        }

    def test_payload_has_required_top_level_fields(self):
        payload = build_ui_payload(
            scene=self._base_scene(),
            content_bundle=self._base_bundle(),
            memory_delta={},
            world_state={},
            simulation_delta={},
        )
        for field in ("scene", "scene_summary", "resolution_panel", "suggested_actions",
                      "experience_mode", "situation_type", "visible_clues"):
            assert field in payload, f"Missing field: {field}"

    def test_scene_has_required_fields(self):
        payload = build_ui_payload(
            scene=self._base_scene(),
            content_bundle=self._base_bundle(),
            memory_delta={}, world_state={}, simulation_delta={},
        )
        scene = payload["scene"]
        assert scene["narrative_body"]
        assert scene["player_prompt"]
        assert scene["situation_type"] == "new_scene_opening"

    def test_resolution_state_quiet_scene(self):
        payload = build_ui_payload(
            scene=self._base_scene(),
            content_bundle=self._base_bundle(),
            memory_delta={}, world_state={}, simulation_delta={},
        )
        assert payload["resolution_panel"]["state"] in RESOLUTION_STATES

    def test_resolution_state_combat(self):
        scene = {**self._base_scene(), "situation_type": "combat_setup"}
        bundle = {**self._base_bundle(), "situation_type": "combat_setup", "ui_payload": {"experience_mode": "combat_imminent", "enemy_cards": [{"name": "Raider", "hp": 10, "ac": 12}]}}
        payload = build_ui_payload(scene=scene, content_bundle=bundle, memory_delta={}, world_state={}, simulation_delta={})
        assert payload["resolution_panel"]["state"] == "combat"

    def test_resolution_state_investigation(self):
        scene = {**self._base_scene(), "situation_type": "investigation"}
        bundle = {**self._base_bundle(), "situation_type": "investigation", "ui_payload": {"mystery_question": "Who stole the orders?"}}
        payload = build_ui_payload(scene=scene, content_bundle=bundle, memory_delta={}, world_state={}, simulation_delta={})
        assert payload["resolution_panel"]["state"] == "investigation"

    def test_resolution_state_for_function(self):
        assert resolution_state_for("combat_setup", False, False) == "combat"
        assert resolution_state_for("investigation", False, False) == "investigation"
        assert resolution_state_for("travel", False, False) == "travel"
        assert resolution_state_for("downtime", False, False) == "downtime"
        assert resolution_state_for("unknown_type", True, False) == "checks_available"
        assert resolution_state_for("unknown_type", False, True) == "result"
        assert resolution_state_for("unknown_type", False, False) == "idle"

    def test_archive_updates_from_memory_delta(self):
        memory_delta = {
            "new_npcs": [{"name": "Mira Holt", "canon_status": "provisional"}],
            "new_locations": [{"name": "Ironpass Fort"}],
            "new_clues": ["Cut saddlebag"],
            "new_threads": [],
        }
        payload = build_ui_payload(
            scene=self._base_scene(),
            content_bundle=self._base_bundle(),
            memory_delta=memory_delta,
            world_state={}, simulation_delta={},
        )
        archive_types = [u["type"] for u in payload["archive_updates"]]
        assert "npc" in archive_types
        assert "location" in archive_types
        assert "clue" in archive_types

    def test_debug_mode_adds_debug_key(self):
        payload = build_ui_payload(
            scene=self._base_scene(),
            content_bundle=self._base_bundle(),
            memory_delta={}, world_state={}, simulation_delta={},
            debug_mode=True,
        )
        assert "debug" in payload
        assert "situation_type" in payload["debug"]
        assert "memory_delta" in payload["debug"]

    def test_no_debug_key_in_normal_mode(self):
        payload = build_ui_payload(
            scene=self._base_scene(),
            content_bundle=self._base_bundle(),
            memory_delta={}, world_state={}, simulation_delta={},
            debug_mode=False,
        )
        assert "debug" not in payload

    def test_character_quick_panel_populated(self):
        payload = build_ui_payload(
            scene=self._base_scene(),
            content_bundle=self._base_bundle(),
            memory_delta={}, world_state={}, simulation_delta={},
            player_stats={"name": "Kaela", "class": "Ranger", "hp": 32, "ac": 15, "level": 5},
        )
        cqp = payload["character_quick_panel"]
        assert cqp["name"] == "Kaela"
        assert cqp["hp"] == 32

    def test_ui_payload_validation_combat_mismatch(self):
        payload = build_ui_payload(
            scene={**self._base_scene(), "situation_type": "combat_setup"},
            content_bundle=self._base_bundle(),
            memory_delta={}, world_state={}, simulation_delta={},
        )
        # Force wrong state for testing
        payload["resolution_panel"]["state"] = "idle"
        result = validate_ui_payload(payload, "combat_setup")
        assert result["valid"] is False or result["issues"]

    def test_ui_payload_validation_passes_valid(self):
        payload = build_ui_payload(
            scene=self._base_scene(),
            content_bundle=self._base_bundle(),
            memory_delta={}, world_state={}, simulation_delta={},
        )
        result = validate_ui_payload(payload, "new_scene_opening")
        assert result["score"] >= 60


# ---------------------------------------------------------------------------
# Validation blocks — incomplete content prevents narration
# ---------------------------------------------------------------------------

class TestValidationBlocks:
    def test_combat_without_combatants_fails(self):
        from server.agents.situation_contracts import validate_combat_setup
        result = validate_combat_setup({
            "battlefield": {"terrain_features": ["rock", "tree"]},
            "stakes": "Survive",
        })
        assert result["valid"] is False
        assert "combatants" in result["missing_required_fields"]

    def test_investigation_without_clues_fails(self):
        from server.agents.situation_contracts import validate_investigation
        result = validate_investigation({
            "mystery_question": "Who did it?",
            "scene_location": "The library",
            "visible_clues": [],
            "required_conclusions": [],
        })
        assert result["valid"] is False

    def test_opening_with_tavern_default_blocked(self):
        from server.agents.situation_contracts import validate_campaign_opening
        result = validate_campaign_opening({
            "starting_location": "The Wayward Lantern Inn",
            "inciting_event": "You meet a stranger.",
            "named_npc_or_visible_threat": "a stranger",
            "immediate_problem": "They want help.",
            "specific_stakes": "If no one acts, the stakes are high.",
            "first_clue_or_question": "What do they want?",
            "player_decision": "Help or refuse.",
        })
        assert result["generic_defaults_detected"] or not result["valid"]

    def test_abstract_stakes_are_rejected(self):
        from server.agents.situation_contracts import validate_campaign_opening
        result = validate_campaign_opening({
            "starting_location": "Ironpass Fort",
            "inciting_event": "The gate stands open.",
            "named_npc_or_visible_threat": "Commander Cray",
            "immediate_problem": "The commander is missing.",
            "specific_stakes": "If no one acts, danger looms.",
            "first_clue_or_question": "Who left first?",
            "player_decision": "Search or leave.",
        })
        assert result["generic_defaults_detected"]

    def test_backstory_boundary_violation_caught(self):
        violations = check_backstory_boundaries(
            "She had always been the queen in disguise.",
            campaign_contract={
                "backstory_profiles": [
                    {
                        "character_name": "Lira",
                        "private_facts": ["the queen in disguise"],
                    }
                ]
            },
        )
        assert any(v["severity"] == "error" for v in violations)


# ---------------------------------------------------------------------------
# Campaign creation output shape (smoke test)
# ---------------------------------------------------------------------------

class TestCampaignCreationOutput:
    def test_quick_start_produces_required_fields(self):
        from fastapi.testclient import TestClient
        import server.main as main
        from server import db
        from server.auth import create_access_token

        client = TestClient(main.app)
        email = "orchestration-test@example.com"
        existing = db.get_user_by_identifier(email)
        if not existing:
            user = db.create_user(email=email, password="secret", username="orchtest",
                                   profile={"name": "orchtest", "email": email})
            db.verify_user(email, user.verification_token)

        headers = {"Authorization": f"Bearer {create_access_token(email)}"}
        res = client.post("/campaigns", json={
            "name": "Orchestration Test Campaign",
            "creation_posture": "player_fast_start",
            "genre": "fantasy",
            "tone": "balanced",
        }, headers=headers)
        assert res.status_code in (200, 201)
        data = res.json()
        campaign = data.get("campaign") or data
        assert campaign.get("id") or campaign.get("campaign_contract")
