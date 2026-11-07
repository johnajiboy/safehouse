import sqlite3

import pytest
from fastapi.testclient import TestClient

from safehome import auth, config, service, store
from safehome.api import app


@pytest.fixture(autouse=True)
def officers(monkeypatch):
    monkeypatch.setattr(auth, "_failures", {})
    auth.add_officer("jo", "jo's test password")
    auth.add_officer("sam", "sam's test password")


def signed_in(name):
    client = TestClient(app)
    client.post("/api/login", json={"username": name, "password": f"{name}'s test password"})
    return client


def entries(ref):
    return [e for e in store.read_log() if e["case_ref"] == ref]


def test_each_officer_decision_records_who_made_it():
    case = service.submit_report("Mould in the bathroom", "1 Test Street", "Linthorpe")
    signed_in("jo").post(f"/api/cases/{case.ref}/confirm-visit")
    signed_in("sam").post(f"/api/cases/{case.ref}/move", json={"to": "later", "reason": "Officer judgement"})
    officer_entries = {e["action"].split(".")[0]: e["officer"] for e in entries(case.ref) if e["actor"] == "Officer"}
    assert officer_entries == {"Confirmed today's inspection visit": "jo", "Override: moved to later": "sam"}


def test_bookings_record_the_approving_officer():
    case = service.submit_report("Smell of gas in the kitchen", "1 Test Street", "Newport")
    signed_in("jo").post(f"/api/cases/{case.ref}/book", json={"repairer_id": case.recommendation["repairer_id"]})
    booked = next(e for e in entries(case.ref) if e["action"].startswith("Approved and booked"))
    assert booked["officer"] == "jo"


def test_agent_entries_have_no_officer():
    case = service.submit_report("Smell of gas in the kitchen", "1 Test Street", "Newport")
    signed_in("jo").post(f"/api/cases/{case.ref}/confirm-visit")
    assert all(e["officer"] is None for e in entries(case.ref) if e["actor"] != "Officer")


def test_sign_ins_record_the_officer():
    signed_in("sam")
    assert any(e["action"] == "sam signed in" and e["officer"] == "sam" for e in store.read_log())


def test_the_officer_is_forgotten_after_the_request():
    signed_in("jo").post("/api/settings/inspectors", json={"inspectors": 3})
    assert store.current_officer.get() is None
    store.log("Officer", "Something done outside a request")
    assert store.read_log()[0]["officer"] is None


def test_older_databases_gain_the_officer_column(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE log (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,"
                   " case_ref TEXT, action TEXT NOT NULL)")
        db.execute("INSERT INTO log (at, actor, action) VALUES ('2026-11-01T09:00:00', 'Officer', 'Old entry')")
    monkeypatch.setattr(config, "DB_PATH", path)
    store.log("Officer", "New entry", officer="jo")
    log = {e["action"]: e["officer"] for e in store.read_log()}
    assert log == {"Old entry": None, "New entry": "jo"}
