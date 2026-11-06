"""Web API and dashboard server.

Run:  uvicorn safehome.api:app --reload
Then open http://localhost:8000
"""
from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, messages, seed, service, simulation, store
from .hazards import EMERGENCY, VULNERABILITY_TYPES

app = FastAPI(title="SafeHome")


class ReportIn(BaseModel):
    text: str = Field(min_length=5, max_length=4000)
    address: str = Field(min_length=2, max_length=200)
    area: str = ""
    contact: str = ""


class TenantReportIn(BaseModel):
    text: str = Field(min_length=5, max_length=4000)
    needs: list[str] = Field(default_factory=list, max_length=len(VULNERABILITY_TYPES))
    address: str = Field(min_length=2, max_length=200)
    area: str = ""
    contact: str = Field(min_length=3, max_length=200)


class MoveIn(BaseModel):
    to: str
    reason: str
    note: str = ""


class ReasonIn(BaseModel):
    reason: str
    note: str = ""


class BookIn(BaseModel):
    repairer_id: str


class MessageIn(BaseModel):
    body: str | None = None


class InspectorsIn(BaseModel):
    inspectors: int


def run(action, *args):
    """Call a service function and turn its errors into HTTP responses."""
    try:
        return action(*args)
    except service.NotFound as error:
        raise HTTPException(404, str(error))
    except service.NotAllowed as error:
        raise HTTPException(400, str(error))


@app.get("/api/plan")
def get_plan():
    return service.plan_view(datetime.now())


@app.post("/api/reports")
def post_report(report: ReportIn):
    case = service.submit_report(report.text, report.address, report.area, report.contact)
    return service.case_view(case.ref, datetime.now())


@app.post("/api/tenant/reports")
def post_tenant_report(report: TenantReportIn):
    """The public form. Tenants get their reference and any safety advice, never the case file."""
    if any(n not in VULNERABILITY_TYPES for n in report.needs):
        raise HTTPException(422, "Unknown household need")
    if report.area and report.area not in service.load_areas():
        raise HTTPException(422, "Unknown area")
    case = service.submit_report(report.text, report.address, report.area, report.contact, needs=report.needs)
    return {
        "ref": case.ref,
        "emergency": case.level == EMERGENCY,
        "safety_advice": messages.safety_message(case),
    }


@app.get("/api/areas")
def get_areas():
    return sorted(service.load_areas())


@app.get("/api/cases/{ref}")
def get_case(ref: str):
    return run(service.case_view, ref, datetime.now())


@app.post("/api/cases/{ref}/confirm-visit")
def confirm_visit(ref: str):
    run(service.confirm_visit, ref)
    return {"ok": True}


@app.post("/api/cases/{ref}/move")
def move_case(ref: str, body: MoveIn):
    run(service.move, ref, body.to, body.reason, body.note)
    return {"ok": True}


@app.post("/api/cases/{ref}/stage")
def record_stage(ref: str):
    return {"recorded": run(service.record_stage, ref, datetime.now())}


@app.get("/api/cases/{ref}/repairers")
def repairer_options(ref: str):
    return run(service.repairer_options, ref, datetime.now())


@app.post("/api/cases/{ref}/book")
def book(ref: str, body: BookIn):
    return {"booked": run(service.book, ref, body.repairer_id, datetime.now())}


@app.post("/api/cases/{ref}/cancel-booking")
def cancel_booking(ref: str, body: ReasonIn):
    run(service.cancel_booking, ref, body.reason, body.note)
    return {"ok": True}


@app.post("/api/messages/{message_id}/approve")
def approve_message(message_id: int, body: MessageIn):
    run(service.approve_message, message_id, body.body)
    return {"ok": True}


@app.post("/api/settings/inspectors")
def set_inspectors(body: InspectorsIn):
    run(service.set_inspectors, body.inspectors)
    return {"ok": True}


@app.post("/api/clusters/{key}/survey")
def toggle_survey(key: str):
    return {"grouped": run(service.toggle_survey, key, datetime.now())}


@app.get("/api/repairers")
def get_repairers():
    return service.repairers_view()


@app.get("/api/log")
def get_log():
    return store.read_log()


@app.get("/api/simulation")
def get_simulation(inspectors: int = 2, cold_snap: bool = False):
    return simulation.compare(inspectors, cold_snap)


@app.post("/api/demo/reset")
def reset_demo():
    seed.load_sample_data()
    return {"ok": True}


@app.get("/")
def intro():
    return FileResponse(config.WEB_DIR / "intro.html")


app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
