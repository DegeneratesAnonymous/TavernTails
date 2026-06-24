"""Visual Director Agent: determines visual state from scene context.

Runs after the Narrative Agent. Converts scene text + Scene Director data into
a VisualState, which drives image generation and refresh decisions.

Images answer "How does this place feel?" — never "Who is the hero?"
"""
from __future__ import annotations

import json

try:
    from ..steward_llm import chat_complete as _chat_complete
except Exception:
    _chat_complete = None  # type: ignore

from .visual_state import (
    SCENE_MOODS,
    THREAT_LEVELS,
    VISUAL_TYPES,
    VisualState,
    build_image_prompt_from_visual_state,
    get_location_identity,
    should_refresh_image,
)


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------

def _derive_mood_from_threat(threat_level: str) -> str:
    mapping = {
        "safe": "calm",
        "low": "unease",
        "moderate": "suspense",
        "high": "danger",
        "critical": "dread",
    }
    return mapping.get(threat_level, "unease")


def _detect_threat_from_scene_text(text: str) -> str:
    text_lower = text.lower()
    if any(w in text_lower for w in ["dead", "dying", "fire", "destroyed", "panic", "massacre"]):
        return "critical"
    if any(w in text_lower for w in ["danger", "attack", "threat", "armed", "weapon", "blood"]):
        return "high"
    if any(w in text_lower for w in ["suspicious", "wary", "patrol", "guard", "tense", "missing"]):
        return "moderate"
    if any(w in text_lower for w in ["worried", "question", "urgent", "locked", "hidden"]):
        return "low"
    return "safe"


def _detect_mood_from_scene_text(text: str) -> str:
    text_lower = text.lower()
    if any(w in text_lower for w in ["celebrate", "triumph", "victory", "cheer", "festival"]):
        return "celebration"
    if any(w in text_lower for w in ["mourn", "funeral", "grief", "loss", "died", "memorial"]):
        return "grief"
    if any(w in text_lower for w in ["wonder", "marvel", "ancient", "magical", "glowing", "ethereal"]):
        return "wonder"
    if any(w in text_lower for w in ["panic", "terror", "horror", "flee", "dread"]):
        return "dread"
    if any(w in text_lower for w in ["danger", "attack", "fight", "battle", "weapon", "blood"]):
        return "danger"
    if any(w in text_lower for w in ["mystery", "secret", "hidden", "strange", "odd", "cryptic"]):
        return "mystery"
    if any(w in text_lower for w in ["suspicious", "wary", "uneasy", "nervous", "dread", "something wrong"]):
        return "unease"
    if any(w in text_lower for w in ["tense", "stalked", "watched", "shadow", "stalking"]):
        return "suspense"
    return "unease"


def _deterministic_visual_state(
    scene_text: str,
    location_name: str,
    location_type: str,
    weather: str,
    time_of_day: str,
    season: str,
    region: str,
    visual_prompt_elements: list[str],
) -> VisualState:
    threat = _detect_threat_from_scene_text(scene_text)
    mood = _detect_mood_from_scene_text(scene_text)
    return VisualState(
        visual_type="scene_mood",
        location_name=location_name,
        location_type=location_type,
        region=region,
        weather=weather,
        time_of_day=time_of_day,
        season=season,
        mood=mood,
        threat_level=threat,
        dominant_theme="",
        visual_focus="environment",
        important_landmarks=[],
        environmental_details=visual_prompt_elements[:3],
        characters_visible=False,
        image_refresh_required=True,
        last_refresh_reason="deterministic_fallback",
    )


# ---------------------------------------------------------------------------
# LLM Visual Director
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a Visual Director for a tabletop RPG companion app.
Your job is to classify and describe the VISUAL ATMOSPHERE of the current scene.
The image produced from your output will be environmental art — NO characters in the foreground.

Given a scene description, output a JSON object with these fields:
{
  "visual_type": "<one of: scene_mood | location_mood | regional_mood | event_splash>",
  "mood": "<one of: calm | unease | suspense | mystery | danger | dread | celebration | grief | triumph | wonder>",
  "threat_level": "<one of: safe | low | moderate | high | critical>",
  "dominant_theme": "<2-4 words: what this place represents emotionally, e.g. 'waiting storm', 'quiet dread'>",
  "visual_focus": "environment",
  "important_landmarks": ["<specific architectural or geographic feature in this location>"],
  "environmental_details": ["<detail 1>", "<detail 2>", "<detail 3>"],
  "characters_visible": false
}

