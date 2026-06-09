#!/bin/bash
# Install the Claw-ED always-on launchd services for the current user:
#   • com.macxlabs.clawed-agent  — the FastAPI agent on 127.0.0.1:8000
#   • com.macxlabs.clawed-tunnel — the named Cloudflare tunnel (public ingress)
# Both RunAtLoad + KeepAlive, so the Mac serves clawed.macxlabs.app from boot,
# survives crashes, and needs no manual start. Idempotent — re-run to update.
#
#   bash scripts/launchd/install.sh
set -euo pipefail

UID_NUM="$(id -u)"
SUPPORT="$HOME/Library/Application Support/MacxLabs"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$SUPPORT" "$AGENTS"

# --- agent wrapper (keeps the python invocation out of the plist) ----------
cat > "$SUPPORT/run-agent.sh" <<'SH'
#!/bin/bash
# Claw-ED agent, launched by launchd. Binds loopback only; the named Cloudflare
# tunnel is the sole public ingress (and requires the device token — see
# clawed/api/deps.local_bypass_ok). The keyring-timeout fix (clawed/config.py)
# means this starts cleanly even though launchd has no GUI keychain session.
set -euo pipefail
cd "$HOME/Projects/Claw-ED"
export EDUAGENT_LOCAL_AUTH_BYPASS=1
export EDUAGENT_EMBEDDER=tfidf
# Never touch the macOS Keychain from this headless service — it can't be
# serviced without a GUI session and pops a password prompt on each launch.
# The provider key is read from ~/.eduagent/secrets.json instead.
export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring
exec /opt/homebrew/bin/python3 -c 'import sys; sys.argv=["clawed","serve","--host","127.0.0.1","--port","8000","--skip-setup"]; from clawed._entry_router import main; main()'
SH
chmod +x "$SUPPORT/run-agent.sh"

# --- agent plist -----------------------------------------------------------
cat > "$AGENTS/com.macxlabs.clawed-agent.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.macxlabs.clawed-agent</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>$SUPPORT/run-agent.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>/tmp/clawed-agent-launchd.log</string>
  <key>StandardErrorPath</key><string>/tmp/clawed-agent-launchd.log</string>
</dict></plist>
PLIST

# --- tunnel plist ----------------------------------------------------------
cat > "$AGENTS/com.macxlabs.clawed-tunnel.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.macxlabs.clawed-tunnel</string>
  <key>ProgramArguments</key><array>
    <string>/opt/homebrew/bin/cloudflared</string>
    <string>tunnel</string><string>--config</string>
    <string>$HOME/.cloudflared/config.yml</string>
    <string>run</string><string>clawed</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>/tmp/clawed-tunnel-launchd.log</string>
  <key>StandardErrorPath</key><string>/tmp/clawed-tunnel-launchd.log</string>
</dict></plist>
PLIST

# --- (re)load --------------------------------------------------------------
for svc in com.macxlabs.clawed-agent com.macxlabs.clawed-tunnel; do
  launchctl bootout "gui/$UID_NUM/$svc" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_NUM" "$AGENTS/$svc.plist"
  launchctl enable "gui/$UID_NUM/$svc"
done
echo "installed + loaded: com.macxlabs.clawed-agent, com.macxlabs.clawed-tunnel"
