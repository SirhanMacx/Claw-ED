"""Autonomy progression — track approval rates and offer auto-approval."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

def _default_db() -> Path:
    from clawed.paths import approvals_db
    return approvals_db()

_DEFAULT_DB = None  # resolved lazily via _default_db()
_MIN_SAMPLES = 10
_AUTO_THRESHOLD = 0.95

# Action types that should NEVER be auto-approved — always require teacher review.
# Student-facing output and external publishing need human oversight in education.
_NEVER_AUTO_APPROVE = {
    "student_publish",
    "student_bot_config",
    "drive_upload",
    "drive_create_slides",
    "drive_create_doc",
    "share_with_students",
}

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS approvals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type     TEXT,
    status          TEXT,
    action_payload  TEXT DEFAULT '{}',
    teacher_id      TEXT DEFAULT '',
    created_at      TEXT,
    resolved_at     TEXT
)
"""

_CREATE_INDEX = """\
CREATE INDEX IF NOT EXISTS idx_approvals_type ON approvals(action_type)
"""


class ApprovalTracker:
    """Tracks approval/rejection rates per action type and offers auto-approval."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _default_db()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._migrate_json_if_needed()

    def _init_db(self) -> None:
        """Create the approvals table and index if they don't exist."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(_CREATE_TABLE)
            conn.execute(_CREATE_INDEX)

    def _migrate_json_if_needed(self) -> None:
        """One-time migration from old JSON approval files to SQLite."""
        old_dir = self._db_path.parent / "approvals"
        if not old_dir.exists() or not old_dir.is_dir():
            return

        json_files = list(old_dir.glob("*.json"))
        if not json_files:
            return

        migrated = 0
        with sqlite3.connect(str(self._db_path)) as conn:
            for path in json_files:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    status = data.get("status", "")
                    if status not in ("approved", "rejected"):
                        continue
                    action_type = data.get("action_payload", {}).get(
                        "action_type", "unknown"
                    )
                    teacher_id = data.get("teacher_id", "")
                    payload = json.dumps(data.get("action_payload", {}))
                    created_at = data.get("created_at", datetime.now().isoformat())
                    conn.execute(
                        "INSERT INTO approvals "
                        "(action_type, status, action_payload, teacher_id, created_at, resolved_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (action_type, status, payload, teacher_id, created_at, datetime.now().isoformat()),
                    )
                    migrated += 1
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Skipping migration of %s: %s", path, exc)

        if migrated:
            logger.info("Migrated %d JSON approval records to SQLite", migrated)

    def record_approval(
        self,
        action_type: str,
        approved: bool,
        teacher_id: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Insert a new approval or rejection record."""
        status = "approved" if approved else "rejected"
        now = datetime.now().isoformat()
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT INTO approvals (action_type, status, action_payload, teacher_id, created_at, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    action_type,
                    status,
                    json.dumps(payload or {}),
                    teacher_id,
                    now,
                    now,
                ),
            )

    def get_rates(self) -> dict[str, dict[str, Any]]:
        """Compute approval rates per action type from resolved approvals."""
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT action_type, status, COUNT(*) FROM approvals "
                "WHERE status IN ('approved','rejected') "
                "GROUP BY action_type, status"
            ).fetchall()

        counts: dict[str, dict[str, int]] = {}
        for action_type, status, cnt in rows:
            if action_type not in counts:
                counts[action_type] = {"approved": 0, "rejected": 0}
            counts[action_type][status] = cnt

        rates: dict[str, dict[str, Any]] = {}
        for action_type, c in counts.items():
            total = c["approved"] + c["rejected"]
            if total > 0:
                rates[action_type] = {
                    "approval_rate": c["approved"] / total,
                    "total": total,
                    "approved": c["approved"],
                    "rejected": c["rejected"],
                }
        return rates

    def should_offer_auto(self, action_type: str) -> bool:
        """Check if an action type qualifies for auto-approval offer.

        Student-facing and external-publishing actions are never auto-approved
        regardless of approval rate — teacher review is always required.
        """
        if action_type in _NEVER_AUTO_APPROVE:
            return False
        rates = self.get_rates()
        if action_type not in rates:
            return False
        r = rates[action_type]
        result: bool = r["total"] >= _MIN_SAMPLES and r["approval_rate"] >= _AUTO_THRESHOLD
        return result

    def summarize_for_prompt(self) -> str:
        """Summarize approval patterns for the system prompt."""
        rates = self.get_rates()
        if not rates:
            return ""

        parts = []
        for action_type, r in rates.items():
            if r["total"] >= _MIN_SAMPLES:
                pct = int(r["approval_rate"] * 100)
                if r["approval_rate"] >= _AUTO_THRESHOLD:
                    parts.append(
                        f"- Teacher always approves '{action_type}' ({pct}% rate, {r['total']} samples) "
                        f"— you can offer to auto-approve this action type."
                    )
                elif r["approval_rate"] >= 0.7:
                    parts.append(
                        f"- Teacher usually approves '{action_type}' ({pct}% rate)."
                    )
                else:
                    parts.append(
                        f"- Teacher often rejects '{action_type}' ({pct}% rate) — always ask first."
                    )
        return "\n".join(parts) if parts else ""
