# Claw-ED always-on services (launchd)

`install.sh` sets up two user LaunchAgents so the Mac serves
`https://clawed.macxlabs.app` automatically — from boot, surviving crashes, with
no manual start:

- **com.macxlabs.clawed-agent** — the agent on `127.0.0.1:8000` (loopback only).
- **com.macxlabs.clawed-tunnel** — the named Cloudflare tunnel: the *sole* public
  ingress, and it requires the device token (see
  `clawed/api/deps.local_bypass_ok` — tunnel traffic carries a `Cf-Ray` header,
  so it never gets the loopback bypass).

```bash
bash scripts/launchd/install.sh     # install / update + load
bash scripts/launchd/uninstall.sh   # stop + remove (leaves config + token)
launchctl list | grep clawed        # status (pid + last exit code)
tail -f /tmp/clawed-agent-launchd.log /tmp/clawed-tunnel-launchd.log
```

The agent starts cleanly under launchd even with no GUI keychain session thanks
to the keyring-timeout fix in `clawed/config.py` (a hung Keychain call falls
through to `~/.eduagent/secrets.json` after 2s).

**Prereqs** (one-time, see `docs/product/PROTOTYPE.md`): `cloudflared tunnel
login`, the `clawed` tunnel + `~/.cloudflared/config.yml` created, and the
agent's provider key in `~/.eduagent/secrets.json`.
