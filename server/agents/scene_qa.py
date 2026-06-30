"""Deterministic scene QA layer.

This module reviews completed scenes as a critic rather than a generator.  It
keeps the quality checks cheap, testable, and independent from LLM behavior.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parents[1] / "sessions"
OPENING_SHAPES_PATH = BASE / "opening_shapes.json"

GENERIC_TERMS = (
    "something", "someone", "danger", "threat", "forces", "situation",
    "disturbance", "mysterious", "urgent", "not saying everything",
    "needs help", "things will get worse", "the region", "a figure",
    "a stranger", "hidden forces", "come quickly", "you need to see this",
)

REPEATED_OPENING_PATTERNS = (
    "sealed packet", "dispatch tube", "warning note", "messenger arrives too late",
    "arrives visibly shaken", "arrives too late", "asks for help",
    "not saying everything", "something went wrong", "sealed message",
)

GM_MOVES = (
    "reveal_unwelcome_truth", "show_approaching_threat", "offer_opportunity_with_cost",
    "put_someone_in_a_spot", "use_up_resources", "turn_move_back_on_them",
    "separate_them", "advance_faction_clock", "show_consequence",
    "introduce_complication", "offer_recovery", "spotlight_backstory",
    "present_moral_choice", "reveal_clue", "start_combat", "escalate_tension",
)

PRIMARY_PURPOSES = (
    "establish_location", "introduce_threat", "reveal_clue", "force_decision",
    "resolve_action", "advance_clock", "spotlight_character", "offer_recovery",
    "start_combat", "complicate_plan", "show_consequence", "deepen_relationship",
    "introduce_npc", "transition_location", "resolve_thread", "seed_thread",
)


class SceneTruthTable(BaseModel):
    approved_location: str = ""
    approved_primary_npc: str = ""
    approved_visible_threat: str = ""
    approved_clue: str = ""
    approved_object: str = ""
    approved_stakes: str = ""
    approved_time_pressure: str = ""
    approved_scene_question: str = ""
    approved_possible_actions: list[str] = Field(default_factory=list)
    forbidden_reveals: list[str] = Field(default_factory=list)
    forbidden_motifs: list[str] = Field(default_factory=list)


class SceneQAResult(BaseModel):
    pass_: bool = Field(alias="pass")
    quality_score: int = 0
    specificity_score: int = 0
    freshness_score: int = 0
    continuity_score: int = 0
    agency_score: int = 0
    playability_score: int = 0
    campaign_fit_score: int = 0
    memorability_score: int = 0
    biggest_issue: str = ""
    required_revision: str = ""
    repair_targets: list[str] = Field(default_factory=list)
    truth_table: dict[str, Any] = Field(default_factory=dict)
    opening_shape: dict[str, Any] = Field(default_factory=dict)
    gm_move: str = ""
    scene_purpose: dict[str, str] = Field(default_factory=dict)
    tension_curve: dict[str, Any] = Field(default_factory=dict)
    npc_scene_roles: list[dict[str, Any]] = Field(default_factory=list)
    detail_budget: dict[str, Any] = Field(default_factory=dict)
    campaign_palette: dict[str, Any] = Field(default_factory=dict)
    memory_delta_consistency: dict[str, Any] = Field(default_factory=dict)
    ui_payload_validation: dict[str, Any] = Field(default_factory=dict)
    freshness_failures: list[str] = Field(default_factory=list)
    continuity_failures: list[str] = Field(default_factory=list)
    specificity_failures: list[str] = Field(default_factory=list)
    regression_tags: list[str] = Field(default_factory=list)


def _text(scene: dict[str, Any], narrative_output: dict[str, Any] | None = None) -> str:
    if narrative_output:
        return " ".join([
            str(narrative_output.get("narrative") or ""),
            str(narrative_output.get("prompt") or ""),
        ]).strip()
    return str(scene.get("text") or " ".join([
        str(scene.get("narrative_body") or ""),
        str(scene.get("player_prompt") or ""),
    ])).strip()


def _required(content_bundle: dict[str, Any] | None) -> dict[str, Any]:
    return (content_bundle or {}).get("required_content") or {}


def _first_nonempty(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            value = next((str(v) for v in value if str(v or "").strip()), "")
        if str(value or "").strip():
            return str(value).strip()
    return ""


def build_scene_truth_table(
    *,
    scene: dict[str, Any] | None = None,
    content_bundle: dict[str, Any] | None = None,
    scene_director_data: dict[str, Any] | None = None,
    scene_beat_plan: dict[str, Any] | None = None,
) -> SceneTruthTable:
    scene = scene or {}
    sd = scene_director_data or scene.get("scene_director_data") or {}
    rc = _required(content_bundle or scene.get("content_bundle"))
    loc = sd.get("location") or {}
    npc = sd.get("primary_npc") or {}
    clues = sd.get("player_visible_clues") or []
    actions = sd.get("possible_actions") or rc.get("possible_actions") or []
    return SceneTruthTable(
        approved_location=_first_nonempty(rc.get("starting_location"), loc.get("name"), scene.get("location")),
        approved_primary_npc=_first_nonempty(rc.get("named_npc_or_visible_threat"), npc.get("name")),
        approved_visible_threat=_first_nonempty(rc.get("visible_threat"), sd.get("central_conflict")),
        approved_clue=_first_nonempty(rc.get("first_clue_or_question"), clues),
        approved_object=_extract_object(rc, sd),
        approved_stakes=_first_nonempty(rc.get("specific_stakes"), sd.get("immediate_stakes"), scene.get("immediate_stakes")),
        approved_time_pressure=_first_nonempty(rc.get("time_pressure"), scene_beat_plan.get("concrete_stakes") if scene_beat_plan else ""),
        approved_scene_question=_first_nonempty(rc.get("first_clue_or_question"), scene_beat_plan.get("scene_purpose") if scene_beat_plan else ""),
        approved_possible_actions=[str(a) for a in actions if str(a or "").strip()][:4],
        forbidden_reveals=[str(x) for x in (scene_beat_plan or {}).get("must_not_include", []) if x],
        forbidden_motifs=[str(x) for x in rc.get("forbidden_motifs", []) if x],
    )


def _extract_object(rc: dict[str, Any], sd: dict[str, Any]) -> str:
    hay = " ".join(str(v) for v in [
        rc.get("first_clue_or_question"), rc.get("inciting_event"),
        rc.get("location_identity"), rc.get("player_decision"),
        sd.get("inciting_incident"), " ".join(sd.get("player_visible_clues") or []),
    ])
    lower = hay.lower()
    for phrase in ("blackened silver charms", "blackened charms", "frozen tracks", "water seal", "stolen ledger", "forbidden bell"):
        if phrase in lower:
            return phrase
    m = re.search(r"\b([a-z]+(?:ed)?\s+(?:charm|symbol|seal|ledger|map|key|blade|bell|mask|coin|flask|note|track|rune|sigil)s?)\b", hay, re.I)
    return m.group(1) if m else ""


def score_specificity(text: str, truth_table: SceneTruthTable | None = None, campaign_palette: dict[str, Any] | None = None) -> tuple[int, list[str]]:
    lower = text.lower()
    truth = truth_table or SceneTruthTable()
    failures: list[str] = []
    score = 20
    positives = {
        "named location": truth.approved_location and truth.approved_location.lower() in lower,
        "named npc": truth.approved_primary_npc and truth.approved_primary_npc.split("(")[0].strip().lower() in lower,
        "specific object": truth.approved_object and truth.approved_object.lower() in lower,
        "specific clue": truth.approved_clue and _keywords_present(truth.approved_clue, lower),
        "specific consequence": bool(re.search(r"\b(if|before|unless|by dusk|by dawn|until|within|loses?|costs?|burns?|vanishes?)\b", lower)),
        "specific decision": bool(re.search(r"\b(inspect|question|follow|protect|confront|aid|choose|search|press|wait|leave)\b", lower)),
        "sensory detail": bool(re.search(r"\b(cold|smoke|iron|snow|rain|blood|ash|mud|salt|glass|wax|bell|pine|dust|wind|stale|bright|blackened)\b", lower)),
    }
    palette = campaign_palette or {}
    palette_terms = [
        str(x).lower()
        for key in ("recurring_symbols", "sensory_palette", "threat_language", "preferred_concrete_nouns")
        for x in (palette.get(key) or [])
        if str(x).strip()
    ]
    positives["campaign motif"] = any(term in lower for term in palette_terms)
    for label, passed in positives.items():
        if passed:
            score += 8
        else:
            failures.append(f"Missing {label}")
    generic_hits = [term for term in GENERIC_TERMS if term in lower]
    score -= min(35, len(generic_hits) * 5)
    if generic_hits:
        failures.append("Generic language: " + ", ".join(generic_hits[:5]))
    return max(0, min(100, score)), failures


def _keywords_present(expected: str, lower_text: str) -> bool:
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", expected) if w.lower() not in {"what", "where", "when", "before", "after", "with", "from", "this", "that"}]
    if not words:
        return False
    return sum(1 for w in words if w in lower_text) >= max(1, min(2, len(words)))


def classify_opening_shape(scene: dict[str, Any], content_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    rc = _required(content_bundle or scene.get("content_bundle"))
    text = _text(scene)
    lower = text.lower()
    sd = scene.get("scene_director_data") or {}
    loc = sd.get("location") or {}
    npc = sd.get("primary_npc") or {}
    inciting = str(rc.get("inciting_event") or sd.get("inciting_incident") or "")
    obj = _extract_object(rc, sd)
    event_type = _classify_event_type(inciting or text)
    object_type = _classify_object_type(text if any(pattern in lower for pattern in REPEATED_OPENING_PATTERNS) else (obj or text))
    npc_role = str(rc.get("named_npc_or_visible_threat") or npc.get("role") or npc.get("name") or "")
    if "arrives" in lower and object_type != "none":
        opening_shape = "named_npc_arrives_with_object_and_warning"
    elif event_type == "witness_refuses":
        opening_shape = f"witness_withheld_information:{object_type}:{_classify_stakes_type(str(rc.get('specific_stakes') or scene.get('immediate_stakes') or text))}"
    elif "attack" in lower or "blood" in lower:
        opening_shape = f"visible_harm_with_clue:{object_type}:{_classify_stakes_type(str(rc.get('specific_stakes') or scene.get('immediate_stakes') or text))}"
    elif object_type != "none":
        opening_shape = f"object_clue_discovery:{event_type}:{object_type}:{_classify_stakes_type(str(rc.get('specific_stakes') or scene.get('immediate_stakes') or text))}"
    else:
        opening_shape = f"{event_type}_at_location:{_classify_stakes_type(str(rc.get('specific_stakes') or scene.get('immediate_stakes') or text))}"
    return {
        "campaign_id": "",
        "opening_shape": opening_shape,
        "location_type": str(rc.get("location_type") or loc.get("type") or scene.get("location") or ""),
        "inciting_event_type": event_type,
        "npc_role": npc_role,
        "object_type": object_type,
        "stakes_type": _classify_stakes_type(str(rc.get("specific_stakes") or scene.get("immediate_stakes") or text)),
        "opening_question_type": _classify_question_type(str(rc.get("first_clue_or_question") or "")),
        "motifs_used": _motifs_from_text(text),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _classify_event_type(text: str) -> str:
    lower = text.lower()
    if "messenger" in lower or "arrives too late" in lower or "dispatch" in lower:
        return "late_message"
    if "collapses" in lower or "blood" in lower or "wounded" in lower:
        return "injured_witness"
    if "refuses" in lower or "silent" in lower:
        return "witness_refuses"
    if "vanish" in lower or "missing" in lower:
        return "disappearance"
    if "attack" in lower or "ambush" in lower:
        return "attack_aftermath"
    if "fails" in lower or "breaks" in lower or "blacken" in lower:
        return "failed_protection"
    return "local_disruption"


def _classify_object_type(text: str) -> str:
    lower = text.lower()
    for label, terms in {
        "sealed_message": ("sealed packet", "dispatch tube", "warning note", "letter", "message"),
        "symbolic_token": ("symbol", "sigil", "rune", "charm", "coin"),
        "trail_clue": ("tracks", "footprints", "blood trail", "ash trail"),
        "damaged_notice": ("notice", "poster", "ledger", "map"),
    }.items():
        if any(term in lower for term in terms):
            return label
    return "none"


def _classify_stakes_type(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ("road", "trade", "settlement", "village")):
        return "community_loss"
    if any(w in lower for w in ("evidence", "clue", "witness", "lead")):
        return "evidence_loss"
    if any(w in lower for w in ("clock", "dusk", "dawn", "hour", "day")):
        return "time_pressure"
    if any(w in lower for w in ("faction", "war", "throne", "court")):
        return "political_escalation"
    return "abstract_urgency"


def _classify_question_type(text: str) -> str:
    lower = text.lower()
    if "why" in lower:
        return "cause"
    if "who" in lower:
        return "culprit"
    if "where" in lower:
        return "location"
    if "how" in lower:
        return "method"
    return "decision"


def _motifs_from_text(text: str) -> list[str]:
    motifs = []
    lower = text.lower()
    for term in ("blackened silver", "sealed packet", "late messenger", "dispatch tube", "warning note", "frozen", "rain-dark", "crossroads", "outer court", "tavern", "inn"):
        if term in lower:
            motifs.append(term)
    return motifs


def load_recent_opening_shapes(limit: int = 50) -> list[dict[str, Any]]:
    try:
        data = json.loads(OPENING_SHAPES_PATH.read_text())
        if isinstance(data, list):
            return data[-limit:]
    except Exception:
        pass
    return []


def record_opening_shape(campaign_id: str, shape: dict[str, Any]) -> None:
    if not campaign_id:
        return
    BASE.mkdir(exist_ok=True)
    shapes = load_recent_opening_shapes(limit=200)
    entry = {**shape, "campaign_id": str(campaign_id), "created_at": datetime.now(timezone.utc).isoformat()}
    shapes.append(entry)
    OPENING_SHAPES_PATH.write_text(json.dumps(shapes[-200:], indent=2))


def validate_freshness(
    *,
    new_scene: dict[str, Any],
    content_bundle: dict[str, Any] | None = None,
    recent_scene_history: list[dict[str, Any]] | None = None,
    recent_opening_shapes: list[dict[str, Any]] | None = None,
    recent_motifs: list[str] | None = None,
    campaign_contract: dict[str, Any] | None = None,
) -> tuple[int, list[str], dict[str, Any]]:
    shape = classify_opening_shape(new_scene, content_bundle)
    failures: list[str] = []
    score = 100
    recent_shapes = recent_opening_shapes if recent_opening_shapes is not None else load_recent_opening_shapes()
    same_shape = [s for s in recent_shapes if s.get("opening_shape") == shape.get("opening_shape")]
    if same_shape:
        score -= 30
        failures.append(f"Opening shape recently used: {shape.get('opening_shape')}")
    for key in ("location_type", "inciting_event_type", "npc_role", "object_type", "stakes_type"):
        value = str(shape.get(key) or "").lower()
        if value and any(str(s.get(key) or "").lower() == value for s in recent_shapes[-10:]):
            score -= 8
            failures.append(f"Repeated {key}: {value}")
    lower = _text(new_scene).lower()
    if ("tavern" in lower or " inn " in f" {lower} ") and "tavern" not in str(campaign_contract or {}).lower():
        score -= 35
        failures.append("Default tavern/inn appeared without campaign request")
    if any(pattern in lower for pattern in REPEATED_OPENING_PATTERNS):
        score -= 25
        failures.append("Repeated messenger/message opening pattern")
    motifs = set(recent_motifs or [])
    overlap = motifs & set(shape.get("motifs_used") or [])
    if overlap:
        score -= min(20, len(overlap) * 8)
        failures.append("Recent motifs repeated: " + ", ".join(sorted(overlap)))
    return max(0, min(100, score)), failures, shape


def validate_truth_table(text: str, truth: SceneTruthTable) -> tuple[int, list[str], list[str]]:
    lower = text.lower()
    failures: list[str] = []
    repairs: list[str] = []
    score = 100
    if truth.approved_location and truth.approved_location.lower() not in lower:
        failures.append("Approved location missing")
        repairs.append("location_identity")
        score -= 25
    npc_name = truth.approved_primary_npc.split("(")[0].strip()
    if npc_name and npc_name.lower() not in lower:
        failures.append("Approved NPC/threat missing")
        repairs.append("npc_intro")
        score -= 20
    if truth.approved_clue and not _keywords_present(truth.approved_clue, lower):
        failures.append("Approved clue/question missing")
        repairs.append("clue_presentation")
        score -= 20
    if truth.approved_stakes and not _keywords_present(truth.approved_stakes, lower):
        failures.append("Approved stakes softened or missing")
        repairs.append("stakes")
        score -= 15
    if truth.approved_stakes and any(term in truth.approved_stakes.lower() for term in ("forces moving", "situation is still moving", "things will get worse")):
        failures.append("Approved stakes are abstract")
        repairs.append("stakes")
        score -= 15
    for forbidden in truth.forbidden_reveals + truth.forbidden_motifs:
        if forbidden and forbidden.lower() in lower:
            failures.append(f"Forbidden reveal/motif present: {forbidden[:60]}")
            score -= 15
    return max(0, score), failures, list(dict.fromkeys(repairs))


def validate_player_action_continuity(
    *,
    player_intent: dict[str, Any] | None = None,
    recent_player_actions: list[str] | None = None,
    current_scene: dict[str, Any] | None = None,
    new_scene: dict[str, Any],
    scene_beat_plan: dict[str, Any] | None = None,
    content_bundle: dict[str, Any] | None = None,
) -> tuple[int, list[str], list[str]]:
    actions = [str(a).strip() for a in (recent_player_actions or []) if str(a or "").strip()]
    if not actions:
        return 85, [], []
    text = _text(new_scene).lower()
    latest = actions[-1]
    keywords = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", latest) if w.lower() not in {"with", "from", "that", "this", "into", "onto", "look", "make"}]
    hits = [w for w in keywords if w in text]
    failures: list[str] = []
    repairs: list[str] = []
    score = 100
    if not hits:
        failures.append("New scene does not acknowledge recent player action")
        repairs.append("continuity")
        score -= 45
    if classify_opening_shape(new_scene, content_bundle).get("opening_shape") == "named_npc_arrives_with_object_and_warning" and actions:
        failures.append("Continuation looks like a restarted opener")
        repairs.append("continuity")
        score -= 25
    if not re.search(r"\b(because|therefore|but|so|as|after|when|the result|the consequence|reveals?|finds?|learns?|costs?)\b", text):
        failures.append("Scene does not resolve, complicate, or advance the action")
        repairs.append("ending_beat")
        score -= 15
    return max(0, score), failures, list(dict.fromkeys(repairs))


def infer_gm_move(scene_beat_plan: dict[str, Any] | None, content_bundle: dict[str, Any] | None) -> str:
    plan = scene_beat_plan or {}
    existing = str(plan.get("gm_move") or "")
    if existing in GM_MOVES:
        return existing
    scene_type = str(plan.get("scene_type") or plan.get("beat_type_chosen") or "").lower()
    rc = _required(content_bundle)
    if "combat" in scene_type:
        return "start_combat"
    if rc.get("first_clue_or_question") or "investigation" in scene_type:
        return "reveal_clue"
    if "consequence" in scene_type:
        return "show_consequence"
    if "social" in scene_type or "choice" in scene_type:
        return "present_moral_choice"
    if rc.get("specific_stakes"):
        return "show_approaching_threat"
    return "introduce_complication"


def infer_scene_purpose(scene_beat_plan: dict[str, Any] | None, content_bundle: dict[str, Any] | None) -> dict[str, str]:
    plan = scene_beat_plan or {}
    primary = str(plan.get("primary_scene_purpose") or "")
    if primary not in PRIMARY_PURPOSES:
        stype = str(plan.get("scene_type") or "").lower()
        if "opening" in stype:
            primary = "seed_thread"
        elif "investigation" in stype or _required(content_bundle).get("first_clue_or_question"):
            primary = "reveal_clue"
        elif "combat" in stype:
            primary = "start_combat"
        elif "travel" in stype:
            primary = "transition_location"
        else:
            primary = "force_decision"
    secondary = str(plan.get("secondary_scene_purpose") or "")
    if secondary and secondary not in PRIMARY_PURPOSES:
        secondary = ""
    return {"primary_scene_purpose": primary, "secondary_scene_purpose": secondary}


def validate_gm_move(text: str, gm_move: str) -> tuple[int, list[str]]:
    lower = text.lower()
    requirements = {
        "reveal_clue": r"\b(clue|mark|symbol|track|trail|seal|rune|ledger|map|notice|evidence|reveals?)\b",
        "show_approaching_threat": r"\b(approach|nearer|before|dusk|dawn|tracks|lanterns|closing|loses?|threat|warning)\b",
        "offer_opportunity_with_cost": r"\b(can|could|chance|opportunity).{0,80}\b(cost|but|unless|risk)\b",
        "show_consequence": r"\b(consequence|because|therefore|loses?|costs?|breaks?|vanishes?|changes?)\b",
        "present_moral_choice": r"\b(or|choose|save|protect|betray|risk|cost)\b",
        "start_combat": r"\b(attack|weapon|strike|enemy|combat|ambush|fight)\b",
        "introduce_complication": r"\b(but|however|complication|worse|another|instead)\b",
    }
    pattern = requirements.get(gm_move)
    if pattern and not re.search(pattern, lower):
        return 55, [f"Scene does not clearly perform GM move: {gm_move}"]
    return 90, []


def build_campaign_palette(campaign_contract: dict[str, Any] | None, content_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = campaign_contract or {}
    rc = _required(content_bundle)
    source = " ".join([
        str(contract.get("campaign_pitch") or ""),
        str((contract.get("campaign_dna") or {}).get("themes") or ""),
        str(rc.get("location_identity") or ""),
        str(rc.get("first_clue_or_question") or ""),
        str(rc.get("specific_stakes") or ""),
    ]).lower()
    palette = {
        "recurring_symbols": [],
        "sensory_palette": [],
        "faction_language": [],
        "location_language": [],
        "threat_language": [],
        "forbidden_overused_motifs": ["sealed-message-object", "late-message-courier", "generic-tavern-default"],
        "preferred_concrete_nouns": [],
    }
    if any(w in source for w in ("winter", "frozen", "snow", "ice")):
        palette["recurring_symbols"] = ["blackened silver", "frozen tracks", "old charms"]
        palette["sensory_palette"] = ["cold iron", "snowmelt", "bitter wind"]
        palette["threat_language"] = ["lost road", "winter pressure", "buried warning"]
        palette["preferred_concrete_nouns"] = ["charm", "snow", "road", "shrine", "tracks"]
    elif any(w in source for w in ("desert", "water", "glass", "dune")):
        palette["recurring_symbols"] = ["water seal", "glass sand", "sun-cracked map"]
        palette["sensory_palette"] = ["hot dust", "dry copper", "white glare"]
        palette["preferred_concrete_nouns"] = ["cistern", "ledger", "well", "glass", "dune"]
    elif any(w in source for w in ("court", "mask", "throne", "faction")):
        palette["recurring_symbols"] = ["borrowed mask", "sealed vote", "broken signet"]
        palette["sensory_palette"] = ["perfume", "wax", "marble echo"]
        palette["preferred_concrete_nouns"] = ["signet", "mask", "ledger", "balcony", "seal"]
    return palette


def validate_memory_delta(scene: dict[str, Any], memory_delta: dict[str, Any] | None, content_bundle: dict[str, Any] | None) -> dict[str, Any]:
    text = _text(scene).lower()
    delta = memory_delta or {}
    issues = []
    for key in ("new_npcs", "new_locations", "new_clues"):
        for item in delta.get(key, []) if isinstance(delta.get(key), list) else []:
            name = str(item.get("name") if isinstance(item, dict) else item)
            if name and name.lower() not in text and name.lower() not in str(content_bundle or {}).lower():
                issues.append(f"{key} item not supported by prose: {name}")
    return {"valid": not issues, "issues": issues}


def validate_ui_payload(scene: dict[str, Any], truth: SceneTruthTable, dice_rolls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    issues = []
    if not scene.get("title"):
        issues.append("scene title missing")
    if not (scene.get("narrative_body") or scene.get("text")):
        issues.append("narrative body missing")
    if truth.approved_location and truth.approved_location != scene.get("location"):
        issues.append("scene location does not match truth table")
    if truth.approved_clue:
        clues = " ".join(str(c) for c in scene.get("visible_clues") or [])
        if not _keywords_present(truth.approved_clue, clues.lower() + " " + _text(scene).lower()):
            issues.append("visible clues do not match truth table")
    if scene.get("world_moves") and all(str(x).lower() in GENERIC_TERMS for x in scene.get("world_moves") or []):
        issues.append("world moves are generic filler")
    return {"valid": not issues, "issues": issues, "dice_roll_count": len(dice_rolls or [])}


def detail_budget(scene: dict[str, Any]) -> dict[str, Any]:
    npcs = set(re.findall(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b", _text(scene)))
    clues = scene.get("visible_clues") or []
    threads = scene.get("active_threads") or []
    issues = []
    if len(npcs) > 3:
        issues.append("too many named NPCs for a focused scene")
    if len(clues) > 3:
        issues.append("too many visible clues")
    if len(threads) > 2:
        issues.append("too many active threads")
    return {
        "max_major_npcs": 1,
        "named_npcs_detected": sorted(npcs),
        "visible_clue_count": len(clues),
        "active_thread_count": len(threads),
        "issues": issues,
        "valid": not issues,
    }


def npc_scene_roles(scene: dict[str, Any], truth: SceneTruthTable) -> list[dict[str, Any]]:
    npc = truth.approved_primary_npc.split("(")[0].strip()
    if not npc:
        return []
    text = _text(scene).lower()
    role = "witness"
    if "blocks" in text or "refuses" in text:
        role = "obstacle"
    elif "attack" in text or "weapon" in text:
        role = "threat"
    elif "knows" in text or "clue" in text or "symbol" in text:
        role = "source_of_partial_truth"
    return [{
        "npc_id": npc.lower().replace(" ", "_"),
        "name": npc,
        "scene_role": role,
        "wants": truth.approved_stakes or scene.get("current_objective") or "",
        "knows": [truth.approved_clue] if truth.approved_clue else [],
        "hides": [],
        "pressure_point": truth.approved_stakes,
        "relationship_to_party": "present in the current scene",
    }]


def run_scene_qa(
    *,
    scene: dict[str, Any],
    campaign_contract: dict[str, Any] | None = None,
    campaign_scale_profile: dict[str, Any] | None = None,
    story_shape_profile: dict[str, Any] | None = None,
    scene_beat_plan: dict[str, Any] | None = None,
    content_bundle: dict[str, Any] | None = None,
    narrative_output: dict[str, Any] | None = None,
    player_intent: dict[str, Any] | None = None,
    recent_player_actions: list[str] | None = None,
    current_scene: dict[str, Any] | None = None,
    recent_scene_history: list[dict[str, Any]] | None = None,
    recent_opening_shapes: list[dict[str, Any]] | None = None,
    recent_motifs: list[str] | None = None,
    memory_delta: dict[str, Any] | None = None,
    ui_payload: dict[str, Any] | None = None,
    dice_rolls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    text = _text(scene, narrative_output)
    truth = build_scene_truth_table(scene=scene, content_bundle=content_bundle, scene_director_data=scene.get("scene_director_data"), scene_beat_plan=scene_beat_plan)
    palette = build_campaign_palette(campaign_contract, content_bundle)
    if not truth.approved_object:
        palette_object = next((str(x) for x in (palette.get("recurring_symbols") or []) if str(x).strip()), "")
        if not palette_object:
            palette_object = next((str(x) for x in (palette.get("preferred_concrete_nouns") or []) if str(x).strip()), "")
        truth.approved_object = palette_object
    if not truth.approved_stakes or any(term in truth.approved_stakes.lower() for term in ("forces moving", "situation is still moving", "things will get worse")):
        concrete = truth.approved_object or truth.approved_clue or "the clearest lead"
        place = truth.approved_location or "this scene"
        truth.approved_stakes = f"If the party delays, {concrete} is moved from {place} before it can be tested."
    specificity_score, specificity_failures = score_specificity(text, truth, palette)
    truth_score, truth_failures, truth_repairs = validate_truth_table(text, truth)
    freshness_score, freshness_failures, shape = validate_freshness(
        new_scene=scene,
        content_bundle=content_bundle,
        recent_scene_history=recent_scene_history,
        recent_opening_shapes=recent_opening_shapes if recent_opening_shapes is not None else load_recent_opening_shapes(),
        recent_motifs=recent_motifs or [],
        campaign_contract=campaign_contract,
    )
    scene_type = str((scene_beat_plan or {}).get("scene_type") or scene.get("situation_type") or "").lower()
    is_opening_scene = scene_type in {"campaign_opening", "opening_choice", "new_scene_opening"} or scene.get("id") == "opening"
    if not is_opening_scene:
        freshness_failures = [
            failure for failure in freshness_failures
            if not (
                failure.startswith("Opening shape recently used")
                or failure.startswith("Repeated location_type")
                or failure.startswith("Repeated inciting_event_type")
                or failure.startswith("Repeated object_type")
                or failure.startswith("Repeated stakes_type")
            )
        ]
        freshness_score = max(freshness_score, 80 if not freshness_failures else 70)
    continuity_score, continuity_failures, continuity_repairs = validate_player_action_continuity(
        player_intent=player_intent,
        recent_player_actions=recent_player_actions,
        current_scene=current_scene,
        new_scene=scene,
        scene_beat_plan=scene_beat_plan,
        content_bundle=content_bundle,
    )
    gm_move = infer_gm_move(scene_beat_plan, content_bundle)
    gm_score, gm_failures = validate_gm_move(text, gm_move)
    purpose = infer_scene_purpose(scene_beat_plan, content_bundle)
    agency_score = 90 if (scene.get("choices") or scene.get("suggested_actions") or "?" in text[-160:]) else 45
    playability_score = min(100, max(0, (truth_score + agency_score + gm_score) // 3))
    campaign_fit_score = min(100, max(0, (truth_score + specificity_score) // 2))
    memorability_score = min(100, max(0, specificity_score - (10 if "generic" in " ".join(freshness_failures).lower() else 0)))
    memory_check = validate_memory_delta(scene, memory_delta, content_bundle)
    ui_check = validate_ui_payload(scene, truth, dice_rolls=dice_rolls)
    budget = detail_budget(scene)
    repair_targets = list(dict.fromkeys(
        truth_repairs
        + continuity_repairs
        + (["specificity"] if specificity_score < 70 else [])
        + (["campaign_fit"] if campaign_fit_score < 70 else [])
        + (["player_agency"] if agency_score < 70 else [])
        + (["suggested_actions"] if agency_score < 70 else [])
        + (["memory_delta"] if not memory_check["valid"] else [])
    ))
    all_failures = specificity_failures + truth_failures + freshness_failures + continuity_failures + gm_failures + budget["issues"] + ui_check["issues"] + memory_check["issues"]
    quality_score = int((specificity_score * 0.2) + (freshness_score * 0.15) + (continuity_score * 0.15) + (agency_score * 0.1) + (playability_score * 0.15) + (campaign_fit_score * 0.15) + (memorability_score * 0.1))
    passed = quality_score >= 75 and not truth_failures and not continuity_failures and ui_check["valid"]
    if freshness_score < 50:
        passed = False
    biggest = all_failures[0] if all_failures else ""
    return SceneQAResult(
        **{
            "pass": passed,
            "quality_score": quality_score,
            "specificity_score": specificity_score,
            "freshness_score": freshness_score,
            "continuity_score": continuity_score,
            "agency_score": agency_score,
            "playability_score": playability_score,
            "campaign_fit_score": campaign_fit_score,
            "memorability_score": memorability_score,
            "biggest_issue": biggest,
            "required_revision": "; ".join(all_failures[:4]),
            "repair_targets": repair_targets,
            "truth_table": truth.model_dump(),
            "opening_shape": shape,
            "gm_move": gm_move,
            "scene_purpose": purpose,
            "tension_curve": _tension_curve(scene_beat_plan, recent_scene_history, campaign_scale_profile, story_shape_profile),
            "npc_scene_roles": npc_scene_roles(scene, truth),
            "detail_budget": budget,
            "campaign_palette": palette,
            "memory_delta_consistency": memory_check,
            "ui_payload_validation": ui_check,
            "freshness_failures": freshness_failures,
            "continuity_failures": continuity_failures,
            "specificity_failures": specificity_failures + truth_failures,
            "regression_tags": _regression_tags(all_failures),
        }
    ).model_dump(by_alias=True)


def _tension_curve(scene_beat_plan: dict[str, Any] | None, recent_scene_history: list[dict[str, Any]] | None, campaign_scale_profile: dict[str, Any] | None, story_shape_profile: dict[str, Any] | None) -> dict[str, Any]:
    recent = []
    for item in recent_scene_history or []:
        plan = item.get("scene_beat_plan") or item.get("selected_scene_beat") or {}
        if isinstance(plan, dict) and plan.get("tension_level") is not None:
            recent.append(plan.get("tension_level"))
    current = (scene_beat_plan or {}).get("tension_level")
    issues = []
    if len(recent) >= 2 and current is not None and recent[-1] == recent[-2] == current:
        issues.append("same tension repeated three scenes in a row")
    return {
        "recent_tension": recent[-5:],
        "current_target": current,
        "desired_curve": (story_shape_profile or {}).get("desired_curve") or [],
        "issues": issues,
    }


def _regression_tags(failures: list[str]) -> list[str]:
    tags = []
    joined = " ".join(failures).lower()
    if "generic" in joined:
        tags.append("generic_language")
    if "repeated" in joined or "recently used" in joined:
        tags.append("freshness")
    if "player action" in joined or "continuation" in joined:
        tags.append("continuity")
    if "location" in joined or "npc" in joined or "clue" in joined:
        tags.append("truth_table")
    return tags


def apply_targeted_scene_repairs(
    scene: dict[str, Any],
    qa_result: dict[str, Any],
    *,
    player_name: str = "the party",
    recent_player_actions: list[str] | None = None,
) -> dict[str, Any]:
    targets = set(qa_result.get("repair_targets") or [])
    if not targets:
        return scene
    truth = SceneTruthTable(**(qa_result.get("truth_table") or {}))
    text = _text(scene)
    narrative = scene.get("narrative_body") or text
    prompt = scene.get("player_prompt") or f"What does {player_name} do?"
    paragraphs = [p for p in narrative.split("\n\n") if p.strip()]
    repair_paras: list[str] = []
    pc = player_name or "the party"
    if "continuity" in targets and recent_player_actions:
        latest = str(recent_player_actions[-1]).strip()
        repair_paras.append(f"Because {pc} chose to {latest.rstrip('.')}, the scene turns on that action instead of resetting: the nearest useful detail is now tied directly to what they just did.")
    if "location_identity" in targets and truth.approved_location:
        repair_paras.append(f"{truth.approved_location} anchors the moment; its visible details make this problem local rather than interchangeable.")
    if "npc_intro" in targets and truth.approved_primary_npc:
        npc = truth.approved_primary_npc.split("(")[0].strip()
        repair_paras.append(f"{npc} has a concrete role here: they can point to what changed, what they want protected, and what they are afraid will be lost next.")
    if "clue_presentation" in targets and truth.approved_clue:
        repair_paras.append(f"The clearest clue is this: {truth.approved_clue.rstrip('.')}.")
    if "stakes" in targets and truth.approved_stakes:
        repair_paras.append(f"The immediate consequence is concrete: {truth.approved_stakes.rstrip('.')}.")
    if "specificity" in targets:
        concrete_bits = [bit for bit in (truth.approved_clue, truth.approved_object, truth.approved_stakes) if bit]
        if concrete_bits:
            repair_paras.append("The scene's concrete table details are: " + "; ".join(bit.rstrip(".") for bit in concrete_bits[:3]) + ".")
    if "player_agency" in targets or "suggested_actions" in targets or "ending_beat" in targets:
        options = truth.approved_possible_actions or [
            "inspect the clue", "question the witness", "secure the location", "follow the freshest lead",
        ]
        prompt = f"What does {pc} do: {', '.join(options[:3])}, or something else?"
        scene["suggested_actions"] = options[:4]
        scene["choices"] = [{"id": f"action_{i}", "label": action} for i, action in enumerate(options[:4])]
    if repair_paras:
        if paragraphs:
            paragraphs.extend(repair_paras)
            narrative = "\n\n".join(paragraphs)
        else:
            narrative = "\n\n".join(repair_paras)
    scene["narrative_body"] = narrative
    scene["player_prompt"] = prompt
    scene["text"] = f"{narrative}\n\n{prompt}".strip()
    scene.setdefault("quality_repairs_applied", []).extend(sorted(targets))
    return scene
