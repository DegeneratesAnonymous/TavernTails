"""Names stay as the table established them; scenes do not echo each other."""
from __future__ import annotations

from server import db
from server.agents import continuity as ct

NAMES = ["Salt Court", "Hale Orrin", "Ashen Market"]


def test_a_near_miss_of_a_locked_name_is_found_and_repaired():
    text = "The Salt Council posted guards. Harl Orrin watched from the Ashen Market."
    drifts = ct.name_drifts(text, NAMES)
    assert ("Salt Council", "Salt Court") in drifts and ("Harl Orrin", "Hale Orrin") in drifts
    assert ct.repair_names(text, drifts) == "The Salt Court posted guards. Hale Orrin watched from the Ashen Market."


def test_the_exact_name_and_unrelated_names_are_left_alone():
    assert ct.name_drifts("The Salt Court met Marta Vey at the Ashen Market.", NAMES) == []
    assert ct.name_drifts("Old Brannock drank at the Rusty Anchor.", NAMES) == []


def test_repair_only_replaces_whole_names():
    assert ct.repair_names("Salt Councillor Vey", [("Salt Council", "Salt Court")]) == "Salt Councillor Vey"


def test_repeated_wording_is_caught_but_a_new_scene_is_not():
    before = "Rain hammered the slate roofs of the Ashen Market while the grain carts waited in the lane."
    again = "Rain hammered the slate roofs of the Ashen Market while the grain carts waited, and Mira listened."
    new = "A bell tolled twice from the harbour and the crowd turned toward the water as one."
    assert ct.check_scene(again, NAMES, [before])["issues"]
    assert not ct.check_scene(new, NAMES, [before])["issues"]
    assert ct.check_scene(new, NAMES, [])["issues"] == []


def test_locked_names_come_from_the_world_the_card_and_the_players_ties():
    owner = db.get_user_by_identifier("continuity@example.com") or db.create_user(
        email="continuity@example.com", password="secret", username="continuity", profile={"name": "c"})
    camp = db.create_campaign(owner_id=owner.id, name="Saltmere")
    db.set_campaign_metadata_keys(camp.id, owner.id, {
        "settings": {"world_name": "Saltmere Reach", "starting_location": "The Ashen Market"},
        "campaign_card": {"factions": [{"name": "Salt Court"}, {"name": "Reeds"}], "people": [{"name": "Hale Orrin"}]},
    })
    names = ct.locked_names(db.get_campaign_by_id(camp.id), ["Tam Ferrier, a ferryman", "Mira"])
    assert names == ["Saltmere Reach", "Ashen Market", "Salt Court", "Hale Orrin", "Tam Ferrier"]
