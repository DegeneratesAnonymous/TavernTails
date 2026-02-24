"""Formal schemas for GM-managed and player-visible documents.

These Pydantic models define *what information is needed to recall each entity*
so that agents can produce consistent, reusable documents.  Each GM schema maps
directly to the corresponding GM document category in
:mod:`server.storage.documents`:

- :class:`GMNPCDocument`       → ``category="gm_npc"``   (hidden from players)
- :class:`GMLocationDocument`  → ``category="gm_location"`` (hidden from players)
- :class:`GMQuestDocument`     → ``category="gm_quest"``  (hidden from players)
- :class:`SessionNoteEntry`    → used by the Notes Agent when appending to session notes

Each player-facing schema contains **only** information the characters have
gathered and is written to the corresponding shared category:

- :class:`PlayerEntityCard`    → ``category="player_npc"`` or ``"player_location"``
                                  (visible to all session members)

Associations
------------
:class:`EntityAssociation` links two entities (e.g. NPC ↔ Location, NPC ↔ Quest).
Associations are stored in ``associations.json`` inside the session folder and are
used to power in-chat hyperlinks — when a player clicks an NPC name in the chat
transcript the UI calls ``GET /sessions/{id}/entity/{name}`` which returns their
:class:`PlayerEntityCard`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# GM document schemas (hidden from players)
# ---------------------------------------------------------------------------


class AttitudeRank(BaseModel):
    """Tracks an NPC's attitude toward a specific character or faction.

    Attitude levels: Hostile → Dislike → Neutral → Like → Love → Worship.
    """

    target: str = Field(..., description="Character name, faction, or group this attitude applies to")
    rank: Literal["hostile", "dislike", "neutral", "like", "love", "worship"] = Field(
        default="neutral",
        description="Attitude level toward the target",
    )
    notes: str = Field(
        default="",
        description="Short context for why this attitude exists (e.g. 'betrayed by them', 'old friend')",
    )


class GMNPCDocument(BaseModel):
    """Full NPC profile stored in a ``gm_npc`` document.

    Contains everything needed to recall and roleplay an NPC consistently across
    sessions.  Players never see this document — they only see :class:`PlayerEntityCard`
    with the subset of information their characters have gathered.

    All fields map to a ``gm_npc`` document's JSON content so the NPC Manager
    Agent can serialize/deserialize it via ``json.dumps(doc.model_dump())``.
    """

    # ---- Identity ----------------------------------------------------------
    name: str = Field(..., description="NPC's full name (and any known aliases)")
    factions: list[str] = Field(
        default_factory=list,
        description="Factions, guilds, or groups the NPC belongs to",
    )

    # ---- Psychology --------------------------------------------------------
    motivations: list[str] = Field(
        default_factory=list,
        description=(
            "What the NPC wants, fears, or is working toward — "
            "these drive their in-scene behaviour"
        ),
    )
    personality: str = Field(
        default="",
        description=(
            "Core personality traits: speech patterns, demeanour, quirks, "
            "how they carry themselves under pressure"
        ),
    )
    attitude: list[AttitudeRank] = Field(
        default_factory=list,
        description=(
            "Attitude ranks toward player characters, factions, or other NPCs. "
            "Ranks: hostile, dislike, neutral, like, love, worship."
        ),
    )
    secrets: list[str] = Field(
        default_factory=list,
        description=(
            "Things the NPC knows but hides — used by the Narrative Agent to "
            "seed dramatic reveals"
        ),
    )

    # ---- Mechanics ---------------------------------------------------------
    classes: list[dict] = Field(
        default_factory=list,
        description=(
            "System-agnostic class/role entries, e.g. "
            "[{\"name\": \"Fighter\", \"level\": 5}].  "
            "Use NPCClassEntry from npc.py for typed input."
        ),
    )
    gear: list[str] = Field(
        default_factory=list,
        description="Notable equipment, weapons, or items the NPC carries",
    )

    # ---- Presentation ------------------------------------------------------
    appearance: str = Field(
        default="",
        description=(
            "Physical description: height, build, distinguishing features, "
            "clothing — this is the only part players may ever see"
        ),
    )
    backstory: str = Field(
        default="",
        description=(
            "Origin story and history.  Context for the GM; "
            "never shared with players unless dramatically appropriate."
        ),
    )

    # ---- Associations ------------------------------------------------------
    linked_locations: list[str] = Field(
        default_factory=list,
        description="Location names where this NPC is typically found or has significance",
    )
    linked_quests: list[str] = Field(
        default_factory=list,
        description="Quest titles this NPC is involved in as giver, target, or obstacle",
    )


class GMLocationDocument(BaseModel):
    """Full location record stored in a ``gm_location`` document.

    Contains everything needed to recall a place consistently — hidden areas,
    true history, and GM secrets are never shown to players.  Players see
    :class:`PlayerEntityCard` (``player_location``) with only what they have
    discovered through exploration.
    """

    # ---- Identity ----------------------------------------------------------
    name: str = Field(..., description="Location name as it appears in the narrative")
    location_type: str = Field(
        default="",
        description=(
            "Classification, e.g. 'city', 'dungeon', 'tavern', 'wilderness', "
            "'ruin', 'stronghold'"
        ),
    )
    region: str = Field(default="", description="Broader region, continent, or world area this belongs to")

    # ---- GM-only detail ----------------------------------------------------
    description: str = Field(
        default="",
        description=(
            "Full sensory description: sights, sounds, smells, atmosphere — "
            "the GM's prompt text for scene setting"
        ),
    )
    hidden_areas: list[str] = Field(
        default_factory=list,
        description="Secret rooms, passages, or sub-locations not yet discovered by players",
    )
    traps_hazards: list[str] = Field(
        default_factory=list,
        description="Traps, environmental hazards, or hidden dangers",
    )
    true_history: str = Field(
        default="",
        description=(
            "The real history of this place — may contradict what locals believe or "
            "what players have been told"
        ),
    )
    secrets: list[str] = Field(
        default_factory=list,
        description="Facts about this location that are not publicly known",
    )

    # ---- Player-visible baseline ------------------------------------------
    known_to_players: str = Field(
        default="",
        description=(
            "What the players currently know about this location — "
            "copied into the player_location card on first visit"
        ),
    )

    # ---- Commerce & contacts ----------------------------------------------
    notable_shops: list[str] = Field(
        default_factory=list,
        description="Shops, vendors, or services available here",
    )
    contacts: list[str] = Field(
        default_factory=list,
        description="NPC names who can be found or reached at this location",
    )

    # ---- Associations ------------------------------------------------------
    linked_npcs: list[str] = Field(
        default_factory=list,
        description="NPC names associated with this location",
    )
    linked_quests: list[str] = Field(
        default_factory=list,
        description="Quest titles that involve or are centred on this location",
    )
    connected_locations: list[str] = Field(
        default_factory=list,
        description="Adjacent or directly reachable locations",
    )


class QuestStage(BaseModel):
    """A single stage or milestone in a quest."""

    title: str = Field(..., description="Short label for this stage, e.g. 'Investigate the docks'")
    description: str = Field(default="", description="What the players need to do / discover in this stage")
    completed: bool = Field(default=False, description="Whether this stage has been resolved")


class GMQuestDocument(BaseModel):
    """Full quest outline stored in a ``gm_quest`` document.

    Captures everything needed to run and track a quest consistently.  The
    Storyboard Agent writes these; they are hidden from players.  The player-
    facing view is the ``player_quest_log`` entries written by the Notes Agent
    as the quest progresses.
    """

    # ---- Identity ----------------------------------------------------------
    title: str = Field(..., description="Quest title as the GM knows it")
    giver: str = Field(
        default="",
        description="NPC name (or faction) who assigned or originated this quest",
    )
    quest_type: str = Field(
        default="",
        description=(
            "Classification, e.g. 'main', 'side', 'faction', 'personal', "
            "'discovery', 'escort', 'retrieval'"
        ),
    )

    # ---- Objective & stakes -----------------------------------------------
    objective: str = Field(
        ...,
        description="Clear one-sentence statement of what success looks like",
    )
    stakes: str = Field(
        default="",
        description="What happens if the players fail or refuse — raises dramatic tension",
    )
    secrets: list[str] = Field(
        default_factory=list,
        description="Hidden truths about this quest that may be revealed mid-play",
    )

    # ---- Structure ---------------------------------------------------------
    stages: list[QuestStage] = Field(
        default_factory=list,
        description=(
            "Ordered stages/milestones.  Each stage can be marked completed as "
            "play progresses.  Used by the Storyboard Agent to track pacing."
        ),
    )
    complications: list[str] = Field(
        default_factory=list,
        description=(
            "Potential complications or twists that could arise — "
            "seeds for dynamic scene generation"
        ),
    )

    # ---- Rewards -----------------------------------------------------------
    rewards: list[str] = Field(
        default_factory=list,
        description="XP, gold, items, or narrative rewards on completion",
    )

    # ---- Associations ------------------------------------------------------
    linked_npcs: list[str] = Field(
        default_factory=list,
        description="NPC names involved as giver, obstacle, ally, or target",
    )
    linked_locations: list[str] = Field(
        default_factory=list,
        description="Location names where key quest events occur",
    )


# ---------------------------------------------------------------------------
# Structured session notes (Notes Agent)
# ---------------------------------------------------------------------------


class SessionNoteEntry(BaseModel):
    """One structured note entry recorded by the Notes Agent.

    Designed to answer the six key questions for reliable session recaps and
    story generation:

    - **What** happened?
    - **Where** did it happen?
    - **Why** did it happen (motive / cause)?
    - **When** did it happen (relative narrative time)?
    - **What changed** as a result?
    - **What stayed the same** (important constants to preserve)?
    """

    what: str = Field(..., description="What happened — the core event in one sentence")
    where: str = Field(
        default="",
        description="Location name or area where the event occurred",
    )
    why: str = Field(
        default="",
        description="Cause or motive — why this event happened",
    )
    when: str = Field(
        default="",
        description=(
            "Relative narrative time, e.g. 'start of scene 3', "
            "'after the party rested', 'immediately after the ambush'"
        ),
    )
    what_changed: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete changes that resulted from this event — "
            "NPC attitudes shifted, quests advanced, locations revealed, etc."
        ),
    )
    what_stayed_same: list[str] = Field(
        default_factory=list,
        description=(
            "Important constants to preserve — ongoing threats, relationships, "
            "or facts that were NOT affected by this event"
        ),
    )
    linked_entities: list[str] = Field(
        default_factory=list,
        description="NPC names, location names, or quest titles referenced in this note",
    )


# ---------------------------------------------------------------------------
# Entity associations (NPC ↔ Location ↔ Quest)
# ---------------------------------------------------------------------------


class EntityAssociation(BaseModel):
    """A link between two named entities (NPC, location, or quest).

    Stored in ``associations.json`` inside the session folder.  Used to:
    - Power in-chat hyperlinks — any entity name in chat output is clickable
      and resolves to the player-visible card via
      ``GET /sessions/{id}/entity/{name}``.
    - Help the Storyboard Agent maintain plot consistency by knowing which
      NPCs appear at which locations or within which quests.
    """

    entity_a: str = Field(..., description="Name of the first entity")
    entity_a_type: Literal["npc", "location", "quest"] = Field(..., description="Type of entity_a")
    entity_b: str = Field(..., description="Name of the second entity")
    entity_b_type: Literal["npc", "location", "quest"] = Field(..., description="Type of entity_b")
    relationship: str = Field(
        default="",
        description=(
            "Free-text description of the relationship, e.g. 'Warlord Vrak is found at The Black Keep', "
            "'The Black Keep is the target of quest Siege of Shadows'"
        ),
    )


# ---------------------------------------------------------------------------
# Player-visible entity card (powers in-chat hyperlinks)
# ---------------------------------------------------------------------------


class PlayerEntityCard(BaseModel):
    """The information a player sees when clicking an entity name in the chat transcript.

    Contains **only** information the characters have gathered.  This is the
    shared view constructed from ``player_npc``, ``player_location``, or
    ``player_quest_log`` documents — never from the hidden GM versions.

    Written by the NPC Manager (for NPCs) or Notes Agent (for locations /
    quests) and updated each time new information is discovered.
    """

    name: str = Field(..., description="Entity name as it appears in chat")
    entity_type: Literal["npc", "location", "quest"] = Field(..., description="What kind of entity this is")

    # ---- Common fields -----------------------------------------------------
    summary: str = Field(
        default="",
        description=(
            "One-paragraph player-visible summary — physical appearance for NPCs, "
            "known description for locations, player's stated objective for quests"
        ),
    )
    relationship_notes: str = Field(
        default="",
        description=(
            "How the party knows this entity — first encounter, current relationship, "
            "any dialogue or interactions logged"
        ),
    )
    known_associations: list[str] = Field(
        default_factory=list,
        description=(
            "Other entity names the players know are connected to this one, "
            "e.g. 'Seen at The Black Keep', 'Involved in Siege of Shadows'"
        ),
    )

    # ---- NPC-specific (ignored for other types) ----------------------------
    appearance: str = Field(
        default="",
        description="Physical description as observed by the players",
    )
    attitude_toward_party: str = Field(
        default="neutral",
        description=(
            "Current observable attitude: hostile, dislike, neutral, like, love, worship. "
            "Derived from the GM attitude rank — shown to players only when they can tell."
        ),
    )

    # ---- Location-specific (ignored for other types) ----------------------
    known_shops_contacts: list[str] = Field(
        default_factory=list,
        description="Shops and contacts the players have discovered at this location",
    )

    # ---- Quest-specific (ignored for other types) -------------------------
    current_objective: str = Field(
        default="",
        description="The player-visible current objective for this quest",
    )
    completed_stages: list[str] = Field(
        default_factory=list,
        description="Stage titles the players know have been completed",
    )
