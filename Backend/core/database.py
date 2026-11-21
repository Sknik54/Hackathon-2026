import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from dotenv import load_dotenv

from .models import TicketCreate


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env", override=False)
DB_PATH = Path(
    os.getenv("QUEUEGUARD_DB_PATH") or os.getenv("QUEUEGUARD_TICKETS_DB")
    or BACKEND_DIR / "queueguard.db"
).expanduser().resolve()
_TICKET_FIELDS = "id, title, priority_score, priority_label, workflow_status, evidence_status, reasoning"
_ANALYSIS_INPUT = "id, reporter, title, description, reported_priority, created_at, analysis_version"


def init_db() -> None:
    with closing(sqlite3.connect(DB_PATH)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY,
                reporter TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                reported_priority TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                priority_score INTEGER NOT NULL CHECK (priority_score BETWEEN 0 AND 100),
                priority_label TEXT NOT NULL,
                workflow_status TEXT NOT NULL,
                evidence_status TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                analysis_version INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        columns = {column[1] for column in connection.execute("PRAGMA table_info(tickets)")}
        if "analysis_version" not in columns:
            connection.execute("ALTER TABLE tickets ADD COLUMN analysis_version INTEGER NOT NULL DEFAULT 0")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                event_type TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
    os.environ["QUEUEGUARD_TICKETS_DB"] = str(DB_PATH.resolve())


def insert_ticket(
    ticket: TicketCreate,
    *,
    priority_score: int,
    priority_label: str,
    workflow_status: str,
    evidence_status: str,
    reasoning: str,
) -> dict:
    with closing(sqlite3.connect(DB_PATH)) as connection, connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            f"""
            INSERT INTO tickets (
                reporter, title, description, reported_priority,
                priority_score, priority_label, workflow_status, evidence_status, reasoning
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING {_ANALYSIS_INPUT}
            """,
            (
                ticket.reporter,
                ticket.title,
                ticket.description,
                ticket.reported_priority,
                priority_score,
                priority_label,
                workflow_status,
                evidence_status,
                reasoning,
            ),
        ).fetchone()
        _insert_audit(connection, row["id"], "created", "Ticket gespeichert. Analyse ausstehend.")
    return dict(row)


def begin_reanalysis(ticket_id: int) -> dict | None:
    with closing(sqlite3.connect(DB_PATH)) as connection, connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            f"""
            UPDATE tickets SET analysis_version = analysis_version + 1
            WHERE id = ?
            RETURNING {_ANALYSIS_INPUT}
            """,
            (ticket_id,),
        ).fetchone()
        if row is not None:
            _insert_audit(connection, ticket_id, "reanalysis_started", "Neubewertung gestartet.")
    return dict(row) if row is not None else None


def update_ticket_result(
    ticket_id: int,
    analysis_version: int,
    *,
    priority_score: int,
    priority_label: str,
    workflow_status: str,
    evidence_status: str,
    reasoning: str,
    event_type: str,
    audit_detail: str,
) -> dict:
    with closing(sqlite3.connect(DB_PATH)) as connection, connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            f"""
            UPDATE tickets
            SET priority_score = ?, priority_label = ?, workflow_status = ?,
                evidence_status = ?, reasoning = ?
            WHERE id = ? AND analysis_version = ?
            RETURNING {_TICKET_FIELDS}
            """,
            (priority_score, priority_label, workflow_status, evidence_status, reasoning,
             ticket_id, analysis_version),
        ).fetchone()
        if row is not None:
            _insert_audit(connection, ticket_id, event_type, audit_detail)
        else:
            row = connection.execute(
                f"SELECT {_TICKET_FIELDS} FROM tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
    return dict(row)


def list_tickets() -> list[dict]:
    with closing(sqlite3.connect(DB_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT {_TICKET_FIELDS}
            FROM tickets
            ORDER BY priority_score DESC, created_at ASC, id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _insert_audit(connection, ticket_id: int | None, event_type: str, detail: str) -> None:
    connection.execute(
        "INSERT INTO audit_events (ticket_id, event_type, detail) VALUES (?, ?, ?)",
        (ticket_id, event_type, detail),
    )


@contextmanager
def audit_monitoring_change(detail: str):
    with closing(sqlite3.connect(DB_PATH)) as connection, connection:
        _insert_audit(connection, None, "monitoring_updated", detail)
        yield


def list_audit() -> list[dict]:
    with closing(sqlite3.connect(DB_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT id, ticket_id, event_type, detail, created_at FROM audit_events ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]
