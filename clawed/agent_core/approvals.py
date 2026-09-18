"""Approval gate — persistence and lifecycle for pending teacher approvals."""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

def _default_dir() -> Path:
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
        self._dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, approval_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", approval_id):
            raise ValueError("Invalid approval ID")
        return self._dir / f"{approval_id}.json"

    @contextmanager
    def _lock(self, approval_id: str) -> Iterator[bool]:
        """Fail closed if another process is resolving/consuming this record."""
        lock_path = self._path(approval_id).with_suffix(".lock")
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            yield False
            return
        try:
            yield True
        finally:
            os.close(fd)
            lock_path.unlink(missing_ok=True)

    @staticmethod
    def _expired(pa: PendingApproval) -> bool:
        try:
            created = datetime.fromisoformat(pa.created_at)
            return datetime.now(created.tzinfo) >= created + timedelta(hours=pa.timeout_hours)
        except (ValueError, TypeError, OverflowError):
            return True

    @staticmethod
    def action_matches(pa: PendingApproval, tool_name: str, params: dict[str, Any]) -> bool:
        """Legacy unscoped approvals cannot authorize a new action."""
        payload = pa.action_payload
        if payload.get("tool_name") != tool_name or not isinstance(payload.get("params"), dict):
            return False
        try:
            expected = json.dumps(payload["params"], sort_keys=True, allow_nan=False)
            actual = json.dumps(params, sort_keys=True, allow_nan=False)
            return expected == actual
        except (TypeError, ValueError):
            return False

    def create(
        self,
        *,
        teacher_id: str,
        action_description: str,
        action_payload: dict[str, Any],
        agent_state: dict[str, Any],
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
        try:
            path = self._path(approval_id)
            if path.is_symlink():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            pa = PendingApproval.from_dict(data)
            if pa.id != approval_id or not isinstance(pa.action_payload, dict):
                return None
            return pa
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.warning("Failed to load approval %s: %s", approval_id, e)
            return None

    def approve(self, approval_id: str, *, teacher_id: str) -> PendingApproval | None:
        return self._resolve(approval_id, teacher_id, "approved")

    def reject(self, approval_id: str, *, teacher_id: str) -> PendingApproval | None:
        return self._resolve(approval_id, teacher_id, "rejected")

    def pending_for_teacher(self, teacher_id: str) -> list[PendingApproval]:
        results = []
        for path in self._dir.glob("*.json"):
            pa = self.load(path.stem)
            if pa and pa.teacher_id == teacher_id and pa.status == "pending" and not self._expired(pa):
                results.append(pa)
        return results

    def expire_old(self) -> list[PendingApproval]:
        expired = []
        for path in self._dir.glob("*.json"):
            if self.load(path.stem) is None:
                continue
            with self._lock(path.stem) as locked:
                pa = self.load(path.stem) if locked else None
                if pa and pa.status in ("pending", "approved") and self._expired(pa):
                    pa.status = "expired"
                    self._save(pa)
                    expired.append(pa)
        return expired

    def consume_approval(
        self, teacher_id: str, tool_name: str, params: dict[str, Any],
    ) -> PendingApproval | None:
        """Atomically consume one unexpired approval for this exact action."""
        for path in self._dir.glob("*.json"):
            if self.load(path.stem) is None:
                continue
            with self._lock(path.stem) as locked:
                pa = self.load(path.stem) if locked else None
                if not pa or pa.teacher_id != teacher_id or pa.status != "approved":
                    continue
                if self._expired(pa):
                    pa.status = "expired"
                    self._save(pa)
                    continue
                if not self.action_matches(pa, tool_name, params):
                    continue
                pa.status = "consumed"
                self._save(pa)
                return pa
        return None

    def _resolve(self, approval_id: str, teacher_id: str, status: str) -> PendingApproval | None:
        if self.load(approval_id) is None:
            return None
        with self._lock(approval_id) as locked:
            pa = self.load(approval_id) if locked else None
            if not pa or pa.teacher_id != teacher_id or pa.status != "pending":
                return None
            if self._expired(pa):
                pa.status = "expired"
                self._save(pa)
                return None
            pa.status = status
            self._save(pa)
            return pa

    def _save(self, pa: PendingApproval) -> None:
        path = self._path(pa.id)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self._dir, suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            try:
                json.dump(pa.to_dict(), f, indent=2, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
