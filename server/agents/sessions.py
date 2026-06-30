import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlmodel import Session, select

from .. import db
from ..auth import get_current_user
from ..realtime import broadcaster
from ..storage import documents as doc_storage
from . import image as image_agent
from . import narrative as narrative_agent
from . import narrative_composer as narrative_composer_agent
from . import notes as notes_agent
from . import npc as npc_agent
from . import scene as scene_agent
from . import scene_director as scene_director_agent
from . import simulation as simulation_agent
from . import storyboard as storyboard_agent
from . import suggestions as suggestions_agent
from .entity_schemas import EntityAssociation, PlayerEntityCard
from .narrative_director import DirectorOutput
from .narrative_director import direct_scene as narrative_direct_scene
from .scene_director import SceneDirectorOutput, SceneDirectorRequest, build_image_prompt
from .scene_validator import (
    MINIMUM_SCORE,
    build_fallback_scene,
    build_retry_feedback,
    validate_campaign_expectations,
    validate_scene_quality,
)
from .campaign_interpretation import build_full_contract_package
from .arc_planner import plan_arc
from .situation_classifier import classify_situation, REQUIRES_CONTRACT
from .content_bundles import build_content_bundle, ensure_content_bundle
from .player_intent_parser import parse_player_intent
from .scene_beat_selector import select_scene_beat_plan
from .memory_extractor import extract_memory
from .scene_qa import apply_targeted_scene_repairs, load_recent_opening_shapes, record_opening_shape, run_scene_qa
from .opening_setup import (
    answers_to_anchor,
    auto_generate_anchor,
    build_opening_scene_contract,
    generate_questionnaire,
    validate_first_scene_contract,
    validate_opening_anchor,
    validate_opening_scene_contract,
)
from .canon_manager import (
    load_canon_index,
    save_canon_index,
    apply_memory_delta,
    validate_canon,
)
from .ui_payload_builder import build_ui_payload as build_full_ui_payload
from .story_state import (
    derive_campaign_dna,
    load_story_state,
    save_story_state,
    story_dashboard_payload,
    sync_threads_from_entities,
    update_state_after_scene,
)
from .story_validator import validate_story_quality as validate_story_structure
from .visual_director import run_visual_pipeline
from .visual_state import load_visual_state, save_visual_state

router = APIRouter(prefix="/sessions")

BASE = Path(__file__).resolve().parents[1] / 'sessions'


def is_player_run_mode(session_id: str) -> bool:
    """Return True if the session's campaign has player-run mode enabled."""
    if not session_id:
        return False
    meta_path = BASE / session_id / 'meta.json'
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        return False
    campaign_id = meta.get('campaign_id')
    if not campaign_id:
        return False
    campaign = db.get_campaign_by_id(str(campaign_id))
    if not campaign:
        return False
    settings = (campaign.metadata_json or {}).get('settings') if isinstance(campaign.metadata_json, dict) else {}
    if not isinstance(settings, dict):
        return False
    return bool(settings.get('player_run_mode'))
BASE.mkdir(exist_ok=True)

_doc_store = doc_storage.get_document_store()

_RECYCLED_OPENING_TERMS = (
    "first crossroads",
    "mira vale",
    "sealed packet",
    "something has gone very wrong at the first crossroads",
    "wayward lantern",
    "torven",
    "mara vell",
    "cracked lantern",
    "harness leather",
    "rusty flagon",
    "silver tankard",
    "outer court",
    "envoy marrec",
    "docking concourse",
    "quartermaster vale",
    "rain-dark crossing",
    "waterlogged dispatch tube sealed with split red wax",
    "arcane observatory",
    "a messenger arrives too late",
    "needs help, but is not saying everything",
    "the phenomenon will not repeat for a decade",
    "conversation falters as attention turns toward the same point of trouble",
    "this was not supposed to reach us like this",
    "the trouble that brought",
    "everyone nearby is already deciding who will risk being seen helping",
)


def _contains_recycled_opening_fixture(*values: object) -> bool:
    text = " ".join(str(value or "") for value in values).lower()
    return any(term in text for term in _RECYCLED_OPENING_TERMS)


def _opening_freshness_context(campaign_id: str | None = None, **extra: object) -> dict:
    recent_shapes = [
        shape for shape in load_recent_opening_shapes(limit=20)
        if not campaign_id or str(shape.get("campaign_id") or "") == str(campaign_id)
    ]
    return {
        "scene_count": 0,
        "recent_location_types": [str(s.get("location_type") or "") for s in recent_shapes if s.get("location_type")],
        "recent_opening_events": [str(s.get("inciting_event_type") or "") for s in recent_shapes if s.get("inciting_event_type")],
        "recent_npc_roles": [str(s.get("npc_role") or "") for s in recent_shapes if s.get("npc_role")],
        "recent_symbols": [
            motif
            for s in recent_shapes
            for motif in (s.get("motifs_used") or [])
            if motif
        ],
        "recent_opening_shapes": [str(s.get("opening_shape") or "") for s in recent_shapes if s.get("opening_shape")],
        **extra,
    }


def _opening_narrative_from_seed(required: dict, player_name: str) -> str:
    """Write a direct, coherent opening from required campaign-opening content."""
    loc = str(required.get("starting_location") or "the opening scene")
    identity = str(required.get("location_identity") or "").strip().rstrip(".")
    event = str(required.get("inciting_event") or "").strip().rstrip(".")
    problem = str(required.get("immediate_problem") or "").strip().rstrip(".")
    stakes = str(required.get("specific_stakes") or "").strip().rstrip(".")
    clue = str(required.get("first_clue_or_question") or "").strip().rstrip(".")
    decision = str(required.get("player_decision") or "").strip().rstrip(".")
    npc_label = str(required.get("named_npc_or_visible_threat") or "the nearest named contact")
    npc_name = npc_label.split("(")[0].strip() or "the nearest named contact"
    pc = player_name or "the party"
    pc_sentence = pc[0].upper() + pc[1:] if pc else "The party"

    if not identity:
        identity = f"{loc} is where the first real sign of trouble becomes visible"
    if not event:
        event = "A visible sign of trouble interrupts the scene"
    if not problem:
        problem = "The situation is already moving, and waiting will let someone else control what happens next"
    if not stakes:
        stakes = "If no one acts, the evidence and the chance to help both slip away"
    if not clue:
        clue = "What happened here before anyone arrived?"
    if not decision:
        decision = "Investigate the evidence, question the witness, or move before the trail disappears"

    ctx = required.get("opening_context") or {}
    campaign_brief = required.get("campaign_brief") or {}
    brief_paragraphs = [
        str(p).strip()
        for p in (campaign_brief.get("brief_paragraphs") or [])
        if str(p).strip()
    ] if isinstance(campaign_brief, dict) else []
    anchor_paragraphs: list[str] = []
    arrival = str(ctx.get("arrival_reason") or "").strip().rstrip(".")
    pre_scene = str(ctx.get("pre_scene_activity") or "").strip().rstrip(".")
    personal_stake = str(ctx.get("personal_stake") or "").strip().rstrip(".")
    npc_connection = str(ctx.get("known_npc_connection") or "").strip().rstrip(".")
    party_bond = str(ctx.get("party_bond") or "").strip().rstrip(".")
    complication = str(ctx.get("followed_complication") or "").strip().rstrip(".")
    fear = str(ctx.get("fear_of_loss") or "").strip().rstrip(".")
    if arrival:
        anchor_paragraphs.append(f"{pc_sentence} reaches {loc} with a reason already in motion: {arrival}.")
    if pre_scene:
        anchor_paragraphs.append(f"Before the trouble becomes public, {pc_sentence} {pre_scene}.")
    if personal_stake:
        anchor_paragraphs.append(f"The moment matters because {personal_stake}.")
    if complication:
        anchor_paragraphs.append(f"The complication following close behind is this: {complication}.")
    if fear:
        anchor_paragraphs.append(f"What can be lost is clear: {fear}.")
    if npc_connection:
        anchor_paragraphs.append(f"{npc_connection}.")
    if party_bond and pc.lower() == "the party":
        anchor_paragraphs.append(f"The party holds together because {party_bond}.")
    anchor_intro = "\n\n".join(anchor_paragraphs[:3])
    if anchor_intro:
        anchor_intro += "\n\n"
    brief_intro = ""
    if brief_paragraphs:
        brief_intro = "\n\n".join(brief_paragraphs[:2]).strip()
        if brief_intro:
            brief_intro += "\n\n"

    return (
        f"{brief_intro}{anchor_intro}{loc} is no place for comfort. {identity}.\n\n"
        f"{event}. {npc_name} is closest to it, shaken enough to need help and steady enough to point out what matters.\n\n"
        f"{problem}. The first clear question is simple and dangerous: {clue}\n\n"
        f"{stakes}. {pc_sentence} can still shape the moment: {decision}."
    )


def _opening_anchor_context(anchor: dict) -> dict:
    return {
        "character_name": anchor.get("character_name") or "",
        "arrival_reason": anchor.get("arrival_reason") or "",
        "pre_scene_activity": anchor.get("pre_scene_activity") or "",
        "personal_stake": anchor.get("personal_stake") or "",
        "known_npc_connection": anchor.get("known_npc_connection") or "",
        "party_bond": anchor.get("party_bond") or "",
        "followed_complication": anchor.get("followed_complication") or "",
        "fear_of_loss": anchor.get("fear_of_loss") or "",
        "trust_or_distrust": anchor.get("trust_or_distrust") or anchor.get("known_npc_connection") or "",
        "belief_or_rumor": anchor.get("belief_or_rumor") or "",
        "why_now": anchor.get("personal_stake") or anchor.get("arrival_reason") or anchor.get("belief_or_rumor") or "",
    }


def _anchor_repair_text(anchor: dict, loc_name: str, player_name: str) -> str:
    pc = str(anchor.get("character_name") or player_name or "the party").strip() or "the party"
    pc_sentence = pc[0].upper() + pc[1:] if pc else "The party"
    loc = loc_name or "the opening scene"
    pieces: list[str] = []
    arrival = str(anchor.get("arrival_reason") or "").strip().rstrip(".")
    pre_scene = str(anchor.get("pre_scene_activity") or "").strip().rstrip(".")
    stake = str(anchor.get("personal_stake") or "").strip().rstrip(".")
    npc_connection = str(anchor.get("known_npc_connection") or "").strip().rstrip(".")
    party_bond = str(anchor.get("party_bond") or "").strip().rstrip(".")
    complication = str(anchor.get("followed_complication") or "").strip().rstrip(".")
    fear = str(anchor.get("fear_of_loss") or "").strip().rstrip(".")
    if arrival:
        pieces.append(f"{pc_sentence} reaches {loc} because {arrival}.")
    if pre_scene:
        pieces.append(f"Before anyone can control the moment, {pc_sentence} {pre_scene}.")
    if stake:
        pieces.append(f"The moment is personal because {stake}.")
    if complication:
        pieces.append(f"A complication has followed close behind: {complication}.")
    if fear:
        pieces.append(f"What can be lost is clear: {fear}.")
    if npc_connection:
        pieces.append(f"{npc_connection}.")
    if party_bond and pc.lower() == "the party":
        pieces.append(f"The party stays together because {party_bond}.")
    return "\n\n".join(pieces[:3])


def _apply_opening_anchor_validation(
    scene: dict,
    opening_anchor: dict,
    *,
    player_name: str,
    known_character_names: list[str] | None = None,
) -> tuple[dict, dict]:
    if not opening_anchor:
        return scene, {"valid": True, "anchor_hits": [], "issues": [], "required_hits": 0, "skipped": True}
    validation = validate_opening_anchor(
        scene_text=str(scene.get("text") or scene.get("narrative_body") or ""),
        anchor=opening_anchor,
        selected_character_name=str(opening_anchor.get("character_name") or player_name or ""),
        known_character_names=known_character_names or [],
    )
    if validation.get("valid"):
        return scene, validation
    repair = _anchor_repair_text(opening_anchor, str(scene.get("location") or ""), player_name)
    if repair:
        body = str(scene.get("narrative_body") or scene.get("text") or "")
        prompt = str(scene.get("player_prompt") or "")
        scene["narrative_body"] = f"{repair}\n\n{body}".strip()
        scene["text"] = f"{scene['narrative_body']}\n\n{prompt}".strip()
        validation = validate_opening_anchor(
            scene_text=scene["text"],
            anchor=opening_anchor,
            selected_character_name=str(opening_anchor.get("character_name") or player_name or ""),
            known_character_names=known_character_names or [],
        )
        validation["repair_applied"] = True
    return scene, validation


def _apply_first_scene_contract(
    scene: dict,
    opening_anchor: dict,
    *,
    player_name: str,
    dice_rolls: list[dict] | None = None,
) -> tuple[dict, dict, list[dict]]:
    validation = validate_first_scene_contract(
        scene=scene,
        anchor=opening_anchor,
        player_name=player_name,
        dice_rolls=dice_rolls if dice_rolls is not None else (scene.get("dice_rolls") or []),
    )
    repaired_dice = list(dice_rolls if dice_rolls is not None else (scene.get("dice_rolls") or []))
    if validation.get("valid"):
        return scene, validation, repaired_dice

    loc = str(scene.get("location") or "the opening scene")
    anchor_text = _anchor_repair_text(opening_anchor, loc, player_name)
    choices = scene.get("choices") or []
    if len(choices) < 3:
        scene["choices"] = [
            {"id": "inspect_clue", "label": "Inspect the most obvious clue before anyone moves it"},
            {"id": "question_contact", "label": "Ask the nearest named contact what they saw"},
            {"id": "watch_crowd", "label": "Watch who reacts before choosing a side"},
        ]
    scene["suggested_actions"] = (scene.get("suggested_actions") or [])[:]
    if len(scene["suggested_actions"]) < 3:
        scene["suggested_actions"] = [
            "Inspect the most obvious clue",
            "Question the nearest named contact",
            "Watch who tries to leave",
        ]
    body = str(scene.get("narrative_body") or scene.get("text") or "")
    for forbidden in (
        "follows the first choice through",
        "the useful detail is not separate from the danger",
        "the first witness",
        "the story plan",
        "the scene should",
        "a safe road becomes unsafe",
    ):
        body = re.sub(re.escape(forbidden), "the pressure in the moment becomes visible", body, flags=re.IGNORECASE)
    body = body.replace(" a underground", " an underground").replace(" an surface", " a surface")
    if anchor_text and anchor_text.lower() not in body.lower():
        body = f"{anchor_text}\n\n{body}".strip()
    prompt = str(scene.get("player_prompt") or f"What does {player_name or 'the party'} do?")
    scene["narrative_body"] = body
    scene["text"] = f"{body}\n\n{prompt}".strip()
    supported: list[dict] = []
    lower = scene["text"].lower()
    for roll in repaired_dice:
        skill = str((roll or {}).get("skill") or (roll or {}).get("type") or "").lower()
        reason = str((roll or {}).get("reason") or "").lower()
        if skill and (skill in lower or any(word in lower for word in reason.split() if len(word) > 5)):
            supported.append(roll)
    repaired_dice = supported
    scene["dice_rolls"] = repaired_dice
    validation = validate_first_scene_contract(
        scene=scene,
        anchor=opening_anchor,
        player_name=player_name,
        dice_rolls=repaired_dice,
    )
    validation["repair_applied"] = True
    return scene, validation, repaired_dice


def _apply_concrete_opening_scene_contract(
    scene: dict,
    *,
    required: dict,
    opening_anchor: dict,
    campaign_brief: dict,
    player_name: str,
    time_of_day: str,
) -> tuple[dict, dict]:
    effective_required = {
        **(required or {}),
        "starting_location": scene.get("location") or (required or {}).get("starting_location") or (campaign_brief or {}).get("location_name") or "",
    }
    opening_scene = build_opening_scene_contract(
        required=effective_required,
        anchor=opening_anchor,
        campaign_brief=campaign_brief,
        player_name=player_name,
        time_of_day=time_of_day,
    )
    validation = validate_opening_scene_contract(
        scene=scene,
        opening_scene=opening_scene,
        campaign_brief=campaign_brief,
        anchor=opening_anchor,
        player_name=player_name,
    )
    if not validation.get("valid"):
        actions = opening_scene.get("action_options") or []
        scene = {
            **scene,
            "title": opening_scene.get("scene_title") or scene.get("title") or "Opening Scene",
            "location": opening_scene.get("location_name") or scene.get("location") or "",
            "time_of_day": opening_scene.get("time_of_day") or scene.get("time_of_day") or time_of_day,
            "narrative_body": opening_scene.get("opening_narrative") or scene.get("narrative_body") or "",
            "player_prompt": f"What does {player_name or 'the party'} do?",
            "choices": [
                {"id": f"opening_action_{idx}", "label": str(label)}
                for idx, label in enumerate(actions[:4])
            ],
            "suggested_actions": list(actions[:4]),
            "visible_clues": list(opening_scene.get("key_objects_or_clues") or scene.get("visible_clues") or [])[:4],
            "immediate_stakes": opening_scene.get("pressure_or_timer") or scene.get("immediate_stakes") or "",
            "current_objective": opening_scene.get("visible_problem") or scene.get("current_objective") or "",
            "opening_scene": opening_scene,
        }
        scene["text"] = f"{scene['narrative_body']}\n\n{scene['player_prompt']}".strip()
        validation = validate_opening_scene_contract(
            scene=scene,
            opening_scene=opening_scene,
            campaign_brief=campaign_brief,
            anchor=opening_anchor,
            player_name=player_name,
        )
        validation["repair_applied"] = True
    else:
        scene["opening_scene"] = opening_scene
    scene["opening_scene_validation"] = validation
    return scene, validation


def _dice_rolls_from_content_bundle(content_bundle: dict) -> list[dict]:
    required = (content_bundle or {}).get("required_content") or {}
    checks: list[str] = []
    for key in ("possible_checks", "available_checks"):
        checks.extend(str(item) for item in (required.get(key) or []) if item)
    npc = required.get("npc") or {}
    if isinstance(npc, dict):
        checks.extend(str(item) for item in (npc.get("possible_checks") or []) if item)
    return [
        {"type": "d20", "skill": skill, "reason": "Supported by validated content bundle."}
        for skill in list(dict.fromkeys(checks))[:4]
    ]


def _fallback_response_from_director(
    *,
    director_data: dict,
    loc_name: str,
    npc_name: str,
    player_name: str,
    derived_style: str,
    session_name: str,
    score_detail: dict | None = None,
) -> narrative_agent.NarrativeResponse:
    loc = director_data.get("location") or {}
    npc = director_data.get("primary_npc") or {}
    sensory = ((loc.get("sensory_details") or [])[:1] or [""])[0]
    fallback_text = build_fallback_scene(
        location_name=loc_name or loc.get("name") or "the opening location",
        npc_name=npc_name or npc.get("name") or "the nearest named contact",
        player_name=player_name,
        emotional_state=npc.get("current_emotional_state") or "urgent",
        inciting_incident=director_data.get("inciting_incident") or director_data.get("central_conflict") or "",
        central_conflict=director_data.get("central_conflict") or "",
        immediate_stakes=director_data.get("immediate_stakes") or "",
        sensory_detail=sensory,
        campaign_name=session_name,
    )
    return narrative_agent.NarrativeResponse(
        narrative=fallback_text,
        prompt=f"What does {player_name} do?",
        tone=derived_style,
        scene_score=80,
        score_passed=True,
        score_detail={**(score_detail or {}), "recycled_opening_guard_used": True},
    )


def _campaign_package_from_metadata(campaign, *, character_context: dict | None = None) -> tuple[dict, list[dict], list[dict], dict]:
    """Return (contract, backstory_profiles, backstory_hooks, session_zero).

    If a campaign has no persisted contract yet, generate and persist one from
    existing metadata. When a character sheet backstory is present, fold it into
    the package as player-canon story fuel.
    """
    if not campaign:
        return {}, [], [], {}
    meta = dict(campaign.metadata_json or {})
    backstories = list(meta.get("player_backstories") or [])
    if character_context and (character_context.get("backstory") or "").strip():
        char_id = str(character_context.get("id") or character_context.get("character_id") or character_context.get("name") or "")
        if not any(str(item.get("character_id") or item.get("name") or "") == char_id for item in backstories if isinstance(item, dict)):
            backstories.append({
                "character_id": char_id,
                "character_name": character_context.get("name") or "",
                "backstory": character_context.get("backstory") or "",
            })
    if meta.get("campaign_contract") and backstories == list(meta.get("player_backstories") or []):
        return (
            meta.get("campaign_contract") or {},
            list(meta.get("backstory_profiles") or []),
            list(meta.get("backstory_hooks") or []),
            meta.get("session_zero") or {},
        )
    package = build_full_contract_package(
        campaign_id=str(campaign.id),
        campaign_name=campaign.name,
        description=campaign.description or "",
        settings=meta.get("settings") or {},
        variables=meta.get("variables") or {},
        docs=meta.get("imported_lore") or [],
        backstories=backstories,
    )
    try:
        db.set_campaign_metadata_keys(str(campaign.id), int(campaign.owner_id), {
            "player_backstories": backstories,
            "campaign_interpretation": package.get("campaign_interpretation", {}),
            "campaign_contract": package.get("campaign_contract", {}),
            "backstory_profiles": package.get("backstory_profiles", []),
            "backstory_hooks": package.get("backstory_hooks", []),
            "backstory_thread_links": package.get("backstory_thread_links", []),
            "backstory_spotlight": package.get("backstory_spotlight", []),
            "session_zero": package.get("session_zero", {}),
            "campaign_contract_debug": package.get("debug", {}),
        })
    except Exception:
        pass
    return (
        package.get("campaign_contract", {}),
        package.get("backstory_profiles", []),
        package.get("backstory_hooks", []),
        package.get("session_zero", {}),
    )


