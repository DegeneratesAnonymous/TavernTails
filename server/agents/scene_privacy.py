"""What a client may be sent from a scene.

``scene.json`` on disk keeps the full director output: the AI GM needs the hidden
pressure and what each NPC knows or wants to write the next scene.  Players must
not receive those in API responses or broadcasts, and the client has no use for
them, so every outgoing scene goes through :func:`player_view`.
"""
from __future__ import annotations

from typing import Any

# Planning and secrets owned by the GM, at the top level of a scene.
GM_ONLY_SCENE_KEYS = frozenset({
    "campaign_storyboard", "session_storyboard", "arc_plan", "scene_beat_plan", "selected_scene_beat",
})
# Inside scene_director_data.
GM_ONLY_DIRECTOR_KEYS = frozenset({"hidden_pressure"})
GM_ONLY_NPC_KEYS = frozenset({"what_they_know", "what_they_want", "secrets", "secret", "motivations"})


def _clean_npc(npc: Any) -> Any:
    return {k: v for k, v in npc.items() if k not in GM_ONLY_NPC_KEYS} if isinstance(npc, dict) else npc


def player_npc_list(npcs: Any) -> Any:
    """``npcs.json`` as a player may read it: the DM's notes on what each NPC knows, wants and hides are removed."""
    if not isinstance(npcs, list):
        return npcs
    hidden = GM_ONLY_NPC_KEYS | {"known_information", "current_goal", "hidden_pressure"}
    return [{k: v for k, v in npc.items() if k not in hidden} if isinstance(npc, dict) else npc for npc in npcs]


def player_view(scene: Any) -> Any:
    """A copy of ``scene`` without GM-only fields; anything that is not a scene dict is returned as is."""
    if not isinstance(scene, dict):
        return scene
    view = {k: v for k, v in scene.items() if k not in GM_ONLY_SCENE_KEYS}
    director = view.get("scene_director_data")
    if isinstance(director, dict):
        director = {k: v for k, v in director.items() if k not in GM_ONLY_DIRECTOR_KEYS}
        if "primary_npc" in director:
            director["primary_npc"] = _clean_npc(director["primary_npc"])
        if isinstance(director.get("secondary_entities"), list):
            director["secondary_entities"] = [_clean_npc(e) for e in director["secondary_entities"]]
        view["scene_director_data"] = director
    return view
