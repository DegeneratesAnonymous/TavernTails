"""Canon Manager — tracks entity canon status and logs changes.

Statuses:
    background          — flavor-only; expires if never reused
    provisional         — AI-inferred; can be promoted by player interaction
    canon               — established in play, confirmed in-world
    player_canon        — user-provided lore or backstory; protected
    confirmed_canon     — player_canon explicitly confirmed in play
    discarded           — removed from active use (not deleted)
    rejected            — contradicts campaign contract; blocked

Rules:
    - Direct user lore and player backstory → player_canon
    - AI-inferred entities → provisional
    - Background flavor expires unless reused in 5 scenes
    - Player interaction promotes provisional → canon
    - Major changes to player_canon require approval
    - All changes are logged
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Status definitions
# ---------------------------------------------------------------------------

CANON_STATUSES = frozenset({
    "background",
    "provisional",
    "canon",
    "player_canon",
    "confirmed_canon",
    "discarded",
    "rejected",
})

_PROMOTION_PATHS: dict[str, list[str]] = {
    "background":       ["provisional", "canon", "discarded"],
    "provisional":      ["canon", "discarded"],
    "canon":            ["confirmed_canon", "discarded"],
    "player_canon":     ["confirmed_canon"],
    "confirmed_canon":  [],
    "discarded":        ["provisional"],
    "rejected":         [],
}

_PROTECTED_STATUSES = frozenset({"player_canon", "confirmed_canon"})

_BACKGROUND_EXPIRY_SCENES = 5


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default if default is not None else {}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Canon record
# ---------------------------------------------------------------------------

def make_canon_record(
    name: str,
    entity_type: str,
    canon_status: str,
    source_scene: str = "",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "type": entity_type,
        "canon_status": canon_status,
        "created_at": _now(),
        "last_updated": _now(),
        "source_scene": source_scene,
        "reuse_count": 0,
        "last_used_scene": source_scene,
        "data": data or {},
        "change_log": [
            {"from": None, "to": canon_status, "at": _now(), "scene": source_scene, "reason": "initial"}
        ],
    }


# ---------------------------------------------------------------------------
# Canon index operations
# ---------------------------------------------------------------------------

def load_canon_index(folder: Path) -> dict[str, Any]:
    """Load the persistent canon index from {folder}/canon_index.json."""
    path = folder / "canon_index.json"
    raw = _read_json(path, {})
    if not isinstance(raw, dict):
        return {}
    return raw


def save_canon_index(folder: Path, index: dict[str, Any]) -> None:
    _write_json(folder / "canon_index.json", index)


def get_entity(index: dict[str, Any], name: str) -> dict[str, Any] | None:
    return index.get(name)


def upsert_entity(
    index: dict[str, Any],
    name: str,
    entity_type: str,
    canon_status: str,
    source_scene: str = "",
    data: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Insert or update an entity. Returns (record, was_new)."""
    existing = index.get(name)
    if existing is None:
        record = make_canon_record(name, entity_type, canon_status, source_scene, data)
        index[name] = record
        return record, True

    existing["reuse_count"] = existing.get("reuse_count", 0) + 1
    existing["last_used_scene"] = source_scene
    existing["last_updated"] = _now()
    if data:
        existing["data"] = {**existing.get("data", {}), **data}
    return existing, False


# ---------------------------------------------------------------------------
# Status promotion
# ---------------------------------------------------------------------------

def can_promote(from_status: str, to_status: str) -> bool:
    return to_status in _PROMOTION_PATHS.get(from_status, [])


def promote_entity(
    index: dict[str, Any],
    name: str,
    new_status: str,
    scene_id: str = "",
    reason: str = "",
    require_approval: bool = False,
) -> dict[str, str | bool]:
    """Promote an entity to a new canon status.

    Returns a result dict with `success`, `blocked_reason`, `old_status`, `new_status`.
    """
    record = index.get(name)
    if record is None:
        return {"success": False, "blocked_reason": f"Entity '{name}' not in canon index."}

    old_status = record.get("canon_status", "provisional")

    if old_status in _PROTECTED_STATUSES and require_approval:
        return {
            "success": False,
            "blocked_reason": f"'{name}' is {old_status} — major changes require approval.",
            "old_status": old_status,
            "new_status": new_status,
            "requires_approval": True,
        }

    if not can_promote(old_status, new_status):
        return {
            "success": False,
            "blocked_reason": f"Cannot promote '{name}' from '{old_status}' to '{new_status}' — not an allowed transition.",
            "old_status": old_status,
            "new_status": new_status,
        }

    record["canon_status"] = new_status
    record["last_updated"] = _now()
    record["change_log"] = record.get("change_log") or []
    record["change_log"].append({
        "from": old_status,
        "to": new_status,
        "at": _now(),
        "scene": scene_id,
        "reason": reason or "promoted",
    })
    return {"success": True, "old_status": old_status, "new_status": new_status}


# ---------------------------------------------------------------------------
# Background expiry
# ---------------------------------------------------------------------------

