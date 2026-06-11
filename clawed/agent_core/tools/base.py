"""Tool protocol and registry for the agent core."""
from __future__ import annotations

import importlib
import inspect
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
RISK_COMMAND_EXEC = "command_exec"       # Arbitrary shell commands — ALWAYS requires confirmation

# Levels that ALWAYS require explicit teacher confirmation regardless of config
_ALWAYS_REQUIRE_APPROVAL = frozenset({
    RISK_PACKAGE_INSTALL,
    RISK_EXTERNAL_PUBLISH,
    RISK_COMMAND_EXEC,
})

# Levels that require approval unless teacher has opted into auto-approve
_REQUIRE_APPROVAL_BY_DEFAULT = frozenset({
    RISK_WRITE_LOCAL,
    RISK_NETWORK_CALL,
    RISK_DAEMON_CONTROL,
})


def _preview_params(params: dict[str, Any], limit: int = 400) -> dict[str, Any]:
    """Truncated, display-safe copy of tool params for approval cards."""
    preview: dict[str, Any] = {}
    for key, value in params.items():
        text = value if isinstance(value, str) else repr(value)
        preview[key] = text if len(text) <= limit else text[:limit] + "…"
    return preview


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
        if name in self._tools:
            # A silent collision shadows a tool (write_file was shadowed by
            # a workspace-scoped duplicate for a while). Make it loud.
            logger.warning(
                "Tool name collision: '%s' (%s) replaces %s",
                name, type(tool).__name__, type(self._tools[name]).__name__,
            )
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any],
                      context: AgentContext) -> ToolResult:
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

        if risk in _ALWAYS_REQUIRE_APPROVAL:
            # NEVER auto-approve package installs or external publishing
            approved = await self._check_approval(name, risk, params, context)
            if not approved:
                return ToolResult(
                    text=f"BLOCKED: '{name}' requires explicit teacher approval "
                         f"(risk level: {risk}). Ask the teacher to confirm "
                         f"before proceeding."
                )

        elif risk in _REQUIRE_APPROVAL_BY_DEFAULT:
            # Check if auto-approve is enabled
            import os
            auto_approve = os.environ.get("CLAWED_AUTO_APPROVE", "").lower() in ("1", "true", "yes")
            if not auto_approve:
                approved = await self._check_approval(name, risk, params, context)
                if not approved:
                    return ToolResult(
                        text=f"BLOCKED: '{name}' requires teacher approval "
                             f"(risk level: {risk}). The teacher can enable "
                             f"auto-approve with CLAWED_AUTO_APPROVE=1 for "
                             f"low-risk write operations."
                    )

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
        """Check if the teacher has approved this action.

        Returns True if approved, False if blocked.

        Resolution order:
        1. A *standing* approval ("Always allow") for this tool — scoped to
           the exact params signature for ``approval_scope = "per_params"``
           tools (e.g. run_command keys on the exact command string).
        2. If the teacher is live (``context.event_callback`` set), pause
           the loop, surface an approval card, and await their decision —
           Allow once / Always allow / Deny — like Claude Code / Codex.
        3. Otherwise fail closed (blocked).
        """
        tool = self._tools.get(tool_name)
        signature = self._params_signature(tool, params)
        teacher_id = getattr(context, "teacher_id", "default")

        try:
            from clawed.agent_core.approvals import ApprovalManager
            mgr = ApprovalManager()
            existing = mgr.get_standing_approval(
                teacher_id, tool_name, params_signature=signature,
            )
            if existing:
                logger.info(
                    "Tool '%s' (risk=%s) approved via standing approval",
                    tool_name, risk_level,
                )
                return True
        except Exception as exc:
            logger.debug("Approval check failed: %s", exc)

        # ── Interactive path — teacher is live on a chat stream ─────────
        if context.event_callback is not None:
            decision = await self._request_interactive_approval(
                tool_name, risk_level, params, signature, context,
            )
            if decision is not None:
                return decision

        logger.warning(
            "Tool '%s' BLOCKED (risk=%s) — no approval found",
            tool_name, risk_level,
        )
        return False

    @staticmethod
    def _params_signature(tool: Tool | None, params: dict[str, Any]) -> str | None:
        """Stable signature for per-params approval scoping.

        Tools that declare ``approval_scope = "per_params"`` get an
        "Always allow" scoped to these exact parameters (e.g. the exact
        shell command) instead of a blanket tool-wide grant.
        """
        if tool is None or getattr(tool, "approval_scope", "tool") != "per_params":
            return None
        custom = getattr(tool, "approval_signature", None)
        if callable(custom):
            try:
                return str(custom(params))
            except Exception:
                pass
        import json as _json
        try:
            return _json.dumps(params, sort_keys=True, default=str)
        except Exception:
            return str(sorted(params.items()))

    async def _request_interactive_approval(
        self, tool_name: str, risk_level: str, params: dict[str, Any],
        signature: str | None, context: AgentContext,
    ) -> bool | None:
        """Pause for a live teacher decision. None means 'no decision' (fail closed)."""
        try:
            from clawed.agent_core.approval_broker import ApprovalBroker
            from clawed.agent_core.approvals import ApprovalManager

            tool = self._tools.get(tool_name)
            describe = getattr(tool, "approval_description", None)
            if callable(describe):
                try:
                    description = str(describe(params))
                except Exception:
                    description = f"Run tool '{tool_name}'"
            else:
                description = f"Run tool '{tool_name}'"

            mgr = ApprovalManager()
            pa = mgr.create(
                teacher_id=context.teacher_id,
                action_description=description,
                action_payload={
                    "tool_name": tool_name,
                    "params_signature": signature or "*",
                    "risk_level": risk_level,
                },
                agent_state={},
                transport=context.transport,
            )

            broker = ApprovalBroker.instance()
            broker.register(pa.id)
            context.emit_event("approval_required", {
                "approval_id": pa.id,
                "tool_name": tool_name,
                "description": description,
                "params": _preview_params(params),
                "risk_level": risk_level,
            })

            decision = await broker.wait(pa.id)
            if decision is None:
                mgr._update_status(pa.id, "expired")
                context.emit_event("approval_resolved", {
                    "approval_id": pa.id, "approved": False, "reason": "timeout",
                })
                return False

            if decision.approved and decision.always:
                # Leave status "approved" → acts as a standing approval,
                # scoped by params_signature for per_params tools.
                mgr.approve(pa.id)
            elif decision.approved:
                # One-time grant — must NOT become standing.
                mgr._update_status(pa.id, "consumed")
            else:
                mgr.reject(pa.id)

            context.emit_event("approval_resolved", {
                "approval_id": pa.id,
                "approved": decision.approved,
                "always": decision.always,
            })
            return decision.approved
        except Exception as exc:
            logger.warning("Interactive approval failed for %s: %s", tool_name, exc)
            return None

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
