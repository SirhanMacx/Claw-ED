#!/bin/bash
# Stop + remove the Claw-ED always-on launchd services. Leaves the tunnel
# config, credentials, and device token in place (only the services go away).
#
#   bash scripts/launchd/uninstall.sh
set -euo pipefail
UID_NUM="$(id -u)"
for svc in com.macxlabs.clawed-agent com.macxlabs.clawed-tunnel; do
  launchctl bootout "gui/$UID_NUM/$svc" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$svc.plist"
done
echo "removed: com.macxlabs.clawed-agent, com.macxlabs.clawed-tunnel"
