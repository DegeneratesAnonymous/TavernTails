"""Visual State — models, mood definitions, location identity system, and threat levels.

The Visual State represents what kind of environmental art should be shown for the
current scene.  It drives image generation and controls when images are refreshed
vs. reused.

Design principle: images answer "How does this place feel?" not "What happened?"
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_SESSION_BASE = Path(__file__).resolve().parents[1] / "sessions"

# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------

VISUAL_TYPES = {
    "campaign_cover": "Campaign identity art — used on home screen and lobby",
    "regional_mood": "Region-establishing art — refreshes when region changes",
    "location_mood": "Specific location art — refreshes when location changes",
    "scene_mood": "Current atmosphere art — refreshes when mood changes significantly",
    "event_splash": "Major event art — boss reveals, disasters, discoveries (characters allowed)",
}

THREAT_LEVELS = ["safe", "low", "moderate", "high", "critical"]

SCENE_MOODS = [
    "calm", "unease", "suspense", "mystery", "danger",
    "celebration", "grief", "triumph", "dread", "wonder",
]


class VisualState(BaseModel):
    visual_type: str = "scene_mood"
    location_name: str = ""
    location_type: str = ""
    region: str = ""
    weather: str = "clear"
    time_of_day: str = "day"
    season: str = "autumn"
    mood: str = "calm"
    threat_level: str = "low"
    dominant_theme: str = ""
    visual_focus: str = "environment"
    important_landmarks: list[str] = Field(default_factory=list)
    environmental_details: list[str] = Field(default_factory=list)
    characters_visible: bool = False
    image_refresh_required: bool = True
    image_prompt: str = ""
    last_refresh_reason: str = ""


class LocationIdentity(BaseModel):
    """Persistent visual descriptors for a named location — creates visual consistency."""
    name: str
    architecture: list[str] = Field(default_factory=list)
    landmarks: list[str] = Field(default_factory=list)
    palette: list[str] = Field(default_factory=list)
    atmosphere: list[str] = Field(default_factory=list)
    region: str = ""
    location_type: str = ""


# ---------------------------------------------------------------------------
# Mood definitions
# ---------------------------------------------------------------------------

MOOD_VISUALS: dict[str, dict[str, Any]] = {
    "calm": {
        "lighting": "warm, even lighting",
        "weather_bias": "clear",
        "crowd_density": "normal activity",
        "visual_symbols": ["open storefronts", "people going about their day", "calm skies"],
    },
    "unease": {
        "lighting": "low contrast, flat grey light",
        "weather_bias": "overcast or mist",
        "crowd_density": "sparse",
        "visual_symbols": ["empty streets", "closed shutters", "distant silhouettes", "wary looks"],
    },
    "suspense": {
        "lighting": "deep shadows, single light source",
        "weather_bias": "dusk or night",
        "crowd_density": "very sparse",
        "visual_symbols": ["long shadows", "hidden corners", "figures watching from doorways"],
    },
    "mystery": {
        "lighting": "diffused, fog-softened",
        "weather_bias": "fog or mist",
        "crowd_density": "sparse",
        "visual_symbols": ["hidden paths", "obscured landmarks", "unusual objects", "symbols in architecture"],
    },
    "danger": {
        "lighting": "harsh shadows, high contrast",
        "weather_bias": "storm or night",
        "crowd_density": "absent or fleeing",
        "visual_symbols": ["damage", "signs of struggle", "warning signals", "barricaded doors"],
    },
    "dread": {
        "lighting": "near-dark, single cold light",
        "weather_bias": "storm or overcast",
        "crowd_density": "abandoned",
        "visual_symbols": ["abandoned streets", "broken structures", "unnatural silence"],
    },
    "celebration": {
        "lighting": "warm golden light, lanterns",
        "weather_bias": "clear, warm",
        "crowd_density": "crowded and festive",
        "visual_symbols": ["banners", "firelight", "music instruments", "gathered crowds"],
    },
    "grief": {
        "lighting": "cool, muted",
        "weather_bias": "rain or overcast",
        "crowd_density": "small groups, heads down",
        "visual_symbols": ["draped cloth", "candles", "gathered mourners", "grey light"],
    },
    "triumph": {
        "lighting": "bright, high contrast",
        "weather_bias": "clear",
        "crowd_density": "crowd, upbeat",
        "visual_symbols": ["banners raised", "open gates", "bright skies", "celebration fire"],
    },
    "wonder": {
        "lighting": "ethereal, soft glow",
        "weather_bias": "clear or dawn",
        "crowd_density": "sparse, awed",
        "visual_symbols": ["unusual phenomena", "glowing elements", "ancient structures", "natural grandeur"],
    },
}


# ---------------------------------------------------------------------------
# Threat level visual properties
# ---------------------------------------------------------------------------

THREAT_VISUALS: dict[str, dict[str, Any]] = {
    "safe": {
        "weather_modifier": "calm",
        "environment_condition": "well-maintained",
        "crowd": "active citizens, open businesses",
        "tension_signs": [],
    },
    "low": {
        "weather_modifier": "mild",
        "environment_condition": "normal wear",
        "crowd": "some residents, some caution",
        "tension_signs": ["occasional locked door", "guards present"],
    },
    "moderate": {
        "weather_modifier": "unsettled",
        "environment_condition": "signs of stress",
        "crowd": "sparse, watchful",
        "tension_signs": ["boarded windows", "patrols", "whispered conversations"],
    },
    "high": {
        "weather_modifier": "stormy or dark",
        "environment_condition": "damaged or neglected",
        "crowd": "few, frightened",
        "tension_signs": ["barricades", "damage visible", "people moving quickly"],
    },
    "critical": {
        "weather_modifier": "storm",
        "environment_condition": "damaged or destroyed",
        "crowd": "abandoned or panicking",
        "tension_signs": ["fires", "destroyed structures", "signs of panic", "abandoned streets"],
    },
}


# ---------------------------------------------------------------------------
# Session visual state persistence
# ---------------------------------------------------------------------------

def load_visual_state(session_id: str) -> VisualState | None:
    path = _SESSION_BASE / session_id / "visual_state.json"
    if not path.exists():
        return None
    try:
        return VisualState(**json.loads(path.read_text()))
    except Exception:
        return None


def save_visual_state(session_id: str, state: VisualState) -> None:
    path = _SESSION_BASE / session_id / "visual_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json())


# ---------------------------------------------------------------------------
# Location identity persistence (per campaign)
# ---------------------------------------------------------------------------

def _location_identity_path(session_id: str) -> Path:
    return _SESSION_BASE / session_id / "location_identity.json"


def load_location_identities(session_id: str) -> dict[str, LocationIdentity]:
    path = _location_identity_path(session_id)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        return {k: LocationIdentity(**v) for k, v in raw.items()}
    except Exception:
        return {}


def save_location_identity(session_id: str, identity: LocationIdentity) -> None:
    identities = load_location_identities(session_id)
    identities[identity.name.lower()] = identity
    path = _location_identity_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: v.model_dump() for k, v in identities.items()}, indent=2))


def get_location_identity(session_id: str, location_name: str) -> LocationIdentity | None:
    identities = load_location_identities(session_id)
    return identities.get(location_name.lower())


# ---------------------------------------------------------------------------
# Similarity / refresh logic
# ---------------------------------------------------------------------------

def _visual_similarity(old: VisualState, new: VisualState) -> int:
    """Return 0–100 similarity score between two visual states.

    Score ≥ 80 → reuse existing image.
    Score < 80 → generate new image.
    """
    score = 0

    # Location (40 points — most important for continuity)
    if old.location_name and old.location_name.lower() == new.location_name.lower():
        score += 40
    elif old.region and old.region.lower() == new.region.lower():
        score += 20

    # Mood (25 points)
    if old.mood == new.mood:
        score += 25
    elif _mood_group(old.mood) == _mood_group(new.mood):
        score += 12

    # Threat level (20 points)
    old_idx = THREAT_LEVELS.index(old.threat_level) if old.threat_level in THREAT_LEVELS else 2
    new_idx = THREAT_LEVELS.index(new.threat_level) if new.threat_level in THREAT_LEVELS else 2
    diff = abs(old_idx - new_idx)
    if diff == 0:
        score += 20
    elif diff == 1:
        score += 10

    # Visual type (15 points)
    if old.visual_type == new.visual_type:
        score += 15

    return min(100, score)


def _mood_group(mood: str) -> str:
    positive = {"calm", "celebration", "triumph", "wonder"}
    negative = {"danger", "dread", "grief"}
    tense = {"unease", "suspense", "mystery"}
    if mood in positive:
        return "positive"
    if mood in negative:
        return "negative"
    if mood in tense:
        return "tense"
    return "neutral"


def should_refresh_image(old: VisualState | None, new: VisualState) -> tuple[bool, str]:
    """Return (should_refresh, reason). Always refresh for event_splash."""
    if new.visual_type == "event_splash":
        return True, "event_splash"
    if old is None:
        return True, "no_prior_state"
    similarity = _visual_similarity(old, new)
    if similarity >= 80:
        return False, f"similarity_{similarity}_pct_reuse"
    if old.location_name.lower() != new.location_name.lower():
        return True, f"location_changed:{old.location_name}->{new.location_name}"
    if old.mood != new.mood:
        return True, f"mood_changed:{old.mood}->{new.mood}"
    if abs(
        THREAT_LEVELS.index(old.threat_level if old.threat_level in THREAT_LEVELS else "low") -
        THREAT_LEVELS.index(new.threat_level if new.threat_level in THREAT_LEVELS else "low")
    ) > 1:
        return True, f"threat_changed:{old.threat_level}->{new.threat_level}"
    return True, f"similarity_{similarity}_pct_below_threshold"


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_FORBIDDEN_PROMPT_TERMS = [
    "heroic warrior", "fantasy hero", "adventurer standing",
    "portrait of", "epic protagonist", "close-up face",
    "generic adventurer", "brave warrior",
]


def build_image_prompt_from_visual_state(
    vs: VisualState,
    location_identity: LocationIdentity | None = None,
) -> str:
    """Build a structured, atmospheric image prompt from a VisualState.

    Produces environment-first, character-absent (unless event_splash) prompts.
    """
    parts: list[str] = []

    # Style header
    style_header = "Dark atmospheric fantasy environment art"
    if vs.visual_type == "campaign_cover":
        style_header = "Epic dark fantasy campaign cover art, environmental panorama"
    elif vs.visual_type == "regional_mood":
        style_header = "Dark fantasy regional environment illustration"
    elif vs.visual_type == "event_splash":
        style_header = "Dramatic dark fantasy event splash illustration"
    parts.append(style_header)

    # Location
    loc = vs.location_name or "ancient settlement"
    loc_type = vs.location_type or ""
    if loc_type and loc_type not in loc.lower():
        loc_desc = f"{loc}, {loc_type}"
    else:
        loc_desc = loc
    if vs.region and vs.region.lower() not in loc.lower():
        loc_desc += f" in {vs.region}"
    parts.append(loc_desc)

    # Time and weather
    time_desc = {
        "dawn": "early dawn light",
        "day": "daylight",
        "dusk": "golden dusk",
        "night": "night, torchlight",
    }.get(vs.time_of_day, vs.time_of_day)
    weather_desc = vs.weather if vs.weather != "clear" else "clear skies"
    parts.append(f"{weather_desc}, {time_desc}")

    # Season
    if vs.season and vs.season not in ("", "unknown"):
        parts.append(f"{vs.season}")

    # Mood-driven visual language
    mood_def = MOOD_VISUALS.get(vs.mood, MOOD_VISUALS["calm"])
    parts.append(mood_def["lighting"])
    if mood_def.get("visual_symbols"):
        parts.append(", ".join(mood_def["visual_symbols"][:2]))

    # Threat level context
    threat_def = THREAT_VISUALS.get(vs.threat_level, THREAT_VISUALS["low"])
    env_condition = threat_def.get("environment_condition", "")
    if env_condition:
        parts.append(env_condition)
    tension = threat_def.get("tension_signs", [])
    if tension:
        parts.append(tension[0])

    # Location identity descriptors
    if location_identity:
        if location_identity.architecture:
            parts.append(", ".join(location_identity.architecture[:2]))
        if location_identity.landmarks:
            parts.append(location_identity.landmarks[0])
        if location_identity.palette:
            parts.append(f"{', '.join(location_identity.palette[:2])} color palette")

    # Environmental details from visual state
    if vs.environmental_details:
        parts.extend(vs.environmental_details[:2])

    # Landmarks
    if vs.important_landmarks:
        parts.append(vs.important_landmarks[0])

    # Character visibility
    if not vs.characters_visible or vs.visual_type != "event_splash":
        parts.append("no characters in foreground")
        parts.append("environment and architecture focus")
    else:
        parts.append("figures small in composition, no close-up portraits")

    # Technical quality footer
    parts.append("cinematic composition, high detail, immersive atmosphere")

    # Validate — strip any forbidden terms
    prompt = ". ".join(p.strip().rstrip(".") for p in parts if p.strip())
    for term in _FORBIDDEN_PROMPT_TERMS:
        if term.lower() in prompt.lower() and vs.visual_type != "event_splash":
            prompt = prompt.replace(term, "")

    return prompt
