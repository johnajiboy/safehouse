import pytest
from fastapi.testclient import TestClient

from safehome import auth, store
from safehome.api import app

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def officer(monkeypatch):
    monkeypatch.setattr(auth, "_failures", {})
    auth.add_officer("jo", PASSWORD)


def signed_in():
    client = TestClient(app)
    assert client.post("/api/login", json={"username": "jo", "password": PASSWORD}).status_code == 200
    return client


@pytest.mark.parametrize("path", ["/api/plan", "/api/log", "/api/cases/SH-3001", "/api/repairers", "/api/me"])
def test_officer_apis_need_a_sign_in(path):
    response = TestClient(app).get(path)
    assert response.status_code == 401


def test_officer_actions_need_a_sign_in():
    client = TestClient(app)
    assert client.post("/api/demo/reset").status_code == 401
    assert client.post("/api/settings/inspectors", json={"inspectors": 5}).status_code == 401


@pytest.mark.parametrize("path", ["/dashboard.html", "/dashboard", "/app.js", "/./dashboard.html", "/%64ashboard.html"])
def test_dashboard_redirects_to_sign_in(path):
    response = TestClient(app).get(path, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login.html"


@pytest.mark.parametrize("path", ["/", "/report.html", "/login.html", "/styles.css", "/api/areas"])
def test_tenant_pages_stay_public(path):
    assert TestClient(app).get(path).status_code == 200


def test_tenants_can_report_without_signing_in():
    report = {"text": "Mould in the bathroom", "address": "2 Test Street", "area": "Linthorpe", "contact": "07700 900123"}
    assert TestClient(app).post("/api/tenant/reports", json=report).status_code == 200


def test_signed_in_officer_can_use_the_dashboard():
    client = signed_in()
    assert client.get("/api/plan").status_code == 200
    assert client.get("/dashboard.html").status_code == 200
    assert client.get("/api/me").json() == {"officer": "jo", "demo": False}


def test_wrong_password_is_refused():
    response = TestClient(app).post("/api/login", json={"username": "jo", "password": "wrong password"})
    assert response.status_code == 401


def test_sign_out_ends_the_session():
    client = signed_in()
    client.post("/api/logout")
    assert client.get("/api/plan").status_code == 401


def test_repeated_wrong_passwords_are_locked_out():
    client = TestClient(app)
    for _ in range(auth.MAX_FAILURES):
        client.post("/api/login", json={"username": "jo", "password": "wrong password"})
    response = client.post("/api/login", json={"username": "jo", "password": PASSWORD})
    assert response.status_code == 429


def test_passwords_and_tokens_are_stored_hashed():
    token = auth.sign_in("jo", PASSWORD)
    with store.connect() as db:
        stored = db.execute("SELECT password_hash FROM officers").fetchone()[0]
        sessions = [r[0] for r in db.execute("SELECT token_hash FROM sessions")]
    assert PASSWORD not in stored and stored.startswith("scrypt$")
    assert token not in sessions


def test_short_passwords_are_refused():
    with pytest.raises(ValueError):
        auth.add_officer("sam", "short")
