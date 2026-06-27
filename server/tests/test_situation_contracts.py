"""Tests for situation classifier, contracts, and content bundles.

Coverage:
  - classify_situation: campaign_opening, player action keywords, director type,
    experience_mode, continuation, fallback
  - validate_situation: all 8 validator types
  - build_content_bundle: opening seed gen, combat, dialogue, investigation, travel
  - freshness / tavern default rejection
"""
import pytest

from server.agents.situation_classifier import classify_situation, REQUIRES_CONTRACT
from server.agents.situation_contracts import (
    validate_situation,
    validate_campaign_opening,
    validate_combat_setup,
    validate_interrogation,
    validate_investigation,
    validate_travel,
    validate_return_to_known_location,
    validate_npc_reappearance,
    validate_social_conflict,
)
from server.agents.content_bundles import (
    build_content_bundle,
    generate_starter_seed,
    empty_freshness,
    build_ui_payload,
)


# ---------------------------------------------------------------------------
# Situation Classifier
# ---------------------------------------------------------------------------

class TestClassifySituation:
    def test_campaign_opening_on_first_scene(self):
        result = classify_situation(
            player_actions=[],
            previous_scene=None,
            scene_count=0,
        )
        assert result["situation_type"] == "campaign_opening"
        assert result["confidence"] == 1.0
        assert result["requires_content_contract"] is True

    def test_combat_keywords_in_player_actions(self):
        result = classify_situation(
            player_actions=["I attack the guard", "strike with my sword"],
            previous_scene={"situation_type": "new_scene_opening"},
            scene_count=3,
        )
        assert result["situation_type"] == "combat_setup"
        assert result["confidence"] >= 0.85
        assert result["requires_content_contract"] is True

    def test_investigation_keywords(self):
        result = classify_situation(
            player_actions=["I search the room for clues", "examine the body"],
            previous_scene={"situation_type": "new_scene_opening"},
            scene_count=2,
        )
        assert result["situation_type"] == "investigation"

    def test_travel_keywords(self):
        result = classify_situation(
            player_actions=["We head to the northern fort"],
            previous_scene={"situation_type": "conversation"},
            scene_count=5,
        )
        assert result["situation_type"] == "travel"

    def test_director_scene_type_used(self):
        result = classify_situation(
            player_actions=[],
            previous_scene={"situation_type": "new_scene_opening"},
            director_scene_type="Investigation",
            scene_count=4,
        )
        assert result["situation_type"] == "investigation"

    def test_experience_mode_combat_imminent(self):
        result = classify_situation(
            player_actions=[],
            previous_scene={"situation_type": "conversation"},
            experience_mode="combat_imminent",
            scene_count=3,
        )
        assert result["situation_type"] == "combat_setup"

    def test_travel_continues_to_arrival(self):
        result = classify_situation(
            player_actions=[],
            previous_scene={"situation_type": "travel"},
            scene_count=6,
        )
        assert result["situation_type"] == "arrival"

    def test_combat_round_continues_from_combat_setup(self):
        result = classify_situation(
            player_actions=[],
            previous_scene={
                "situation_type": "combat_setup",
                "content_bundle": {"combatants": [{"name": "Guard", "hp": 5}]},
            },
            scene_count=7,
        )
        assert result["situation_type"] in ("combat_round", "combat_setup")

    def test_requires_contract_set_includes_key_types(self):
        for t in ("campaign_opening", "combat_setup", "investigation", "travel"):
            assert t in REQUIRES_CONTRACT

    def test_fallback_when_no_signals(self):
        result = classify_situation(
            player_actions=[],
            previous_scene={"situation_type": "downtime"},
            scene_count=10,
        )
        assert result["situation_type"] in ("new_scene_opening", "downtime", "consequence", "npc_reappearance")
        assert "confidence" in result


# ---------------------------------------------------------------------------
# Campaign Opening Validator
# ---------------------------------------------------------------------------

