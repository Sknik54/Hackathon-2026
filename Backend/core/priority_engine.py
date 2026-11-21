def calculate_priority(
    impact: int,
    urgency: int,
    affected_scope: int,
    sla_risk: int,
    age_hours: float = 0,
    evidence_status: str = "unverified",
) -> tuple[int, str]:
    for name, value in (
        ("impact", impact),
        ("urgency", urgency),
        ("affected_scope", affected_scope),
        ("sla_risk", sla_risk),
    ):
        if type(value) is not int or not 0 <= value <= 5:
            raise ValueError(f"{name} must be an integer between 0 and 5")

    if type(age_hours) not in (int, float) or not 0 <= age_hours < float("inf"):
        raise ValueError("age_hours must be a finite non-negative number")
    if not isinstance(evidence_status, str) or not evidence_status.strip():
        raise ValueError("evidence_status must be a non-empty string")

    age_bonus = int(min(age_hours, 20) / 4)
    score = min(100, impact * 8 + urgency * 6 + affected_scope * 3 + sla_risk * 2 + age_bonus)
    if impact == 5 and evidence_status != "confirmed":
        score = min(score, 69)

    if score >= 70:
        return score, "Critical"
    if score >= 50:
        return score, "High"
    if score >= 30:
        return score, "Medium"
    return score, "Low"
