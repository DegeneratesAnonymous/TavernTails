"""Braid each character's backstory (the B plot) into the campaign's main trouble (the A plot).

A character's backstory builder collects goals, ties and a required link to the world's main trouble.  Before a
session starts, this module reads those threads next to the world skeleton's hidden truth and factions and writes,
for each character, a GM-only story thread: how the main trouble touches their goal, what it does to that goal if
nobody acts, and one scene idea that serves both.  The threads are ordinary ``story_thread`` memory rows, so the
context orchestrator offers them to the scene writers the same way it offers the skeleton's own.

The model's answer is only a draft.  A connection that names nothing from the world, or a name nobody supplied,
is replaced by a plain sentence built from what the player chose; a thread is rebuilt only when its inputs change.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from .. import db, steward_llm
from ..db import CampaignChangeLog, CampaignEntity
from . import world_skeleton
from .campaign_card import name_in_text
from .generation_intent import clean_text, content_tokens
from .lifepath import invented_names
from .premise_seed import parse_json_object

logger = logging.getLogger("taverntails.thread_weaver")

TAG = "b_plot"
MAX_FIELD = 240
TERMS = ("long", "mid", "short")


# ---------------------------------------------------------------------------
# Reading the threads
# ---------------------------------------------------------------------------

def _goals(raw: Any) -> list[dict[str, str]]:
    out = []
    for goal in raw if isinstance(raw, list) else []:
        if isinstance(goal, dict) and clean_text(goal.get("text")):
            if goal.get("status") not in ("done", "dropped"):  # finished and abandoned goals no longer drive scenes
                out.append({k: clean_text(goal.get(k)) for k in ("term", "text", "because", "but")})
    return sorted(out, key=lambda g: TERMS.index(g["term"]) if g["term"] in TERMS else 1)


def _strings(raw: Any) -> list[str]:
    items = raw if isinstance(raw, list) else re.split(r"[\n;]+", str(raw or ""))
    return [clean_text(i) for i in items if clean_text(i)]


def _pick(entry: dict[str, Any], sheet: dict[str, Any], key: str, sheet_key: str | None = None) -> Any:
    """The campaign's own value when it has the field at all (an empty one is a choice); else the sheet's."""
    return entry[key] if key in entry else sheet.get(sheet_key or key)


def character_threads(campaign: db.Campaign | None, members: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One thread per seated character that has goals, ties or a link.

    A backstory kept for this campaign only overrides the character's own sheet for that campaign.
    """
    meta = dict(campaign.metadata_json or {}) if campaign else {}
    kept = {str(b.get("character_id")): b for b in meta.get("player_backstories") or [] if isinstance(b, dict)}
    threads: list[dict[str, Any]] = []
    seen: set[int] = set()
    for member in members or []:
        try:
            char_id = int(str(member.get("character_id")))
        except ValueError:
            continue
        if char_id in seen:
            continue
        seen.add(char_id)
        character = db.get_character_by_id(char_id)
        if character is None:
            continue
        sheet = character.sheet if isinstance(character.sheet, dict) else {}
        entry = kept.get(str(char_id), {})

        link = _pick(entry, sheet, "link", "backstory_link") or None
        thread = {
            "character_id": char_id,
            "name": character.name or "",
            "backstory": clean_text(_pick(entry, sheet, "backstory"))[:500],
            "goals": _goals(_pick(entry, sheet, "goals")),
            "allies": _strings(_pick(entry, sheet, "allies")),
            "rivals": _strings(_pick(entry, sheet, "rivals")),
            "patron": clean_text(_pick(entry, sheet, "patron")),
            "link": {"kind": str(link.get("kind", "")), "name": clean_text(link.get("name"))} if isinstance(link, dict) else None,
        }
        if thread["goals"] or thread["allies"] or thread["rivals"] or thread["patron"] or thread["link"]:
            threads.append(thread)
    return threads


