"""Template fallback scenes must not paste the same sentences into every scene."""
import re

from server.agents.scene_validator import build_fallback_scene

ARGS = {
    "location_name": "Ashen Market", "npc_name": "Eldrin", "player_name": "Mira Vale", "emotional_state": "guarded",
    "inciting_incident": "Grain stores in Saltmere are catching fire, causing shortages and unrest",
    "central_conflict": "The Salt Court controls the grain and the Reed Guild keeps the ferries free",
    "immediate_stakes": "If the fires continue the town will starve", "sensory_detail": "Smoke hangs over the stalls",
    "campaign_name": "Saltmere",
}


def _sentences(text):
    return {" ".join(s.lower().split()) for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.split()) >= 6}


def _chain(count):
    scenes = []
    for index in range(count):
        scenes.append(build_fallback_scene(**ARGS, recent_text="\n".join(scenes[-3:]), variation=index))
    return scenes


def test_consecutive_fallback_scenes_do_not_restate_the_same_sentences():
    first, second, third = _chain(3)
    assert not _sentences(first) & _sentences(second)
    assert not _sentences(second) & _sentences(third)


def test_the_shell_rotates_between_scenes():
    first, second, third = _chain(3)
    assert len({first.split("\n")[0], second.split("\n")[0], third.split("\n")[0]}) == 3


def test_first_scene_is_unchanged_without_history():
    assert build_fallback_scene(**ARGS) == build_fallback_scene(**ARGS, recent_text="", variation=0)
    assert "Grain stores in Saltmere" in build_fallback_scene(**ARGS)
