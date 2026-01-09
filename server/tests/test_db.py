from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

import server.db as db


def setup_module(module):
    # Use an in-memory SQLite DB for tests
    db.engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db.create_db_and_tables()


def test_create_and_authenticate_user():
    user = db.create_user(email="test@example.local", password="secret", username="tester", profile={"name": "tester"})
    assert user.email == "test@example.local"
    # can authenticate with email
    found = db.authenticate_user("test@example.local", "secret")
    assert found is not None


def test_verify_and_beyond20_domains():
    # verify_user should fail with wrong token
    user = db.get_user_by_identifier("test@example.local")
    assert user is not None
    assert not db.verify_user("test@example.local", "bad-token")
    # verify with real token
    token = user.verification_token
    assert token
    assert db.verify_user("test@example.local", token)
    # set/get beyond20 domains
    domains = ["https://a.example", "https://b.example/path"]
    saved = db.set_beyond20_domains_for("test@example.local", domains)
    assert saved == domains
    got = db.get_beyond20_domains_for("test@example.local")
    assert got == domains
