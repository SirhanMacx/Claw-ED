# Claw-ED iOS — App Store Connect metadata (draft)

Draft listing for the App Store Connect record (`com.macxlabs.clawed`,
team Y8MX8Q77B2). This is the content to paste when the app record exists.
TestFlight only needs Name + Privacy + a build; the rest is for the eventual
public listing. Character limits noted in parentheses.

## App information
- **Name** (30): `Claw-ED`
- **Subtitle** (30): `Lesson-planning co-teacher`  *(set in ASC)*
- **Primary language**: English (U.S.)
- **Bundle ID**: `com.macxlabs.clawed` *(registered: J6MYZ2VRS9)*
- **SKU**: `CLAWED001`
- **Primary category**: Education *(portal-only remaining gate; API rejects category relationship updates)*
- **Secondary category**: Productivity *(portal-only remaining gate; API rejects category relationship updates)*
- **Age rating**: 4+ (set in ASC; no ads, no unrestricted web access, no UGC/social chat)
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
- **Privacy Policy URL**: `https://macxlabs.app/privacy/` *(live, verified 200 on 2026-06-11)*

## App Privacy (nutrition label)
**Data Not Collected.** The app collects no data. It connects only to the
teacher's own Claw-ED server on their local network; it has no analytics, no
accounts, and no third-party SDKs. (`Info.plist`:
`ITSAppUsesNonExemptEncryption=false`; `NSAllowsLocalNetworking=true` for the
LAN connection only.)

App Privacy appears to be web-portal-only for this account/API key; attempted
API paths for `appPrivacyDetails` / `appPrivacyDeclarations` returned 404.
Before public submission, set App Privacy in App Store Connect to **Data Not
Collected**.

## App Review information
- **Sign-in required**: No account. Demo of the LAN-pairing flow below.
- **Contact**: Jon Maccarello — (phone + email as set on the ASC record).
- **Notes for the reviewer**:
  > Claw-ED iOS is a thin client for a self-hosted Claw-ED server (like a
  > client for a self-hosted service). On first launch it asks for the server
  > URL (scan a QR or paste a link). To review end-to-end, point it at a
  > running Claw-ED instance: https://clawed.macxlabs.app. This tunnel is live
  > and `/api/health` returns 200. Because the server is intentionally protected,
  > include the current private pairing token in App Store Connect review notes
  > only; do not commit it to the repo. Without a server/token, the app shows the
  > pairing screen and a clear explanation, which is the intended first-run state.

### ⚠️ Review-viability note (not a blocker for TestFlight)
A companion/thin-client app can draw **Guideline 4.2 (minimum functionality)**
scrutiny because it needs the self-hosted server to do anything. This is fine
for **TestFlight** (internal + external testing) — the immediate target. For a
public App Store release, give the reviewer the live demo URL plus private
pairing token in App Store Connect review notes and lean on the precedent of
approved self-hosted clients (Plex, Home Assistant, etc.).

## Build / signing
- App Store Connect app record exists: App ID `6777690676`, bundle
  `com.macxlabs.clawed`, SKU `CLAWED001`.
- Current selected App Store version build: v1.0 build 5, processing state
  `VALID`, `usesNonExemptEncryption=false`.
- Current App Store version state: version 1.0 is `DEVELOPER_REJECTED`, release
  type `AFTER_APPROVAL`, with build 5 selected. Latest review submission is
  `COMPLETE` at `2026-06-11T03:15:35.219Z`.
- Current TestFlight state for build 5: internal testing is live
  (`internalBuildState=IN_BETA_TESTING`); external testing is ready for beta
  submission (`externalBuildState=READY_FOR_BETA_SUBMISSION`).
- Latest export from this repo: `ios-app/build/export-1.0.4/App.ipa`
  (IPA `CFBundleVersion=5`; the folder name is stale).
- Upload/verify (no browser; uses the ASC API key):
  ```
  xcrun altool --upload-app -t ios -f ios-app/build/export-1.0.4/App.ipa \
    --apiKey K5RKF383QT --apiIssuer 6a02d8d5-4d1e-4f92-9936-18d05e663ff2
  node ios-app/scripts/asc.mjs verify-build --version 5
  node ios-app/scripts/asc.mjs verify-beta --version 5
  node ios-app/scripts/asc.mjs verify-version
  ```

## Current Submit Gate
- Build, screenshots, listing text, privacy URL, age rating, and review notes are
  populated.
- Review notes include the live demo URL plus private pairing token in App Store
  Connect only; do not commit or print the token elsewhere.
- API submission currently fails at `POST /v1/reviewSubmissionItems` with
  `STATE_ERROR.ENTITY_STATE_INVALID` because the version is still not in a valid
  reviewable state.
- Known remaining portal-only fields:
  - Set primary category to **Education** and secondary category to
    **Productivity**. ASC API returned 403:
    `primaryCategory relationship does not allow UPDATE`.
  - Set App Privacy to **Data Not Collected** in the web UI.
- After those fields are complete, resubmit version 1.0 from App Store Connect;
  it is currently `DEVELOPER_REJECTED`, not waiting for Apple review.

## Screenshots
- iPhone 6.9" (`APP_IPHONE_67`): five screenshots generated from
  `ios-app/app-store/screenshots/iphone-6.9/` and uploaded to App Store Connect;
  all processed `COMPLETE`.
- iPad 12.9" (`APP_IPAD_PRO_3GEN_129`): five screenshots generated from
  `ios-app/app-store/screenshots/ipad-12.9/` and uploaded to App Store Connect;
  all processed `COMPLETE`.
- Repeatable commands:
  ```
  cd ios-app
  npm run screenshots:app-store
  npm run screenshots:verify
  ```
