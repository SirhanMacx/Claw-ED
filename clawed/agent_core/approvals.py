"""Approval gate — persistence and lifecycle for pending teacher approvals."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

def _default_dir():
    from clawed.paths import data_dir
    return data_dir() / "approvals"

_DEFAULT_DIR = None  # resolved lazily via _default_dir()


@dataclass
class PendingApproval:
    """A pending approval awaiting teacher response."""

    teacher_id: str
    action_description: str
    action_payload: dict[str, Any]
    agent_state: dict[str, Any]
    transport: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    timeout_hours: int = 48
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "teacher_id": self.teacher_id,
            "created_at": self.created_at,
            "action_description": self.action_description,
            "action_payload": self.action_payload,
            "agent_state": self.agent_state,
            "transport": self.transport,
            "timeout_hours": self.timeout_hours,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PendingApproval:
        return cls(
            id=data["id"],
            teacher_id=data["teacher_id"],
            created_at=data["created_at"],
            action_description=data["action_description"],
            action_payload=data["action_payload"],
            agent_state=data["agent_state"],
            transport=data["transport"],
            timeout_hours=data.get("timeout_hours", 48),
            status=data.get("status", "pending"),
        )


class ApprovalManager:
    """Manages PendingApproval lifecycle — create, persist, load, resolve."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._dir = base_dir or _default_dir()
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, approval_id: str) -> Path:
        return self._dir / f"{approval_id}.json"

    def create(
        self,
        *,
        teacher_id: str,
        action_description: str,
        action_payload: dict,
        agent_state: dict,
        transport: str,
        timeout_hours: int = 48,
    ) -> PendingApproval:
        pa = PendingApproval(
            teacher_id=teacher_id,
            action_description=action_description,
            action_payload=action_payload,
            agent_state=agent_state,
            transport=transport,
            timeout_hours=timeout_hours,
        )
        self._save(pa)
        return pa

    def load(self, approval_id: str) -> PendingApproval | None:
        path = self._path(approval_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PendingApproval.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load approval %s: %s", approval_id, e)
            return None

    def approve(self, approval_id: str) -> PendingApproval | None:
        return self._update_status(approval_id, "approved")

    def reject(self, approval_id: str) -> PendingApproval | None:
        return self._update_status(approval_id, "rejected")

    def pending_for_teacher(self, teacher_id: str) -> list[PendingApproval]:
        results = []
        for path in self._dir.glob("*.json"):
            pa = self.load(path.stem)
            if pa and pa.teacher_id == teacher_id and pa.status == "pending":
                results.append(pa)
        return results

    def expire_old(self) -> list[PendingApproval]:
        expired = []
        now = datetime.now()
        for path in self._dir.glob("*.json"):
            pa = self.load(path.stem)
            if pa and pa.status == "pending":
                created = datetime.fromisoformat(pa.created_at)
                if now - created > timedelta(hours=pa.timeout_hours):
                    self._update_status(pa.id, "expired")
                    pa.status = "expired"
                    expired.append(pa)
        return expired

    def _update_status(self, approval_id: str, status: str) -> PendingApproval | None:
        pa = self.load(approval_id)
        if pa is None:
            return None
        pa.status = status
        self._save(pa)
        return pa

    def _save(self, pa: PendingApproval) -> None:
        path = self._path(pa.id)
        path.write_text(json.dumps(pa.to_dict(), indent=2), encoding="utf-8")
