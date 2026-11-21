"""Deterministic authorization and schema checks for QueueGuard.

This module enforces application policy. It does not authenticate users or
validate tokens; actor names are internal service labels, not credentials.
"""

from __future__ import annotations

import re
from typing import Any


READ_ONLY_ACTIONS = frozenset(
    {
        "get_service_status",
        "search_similar_tickets",
        "read_ticket",
        "list_tickets",
        "get_monitoring",
    }
)
TICKET_UPDATE_FIELDS = frozenset(
    {
        "category",
        "service_id",
        "impact",
        "urgency",
        "affected_scope",
        "sla_risk",
        "duplicate_ids",
        "checked_evidence",
        "reasoning",
        "missing_information",
        "evidence_status",
        "injection_suspected",
        "injection_reasons",
        "conflicting_facts",
        "recommended_status",
        "explanation",
        "priority_score",
        "priority_label",
        "workflow_status",
    }
)
_DELETE_ACTIONS = frozenset({"delete_ticket", "delete_all_tickets"})
_CATEGORIES = frozenset(
    {"access", "network", "hardware", "software", "security", "email", "other"}
)
_EVIDENCE_STATUSES = frozenset({"confirmed", "unverified", "conflicting"})
_WORKFLOW_STATUSES = frozenset({"open", "in_progress", "needs_review", "resolved", "closed"})
_INJECTION_PATTERNS = (
    re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b", re.I),
    re.compile(r"\b(?:delete|erase|remove)\s+(?:all\s+)?(?:tickets?|queue|records?)\b", re.I),
    re.compile(r"\b(?:i am|i'm)\s+(?:the\s+)?admin\b", re.I),
    re.compile(r"\b(?:reveal|print|show)\s+(?:the\s+)?(?:system\s+)?prompt\b", re.I),
    re.compile(r"\b(?:bypass|disable)\s+(?:the\s+)?(?:security|policy|validation)\b", re.I),
)
_ISSUE_CUES = re.compile(
    r"\b(error|fail(?:s|ed|ure)?|broken|cannot|can't|unable|down|offline|"
    r"crash(?:es|ed)?|disconnect(?:ed|s)?|not working|doesn't work|kaputt|"
    r"funktioniert nicht|fehler|ausfall|verbindung|anmelden|login)\b",
    re.I,
)


def authorize_action(actor: str, action: str) -> bool:
    """Return whether an internal actor may perform a named action.

    This is an allowlist for application components, not an authentication
    check. User supplied claims such as "I am admin" never change the actor.
    """
    if not isinstance(actor, str) or not isinstance(action, str):
        return False
    actor, action = actor.strip().lower(), action.strip().lower()
    if not actor or not action or action in _DELETE_ACTIONS:
        return False
    if actor in {"analyst_agent", "validator_agent"}:
        return action in READ_ONLY_ACTIONS
    if actor == "ticket_service":
        if action in {"create_ticket", "append_audit_event", "read_ticket", "list_tickets"}:
            return True
        if action.startswith("update_ticket:"):
            fields = {field.strip() for field in action.partition(":")[2].split(",")}
            return bool(fields) and fields <= TICKET_UPDATE_FIELDS
        return False
    return False


def validate_ticket_input(payload: Any) -> dict[str, str]:
    """Validate and normalize the public POST /tickets request fields."""
    if not isinstance(payload, dict):
        raise ValueError("Ticket must be a JSON object.")
    required = {"reporter", "title", "description", "reported_priority"}
    if set(payload) != required:
        missing, extra = required - set(payload), set(payload) - required
        raise ValueError(f"Ticket fields mismatch (missing={sorted(missing)}, extra={sorted(extra)}).")
    limits = {"reporter": 120, "title": 200, "description": 5000}
    normalized: dict[str, str] = {}
    for name, maximum in limits.items():
        value = payload[name]
        if not isinstance(value, str):
            raise ValueError(f"{name} must be text.")
        value = value.strip()
        if not value:
            raise ValueError(f"{name} cannot be empty.")
        if len(value) > maximum:
            raise ValueError(f"{name} must be at most {maximum} characters.")
        if "\x00" in value:
            raise ValueError(f"{name} contains an invalid null character.")
        normalized[name] = value
    priority = payload["reported_priority"]
    if not isinstance(priority, str) or priority not in {"low", "medium", "high"}:
        raise ValueError("reported_priority must be low, medium, or high.")
    normalized["reported_priority"] = priority
    return normalized


def validate_analysis(data: Any) -> dict[str, Any]:
    """Validate untrusted analyst/validator output and return known fields only."""
    if not isinstance(data, dict):
        raise ValueError("Analysis must be a JSON object.")
    numbers = {"impact", "urgency", "affected_scope", "sla_risk"}
    booleans = {"injection_suspected"}
    enums = {"evidence_status": _EVIDENCE_STATUSES, "recommended_status": _WORKFLOW_STATUSES}
    strings = {"category", "service_id", "reasoning", "explanation"}
    string_lists = {"checked_evidence", "missing_information", "injection_reasons", "conflicting_facts"}
    allowed = numbers | booleans | set(enums) | strings | string_lists | {"duplicate_ids"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unknown analysis fields: {sorted(unknown)}")

    clean: dict[str, Any] = {}
    for name in numbers:
        if name in data:
            value = data[name]
            if type(value) is not int or not 0 <= value <= 5:
                raise ValueError(f"{name} must be an integer from 0 to 5.")
            clean[name] = value
    for name in booleans:
        if name in data:
            if type(data[name]) is not bool:
                raise ValueError(f"{name} must be a boolean.")
            clean[name] = data[name]
    for name, choices in enums.items():
        if name in data:
            if not isinstance(data[name], str) or data[name] not in choices:
                raise ValueError(f"Invalid {name}.")
            clean[name] = data[name]
    if "category" in data:
        if not isinstance(data["category"], str) or data["category"] not in _CATEGORIES:
            raise ValueError("Invalid category.")
        clean["category"] = data["category"]
    for name in strings - {"category"}:
        if name in data:
            value = data[name]
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError(f"{name} must be text of at most 2000 characters.")
            clean[name] = value
    for name in string_lists:
        if name in data:
            values = data[name]
            if not isinstance(values, list) or len(values) > 50 or any(
                not isinstance(item, str) or len(item) > 500 for item in values
            ):
                raise ValueError(f"{name} must be a list of short strings.")
            clean[name] = list(values)
    if "duplicate_ids" in data:
        ids = data["duplicate_ids"]
        if not isinstance(ids, list) or len(ids) > 100 or any(type(item) is not int or item < 1 for item in ids):
            raise ValueError("duplicate_ids must contain positive integer ticket IDs.")
        clean["duplicate_ids"] = list(ids)
    return clean


def inspect_ticket_text(title: str, description: str) -> dict[str, Any]:
    """Flag common instruction attacks without discarding the reported issue."""
    text = f"{title}\n{description}"
    reasons = [pattern.pattern for pattern in _INJECTION_PATTERNS if pattern.search(text)]
    suspected = bool(reasons)
    issue_present = bool(_ISSUE_CUES.search(text))
    return {
        "injection_suspected": suspected,
        "injection_reasons": reasons,
        "manipulation_only": suspected and not issue_present,
        "workflow_status": "needs_review" if suspected and not issue_present else "open",
    }
