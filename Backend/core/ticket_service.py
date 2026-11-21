import json
from datetime import datetime, timezone

from . import database, policy_engine
from .models import AnalysisResult, MonitoringEvidence, TicketCreate, ValidationResult
from .priority_engine import calculate_priority

if __package__ == "Backend.core":
    from ..agents.analyst import AnalystAgent
    from ..agents.llm_client import AgentError
    from ..agents.validator import ValidatorAgent
else:
    from agents.analyst import AnalystAgent
    from agents.llm_client import AgentError
    from agents.validator import ValidatorAgent


_ACTOR = "ticket_service"
_RESULT_UPDATE = "update_ticket:priority_score,priority_label,workflow_status,evidence_status,reasoning"
_LEGACY_CATEGORIES = {"authentication": "access", "database": "software"}
_CATEGORIES = {"authentication", "network", "database", "hardware", "software", "security", "other"}
_EVIDENCE_EXAMPLE = {
    "service_id": "auth", "status": "online", "affected_users": 0, "source": "SIMULATED_MONITORING"
}


class InvalidTicketInput(ValueError):
    pass


class TicketPolicyDenied(PermissionError):
    pass


def create_and_process_ticket(
    reporter: str, title: str, description: str, reported_priority: str
) -> dict:
    try:
        data = policy_engine.validate_ticket_input(dict(
            reporter=reporter, title=title, description=description,
            reported_priority=reported_priority,
        ))
    except ValueError as exc:
        raise InvalidTicketInput(str(exc)) from exc

    ticket = TicketCreate(**data)
    _require_permission("create_ticket")
    _require_analysis_permissions()
    score, label = calculate_priority(0, 0, 0, 0)
    saved = database.insert_ticket(
        ticket,
        priority_score=score,
        priority_label=label,
        workflow_status="needs_review",
        evidence_status="unverified",
        reasoning="Ticket gespeichert. Die Analyse läuft.",
    )
    return _process_ticket(saved)


def reanalyze_ticket(ticket_id: int) -> dict | None:
    _require_permission("read_ticket")
    _require_analysis_permissions()
    saved = database.begin_reanalysis(ticket_id)
    return _process_ticket(saved) if saved is not None else None


def get_queue_snapshot() -> list[dict]:
    _require_permission("list_tickets")
    return database.list_tickets()


def _require_permission(action: str) -> None:
    if not policy_engine.authorize_action(_ACTOR, action):
        raise TicketPolicyDenied("Die Ticket-Policy erlaubt diese Aktion nicht.")


def _require_analysis_permissions() -> None:
    _require_permission(_RESULT_UPDATE)
    _require_permission("append_audit_event")


def _process_ticket(saved: dict) -> dict:
    ticket = {key: saved[key] for key in ("id", "reporter", "title", "description", "reported_priority")}
    stage = "Analyst"
    flags = policy_engine.inspect_ticket_text(ticket["title"], ticket["description"])
    try:
        raw_analysis = AnalystAgent().analyze(ticket)
        stage = "Validator"
        raw_validation = ValidatorAgent().validate(ticket, raw_analysis)
        stage = "Ergebnisprüfung"
        analysis = _approve_analysis(raw_analysis)
        validation = _approve_validation(raw_validation)
        evidence = validation.evidence_status
        if evidence == "confirmed" and not any(
            item["service_id"] == analysis.service_id
            and item["status"] in {"offline", "degraded"} and not item.get("error")
            for item in analysis.checked_evidence
        ):
            raise ValueError("Bestätigung ohne passenden Ausfallbeleg")
        age = datetime.now(timezone.utc) - datetime.fromisoformat(saved["created_at"])
        score, label = calculate_priority(
            impact=analysis.impact,
            urgency=analysis.urgency,
            affected_scope=analysis.affected_scope,
            sla_risk=analysis.sla_risk,
            age_hours=max(0, age.total_seconds() / 3600),
            evidence_status=evidence,
        )
        needs_review = (
            validation.recommended_status == "needs_review"
            or validation.injection_suspected
            or validation.injection_reasons
            or validation.conflicting_facts
            or flags["manipulation_only"]
            or evidence == "conflicting"
            or (analysis.impact == 5 and evidence != "confirmed")
        )
        workflow = "needs_review" if needs_review else "open"
        reasoning = f"{analysis.reasoning} Prüfung: {validation.explanation}"
        detail = f"Dienst {analysis.service_id}. Evidenz {evidence}. Score {score}. Status {workflow}."
        if validation.injection_suspected or validation.injection_reasons or flags["injection_suspected"]:
            detail += " Manipulationshinweis erkannt."
        event = "analyzed"
    except AgentError as exc:
        reasoning = _agent_failure(stage, exc)
        event = "analysis_failed"
    except (TypeError, ValueError):
        reasoning = f"{stage}: Ungültige oder nicht freigegebene Agentenausgabe."
        event = "analysis_failed"

    if event == "analysis_failed":
        score, label = calculate_priority(0, 0, 0, 0)
        workflow, evidence = "needs_review", "unverified"
        reasoning += " Das Ticket wurde gespeichert und muss geprüft werden."
        detail = reasoning
        if flags["injection_suspected"]:
            detail += " Manipulationshinweis erkannt."

    return database.update_ticket_result(
        ticket["id"], saved["analysis_version"],
        priority_score=score,
        priority_label=label,
        workflow_status=workflow,
        evidence_status=evidence,
        reasoning=reasoning,
        event_type=event,
        audit_detail=detail,
    )