Rules:
- event_splash is ONLY for major revelations, catastrophes, boss reveals, or world-changing moments
- characters_visible MUST be false unless visual_type is event_splash
- environmental_details must be SPECIFIC to this location (not generic "dark forest" etc.)
- threat_level must match the actual danger implied by the scene text
- mood must reflect the emotional atmosphere, not the plot

Return ONLY valid JSON. No markdown, no commentary."""


def direct_visual(
    scene_text: str,
    location_name: str,
    location_type: str = "",
    weather: str = "clear",
    time_of_day: str = "day",
    season: str = "autumn",
    region: str = "",
    visual_prompt_elements: list[str] | None = None,
) -> VisualState:
    """Determine visual state from scene text and location context.

    Falls back to deterministic analysis if LLM is unavailable or fails.
    """
    elements = visual_prompt_elements or []
    fallback = _deterministic_visual_state(
        scene_text, location_name, location_type,
        weather, time_of_day, season, region, elements,
    )

    if not _chat_complete:
        return fallback

    context_parts = [f"Location: {location_name}"]
    if location_type:
        context_parts.append(f"Type: {location_type}")
    if region:
        context_parts.append(f"Region: {region}")
    context_parts.append(f"Weather: {weather}, Time: {time_of_day}, Season: {season}")
    if elements:
        context_parts.append(f"Visual elements from scene director: {', '.join(elements[:4])}")
    context_parts.append("")
    context_parts.append("Scene text:")
    context_parts.append(scene_text[:600])

    try:
        raw = _chat_complete(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": "\n".join(context_parts)},
            ],
            task_scope="taverntails_visual",
            max_tokens=300,
            timeout=60.0,
        )
        if not raw:
            return fallback

        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end <= start:
            return fallback

        data = json.loads(raw[start : end + 1])

        # Validate and sanitize
        vtype = data.get("visual_type", "scene_mood")
        if vtype not in VISUAL_TYPES:
            vtype = "scene_mood"
        mood = data.get("mood", "unease")
        if mood not in SCENE_MOODS:
            mood = fallback.mood
        threat = data.get("threat_level", "low")
        if threat not in THREAT_LEVELS:
            threat = fallback.threat_level
        chars_visible = bool(data.get("characters_visible", False)) and vtype == "event_splash"

        return VisualState(
            visual_type=vtype,
            location_name=location_name,
            location_type=location_type,
            region=region,
            weather=weather,
            time_of_day=time_of_day,
            season=season,
            mood=mood,
            threat_level=threat,
            dominant_theme=str(data.get("dominant_theme", ""))[:60],
            visual_focus="environment",
            important_landmarks=[str(x) for x in (data.get("important_landmarks") or [])[:3]],
            environmental_details=[str(x) for x in (data.get("environmental_details") or elements)[:4]],
            characters_visible=chars_visible,
            image_refresh_required=True,
            last_refresh_reason="llm",
        )
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# Full pipeline: determine visual state + decide refresh + build prompt
# ---------------------------------------------------------------------------

def run_visual_pipeline(
    session_id: str,
    scene_text: str,
    location_name: str,
    location_type: str = "",
    weather: str = "clear",
    time_of_day: str = "day",
    season: str = "autumn",
    region: str = "",
    visual_prompt_elements: list[str] | None = None,
    previous_visual_state: VisualState | None = None,
) -> tuple[VisualState, str, bool]:
    """Run the full visual pipeline. Returns (visual_state, image_prompt, should_generate_image).

    - Calls LLM Visual Director to determine new visual state
    - Checks if image should be refreshed vs. reused
    - Builds the structured image prompt from visual state
    """
    new_state = direct_visual(
        scene_text=scene_text,
        location_name=location_name,
        location_type=location_type,
        weather=weather,
        time_of_day=time_of_day,
        season=season,
        region=region,
        visual_prompt_elements=visual_prompt_elements,
    )

    refresh, reason = should_refresh_image(previous_visual_state, new_state)
    new_state.image_refresh_required = refresh
    new_state.last_refresh_reason = reason

    # Look up persistent location identity descriptors
    loc_identity = get_location_identity(session_id, location_name) if session_id else None

    image_prompt = build_image_prompt_from_visual_state(new_state, loc_identity)
    new_state.image_prompt = image_prompt

    return new_state, image_prompt, refresh