def thread_block(thread: dict[str, Any]) -> str:
    """The thread as a campaign-doc block for the storyboard: what the table is told about this character."""
    lines = [f"[Character thread: {thread['name']}]"]
    for goal in thread["goals"]:
        extra = (f" because {goal['because']}" if goal["because"] else "") + (f", but {goal['but']}" if goal["but"] else "")
        lines.append(f"{goal['term'].capitalize()} goal: {goal['text']}{extra}")
    for label, key in (("Allies", "allies"), ("Rivals", "rivals")):
        if thread[key]:
            lines.append(f"{label}: {', '.join(thread[key])}")
    if thread["patron"]:
        lines.append(f"Patron: {thread['patron']}")
    link = thread["link"]
    if link and link["kind"] != "story" and link["name"]:
        lines.append(f"Touches the main trouble through: {link['name']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Weaving
# ---------------------------------------------------------------------------

def _long_goal(thread: dict[str, Any]) -> str:
    goals = thread["goals"]
    return goals[0]["text"] if goals else ""


def _fallback(thread: dict[str, Any], truth: dict[str, str] | None) -> dict[str, str]:
    """A plain thread built only from what the player chose and the world's own names."""
    name = thread["name"] or "The character"
    link = thread["link"] if thread["link"] and thread["link"]["kind"] != "story" else None
    anchor = (link or {}).get("name") or (truth or {}).get("thread_name") or "the main trouble"
    goal = _long_goal(thread) or "their own aims"
    short = thread["goals"][-1]["text"] if thread["goals"] else goal
    return {
        "connection": f"{name}'s goal ({goal}) runs into {anchor}.",
        "complication": f"If no one acts, {anchor} worsens and {goal} gets harder to reach.",
        "beat": f"Let {name} meet a consequence of {anchor} while working toward: {short}.",
    }


def _world_names(truth: dict[str, str] | None, factions: list[dict[str, str]], npcs: list[dict[str, str]]) -> list[str]:
    names = [f["name"] for f in factions] + [n["name"] for n in npcs]
    if truth and truth.get("thread_name"):
        names.append(truth["thread_name"])
    return [n for n in names if n]


def _supplied(threads: list[dict[str, Any]], truth: dict[str, str] | None, factions: list[dict[str, str]],
              npcs: list[dict[str, str]], campaign_name: str) -> str:
    parts = [campaign_name, json.dumps(threads), json.dumps(truth or {}), json.dumps(factions), json.dumps(npcs)]
    return " ".join(parts)


def _touches_world(text: str, thread: dict[str, Any], names: list[str], truth: dict[str, str] | None) -> bool:
    if any(name_in_text(n, text) for n in names):
        return True
    link = thread["link"]
    if link and link["name"] and link["kind"] != "story" and content_tokens(link["name"]) & content_tokens(text):
        return True
    return bool(truth and len(content_tokens(truth.get("hidden_truth", "") + " " + truth.get("thread_name", "")) & content_tokens(text)) >= 2)


def _messages(threads: list[dict[str, Any]], truth: dict[str, str] | None, factions: list[dict[str, str]],
              npcs: list[dict[str, str]]) -> list[dict[str, str]]:
    system = (
        "You are the game master's private planner. Each character below has a personal story (goals, ties, a link to the "
        "main trouble). Connect each one to the main trouble. Reply with ONLY a JSON object: "
        '{"threads":[{"id":<the number given for the character>,"character":"<name>","connection":"how the hidden truth or a faction touches this character\'s goal",'
        '"complication":"what the main trouble does to their goal if nobody acts","beat":"one scene idea that serves both"}]}. '
        f"Each value is one plain sentence under {MAX_FIELD} characters. Use only the names listed. Do not invent people, "
        "places or groups. Do not give the character new goals."
    )
    world: list[str] = []
    if truth:
        world += [f"Main trouble: {truth.get('thread_name')} - {truth.get('visible_problem')}", f"Hidden truth: {truth.get('hidden_truth')}"]
    world += [f"Faction {f['name']}: wants {f['wants']}" for f in factions]
    world += [f"Person {n['name']} ({n.get('role', '')}): {n.get('wants', '')}" for n in npcs]
    chars = [
        f"- id {t['character_id']}, {t['name']}: " + "; ".join(
            [*(f"{g['term']} goal: {g['text']}" for g in t["goals"]),
             *( [f"link: {t['link']['name']}"] if t["link"] and t["link"]["name"] else [] ),
             *( [f"allies: {', '.join(t['allies'])}"] if t["allies"] else [] ),
             *( [f"rivals: {', '.join(t['rivals'])}"] if t["rivals"] else [] )])
        for t in threads
    ]
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join([*world, "Characters:", *chars])}]


