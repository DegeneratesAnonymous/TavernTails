import importlib
import random

from server.agents import rollable_tables as rt
from server.agents import rollable_tables_extract as ex


def _narrative():
    importlib.import_module("server.agents.sessions")  # sessions <-> narrative import cycle: sessions must load first
    return importlib.import_module("server.agents.narrative")


def _word(x0, y0, text, w=None, h=10.0):
    return (x0, y0, x0 + (w or 6.0 * len(text)), y0 + h, text)


def _table_words(rows, gutter_x=100.0, text_x=110.0, start_y=200.0, step=14.0, header=None):
    words = []
    if header:
        words.append(_word(gutter_x - 24, start_y - 20, "1d6", w=22))
        x = text_x
        for tok in header.split():
            words.append(_word(x, start_y - 20, tok))
            x += 6.0 * len(tok) + 4
    for i, text in enumerate(rows):
        y = start_y + i * step
        num = str(i + 1)
        words.append((gutter_x - 6.0 * len(num), y, gutter_x, y + 10, num))
        x = text_x
        for tok in text.split():
            words.append(_word(x, y, tok))
            x += 6.0 * len(tok) + 4
    return words


def _filler(n=30):
    return [_word(400 + (i % 5) * 40, 20 + i * 3, "filler") for i in range(n)]


def test_extractor_reads_a_gutter_table_with_its_lead_in():
    rows = ["...a goblin selling maps", "...two bandits at the gate", "...a lost child by the well",
            "...a hooded rider at dusk", "...a toll collector asleep", "...a ghost weeping softly"]
    tables = ex.extract_page_tables(_table_words(rows, header="The party meets...") + _filler(), 612)
    assert len(tables) == 1
    table = tables[0]
    assert table["title"].endswith("The party meets...")
    assert [r["lo"] for r in table["rows"]] == [1, 2, 3, 4, 5, 6]
    assert table["rows"][1]["text"] == "...two bandits at the gate"


def test_extractor_ignores_numbers_that_do_not_count_up_like_a_die():
    words = _table_words(["gold", "silver", "copper", "iron"])
    # relabel 1,2,3,4 -> 7,3,9,2 so nothing resembles a die sequence
    scrambled = [(a, b, c, d, {"1": "7", "2": "3", "3": "9", "4": "2"}.get(t, t)) for a, b, c, d, t in words]
    assert ex.extract_page_tables(scrambled + _filler(), 612) == []


def test_extractor_merges_a_table_split_across_two_columns():
    left = _table_words([f"left entry {i}" for i in range(1, 5)], gutter_x=60, text_x=70)
    right_rows = [f"right entry {i}" for i in range(5, 9)]
    right = []
    for i, text in enumerate(right_rows):
        y = 200 + i * 14
        right.append((300 - 6, y, 300, y + 10, str(5 + i)))
        right.append(_word(310, y, text.split()[0]))
        right.append(_word(350, y, text.split()[1]))
        right.append(_word(380, y, text.split()[2]))
    tables = ex.extract_page_tables(left + right + _filler(), 612)
    assert len(tables) == 1 and [r["lo"] for r in tables[0]["rows"]] == list(range(1, 9))


RAW = [{
    "title": "The party encounters...", "source": "book.pdf", "page": 9,
    "rows": [{"lo": i, "hi": i, "text": t} for i, t in enumerate([
        "...a goblin selling maps of a place that does not exist.",
        "...two bandits arguing over a stolen cheese wheel.",
        "...a lost child leading a very large dog on a rope.",
        "...a toll collector who weeps whenever coins are paid.",
        "...a hooded rider who asks everyone the way to the sea.",
        "...a ghost insisting the road was moved last night.",
    ], 1)],
}]


