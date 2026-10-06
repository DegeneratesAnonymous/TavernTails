from server import steward_llm


def test_steward_payload_forwards_temperature_and_scope_model(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL_TAVERNTAILS_NARRATIVE", raising=False)
    payload = steward_llm._steward_payload([{"role": "user", "content": "hi"}], "taverntails_narrative", 600, 0.7, 120)
    assert payload["temperature"] == 0.7
    assert payload["task_scope"] == "taverntails_narrative"
    assert payload["timeout"] == 90
    assert "model" not in payload  # Steward picks the model unless TavernTails overrides it

    monkeypatch.setenv("OLLAMA_MODEL_TAVERNTAILS_NARRATIVE", "gemma3:12b")
    assert steward_llm._steward_payload([], "taverntails_narrative", 600, 0.7, 120)["model"] == "gemma3:12b"
