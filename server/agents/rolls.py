import json
import random
import re
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..realtime import broadcaster

router = APIRouter(tags=["rolls"])


class RollRequest(BaseModel):
    expression: str
    reason: str | None = None
    session_id: str | None = None


def _parse_roll(expr: str) -> dict[str, Any]:
    # Simple parser: supports NdM +/- K
    m = re.fullmatch(r"(\d*)d(\d+)([+-]\d+)?", expr.replace(' ', ''))
    if not m:
        raise ValueError("Invalid roll expression")
    n = int(m.group(1) or '1')
    sides = int(m.group(2))
    mod = int(m.group(3) or '0')
    return {'n': n, 'sides': sides, 'mod': mod}


def _roll(n: int, sides: int) -> list[int]:
    return [random.randint(1, sides) for _ in range(n)]


def _coerce_roll_values(raw: Any) -> list[int]:
    if raw is None:
        return []
    payload = raw
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = [payload]
    if not isinstance(payload, list):
        payload = [payload]
    values: list[int] = []
    for entry in payload:
        candidate = entry
        if isinstance(entry, dict):
            candidate = entry.get('value') or entry.get('result') or entry.get('total') or entry.get('die')
        try:
            values.append(int(candidate))
        except (TypeError, ValueError):
            continue
    return values


def _normalize_beyond20_payload(payload: dict[str, Any]) -> dict[str, Any]:
    expr = (payload.get('expression') or payload.get('label') or payload.get('name') or '').strip()
    rolls = _coerce_roll_values(payload.get('rolls') or payload.get('dice') or payload.get('results'))
    try:
        raw_mod = payload.get('modifier') if payload.get('modifier') is not None else payload.get('mod')
        mod = int(raw_mod) if raw_mod is not None else 0
    except (TypeError, ValueError):
        mod = 0
    total = payload.get('total')
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None
    if total is None and rolls:
        total = sum(rolls) + mod
    if total is None and expr:
        try:
            parsed = _parse_roll(expr)
            rolls = _roll(parsed['n'], parsed['sides'])
            mod = parsed['mod']
            total = sum(rolls) + mod
        except ValueError:
            total = 0
    by = payload.get('player') or payload.get('character') or payload.get('by') or 'Beyond20'
    reason = payload.get('reason') or payload.get('label') or payload.get('title')
    return {
        'expression': expr,
        'rolls': rolls,
        'mod': mod,
        'total': int(total or 0),
        'by': by,
        'reason': reason,
        'source': 'beyond20',
    }


def _extract_from_b20_roll_obj(roll_obj: Dict[str, Any]) -> Tuple[str, List[int], int, int]:
    """Extract (formula, rolls, mod, total) from a Beyond20 Roll object."""
    formula = (roll_obj.get("formula") or "").strip()
    parts = roll_obj.get("parts")
    op = 1
    rolls: List[int] = []
    mod = 0
    total_calc = 0

    if isinstance(parts, list):
        for part in parts:
            if part == "+":
                op = 1
                continue
            if part == "-":
                op = -1
                continue
            if isinstance(part, (int, float)):
                val = int(part)
                mod += op * val
                total_calc += op * val
                continue
            if isinstance(part, str):
                s = part.strip()
                if s in {"+", "-"}:
                    op = 1 if s == "+" else -1
                    continue
                try:
                    val = int(s)
                except ValueError:
                    continue
                mod += op * val
                total_calc += op * val
                continue
            if isinstance(part, dict):
                raw_rolls = part.get("rolls")
                if isinstance(raw_rolls, list):
                    for r in raw_rolls:
                        if not isinstance(r, dict):
                            continue
                        if r.get("discarded") is True:
                            continue
                        try:
                            die_val = int(r.get("roll") or 0)
                        except (TypeError, ValueError):
                            continue
                        rolls.append(op * die_val)
                        total_calc += op * die_val

    total = roll_obj.get("total")
    try:
        total_int = int(total) if total is not None else int(total_calc)
    except (TypeError, ValueError):
        total_int = int(total_calc)

    # Keep mod consistent with total if possible
    dice_sum = sum(rolls)
    mod = total_int - dice_sum
    return formula, rolls, int(mod), int(total_int)


