#!/usr/bin/env bash
set -euo pipefail

BASE="${CLAWED_AGENT_URL:-http://127.0.0.1:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP="${CLAWED_APP:-$DESKTOP_DIR/src-tauri/target/release/bundle/macos/Claw-ED.app}"
TMP="$(mktemp -d)"
failures=0
warnings=0

cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

pass() { printf 'PASS %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; warnings=$((warnings + 1)); }
bad() { printf 'FAIL %s\n' "$*"; failures=$((failures + 1)); }

printf 'Claw-ED Mac preflight\n'
printf 'Agent: %s\n' "$BASE"
printf 'App:   %s\n\n' "$APP"

if curl -fsS --max-time 5 "$BASE/api/health" -o "$TMP/health.json"; then
  pass "agent health endpoint answers"
  if ! python3 - "$TMP/health.json" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
status = data.get("status")
provider = data.get("llm_provider") or "unknown"
model = data.get("llm_model") or "unknown"
connected = bool(data.get("llm_connected"))
print(f"INFO provider={provider} model={model} llm_connected={connected}")
if status != "ok":
    print(f"FAIL health status is {status!r}")
    raise SystemExit(1)
print("PASS health status is ok")
if not connected:
    print("FAIL LLM provider is not connected")
    raise SystemExit(1)
print("PASS LLM provider is connected")
PY
  then
    failures=$((failures + 1))
  fi
else
  bad "agent health endpoint is not reachable"
fi

if curl -fsS --max-time 8 "$BASE/api/agent/tools" -o "$TMP/tools.json"; then
  pass "tool registry endpoint answers"
  if ! python3 - "$TMP/tools.json" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
tools = data.get("tools") or []
names = {tool.get("name"): tool for tool in tools}
print(f"INFO tool_count={len(tools)}")
if len(tools) < 20:
    print("FAIL tool registry is unexpectedly small")
    raise SystemExit(1)
print("PASS tool registry has production breadth")
run_command = names.get("run_command")
if not run_command:
    print("FAIL run_command tool is missing")
    raise SystemExit(1)
risk = run_command.get("risk_level")
print(f"INFO run_command_risk={risk}")
if risk != "command_exec":
    print("FAIL run_command is not classified as command_exec")
    raise SystemExit(1)
print("PASS run_command stays approval-gated")
PY
  then
    failures=$((failures + 1))
  fi
else
  bad "tool registry endpoint is not reachable"
fi

if [[ -s "$HOME/.eduagent/api_token" ]]; then
  pass "iPhone pairing token exists (value hidden)"
else
  warn "iPhone pairing token is missing; open the Mac app and restart the agent before pairing"
fi

if [[ -s "$HOME/.eduagent/workspace/clawed-readiness-report.md" ]]; then
  pass "district readiness report has been exported"
else
  warn "district readiness report has not been exported yet"
fi

if pids="$(lsof -nP -tiTCP:8000 -sTCP:LISTEN 2>/dev/null)" && [[ -n "$pids" ]]; then
  pass "a local process is listening on port 8000"
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    db_handles="$(lsof -p "$pid" 2>/dev/null | grep -Ec '\\.db|\\.sqlite|\\.sqlite3' || true)"
    printf 'INFO pid=%s sqlite_handles=%s\n' "$pid" "$db_handles"
  done <<< "$pids"
else
  warn "no process was found listening on port 8000 after health checks"
fi

if [[ -d "$APP" ]]; then
  pass "built .app exists"
  if codesign --verify --deep --strict "$APP" >/dev/null 2>&1; then
    pass "codesign verification passes"
  else
    warn "codesign verification did not pass for $APP"
  fi

  signature="$(codesign -dv "$APP" 2>&1 || true)"
  authority="$(printf '%s\n' "$signature" | awk -F= '/Authority=/ {print $2; exit}')"
  if [[ "$authority" == Developer\ ID\ Application:* ]]; then
    pass "app is signed with Developer ID"
  else
    warn "app is not Developer ID signed; broad district distribution still needs Developer ID signing"
  fi

  if command -v xcrun >/dev/null 2>&1 && xcrun stapler validate "$APP" >/dev/null 2>&1; then
    pass "notarization ticket is stapled"
  else
    warn "notarization ticket is not stapled; broad district distribution still needs notarization"
  fi
else
  warn "built .app not found at $APP"
fi

printf '\n'
if [[ "$failures" -eq 0 ]]; then
  printf 'READY controlled teacher pilot passed with %s warning(s).\n' "$warnings"
else
  printf 'NOT READY %s failure(s), %s warning(s).\n' "$failures" "$warnings"
fi

exit "$failures"