def weave(threads: list[dict[str, Any]], truth: dict[str, str] | None, factions: list[dict[str, str]],
          npcs: list[dict[str, str]], campaign_name: str = "", *, call: Callable[..., Any] | None = None) -> dict[int, dict[str, str]]:
    """``{character_id: {connection, complication, beat, source}}`` for every thread, drafts checked, gaps filled."""
    result: dict[int, dict[str, str]] = {}
    drafts: dict[str, dict[str, Any]] = {}
    if threads and (truth or factions):
        ask = call or steward_llm.chat_complete
        try:
            raw = ask(_messages(threads, truth, factions, npcs), task_scope="taverntails_plot", max_tokens=700, temperature=0.6, timeout=60.0)
            data = parse_json_object(str(raw or "")) or {}
            for item in data.get("threads") or []:
                if isinstance(item, dict):
                    key = str(item.get("id", "")).strip() or clean_text(item.get("character")).casefold()
                    drafts[key] = item
        except Exception:
            logger.exception("thread weave call failed")
    by_name: dict[str, int] = {}
    for t in threads:
        by_name[t["name"].casefold()] = by_name.get(t["name"].casefold(), 0) + 1
    names = _world_names(truth, factions, npcs)
    supplied = _supplied(threads, truth, factions, npcs, campaign_name)
    for thread in threads:
        draft = drafts.get(str(thread["character_id"]))
        if draft is None and by_name[thread["name"].casefold()] == 1:  # a name identifies a draft only when it is unique
            draft = drafts.get(thread["name"].casefold())
        fields = {k: clean_text((draft or {}).get(k))[:MAX_FIELD] for k in ("connection", "complication", "beat")}
        ok = bool(draft) and all(fields.values())
        if ok:
            joined = ". ".join(fields.values())
            ok = not invented_names(joined, supplied) and "?" not in joined and _touches_world(fields["connection"], thread, names, truth)
        result[thread["character_id"]] = {**(fields if ok else _fallback(thread, truth)), "source": "model" if ok else "template"}
    return result


# ---------------------------------------------------------------------------
# Persisting
# ---------------------------------------------------------------------------

def _row_id(campaign_id: str, character_id: int) -> str:
    return f"bplot-{campaign_id}-{character_id}"[:120]


