# Claw-ED District Rollout

Claw-ED should be positioned as a free local AI-agent harness for managed Macs,
not as another browser subscription that asks schools to upload materials first.
The district argument is simple: put a managed Mac mini on a teacher's desk, run
the agent locally, keep classroom files local by default, connect only the model
provider the district approves, and give the teacher an agent that can make,
organize, and adapt materials on that machine.

## The Pitch

For teachers:

- Claw-ED works on the Mac where the teacher's files already live.
- It can learn from real lesson folders and match the teacher's structure.
- It can create and organize files with approval gates instead of making the
  teacher copy text between tabs.
- It can be paired with an iPhone so the teacher can drive the desk Mac while
  moving around the room.
- It is bring-your-own-provider: OpenRouter for easy hosted models, Ollama local
  for privacy/cost-sensitive technical users, or any district-approved provider.

For districts:

- The app is free for the teacher pilot.
- The most sensitive boundary is clear: the Mac app talks to the agent on
  `127.0.0.1`, generated files stay on the teacher's Mac by default, and cloud
  model calls share prompt/context with the configured provider and, for model
  routers such as OpenRouter, the downstream model provider used for that
  request.
- Managed Macs can be deployed through Apple School Manager or Apple Business
  plus MDM, which is already the normal Apple fleet model.
- IT can run `desktop/scripts/preflight.sh` and export an in-app readiness report
  before expanding a pilot.

For MacxLabs:

- The free app creates trust, usage, and teacher proof.
- Paid work should stay downstream: optional district services, support,
  professional development, or fully generated and reviewed teacher materials.
- Do not sell partial generated materials or unreviewed archives.

## Why Mac Mini

The credible hardware case is not "AI needs a shiny computer." It is:

- A Mac mini gives each teacher a stable, managed classroom hub.
- The agent can run continuously without depending on a teacher's personal
  laptop battery, browser tabs, or student device policies.
- A district can manage the device with Apple School Manager or Apple Business
  and its MDM service.
- Apple silicon Macs support modern platform security features, including
  managed device attestation on supported macOS versions.

Do not quote a fixed Mac mini price in launch copy without rechecking Apple's
current education store. Apple's current store pages and older newsroom launch
pricing can differ by configuration and date.

## What Ships In The Pilot

- Claw-ED Mac app, Developer ID signed and notarized for non-developer installs.
- Local Python agent bundled inside the app, with fallback to an existing
  `clawed` install only for development.
- Loopback-only desktop UI traffic.
- Bring-your-own-provider setup and docs: OpenRouter, Ollama local, Ollama
  Cloud, Anthropic, OpenAI, and Google.
- Approval-gated shell and file-write tools.
- Style learning from teacher folders.
- Workspace artifact collection with Open and Finder actions.
- Pair iPhone screen with QR code that hides the token.
- Settings export for `~/.eduagent/workspace/clawed-readiness-report.md`.
- `desktop/scripts/preflight.sh` for IT verification.
- Trust and security explainer in `docs/product/TRUST_AND_SECURITY.md`.
- Harness/provider explainer in `docs/product/AGENT_HARNESS.md`.

## Pilot Sequence

1. Pick 3-5 high-output teachers in different subjects.
2. Give each teacher one managed Mac mini or a managed test Mac.
3. Install the notarized Claw-ED DMG through MDM or a supervised IT install.
4. Configure the district-approved AI provider key. If using OpenRouter or
   Ollama Cloud, document that prompts/context are sent to that cloud provider.
   If using OpenRouter, also document that the downstream model provider may
   process the request. If using local Ollama, verify the model is installed on
   the Mac.
5. Run `desktop/scripts/preflight.sh` on each pilot Mac.
6. Open Claw-ED, export the readiness report, and save it with the pilot record.
7. Have each teacher teach Claw-ED one real materials folder.
8. Run three classroom workflows:
   - build tomorrow's Do-Now and handout from existing materials;
   - reorganize or package a generated lesson folder;
   - pair iPhone and trigger one safe classroom-prep action remotely.
9. Collect time saved, artifact quality, approval friction, and support tickets.
10. Decide expansion only after the pilot has real teacher evidence.

## IT Deployment Checklist

- Enroll devices through Apple School Manager or Apple Business when possible.
- Apply MDM configuration for FileVault, updates, firewall, Gatekeeper, and
  app installation.
- Install a Developer ID signed and notarized Claw-ED DMG.
- Confirm the app launches without a quarantine or Gatekeeper warning.
- Confirm `GET http://127.0.0.1:8000/api/health` answers locally.
- Confirm `/api/agent/tools` returns the full registry.
- Confirm `run_command` remains `command_exec`.
- Confirm the provider is connected.
- Confirm the provider data boundary is documented for the pilot: local Ollama
  stays local; OpenRouter/Ollama Cloud/other cloud providers receive
  prompt/context; OpenRouter may route to a downstream model provider.
- Confirm no API keys or pairing tokens are printed in logs, reports, or support
  screenshots.
- Export the readiness report from Settings.

## Success Metrics

Minimum pilot bar:

- 90 percent of pilot launches reach "Agent ready" without IT intervention.
- Each teacher creates at least three usable classroom artifacts in the first
  week.
- Teachers report at least one saved prep period per week.
- No teacher needs to upload whole course folders to a third-party web app.
- Approval prompts are understood and do not block normal workflows.
- IT can reproduce readiness using the preflight script and report.

Expansion bar:

- A department lead can teach Claw-ED a folder and produce a usable lesson set
  without MacxLabs present.
- The district can deploy and update the app through its normal Mac management
  path.
- Support issues are about curriculum workflow, not broken installation.

## Remaining Gates Before Public Download

- Developer ID certificate and notarized DMG: built internally, but not public.
- Public landing page: live with a "coming soon" download state.
- GitHub release asset: pulled from public download until testing is complete.
- Mac prototype test pass on the teacher workflow.
- Companion iOS path test pass.
- A stable update channel or MDM update package.
- District-approved AI provider configuration guidance.
- A short support form that asks for the readiness report before collecting logs.
- A short district pilot packet that says exactly what is local, what goes to
  the AI provider, and what the app can do on the Mac.

## Sources To Keep Current

- Apple Mac mini education store:
  https://www.apple.com/us-edu/shop/buy-mac/mac-mini
- Apple Platform Deployment:
  https://support.apple.com/guide/deployment/welcome/web
- Apple School Manager / Apple Business device deployment:
  https://support.apple.com/guide/deployment/deploy-devices-apple-school-manager-business-depd3a5dd518/web
- Apple Managed Device Attestation:
  https://support.apple.com/guide/deployment/managed-device-attestation-dep28afbde6a/web
