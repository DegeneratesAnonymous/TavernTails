from server.storage.documents import (
    CATEGORY_DEFAULT_VISIBILITY,
    KNOWN_CATEGORIES,
    LocalDocumentStore,
    default_visibility_for_category,
)


def test_local_store_round_trip(tmp_path):
    store = LocalDocumentStore(tmp_path)
    created = store.save_document(session_id="sess1", name="Guide", content="Hello DM")
    assert created.id and created.session_id == "sess1"
    assert created.filename.endswith('.txt')
    listed = store.list_documents("sess1")
    assert len(listed) == 1
    assert listed[0].name == "Guide"
    assert listed[0].filename.endswith('.txt')
    assert listed[0].size == len(b"Hello DM")
    meta, content = store.read_document("sess1", created.id)
    assert meta.id == created.id
    assert content == "Hello DM"
    deleted = store.delete_document("sess1", created.id)
    assert deleted is True
    assert store.list_documents("sess1") == []


# ---------------------------------------------------------------------------
# DocumentCategory model — visibility defaults
# ---------------------------------------------------------------------------

def test_gm_categories_default_to_hidden():
    """GM document categories must default to hidden so players never see them."""
    for cat in ("gm_plot", "gm_npc", "gm_location", "gm_quest", "gm_notes"):
        assert CATEGORY_DEFAULT_VISIBILITY[cat] == "hidden", (
            f"Expected gm category '{cat}' to default to hidden"
        )
        assert default_visibility_for_category(cat) == "hidden"


def test_player_categories_default_to_shared():
    """Player and world document categories must default to shared."""
    for cat in ("player_npc", "player_location", "player_quest_log", "player_journal", "world_lore", "core"):
        assert CATEGORY_DEFAULT_VISIBILITY[cat] == "shared", (
            f"Expected player/world category '{cat}' to default to shared"
        )
        assert default_visibility_for_category(cat) == "shared"


def test_unknown_category_defaults_to_shared():
    """Unknown / custom category names fall back to shared for forward-compatibility."""
    assert default_visibility_for_category("custom_category") == "shared"
    assert default_visibility_for_category("") == "shared"


def test_known_categories_contains_all_expected():
    """KNOWN_CATEGORIES covers all documented category strings."""
    expected = {
        "gm_plot", "gm_npc", "gm_location", "gm_quest", "gm_notes",
        "player_npc", "player_location", "player_quest_log", "player_journal",
        "world_lore", "core",
    }
    assert expected.issubset(KNOWN_CATEGORIES)

