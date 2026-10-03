"""Issue #180: canonical intent, provenance, and semantic QA for generated openings.

Acceptance criteria (from the issue):

1. A campaign title or one generic keyword cannot select an unrelated setting template.
2. Character class alone cannot establish object properties, secret knowledge,
   patron intent, prior relationships, or setting law.
3. "AI build setup" produces a mutually coherent answer set, not independent option picks.
4. Every player-facing opening claim can be traced to an approved source fact or an
   explicitly provisional generation.
5. Regression cases fail when unsupported facts are introduced, even if the prose is
   grammatically fluent and specific.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.agents import generation_intent as gi
from server.agents import opening_setup as opening_setup_module
from server.agents import sessions as sessions_module
from server.agents.content_bundles import generate_starter_seed
from server.agents.generation_intent import (
    OpeningIntent,
    PromotionError,
    build_opening_intent,
    build_source_trace,
    can_promote,
    capitalize_sentences,
    definite,
    elaborate_fact,
    find_internal_language,
    find_malformed_sentences,
    find_unsupported_claims,
    intent_from_opening,
    intent_with_seed,
    make_fact,
    promote_fact,
    semantic_report,
    strip_internal_language,
    to_canon_status,
)
from server.agents.opening_setup import (
    NEUTRAL_OBJECT,
    UNKNOWN_PROBLEM,
    UNNAMED_WITNESS,
    answers_coherence_issues,
    answers_to_anchor,
    auto_generate_answers,
    build_campaign_brief,
    build_opening_scene_contract,
    generate_provisional_character_anchor,
    validate_campaign_brief,
    validate_opening_scene_contract,
)
from server.agents.scene_qa import apply_targeted_scene_repairs, run_scene_qa, score_specificity
from server.tests.test_opening_setup import _auth, _client, _create_campaign_session
from server.tests.test_scene_qa import _bundle, _scene

FIXTURE = Path(__file__).parent / "fixtures" / "generation_regressions.json"
CORPUS = json.loads(FIXTURE.read_text(encoding="utf-8"))
SOURCE = CORPUS["source_facts"]
CLASSES = ["", "Paladin", "Warlock", "Wizard", "Rogue", "Ranger", "Cleric", "Fighter", "Warlock / Paladin", "Bard"]


def _corpus_intent() -> OpeningIntent:
    return build_opening_intent(SOURCE["settings"], SOURCE["contract"], character=SOURCE["character"])


# ---------------------------------------------------------------------------
# Provenance and promotion rules
# ---------------------------------------------------------------------------

def test_facts_carry_provenance_and_reject_unknown_labels():
    fact = make_fact("location", "Marrow Gate", "user", source="settings.starting_location")
    assert fact.provenance == "user" and fact.established
    assert not make_fact("location", "Marrow Gate", "seed").established
    assert not make_fact("location", "Marrow Gate", "generated_provisional").established
    with pytest.raises(ValueError):
        make_fact("location", "Marrow Gate", "made_up")


def test_elaboration_is_always_provisional_and_never_inherits_authority():
    parent = make_fact("location", "Marrow Gate", "confirmed_canon")
    child = elaborate_fact(parent, "Marrow Gate, where the lamps burn green")
    assert child.provenance == "generated_provisional"
    assert child.derived_from == [parent.id]
    assert not child.established


def test_a_guess_is_only_promoted_with_an_explicit_confirmation():
    guess = make_fact("actor", "Captain Vell", "generated_provisional")
    with pytest.raises(PromotionError):
        promote_fact(guess, "confirmed_canon", confirmed_by="")
    promoted = promote_fact(guess, "confirmed_canon", confirmed_by="player accepted in session zero")
    assert promoted.provenance == "confirmed_canon" and promoted.established
    assert promoted.confirmed_by == "player accepted in session zero"


def test_origins_are_not_destinations():
    # "user" / "imported" describe who authored a fact; the system cannot promote a guess into them.
    for origin in ("user", "imported", "seed", "generated_provisional"):
        assert not can_promote("generated_provisional", origin)
    assert can_promote("seed", "confirmed_canon")
    with pytest.raises(PromotionError):
        promote_fact(make_fact("actor", "X", "seed"), "user", confirmed_by="me")


def test_provenance_maps_onto_existing_canon_manager_statuses():
    assert to_canon_status("user") == "player_canon"
    assert to_canon_status("imported") == "player_canon"
    assert to_canon_status("confirmed_canon") == "confirmed_canon"
    assert to_canon_status("seed") == "provisional"
    assert to_canon_status("generated_provisional") == "provisional"


def test_intent_keeps_the_strongest_provenance_for_the_same_fact():
    intent = OpeningIntent()
    intent.add(make_fact("location", "Marrow Gate", "generated_provisional"))
    intent.add(make_fact("location", "Marrow Gate", "user"))
    intent.add(make_fact("location", "Marrow Gate", "seed"))
    assert [f.provenance for f in intent.locations] == ["user"]


def test_player_text_becomes_established_facts_and_gaps_become_unknowns():
    intent = _corpus_intent()
    assert intent.premise is not None and intent.premise.provenance == "user"
    assert intent.is_unknown("location")  # the player never named a starting location
    assert intent.is_unknown("stakes")
    intent.add(make_fact("location", "Marrow Gate", "user"))
    assert not intent.is_unknown("location")  # establishing a fact resolves the unknown
    constraint = [f for f in intent.constraints if f.source == "character.backstory"]
    assert constraint and constraint[0].provenance == "user"  # backstory is a constraint, never an actor


# ---------------------------------------------------------------------------
# Acceptance 1: a title or one generic keyword cannot select a template
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "contract",
    [
        {"campaign_name": "The Drowned Citadel of the Pearl Tide", "campaign_pitch": "The Drowned Citadel of the Pearl Tide"},
        {"campaign_name": "Harvest", "campaign_pitch": "Harvest"},
        {"campaign_name": "Ash Guild Election", "campaign_pitch": ""},
    ],
)
def test_title_alone_never_selects_a_premise_template(contract):
    seed = generate_starter_seed({}, contract, seed=1)
    assert seed["seed_mode"] == "grounded_fallback"
    assert seed["generated_by"] == "starter_seed"
    assert seed["starting_location"] not in {"The Low-Tide Reef Gate", "The Cinder Vote Hall", "The Helix Orchard Gantry"}


@pytest.mark.parametrize(
    "pitch",
    [
        "A quiet tale of a village harvest festival.",
        "The council holds a vote about the new well.",
        "Sailors argue about the tide table.",
    ],
)
def test_one_generic_keyword_cannot_hijack_the_premise(pitch):
    seed = generate_starter_seed({"setting_summary": pitch}, {"campaign_pitch": pitch}, seed=1)
    assert seed["seed_mode"] == "grounded_fallback"
    assert seed["generated_by"] == "starter_seed"


def test_a_real_premise_anchor_still_selects_its_template():
    pitch = "A drowned citadel surfaces at low tide and pearl divers vanish."
    seed = generate_starter_seed({"setting_summary": pitch}, {"campaign_pitch": pitch}, seed=1)
    assert seed["seed_mode"] == "premise_template"
    assert seed["generated_by"] == "premise_seed"
    assert seed["field_provenance"]["inciting_event"] == "seed"  # template output is never "user"


def test_random_tables_flavor_established_facts_instead_of_inventing_them():
    contract = {
        "campaign_name": "Salt",
        "campaign_pitch": "Salt smugglers work the docks of Grayhaven Harbor.",
        "player_canon": [{"name": "Old Marrow", "type": "npc", "source": "labelled_lore"}],
    }
    seed = generate_starter_seed({"starting_location": "Grayhaven Harbor"}, contract, seed=7)
    assert seed["starting_location"] == "Grayhaven Harbor"
    assert seed["named_npc_or_visible_threat"].startswith("Old Marrow")
    assert seed["field_provenance"]["starting_location"] == "user"
    assert seed["field_provenance"]["named_npc_or_visible_threat"] == "imported"
    assert seed["field_provenance"]["inciting_event"] == "generated_provisional"
    assert seed["premise_anchor"].startswith("Salt")
    assert "conflict" in seed["unknowns"] and "location" not in seed["unknowns"]


def test_a_campaign_with_nothing_established_says_so():
    seed = generate_starter_seed({}, {}, seed=3)
    assert seed["unknowns"] == ["location", "actor", "conflict", "stakes"]
    assert set(seed["field_provenance"].values()) == {"generated_provisional"}


def test_bundles_built_from_scene_director_output_also_report_provenance():
    from server.agents.content_bundles import build_content_bundle

    bundle = build_content_bundle(
        "campaign_opening",
        scene_director_output={"location": {"name": "Marrow Gate"}, "primary_npc": {"name": "Ilyen"}},
        campaign_settings={"starting_location": "Marrow Gate"},
    )
    required = bundle["required_content"]
    assert required["seed_mode"] == "scene_director"
    assert required["field_provenance"]["starting_location"] == "user"


# ---------------------------------------------------------------------------
# Acceptance 2: class alone cannot establish world facts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("class_name", CLASSES)
@pytest.mark.parametrize("backstory", [{}, {"backstory": "A scholar of border omens."}])
def test_provisional_anchor_never_makes_class_based_claims(class_name, backstory):
    intent = build_opening_intent(
        {"setting_summary": "A hall.", "starting_location": "Cinder Vote Hall"},
        {"campaign_pitch": "Guild factions fight over a charter."},
        character={"name": "Bastog"},
    )
    anchor = generate_provisional_character_anchor(
        character={"name": "Bastog", "class_name": class_name, **backstory},
        premise={"starting_location": "Cinder Vote Hall", "first_clue_or_question": "Who is lying?"},
    )
    for key, value in anchor.items():
        report = semantic_report(value, intent, allow=["Bastog"])
        assert report["ok"], (class_name, key, value, report)


@pytest.mark.parametrize("case", [c for c in CORPUS["cases"] if c["category"] == "invented_class_lore"], ids=lambda c: c["id"])
def test_class_lore_and_invented_history_are_flagged(case):
    kinds = {c["kind"] for c in find_unsupported_claims(case["text"], _corpus_intent(), allow=["Bastog"])}
    assert set(case["expect_kinds"]) <= kinds


def test_only_established_facts_can_vouch_for_history():
    text = "Bastog's patron stirs at the cinder relic."
    bare = _corpus_intent()
    assert any(c["kind"] in {"history", "class_lore"} for c in find_unsupported_claims(text, bare, allow=["Bastog"]))

    # The player wrote it into the backstory: now it is established and allowed.
    written = build_opening_intent(
        SOURCE["settings"], SOURCE["contract"],
        character={"name": "Bastog", "backstory": "Bastog's patron stirs whenever a cinder relic is near."},
    )
    assert not find_unsupported_claims(text, written, allow=["Bastog"])

    # A seed or provisional elaboration must not vouch for it.
    guessed = build_opening_intent(SOURCE["settings"], SOURCE["contract"], character={"name": "Bastog"})
    guessed.add(make_fact("conflict", "Bastog's patron stirs at the cinder relic", "generated_provisional"))
    assert find_unsupported_claims(text, guessed, allow=["Bastog"])


def test_negated_and_hedged_statements_are_not_claims():
    intent = _corpus_intent()
    for text in (
        "No prior relationship with the harbor is assumed.",
        "Bastog may choose to care about the old debt, but nothing establishes one.",
        "Bastog has no assumed debt or secret connection to the guild.",
    ):
        assert not [c for c in find_unsupported_claims(text, intent, allow=["Bastog"]) if c["blocking"] == "yes"], text


# ---------------------------------------------------------------------------
# Acceptance 3: "AI build setup" is one coherent answer set
# ---------------------------------------------------------------------------

def _questionnaire():
    return {
        "campaign_brief": {
            "title": "Ashes of the Fallen Throne",
            "location_name": "Royal Crypt of Varyn",
            "known_facts": ["The dead king's signet was found in a rebel camp.", "The public funeral is underway."],
            "brief_paragraphs": [],
        },
        "questions": [
            {"id": "arrival_reason", "question": "Why are you here?", "options": [
                {"id": "debt", "value": "Repay an old debt"}, {"id": "ai_choose", "value": ""}]},
            {"id": "personal_stake", "question": "Why care?", "options": [
                {"id": "family", "value": "Protect my sister"}, {"id": "ai_choose", "value": ""}]},
            {"id": "followed_complication", "question": "What followed?", "options": [
                {"id": "rival", "value": "A rival followed me"}, {"id": "ai_choose", "value": ""}]},
            {"id": "npc_connection", "question": "Who do you know?", "options": [
                {"id": "friend", "value": "The regent once helped me"}, {"id": "ai_choose", "value": ""}]},
        ],
    }


def test_choosing_ai_per_question_does_not_pick_the_first_option():
    questionnaire = _questionnaire()
    answers = [{"question_id": q["id"], "option_id": "ai_choose"} for q in questionnaire["questions"]]
    anchor = answers_to_anchor(session_id="s", questionnaire=questionnaire, answers=answers, character={"name": "Yungmin"})
    blob = json.dumps(anchor).lower()
    for first_option in ("old debt", "my sister", "a rival followed", "once helped me"):
        assert first_option not in blob
    assert anchor["known_npc_connection"].startswith("No one here has an assumed history")
    # the defaults were produced as a set, so they must agree with each other
    assert not answers_coherence_issues({
        "arrival_reason": anchor["arrival_reason"],
        "personal_stake": anchor["personal_stake"],
        "followed_complication": anchor["followed_complication"],
        "npc_connection": anchor["known_npc_connection"],
    })


def test_contradictory_answers_are_detected():
    assert answers_coherence_issues({
        "followed_complication": "No extra complication followed me here.",
        "fear_of_loss": "The rival who followed me here will find me.",
    })
    assert answers_coherence_issues({
        "npc_connection": "No one here has an assumed history with me.",
        "personal_stake": "My old friend the regent is in danger.",
    })
    assert not answers_coherence_issues({
        "arrival_reason": "I came to see whether the signet is genuine.",
        "personal_stake": "I want the evidence to survive until it can be tested.",
    })


def test_a_contradictory_generated_set_falls_back_as_a_whole(monkeypatch):
    questionnaire = _questionnaire()
    contradictory = {
        "arrival_reason": "I came to see whether the signet is genuine.",
        "followed_complication": "No extra complication followed me here.",
        "personal_stake": "The rival who followed me here is why this matters.",
    }
    monkeypatch.setattr(opening_setup_module, "chat_complete", lambda *a, **k: json.dumps(contradictory))
    monkeypatch.setattr(opening_setup_module, "_is_grounded_ai_answer", lambda *a, **k: True)
    answers = auto_generate_answers(questionnaire=questionnaire, character={"name": "Yungmin"})
    by_id = {a["question_id"]: a["answer_text"] for a in answers}
    assert "the rival" not in json.dumps(by_id).lower()
    assert by_id == {
        q["id"]: opening_setup_module._safe_auto_answer(q, questionnaire) for q in questionnaire["questions"]
    }


# ---------------------------------------------------------------------------
# Acceptance 4: every opening claim traces to a source fact or a provisional generation
# ---------------------------------------------------------------------------

REQUIRED = {
    "starting_location": "Greywood Market",
    "location_identity": "Greywood Market is a crowded square beneath old chapel bells.",
    "first_clue_or_question": "Who moved the reliquary?",
    "specific_stakes": "If no one acts, the reliquary leaves by dusk.",
    "named_npc_or_visible_threat": "Mara Voss (watch captain)",
    "inciting_event": "A chapel reliquary appears on a fishmonger's table.",
    "generated_by": "premise_seed",
}
ANCHOR = {"character_name": "Bastog", "arrival_reason": "I came to inspect chapel marks on the cloth",
          "personal_stake": "my oath depends on proving the relic was moved", "source": "player_answered"}


def test_opening_contract_traces_every_card():
    brief = build_campaign_brief(campaign={"campaign_name": "Amber"}, character={"name": "Bastog"}, opening_seed=REQUIRED)
    opening = build_opening_scene_contract(required=REQUIRED, anchor=ANCHOR, campaign_brief=brief, player_name="Bastog")
    trace = opening["source_trace"]
    cards = {e["card"]: e for e in trace["entries"]}
    assert {"location", "named_npc", "key_object", "visible_problem", "personal_hook", "pressure_or_timer"} <= set(cards)
    assert all(e["status"] in {"traced", "provisional"} for e in trace["entries"])
    assert all(e["status"] != "unsupported" for e in trace["entries"])
    assert trace["summary"]["unsupported"] == 0
    assert cards["location"]["status"] == "traced"
    assert cards["named_npc"]["sources"], "a traced card names the fact that produced it"
    assert trace["facts"] and all(f["provenance"] for f in trace["facts"])


def test_trace_marks_invented_text_as_provisional_or_unsupported():
    intent = intent_with_seed(OpeningIntent(), REQUIRED)
    cards = {"invented": "A forgotten treaty binds the Ashen Conclave to guard the vault."}
    assert build_source_trace(cards, intent)["entries"][0]["status"] == "provisional"
    strict = build_source_trace(cards, intent, allow_provisional=False)
    assert strict["entries"][0]["status"] == "unsupported"
    assert strict["summary"]["unsupported"] == 1


def test_player_answers_vouch_for_history_but_auto_generated_answers_do_not():
    anchor = {**ANCHOR, "personal_stake": "my patron wants proof the relic was moved"}
    answered = intent_from_opening(required=REQUIRED, anchor=anchor, player_name="Bastog")
    generated = intent_from_opening(required=REQUIRED, anchor={**anchor, "source": "auto_generated"}, player_name="Bastog")
    text = "Bastog's patron wants proof the relic was moved."
    assert not find_unsupported_claims(text, answered, allow=["Bastog"])
    assert find_unsupported_claims(text, generated, allow=["Bastog"])


def test_opening_validation_rejects_unsupported_claims_in_fluent_prose():
    brief = build_campaign_brief(campaign={"campaign_name": "Amber"}, character={"name": "Bastog"}, opening_seed=REQUIRED)
    intent = intent_from_opening(required=REQUIRED, brief=brief, anchor=ANCHOR, player_name="Bastog")
    opening = build_opening_scene_contract(required=REQUIRED, anchor=ANCHOR, campaign_brief=brief,
                                           player_name="Bastog", source_intent=intent)
    good = {"text": opening["opening_narrative"], "location": opening["location_name"],
            "choices": [{"label": a} for a in opening["action_options"]]}
    assert validate_opening_scene_contract(scene=good, opening_scene=opening, campaign_brief=brief, anchor=ANCHOR,
                                           player_name="Bastog", source_intent=intent)["valid"]

    invented = {**good, "text": good["text"] + "\n\nThe Ashen Conclave has watched Bastog since the oath was broken."}
    result = validate_opening_scene_contract(scene=invented, opening_scene=opening, campaign_brief=brief, anchor=ANCHOR,
                                             player_name="Bastog", source_intent=intent)
    assert result["valid"] is False
    assert result["checks"]["claims_supported"] is False
    assert any("unsupported" in issue.lower() for issue in result["issues"])


def test_started_session_exposes_the_source_trace(monkeypatch):
    client = _client()
    email = "coherence-trace@example.com"
    session_id, _ = _create_campaign_session(client, email, "Maris Vale")
    monkeypatch.setattr(sessions_module.image_agent, "generate_image",
                        lambda request: type("ImageResult", (), {"image_url": None})())
    setup = client.get(f"/sessions/{session_id}/opening-setup", headers=_auth(email)).json()["questionnaire"]
    submit = client.post(f"/sessions/{session_id}/opening-setup", headers=_auth(email), json={
        "questionnaire_id": setup["questionnaire_id"],
        "answers": [{"question_id": "arrival_reason", "custom_value": "I came to audit a cracked signal mirror"}],
    })
    assert submit.status_code == 200, submit.text
    start = client.post(f"/sessions/{session_id}/start", headers=_auth(email), json={})
    assert start.status_code == 200, start.text
    debug = start.json()["scene"]["quality_debug"]
    assert debug["source_trace"]["entries"], "the debug trace shows which fact produced each opening card"
    assert debug["source_trace"]["summary"]["unsupported"] == 0
    assert isinstance(debug["opening_unknowns"], list)
    assert set(debug["semantic_qa"]) == {"unsupported_claims", "internal_language"}
    assert debug["semantic_qa"]["internal_language"] == []


# ---------------------------------------------------------------------------
# Acceptance 5 + corpus: real bad outputs keep failing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", [c for c in CORPUS["cases"] if c["category"] == "internal_language"], ids=lambda c: c["id"])
def test_corpus_planner_language_is_caught_and_stripped(case):
    assert find_internal_language(case["text"])
    assert not find_internal_language(strip_internal_language(case["text"]))


@pytest.mark.parametrize(
    "case",
    [c for c in CORPUS["cases"] if c["category"] in {"unrelated_faction", "invented_named_character"}],
    ids=lambda c: c["id"],
)
def test_corpus_unsupported_factions_and_names_are_caught(case):
    kinds = {c["kind"] for c in find_unsupported_claims(case["text"], _corpus_intent(), allow=["Bastog"])}
    assert set(case["expect_kinds"]) <= kinds


@pytest.mark.parametrize("case", [c for c in CORPUS["cases"] if c["category"] == "vague_stakes"], ids=lambda c: c["id"])
def test_corpus_vague_stakes_fail_specificity(case):
    assert any(f.startswith("Generic language") for f in score_specificity(case["text"])[1])


@pytest.mark.parametrize("case", [c for c in CORPUS["cases"] if c["category"] == "malformed"], ids=lambda c: c["id"])
def test_corpus_malformed_sentences_are_caught(case):
    defects = {d["defect"] for d in find_malformed_sentences(case["text"])}
    assert set(case["expect_defects"]) <= defects


@pytest.mark.parametrize("case", CORPUS["clean"], ids=lambda c: c["id"])
def test_corpus_clean_prose_still_passes(case):
    assert semantic_report(case["text"], _corpus_intent(), allow=["Bastog"])["ok"]


def test_every_corpus_case_is_rejected_by_semantic_report():
    intent = _corpus_intent()
    for case in CORPUS["cases"]:
        if case["category"] == "vague_stakes":
            continue  # judged by the specificity scorer above
        assert not semantic_report(case["text"], intent, allow=["Bastog"])["ok"], case["id"]


def test_run_scene_qa_fails_fluent_prose_that_adds_unsupported_facts():
    intent = intent_with_seed(OpeningIntent(), {
        "starting_location": "The Frostmark Road Shrine",
        "named_npc_or_visible_threat": "Hadwin Crowe (winter survivor)",
        "first_clue_or_question": "Why did the old silver charms blacken before the survivor arrived?",
    })
    clean = run_scene_qa(scene=_scene(), content_bundle=_bundle(), source_intent=intent, recent_opening_shapes=[])
    assert clean["unsupported_claims"] == [] and clean["internal_language"] == []

    invented = _scene(
        "The Frostmark Road Shrine is no place for comfort. Blackened silver charms hang from ice-stiff cords.\n\n"
        "A bloodied survivor named Hadwin Crowe presses a forgotten symbol into the snow, while the Ashen Conclave "
        "watches from the treeline and Captain Vell recalls the oath the party broke years ago.\n\n"
        "If ignored, the next settlement loses its road, trade, and last witness before nightfall."
    )
    qa = run_scene_qa(scene=invented, content_bundle=_bundle(), source_intent=intent, recent_opening_shapes=[])
    assert qa["pass"] is False
    kinds = {c["kind"] for c in qa["unsupported_claims"]}
    assert {"faction", "named_entity"} <= kinds
    assert any(f.startswith("Unsupported") for f in qa["semantic_failures"])
    assert "unsupported_claim" in qa["regression_tags"]
    assert "unsupported_claims" in qa["repair_targets"]


def test_repairs_cut_unsupported_sentences_instead_of_adding_planner_language():
    intent = intent_with_seed(OpeningIntent(), {"starting_location": "The Frostmark Road Shrine",
                                                "named_npc_or_visible_threat": "Hadwin Crowe (winter survivor)"})
    scene = _scene(
        "The Frostmark Road Shrine is no place for comfort.\n\n"
        "The Ashen Conclave watches from the treeline.\n\n"
        "The scene's concrete table details are: charms; frost."
    )
    qa = run_scene_qa(scene=scene, content_bundle=_bundle(), source_intent=intent, recent_opening_shapes=[])
    repaired = apply_targeted_scene_repairs(scene, qa, player_name="Bastog")
    assert "Ashen Conclave" not in repaired["narrative_body"]
    assert not find_internal_language(repaired["narrative_body"])
    assert not find_internal_language(repaired["text"])


# ---------------------------------------------------------------------------
# Planning / QA language never reaches player-facing prose
# ---------------------------------------------------------------------------

def test_repair_pass_adds_only_in_world_sentences():
    scene = _scene("Bare opening.")
    qa = {
        "repair_targets": ["continuity", "location_identity", "npc_intro", "clue_presentation", "stakes", "specificity",
                           "player_agency"],
        "truth_table": {
            "approved_location": "The Frostmark Road Shrine", "approved_primary_npc": "Hadwin Crowe (winter survivor)",
            "approved_clue": "Why did the old silver charms blacken?", "approved_object": "silver charms",
            "approved_stakes": "If ignored, the road closes before nightfall.",
            "approved_possible_actions": ["Inspect the charms", "Aid Hadwin Crowe", "Follow the tracks"],
        },
    }
    repaired = apply_targeted_scene_repairs(scene, qa, player_name="Bastog", recent_player_actions=["inspect the charms"])
    assert find_internal_language(repaired["text"]) == []
    assert find_malformed_sentences(repaired["text"]) == []
    assert "Hadwin Crowe" in repaired["narrative_body"]


def test_run_scene_qa_fails_scenes_that_leak_planner_language():
    scene = _scene("The scene should start here. The Frostmark Road Shrine waits. Hadwin Crowe watches the charms.")
    qa = run_scene_qa(scene=scene, content_bundle=_bundle(), recent_opening_shapes=[])
    assert qa["pass"] is False
    assert qa["internal_language"]
    assert "internal_language_leak" in qa["regression_tags"]
    assert "internal_language" in qa["repair_targets"]


def test_first_scene_repair_removes_planner_sentences_instead_of_splicing_filler():
    scene = {
        "location": "Gate",
        "narrative_body": "Bastog stands at the gate. The story plan says the scene should start here. The first witness waits.",
        "text": "Bastog stands at the gate. The story plan says the scene should start here. The first witness waits.",
        "choices": [{"label": "Look"}],
    }
    repaired, _validation, _dice = sessions_module._apply_first_scene_contract(
        scene, {"character_name": "Bastog", "arrival_reason": "I came to recover the brass writ"}, player_name="Bastog",
    )
    assert "story plan" not in repaired["narrative_body"].lower()
    assert "pressure in the moment becomes visible" not in repaired["narrative_body"]


def test_safe_fallback_answers_have_no_doubled_punctuation():
    questionnaire = _questionnaire()
    for question in questionnaire["questions"]:
        answer = opening_setup_module._safe_auto_answer(question, questionnaire)
        assert find_malformed_sentences(answer) == [], answer
    assert ".," not in opening_setup_module._safe_auto_answer(questionnaire["questions"][1], questionnaire)


def test_anchor_repair_quotes_first_person_answers_and_skips_null_answers():
    anchor = {
        "character_name": "Maris Vale",
        "arrival_reason": "I came to audit a cracked signal mirror",
        "personal_stake": "My sister vanished after recording this flaw",
        "followed_complication": "No extra complication followed me here; the problem in front of me is enough.",
        "fear_of_loss": "I do not want the clearest evidence to disappear.",
        "known_npc_connection": "No one here has an assumed history with me; I will judge them by what they do now.",
    }
    text = sessions_module._anchor_repair_text(anchor, "Coldbrook Camp", "Maris Vale")
    assert "because I" not in text and "trying to i" not in text
    assert "complication" not in text.lower() and "assumed history" not in text  # null answers are skipped
    assert '"I came to audit a cracked signal mirror."' in text
    assert find_malformed_sentences(text) == []


def test_first_person_arrival_is_not_turned_into_a_broken_pre_scene_clause():
    assert opening_setup_module._pre_scene_from_arrival("I came to audit a mirror") == ""
    assert opening_setup_module._pre_scene_from_arrival("Study an urn before it is hidden") == (
        "was already trying to study an urn before it is hidden"
    )


# ---------------------------------------------------------------------------
# "Unknown / not established" is an acceptable state
# ---------------------------------------------------------------------------

def test_brief_reports_unknowns_instead_of_inventing_lore():
    brief = build_campaign_brief(campaign={"campaign_name": "Quiet Start"},
                                 character={"name": "Ayla", "class_name": "Rogue"},
                                 opening_seed={"starting_location": "Marrow Gate"})
    assert set(brief["unknowns"]) == {"conflict", "stakes", "actor", "object"}
    assert brief["quality_debug"]["valid"] is True
    assert set(brief["quality_debug"]["waived_for_unknowns"]) == {"immediate_problem", "time_matters", "concrete_entity"}
    blob = json.dumps(brief).lower()
    for invented in ("sealed letter", "warden", "guild", "refuge keepers", "rumors contradict"):
        assert invented not in blob
    assert UNKNOWN_PROBLEM in brief["brief_paragraphs"][1]
    assert UNKNOWN_PROBLEM not in brief["known_facts"], "unknowns are never listed as known facts"
    assert NEUTRAL_OBJECT in blob


def test_undeclared_gaps_still_fail_brief_validation():
    brief = build_campaign_brief(campaign={"campaign_name": "Quiet Start"}, character={"name": "Ayla"},
                                 opening_seed={"starting_location": "Marrow Gate"})
    stripped = {**brief, "unknowns": []}
    result = validate_campaign_brief(stripped)
    assert result["valid"] is False and "concrete_entity" in result["issues"]


def test_established_input_is_not_reported_as_unknown():
    brief = build_campaign_brief(
        campaign={"campaign_name": "Relics", "campaign_pitch": "Guild factions fight over a miners' charter."},
        character={"name": "Bastog"},
        opening_seed={
            "starting_location": "Cinder Vote Hall", "inciting_event": "A sealed cinder relic has cracked open.",
            "specific_stakes": "If the count is certified tonight, the charter becomes law.",
        },
    )
    assert brief["unknowns"] == []
    assert "guild factions" in json.dumps(brief).lower()


def test_scene_contract_uses_an_honest_unnamed_witness_not_a_made_up_npc():
    opening = build_opening_scene_contract(
        required={"starting_location": "Marrow Gate", "inciting_event": "A bell rings from the sealed crypt."},
        anchor={"character_name": "the party"}, campaign_brief={}, player_name="",
    )
    assert "Warden Hale" not in opening["opening_narrative"]
    assert UNNAMED_WITNESS in opening["opening_narrative"]
    assert opening["action_options"][1] == "Question the nearest witness"
    assert find_malformed_sentences(opening["opening_narrative"]) == []
    assert opening["opening_narrative"].split("\n\n")[1].startswith("The party arrives")


# ---------------------------------------------------------------------------
# Generated prose is well formed; shared helpers are shared
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pc", ["the party", "Maris Vale"])
@pytest.mark.parametrize("seed", [
    {"starting_location": "Glass Harbor", "inciting_event": "A signal mirror cracks.", "first_clue_or_question": "Who moved it?"},
    {"starting_location": "Thornwatch Pass", "first_clue_or_question": "Who is lying?", "specific_stakes": "At dusk the gate locks."},
    {"starting_location": "Marrow Gate"},
])
def test_generated_openings_are_well_formed(pc, seed):
    brief = build_campaign_brief(campaign={"campaign_name": "Test"}, character={"name": pc}, opening_seed=seed)
    opening = build_opening_scene_contract(required=seed, anchor={"character_name": pc}, campaign_brief=brief, player_name=pc)
    for text in (opening["opening_narrative"], *brief["brief_paragraphs"], *brief["known_facts"]):
        assert find_malformed_sentences(text) == [], text
        assert find_internal_language(text) == [], text


def test_prose_helpers_fix_the_defects_seen_in_real_output():
    assert capitalize_sentences("the party arrives. the pressure rises!\n\nthe party waits.") == (
        "The party arrives. The pressure rises!\n\nThe party waits."
    )
    assert definite("marked clue") == "the marked clue"
    assert definite("The Seal") == "The Seal" and definite("a bell") == "a bell"
    assert opening_setup_module._place_intro("Relics", "Cinder Vote Hall", "Cinder Vote Hall is a heat-stained chamber.") == (
        "Relics begins at Cinder Vote Hall. Cinder Vote Hall is a heat-stained chamber."
    )


def test_generation_modules_share_one_set_of_text_helpers():
    from server.agents import campaign_interpretation

    assert opening_setup_module._clean_raw is gi.clean_text
    assert opening_setup_module._trim_sentence is gi.trim_sentence
    assert opening_setup_module._GROUNDING_STOP_WORDS is gi.STOP_WORDS
    assert campaign_interpretation._text is gi.text_of
    assert campaign_interpretation._unique is gi.unique


def test_scene_director_prefers_the_established_location_over_keyword_invention():
    from server.agents.scene_director import SceneDirectorRequest, _deterministic_director

    request = SceneDirectorRequest(
        campaign_settings={"starting_location": "Grayhaven Harbor", "setting_summary": "Smugglers in a city market."},
        campaign_contract={"campaign_name": "Salt", "campaign_pitch": "Smugglers in a city market."},
    )
    assert _deterministic_director(request).location.name == "Grayhaven Harbor"


def test_fact_discipline_prompt_separates_canon_from_placeholders():
    intent = build_opening_intent(
        {"setting_summary": "Salt smugglers work Grayhaven Harbor.", "starting_location": "Grayhaven Harbor"}, {},
    )
    intent = intent_with_seed(intent, {"generated_by": "starter_seed", "named_npc_or_visible_threat": "Elara Voss (witness)"})
    prompt = gi.fact_discipline_prompt(intent)
    assert "Grayhaven Harbor" in prompt.split("Provisional")[0]
    assert "Elara Voss" in prompt.split("Provisional")[1]
    assert "Never invent" in prompt and "Not established" in prompt


# ---------------------------------------------------------------------------
# Review findings on #182 (each one has a regression test)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pitch", ["A quiet story in a forest.", "Travelers cross the woods at dusk."])
def test_scenery_alone_does_not_select_the_hidden_woodline_template(pitch):
    seed = generate_starter_seed({"setting_summary": pitch}, {"campaign_pitch": pitch}, seed=1)
    assert seed["seed_mode"] == "grounded_fallback"
    assert seed["starting_location"] != "The Hidden Woodline"


def test_woods_plus_a_reason_to_hide_still_selects_the_template():
    pitch = "Refugees are hiding in the woods from raiders."
    seed = generate_starter_seed({"setting_summary": pitch}, {"campaign_pitch": pitch}, seed=1)
    assert seed["seed_mode"] == "premise_template"
    assert seed["starting_location"] == "The Hidden Woodline"


@pytest.mark.parametrize("text", ["Vell watches the gate.", "Mara slammed the door.", "Soren nods at the stranger."])
def test_a_name_that_opens_a_sentence_is_still_checked(text):
    kinds = {c["kind"] for c in find_unsupported_claims(text, _corpus_intent(), allow=["Bastog"])}
    assert "named_entity" in kinds


@pytest.mark.parametrize("text", [
    "Smoke curls from the chimney.", "Rain falls on the road.", "Then the bell rings.", "Silence settles over the crowd.",
    "Nothing moves in the square.", "The signal mirror fails again.",
])
def test_ordinary_sentence_openers_are_not_mistaken_for_names(text):
    assert not find_unsupported_claims(text, _corpus_intent(), allow=["Bastog"]), text


def test_an_established_name_may_open_a_sentence():
    intent = build_opening_intent(SOURCE["settings"], {**SOURCE["contract"],
                                  "player_canon": [{"name": "Vell", "type": "npc", "source": "labelled_lore"}]})
    assert not find_unsupported_claims("Vell watches the gate.", intent)


def test_establishing_a_fact_clears_its_unknown_even_when_it_replaces_a_provisional_one():
    intent = OpeningIntent()
    intent.add_unknown("location")
    intent.add(make_fact("location", "Marrow Gate", "generated_provisional"))
    assert intent.is_unknown("location"), "a guess does not resolve the unknown"
    intent.add(make_fact("location", "Marrow Gate", "user"))
    assert not intent.is_unknown("location")
    assert [f.provenance for f in intent.locations] == ["user"]


def test_stored_bridge_answers_match_the_anchor_and_never_take_the_first_option():
    questionnaire = _questionnaire()
    question = questionnaire["questions"][0]
    stored = sessions_module._normalized_bridge_answers(
        session_id="s", campaign_id="1", character={"id": 7}, questionnaire=questionnaire,
        answers=[{"question_id": question["id"], "option_id": "ai_choose"}],
    )
    assert stored[0]["answer_source"] == "ai_choice"
    assert stored[0]["answer_text"] != "Repay an old debt"
    anchor = answers_to_anchor(session_id="s", questionnaire=questionnaire, character={"name": "Y"},
                               answers=[{"question_id": question["id"], "option_id": "ai_choose"}])
    assert stored[0]["answer_text"] == anchor["arrival_reason"]


def test_brief_does_not_turn_a_pitch_keyword_into_an_object():
    brief = build_campaign_brief(
        campaign={"campaign_name": "Festival", "campaign_pitch": "A harvest festival in a river town."},
        character={"name": "Ayla"}, opening_seed={"starting_location": "Marrow Gate"},
    )
    assert "harvest ledger" not in json.dumps(brief).lower()
    assert "object" in brief["unknowns"]
    # ...while an object the opening seed itself supplies is still used
    seeded = build_campaign_brief(
        campaign={"campaign_name": "Festival"}, character={"name": "Ayla"},
        opening_seed={"starting_location": "Marrow Gate", "inciting_event": "A cracked signal mirror is found on the quay."},
    )
    assert "object" not in seeded["unknowns"]
    assert "cracked signal mirror" in json.dumps(seeded).lower()


def test_runtime_intent_includes_the_selected_characters_backstory():
    claim = "Bastog's patron wants proof the relic was moved."
    without = sessions_module._opening_source_intent(
        required=REQUIRED, opening_anchor=ANCHOR, campaign_brief={}, campaign_settings=SOURCE["settings"],
        campaign_contract=SOURCE["contract"], player_name="Bastog",
    )
    assert find_unsupported_claims(claim, without, allow=["Bastog"])
    with_character = sessions_module._opening_source_intent(
        required=REQUIRED, opening_anchor=ANCHOR, campaign_brief={}, campaign_settings=SOURCE["settings"],
        campaign_contract=SOURCE["contract"], player_name="Bastog",
        character={"name": "Bastog", "backstory": "Bastog's patron wants proof the relic was moved."},
    )
    assert not find_unsupported_claims(claim, with_character, allow=["Bastog"])


def test_quoted_answers_keep_their_own_terminal_punctuation():
    anchor = {
        "character_name": "Maris Vale",
        "arrival_reason": "Who moved the mirror?",
        "personal_stake": "I will not let it vanish!",
        "fear_of_loss": "I do not want the evidence to disappear",
    }
    text = sessions_module._anchor_repair_text(anchor, "Coldbrook Camp", "Maris Vale")
    assert '"Who moved the mirror?"' in text and '"I will not let it vanish!"' in text
    assert '"I do not want the evidence to disappear."' in text  # no terminal mark supplied: exactly one is added
    assert "?." not in text and "!." not in text
    assert find_malformed_sentences(text) == []


def test_opening_qa_inspects_the_current_scene_not_stale_composer_text(monkeypatch):
    calls: list[dict] = []
    real = sessions_module.run_scene_qa

    def spy(**kwargs):
        if "source_intent" in kwargs:
            calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(sessions_module, "run_scene_qa", spy)
    monkeypatch.setattr(sessions_module.image_agent, "generate_image",
                        lambda request: type("ImageResult", (), {"image_url": None})())
    client = _client()
    email = "coherence-qa-current@example.com"
    session_id, _ = _create_campaign_session(client, email, "Maris Vale")
    setup = client.get(f"/sessions/{session_id}/opening-setup", headers=_auth(email)).json()["questionnaire"]
    client.post(f"/sessions/{session_id}/opening-setup", headers=_auth(email), json={
        "questionnaire_id": setup["questionnaire_id"],
        "answers": [{"question_id": "arrival_reason", "custom_value": "I came to audit a cracked signal mirror"}],
    })
    start = client.post(f"/sessions/{session_id}/start", headers=_auth(email), json={})
    assert start.status_code == 200, start.text
    assert len(calls) >= 2
    assert all("narrative_output" not in call for call in calls), (
        "opening QA must read the repaired scene; narrative_output would shadow it with the pre-repair composer text"
    )
