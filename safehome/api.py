"""Web API and dashboard server.

Run:  uvicorn safehome.api:app --reload
Then open http://localhost:8000
"""
from __future__ import annotations

import posixpath
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, config, messages, seed, service, simulation, store
from .hazards import EMERGENCY, VULNERABILITY_TYPES

@asynccontextmanager
async def lifespan(app: FastAPI):
    auth.ensure_default_officer()
    yield


app = FastAPI(title="SafeHome", lifespan=lifespan)

SESSION_COOKIE = "safehome_session"
# Everything under /api/ needs an officer to be signed in, except these.
PUBLIC_API = {"/api/login", "/api/login/demo", "/api/demo-mode", "/api/tenant/reports", "/api/areas"}
OFFICER_PAGES = {"/dashboard", "/dashboard.html", "/app.js"}


@app.middleware("http")
async def require_officer(request: Request, call_next):
    """Tenants can reach the intro and report form; everything officers use needs a sign-in."""
    path = posixpath.normpath(unquote(request.url.path))
    is_api = path == "/api" or path.startswith("/api/")
    protected = (is_api and path not in PUBLIC_API) or path in OFFICER_PAGES
    if protected:
        officer = auth.officer_for(request.cookies.get(SESSION_COOKIE))
        if officer is None:
            if is_api:
                return JSONResponse({"detail": "Please sign in"}, status_code=401)
            return RedirectResponse("/login.html", status_code=303)
        request.state.officer = officer
    return await call_next(request)


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


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


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


@app.post("/api/login")
def login(body: LoginIn, request: Request, response: Response):
    try:
        token = auth.sign_in(body.username, body.password)
    except auth.TooManyAttempts as error:
        raise HTTPException(429, str(error))
    if token is None:
        raise HTTPException(401, "Wrong username or password")
    set_session(response, request, token)
    return {"officer": body.username}


@app.get("/api/demo-mode")
def demo_mode():
    return {"demo": config.DEMO_MODE}


@app.post("/api/login/demo")
def login_demo(request: Request, response: Response):
    token = auth.sign_in_demo()
    if token is None:
        raise HTTPException(404, "Demo mode is off")
    set_session(response, request, token)
    return {"officer": auth.DEMO_OFFICER}


def set_session(response: Response, request: Request, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, max_age=auth.SESSION_HOURS * 3600, httponly=True,
                        samesite="strict", secure=request.url.scheme == "https")


@app.post("/api/logout")
def logout(request: Request, response: Response):
    auth.sign_out(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return {"officer": request.state.officer, "demo": auth.is_demo(request.state.officer)}


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