def _normalize_beyond20_dom_event(payload: Dict[str, Any], *, fallback_by: str) -> Dict[str, Any]:
    """Normalize Beyond20 DOM event payloads (roll / rendered-roll) into TavernTails roll shape."""
    action = (payload.get("action") or "").strip().lower()
    if action not in {"roll", "rendered-roll"}:
        # Fall back to old, simpler normalizer (supports expression/rolls/total, etc.)
        out = _normalize_beyond20_payload(payload)
        if not out.get("by"):
            out["by"] = fallback_by
        return out

    if action == "roll":
        roll_req: Dict[str, Any] = payload
        roll_character_raw = roll_req.get("character")
        roll_character: Dict[str, Any] = roll_character_raw if isinstance(roll_character_raw, dict) else {}
        by = (roll_character.get("name") or roll_req.get("player") or roll_req.get("by") or fallback_by)
        expr = (roll_req.get("roll") or roll_req.get("modifier") or roll_req.get("name") or roll_req.get("type") or "").strip()
        reason = roll_req.get("name") or roll_req.get("type")
        # No dice results available; let the backend parser roll if possible.
        return _normalize_beyond20_payload({
            "expression": expr,
            "rolls": [],
            "mod": 0,
            "total": None,
            "by": by,
            "reason": reason,
            "source": "beyond20",
        })

    # rendered-roll
    req_raw = payload.get("request")
    req: Dict[str, Any] = req_raw if isinstance(req_raw, dict) else {}

    character_raw = payload.get("character")
    character: Dict[str, Any] = character_raw if isinstance(character_raw, dict) else {}
    if not character:
        req_character_raw = req.get("character")
        if isinstance(req_character_raw, dict):
            character = req_character_raw
    by = (character.get("name") or req.get("player") or req.get("by") or fallback_by)
    title = (payload.get("title") or req.get("name") or req.get("type") or "Roll").strip()

    attack_rolls = payload.get("attack_rolls")
    chosen: Dict[str, Any] | None = None
    if isinstance(attack_rolls, list) and attack_rolls:
        for item in attack_rolls:
            candidate: Dict[str, Any] | None = None
            if isinstance(item, dict):
                candidate = item
            elif isinstance(item, list) and len(item) >= 1 and isinstance(item[0], dict):
                candidate = item[0]
            elif isinstance(item, list) and len(item) >= 2 and isinstance(item[1], dict):
                candidate = item[1]
            if candidate and not candidate.get("discarded"):
                chosen = candidate
                break

    if not chosen:
        # Fall back to a dice formula if no structured roll is available
        expr = (req.get("roll") or title or "Roll").strip()
        return _normalize_beyond20_payload({
            "expression": expr,
            "rolls": [],
            "mod": 0,
            "total": None,
            "by": by,
            "reason": title,
            "source": "beyond20",
        })

    formula, rolls, mod, total = _extract_from_b20_roll_obj(chosen)
    expr = formula or (req.get("roll") or title)
    return {
        "expression": expr,
        "rolls": rolls,
        "mod": mod,
        "total": total,
        "by": by,
        "reason": title,
        "source": "beyond20",
    }


@router.post('/rolls')
async def do_roll(req: RollRequest, current_user=Depends(get_current_user)):
    try:
        parsed = _parse_roll(req.expression)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    rolls = _roll(parsed['n'], parsed['sides'])
    total = sum(rolls) + parsed['mod']
    result = {
        'expression': req.expression,
        'rolls': rolls,
        'mod': parsed['mod'],
        'total': total,
        'by': getattr(current_user, 'email', None) or getattr(current_user, 'username', None),
    }
    # persist the roll
    from .. import db
    by = result.get('by')
    campaign_id = None
    try:
        db.create_roll(campaign_id=campaign_id, expression=req.expression, rolls=rolls, mod=parsed['mod'], total=total, by=by)
    except Exception:
        # non-fatal on persistence failure
        pass
    if req.session_id:
        await broadcaster.broadcast_json(req.session_id, {
            'type': 'rolls.result',
            'session_id': req.session_id,
            'result': result,
        })
    return {'result': result}


@router.post('/integrations/beyond20/roll')
async def ingest_beyond20(payload: dict[str, Any] = Body(...)):
    session_id = payload.get('session_id')
    result = _normalize_beyond20_payload(payload)
    from .. import db
    try:
        db.create_roll(
            campaign_id=payload.get('campaign_id'),
            expression=result['expression'],
            rolls=result['rolls'],
            mod=result['mod'],
            total=result['total'],
            by=result['by'],
        )
    except Exception:
        pass
    envelope = {
        'type': 'rolls.result',
        'session_id': session_id,
        'result': result,
        'source': 'beyond20',
    }
    if session_id:
        await broadcaster.broadcast_json(session_id, envelope)
        await broadcaster.broadcast_json(session_id, {
            'type': 'beyond20.roll',
            'session_id': session_id,
            'expression': result['expression'],
            'total': result['total'],
            'by': result['by'],
            'reason': result.get('reason') or payload.get('reason'),
        })
    return {'result': result}


@router.post('/integrations/beyond20/roll/relay')
async def ingest_beyond20_relay(
    payload: Dict[str, Any] = Body(...),
    x_relay_token: str | None = Header(default=None, alias='X-Relay-Token'),
):
    from .. import db

    token = (x_relay_token or payload.get("relay_token") or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing relay token")
    user = db.get_user_by_beyond20_relay_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid relay token")

    session_id = payload.get('session_id')
    b20_raw = payload.get("beyond20")
    b20: Dict[str, Any] = b20_raw if isinstance(b20_raw, dict) else (payload if isinstance(payload, dict) else {})
    fallback_by = (user.profile or {}).get("name") or user.email or user.username or "Beyond20"
    result = _normalize_beyond20_dom_event(b20, fallback_by=fallback_by)

    try:
        db.create_roll(
            campaign_id=payload.get('campaign_id'),
            expression=result['expression'],
            rolls=result['rolls'],
            mod=result['mod'],
            total=result['total'],
            by=result['by'],
        )
    except Exception:
        pass

    envelope = {
        'type': 'rolls.result',
        'session_id': session_id,
        'result': result,
        'source': 'beyond20',
    }
    if session_id:
        await broadcaster.broadcast_json(session_id, envelope)
        await broadcaster.broadcast_json(session_id, {
            'type': 'beyond20.roll',
            'session_id': session_id,
            'expression': result['expression'],
            'total': result['total'],
            'by': result['by'],
            'reason': result.get('reason'),
        })
    return {'result': result}