def expire_stale_background(
    index: dict[str, Any],
    current_scene_number: int,
    expiry_window: int = _BACKGROUND_EXPIRY_SCENES,
) -> list[str]:
    """Discard background entities that haven't been used in expiry_window scenes."""
    discarded = []
    for name, record in index.items():
        if record.get("canon_status") != "background":
            continue
        last_used = record.get("last_used_scene") or ""
        reuse_count = record.get("reuse_count") or 0
        if reuse_count == 0 and current_scene_number > expiry_window:
            record["canon_status"] = "discarded"
            record["change_log"] = record.get("change_log") or []
            record["change_log"].append({
                "from": "background",
                "to": "discarded",
                "at": _now(),
                "scene": f"auto-expiry after scene {current_scene_number}",
                "reason": f"unused for {expiry_window} scenes",
            })
            discarded.append(name)
    return discarded


# ---------------------------------------------------------------------------
# Memory delta → canon index
# ---------------------------------------------------------------------------

def apply_memory_delta(
    index: dict[str, Any],
    memory_delta: dict[str, Any],
    scene_id: str = "",
    campaign_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply a memory extractor delta to the canon index.

    Returns a summary of changes: {new, updated, promoted, conflicts}.
    """
    new: list[str] = []
    updated: list[str] = []
    conflicts: list[dict[str, Any]] = []

    # Player canon from campaign contract (always highest priority)
    player_canon_names: set[str] = set()
    for entity in (campaign_contract or {}).get("player_canon") or []:
        if isinstance(entity, dict) and entity.get("name"):
            player_canon_names.add(entity["name"])

    def _ingest(name: str, entity_type: str, default_status: str, data: dict[str, Any] | None = None) -> None:
        status = "player_canon" if name in player_canon_names else default_status
        record, was_new = upsert_entity(index, name, entity_type, status, scene_id, data)
        if was_new:
            new.append(name)
        else:
            updated.append(name)

    for npc in (memory_delta.get("new_npcs") or []):
        name = npc.get("name") if isinstance(npc, dict) else str(npc)
        data = {k: v for k, v in (npc if isinstance(npc, dict) else {}).items() if k != "name"}
        if name:
            _ingest(name, "npc", "provisional", data)

    for npc in (memory_delta.get("updated_npcs") or []):
        name = npc.get("name") if isinstance(npc, dict) else str(npc)
        if name:
            _ingest(name, "npc", "provisional")

    for loc in (memory_delta.get("new_locations") or []):
        name = loc.get("name") if isinstance(loc, dict) else str(loc)
        data = {k: v for k, v in (loc if isinstance(loc, dict) else {}).items() if k != "name"}
        if name:
            _ingest(name, "location", "provisional", data)

    for loc in (memory_delta.get("updated_locations") or []):
        name = loc.get("name") if isinstance(loc, dict) else str(loc)
        if name:
            _ingest(name, "location", "provisional")

    # Check for canon violations: AI-generated entity with same name as player_canon but different type
    for name in new:
        record = index.get(name)
        if not record:
            continue
        if name in player_canon_names and record.get("canon_status") == "provisional":
            record["canon_status"] = "player_canon"
            conflicts.append({"name": name, "issue": "promoted to player_canon (matched campaign contract)"})

    return {"new": new, "updated": updated, "conflicts": conflicts}


# ---------------------------------------------------------------------------
# Canon violation checker
# ---------------------------------------------------------------------------

def check_canon_violations(
    narrative_text: str,
    index: dict[str, Any],
    campaign_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Check prose text for entities that contradict canon facts.

    Returns a list of violation dicts: {name, issue, severity}.
    """
    violations: list[dict[str, Any]] = []
    if not campaign_contract:
        return violations

    player_canon = campaign_contract.get("player_canon") or []
    for entity in player_canon:
        if not isinstance(entity, dict):
            continue
        name = entity.get("name") or ""
        entity_type = entity.get("type") or ""
        if not name:
            continue
        # Simple: check that if a player-canon NPC is mentioned, they aren't described as a location etc.
        if name in narrative_text:
            record = index.get(name)
            if record and record.get("type") and entity_type and record["type"] != entity_type:
                violations.append({
                    "name": name,
                    "issue": f"entity type mismatch: canon says '{entity_type}', index has '{record['type']}'",
                    "severity": "warning",
                })

    return violations


# ---------------------------------------------------------------------------
# Backstory boundary checker
# ---------------------------------------------------------------------------

def check_backstory_boundaries(
    narrative_text: str,
    campaign_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Check that narrative doesn't violate backstory privacy boundaries."""
    violations: list[dict[str, Any]] = []
    if not campaign_contract:
        return violations

    backstory_profiles = campaign_contract.get("backstory_profiles") or []
    for profile in backstory_profiles:
        if not isinstance(profile, dict):
            continue
        private_facts = profile.get("private_facts") or []
        for fact in private_facts:
            if isinstance(fact, str) and fact.lower() in narrative_text.lower():
                violations.append({
                    "name": profile.get("character_name") or "unknown",
                    "issue": f"private backstory fact exposed in narrative: '{fact[:60]}'",
                    "severity": "error",
                })
    return violations


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------

def validate_canon(
    narrative_text: str,
    index: dict[str, Any],
    campaign_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run all canon validators and return a combined report."""
    violations = check_canon_violations(narrative_text, index, campaign_contract)
    backstory_violations = check_backstory_boundaries(narrative_text, campaign_contract)
    all_issues = violations + backstory_violations
    errors = [v for v in all_issues if v.get("severity") == "error"]
    return {
        "valid": len(errors) == 0,
        "score": max(0, 100 - len(all_issues) * 15),
        "issues": all_issues,
        "recommended_fix": errors[0]["issue"] if errors else "",
    }
