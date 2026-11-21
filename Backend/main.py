import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path as RoutePath, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

if __package__:
    from .core import database, policy_engine
    from .core.models import (
        MonitoringChange, MonitoringEvidence, MonitoringSnapshot, ServiceId, TicketCreate,
        TicketResponse,
    )
    from .core.ticket_service import (
        InvalidTicketInput, TicketPolicyDenied, create_and_process_ticket, get_queue_snapshot,
        reanalyze_ticket,
    )
    from .tools import monitoring
else:
    from core import database, policy_engine
    from core.models import (
        MonitoringChange, MonitoringEvidence, MonitoringSnapshot, ServiceId, TicketCreate,
        TicketResponse,
    )
    from core.ticket_service import (
        InvalidTicketInput, TicketPolicyDenied, create_and_process_ticket, get_queue_snapshot,
        reanalyze_ticket,
    )
    from tools import monitoring


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


app = FastAPI(title="QueueGuard AI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
)


@app.exception_handler(TicketPolicyDenied)
async def handle_policy_denial(request: Request, exc: TicketPolicyDenied) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tickets", response_model=list[TicketResponse])
def list_tickets() -> list[dict]:
    return get_queue_snapshot()


@app.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_ticket(ticket: TicketCreate) -> dict:
    try:
        return create_and_process_ticket(**ticket.model_dump())
    except InvalidTicketInput as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/monitoring", response_model=MonitoringSnapshot, response_model_exclude_none=True)
def get_monitoring() -> dict:
    return {"services": [
        monitoring.get_service_status(service_id) for service_id in sorted(monitoring.SERVICE_IDS)
    ]}


@app.post(
    "/demo/monitoring/{service_id}",
    response_model=MonitoringEvidence,
    response_model_exclude_none=True,
)
def update_demo_monitoring(service_id: ServiceId, change: MonitoringChange) -> dict:
    if not policy_engine.authorize_action("ticket_service", "append_audit_event"):
        raise TicketPolicyDenied("Die Ticket-Policy erlaubt dieses Audit-Ereignis nicht.")

    path = monitoring.MONITORING_PATH
    values = change.model_dump()
    detail = (
        f"Simuliertes Monitoring für {service_id} auf {change.status} gesetzt. "
        f"Betroffene Nutzer {change.affected_users}."
    )
    temporary_path = None
    try:
        # A SQLite write transaction serializes the read-modify-write across server workers.
        with database.audit_monitoring_change(detail):
            content = json.loads(path.read_text(encoding="utf-8"))
            content["services"][service_id] = values
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
            ) as output:
                temporary_path = Path(output.name)
                json.dump(content, output, indent=2, ensure_ascii=False)
                output.write("\n")
            temporary_path.replace(path)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="Demo-Monitoring konnte nicht gespeichert werden.") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return {"service_id": service_id, "source": "SIMULATED_MONITORING", **values}


@app.post("/tickets/{ticket_id}/reanalyze", response_model=TicketResponse)
def reanalyze(ticket_id: Annotated[int, RoutePath(ge=1, le=2**63 - 1)]) -> dict:
    ticket = reanalyze_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket wurde nicht gefunden.")
    return ticket


@app.get("/audit")
def get_audit() -> list[dict]:
    return database.list_audit()