class TestValidateCampaignOpening:
    def _good_bundle(self) -> dict:
        return {
            "starting_location": "Ironpass Fort",
            "location_identity": "A frontier fort where a messenger arrived without the message.",
            "inciting_event": "The dispatch rider returned — but the orders she carried are missing.",
            "named_npc_or_visible_threat": "Commander Theron Cray",
            "immediate_problem": "Commander Cray needs to know what those orders contained before dawn.",
            "specific_stakes": "Without the orders, the fort cannot coordinate the supply convoy. It will be ambushed.",
            "first_clue_or_question": "Why did the rider's saddlebag show fresh cuts?",
            "player_decision": "Interrogate the rider now, or sweep the road before the trail goes cold.",
        }

    def test_good_bundle_passes(self):
        r = validate_campaign_opening(self._good_bundle())
        assert r["valid"] is True
        assert r["score"] >= 75
        assert not r["missing_required_fields"]

    def test_tavern_default_detected(self):
        bundle = self._good_bundle()
        bundle["starting_location"] = "The Wayward Lantern Inn"
        r = validate_campaign_opening(bundle)
        assert r["valid"] is False or r["score"] < 75 or r["generic_defaults_detected"]
        assert r["generic_defaults_detected"]

    def test_generic_threat_penalised(self):
        bundle = self._good_bundle()
        bundle["named_npc_or_visible_threat"] = "mysterious threat"
        r = validate_campaign_opening(bundle)
        assert r["score"] < 100

    def test_abstract_stakes_flagged(self):
        bundle = self._good_bundle()
        bundle["specific_stakes"] = "If no one acts, the stakes are high."
        r = validate_campaign_opening(bundle)
        assert r["generic_defaults_detected"] or r["score"] < 80

    def test_missing_required_fields_fails(self):
        r = validate_campaign_opening({})
        assert r["valid"] is False
        assert len(r["missing_required_fields"]) >= 4


# ---------------------------------------------------------------------------
# Combat Validator
# ---------------------------------------------------------------------------

class TestValidateCombatSetup:
    def _good_bundle(self) -> dict:
        return {
            "encounter_id": "enc001",
            "combatants": [
                {
                    "name": "Raider Captain",
                    "hp": 30, "ac": 14,
                    "attacks": [{"name": "Shortsword", "damage": "1d6+3"}],
                    "tactics": "Flanks and focuses on the weakest target.",
                    "goal": "Capture the dispatch rider.",
                }
            ],
            "battlefield": {
                "location": "Forest clearing",
                "terrain_features": ["dense underbrush", "fallen log"],
                "hazards": ["muddy ground slows movement"],
                "interactive_objects": ["wagon with locked chest"],
            },
            "stakes": "The rider will be captured and the orders decoded if the party fails.",
            "victory_conditions": ["Defeat the Raider Captain"],
            "failure_consequences": ["Party is driven back; rider is taken"],
            "non_combat_options": ["Negotiate", "Flee"],
        }

    def test_good_bundle_passes(self):
        r = validate_combat_setup(self._good_bundle())
        assert r["valid"] is True
        assert r["score"] >= 75

    def test_missing_combatants_fails(self):
        bundle = self._good_bundle()
        bundle["combatants"] = []
        r = validate_combat_setup(bundle)
        assert r["valid"] is False
        assert "combatants" in r["missing_required_fields"]

    def test_combatant_missing_stats_penalised(self):
        bundle = self._good_bundle()
        bundle["combatants"][0].pop("ac")
        r = validate_combat_setup(bundle)
        assert r["score"] < 100
        assert any("ac" in g for g in r["mechanical_gaps"])

    def test_battlefield_needs_features(self):
        bundle = self._good_bundle()
        bundle["battlefield"]["terrain_features"] = []
        bundle["battlefield"]["interactive_objects"] = []
        r = validate_combat_setup(bundle)
        assert r["mechanical_gaps"]


