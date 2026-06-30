from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.auth import create_access_token
from server.agents.campaign_interpretation import build_full_contract_package, interpret_imports
from server.agents.scene_validator import validate_campaign_expectations


def _client() -> TestClient:
    return TestClient(main.app)


def _ensure_user(email: str) -> db.User:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return existing
    user = db.create_user(
        email=email,
        password="secret",
        username=email.split("@")[0],
        profile={"name": email.split("@")[0], "email": email},
    )
    assert user.verification_token
    db.verify_user(email, user.verification_token)
    return user


def _auth(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(email)}"}


def test_campaign_creation_generates_persistent_contract_and_session_zero():
    client = _client()
    user = _ensure_user("campaign-contract-owner@example.com")
    assert user.id is not None

    res = client.post(
        "/campaigns",
        headers=_auth(user.email or ""),
        json={
            "name": "Contract Mystery",
            "description": "A mystery-forward campaign where canon matters.",
            "create_session": False,
            "creation_posture": "lore_importer",
            "preferences": {
                "tone": "investigative gothic",
                "setting_summary": "Strict canon, rich description, political intrigue.",
                "mystery_mode": "clue-driven",
            },
            "imported_lore_summary": "The lantern guild controls old road shrines. Do not invent major lore.",
            "player_backstories": [
                {
                    "character_id": "char-yungmin",
                    "character_name": "Yungmin",
                    "text": "Yungmin's mentor vanished after researching a forbidden lantern secret.",
                }
            ],
        },
    )
    assert res.status_code == 201, res.text
    campaign = res.json()["campaign"]
    meta = campaign["metadata_json"]
    contract = meta["campaign_contract"]

    assert meta["campaign_interpretation"]["creation_posture"] == "lore_importer"
    assert meta["campaign_interpretation"]["onboarding_flow"]["mode"] == "lore_review"
    assert contract["canon_policy"]["mode"] == "strict_canon"
    assert contract["description_policy"]["depth"] == "high"
    assert contract["validator_policy"]["require_concrete_clues"] is True
    assert "Yungmin" in meta["session_zero"]["summary"]["characters_with_backstory"]
    assert meta["session_zero_confirmed"] is False
    assert meta["backstory_hooks"][0]["character_id"] == "char-yungmin"
    assert meta["backstory_thread_links"][0]["backstory_hook_id"] == meta["backstory_hooks"][0]["hook_id"]

    contract_res = client.get(f"/campaigns/{campaign['id']}/contract", headers=_auth(user.email or ""))
    assert contract_res.status_code == 200, contract_res.text
    assert contract_res.json()["confirmed"] is False
    assert contract_res.json()["backstory_thread_links"][0]["character_id"] == "char-yungmin"
    returned_contract = contract_res.json()["campaign_contract"]
    assert returned_contract["canon_policy"]["mode"] == "strict_canon"
    assert "CAMPAIGN OUTPUT CONTRACT" in returned_contract["agent_output_contract"]


def test_contract_regenerates_on_settings_and_can_be_confirmed():
    client = _client()
    user = _ensure_user("campaign-contract-settings@example.com")
    assert user.id is not None

    camp = db.create_campaign(owner_id=user.id, name="Contract Settings", description="")
    assert camp.id is not None

    put = client.put(
        f"/campaigns/{camp.id}/settings",
        headers=_auth(user.email or ""),
        json={
            "genre": "fantasy",
            "tone": "political mystery",
            "setting_summary": "Use detailed description and conservative canon.",
            "world_name": "Lanternmark",
            "ruleset": "5e",
            "starting_level": 5,
            "house_rules": "Investigation should offer multiple approaches.",
        },
    )
    assert put.status_code == 200, put.text
    data = put.json()
    assert data["campaign_contract"]["validator_policy"]["reject_single_solution"] is True
    assert data["campaign_contract"]["ui_policy"]["right_panel_default"] == "scene_relevant"

    zero = client.get(f"/campaigns/{camp.id}/session-zero", headers=_auth(user.email or ""))
    assert zero.status_code == 200, zero.text
    assert zero.json()["confirmed"] is False

    confirm = client.post(f"/campaigns/{camp.id}/contract/confirm", headers=_auth(user.email or ""))
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["confirmed"] is True


def test_contract_endpoints_are_forbidden_for_non_owner():
    client = _client()
    owner = _ensure_user("campaign-contract-owner2@example.com")
    other = _ensure_user("campaign-contract-other@example.com")
    assert owner.id is not None

    camp = db.create_campaign(owner_id=owner.id, name="Private Contract", description="")
    assert camp.id is not None

    res = client.get(f"/campaigns/{camp.id}/contract", headers=_auth(other.email or ""))
    assert res.status_code == 403, res.text

    confirm = client.post(f"/campaigns/{camp.id}/contract/confirm", headers=_auth(other.email or ""))
    assert confirm.status_code == 403, confirm.text


