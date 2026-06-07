# Claw-ED iOS — App Store Connect metadata (draft)

Draft listing for the App Store Connect record (`com.macxlabs.clawed`,
team Y8MX8Q77B2). This is the content to paste when the app record exists.
TestFlight only needs Name + Privacy + a build; the rest is for the eventual
public listing. Character limits noted in parentheses.

## App information
- **Name** (30): `Claw-ED`
- **Subtitle** (30): `Lesson-planning co-teacher`  *(26)*
- **Primary language**: English (U.S.)
- **Bundle ID**: `com.macxlabs.clawed` *(registered: J6MYZ2VRS9)*
- **SKU**: `CLAWED001`
- **Primary category**: Education
- **Secondary category**: Productivity
- **Age rating**: 4+ (no objectionable content)
- **Copyright**: `© 2026 MacxLabs`

## Pricing & availability
- **Price**: Free (Tier 0)
- **Availability**: All territories
- No in-app purchases.

## Promotional text (170)
> Connect to your own Claw-ED workspace and build lessons, units, quizzes,
> and differentiated versions — in your teaching voice — from your phone or
> tablet. Your files never leave your machine.

## Description (4000)
> Claw-ED is the companion app for your Claw-ED teaching workspace.
>
> Claw-ED runs on your own computer and learns how YOU teach from your own
> files. This app is the phone- and tablet-friendly way to reach it: open it
> on the same Wi-Fi as your computer, scan the QR code your Claw-ED desktop
> app shows (or paste the link), and you're in.
>
> From your phone you can:
> • Ask your co-teacher anything — a hook, a Do Now, three discussion
>   questions, an IEP scaffold — and watch the answer stream in.
> • Build a full lesson, a unit, materials, a quiz, a differentiated version,
>   or a review game.
> • Read a lesson in a clean preview before you download it.
>
> Why teachers like it:
> • It writes like you. Claw-ED reads your old lessons and matches your
>   vocabulary, scaffolds, and structure.
> • It's private. Everything runs on your own machine — your files, your
>   students, your lessons never leave your computer. This app just talks to
>   your machine over your local network.
> • It's calm. A warm, focused, teacher-first design — no clutter, no ads,
>   no accounts.
>
> Requires a running Claw-ED workspace on your computer (free, open source —
> github.com/SirhanMacx/Claw-ED). This app is a client for that workspace; it
> does not generate content on its own.
>
> Made by a teacher, for teachers. Part of MacxLabs.

## Keywords (100, comma-separated, no spaces after commas)
`teacher,lesson plan,lesson planning,curriculum,education,classroom,quiz maker,differentiation,IEP,co-teacher`

## URLs
- **Support URL**: `https://github.com/SirhanMacx/Claw-ED`
- **Marketing URL**: `https://macxlabs.app`
- **Privacy Policy URL**: `https://macxlabs.app/privacy/` *(confirm live before public submit)*

## App Privacy (nutrition label)
**Data Not Collected.** The app collects no data. It connects only to the
teacher's own Claw-ED server on their local network; it has no analytics, no
accounts, and no third-party SDKs. (`Info.plist`:
`ITSAppUsesNonExemptEncryption=false`; `NSAllowsLocalNetworking=true` for the
LAN connection only.)

## App Review information
- **Sign-in required**: No account. Demo of the LAN-pairing flow below.
- **Contact**: Jon Maccarello — (phone + email as set on the ASC record).
- **Notes for the reviewer**:
  > Claw-ED iOS is a thin client for a self-hosted Claw-ED server (like a
  > client for a self-hosted service). On first launch it asks for the server
  > URL (scan a QR or paste a link). To review end-to-end, point it at a
  > running Claw-ED instance: [REVIEWER DEMO SERVER URL — provide a
  > temporary public/ngrok URL to a Claw-ED instance before external review].
  > Without a server it shows the pairing screen and a clear explanation, which
  > is the intended first-run state.

### ⚠️ Review-viability note (not a blocker for TestFlight)
A companion/thin-client app can draw **Guideline 4.2 (minimum functionality)**
scrutiny because it needs the self-hosted server to do anything. This is fine
for **TestFlight** (internal + external testing) — the immediate target. For a
public App Store release, give the reviewer a reachable demo server (temporary
tunnel to a Claw-ED instance) and lean on the precedent of approved
self-hosted clients (Plex, Home Assistant, etc.).

## Build / signing
- Signed IPA built: `ios-app/build/ipa/App.ipa` — v1.0 (build 1),
  "Apple Distribution: JON ANTHONY MACCARELLO (Y8MX8Q77B2)".
- Upload (no browser; uses the ASC API key) once the app record exists:
  ```
  xcrun altool --upload-app -t ios -f ios-app/build/ipa/App.ipa \
    --apiKey K5RKF383QT --apiIssuer 6a02d8d5-4d1e-4f92-9936-18d05e663ff2
  node ios-app/scripts/asc.mjs verify-build --version 1
  ```

## Screenshots (required sizes — capture from the connected web UI on device/sim)
- 6.7" (1290×2796) — required. Capture: pairing screen, Create screen,
  co-teacher streaming, a rendered lesson preview.
- 6.5" (1242×2688) — required if 6.7" not provided for all.
- 12.9" iPad (2048×2732) — only if iPad is enabled.
- (Capture during the iOS-Simulator smoke verify.)
