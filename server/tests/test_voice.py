"""A campaign's voice comes from its own tone and words, the same way every time."""
from server.agents import voice


def test_the_voice_follows_the_tone_the_table_chose():
    grim = voice.voice_sheet({"settings": {"tone": "grim and grounded", "genre": "fantasy"}})
    cozy = voice.voice_sheet({"settings": {"tone": "warm and cozy", "genre": "fantasy"}})
    assert "No jokes in the narration" in grim and "No jokes" not in cozy
    assert "Warm and unhurried" in cozy


def test_the_tables_own_words_are_a_register_sample_not_facts():
    sheet = voice.voice_sheet({"settings": {"tone": "grim", "setting_summary": "A grim harbour town where the lighthouse keeper vanished. Nobody talks about the fog."}})
    assert "match the register, not the facts" in sheet and "lighthouse keeper vanished" in sheet


def test_the_voice_has_base_rules_even_with_no_settings():
    sheet = voice.voice_sheet(None)
    assert sheet.startswith("VOICE:") and "Plain, concrete sentences" in sheet and "match the register" not in sheet


def test_it_is_added_to_the_contract_once_and_the_original_is_untouched():
    contract = {"agent_output_contract": "Obey canon."}
    meta = {"settings": {"tone": "grim"}}
    once = voice.with_voice(contract, meta)
    twice = voice.with_voice(once, meta)
    assert once["agent_output_contract"].startswith("Obey canon.") and "VOICE:" in once["agent_output_contract"]
    assert twice == once and contract == {"agent_output_contract": "Obey canon."}
    assert voice.with_voice({}, None)["agent_output_contract"].startswith("VOICE:")
