import os
import sqlite3
from contextlib import closing
from pathlib import Path

from .models import TicketCreate


DB_PATH = Path(
    os.environ.get("QUEUEGUARD_DB_PATH", Path(__file__).resolve().parents[1] / "queueguard.db")
)
_TICKET_FIELDS = "id, title, priority_score, priority_label, workflow_status, evidence_status, reasoning"


def init_db() -> None:
    with closing(sqlite3.connect(DB_PATH)) as connection, connection:
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
                reasoning TEXT NOT NULL
            )
            """
        )


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
            RETURNING {_TICKET_FIELDS}
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
