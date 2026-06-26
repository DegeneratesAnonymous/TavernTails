"""Shared test configuration.

Two test tiers:
  - Structural tests (default): LLM is stubbed. Fast, zero tokens, safe for CI.
    These verify routing, persistence, auth, response shape.

  - Quality tests (opt-in): real LLM. Run with --llm flag or mark with
    @pytest.mark.llm. These verify prompt construction and output coherence.
    They cost tokens and are slower — run them before shipping or after
    changing prompts, not on every commit.

Usage:
  pytest                      # fast run, all structural tests
  pytest --llm                # include real-LLM quality tests
  pytest -m llm               # only quality tests
"""

import json
import os

import pytest

os.environ.setdefault("TAVERNTAILS_SEED_DEV_USER", "1")

# ---------------------------------------------------------------------------
# CLI option
# ---------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--llm",
        action="store_true",
        default=False,
        help="Run tests marked with @pytest.mark.llm (uses real LLM, costs tokens).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "llm: mark test as requiring a live LLM (skipped unless --llm is passed).",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    if not config.getoption("--llm"):
        skip = pytest.mark.skip(reason="requires --llm flag to run (uses real LLM tokens)")
        for item in items:
            if item.get_closest_marker("llm"):
                item.add_marker(skip)


# ---------------------------------------------------------------------------
# LLM stub fixture (structural tests)
# ---------------------------------------------------------------------------

# Realistic stub that satisfies narrative JSON parsing.
# Scene/analysis agents have keyword fallbacks so the wrong shape is fine there.
_STUB_NARRATIVE = json.dumps({
    "narrative": "The torchlight flickers as shadows dance across ancient stone walls.",
    "prompt": "What do you do next?",
})


@pytest.fixture(autouse=True)
def stub_llm(request, monkeypatch):
    """Stub all LLM calls unless the test is marked @pytest.mark.llm.

    Tests marked with @pytest.mark.llm skip this fixture and hit the real LLM.
    Other tests can still override per-test with their own monkeypatch.setattr
    call — the last setattr wins.
    """
    if request.node.get_closest_marker("llm"):
        # Quality test — let it talk to the real LLM
        yield
        return

    _stub = lambda *a, **kw: _STUB_NARRATIVE  # noqa: E731

    # Patch the canonical module (covers lazy-import callers)
    import server.steward_llm as steward_llm_module
    monkeypatch.setattr(steward_llm_module, "chat_complete", _stub)

    # Patch modules that imported chat_complete at module level
    try:
        from server.agents import narrative as _narrative
        monkeypatch.setattr(_narrative, "chat_complete", _stub)
    except Exception:
        pass
    try:
        from server.agents import scene as _scene
        monkeypatch.setattr(_scene, "chat_complete", _stub)
    except Exception:
        pass
    try:
        from server.agents import generate as _generate
        monkeypatch.setattr(_generate, "chat_complete", _stub)
    except Exception:
        pass

    yield
