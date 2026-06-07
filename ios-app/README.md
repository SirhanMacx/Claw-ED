# Claw-ED iOS (thin client)

> A calm Capacitor wrapper that connects to a teacher's **own** Claw-ED server
> over the local network. **No Python runs on the phone.** The engine stays on
> the teacher's Mac; this app is just a friendly front door to it from an iPad or
> iPhone on the same Wi-Fi.

## What this is (and isn't)

- **Is:** a native shell whose only bundled screen is a **CONNECT** screen. The
  teacher types or scans the LAN URL their Mac shows (e.g.
  `http://192.168.1.42:8000`), and the WebView navigates to that running server.
  Everything after that is the teacher's real Claw-ED web app, served from their
  Mac.
- **Isn't:** a reimplementation of Claw-ED, a cloud client, or anything that
  phones home. It bundles no curriculum engine and no Python. Consistent with
  `docs/PRIVACY_MODEL.md` — no telemetry.

This mirrors the desktop story in `docs/product/CLAWED_DESKTOP_PLAN.md`: the Mac
menu-bar app (`mac-app/`) already shows a **LAN URL + QR code** for exactly this
purpose. The phone reaching that URL requires the Mac side to opt into LAN
sharing ("Allow phones on my Wi-Fi to connect"); until then the server binds to
`127.0.0.1` and the CONNECT screen explains the caveat.

## Layout

```
ios-app/
├── package.json            # clawed-ios; @capacitor/core + ios + cli
├── capacitor.config.ts     # appId app.macxlabs.clawed, appName Claw-ED, webDir www
├── www/                    # the ONLY bundled web content (the CONNECT screen)
│   ├── index.html
│   ├── connect.js          # dependency-free vanilla JS: validate, remember, navigate
│   └── styles.css          # calm Claude palette (cream #FAF9F5, clay #C96442, serif)
├── resources/
│   ├── icon.png            # 1024×1024 placeholder (clay square, serif "C")
│   └── README.md           # how to expand to the full icon set; final icon is a follow-up
└── README.md               # this file
```

## Prerequisites

- **macOS + Xcode** (the iOS toolchain). Confirm with `xcodebuild -version`.
- **Node.js 18+** and npm. Confirm with `node -v` / `npm -v`.
- **CocoaPods** (Capacitor uses it for the iOS project): `sudo gem install cocoapods`.

## Build steps

From this `ios-app/` directory:

```bash
npm i                 # install Capacitor (core, ios, cli)
npx cap add ios       # generate the native ios/ Xcode project (one time)
npx cap sync ios      # copy www/ + config into the native project, install pods
npx cap open ios      # open the workspace in Xcode
```

Then in Xcode press **Run** to launch on a simulator or a connected device.

There is **no web build step**: `www/` is plain HTML/CSS/JS and is the web
directory Capacitor copies as-is. After editing anything in `www/`, re-run
`npx cap sync ios` (or `npx cap copy ios`) and Run again.

### Optional: generate the full icon set

```bash
npm i -D @capacitor/assets
npx capacitor-assets generate --ios \
  --iconBackgroundColor '#C96442' --splashBackgroundColor '#FAF9F5'
```

See `resources/README.md`.

## QR scanning

The **Scan QR** button is wired as a graceful stub. If the camera plugin is
added to the native project, the button uses it; otherwise it falls back to a
clear "type the URL" message. To enable real scanning:

```bash
npm i @capacitor/barcode-scanner
npx cap sync ios
```

Then add a camera-usage string to the iOS app's `Info.plist`
(`NSCameraUsageDescription` — e.g. "Scan the QR code shown by Claw-ED on your
Mac to connect.").

## Signing & TestFlight — the owner's (Jon's) step

**Apple Developer signing and any TestFlight / App Store upload are the repo
owner's responsibility and are intentionally not automated here.** This scaffold
deliberately stops at "opens in Xcode and runs." Shipping requires the owner's
Apple Developer account and credentials:

1. In Xcode → the **App** target → **Signing & Capabilities**, set the **Team**
   to the owner's Apple Developer team and confirm the bundle identifier
   `app.macxlabs.clawed` is registered (or let Xcode register it).
2. Pick a real signing identity / provisioning profile (automatic signing is
   fine for a first TestFlight build).
3. **Product → Archive**, then distribute via **App Store Connect** to upload a
   TestFlight build.

No signing certificates, provisioning profiles, API keys, or `ExportOptions`
live in this repo, and none should — those belong to the owner's account.
