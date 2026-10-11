"""Decide what is secretly going on in a new campaign before play starts.

The visible world (places, minor people, scenery) is cheap to invent when the
party gets there.  What lies underneath is not: if the hidden truth behind the
opening trouble is improvised scene by scene, clues stop adding up.  So after
the Campaign Card is confirmed, a background job makes four small model calls:

1. the hidden truth behind the opening trouble (and the first clue toward it),
2. two or three factions and what each wants,
3. three or four key NPCs, each with a want and a secret,
4. one clock: what escalates if the party does nothing.

Right after the truth exists, the job also prepares the first session's opening
seed so the questionnaire does not wait on that call and the first clue points
at something real.

Every piece is written as soon as it is valid, as GM-only campaign memory
(``CampaignEntity`` / ``CampaignHook``) that the context orchestrator already
ranks into scene context.  Generated content is ``generated_provisional``;
names the player wrote keep ``user`` provenance and names found in imported
lore keep ``imported``.  A piece that fails stays "open" and play fills it in,
as it did before this existed; the status records why.
"""
from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TypeVar

from sqlmodel import Session, col, select

from .. import db
from ..db import CampaignChangeLog, CampaignEntity, CampaignHook
from .campaign_card import name_in_text, relevant_lore
from .generation_intent import clean_text, content_tokens
from .premise_seed import parse_json_object

log = logging.getLogger("taverntails.world_skeleton")

PIECES = ("truth", "factions", "npcs", "clock")
TAG = "world_skeleton"
VISIBILITIES = ("surprise", "show")
# Keys the background job owns. Everything else in the stored state (the visibility the owner picks,
# whether the opening seed was used) is written by requests while the job runs and must survive its saves.
_JOB_KEYS = ("status", "pieces", "started_at", "finished_at", "opening_seed")
# Four calls plus the opening seed take about a minute on one GPU, longer behind a queue. A job silent for
# this long was lost to a restart (or runs in a process that cannot tell us otherwise).
STALE_AFTER_S = 15 * 60
CLOCK_STEP_JOINER = " Then: "

_R = TypeVar("_R")
MAX_FIELD_CHARS = 240
MAX_LORE_PROMPT_CHARS = 6000

_running: set[str] = set()
_running_lock = threading.Lock()

_COMMON = (
    "You are the game master quietly preparing a tabletop RPG campaign. The players will never see this; "
    "it is what is true underneath. Keep everything consistent with the campaign brief and the player's own "
    "words; never contradict them. If setting notes are given, take names and facts from them and invent "
    "only where they are silent. Keep each value short. Reply with ONLY a JSON object.\n"
)
TRUTH_SYSTEM = _COMMON + (
    'Keys: "thread_name" (2-6 words naming the mystery or conflict), '
    '"visible_problem" (one sentence: what the party can see is wrong at the start; it must match the opening trouble if one is given), '
    '"hidden_truth" (one or two sentences: what is really happening and why), '
    '"who_benefits" (who gains from it, "Name (role)" or a group), '
    '"first_clue" (one sentence: a concrete thing present at the start that points toward the hidden truth without revealing it), '
    '"stakes" (one sentence: what is lost if nobody acts).'
)
FACTIONS_SYSTEM = _COMMON + (
    'Keys: "factions": a list of 2 or 3 objects with "name", "wants" (one sentence), '
    '"plan" (one sentence: what they are doing right now), "if_ignored" (one sentence: what they do next if '
    "nobody interferes). Include every faction the player named, with the same name. At least one faction "
    "should be tied to the hidden truth."
)
NPCS_SYSTEM = _COMMON + (
    'Keys: "npcs": a list of 3 or 4 objects with "name" (a full name), "role", "faction" (one of the faction '
    'names given, or ""), "wants" (one sentence), "secret" (one sentence), "knows" (one sentence: what they '
    "could tell the party). Include every person the player named, with the same name. At least one of them "
    "knows part of the hidden truth."
)
CLOCK_SYSTEM = _COMMON + (
    'Keys: "title" (2-6 words), "steps" (a list of exactly 3 short sentences: what happens, in order, if the '
    'party does nothing), "deadline" (a short phrase for when the last step lands, e.g. "the third night").'
)


