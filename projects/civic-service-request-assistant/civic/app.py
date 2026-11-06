import secrets
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from civic.assistant import Assistant
from civic.graph import GraphExport
from civic.settings import CONFIG, HANDBOOK, Settings
from civic.store import Conflict, Store

STATIC = Path(__file__).parent / "static"


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Intake(Body):
    service: str
    location: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=2000)
    contact: str = Field(default="", max_length=200)

    @field_validator("service")
    @classmethod
    def valid_service(cls, value):
        if value not in {s["id"] for s in CONFIG["services"]}:
            raise ValueError("Choose a supported service")
        return value


class Transition(Body):
    status: Literal["approved", "rejected", "in_progress", "resolved"]
    version: int = Field(ge=1)
    note: str = Field(min_length=3, max_length=1000)


class Question(Body):
    question: str = Field(min_length=5, max_length=500)


class Receipt(Body):
    receipt: str = Field(min_length=32, max_length=100)


def create_app(settings=None, model_client=None, graph_client=None):
    settings = settings or Settings()
    store = Store(settings.db)
    assistant = Assistant(settings, model_client)
    exporter = GraphExport(settings, store, graph_client)
    app = FastAPI(title="Northfield service desk", docs_url=None, redoc_url=None)
    app.state.store = store

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, error):
        # Default validation errors echo raw input, which can contain resident details.
        return JSONResponse(
            {"detail": "Check the required fields and their length limits."}, status_code=422
        )

    @app.middleware("http")
    async def security(request: Request, call_next):
        # No cookie authentication or CORS; reject browser cross-origin writes before side effects.
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD"}
            and origin
            and origin != str(request.base_url).rstrip("/")
        ):
            return JSONResponse({"detail": "Cross-origin writes are disabled"}, status_code=403)
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
                "style-src 'self'; "
                "connect-src 'self'; frame-ancestors 'none'; form-action 'self'",
            }
        )
        return response

    def staff(authorization: Annotated[str | None, Header()] = None):
        if not settings.staff_token:
            raise HTTPException(503, "Set CIVIC_STAFF_TOKEN to enable the staff desk")
        if not secrets.compare_digest(authorization or "", f"Bearer {settings.staff_token}"):
            raise HTTPException(401, "Enter the staff access token")

    def found(request_id):
        row = store.get(request_id)
        if not row:
            raise HTTPException(404, "Request not found")
        return row

    @app.get("/")
    def home():
        return FileResponse(STATIC / "index.html")

    @app.get("/staff")
    def dashboard():
        return FileResponse(STATIC / "staff.html")

    @app.get("/api/config")
    def config():
        return CONFIG

    @app.get("/api/guides")
    def guides():
        return HANDBOOK

    @app.post("/api/requests", status_code=201)
    def submit(body: Intake):
        row = store.create(body)
        return {k: row[k] for k in ("id", "receipt", "status", "created_at")}

    @app.post("/api/track")
    def track(body: Receipt):
        row = store.track(body.receipt)
        if not row:
            raise HTTPException(404, "Receipt not found. Check your saved receipt.")
        return row

    @app.post("/api/faq")
    def faq(body: Question):
        return assistant.answer(body.question)

    @app.get("/api/staff/requests", dependencies=[Depends(staff)])
    def queue(status: str | None = None, service: str | None = None):
        return [
            {k: v for k, v in row.items() if k != "receipt"} for row in store.queue(status, service)
        ]

    @app.get("/api/staff/requests/{request_id}", dependencies=[Depends(staff)])
    def detail(request_id: str):
        row = found(request_id)
        row.pop("receipt")
        return {**row, "events": store.events(request_id)}

    @app.post("/api/staff/requests/{request_id}/status", dependencies=[Depends(staff)])
    def transition(request_id: str, body: Transition):
        try:
            store.transition(request_id, body)
        except KeyError:
            raise HTTPException(404, "Request not found") from None
        except Conflict as error:
            raise HTTPException(409, str(error)) from None
        return detail(request_id)

    @app.get("/api/staff/requests/{request_id}/export", dependencies=[Depends(staff)])
    def preview(request_id: str):
        from civic.privacy import export_fields

        return {"fields": export_fields(found(request_id))}

    @app.post("/api/staff/requests/{request_id}/export", dependencies=[Depends(staff)])
    def export(request_id: str):
        try:
            return exporter.export(request_id)
        except KeyError:
            raise HTTPException(404, "Request not found") from None
        except (httpx.HTTPError, ValueError, TypeError):
            raise HTTPException(
                502,
                "Export failed. Check the local Graph sandbox; do not "
                "repeat an uncertain first export without checking its list.",
            ) from None

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
