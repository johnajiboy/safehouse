from fastapi.testclient import TestClient

from safehome import store
from safehome.api import app

client = TestClient(app)


def send(**fields):
    report = {"text": "Mould in the bathroom", "address": "2 Test Street", "area": "Linthorpe",
              "contact": "07700 900123", **fields}
    return client.post("/api/tenant/reports", json=report)


def test_tenant_sees_only_reference_emergency_and_advice():
    response = send(text="Strong smell of gas in the kitchen")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"ref", "emergency", "safety_advice"}
    assert body["emergency"] is True
    assert "0800 111 999" in body["safety_advice"]


def test_non_emergency_has_no_safety_advice():
    body = send().json()
    assert body["emergency"] is False and body["safety_advice"] is None


def test_needs_are_saved_as_vulnerabilities():
    ref = send(needs=["Young child", "Mobility need"]).json()["ref"]
    case = store.get_case(ref)
    assert case.extraction.vulnerability == ["Young child", "Mobility need"]
    assert case.stated_needs == ["Young child", "Mobility need"]


def test_unknown_needs_and_areas_are_refused():
    assert send(needs=["Not a need"]).status_code == 422
    assert send(area="Atlantis").status_code == 422
    assert store.all_cases() == []
