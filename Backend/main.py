from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

if __package__:
    from .core.database import init_db
    from .core.models import TicketCreate, TicketResponse
    from .core.ticket_service import create_and_process_ticket, get_queue_snapshot
else:
    from core.database import init_db
    from core.models import TicketCreate, TicketResponse
    from core.ticket_service import create_and_process_ticket, get_queue_snapshot


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="QueueGuard AI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tickets", response_model=list[TicketResponse])
def list_tickets() -> list[dict]:
    return get_queue_snapshot()


@app.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_ticket(ticket: TicketCreate) -> dict:
    return create_and_process_ticket(**ticket.model_dump())
