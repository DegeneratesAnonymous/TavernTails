import json
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
from .situation_classifier import classify_situation, REQUIRES_CONTRACT
from .content_bundles import build_content_bundle
from .memory_extractor import extract_memory
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
) -> dict:
    """Deterministic action-result narration when the LLM cannot produce prose."""
    pc = player_name or "you"
    loc = location_name or "the current location"
    action = (latest_action or "").strip()
    lower = action.lower()
    context = f"{loc} {action}".lower()

    title = "The Next Move"
    objective = f"Turn {action[:80] or 'the latest move'} into a concrete advantage at {loc}."
    stakes = "The situation is still moving; delay will let someone else define what this moment means."
    clues = [
        "One nearby detail does not match the explanation people are giving.",
        "Someone present reacts before they can hide it.",
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
                "Yungmin can feel the choice narrowing. Leaving now may keep the escapees ahead of the army, "
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
                "Wind drags old leaves across the camp's border. Under that dry scraping, Yungmin hears a second "
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
        body = (
            f"{pc}'s question lands harder than expected. The first answer is too quick, too polished, and the second "
            "comes only after an uncomfortable silence.\n\n"
            "The useful part is not the words. It is the glance that follows them: toward a person, door, object, or route "
            "that everyone else has been carefully pretending is ordinary.\n\n"
            "Someone nearby notices that glance and changes posture, one shoulder turning as if to hide what their hands "
            "are doing. The room keeps breathing, but it is no longer relaxed.\n\n"
            "There is a narrow opening now. Press too softly and it closes. Press too hard and the person with the truth "
            "may bolt before Yungmin can learn why they are afraid."
        )
        objective = "Use the nervous glance to identify who or what is being protected."
        clues = ["The first answer is rehearsed.", "A nervous glance points toward a hidden priority.", "Someone is withholding the useful part of the truth."]
        actions = ["Follow the glance", "Ask a sharper follow-up", "Separate the nervous witness", "Offer protection for honesty"]
    elif any(word in lower for word in ("search", "inspect", "examine", "investigate", "track", "look")):
        title = "The Detail Out of Place"
        body = (
            f"{pc} slows down and lets the scene become physical: scuffs, dust, disturbed edges, a mark where a hand rested "
            "too long. The obvious story starts to separate from the real one.\n\n"
            "The clearest sign is small, but fresh. It points away from the center of attention and toward the route someone "
            "used when they thought no one would be looking.\n\n"
            "Once seen, the route becomes hard to ignore. A smear breaks the pattern of the floor. A thread catches on a rough "
            "edge. Even the bystanders seem arranged to keep eyes away from that direction.\n\n"
            "The evidence will not stay clean for long. Every passing footstep makes the real trail look more like noise."
        )
        objective = "Follow the fresh sign before the trail is disturbed."
        clues = ["The obvious story is incomplete.", "A fresh physical sign points away from the center of attention.", "Someone used a less visible route."]
        actions = ["Follow the sign", "Preserve the evidence", "Compare it to nearby surfaces", "Ask who had access"]
    elif any(word in lower for word in ("watch", "scan", "observe", "listen")):
        title = "What Moves First"
        body = (
            f"{pc} waits instead of filling the silence. That patience catches what movement would have missed: one person "
            "reacts to the wrong detail, and another notices that reaction before looking away.\n\n"
            "The room has a pattern now. Fear near the center, calculation near the edge, and a narrow gap where someone may slip out.\n\n"
            "A sleeve brushes against a pouch. A boot turns toward the nearest exit. Someone who should be relieved looks "
            "angry instead, as though Yungmin has accidentally stepped on the one part of the truth they needed buried.\n\n"
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
            "Yungmin has room for one clean follow-up before the moment disperses: press the witness, secure the detail, or "
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


def create_session_folder(name: str, owner_email: str, invites=None, campaign_id: str | None = None):
    """Create a session folder programmatically and return the session id and meta."""
    sid = uuid.uuid4().hex[:8]
    folder = BASE / sid
    if folder.exists():
        raise Exception('Session id collision')
    folder.mkdir(parents=True)
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
                'character_id': None,
                'role': 'owner'
            }
        ]
    }
    (folder / 'meta.json').write_text(json.dumps(meta))
    (folder / 'notes.md').write_text(f'# Notes for {name}\n')
    (folder / 'npcs.json').write_text('[]')
    (folder / 'pcs.json').write_text('[]')
    (folder / 'associations.json').write_text('[]')
    (folder / 'story.json').write_text(json.dumps([{'type': 'meta', 'text': 'The session begins.'}]))
    (folder / 'scene.json').write_text(json.dumps({
        'id': 'opening',
        'title': f"{name} — Opening Scene",
        'image': None,
        'text': 'Your adventure is about to begin. Choose an approach to set the tone.',
        'choices': [
            {'id': 'scout', 'label': 'Scout ahead cautiously'},
            {'id': 'parley', 'label': 'Seek conversation first'},
            {'id': 'press_on', 'label': 'Press forward decisively'},
        ],
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
        if _normalize_email(member.get('email')) == identifier:
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
        return json.loads(text)
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
    if any(inv.get('email') == invite_email for inv in invites):
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
                freshness_context={"scene_count": 0},
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
    if campaign_contract.get("agent_output_contract"):
        campaign_docs.insert(0, "[Campaign Contract]\n" + campaign_contract["agent_output_contract"])

    # Derive narrative style: campaign_variables.narrative_style →
    # campaign_settings.tone → request payload style → default 'balanced'
    derived_style = (
        str(campaign_variables.get('narrative_style') or '').strip()
        or str(campaign_settings.get('tone') or '').strip()
        or style
    )

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
        or (campaign_contract.get("campaign_dna") or {}).get("starting_location")
        or (campaign_contract.get("world_contract") or {}).get("known_starting_location")
    )
    if not _explicit_starting_location:
        try:
            _bootstrap_seed_rc = build_content_bundle(
                situation_type="campaign_opening",
                scene_director_output={},
                world_state={},
                campaign_contract=campaign_contract,
                freshness_context={"scene_count": 0},
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
                if _seed_source == "premise_seed" or not loc_name or _looks_like_tavern_default(loc_name):
                    director_data_dict["location"]["name"] = _seed_loc
                    director_data_dict["scene_title"] = f"Opening — {_seed_loc}"
                    loc_name = _seed_loc
                if _seed_source == "premise_seed":
                    director_data_dict["location"]["type"] = _bsrc.get("location_type") or director_data_dict["location"].get("type") or "camp"
                    director_data_dict["location"]["sensory_details"] = [
                        _bsrc.get("location_identity") or f"The hidden camp at {_seed_loc} is quiet under the trees.",
                        _seed_event or "The woods carry sound farther than they should.",
                    ]
                    director_data_dict["visual_prompt_elements"] = [
                        f"{_seed_loc}, concealed forest camp",
                        "cold woods, army road nearby, signs of pursuit",
                        "fresh bootprints and snapped branches",
                    ]
                    director_data_dict["world_moves"] = [
                        "Search horns move along the army road beyond the trees.",
                        "Someone or something has found the edge of the escapees' trail.",
                    ]
            if _seed_npc:
                _llm_npc = (director_data_dict.get("primary_npc") or {}).get("name") or ""
                if _seed_source == "premise_seed" or not _llm_npc or _looks_like_tavern_default(_llm_npc) or _llm_npc.lower() in (
                    "a stranger", "a mysterious figure", "the barkeep", "innkeeper", "the innkeeper"
                ):
                    director_data_dict["primary_npc"]["name"] = _seed_npc
                    npc_name = _seed_npc
            if _seed_event and (_seed_source == "premise_seed" or not director_data_dict.get("inciting_incident")):
                director_data_dict["inciting_incident"] = _seed_event
            if _seed_stakes and (_seed_source == "premise_seed" or not director_data_dict.get("immediate_stakes")):
                director_data_dict["immediate_stakes"] = _seed_stakes
            if _seed_problem and _seed_source == "premise_seed":
                director_data_dict["central_conflict"] = _seed_problem
            if _seed_question and _seed_source == "premise_seed":
                director_data_dict["player_visible_clues"] = [_seed_question]
            if _seed_decision and _seed_source == "premise_seed":
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
        _narr_lower = (narrative.narrative or "").lower()
        _looks_stock = (
            "sealed packet" in _narr_lower
            or "something has gone very wrong" in _narr_lower
            or "first crossroads" in _narr_lower
        )
        if _looks_stock:
            sensory = ((director_data_dict.get("location") or {}).get("sensory_details") or [""])[0]
            npc_data = director_data_dict.get("primary_npc") or {}
            fallback_text = build_fallback_scene(
                location_name=loc_name or 'the hiding place',
                npc_name=npc_name,
                player_name=player_name,
                emotional_state=npc_data.get("current_emotional_state") or 'urgent',
                inciting_incident=director_data_dict.get("inciting_incident") or _seed_event,
                central_conflict=director_data_dict.get("central_conflict") or _seed_problem,
                immediate_stakes=director_data_dict.get("immediate_stakes") or _seed_stakes,
                sensory_detail=sensory,
                campaign_name=session_name,
            )
            narrative = narrative_agent.NarrativeResponse(
                narrative=fallback_text,
                prompt=f"What does {player_name} do?",
                tone=derived_style,
                scene_score=max(narrative.scene_score or 0, 80),
                score_passed=True,
                score_detail={**(narrative.score_detail or {}), "premise_fallback_used": True},
                suggested_actions=narrative.suggested_actions,
                world_moves=narrative.world_moves,
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
    retry_used = False
    fallback_used = False
    contract_minimum = int((campaign_contract.get("validator_policy") or {}).get("minimum_scene_score") or MINIMUM_SCORE) if campaign_contract else MINIMUM_SCORE
    minimum_score = max(MINIMUM_SCORE, contract_minimum)

    if quality_score < minimum_score or contract_validator.get("failed_expectations"):
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

    if quality_score < minimum_score:
        fallback_used = True
        sensory = (director_output.location.sensory_details[:1] or [''])[0]
        fallback_text = build_fallback_scene(
            location_name=loc_name or 'the settlement',
            npc_name=npc_name,
            player_name=player_name,
            emotional_state=director_output.primary_npc.current_emotional_state or 'grim-faced',
            inciting_incident=director_output.inciting_incident or director_output.central_conflict,
            central_conflict=director_output.central_conflict,
            immediate_stakes=director_output.immediate_stakes,
            sensory_detail=sensory,
            campaign_name=session_name,
        )
        narrative = narrative_agent.NarrativeResponse(
            narrative=fallback_text,
            prompt=f"What does {player_name} do?",
            tone=derived_style,
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
        'campaign_contract': {
            'contract_version': campaign_contract.get('contract_version'),
            'canon_policy': campaign_contract.get('canon_policy', {}),
            'ui_policy': campaign_contract.get('ui_policy', {}),
            'validator_policy': campaign_contract.get('validator_policy', {}),
        } if campaign_contract else {},
        'ui_policy': campaign_contract.get('ui_policy', {}) if campaign_contract else {},
    }
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
        except Exception:
            pass

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
                freshness_context={"scene_count": 0},
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
        adv_content_bundle = build_content_bundle(
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
        'campaign_contract': {
            'contract_version': campaign_contract.get('contract_version'),
            'canon_policy': campaign_contract.get('canon_policy', {}),
            'ui_policy': campaign_contract.get('ui_policy', {}),
            'validator_policy': campaign_contract.get('validator_policy', {}),
        } if campaign_contract else {},
        'ui_policy': campaign_contract.get('ui_policy', {}) if campaign_contract else {},
    }

    post_scene_dice_rolls: list[dict] = []
    try:
        post_cues = await scene_agent.analyze_scene(scene_agent.SceneAnalysisRequest(
            scene=new_scene['text'],
            actions=[c.get('label', '') for c in new_scene.get('choices', []) if isinstance(c, dict)],
            session_id=session_id,
        ))
        post_scene_dice_rolls = [r.model_dump() for r in post_cues.dice_rolls]
    except Exception:
        pass

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
