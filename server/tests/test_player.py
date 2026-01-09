from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

import server.agents.player_clean as player
import server.db as db


def setup_module(module):
    # use in-memory DB for tests and create the tables before starting TestClient
    db.engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db.create_db_and_tables()


app = FastAPI()
app.include_router(player.router)
client = None


def setup_module_after_db(module):
    # create TestClient after DB/tables are ready
    global client
    client = TestClient(app)


setup_module_after_db(None)


def test_signup_verify_login_and_beyond20():
    # signup
    r = client.post("/player/signup", json={"email": "new@local", "password": "pw", "name": "new"})
    assert r.status_code == 200
    data = r.json()
    assert "verification_token" in data
    token = data["verification_token"]
    # verify
    r = client.post("/player/verify-email", json={"email": "new@local", "token": token})
    assert r.status_code == 200 and r.json().get("verified") is True
    # login
    r = client.post("/player/login", json={"email": "new@local", "password": "pw"})
    assert r.status_code == 200 and "profile" in r.json()
    # set beyond20 domains
    r = client.post("/player/beyond20", json={"identifier": "new@local", "domains_text": "https://one.local\nhttps://two.local"})
    assert r.status_code == 200
    assert r.json().get("domains") == ["https://one.local", "https://two.local"]
    # get beyond20
    r = client.get("/player/beyond20", params={"identifier": "new@local"})
    assert r.status_code == 200 and "domains" in r.json()


def test_dndbeyond_text_parse():
    payload = {"text": "Name: Sir Test\nClass: Fighter Level: 3\nRace: Human\nSTR: 16\nDEX: 12\nCON: 14"}
    r = client.post("/player/dndbeyond", json=payload)
    assert r.status_code == 200
    data = r.json().get("dndbeyond_character", {})
    assert data.get("imported") is True
    assert data.get("character", {}).get("name") == "Sir Test"
