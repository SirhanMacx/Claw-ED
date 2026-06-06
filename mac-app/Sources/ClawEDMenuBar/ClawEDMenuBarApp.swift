import SwiftUI
import AppKit

/// Claw-ED Menu Bar — the friendly desktop launcher.
///
/// "Claude Code for teachers": the heavy engine stays in Python; this app is
/// the calm, one-click front door. It lives in the menu bar, starts/stops the
/// known local server, shows health + a QR code for phone access, and opens
/// the browser. It never exposes a terminal or arbitrary command execution.
@main
struct ClawEDMenuBarApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var server = ServerController()

    var body: some Scene {
        MenuBarExtra {
            MenuBarContentView(server: server)
        } label: {
            // Menu-bar icon reflects status at a glance.
            Label("Claw-ED", systemImage: server.status == .running
                  ? "graduationcap.fill"
                  : "graduationcap")
        }
        // `.window` gives us a rich popover panel (vs. a plain menu) — better
        // for the status card, URLs, and QR code.
        .menuBarExtraStyle(.window)

        // Settings window (⌘,) — only the launcher path and port.
        Settings {
            SettingsView()
        }
    }
}

/// Minimal app delegate: make this a menu-bar-only agent (no Dock icon) and
/// guarantee the server child process is torn down on quit.
final class AppDelegate: NSObject, NSApplicationDelegate {
    /// The app shares the single ServerController via a weak hook so the
    /// delegate can terminate the child on exit even though SwiftUI owns it.
    static weak var server: ServerController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Belt-and-suspenders: even without LSUIElement in Info.plist (e.g.
        // when run via `swift run`), force agent (accessory) activation so no
        // Dock icon appears.
        NSApp.setActivationPolicy(.accessory)
    }

    func applicationWillTerminate(_ notification: Notification) {
        AppDelegate.server?.terminateForAppExit()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        // Menu-bar app: keep running when popover/settings windows close.
        false
    }
}