# ---------------------------------------------------------------------------
# Campaign brief
# ---------------------------------------------------------------------------

def _meta(campaign: db.Campaign) -> dict[str, Any]:
    return dict(campaign.metadata_json or {}) if isinstance(campaign.metadata_json, dict) else {}


def _card_roles(meta: dict[str, Any]) -> dict[str, str]:
    """Roles the player confirmed for the people they named ("Maren Vey" -> "lighthouse keeper")."""
    card = meta.get("campaign_card") or {}
    roles: dict[str, str] = {}
    for item in card.get("people") or []:
        if isinstance(item, dict) and clean_text(item.get("name")) and clean_text(item.get("role")):
            roles[clean_text(item.get("name")).casefold()] = clean_text(item.get("role"))
    return roles


def _card_names(meta: dict[str, Any], key: str) -> list[str]:
    card = meta.get("campaign_card") or {}
    return [clean_text(item.get("name")) for item in card.get(key) or [] if isinstance(item, dict) and clean_text(item.get("name"))]


def _player_text(meta: dict[str, Any]) -> str:
    """What the player typed (description, card edits and follow-up answers), not their setting notes.

    Card names are not added wholesale: the card accepts names found in uploaded notes too, and those
    must keep ``imported`` provenance.
    """
    settings = meta.get("settings") or {}
    card = meta.get("campaign_card") or {}
    typed = [str(card.get("text") or "")]
    for entry in (card.get("fields") or {}).values():
        if isinstance(entry, dict) and entry.get("status") == "said":
            typed.append(str(entry.get("value") or ""))
    written = [str(settings.get(k) or "") for k in ("setting_summary", "world_name", "starting_location", "opening_trouble")]
    return " ".join(written + typed)


def _lore(meta: dict[str, Any]) -> str:
    return "\n".join(str(doc) for doc in meta.get("imported_lore") or [] if doc)


