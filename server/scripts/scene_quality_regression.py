"""Scene quality regression harness.

Runs deterministic QA over a matrix of campaign premises and canned player
actions.  It is intentionally lightweight so it can run in CI without making
LLM calls.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.agents.campaign_interpretation import build_full_contract_package
from server.agents.content_bundles import ensure_content_bundle
from server.agents.scene_qa import run_scene_qa

TEST_CAMPAIGN_SEEDS = [
    {
        "id": "long_winter_survival_mystery",
        "name": "Long Winter survival mystery",
        "description": "A frozen northern road where silver charms blacken before settlements vanish.",
        "settings": {"genre": "fantasy", "tone": "dark mystery", "setting_summary": "Frozen roads, blackened silver charms, and howls from the wilderness."},
    },
    {
        "id": "desert_political_survival",
        "name": "Desert political survival",
        "description": "Water houses and caravan factions fight over a poisoned cistern.",
        "settings": {"genre": "fantasy", "tone": "political thriller", "setting_summary": "A glass desert where water seals decide who lives."},
    },
    {
        "id": "urban_noir_fantasy",
        "name": "Urban noir fantasy",
        "description": "Masked debt collectors hunt stolen memories through rainlit alleys.",
        "settings": {"genre": "fantasy noir", "tone": "noir", "setting_summary": "A rain-black city of masks, debts, and memory magic."},
    },
    {
        "id": "heroic_goblin_rescue",
        "name": "Heroic rescue one-shot",
        "description": "A bright one-shot rescue in a collapsed mine with a strict sunset clock.",
        "settings": {"genre": "fantasy", "tone": "heroic", "campaign_length": "one_shot", "setting_summary": "A rescue mission in a collapsed copper mine before sunset."},
    },
    {
        "id": "endless_west_marches",
        "name": "Endless West Marches frontier",
        "description": "Open-table frontier scouts map ruins beyond a changing home base.",
        "settings": {"genre": "fantasy", "tone": "frontier", "campaign_length": "endless", "setting_summary": "A frontier map, unstable roads, lost towers, and faction scouts."},
    },
    {
        "id": "tactical_dungeon_assault",
        "name": "Tactical dungeon assault",
        "description": "A tactical assault on a living dungeon where doors change allegiance.",
        "settings": {"genre": "fantasy", "tone": "tactical", "setting_summary": "A living dungeon with shifting doors, hazards, and enemy patrol clocks."},
    },
    {
        "id": "cozy_village_mystery",
        "name": "Cozy village mystery",
        "description": "A friendly village hides why every clock stopped at breakfast.",
        "settings": {"genre": "mystery", "tone": "cozy", "setting_summary": "A quiet village, stopped clocks, warm kitchens, and guarded neighbors."},
    },
    {
        "id": "faction_war_sandbox",
        "name": "Faction war sandbox",
        "description": "Three banners compete for river forts after a treaty ledger is stolen.",
        "settings": {"genre": "fantasy", "tone": "political", "setting_summary": "A river war of banners, forts, smugglers, and a stolen treaty ledger."},
    },
    {
        "id": "academy_drama",
        "name": "Character-driven academy drama",
        "description": "Students uncover why a forbidden bell rings only for one bloodline.",
        "settings": {"genre": "fantasy", "tone": "character drama", "setting_summary": "An old academy, forbidden bells, rival houses, and family secrets."},
    },
]

CANNED_PLAYER_ACTIONS = [
    "I inspect the marked clue before anyone moves it.",
    "I question the witness about what they touched last.",
    "I follow the freshest tracks away from the scene.",
    "I protect the bystander and watch who tries to leave.",
    "I compare the symbol to my notes and call for help.",
]


def _scene_from_required(seed: dict[str, Any], required: dict[str, Any], run_index: int) -> dict[str, Any]:
    loc = required.get("starting_location") or f"{seed['name']} Site {run_index}"
    npc = str(required.get("named_npc_or_visible_threat") or f"Witness {run_index}").split("(")[0].strip()
    motif = _seed_motif(seed)
    base_clue = required.get("first_clue_or_question") or f"Why is the {motif} out of place?"
    clue = f"{base_clue.rstrip('.')} The {motif} is the first physical evidence."
    stakes = required.get("specific_stakes") or "If ignored, the first lead disappears before dusk."
    event = required.get("inciting_event") or "A visible clue appears in the wrong hands."
    identity = required.get("location_identity") or f"{loc} carries the campaign's first pressure: {motif} rests where it should not, sharp against the air."
    decision = required.get("player_decision") or "Inspect the clue, question the witness, or follow the trail."
    narrative = (
        f"{loc} is immediately specific: {identity.rstrip('.')}.\n\n"
        f"{event.rstrip('.')}. {npc} points to the clue without explaining it away.\n\n"
        f"The clue is concrete: {clue.rstrip('.')}. {stakes.rstrip('.')}.\n\n"
        f"The party can choose now: {decision.rstrip('.')}."
    )
    return {
        "id": f"{seed['id']}-opening-{run_index}",
        "title": f"Opening — {loc}",
        "narrative_body": narrative,
        "player_prompt": "What does the party do?",
        "text": f"{narrative}\n\nWhat does the party do?",
        "choices": [{"id": "inspect", "label": "Inspect the clue"}, {"id": "question", "label": "Question the witness"}],
        "suggested_actions": ["Inspect the clue", "Question the witness", "Follow the trail"],
        "world_moves": [stakes],
        "location": loc,
        "visible_clues": [clue],
        "immediate_stakes": stakes,
        "current_objective": decision,
        "scene_director_data": {
            "location": {"name": loc, "type": required.get("location_type") or "opening location", "sensory_details": [identity]},
            "primary_npc": {"name": npc, "role": "witness", "what_they_want": decision, "what_they_know": clue},
            "central_conflict": required.get("immediate_problem") or stakes,
            "inciting_incident": event,
            "immediate_stakes": stakes,
            "player_visible_clues": [clue],
            "possible_actions": ["Inspect the clue", "Question the witness", "Follow the trail"],
        },
    }


def _seed_motif(seed: dict[str, Any]) -> str:
    text = f"{seed.get('name','')} {seed.get('description','')} {seed.get('settings',{}).get('setting_summary','')}".lower()
    if "winter" in text or "frozen" in text:
        return "blackened silver charm"
    if "desert" in text or "water" in text:
        return "cracked water seal"
    if "mask" in text or "noir" in text:
        return "borrowed mask"
    if "mine" in text:
        return "copper rescue tag"
    if "frontier" in text:
        return "unfinished trail map"
    if "dungeon" in text:
        return "shifting door rune"
    if "village" in text or "clock" in text:
        return "stopped brass clock hand"
    if "faction" in text or "treaty" in text:
        return "stolen treaty ledger"
    if "academy" in text or "bell" in text:
        return "forbidden bell clapper"
    return "marked clue"


def _advance_scene_from_action(opening: dict[str, Any], action: str, run_index: int) -> dict[str, Any]:
    loc = opening["location"]
    clue = (opening.get("visible_clues") or ["the clue"])[0]
    narrative = (
        f"Because the party chose to {action.rstrip('.')}, {loc} changes in a way the table can use.\n\n"
        f"The action reveals a sharper detail: {clue.rstrip('.')} now points toward a specific next risk.\n\n"
        f"If the party delays, the witness leaves before the next question can be asked. "
        f"They can press the witness, secure the clue, or follow the lead immediately."
    )
    return {
        **opening,
        "id": f"{opening['id']}-advance-{run_index}",
        "title": f"Follow-up — {loc}",
        "narrative_body": narrative,
        "player_prompt": "What does the party do next?",
        "text": f"{narrative}\n\nWhat does the party do next?",
        "choices": [{"id": "press", "label": "Press the witness"}, {"id": "secure", "label": "Secure the clue"}],
        "suggested_actions": ["Press the witness", "Secure the clue", "Follow the lead"],
    }


def run_quality_regression(runs_per_seed: int = 5) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for seed in TEST_CAMPAIGN_SEEDS:
        package = build_full_contract_package(
            campaign_id=seed["id"],
            campaign_name=seed["name"],
            description=seed["description"],
            settings=seed["settings"],
            variables={},
        )
        contract = package["campaign_contract"]
        shape_counts: dict[str, int] = {}
        recent_shapes: list[dict[str, Any]] = []
        recent_location_types: list[str] = []
        recent_opening_events: list[str] = []
        scores: list[int] = []
        freshness_failures: list[str] = []
        specificity_failures: list[str] = []
        continuity_failures: list[str] = []
        stale_data_leaks: list[str] = []
        for i in range(runs_per_seed):
            bundle = ensure_content_bundle(
                situation_type="campaign_opening",
                scene_director_output={},
                campaign_contract=contract,
                campaign_settings=seed["settings"],
                freshness_context={
                    "scene_count": 0,
                    "regression_run": i,
                    "recent_location_types": recent_location_types,
                    "recent_opening_events": recent_opening_events,
                },
            )
            consumed = (bundle.get("required_content") or {}).get("freshness_consumed") or {}
            if consumed.get("location_type"):
                recent_location_types.append(consumed["location_type"])
            if consumed.get("event"):
                recent_opening_events.append(consumed["event"])
            scene = _scene_from_required(seed, bundle.get("required_content") or {}, i)
            qa = run_scene_qa(
                scene=scene,
                campaign_contract=contract,
                campaign_scale_profile=package["campaign_scale_profile"],
                story_shape_profile=package["story_shape_profile"],
                scene_beat_plan={"scene_type": "campaign_opening", "primary_scene_purpose": "seed_thread", "gm_move": "reveal_clue", "tension_level": 2 + i},
                content_bundle=bundle,
                recent_scene_history=[],
                recent_opening_shapes=recent_shapes,
                recent_motifs=[],
            )
            scores.append(int(qa["quality_score"]))
            shape = qa.get("opening_shape", {}).get("opening_shape", "")
            shape_counts[shape] = shape_counts.get(shape, 0) + 1
            recent_shapes.append(qa.get("opening_shape") or {})
            freshness_failures.extend(qa.get("freshness_failures") or [])
            specificity_failures.extend(qa.get("specificity_failures") or [])
            if any(leak in scene["text"] for leak in ("Yungmin", "Mira Vale", "The First Crossroads", "Outer Court")):
                stale_data_leaks.append(scene["id"])
            action = CANNED_PLAYER_ACTIONS[i % len(CANNED_PLAYER_ACTIONS)]
            adv = _advance_scene_from_action(scene, action, i)
            adv_qa = run_scene_qa(
                scene=adv,
                campaign_contract=contract,
                campaign_scale_profile=package["campaign_scale_profile"],
                story_shape_profile=package["story_shape_profile"],
                scene_beat_plan={"scene_type": "resolve_action", "primary_scene_purpose": "resolve_action", "gm_move": "show_consequence", "tension_level": 3 + i},
                content_bundle=bundle,
                player_intent={"declared_actions": [action]},
                recent_player_actions=[action],
                current_scene=scene,
                recent_scene_history=[scene],
                recent_motifs=scene.get("visible_clues") or [],
            )
            scores.append(int(adv_qa["quality_score"]))
            continuity_failures.extend(adv_qa.get("continuity_failures") or [])
        repeated = [shape for shape, count in shape_counts.items() if count > 1]
        reports.append({
            "campaign_seed": seed["name"],
            "runs": runs_per_seed,
            "average_quality_score": round(sum(scores) / max(1, len(scores)), 2),
            "freshness_failures": freshness_failures[:10],
            "specificity_failures": specificity_failures[:10],
            "continuity_failures": continuity_failures[:10],
            "repeated_shapes": repeated,
            "stale_data_leaks": stale_data_leaks,
            "recommended_fixes": _recommended_fixes(freshness_failures, specificity_failures, continuity_failures, repeated),
        })
    return reports


def _recommended_fixes(fresh: list[str], spec: list[str], cont: list[str], repeated: list[str]) -> list[str]:
    fixes = []
    if repeated:
        fixes.append("increase opening shape variety for affected seed")
    if fresh:
        fixes.append("tighten freshness context and motif memory")
    if spec:
        fixes.append("add more premise-specific concrete nouns to content bundle")
    if cont:
        fixes.append("repair continuation prose to echo player action")
    return fixes


def main() -> None:
    report = run_quality_regression()
    out = Path("scene_quality_regression_report.json")
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
