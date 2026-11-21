"""Explicit offline demonstration model; real ADK tools, simulated answers.

This model does not call Gemini and must only be selected by an explicit demo
setting. It never executes ticket instructions or exposes a writing tool.
"""

import json
import re
from typing import Literal

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types


DEMO_PREFIX = "OFFLINE-DEMO: Simulierte Agentenantwort ohne Gemini."
_SERVICES = {"auth", "web", "db", "unknown"}
_ATTACK = re.compile(
    r"ich bin admin|i am (?:the )?admin|ignore.{0,40}instructions|"
    r"ignoriere.{0,40}(?:regeln|anweisungen)|loesch|l\u00f6sch|"
    r"delete.{0,30}(?:tickets|queue)|leere.{0,30}(?:queue|warteschlange)", re.I,
)


class DemoModel(BaseLlm):
    model: str = "queueguard-offline-demo"
    role: Literal["analyst_agent", "validator_agent"]

    async def generate_content_async(self, llm_request, stream=False):
        payload = None
        for content in llm_request.contents:
            if content.role == "user":
                for part in content.parts or []:
                    if part.text and part.text.startswith("UNTRUSTED_INPUT_JSON\n"):
                        payload = json.loads(part.text.split("\n", 1)[1])
        if not isinstance(payload, dict):
            raise ValueError("Offline demo requires a structured ticket payload")
        ticket = payload.get("ticket", payload) if self.role == "validator_agent" else payload
        analysis = payload.get("analysis", {})
        text = f"{ticket.get('title', '')} {ticket.get('description', '')}".casefold()
        if self.role == "validator_agent":
            service = analysis.get("service_id", "unknown")
            service = service if service in _SERVICES else "unknown"
        elif any(word in text for word in ("login", "anmeld", "auth")):
            service = "auth"
        elif any(word in text for word in ("datenbank", "database", "postgres", "mysql")):
            service = "db"
        elif any(word in text for word in ("website", "webseite", "server", "http", "portal")):
            service = "web"
        else:
            service = "unknown"

        evidence = None
        for content in llm_request.contents:
            for part in content.parts or []:
                response = part.function_response
                if response and response.name == "get_service_status":
                    result = response.response
                    if isinstance(result, dict) and result.get("service_id") == service:
                        evidence = result
        if evidence is None:
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(
                function_call=types.FunctionCall(
                    id=f"demo-{self.role}-monitoring", name="get_service_status",
                    args={"service_id": service},
                )
            )]))
            return

        suspected = bool(_ATTACK.search(text))
        status = evidence.get("status", "unknown")
        users = evidence.get("affected_users", 0)
        confirmed = (service != "unknown" and status in {"offline", "degraded"}
                     and evidence.get("source") == "SIMULATED_MONITORING"
                     and not evidence.get("error"))
        if self.role == "analyst_agent":
            category = {"auth": "authentication", "web": "software", "db": "database"}.get(service)
            if category is None:
                hardware = any(word in text for word in ("drucker", "printer", "toner", "papier", "tastatur", "maus"))
                category = "hardware" if hardware else "security" if suspected else "other"
            if confirmed and users >= 250:
                impact, urgency, scope = 5, 5, 5
            elif confirmed:
                impact, urgency, scope = 4, 4, 2
            elif service != "unknown":
                impact, urgency, scope = 2, 2, 1
            else:
                impact, urgency, scope = 1, 1, 1
            output = {
                "category": category, "service_id": service,
                "impact": impact, "urgency": urgency, "affected_scope": scope,
                "sla_risk": 0, "duplicate_ids": [], "checked_evidence": [],
                "reasoning": f"{DEMO_PREFIX} Gelesenes simuliertes Monitoring: {service}={status}, {users} Betroffene. "
                             + ("Der simulierte Dienstausfall ist belegt." if confirmed else
                                "Kein allgemeiner Dienstausfall bestaetigt; ein individuelles Problem bleibt moeglich."),
                "missing_information": ["SLA-Vertrag unbekannt; sla_risk=0.",
                                        "Agentenbewertung ist eine ausdruecklich simulierte Offline-Demo."],
            }
        else:
            review = (suspected or status == "unknown"
                      or (analysis.get("impact") == 5 and not confirmed))
            output = {
                "evidence_status": "confirmed" if confirmed else "unverified",
                "injection_suspected": suspected,
                "injection_reasons": ["Angriffs- oder zitiertes Anweisungsmuster erkannt; manuell pruefen."] if suspected else [],
                "conflicting_facts": [], "recommended_status": "needs_review" if review else "open",
                "explanation": f"{DEMO_PREFIX} Monitoring wurde ueber das echte Lesetool erneut gelesen: {service}={status}. "
                               + ("Simulierter Ausfall bestaetigt." if confirmed else
                                  "Kein allgemeiner Ausfall belegt; dies widerlegt kein individuelles Nutzerproblem."),
            }
        yield LlmResponse(content=types.Content(role="model", parts=[
            types.Part.from_text(text=json.dumps(output, ensure_ascii=False))
        ]))