# ---------------------------------------------------------------------------
# Interrogation Validator
# ---------------------------------------------------------------------------

class TestValidateInterrogation:
    def _good_bundle(self) -> dict:
        return {
            "npc": {
                "name": "Mira Holt",
                "goal": "Protect her employer at any cost.",
                "fear": "Losing her anonymity.",
                "attitude": "hostile",
                "knows": ["The real destination of the orders", "Name of the fence"],
                "is_hiding": ["her employer's identity"],
            },
            "secrets": [
                {
                    "secret": "The orders were sold to House Vance.",
                    "disclosure_threshold": "Insight DC 15 or physical evidence",
                    "revealed_by": "direct accusation backed by the cut saddlebag",
                }
            ],
            "pressure_points": ["Fear of identification"],
            "trust_state": "hostile",
            "possible_checks": ["Intimidation", "Insight"],
            "failure_forward_options": ["Partial name slips out", "NPC demands a deal"],
        }

    def test_good_bundle_passes(self):
        r = validate_interrogation(self._good_bundle())
        assert r["valid"] is True
        assert r["score"] >= 75

    def test_missing_npc_fails(self):
        r = validate_interrogation({})
        assert r["valid"] is False

    def test_secret_without_reveal_conditions_flagged(self):
        bundle = self._good_bundle()
        bundle["secrets"] = [{"secret": "Something big"}]
        r = validate_interrogation(bundle)
        assert r["mechanical_gaps"]

    def test_no_failure_forward_flagged(self):
        bundle = self._good_bundle()
        bundle["failure_forward_options"] = []
        r = validate_interrogation(bundle)
        assert r["mechanical_gaps"] or r["score"] < 90


# ---------------------------------------------------------------------------
# Investigation Validator
# ---------------------------------------------------------------------------

class TestValidateInvestigation:
    def _good_bundle(self) -> dict:
        return {
            "mystery_question": "Who cut the saddlebag and stole the orders?",
            "scene_location": "Fort Ironpass stables",
            "visible_clues": [
                "Fresh blade cuts on the saddlebag leather",
                "Muddy boot prints leading to the hay loft",
                "A copper coin from House Vance stamped 873",
            ],
            "required_conclusions": [
                {
                    "conclusion": "The orders were intercepted by a House Vance agent",
                    "clue_paths": [
                        "Coin matches House Vance treasury mintage",
                        "Boot prints match the farrier's size",
                        "Farrier was last seen near the hay loft",
                    ],
                }
            ],
            "failure_forward": ["Partial evidence found pointing to the stables"],
        }

    def test_good_bundle_passes(self):
        r = validate_investigation(self._good_bundle())
        assert r["valid"] is True
        assert r["score"] >= 75

    def test_no_visible_clues_fails(self):
        bundle = self._good_bundle()
        bundle["visible_clues"] = []
        r = validate_investigation(bundle)
        assert r["valid"] is False

    def test_conclusion_with_few_clue_paths_flagged(self):
        bundle = self._good_bundle()
        bundle["required_conclusions"][0]["clue_paths"] = ["Only one clue"]
        r = validate_investigation(bundle)
        assert r["mechanical_gaps"]


# ---------------------------------------------------------------------------
# Travel Validator
# ---------------------------------------------------------------------------

class TestValidateTravel:
    def _good_bundle(self) -> dict:
        return {
            "origin": "Fort Ironpass",
            "destination": "Thornwick Post",
            "route": "Northern military road",
            "travel_time": "4 hours",
            "complication_or_discovery": "A second set of tracks appears on the road — someone followed the rider.",
            "arrival_state": "The post is dark; no lights and no guards visible.",
        }

    def test_good_bundle_passes(self):
        r = validate_travel(self._good_bundle())
        assert r["valid"] is True
        assert r["score"] >= 75

    def test_missing_origin_fails(self):
        bundle = self._good_bundle()
        del bundle["origin"]
        r = validate_travel(bundle)
        assert "origin" in r["missing_required_fields"]

    def test_short_complication_penalised(self):
        bundle = self._good_bundle()
        bundle["complication_or_discovery"] = "Rain."
        r = validate_travel(bundle)
        assert r["score"] <= 90 and r["weak_fields"]


