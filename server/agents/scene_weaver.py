"""Write one coherent opening scene from the facts the campaign already established.

The opening pipeline can end up with a scene stitched together from separate repairs: the character's own setup
answers quoted back, a template, and appended fragments.  Each part is valid alone, but together they repeat
themselves, name people nobody introduced, and read as a list.  This module makes a single bounded model call that
writes the scene as one piece of fiction in a fixed order (where and when, what is happening, who is here, what
the character brings, what is at stake), then checks the result mechanically.  A draft that fails any check is
discarded and the caller keeps the scene it already has, so this can only improve an opening, never block one.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from .opening_voice import first_to_third, usable_answer

logger = logging.getLogger("taverntails.scene_weaver")

MIN_WORDS = 90
MAX_WORDS = 260

_NIGHT_WORDS = re.compile(
    r"\b(?:night|nighttime|nightfall|midnight|moonlit|moonlight|moon|starlit|starlight|stars|after dark|darkness fell)\b", re.IGNORECASE)
_DAY_WORDS = re.compile(r"\b(?:day|daylight|daytime|midday|noon|sunlit|sunshine|sunny|morning|afternoon)\b", re.IGNORECASE)
# "<Name> can look closely at X, question Y, watch Z, or follow W" - a menu of options written as prose.
_OPTION_MENU = re.compile(r"\b(?:can|could|may|might)\b[^.!?]{0,160}(?:,[^.!?]{3,90}){2,}[,\s]+or\b", re.IGNORECASE)
_DAY_TIMES = {"day", "morning", "noon", "midday", "afternoon", "dawn"}
_NIGHT_TIMES = {"night", "midnight", "evening", "dusk"}


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _npc_name_and_role(label: str) -> tuple[str, str]:
    """``"Tobias Fell (lead witness)"`` -> ``("Tobias Fell", "lead witness")``."""
    label = _clean(label)
    if "(" in label:
        name, _, rest = label.partition("(")
        return _clean(name), _clean(rest.rstrip(") "))
    return label, ""


def build_facts(
    *,
    location: str,
    time_of_day: str,
    weather: str = "",
    player_name: str,
    anchor: dict | None,
    required: dict | None,
    opening_scene: dict | None = None,
    brief_sentences: list[str] | None = None,
) -> dict[str, Any]:
    """Everything the opening may say, taken only from what the campaign and the player already established."""
    anchor = anchor or {}
    if str(anchor.get("source") or "") == "auto_generated":
        # Nobody wrote these answers: the scene need not echo generic filler and must not be graded on it.
        anchor = {k: v for k, v in anchor.items() if k in ("character_name", "source")}
    required = required or {}
    contract = opening_scene or {}
    npc_label = _clean(required.get("named_npc_or_visible_threat")) or _clean((contract.get("named_npcs") or [""])[0])
    npc_name, npc_role = _npc_name_and_role(npc_label)
    if npc_name.lower().startswith("the nearest"):
        npc_name = ""  # the placeholder for "no named contact" is not a name
    what_is_happening = _clean(required.get("inciting_event")) or _clean(contract.get("visible_problem"))
    return {
        "location": _clean(location) or _clean(required.get("starting_location")),
        "time_of_day": _clean(time_of_day) or "day",
        "weather": _clean(weather),
        "player": _clean(player_name) or _clean(anchor.get("character_name")) or "the party",
        "place_identity": _clean(required.get("location_identity")),
        "happening": what_is_happening,
        "problem": _clean(required.get("immediate_problem")),
        "npc_name": npc_name,
        "npc_role": npc_role,
        "open_question": _clean(required.get("first_clue_or_question")),
        "stakes": _clean(required.get("specific_stakes")) or _clean(contract.get("pressure_or_timer")),
        "clock": _clean(contract.get("pressure_or_timer")),
        "object": _clean(required.get("approved_object")) or "",
        "reason_for_coming": usable_answer(anchor.get("arrival_reason")),
        "why_it_matters": usable_answer(anchor.get("personal_stake")),
        "what_they_fear_losing": usable_answer(anchor.get("fear_of_loss")),
        "knows_here": usable_answer(anchor.get("known_npc_connection")),
        "brief_sentences": list(brief_sentences or []),
    }


def _fact_lines(facts: dict[str, Any]) -> list[str]:
    player = facts["player"]
    lines = [f"PLACE: {facts['location']}", f"TIME OF DAY: {facts['time_of_day']}"]
    if facts.get("weather"):
        lines.append(f"WEATHER: {facts['weather']}")
    if facts.get("place_identity"):
        lines.append(f"WHAT KIND OF PLACE: {facts['place_identity']}")
    if facts.get("happening"):
        lines.append(f"WHAT IS HAPPENING RIGHT NOW: {facts['happening']}")
    if facts.get("problem") and facts["problem"] != facts.get("happening"):
        lines.append(f"THE IMMEDIATE PROBLEM: {facts['problem']}")
    if facts.get("npc_name"):
        role = f" ({facts['npc_role']})" if facts.get("npc_role") else ""
        lines.append(f"ONE PERSON PRESENT: {facts['npc_name']}{role}")
    if facts.get("object"):
        lines.append(f"THE OBJECT THAT MATTERS: {facts['object']}")
    if facts.get("open_question"):
        lines.append(f"THE MYSTERY NOBODY CAN EXPLAIN YET (state it as something people avoid, never as a question): {facts['open_question']}")
    if facts.get("stakes"):
        lines.append(f"WHAT IS AT STAKE / THE CLOCK (restate in new words, do not copy it): {facts['stakes']}")
    if facts.get("clock") and facts["clock"] != facts.get("stakes"):
        lines.append(f"A CLOCK THE SCENE MUST CONVEY (restate in new words, as something that will happen later): {facts['clock']}")
    for label, key in (
        ("WHY " + player.upper() + " CAME (their own words, first person)", "reason_for_coming"),
        ("WHY IT MATTERS TO " + player.upper() + " (their own words)", "why_it_matters"),
        (player.upper() + " DOES NOT WANT TO LOSE (their own words)", "what_they_fear_losing"),
        ("WHAT " + player.upper() + " SAYS ABOUT THE PEOPLE HERE (their own words)", "knows_here"),
    ):
        if facts.get(key):
            lines.append(f"{label}: {facts[key]}")
    return lines


def _messages(facts: dict[str, Any], feedback: str = "") -> list[dict]:
    player = facts["player"]
    time = facts["time_of_day"]
    system = (
        "You write the opening scene of a tabletop roleplaying campaign. A player will read it and then decide what "
        f"their character, {player}, does. Write ONE coherent scene, not a summary and not a list.\n\n"
        "Write in this order, one short paragraph each, with a blank line between paragraphs:\n"
        f"1. Where and when: name the place ({facts['location']}) in the first sentence and make the time of day "
        f"({time}) clear through light and sound. Say how {player} comes to be here.\n"
        "2. What is happening right now, shown through things the character can see or hear.\n"
        "3. The person present: describe what they are doing before you give their name, then use the name. "
        "Do not use a name the facts do not give.\n"
        f"4. What {player} brings: turn their own words into narration in the third person (use their name or "
        "'they'). Never quote their words back and never write them as a list.\n"
        "5. What is at stake and the clock, as something that will happen later, not something already happening. "
        "End on one concrete beat the character can see or hear, not on a question.\n\n"
        "Hard rules:\n"
        f"- {MIN_WORDS + 30}-{MAX_WORDS - 50} words. Plain, concrete prose. No headings, labels or bullet points.\n"
        "- Use ONLY the facts below. Invent no names, objects, motives or history beyond them. You may add ordinary "
        "sensory detail (light, sound, smell) that does not change the facts.\n"
        "- Do not give the character belongings or tools (no notebook, weapon, lantern), do not invent buildings, "
        "doors or furniture, and do not hint that anyone knows or hides more than the facts say.\n"
        "- Mention each fact once. Do not repeat a sentence or restate the same idea.\n"
        "- Do NOT copy a fact sentence word for word; say it in new words.\n"
        "- Do NOT write a question anywhere. Do NOT list what the character could do, and never write sentences like "
        "'X can look closely, question Y, or watch Z'.\n"
        f"- The scene happens in the {time}. Do not describe any other time of day as the present; a deadline like "
        "'the doors lock at dusk' is in the future.\n"
        "- No mention of 'the scene', 'the player', or of these instructions. "
        + ("Refer to the group as 'the party' and to its members as 'they'.\n\n" if player.lower() == "the party"
           else "Never write 'the party'; use the character's name.\n\n")
        + "Return only the scene text."
    )
    user = "FACTS:\n" + "\n".join(_fact_lines(facts))
    if feedback:
        user += "\n\nYOUR PREVIOUS DRAFT WAS REJECTED. FIX THESE PROBLEMS:\n" + feedback
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", _clean(text)) if s.strip()]


def _ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z']+", text.lower())
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


_FILLER = frozenset({"about", "before", "after", "their", "there", "where", "which", "while", "would", "could", "should",
                     "because", "something", "someone", "being", "other", "these", "those", "never", "every"})


def _answer_used(answer: str, lower_text: str, location: str) -> bool:
    """True when the scene carries at least two meaningful words of ``answer`` that are not part of the place name."""
    skip = set(re.findall(r"[a-z']+", location.lower())) | _FILLER
    words = {w for w in re.findall(r"[a-z']+", answer.lower()) if len(w) > 4 and w not in skip}
    return sum(1 for w in words if w[:5] in lower_text) >= min(2, len(words))


def check_woven(text: str, facts: dict[str, Any]) -> list[str]:
    """Why ``text`` is not an acceptable opening; empty when it is."""
    from .scene_validator import _names_place  # imported here: scene_validator imports this package's siblings

    issues: list[str] = []
    body = str(text or "").strip()
    lower = body.lower()
    words = body.split()
    if len(words) < MIN_WORDS:
        issues.append(f"Too short ({len(words)} words); write at least {MIN_WORDS}.")
    if len(words) > MAX_WORDS:
        issues.append(f"Too long ({len(words)} words); keep it under {MAX_WORDS}.")
    if len([p for p in re.split(r"\n\s*\n", body) if p.strip()]) < 3:
        issues.append("Write at least three short paragraphs separated by a blank line.")
    if "?" in body:
        issues.append("Contains a question; write statements only.")
    if _OPTION_MENU.search(body):
        issues.append("Lists what the character could do; describe the situation instead.")
    player = facts["player"]
    if player.lower() != "the party" and player.lower() not in lower:
        issues.append(f"Never names {player}.")
    if facts["location"] and not _names_place(lower, facts["location"]):
        issues.append(f"Never names the place, {facts['location']}.")
    if facts.get("npc_name") and facts["npc_name"].lower() not in lower:
        issues.append(f"Never names {facts['npc_name']}.")
    if player.lower() != "the party" and "the party" in lower:
        issues.append("Says 'the party'; use the character's name.")
    if re.search(r"\b(?:the scene|the player|these facts|the story plan)\b", lower):
        issues.append("Refers to the scene, the player or the facts directly.")
    sentences = [s.lower().rstrip(".!?") for s in _sentences(body)]
    if len(set(sentences)) < len(sentences):
        issues.append("Repeats a sentence.")
    for known in facts.get("brief_sentences") or []:
        known = known.lower().strip().rstrip(".!?")
        if len(known.split()) >= 6 and known in lower:
            issues.append(f"Copies a sentence the player has already read ('{known[:60]}'); use new words.")
            break
    time = facts["time_of_day"].lower()
    future = f"{facts.get('stakes', '')} {facts.get('clock', '')}"  # a deadline at night is in the future, not the present
    if time in _DAY_TIMES and _NIGHT_WORDS.search(body) and not _NIGHT_WORDS.search(future):
        issues.append("Describes night although the scene happens in the " + time + ".")
    if time in _NIGHT_TIMES and _DAY_WORDS.search(body):
        issues.append("Describes daylight although the scene happens at " + time + ".")
    brought = [facts[k] for k in ("reason_for_coming", "why_it_matters", "what_they_fear_losing") if facts.get(k)]
    if brought and not any(_answer_used(answer, lower, facts["location"]) for answer in brought):
        issues.append(f"Never says why {player} came or what they stand to lose; work their reason into the scene.")
    # The character's own words are paraphrased, never copied: an eight-word run from an answer is a quote.
    for key in ("reason_for_coming", "why_it_matters", "what_they_fear_losing", "knows_here"):
        answer = facts.get(key) or ""
        copied = _ngrams(body, 8) & (_ngrams(answer, 8) | _ngrams(first_to_third(answer), 8)) if answer else set()
        if copied:
            run = " ".join(sorted(copied)[0])
            issues.append(f"Copies the character's own words ('{run} ...'); say the same thing in different words.")
            break
    return issues


def weave_opening(facts: dict[str, Any], *, attempts: int = 3, timeout: float = 120.0) -> str:
    """One coherent opening written from ``facts``; ``""`` when no draft passes the checks."""
    from .. import steward_llm  # looked up at call time so the test stub for the model applies

    if not facts.get("location"):
        return ""
    feedback = ""
    for attempt in range(max(1, attempts)):
        try:
            raw = steward_llm.chat_complete(
                _messages(facts, feedback),
                task_scope="taverntails_narrative",
                max_tokens=520,
                temperature=0.7,
                timeout=timeout,
            )
        except Exception:  # a model failure must never block the opening
            logger.exception("scene weave call failed")
            return ""
        if not raw:
            logger.info("scene weave: the model returned nothing (attempt %s)", attempt + 1)
            return ""
        draft = _strip_wrapping(raw)
        issues = check_woven(draft, facts)
        if not issues:
            return draft
        logger.info("scene weave attempt %s rejected: %s", attempt + 1, "; ".join(issues))
        feedback = "\n".join(f"- {issue}" for issue in issues)
    return ""


def _strip_wrapping(raw: str) -> str:
    """The scene text without code fences, a JSON wrapper or surrounding quotes."""
    text = str(raw or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            import json

            data = json.loads(text)
            for key in ("narrative", "scene", "text"):
                if isinstance(data, dict) and isinstance(data.get(key), str):
                    return data[key].strip()
        except ValueError:
            pass
    return text.strip('"“”')


def keyword_set(text: str, skip: str = "") -> set[str]:
    skipped = set(re.findall(r"[a-z']+", skip.lower())) | _FILLER
    return {w[:5] for w in re.findall(r"[a-z']+", str(text or "").lower()) if len(w) >= 4 and w not in skipped}


def best_sentence(text: str, source: str, skip: str = "") -> str:
    """The sentence of ``text`` that carries the most meaningful words of ``source``; ``""`` when none carries two."""
    wanted = keyword_set(source, skip)
    best, score = "", 1
    for sentence in _sentences(text):
        hits = len(wanted & keyword_set(sentence, skip))
        if hits > score:
            best, score = sentence, hits
    return best
