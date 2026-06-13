#!/usr/bin/env python3
"""Run an end-to-end Claw-ED cloud-model harness demo.

This script talks to the same SSE endpoint used by the Mac and iOS UIs. It is
intended for prototype validation: cloud model -> agent tool calls -> streamed
progress -> approval resolution -> generated classroom artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_MESSAGE = """Run a concise Claw-ED prototype demo using the configured cloud model and synthetic or bundled sample materials only.

Use the agent tools, not just prose. Do not inspect private files. Do not use ads, AdSense, AdMob, publishing, package installation, shell commands, Drive upload, or external posting.

Required tool flow:
1. Call brain_stats.
2. Call curriculum_index with action=stats.
3. Call curriculum_index with action=search, query="American Revolution", limit=3.
4. Call brain_dream with dry_run=true and consolidate=false.
5. Call self_distill.
6. Call portfolio_build with topic="American Revolution", course="Grade 8 US History", source_status="synthetic".
7. Call generate_lesson_bundle with topic="American Revolution", grade="8", subject="US History", activity_type="document_analysis", include_images=false.

In the final response, list every file created, summarize whether approvals were required, and state the cloud-provider boundary: the agent runs locally, but model prompts/results go through the configured cloud provider."""


DEFAULT_APPROVAL_TOOLS = {
    "portfolio_build",
    "generate_lesson_bundle",
    "self_distill",
}


def _is_loopback(base_url: str) -> bool:
    return base_url.startswith("http://127.0.0.1") or base_url.startswith("http://localhost")


def _load_token(base_url: str, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    env_token = os.environ.get("CLAWED_API_TOKEN")
    if env_token:
        return env_token
    if _is_loopback(base_url):
        return None
    try:
        from clawed.api.deps import get_api_token

        return get_api_token()
    except Exception:
        return None


def _request_headers(token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _post_json(base_url: str, path: str, payload: dict[str, Any], token: str | None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=body,
        headers=_request_headers(token),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _should_approve(tool_name: str, params: dict[str, Any], allow_tools: set[str]) -> bool:
    if tool_name == "brain_dream":
        return bool(params.get("dry_run", False))
    return tool_name in allow_tools


def _short(value: Any, limit: int = 220) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _dispatch_event(
    event: str,
    payload: dict[str, Any],
    *,
    base_url: str,
    token: str | None,
    allow_tools: set[str],
    events: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    events.append({"event": event, "data": payload})

    if event == "tool_start":
        tool = str(payload.get("tool_name") or "")
        summary.setdefault("tools_started", []).append(tool)
        print(f"tool_start: {tool} {_short(payload.get('params', {}))}")
        return

    if event == "tool_end":
        tool = str(payload.get("tool_name") or "")
        summary.setdefault("tools_finished", []).append(tool)
        files = payload.get("files") or []
        if files:
            summary.setdefault("files", []).extend(str(f) for f in files)
        print(f"tool_end: {tool} ok={payload.get('ok')} {_short(payload.get('summary', ''))}")
        return

    if event == "approval_required":
        approval_id = str(payload.get("approval_id") or "")
        tool = str(payload.get("tool_name") or "")
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        approved = _should_approve(tool, params, allow_tools)
        decision = {"approved": approved, "always": False}
        result = _post_json(base_url, f"/api/approvals/{approval_id}/resolve", decision, token)
        summary.setdefault("approvals", []).append({
            "approval_id": approval_id,
            "tool_name": tool,
            "approved": approved,
            "resolve_result": result,
        })
        print(f"approval_required: {tool} -> {'approved' if approved else 'denied'}")
        return

    if event == "approval_resolved":
        print(f"approval_resolved: {_short(payload)}")
        return

    if event == "progress":
        print(f"progress: {_short(payload.get('message', ''))}")
        return

    if event == "final":
        summary["final_text"] = str(payload.get("text") or "")
        files = payload.get("files") or []
        if files:
            summary.setdefault("files", []).extend(str(f) for f in files)
        print("\nfinal:")
        print(summary["final_text"])
        return

    if event == "error":
        summary.setdefault("errors", []).append(payload)
        print(f"error: {_short(payload)}")
        return

    if event not in {"start", "done"}:
        print(f"{event}: {_short(payload)}")


def run_demo(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    token = _load_token(base_url, args.token)
    if not token and not _is_loopback(base_url):
        raise SystemExit("A token is required for non-loopback demo URLs.")

    message = args.message or DEFAULT_MESSAGE
    allow_tools = set(DEFAULT_APPROVAL_TOOLS)
    allow_tools.update(args.approve_tool or [])

    req = urllib.request.Request(
        base_url + "/api/gateway/chat/stream",
        data=json.dumps({"message": message}).encode("utf-8"),
        headers=_request_headers(token),
        method="POST",
    )

    events: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "base_url": base_url,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "message": message,
        "approved_tools": sorted(allow_tools),
    }

    current_event = "message"
    data_lines: list[str] = []

    def flush_event() -> None:
        nonlocal current_event, data_lines
        if not data_lines:
            current_event = "message"
            return
        raw = "\n".join(data_lines)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        _dispatch_event(
            current_event,
            payload,
            base_url=base_url,
            token=token,
            allow_tools=allow_tools,
            events=events,
            summary=summary,
        )
        current_event = "message"
        data_lines = []

    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=args.timeout_seconds) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").rstrip("\n")
                if not line:
                    flush_event()
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[5:].strip())
            flush_event()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {body}") from exc

    summary["duration_seconds"] = round(time.time() - started, 2)
    summary["events"] = events
    summary["completed_at"] = datetime.now().isoformat(timespec="seconds")
    return summary


def write_report(summary: dict[str, Any]) -> Path:
    try:
        from clawed.paths import workspace_dir

        out_dir = workspace_dir() / "demo_runs"
    except Exception:
        out_dir = Path.home() / ".eduagent" / "workspace" / "demo_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"cloud_harness_demo-{stamp}.json"
    safe_summary = dict(summary)
    safe_summary["events"] = summary.get("events", [])[-80:]
    out_path.write_text(json.dumps(safe_summary, indent=2, default=str), encoding="utf-8")
    return out_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default=None, help="Bearer token for tunnel demos.")
    parser.add_argument("--message", default=None, help="Override the default demo prompt.")
    parser.add_argument(
        "--approve-tool",
        action="append",
        default=[],
        help="Additional tool name to auto-approve for this run.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=420)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    summary = run_demo(args)
    report = write_report(summary)
    summary_view = {
        "report": str(report),
        "duration_seconds": summary.get("duration_seconds"),
        "tools_started": summary.get("tools_started", []),
        "tools_finished": summary.get("tools_finished", []),
        "approvals": summary.get("approvals", []),
        "files": summary.get("files", []),
        "errors": summary.get("errors", []),
    }
    print("\ndemo_summary:")
    print(json.dumps(summary_view, indent=2, default=str))
    return 0 if not summary.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