def _approve_analysis(raw: dict) -> AnalysisResult:
    analysis = AnalysisResult(**raw)
    if analysis.category not in _CATEGORIES:
        raise ValueError("Ungültige Kategorie")
    if analysis.service_id not in {"auth", "web", "db", "unknown"}:
        raise ValueError("Ungültiger Dienst")
    if not isinstance(analysis.checked_evidence, list) or not 1 <= len(analysis.checked_evidence) <= 50:
        raise ValueError("Ungültige Monitoring-Belege")
    evidence = [MonitoringEvidence.model_validate(item) for item in analysis.checked_evidence]
    if not any(item.service_id == analysis.service_id for item in evidence):
        raise ValueError("Monitoring-Beleg für den analysierten Dienst fehlt")

    # Probe the supported format separately so rejection of submitted values still fails closed.
    policy_data = raw.copy()
    policy_data["checked_evidence"] = [item.model_dump(exclude_none=True) for item in evidence]
    if analysis.category in _LEGACY_CATEGORIES:
        try:
            policy_engine.validate_analysis({"category": analysis.category})
        except ValueError:
            policy_data["category"] = _LEGACY_CATEGORIES[analysis.category]
    try:
        policy_engine.validate_analysis({"checked_evidence": [_EVIDENCE_EXAMPLE.copy()]})
    except ValueError:
        policy_data["checked_evidence"] = [
            json.dumps(item, ensure_ascii=False) for item in policy_data["checked_evidence"]
        ]
        legacy_evidence = True
    else:
        legacy_evidence = False
    approved = policy_engine.validate_analysis(policy_data)
    if policy_data["category"] != analysis.category:
        approved["category"] = analysis.category
    if legacy_evidence:
        approved["checked_evidence"] = [json.loads(item) for item in approved["checked_evidence"]]
    if not approved["reasoning"].strip():
        raise ValueError("Begründung der Analyse fehlt")
    return AnalysisResult(**approved)


def _approve_validation(raw: dict) -> ValidationResult:
    validation = ValidationResult(**raw)
    if validation.recommended_status not in {"open", "needs_review", "reject"}:
        raise ValueError("Ungültige Workflow-Empfehlung")
    if validation.recommended_status == "reject":
        raw = raw | {"recommended_status": "needs_review"}
    approved = ValidationResult(**policy_engine.validate_analysis(raw))
    if not approved.explanation.strip():
        raise ValueError("Begründung der Validierung fehlt")
    return approved


def _agent_failure(stage: str, exc: AgentError) -> str:
    error = str(exc).lower()
    if "google_api_key" in error:
        return f"{stage}: Der Gemini-API-Key fehlt."
    if "429" in error:
        return f"{stage}: Das Gemini-Quotenlimit wurde erreicht (HTTP 429)."
    if "503" in error:
        return f"{stage}: Gemini ist vorübergehend nicht verfügbar (HTTP 503)."
    if "timeout" in error:
        return f"{stage}: Gemini hat nicht rechtzeitig geantwortet."
    if any(term in error for term in ("ungueltig", "ungültig", "json", "decode")):
        return f"{stage}: Der Agent hat eine ungültige Ausgabe geliefert."
    return f"{stage}: Die Agentenanalyse konnte nicht abgeschlossen werden."
