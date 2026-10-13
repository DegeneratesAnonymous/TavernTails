from server.agents import scene_qa


def test_noun_phrase_clue_becomes_a_sentence():
    assert scene_qa._clue_sentence("a charred scrap of paper") == "Lying in plain sight is a charred scrap of paper."
    assert scene_qa._clue_sentence("A cracked seal.") == "Lying in plain sight is a cracked seal."


def test_clue_ending_in_markup_is_not_given_a_second_full_stop():
    out = scene_qa._clue_sentence("a charred scrap of paper with *The Court has spoken.*")
    assert out.endswith("*") and not out.endswith("*.")


def test_clue_that_is_already_a_sentence_is_kept():
    assert scene_qa._clue_sentence("The ferryman saw who lit the fire") == "The ferryman saw who lit the fire."


def test_a_clue_that_is_already_a_clause_is_not_given_a_second_lead_in():
    clue = "a charred grain sack bearing the Reed Guild's emblem is found near the Low Dock"
    out = scene_qa._clue_sentence(clue)
    assert out == "A charred grain sack bearing the Reed Guild's emblem is found near the Low Dock."
    assert "Lying in plain sight" not in out
