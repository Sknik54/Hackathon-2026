import json
import os
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from Backend.agents.llm_client import AgentError
from Backend.core import database, policy_engine, ticket_service
from Backend.main import app
from Backend.tools import monitoring


class TicketApiTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.db_path = Path(directory) / "test.db"
        self.enterContext(patch.object(database, "DB_PATH", self.db_path))
        self.enterContext(patch.dict(os.environ))
        self.analyst = self.enterContext(patch.object(ticket_service, "AnalystAgent"))
        self.validator = self.enterContext(patch.object(ticket_service, "ValidatorAgent"))
        self.analyze = self.analyst.return_value.analyze
        self.validate = self.validator.return_value.validate
        self.analyze.side_effect = self.analyze_by_title
        self.validate.return_value = {
            "evidence_status": "confirmed", "injection_suspected": False,
            "injection_reasons": [], "conflicting_facts": [], "recommended_status": "open",
            "explanation": "Das Monitoring bestätigt den Ausfall.",
        }

    @staticmethod
    def analyze_by_title(ticket):
        impact, urgency, scope, sla = (5, 5, 5, 4)
        if ticket["title"] == "Drucker leer":
            impact, urgency, scope, sla = (1, 1, 1, 0)
        return {
            "category": "authentication", "service_id": "auth", "impact": impact,
            "urgency": urgency, "affected_scope": scope, "sla_risk": sla, "duplicate_ids": [],
            "checked_evidence": [{
                "service_id": "auth", "status": "offline", "affected_users": 250,
                "source": "SIMULATED_MONITORING",
            }],
            "reasoning": "Der Login-Dienst ist offline.", "missing_information": [],
        }

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

        def analyze_persisted_ticket(ticket):
            with closing(sqlite3.connect(self.db_path)) as connection:
                stored = connection.execute(
                    "SELECT description, workflow_status FROM tickets WHERE id = ?", (ticket["id"],)
                ).fetchone()
            self.assertEqual(stored, (payload["description"], "needs_review"))
            self.assertEqual(os.environ["QUEUEGUARD_TICKETS_DB"], str(self.db_path))
            self.assertEqual(ticket, payload | {"id": 1})
            return self.analyze_by_title(ticket)

        self.analyze.side_effect = analyze_persisted_ticket
        with TestClient(app) as client:
            response = client.post("/tickets", json=payload)
            self.assertEqual(response.status_code, 201)
            ticket = response.json()
            self.validate.assert_called_once_with(
                payload | {"id": 1}, self.analyze_by_title(payload)
            )
            self.assertEqual(
                ticket,
                {
                    "id": 1,
                    "title": "Login kaputt",
                    "priority_score": 93,
                    "priority_label": "Critical",
                    "workflow_status": "open",
                    "evidence_status": "confirmed",
                    "reasoning": "Der Login-Dienst ist offline. Prüfung: Das Monitoring bestätigt den Ausfall.",
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
            printer = self.post_ticket(client, "Drucker leer", "Kein Papier", "high")
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

    def test_unverified_critical_score_is_capped(self):
        self.validate.return_value["evidence_status"] = "unverified"
        with TestClient(app) as client:
            ticket = self.post_ticket(client, "Login", "Kann mich nicht anmelden", "low")
        self.assertEqual(ticket["priority_score"], 69)
        self.assertEqual(ticket["workflow_status"], "needs_review")
        self.assertEqual(ticket["evidence_status"], "unverified")

    def test_agent_failures_keep_tickets_and_do_not_expose_exception_text(self):
        with TestClient(app) as client:
            key_error = AgentError("GOOGLE_API_KEY fehlt")
            self.analyze.side_effect = key_error
            missing_key = self.post_ticket(client, "Login fehlt", "Keine Anmeldung", "low")
            self.assertIn("API-Key fehlt", missing_key["reasoning"])
            self.validate.assert_not_called()

            self.analyze.side_effect = self.analyze_by_title
            self.validate.side_effect = AgentError("HTTP 429, secret provider detail")
            quota = self.post_ticket(client, "Login offline", "Dienst offline", "high")
            self.assertIn("HTTP 429", quota["reasoning"])
            self.assertNotIn("secret provider detail", quota["reasoning"])
            for ticket in (missing_key, quota):
                self.assertEqual(ticket["workflow_status"], "needs_review")
                self.assertEqual(ticket["evidence_status"], "unverified")
                self.assertEqual(ticket["priority_score"], 0)
            self.assertEqual(client.get("/tickets").json(), [missing_key, quota])
            failures = [entry for entry in client.get("/audit").json()
                        if entry["event_type"] == "analysis_failed"]
            self.assertEqual([entry["ticket_id"] for entry in failures], [quota["id"], missing_key["id"]])
            self.assertIn("HTTP 429", failures[0]["detail"])

    def test_unapproved_agent_results_cannot_override_ticket_fields(self):
        analysis = self.analyze_by_title({"title": "Login"})
        invalid_updates = (
            {"priority_score": 100},
            {"impact": True},
            {"category": "unknown"},
            {"checked_evidence": ["erfunden"]},
            {"reasoning": "   "},
        )
        with TestClient(app) as client:
            for update in invalid_updates:
                with self.subTest(update=update):
                    self.analyze.side_effect = None
                    self.analyze.return_value = analysis | update
                    ticket = self.post_ticket(client, "Login", "Fehler", "high")
                    self.assertEqual(ticket["priority_score"], 0)
                    self.assertEqual(ticket["evidence_status"], "unverified")
                    self.assertIn("nicht freigegebene Agentenausgabe", ticket["reasoning"])
            self.analyze.return_value = analysis
            self.validate.return_value["evidence_status"] = "invalid"
            ticket = self.post_ticket(client, "Login", "Fehler", "high")
            self.assertEqual(ticket["workflow_status"], "needs_review")
            self.assertEqual(ticket["evidence_status"], "unverified")

    def test_structured_evidence_rejected_by_policy_is_not_accepted_as_legacy(self):
        original_validate = policy_engine.validate_analysis

        def validate_structured(data):
            rest = dict(data)
            evidence = rest.pop("checked_evidence", None)
            if rest.get("category") == "authentication":
                rest.pop("category")
            clean = original_validate(rest)
            if "category" in data:
                clean["category"] = data["category"]
            if evidence is not None:
                if not all(isinstance(item, dict) and item["affected_users"] <= 100 for item in evidence):
                    raise ValueError("The monitoring evidence was rejected.")
                clean["checked_evidence"] = evidence
            return clean

        with patch.object(policy_engine, "validate_analysis", side_effect=validate_structured):
            with TestClient(app) as client:
                ticket = self.post_ticket(client, "Login", "Login-Dienst offline", "high")
        self.assertEqual(ticket["evidence_status"], "unverified")
        self.assertEqual(ticket["workflow_status"], "needs_review")

    def test_integrated_adk_pipeline_without_gemini(self):
        from Backend.agents.analyst import AnalystAgent
        from Backend.agents.validator import ValidatorAgent
        from Backend.tests.test_agents import ScriptedModel, valid_validation

        monitoring_path = self.db_path.with_name("monitoring.json")
        monitoring_path.write_text(
            '{"services":{"auth":{"status":"offline","affected_users":250}}}', encoding="utf-8"
        )
        self.enterContext(patch.object(monitoring, "MONITORING_PATH", monitoring_path))
        analyst_model = ScriptedModel()
        validator_model = ScriptedModel(output=valid_validation())
        self.analyst.return_value = AnalystAgent(model=analyst_model)
        self.validator.return_value = ValidatorAgent(model=validator_model)
        with TestClient(app) as client:
            ticket = self.post_ticket(client, "Login", "Anmeldung ausgefallen", "high")
            self.assertEqual(client.get("/tickets").json(), [ticket])
        self.assertEqual(ticket["evidence_status"], "confirmed")
        self.assertEqual(ticket["priority_score"], 85)
        for model in (analyst_model, validator_model):
            self.assertEqual(model.seen_tool_results[0]["affected_users"], 250)

    def test_demo_monitoring_and_reanalysis_use_same_data(self):
        monitoring_path = self.db_path.with_name("monitoring.json")
        monitoring_path.write_text(json.dumps({
            "services": {service: {"status": "online", "affected_users": 0}
                         for service in ("auth", "web", "db")}
        }), encoding="utf-8")
        self.enterContext(patch.object(monitoring, "MONITORING_PATH", monitoring_path))

        def analyze_current_monitoring(ticket):
            analysis = self.analyze_by_title(ticket)
            return analysis | {"checked_evidence": [monitoring.get_service_status("auth")]}

        self.analyze.side_effect = analyze_current_monitoring
        self.validate.return_value["evidence_status"] = "unverified"
        with TestClient(app) as client:
            ticket = self.post_ticket(client, "Login", "Anmeldung ausgefallen", "high")
            self.assertEqual(ticket["evidence_status"], "unverified")
            monitoring_before = client.get("/monitoring").json()["services"]
            self.assertEqual(monitoring_before[0], {
                "service_id": "auth", "status": "online", "affected_users": 0,
                "source": "SIMULATED_MONITORING",
            })

            path = "/demo/monitoring/auth"
            self.assertEqual(client.post(path, json={"status": "unknown", "affected_users": 0}).status_code, 422)
            self.assertEqual(client.post(path, json={"status": "offline", "affected_users": True}).status_code, 422)
            self.assertEqual(client.post(path, json={"status": "offline", "affected_users": -1}).status_code, 422)
            self.assertEqual(client.get("/monitoring").json()["services"], monitoring_before)
            change = client.post(path, json={"status": "offline", "affected_users": 250})
            expected = monitoring_before[0] | {"status": "offline", "affected_users": 250}
            self.assertEqual(change.status_code, 200)
            self.assertEqual(change.json(), expected)
            self.assertEqual(client.get("/monitoring").json()["services"], [expected, *monitoring_before[1:]])

            self.validate.return_value["evidence_status"] = "confirmed"
            response = client.post(f'/tickets/{ticket["id"]}/reanalyze')
            self.assertEqual(response.status_code, 200)
            reanalyzed = response.json()
            self.assertEqual(reanalyzed.keys(), ticket.keys())
            self.assertEqual(reanalyzed["id"], ticket["id"])
            self.assertEqual(reanalyzed["evidence_status"], "confirmed")
            self.assertEqual(reanalyzed["priority_score"], 93)
            self.assertEqual(client.get("/tickets").json(), [reanalyzed])
            self.assertEqual(client.post("/tickets/999/reanalyze").status_code, 404)
            audit = client.get("/audit").json()
            self.assertEqual([entry["event_type"] for entry in reversed(audit)],
                             ["created", "analyzed", "monitoring_updated", "reanalysis_started", "analyzed"])
            self.assertEqual(audit[0]["ticket_id"], ticket["id"])
            self.assertIsNone(audit[2]["ticket_id"])

    def test_existing_tickets_survive_sqlite_migration_and_can_be_reanalyzed(self):
        with TestClient(app) as client:
            ticket = self.post_ticket(client, "Login", "Anmeldung ausgefallen", "high")
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("ALTER TABLE tickets DROP COLUMN analysis_version")
            connection.execute("DROP TABLE audit_events")
        with TestClient(app) as client:
            self.assertEqual(client.get("/tickets").json(), [ticket])
            self.validate.side_effect = AgentError("HTTP 429")
            result = client.post(f'/tickets/{ticket["id"]}/reanalyze').json()
            self.assertEqual(result["id"], ticket["id"])
            self.assertEqual(result["evidence_status"], "unverified")
            self.assertEqual(result["workflow_status"], "needs_review")
            self.assertEqual(client.get("/tickets").json(), [result])

    def test_older_analysis_cannot_overwrite_a_newer_reanalysis(self):
        with TestClient(app) as client:
            ticket = self.post_ticket(client, "Login", "Anmeldung ausgefallen", "high")
            first = database.begin_reanalysis(ticket["id"])
            second = database.begin_reanalysis(ticket["id"])
            earlier = dict(priority_score=93, priority_label="Critical", workflow_status="open",
                           evidence_status="confirmed", reasoning="Früheres Ergebnis",
                           event_type="analyzed", audit_detail="Früheres Ergebnis")
            later = earlier | dict(priority_score=69, priority_label="High", workflow_status="needs_review",
                                  evidence_status="unverified", reasoning="Späteres Ergebnis")
            expected = database.update_ticket_result(ticket["id"], second["analysis_version"], **later)
            self.assertEqual(database.update_ticket_result(
                ticket["id"], first["analysis_version"], **earlier
            ), expected)
            self.assertEqual(client.get("/tickets").json(), [expected])

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
            self.assertEqual(client.post(
                "/tickets", json=payload | {"reported_priority": "critical"}
            ).status_code, 422)
            self.assertEqual(client.post(
                "/tickets", json=payload | {"is_admin": True}
            ).status_code, 422)
            self.assertEqual(client.get("/tickets").json(), [])
            self.analyst.assert_not_called()

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