def campaign_brief(campaign: db.Campaign) -> str:
    """What every skeleton call is told about the campaign."""
    meta = _meta(campaign)
    settings = meta.get("settings") or {}
    lines = [
        f"Campaign: {campaign.name}",
        f"Genre: {settings.get('genre') or 'fantasy'}; tone: {settings.get('tone') or 'balanced'}",
        f"Premise in the player's words: {clean_text(settings.get('setting_summary')) or clean_text(campaign.description) or '(none)'}",
    ]
    for label, key in (("World", "world_name"), ("The story opens at", "starting_location"), ("Opening trouble", "opening_trouble")):
        if clean_text(settings.get(key)):
            lines.append(f"{label}: {clean_text(settings.get(key))}")
    people = _card_names(meta, "people")
    factions = _card_names(meta, "factions")
    if people:
        roles = _card_roles(meta)
        named = [f"{p} ({roles[p.casefold()]})" if p.casefold() in roles else p for p in people]
        lines.append("People the player named (keep these roles): " + ", ".join(named))
    if factions:
        lines.append("Factions the player named: " + ", ".join(factions))
    if settings.get("content_limits"):
        lines.append("Avoid: " + "; ".join(str(c) for c in settings["content_limits"]))
    questions = [str(q) for q in (meta.get("campaign_card") or {}).get("open_questions") or [] if q]
    if questions:
        lines.append("Questions the player left open (the hidden truth should answer them): " + " ".join(questions))
    lore = _lore(meta)
    if lore:
        query = " ".join([str(settings.get(k) or "") for k in ("setting_summary", "starting_location", "opening_trouble")] + people + factions)
        lines.append(f"Setting notes (the parts most relevant to this campaign):\n{relevant_lore(lore, query, MAX_LORE_PROMPT_CHARS)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _clip(value: Any) -> str:
    """Whitespace collapsed; sentence punctuation kept, since these are read back as prose."""
    return " ".join(str(value or "").split())[:MAX_FIELD_CHARS]


def validate_truth(data: dict[str, Any], *, opening_trouble: str = "") -> dict[str, str] | None:
    keys = ("thread_name", "visible_problem", "hidden_truth", "who_benefits", "first_clue", "stakes")
    out = {k: _clip(data.get(k)) for k in keys}
    if not all(out.values()):
        return None
    if not 1 <= len(out["thread_name"].split()) <= 8:
        return None
    hidden, visible = content_tokens(out["hidden_truth"]), content_tokens(out["visible_problem"])
    if hidden and len(hidden - visible) < 2:
        return None  # the "truth" only restates what everyone can already see
    # The first clue is shown to players and treated as public by the seed's leak check, so it must point
    # at the truth without carrying it.
    secret_only = hidden - visible
    if secret_only and len(secret_only & content_tokens(out["first_clue"])) >= max(2, (len(secret_only) + 1) // 2):
        return None
    trouble = content_tokens(opening_trouble)
    if trouble:
        # Most of what the player said is wrong must be what the party sees: a murder "near the bridge"
        # does not match "the bridge collapsed". Small models paraphrase, so not every word is required.
        shared = trouble & (visible | content_tokens(out["thread_name"]))
        if len(shared) < min(3, (len(trouble) + 1) // 2):
            return None  # it planned a different crisis than the one the player described
    return out


def _named_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    items = data.get(key)
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def validate_factions(data: dict[str, Any], authored: list[str]) -> list[dict[str, str]] | None:
    out: list[dict[str, str]] = []
    for item in _named_list(data, "factions"):
        entry = {k: _clip(item.get(k)) for k in ("name", "wants", "plan", "if_ignored")}
        if entry["name"] and entry["wants"] and entry["name"].casefold() not in {f["name"].casefold() for f in out}:
            entry["name"] = entry["name"][:80]
            out.append(entry)
    returned = {f["name"].casefold() for f in out}
    for name in authored:  # the player's factions exist whether or not the model kept them
        if name.casefold() not in returned:
            out.insert(0, {"name": name, "wants": "", "plan": "", "if_ignored": ""})
    return out[: max(3, len(authored))] if len(out) >= 2 else None


def validate_npcs(
    data: dict[str, Any], authored: list[str], faction_names: list[str], roles: dict[str, str] | None = None,
) -> list[dict[str, str]] | None:
    """Usable NPCs; the player's named people are always present, with the roles they confirmed."""
    roles = roles or {}
    taken = {f.casefold() for f in faction_names}
    known_factions = {f.casefold(): f for f in faction_names}
    out: list[dict[str, str]] = []
    for item in _named_list(data, "npcs"):
        entry = {k: _clip(item.get(k)) for k in ("name", "role", "faction", "wants", "secret", "knows")}
        name = entry["name"][:80]
        if not (name and entry["wants"] and entry["secret"]) or name.casefold() in taken:
            continue
        taken.add(name.casefold())
        entry["name"] = name
        entry["role"] = roles.get(name.casefold(), entry["role"])  # a confirmed role is a fact, not a suggestion
        entry["faction"] = known_factions.get(entry["faction"].casefold(), "")
        out.append(entry)
    returned = {n["name"].casefold() for n in out}
    for name in authored:
        if name.casefold() not in returned:
            out.insert(0, {"name": name, "role": roles.get(name.casefold(), ""), "faction": "", "wants": "",
                           "secret": "", "knows": ""})
    return out[: max(4, len(authored))] if len(out) >= 2 else None


def validate_clock(data: dict[str, Any]) -> dict[str, Any] | None:
    title, deadline = _clip(data.get("title")), _clip(data.get("deadline"))
    steps = [_clip(s) for s in data.get("steps") or [] if _clip(s)] if isinstance(data.get("steps"), list) else []
    if not title or not deadline or len(steps) < 2:
        return None
    return {"title": title[:80], "steps": steps[:3], "deadline": deadline[:80]}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _provenance(name: str, player_text: str, lore: str) -> str:
    if name_in_text(name, player_text):
        return "user"
    if lore and name_in_text(name, lore):
        return "imported"
    return "generated_provisional"


def _add_entity(s: Session, campaign_id: str, entity_type: str, name: str, data: dict[str, Any]) -> str:
    eid = uuid.uuid4().hex[:12]
    s.add(CampaignEntity(
        id=eid, campaign_id=campaign_id, entity_type=entity_type, name=name, status="active",
        visibility="gm_only", tags=[TAG], data=data, created_at=_now(), updated_at=_now(),
    ))
    s.add(CampaignChangeLog(
        id=uuid.uuid4().hex[:12], campaign_id=campaign_id, entity_id=eid, change_type="create",
        summary=f"World skeleton created {entity_type} '{name}'", before_data={}, after_data=data,
        caused_by_player_action=False, created_at=_now(),
    ))
    return eid


def _persist(campaign: db.Campaign, piece: str, value: Any, *, thread_id: str | None = None) -> list[str]:
    """Write one piece as GM-only memory in a single transaction; returns the new row ids."""
    campaign_id = str(campaign.id)
    meta = _meta(campaign)
    player_text, lore = _player_text(meta), _lore(meta)
    ids: list[str] = []
    with Session(db.engine) as s:
        if piece == "truth":
            ids.append(_add_entity(s, campaign_id, "story_thread", value["thread_name"], {
                # current_situation is what the orchestrator offers as an available clue, so it carries
                # only what the party can already see; the truth itself goes in gm_notes (never revealed).
                "current_situation": value["visible_problem"],
                "stakes": value["stakes"],
                "gm_notes": value["hidden_truth"],
                "who_benefits": value["who_benefits"],
                "first_clue": value["first_clue"],
                "next_recommended_dm_move": f"Put this within reach: {value['first_clue']}",
                "current_priority": 8,
                "provenance": "generated_provisional",
                "skeleton_piece": "truth",
            }))
        elif piece == "factions":
            for faction in value:
                ids.append(_add_entity(s, campaign_id, "faction", faction["name"], {
                    "current_goal": faction["wants"],
                    "active_plan": faction["plan"],
                    "likely_escalation": faction["if_ignored"],
                    "provenance": _provenance(faction["name"], player_text, lore),
                    "details_provenance": "generated_provisional",
                    "skeleton_piece": "factions",
                }))
        elif piece == "npcs":
            for npc in value:
                ids.append(_add_entity(s, campaign_id, "npc", npc["name"], {
                    "role": npc["role"],
                    "primary_goal": npc["wants"],
                    "secrets": [npc["secret"]] if npc["secret"] else [],
                    "known_information": [npc["knows"]] if npc["knows"] else [],
                    "faction_affiliations": [npc["faction"]] if npc["faction"] else [],
                    "provenance": _provenance(npc["name"], player_text, lore),
                    "details_provenance": "generated_provisional",
                    "skeleton_piece": "npcs",
                }))
        elif piece == "clock":
            hook_id = uuid.uuid4().hex[:12]
            s.add(CampaignHook(
                id=hook_id, campaign_id=campaign_id, title=value["title"],
                description=CLOCK_STEP_JOINER.join(value["steps"]), hook_type="ticking_clock", priority=8,
                status="active", deadline=value["deadline"], created_at=_now(), updated_at=_now(),
            ))
            ids.append(hook_id)
            thread = s.get(CampaignEntity, thread_id) if thread_id else None
            if thread is not None:
                thread.data = {**(thread.data or {}), "ticking_clock": value["deadline"]}
                thread.updated_at = _now()
                s.add(thread)
        s.commit()
    return ids


# ---------------------------------------------------------------------------
# Reading pieces back
# ---------------------------------------------------------------------------
#
# Campaign metadata is returned whole by the campaign list and detail routes, so it only ever
# holds progress and row ids. The contents (the secrets) are read from the GM-only rows, and only
# for a caller who may see them.

def _entities(ids: list[str]) -> list[CampaignEntity]:
    if not ids:
        return []
    with Session(db.engine) as s:
        rows = {e.id: e for e in s.exec(select(CampaignEntity).where(col(CampaignEntity.id).in_(ids))).all()}
    return [rows[i] for i in ids if i in rows]


def _first(values: Any) -> str:
    return str(values[0]) if isinstance(values, list) and values else ""


def _piece_contents(piece: str, ids: list[str]) -> Any:
    if piece == "clock":
        with Session(db.engine) as s:
            hook = s.get(CampaignHook, ids[0]) if ids else None
        if hook is None:
            return None
        return {"title": hook.title, "steps": [p for p in (hook.description or "").split(CLOCK_STEP_JOINER) if p],
                "deadline": hook.deadline or ""}
    rows = _entities(ids)
    if piece == "truth":
        if not rows:
            return None
        d = rows[0].data or {}
        return {"thread_name": rows[0].name, "visible_problem": d.get("current_situation", ""),
                "hidden_truth": d.get("gm_notes", ""), "who_benefits": d.get("who_benefits", ""),
                "first_clue": d.get("first_clue", ""), "stakes": d.get("stakes", "")}
    if piece == "factions":
        return [{"name": e.name, "wants": (e.data or {}).get("current_goal", ""),
                 "plan": (e.data or {}).get("active_plan", ""), "if_ignored": (e.data or {}).get("likely_escalation", "")}
                for e in rows]
    if piece == "npcs":
        return [{"name": e.name, "role": (e.data or {}).get("role", ""), "wants": (e.data or {}).get("primary_goal", ""),
                 "secret": _first((e.data or {}).get("secrets")), "knows": _first((e.data or {}).get("known_information")),
                 "faction": _first((e.data or {}).get("faction_affiliations"))}
                for e in rows]
    return None


def _ready_contents(state: dict[str, Any], piece: str) -> Any:
    entry = (state.get("pieces") or {}).get(piece) or {}
    return _piece_contents(piece, list(entry.get("entity_ids") or [])) if entry.get("status") == "ready" else None


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def _normalized(stored: Any) -> dict[str, Any]:
    state = dict(stored or {})
    state.setdefault("status", "not_started")
    state.setdefault("visibility", "surprise")
    pieces = dict(state.get("pieces") or {})
    for piece in PIECES:
        pieces.setdefault(piece, {"status": "pending"})
    state["pieces"] = pieces
    return state


def _state(campaign: db.Campaign) -> dict[str, Any]:
    return _normalized(_meta(campaign).get("world_skeleton"))


def _fresh_state(campaign_id: str) -> dict[str, Any]:
    campaign = db.get_campaign_by_id(campaign_id)
    return _state(campaign) if campaign is not None else _normalized(None)


def _update(campaign_id: str, change: Callable[[dict[str, Any]], _R]) -> _R | None:
    """Apply ``change`` to the stored state inside one locked transaction."""
    def mutate(meta: dict[str, Any]) -> _R:
        state = dict(meta.get("world_skeleton") or {})
        result = change(state)
        meta["world_skeleton"] = state
        return result

    return db.update_campaign_metadata(campaign_id, mutate)


def _save(campaign_id: str, job: dict[str, Any]) -> None:
    """Write the job's keys over the stored state, keeping what requests changed meanwhile."""
    def change(state: dict[str, Any]) -> None:
        for key in _JOB_KEYS:
            if key in job:
                state[key] = job[key]
        if state.get("opening_seed_used"):
            state.pop("opening_seed", None)  # a session already opened without it

    _update(campaign_id, change)


def _overall(pieces: dict[str, Any]) -> str:
    statuses = [pieces[p].get("status") for p in PIECES]
    if all(s == "ready" for s in statuses):
        return "ready"
    if any(s == "ready" for s in statuses):
        return "partial"
    return "failed"


def init_state(campaign_id: str, visibility: str = "surprise") -> None:
    """Record that a skeleton is wanted, before the background job starts."""
    def change(state: dict[str, Any]) -> None:
        state.clear()
        state.update({
            "status": "pending",
            "visibility": visibility if visibility in VISIBILITIES else "surprise",
            "pieces": {piece: {"status": "pending"} for piece in PIECES},
            "requested_at": _now().isoformat(),
        })

    _update(campaign_id, change)


def request_retry(campaign_id: str) -> None:
    """Queue another run: finished pieces (and the opening-seed flag) are kept, the rest are retried."""
    def change(state: dict[str, Any]) -> None:
        if not state.get("pieces"):
            state["pieces"] = {piece: {"status": "pending"} for piece in PIECES}
            state.setdefault("visibility", "surprise")
        state.update({"status": "pending", "requested_at": _now().isoformat(), "started_at": None})

    _update(campaign_id, change)


def set_visibility(campaign_id: str, visibility: str) -> None:
    def change(state: dict[str, Any]) -> None:
        state["visibility"] = visibility

    _update(campaign_id, change)


def hidden_from(campaign: db.Campaign, user_id: int | None) -> bool:
    """True for a player-owner who chose "Keep it a surprise"; the DM and the assigned GM always see it."""
    meta = _meta(campaign)
    state = meta.get("world_skeleton") or {}
    if not state or state.get("visibility") == "show":
        return False
    if user_id is not None and user_id == campaign.gm_user_id:
        return False
    return (meta.get("owner_participation") or {}).get("role") != "dm"


def skeleton_row_ids(campaign: db.Campaign) -> tuple[set[str], set[str]]:
    """(entity ids, hook ids) the skeleton wrote, for filtering GM tooling a surprised owner can call."""
    entity_ids: set[str] = set()
    with Session(db.engine) as s:
        for row in s.exec(select(CampaignEntity).where(CampaignEntity.campaign_id == str(campaign.id))).all():
            if TAG in (row.tags or []):
                entity_ids.add(row.id)
    pieces = (_meta(campaign).get("world_skeleton") or {}).get("pieces") or {}
    hook_ids = set((pieces.get("clock") or {}).get("entity_ids") or [])
    return entity_ids, hook_ids


def is_active(campaign_id: str, state: dict[str, Any]) -> bool:
    """Whether a job is (probably) still working on this state, in this process or another."""
    if is_running(campaign_id):
        return True
    if state.get("status") not in ("pending", "running"):
        return False
    stamp = state.get("started_at") or state.get("requested_at")
    try:
        started = datetime.fromisoformat(str(stamp))
    except ValueError:
        return False
    return (_now() - started).total_seconds() < STALE_AFTER_S


def public_view(state: dict[str, Any], *, reveal: bool = False) -> dict[str, Any]:
    """Status always; contents for a DM (``reveal``) or when the owner chose to see the world."""
    state = _normalized(state)
    view = {
        "status": state["status"],
        "visibility": state["visibility"],
        "pieces": {p: {"status": state["pieces"][p].get("status", "pending")} for p in PIECES},
    }
    for piece in PIECES:  # why a piece fell back to play (model_error, unparseable, invalid, ...)
        reason = state["pieces"][piece].get("reason")
        if reason and view["pieces"][piece]["status"] == "failed":
            view["pieces"][piece]["reason"] = reason
    if reveal or view["visibility"] == "show":
        for piece in PIECES:
            contents = _ready_contents(state, piece)
            if contents is not None:
                view["pieces"][piece]["data"] = contents
    return view


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _ask(call: Callable[..., str | None], system: str, user: str, *, max_tokens: int, timeout: float) -> tuple[dict[str, Any] | None, str]:
    """The parsed answer, and the failure reason to record if it turns out unusable."""
    try:
        raw = call(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            task_scope="taverntails_plot", max_tokens=max_tokens, temperature=0.7, timeout=timeout,
        )
    except Exception:  # noqa: BLE001 - a missing piece stays open and play fills it in
        log.warning("world skeleton call failed", exc_info=True)
        return None, "model_error"
    if not raw:
        return None, "no_answer"
    data = parse_json_object(raw)
    return data, "invalid" if data is not None else "unparseable"


def _prepare_opening_seed(campaign: db.Campaign, truth: dict[str, str] | None, call: Callable[..., str | None], timeout: float) -> dict[str, Any] | None:
    """The first session's opening seed, read from the premise with the truth in mind."""
    from .premise_seed import extract_premise_seed

    meta = _meta(campaign)
    settings = meta.get("settings") or {}
    contract = {**(meta.get("campaign_contract") or {}), "campaign_name": campaign.name}
    seed = extract_premise_seed(settings, contract, complete=call, timeout=timeout, hidden_truth=truth)
    if seed is None and truth is not None:
        # Without the hint, but still checked against the secret.
        seed = extract_premise_seed(settings, contract, complete=call, timeout=timeout, hidden_truth=truth, hint=False)
    return seed


def generate_world_skeleton(
    campaign_id: str,
    *,
    complete: Callable[..., str | None] | None = None,
    timeout: float = 45.0,
) -> dict[str, Any]:
    """Generate every piece that is not ready yet; returns the saved state."""
    found = db.get_campaign_by_id(campaign_id)
    if found is None:
        return {"status": "failed", "reason": "campaign_missing"}
    campaign: db.Campaign = found
    call = complete
    if call is None:
        from ..steward_llm import chat_complete

        call = chat_complete

    state = _state(campaign)
    job: dict[str, Any] = {"status": "running", "started_at": _now().isoformat(), "pieces": state["pieces"]}
    _save(campaign_id, job)
    pieces = job["pieces"]

    meta = _meta(campaign)
    settings = meta.get("settings") or {}
    brief = campaign_brief(campaign)
    truth: dict[str, str] | None = _ready_contents(state, "truth")

    def record(piece: str, value: Any, reason: str) -> None:
        if value is None:
            pieces[piece] = {"status": "failed", "reason": reason}
        else:
            truth_entry = pieces["truth"]
            thread_ids = list(truth_entry.get("entity_ids") or []) if truth_entry.get("status") == "ready" else []
            try:
                ids = _persist(campaign, piece, value, thread_id=thread_ids[0] if thread_ids else None)
            except Exception:  # noqa: BLE001 - nothing was written; the piece can be retried
                log.exception("world skeleton could not save %s campaign=%s", piece, campaign_id)
                pieces[piece] = {"status": "failed", "reason": "persist_error"}
            else:
                # Only published as ready once its rows exist, so a retry never skips a piece play cannot see.
                pieces[piece] = {"status": "ready", "entity_ids": ids}
        _save(campaign_id, job)

    if pieces["truth"].get("status") != "ready":
        data, reason = _ask(call, TRUTH_SYSTEM, brief, max_tokens=420, timeout=timeout)
        truth = validate_truth(data, opening_trouble=clean_text(settings.get("opening_trouble"))) if data else None
        record("truth", truth, reason)
        if pieces["truth"].get("status") != "ready":
            truth = None

    stored = _fresh_state(campaign_id)
    # Only a truth-aware seed is prepared: one made without the truth would be kept after a retry made it.
    if truth is not None and not stored.get("opening_seed") and not stored.get("opening_seed_used"):
        seed = _prepare_opening_seed(campaign, truth, call, timeout)
        if seed:
            job["opening_seed"] = seed
            _save(campaign_id, job)

    if truth is None:
        # Factions, people and the clock are built around the truth; made without it they would not fit the
        # truth a retry produces, and a retry would keep them. Leave them for the retry that has the truth.
        for piece in ("factions", "npcs", "clock"):
            if pieces[piece].get("status") != "ready":
                pieces[piece] = {"status": "failed", "reason": "needs_truth"}
        job["status"] = _overall(pieces)
        job["finished_at"] = _now().isoformat()
        _save(campaign_id, job)
        log.info("world skeleton campaign=%s stopped: no truth", campaign_id)
        return _fresh_state(campaign_id)

    truth_line = f"\nHidden truth (GM only): {truth['hidden_truth']} Who benefits: {truth['who_benefits']}"
    factions: list[dict[str, str]] = _ready_contents(state, "factions") or []
    if pieces["factions"].get("status") != "ready":
        data, reason = _ask(call, FACTIONS_SYSTEM, brief + truth_line, max_tokens=520, timeout=timeout)
        found_factions = validate_factions(data, _card_names(meta, "factions")) if data else None
        record("factions", found_factions, reason)
        factions = found_factions if pieces["factions"].get("status") == "ready" and found_factions else []

    if pieces["npcs"].get("status") != "ready" and pieces["factions"].get("status") != "ready":
        # People are tied to factions; made without them they would not fit the factions a retry makes.
        pieces["npcs"] = {"status": "failed", "reason": "needs_factions"}
        _save(campaign_id, job)
    elif pieces["npcs"].get("status") != "ready":
        faction_names = [f["name"] for f in factions]
        listing = f"\nFactions: {', '.join(faction_names)}" if faction_names else ""
        data, reason = _ask(call, NPCS_SYSTEM, brief + truth_line + listing, max_tokens=700, timeout=timeout)
        found_npcs = validate_npcs(data, _card_names(meta, "people"), faction_names, _card_roles(meta)) if data else None
        record("npcs", found_npcs, reason)

    if pieces["clock"].get("status") != "ready":
        data, reason = _ask(call, CLOCK_SYSTEM, brief + truth_line, max_tokens=300, timeout=timeout)
        clock = validate_clock(data) if data else None
        record("clock", clock, reason)

    job["status"] = _overall(pieces)
    job["finished_at"] = _now().isoformat()
    _save(campaign_id, job)
    log.info("world skeleton campaign=%s status=%s pieces=%s", campaign_id, job["status"],
             {p: pieces[p].get("status") for p in PIECES})
    return _fresh_state(campaign_id)


def run_world_skeleton(campaign_id: str) -> None:
    """Background entry point: at most one job per campaign in this process."""
    with _running_lock:
        if campaign_id in _running:
            return
        _running.add(campaign_id)
    try:
        generate_world_skeleton(campaign_id)
    except Exception:  # noqa: BLE001 - never let a background job take the worker down
        log.exception("world skeleton failed campaign=%s", campaign_id)
        _save(campaign_id, {"status": _overall(_fresh_state(campaign_id)["pieces"])})
    finally:
        with _running_lock:
            _running.discard(campaign_id)


def is_running(campaign_id: str) -> bool:
    with _running_lock:
        return campaign_id in _running


def hidden_truth(campaign: db.Campaign | None) -> dict[str, str] | None:
    """The truth piece, read from its GM-only thread (never from campaign metadata)."""
    if campaign is None:
        return None
    return _ready_contents(_state(campaign), "truth")


TRUTH_WAIT_S = 25.0


def wait_for_opening(campaign: db.Campaign | None, timeout: float = TRUTH_WAIT_S, poll: float = 1.0) -> db.Campaign | None:
    """Give a running job up to ``timeout`` seconds to finish the truth and its opening seed.

    The first questionnaire can be opened while the truth call (about 10 s) is still running. Taking the seed
    slot then would make the first scene ignore the truth for good, so wait a little; the job prepares the seed
    right after the truth. Returns the freshest campaign.
    """
    import time

    if campaign is None:
        return None
    deadline = time.monotonic() + timeout
    while True:
        fresh = db.get_campaign_by_id(str(campaign.id)) or campaign
        state = _state(fresh)
        truth_settled = state["pieces"]["truth"].get("status") != "pending"
        seed_settled = bool(state.get("opening_seed")) or state.get("status") not in ("pending", "running")
        if (truth_settled and seed_settled) or not is_active(str(fresh.id), state) or time.monotonic() >= deadline:
            return fresh
        time.sleep(poll)


def take_opening_seed(campaign: db.Campaign | None) -> dict[str, Any] | None:
    """The prepared opening seed, once.

    The read and the "used" mark happen in one locked transaction, so two sessions opening at the same
    moment cannot both get it. Taking it closes the slot even when nothing was prepared yet: a seed
    finished after the first session opened would otherwise open the second, which should start
    somewhere new.
    """
    if campaign is None:
        return None

    def change(state: dict[str, Any]) -> dict[str, Any] | None:
        if not state or state.get("opening_seed_used"):
            return None
        seed = state.pop("opening_seed", None)
        state["opening_seed_used"] = True
        return seed if isinstance(seed, dict) and seed else None

    return _update(str(campaign.id), change)