def test_campaign_expectation_validator_enforces_contract_policy():
    contract = {
        "canon_policy": {"mode": "strict_canon"},
        "backstory_policy": {"protect_family_content": True},
        "validator_policy": {
            "reject_single_solution": True,
            "require_concrete_clues": True,
            "preserve_unanswered_questions": True,
        },
    }

    result = validate_campaign_expectations(
        "You must ask the mayor. The truth is revealed: the lost mother is murdered.",
        campaign_contract=contract,
        invented_entities=["New capital city"],
    )

    assert result["score"] < 100
    assert "single_solution" in result["agency_issues"]
    assert "missing_concrete_clue" in result["failed_expectations"]
    assert result["canon_violations"]
    assert result["backstory_boundary_violations"]


def test_quick_start_creates_campaign_contract():
    """Minimal campaign creation (Quick Start posture) still produces a full contract."""
    client = _client()
    user = _ensure_user("campaign-quick-start@example.com")
    assert user.id is not None

    res = client.post(
        "/campaigns",
        headers=_auth(user.email or ""),
        json={
            "name": "Quick Adventure",
            "description": "",
            "create_session": False,
            "creation_posture": "player_fast_start",
            "preferences": {"genre": "fantasy", "tone": "balanced"},
        },
    )
    assert res.status_code == 201, res.text
    campaign = res.json()["campaign"]
    meta = campaign["metadata_json"]

    # Contract must be generated even with minimal input
    contract = meta.get("campaign_contract", {})
    assert contract, "Expected campaign_contract to be generated for quick start"
    assert contract.get("campaign_id") == str(campaign["id"])
    assert contract.get("campaign_dna"), "Expected campaign_dna in contract"
    assert contract.get("agent_output_contract"), "Expected agent_output_contract text"

    # Posture must be inferred correctly
    interp = meta.get("campaign_interpretation", {})
    assert interp.get("creation_posture") == "player_fast_start"

    # Session Zero should exist (not yet confirmed)
    assert meta.get("session_zero"), "Expected session_zero to be populated"
    assert meta.get("session_zero_confirmed") is False

    # Seeds endpoint should work without auth
    seeds_res = client.get("/campaigns/seeds")
    assert seeds_res.status_code == 200, seeds_res.text
    seeds = seeds_res.json()["seeds"]
    assert len(seeds) >= 4
    assert all("id" in s and "title" in s and "emoji" in s for s in seeds)


def test_imported_lore_creates_canon_and_provisional_entities():
    """Rich lore text produces named entities with correct canon status."""
    # Unit-test the interpret_imports function directly for entity extraction
    lore = (
        "NPC: Velara Ashveil, leader of the Obsidian Council.\n"
        "Location: Thornwatch Keep, abandoned fortress on the northern pass.\n"
        "Faction: The Obsidian Council controls all sanctioned magic in the realm.\n"
        "The players will encounter Lord Maldrek at Thornwatch Keep.\n"
        "The Iron Brotherhood Guild opposes the Council."
    )
    result = interpret_imports([lore])

    # Labelled entities must be player_canon
    canon_names = {e["name"] for e in result["canon_sensitive_entities"]}
    assert "Velara Ashveil" in canon_names, f"Expected 'Velara Ashveil' in canon entities, got {canon_names}"
    assert "Thornwatch Keep" in canon_names, f"Expected 'Thornwatch Keep' in canon entities"

    # Inline-mentioned entities should be provisional
    all_names = {e["name"] for e in result["all_named_entities"]}
    assert len(all_names) >= 3, f"Expected at least 3 named entities, got {all_names}"

    # Entity types should be classified correctly
    by_name = {e["name"]: e for e in result["canon_sensitive_entities"]}
    assert by_name.get("Velara Ashveil", {}).get("type") == "npc"
    assert by_name.get("Thornwatch Keep", {}).get("type") == "place"

    # Via API: lore import should surface entities in the contract debug
    client = _client()
    user = _ensure_user("campaign-lore-import@example.com")
    assert user.id is not None

    res = client.post(
        "/campaigns",
        headers=_auth(user.email or ""),
        json={
            "name": "Lore Import Campaign",
            "create_session": False,
            "creation_posture": "lore_importer",
            "imported_lore_summary": lore,
        },
    )
    assert res.status_code == 201, res.text
    meta = res.json()["campaign"]["metadata_json"]
    interp = meta.get("campaign_interpretation", {})
    import_interp = interp.get("import_interpretation", {})
    api_entities = import_interp.get("canon_sensitive_entities", [])
    api_names = {e["name"] for e in api_entities}
    assert "Velara Ashveil" in api_names, f"Expected Velara Ashveil in API-returned entities, got {api_names}"
    contract_names = {e["name"] for e in meta["campaign_contract"].get("player_canon", [])}
    assert "Velara Ashveil" in contract_names


