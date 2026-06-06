// swift-tools-version: 5.9
//
// Claw-ED Menu Bar — a friendly macOS launcher for the Claw-ED engine.
//
// This is a pure SwiftPM executable. It builds and runs without Xcode:
//
//     swift build
//     swift run
//
// MenuBarExtra (the menu-bar UI) needs a real app bundle with the
// LSUIElement / "Application is agent" Info.plist key so the app has no
// Dock icon and lives only in the menu bar. `swift run` launches the
// executable directly (no bundle), which works for development, but for a
// shippable app you wrap this binary in a .app — see mac-app/README.md
// ("Ship a signed/notarized .app").
//
// No third-party dependencies. Everything used here ships with macOS
// (SwiftUI, AppKit, CoreImage, Foundation, Network).

import PackageDescription

let package = Package(
    name: "ClawEDMenuBar",
    platforms: [
        // MenuBarExtra is available from macOS 13. We require 14 for the
        // stable `.menuBarExtraStyle(.window)` behaviour and modern SwiftUI.
        .macOS(.v14)
    ],
    products: [
        .executable(name: "ClawEDMenuBar", targets: ["ClawEDMenuBar"])
    ],
    targets: [
        .executableTarget(
            name: "ClawEDMenuBar",
            path: "Sources/ClawEDMenuBar"
        )
    ]
)
