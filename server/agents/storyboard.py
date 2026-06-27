"""Storyboard agent: track beats and hooks, and generate story plots from campaign context."""


from fastapi import APIRouter
from pydantic import BaseModel, Field

try:
    from ..steward_llm import chat_complete as _chat_complete
except Exception:
    _chat_complete = None  # type: ignore

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
    """Input for generating an initial story plot (New Session Workflow, Step 1).

    Data sources:
    - ``players`` — session members' character names (from ``pcs.json`` / session meta)
    - ``campaign_settings`` — :class:`CampaignSettings` dict from
      ``/campaigns/{id}/settings`` (genre, tone, setting_summary, world_name, …)
    - ``campaign_variables`` — :class:`CampaignVariables` dict from
      ``/campaigns/{id}/variables`` (narrative_style, themes, factions, pacing, …)
    - ``campaign_docs`` — document content from the session document store
    """

    session_id: str | None = Field(default=None, description="Session context, used for logging")
    players: list[str] = Field(default_factory=list, description="Player/character names involved")
    campaign_settings: dict = Field(
        default_factory=dict,
        description=(
            "CampaignSettings fields: genre, tone, setting_summary, world_name, "
            "ruleset, starting_level, house_rules, player_run_mode"
        ),
    )
    campaign_variables: dict = Field(
        default_factory=dict,
        description=(
            "CampaignVariables fields: narrative_style, themes, pacing, "
            "factions, npc_archetypes, naming_style, content_rating"
        ),
    )
    campaign_docs: list[str] = Field(default_factory=list, description="Campaign document texts to draw story hooks from")


class StoryboardPlotResponse(BaseModel):
    """Raw campaign material produced for the Scene Director (New Session Workflow, Step 1 output)."""

    plot: str = Field(..., description="Evocative plot seed — passed to Scene Director as context")
    hooks: list[str] = Field(default_factory=list, description="Active story hooks from campaign docs/memory")
    npcs_mentioned: list[str] = Field(default_factory=list, description="NPC names extracted from docs/factions")

    # Structured candidate lists for the Scene Director
    candidate_story_threads: list[str] = Field(default_factory=list, description="Unresolved threads / quests from docs")
    candidate_npcs: list[str] = Field(default_factory=list, description="Alias for npcs_mentioned — for Scene Director")
    candidate_locations: list[str] = Field(default_factory=list, description="Named locations extracted from docs/settings")
    candidate_factions: list[str] = Field(default_factory=list, description="Faction names from campaign variables")
    recent_events: list[str] = Field(default_factory=list, description="Recent-event lines from campaign docs")
    open_hooks: list[str] = Field(default_factory=list, description="Player-facing hooks (not yet resolved)")
    recommended_scene_purpose: str = Field(
        default="opening",
        description="Suggested scene type: opening | consequence | discovery | social | travel",
    )


_DEFAULT_HOOKS = [
    "The road ahead is quiet — too quiet for a busy trade route.",
    "Smoke rises from a direction it shouldn't.",
    "A sealed letter arrived last night, addressed to no one.",
]

_MIN_HOOK_LENGTH = 10
_MAX_HOOK_LENGTH = 120

# Doc-line prefixes that mark candidate entities
_NPC_PREFIXES = ("npc:", "enemy:", "villain:", "ally:", "contact:", "boss:", "patron:")
_LOCATION_PREFIXES = ("location:", "place:", "town:", "city:", "village:", "dungeon:", "inn:", "keep:", "fortress:", "region:")
_THREAD_PREFIXES = ("thread:", "quest:", "hook:", "mission:", "task:", "objective:", "conflict:", "problem:")
_EVENT_PREFIXES = ("event:", "recent:", "news:", "rumor:", "rumour:", "happening:", "incident:")


def _extract_hooks_from_docs(docs: list[str]) -> list[str]:
    """Pull meaningful lines from campaign documents to use as story hooks."""
    hooks: list[str] = []
    for doc in docs:
        for line in doc.splitlines():
            stripped = line.strip(" -#*\t")
            if len(stripped) > _MIN_HOOK_LENGTH and not stripped.lower().startswith(("use this", "(ai gm", "session notes")):
                hooks.append(stripped[:_MAX_HOOK_LENGTH])
                break
    return hooks


