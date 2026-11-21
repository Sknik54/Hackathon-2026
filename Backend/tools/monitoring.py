"""Read simulated monitoring on every call, including after demo changes."""

import json
import logging
from pathlib import Path


MONITORING_PATH = Path(__file__).resolve().parents[1] / "data" / "monitoring.json"
SERVICE_IDS = frozenset({"auth", "web", "db"})
STATUSES = frozenset({"online", "offline", "degraded"})
logger = logging.getLogger("queueguard.tools")


def get_service_status(service_id: str) -> dict:
    """Read SIMULATED monitoring for service_id: auth (login), web, or db.

    Returns status, affected_users and source. Unknown/unavailable is NOT
    evidence of an outage. Online does NOT rule out an individual problem.
    This function never changes monitoring or tickets.
    """
    normalized = service_id.strip().lower() if isinstance(service_id, str) else ""
    result = {
        "service_id": normalized if normalized in SERVICE_IDS else "unknown",
        "status": "unknown",
        "affected_users": 0,
        "source": "SIMULATED_MONITORING",
    }
    if normalized not in SERVICE_IDS:
        result["error"] = "unknown_service"
    else:
        try:
            data = json.loads(MONITORING_PATH.read_text(encoding="utf-8"))
            service = data["services"][normalized]
            status, affected = service["status"], service["affected_users"]
            if status not in STATUSES or type(affected) is not int or affected < 0:
                raise ValueError("Invalid monitoring entry")
            result.update(status=status, affected_users=affected)
        except (OSError, ValueError, KeyError, TypeError):
            result["error"] = "monitoring_unavailable"
    logger.info("READ_ONLY get_service_status result=%s", json.dumps(result))
    return result