def _signature(thread: dict[str, Any], truth: dict[str, str] | None, factions: list[dict[str, str]]) -> str:
    blob = json.dumps({"t": thread, "truth": (truth or {}).get("hidden_truth", ""), "f": [f["name"] for f in factions]}, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def ensure_threads(campaign: db.Campaign | None, members: Iterable[dict[str, Any]], *, call: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    """Make sure each seated character's B-plot row is current.  Returns the threads that were read."""
    if campaign is None:
        return []
    threads = character_threads(campaign, members)
    if not threads:
        return []
    state = world_skeleton._state(campaign)
    truth = world_skeleton._ready_contents(state, "truth")
    factions = world_skeleton._ready_contents(state, "factions") or []
    npcs = world_skeleton._ready_contents(state, "npcs") or []
    campaign_id = str(campaign.id)
    with Session(db.engine) as s:
        existing = {t["character_id"]: s.get(CampaignEntity, _row_id(campaign_id, t["character_id"])) for t in threads}
    def current(thread: dict[str, Any]) -> bool:
        row = existing[thread["character_id"]]
        return row is not None and (row.data or {}).get("signature") == _signature(thread, truth, factions)

    stale = [t for t in threads if not current(t)]
    if not stale:
        return threads
    woven = weave(stale, truth, factions, npcs, campaign.name or "", call=call)
    now = datetime.now(timezone.utc)
    with Session(db.engine) as s:
        if s.get(db.Campaign, campaign_id) is None:
            return threads
        for thread in stale:
            out = woven[thread["character_id"]]
            goal = _long_goal(thread)
            data = {
                "current_situation": f"{thread['name']} wants to {goal}." if goal else f"{thread['name']} has a stake in the main trouble.",
                "stakes": out["complication"],
                "gm_notes": out["connection"],
                "primary_goal": goal,
                "story_engine": out["connection"],
                "next_recommended_dm_move": out["beat"],
                "current_priority": 6,
                "provenance": "user",
                "plot": "B",
                "character_id": thread["character_id"],
                "weave_source": out["source"],
                "link": thread["link"],
                "signature": _signature(thread, truth, factions),
            }
            row = s.get(CampaignEntity, _row_id(campaign_id, thread["character_id"]))
            name = f"{thread['name']}'s story"
            if row is None:
                s.add(CampaignEntity(
                    id=_row_id(campaign_id, thread["character_id"]), campaign_id=campaign_id, entity_type="story_thread", name=name,
                    status="active", visibility="gm_only", tags=[TAG], data=data, created_at=now, updated_at=now,
                ))
            else:
                before = dict(row.data or {})
                row.data, row.name, row.updated_at, row.status = data, name, now, "active"
                s.add(row)
                s.add(CampaignChangeLog(
                    id=uuid.uuid4().hex[:12], campaign_id=campaign_id, entity_id=row.id, change_type="update",
                    summary=f"Backstory thread rewoven for {thread['name']}", before_data=before, after_data=data,
                    caused_by_player_action=False, created_at=now,
                ))
        s.commit()
    return threads


def b_plot_rows(campaign_id: str, character_ids: Iterable[int] | None = None) -> list[CampaignEntity]:
    """The campaign's active B-plot rows, limited to ``character_ids`` (the session's roster) when given."""
    wanted = None if character_ids is None else {int(c) for c in character_ids}
    with Session(db.engine) as s:
        rows = s.exec(select(CampaignEntity).where(
            CampaignEntity.campaign_id == campaign_id, CampaignEntity.entity_type == "story_thread", CampaignEntity.status == "active",
        )).all()
        return [r for r in rows if TAG in (r.tags or []) and (wanted is None or int((r.data or {}).get("character_id", -1)) in wanted)]


def refresh_after_goal_change(campaign_id: str, character_id: int, goals: list[dict[str, Any]]) -> None:
    """A goal changed: bring the character's stored thread in line now, and have it rewoven at the next session start.

    Finished and dropped goals stop driving scenes at once; with none left the thread is resolved.
    """
    active = _goals(goals)
    with Session(db.engine) as s:
        row = s.get(CampaignEntity, _row_id(campaign_id, character_id))
        if row is None:
            missing = True
        else:
            missing = False
            data = dict(row.data or {})
            name = row.name.removesuffix("'s story")
            data["signature"] = ""
    if missing:
        # A first goal added during play: write the thread now (from the player's own words), and reweave it at the next start.
        if active:
            ensure_threads(db.get_campaign_by_id(campaign_id), [{"character_id": character_id}], call=lambda *a, **k: None)
        return
    with Session(db.engine) as s:
        row = s.get(CampaignEntity, _row_id(campaign_id, character_id))
        if row is None:
            return
        if active:
            # Everything that came from the old goal goes with it: the connection, the complication and the scene idea.
            plain = _fallback({"name": name, "goals": active, "link": data.get("link")}, None)
            data.update({
                "current_situation": f"{name} wants to {active[0]['text']}.", "primary_goal": active[0]["text"],
                "gm_notes": plain["connection"], "story_engine": plain["connection"],
                "stakes": plain["complication"], "next_recommended_dm_move": plain["beat"], "weave_source": "template",
            })
            row.status = "active"
        else:
            row.status = "resolved"
        row.data, row.updated_at = data, datetime.now(timezone.utc)
        s.add(row)
        s.commit()