def test_build_tables_drops_rule_text_and_adventure_specific_rows():
    raw = [{
        "title": "Traps", "source": "b.pdf", "page": 1,
        "rows": [{"lo": i, "hi": i, "text": t} for i, t in enumerate([
            "A spike pit. DC 15 Dexterity saving throw or take damage.",
            "Roll again twice on this table.",
            "See page 44 for details of Door 9.",
            "The Hall of Echoes in Area 4 has a dais.",
        ], 1)],
    }]
    assert rt.build_tables(raw) == []
    built = rt.build_tables(RAW)
    assert len(built) == 1 and built[0]["category"] == "encounter" and built[0]["lead"] == "The party encounters"


def test_roll_is_a_real_die_roll_reproducible_by_seed_and_avoids_party_phrase():
    index = {"tables": rt.build_tables(RAW)}
    a = rt.roll_for_scene(context="road", scene_type="travel", seed=7, index=index)
    b = rt.roll_for_scene(context="road", scene_type="travel", seed=7, index=index)
    assert a[0]["result"] == b[0]["result"] and a[0]["die"] == "1d6" and 1 <= a[0]["roll"] <= 6
    assert a[0]["result"].startswith("The characters encounter ")
    assert "the party" not in a[0]["result"].lower()
    seen = {rt.roll_for_scene(scene_type="travel", seed=s, index=index)[0]["roll"] for s in range(60)}
    assert seen == {1, 2, 3, 4, 5, 6}


def test_roll_for_scene_without_an_index_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "DEFAULT_INDEX", tmp_path / "missing.json")
    rt._CACHE["data"] = None
    assert rt.roll_for_scene(scene_type="opening", count=2, index=rt.load_index(tmp_path / "missing.json")) == []


def test_prompt_block_requires_weaving_and_hides_the_machinery():
    rolls = [{"category": "encounter", "result": "The characters encounter a toll collector who weeps."},
             {"category": "name", "result": "Horia"}]
    block = rt.rolls_prompt_block(rolls)
    assert "REQUIRED" in block and "Weave EVERY one" in block
    assert "Never mention dice, tables, rolls" in block
    assert "toll collector who weeps" in block and "name of a person" in block
    assert rt.rolls_prompt_block([]) == ""


def test_rolls_missing_detects_an_ignored_roll_but_accepts_adapted_wording():
    rolls = [{"result": "The characters encounter 2d4 wandering doppelgangers disguised as site workers."}]
    assert rt.rolls_missing("Mara pushed through the market, bargaining for bread.", rolls) == rolls
    assert rt.rolls_missing("Two doppelganger workers in dusty site clothes watch Mara.", rolls) == []


def test_enabled_respects_genre_and_opt_outs(monkeypatch):
    assert rt.enabled(None) and rt.enabled({"campaign_dna": {"genre": "dark fantasy"}})
    assert not rt.enabled({"campaign_dna": {"genre": "cyberpunk"}})
    assert not rt.enabled({"random_tables": False})
    monkeypatch.setenv("TAVERNTAILS_ROLLABLE_TABLES", "0")
    assert not rt.enabled(None)


def test_narrative_prompt_carries_the_rolls_and_retries_once_when_ignored(monkeypatch):
    narrative = _narrative()

    rolls = [{"category": "encounter", "die": "1d6", "roll": 3, "table": "T", "source": "b.pdf", "page": 1,
              "result": "The characters encounter a toll collector who weeps whenever coins are paid."}]
    prompts: list[str] = []
    drafts = iter([
        '{"narrative": "Mara reached Ashfall at dusk and bought bread from a baker while smoke curled over the rooftops of the quiet market square.", "prompt": "What does Mara do?"}',
        '{"narrative": "Mara reached Ashfall at dusk, where a toll collector wept as every coin clinked into his tin.", "prompt": "What does Mara do?"}',
    ])

    def fake_chat(messages, **_):
        prompts.append(messages[0]["content"])
        return next(drafts, None) or '{"narrative": "Mara reached Ashfall at dusk, where a toll collector wept as every coin clinked into his tin.", "prompt": "What does Mara do?"}'

    monkeypatch.setattr(narrative, "chat_complete", fake_chat)
    result = narrative.generate_narrative(narrative.NarrativeRequest(scene="Ashfall road", player="Mara", table_rolls=rolls))
    assert all("THE DICE HAVE SPOKEN" in p and "toll collector" in p for p in prompts[:2])  # kept until a draft misses the bar
    assert len(prompts) >= 2 and "toll collector" in result.narrative
    assert result.score_detail["table_rolls_woven"] is True
    assert result.score_detail["table_rolls"][0]["die"] == "1d6"


