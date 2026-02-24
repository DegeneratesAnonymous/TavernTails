"""Storyboard agent: track beats and hooks, and generate story plots from campaign context."""


from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["storyboard"])


class StoryboardRequest(BaseModel):
    scene: str
    choices: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    completed: list[str] = Field(default_factory=list)


class StoryboardResponse(BaseModel):
    storyboard: dict
    next_focus: str


@router.post("/storyboard/update", response_model=StoryboardResponse)
def update_storyboard(payload: StoryboardRequest) -> StoryboardResponse:
    next_focus = payload.unresolved[0] if payload.unresolved else "Introduce a fresh complication."
    storyboard = {
        "scene": payload.scene,
        "choices": payload.choices,
        "unresolved": payload.unresolved,
        "completed": payload.completed,
    }
    return StoryboardResponse(storyboard=storyboard, next_focus=next_focus)


class StoryboardPlotRequest(BaseModel):
    """Input for generating an initial story plot (New Session Workflow, Step 1)."""

    session_id: str | None = Field(default=None, description="Session context, used for logging")
    players: list[str] = Field(default_factory=list, description="Player/character names involved")
    campaign_settings: dict = Field(default_factory=dict, description="Campaign metadata: genre, tone, etc.")
    campaign_docs: list[str] = Field(default_factory=list, description="Campaign document texts to draw story hooks from")


class StoryboardPlotResponse(BaseModel):
    """Structured story plot produced for the Narrative Agent (New Session Workflow, Step 1 output)."""

    plot: str = Field(..., description="High-level story plot description for the opening scene")
    hooks: list[str] = Field(default_factory=list, description="Active story hooks/threads to weave into the scene")
    npcs_mentioned: list[str] = Field(default_factory=list, description="NPC names referenced in the plot")


_DEFAULT_HOOKS = [
    "A mysterious threat looms on the horizon.",
    "An old acquaintance appears with an urgent request.",
    "Strange omens hint at danger ahead.",
]

_MIN_HOOK_LENGTH = 10   # Discard lines shorter than this — they're likely headings or noise.
_MAX_HOOK_LENGTH = 120  # Truncate hooks at this length so they fit cleanly in prompt context.


def _extract_hooks_from_docs(docs: list[str]) -> list[str]:
    """Pull meaningful lines from campaign documents to use as story hooks."""
    hooks: list[str] = []
    for doc in docs:
        for line in doc.splitlines():
            stripped = line.strip(" -#*\t")
            if len(stripped) > _MIN_HOOK_LENGTH and not stripped.lower().startswith(("use this", "(ai gm", "session notes")):
                hooks.append(stripped[:_MAX_HOOK_LENGTH])
                break  # one hook per document
    return hooks


@router.post("/storyboard/generate", response_model=StoryboardPlotResponse)
def generate_plot(payload: StoryboardPlotRequest) -> StoryboardPlotResponse:
    """Step 1 of New Session Workflow.

    Reads player roster, campaign settings, and campaign documents to produce
    a structured story plot that the Narrative Agent will use to craft the opening scene.
    """
    genre = str(payload.campaign_settings.get("genre") or "fantasy").strip() or "fantasy"
    tone = str(payload.campaign_settings.get("tone") or "balanced").strip() or "balanced"
    setting = str(payload.campaign_settings.get("setting") or "").strip()

    player_list = ", ".join(p for p in payload.players if p) if payload.players else "the party"

    doc_hooks = _extract_hooks_from_docs(payload.campaign_docs)
    hooks = doc_hooks if doc_hooks else list(_DEFAULT_HOOKS[:2])

    # Build a succinct plot seed from available context.
    location_hint = f" in {setting}" if setting else ""
    plot_parts = [f"A {tone} {genre} adventure{location_hint} awaits {player_list}."]
    plot_parts.extend(hooks[:3])
    plot = " ".join(plot_parts)

    # Extract simple NPC names: look for "NPC:" or "Enemy:" prefixes in docs.
    npcs_mentioned: list[str] = []
    for doc in payload.campaign_docs:
        for line in doc.splitlines():
            lower = line.lower().strip()
            for prefix in ("npc:", "enemy:", "villain:", "ally:"):
                if lower.startswith(prefix):
                    name = line[len(prefix):].split(",")[0].split(".")[0].strip()
                    if name and name not in npcs_mentioned:
                        npcs_mentioned.append(name)

    return StoryboardPlotResponse(plot=plot, hooks=hooks, npcs_mentioned=npcs_mentioned)
