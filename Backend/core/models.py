from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


ServiceId = Literal["auth", "web", "db"]
ServiceStatus = Literal["online", "offline", "degraded"]
AffectedUsers = Annotated[int, Field(strict=True, ge=0)]


class TicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    reporter: str
    title: str
    description: str
    reported_priority: str


class TicketResponse(BaseModel):
    id: int
    title: str
    priority_score: int
    priority_label: str
    workflow_status: str
    evidence_status: str
    reasoning: str


class MonitoringChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ServiceStatus
    affected_users: AffectedUsers


class MonitoringEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: Literal["auth", "web", "db", "unknown"]
    status: Literal["online", "offline", "degraded", "unknown"]
    affected_users: AffectedUsers
    source: Literal["SIMULATED_MONITORING"]
    error: Literal["unknown_service", "monitoring_unavailable"] | None = None


class MonitoringSnapshot(BaseModel):
    services: list[MonitoringEvidence]


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