def _repair_recycled_opening_scene_if_needed(folder: Path, scene: dict, *, meta: dict | None = None) -> dict:
    """Replace stale canned openings that were written before the content gate existed."""
    if not isinstance(scene, dict):
        return scene
    scene_text = json.dumps(scene, default=str)
    if not _contains_recycled_opening_fixture(scene_text):
        return scene

    meta = meta or {}
    try:
        meta_path = folder / "meta.json"
        if not meta and meta_path.exists():
            meta = json.loads(meta_path.read_text())
    except Exception:
        meta = {}

    campaign = None
    campaign_id = str(meta.get("campaign_id") or "").strip()
    if campaign_id:
        try:
            campaign = db.get_campaign_by_id(campaign_id)
        except Exception:
            campaign = None

    campaign_meta = dict(getattr(campaign, "metadata_json", None) or {})
    settings = dict(campaign_meta.get("settings") or {})
    if campaign and not settings.get("setting_summary"):
        settings["setting_summary"] = getattr(campaign, "description", "") or ""
    contract, _profiles, _hooks, _session_zero = _campaign_package_from_metadata(campaign) if campaign else ({}, [], [], {})
    if campaign and not contract.get("campaign_name"):
        contract = {**contract, "campaign_name": getattr(campaign, "name", "")}
    if campaign and not contract.get("campaign_pitch"):
        contract = {**contract, "campaign_pitch": getattr(campaign, "description", "") or settings.get("setting_summary", "")}

    content_bundle = ensure_content_bundle(
        "campaign_opening",
        scene_director_output={},
        campaign_contract=contract,
        freshness_context={"scene_count": 0, "repaired_recycled_opening": True},
        campaign_settings=settings,
        max_attempts=3,
    )
    required = content_bundle.get("required_content") or {}
    if required.get("generated_by") != "premise_seed" and _contains_recycled_opening_fixture(json.dumps(required, default=str)):
        fallback_loc = scene_director_agent._location_from_text(  # type: ignore[attr-defined]
            " ".join([
                str(settings.get("setting_summary") or ""),
                str(contract.get("campaign_pitch") or ""),
                str(getattr(campaign, "name", "") or meta.get("name") or ""),
            ]),
            str(settings.get("genre") or ""),
        )
        if _contains_recycled_opening_fixture(fallback_loc):
            fallback_loc = "The Opening Ground"
        fallback_npc = scene_director_agent._contact_from_text(  # type: ignore[attr-defined]
            " ".join([
                str(settings.get("setting_summary") or ""),
                str(contract.get("campaign_pitch") or ""),
                str(getattr(campaign, "name", "") or meta.get("name") or ""),
            ]),
            str(settings.get("genre") or ""),
        )
        required = {
            "starting_location": fallback_loc,
            "location_type": "opening location",
            "location_identity": f"{fallback_loc} holds the first visible sign of the campaign's trouble.",
            "inciting_event": "A local warning arrives before anyone has agreed what it means.",
            "named_npc_or_visible_threat": f"{fallback_npc} (local witness)",
            "immediate_problem": "Someone nearby is trying to control what the party learns first.",
            "specific_stakes": "If the moment passes, the first clear lead becomes much harder to follow.",
            "first_clue_or_question": "Who benefits if this warning is ignored?",
            "player_decision": "Question the witness, inspect the warning, or watch who tries to leave.",
            "generated_by": "repair_seed",
        }
        content_bundle = {
            **content_bundle,
            "required_content": required,
            "memory_updates": [],
            "ui_payload": {},
            "content_gate_passed": True,
        }
    location_name = str(required.get("starting_location") or settings.get("world_name") or "The Opening Ground")
    npc_label = str(required.get("named_npc_or_visible_threat") or "Sera Vane")
    npc_name = npc_label.split("(")[0].strip() or "Sera Vane"
    player_names = _session_player_names(folder, meta)
    player_name = player_names[0] if player_names else "the party"
    sensory = str(required.get("location_identity") or "")
    inciting = str(required.get("inciting_event") or required.get("first_clue_or_question") or "")
    conflict = str(required.get("immediate_problem") or inciting)
    stakes = str(required.get("specific_stakes") or "")
    if required.get("generated_by") == "premise_seed":
        narrative = _opening_narrative_from_seed(required, player_name)
    else:
        narrative = build_fallback_scene(
            location_name=location_name,
            npc_name=npc_name,
            player_name=player_name,
            emotional_state="focused and wary",
            inciting_incident=inciting,
            central_conflict=conflict,
            immediate_stakes=stakes,
            sensory_detail=sensory,
            campaign_name=str(getattr(campaign, "name", "") or meta.get("name") or ""),
        )
    if _contains_recycled_opening_fixture(narrative):
        return scene

    prompt = f"What does {player_name} do?"
    repaired = {
        "id": scene.get("id") or "opening",
        "title": f"Opening — {location_name}",
        "image": None if _contains_recycled_opening_fixture(scene.get("image")) else scene.get("image"),
        "text": narrative,
        "narrative_body": narrative,
        "player_prompt": prompt,
        "prompt": prompt,
        "scene_type": scene.get("scene_type") or "opening",
        "location": location_name,
        "location_detail": {"name": location_name, "description": sensory},
        "primary_npc": {"name": npc_name, "role": npc_label},
        "content_bundle": content_bundle,
        "current_objective": str(required.get("player_decision") or conflict),
        "immediate_stakes": stakes,
        "visible_clues": [str(required.get("first_clue_or_question") or inciting)],
        "choices": [
            {"id": "press", "label": f"Ask {npc_name} what they know"},
            {"id": "inspect", "label": "Inspect the most obvious sign of trouble"},
            {"id": "watch", "label": "Watch who reacts before acting"},
        ],
        "scene_director_data": {
            "source": "recycled_fixture_repair",
            "scene_title": f"Opening — {location_name}",
            "scene_type": "opening",
            "location": {"name": location_name, "sensory_details": [sensory] if sensory else []},
            "primary_npc": {
                "name": npc_name,
                "role": npc_label,
                "current_emotional_state": "focused and wary",
                "what_they_want": str(required.get("player_decision") or "resolve the immediate danger"),
                "what_they_know": str(required.get("first_clue_or_question") or ""),
            },
            "central_conflict": conflict,
            "inciting_incident": inciting,
            "immediate_stakes": stakes,
        },
    }
    simulation_agent.atomic_write_json(folder / "scene.json", repaired)
    return repaired


def _normalize_scene_render_fields(folder: Path, scene: dict) -> dict:
    """Keep scene.json render-facing fields compatible with the React client."""
    if not isinstance(scene, dict):
        return scene
    changed = False
    normalized = dict(scene)
    loc = normalized.get("location")
    if isinstance(loc, dict):
        loc_name = str(loc.get("name") or loc.get("title") or "").strip()
        if loc_name:
            normalized["location"] = loc_name
            normalized.setdefault("location_detail", loc)
            changed = True
    image = normalized.get("image")
    if isinstance(image, dict):
        image_loc = image.get("location")
        if isinstance(image_loc, dict):
            image_loc_name = str(image_loc.get("name") or image_loc.get("title") or "").strip()
            normalized["image"] = {**image, "location": image_loc_name}
            changed = True
    if changed:
        simulation_agent.atomic_write_json(folder / "scene.json", normalized)
    return normalized


def _session_player_names(folder: Path, meta: dict) -> list[str]:
    names: list[str] = []
    try:
        pcs_path = folder / 'pcs.json'
        if pcs_path.exists():
            pcs_raw = json.loads(pcs_path.read_text()) or []
            for pc in pcs_raw:
                if not isinstance(pc, dict):
                    continue
                name = str(pc.get('name') or pc.get('character_name') or '').strip()
                if name and name not in names:
                    names.append(name)
    except Exception:
        pass
    for member in meta.get('members', []) or []:
        if not isinstance(member, dict):
            continue
        if not member.get('character_id'):
            continue
        name = str(member.get('character_name') or '').strip()
        if name and name not in names:
            names.append(name)
    return names


def _load_story_entries(folder: Path) -> list[dict]:
    story_path = folder / "story.json"
    try:
        cur = json.loads(story_path.read_text()) if story_path.exists() else []
    except Exception:
        cur = []
    if isinstance(cur, list):
        return [entry for entry in cur if isinstance(entry, dict)]
    if isinstance(cur, dict):
        return [cur]
    return []


def _story_last_timestamp(entries: list[dict]) -> datetime | None:
    latest: datetime | None = None
    for entry in entries:
        if entry.get("type") not in ("narration", "narrative.scene"):
            continue
        raw = entry.get("ts")
        if not isinstance(raw, str) or not raw:
            continue
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if latest is None or parsed > latest:
            latest = parsed
    return latest


def _story_roll_entries_since(campaign_id: str | None, by: str | None, since: datetime | None) -> list[dict]:
    if not campaign_id:
        return []
    entries: list[dict] = []
    try:
        with Session(db.engine) as session:
            stmt = select(db.Roll).where(db.Roll.campaign_id == str(campaign_id))
            if by:
                stmt = stmt.where(db.Roll.by == by)
            rolls = list(session.exec(stmt).all())
    except Exception:
        return []
    for roll in rolls:
        created_raw = roll.created_at or ""
        try:
            created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except Exception:
            created = None
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if since and created and created <= since:
            continue
        total = int(roll.total or 0)
        expression = roll.expression or "roll"
        dice = ", ".join(str(v) for v in (roll.rolls or []))
        detail = f"{expression}"
        if dice:
            detail += f" [{dice}]"
        if roll.mod:
            detail += f" {'+' if roll.mod > 0 else ''}{roll.mod}"
        entries.append({
            "type": "roll",
            "ts": created.isoformat() if created else datetime.now(timezone.utc).isoformat(),
            "text": f"{roll.by or 'Player'} rolled {detail}: {total}.",
            "roll": {
                "expression": expression,
                "rolls": roll.rolls or [],
                "mod": roll.mod,
                "total": total,
                "by": roll.by,
            },
        })
    return sorted(entries, key=lambda e: str(e.get("ts") or ""))


def _story_action_entries_since(messages: list, since: datetime | None) -> list[dict]:
    entries: list[dict] = []
    for msg in messages:
        if getattr(msg, "role", "player") in ("gm", "narrator", "system"):
            continue
        created = getattr(msg, "created_at", None)
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if since and created and created <= since:
            continue
        text = (getattr(msg, "message", "") or "").strip()
        if not text:
            continue
        sender = getattr(msg, "sender_name", None) or "Player"
        entries.append({
            "type": "player_action",
            "ts": created.isoformat() if created else datetime.now(timezone.utc).isoformat(),
            "text": f"{sender}: {text}",
            "message_id": getattr(msg, "id", None),
        })
    return entries


def _write_story_entries(folder: Path, entries: list[dict]) -> None:
    simulation_agent.atomic_write_json(folder / "story.json", entries)


def _action_response_scene(
    *,
    player_name: str,
    location_name: str,
    latest_action: str,
    action_count: int,
    approved_context: dict | None = None,
) -> dict:
    """Deterministic action-result narration when the LLM cannot produce prose."""
    pc = player_name or "you"
    loc = location_name or "the current location"
    action = (latest_action or "").strip()
    lower = action.lower()
    context = f"{loc} {action}".lower()
    approved = approved_context or {}
    approved_clue = str(approved.get("clue") or approved.get("first_clue_or_question") or "").strip()
    approved_object = str(approved.get("object") or approved.get("approved_object") or "").strip()
    approved_stakes = str(approved.get("stakes") or approved.get("specific_stakes") or "").strip()
    approved_npc = str(approved.get("npc") or approved.get("named_npc_or_visible_threat") or "").split("(")[0].strip()
    concrete_detail = approved_object or approved_clue or (
        "blackened charm" if "charm" in lower else
        "water seal" if "water" in lower or "seal" in lower else
        "marked clue"
    )

    title = "The Next Move"
    objective = f"Turn {action[:80] or 'the latest move'} into a concrete advantage at {loc}."
    stakes = approved_stakes or f"If the party waits, the clearest lead at {loc} is disturbed before it can be tested."
    clues = [
        approved_clue or f"The {concrete_detail} does not match the explanation people are giving.",
        f"{approved_npc or 'Someone present'} reacts before they can hide it.",
        f"{pc}'s action changes what is safe to ask or attempt next.",
    ]
    moves = [
        f"Pressure around {loc} increases as word of the disturbance spreads.",
        "Someone with private knowledge adjusts their plan.",
    ]
    actions = [
        "Press the person who reacted first",
        "Examine the detail that does not fit",
        "Move to a better position",
        "Ask what everyone is avoiding",
    ]

    if any(word in context for word in ("northwood", "hiding place", "slave army", "escape", "escaped", "camp", "march north", "pack up", "move on")):
        title = "Breaking Camp"
        if any(word in lower for word in ("pack", "move", "leave", "march", "go", "on")):
            body = (
                f"{pc} turns the quiet decision into motion. Blankets are rolled with stiff fingers, "
                "cold ash is kicked apart, and every strap is checked twice because a loose buckle can sound "
                f"like a bell in the trees around {loc}.\n\n"
                "The hiding place answers in small betrayals. A heel-print near the edge of camp is too deep, "
                "made by someone carrying weight or dragging fear behind them. A broken twig points north by "
                "habit, not accident. Farther off, where the wind moves through bare branches, a horn gives one "
                "short note and then stops as if the searchers are listening for what the camp will do next.\n\n"
                f"{pc} can feel the choice narrowing. Leaving now may keep the escapees ahead of the army, "
                "but a rushed departure will leave a trail any practiced tracker can read. Staying long enough "
                "to clean the site may save lives tomorrow and cost them the lead today.\n\n"
                "One person in the group hesitates over a half-buried scrap of cloth caught under a root. It is "
                "not camp gear. It is dyed in the color of the marching column, and it is fresh."
            )
            objective = "Choose the escape route and decide whether to hide the camp's trail."
            stakes = "Moving fast protects the escapees from encirclement; moving carelessly gives the army a road to follow."
            clues = [
                "A heavy heel-print marks the edge of camp.",
                "A fresh scrap of army-colored cloth is caught under a root.",
                "A distant horn suggests the search line is closer than anyone hoped.",
            ]
            moves = [
                "The army search line tests the woods with short horn calls.",
                "A frightened escapee delays the group over something they found.",
                "The weather begins to preserve tracks instead of hiding them.",
            ]
            actions = [
                "Hide the camp's trail before leaving",
                "Inspect the army-colored cloth",
                "Send someone ahead to find safer ground",
                "Question who stepped near the camp edge",
            ]
        else:
            body = (
                f"{pc}'s words settle over {loc} and make the silence honest. The escapees stop pretending this "
                "is a rest. It is a decision point: the last pocket of stillness before the woods either protects "
                "them or gives them away.\n\n"
                "A woman with mud on one sleeve grips her pack too tightly. A younger man keeps watching the "
                "tree line instead of the speaker. Neither of them interrupts, but both know something about the "
                "route that no one has said aloud.\n\n"
                f"Wind drags old leaves across the camp's border. Under that dry scraping, {pc} hears a second "
                "sound: leather, brushed once against bark, then held still. Someone outside the hiding place is "
                "close enough to be careful.\n\n"
                "The camp has seconds before fear turns into noise. A clear order, a quiet spell, or one sharp "
                "question could decide whether the group moves as fugitives or scatters as prey."
            )
            objective = "Find out who knows the unsafe route before the camp breaks into panic."
            stakes = "If the group loses discipline, the hidden camp becomes visible before anyone chooses a direction."
            clues = [
                "Two escapees react like they know more about the route.",
                "A careful sound comes from beyond the camp edge.",
                "The hiding place is close to becoming noisy.",
            ]
            actions = [
                "Question the two nervous escapees",
                "Listen for the watcher outside camp",
                "Cast a quiet protective spell",
                "Give the group a clear marching order",
            ]
    elif any(word in lower for word in ("detect magic", "arcana", "ritual", "spell")) or (
        "cast" in lower and not any(word in lower for word in ("mage armor", "light"))
    ):
        title = "A Trace in the Air"
        body = (
            f"{pc} lets the working settle over {loc}. The first answer is not light or sound, but a pressure "
            "behind the eyes, as if the place is remembering a shape it was forced to hold.\n\n"
            "A faint trace gathers around the most handled surface nearby. It is not enough to explain the whole "
            "danger, but it proves the trouble was deliberate, recent, and touched by someone who expected not to be noticed.\n\n"
            "The residue is strongest where ordinary attention would skip past it: the underside of a latch, the seam "
            "of a wrapped object, the dark line where dust should have settled evenly and did not.\n\n"
            "Following it will take focus. Disturbing it will make the next answer harder to trust."
        )
        objective = "Follow the fresh magical trace before it fades or is hidden."
        clues = ["A recent magical trace is present.", "The effect was deliberate.", "Someone expected the sign to be overlooked."]
        actions = ["Follow the trace", "Identify the magic", "Ask who handled the marked object", "Shield the area from interference"]
    elif any(word in lower for word in ("ask", "question", "talk", "press", "persuade")):
        title = "The Answer Between Answers"
        target_detail = approved_object or approved_clue or f"{loc}'s guarded clue"
        witness = approved_npc or "the witness"
        body = (
            f"{pc}'s question lands harder than expected. The first answer is too quick, too polished, and the second "
            f"comes only after an uncomfortable silence from {witness}.\n\n"
            f"The useful part is not the words. It is the glance that follows them: toward {target_detail}, "
            f"the detail everyone else at {loc} has been carefully pretending is ordinary.\n\n"
            f"{witness} notices that glance being noticed and changes posture, one shoulder turning as if to hide "
            "what their hands are doing. The room keeps breathing, but it is no longer relaxed.\n\n"
            "There is a narrow opening now. Press too softly and it closes. Press too hard and the person with the truth "
            f"may bolt before {pc} can learn why they are afraid."
        )
        objective = f"Use the nervous glance to learn why {target_detail} is being protected."
        clues = [approved_clue or "The first answer is rehearsed.", f"A nervous glance points toward {target_detail}.", f"{witness} is withholding the useful part of the truth."]
        actions = [f"Follow the glance toward {target_detail}", "Ask a sharper follow-up", f"Separate {witness}", "Offer protection for honesty"]
    elif any(word in lower for word in ("search", "inspect", "examine", "investigate", "track", "look")):
        title = "The Detail Out of Place"
        target_detail = approved_object or approved_clue or concrete_detail
        witness = approved_npc or "the nearest witness"
        body = (
            f"{pc} slows down and lets {loc} become physical: scuffs, dust, disturbed edges, and {target_detail} "
            "held against the light long enough for the false story to split from the real one.\n\n"
            f"The clearest sign is small, but fresh. {approved_clue or f'The {target_detail} points away from the center of attention.'} "
            f"{witness} sees the same detail and goes still.\n\n"
            f"Once seen, {target_detail} becomes hard to ignore. A smear breaks the pattern nearby, and a thread catches "
            "on a rough edge as if someone passed through in a hurry.\n\n"
            f"{stakes}"
        )
        objective = f"Use {target_detail} before the trail is disturbed."
        clues = [approved_clue or f"{target_detail} contradicts the obvious story.", f"{witness} reacts to the detail.", "Someone used a less visible route."]
        actions = [f"Follow the sign from {target_detail}", "Preserve the evidence", "Compare it to nearby surfaces", f"Ask {witness} who had access"]
    elif any(word in lower for word in ("watch", "scan", "observe", "listen")):
        title = "What Moves First"
        body = (
            f"{pc} waits instead of filling the silence. That patience catches what movement would have missed: one person "
            "reacts to the wrong detail, and another notices that reaction before looking away.\n\n"
            "The room has a pattern now. Fear near the center, calculation near the edge, and a narrow gap where someone may slip out.\n\n"
            "A sleeve brushes against a pouch. A boot turns toward the nearest exit. Someone who should be relieved looks "
            f"angry instead, as though {pc} has accidentally stepped on the one part of the truth they needed buried.\n\n"
            "The next move can be quiet or direct, but it has to be chosen before the room realizes it has been read."
        )
        objective = "Decide whether to confront the reaction or quietly follow the person trying to leave."
        clues = ["One person reacts to the wrong detail.", "Another person notices and looks away.", "Someone may be preparing to leave."]
        actions = ["Confront the first reaction", "Follow the person near the edge", "Signal an ally", "Block the quiet exit"]
    else:
        title = "A Choice Takes Shape"
        body = (
            f"{pc} acts, and {loc} changes in response. Not dramatically at first: a pause in conversation, a shift of weight, "
            "a hand leaving something half-covered instead of finishing the motion.\n\n"
            "That small hesitation gives the scene texture. The danger is not abstract anymore. It has a direction, a witness, "
            "and at least one person who understands more than they meant to reveal.\n\n"
            "Near the edge of attention, a detail stands out because it does not belong with the story everyone is accepting. "
            "It could be evidence, bait, or the first honest sign in the room.\n\n"
            f"{pc} has room for one clean follow-up before the moment disperses: press the witness, secure the detail, or "
            "move before the people with something to hide can rearrange themselves."
        )

    if action_count >= 8:
        stakes = f"The longer {pc} waits, the more the trail spreads beyond easy reach."

    return {
        "title": title,
        "narrative": body,
        "objective": objective,
        "stakes": stakes,
        "clues": clues,
        "world_moves": moves[:4],
        "suggested_actions": actions[:5],
    }


def _identifier_for_user(user) -> str:
    value = (getattr(user, 'email', None) or getattr(user, 'username', '') or '').strip()
    return value.lower()


def _normalize_email(value: str | None) -> str:
    return (value or '').strip().lower()


def _normalize_invites(raw):
    normalized = []
    for entry in raw or []:
        if isinstance(entry, str):
            normalized.append({
                'email': _normalize_email(entry),
                'min_level': 1,
                'accepted': False,
                'character_id': None,
                'character_name': None,
            })
        elif isinstance(entry, dict):
            normalized.append({
                'email': _normalize_email(entry.get('email')),
                'min_level': max(1, int(entry.get('min_level', 1))),
                'accepted': bool(entry.get('accepted', False)),
                'character_id': entry.get('character_id'),
                'character_name': entry.get('character_name'),
                'note': entry.get('note'),
                'accepted_at': entry.get('accepted_at'),
            })
    return normalized


def create_session_folder(
    name: str,
    owner_email: str,
    invites=None,
    campaign_id: str | None = None,
    owner_character_id: int | None = None,
    owner_role: str = "owner",
    opening_setup_required: bool = False,
):
    """Create a session folder programmatically and return the session id and meta."""
    sid = uuid.uuid4().hex[:8]
    folder = BASE / sid
    if folder.exists():
        raise Exception('Session id collision')
    folder.mkdir(parents=True)
    owner_character_name = None
    if owner_character_id is not None:
        try:
            owner_user = db.get_user_by_identifier(owner_email)
            if owner_user and owner_user.id is not None:
                owner_character = db.get_character_for_owner(int(owner_character_id), int(owner_user.id))
                if owner_character:
                    owner_character_name = owner_character.name
                else:
                    owner_character_id = None
        except Exception:
            owner_character_id = None
            owner_character_name = None

    normalized_owner_role = "dm" if owner_role == "dm" else "owner"
    meta = {
        'id': sid,
        'name': name,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'owner': owner_email,
        'campaign_id': campaign_id,
        'invites': _normalize_invites(invites or []),
        'members': [
            {
                'email': owner_email,
                'character_id': owner_character_id,
                'character_name': owner_character_name,
                'role': normalized_owner_role,
            }
        ],
        'opening_setup': {
            'required': bool(opening_setup_required),
            'completed': False,
            'questionnaire_id': None,
            'anchors': [],
        },
    }
    (folder / 'meta.json').write_text(json.dumps(meta))
    (folder / 'notes.md').write_text(f'# Notes for {name}\n')
    (folder / 'npcs.json').write_text('[]')
    (folder / 'pcs.json').write_text('[]')
    (folder / 'associations.json').write_text('[]')
    (folder / 'story.json').write_text(json.dumps([{'type': 'meta', 'text': 'The session begins.'}]))
    (folder / 'scene.json').write_text(json.dumps({
        'id': 'opening',
        'title': f"{name} - Setup Pending",
        'image': None,
        'text': 'Complete the campaign brief and character setup to begin the opening scene.',
        'narrative_body': 'Complete the campaign brief and character setup to begin the opening scene.',
        'player_prompt': '',
        'choices': [],
        'suggested_actions': [],
        'setup_pending': True,
    }))
    simulation_agent.atomic_write_json(folder / 'world_state.json', simulation_agent.default_world_state())
    simulation_agent.atomic_write_json(folder / 'persistent_npcs.json', [])
    simulation_agent.atomic_write_json(folder / 'locations_dynamic.json', [])
    simulation_agent.atomic_write_json(folder / 'canon_memory.json', [])

    # Default documents:
    # - Some are player-visible (shared)
    # - Some are AI-GM private (category=gm + visibility=hidden) and are hidden from the UI.
    try:
        _doc_store.save_document(
            session_id=sid,
            name='Session Notes',
            content='# Session Notes\n\n- ',
            category='core',
            visibility='shared',
        )
        _doc_store.save_document(
            session_id=sid,
            name='GM Scratchpad',
            content='(AI GM private)\n\nUse this for behind-the-scenes state, secrets, and internal tracking.',
            category='gm',
            visibility='hidden',
        )
        _doc_store.save_document(
            session_id=sid,
            name='GM World State',
            content='(AI GM private)\n\n- Open threads:\n- Secrets:\n- NPC motives:\n',
            category='gm',
            visibility='hidden',
        )
    except Exception:
        # Documents are best-effort; session creation must still succeed.
        pass
    return sid, meta


