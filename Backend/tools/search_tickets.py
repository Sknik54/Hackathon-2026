"""Optional SQLite search: fixed SELECT only, read-only connection.

Person 1 can set QUEUEGUARD_TICKETS_DB to the SQLite file. Expected columns:
tickets(id, title, description). No configured database means no matches;
we never invent demo duplicates or create an empty database on disk.
"""

import logging
import os
from pathlib import Path
import re
import sqlite3


logger = logging.getLogger("queueguard.tools")


def search_similar_tickets(query: str, limit: int = 5) -> list[dict]:
    """Read up to limit similar tickets by literal words from query.

    Results are candidate duplicates, not verified duplicates. Empty results
    can also mean that the optional database is not configured/available.
    No SQL, paths or commands supplied in query are ever executed.
    """
    if not isinstance(query, str) or type(limit) is not int or limit < 1:
        return []
    configured_path = os.getenv("QUEUEGUARD_TICKETS_DB")
    if not configured_path:
        logger.info("READ_ONLY search_similar_tickets unavailable=not_configured")
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
        uri = Path(configured_path).expanduser().resolve().as_uri() + "?mode=ro"
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
