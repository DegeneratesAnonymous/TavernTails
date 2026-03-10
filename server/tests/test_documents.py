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
# Folder support
# ---------------------------------------------------------------------------

def test_save_document_with_folder(tmp_path):
    """Documents saved with a folder value should persist and appear in list_folders."""
    store = LocalDocumentStore(tmp_path)
    doc = store.save_document(session_id="sess1", name="Spell List", content="fireball", folder="rules/combat")
    assert doc.folder == "rules/combat"
    listed = store.list_documents("sess1")
    assert listed[0].folder == "rules/combat"
    # folder inferred from doc metadata must appear in list_folders
    folders = store.list_folders("sess1")
    assert "rules/combat" in folders


def test_list_folders_union(tmp_path):
    """list_folders returns the union of explicit folders.json entries and doc-derived folders."""
    store = LocalDocumentStore(tmp_path)
    # create an explicit folder with no docs
    store.create_folder("sess1", "empty-folder")
    # save a doc in a different folder
    store.save_document(session_id="sess1", name="Note", content="x", folder="notes")
    folders = store.list_folders("sess1")
    assert "empty-folder" in folders
    assert "notes" in folders


def test_create_folder_persistence(tmp_path):
    """create_folder should persist the folder so it survives a fresh store instance."""
    store = LocalDocumentStore(tmp_path)
    result = store.create_folder("sess1", "my-folder")
    assert result is True
    assert "my-folder" in store.list_folders("sess1")
    # A fresh store reading from the same path should see the same folder
    store2 = LocalDocumentStore(tmp_path)
    assert "my-folder" in store2.list_folders("sess1")


def test_delete_folder_fails_when_docs_exist(tmp_path):
    """delete_folder must return False when documents live directly in that folder."""
    store = LocalDocumentStore(tmp_path)
    store.save_document(session_id="sess1", name="Rules", content="data", folder="rules")
    result = store.delete_folder("sess1", "rules")
    assert result is False


def test_delete_folder_fails_when_subfolder_docs_exist(tmp_path):
    """delete_folder must return False when documents exist in subfolders."""
    store = LocalDocumentStore(tmp_path)
    store.save_document(session_id="sess1", name="Rules", content="data", folder="rules/combat")
    result = store.delete_folder("sess1", "rules")
    assert result is False


def test_delete_folder_succeeds_when_empty(tmp_path):
    """delete_folder should return True and remove the folder when it contains no docs."""
    store = LocalDocumentStore(tmp_path)
    store.create_folder("sess1", "temp")
    result = store.delete_folder("sess1", "temp")
    assert result is True
    assert "temp" not in store.list_folders("sess1")


def test_move_document_updates_folder(tmp_path):
    """move_document should update the doc's folder field in persisted metadata."""
    store = LocalDocumentStore(tmp_path)
    doc = store.save_document(session_id="sess1", name="Map", content="img", folder="")
    assert doc.folder == ""
    moved = store.move_document("sess1", doc.id, "maps/world")
    assert moved is not None
    assert moved.folder == "maps/world"
    # verify persistence
    listed = store.list_documents("sess1")
    assert listed[0].folder == "maps/world"


def test_move_document_unknown_id_returns_none(tmp_path):
    """move_document should return None for an unknown document id."""
    store = LocalDocumentStore(tmp_path)
    result = store.move_document("sess1", "nonexistent", "folder")
    assert result is None


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