# ---------------------------------------------------------------------------
# Return to Known Location Validator
# ---------------------------------------------------------------------------

class TestValidateReturnToKnownLocation:
    def test_valid_bundle_passes(self):
        r = validate_return_to_known_location({
            "location": "Fort Ironpass",
            "last_known_state": "Full complement of 30 soldiers and active patrols.",
            "what_changed": "Half the garrison is gone; the gate hangs open.",
            "new_visible_detail": "A smear of blood on the gatehouse stones.",
            "prompt": "Do you approach openly or look for another way in?",
        })
        assert r["valid"] is True
        assert r["score"] >= 75

    def test_missing_what_changed_fails(self):
        r = validate_return_to_known_location({
            "location": "Fort Ironpass",
            "prompt": "What do you do?",
        })
        assert "what_changed" in r["missing_required_fields"]


# ---------------------------------------------------------------------------
# NPC Reappearance Validator
# ---------------------------------------------------------------------------

class TestValidateNpcReappearance:
    def test_valid_bundle_passes(self):
        r = validate_npc_reappearance({
            "npc": "Commander Theron Cray",
            "last_seen": "Scene 1 — gave the party their orders at the fort.",
            "relationship_to_party": "Superior officer; cautious trust.",
            "what_changed_for_npc": "He has been demoted and stripped of his command.",
            "what_npc_wants_now": "Proof that he was set up — and help getting it.",
            "prompt": "Cray steps from the shadows. 'I thought you were dead,' he says.",
        })
        assert r["valid"] is True

    def test_generic_npc_name_flagged(self):
        r = validate_npc_reappearance({
            "npc": "stranger",
            "what_changed_for_npc": "something",
            "what_npc_wants_now": "something",
            "prompt": "They approach.",
        })
        assert r["generic_defaults_detected"] or r["score"] < 90


# ---------------------------------------------------------------------------
# Social Conflict Validator
# ---------------------------------------------------------------------------

class TestValidateSocialConflict:
    def test_valid_bundle_passes(self):
        r = validate_social_conflict({
            "npc": {"name": "Lord Vance", "goal": "Discredit the party publicly.", "attitude": "hostile"},
            "conflict_topic": "Ownership of the intercepted orders",
            "stakes": "If Vance succeeds, the party is arrested for theft of military documents.",
            "leverage_available": ["The copper coin", "The farrier's boot prints"],
            "possible_checks": ["Persuasion", "Deception", "Intimidation"],
            "failure_forward_options": ["Party retreats but copies the coin", "Vance overcorrects and reveals too much"],
        })
        assert r["valid"] is True

    def test_abstract_stakes_flagged(self):
        r = validate_social_conflict({
            "npc": {"name": "Lord Vance", "goal": "Win.", "attitude": "hostile"},
            "conflict_topic": "Documents",
            "stakes": "The stakes are high if no one acts.",
            "leverage_available": [],
            "possible_checks": [],
            "failure_forward_options": ["something"],
        })
        assert r["generic_defaults_detected"] or r["score"] < 90


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class TestValidateSituationDispatcher:
    def test_unknown_type_passes_through(self):
        r = validate_situation("session_recap", {})
        assert r["valid"] is True

    def test_dispatches_to_combat(self):
        r = validate_situation("combat_setup", {})
        assert r["valid"] is False
        assert "combatants" in r["missing_required_fields"]

    def test_dispatches_to_opening(self):
        r = validate_situation("campaign_opening", {})
        assert r["valid"] is False


# ---------------------------------------------------------------------------
# Starter Seed Generator
# ---------------------------------------------------------------------------

