"""Opening setup questionnaire and character anchor helpers."""
from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field


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
    trouble = _natural_problem(seed, camp)
    urgency = _natural_urgency(seed, camp)
    rumor = _natural_rumor(seed, camp)
    clue = _natural_clue(seed, camp)
    place_identity = _natural_location_identity(location, seed, camp)
    object_name = _opening_object_name({**camp, **seed})
    concrete_object = _concrete_object(seed, camp, object_name)
    institution = _institution_or_faction(seed, camp, location)
    visible_consequence = _visible_consequence(seed, camp, institution)
    char_context = naturalize_character_knowledge(char, {**camp, **seed, "object_name": object_name}, anchor)
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
    facts = [_trim_sentence(f) for f in facts if f]
    place_intro = f"{title} begins at {location}, {place_identity[0].lower() + place_identity[1:] if place_identity else 'where the first public trouble has surfaced.'}"
    if place_identity.lower().startswith(location.lower()):
        place_intro = f"{title} begins at {place_identity}"
    paragraphs = [
        place_intro,
        f"{trouble} {concrete_object}",
        f"{urgency} {visible_consequence}",
        char_context,
    ]
    paragraphs = [_trim_sentence(p) for p in paragraphs if p]
    brief = {
        "title": title,
        "location_name": location,
        "brief_paragraphs": paragraphs[:4],
        "known_facts": facts[:6],
        "character_anchor": anchor,
        "character_entry_prompt": f"{char_name} arrives before the truth is known. Decide why this mystery has pulled {char_name} here.",
    }
    validation = validate_campaign_brief(brief)
    if not validation["valid"]:
        brief = _repair_campaign_brief(brief, seed, camp, char)
        validation = validate_campaign_brief(brief)
    brief["quality_debug"] = validation
    return brief


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
    object_name = _opening_object_name(prem)
    location = str(prem.get("starting_location") or prem.get("location_name") or "the starting place").strip()
    institution = _institution_or_faction(prem, prem, location)
    institution_subject = _institution_subject(institution)
    class_flavor = _class_flavor_translation(name, class_name, object_name)
    backstory = _character_backstory_text(char)
    if backstory:
        reason = f"{name} has already lost enough to know the {object_name} cannot be treated as local gossip."
        tension = f"{name} keeps one personal obligation private while weighing what the trouble at {location} might expose."
    else:
        reason = _character_reason_to_care(name, class_name, object_name, location)
        tension = f"{name} does not yet know whether helping {institution_subject} will settle an old debt or deepen it."
    connection = f"{name} has heard that {institution_subject} is tied to the first dispute, and the {object_name} is the part no one can explain cleanly."
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
    object_name = str(prem.get("object_name") or _opening_object_name(prem)).strip() or "first physical sign"
    flavor = anch.get("class_flavor_translation") or _class_flavor_translation(name, str(char.get("class_name") or ""), object_name)
    reason = anch.get("reason_to_care") or ""
    if reason:
        return _trim_sentence(f"{flavor} {reason}")
    return _trim_sentence(flavor)


naturalizeCharacterKnowledge = naturalize_character_knowledge


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
    for key, ok in checks.items():
        if not ok:
            issues.append(key)
    return {"valid": not issues, "issues": issues, "checks": checks}