def _user_is_member(meta: dict, identifier: str) -> bool:
    owner = _normalize_email(meta.get('owner'))
    if identifier == owner:
        return True
    invites = _normalize_invites(meta.get('invites'))
    if any(inv['email'] == identifier for inv in invites):
        return True
    for member in meta.get('members', []) or []:
        if _normalize_email(member.get('email')) == identifier:
            return True
    return False


class CreateSessionRequest(BaseModel):
    name: str
    owner: str | None = None


@router.post('', status_code=201)
def create_session(req: CreateSessionRequest, current_user=Depends(get_current_user)):
    try:
        owner_email = current_user.email or current_user.username
        sid, meta = create_session_folder(req.name, owner_email, invites=[])
        return {'id': sid, 'name': req.name, 'owner': owner_email}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get('', response_model=list[dict])
def list_sessions(current_user=Depends(get_current_user)):
    out = []
    identifier = _identifier_for_user(current_user)
    for p in BASE.iterdir():
        if p.is_dir():
            meta = p / 'meta.json'
            if meta.exists():
                try:
                    d = json.loads(meta.read_text())
                except Exception:
                    d = {'id': p.name, 'name': p.name}
            else:
                d = {'id': p.name, 'name': p.name}
            # filter to sessions where the current user is owner, invited, or already a member
            if _user_is_member(d, identifier):
                d['invites'] = _normalize_invites(d.get('invites'))
                d['members'] = d.get('members', []) or []
                out.append(d)
    return out


