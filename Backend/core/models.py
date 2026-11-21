from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, StringConstraints


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TicketCreate(BaseModel):
    reporter: NonEmptyText
    title: NonEmptyText
    description: NonEmptyText
    reported_priority: NonEmptyText


class TicketResponse(BaseModel):
    id: int
    title: str
    priority_score: int
    priority_label: str
    workflow_status: str
    evidence_status: str
    reasoning: str


@dataclass
class AnalysisResult:
    category: str
    service_id: str | None
    impact: int
    urgency: int
    affected_scope: int
    sla_risk: int
    duplicate_ids: list[int]
    checked_evidence: list[dict[str, object]]
    reasoning: str
    missing_information: list[str]


@dataclass
class ValidationResult:
    evidence_status: str
    injection_suspected: bool
    injection_reasons: list[str]
    conflicting_facts: list[str]
    recommended_status: str
    explanation: str
