# Claw-ED iOS (thin client)

> A calm Capacitor wrapper that connects to a teacher's **own** Claw-ED server
> over the local network. **No Python runs on the phone.** The engine stays on
> the teacher's Mac; this app is just a friendly front door to it from an iPad or
> iPhone on the same Wi-Fi, or to the teacher's paired remote/tunnel URL.

## What this is (and isn't)

- **Is:** a native shell whose only bundled screen is a **CONNECT** screen. The
  teacher scans the Mac QR code with the iPhone Camera, follows a `clawed://`
  pairing link, or types the URL their Mac shows (e.g.
  `http://192.168.1.42:8000`). The WebView navigates to that running server.
  Everything after that is the teacher's real Claw-ED web app.
- **Isn't:** a reimplementation of Claw-ED, a cloud client, or anything that
  phones home. It bundles no curriculum engine and no Python. Consistent with
  `docs/PRIVACY_MODEL.md` — no telemetry.

This mirrors the desktop story in `docs/product/CLAWED_DESKTOP_PLAN.md`: the Mac
menu-bar app (`mac-app/`) shows local, LAN, and remote/tunnel pairing options.
LAN sharing is explicit and off by default; the Mac launcher only binds
`0.0.0.0` after the teacher turns on "Share on my Wi-Fi."

## Layout

```
ios-app/
├── package.json            # clawed-ios; @capacitor/core + ios + cli
├── capacitor.config.json   # appId com.macxlabs.clawed, appName Claw-ED, webDir www
├── www/                    # the ONLY bundled web content (the CONNECT screen)
│   ├── index.html
│   ├── connect.js          # validate, remember, deep-link pair, bootstrap token, navigate
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

## QR pairing

The primary path is the normal iPhone/iPad **Camera** app: scan the QR code in
the Mac menu-bar app, tap the `clawed://connect?...` prompt, and Claw-ED opens
with the server URL and optional device token already filled in. The app also
handles warm links while already open and cold links from a fresh launch.

The in-app **Scan QR** button remains a graceful fallback. If a native barcode
plugin is added, the button can scan directly; otherwise it tells the teacher to
use the Camera app or type the Mac address. To enable direct in-app scanning:

```bash
npm i @capacitor/barcode-scanner
npx cap sync ios
```

Then add a camera-usage string to the iOS app's `Info.plist`
(`NSCameraUsageDescription` — e.g. "Scan the QR code shown by Claw-ED on your
Mac to connect.").

## Signing & TestFlight

The native Xcode project is committed and configured for the MacxLabs team and
bundle identifier. Shipping still requires valid Apple signing credentials on
the build host, but it does not require recreating the project by hand:

1. Confirm the **App** target is signed with team `Y8MX8Q77B2` and bundle
   identifier `com.macxlabs.clawed`.
2. Run `npm run sync:ios` after editing `www/`.
3. Archive the `App` scheme from `ios/App/App.xcworkspace`.
4. Export with `ios/ExportOptions.plist` and upload to App Store Connect.

No private signing certificates or App Store Connect API keys should be
committed to this repo.
