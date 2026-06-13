# Claw-ED Trust And Security

This document is the plain-language security position for teacher pilots and
district IT review. It should stay conservative: say what the app actually does,
what remains configurable, and what still depends on district policy.

## Operating Boundary

- The Mac app is a Tauri shell that talks to the local agent over
  `http://127.0.0.1:8000`.
- The agent is supervised by the app, or the app adopts an already-running local
  agent on the same port.
- Generated files are written to local paths, usually under
  `~/.eduagent/workspace`.
- The app does not require teachers to upload a whole course folder to a web
  product.
- The product should be described as a local AI-agent harness: local control
  plane, local workspace, provider-selected model calls.

## AI Provider Boundary

- Claw-ED uses the AI provider configured for the local agent.
- Provider setup is a district or teacher configuration decision, not hard-coded
  into the Mac UI.
- Style learning reads local materials and sends only short excerpts for
  analysis. It should not send full folders wholesale.
- The Settings readiness report records provider/model status, but never prints
  API keys.
- If the configured provider is local Ollama at `http://localhost:11434`, model
  prompts stay on the Mac.
- If the configured provider is OpenRouter, Ollama Cloud, Anthropic, OpenAI,
  Google, or another cloud model provider, prompts and relevant context are sent
  to that provider. That provider's terms, privacy policy, logging, retention,
  and downstream routing rules apply.
- OpenRouter is a cloud model router. Depending on the selected model, data may
  be processed by OpenRouter and the downstream model provider.
- District pilots should choose and approve the model provider before classroom
  use.

## API Keys

- Teachers can run `clawed setup` for guided setup.
- Technical users can run `clawed config set-key PROVIDER YOUR_KEY`.
- Supported provider names are `openrouter`, `ollama`, `anthropic`, `openai`,
  and `google`.
- Claw-ED checks environment variables first, then OS keychain, then
  `~/.eduagent/secrets.json`.
- `~/.eduagent/secrets.json` is written with user-only file permissions when
  the keychain is unavailable.
- API keys must never be included in screenshots, support tickets, readiness
  reports, or logs.

## Approval Model

- Risky actions, including shell commands and file writes, require approval.
- "Always allow" is scoped to the exact command or file action. Changed
  parameters ask again.
- The Skills view reads the live tool registry so teachers can inspect what the
  agent can do.
- `run_command` must remain classified as `command_exec`.

### Local vs. remote approval policy (defense against a leaked token)

The public tunnel's only barrier is the device token, so a turn that arrives
over it (Cloudflare stamps a `Cf-Ray` header — see `deps._via_cloudflare_edge`)
is held to a **strictly tighter** approval policy than a local turn on the Mac:

- A remote turn **never honors a standing "Always allow"** — every risky action
  is confirmed fresh on the device, so a leaked token can't ride a prior grant
  into blanket shell/file access.
- A remote "Always allow" tap **cannot create** a standing grant; it is
  downgraded to one-time (enforced both in the live approval path via
  `context.is_remote` and at the resolve endpoint via the resolving request's
  own `Cf-Ray`).
- `CLAWED_AUTO_APPROVE` (a local convenience) **never applies to a remote turn**.

Standing grants and auto-approve are therefore a *local-Mac-only* convenience.
This is a pure tightening: it can only add confirmation friction for the remote
path, never remove it. Covered by `tests/test_desktop_agent_tools.py`
(`test_remote_turn_ignores_standing_approval`,
`test_remote_always_does_not_create_standing_grant`,
`test_remote_turn_disables_auto_approve`).

## Keychain And Secrets

- The general file tools (`read_file`/`write_file`/`edit_file`/`list_directory`)
  are bounded to the teacher's home directory (a `..` traversal or absolute path
  that resolves outside home is refused), and a **credential denylist** refuses
  any path segment that names a secret store — `.ssh`, `.gnupg`, `.aws`,
  `.azure`, `.gcloud`, `.kube`, `.docker`, `.git-credentials`, `.env`, `.netrc`,
  `.npmrc`, `.pgpass`, key files, `*.pem/.p8/.p12/.key`, etc. — for reads as
  well as writes, so the agent can't exfiltrate or clobber them. See
  `clawed/agent_core/tools/mac_files.py::_resolve` and the denylist tests.
- The sidecar sets `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`.
- The agent should not touch the login keychain.
- The iPhone pairing token lives in `~/.eduagent/api_token`.
- The pairing token is embedded in the QR code and is not displayed as text in
  the Mac app or readiness report.

## Remote Pairing

- The Pair iPhone screen points to `https://clawed.macxlabs.app`.
- The Mac app only exposes the remote pairing token through the QR code.
- A paired phone should be treated as a remote control for the teacher's Mac.
- District pilots should decide whether the remote route is enabled, blocked, or
  limited to trusted networks.

## Local Data

Default local paths:

- `~/.eduagent/`
- `~/.eduagent/workspace/`
- `~/.eduagent/api_token`

Teachers and IT can delete local Claw-ED state by removing `~/.eduagent` after
closing the app. That removes local profiles, workspace outputs, and pairing
state. It does not delete files the teacher asked Claw-ED to write elsewhere.

## Logs And Reports

- `desktop/scripts/preflight.sh` prints status, provider/model, tool count,
  approval risk classification, signing state, and notarization state.
- The readiness report is written to
  `~/.eduagent/workspace/clawed-readiness-report.md`.
- Neither path should print API keys, account tokens, or the pairing token.
- Support intake should ask for the readiness report first, then request logs
  only when needed.

## District Controls

Recommended controls for managed pilots:

- Enroll Macs through Apple School Manager or Apple Business.
- Use MDM for FileVault, OS updates, firewall, app installation, permissions,
  and network policy.
- Install only Developer ID signed and notarized Claw-ED builds.
- Use district-approved AI provider accounts and billing controls.
- Keep the remote pairing URL policy explicit.
- Review generated materials before classroom use, especially assessments,
  accommodations, legal content, and sensitive student contexts.

## Known Limits

- This is not an offline-only product if the configured AI provider is remote.
- "Local agent" does not mean cloud providers never see data. It means the
  agent process and permission harness run locally; cloud model calls still send
  prompt/context to the chosen provider.
- The app can act on local files after approval, so teacher training must cover
  approvals and review.
- Notarization and Developer ID signing are distribution gates, not local code
  quality gates.
- The Mac app does not replace district policy for student data, records
  retention, accessibility, or AI acceptable use.
