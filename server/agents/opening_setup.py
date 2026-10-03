"""Opening setup questionnaire and character anchor helpers."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, Field

from ..steward_llm import chat_complete
from .generation_intent import STOP_WORDS as _GROUNDING_STOP_WORDS
from .generation_intent import (
    OpeningIntent,
    blocking_claims,
    build_source_trace,
    find_internal_language,
    find_unsupported_claims,
    intent_from_opening,
)
from .generation_intent import clean_text as _clean_raw
from .generation_intent import trim_sentence as _trim_sentence

_PERSONAL_HISTORY_PATTERNS = (
    re.compile(
        r"\b(?:my|our)\s+(?:mother|father|sister|brother|parent|child|son|daughter|spouse|partner|friend|mentor|rival|ally|enemy|acquaintance)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:i|we)\s+(?:already\s+)?(?:owe|owed|paid|repay|repaid|trust|distrust|know|knew|met|worked with|grew up with|was raised by|once helped|saved|betrayed|promised)\b[^.!?]{0,100}",
        re.I,
    ),
    re.compile(r"\b(?:someone|somebody|a person)\s+(?:i|we)\s+(?:care about|love|miss)\b", re.I),
    re.compile(r"\b(?:debt collector|old debt|former friend|old friend|old rival|old ally|old enemy)\b", re.I),
)
_SENTENCE_STARTERS = {
    "a", "an", "and", "as", "at", "because", "before", "but", "if", "i", "in", "it", "my", "no",
    "nothing", "one", "our", "someone", "the", "there", "they", "this", "we", "when",
}


class OpeningSetupOption(BaseModel):
    id: str
    label: str
    value: str
    effects: dict[str, Any] = Field(default_factory=dict)


class OpeningSetupQuestion(BaseModel):
    id: str
    kind: str
    question: str
    helper_text: str = ""
    options: list[OpeningSetupOption] = Field(default_factory=list)
    allow_custom: bool = True
    required: bool = True


class CampaignBrief(BaseModel):
    title: str = ""
    location_name: str = ""
    brief_paragraphs: list[str] = Field(default_factory=list)
    known_facts: list[str] = Field(default_factory=list)
    character_entry_prompt: str = ""
    character_anchor: dict[str, str] = Field(default_factory=dict)
    quality_debug: dict[str, Any] = Field(default_factory=dict)


class OpeningSetupQuestionnaire(BaseModel):
    questionnaire_id: str
    campaign_id: str = ""
    session_id: str = ""
    character_id: str = ""
    intro_text: str = ""
    campaign_brief: CampaignBrief = Field(default_factory=CampaignBrief)
    questions: list[OpeningSetupQuestion] = Field(default_factory=list)


class OpeningCharacterAnchor(BaseModel):
    session_id: str = ""
    campaign_id: str = ""
    character_id: str = ""
    character_name: str = ""
    arrival_reason: str = ""
    pre_scene_activity: str = ""
    personal_stake: str = ""
    known_npc_connection: str = ""
    belief_or_rumor: str = ""
    party_bond: str = ""
    followed_complication: str = ""
    fear_of_loss: str = ""
    trust_or_distrust: str = ""
    opening_tone: str = ""
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    source: str = "player_answered"


class ProvisionalCharacterAnchor(BaseModel):
    public_identity: str = ""
    private_tension: str = ""
    reason_to_care: str = ""
    known_connection_to_starting_problem: str = ""
    class_flavor_translation: str = ""


def questionnaire_id(session_id: str, character_id: str = "") -> str:
    digest = hashlib.sha1(f"{session_id}:{character_id}".encode()).hexdigest()[:10]
    return f"oq_{digest}"


def generate_questionnaire(
    *,
    session_id: str,
    campaign_id: str = "",
    campaign_contract: dict[str, Any] | None = None,
    opening_seed: dict[str, Any] | None = None,
    character: dict[str, Any] | None = None,
    backstory_hooks: list[dict[str, Any]] | None = None,
    party_mode: bool = False,
) -> dict[str, Any]:
    contract = campaign_contract or {}
    seed = opening_seed or {}
    char = character or {}
    char_id = str(char.get("id") or char.get("character_id") or "")
    char_name = str(char.get("name") or "your character").strip() or "your character"
    loc = str(seed.get("starting_location") or "the opening scene")
    display_loc = loc
    if display_loc.lower().startswith("the "):
        display_loc = display_loc[4:]
    npc = str(seed.get("named_npc_or_visible_threat") or "a named witness").split("(")[0].strip()
    if not npc or npc.lower() == "the first witness":
        npc = "the nearest named contact"
    brief = build_campaign_brief(
        campaign={**contract, "name": contract.get("campaign_name") or contract.get("name") or ""},
        character=char,
        opening_seed=seed,
    )
    intro = brief.get("character_entry_prompt") or "First, here is what your character knows before arriving."
    trouble = _natural_problem(seed, contract)
    urgency = _natural_urgency(seed, contract)
    rumor = _natural_rumor(seed, contract)
    object_hint = _object_hint(seed, contract) or _opening_object_name({**contract, **seed})
    provisional_anchor = generate_provisional_character_anchor(character=char, premise={**contract, **seed})
    questions: list[OpeningSetupQuestion] = []
    subject = "the party" if party_mode else char_name
    questions.append(OpeningSetupQuestion(
        id="arrival_reason",
        kind="arrival_reason",
        question=f"What brought {subject} here?",
        helper_text=f"{trouble} {urgency}",
        options=_with_ai(_options([
            ("study", f"Study {object_hint} before it is hidden"),
            ("escort", f"Escort someone through {display_loc} before trouble closes in"),
            ("search", f"Find someone connected to {rumor.lower()}"),
            ("shelter", f"Seek shelter near {display_loc} from pressure already following me"),
        ])),
    ))
    questions.append(OpeningSetupQuestion(
        id="personal_stake",
        kind="personal_stake",
        question=f"Why does this matter to {subject}?",
        helper_text=provisional_anchor.get("reason_to_care") or urgency,
        options=_with_ai(_options([
            ("knowledge", provisional_anchor.get("reason_to_care") or f"It matches something I know about {display_loc}"),
            ("person", "Someone I care about could be exposed"),
            ("promise", "I gave my word to protect someone caught in this"),
            ("past", "I have seen a sign like this before, and it ended badly"),
        ])),
    ))
    questions.append(OpeningSetupQuestion(
        id="followed_complication",
        kind="followed_complication",
        question=f"What complication followed {subject} here?",
        helper_text=rumor,
        options=_with_ai(_options([
            ("debt", "A rival or debt collector is close behind"),
            ("rumor", f"A rumor about me reached {display_loc} first"),
            ("evidence", f"I carry evidence tied to {object_hint}"),
            ("wound", "I am hiding an injury, curse, or mistake"),
        ])),
    ))
    questions.append(OpeningSetupQuestion(
        id="fear_of_loss",
        kind="fear_of_loss",
        question=f"What does {subject} fear losing?",
        helper_text="The first scene begins before the truth is known.",
        options=_with_ai(_options([
            ("person", "A person who still believes in me"),
            ("name", "My good name"),
            ("home", f"A place near {display_loc} I cannot abandon"),
            ("truth", "The only proof of what really happened"),
        ])),
    ))
    if party_mode:
        questions.append(OpeningSetupQuestion(
            id="party_bond",
            kind="party_bond",
            question="What keeps the party together when the opening problem becomes risky?",
            helper_text=trouble,
            options=_with_ai(_options([
                ("shared_debt", "We owe the same person a debt."),
                ("shared_job", "We accepted the same job before we understood the cost."),
                ("shared_secret", "We share a secret that this scene could expose."),
                ("shared_survival", "We survive better together than apart."),
            ])),
        ))
    else:
        questions.append(OpeningSetupQuestion(
            id="npc_connection",
            kind="npc_connection",
            question=f"Who does {subject} trust or distrust here?",
            helper_text=f"{npc} is visible before the first scene settles into answers.",
            options=_with_ai(_options([
                ("npc_known", provisional_anchor.get("known_connection_to_starting_problem") or f"{npc} once helped me"),
                ("family", "Someone here recognizes my name"),
                ("blame", "Someone blames me for an earlier failure"),
                ("unknown", "No one knows me, and I prefer it that way"),
            ])),
            required=False,
        ))
    if len(questions) > 5:
        questions = questions[:5]
    return OpeningSetupQuestionnaire(
        questionnaire_id=questionnaire_id(session_id, char_id),
        campaign_id=str(campaign_id or ""),
        session_id=session_id,
        character_id=char_id,
        intro_text=intro,
        campaign_brief=CampaignBrief(**brief),
        questions=questions,
    ).model_dump()


def build_campaign_brief(
    *,
    campaign: dict[str, Any] | None = None,
    character: dict[str, Any] | None = None,
    opening_seed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    camp = campaign or {}
    char = character or {}
    seed = opening_seed or {}
    title = str(camp.get("campaign_name") or camp.get("name") or camp.get("title") or "This campaign").strip()
    location = str(seed.get("starting_location") or camp.get("starting_location") or "the starting location").strip()
    char_name = str(char.get("name") or "your character").strip() or "your character"
    anchor = generate_provisional_character_anchor(character=char, premise={**camp, **seed})
    trouble = _natural_problem(seed, camp, strict=True)
    urgency = _natural_urgency(seed, camp, strict=True)
    rumor = _natural_rumor(seed, camp, strict=True)
    place_identity = _natural_location_identity(location, seed, camp)
    object_name = _opening_object_name({**camp, **seed}, neutral_default=True)
    concrete_object = _concrete_object(seed, camp, object_name, strict=True)
    institution = _institution_or_faction(seed, camp, location, strict=True)
    visible_consequence = _visible_consequence(seed, camp, institution, strict=True)
    char_context = naturalize_character_knowledge(char, {**camp, **seed, "object_name": object_name}, anchor)
    # Anything we could only answer with "not established" is an explicit unknown:
    # it is reported, kept out of the known facts, and never dressed up as lore.
    unknown_lines = {
        "conflict": trouble if trouble == UNKNOWN_PROBLEM else "",
        "stakes": urgency if urgency == UNKNOWN_URGENCY else "",
        "actor": institution if institution == UNKNOWN_AUTHORITY else "",
        "object": concrete_object if concrete_object == UNKNOWN_OBJECT else "",
    }
    unknowns = [field for field, line in unknown_lines.items() if line]
    facts = [
        place_identity,
        trouble,
        urgency,
        rumor,
        concrete_object,
        institution,
        visible_consequence,
        char_context,
    ]
    open_lines = {UNKNOWN_PROBLEM, UNKNOWN_URGENCY, UNKNOWN_AUTHORITY, UNKNOWN_OBJECT, UNKNOWN_CONSEQUENCE}
    facts = [_trim_sentence(f) for f in facts if f and f not in open_lines]
    place_intro = _place_intro(title, location, place_identity)
    paragraphs = [
        place_intro,
        f"{trouble} {concrete_object}",
        f"{urgency} {visible_consequence}" if urgency != visible_consequence else urgency,
        char_context,
    ]
    paragraphs = [_trim_sentence(p) for p in paragraphs if p]
    brief = {
        "title": title,
        "location_name": location,
        "brief_paragraphs": paragraphs[:4],
        "known_facts": facts[:6],
        "unknowns": unknowns,
        "character_anchor": anchor,
        "character_entry_prompt": f"{char_name} arrives before the truth is known. Decide why this mystery has pulled {char_name} here.",
    }
    validation = validate_campaign_brief(brief)
    if not validation["valid"]:
        brief = _repair_campaign_brief(brief, seed, camp, char)
        validation = validate_campaign_brief(brief)
    brief["quality_debug"] = validation
    return brief


def _place_intro(title: str, location: str, place_identity: str) -> str:
    """"<Title> begins at <Location>." followed by what the place is, grammatically."""
    identity = _clean_raw(place_identity)
    if not identity:
        return _trim_sentence(f"{title} begins at {location}, where the first public trouble has surfaced")
    if identity.lower().startswith(location.lower()):
        # The identity already names the place ("<Location> is a ..."): don't splice it into the clause.
        return f"{_trim_sentence(f'{title} begins at {location}')} {_trim_sentence(identity)}"
    return _trim_sentence(f"{title} begins at {location}, {identity[0].lower() + identity[1:]}")


def generate_provisional_character_anchor(
    *,
    character: dict[str, Any] | None = None,
    premise: dict[str, Any] | None = None,
) -> dict[str, str]:
    char = character or {}
    prem = premise or {}
    name = str(char.get("name") or "Your character").strip() or "Your character"
    level = str(char.get("level") or "").strip()
    class_name = str(char.get("class_name") or "").strip()
    public_role = _public_identity(name, level, class_name)
    object_name = _opening_object_name(prem, neutral_default=True)
    location = str(prem.get("starting_location") or prem.get("location_name") or "the starting place").strip()
    institution = _institution_or_faction(prem, prem, location)
    institution_subject = _institution_subject(institution)
    class_flavor = _class_flavor_translation(name, class_name, object_name)
    backstory = _character_backstory_text(char)
    # Provisional anchors must not manufacture character history.  These values
    # are shown to the player before they have approved the opening, so an
    # "old debt", prior loss, secret obligation, or hearsay connection becomes
    # accidental canon.  Keep the provisional hook observable and reversible.
    if backstory:
        reason = (
            f"{name}'s established background gives them a reason to pay attention to the "
            f"{object_name}, but the campaign has not yet decided what personal history connects them to it."
        )
        tension = (
            f"{name} can decide at {location} whether the {object_name} is personally important "
            f"or simply the clearest sign that something is wrong."
        )
    else:
        reason = _character_reason_to_care(name, class_name, object_name, location)
        tension = (
            f"{name} has no assumed debt or secret connection to {institution_subject}; "
            f"their reason for becoming involved is still the player's choice."
        )
    connection = (
        f"No prior relationship with {institution_subject} is assumed. "
        f"The {object_name} is the first concrete reason for {name} to pay attention."
    )
    return ProvisionalCharacterAnchor(
        public_identity=public_role,
        private_tension=_trim_sentence(tension),
        reason_to_care=_trim_sentence(reason),
        known_connection_to_starting_problem=_trim_sentence(connection),
        class_flavor_translation=_trim_sentence(class_flavor),
    ).model_dump()


def naturalize_character_knowledge(
    character: dict[str, Any] | None,
    premise: dict[str, Any] | None,
    anchor: dict[str, str] | None = None,
) -> str:
    char = character or {}
    prem = premise or {}
    anch = anchor or {}
    name = str(char.get("name") or "Your character").strip() or "Your character"
    object_name = str(prem.get("object_name") or _opening_object_name(prem, neutral_default=True)).strip() or "first physical sign"
    flavor = anch.get("class_flavor_translation") or _class_flavor_translation(name, str(char.get("class_name") or ""), object_name)
    reason = anch.get("reason_to_care") or ""
    if reason:
        return _trim_sentence(f"{flavor} {reason}")
    return _trim_sentence(flavor)


naturalizeCharacterKnowledge = naturalize_character_knowledge  # noqa: N816 - camelCase alias kept for API compatibility


BRIEF_FORBIDDEN_PHRASES = (
    "wrong faction",
    "trusted object appears in the wrong place",
    "before the truth is public",
    "act on what is immediately visible",
    "the public story",
    "covered clue",
    "first useful evidence",
    "same pressure",
    "practical reason",
    "someone is lying",
    "concrete clue",
    "visible clue",
    "if no one acts soon",
)


def validate_campaign_brief(brief: dict[str, Any]) -> dict[str, Any]:
    text = json_blob = " ".join([
        str(brief.get("title") or ""),
        str(brief.get("location_name") or ""),
        " ".join(str(p) for p in brief.get("brief_paragraphs") or []),
        " ".join(str(f) for f in brief.get("known_facts") or []),
        str(brief.get("character_entry_prompt") or ""),
    ]).lower()
    location = str(brief.get("location_name") or "").strip().lower()
    anchor = brief.get("character_anchor") or {}
    issues: list[str] = []
    checks = {
        "names_starting_location": bool(location and location in text),
        "explains_location": any(word in text for word in ("hall", "harbor", "pass", "road", "market", "observatory", "chamber", "crossing", "watchpoint", "built", "where")),
        "immediate_problem": any(word in text for word in ("cracked", "vanished", "missing", "sabotage", "dispute", "disagree", "contradict", "fraud", "poison", "stolen", "broken", "sealed", "stopped", "failed", "failing", "accuse", "ripen", "cycle", "cycles", "caught", "shear")),
        "concrete_entity": any(word in text for word in ("relic", "seal", "ledger", "mirror", "bell", "guild", "charter", "warden", "archivist", "faction", "institution", "survivor", "witness", "corpse", "token", "letter", "tracks", "blood", "charm", "bowl")),
        "time_matters": any(word in text for word in ("before", "soon", "tonight", "dawn", "dusk", "certified", "closes", "disappear", "final")),
        "character_knowledge": bool(anchor.get("reason_to_care") or anchor.get("class_flavor_translation")) and any(str(v).lower()[:24] in text for v in anchor.values() if v),
        "no_raw_class_label": not re.search(r"\bas a\s+[a-z][a-z /-]{2,40},", json_blob),
        "no_forbidden": not any(phrase in json_blob for phrase in BRIEF_FORBIDDEN_PHRASES),
    }
    waived = sorted({_UNKNOWN_WAIVES[u] for u in brief.get("unknowns") or [] if u in _UNKNOWN_WAIVES})
    for key, ok in checks.items():
        if not ok and key not in waived:
            issues.append(key)
    return {"valid": not issues, "issues": issues, "checks": checks, "waived_for_unknowns": waived}


def _repair_campaign_brief(
    brief: dict[str, Any],
    seed: dict[str, Any],
    camp: dict[str, Any],
    char: dict[str, Any],
) -> dict[str, Any]:
    title = str(brief.get("title") or camp.get("campaign_name") or "This campaign")
    location = str(brief.get("location_name") or seed.get("starting_location") or "the starting location")
    object_name = _opening_object_name({**camp, **seed}, neutral_default=True)
    institution = _institution_or_faction(seed, camp, location, strict=True)
    place = _natural_location_identity(location, seed, camp)
    trouble = _natural_problem(seed, camp, strict=True)
    consequence = _visible_consequence(seed, camp, institution, strict=True)
    anchor = brief.get("character_anchor") or generate_provisional_character_anchor(character=char, premise={**camp, **seed})
    knowledge = naturalize_character_knowledge(char, {**camp, **seed, "object_name": object_name}, anchor)
    institution_clean = _clean_raw(institution)
    unknowns = set(brief.get("unknowns") or [])
    object_known = "object" not in unknowns
    object_line = (
        f"The physical object drawing every eye is the {object_name}"
        + (f", and {institution_clean.lower()} cannot agree what it proves" if "actor" not in unknowns else "")
        if object_known else UNKNOWN_OBJECT
    )
    consequence_line = consequence if "stakes" in unknowns else f"By the next bell, {consequence[0].lower() + consequence[1:]}"
    open_lines = {UNKNOWN_PROBLEM, UNKNOWN_URGENCY, UNKNOWN_AUTHORITY, UNKNOWN_OBJECT, UNKNOWN_CONSEQUENCE}
    known_facts = [
        _trim_sentence(place),
        None if "conflict" in unknowns else _trim_sentence(f"The immediate problem is that {trouble[0].lower() + trouble[1:]}"),
        _trim_sentence(f"The physical object that starts the mystery is the {object_name}") if object_known else None,
        None if "actor" in unknowns else _trim_sentence(institution),
        None if "stakes" in unknowns else _trim_sentence(consequence),
        knowledge,
    ]
    repaired = {
        **brief,
        "brief_paragraphs": [
            _place_intro(title, location, place),
            _trim_sentence(f"{trouble} {object_line}"),
            _trim_sentence(consequence_line),
            knowledge,
        ],
        "known_facts": [f for f in known_facts if f and f not in open_lines],
        "character_anchor": anchor,
    }
    return repaired


def answers_to_anchor(
    *,
    session_id: str,
    campaign_id: str = "",
    character: dict[str, Any] | None = None,
    questionnaire: dict[str, Any] | None = None,
    answers: list[dict[str, Any]] | None = None,
    source: str = "player_answered",
    character_hook_override: str = "",
) -> dict[str, Any]:
    char = character or {}
    q_by_id = {q.get("id"): q for q in (questionnaire or {}).get("questions", [])}
    values: dict[str, str] = {}
    for ans in answers or []:
        qid = str(ans.get("question_id") or ans.get("id") or "")
        custom = str(ans.get("custom_value") or ans.get("answer_text") or ans.get("value") or "").strip()
        if custom:
            values[qid] = custom
            continue
        option_id = str(ans.get("option_id") or "")
        option = next((opt for opt in (q_by_id.get(qid, {}).get("options") or []) if opt.get("id") == option_id), None)
        if option:
            if option.get("id") == "ai_choose":
                continue
            values[qid] = str(option.get("value") or option.get("label") or "")
    character_name = str(char.get("name") or "the party")
    arrival = values.get("arrival_reason") or _coherent_default(questionnaire, "arrival_reason")
    stake = values.get("personal_stake") or _coherent_default(questionnaire, "personal_stake")
    npc = values.get("npc_connection") or _coherent_default(questionnaire, "npc_connection")
    party_bond = values.get("party_bond") or _coherent_default(questionnaire, "party_bond")
    followed_complication = values.get("followed_complication") or _coherent_default(questionnaire, "followed_complication")
    fear_of_loss = values.get("fear_of_loss") or _coherent_default(questionnaire, "fear_of_loss")
    hook_override = " ".join(str(character_hook_override or "").split()).strip()
    if hook_override:
        stake = hook_override
    pre_scene = _pre_scene_from_arrival(arrival)
    anchor = OpeningCharacterAnchor(
        session_id=session_id,
        campaign_id=str(campaign_id or ""),
        character_id=str(char.get("id") or char.get("character_id") or ""),
        character_name=character_name,
        arrival_reason=arrival,
        pre_scene_activity=pre_scene,
        personal_stake=stake,
        known_npc_connection=npc,
        party_bond=party_bond,
        followed_complication=followed_complication,
        fear_of_loss=fear_of_loss,
        trust_or_distrust=npc,
        belief_or_rumor="The first sign of trouble is not random.",
        opening_tone="personally invested",
        must_include=[v for v in (arrival, pre_scene, stake, hook_override, followed_complication, fear_of_loss, npc, party_bond) if v][:7],
        must_not_include=["do not force the character to accept a quest", "do not use stale character names"],
        source=source,
    )
    data = anchor.model_dump()
    if hook_override:
        data["character_hook_override"] = hook_override
    return data


def _safe_auto_answer(question: dict[str, Any], questionnaire: dict[str, Any]) -> str:
    """Return a conservative setup answer when no LLM is available.

    The fallback deliberately avoids inventing prior relationships, debts,
    trauma, hidden obligations, or off-screen events.  It should connect the
    character to what is visibly happening now, not manufacture a backstory.
    """
    qid = str(question.get("id") or "")
    brief = questionnaire.get("campaign_brief") or {}
    location = str(brief.get("location_name") or "this place").strip() or "this place"
    facts = [str(f).strip() for f in (brief.get("known_facts") or []) if str(f).strip()]
    concrete_fact = facts[1] if len(facts) > 1 else (facts[0] if facts else "something here is clearly wrong")

    fallbacks = {
        "arrival_reason": f"I came to understand what is happening at {location} before committing to a side.",
        "personal_stake": f"What I know so far is this: {concrete_fact.rstrip(' .!?') if concrete_fact else 'this problem is real'}. I want enough facts to choose what to do about it.",
        "followed_complication": "No extra complication followed me here; the problem in front of me is enough.",
        "fear_of_loss": "I do not want the clearest evidence or the chance to act on it to disappear.",
        "npc_connection": "No one here has an assumed history with me; I will judge them by what they do now.",
        "party_bond": "We agreed to face the immediate problem together until we understand what is actually happening.",
    }
    return fallbacks.get(qid, f"I will respond to the concrete situation at {location} without assuming facts that have not been established.")


def coherent_default_answer(question: dict[str, Any], questionnaire: dict[str, Any] | None) -> str:
    """The shared-motive, history-free answer for ``question`` (no first-option pick)."""
    return _safe_auto_answer(question, questionnaire or {})


def _coherent_default(questionnaire: dict[str, Any] | None, qid: str) -> str:
    """Default for an unanswered / "let the AI choose" question.

    Taking each question's first option independently produces unrelated debts,
    fears and relationships that merely happened to be listed first.  The safe
    defaults share one present-tense motive and invent no history.
    """
    for question in (questionnaire or {}).get("questions", []):
        if question.get("id") == qid:
            return _safe_auto_answer(question, questionnaire or {})
    return ""


# (negation, assertion) pairs: one answer may not deny what another asserts.
_COHERENCE_RULES: dict[str, tuple[re.Pattern[str], re.Pattern[str]]] = {
    "prior_history": (
        re.compile(r"\bno one (?:here )?has an assumed history\b|\bno prior (?:relationship|history|connection)\b|\bnobody here knows me\b", re.I),
        re.compile(r"\b(?:old|former) (?:friend|rival|ally|enemy|debt)\b|\bowe[sd]?\b|\bonce (?:helped|saved|served|knew)\b|\b(?:already )?(?:trust|distrust)\b", re.I),
    ),
    "followed": (
        re.compile(r"\bnothing (?:has )?followed me\b|\bno extra complication\b|\bno complication\b", re.I),
        re.compile(r"\b(?:followed|chas(?:ing|ed)|pursu(?:ed|ing)|tracked) me\b|\bis close behind\b|\bfollowed me here\b", re.I),
    ),
}


def answers_coherence_issues(answers: dict[str, str]) -> list[str]:
    """Contradictions inside one set of setup answers (empty means coherent)."""
    issues: list[str] = []
    for label, (denial, assertion) in _COHERENCE_RULES.items():
        denies = [qid for qid, text in answers.items() if denial.search(text or "")]
        asserts = [qid for qid, text in answers.items() if assertion.search(text or "") and not denial.search(text or "")]
        if denies and asserts:
            issues.append(f"{label}: '{denies[0]}' denies what '{asserts[0]}' asserts")
    return issues


def _parse_ai_setup_answers(raw: str | None, allowed_ids: set[str]) -> dict[str, str]:
    if not raw:
        return {}
    text = raw.strip()
    try:
        payload = json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            payload = json.loads(text[start:end + 1])
        except Exception:
            return {}
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("answers"), dict):
        payload = payload["answers"]
    cleaned: dict[str, str] = {}
    for qid, value in payload.items():
        qid = str(qid)
        if qid not in allowed_ids:
            continue
        if isinstance(value, dict):
            value = value.get("answer_text") or value.get("value") or ""
        answer = " ".join(str(value or "").split()).strip()
        if answer:
            cleaned[qid] = answer[:320]
    return cleaned


def _is_grounded_ai_answer(
    answer: str,
    questionnaire: dict[str, Any],
    character: dict[str, Any],
) -> bool:
    brief = questionnaire.get("campaign_brief") or {}
    context_parts = [
        brief.get("title"),
        brief.get("location_name"),
        *(brief.get("known_facts") or []),
        *(brief.get("brief_paragraphs") or []),
        _character_backstory_text(character),
    ]
    context = " ".join(str(part) for part in context_parts if part).casefold()
    source = f"{context} {character.get('name') or ''}".casefold()
    context_tokens = set(re.findall(r"[a-z0-9]+", context))
    source_tokens = set(re.findall(r"[a-z0-9]+", source))
    answer_tokens = set(re.findall(r"[a-z0-9]+", answer.casefold()))
    if not (answer_tokens - _GROUNDING_STOP_WORDS).intersection(context_tokens):
        return False

    source_claim_tokens = {
        token[:-1] if token.endswith("s") and len(token) > 3 else token
        for token in source_tokens
    }
    for pattern in _PERSONAL_HISTORY_PATTERNS:
        for claim in pattern.findall(answer):
            claim_tokens = {
                token[:-1] if token.endswith("s") and len(token) > 3 else token
                for token in re.findall(r"[a-z0-9]+", claim.casefold())
                if token not in _GROUNDING_STOP_WORDS and len(token) > 2
            }
            if not claim_tokens.issubset(source_claim_tokens):
                return False

    for match in re.finditer(r"\b[A-Z][a-z]{2,}\b", answer):
        prefix = answer[:match.start()].rstrip()
        token = match.group().casefold()
        if (not prefix or prefix[-1] in ".!?") and token in _SENTENCE_STARTERS:
            continue
        if token not in source_tokens:
            return False
    return True


def auto_generate_answers(
    *,
    questionnaire: dict[str, Any],
    character: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate one coherent set of opening answers.

    "Let AI build my setup" used to mean "pick option zero for every
    question."  That created unrelated debts, fears, NPC histories, and motives
    that merely happened to be first in their lists.  Generate the set as a
    whole so the answers share one motive and remain grounded in approved facts.
    """
    questions = [q for q in (questionnaire.get("questions") or []) if q.get("id")]
    if not questions:
        return []

    char = character or {}
    allowed_ids = {str(q.get("id")) for q in questions}
    brief = questionnaire.get("campaign_brief") or {}
    prompt_payload = {
        "campaign_brief": {
            "title": brief.get("title"),
            "location_name": brief.get("location_name"),
            "known_facts": brief.get("known_facts") or [],
            "brief_paragraphs": brief.get("brief_paragraphs") or [],
        },
        "character": {
            "name": char.get("name") or "the party",
            "class_name": char.get("class_name") or "",
            "backstory": _character_backstory_text(char)[:1200],
        },
        "questions": [
            {
                "id": q.get("id"),
                "question": q.get("question"),
                "options": [
                    str(opt.get("value") or opt.get("label") or "")
                    for opt in (q.get("options") or [])
                    if opt.get("id") != "ai_choose"
                ],
            }
            for q in questions
        ],
    }
    system = (
        "Build one coherent tabletop campaign opening setup from the supplied facts. "
        "Return ONLY a JSON object whose keys are the supplied question ids and whose values are short first-person answers. "
        "Treat campaign_brief facts and explicit character backstory as canon. "
        "Do not invent prior relationships, relatives, debts, trauma, secret obligations, previous encounters, named organizations, "
        "or knowledge the character was never given. Do not force every offered option into the setup. "
        "All answers must support one understandable reason for being present and must make sense together. "
        "Prefer an observable present-tense motive over invented history. If the source does not establish a personal connection, say so."
    )
    raw = chat_complete(
        [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)}],
        task_scope="taverntails_setup",
        max_tokens=500,
        temperature=0.35,
        timeout=60.0,
    )
    generated = _parse_ai_setup_answers(raw, allowed_ids)

    chosen = {
        str(q.get("id")): (
            generated_answer
            if generated_answer and _is_grounded_ai_answer(generated_answer, questionnaire, char)
            else _safe_auto_answer(q, questionnaire)
        )
        for q in questions
        for generated_answer in [generated.get(str(q.get("id")))]
    }
    if answers_coherence_issues(chosen):
        # A mix of generated and fallback answers contradicts itself: use the
        # shared-motive fallback for the whole set rather than a patchwork.
        chosen = {str(q.get("id")): _safe_auto_answer(q, questionnaire) for q in questions}
    return [
        {"question_id": qid, "answer_source": "ai_choice", "answer_text": text}
        for qid, text in chosen.items()
    ]


