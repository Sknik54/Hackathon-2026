"""Optional SQLite search: fixed SELECT only, read-only connection.

Use QUEUEGUARD_DB_PATH like core.database; QUEUEGUARD_TICKETS_DB remains a
legacy fallback. Without either variable, read Backend/queueguard.db.
Relative paths resolve from the process working directory, like the backend.
Expected columns: tickets(id, title, description). Missing/unavailable files
mean no matches; we never create an empty database or invent duplicates.
"""

import logging
import os
from pathlib import Path
import re
import sqlite3


logger = logging.getLogger("queueguard.tools")
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "queueguard.db"


def _database_path() -> Path:
    # Presence matters: an invalid/empty primary setting must not silently
    # select a different database via the legacy variable or the default.
    configured = os.getenv("QUEUEGUARD_DB_PATH")
    if configured is None:
        configured = os.getenv("QUEUEGUARD_TICKETS_DB")
    return Path(configured) if configured is not None else DEFAULT_DB_PATH


def search_similar_tickets(query: str, limit: int = 5) -> list[dict]:
    """Read up to limit similar tickets by literal words from query.

    Results are candidate duplicates, not verified duplicates. Empty results
    can also mean that the database is missing/unavailable.
    No SQL, paths or commands supplied in query are ever executed.
    """
    if not isinstance(query, str) or type(limit) is not int or limit < 1:
        return []
    words = list(dict.fromkeys(re.findall(r"\w{3,}", query[:2000].lower())))[:8]
    if not words:
        return []
    clauses, params = [], []
    for word in words:
        literal = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("(lower(title) LIKE ? ESCAPE '\\' OR lower(description) LIKE ? ESCAPE '\\')")
        params.extend([f"%{literal}%", f"%{literal}%"])
    params.append(min(limit, 20))
    try:
        uri = _database_path().resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=1)
        try:
            connection.execute("PRAGMA query_only = ON")
            rows = connection.execute(
                "SELECT id, title, description FROM tickets WHERE "
                + " OR ".join(clauses) + " ORDER BY id DESC LIMIT ?", params
            ).fetchall()
        finally:
            connection.close()
    except (OSError, ValueError, sqlite3.Error):
        logger.info("READ_ONLY search_similar_tickets unavailable=database_unavailable")
        return []
    result = [{"id": row[0], "title": str(row[1])[:500],
               "description": str(row[2])[:2000], "source": "SQLITE_READ_ONLY"}
              for row in rows if type(row[0]) is int and row[0] > 0]
    logger.info("READ_ONLY search_similar_tickets ids=%s", [item["id"] for item in result])
    return result
