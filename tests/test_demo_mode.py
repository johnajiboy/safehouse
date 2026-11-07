import pytest
from fastapi.testclient import TestClient

from safehome import auth, config
from safehome.api import app

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def officer(monkeypatch):
    monkeypatch.setattr(auth, "_failures", {})
    auth.add_officer("jo", PASSWORD)


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", True)


def login(client, username, password):
    return client.post("/api/login", json={"username": username, "password": password})


def test_demo_mode_is_off_by_default():
    client = TestClient(app)
    assert client.get("/api/demo-mode").json() == {"demo": False}
    assert client.post("/api/login/demo").status_code == 404
    assert client.get("/api/plan").status_code == 401


def test_demo_button_signs_in_as_demo_officer(demo_on):
    client = TestClient(app)
    assert client.get("/api/demo-mode").json() == {"demo": True}
    assert client.post("/api/login/demo").status_code == 200
    assert client.get("/api/me").json() == {"officer": "demo", "demo": True}
    assert client.get("/api/plan").status_code == 200


def test_real_officers_are_not_labelled_demo(demo_on):
    client = TestClient(app)
    login(client, "jo", PASSWORD)
    assert client.get("/api/me").json() == {"officer": "jo", "demo": False}


@pytest.mark.parametrize("demo", [False, True])
def test_wrong_passwords_are_always_rejected(monkeypatch, demo):
    monkeypatch.setattr(config, "DEMO_MODE", demo)
    client = TestClient(app)
    assert login(client, "jo", "wrong password").status_code == 401
    assert login(client, "demo", "").status_code == 422
    assert login(client, "demo", "anything at all").status_code == 401
    assert client.get("/api/plan").status_code == 401


def test_demo_sessions_end_when_demo_mode_is_turned_off(monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", True)
    client = TestClient(app)
    client.post("/api/login/demo")
    monkeypatch.setattr(config, "DEMO_MODE", False)
    assert client.get("/api/plan").status_code == 401


def test_demo_name_is_reserved():
    with pytest.raises(ValueError):
        auth.add_officer("demo", "a long enough password")
