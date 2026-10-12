"""Per-table state the generation pipeline reads: what the table did this round, and what it asked the story to avoid.

Kept free of route and session imports so ``sessions`` can use it while ``session_assist`` (which imports
``sessions``) serves the routes.
"""
from __future__ import annotations

from typing import Any


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def round_recap(messages: list, roll_entries: list[dict] | None = None) -> dict[str, Any]:
    """What the table did this round, shown with the scene it led to, so every action visibly mattered."""
    actions = [
        {"by": _clean(m.sender_name) or "Player", "text": _clean(m.message)}
        for m in messages
        if getattr(m, "role", "") not in ("gm", "narrator", "system") and _clean(getattr(m, "message", ""))
    ]
    rolls = [
        {"by": _clean((r.get("roll") or {}).get("by")) or "Player", "expression": (r.get("roll") or {}).get("expression", ""),
         "total": (r.get("roll") or {}).get("total")}
        for r in (roll_entries or []) if r.get("type") == "roll"
    ]
    return {"actions": actions[:12], "rolls": rolls[:12]}


def table_safety(meta: dict) -> dict[str, Any]:
    raw = meta.get("table_safety")
    return raw if isinstance(raw, dict) else {"avoid": [], "events": [], "paused": False}


def with_table_safety(contract: dict, meta: dict) -> dict:
    """The campaign contract with anything the table asked the story to leave out, so the next scene honours it."""
    avoid = [a for a in table_safety(meta).get("avoid", []) if _clean(a)]
    if not avoid:
        return contract
    policy = dict(contract.get("safety_policy") or {})
    policy["table_avoid"] = list(dict.fromkeys([*(policy.get("table_avoid") or []), *avoid]))
    rule = "TABLE SAFETY: the players asked the story to leave out, and not depict or hint at: " + "; ".join(avoid) + "."
    return {**contract, "safety_policy": policy, "agent_output_contract": f"{rule}\n{contract.get('agent_output_contract') or ''}".strip()}