def test_full_contract_promotes_imports_and_backstories_to_agent_contract():
    lore = (
        "NPC: Ilyra Voss, keeper of the sealed archive.\n"
        "Location: Moonfall Academy, safe refuge for exiles.\n"
        "The Argent Order Guild hides a forbidden map. Rumor contradicts the official record."
    )
    package = build_full_contract_package(
        campaign_id="contract-pack",
        campaign_name="Moonfall Intrigue",
        description="Roleplay-heavy slow-burn mystery with strict canon.",
        settings={"creation_posture": "lore_importer", "tone": "investigative"},
        variables={"themes": "political intrigue, secrets"},
        docs=[lore],
        backstories=[
            {
                "character_id": "char-1",
                "player_id": "player-1",
                "character_name": "Seren",
                "text": (
                    "Seren's mentor Alar Venn vanished from Moonfall Academy. "
                    "Seren owes a debt, carries a secret, and has no family danger."
                ),
            }
        ],
    )

    contract = package["campaign_contract"]
    canon_names = {e["name"] for e in contract["player_canon"]}
    provisional_names = {e["name"] for e in contract["provisional_entities"]}

    assert "Ilyra Voss" in canon_names
    assert "Alar Venn" in canon_names
    assert "Argent Order" in provisional_names
    assert contract["backstory_profiles"][0]["private_facts"] == ["protected secret"]
    assert "family_danger" in contract["backstory_profiles"][0]["hard_boundaries"]
    assert any(h["type"] == "mentor_message" for h in contract["backstory_hooks"])
    assert any(h["type"] == "debt_called_in" for h in contract["backstory_hooks"])
    assert contract["backstory_spotlight"]
    assert package["debug"]["user_input"]["backstory_count"] == 1
    assert package["session_zero"]["character_hooks"][0]["unresolved_questions"]


def test_explicit_ui_contract_choices_override_inference():
    package = build_full_contract_package(
        campaign_id="explicit-ui",
        campaign_name="Open Road",
        description="A bright sandbox adventure.",
        settings={
            "creation_posture": "player_fast_start",
            "canon_policy": "strict_canon",
            "ai_creativity_level": "conservative",
            "playstyle_profile": "slow-burn mystery",
        },
        variables={},
        docs=[],
        backstories=[],
    )

    contract = package["campaign_contract"]
    interp = package["campaign_interpretation"]
    assert interp["canon_policy"] == "strict_canon"
    assert interp["ai_creativity_level"] == "conservative"
    assert "investigation" in interp["primary_play_pillars"]
    assert contract["canon_policy"]["mode"] == "strict_canon"
    assert contract["ai_creativity_policy"]["level"] == "conservative"


def test_validator_consumes_player_canon_and_profile_boundaries():
    contract = {
        "canon_policy": {"mode": "guided_canon"},
        "backstory_policy": {"allow_secret_reveals": "with_setup"},
        "validator_policy": {"reject_single_solution": False},
        "player_canon": [{"name": "Ilyra Voss", "type": "npc", "canon_status": "player_canon"}],
        "backstory_profiles": [
            {
                "character_id": "char-1",
                "hard_boundaries": ["family_danger", "identity_retcon"],
                "spotlight_preferences": {"approval_required_for": ["secret_reveal"]},
            }
        ],
    }

    result = validate_campaign_expectations(
        "Ilyra Voss never existed. Your family is in danger, everyone learns your secret, and you were secretly royal.",
        campaign_contract=contract,
    )

    assert any("contradicts_player_canon" in v for v in result["canon_violations"])
    assert "profile_family_danger_requires_permission" in result["backstory_boundary_violations"]
    assert "profile_secret_reveal_requires_permission" in result["backstory_boundary_violations"]
    assert "identity_retcon_forbidden" in result["backstory_boundary_violations"]


def test_session_zero_surfaces_low_confidence_assumptions():
    """Ambiguous campaign setup produces low_confidence_items in Session Zero."""
    client = _client()
    user = _ensure_user("campaign-low-confidence@example.com")
    assert user.id is not None

    # Minimal, ambiguous setup — no genre/tone/posture signal, should trigger low-confidence
    res = client.post(
        "/campaigns",
        headers=_auth(user.email or ""),
        json={
            "name": "Ambiguous Campaign",
            "description": "A campaign.",
            "create_session": False,
            "preferences": {},
        },
    )
    assert res.status_code == 201, res.text
    meta = res.json()["campaign"]["metadata_json"]

    # With no clear signals, posture confidence should be low → low_confidence_items generated
    interp = meta.get("campaign_interpretation", {})
    assert interp.get("confidence", 1.0) < 0.7, (
        f"Expected confidence < 0.7 for ambiguous setup, got {interp.get('confidence')}"
    )
    low_conf = interp.get("low_confidence_items", [])
    assert low_conf, "Expected at least one low_confidence_item for ambiguous campaign"

    # Session Zero should surface those items
    session_zero = meta.get("session_zero", {})
    sz_low_conf = session_zero.get("low_confidence_items", [])
    assert sz_low_conf, "Expected low_confidence_items to be surfaced in session_zero"
    assert session_zero.get("options"), "Expected session_zero to include confirmation options"
    assert "Confirm and Start" in session_zero["options"]
