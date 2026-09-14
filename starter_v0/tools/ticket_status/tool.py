from __future__ import annotations

import json
import re
from typing import Any

from tools._shared import ROOT, err


TICKET_DIR = ROOT / "tickets"
# Same ID shape create_ticket generates: "LAB-" + 8 hex chars.
TICKET_ID_PATTERN = re.compile(r"^LAB-[0-9A-F]{8}$")


def ticket_status(ticket_id: str = "") -> dict[str, Any]:
    """Read-only lookup of a ticket previously created by create_ticket.

    No side effects: never creates, modifies, or deletes ticket files.
    Rejects any ticket_id that does not match the exact ID shape create_ticket
    generates, which also prevents path-traversal style input (e.g. "../..")
    from ever reaching the filesystem lookup.
    """
    if not isinstance(ticket_id, str):
        return {"tool": "ticket_status", "error": "invalid_ticket_id_type"}
    normalized_id = (ticket_id or "").strip().upper()
    if not normalized_id:
        return {"tool": "ticket_status", "error": "missing_ticket_id"}
    if not TICKET_ID_PATTERN.fullmatch(normalized_id):
        return {"tool": "ticket_status", "error": "invalid_ticket_id_format", "ticket_id": normalized_id}
    try:
        path = TICKET_DIR / f"{normalized_id}.json"
        if not path.is_file():
            return {"tool": "ticket_status", "ticket_id": normalized_id, "error": "ticket_not_found"}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            "tool": "ticket_status",
            "ticket_id": payload.get("ticket_id", normalized_id),
            "summary": payload.get("summary"),
            "priority": payload.get("priority"),
            "asset_id": payload.get("asset_id"),
            "created_at": payload.get("created_at"),
            "source": payload.get("source"),
        }
    except Exception as exc:
        return err("ticket_status", exc)