def _extract_prefixed(docs: list[str], prefixes: tuple[str, ...]) -> list[str]:
    """Extract values after labelled prefixes (e.g. 'NPC: Elira Voss') from docs."""
    found: list[str] = []
    for doc in docs:
        for line in doc.splitlines():
            lower = line.lower().strip()
            for prefix in prefixes:
                if lower.startswith(prefix):
                    value = line[len(prefix):].split(",")[0].split(".")[0].strip()
                    if value and value not in found:
                        found.append(value)
                    break
    return found


@router.post("/storyboard/generate", response_model=StoryboardPlotResponse)
def generate_plot(payload: StoryboardPlotRequest) -> StoryboardPlotResponse:
    """Step 1 of New Session Workflow.

    Reads player roster, campaign settings, campaign variables, and campaign
    documents to produce a structured story plot that the Narrative Agent will
    use to craft the opening scene.

    Data consumed and where it originates:
    - ``genre`` / ``tone`` / ``setting_summary`` / ``world_name``
        → ``campaign_settings`` (set via ``PUT /campaigns/{id}/settings``)
    - ``narrative_style`` / ``themes`` / ``factions`` / ``pacing``
        → ``campaign_variables`` (set via ``PUT /campaigns/{id}/variables``)
    - ``players`` → session members' character names
    - ``campaign_docs`` → session document store content
    """
    # -- Campaign settings (genre, tone, setting) --
    genre = str(payload.campaign_settings.get("genre") or "fantasy").strip() or "fantasy"
    tone = (
        str(payload.campaign_settings.get("tone") or "").strip()
        or str(payload.campaign_variables.get("narrative_style") or "balanced").strip()
        or "balanced"
    )
    setting = str(
        payload.campaign_settings.get("setting_summary")
        or payload.campaign_settings.get("setting") or ""
    ).strip()
    world_name = str(payload.campaign_settings.get("world_name") or "").strip()

    # -- Campaign variables (themes, factions) --
    themes: list[str] = [str(t) for t in (payload.campaign_variables.get("themes") or []) if t]
    factions: list[dict] = [
        f for f in (payload.campaign_variables.get("factions") or [])
        if isinstance(f, dict) and f.get("name")
    ]
    player_list = ", ".join(p for p in payload.players if p) if payload.players else "the party"

    # -- Extract structured candidates from docs --
    doc_hooks = _extract_hooks_from_docs(payload.campaign_docs)
    candidate_locations = _extract_prefixed(payload.campaign_docs, _LOCATION_PREFIXES)
    candidate_npcs_from_docs = _extract_prefixed(payload.campaign_docs, _NPC_PREFIXES)
    candidate_threads = _extract_prefixed(payload.campaign_docs, _THREAD_PREFIXES)
    recent_events = _extract_prefixed(payload.campaign_docs, _EVENT_PREFIXES)

    # Faction names from variables
    faction_names = [str(f.get("name", "")).strip() for f in factions if f.get("name")]
    # Faction members as NPC candidates
    npcs_mentioned: list[str] = list(candidate_npcs_from_docs)
    for faction in factions:
        for member in faction.get("members") or []:
            if member and member not in npcs_mentioned:
                npcs_mentioned.append(member)

    # -- Open hooks: prefer thread / quest lines over generic doc hooks --
    open_hooks = candidate_threads[:3] or doc_hooks[:3]
    hooks: list[str] = []
    if themes:
        hooks.extend(themes[:3])
    for h in (candidate_threads or doc_hooks):
        if h not in hooks:
            hooks.append(h)
    if not hooks:
        hooks = list(_DEFAULT_HOOKS[:2])

    # -- Determine recommended scene purpose --
    if candidate_threads or open_hooks:
        recommended_purpose = "consequence" if recent_events else "opening"
    else:
        recommended_purpose = "opening"

    # -- Build rule-based plot seed from structured data --
    # Don't write "A heroic fantasy adventure awaits." — be specific.
    world_ref = world_name or setting
    plot_parts: list[str] = []
    if candidate_threads:
        plot_parts.append(candidate_threads[0][:200])
    elif open_hooks:
        plot_parts.append(open_hooks[0][:200])
    if factions:
        fname = factions[0].get("name", "")
        fgoals = [str(g) for g in (factions[0].get("goals") or []) if g]
        if fname and fgoals:
            plot_parts.append(f"The {fname} is moving: {fgoals[0][:80]}.")
        elif fname:
            plot_parts.append(f"The {fname} casts a long shadow over events.")
    if not plot_parts:
        loc = candidate_locations[0] if candidate_locations else (world_ref or "the region")
        flavor = f"{genre} world of {tone}" if tone and tone not in ("balanced", "moderate") else f"{genre} world"
        plot_parts.append(f"In the {flavor}, {loc} demands the party's immediate attention.")
    if recent_events:
        plot_parts.append(recent_events[0][:120])
    plot = " ".join(plot_parts)

    # -- LLM enrichment: produce a specific, grounded plot seed --
    if _chat_complete:
        try:
            ctx: list[str] = []
            if world_ref:
                ctx.append(f"Setting: {world_ref[:150]}")
            ctx.append(f"Genre/Tone: {genre}, {tone}")
            ctx.append(f"Player character: {player_list}")
            if candidate_threads:
                ctx.append("Active story threads:\n" + "\n".join(f"  • {t}" for t in candidate_threads[:3]))
            if open_hooks:
                ctx.append("Open hooks:\n" + "\n".join(f"  • {h}" for h in open_hooks[:3]))
            if npcs_mentioned:
                ctx.append(f"Known NPCs: {', '.join(npcs_mentioned[:5])}")
            if candidate_locations:
                ctx.append(f"Known locations: {', '.join(candidate_locations[:4])}")
            if faction_names:
                ctx.append(f"Factions: {', '.join(faction_names[:3])}")
            if recent_events:
                ctx.append(f"Recent events: {'; '.join(recent_events[:2])}")

            llm_sys = (
                "You are a tabletop RPG campaign architect. Write a SPECIFIC, GROUNDED plot seed "
                f"(2–3 sentences, max 80 words) for the opening of this {genre} session.\n\n"
                "Requirements:\n"
                "  — Name a SPECIFIC location from the context (or invent one that fits) — do NOT default to a tavern or inn unless the context mentions one\n"
                "  — Name a SPECIFIC NPC from the context (or invent one with a real name)\n"
                "  — Describe what is ACTIVELY HAPPENING right now — a concrete event, not a vague mood\n"
                "  — Create immediate urgency or tension\n"
                "  — Do NOT start with 'The party'. Do NOT say 'heroic fantasy adventure' or similar.\n"
                "  — Do NOT describe the genre or campaign structure\n\n"
                "Return only the plot text. No JSON, no commentary, no title."
            )
            llm_result = _chat_complete(
                [{"role": "system", "content": llm_sys},
                 {"role": "user", "content": "\n".join(ctx)}],
                task_scope="taverntails_plot",
                max_tokens=200,
                timeout=90.0,
            )
            if llm_result and len(llm_result.strip()) > 20:
                plot = llm_result.strip()
        except Exception:
            pass

    # Ensure genre/tone always appear in the plot so downstream consumers and tests
    # can identify the requested style (especially when deterministic fallback ran).
    if genre.lower() not in plot.lower():
        plot = f"({genre}, {tone}) {plot}"

    return StoryboardPlotResponse(
        plot=plot,
        hooks=hooks,
        npcs_mentioned=npcs_mentioned,
        candidate_story_threads=candidate_threads,
        candidate_npcs=npcs_mentioned,
        candidate_locations=candidate_locations,
        candidate_factions=faction_names,
        recent_events=recent_events,
        open_hooks=open_hooks,
        recommended_scene_purpose=recommended_purpose,
    )