@router.get('/{session_id}/files')
def get_files(session_id: str, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_file = folder / 'meta.json'
    if meta_file.exists():
        data = json.loads(meta_file.read_text())
        identifier = _identifier_for_user(current_user)
        if not _user_is_member(data, identifier):
            raise HTTPException(status_code=403, detail='Not a member of this session')
    files = [p.name for p in folder.iterdir() if p.is_file()]
    return {'files': files}


@router.get('/{session_id}/meta')
def get_meta(session_id: str, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta = folder / 'meta.json'
    if not meta.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        data = json.loads(meta.read_text())
        identifier = _identifier_for_user(current_user)
        if not _user_is_member(data, identifier):
            raise HTTPException(status_code=403, detail='Not a member of this session')
        data['invites'] = _normalize_invites(data.get('invites'))
        data['members'] = data.get('members', []) or []
        return data
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err


class SetCharacterRequest(BaseModel):
    character_id: int | None = None


@router.post('/{session_id}/character')
def set_character_for_session(session_id: str, req: SetCharacterRequest, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')

    try:
        data = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    if not _user_is_member(data, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    owner_id = getattr(current_user, 'id', None)
    if not isinstance(owner_id, int):
        raise HTTPException(status_code=401, detail='Invalid authentication credentials')

    character_name = None
    if req.character_id is not None:
        character = db.get_character_for_owner(req.character_id, owner_id)
        if not character:
            raise HTTPException(status_code=404, detail='Character not found')
        character_name = character.name

    members = data.get('members', []) or []
    owner_normalized = _normalize_email(data.get('owner'))
    role = 'owner' if identifier == owner_normalized else 'member'

    found = False
    for member in members:
        same_user = _normalize_email(member.get('email')) == identifier
        same_character = member.get('character_id') == req.character_id
        empty_slot = member.get('character_id') is None
        if same_user and (same_character or empty_slot):
            member['character_id'] = req.character_id
            member['character_name'] = character_name
            member.setdefault('role', role)
            found = True
            break

    if not found:
        members.append({
            'email': identifier,
            'character_id': req.character_id,
            'character_name': character_name,
            'role': role,
        })

    data['members'] = members
    meta_path.write_text(json.dumps(data))
    return {'ok': True, 'session_id': session_id, 'character_id': req.character_id, 'character_name': character_name}


class JoinSessionRequest(BaseModel):
    character_id: int


@router.post('/{session_id}/join')
def join_session_with_character(session_id: str, req: JoinSessionRequest, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')

    try:
        data = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    invites = _normalize_invites(data.get('invites'))
    invite = next((item for item in invites if item.get('email') == identifier and not item.get('accepted')), None)
    owner = _normalize_email(data.get('owner'))
    if not invite and identifier != owner:
        raise HTTPException(status_code=403, detail='No pending invite for this account')

    owner_id = getattr(current_user, 'id', None)
    if not isinstance(owner_id, int):
        raise HTTPException(status_code=401, detail='Invalid authentication credentials')

    character = db.get_character_for_owner(req.character_id, owner_id)
    if not character:
        raise HTTPException(status_code=404, detail='Character not found')
    if invite and character.level < int(invite.get('min_level') or 1):
        raise HTTPException(status_code=400, detail='Character does not meet invite level requirement')

    members = data.get('members', []) or []
    already_joined = any(
        _normalize_email(member.get('email')) == identifier
        and member.get('character_id') == req.character_id
        for member in members
    )
    if not already_joined:
        members.append({
            'email': identifier,
            'character_id': req.character_id,
            'character_name': character.name,
            'role': 'member' if identifier != owner else 'owner',
            'joined_at': datetime.now(timezone.utc).isoformat(),
        })

    if invite:
        invite['accepted'] = True
        invite['character_id'] = req.character_id
        invite['character_name'] = character.name
        invite['accepted_at'] = datetime.now(timezone.utc).isoformat()

    data['members'] = members
    data['invites'] = invites
    meta_path.write_text(json.dumps(data))
    return {
        'ok': True,
        'session_id': session_id,
        'character_id': req.character_id,
        'character_name': character.name,
    }


@router.delete('/{session_id}/file/{filename}')
def delete_file(session_id: str, filename: str, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    target = folder / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail='File not found')
    try:
        # membership check
        meta = folder / 'meta.json'
        if meta.exists():
            data = json.loads(meta.read_text())
            identifier = _identifier_for_user(current_user)
            if not _user_is_member(data, identifier):
                raise HTTPException(status_code=403, detail='Not a member of this session')
        target.unlink()
        return {'ok': True}
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to delete file') from err


@router.get('/{session_id}/file/{filename}')
def get_file(session_id: str, filename: str, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    target = folder / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail='File not found')
    # membership check
    meta = folder / 'meta.json'
    if meta.exists():
        data = json.loads(meta.read_text())
        identifier = _identifier_for_user(current_user)
        if not _user_is_member(data, identifier):
            raise HTTPException(status_code=403, detail='Not a member of this session')

    text = target.read_text()
    # try to return json if parseable
    try:
        parsed = json.loads(text)
        if filename == "scene.json" and isinstance(parsed, dict):
            repaired = _repair_recycled_opening_scene_if_needed(folder, parsed, meta=data if meta.exists() else {})
            return _normalize_scene_render_fields(folder, repaired)
        return parsed
    except Exception:
        return {'content': text}


class SaveFileRequest(BaseModel):
    content: str


@router.post('/{session_id}/file/{filename}')
def save_file(session_id: str, filename: str, req: SaveFileRequest, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    # membership check
    meta = folder / 'meta.json'
    if meta.exists():
        data = json.loads(meta.read_text())
        identifier = _identifier_for_user(current_user)
        if not _user_is_member(data, identifier):
            raise HTTPException(status_code=403, detail='Not a member of this session')
    target = folder / filename
    target.write_text(req.content)
    return {'ok': True}


class InviteRequest(BaseModel):
    identifier: str | None = None
    email: str | None = None
    note: str | None = None

    @model_validator(mode='after')
    def _ensure_identifier(self):
        if not (self.identifier or self.email):
            raise ValueError('identifier required')
        if not self.identifier:
            self.identifier = self.email
        return self


class BootstrapRequest(BaseModel):
    style: str | None = None
    weather: str | None = None
    time_of_day: str | None = None


def _opening_setup_default(required: bool = False) -> dict:
    return {
        "required": bool(required),
        "completed": False,
        "questionnaire_id": None,
        "campaign_brief": {},
        "anchors": [],
    }


def _selected_character_from_meta(meta: dict) -> dict:
    for member in meta.get("members", []) or []:
        char_id = member.get("character_id")
        if not char_id:
            continue
        try:
            ch = db.get_character_by_id(int(char_id))
            if ch:
                sheet = ch.sheet or {}
                return {
                    "id": ch.id,
                    "name": ch.name or member.get("character_name") or "",
                    "class_name": ch.class_name or "",
                    "level": ch.level or 1,
                    "backstory": sheet.get("backstory") or "",
                    "personality_traits": sheet.get("personality_traits") or "",
                    "ideals": sheet.get("ideals") or "",
                    "bonds": sheet.get("bonds") or "",
                    "flaws": sheet.get("flaws") or "",
                }
        except Exception:
            pass
    return {"id": "", "name": "the party"}


def _opening_anchor_from_meta(meta: dict) -> dict:
    setup = meta.get("opening_setup") or {}
    anchors = setup.get("anchors") or []
    if anchors:
        return anchors[0]
    return {}


def _build_opening_setup_questionnaire(folder: Path, meta: dict) -> dict:
    campaign_id = str(meta.get("campaign_id") or "")
    campaign_contract: dict = {}
    campaign_scale_profile: dict = {}
    story_shape_profile: dict = {}
    backstory_hooks: list[dict] = []
    campaign_settings: dict = {}
    campaign = db.get_campaign_by_id(campaign_id) if campaign_id else None
    if campaign and isinstance(campaign.metadata_json, dict):
        campaign_settings = campaign.metadata_json.get("settings") or {}
        campaign_contract, _profiles, backstory_hooks, _session_zero = _campaign_package_from_metadata(campaign)
        campaign_scale_profile = campaign.metadata_json.get("campaign_scale_profile") or campaign_contract.get("campaign_scale_profile") or {}
        story_shape_profile = campaign.metadata_json.get("story_shape_profile") or campaign_contract.get("story_shape_profile") or {}
    try:
        opening_seed = ensure_content_bundle(
            situation_type="campaign_opening",
            scene_director_output={},
            world_state={},
            campaign_contract=campaign_contract,
            freshness_context=_opening_freshness_context(campaign_id or None),
            campaign_settings=campaign_settings,
        ).get("required_content") or {}
    except Exception:
        opening_seed = {}
    character = _selected_character_from_meta(meta)
    party_mode = len(_session_player_names(folder, meta)) > 1 or not character.get("id")
    return generate_questionnaire(
        session_id=str(meta.get("id") or folder.name),
        campaign_id=campaign_id,
        campaign_contract={
            **campaign_contract,
            "campaign_name": campaign.name if campaign else meta.get("name", ""),
            "description": campaign.description if campaign else "",
            "setting_summary": campaign_settings.get("setting_summary") or campaign_contract.get("setting_summary") or "",
        },
        opening_seed=opening_seed,
        character=character,
        backstory_hooks=backstory_hooks,
        party_mode=party_mode,
    )


class OpeningSetupAnswer(BaseModel):
    question_id: str | None = None
    id: str | None = None
    option_id: str | None = None
    value: str | None = None
    custom_value: str | None = None
    question_text: str | None = None
    answer_source: str | None = None
    answer_text: str | None = None
    character_id: str | int | None = None
    campaign_id: str | int | None = None
    session_id: str | None = None


class OpeningSetupSubmit(BaseModel):
    questionnaire_id: str
    answers: list[OpeningSetupAnswer] = []
    character_hook_override: str | None = None


class OpeningSetupSkip(BaseModel):
    character_hook_override: str | None = None


def _normalized_bridge_answers(
    *,
    session_id: str,
    campaign_id: str,
    character: dict,
    questionnaire: dict,
    answers: list[dict],
) -> list[dict]:
    q_by_id = {str(q.get("id") or ""): q for q in (questionnaire or {}).get("questions", [])}
    normalized: list[dict] = []
    for raw in answers:
        qid = str(raw.get("question_id") or raw.get("id") or "").strip()
        if not qid:
            continue
        question = q_by_id.get(qid) or {}
        question_text = str(raw.get("question_text") or question.get("question") or "").strip()
        answer_text = str(raw.get("answer_text") or raw.get("custom_value") or raw.get("value") or "").strip()
        option_id = str(raw.get("option_id") or "").strip()
        answer_source = str(raw.get("answer_source") or "").strip()
        if option_id == "ai_choose":
            answer_source = "ai_choice"
            answer_text = answer_text or ""
        elif answer_text and not option_id:
            answer_source = answer_source or "custom"
        else:
            option = next((opt for opt in (question.get("options") or []) if str(opt.get("id") or "") == option_id), None)
            if option:
                answer_text = answer_text or str(option.get("value") or option.get("label") or "")
            answer_source = answer_source or "user_choice"
        if not answer_text and answer_source == "ai_choice":
            option = next((opt for opt in (question.get("options") or []) if str(opt.get("id") or "") != "ai_choose"), None)
            answer_text = str((option or {}).get("value") or (option or {}).get("label") or "")
        if not answer_text:
            continue
        normalized.append({
            "question_id": qid,
            "question_text": question_text,
            "answer_source": answer_source,
            "answer_text": answer_text,
            "character_id": str(character.get("id") or character.get("character_id") or raw.get("character_id") or ""),
            "campaign_id": str(campaign_id or raw.get("campaign_id") or ""),
            "session_id": str(session_id or raw.get("session_id") or ""),
        })
    return normalized


def _campaign_brief_with_hook(campaign_brief: dict, hook: str | None) -> dict:
    hook_text = " ".join(str(hook or "").split()).strip()
    if not hook_text:
        return campaign_brief
    brief = dict(campaign_brief or {})
    anchor = dict(brief.get("character_anchor") or {})
    anchor["reason_to_care"] = hook_text
    brief["character_anchor"] = anchor
    facts = [str(f) for f in (brief.get("known_facts") or []) if str(f).strip()]
    if facts:
        if len(facts) >= 6:
            facts[-1] = hook_text
        elif hook_text not in facts:
            facts.append(hook_text)
    else:
        facts = [hook_text]
    brief["known_facts"] = facts
    paragraphs = [str(p) for p in (brief.get("brief_paragraphs") or []) if str(p).strip()]
    if paragraphs:
        if len(paragraphs) >= 4:
            paragraphs[-1] = hook_text
        elif hook_text not in paragraphs:
            paragraphs.append(hook_text)
    else:
        paragraphs = [hook_text]
    brief["brief_paragraphs"] = paragraphs
    return brief


@router.get('/{session_id}/opening-setup')
def get_opening_setup(session_id: str, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    meta_path = folder / 'meta.json'
    if not folder.exists() or not meta_path.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta = json.loads(meta_path.read_text())
    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')
    setup = meta.get("opening_setup") or _opening_setup_default(bool(meta.get("campaign_id")))
    meta["opening_setup"] = setup
    if setup.get("completed"):
        meta_path.write_text(json.dumps(meta))
        return {"opening_setup": setup, "completed": True, "anchors": setup.get("anchors") or []}
    questionnaire = setup.get("questionnaire")
    if not questionnaire:
        questionnaire = _build_opening_setup_questionnaire(folder, meta)
        setup["questionnaire"] = questionnaire
        setup["questionnaire_id"] = questionnaire.get("questionnaire_id")
        setup["campaign_brief"] = questionnaire.get("campaign_brief") or {}
        meta_path.write_text(json.dumps(meta))
    return {"opening_setup": setup, "questionnaire": questionnaire, "completed": False}


@router.post('/{session_id}/opening-setup')
def submit_opening_setup(session_id: str, payload: OpeningSetupSubmit, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    meta_path = folder / 'meta.json'
    if not folder.exists() or not meta_path.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta = json.loads(meta_path.read_text())
    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')
    setup = meta.get("opening_setup") or _opening_setup_default(bool(meta.get("campaign_id")))
    questionnaire = setup.get("questionnaire") or _build_opening_setup_questionnaire(folder, meta)
    if payload.questionnaire_id != questionnaire.get("questionnaire_id"):
        raise HTTPException(status_code=400, detail="Questionnaire mismatch")
    character = _selected_character_from_meta(meta)
    raw_answers = [ans.model_dump() for ans in payload.answers]
    campaign_brief = _campaign_brief_with_hook(
        questionnaire.get("campaign_brief") or setup.get("campaign_brief") or {},
        payload.character_hook_override,
    )
    bridge_answers = _normalized_bridge_answers(
        session_id=session_id,
        campaign_id=str(meta.get("campaign_id") or ""),
        character=character,
        questionnaire=questionnaire,
        answers=raw_answers,
    )
    anchor = answers_to_anchor(
        session_id=session_id,
        campaign_id=str(meta.get("campaign_id") or ""),
        character=character,
        questionnaire=questionnaire,
        answers=raw_answers,
        source="player_answered",
        character_hook_override=payload.character_hook_override or "",
    )
    setup.update({
        "required": bool(setup.get("required", True)),
        "completed": True,
        "questionnaire_id": questionnaire.get("questionnaire_id"),
        "questionnaire": questionnaire,
        "campaign_brief": campaign_brief,
        "anchors": [anchor],
        "bridge_answers": bridge_answers,
    })
    meta["opening_setup"] = setup
    meta["session_start_context"] = {
        "source": anchor.get("source") or "player_answered",
        "questionnaire_id": questionnaire.get("questionnaire_id"),
        "character_id": anchor.get("character_id"),
        "character_name": anchor.get("character_name"),
        "campaign_brief": campaign_brief,
        "bridge_answers": bridge_answers,
        "answers": anchor,
        "character_hook_override": payload.character_hook_override or anchor.get("character_hook_override") or "",
    }
    meta_path.write_text(json.dumps(meta))
    (folder / "opening_character_anchors.json").write_text(json.dumps([anchor], indent=2))
    return {"ok": True, "opening_setup": setup, "anchors": [anchor]}


@router.post('/{session_id}/opening-setup/skip')
def skip_opening_setup(session_id: str, payload: OpeningSetupSkip | None = None, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    meta_path = folder / 'meta.json'
    if not folder.exists() or not meta_path.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta = json.loads(meta_path.read_text())
    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')
    setup = meta.get("opening_setup") or _opening_setup_default(bool(meta.get("campaign_id")))
    questionnaire = setup.get("questionnaire") or _build_opening_setup_questionnaire(folder, meta)
    character = _selected_character_from_meta(meta)
    campaign_brief = _campaign_brief_with_hook(
        questionnaire.get("campaign_brief") or setup.get("campaign_brief") or {},
        (payload.character_hook_override if payload else ""),
    )
    anchor = auto_generate_anchor(
        session_id=session_id,
        campaign_id=str(meta.get("campaign_id") or ""),
        questionnaire=questionnaire,
        character=character,
        character_hook_override=(payload.character_hook_override if payload else "") or "",
    )
    bridge_answers = _normalized_bridge_answers(
        session_id=session_id,
        campaign_id=str(meta.get("campaign_id") or ""),
        character=character,
        questionnaire=questionnaire,
        answers=[
            {"question_id": q.get("id"), "option_id": "ai_choose", "answer_source": "ai_choice"}
            for q in (questionnaire.get("questions") or [])
            if q.get("id")
        ],
    )
    setup.update({
        "required": bool(setup.get("required", True)),
        "completed": True,
        "questionnaire_id": questionnaire.get("questionnaire_id"),
        "questionnaire": questionnaire,
        "campaign_brief": campaign_brief,
        "anchors": [anchor],
        "bridge_answers": bridge_answers,
    })
    meta["opening_setup"] = setup
    meta["session_start_context"] = {
        "source": anchor.get("source") or "auto_generated",
        "questionnaire_id": questionnaire.get("questionnaire_id"),
        "character_id": anchor.get("character_id"),
        "character_name": anchor.get("character_name"),
        "campaign_brief": campaign_brief,
        "bridge_answers": bridge_answers,
        "answers": anchor,
        "character_hook_override": (payload.character_hook_override if payload else "") or anchor.get("character_hook_override") or "",
    }
    meta_path.write_text(json.dumps(meta))
    (folder / "opening_character_anchors.json").write_text(json.dumps([anchor], indent=2))
    return {"ok": True, "opening_setup": setup, "anchors": [anchor]}


@router.post('/{session_id}/invite')
def invite_user(session_id: str, req: InviteRequest, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta = folder / 'meta.json'
    if not meta.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    data = json.loads(meta.read_text())
    # only owner may invite
    owner = data.get('owner')
    identifier = current_user.email or current_user.username
    if identifier != owner:
        raise HTTPException(status_code=403, detail='Only owner may invite users')

    raw_identifier = (req.identifier or '').strip()
    if not raw_identifier:
        raise HTTPException(status_code=400, detail='identifier required')

    invite_email = None
    if '@' in raw_identifier:
        invite_email = _normalize_email(raw_identifier)
    else:
        user = db.get_user_by_identifier(raw_identifier)
        if not user or not user.email:
            raise HTTPException(status_code=404, detail='User not found')
        invite_email = _normalize_email(user.email)

    invites = _normalize_invites(data.get('invites'))
    if any(inv.get('email') == invite_email and not inv.get('accepted') for inv in invites):
        data['invites'] = invites
        meta.write_text(json.dumps(data))
        return {'ok': True, 'invites': invites}

    invites.append({
        'email': invite_email,
        'min_level': 1,
        'accepted': False,
        'character_id': None,
        'character_name': None,
        'note': (req.note or None),
    })
    data['invites'] = invites
    meta.write_text(json.dumps(data))
    return {'ok': True, 'invites': invites}


@router.get('/{session_id}/party')
def get_party(session_id: str, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    members = meta.get('members', []) or []
    invites = _normalize_invites(meta.get('invites'))

    out_members = []
    for member in members:
        email = _normalize_email(member.get('email'))
        user = db.get_user_by_identifier(email) if email else None
        username = user.username if user else None
        name = None
        if user:
            profile = db._profile_with_identity(user)
            name = profile.get('name')

        character_id = member.get('character_id')
        character = None
        if isinstance(character_id, int):
            ch = db.get_character_by_id(character_id)
            if ch:
                character = {
                    'id': ch.id,
                    'name': ch.name,
                    'level': ch.level,
                    'class_name': ch.class_name,
                    'sheet': ch.sheet,
                }

        out_members.append({
            'email': email,
            'username': username,
            'name': name or username or email,
            'role': member.get('role') or 'member',
            'character_id': character_id,
            'character_name': member.get('character_name'),
            'character': character,
        })

    out_invites = []
    for inv in invites:
        email = _normalize_email(inv.get('email'))
        user = db.get_user_by_identifier(email) if email else None
        username = user.username if user else None
        name = None
        if user:
            profile = db._profile_with_identity(user)
            name = profile.get('name')
        out_invites.append({
            **inv,
            'email': email,
            'username': username,
            'name': name or username or email,
        })

    npcs = []
    try:
        npcs_path = folder / 'npcs.json'
        if npcs_path.exists():
            raw = json.loads(npcs_path.read_text())
            if isinstance(raw, list):
                npcs = raw
    except Exception:
        npcs = []

    return {
        'session_id': session_id,
        'members': out_members,
        'invites': out_invites,
        'npcs': npcs,
    }


@router.post('/{session_id}/bootstrap')
async def bootstrap_session(session_id: str, payload: BootstrapRequest, current_user=Depends(get_current_user)):
    """Create/refresh an opening scene for a session.

    This is intentionally deterministic and offline-friendly: it uses the Narrative agent's
    deterministic generator and writes the current scene to `scene.json`.
    """
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    opening_setup = meta.get("opening_setup") or _opening_setup_default(bool(meta.get("campaign_id")))
    meta["opening_setup"] = opening_setup
    if opening_setup.get("required") and not opening_setup.get("completed"):
        meta_path.write_text(json.dumps(meta))
        return {
            "ok": False,
            "requires_opening_setup": True,
            "opening_setup_url": f"/sessions/{session_id}/opening-setup",
            "opening_setup": {
                "required": True,
                "completed": False,
                "questionnaire_id": opening_setup.get("questionnaire_id"),
            },
        }

    session_name = (meta.get('name') or session_id)
    owner = (meta.get('owner') or 'GM')
    style = (payload.style or 'balanced')
    weather = (payload.weather or 'clear')
    time_of_day = (payload.time_of_day or 'day')

    if is_player_run_mode(session_id):
        scene = {
            'id': 'opening',
            'title': f"{session_name} — Player-Run Session",
            'image': None,
            'text': "Player-run mode is enabled. Use chat, notes, and documents to run the session without AI narration.",
            'choices': [],
        }
        (folder / 'scene.json').write_text(json.dumps(scene))
        return {'ok': True, 'scene': scene}

    # Load campaign settings so the seed can match the genre
    _boot_campaign_settings: dict = {}
    _boot_campaign_contract: dict = {}
    _boot_campaign_id = meta.get('campaign_id')
    if _boot_campaign_id:
        try:
            _boot_campaign = db.get_campaign_by_id(str(_boot_campaign_id))
            if _boot_campaign and isinstance(_boot_campaign.metadata_json, dict):
                _boot_campaign_settings = _boot_campaign.metadata_json.get('settings') or {}
                _boot_campaign_contract, _, _, _ = _campaign_package_from_metadata(_boot_campaign)
        except Exception:
            pass

    # Generate a starter seed so the LLM is constrained to a non-tavern location
    _boot_seed_rc: dict = {}
    _has_boot_location_context = bool(
        (_boot_campaign_settings or {}).get("starting_location")
        or (_boot_campaign_contract.get("campaign_dna") or {}).get("starting_location")
        or (_boot_campaign_contract.get("world_contract") or {}).get("known_starting_location")
    )
    if not _has_boot_location_context:
        try:
            _boot_seed_rc = build_content_bundle(
                situation_type="campaign_opening",
                scene_director_output={},
                world_state={},
                campaign_contract=_boot_campaign_contract,
                freshness_context=_opening_freshness_context(str(campaign_id) if campaign_id else None),
                campaign_settings=_boot_campaign_settings,
            ).get("required_content") or {}
        except Exception:
            pass

    if _boot_seed_rc.get("generated_by") in ("starter_seed", "premise_seed"):
        _s_loc = _boot_seed_rc.get("starting_location") or ""
        _s_npc = _boot_seed_rc.get("named_npc_or_visible_threat") or ""
        _s_event = _boot_seed_rc.get("inciting_event") or ""
        _s_stakes = _boot_seed_rc.get("specific_stakes") or ""
        scene_seed = (
            f"The campaign '{session_name}' opens at {_s_loc}. "
            f"{_s_event}. "
            f"{_s_npc} is present. "
            f"Stakes: {_s_stakes}. "
            f"Do NOT set this scene in a tavern or inn."
        )
    else:
        scene_seed = f"the first scene of the campaign '{session_name}', as the party arrives and the hook is revealed — NOT in a tavern or inn"

    narrative = narrative_agent.generate_narrative(narrative_agent.NarrativeRequest(
        scene=scene_seed,
        player='party',
        style=style,
        weather=weather,
        time_of_day=time_of_day,
    ))
    if _contains_recycled_opening_fixture(narrative.narrative, narrative.prompt):
        fallback_loc = _boot_seed_rc.get("starting_location") or session_name
        fallback_npc = _boot_seed_rc.get("named_npc_or_visible_threat") or "the nearest named contact"
        fallback_text = build_fallback_scene(
            location_name=fallback_loc,
            npc_name=fallback_npc,
            player_name="party",
            emotional_state="urgent",
            inciting_incident=_boot_seed_rc.get("inciting_event") or scene_seed,
            central_conflict=_boot_seed_rc.get("immediate_problem") or scene_seed,
            immediate_stakes=_boot_seed_rc.get("specific_stakes") or "",
            sensory_detail="The air is tense with held breath.",
            campaign_name=session_name,
        )
        narrative = narrative_agent.NarrativeResponse(
            narrative=fallback_text,
            prompt="What does the party do?",
            tone=style,
            scene_score=80,
            score_passed=True,
            score_detail={"recycled_opening_guard_used": True},
        )

    scene = {
        'id': 'opening',
        'title': f"{session_name} — Opening Scene",
        'image': None,
        'narrative_body': narrative.narrative,
        'player_prompt': narrative.prompt,
        'text': f"{narrative.narrative}\n\n{narrative.prompt}",  # kept for compat
        'choices': [
            {'id': 'ask_contact', 'label': 'Ask the nearest contact what they know'},
            {'id': 'study_trouble', 'label': 'Study the most obvious sign of trouble'},
            {'id': 'watch_reactions', 'label': 'Watch who reacts strangely'},
            {'id': 'secure_position', 'label': 'Look for a safer angle before acting'},
        ],
    }

    (folder / 'scene.json').write_text(json.dumps(scene))

    # append a log entry for history
    story_path = folder / 'story.json'
    cur = _load_story_entries(folder)
    cur.append({
        'type': 'narration',
        'ts': datetime.now(timezone.utc).isoformat(),
        'text': scene['text'],
    })
    story_path.write_text(json.dumps(cur))

    await broadcaster.broadcast_json(session_id, {
        'type': 'narrative.scene',
        'session_id': session_id,
        'scene': scene,
    })

    # Best-effort: emit cues + suggestions so the UI feels reactive immediately.
    try:
        await scene_agent.analyze_scene(scene_agent.SceneAnalysisRequest(
            scene=scene['text'],
            actions=[c.get('label', '') for c in (scene.get('choices') or []) if isinstance(c, dict)],
            session_id=session_id,
        ))
    except Exception:
        pass

    try:
        await suggestions_agent.get_suggestions(session_id=session_id, limit=4, current_user=current_user)
    except Exception:
        pass

    return {'ok': True, 'scene': scene, 'owner': owner}


# ---------------------------------------------------------------------------
# New Session Workflow (Steps 1–5)
# ---------------------------------------------------------------------------

class StartSessionRequest(BaseModel):
    style: str | None = None
    weather: str | None = None
    time_of_day: str | None = None


@router.post('/{session_id}/start')
async def start_session(session_id: str, payload: StartSessionRequest, current_user=Depends(get_current_user)):
    """Orchestrate the New Session Workflow (Steps 1–5).

    Step 1 – Storyboard Agent builds a story plot from players, campaign settings, and docs.
    Step 2 – Narrative Agent creates the opening scene from the storyboard output.
    Step 3 – Scene Analysis Agent checks for dice-roll opportunities.
    Step 4 – NPC Manager initialises profiles for NPCs mentioned in the plot.
    Step 5 – Scene is broadcast to all session members.
    """
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    opening_setup = meta.get("opening_setup") or _opening_setup_default(bool(meta.get("campaign_id")))
    meta["opening_setup"] = opening_setup
    if opening_setup.get("required") and not opening_setup.get("completed"):
        meta_path.write_text(json.dumps(meta))
        return {
            "ok": False,
            "requires_opening_setup": True,
            "opening_setup_url": f"/sessions/{session_id}/opening-setup",
            "opening_setup": {
                "required": True,
                "completed": False,
                "questionnaire_id": opening_setup.get("questionnaire_id"),
            },
        }
    opening_anchor = _opening_anchor_from_meta(meta)
    opening_campaign_brief = (meta.get("session_start_context") or {}).get("campaign_brief") or (meta.get("opening_setup") or {}).get("campaign_brief") or {}

    session_name = meta.get('name') or session_id
    style = payload.style or 'balanced'
    weather = payload.weather or 'clear'
    time_of_day = payload.time_of_day or 'day'

    if is_player_run_mode(session_id):
        scene = {
            'id': 'opening',
            'title': f"{session_name} — Player-Run Session",
            'image': None,
            'text': "Player-run mode is enabled. Use chat, notes, and documents to run the session without AI narration.",
            'choices': [],
        }
        (folder / 'scene.json').write_text(json.dumps(scene))
        await broadcaster.broadcast_json(session_id, {'type': 'narrative.scene', 'session_id': session_id, 'scene': scene})
        return {'ok': True, 'scene': scene}

    # --- Step 1: Storyboard Agent ---
    players: list[str] = _session_player_names(folder, meta)

    # --- Extract character sheet context for narrative personalization ---
    character_context: dict | None = None
    try:
        for member in meta.get('members', []) or []:
            char_id = member.get('character_id')
            if char_id:
                ch = db.get_character_by_id(int(char_id))
                if ch:
                    sheet = ch.sheet or {}
                    character_context = {
                        'id': ch.id,
                        'name': ch.name or '',
                        'class_name': ch.class_name or '',
                        'level': ch.level or 1,
                        'race': sheet.get('ancestry') or sheet.get('race') or sheet.get('lineage') or '',
                        'backstory': sheet.get('backstory') or '',
                        'personality_traits': sheet.get('personality_traits') or '',
                        'ideals': sheet.get('ideals') or '',
                        'bonds': sheet.get('bonds') or '',
                        'flaws': sheet.get('flaws') or '',
                        'appearance': sheet.get('appearance') or '',
                    }
                    # Add non-empty fields as a campaign doc so Storyboard can use them
                    ctx_lines = [f"[Character: {ch.name}]"]
                    if ch.class_name:
                        ctx_lines.append(f"Class: {ch.class_name} Level {ch.level}")
                    if character_context['race']:
                        ctx_lines.append(f"Race: {character_context['race']}")
                    if character_context['backstory']:
                        ctx_lines.append(f"Backstory: {character_context['backstory'][:400]}")
                    if character_context['bonds']:
                        ctx_lines.append(f"Bonds: {character_context['bonds'][:150]}")
                    if character_context['flaws']:
                        ctx_lines.append(f"Flaws: {character_context['flaws'][:120]}")
                    if len(ctx_lines) > 1:
                        character_context['_doc_block'] = '\n'.join(ctx_lines)
                    break  # Use the first (owner) character
    except Exception:
        character_context = None

    campaign_settings: dict = {}
    campaign_variables: dict = {}
    campaign_contract: dict = {}
    backstory_profiles: list[dict] = []
    backstory_hooks: list[dict] = []
    session_zero_summary: dict = {}
    campaign_scale_profile: dict = {}
    story_shape_profile: dict = {}
    campaign_docs: list[str] = []
    campaign_id = meta.get('campaign_id')
    if campaign_id:
        try:
            campaign = db.get_campaign_by_id(str(campaign_id))
            if campaign and isinstance(campaign.metadata_json, dict):
                campaign_settings = campaign.metadata_json.get('settings') or {}
                if not isinstance(campaign_settings, dict):
                    campaign_settings = {}
                campaign_variables = campaign.metadata_json.get('variables') or {}
                if not isinstance(campaign_variables, dict):
                    campaign_variables = {}
                campaign_contract, backstory_profiles, backstory_hooks, session_zero_summary = _campaign_package_from_metadata(
                    campaign,
                    character_context=character_context,
                )
                campaign_scale_profile = campaign.metadata_json.get('campaign_scale_profile') or campaign_contract.get('campaign_scale_profile') or {}
                story_shape_profile = campaign.metadata_json.get('story_shape_profile') or campaign_contract.get('story_shape_profile') or {}
        except Exception:
            pass
        try:
            docs = _doc_store.list_documents(session_id=session_id)
            for doc in docs or []:
                content = doc.get('content') or ''
                if content:
                    campaign_docs.append(content)
        except Exception:
            pass

    # Inject character context into campaign_docs so Storyboard can build personal hooks
    if character_context and character_context.get('_doc_block'):
        campaign_docs.insert(0, character_context['_doc_block'])
    if opening_anchor:
        campaign_docs.insert(0, "[Opening Character Anchor]\n" + json.dumps(opening_anchor, sort_keys=True))
    if campaign_contract.get("agent_output_contract"):
        campaign_docs.insert(0, "[Campaign Contract]\n" + campaign_contract["agent_output_contract"])

    # Derive narrative style: campaign_variables.narrative_style →
    # campaign_settings.tone → request payload style → default 'balanced'
    derived_style = (
        str(campaign_variables.get('narrative_style') or '').strip()
        or str(campaign_settings.get('tone') or '').strip()
        or style
    )
    if campaign_scale_profile:
        campaign_contract.setdefault("campaign_scale_profile", campaign_scale_profile)
    if story_shape_profile:
        campaign_contract.setdefault("story_shape_profile", story_shape_profile)

    # --- Context Orchestrator: assemble ranked context packet ---
    from .context_collector import summarize_active_threads, summarize_recent_world_changes
    from .context_orchestrator import ContextPacket, orchestrate

    context_packet: ContextPacket | None = None
    world_ctx: dict = {}

    if campaign_id:
        try:
            context_packet = orchestrate(
                campaign_id=str(campaign_id),
                session_id=session_id,
                player_name=players[0] if players else "",
                player_actions=[],
                use_cache=False,
            )
            # Normalize NPC/thread/location format to what Scene Director and downstream code expect
            def _npc_to_old_format(n) -> dict:
                return {
                    "name": n.name, "goal": n.goal, "fear": n.fear,
                    "emotional_state": n.current_emotional_state,
                    "next_action": n.likely_next_action,
                    "faction": n.faction, "relevance_score": n.relevance_score,
                    "known_information": n.known_information,
                }
            def _thread_to_old_format(t) -> dict:
                return {
                    "name": t.title, "situation": t.current_state, "stakes": t.stakes,
                    "next_beat": t.next_escalation, "ticking_clock": t.ticking_clock,
                    "relevance_score": t.relevance_score,
                }
            def _loc_to_old_format(loc) -> dict:
                return {
                    "name": loc.name, "current_tension": loc.current_tensions[0] if loc.current_tensions else "",
                    "description": loc.description, "atmosphere": loc.atmosphere,
                }

            world_ctx = {
                "relevant_npcs": [_npc_to_old_format(n) for n in context_packet.active_npcs],
                "locations": [_loc_to_old_format(context_packet.location)] if context_packet.location.name else [],
                "active_threads": [_thread_to_old_format(t) for t in context_packet.story_threads],
                "open_hooks": [{"title": t.title, "description": t.ticking_clock} for t in context_packet.story_threads if t.ticking_clock],
                "recent_changes": [],
                "prompt_block": context_packet.for_narrative(),
            }
            # Inject story thread / hook summary into campaign_docs for Storyboard LLM
            memory_parts = []
            if context_packet.story_threads:
                memory_parts.append(summarize_active_threads(str(campaign_id)))
            if context_packet.clues.available_clues:
                hook_lines = [f"Hook: {c}" for c in context_packet.clues.available_clues[:4]]
                memory_parts.append("\n".join(hook_lines))
            if memory_parts:
                campaign_docs.append("[Campaign Memory]\n" + "\n\n".join(memory_parts))
        except Exception:
            # Fallback to legacy context_collector
            try:
                from .context_collector import collect_context
                world_ctx = collect_context(str(campaign_id), session_id=session_id)
                memory_parts = []
                if world_ctx.get("active_threads"):
                    memory_parts.append(summarize_active_threads(str(campaign_id)))
                if world_ctx.get("recent_changes"):
                    memory_parts.append(summarize_recent_world_changes(str(campaign_id)))
                if world_ctx.get("open_hooks"):
                    hook_lines = [f"Hook: {h['title']}" for h in world_ctx["open_hooks"][:5]]
                    memory_parts.append("\n".join(hook_lines))
                if memory_parts:
                    campaign_docs.append("[Campaign Memory]\n" + "\n\n".join(memory_parts))
            except Exception:
                pass

    # --- Steps 1 + Director: run in parallel (they don't depend on each other) ---
    # Storyboard generates raw plot material; Narrative Director sets story guidance.
    # Both are synchronous LLM calls — run them in a thread pool concurrently.
    import asyncio
    import concurrent.futures as _cf

    _loop = asyncio.get_event_loop()
    player_name = players[0] if players else 'the party'

    def _run_storyboard():
        return storyboard_agent.generate_plot(storyboard_agent.StoryboardPlotRequest(
            session_id=session_id,
            players=players,
            campaign_settings=campaign_settings,
            campaign_variables=campaign_variables,
            campaign_docs=campaign_docs,
        ))

    # Prepare story state for narrative director (pure data ops, no I/O)
    story_state = load_story_state(str(campaign_id)) if campaign_id else None
    mem_threads_raw: list[dict] = world_ctx.get('active_threads') or []
    if story_state is not None:
        try:
            story_state = sync_threads_from_entities(story_state, mem_threads_raw)
            if not story_state.campaign_dna.themes:
                story_state.campaign_dna = derive_campaign_dna(campaign_settings, campaign_variables)
        except Exception:
            pass

    def _run_director():
        if story_state is None:
            return None
        try:
            return narrative_direct_scene(
                state=story_state,
                player_name=player_name if players else "",
                player_actions=[],
            )
        except Exception:
            return None

    with _cf.ThreadPoolExecutor(max_workers=2) as _pool:
        fut_plot = _loop.run_in_executor(_pool, _run_storyboard)
        fut_director = _loop.run_in_executor(_pool, _run_director)
        plot_result, narrative_director_output = await asyncio.gather(fut_plot, fut_director)

    narrative_director_output: DirectorOutput | None = narrative_director_output  # type annotation

    opening_campaign_storyboard = getattr(plot_result, 'campaign_storyboard', {}) or {}
    opening_session_storyboard = getattr(plot_result, 'session_storyboard', {}) or {}
    opening_arc_plan = plan_arc({
        "campaign_contract": campaign_contract,
        "campaign_scale_profile": campaign_scale_profile,
        "story_shape_profile": story_shape_profile,
        "campaign_storyboard": opening_campaign_storyboard,
        "active_threads": world_ctx.get('active_threads') or [],
        "world_clocks": world_ctx.get('world_clocks') or [],
        "backstory_spotlight": campaign_contract.get("backstory_spotlight") or [],
    }).model_dump()
    opening_scene_beat = select_scene_beat_plan({
        "session_storyboard": opening_session_storyboard,
        "campaign_storyboard": opening_campaign_storyboard,
        "arc_plan": opening_arc_plan,
        "player_intent": {"declared_actions": [], "requested_mode": "other"},
        "simulation_delta": {},
        "current_location": {},
        "active_npcs": world_ctx.get('relevant_npcs') or [],
        "active_threads": world_ctx.get('active_threads') or [],
        "recent_scene_types": [],
        "recent_motifs": [],
        "backstory_spotlight": campaign_contract.get("backstory_spotlight") or [],
    })
    opening_scene_beat["scene_type"] = "campaign_opening"
    opening_scene_beat["required_content_bundle"] = "OpeningBundle"

    # --- Step 1b: Merge campaign memory into Scene Director candidates ---
    mem_npc_details: list[dict] = world_ctx.get('relevant_npcs') or []
    mem_loc_details: list[dict] = world_ctx.get('locations') or []
    mem_threads: list[dict] = mem_threads_raw
    mem_hooks: list[dict] = world_ctx.get('open_hooks') or []
    mem_changes: list[dict] = world_ctx.get('recent_changes') or []

    # Flatten to strings for candidate lists, prefer memory-sourced (more structured) over doc-sourced
    mem_npc_names = [n['name'] for n in mem_npc_details if n.get('name')]
    mem_loc_names = [loc['name'] for loc in mem_loc_details if loc.get('name')]
    mem_thread_texts = [
        t.get('situation') or t.get('name') or ''
        for t in mem_threads if t.get('situation') or t.get('name')
    ]
    mem_hook_texts = [h.get('title', '') for h in mem_hooks if h.get('title')]
    mem_event_texts = [c.get('summary', '') for c in mem_changes if c.get('summary')]
    _tavern_words = {"tavern", "inn", "alehouse", "flagon", "tankard", "wayward", "lantern"}
    usable_mem_loc_names = [
        loc for loc in mem_loc_names
        if not any(w in loc.lower() for w in _tavern_words)
    ]

    candidate_npcs = (mem_npc_names or plot_result.candidate_npcs)
    # Filter tavern defaults from storyboard-generated location candidates — the
    # Storyboard LLM may invent a tavern for new campaigns with no context,
    # and those names must not reach the Scene Director or the _has_location_context check.
    candidate_locations = [
        loc for loc in (usable_mem_loc_names or plot_result.candidate_locations)
        if not any(w in loc.lower() for w in _tavern_words)
    ]
    candidate_threads = (mem_thread_texts or plot_result.candidate_story_threads)
    open_hooks = (mem_hook_texts or plot_result.open_hooks)
    recent_events = (mem_event_texts or plot_result.recent_events)

    # All known entity names for quality validator
    all_campaign_entities = list({*candidate_npcs, *candidate_locations, *candidate_threads})

    # --- Step 2: Opening seed injection (first scene, no prior location context) ---
    # Pre-generate a structured seed so the Scene Director LLM is not free to default
    # to a tavern when the plot seed and candidate lists are empty.
    _bootstrap_guidance = narrative_director_output.model_dump() if narrative_director_output else {}
    _bootstrap_plot_seed = plot_result.plot
    _bootstrap_seed_rc: dict = {}
    _explicit_starting_location = bool(
        (campaign_settings or {}).get("starting_location")
        or (campaign_settings or {}).get("world_name")
        or (campaign_contract.get("campaign_dna") or {}).get("starting_location")
        or (campaign_contract.get("world_contract") or {}).get("known_starting_location")
    )
    if not _explicit_starting_location:
        try:
            _bootstrap_seed_rc = ensure_content_bundle(
                situation_type="campaign_opening",
                scene_director_output={},
                world_state={},
                campaign_contract=campaign_contract,
                freshness_context={**_opening_freshness_context(str(campaign_id) if campaign_id else None), "opening_anchor": opening_anchor},
                campaign_settings=campaign_settings,
            ).get("required_content") or {}
        except Exception:
            _bootstrap_seed_rc = {}
    _has_premise_seed = _bootstrap_seed_rc.get("generated_by") == "premise_seed"
    # Only treat "real" campaign context as location context — NOT storyboard-generated
    # candidate_locations, which are LLM outputs that default to taverns for new campaigns.
    _has_location_context = bool(
        not _has_premise_seed
        and (
            usable_mem_loc_names
            or _explicit_starting_location
        )
    )
    if not _has_location_context:
        try:
            if _bootstrap_seed_rc and _bootstrap_seed_rc.get("generated_by") in ("starter_seed", "premise_seed"):
                if _bootstrap_seed_rc.get("starting_location"):
                    _bootstrap_guidance["required_opening_location"] = _bootstrap_seed_rc["starting_location"]
                if _bootstrap_seed_rc.get("named_npc_or_visible_threat"):
                    _bootstrap_guidance["required_opening_npc"] = _bootstrap_seed_rc["named_npc_or_visible_threat"]
                if _bootstrap_seed_rc.get("inciting_event"):
                    _bootstrap_guidance["required_opening_event"] = _bootstrap_seed_rc["inciting_event"]
                if _bootstrap_seed_rc.get("specific_stakes"):
                    _bootstrap_guidance["required_opening_stakes"] = _bootstrap_seed_rc["specific_stakes"]
                if _bootstrap_seed_rc.get("player_decision"):
                    _bootstrap_guidance["required_opening_decision"] = _bootstrap_seed_rc["player_decision"]
                _seed_summary = (
                    f"Opening location: {_bootstrap_seed_rc.get('starting_location', '')}. "
                    f"Inciting event: {_bootstrap_seed_rc.get('inciting_event', '')}. "
                    f"NPC: {_bootstrap_seed_rc.get('named_npc_or_visible_threat', '')}."
                )
                _bootstrap_plot_seed = f"{_seed_summary}\n\n{_bootstrap_plot_seed}" if _bootstrap_plot_seed else _seed_summary
        except Exception:
            pass

    # --- Step 2: Scene Director Agent — converts raw material into a concrete scene plan ---
    director_output: SceneDirectorOutput = scene_director_agent.direct_scene(SceneDirectorRequest(
        campaign_settings=campaign_settings,
        campaign_variables=campaign_variables,
        players=players,
        plot_seed=_bootstrap_plot_seed,
        candidate_npcs=candidate_npcs[:6],
        candidate_npc_details=mem_npc_details[:6],
        candidate_locations=candidate_locations[:4],
        candidate_location_details=mem_loc_details[:4],
        candidate_factions=plot_result.candidate_factions,
        candidate_story_threads=candidate_threads[:4],
        candidate_thread_details=mem_threads[:4],
        open_hooks=open_hooks[:4],
        recent_events=recent_events[:4],
        world_context_block=world_ctx.get('prompt_block') or '',
        director_guidance=_bootstrap_guidance or None,
        campaign_contract=campaign_contract,
    ))

    loc_name = director_output.location.name or ''
    npc_name = director_output.primary_npc.name or ''

    # --- Deterministic override for opening scenes (start_session path) ---
    # If the seed was generated and the Scene Director LLM still produced a tavern/generic
    # location, forcibly patch the director data before Composer + Narrative Writer run.
    # Instruction-following alone is not reliable enough — this is a hard code-level guard.
    director_data_dict = director_output.model_dump()
    _explicit_location_name = str(
        (campaign_settings or {}).get("starting_location")
        or (campaign_settings or {}).get("world_name")
        or (campaign_contract.get("campaign_dna") or {}).get("starting_location")
        or (campaign_contract.get("world_contract") or {}).get("known_starting_location")
        or ""
    ).strip()
    if _explicit_location_name and director_data_dict.get("location"):
        director_data_dict["location"]["name"] = _explicit_location_name
        director_data_dict["scene_title"] = director_data_dict.get("scene_title") or f"Opening — {_explicit_location_name}"
        loc_name = _explicit_location_name
    _seed_source = ""
    _seed_event = ""
    _seed_stakes = ""
    _seed_problem = ""
    if not _has_location_context and '_bootstrap_seed_rc' in dir():
        _bsrc = locals().get('_bootstrap_seed_rc') or {}
        _seed_source = _bsrc.get("generated_by")
        if _seed_source in ("starter_seed", "premise_seed"):
            from .content_bundles import _looks_like_tavern_default
            _seed_loc = _bsrc.get("starting_location") or ""
            _seed_npc = _bsrc.get("named_npc_or_visible_threat") or ""
            _seed_event = _bsrc.get("inciting_event") or ""
            _seed_stakes = _bsrc.get("specific_stakes") or ""
            _seed_problem = _bsrc.get("immediate_problem") or ""
            _seed_decision = _bsrc.get("player_decision") or ""
            _seed_question = _bsrc.get("first_clue_or_question") or ""
            if _seed_loc:
                if (
                    _seed_source == "premise_seed"
                    or (_seed_source == "starter_seed" and not _has_location_context)
                    or not loc_name
                    or _looks_like_tavern_default(loc_name)
                    or _contains_recycled_opening_fixture(loc_name, json.dumps(director_data_dict))
                ):
                    director_data_dict["location"]["name"] = _seed_loc
                    director_data_dict["scene_title"] = f"Opening — {_seed_loc}"
                    loc_name = _seed_loc
                if _seed_source == "premise_seed":
                    _seed_loc_type = _bsrc.get("location_type") or director_data_dict["location"].get("type") or "opening location"
                    _seed_identity = _bsrc.get("location_identity") or f"{_seed_loc} is a {_seed_loc_type} where the opening problem is already visible."
                    director_data_dict["location"]["type"] = _seed_loc_type
                    director_data_dict["location"]["sensory_details"] = [
                        _seed_identity,
                        _seed_event or _seed_problem or _seed_question or "The first scene has a visible, local problem.",
                    ]
                    director_data_dict["visual_prompt_elements"] = [
                        str(bit)
                        for bit in (
                            f"{_seed_loc}, {_seed_loc_type}",
                            _seed_identity,
                            _seed_event or _seed_problem,
                            _seed_stakes or _seed_question,
                        )
                        if bit
                    ][:4]
                    director_data_dict["world_moves"] = [
                        str(bit)
                        for bit in (
                            _seed_problem,
                            _seed_stakes,
                        )
                        if bit
                    ]
            if _seed_npc:
                _llm_npc = (director_data_dict.get("primary_npc") or {}).get("name") or ""
                if (
                    _seed_source == "premise_seed"
                    or (_seed_source == "starter_seed" and not _has_location_context)
                    or not _llm_npc
                    or _looks_like_tavern_default(_llm_npc)
                    or _contains_recycled_opening_fixture(_llm_npc, json.dumps(director_data_dict))
                    or _llm_npc.lower() in ("a stranger", "a mysterious figure", "the barkeep", "innkeeper", "the innkeeper")
                ):
                    director_data_dict["primary_npc"]["name"] = _seed_npc
                    npc_name = _seed_npc
            if _seed_event and (_seed_source in ("premise_seed", "starter_seed") or not director_data_dict.get("inciting_incident")):
                director_data_dict["inciting_incident"] = _seed_event
            if _seed_stakes and (_seed_source in ("premise_seed", "starter_seed") or not director_data_dict.get("immediate_stakes")):
                director_data_dict["immediate_stakes"] = _seed_stakes
            if _seed_problem and _seed_source in ("premise_seed", "starter_seed"):
                director_data_dict["central_conflict"] = _seed_problem
            if _seed_question and _seed_source in ("premise_seed", "starter_seed"):
                director_data_dict["player_visible_clues"] = [_seed_question]
            if _seed_decision and _seed_source in ("premise_seed", "starter_seed"):
                director_data_dict["possible_actions"] = [
                    part.strip()
                    for part in _seed_decision.replace(" or ", ", ").split(",")
                    if part.strip()
                ][:4] or director_data_dict.get("possible_actions", [])
            # Also patch the plot_seed so the Narrative Writer prose is anchored correctly
            _bootstrap_plot_seed = (
                f"Opening location: {_seed_loc}. "
                f"Inciting event: {_seed_event}. "
                f"NPC: {_seed_npc}. "
                f"Stakes: {_seed_stakes}.\n\n" + (_bootstrap_plot_seed or "")
            ).strip()
    try:
        director_output = SceneDirectorOutput(**director_data_dict)
    except Exception:
        pass
    if _contains_recycled_opening_fixture(json.dumps(director_data_dict)):
        replacement_loc = ""
        replacement_npc = ""
        replacement_event = ""
        replacement_stakes = ""
        try:
            _guard_seed = build_content_bundle(
                situation_type="campaign_opening",
                scene_director_output={},
                world_state={},
                campaign_contract=campaign_contract,
                freshness_context={**_opening_freshness_context(str(campaign_id) if campaign_id else None), "opening_anchor": opening_anchor},
                campaign_settings=campaign_settings,
            ).get("required_content") or {}
            replacement_loc = _guard_seed.get("starting_location") or ""
            replacement_npc = _guard_seed.get("named_npc_or_visible_threat") or ""
            replacement_event = _guard_seed.get("inciting_event") or ""
            replacement_stakes = _guard_seed.get("specific_stakes") or ""
        except Exception:
            pass
        replacement_loc = replacement_loc or scene_director_agent._location_from_text(  # type: ignore[attr-defined]
            " ".join([
                str(campaign_settings.get("world_name") or ""),
                str(campaign_settings.get("setting_summary") or ""),
                str(campaign_contract.get("campaign_pitch") or ""),
                session_name,
            ]),
            str(campaign_settings.get("genre") or ""),
        )
        replacement_npc = replacement_npc or scene_director_agent._contact_from_text(  # type: ignore[attr-defined]
            " ".join([
                str(campaign_settings.get("setting_summary") or ""),
                str(campaign_contract.get("campaign_pitch") or ""),
                session_name,
            ]),
            str(campaign_settings.get("genre") or ""),
        )
        director_data_dict["scene_title"] = f"Opening — {replacement_loc}"
        director_data_dict["location"] = {
            **(director_data_dict.get("location") or {}),
            "name": replacement_loc,
            "sensory_details": scene_director_agent._sensory_from_context(  # type: ignore[attr-defined]
                replacement_loc,
                str(campaign_settings.get("setting_summary") or campaign_contract.get("campaign_pitch") or session_name),
                str(campaign_settings.get("genre") or ""),
                derived_style,
            ),
        }
        director_data_dict["primary_npc"] = {
            **(director_data_dict.get("primary_npc") or {}),
            "name": replacement_npc,
        }
        if replacement_event:
            director_data_dict["inciting_incident"] = replacement_event
        if replacement_stakes:
            director_data_dict["immediate_stakes"] = replacement_stakes
        loc_name = replacement_loc
        npc_name = replacement_npc
        try:
            director_output = SceneDirectorOutput(**director_data_dict)
        except Exception:
            pass
    opening_content_bundle = ensure_content_bundle(
        situation_type="campaign_opening",
        scene_director_output=director_data_dict,
        world_state={},
        campaign_contract=campaign_contract,
        previous_scene=None,
        freshness_context={**_opening_freshness_context(str(campaign_id) if campaign_id else None), "opening_anchor": opening_anchor},
        campaign_settings=campaign_settings,
    )
    if not opening_content_bundle.get("content_gate_passed"):
        fallback_bundle = ensure_content_bundle(
            situation_type="campaign_opening",
            scene_director_output={},
            world_state={},
            campaign_contract=campaign_contract,
            freshness_context={**_opening_freshness_context(str(campaign_id) if campaign_id else None), "opening_anchor": opening_anchor},
            campaign_settings=campaign_settings,
        )
        opening_content_bundle = fallback_bundle
        rc = fallback_bundle.get("required_content") or {}
        if rc.get("starting_location") and director_data_dict.get("location"):
            director_data_dict["location"]["name"] = rc["starting_location"]
            loc_name = rc["starting_location"]
        if rc.get("named_npc_or_visible_threat") and director_data_dict.get("primary_npc"):
            director_data_dict["primary_npc"]["name"] = rc["named_npc_or_visible_threat"]
            npc_name = rc["named_npc_or_visible_threat"]
        if rc.get("inciting_event"):
            director_data_dict["inciting_incident"] = rc["inciting_event"]
        if rc.get("specific_stakes"):
            director_data_dict["immediate_stakes"] = rc["specific_stakes"]
        try:
            director_output = SceneDirectorOutput(**director_data_dict)
        except Exception:
            pass
    if opening_anchor:
        required_context = opening_content_bundle.setdefault("required_content", {})
        required_context.setdefault("opening_context", _opening_anchor_context(opening_anchor))
        required_context.setdefault("opening_character_anchor", opening_anchor)
        if opening_campaign_brief:
            required_context.setdefault("campaign_brief", opening_campaign_brief)
        director_data_dict["opening_character_anchor"] = opening_anchor
        director_data_dict["opening_context"] = required_context.get("opening_context") or {}
        if opening_campaign_brief:
            director_data_dict["campaign_brief"] = opening_campaign_brief
    composer_output = narrative_composer_agent.compose_scene(
        scene_director_data=director_data_dict,
        player_name=player_name,
        scene_type=director_output.scene_type or "opening",
    )
    composer_data_dict = composer_output.model_dump()

    # --- Step 3: Narrative Agent — first attempt ---
    narrative = narrative_agent.generate_narrative(narrative_agent.NarrativeRequest(
        scene=_bootstrap_plot_seed or plot_result.plot,
        player=player_name,
        style=derived_style,
        weather=weather,
        time_of_day=time_of_day,
        scene_director_data=director_data_dict,
        composer_data=composer_data_dict,
        is_opening_scene=True,
        character_context=character_context,
        campaign_contract=campaign_contract,
    ))
    if _seed_source == "premise_seed":
        _seed_required = locals().get("_bsrc") or {}
        if opening_anchor:
            _seed_required = {
                **_seed_required,
                "opening_context": _opening_anchor_context(opening_anchor),
                "opening_character_anchor": opening_anchor,
                "campaign_brief": opening_campaign_brief,
            }
        narrative = narrative_agent.NarrativeResponse(
            narrative=_opening_narrative_from_seed(_seed_required, player_name),
            prompt=f"What does {player_name} do?",
            tone=derived_style,
            scene_score=90,
            score_passed=True,
            score_detail={**(narrative.score_detail or {}), "premise_seed_opening_used": True},
            suggested_actions=director_data_dict.get("possible_actions") or [],
            world_moves=director_data_dict.get("world_moves") or [],
        )

    # --- Step 3b: Quality validation + retry/fallback ---
    quality_score, quality_issues = validate_scene_quality(
        narrative_text=f"{narrative.narrative}\n\n{narrative.prompt}",
        location_name=loc_name,
        npc_name=npc_name,
        player_name=player_name,
        conflict=director_output.central_conflict,
        campaign_entities=all_campaign_entities,
    )
    contract_validator = validate_campaign_expectations(
        narrative_text=f"{narrative.narrative}\n\n{narrative.prompt}",
        campaign_contract=campaign_contract,
    )
    recycled_opening_detected = _contains_recycled_opening_fixture(narrative.narrative, narrative.prompt)
    if recycled_opening_detected:
        quality_score = 0
        quality_issues.append("Recycled opening fixture returned instead of campaign-specific content")
    retry_used = False
    fallback_used = False
    contract_minimum = int((campaign_contract.get("validator_policy") or {}).get("minimum_scene_score") or MINIMUM_SCORE) if campaign_contract else MINIMUM_SCORE
    minimum_score = max(MINIMUM_SCORE, contract_minimum)

    if quality_score < minimum_score or contract_validator.get("failed_expectations") or recycled_opening_detected:
        retry_used = True
        feedback = build_retry_feedback(
            quality_issues + list(contract_validator.get("failed_expectations", [])),
            quality_score,
            loc_name,
            npc_name,
            player_name,
        )
        narrative = narrative_agent.generate_narrative(narrative_agent.NarrativeRequest(
            scene=plot_result.plot,
            player=player_name,
            style=derived_style,
            weather=weather,
            time_of_day=time_of_day,
            scene_director_data=director_data_dict,
            composer_data=composer_data_dict,
            validator_feedback=feedback,
            is_opening_scene=True,
            character_context=character_context,
            campaign_contract=campaign_contract,
        ))
        quality_score, quality_issues = validate_scene_quality(
            narrative_text=f"{narrative.narrative}\n\n{narrative.prompt}",
            location_name=loc_name,
            npc_name=npc_name,
            player_name=player_name,
            conflict=director_output.central_conflict,
            campaign_entities=all_campaign_entities,
        )
        contract_validator = validate_campaign_expectations(
            narrative_text=f"{narrative.narrative}\n\n{narrative.prompt}",
            campaign_contract=campaign_contract,
        )
        recycled_opening_detected = _contains_recycled_opening_fixture(narrative.narrative, narrative.prompt)
        if recycled_opening_detected:
            quality_score = 0
            quality_issues.append("Recycled opening fixture returned again after retry")

    if quality_score < minimum_score or recycled_opening_detected:
        fallback_used = True
        narrative = _fallback_response_from_director(
            director_data=director_data_dict,
            loc_name=loc_name or "the settlement",
            npc_name=npc_name,
            player_name=player_name,
            derived_style=derived_style,
            session_name=session_name,
            score_detail={"quality_fallback_used": True},
        )

    # --- Step 4: Build scene object ---
    # Choices from Scene Director possible_actions if available
    if director_output.possible_actions:
        choices = [
            {'id': f'action_{i}', 'label': a}
            for i, a in enumerate(director_output.possible_actions[:4])
        ]
    else:
        choices = [
            {'id': 'ask_contact', 'label': f"Ask {npc_name or 'the nearest contact'} what they know"},
            {'id': 'study_trouble', 'label': 'Study the most obvious sign of trouble'},
            {'id': 'watch_reactions', 'label': 'Watch who reacts strangely'},
            {'id': 'secure_position', 'label': 'Look for a safer angle before acting'},
        ]

    # Merge world moves: prefer Composer output (richer), fall back to Scene Director
    scene_world_moves = (
        composer_output.world_moves
        or director_output.world_moves
        or plot_result.hooks
        or []
    )

    scene = {
        'id': 'opening',
        'title': director_data_dict.get("scene_title") or director_output.scene_title or f"{session_name} — Opening Scene",
        'image': None,
        'narrative_body': narrative.narrative,
        'player_prompt': narrative.prompt,
        'text': f"{narrative.narrative}\n\n{narrative.prompt}",  # kept for compat
        'choices': choices,
        'hooks': plot_result.hooks,
        'world_moves': scene_world_moves[:4],
        'active_player': player_name,
        'location': loc_name,
        'weather': weather,
        'time_of_day': time_of_day,
        'immediate_stakes': director_output.immediate_stakes or '',
        'active_threads': director_output.threads_to_advance or [],
        'visible_clues': director_output.player_visible_clues[:4] or [],
        'current_objective': (
            director_output.central_conflict[:120]
            if director_output.central_conflict
            else ''
        ),
        'active_thread': (
            director_output.threads_to_advance[0]
            if director_output.threads_to_advance
            else ''
        ),
        'suggested_actions': (narrative.suggested_actions or composer_output.suggested_actions or [])[:4],
        # Persisted for regeneration — gives /narrative/regenerate the full structured brief
        'scene_director_data': director_data_dict,
        'situation_type': opening_scene_beat.get("scene_type") or "campaign_opening",
        'content_bundle': opening_content_bundle,
        'ui_payload': opening_content_bundle.get('ui_payload', {}),
        'campaign_scale_profile': campaign_scale_profile,
        'story_shape_profile': story_shape_profile,
        'arc_plan': opening_arc_plan,
        'campaign_storyboard': opening_campaign_storyboard,
        'session_storyboard': opening_session_storyboard,
        'scene_beat_plan': opening_scene_beat,
        'selected_scene_beat': opening_scene_beat,
        'opening_setup': meta.get("opening_setup") or {},
        'opening_character_anchor': opening_anchor,
        'opening_bundle_context': (opening_content_bundle.get("required_content") or {}).get("opening_context") or {},
        'beat_selection_reason': opening_scene_beat.get("selection_reason", ""),
        'repetition_warnings': opening_scene_beat.get("repetition_warnings", []),
        'thread_budget': {
            'max_open_threads': campaign_scale_profile.get('max_open_threads'),
            'active_thread_count': len(candidate_threads),
            'threads_to_retire': opening_arc_plan.get('threads_to_retire', []),
        },
        'campaign_contract': {
            'contract_version': campaign_contract.get('contract_version'),
            'canon_policy': campaign_contract.get('canon_policy', {}),
            'ui_policy': campaign_contract.get('ui_policy', {}),
            'validator_policy': campaign_contract.get('validator_policy', {}),
        } if campaign_contract else {},
        'ui_policy': campaign_contract.get('ui_policy', {}) if campaign_contract else {},
    }
    scene = _repair_recycled_opening_scene_if_needed(folder, scene, meta=meta)
    scene = _normalize_scene_render_fields(folder, scene)
    scene, opening_scene_validation = _apply_concrete_opening_scene_contract(
        scene,
        required=(opening_content_bundle.get("required_content") or {}),
        opening_anchor=opening_anchor,
        campaign_brief=opening_campaign_brief,
        player_name=player_name,
        time_of_day=time_of_day,
    )
    known_character_names = [
        str(member.get("character_name") or "")
        for member in (meta.get("members") or [])
        if member.get("character_name")
    ]
    scene, opening_anchor_validation = _apply_opening_anchor_validation(
        scene,
        opening_anchor,
        player_name=player_name,
        known_character_names=known_character_names,
    )
    scene["anchor_validation"] = opening_anchor_validation
    scene, first_scene_validation, _contract_dice_rolls = _apply_first_scene_contract(
        scene,
        opening_anchor,
        player_name=player_name,
        dice_rolls=[],
    )
    scene["first_scene_validation"] = first_scene_validation
    scene["opening_scene_validation"] = opening_scene_validation
    scene_qa_initial = run_scene_qa(
        scene=scene,
        campaign_contract=campaign_contract,
        campaign_scale_profile=campaign_scale_profile,
        story_shape_profile=story_shape_profile,
        scene_beat_plan=opening_scene_beat,
        content_bundle=opening_content_bundle,
        narrative_output={"narrative": narrative.narrative, "prompt": narrative.prompt},
        player_intent={"declared_actions": [], "requested_mode": "campaign_opening"},
        recent_player_actions=[],
        current_scene=None,
        recent_scene_history=[],
        recent_motifs=[],
        memory_delta={},
        ui_payload=scene.get("ui_payload") or {},
    )
    scene = apply_targeted_scene_repairs(scene, scene_qa_initial, player_name=player_name)
    scene_qa_final = run_scene_qa(
        scene=scene,
        campaign_contract=campaign_contract,
        campaign_scale_profile=campaign_scale_profile,
        story_shape_profile=story_shape_profile,
        scene_beat_plan=opening_scene_beat,
        content_bundle=opening_content_bundle,
        player_intent={"declared_actions": [], "requested_mode": "campaign_opening"},
        recent_player_actions=[],
        current_scene=None,
        recent_scene_history=[],
        recent_motifs=[],
        memory_delta={},
        ui_payload=scene.get("ui_payload") or {},
    )
    scene["scene_qa"] = scene_qa_final
    scene["quality_debug"] = {
        "scene_qa_initial": scene_qa_initial,
        "scene_qa_final": scene_qa_final,
        "truth_table": scene_qa_final.get("truth_table", {}),
        "opening_shape": scene_qa_final.get("opening_shape", {}),
        "gm_move": scene_qa_final.get("gm_move", ""),
        "scene_purpose": scene_qa_final.get("scene_purpose", {}),
        "tension_curve": scene_qa_final.get("tension_curve", {}),
        "npc_scene_roles": scene_qa_final.get("npc_scene_roles", []),
        "detail_budget": scene_qa_final.get("detail_budget", {}),
        "campaign_palette": scene_qa_final.get("campaign_palette", {}),
        "memory_delta_consistency": scene_qa_final.get("memory_delta_consistency", {}),
        "ui_payload_validation": scene_qa_final.get("ui_payload_validation", {}),
        "regression_tags": scene_qa_final.get("regression_tags", []),
        "opening_setup": meta.get("opening_setup") or {},
        "opening_bundle_context": scene.get("opening_bundle_context") or {},
        "anchor_validation": opening_anchor_validation,
        "first_scene_validation": first_scene_validation,
    }
    if campaign_id:
        try:
            record_opening_shape(str(campaign_id), scene_qa_final.get("opening_shape") or {})
        except Exception:
            pass
    loc_name = str(scene.get('location') or loc_name)
    (folder / 'scene.json').write_text(json.dumps(scene))

    # --- Step 4b: Visual Director + Image generation ---
    loc_type = director_output.location.type if director_output.location else ""
    vd_elements = director_output.visual_prompt_elements or []
    try:
        visual_state, image_prompt, _ = run_visual_pipeline(
            session_id=session_id,
            scene_text=scene['text'],
            location_name=loc_name,
            location_type=loc_type,
            weather=weather,
            time_of_day=time_of_day,
            season="",
            region="",
            visual_prompt_elements=vd_elements,
            previous_visual_state=None,
        )
        save_visual_state(session_id, visual_state)
        scene['visual_state'] = visual_state.model_dump()
    except Exception:
        visual_state = None
        image_prompt = build_image_prompt(director_output, style=derived_style, weather=weather, time_of_day=time_of_day)

    try:
        img = image_agent.generate_image(image_agent.ImageRequest(
            prompt=image_prompt,
            style='realistic',
            session_id=session_id,
        ))
        scene['image'] = img.image_url
        (folder / 'scene.json').write_text(json.dumps(scene))
    except Exception:
        pass

    story_path = folder / 'story.json'
    cur = _load_story_entries(folder)
    cur.append({'type': 'narration', 'ts': datetime.now(timezone.utc).isoformat(), 'text': scene['text']})
    story_path.write_text(json.dumps(cur))

    # --- Step 5: Scene Analysis ---
    dice_rolls: list[dict] = []
    try:
        cues = await scene_agent.analyze_scene(scene_agent.SceneAnalysisRequest(
            scene=scene['text'],
            actions=[c.get('label', '') for c in scene.get('choices', []) if isinstance(c, dict)],
            session_id=session_id,
        ))
        dice_rolls = [r.model_dump() for r in cues.dice_rolls]
    except Exception:
        pass

    opening_world_state = simulation_agent.load_world_state(folder)
    opening_world_state["weather"] = weather
    opening_delta = {
        "time_changes": [],
        "weather_changes": [],
        "npc_movements": [],
        "faction_advances": [],
        "rumors_spread": [],
        "quest_updates": [],
        "threat_updates": [],
        "relationship_changes": [],
        "consequences_triggered": [],
    }
    scene = simulation_agent.normalize_scene_presentation(scene, opening_world_state, opening_delta)
    opening_memory_delta = simulation_agent.build_memory_delta(scene, opening_world_state, opening_delta)
    scene.update(simulation_agent.build_structured_scene_fields(
        scene,
        opening_world_state,
        opening_delta,
        opening_memory_delta,
        ["Campaign Opening"],
        dice_rolls=dice_rolls,
    ))
    scene = _repair_recycled_opening_scene_if_needed(folder, scene, meta=meta)
    scene = _normalize_scene_render_fields(folder, scene)
    scene, opening_scene_validation = _apply_concrete_opening_scene_contract(
        scene,
        required=(opening_content_bundle.get("required_content") or {}),
        opening_anchor=opening_anchor,
        campaign_brief=opening_campaign_brief,
        player_name=player_name,
        time_of_day=time_of_day,
    )
    scene, first_scene_validation, dice_rolls = _apply_first_scene_contract(
        scene,
        opening_anchor,
        player_name=player_name,
        dice_rolls=dice_rolls,
    )
    scene["first_scene_validation"] = first_scene_validation
    scene["opening_scene_validation"] = opening_scene_validation
    opening_memory_delta = simulation_agent.build_memory_delta(scene, opening_world_state, opening_delta)
    scene_qa_memory = run_scene_qa(
        scene=scene,
        campaign_contract=campaign_contract,
        campaign_scale_profile=campaign_scale_profile,
        story_shape_profile=story_shape_profile,
        scene_beat_plan=opening_scene_beat,
        content_bundle=opening_content_bundle,
        player_intent={"declared_actions": [], "requested_mode": "campaign_opening"},
        recent_player_actions=[],
        current_scene=None,
        recent_scene_history=[],
        recent_motifs=[],
        memory_delta=opening_memory_delta,
        ui_payload=scene.get("ui_payload") or {},
        dice_rolls=dice_rolls,
    )
    scene["scene_qa"] = scene_qa_memory
    scene["quality_debug"] = {
        **(scene.get("quality_debug") or {}),
        "scene_qa_final": scene_qa_memory,
        "truth_table": scene_qa_memory.get("truth_table", {}),
        "opening_shape": scene_qa_memory.get("opening_shape", {}),
        "gm_move": scene_qa_memory.get("gm_move", ""),
        "scene_purpose": scene_qa_memory.get("scene_purpose", {}),
        "tension_curve": scene_qa_memory.get("tension_curve", {}),
        "npc_scene_roles": scene_qa_memory.get("npc_scene_roles", []),
        "detail_budget": scene_qa_memory.get("detail_budget", {}),
        "campaign_palette": scene_qa_memory.get("campaign_palette", {}),
        "memory_delta_consistency": scene_qa_memory.get("memory_delta_consistency", {}),
        "ui_payload_validation": scene_qa_memory.get("ui_payload_validation", {}),
        "regression_tags": scene_qa_memory.get("regression_tags", []),
        "first_scene_validation": first_scene_validation,
    }
    simulation_agent.atomic_write_json(folder / 'world_state.json', opening_world_state)
    simulation_agent.seed_persistent_npcs(folder, scene)
    simulation_agent.seed_location_state(folder, scene, opening_world_state)
    simulation_agent.atomic_write_json(folder / 'last_memory_delta.json', opening_memory_delta)
    simulation_agent.append_canon_memory(folder, scene.get('id', 'opening'), opening_memory_delta)
    simulation_agent.atomic_write_json(folder / 'scene.json', scene)

    # --- Step 6: NPC Manager — enrich profiles from Scene Director data ---
    npc_profiles: list[dict] = []

    def _make_npc_from_director(blueprint: dict, scene_id: str, sid: str) -> dict:
        """Build an enriched NPC profile dict from a Scene Director NPC blueprint."""
        existing_detail = next(
            (n for n in mem_npc_details if n.get('name') == blueprint.get('name')), {}
        )
        return {
            'name': blueprint.get('name', ''),
            'role': blueprint.get('role', ''),
            'emotional_state': blueprint.get('current_emotional_state', ''),
            'motivations': [blueprint.get('what_they_want', '')] if blueprint.get('what_they_want') else [],
            'secrets': [],
            'first_seen_scene_id': scene_id,
            'associated_location': loc_name,
            'associated_thread': candidate_threads[0] if candidate_threads else '',
            'current_goal': existing_detail.get('goal') or blueprint.get('what_they_want', ''),
            'known_information': [blueprint.get('what_they_know', '')] if blueprint.get('what_they_know') else [],
            'relationship_to_player': director_output.why_player_is_involved[:120] if director_output.why_player_is_involved else '',
            'source': director_output.source,
        }

    # Primary NPC from Scene Director
    if npc_name:
        try:
            blueprint = director_output.primary_npc.model_dump()
            enriched = _make_npc_from_director(blueprint, 'opening', session_id)
            result = await npc_agent.manage_npc(npc_agent.NPCManageRequest(
                name=npc_name,
                motivations=enriched['motivations'],
                personality=enriched.get('emotional_state', ''),
                appearance='',
                backstory='',
                session_id=session_id,
                traits=enriched,
            ))
            npc_profiles.append(result.npc_profile)
        except Exception:
            pass

    # Secondary entities (name-only) from Scene Director
    for secondary_name in director_output.secondary_entities[:3]:
        if secondary_name and secondary_name != npc_name:
            try:
                result = await npc_agent.manage_npc(npc_agent.NPCManageRequest(
                    name=secondary_name,
                    session_id=session_id,
                    traits={'source': 'scene_director', 'first_seen_scene_id': 'opening'},
                ))
                npc_profiles.append(result.npc_profile)
            except Exception:
                pass

    # Any additional NPCs mentioned in storyboard but not yet profiled
    existing_names = {p.get('name') for p in npc_profiles}
    for extra_name in plot_result.npcs_mentioned:
        if extra_name and extra_name not in existing_names:
            try:
                result = await npc_agent.manage_npc(npc_agent.NPCManageRequest(
                    name=extra_name,
                    session_id=session_id,
                    traits={'source': 'storyboard', 'first_seen_scene_id': 'opening'},
                ))
                npc_profiles.append(result.npc_profile)
                existing_names.add(extra_name)
            except Exception:
                pass

    # --- Step 7: Broadcast scene to players ---
    await broadcaster.broadcast_json(session_id, {
        'type': 'narrative.scene',
        'session_id': session_id,
        'scene': scene,
    })

    ready_path = folder / 'ready.json'
    ready_path.write_text(json.dumps({}))

    # --- Story Validator + State Update ---
    story_validator_result = None
    story_debug: dict | None = None
    if story_state is not None and narrative_director_output is not None:
        try:
            story_validator_result = validate_story_structure(
                scene_text=scene.get('text', ''),
                director=narrative_director_output,
                state=story_state,
                scene_type=narrative_director_output.recommended_scene_type,
                npc_names=candidate_npcs[:10],
                location_names=candidate_locations[:6],
            )
            story_state = update_state_after_scene(
                state=story_state,
                scene_type=narrative_director_output.recommended_scene_type,
                scene_purpose=narrative_director_output.scene_purpose,
                scene_id=scene.get('id', session_id),
                location=loc_name,
                npcs_featured=[n for n in candidate_npcs[:5] if n.lower() in scene.get('text', '').lower()],
                threads_advanced=narrative_director_output.threads_to_advance,
                threads_resolved=narrative_director_output.threads_to_resolve,
                emotional_target=narrative_director_output.emotional_target,
                director_tension_target=narrative_director_output.target_tension,
                story_score=story_validator_result.score,
                director_recommendation_followed=True,
            )
            save_story_state(story_state)
            story_debug = {
                'director': narrative_director_output.model_dump(),
                'story_state': story_dashboard_payload(story_state),
                'story_validator': story_validator_result.to_dict(),
            }
        except Exception:
            pass

    scene_debug = {
        'storyboard_plot': plot_result.plot,
        'storyboard_hooks': plot_result.hooks,
        'campaign_storyboard': getattr(plot_result, 'campaign_storyboard', {}),
        'session_storyboard': getattr(plot_result, 'session_storyboard', {}),
        'campaign_scale_profile': campaign_scale_profile,
        'story_shape_profile': story_shape_profile,
        'arc_plan': opening_arc_plan,
        'selected_scene_beat': opening_scene_beat,
        'content_bundle': opening_content_bundle,
        'content_bundle_validation': opening_content_bundle.get('validation_result', {}),
        'story_model_stage': story_shape_profile.get('current_arc_stage', ''),
        'thread_budget': {
            'max_open_threads': campaign_scale_profile.get('max_open_threads'),
            'active_thread_count': len(candidate_threads),
            'threads_to_retire': opening_arc_plan.get('threads_to_retire', []),
        },
        'repetition_warnings': opening_scene_beat.get("repetition_warnings", []),
        'scene_director_source': director_output.source,
        'scene_director': {
            'location': loc_name,
            'primary_npc': npc_name,
            'central_conflict': director_output.central_conflict,
            'inciting_incident': director_output.inciting_incident,
            'immediate_stakes': director_output.immediate_stakes,
        },
        'quality_score': quality_score,
        'quality_issues': quality_issues,
        'retry_used': retry_used,
        'fallback_used': fallback_used,
        'image_prompt': image_prompt,
        'scene_score': narrative.scene_score,
        'scene_score_passed': narrative.score_passed,
        'scene_score_detail': narrative.score_detail,
        'scene_qa': scene.get('scene_qa') or {},
        'quality_debug': scene.get('quality_debug') or {},
        'campaign_contract': {
            'canon_policy': campaign_contract.get('canon_policy', {}),
            'ai_creativity_policy': campaign_contract.get('ai_creativity_policy', {}),
            'backstory_policy': campaign_contract.get('backstory_policy', {}),
            'ui_policy': campaign_contract.get('ui_policy', {}),
        } if campaign_contract else {},
        'contract_validator': contract_validator,
        'backstory_profiles': backstory_profiles,
        'backstory_hooks': backstory_hooks,
        'session_zero': session_zero_summary,
    }

    context_debug = context_packet.debug_payload() if context_packet else None

    return {
        'ok': True,
        'scene': scene,
        'plot': plot_result.plot,
        'hooks': plot_result.hooks,
        'dice_rolls': dice_rolls,
        'npc_profiles': npc_profiles,
        'scene_debug': scene_debug,
        'context_debug': context_debug,
        'story_debug': story_debug,
    }


# ---------------------------------------------------------------------------
# Returning Session Workflow – Step 1: Player "Done" Signal
# ---------------------------------------------------------------------------

class PlayerReadyRequest(BaseModel):
    done: bool = True


@router.post('/{session_id}/player-ready')
async def player_ready(session_id: str, payload: PlayerReadyRequest, current_user=Depends(get_current_user)):
    """Mark the current player as done contributing to chat (Returning Session Workflow, Step 1).

    When all session members have signalled ready, the response includes
    ``all_ready: true`` so the frontend knows it can trigger ``/advance-scene``.
    """
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    # Load/update ready state
    ready_path = folder / 'ready.json'
    try:
        ready: dict = json.loads(ready_path.read_text()) if ready_path.exists() else {}
    except Exception:
        ready = {}

    ready[identifier] = payload.done
    ready_path.write_text(json.dumps(ready))

    # Determine all_ready: every member who has an entry must be done.
    members = meta.get('members', []) or []
    member_ids = [_normalize_email(m.get('email')) for m in members if m.get('email')]
    if not member_ids:
        member_ids = [_normalize_email(meta.get('owner') or '')]
    all_ready = bool(member_ids) and all(ready.get(mid) for mid in member_ids)

    await broadcaster.broadcast_json(session_id, {
        'type': 'player.ready',
        'session_id': session_id,
        'player': identifier,
        'done': payload.done,
        'all_ready': all_ready,
    })

    return {'ok': True, 'player': identifier, 'done': payload.done, 'all_ready': all_ready}


# ---------------------------------------------------------------------------
# Returning Session Workflow – Steps 2–5: Advance Scene
# ---------------------------------------------------------------------------

class AdvanceSceneRequest(BaseModel):
    style: str | None = None
    weather: str | None = None
    time_of_day: str | None = None
    developer_mode: bool = False
    opening_approach: str | None = None


@router.post('/{session_id}/advance-scene')
async def advance_scene(session_id: str, payload: AdvanceSceneRequest, current_user=Depends(get_current_user)):
    """Orchestrate the Returning Session Workflow (Steps 2–5).

    Step 2 – Narrative Agent analyses recent chat; Scene Analysis checks for dice rolls.
    Step 3 – Notes Agent logs session notes; Storyboard is updated with player choices.
    Step 4 – Narrative Agent creates the new scene; Image Generation kicks off.
    Step 5 – New scene is broadcast to all session members.
    """
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    style = payload.style or 'balanced'
    campaign_id = meta.get('campaign_id')
    campaign_settings: dict = {}
    campaign_variables: dict = {}
    campaign_contract: dict = {}
    backstory_profiles: list[dict] = []
    backstory_hooks: list[dict] = []
    session_zero_summary: dict = {}
    campaign_scale_profile: dict = {}
    story_shape_profile: dict = {}
    if campaign_id:
        try:
            campaign = db.get_campaign_by_id(str(campaign_id))
            if campaign and isinstance(campaign.metadata_json, dict):
                campaign_settings = campaign.metadata_json.get('settings') or {}
                if not isinstance(campaign_settings, dict):
                    campaign_settings = {}
                campaign_variables = campaign.metadata_json.get('variables') or {}
                if not isinstance(campaign_variables, dict):
                    campaign_variables = {}
                campaign_contract, backstory_profiles, backstory_hooks, session_zero_summary = _campaign_package_from_metadata(campaign)
                campaign_scale_profile = campaign.metadata_json.get('campaign_scale_profile') or campaign_contract.get('campaign_scale_profile') or {}
                story_shape_profile = campaign.metadata_json.get('story_shape_profile') or campaign_contract.get('story_shape_profile') or {}
        except Exception:
            pass
    if campaign_scale_profile:
        campaign_contract.setdefault("campaign_scale_profile", campaign_scale_profile)
    if story_shape_profile:
        campaign_contract.setdefault("story_shape_profile", story_shape_profile)

    if is_player_run_mode(session_id):
        raise HTTPException(status_code=400, detail='advance-scene is not available in player-run mode')

    owns_generation, generation_lock = simulation_agent.acquire_scene_lock(folder, session_id)
    if not owns_generation:
        return {
            'ok': False,
            'generation': generation_lock,
            'status': generation_lock.get('status') or 'running',
        }

    # --- Step 2: Collect recent player chat and analyse for dice rolls ---
    recent_messages = db.list_chat_messages(session_id=session_id, limit=20)
    player_actions = [
        m.message for m in recent_messages
        if m.role not in ('gm', 'narrator', 'system') and m.message
    ]
    # Opening approach from the pre-first-scene selection UI — used when there
    # are no chat messages yet so the LLM has context for the scene tone.
    if not player_actions and payload.opening_approach:
        player_actions = [payload.opening_approach]

    # Load current scene for context
    scene_text = ''
    previous_scene: dict = {}
    try:
        scene_path = folder / 'scene.json'
        if scene_path.exists():
            previous_scene = json.loads(scene_path.read_text())
            scene_text = previous_scene.get('text', '')
    except Exception:
        pass

    selected_character_context = {}
    for member in meta.get('members', []) or []:
        if member.get('character_name'):
            selected_character_context = {"name": member.get('character_name'), "id": member.get('character_id')}
            break
    player_intent = parse_player_intent(
        recent_player_chat=player_actions,
        selected_character=selected_character_context,
        current_scene=previous_scene,
        pending_rolls=[],
        active_situation=previous_scene.get("situation_type") or "",
    ).model_dump()

    dice_rolls: list[dict] = []
    try:
        cues = await scene_agent.analyze_scene(scene_agent.SceneAnalysisRequest(
            scene=scene_text,
            actions=player_actions,
            session_id=session_id,
        ))
        dice_rolls = [r.model_dump() for r in cues.dice_rolls]
    except Exception:
        pass

    # --- Step 3: Notes Agent logs the interaction; Storyboard is updated ---
    notes_to_log = [f"[player] {a}" for a in player_actions[:10]]
    try:
        notes_agent._ensure_notes_member(session_id, current_user)
        notes_agent._append_to_session_notes(
            session_id,
            notes_to_log,
            notes_agent._generate_recap(notes_to_log),
        )
    except Exception:
        pass

    # Update storyboard with player choices as new story beats
    storyboard_choices = player_actions[:5]
    try:
        storyboard_agent.update_storyboard(storyboard_agent.StoryboardRequest(
            scene=scene_text,
            choices=storyboard_choices,
            unresolved=[],
            completed=[],
        ))
    except Exception:
        pass

    # --- Time Resolver + World Tick Engine ---
    world_state_before = simulation_agent.load_world_state(folder)
    simulation_agent.seed_persistent_npcs(folder, previous_scene)
    simulation_agent.seed_location_state(folder, previous_scene, world_state_before)
    time_result = simulation_agent.resolve_time(world_state_before, player_actions)
    world_state, simulation_delta, tick_policies = simulation_agent.tick_world(
        folder,
        world_state_before,
        time_result,
        player_actions,
    )
    if payload.weather:
        world_state["weather"] = payload.weather
    if payload.time_of_day:
        world_state["time_of_day"] = payload.time_of_day
    weather = str(world_state.get("weather") or "clear")
    time_of_day = str(world_state.get("time_of_day") or "day")
    persistent_npcs = simulation_agent.seed_persistent_npcs(folder, previous_scene)
    simulation_agent.seed_location_state(folder, previous_scene, world_state)
    selected_templates = simulation_agent.select_scene_templates(player_actions, time_result, simulation_delta)

    # --- Step 4a: Situation Classifier ---
    adv_experience_mode = str((simulation_delta or {}).get("experience_mode") or "")
    # Derive an approximate scene count from whether a *real* previous scene exists.
    # The initial scene.json is a placeholder (id='opening', no narrative_body) and
    # must NOT count as a prior scene — otherwise scene_count=1 and the campaign_opening
    # classifier never fires, so the tavern-avoidance seed injection never runs.
    _adv_prior_scene_text = previous_scene.get("text") or ""
    _adv_prior_is_placeholder = (
        previous_scene.get("id") == "opening"
        and not previous_scene.get("narrative_body")
        and (
            not _adv_prior_scene_text
            or _adv_prior_scene_text.startswith("Your adventure is about to begin")
        )
    )
    _adv_prior_scene_exists = bool(
        (previous_scene.get("id") or previous_scene.get("text"))
        and not _adv_prior_is_placeholder
    )
    adv_scene_count = 0 if not _adv_prior_scene_exists else 1
    adv_situation = classify_situation(
        player_actions=player_actions,
        previous_scene=previous_scene if _adv_prior_scene_exists else None,
        world_state=world_state,
        simulation_delta=simulation_delta,
        experience_mode=adv_experience_mode,
        director_scene_type=selected_templates[0] if selected_templates else "",
        scene_count=adv_scene_count,
    )
    adv_situation_type: str = adv_situation["situation_type"]

    # --- Step 4: Context Orchestrator + Scene Template Selector + Narrative Agent ---
    adv_context_packet = None
    world_context_block = ""
    session_players = _session_player_names(folder, meta)
    adv_player_name = session_players[0] if session_players else "the party"

    current_location_name = (
        previous_scene.get('location')
        or ((previous_scene.get('scene_director_data') or {}).get('location') or {}).get('name')
        or ((previous_scene.get('visual_state') or {}).get('location_name'))
        or ''
    )
    simulation_context_block = simulation_agent.orchestrated_simulation_context(
        world_state,
        simulation_delta,
        location_name=current_location_name,
        npcs=persistent_npcs,
    )

    if payload.opening_approach:
        required = {}
        try:
            required = (ensure_content_bundle(
                situation_type="campaign_opening",
                scene_director_output={},
                world_state=world_state,
                campaign_contract=campaign_contract,
                previous_scene=previous_scene,
                freshness_context=_opening_freshness_context(str(campaign_id) if campaign_id else None, fast_opening_choice=True),
                campaign_settings=campaign_settings,
            ).get("required_content") or {})
        except Exception:
            required = {}
        loc_hay = str(current_location_name or "").strip().lower()
        loc_needs_seed = (
            not loc_hay
            or loc_hay in {"the current location", "current location"}
            or loc_hay.startswith("for ")
            or _contains_recycled_opening_fixture(loc_hay)
            or required.get("generated_by") == "premise_seed"
        )
        if loc_needs_seed and not required:
            try:
                required = (ensure_content_bundle(
                    situation_type="campaign_opening",
                    scene_director_output={},
                    world_state=world_state,
                    campaign_contract=campaign_contract,
                    previous_scene=previous_scene,
                    freshness_context=_opening_freshness_context(str(campaign_id) if campaign_id else None, fast_opening_choice=True),
                    campaign_settings=campaign_settings,
                ).get("required_content") or {})
            except Exception:
                required = {}
        fast_location = str(required.get("starting_location") or current_location_name or meta.get("name") or "the opening scene")
        fast_location_type = str(required.get("location_type") or "opening location")
        fast_npc_label = str(required.get("named_npc_or_visible_threat") or "")
        fast_npc = fast_npc_label.split("(")[0].strip() or (
            ((previous_scene.get("scene_director_data") or {}).get("primary_npc") or {}).get("name")
            or "the nearest witness"
        )
        action_response = _action_response_scene(
            player_name=adv_player_name,
            location_name=fast_location,
            latest_action=str(payload.opening_approach or ""),
            action_count=len(player_actions),
            approved_context={
                "clue": required.get("first_clue_or_question") or "",
                "object": required.get("approved_object") or "",
                "stakes": required.get("specific_stakes") or "",
                "npc": fast_npc_label or fast_npc,
            },
        )
        if required:
            action_response["objective"] = str(required.get("player_decision") or action_response["objective"])
            action_response["stakes"] = str(required.get("specific_stakes") or action_response["stakes"])
            action_response["clues"] = [
                str(required.get("first_clue_or_question") or ""),
                str(required.get("inciting_event") or ""),
                *action_response.get("clues", []),
            ]
            action_response["clues"] = [c for c in action_response["clues"] if c][:4]
            identity = str(required.get("location_identity") or f"{fast_location} is already under pressure").rstrip(".")
            inciting = str(required.get("inciting_event") or "").rstrip(".")
            first_clue = str(required.get("first_clue_or_question") or (action_response["clues"] or [""])[0]).rstrip(".")
            decision = str(required.get("player_decision") or action_response["objective"]).rstrip(".")
            action_text = str(payload.opening_approach or "act").strip()
            identity_sentence = identity[0].lower() + identity[1:] if identity else "the opening danger is visible"
            player_sentence = adv_player_name[0].upper() + adv_player_name[1:] if adv_player_name else "The party"
            clue_sentence = first_clue if first_clue.endswith(("?", "!", ".")) else f"{first_clue}."
            action_response["narrative"] = (
                f"At {fast_location}, {identity_sentence}.\n\n"
                f"{player_sentence} follows the first choice through: {action_text}. "
                f"{inciting or 'The scene answers with a sign too concrete to ignore'}.\n\n"
                f"The useful detail is not separate from the danger. {clue_sentence} "
                f"{action_response['stakes']}\n\n"
                f"The moment is still narrow enough to shape. {decision}."
            )

        now = datetime.now(timezone.utc)
        scene_index = f"scene-{uuid.uuid4().hex[:8]}"
        prompt = f"What does {adv_player_name} do?"
        fast_scene = {
            "id": scene_index,
            "title": action_response["title"],
            "image": previous_scene.get("image"),
            "narrative_body": action_response["narrative"],
            "player_prompt": prompt,
            "text": f"{action_response['narrative']}\n\n{prompt}",
            "choices": [
                {"id": f"action_{i}", "label": label}
                for i, label in enumerate((action_response.get("suggested_actions") or [])[:4])
            ],
            "suggested_actions": (action_response.get("suggested_actions") or [])[:4],
            "world_moves": (action_response.get("world_moves") or [])[:4],
            "active_player": adv_player_name,
            "location": fast_location,
            "weather": weather,
            "time_of_day": time_of_day,
            "time_block": world_state.get("time_block"),
            "campaign_day": world_state.get("campaign_day"),
            "immediate_stakes": action_response["stakes"],
            "visible_clues": action_response.get("clues") or [],
            "current_objective": action_response["objective"],
            "situation_type": "opening_choice",
            "situation_classification": {
                **adv_situation,
                "situation_type": "opening_choice",
                "reason": "Fast deterministic response to opening choice.",
            },
            "scene_director_data": {
                "source": "fast_opening_choice",
                "scene_title": action_response["title"],
                "scene_type": "opening_choice",
                "location": {
                    "name": fast_location,
                    "type": fast_location_type,
                    "sensory_details": [str(required.get("location_identity") or "")] if required.get("location_identity") else [],
                },
                "primary_npc": {
                    "name": fast_npc,
                    "role": fast_npc_label or "local witness",
                    "current_emotional_state": "urgent",
                    "what_they_want": action_response["objective"],
                    "what_they_know": str(required.get("first_clue_or_question") or ""),
                },
                "central_conflict": action_response["objective"],
                "inciting_incident": str(required.get("inciting_event") or payload.opening_approach or ""),
                "immediate_stakes": action_response["stakes"],
                "player_visible_clues": action_response.get("clues") or [],
                "possible_actions": (action_response.get("suggested_actions") or [])[:4],
                "world_moves": (action_response.get("world_moves") or [])[:4],
                "visual_prompt_elements": [
                    f"{fast_location}, {fast_location_type}",
                    str(required.get("location_identity") or action_response["objective"]),
                    str(required.get("inciting_event") or payload.opening_approach or ""),
                ],
            },
            "content_bundle": {"required_content": required} if required else previous_scene.get("content_bundle", {}),
            "fast_path": "opening_choice",
        }
        try:
            fast_vs, fast_img_prompt, fast_refresh = run_visual_pipeline(
                session_id=session_id,
                scene_text=fast_scene["text"],
                location_name=fast_location,
                location_type=fast_location_type,
                weather=weather,
                time_of_day=time_of_day,
                previous_visual_state=load_visual_state(session_id),
            )
            fast_scene["visual_state"] = fast_vs.model_dump()
            save_visual_state(session_id, fast_vs)
            if fast_refresh or not fast_scene.get("image"):
                img = image_agent.generate_image(image_agent.ImageRequest(prompt=fast_img_prompt, style="realistic"))
                fast_scene["image"] = img.image_url
        except Exception:
            pass

        fast_scene = simulation_agent.normalize_scene_presentation(fast_scene, world_state, simulation_delta)
        simulation_agent.atomic_write_json(folder / 'world_state.json', world_state)
        simulation_agent.atomic_write_json(folder / 'last_simulation_delta.json', simulation_delta)
        simulation_agent.atomic_write_json(folder / 'scene.json', fast_scene)
        cur = _load_story_entries(folder)
        last_story_ts = _story_last_timestamp(cur)
        cur.extend(_story_action_entries_since(recent_messages, last_story_ts))
        cur.append({
            "type": "narration",
            "ts": now.isoformat(),
            "text": fast_scene["text"],
            "scene_id": scene_index,
            "campaign_day": fast_scene.get("campaign_day"),
            "time_block": fast_scene.get("time_block"),
        })
        _write_story_entries(folder, sorted(cur, key=lambda e: str(e.get("ts") or "")))
        simulation_agent.atomic_write_json(folder / 'ready.json', {})
        generation_lock = simulation_agent.complete_scene_lock(folder, generation_lock, "complete")
        await broadcaster.broadcast_json(session_id, {
            "type": "narrative.scene",
            "session_id": session_id,
            "scene": fast_scene,
        })
        return {
            "ok": True,
            "scene": fast_scene,
            "dice_rolls": [],
            "generation": generation_lock,
            "simulation_debug": {"fast_path": "opening_choice", "required_content": required},
        }

    if campaign_id:
        try:
            from .context_orchestrator import orchestrate
            adv_context_packet = orchestrate(
                campaign_id=str(campaign_id),
                session_id=session_id,
                player_name=adv_player_name,
                player_actions=player_actions,
                use_cache=False,
            )
            world_context_block = adv_context_packet.for_narrative()
        except Exception:
            try:
                from .context_collector import collect_context
                ctx = collect_context(
                    campaign_id=str(campaign_id),
                    session_id=session_id,
                    recent_chat=player_actions,
                )
                world_context_block = ctx.get("prompt_block") or ""
            except Exception:
                pass

    world_context_parts = [part for part in (simulation_context_block, world_context_block) if part]
    world_context_block = "\n\n".join(world_context_parts)

    # --- Narrative Director: scene-level story guidance ---
    adv_story_state = load_story_state(str(campaign_id)) if campaign_id else None
    adv_director_output: DirectorOutput | None = None
    if adv_story_state is not None:
        try:
            adv_director_output = narrative_direct_scene(
                state=adv_story_state,
                player_name=adv_player_name,
                player_actions=player_actions,
            )
        except Exception:
            adv_director_output = None

    scene_summary = ' '.join(player_actions[:3]) if player_actions else 'The party deliberates their next move.'
    if world_context_block:
        scene_summary = f"{scene_summary}\n\n{world_context_block}"

    director_guidance = simulation_agent.build_director_guidance(
        adv_director_output.model_dump() if adv_director_output else None,
        selected_templates,
        simulation_delta,
        world_state,
    )

    # --- Step 4b: Pre-generate opening seed for first scene ---
    # For campaign openings with no prior context, generate the starter seed NOW —
    # before the Scene Director LLM runs — and inject it as hard constraints.
    # Without this, the LLM defaults to a tavern because the plot_seed is empty.
    adv_opening_seed: dict = {}
    if adv_situation_type == "campaign_opening" and adv_scene_count == 0:
        # Only seed if the campaign has no location context of its own
        contract_has_location = bool(
            campaign_contract and (
                (campaign_contract.get("campaign_dna") or {}).get("starting_location")
                or (campaign_contract.get("world_contract") or {}).get("known_starting_location")
                or campaign_contract.get("player_canon")
            )
        )
        if not contract_has_location:
            adv_opening_seed = build_content_bundle(
                situation_type="campaign_opening",
                scene_director_output={},
                world_state=world_state,
                campaign_contract=campaign_contract,
                freshness_context=_opening_freshness_context(str(campaign_id) if campaign_id else None),
                campaign_settings=campaign_settings,
            ).get("required_content") or {}
        else:
            # Campaign has lore — generate seed to derive location type but use
            # contract's setting summary rather than a random seed location
            setting_summary = (campaign_contract.get("campaign_dna") or {}).get("setting_summary") or ""
            if setting_summary:
                adv_opening_seed = {
                    "required_location_constraint": setting_summary[:200],
                    "generated_by": "contract_setting",
                }

        # Inject seed as hard director_guidance constraints so the LLM is bound
        if adv_opening_seed and adv_opening_seed.get("generated_by") != "contract_setting":
            loc = adv_opening_seed.get("starting_location") or ""
            npc = adv_opening_seed.get("named_npc_or_visible_threat") or ""
            event = adv_opening_seed.get("inciting_event") or ""
            stakes = adv_opening_seed.get("specific_stakes") or ""
            decision = adv_opening_seed.get("player_decision") or ""
            if loc:
                director_guidance["required_opening_location"] = loc
            if npc:
                director_guidance["required_opening_npc"] = npc
            if event:
                director_guidance["required_opening_event"] = event
            if stakes:
                director_guidance["required_opening_stakes"] = stakes
            if decision:
                director_guidance["required_opening_decision"] = decision
            # Strengthen the plot_seed so the LLM has rich context
            seed_summary = f"Opening location: {loc}. Inciting event: {event}. NPC: {npc}. Stakes: {stakes}."
            if scene_summary and "deliberates" not in scene_summary:
                scene_summary = f"{seed_summary}\n\n{scene_summary}"
            else:
                scene_summary = seed_summary
        elif adv_opening_seed.get("required_location_constraint"):
            director_guidance["required_opening_location_context"] = adv_opening_seed["required_location_constraint"]

    mem_npc_details = []
    if adv_context_packet:
        mem_npc_details = [
            {
                "name": n.name,
                "goal": n.goal,
                "emotional_state": n.current_emotional_state,
                "next_action": n.likely_next_action,
                "faction": n.faction,
                "known_information": n.known_information,
            }
            for n in adv_context_packet.active_npcs
        ]
    if not mem_npc_details:
        mem_npc_details = [
            {
                "name": n.get("name"),
                "goal": n.get("immediate_goal") or n.get("current_task"),
                "emotional_state": n.get("current_mood"),
                "next_action": n.get("current_task"),
                "faction": n.get("role"),
                "known_information": n.get("knowledge") or [],
            }
            for n in persistent_npcs if n.get("name")
        ]

    mem_loc_details = []
    if adv_context_packet and adv_context_packet.location.name:
        mem_loc_details.append({
            "name": adv_context_packet.location.name,
            "current_tension": (adv_context_packet.location.current_tensions or [""])[0],
            "description": adv_context_packet.location.description,
            "atmosphere": adv_context_packet.location.atmosphere,
        })
    if current_location_name and not any(loc_item.get("name") == current_location_name for loc_item in mem_loc_details):
        mem_loc_details.append({
            "name": current_location_name,
            "current_tension": "",
            "description": "",
            "atmosphere": f"{weather}, {time_of_day}",
        })

    candidate_threads = []
    if adv_context_packet:
        candidate_threads = [
            t.current_state or t.title
            for t in adv_context_packet.story_threads
            if t.current_state or t.title
        ]

    adv_campaign_storyboard = previous_scene.get("campaign_storyboard") or storyboard_agent.create_campaign_storyboard(
        campaign_id=str(campaign_id or session_id),
        campaign_premise=campaign_contract.get("campaign_pitch") or meta.get("name") or "",
        central_question=(candidate_threads[0] if candidate_threads else ""),
        major_threat=str(campaign_variables.get("major_threat") or ""),
        major_factions=[],
        open_threads=candidate_threads,
        backstory_hooks_available=[str(h.get("summary") or h.get("hook") or "") for h in backstory_hooks if isinstance(h, dict)],
    ).model_dump()
    adv_arc_plan = plan_arc({
        "campaign_contract": campaign_contract,
        "campaign_scale_profile": campaign_scale_profile,
        "story_shape_profile": story_shape_profile,
        "campaign_storyboard": adv_campaign_storyboard,
        "active_threads": candidate_threads,
        "world_clocks": simulation_delta.get("faction_advances") or simulation_delta.get("threat_updates") or [],
        "backstory_spotlight": campaign_contract.get("backstory_spotlight") or [],
    }).model_dump()
    adv_session_storyboard = previous_scene.get("session_storyboard") or storyboard_agent.generate_session_storyboard(
        session_id=session_id,
        campaign=storyboard_agent.CampaignStoryboard(**adv_campaign_storyboard),
        campaign_contract={
            **campaign_variables,
            "pacing_profile": (campaign_scale_profile or {}).get("planning_horizon") or "",
        },
        recent_patterns=storyboard_agent.PacingPatternState(
            recent_scene_types=[previous_scene.get("situation_type") or ""] if previous_scene.get("situation_type") else [],
            recent_motifs=previous_scene.get("visible_clues") or [],
            recent_locations=[current_location_name] if current_location_name else [],
        ),
    ).model_dump()
    selected_scene_beat = select_scene_beat_plan({
        "session_storyboard": adv_session_storyboard,
        "campaign_storyboard": adv_campaign_storyboard,
        "arc_plan": adv_arc_plan,
        "player_intent": player_intent,
        "simulation_delta": simulation_delta,
        "current_location": {"name": current_location_name},
        "active_npcs": mem_npc_details,
        "active_threads": candidate_threads,
        "recent_scene_types": [previous_scene.get("situation_type") or ""] if previous_scene.get("situation_type") else [],
        "recent_motifs": previous_scene.get("visible_clues") or [],
        "backstory_spotlight": campaign_contract.get("backstory_spotlight") or [],
    })
    if selected_scene_beat.get("scene_type"):
        adv_situation_type = selected_scene_beat["scene_type"]
        adv_situation = {
            **adv_situation,
            "situation_type": adv_situation_type,
            "reason": f"{adv_situation.get('reason', '')}; scene beat selector: {selected_scene_beat.get('selection_reason', '')}".strip("; "),
            "requires_content_contract": adv_situation_type in REQUIRES_CONTRACT,
        }
    director_guidance["selected_scene_beat"] = selected_scene_beat
    if selected_scene_beat.get("location"):
        scene_summary = f"{scene_summary}\n\nSelected scene beat: {selected_scene_beat.get('scene_purpose')} at {selected_scene_beat.get('location')}"
    else:
        scene_summary = f"{scene_summary}\n\nSelected scene beat: {selected_scene_beat.get('scene_purpose')}"

    adv_scene_director_output: SceneDirectorOutput = scene_director_agent.direct_scene(SceneDirectorRequest(
        campaign_settings=campaign_settings,
        campaign_variables=campaign_variables,
        players=[adv_player_name] if adv_player_name else [],
        plot_seed=scene_summary,
        candidate_npcs=[n.get("name", "") for n in mem_npc_details if n.get("name")][:6],
        candidate_npc_details=mem_npc_details[:6],
        candidate_locations=[loc_item.get("name", "") for loc_item in mem_loc_details if loc_item.get("name")][:4],
        candidate_location_details=mem_loc_details[:4],
        candidate_factions=[],
        candidate_story_threads=candidate_threads[:4],
        candidate_thread_details=[],
        open_hooks=[],
        recent_events=[
            item if isinstance(item, str) else json.dumps(item, sort_keys=True)
            for key, values in simulation_delta.items()
            if key != "time_changes"
            for item in values[:2]
        ][:4],
        world_context_block=world_context_block,
        director_guidance=director_guidance,
        campaign_contract=campaign_contract,
    ))
    if selected_templates:
        adv_scene_director_output.scene_type = " + ".join(selected_templates)

    adv_director_data = adv_scene_director_output.model_dump()

    # --- Step 4c: Content Bundle + Situation Validation ---
    adv_content_bundle: dict = {}
    adv_situation_validated = True
    if adv_situation.get("requires_content_contract"):
        adv_freshness_context = {
            "scene_count": adv_scene_count,
            "recent_location_types": [],
            "recent_opening_events": [],
        }
        adv_content_bundle = ensure_content_bundle(
            situation_type=adv_situation_type,
            scene_director_output=adv_director_data,
            world_state=world_state,
            campaign_contract=campaign_contract,
            previous_scene=previous_scene,
            freshness_context=adv_freshness_context,
            campaign_settings=campaign_settings,
        )
        adv_situation_validated = adv_content_bundle.get("validated", True)

        # --- Deterministic override: if the seed replaced a tavern default,
        # patch adv_director_data NOW so the Composer and Narrative Writer use
        # the seed's content rather than whatever the LLM Scene Director produced.
        # This is a hard override — LLM instruction-following is unreliable here.
        _rc = adv_content_bundle.get("required_content") or {}
        if _rc.get("generated_by") == "starter_seed":
            seed_loc = _rc.get("starting_location") or ""
            seed_npc = _rc.get("named_npc_or_visible_threat") or ""
            seed_event = _rc.get("inciting_event") or ""
            seed_stakes = _rc.get("specific_stakes") or ""
            if seed_loc and adv_director_data.get("location"):
                adv_director_data["location"]["name"] = seed_loc
            if seed_npc and adv_director_data.get("primary_npc"):
                # Only override if the LLM produced a tavern/generic name
                from .content_bundles import _looks_like_tavern_default
                llm_npc = (adv_director_data.get("primary_npc") or {}).get("name") or ""
                if not llm_npc or _looks_like_tavern_default(llm_npc) or llm_npc.lower() in ("a stranger", "a mysterious figure", "the barkeep", "innkeeper"):
                    adv_director_data["primary_npc"]["name"] = seed_npc
            if seed_event and not adv_director_data.get("inciting_incident"):
                adv_director_data["inciting_incident"] = seed_event
            if seed_stakes and not adv_director_data.get("immediate_stakes"):
                adv_director_data["immediate_stakes"] = seed_stakes
            # Rebuild the scene_summary so the narrative writer also gets the correct location
            scene_summary = (
                f"Opening location: {seed_loc}. "
                f"Inciting event: {seed_event}. "
                f"NPC: {seed_npc}. "
                f"Stakes: {seed_stakes}.\n\n" + scene_summary
            ).strip()
    else:
        adv_content_bundle = ensure_content_bundle(
            situation_type=adv_situation_type,
            scene_director_output=adv_director_data,
            world_state=world_state,
            campaign_contract=campaign_contract,
            previous_scene=previous_scene,
            freshness_context={"scene_count": adv_scene_count},
            campaign_settings=campaign_settings,
        )
        adv_situation_validated = adv_content_bundle.get("validated", True)

    bundle_dice_rolls = _dice_rolls_from_content_bundle(adv_content_bundle)
    if bundle_dice_rolls:
        dice_rolls = bundle_dice_rolls

    adv_composer_output = narrative_composer_agent.compose_scene(
        scene_director_data=adv_director_data,
        player_name=adv_player_name,
        scene_type=adv_scene_director_output.scene_type or selected_templates[0],
    )
    adv_composer_data = adv_composer_output.model_dump()

    narrative = narrative_agent.generate_narrative(narrative_agent.NarrativeRequest(
        scene=scene_summary,
        player=adv_player_name,
        style=style,
        weather=weather,
        time_of_day=time_of_day,
        scene_director_data=adv_director_data,
        composer_data=adv_composer_data,
        player_actions=player_actions,
        campaign_contract=campaign_contract,
    ))
    action_response: dict | None = None
    narrative_fallback_used = bool((getattr(narrative, 'score_detail', {}) or {}).get('fallback_used'))
    if player_actions and narrative_fallback_used:
        action_response = _action_response_scene(
            player_name=adv_player_name,
            location_name=adv_scene_director_output.location.name or current_location_name or "the current location",
            latest_action=player_actions[-1],
            action_count=len(player_actions),
            approved_context={
                "clue": (adv_content_bundle.get("required_content") or {}).get("first_clue_or_question") or (adv_scene_director_output.player_visible_clues[:1] or [""])[0],
                "object": (adv_content_bundle.get("required_content") or {}).get("approved_object") or "",
                "stakes": (adv_content_bundle.get("required_content") or {}).get("specific_stakes") or adv_scene_director_output.immediate_stakes,
                "npc": (adv_content_bundle.get("required_content") or {}).get("named_npc_or_visible_threat") or adv_scene_director_output.primary_npc.name,
            },
        )
        narrative = narrative_agent.NarrativeResponse(
            narrative=action_response["narrative"],
            prompt=f"What does {adv_player_name} do?",
            tone=style,
            scene_score=85,
            score_passed=True,
            score_detail={"deterministic_action_response": True},
            suggested_actions=action_response["suggested_actions"],
            world_moves=action_response["world_moves"],
        )
        adv_scene_director_output.central_conflict = action_response["objective"]
        adv_scene_director_output.immediate_stakes = action_response["stakes"]
        adv_scene_director_output.player_visible_clues = action_response["clues"]
        adv_director_data = adv_scene_director_output.model_dump()

    quality_score, quality_issues = validate_scene_quality(
        narrative_text=f"{narrative.narrative}\n\n{narrative.prompt}",
        location_name=adv_scene_director_output.location.name,
        npc_name=adv_scene_director_output.primary_npc.name,
        player_name=adv_player_name,
        conflict=adv_scene_director_output.central_conflict,
        campaign_entities=[
            *(n.get("name", "") for n in mem_npc_details if n.get("name")),
            *(loc_item.get("name", "") for loc_item in mem_loc_details if loc_item.get("name")),
            *candidate_threads,
        ],
    )
    contract_validator = validate_campaign_expectations(
        narrative_text=f"{narrative.narrative}\n\n{narrative.prompt}",
        campaign_contract=campaign_contract,
    )
    retry_used = False
    fallback_used = False
    contract_minimum = int((campaign_contract.get("validator_policy") or {}).get("minimum_scene_score") or MINIMUM_SCORE) if campaign_contract else MINIMUM_SCORE
    minimum_score = max(MINIMUM_SCORE, contract_minimum)
    if action_response:
        quality_score = max(quality_score, 85)
        quality_issues = []
        contract_validator = {"score": 100, "failed_expectations": [], "canon_violations": [], "backstory_boundary_violations": [], "agency_issues": [], "tone_issues": [], "recommended_fix": ""}
    if quality_score < minimum_score or contract_validator.get("failed_expectations"):
        retry_used = True
        feedback = build_retry_feedback(
            quality_issues + list(contract_validator.get("failed_expectations", [])),
            quality_score,
            adv_scene_director_output.location.name,
            adv_scene_director_output.primary_npc.name,
            adv_player_name,
        )
        narrative = narrative_agent.generate_narrative(narrative_agent.NarrativeRequest(
            scene=scene_summary,
            player=adv_player_name,
            style=style,
            weather=weather,
            time_of_day=time_of_day,
            scene_director_data=adv_director_data,
            composer_data=adv_composer_data,
            validator_feedback=feedback,
            player_actions=player_actions,
            campaign_contract=campaign_contract,
        ))
        quality_score, quality_issues = validate_scene_quality(
            narrative_text=f"{narrative.narrative}\n\n{narrative.prompt}",
            location_name=adv_scene_director_output.location.name,
            npc_name=adv_scene_director_output.primary_npc.name,
            player_name=adv_player_name,
            conflict=adv_scene_director_output.central_conflict,
        )
        contract_validator = validate_campaign_expectations(
            narrative_text=f"{narrative.narrative}\n\n{narrative.prompt}",
            campaign_contract=campaign_contract,
        )

    if quality_score < minimum_score:
        fallback_used = True
        fallback_text = build_fallback_scene(
            location_name=adv_scene_director_output.location.name or current_location_name or 'the current location',
            npc_name=adv_scene_director_output.primary_npc.name,
            player_name=adv_player_name,
            emotional_state=adv_scene_director_output.primary_npc.current_emotional_state or 'urgent',
            inciting_incident=adv_scene_director_output.inciting_incident or adv_scene_director_output.central_conflict,
            central_conflict=adv_scene_director_output.central_conflict,
            immediate_stakes=adv_scene_director_output.immediate_stakes,
            sensory_detail=(adv_scene_director_output.location.sensory_details[:1] or [''])[0],
            campaign_name=meta.get('name') or session_id,
        )
        narrative = narrative_agent.NarrativeResponse(
            narrative=fallback_text,
            prompt=f"What does {adv_player_name} do?",
            tone=style,
        )

    now = datetime.now(timezone.utc)
    scene_index = f"scene-{uuid.uuid4().hex[:8]}"
    adv_suggested_actions = narrative.suggested_actions or adv_composer_output.suggested_actions or adv_scene_director_output.possible_actions or [
        'Investigate the most immediate clue',
        'Talk to someone nearby',
        'Press on toward the obvious destination',
        'Make a plan',
    ]
    scene_title = (
        (action_response or {}).get("title")
        or getattr(adv_scene_director_output, "scene_title", "")
        or adv_scene_director_output.location.name
        or f"Scene — {now.strftime('%Y-%m-%d %H:%M')} UTC"
    )
    new_scene = {
        'id': scene_index,
        'title': scene_title,
        'image': None,
        'narrative_body': narrative.narrative,
        'player_prompt': narrative.prompt,
        'text': f"{narrative.narrative}\n\n{narrative.prompt}",  # kept for compat
        'choices': [
            {'id': f'action_{i}', 'label': a}
            for i, a in enumerate(adv_suggested_actions[:4])
        ],
        'suggested_actions': adv_suggested_actions[:4],
        'world_moves': (
            narrative.world_moves
            or adv_composer_output.world_moves
            or adv_scene_director_output.world_moves
            or []
        )[:4],
        'active_player': adv_player_name,
        'location': adv_scene_director_output.location.name or current_location_name,
        'weather': weather,
        'time_of_day': time_of_day,
        'time_block': world_state.get('time_block'),
        'campaign_day': world_state.get('campaign_day'),
        'immediate_stakes': adv_scene_director_output.immediate_stakes or '',
        'active_threads': adv_scene_director_output.threads_to_advance or [],
        'visible_clues': adv_scene_director_output.player_visible_clues[:4] or [],
        'current_objective': adv_scene_director_output.central_conflict[:120] if adv_scene_director_output.central_conflict else '',
        'scene_templates': selected_templates,
        'situation_type': adv_situation_type,
        'situation_classification': adv_situation,
        'content_bundle': adv_content_bundle,
        'ui_payload': adv_content_bundle.get('ui_payload', {}),
        'scene_director_data': adv_director_data,
        'composer_data': adv_composer_data,
        'simulation_delta': simulation_delta,
        'campaign_scale_profile': campaign_scale_profile,
        'story_shape_profile': story_shape_profile,
        'arc_plan': adv_arc_plan,
        'campaign_storyboard': adv_campaign_storyboard,
        'session_storyboard': adv_session_storyboard,
        'player_intent': player_intent,
        'scene_beat_plan': selected_scene_beat,
        'selected_scene_beat': selected_scene_beat,
        'beat_selection_reason': selected_scene_beat.get("selection_reason", ""),
        'repetition_warnings': selected_scene_beat.get("repetition_warnings", []),
        'thread_budget': {
            'max_open_threads': campaign_scale_profile.get('max_open_threads'),
            'active_thread_count': len(candidate_threads),
            'threads_to_retire': adv_arc_plan.get('threads_to_retire', []),
        },
        'campaign_contract': {
            'contract_version': campaign_contract.get('contract_version'),
            'canon_policy': campaign_contract.get('canon_policy', {}),
            'ui_policy': campaign_contract.get('ui_policy', {}),
            'validator_policy': campaign_contract.get('validator_policy', {}),
        } if campaign_contract else {},
        'ui_policy': campaign_contract.get('ui_policy', {}) if campaign_contract else {},
    }

    recent_scene_history = [previous_scene] if previous_scene else []
    recent_motifs = list((previous_scene.get("visible_clues") or [])[:5]) if previous_scene else []
    adv_scene_qa_initial = run_scene_qa(
        scene=new_scene,
        campaign_contract=campaign_contract,
        campaign_scale_profile=campaign_scale_profile,
        story_shape_profile=story_shape_profile,
        scene_beat_plan=selected_scene_beat,
        content_bundle=adv_content_bundle,
        narrative_output={"narrative": narrative.narrative, "prompt": narrative.prompt},
        player_intent=player_intent,
        recent_player_actions=player_actions,
        current_scene=previous_scene,
        recent_scene_history=recent_scene_history,
        recent_motifs=recent_motifs,
        memory_delta={},
        ui_payload=new_scene.get("ui_payload") or {},
    )
    new_scene = apply_targeted_scene_repairs(
        new_scene,
        adv_scene_qa_initial,
        player_name=adv_player_name,
        recent_player_actions=player_actions,
    )
    adv_scene_qa_after_repair = run_scene_qa(
        scene=new_scene,
        campaign_contract=campaign_contract,
        campaign_scale_profile=campaign_scale_profile,
        story_shape_profile=story_shape_profile,
        scene_beat_plan=selected_scene_beat,
        content_bundle=adv_content_bundle,
        player_intent=player_intent,
        recent_player_actions=player_actions,
        current_scene=previous_scene,
        recent_scene_history=recent_scene_history,
        recent_motifs=recent_motifs,
        memory_delta={},
        ui_payload=new_scene.get("ui_payload") or {},
    )
    new_scene["scene_qa"] = adv_scene_qa_after_repair
    new_scene["quality_debug"] = {
        "scene_qa_initial": adv_scene_qa_initial,
        "scene_qa_final": adv_scene_qa_after_repair,
        "truth_table": adv_scene_qa_after_repair.get("truth_table", {}),
        "opening_shape": adv_scene_qa_after_repair.get("opening_shape", {}),
        "gm_move": adv_scene_qa_after_repair.get("gm_move", ""),
        "scene_purpose": adv_scene_qa_after_repair.get("scene_purpose", {}),
        "tension_curve": adv_scene_qa_after_repair.get("tension_curve", {}),
        "npc_scene_roles": adv_scene_qa_after_repair.get("npc_scene_roles", []),
        "detail_budget": adv_scene_qa_after_repair.get("detail_budget", {}),
        "campaign_palette": adv_scene_qa_after_repair.get("campaign_palette", {}),
        "memory_delta_consistency": adv_scene_qa_after_repair.get("memory_delta_consistency", {}),
        "ui_payload_validation": adv_scene_qa_after_repair.get("ui_payload_validation", {}),
        "regression_tags": adv_scene_qa_after_repair.get("regression_tags", []),
    }

    post_scene_dice_rolls: list[dict] = []
    scene_analysis_consistency: dict = {}
    try:
        post_cues = await scene_agent.analyze_scene(scene_agent.SceneAnalysisRequest(
            scene=new_scene['text'],
            actions=[c.get('label', '') for c in new_scene.get('choices', []) if isinstance(c, dict)],
            session_id=session_id,
        ))
        post_scene_dice_rolls = [r.model_dump() for r in post_cues.dice_rolls]
        scene_analysis_consistency = scene_agent.check_roll_consistency(adv_content_bundle, post_cues)
    except Exception:
        pass
    if bundle_dice_rolls:
        post_scene_dice_rolls = bundle_dice_rolls
    new_scene['scene_analysis_consistency'] = scene_analysis_consistency

    # --- Visual Director: determine atmosphere + image refresh decision ---
    image_url = None
    prev_vs = load_visual_state(session_id)

    # Extract location hint from previous scene.json if available
    adv_loc_name = adv_scene_director_output.location.name or ""
    adv_loc_type = adv_scene_director_output.location.type or ""
    try:
        prev_scene_raw = folder / 'scene.json'
        if prev_scene_raw.exists():
            prev_scene_data = json.loads(prev_scene_raw.read_text())
            prev_vs_data = prev_scene_data.get('visual_state') or {}
            adv_loc_name = adv_loc_name or prev_vs_data.get('location_name', '')
            adv_loc_type = adv_loc_type or prev_vs_data.get('location_type', '')
    except Exception:
        pass

    try:
        adv_vs, adv_img_prompt, do_refresh = run_visual_pipeline(
            session_id=session_id,
            scene_text=new_scene['text'],
            location_name=adv_loc_name,
            location_type=adv_loc_type,
            weather=weather,
            time_of_day=time_of_day,
            previous_visual_state=prev_vs,
        )
        save_visual_state(session_id, adv_vs)
        new_scene['visual_state'] = adv_vs.model_dump()
    except Exception:
        do_refresh = True
        adv_img_prompt = narrative.narrative[:200]

    if do_refresh:
        try:
            img = image_agent.generate_image(image_agent.ImageRequest(
                prompt=adv_img_prompt,
                style='realistic',
            ))
            image_url = img.image_url
            new_scene['image'] = image_url
        except Exception:
            pass
    elif prev_vs:
        # Reuse prior image — copy from previous scene.json if available
        try:
            prev_scene_raw2 = folder / 'scene.json'
            if prev_scene_raw2.exists():
                prev_img = json.loads(prev_scene_raw2.read_text()).get('image')
                if prev_img:
                    image_url = prev_img
                    new_scene['image'] = prev_img
        except Exception:
            pass

    new_scene = simulation_agent.normalize_scene_presentation(new_scene, world_state, simulation_delta)

    # --- Memory Extractor ---
    memory_delta = extract_memory(
        scene=new_scene,
        world_state=world_state,
        simulation_delta=simulation_delta,
        content_bundle=adv_content_bundle or None,
        campaign_contract=campaign_contract,
        previous_scene=previous_scene,
    )

    # --- Canon Manager ---
    try:
        canon_index = load_canon_index(folder)
        canon_changes = apply_memory_delta(
            canon_index,
            memory_delta,
            scene_id=scene_index,
            campaign_contract=campaign_contract,
        )
        canon_validation = validate_canon(
            new_scene.get("narrative_body") or new_scene.get("text") or "",
            canon_index,
            campaign_contract,
        )
        save_canon_index(folder, canon_index)
    except Exception:
        canon_changes = {}
        canon_validation = {"valid": True, "score": 100, "issues": []}

    # --- Full UI Payload ---
    _adv_debug_mode = bool((payload.__dict__ if hasattr(payload, '__dict__') else {}).get("debug") or False)
    try:
        full_ui_payload = build_full_ui_payload(
            scene=new_scene,
            content_bundle=adv_content_bundle or {},
            memory_delta=memory_delta,
            world_state=world_state,
            simulation_delta=simulation_delta,
            campaign_contract=campaign_contract,
            player_stats=None,
            turn_state={},
            dice_rolls=post_scene_dice_rolls,
            debug_mode=False,
        )
        new_scene["full_ui_payload"] = full_ui_payload
        new_scene["canon_validation"] = canon_validation
    except Exception:
        full_ui_payload = {}

    adv_scene_qa_final = run_scene_qa(
        scene=new_scene,
        campaign_contract=campaign_contract,
        campaign_scale_profile=campaign_scale_profile,
        story_shape_profile=story_shape_profile,
        scene_beat_plan=selected_scene_beat,
        content_bundle=adv_content_bundle,
        player_intent=player_intent,
        recent_player_actions=player_actions,
        current_scene=previous_scene,
        recent_scene_history=recent_scene_history,
        recent_motifs=recent_motifs,
        memory_delta=memory_delta,
        ui_payload=full_ui_payload,
        dice_rolls=post_scene_dice_rolls,
    )
    new_scene["scene_qa"] = adv_scene_qa_final
    new_scene["quality_debug"] = {
        **(new_scene.get("quality_debug") or {}),
        "scene_qa_final": adv_scene_qa_final,
        "truth_table": adv_scene_qa_final.get("truth_table", {}),
        "opening_shape": adv_scene_qa_final.get("opening_shape", {}),
        "gm_move": adv_scene_qa_final.get("gm_move", ""),
        "scene_purpose": adv_scene_qa_final.get("scene_purpose", {}),
        "tension_curve": adv_scene_qa_final.get("tension_curve", {}),
        "npc_scene_roles": adv_scene_qa_final.get("npc_scene_roles", []),
        "detail_budget": adv_scene_qa_final.get("detail_budget", {}),
        "campaign_palette": adv_scene_qa_final.get("campaign_palette", {}),
        "memory_delta_consistency": adv_scene_qa_final.get("memory_delta_consistency", {}),
        "ui_payload_validation": adv_scene_qa_final.get("ui_payload_validation", {}),
        "regression_tags": adv_scene_qa_final.get("regression_tags", []),
    }

    new_scene.update(simulation_agent.build_structured_scene_fields(
        new_scene,
        world_state,
        simulation_delta,
        memory_delta,
        selected_templates,
        dice_rolls=post_scene_dice_rolls,
    ))
    simulation_agent.atomic_write_json(folder / 'world_state.json', world_state)
    simulation_agent.seed_persistent_npcs(folder, new_scene)
    simulation_agent.seed_location_state(folder, new_scene, world_state)
    simulation_agent.atomic_write_json(folder / 'last_simulation_delta.json', simulation_delta)
    simulation_agent.atomic_write_json(folder / 'last_memory_delta.json', memory_delta)
    simulation_agent.append_canon_memory(folder, scene_index, memory_delta)
    simulation_agent.atomic_write_json(folder / 'scene.json', new_scene)

    cur = _load_story_entries(folder)
    last_story_ts = _story_last_timestamp(cur)
    cur.extend(_story_action_entries_since(recent_messages, last_story_ts))
    cur.append({
        'type': 'narration',
        'ts': now.isoformat(),
        'text': new_scene['text'],
        'scene_id': scene_index,
        'campaign_day': new_scene.get('campaign_day'),
        'time_block': new_scene.get('time_block'),
    })
    cur = sorted(cur, key=lambda e: str(e.get('ts') or ''))
    _write_story_entries(folder, cur)

    # Reset player-ready state for the next round
    ready_path = folder / 'ready.json'
    simulation_agent.atomic_write_json(ready_path, {})

    # --- Step 5: Broadcast the new scene ---
    await broadcaster.broadcast_json(session_id, {
        'type': 'narrative.scene',
        'session_id': session_id,
        'scene': new_scene,
    })

    adv_context_debug = adv_context_packet.debug_payload() if adv_context_packet else None

    # --- Story Validator + State Update (advance scene) ---
    adv_story_debug: dict | None = None
    if adv_story_state is not None and adv_director_output is not None:
        try:
            adv_story_result = validate_story_structure(
                scene_text=new_scene.get('text', ''),
                director=adv_director_output,
                state=adv_story_state,
                scene_type=adv_director_output.recommended_scene_type,
            )
            adv_story_state = update_state_after_scene(
                state=adv_story_state,
                scene_type=adv_director_output.recommended_scene_type,
                scene_purpose=adv_director_output.scene_purpose,
                scene_id=new_scene.get('id', session_id),
                location=new_scene.get('title', ''),
                npcs_featured=[],
                threads_advanced=adv_director_output.threads_to_advance,
                threads_resolved=adv_director_output.threads_to_resolve,
                emotional_target=adv_director_output.emotional_target,
                director_tension_target=adv_director_output.target_tension,
                story_score=adv_story_result.score,
                director_recommendation_followed=True,
            )
            save_story_state(adv_story_state)
            adv_story_debug = {
                'director': adv_director_output.model_dump(),
                'story_state': story_dashboard_payload(adv_story_state),
                'story_validator': adv_story_result.to_dict(),
            }
        except Exception:
            pass

    generation_lock = simulation_agent.complete_scene_lock(folder, generation_lock, "complete")

    simulation_debug = {
        'generation': generation_lock,
        'time_resolver': time_result,
        'world_tick_results': {
            'policies': tick_policies,
            'world_state': world_state,
        },
        'simulation_delta': simulation_delta,
        'selected_template': selected_templates,
        'narrative_director': director_guidance,
        'scene_director': adv_director_data,
        'narrative_composer': adv_composer_data,
        'narrative_writer': {
            'narrative': narrative.narrative,
            'prompt': narrative.prompt,
            'scene_score': narrative.scene_score,
            'score_passed': narrative.score_passed,
        },
        'scene_validator': {
            'score': quality_score,
            'issues': quality_issues,
            'retry_used': retry_used,
            'fallback_used': fallback_used,
            'contract_validator': contract_validator,
        },
        'campaign_contract': {
            'canon_policy': campaign_contract.get('canon_policy', {}),
            'ai_creativity_policy': campaign_contract.get('ai_creativity_policy', {}),
            'backstory_policy': campaign_contract.get('backstory_policy', {}),
            'ui_policy': campaign_contract.get('ui_policy', {}),
        } if campaign_contract else {},
        'backstory_profiles': backstory_profiles,
        'backstory_hooks': backstory_hooks,
        'session_zero': session_zero_summary,
        'memory_delta': memory_delta,
        'situation_type': adv_situation_type,
        'situation_classification': adv_situation,
        'content_bundle': adv_content_bundle,
        'content_bundle_validation': adv_content_bundle.get('validation_result', {}),
        'campaign_scale_profile': campaign_scale_profile,
        'story_shape_profile': story_shape_profile,
        'arc_plan': adv_arc_plan,
        'campaign_storyboard': adv_campaign_storyboard,
        'session_storyboard': adv_session_storyboard,
        'player_intent': player_intent,
        'selected_scene_beat': selected_scene_beat,
        'story_model_stage': story_shape_profile.get('current_arc_stage', ''),
        'thread_budget': {
            'max_open_threads': campaign_scale_profile.get('max_open_threads'),
            'active_thread_count': len(candidate_threads),
            'threads_to_retire': adv_arc_plan.get('threads_to_retire', []),
        },
        'repetition_warnings': selected_scene_beat.get("repetition_warnings", []),
        'scene_analysis_consistency': scene_analysis_consistency,
        'scene_qa': new_scene.get('scene_qa') or {},
        'quality_debug': new_scene.get('quality_debug') or {},
        'canon_changes': canon_changes,
        'canon_validation': canon_validation,
        'ui_payload': full_ui_payload,
        'context_retrieved': adv_context_debug,
    }

    return {
        'ok': True,
        'generation': generation_lock,
        'scene': new_scene,
        'dice_rolls': dice_rolls,
        'pre_scene_dice_rolls': dice_rolls,
        'post_scene_dice_rolls': post_scene_dice_rolls,
        'image_url': image_url,
        'ui_payload': full_ui_payload,
        'situation_type': adv_situation_type,
        'situation_classification': adv_situation,
        'canon_validation': canon_validation,
        'context_debug': adv_context_debug,
        'story_debug': adv_story_debug,
        'simulation_debug': simulation_debug if payload.developer_mode else {
            'generation': generation_lock,
            'time_resolver': time_result,
            'simulation_delta': simulation_delta,
            'selected_template': selected_templates,
            'scene_validator': simulation_debug['scene_validator'],
            'memory_delta': memory_delta,
        },
    }


# ---------------------------------------------------------------------------
# Entity associations + in-chat hyperlink lookup
# ---------------------------------------------------------------------------

def _associations_path(session_id: str) -> Path:
    return BASE / session_id / 'associations.json'


def _load_associations(session_id: str) -> list[dict]:
    path = _associations_path(session_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_associations(session_id: str, associations: list[dict]) -> None:
    path = _associations_path(session_id)
    path.write_text(json.dumps(associations, indent=2))


@router.post('/{session_id}/entities/associate', status_code=201)
def add_association(session_id: str, payload: EntityAssociation, current_user=Depends(get_current_user)):
    """Record a link between two entities (NPC ↔ Location, NPC ↔ Quest, etc.).

    Associations are stored in ``associations.json`` inside the session folder.
    They power in-chat hyperlinks: when a player clicks an entity name in the
    chat transcript the UI resolves it to the player-visible card via
    ``GET /sessions/{id}/entity/{name}``.

    Only session members may call this endpoint.
    """
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err
    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    existing = _load_associations(session_id)
    # Upsert: replace any existing link that shares the same ordered (entity_a, entity_b) pair.
    # Associations are directional by default — "NPC guards Location" and "Location is guarded
    # by NPC" are treated as distinct entries.  If you want to replace in both directions,
    # submit a second association with the entities swapped.
    new_entry = payload.model_dump()
    updated = [
        e for e in existing
        if not (
            e.get('entity_a') == payload.entity_a and e.get('entity_b') == payload.entity_b
        )
    ]
    updated.append(new_entry)
    _save_associations(session_id, updated)
    return {'ok': True, 'association': new_entry}


@router.get('/{session_id}/entities/associations')
def list_associations(session_id: str, current_user=Depends(get_current_user)):
    """Return all entity associations for the session.  All session members may read."""
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err
    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')
    return {'session_id': session_id, 'associations': _load_associations(session_id)}


@router.get('/{session_id}/entity/{entity_name}', response_model=PlayerEntityCard)
def get_entity_card(session_id: str, entity_name: str, current_user=Depends(get_current_user)):
    """Return the player-visible card for a named entity (NPC, location, or quest).

    This endpoint powers in-chat hyperlinks.  When a player clicks an entity
    name in the chat transcript the frontend calls this endpoint and displays
    the returned card in a pop-up.

    The card contains **only** information the players have gathered:
    - For NPCs: appearance, observable attitude, dialogue/relationships —
      never stats, motivations, or secrets.
    - For locations: shops, contacts, explored layout — never hidden areas or traps.
    - For quests: current objective, completed stages — never hidden complications.

    Returns ``404`` if no player-visible information exists for the name yet.
    """
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err
    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    name_lower = entity_name.strip().lower()

    # Load associations once; reused by all branches below.
    assoc = _load_associations(session_id)

    def _known_for(name_lc: str) -> list[str]:
        return [
            f"{a['entity_b']} ({a.get('relationship', '')})"
            for a in assoc
            if (a.get('entity_a') or '').strip().lower() == name_lc
        ] + [
            f"{a['entity_a']} ({a.get('relationship', '')})"
            for a in assoc
            if (a.get('entity_b') or '').strip().lower() == name_lc
        ]

    # --- 1. Try the session npcs.json (player-visible NPC profiles) ---
    npcs_path = folder / 'npcs.json'
    if npcs_path.exists():
        try:
            npcs = json.loads(npcs_path.read_text()) or []
            for npc in npcs:
                if (npc.get('name') or '').strip().lower() == name_lower:
                    # Canonical appearance lives at the top level (written by the updated
                    # manage_npc endpoint).  Fall back to traits['appearance'] for profiles
                    # written by older code.
                    appearance = npc.get('appearance') or ''
                    if not appearance:
                        traits = npc.get('traits') or {}
                        appearance = traits.get('appearance', '') if isinstance(traits, dict) else ''
                    return PlayerEntityCard(
                        name=npc.get('name', entity_name),
                        entity_type='npc',
                        summary=appearance or f"You have encountered {npc.get('name', entity_name)}.",
                        appearance=appearance,
                        relationship_notes=npc.get('personality', '') or ', '.join(npc.get('quirks') or []),
                        known_associations=_known_for(name_lower),
                    )
        except Exception:
            pass

    # --- 2. Try player-visible documents (player_npc, player_location, player_quest_log) ---
    docs = _doc_store.list_documents(session_id)
    player_cats = {'player_npc', 'player_location', 'player_quest_log'}
    for doc_meta in docs:
        if doc_meta.visibility == 'hidden':
            continue
        if doc_meta.category not in player_cats:
            continue
        if (doc_meta.name or '').strip().lower() != name_lower:
            continue
        record = _doc_store.read_document(session_id, doc_meta.id)
        if not record:
            continue
        _, content = record
        entity_type_map = {
            'player_npc': 'npc',
            'player_location': 'location',
            'player_quest_log': 'quest',
        }
        return PlayerEntityCard(
            name=doc_meta.name,
            entity_type=entity_type_map.get(doc_meta.category, 'npc'),  # type: ignore[arg-type]
            summary=content[:500] if content else '',
            known_associations=_known_for(name_lower),
        )

    raise HTTPException(status_code=404, detail=f"No player-visible information found for '{entity_name}'")
