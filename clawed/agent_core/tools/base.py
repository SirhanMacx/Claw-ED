"""Tool protocol and registry for the agent core."""
from __future__ import annotations

import importlib
import inspect
import json
import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


# ── Risk levels for tool capability classification ──────────────────
# Every tool should declare a risk_level attribute. If absent, defaults
# to WRITE_LOCAL for safety (requires approval).

RISK_READ_ONLY = "read_only"             # No side effects — always allowed
RISK_WRITE_LOCAL = "write_local"         # Writes local files — requires approval
RISK_NETWORK_CALL = "network_call"       # External API calls — requires approval
RISK_PACKAGE_INSTALL = "package_install" # pip install — ALWAYS requires confirmation
RISK_EXTERNAL_PUBLISH = "external_publish"  # Posts to external services — ALWAYS requires confirmation
RISK_DAEMON_CONTROL = "daemon_control"   # Starts/stops background processes

# Levels that ALWAYS require explicit teacher confirmation regardless of config
_ALWAYS_REQUIRE_APPROVAL = frozenset({
    RISK_PACKAGE_INSTALL,
    RISK_EXTERNAL_PUBLISH,
})

# Levels that require approval unless teacher has opted into auto-approve
_REQUIRE_APPROVAL_BY_DEFAULT = frozenset({
    RISK_WRITE_LOCAL,
    RISK_NETWORK_CALL,
    RISK_DAEMON_CONTROL,
})


@runtime_checkable
class Tool(Protocol):
    """Protocol that all agent tools must implement."""

    def schema(self) -> dict[str, Any]:
        """Return the JSON Schema definition the LLM sees."""
        ...

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        """Execute the tool and return a result."""
        ...


