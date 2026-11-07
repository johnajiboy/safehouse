import pytest
from fastapi.testclient import TestClient

from safehome import auth, config, store
from safehome.api import app

PASSWORD = "a test-only password"


def officers():
    with store.connect() as db:
        return {r["username"]: r["password_hash"] for r in db.execute("SELECT * FROM officers")}


@pytest.fixture
def env_officer(monkeypatch):
    monkeypatch.setattr(config, "OFFICER_USERNAME", "lead")
    monkeypatch.setattr(config, "OFFICER_PASSWORD", PASSWORD)


def test_default_officer_is_created_at_start_up_and_can_sign_in(env_officer):
    with TestClient(app) as client:  # entering the client runs the app's start-up
        stored = officers()["lead"]
        assert PASSWORD not in stored and stored.startswith("scrypt$")
        assert client.post("/api/login", json={"username": "lead", "password": PASSWORD}).status_code == 200
        assert client.post("/api/login", json={"username": "lead", "password": "wrong password"}).status_code == 401


def test_default_officer_is_skipped_when_accounts_already_exist(env_officer):
    auth.add_officer("jo", "another test password")
    assert auth.ensure_default_officer() is False
    assert set(officers()) == {"jo"}


def test_nothing_is_created_when_env_is_not_set():
    assert auth.ensure_default_officer() is False
    assert officers() == {}


@pytest.mark.parametrize("username, password", [("lead", "short"), ("demo", PASSWORD)])
def test_bad_default_officer_is_refused_without_crashing(monkeypatch, username, password):
    monkeypatch.setattr(config, "OFFICER_USERNAME", username)
    monkeypatch.setattr(config, "OFFICER_PASSWORD", password)
    assert auth.ensure_default_officer() is False
    assert officers() == {}
