#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DIR="$ROOT_DIR/desktop"
APP_NAME="clawed-desktop"
BUNDLE_NAME="Claw-ED"
BUNDLE_ID="com.macxlabs.clawed"
APP_BUNDLE="$DESKTOP_DIR/src-tauri/target/release/bundle/macos/$BUNDLE_NAME.app"

usage() {
  echo "usage: $0 [run|--debug|--logs|--telemetry|--verify]" >&2
}

stop_app() {
  pkill -x "$APP_NAME" >/dev/null 2>&1 || true
}

build_app() {
  (cd "$DESKTOP_DIR" && npm run build)
}

open_app() {
  /usr/bin/open -n "$APP_BUNDLE"
}

stop_app
build_app

case "$MODE" in
  run)
    open_app
    ;;
  --debug|debug)
    lldb -- "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
    ;;
  --logs|logs)
    open_app
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\""
    ;;
  --telemetry|telemetry)
    open_app
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\" OR process == \"$APP_NAME\""
    ;;
  --verify|verify)
    open_app
    sleep 5
    pgrep -x "$APP_NAME" >/dev/null
    curl --fail --silent --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
    ;;
  *)
    usage
    exit 2
    ;;
esac