def _repair_campaign_brief(
    brief: dict[str, Any],
    seed: dict[str, Any],
    camp: dict[str, Any],
    char: dict[str, Any],
) -> dict[str, Any]:
    title = str(brief.get("title") or camp.get("campaign_name") or "This campaign")
    location = str(brief.get("location_name") or seed.get("starting_location") or "the starting location")
    object_name = _opening_object_name({**camp, **seed})
    institution = _institution_or_faction(seed, camp, location)
    place = _natural_location_identity(location, seed, camp)
    trouble = _natural_problem(seed, camp)
    consequence = _visible_consequence(seed, camp, institution)
    anchor = brief.get("character_anchor") or generate_provisional_character_anchor(character=char, premise={**camp, **seed})
    knowledge = naturalize_character_knowledge(char, {**camp, **seed, "object_name": object_name}, anchor)
    place_sentence = place if place.lower().startswith(location.lower()) else f"{location}, {place[0].lower() + place[1:]}"
    institution_clean = _clean_raw(institution)
    repaired = {
        **brief,
        "brief_paragraphs": [
            _trim_sentence(f"{title} begins at {place_sentence}"),
            _trim_sentence(f"{trouble} The physical object drawing every eye is the {object_name}, and {institution_clean.lower()} cannot agree what it proves"),
            _trim_sentence(f"By the next bell, {consequence[0].lower() + consequence[1:]}"),
            knowledge,
        ],
        "known_facts": [
            _trim_sentence(place),
            _trim_sentence(f"The immediate problem is that {trouble[0].lower() + trouble[1:]}"),
            _trim_sentence(f"The physical object that starts the mystery is the {object_name}"),
            _trim_sentence(institution),
            _trim_sentence(consequence),
            knowledge,
        ],
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
    arrival = values.get("arrival_reason") or _auto_answer(questionnaire, "arrival_reason")
    stake = values.get("personal_stake") or _auto_answer(questionnaire, "personal_stake")
    npc = values.get("npc_connection") or _auto_answer(questionnaire, "npc_connection")
    party_bond = values.get("party_bond") or _auto_answer(questionnaire, "party_bond")
    followed_complication = values.get("followed_complication") or _auto_answer(questionnaire, "followed_complication")
    fear_of_loss = values.get("fear_of_loss") or _auto_answer(questionnaire, "fear_of_loss")
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


def auto_generate_anchor(
    *,
    session_id: str,
    campaign_id: str = "",
    questionnaire: dict[str, Any],
    character: dict[str, Any] | None = None,
    character_hook_override: str = "",
) -> dict[str, Any]:
    answers = []
    for q in questionnaire.get("questions", []):
        options = [opt for opt in (q.get("options") or []) if opt.get("id") != "ai_choose"]
        if options:
            answers.append({"question_id": q.get("id"), "option_id": options[0].get("id")})
    return answers_to_anchor(
        session_id=session_id,
        campaign_id=campaign_id,
        character=character,
        questionnaire=questionnaire,
        answers=answers,
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


def build_opening_scene_contract(
    *,
    required: dict[str, Any] | None,
    anchor: dict[str, Any] | None,
    campaign_brief: dict[str, Any] | None,
    player_name: str = "",
    time_of_day: str = "day",
) -> dict[str, Any]:
    req = required or {}
    anch = anchor or {}
    brief = campaign_brief or {}
    pc = str(anch.get("character_name") or player_name or "the party").strip() or "the party"
    location = str(req.get("starting_location") or brief.get("location_name") or "the opening location").strip()
    npc_label = str(req.get("named_npc_or_visible_threat") or "Warden Hale (local witness)")
    npc_name = npc_label.split("(")[0].strip() or "Warden Hale"
    object_name = _opening_object_name(req)
    sensory = _opening_sensory_detail(location, req, object_name)
    visible_problem = _opening_visible_problem(req, npc_name, object_name)
    personal_hook = _opening_personal_hook(anch, pc, object_name, location)
    pressure = _opening_pressure(req, npc_name)
    actions = _opening_action_options(npc_name, object_name, location, visible_problem)
    narrative = (
        f"{location} is already too quiet for {time_of_day}.\n\n"
        f"{pc} arrives through {sensory}. {visible_problem}\n\n"
        f"{personal_hook}\n\n"
        f"{npc_name} is close enough to intervene, but not calm enough to hide what is wrong. "
        f"{pressure}\n\n"
        f"{pc} can {', '.join(action[0].lower() + action[1:] for action in actions[:3])}, "
        f"or {actions[3][0].lower() + actions[3][1:]}."
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
    }


def validate_opening_scene_contract(
    *,
    scene: dict[str, Any],
    opening_scene: dict[str, Any] | None = None,
    campaign_brief: dict[str, Any] | None = None,
    anchor: dict[str, Any] | None = None,
    player_name: str = "",
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
    return {
        "valid": not issues,
        "issues": issues,
        "checks": checks,
        "repeated_brief_sentences": repeated,
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
        return "bearer of a pact that notices forbidden pressure"
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
    lowered = class_name.lower()
    if "paladin" in lowered and "warlock" in lowered:
        return f"{name} recognizes two kinds of power around the {object_name}: the lawful pull of an oath, and the colder pressure of a pact that answers when prayer goes too long."
    if "paladin" in lowered:
        return f"{name} feels a vow tighten around the {object_name}, the kind of sacred unease that turns judgment into duty."
    if "warlock" in lowered:
        return f"{name} feels the {object_name} answer with a private pressure, like a debt being named by something just out of sight."
    if "wizard" in lowered:
        return f"{name} notices the old formulae around the {object_name} do not agree with the story being told aloud."
    if "rogue" in lowered:
        return f"{name} reads the tells around the {object_name}: blocked exits, careful hands, and lies rehearsed too cleanly."
    if "ranger" in lowered:
        return f"{name} notices the unnatural quiet around the {object_name}, where tracks, weather, and crowd movement should make more sense."
    if "cleric" in lowered:
        return f"{name} senses a rite around the {object_name} has been bent away from blessing and toward accusation."
    if "fighter" in lowered:
        return f"{name} reads the threat around the {object_name} in stance, spacing, and the way weapons are kept too close."
    return f"{name} recognizes enough about the {object_name} to know the visible problem is only the first edge of it."


def _character_reason_to_care(name: str, class_name: str, object_name: str, location: str) -> str:
    lowered = class_name.lower()
    if "paladin" in lowered and "warlock" in lowered:
        return f"{name}'s oath demands judgment over the {object_name}, while the pact behind it whispers that {location} is hiding a debt older than the public vote."
    if "paladin" in lowered:
        return f"{name}'s vows make the {object_name} impossible to ignore: someone has bent sworn law in a place where judgment still matters."
    if "warlock" in lowered:
        return f"{name}'s patron stirs at the {object_name}, naming it as payment, warning, or bait before anyone else hears the bargain."
    if "wizard" in lowered:
        return f"{name} recognizes an impossible pattern in the {object_name}, the kind of formula that should not survive outside a sealed archive."
    if "rogue" in lowered:
        return f"{name} recognizes the hand behind the {object_name}: someone moved it through blind corners, paid silence, and planned exits."
    if "ranger" in lowered:
        return f"{name} reads the ground around the {object_name} and sees a trail that should continue but stops where nature would never stop it."
    if "cleric" in lowered:
        return f"{name} feels a rite curdled around the {object_name}, turning a blessing into an accusation that cannot be left unanswered."
    if "fighter" in lowered:
        return f"{name} reads the crowd around the {object_name} like a battlefield: the dangerous people are already choosing positions."
    return f"{name} has seen enough trouble to know the {object_name} at {location} will name a victim before it names a culprit."


def _concrete_object(seed: dict[str, Any], contract: dict[str, Any], fallback: str) -> str:
    object_name = _opening_object_name(seed)
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


def _institution_or_faction(seed: dict[str, Any], contract: dict[str, Any], location: str) -> str:
    text = " ".join(str(seed.get(k) or contract.get(k) or "") for k in ("inciting_event", "first_clue_or_question", "specific_stakes", "campaign_pitch", "setting_summary", "description")).lower()
    if "guild" in text or "charter" in text or "vote" in text or "mine" in text:
        return "Guild factions are fighting over the charter."
    if "harbor" in text or "envoy" in text:
        return "The harbor office and envoy guard are blaming each other."
    if "road" in text or "pass" in location.lower() or "route" in text:
        return "The road wardens and local refuge keepers disagree over who controls the crossing."
    if "observatory" in location.lower() or "star" in text or "moon" in text:
        return "The observatory staff and civic watch disagree over who may seal the evidence."
    return "The local authority and the people caught outside its protection are already in dispute."


def _institution_subject(institution: str) -> str:
    text = _clean_raw(institution).lower()
    for marker in (" are ", " is "):
        if marker in text:
            return text.split(marker, 1)[0].strip()
    if " disagree " in text:
        return text.split(" disagree ", 1)[0].strip()
    return text or "the people closest to the dispute"


def _visible_consequence(seed: dict[str, Any], contract: dict[str, Any], institution: str) -> str:
    stakes = _clean_raw(str(seed.get("specific_stakes") or seed.get("stakes") or ""))
    if stakes and not _is_raw_question(stakes) and not _is_weak_player_facing_text(stakes):
        return _trim_sentence(stakes)
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


def _clean_raw(raw: str) -> str:
    text = " ".join(str(raw or "").replace("\n", " ").split()).strip()
    text = text.strip(" .")
    return text


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


def _trim_sentence(text: str) -> str:
    cleaned = _clean_raw(text)
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith((".", "!", "?")) else f"{cleaned}."


def _natural_problem(seed: dict[str, Any], contract: dict[str, Any]) -> str:
    inciting = _clean_raw(str(seed.get("inciting_event") or ""))
    clue = _clean_raw(str(seed.get("first_clue_or_question") or ""))
    pitch = _clean_raw(str(contract.get("campaign_pitch") or contract.get("setting_summary") or contract.get("description") or ""))
    lower = " ".join([inciting, clue, pitch]).lower()
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


def _natural_urgency(seed: dict[str, Any], contract: dict[str, Any]) -> str:
    stakes = _clean_raw(str(seed.get("specific_stakes") or seed.get("stakes") or ""))
    if stakes and not _is_raw_question(stakes) and not _is_weak_player_facing_text(stakes):
        return _trim_sentence(stakes)
    text = " ".join(str(seed.get(k) or contract.get(k) or "") for k in ("inciting_event", "campaign_pitch", "setting_summary")).lower()
    object_name = _opening_object_name({**contract, **seed})
    if "road" in text or "pass" in text or "route" in text:
        return f"At dusk, the road wardens will close the crossing and carry the {object_name} behind their barricade."
    if "harbor" in text or "envoy" in text:
        return f"At the next tide bell, the harbor office will seal the quay and send the {object_name} aboard an outbound ship."
    return f"Before the final public count, the {object_name} may be locked away by whoever claims authority here."


def _natural_rumor(seed: dict[str, Any], contract: dict[str, Any]) -> str:
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


def _opening_object_name(required: dict[str, Any]) -> str:
    text = " ".join(str(required.get(k) or "") for k in (
        "approved_object",
        "first_clue_or_question",
        "inciting_event",
        "location_identity",
        "campaign_pitch",
        "setting_summary",
        "description",
    )).lower()
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
    return "sealed letter"


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
        return f"{event}. {object_name[0].upper() + object_name[1:]} sits where everyone can see it, but no one wants to claim it."
    clue = _clean_raw(str(required.get("first_clue_or_question") or ""))
    if "lying" in clue.lower() or _is_raw_question(clue):
        return f"Three accounts already contradict each other while {npc_name} guards the {object_name} like it might accuse someone aloud."
    return f"{npc_name} stands beside the {object_name}, and the crowd has gone quiet in the wrong way."


def _opening_personal_hook(anchor: dict[str, Any], pc: str, object_name: str, location: str) -> str:
    arrival = _clean_raw(str(anchor.get("arrival_reason") or ""))
    stake = _clean_raw(str(anchor.get("personal_stake") or ""))
    fear = _clean_raw(str(anchor.get("fear_of_loss") or ""))
    if arrival and stake:
        return f"{pc} reaches {location} with a reason already in motion, and the {object_name} turns that reason into an immediate choice."
    if arrival:
        return f"{pc} reaches {location} because the trail here already touches a promise, debt, or danger they cannot ignore."
    if stake:
        return f"For {pc}, the {object_name} is personal enough that leaving it to strangers would cost more than time."
    if fear:
        return f"{pc} can feel the old fear behind this moment tighten as the {object_name} draws every eye."
    return f"{pc} recognizes enough about {object_name} and {location} to know this is not ordinary trouble."


def _opening_pressure(required: dict[str, Any], npc_name: str) -> str:
    stakes = _clean_raw(str(required.get("specific_stakes") or ""))
    lower = stakes.lower()
    if _is_weak_player_facing_text(stakes):
        stakes = ""
        lower = ""
    if "dusk" in lower or "dawn" in lower or "hour" in lower:
        return f"{npc_name} keeps glancing at the sinking light because the lead will be gone before the next watch changes."
    if "road" in lower or "pass" in lower or "close" in lower:
        return f"By dusk, the pass wardens will close the road and {npc_name} will lose the only cooperative witness."
    if "harbor" in lower or "envoy" in lower:
        return f"When the tide turns, the harbor watch will seal the quay and the clearest lead will be moved."
    return f"Before the next bell, someone here will leave with the clearest lead."


def _opening_action_options(npc_name: str, object_name: str, location: str, visible_problem: str) -> list[str]:
    options = [
        f"Study the {object_name}",
        f"Question {npc_name}",
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


def _auto_answer(questionnaire: dict[str, Any] | None, qid: str) -> str:
    for q in (questionnaire or {}).get("questions", []):
        if q.get("id") == qid and q.get("options"):
            for opt in q["options"]:
                if opt.get("id") == "ai_choose":
                    continue
                return str(opt.get("value") or opt.get("label") or "")
    return ""


def _pre_scene_from_arrival(arrival: str) -> str:
    if not arrival:
        return ""
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
