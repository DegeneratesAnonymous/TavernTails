"""Quick Start seeds follow the chosen genre (found via a Fantasy campaign that got a witness mystery)."""
import re

import pytest

from server.agents.content_bundles import _LOCATION_TYPES, generate_starter_seed
from server.agents.genre_seeds import GENRE_SEEDS, pools_for
from server.agents.opening_setup import _mentions_lying, build_campaign_brief

GENRES = sorted(GENRE_SEEDS)
CHAR = {"name": "Arin Quickstep", "class_name": "Rogue", "level": 3}


def _brief(genre: str, n: int) -> tuple[dict, dict]:
    seed = generate_starter_seed({"genre": genre}, seed=n)
    camp = {"campaign_name": "Shadows Over Veldrath", "genre": genre}
    return seed, build_campaign_brief(campaign=camp, character=CHAR, opening_seed=seed)


@pytest.mark.parametrize("genre", GENRES)
def test_each_genre_draws_a_coherent_scenario_from_its_own_pool(genre):
    place_for = {p.type: p for p in pools_for(genre).places}
    for n in range(30):
        seed = generate_starter_seed({"genre": genre}, seed=n)
        place = place_for[seed["location_type"]]  # a place from this genre, not the generic table
        assert seed["location_type"] not in _LOCATION_TYPES
        assert seed["inciting_event"].rstrip(".").lower() in {e.lower() for e in place.events}
        assert seed["first_clue_or_question"] in place.questions  # the event and question belong to the place
        assert seed["specific_stakes"] == place.stakes
        assert seed["player_decision"] == place.decision
        assert seed["named_npc_or_visible_threat"].split(" (")[0]  # named, with a role from the place
        assert seed["genre_pool"] == genre


@pytest.mark.parametrize("genre", GENRES)
def test_genre_briefs_are_valid_and_free_of_mystery_fixtures(genre):
    for n in range(30):
        seed, brief = _brief(genre, n)
        text = " ".join(brief["brief_paragraphs"] + brief["known_facts"] + brief["provisional_facts"])
        assert brief["quality_debug"]["valid"], (genre, n, brief["quality_debug"])
        for fixture in ("Three witnesses", "road wardens", "refuge keepers", "sealed letter", "public count", "the object"):
            assert fixture not in text, (genre, n, text)
        assert not re.search(r"[.!?] [a-z]", text), text
        assert not re.search(r"\ba [aeiou]", text, re.I), text  # "a abandoned asylum"
        assert "this trouble" in brief["character_entry_prompt"]


def test_unspecified_and_mystery_genres_keep_the_generic_pools():
    for genre in ("", "mystery", "noir"):
        assert pools_for(genre) is None
        for n in range(15):
            seed = generate_starter_seed({"genre": genre} if genre else {}, seed=n)
            assert seed["location_type"] in _LOCATION_TYPES
            assert seed["genre_pool"] == ""


def test_open_question_is_the_trouble_instead_of_an_invented_scene():
    seed, brief = _brief("fantasy", 3)
    assert f"Everyone is asking the same thing: {seed['first_clue_or_question']}" in brief["brief_paragraphs"][1]


def test_lying_matches_whole_words_only():
    assert _mentions_lying("who is lying about the ward?")
    assert _mentions_lying("someone lied")
    for innocent in ("who is hoarding supplies?", "i believe it", "what relief is coming", "the allies arrive"):
        assert not _mentions_lying(innocent), innocent


def test_a_mine_in_a_fantasy_seed_is_not_a_guild_charter_dispute():
    from server.agents.opening_setup import UNKNOWN_AUTHORITY, _institution_or_faction

    seed = {"genre_pool": "fantasy", "inciting_event": "The night shift fails to come up.", "specific_stakes": "the mine"}
    assert _institution_or_faction(seed, {}, "Ashveil Delve", strict=True) == UNKNOWN_AUTHORITY
    assert "Guild factions" in _institution_or_faction(
        {"genre_pool": "political", "inciting_event": "a ledger of bribes surfaces during the vote"}, {}, "Greymoor Hall", strict=True)