class TestStarterSeedGenerator:
    def test_seed_returns_required_fields(self):
        seed = generate_starter_seed(seed=42)
        for field in (
            "starting_location", "location_identity", "inciting_event",
            "named_npc_or_visible_threat", "immediate_problem",
            "specific_stakes", "first_clue_or_question", "player_decision",
        ):
            assert seed.get(field), f"Missing required field: {field}"

    def test_seed_is_not_tavern_default(self):
        for i in range(8):
            seed = generate_starter_seed(seed=i)
            loc = seed["starting_location"].lower()
            assert "tavern" not in loc
            assert "inn" not in loc
            assert "alehouse" not in loc

    def test_deterministic_with_same_seed(self):
        a = generate_starter_seed(seed=7)
        b = generate_starter_seed(seed=7)
        assert a["starting_location"] == b["starting_location"]
        assert a["named_npc_or_visible_threat"] == b["named_npc_or_visible_threat"]

    def test_different_seeds_produce_variation(self):
        locations = {generate_starter_seed(seed=i)["starting_location"] for i in range(6)}
        assert len(locations) > 1


# ---------------------------------------------------------------------------
# Content Bundle Builder
# ---------------------------------------------------------------------------

class TestBuildContentBundle:
    def test_campaign_opening_bundle_for_first_scene(self):
        bundle = build_content_bundle(
            situation_type="campaign_opening",
            scene_director_output={},
            freshness_context={"scene_count": 0},
        )
        assert bundle["situation_type"] == "campaign_opening"
        assert bundle["bundle_type"] == "OpeningBundle"
        assert "required_content" in bundle
        assert "ui_payload" in bundle
        assert "validated" in bundle

    def test_tavern_default_triggers_seed_generation(self):
        bundle = build_content_bundle(
            situation_type="campaign_opening",
            scene_director_output={"location": {"name": "The Wayward Lantern Inn"}},
            freshness_context={"scene_count": 0},
        )
        rc = bundle["required_content"]
        loc = rc.get("starting_location") or rc.get("location", "")
        assert "tavern" not in loc.lower()
        assert "inn" not in loc.lower()

    def test_combat_bundle_structure(self):
        bundle = build_content_bundle(
            situation_type="combat_setup",
            world_state={"active_enemies": [
                {"name": "Raider", "hp": 12, "ac": 13, "tactics": "Rush forward"}
            ]},
        )
        assert bundle["bundle_type"] == "CombatBundle"
        assert "combatants" in bundle["required_content"]

    def test_investigation_bundle_structure(self):
        bundle = build_content_bundle(
            situation_type="investigation",
            scene_director_output={
                "central_conflict": "Who stole the orders?",
                "player_visible_clues": ["Cut saddlebag", "Muddy boot prints", "Vance coin"],
                "location": {"name": "Fort Ironpass stables"},
            },
        )
        rc = bundle["required_content"]
        assert rc.get("mystery_question")
        assert rc.get("visible_clues")

    def test_travel_bundle_structure(self):
        bundle = build_content_bundle(
            situation_type="travel",
            scene_director_output={"location": {"name": "Thornwick Post"}},
            previous_scene={"location": "Fort Ironpass"},
        )
        rc = bundle["required_content"]
        assert rc.get("origin") == "Fort Ironpass"
        assert rc.get("destination") == "Thornwick Post"

    def test_ui_payload_present_for_opening(self):
        bundle = build_content_bundle(
            situation_type="campaign_opening",
            freshness_context={"scene_count": 0},
        )
        ui = bundle["ui_payload"]
        assert ui.get("situation_type") == "campaign_opening"
        assert ui.get("bundle_type") == "OpeningBundle"
        assert "experience_mode" in ui

    def test_non_contract_situation_skips_validation(self):
        # "downtime" is not in REQUIRES_CONTRACT — bundle should still build
        bundle = build_content_bundle(situation_type="downtime")
        assert bundle["situation_type"] == "downtime"
