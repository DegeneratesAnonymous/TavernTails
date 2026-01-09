from server.storage.documents import LocalDocumentStore


def test_local_store_round_trip(tmp_path):
    store = LocalDocumentStore(tmp_path)
    created = store.save_document(session_id="sess1", name="Guide", content="Hello DM")
    assert created.id and created.session_id == "sess1"
    assert created.filename.endswith('.txt')
    listed = store.list_documents("sess1")
    assert len(listed) == 1
    assert listed[0].name == "Guide"
    assert listed[0].filename.endswith('.txt')
    assert listed[0].size == len("Hello DM".encode("utf-8"))
    meta, content = store.read_document("sess1", created.id)
    assert meta.id == created.id
    assert content == "Hello DM"
    deleted = store.delete_document("sess1", created.id)
    assert deleted is True
    assert store.list_documents("sess1") == []