def auto_generate_anchor(
    *,
    session_id: str,
    campaign_id: str = "",
    questionnaire: dict[str, Any],
    character: dict[str, Any] | None = None,
    character_hook_override: str = "",
    answers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    generated_answers = answers if answers is not None else auto_generate_answers(
        questionnaire=questionnaire,
        character=character,
    )
    return answers_to_anchor(
        session_id=session_id,
        campaign_id=campaign_id,
        character=character,
        questionnaire=questionnaire,
        answers=generated_answers,
        source="auto_generated",
        character_hook_override=character_hook_override,
    )


def validate_opening_anchor(
    *,
    scene_text: str,
    anchor: dict[str, Any] | None,
    selected_character_name: str = "",
    known_character_names: list[str] | None = None,
) -> dict[str, Any]:
    anchor = anchor or {}
    text = (scene_text or "").lower()
    issues: list[str] = []
    hits = []
    for key in ("arrival_reason", "pre_scene_activity", "personal_stake", "known_npc_connection", "party_bond", "followed_complication", "fear_of_loss"):
        value = str(anchor.get(key) or "")
        if value and _keywords_present(value, text):
            hits.append(key)
    if len(hits) < 2:
        issues.append("Opening scene includes fewer than two anchor elements")
    selected = selected_character_name or str(anchor.get("character_name") or "")
    if selected and selected.lower() != "the party" and selected.lower() not in text:
        issues.append(f"Selected character '{selected}' is not present in opening")
    stale = [
        name for name in (known_character_names or [])
        if name and selected and name != selected and name.lower() in text
    ]
    if stale:
        issues.append("Stale character name present: " + ", ".join(stale[:3]))
    if "you must accept" in text or "you have no choice" in text:
        issues.append("Opening forces a motivation")
    return {
        "valid": not issues,
        "anchor_hits": hits,
        "issues": issues,
        "required_hits": 2,
    }


FORBIDDEN_FIRST_SCENE_PATTERNS = (
    "follows the first choice through",
    "the useful detail is not separate from the danger",
    "if ignored,",
    "the first witness",
    "the story plan",
    "the scene should",
    "a safe road becomes unsafe",
)


def validate_first_scene_contract(
    *,
    scene: dict[str, Any],
    anchor: dict[str, Any] | None,
    player_name: str = "",
    dice_rolls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    anchor = anchor or {}
    text = str(scene.get("text") or scene.get("narrative_body") or "")
    lower = text.lower()
    issues: list[str] = []
    checks: dict[str, bool] = {}
    selected = str(anchor.get("character_name") or player_name or "").strip()
    checks["mentions_player_character"] = bool(selected and selected.lower() in lower) or selected.lower() == "the party"
    checks["explains_presence"] = any(_keywords_present(str(anchor.get(key) or ""), lower) for key in ("arrival_reason", "pre_scene_activity", "personal_stake"))
    checks["concrete_event_or_clue"] = any(str(scene.get(key) or "").strip() for key in ("location", "current_objective", "immediate_stakes")) or bool(
        any(word in lower for word in ("arrives", "falls", "breaks", "blood", "letter", "ledger", "mirror", "seal", "bell", "smoke", "witness", "npc"))
    )
    action_labels = [
        str(choice.get("label") or "")
        for choice in (scene.get("choices") or [])
        if isinstance(choice, dict) and choice.get("label")
    ]
    suggested = [str(item) for item in (scene.get("suggested_actions") or []) if item]
    checks["three_action_vectors"] = len([a for a in action_labels + suggested if a.strip()]) >= 3
    forbidden_hits = [pattern for pattern in FORBIDDEN_FIRST_SCENE_PATTERNS if pattern in lower]
    checks["no_forbidden_language"] = not forbidden_hits
    checks["basic_grammar"] = " a underground" not in lower and " an surface" not in lower
    roll_source = dice_rolls if dice_rolls is not None else (scene.get("dice_rolls") or [])
    supported_rolls: list[str] = []
    for roll in roll_source:
        skill = str((roll or {}).get("skill") or (roll or {}).get("type") or "").lower()
        reason = str((roll or {}).get("reason") or "").lower()
        if skill and (skill in lower or reason and _keywords_present(reason, lower)):
            supported_rolls.append(skill)
    checks["dice_requests_justified"] = not roll_source or bool(supported_rolls)

    if not checks["mentions_player_character"]:
        issues.append("Scene does not mention the selected player character by name")
    if not checks["explains_presence"]:
        issues.append("Scene does not explain why the character is present")
    if not checks["concrete_event_or_clue"]:
        issues.append("Scene lacks a concrete NPC, clue, threat, or event")
    if not checks["three_action_vectors"]:
        issues.append("Scene has fewer than three clear action vectors")
    if forbidden_hits:
        issues.append("Forbidden first-scene language present: " + ", ".join(forbidden_hits[:4]))
    if not checks["basic_grammar"]:
        issues.append("Basic article/grammar issue detected")
    if not checks["dice_requests_justified"]:
        issues.append("Dice request is not justified by the current scene")
    return {
        "valid": not issues,
        "issues": issues,
        "checks": checks,
        "forbidden_hits": forbidden_hits,
        "supported_rolls": supported_rolls,
    }


GENERIC_OPENING_OPTIONS = (
    "scout ahead cautiously",
    "seek conversation first",
    "press forward decisively",
    "choose an approach to set the tone",
    "act on what is immediately visible",
)

FORBIDDEN_OPENING_SCENE_PHRASES = (
    "choose an approach to set the tone",
    "act on what is immediately visible",
    "the person carrying the clearest lead",
    "a trusted object appears in the wrong place",
    "the truth is public",
    "scout ahead cautiously",
    "press forward decisively",
    "the story plan",
    "the scene should",
)


UNNAMED_WITNESS = "The nearest witness"


def _mid_sentence(name: str) -> str:
    """Lower-case a leading article so ``name`` reads naturally mid-sentence."""
    return name[0].lower() + name[1:] if name.startswith(("The ", "A ", "An ")) else name


def build_opening_scene_contract(
    *,
    required: dict[str, Any] | None,
    anchor: dict[str, Any] | None,
    campaign_brief: dict[str, Any] | None,
    player_name: str = "",
    time_of_day: str = "day",
    source_intent: OpeningIntent | None = None,
) -> dict[str, Any]:
    req = required or {}
    anch = anchor or {}
    brief = campaign_brief or {}
    pc = str(anch.get("character_name") or player_name or "the party").strip() or "the party"
    location = str(req.get("starting_location") or brief.get("location_name") or "the opening location").strip()
    # An unnamed witness is honest; a made-up "Warden Hale" is invented canon.
    npc_label = str(req.get("named_npc_or_visible_threat") or UNNAMED_WITNESS)
    npc_name = npc_label.split("(")[0].strip() or UNNAMED_WITNESS
    object_name = _opening_object_name(req)
    sensory = _opening_sensory_detail(location, req, object_name)
    visible_problem = _opening_visible_problem(req, npc_name, object_name)
    personal_hook = _opening_personal_hook(anch, pc, object_name, location)
    pressure = _opening_pressure(req, npc_name)
    actions = _opening_action_options(npc_name, object_name, location, visible_problem)
    pc_start = pc[0].upper() + pc[1:]
    narrative = (
        f"{location} is already too quiet for {time_of_day}.\n\n"
        f"{pc_start} arrives through {sensory}. {visible_problem}\n\n"
        f"{personal_hook}\n\n"
        f"{npc_name} is close enough to intervene, but not calm enough to hide what is wrong. "
        f"{pressure}\n\n"
        f"{pc_start} can {', '.join(action[0].lower() + action[1:] for action in actions[:3])}, "
        f"or {actions[3][0].lower() + actions[3][1:]}."
    )
    intent = source_intent or intent_from_opening(required=req, brief=brief, anchor=anch, player_name=pc)
    source_trace = build_source_trace(
        {
            "location": location,
            "named_npc": npc_name if npc_name != UNNAMED_WITNESS else "",
            "key_object": object_name,
            "sensory_detail": sensory,
            "visible_problem": visible_problem,
            "personal_hook": personal_hook,
            "pressure_or_timer": pressure,
            "action_options": " ".join(actions),
        },
        intent,
    )
    return {
        "scene_title": f"Opening - {location}",
        "location_name": location,
        "time_of_day": time_of_day,
        "opening_narrative": narrative,
        "visible_problem": visible_problem,
        "personal_hook": personal_hook,
        "named_npcs": [npc_name],
        "key_objects_or_clues": [object_name],
        "pressure_or_timer": pressure,
        "action_options": actions,
        "source_trace": source_trace,
    }


def validate_opening_scene_contract(
    *,
    scene: dict[str, Any],
    opening_scene: dict[str, Any] | None = None,
    campaign_brief: dict[str, Any] | None = None,
    anchor: dict[str, Any] | None = None,
    player_name: str = "",
    source_intent: OpeningIntent | None = None,
) -> dict[str, Any]:
    contract = opening_scene or scene.get("opening_scene") or {}
    text = str(scene.get("text") or scene.get("narrative_body") or contract.get("opening_narrative") or "")
    lower = text.lower()
    choices = [
        str(c.get("label") or c)
        for c in (scene.get("choices") or contract.get("action_options") or [])
        if c
    ]
    choice_lower = " ".join(choices).lower()
    location = str(contract.get("location_name") or scene.get("location") or "").strip()
    pc = str((anchor or {}).get("character_name") or player_name or "").strip()
    npc_or_objects = [
        *[str(n) for n in contract.get("named_npcs") or []],
        *[str(o) for o in contract.get("key_objects_or_clues") or []],
    ]
    issues: list[str] = []
    checks = {
        "mentions_character": bool(pc and pc.lower() in lower) or pc.lower() == "the party",
        "mentions_location": bool(location and location.lower() in lower),
        "sensory_detail": any(word in lower for word in ("smell", "sound", "humming", "rain", "dust", "canvas", "lantern", "salt", "cold", "quiet", "smoke", "market", "bells")),
        "concrete_npc_object": any(item and item.lower() in lower for item in npc_or_objects),
        "personal_hook": _keywords_present(str(contract.get("personal_hook") or (anchor or {}).get("arrival_reason") or ""), lower),
        "pressure_timer": bool(contract.get("pressure_or_timer")) and _keywords_present(str(contract.get("pressure_or_timer")), lower),
        "three_grounded_options": len(choices) >= 3 and not any(option.lower().strip() in GENERIC_OPENING_OPTIONS for option in choices),
        "no_forbidden": not any(phrase in lower or phrase in choice_lower for phrase in FORBIDDEN_OPENING_SCENE_PHRASES),
        "no_brief_repetition": True,
    }
    brief_sentences = _brief_sentences(campaign_brief or {})
    repeated = [sentence for sentence in brief_sentences if len(sentence.split()) >= 6 and sentence.lower() in lower]
    checks["no_brief_repetition"] = not repeated
    internal = find_internal_language(text)
    checks["no_internal_language"] = not internal
    unsupported: list[dict[str, str]] = []
    if source_intent is not None:
        unsupported = blocking_claims(find_unsupported_claims(text, source_intent, allow=[pc] if pc else ()))
        checks["claims_supported"] = not unsupported
    if not checks["mentions_character"]:
        issues.append("Opening scene does not mention the selected character by name")
    if not checks["mentions_location"]:
        issues.append("Opening scene does not mention the exact starting location")
    if not checks["sensory_detail"]:
        issues.append("Opening scene lacks concrete sensory detail")
    if not checks["concrete_npc_object"]:
        issues.append("Opening scene lacks a named NPC, object, clue, or threat")
    if not checks["personal_hook"]:
        issues.append("Opening scene does not explain why the character is present")
    if not checks["pressure_timer"]:
        issues.append("Opening scene lacks an in-world pressure or timer")
    if not checks["three_grounded_options"]:
        issues.append("Opening scene lacks three grounded, scene-specific action options")
    if not checks["no_forbidden"]:
        issues.append("Opening scene contains generic or planner-facing phrasing")
    if repeated:
        issues.append("Opening scene repeats campaign brief sentences verbatim")
    if internal:
        issues.append("Opening scene contains planner or QA language: " + ", ".join(internal[:3]))
    for claim in unsupported[:4]:
        issues.append(f"Opening scene makes an unsupported {claim['kind'].replace('_', ' ')} claim: {claim['text'][:80]}")
    return {
        "valid": not issues,
        "issues": issues,
        "checks": checks,
        "repeated_brief_sentences": repeated,
        "unsupported_claims": unsupported,
        "internal_language": internal,
    }


def _options(items: list[tuple[str, str]]) -> list[OpeningSetupOption]:
    return [
        OpeningSetupOption(id=key, label=value, value=value, effects={"anchor_field": key})
        for key, value in items
    ]


def _with_ai(options: list[OpeningSetupOption]) -> list[OpeningSetupOption]:
    return [
        *options,
        OpeningSetupOption(
            id="ai_choose",
            label="Let the AI choose based on my character.",
            value="",
            effects={"ai_choose": True},
        ),
    ]


def _object_hint(seed: dict[str, Any], contract: dict[str, Any]) -> str:
    text = " ".join(str(seed.get(k) or "") for k in ("location_identity", "first_clue_or_question", "inciting_event", "player_decision")).lower()
    for phrase in ("blackened silver charms", "blackened charm", "water seal", "cistern ledger", "forbidden bell", "marked token"):
        if phrase in text:
            return phrase
    pitch = str(contract.get("campaign_pitch") or "").lower()
    for phrase in ("blackened silver", "water seal", "stopped clocks", "treaty ledger"):
        if phrase in pitch:
            return phrase
    return ""


def _character_backstory_text(character: dict[str, Any]) -> str:
    sheet = character.get("sheet") if isinstance(character.get("sheet"), dict) else {}
    parts = [
        character.get("backstory"),
        character.get("bonds"),
        character.get("personality_traits"),
        sheet.get("backstory"),
        sheet.get("bonds"),
        sheet.get("personality_traits"),
    ]
    return " ".join(str(part or "").strip() for part in parts if str(part or "").strip())


def _public_identity(name: str, level: str, class_name: str) -> str:
    level_text = f"seasoned level {level} " if level else ""
    if not class_name:
        return _trim_sentence(f"{name} is a {level_text}traveler with enough experience to notice when a scene is wrong")
    translated = _class_role_label(class_name)
    return _trim_sentence(f"{name} is a {level_text}{translated} whose reputation is useful but incomplete")


def _class_role_label(class_name: str) -> str:
    lowered = class_name.lower()
    if "paladin" in lowered and "warlock" in lowered:
        return "oath-bound pact bearer"
    if "paladin" in lowered:
        return "oath-sworn judge of dangerous vows"
    if "warlock" in lowered:
        return "bearer of an unspoken pact"
    if "wizard" in lowered:
        return "student of old sigils and broken formulae"
    if "rogue" in lowered:
        return "reader of tells, exits, and hidden hands"
    if "ranger" in lowered:
        return "tracker of terrain, weather, and unnatural silence"
    if "cleric" in lowered:
        return "keeper of rites who knows when sanctity has turned"
    if "fighter" in lowered:
        return "veteran of drilled movement and tactical threat"
    return "capable wanderer"


def _class_flavor_translation(name: str, class_name: str, object_name: str) -> str:
    """Translate a class into an investigative lens, never into new world facts.

    A character class tells us how a player *might approach* evidence. It does
    not prove that an object is magical, cursed, illegal, familiar, tied to a
    patron, or governed by some invented body of lore.
    """
    lowered = class_name.lower()
    if "paladin" in lowered and "warlock" in lowered:
        return f"{name} can examine the {object_name} through both oath and pact, but neither establishes what the object means or who is responsible."
    if "paladin" in lowered:
        return f"{name}'s experience with oaths may shape which promises and claims they question around the {object_name}; it does not establish that an oath was broken."
    if "warlock" in lowered:
        return f"{name}'s pact may shape the questions they ask about the {object_name}, but no supernatural connection to it is assumed."
    if "wizard" in lowered:
        return f"{name}'s training makes careful inspection of the {object_name} a natural approach, but no prior formula, law, or magical property is assumed."
    if "rogue" in lowered:
        return f"{name}'s experience with deception and access makes provenance, handling, exits, and opportunity useful questions around the {object_name}."
    if "ranger" in lowered:
        return f"{name}'s fieldcraft makes tracks, weather, movement, and physical disturbance useful things to inspect around the {object_name}."
    if "cleric" in lowered:
        return f"{name}'s religious experience may help them ask informed questions about any rites or claims involving the {object_name}, without assuming one occurred."
    if "fighter" in lowered:
        return f"{name}'s practical experience makes crowd position, weapons, and immediate danger useful things to watch while the {object_name} is examined."
    return f"{name} can investigate the {object_name} using their established skills without assuming knowledge the campaign has not provided."


def _character_reason_to_care(name: str, class_name: str, object_name: str, location: str) -> str:
    lowered = class_name.lower()
    if "paladin" in lowered and "warlock" in lowered:
        return f"{name} has a useful perspective on promises and bargains around the {object_name}, but the player still decides whether oath, pact, or simple curiosity makes this personal."
    if "paladin" in lowered:
        return f"{name} may choose to care about the claims surrounding the {object_name} because promises and accountability matter to them; no broken vow is assumed."
    if "warlock" in lowered:
        return f"{name} may choose to examine the {object_name} through the lens of their pact, but the campaign does not assume their patron knows or wants anything about it."
    if "wizard" in lowered:
        return f"{name} has the training to inspect the {object_name} carefully, but no special prior knowledge of its material, history, or rules is assumed."
    if "rogue" in lowered:
        return f"{name} has useful skills for asking who handled the {object_name}, how it moved, and who had access, without assuming a culprit."
    if "ranger" in lowered:
        return f"{name} has useful skills for examining the physical trail around the {object_name}, without assuming what that trail will prove."
    if "cleric" in lowered:
        return f"{name} can evaluate religious claims around the {object_name} if they arise, but no rite, blessing, or corruption is assumed."
    if "fighter" in lowered:
        return f"{name} can read immediate physical danger around the {object_name} while the facts are still uncertain."
    return f"{name} has a reason to look closely at the {object_name} at {location}, while the exact personal stake remains the player's choice."

def _concrete_object(seed: dict[str, Any], contract: dict[str, Any], fallback: str, *, strict: bool = False) -> str:
    object_name = _opening_object_name(seed, neutral_default=strict)
    if strict and object_name == NEUTRAL_OBJECT:
        return UNKNOWN_OBJECT
    if object_name:
        return f"The physical object that starts the mystery is the {object_name}."
    text = " ".join(str(seed.get(k) or contract.get(k) or "") for k in ("inciting_event", "first_clue_or_question", "campaign_pitch", "setting_summary", "description")).lower()
    if "ledger" in text:
        return "The physical object that starts the mystery is a marked ledger with the decisive entry cut away."
    if "bell" in text:
        return "The physical object that starts the mystery is a marked bell found where no bell should be."
    if "bowl" in text or "rite" in text:
        return "The physical object that starts the mystery is a blessing bowl stained by a rite that no longer behaves like a blessing."
    if "vote" in text or "charter" in text:
        return "The physical object that starts the mystery is a sealed cinder relic cracked open before the count can be certified."
    if "mine" in text:
        return "The physical object that starts the mystery is a scorched miners' charter with one signature burned away."
    if "harbor" in text:
        return "The physical object that starts the mystery is a cracked signal mirror recovered where no mirror should be."
    return f"The physical object that starts the mystery is the {fallback}."


def _institution_or_faction(seed: dict[str, Any], contract: dict[str, Any], location: str, *, strict: bool = False) -> str:
    text = " ".join(str(seed.get(k) or contract.get(k) or "") for k in ("inciting_event", "first_clue_or_question", "specific_stakes", "campaign_pitch", "setting_summary", "description")).lower()
    if "guild" in text or "charter" in text or "vote" in text or "mine" in text:
        return "Guild factions are fighting over the charter."
    if "harbor" in text or "envoy" in text:
        return "The harbor office and envoy guard are blaming each other."
    if "road" in text or "pass" in location.lower() or "route" in text:
        return "The road wardens and local refuge keepers disagree over who controls the crossing."
    if "observatory" in location.lower() or "star" in text or "moon" in text:
        return "The observatory staff and civic watch disagree over who may seal the evidence."
    if strict:
        return UNKNOWN_AUTHORITY
    return "The local authority and the people caught outside its protection are already in dispute."


def _institution_subject(institution: str) -> str:
    text = _clean_raw(institution).lower()
    for marker in (" are ", " is "):
        if marker in text:
            return text.split(marker, 1)[0].strip()
    if " disagree " in text:
        return text.split(" disagree ", 1)[0].strip()
    return text or "the people closest to the dispute"


def _visible_consequence(seed: dict[str, Any], contract: dict[str, Any], institution: str, *, strict: bool = False) -> str:
    stakes = _clean_raw(str(seed.get("specific_stakes") or seed.get("stakes") or ""))
    if stakes and not _is_raw_question(stakes) and not _is_weak_player_facing_text(stakes):
        return _trim_sentence(stakes)
    if strict and not stakes:
        return UNKNOWN_CONSEQUENCE
    text = " ".join(str(seed.get(k) or contract.get(k) or "") for k in ("inciting_event", "first_clue_or_question", "campaign_pitch", "setting_summary", "description")).lower()
    if "vote" in text or "charter" in text or "mine" in text:
        return "The wrong charter claim could gain legal control of the mines, roads, and workers before anyone proves fraud."
    if "vanish" in text or "missing" in text or "disappear" in text:
        return "The next witness may vanish before their account can be challenged."
    if "harbor" in text:
        return "The harbor may close ranks around a false account before ships leave with the evidence."
    if "road" in text or "pass" in text or "route" in text:
        return "The crossing may close, stranding travelers with whoever caused the first disappearance."
    return f"{institution} could settle the matter publicly before the first evidence is understood."


def _is_raw_question(text: str) -> bool:
    cleaned = _clean_raw(text).lower()
    return cleaned.endswith("?") or cleaned.startswith(("who ", "what ", "why ", "where ", "when ", "how "))


def _is_weak_player_facing_text(text: str) -> bool:
    lowered = _clean_raw(text).lower()
    weak = (
        "act on what is immediately visible",
        "person carrying the clearest lead",
        "trusted object",
        "wrong place",
        "truth is public",
        "wrong faction",
        "public story",
        "choose an approach",
        "set the tone",
        "covered clue",
        "first useful evidence",
        "same pressure",
        "practical reason",
        "someone is lying",
        "concrete clue",
        "visible clue",
        "if no one acts soon",
    )
    return any(phrase in lowered for phrase in weak)


# Honest placeholders for the campaign brief.  The brief's "known facts" are
# treated as canon by players, so when nothing was established we say so
# instead of inventing a crisis, a deadline, an authority, or an object.
UNKNOWN_PROBLEM = "What has gone wrong here has not been established yet."
UNKNOWN_URGENCY = "No deadline has been established yet."
UNKNOWN_AUTHORITY = "Who holds authority here has not been established yet."
UNKNOWN_CONSEQUENCE = "What is at stake has not been established yet."
UNKNOWN_OBJECT = "The first physical sign of trouble has not been established yet."
NEUTRAL_OBJECT = "first sign of trouble"

# brief unknown field -> brief validation checks it waives
_UNKNOWN_WAIVES = {
    "conflict": "immediate_problem",
    "stakes": "time_matters",
    "actor": "concrete_entity",
    "object": "concrete_entity",
}


def _natural_problem(seed: dict[str, Any], contract: dict[str, Any], *, strict: bool = False) -> str:
    inciting = _clean_raw(str(seed.get("inciting_event") or ""))
    clue = _clean_raw(str(seed.get("first_clue_or_question") or ""))
    pitch = _clean_raw(str(contract.get("campaign_pitch") or contract.get("setting_summary") or contract.get("description") or ""))
    lower = " ".join([inciting, clue, pitch]).lower()
    if strict and not (inciting or clue or pitch):
        return UNKNOWN_PROBLEM
    if "vanish" in lower or "disappear" in lower or "missing" in lower:
        return "Travelers and witnesses have vanished, and the old route is becoming a dangerous mystery."
    if "lie" in lower or "lying" in lower or _is_raw_question(clue):
        return "Three witnesses contradict each other: one names a hand at the object, one swears the room was empty, and one refuses to say whose voice they heard."
    if "clue" in lower or "mirror" in lower or "ledger" in lower or "seal" in lower:
        return "The first physical sign of trouble has already made the locals afraid to speak plainly."
    if inciting and not _is_raw_question(inciting) and not _is_weak_player_facing_text(inciting):
        return _trim_sentence(inciting)
    if pitch:
        return "A local crisis has turned the opening road into a mystery no one can safely ignore."
    return "A local crisis has made the first scene dangerous before the party arrives."


def _natural_urgency(seed: dict[str, Any], contract: dict[str, Any], *, strict: bool = False) -> str:
    stakes = _clean_raw(str(seed.get("specific_stakes") or seed.get("stakes") or ""))
    if stakes and not _is_raw_question(stakes) and not _is_weak_player_facing_text(stakes):
        return _trim_sentence(stakes)
    if strict and not stakes:
        return UNKNOWN_URGENCY
    text = " ".join(str(seed.get(k) or contract.get(k) or "") for k in ("inciting_event", "campaign_pitch", "setting_summary")).lower()
    object_name = _opening_object_name({**contract, **seed})
    if "road" in text or "pass" in text or "route" in text:
        return f"At dusk, the road wardens will close the crossing and carry the {object_name} behind their barricade."
    if "harbor" in text or "envoy" in text:
        return f"At the next tide bell, the harbor office will seal the quay and send the {object_name} aboard an outbound ship."
    return f"Before the final public count, the {object_name} may be locked away by whoever claims authority here."


def _natural_rumor(seed: dict[str, Any], contract: dict[str, Any], *, strict: bool = False) -> str:
    rumor = _clean_raw(str(seed.get("rumor") or seed.get("conflicting_claim") or seed.get("player_decision") or ""))
    if rumor and not _is_raw_question(rumor) and not _is_weak_player_facing_text(rumor):
        return _trim_sentence(rumor)
    clue = _clean_raw(str(seed.get("first_clue_or_question") or ""))
    if _is_raw_question(clue):
        lowered = clue.lower()
        if "lying" in lowered or "lie" in lowered:
            return "Some blame frightened witnesses; others insist the official account is false."
        if "who" in lowered:
            return "Everyone has a suspect, but no two accounts point to the same person."
        if "what" in lowered:
            return "People argue over what happened, and each version leaves something important out."
    pitch = _clean_raw(str(contract.get("campaign_pitch") or contract.get("setting_summary") or ""))
    if "sabotage" in pitch.lower():
        return "Some call it sabotage; others say the accusation is a cover for older guilt."
    if strict:
        return ""
    return "The rumors contradict each other, and no one wants to be the first to speak plainly."


def _natural_clue(seed: dict[str, Any], contract: dict[str, Any]) -> str:
    obj = _object_hint(seed, contract)
    if obj:
        return f"The visible object is {obj}, but its meaning is not settled."
    clue = _clean_raw(str(seed.get("first_clue_or_question") or ""))
    if clue and not _is_raw_question(clue) and not _is_weak_player_facing_text(clue):
        return _trim_sentence(clue)
    return "The first physical sign is visible enough to draw attention, but not enough to solve the mystery."


def _natural_location_identity(location: str, seed: dict[str, Any], contract: dict[str, Any]) -> str:
    identity = _clean_raw(str(seed.get("location_identity") or ""))
    if identity and not _is_raw_question(identity) and not _is_weak_player_facing_text(identity):
        return _trim_sentence(identity)
    loc = _clean_raw(location) or "the starting location"
    lower = loc.lower()
    if "pass" in lower:
        return f"{loc} is an old crossing where delays can strand travelers between shelter and danger."
    if "harbor" in lower:
        return f"{loc} is a working harbor where news, cargo, and fear move faster than guards can follow."
    if "observatory" in lower:
        return f"{loc} is a remote watchpoint where strange signs are supposed to be studied, not hidden."
    if "road" in lower or "crossing" in lower:
        return f"{loc} is a traveled route that has become unsafe for reasons no one agrees on."
    return f"{loc} is where the campaign's first public trouble has surfaced."


_SEED_OBJECT_FIELDS = ("approved_object", "first_clue_or_question", "inciting_event", "location_identity")
_CAMPAIGN_OBJECT_FIELDS = ("campaign_pitch", "setting_summary", "description")


def _opening_object_name(required: dict[str, Any], *, neutral_default: bool = False) -> str:
    """Name the opening's object.

    ``neutral_default`` is the strict mode used for the campaign brief, whose
    "known facts" are treated as canon.  It reads only the fields the opening
    seed itself supplies: a lone keyword in the campaign pitch ("harvest")
    must not become a concrete invented object ("harvest ledger").
    """
    fields = _SEED_OBJECT_FIELDS if neutral_default else (*_SEED_OBJECT_FIELDS, *_CAMPAIGN_OBJECT_FIELDS)
    text = " ".join(str(required.get(k) or "") for k in fields).lower()
    if "token" in text:
        return "funeral token"
    if "corpse" in text or "body" in text:
        return "wrong corpse"
    if "blood mark" in text or "bloodmark" in text:
        return "blood mark"
    if "metal fruit" in text or "gravity fruit" in text:
        return "metal fruit"
    if "track" in text:
        return "stopped tracks"
    if "harvest" in text:
        return "harvest ledger"
    if "reliquary" in text:
        return "covered reliquary"
    if "mirror" in text:
        return "cracked signal mirror"
    if "ledger" in text:
        return "marked ledger"
    if "seal" in text:
        return "broken seal"
    if "bell" in text:
        return "forbidden bell"
    if "charm" in text:
        return "blackened charm"
    if "packet" in text:
        return "sealed packet"
    if "warning" in text:
        return "damaged warning notice"
    return NEUTRAL_OBJECT if neutral_default else "sealed letter"


def _opening_sensory_detail(location: str, required: dict[str, Any], object_name: str) -> str:
    lower = f"{location} {required.get('location_identity') or ''}".lower()
    if "market" in lower:
        return f"sagging canvas awnings, bruised fruit, and the low hum coming from the {object_name}"
    if "harbor" in lower:
        return f"salt air, wet rope, gull cries, and lanternlight catching on the {object_name}"
    if "pass" in lower or "road" in lower:
        return f"cold road dust, wind-bent warning flags, and travelers pretending not to stare at the {object_name}"
    if "observatory" in lower:
        return f"cold brass instruments, ink-stained charts, and a thin vibration around the {object_name}"
    return f"uneasy quiet, hard faces, and everyone watching the {object_name}"


def _opening_visible_problem(required: dict[str, Any], npc_name: str, object_name: str) -> str:
    event = _clean_raw(str(required.get("inciting_event") or required.get("immediate_problem") or ""))
    if event and not _is_raw_question(event) and not _is_weak_player_facing_text(event):
        return f"{event}. The {object_name} sits where everyone can see it, but no one wants to claim it."
    clue = _clean_raw(str(required.get("first_clue_or_question") or ""))
    if "lying" in clue.lower() or _is_raw_question(clue):
        return f"Three accounts already contradict each other while {_mid_sentence(npc_name)} guards the {object_name} like it might accuse someone aloud."
    return f"{npc_name} stands beside the {object_name}, and the crowd has gone quiet in the wrong way."


def pc_start_sentence(pc: str) -> str:
    return pc[0].upper() + pc[1:] if pc else pc


def _opening_personal_hook(anchor: dict[str, Any], pc: str, object_name: str, location: str) -> str:
    arrival = _clean_raw(str(anchor.get("arrival_reason") or ""))
    stake = _clean_raw(str(anchor.get("personal_stake") or ""))
    fear = _clean_raw(str(anchor.get("fear_of_loss") or ""))
    if arrival and stake:
        return f"{pc_start_sentence(pc)} reaches {location} with a reason already in motion, and the {object_name} turns that reason into an immediate choice."
    if arrival:
        return f"{pc_start_sentence(pc)} reaches {location} with a reason of their own, and the {object_name} makes it urgent."
    if stake:
        return f"For {pc}, the {object_name} is personal enough that leaving it to strangers would cost more than time."
    if fear:
        return f"{pc_start_sentence(pc)} feels the weight of what could be lost as the {object_name} draws every eye."
    return f"{pc_start_sentence(pc)} can see for themselves that the {object_name} at {location} is no ordinary matter."


def _opening_pressure(required: dict[str, Any], npc_name: str) -> str:
    stakes = _clean_raw(str(required.get("specific_stakes") or ""))
    lower = stakes.lower()
    if _is_weak_player_facing_text(stakes):
        stakes = ""
        lower = ""
    if "dusk" in lower or "dawn" in lower or "hour" in lower:
        return f"{npc_name} keeps glancing at the sinking light because the lead will be gone before the next watch changes."
    if "road" in lower or "pass" in lower or "close" in lower:
        return f"By dusk, the pass wardens will close the road and {_mid_sentence(npc_name)} will lose the only cooperative witness."
    if "harbor" in lower or "envoy" in lower:
        return "When the tide turns, the harbor watch will seal the quay and the clearest lead will be moved."
    return "Before the next bell, someone here will leave with the clearest lead."


def _opening_action_options(npc_name: str, object_name: str, location: str, visible_problem: str) -> list[str]:
    options = [
        f"Study the {object_name}",
        f"Question {_mid_sentence(npc_name)}",
        f"Watch {location} quietly",
    ]
    if "survivor" in visible_problem.lower() or "account" in visible_problem.lower():
        options.append("Follow the witness preparing to leave")
    else:
        options.append(f"Inspect where the {object_name} was placed")
    return options


def _brief_sentences(campaign_brief: dict[str, Any]) -> list[str]:
    sentences: list[str] = []
    for value in list(campaign_brief.get("brief_paragraphs") or []) + list(campaign_brief.get("known_facts") or []):
        for part in str(value or "").split("."):
            sentence = _clean_raw(part)
            if sentence:
                sentences.append(sentence)
    return list(dict.fromkeys(sentences))


_FIRST_PERSON = re.compile(r"^\s*(?:i|i'm|i\u2019m|i've|i\u2019ve|i'd|we|we're|my|our)\b", re.IGNORECASE)


def _pre_scene_from_arrival(arrival: str) -> str:
    if not arrival:
        return ""
    if _FIRST_PERSON.match(arrival):
        return ""  # a first-person answer cannot be turned into "was already trying to I ..."
    first = arrival[0].lower() + arrival[1:] if arrival else arrival
    return f"was already trying to {first.rstrip('.')}"


def _keywords_present(expected: str, lower_text: str) -> bool:
    words = [
        w.lower()
        for w in expected.replace("’", "'").split()
        if len(w) > 4 and w.lower().strip(".,!?") not in {"before", "after", "through", "someone", "something"}
    ]
    if not words:
        return False
    return sum(1 for w in words if w.strip(".,!?") in lower_text) >= min(2, len(words))
