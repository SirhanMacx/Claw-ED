#!/bin/bash
# Build the self-contained clawed agent sidecar with PyInstaller.
#
#   desktop/agent-bundle/build.sh [--smoke-port 8899]
#
# Output: desktop/src-tauri/agent/clawed-agent/   (onedir bundle)
# The Tauri bundle ships that directory as a macOS resource and the
# supervisor (sidecar.rs) prefers it over any system install.
#
# Requires: uv (https://docs.astral.sh/uv/). No keychain, no sudo.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
VENV="${CLAWED_BUNDLE_VENV:-/tmp/clawed-bundle-venv}"
DIST="$REPO/desktop/src-tauri/agent"
WORK="${CLAWED_BUNDLE_WORK:-/tmp/clawed-pyi-build}"
SMOKE_PORT="${2:-8899}"

echo "── 1/4 build venv ($VENV)"
# The default ~/.cache/uv on this Mac grows AppleDouble (._*) turds that
# break wheel RECORD validation — use a clean per-build cache instead.
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/clawed-bundle-uv-cache}"
uv venv "$VENV" --python 3.12 -q --allow-existing
# (no [formats] extra: xlrd's wheel RECORD is broken on this box and .xls
# ingestion isn't needed by the sidecar)
uv pip install -q --python "$VENV/bin/python" "$REPO[google,qr,keyring]" pyinstaller

echo "── 2/4 pyinstaller"
rm -rf "$DIST/clawed-agent"
"$VENV/bin/python" -m PyInstaller "$HERE/clawed-agent.spec" \
  --distpath "$DIST" --workpath "$WORK" -y --log-level WARN

echo "── 3/4 smoke test (clean env, no repo cwd, port $SMOKE_PORT)"
SMOKE_HOME="$(mktemp -d /tmp/clawed-bundle-smoke.XXXX)"
(
  cd /
  # Deliberately NO EDUAGENT_DATA_DIR and cwd=/ — the entry script must
  # default the data dir itself (a relative ./clawed_data fallback once
  # crashed the GUI-spawned agent with cwd=/).
  env -i HOME="$SMOKE_HOME" \
    EDUAGENT_LOCAL_AUTH_BYPASS=1 \
    "$DIST/clawed-agent/clawed-agent" serve --host 127.0.0.1 \
    --port "$SMOKE_PORT" --skip-setup >"$SMOKE_HOME/agent.log" 2>&1 &
  echo $! >"$SMOKE_HOME/agent.pid"
)
PID="$(cat "$SMOKE_HOME/agent.pid")"
trap 'kill "$PID" 2>/dev/null || true' EXIT
ok=""
for _ in $(seq 1 30); do
  sleep 1
  if curl -sf -m 2 "http://127.0.0.1:$SMOKE_PORT/api/health" >/dev/null; then
    ok=1; break
  fi
done
if [ -z "$ok" ]; then
  echo "SMOKE FAILED — log tail:"; tail -30 "$SMOKE_HOME/agent.log"; exit 1
fi
curl -s -m 5 "http://127.0.0.1:$SMOKE_PORT/api/health"; echo
TOOLS_JSON="$(curl -s -m 10 "http://127.0.0.1:$SMOKE_PORT/api/agent/tools" || true)"
echo "$TOOLS_JSON" | head -c 200; echo
kill "$PID" 2>/dev/null || true

echo "── 4/4 done"
du -sh "$DIST/clawed-agent"
