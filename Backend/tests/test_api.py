import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from Backend.core import database
from Backend.main import app


class TicketApiTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.db_path = Path(directory) / "test.db"
        self.enterContext(patch.object(database, "DB_PATH", self.db_path))

    def test_health_and_empty_queue(self):
        with TestClient(app) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json(), {"status": "ok"})

            queue = client.get("/tickets")
            self.assertEqual(queue.status_code, 200)
            self.assertEqual(queue.json(), [])

    def test_post_contract_and_persistence_across_startups(self):
        payload = {
            "reporter": "Anna",
            "title": "Login kaputt",
            "description": "Niemand kann sich anmelden",
            "reported_priority": "high",
        }
        with TestClient(app) as client:
            response = client.post("/tickets", json=payload)
            self.assertEqual(response.status_code, 201)
            ticket = response.json()
            self.assertTrue(ticket["reasoning"].startswith("Mock-Analyse."))
            self.assertEqual(
                ticket,
                {
                    "id": 1,
                    "title": "Login kaputt",
                    "priority_score": 69,
                    "priority_label": "High",
                    "workflow_status": "needs_review",
                    "evidence_status": "unverified",
                    "reasoning": ticket["reasoning"],
                },
            )

        with TestClient(app) as restarted_client:
            self.assertEqual(restarted_client.get("/tickets").json(), [ticket])

        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                "SELECT reporter, title, description, reported_priority FROM tickets"
            ).fetchone()
        self.assertEqual(row, tuple(payload.values()))

    def test_queue_orders_by_score_and_then_creation_time(self):
        with TestClient(app) as client:
            printer = self.post_ticket(client, "Drucker leer", "Kein Papier", "critical")
            login = self.post_ticket(client, "Login", "Ich kann mich nicht anmelden", "low")
            second_login = self.post_ticket(client, "Login", "Anmeldung fehlgeschlagen", "high")

            self.assertEqual(printer["priority_label"], "Low")
            self.assertEqual(login["workflow_status"], "open")
            self.assertEqual(login["priority_score"], second_login["priority_score"])
            self.assertEqual(client.get("/tickets").json(), [login, second_login, printer])

            with closing(sqlite3.connect(self.db_path)) as connection, connection:
                connection.execute(
                    "UPDATE tickets SET created_at = ? WHERE id = ?",
                    ("2000-01-01T00:00:00.000Z", second_login["id"]),
                )
            self.assertEqual(client.get("/tickets").json(), [second_login, login, printer])

    def test_invalid_requests_do_not_create_tickets(self):
        payload = {
            "reporter": "Anna",
            "title": "Drucker leer",
            "description": "Kein Papier",
            "reported_priority": "low",
        }
        with TestClient(app) as client:
            for field in payload:
                for value in ("   ", 1):
                    with self.subTest(field=field, value=value):
                        invalid = payload | {field: value}
                        self.assertEqual(client.post("/tickets", json=invalid).status_code, 422)
            self.assertEqual(client.post("/tickets", json={}).status_code, 422)
            self.assertEqual(client.get("/tickets").json(), [])

    def test_cors_allows_vite_origins(self):
        with TestClient(app) as client:
            for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
                with self.subTest(origin=origin):
                    response = client.options(
                        "/tickets",
                        headers={
                            "Origin": origin,
                            "Access-Control-Request-Method": "POST",
                            "Access-Control-Request-Headers": "Content-Type",
                        },
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)

    def post_ticket(self, client, title, description, reported_priority):
        response = client.post(
            "/tickets",
            json={
                "reporter": "Anna",
                "title": title,
                "description": description,
                "reported_priority": reported_priority,
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()
