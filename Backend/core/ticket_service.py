from . import database
from .models import AnalysisResult, TicketCreate
from .priority_engine import calculate_priority


def _mock_analysis(ticket: TicketCreate) -> AnalysisResult:
    text = f"{ticket.title} {ticket.description}".casefold()
    if any(phrase in text for phrase in ("niemand kann sich anmelden", "nobody can log in")):
        category, service_id = "access", "auth"
        impact, urgency, affected_scope, sla_risk = 5, 5, 5, 4
        assessment = "Der Tickettext deutet auf einen Ausfall der Anmeldung für viele Nutzer hin."
    elif any(term in text for term in ("login", "anmeld", "log in")):
        category, service_id = "access", "auth"
        impact, urgency, affected_scope, sla_risk = 3, 3, 1, 2
        assessment = "Der Tickettext deutet auf ein Anmeldeproblem hin."
    else:
        category, service_id = "other", None
        impact, urgency, affected_scope, sla_risk = 1, 1, 1, 0
        assessment = "Der Tickettext ergibt die vorläufige Einstufung als Standardticket."

    return AnalysisResult(
        category=category,
        service_id=service_id,
        impact=impact,
        urgency=urgency,
        affected_scope=affected_scope,
        sla_risk=sla_risk,
        duplicate_ids=[],
        checked_evidence=[],
        reasoning=f"Mock-Analyse. {assessment} Monitoring-Daten fehlen.",
        missing_information=["Monitoring-Daten"],
    )


def create_and_process_ticket(
    reporter: str, title: str, description: str, reported_priority: str
) -> dict:
    ticket = TicketCreate(
        reporter=reporter,
        title=title,
        description=description,
        reported_priority=reported_priority,
    )
    analysis = _mock_analysis(ticket)
    evidence_status = "unverified"
    score, label = calculate_priority(
        impact=analysis.impact,
        urgency=analysis.urgency,
        affected_scope=analysis.affected_scope,
        sla_risk=analysis.sla_risk,
        evidence_status=evidence_status,
    )
    workflow_status = "needs_review" if analysis.impact == 5 else "open"
    return database.insert_ticket(
        ticket,
        priority_score=score,
        priority_label=label,
        workflow_status=workflow_status,
        evidence_status=evidence_status,
        reasoning=analysis.reasoning,
    )


def get_queue_snapshot() -> list[dict]:
    return database.list_tickets()