class ToolRegistry:
    """Discovers, registers, and dispatches tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance. Name extracted from schema."""
        name = tool.schema()["function"]["name"]
        if not hasattr(tool, "risk_level"):
            logger.warning(
                "Tool '%s' has no risk_level — defaults to write_local. "
                "Add explicit risk_level attribute for clarity.", name,
            )
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any],
                      context: AgentContext, *, require_approval: bool = False) -> ToolResult:
        """Execute a tool by name with policy enforcement.

        Every tool is checked against its declared risk_level before execution.
        High-risk tools (package_install, external_publish) ALWAYS require
        teacher confirmation. Medium-risk tools require approval unless the
        teacher has opted into auto-approve mode.

        This enforcement happens HERE in the dispatch path — the LLM cannot
        bypass it regardless of prompt manipulation.
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(text=f"Unknown tool: {name}")

        # ── Policy enforcement ────────────────────────────────────────
        risk = getattr(tool, "risk_level", RISK_WRITE_LOCAL)

        if risk in _ALWAYS_REQUIRE_APPROVAL or require_approval:
            # NEVER auto-approve package installs or external publishing
            approved = await self._check_approval(name, risk, params, context)
            if not approved:
                return self._request_approval(name, params, context)

        elif risk in _REQUIRE_APPROVAL_BY_DEFAULT:
            # Check if auto-approve is enabled
            import os
            auto_approve = os.environ.get("CLAWED_AUTO_APPROVE", "").lower() in ("1", "true", "yes")
            if not auto_approve:
                approved = await self._check_approval(name, risk, params, context)
                if not approved:
                    return self._request_approval(name, params, context)

        # risk == RISK_READ_ONLY → always allowed, no check needed

        try:
            return await tool.execute(params, context)
        except Exception as e:
            logger.error("Tool %s failed: %s", name, e)
            return ToolResult(
                text=f"ERROR: Tool '{name}' failed and did NOT complete. "
                     f"Reason: {e}. "
                     f"Do NOT tell the teacher this action succeeded — it did not. "
                     f"Either retry with corrected parameters or tell the teacher "
                     f"what went wrong."
            )

    async def _check_approval(
        self, tool_name: str, risk_level: str,
        params: dict[str, Any], context: AgentContext,
    ) -> bool:
        """Consume permission for the exact action before it starts."""
        try:
            from clawed.agent_core.approvals import ApprovalManager
            mgr = ApprovalManager()
            teacher_id = context.approval_owner or context.teacher_id
            existing = mgr.consume_approval(teacher_id, tool_name, params)
            if existing:
                logger.info(
                    "Tool '%s' (risk=%s) consumed a one-time approval",
                    tool_name, risk_level,
                )
                return True
        except Exception as exc:
            logger.debug("Approval check failed: %s", exc)

        logger.warning(
            "Tool '%s' BLOCKED (risk=%s) — no approval found",
            tool_name, risk_level,
        )
        return False

    @staticmethod
    def _request_approval(name: str, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.agent_core.approvals import ApprovalManager
        try:
            manager = ApprovalManager()
            owner = context.approval_owner or context.teacher_id
            pending = next((pa for pa in manager.pending_for_teacher(owner)
                            if manager.action_matches(pa, name, params)), None)
            if pending is None:
                pending = manager.create(
                    teacher_id=owner, action_description=name.replace("_", " "),
                    action_payload={"tool_name": name, "params": params},
                    agent_state={}, transport=context.transport,
                )
            return ToolResult(
                text=(f"BLOCKED: Teacher approval required to {pending.action_description}.\n"
                      f"{json.dumps(params, indent=2, ensure_ascii=False)}\n\n"
                      f"Approve once: /approve {pending.id}\nReject: /reject {pending.id}"),
                data=pending.to_dict(), approval_id=pending.id,
            )
        except Exception:
            logger.exception("Could not persist approval request for %s", name)
            return ToolResult(text=f"BLOCKED: Could not request approval for '{name}'. Please retry.")

    def discover_custom(self, dir_path: Path) -> None:
        """Load custom YAML prompt-template tools from a directory."""
        if not dir_path.exists():
            return
        from clawed.agent_core.custom_tools import YAMLPromptTool

        for yaml_file in sorted(dir_path.glob("*.y*ml")):
            tool = YAMLPromptTool.from_file(yaml_file)
            if tool is not None:
                self.register(tool)
                logger.debug("Loaded custom tool: %s", yaml_file.name)

    def discover(self, package_path: Path) -> None:
        """Auto-discover and register tool classes from a package directory.

        Scans ``package_path`` for Python modules, imports each one, and
        registers any class whose name ends with ``Tool`` and that has both
        ``schema()`` and ``execute()`` methods.

        Broken modules are skipped with a warning.
        """
        package_path = Path(package_path)
        # Determine the dotted package name from the path
        # e.g. /…/clawed/agent_core/tools → clawed.agent_core.tools
        parts: list[str] = []
        cur = package_path
        while True:
            init_file = cur / "__init__.py"
            if not init_file.exists():
                break
            parts.insert(0, cur.name)
            cur = cur.parent
        package_name = ".".join(parts) if parts else ""

        for py_file in sorted(package_path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = py_file.stem
            fq_name = f"{package_name}.{module_name}" if package_name else module_name
            try:
                mod = importlib.import_module(fq_name)
            except Exception as exc:
                logger.warning("Skipping broken tool module %s: %s", fq_name, exc)
                continue

            for _attr_name, obj in inspect.getmembers(mod, inspect.isclass):
                if (
                    _attr_name.endswith("Tool")
                    and hasattr(obj, "schema")
                    and hasattr(obj, "execute")
                    and obj.__module__ == mod.__name__
                    and not getattr(obj, "_is_protocol", False)
                ):
                    try:
                        instance = obj()
                        self.register(instance)
                        logger.debug("Discovered tool: %s", _attr_name)
                    except Exception as exc:
                        logger.warning(
                            "Failed to instantiate tool %s: %s", _attr_name, exc
                        )