def test_narrative_without_tables_is_unchanged(monkeypatch):
    narrative = _narrative()

    seen = []
    monkeypatch.setattr(narrative, "chat_complete", lambda m, **_: seen.append(m[0]["content"]) or '{"narrative": "x", "prompt": "What does Mara do?"}')
    narrative.generate_narrative(narrative.NarrativeRequest(scene="road", player="Mara", table_rolls=[]))
    assert seen and "THE DICE HAVE SPOKEN" not in seen[0]


def _scan_page(first, count, step=60.0, cols=((100, "alpha"), (300, "bravo")), misread=None, start_y=100.0):
    """A scanned-style page: centred die numbers, then result columns (OCR word boxes in points)."""
    words = []
    for i in range(count):
        n = first + i
        y = start_y + i * step
        label = str(n) if misread is None or n != misread[0] else misread[1]
        words.append((46.0, y, 46.0 + 7 * len(label), y + 10, label))
        for x, name in cols:
            for j, tok in enumerate(f"{name.capitalize()} entry marker{chr(96 + n)} with some words.".split()):
                words.append((x + (j % 3) * 30, y + (j // 3) * 12, x + (j % 3) * 30 + 26, y + (j // 3) * 12 + 10, tok))
    return words


def test_tsv_words_scale_to_points_and_drop_low_confidence():
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    tsv = "\n".join([header, "5\t1\t1\t1\t1\t1\t150\t300\t75\t30\t95.0\tHello", "5\t1\t1\t1\t1\t2\t300\t300\t40\t30\t3.0\tjunk"])
    assert ex.words_from_tsv(tsv, dpi=150) == [(72.0, 144.0, 108.0, 158.4, "Hello")]


def test_scanned_table_chains_across_pages_and_splits_result_columns():
    tables = ex.extract_scanned_tables([(1, 612, 792, _scan_page(1, 8)), (2, 612, 792, _scan_page(9, 3))], "scan.pdf")
    assert tables == []  # 11 rows is not a die; nothing is invented from a run that stops short

    page2 = _scan_page(9, 12)  # 1..20 over two pages
    tables = ex.extract_scanned_tables([(1, 612, 792, _scan_page(1, 8)), (2, 612, 792, page2)], "scan.pdf")
    assert len(tables) == 2
    assert [r["lo"] for r in tables[0]["rows"]] == list(range(1, 21))
    assert tables[0]["rows"][14]["text"] == "Alpha entry markero with some words."
    assert tables[1]["rows"][19]["text"] == "Bravo entry markert with some words."


def test_scanned_gutter_survives_a_misread_number():
    tables = ex.extract_scanned_tables([(1, 612, 792, _scan_page(1, 12, misread=(11, "1")))], "scan.pdf")
    assert tables and [r["lo"] for r in tables[0]["rows"]] == list(range(1, 13))


def test_ocr_word_repair_splits_a_glued_article(monkeypatch):
    monkeypatch.setattr(ex, "_DICT", {"group", "a", "rift"})
    assert ex.repair_ocr_word("Agroup") == "A group"
    assert ex.repair_ocr_word("Arift") == "A rift"
    assert ex.repair_ocr_word("Ashfall") == "Ashfall"
    assert ex.repair_ocr_word("0n") == "on"


def test_context_dependent_rows_are_dropped_at_build_time():
    raw = [{"title": "Things", "source": "b.pdf", "page": 1, "rows": [
        {"lo": i, "hi": i, "text": t} for i, t in enumerate([
            "This item is obsessed with a person long dead or who never existed.",
            "The space is attached to the back of a wandering storm giant.",
            "A toll collector weeps whenever coins are paid into his tin.",
            "Two bandits argue over a stolen cheese wheel at the gate.",
            "A hooded rider asks everyone the way to the sea.",
            "A lost child leads a very large dog on a rope.",
            "A ghost insists the road was moved last night.",
            "A peddler sells umbrellas to people standing in the sun.",
            "A bard sings the same verse louder each time he is ignored.",
            "A pair of twins finish each other's lies at the market stall.",
        ], 1)]}]
    texts = [r["text"] for r in rt.build_tables(raw)[0]["rows"]]
    assert len(texts) == 8 and not any(t.startswith(("This item", "The space")) for t in texts)


def test_continuation_scenes_never_roll_bare_names_or_places(monkeypatch):
    narrative = _narrative()
    seen = []
    monkeypatch.setattr(rt, "roll_for_scene", lambda **kw: seen.append(kw["exclude"]) or [])
    narrative._scene_table_rolls(narrative.NarrativeRequest(scene="x", player="Mara", player_actions=["Mara asks about the caravan"]))
    narrative._scene_table_rolls(narrative.NarrativeRequest(scene="x", player="Mara", is_opening_scene=True))
    assert seen[0] == frozenset({"name", "place"}) and seen[1] == frozenset()


def test_roll_text_drops_repeated_lead_ins_and_stray_dots():
    table = {"id": "t", "title": "The party encounters...", "lead": "The party encounters", "die": 4, "category": "encounter",
             "source": "b.pdf", "page": 1, "rows": [{"lo": 1, "hi": 4, "text": "the party encounters.....a dragon turtle harassing a vessel."}]}
    assert rt.roll_table(table, random.Random(1))["result"] == "The characters encounter a dragon turtle harassing a vessel."
    raw = [{"title": "Trouble", "source": "b.pdf", "page": 1, "rows": [
        {"lo": i, "hi": i, "text": t} for i, t in enumerate([
            "The soft floor collapses below the.. party dropping them into a lair.",
            "A toll collector weeps whenever coins are paid into his tin.",
            "Two bandits argue over a stolen cheese wheel at the gate.",
            "A hooded rider asks everyone the way to the sea.",
        ], 1)]}]
    assert rt.build_tables(raw)[0]["rows"][0]["text"] == "The soft floor collapses below the party dropping them into a lair."


def test_a_hard_failure_drops_the_rolls_so_the_retry_runs_as_it_would_without_tables(monkeypatch):
    narrative = _narrative()
    rolls = [{"category": "encounter", "die": "1d6", "roll": 2, "table": "T", "source": "b.pdf", "page": 1,
              "result": "The characters encounter a roadworkers union demanding tolls."}]
    prompts: list[str] = []
    drafts = iter([
        # invents a named person the fact-check does not know -> hard failure
        '{"narrative": "Mara met Captain Hollis Brandt at the gate, who demanded a toll of every wagon on the road.", "prompt": "What does Mara do?"}',
        '{"narrative": "Mara waited at the gate while Orrin Vale counted the wagons on the muddy road, wary of every shadow.", "prompt": "What does Mara do?"}',
    ])

    def fake_chat(messages, **_):
        prompts.append(messages[0]["content"])
        return next(drafts, None) or '{"narrative": "Mara waited at the gate.", "prompt": "What does Mara do?"}'

    monkeypatch.setattr(narrative, "chat_complete", fake_chat)
    result = narrative.generate_narrative(narrative.NarrativeRequest(
        scene="gate", player="Mara", table_rolls=rolls, known_names=["Mara", "Orrin Vale"],
        player_actions=["Mara waits at the gate"]))
    assert "THE DICE HAVE SPOKEN" in prompts[0]
    assert all("THE DICE HAVE SPOKEN" not in p for p in prompts[1:])
    assert result.score_detail["table_rolls_dropped"] is True
    assert result.score_detail["table_rolls_woven"] is False


def test_prompt_keeps_new_introductions_unnamed_in_continuations_only():
    rolls = [{"category": "encounter", "result": "The characters encounter a toll collector."}]
    assert "UNNAMED" in rt.rolls_prompt_block(rolls)
    assert "UNNAMED" not in rt.rolls_prompt_block(rolls, is_opening=True)


def test_no_names_rerolls_results_that_introduce_a_proper_name():
    named = {"id": "n", "title": "The party encounters...", "lead": "The party encounters", "die": 4, "category": "encounter",
             "rows": [{"lo": i, "hi": i, "text": "Christoff Erson, a frail man of remarkable height, pondering the road."} for i in range(1, 5)]}
    plain = {"id": "p", "title": "The party sees...", "lead": "The party sees", "die": 4, "category": "encounter",
             "rows": [{"lo": i, "hi": i, "text": "a toll collector weeping over a tin of coins."} for i in range(1, 5)]}
    for seed in range(20):
        rolls = rt.roll_for_scene(scene_type="travel", seed=seed, index={"tables": [named, plain]}, no_names=True)
        assert rolls and "Christoff" not in rolls[0]["result"]
    assert rt.roll_for_scene(scene_type="travel", seed=1, index={"tables": [named]}, no_names=True) == []
    assert "Christoff" in rt.roll_for_scene(scene_type="travel", seed=1, index={"tables": [named]})[0]["result"]


def test_a_draft_below_the_quality_bar_is_retried_without_the_rolls(monkeypatch):
    narrative = _narrative()
    rolls = [{"category": "sensory", "die": "1d6", "roll": 4, "table": "T", "source": "b.pdf", "page": 1,
              "result": "The characters see a violent thunderstorm masking a storm giant family reunion."}]
    prompts: list[str] = []
    monkeypatch.setattr(narrative, "score_scene", lambda *a, **k: narrative.ScoreResult(score=40, passes_threshold=False))

    def fake_chat(messages, **_):
        prompts.append(messages[0]["content"])
        return '{"narrative": "Mara waited at the gate as rain hammered the stone and a storm giant roared over the marsh.", "prompt": "What does Mara do?"}'

    monkeypatch.setattr(narrative, "chat_complete", fake_chat)
    result = narrative.generate_narrative(narrative.NarrativeRequest(scene="gate", player="Mara", table_rolls=rolls))
    assert "THE DICE HAVE SPOKEN" in prompts[0]
    assert all("THE DICE HAVE SPOKEN" not in p for p in prompts[1:]) and len(prompts) > 1
    assert result.score_detail["table_rolls_dropped"] is True


def test_openings_roll_one_gentle_ingredient_never_a_creature_encounter():
    assert rt.rolls_needed(True) == 1 and rt.rolls_needed(False) == 1
    assert not {"encounter", "npc"} & set(rt.CATEGORY_WEIGHTS["opening"])
    index = {"tables": [
        {"id": "e", "title": "The party encounters...", "lead": "The party encounters", "die": 4, "category": "encounter",
         "rows": [{"lo": i, "hi": i, "text": "a storm giant family reunion in the rain"} for i in range(1, 5)]},
        {"id": "s", "title": "The space smells of...", "lead": "", "die": 4, "category": "sensory",
         "rows": [{"lo": i, "hi": i, "text": "Brine and lamp oil hang in the cold air."} for i in range(1, 5)]},
    ]}
    for seed in range(25):
        rolls = rt.roll_for_scene(scene_type="opening", seed=seed, index=index, count=rt.rolls_needed(True))
        assert [r["category"] for r in rolls] == ["sensory"]
