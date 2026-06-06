import SwiftUI
import AppKit

/// Settings (⌘,). Deliberately tiny and safe.
///
/// The ONLY things configurable are:
///   • Launcher path — where `clawed` (or `python3`) lives, for teachers whose
///     install isn't on the GUI PATH. Empty ⇒ auto-detect from PATH.
///   • Port — the port the local server listens on.
///   • Auto-open — open the browser automatically when the server is ready.
///
/// There is intentionally NO field for arbitrary commands or flags. The app
/// only ever runs the documented `clawed app` server.
struct SettingsView: View {
    @AppStorage(SettingsKey.launcherPath) private var launcherPath = ""
    @AppStorage(SettingsKey.port) private var port = ClawED.defaultPort
    @AppStorage(SettingsKey.autoOpenOnStart) private var autoOpen = true

    @State private var detected: String = "Checking…"

    var body: some View {
        Form {
            Section {
                LabeledContent("Auto-detected") {
                    Text(detected)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }

                HStack {
                    TextField("Leave empty to auto-detect", text: $launcherPath)
                        .textFieldStyle(.roundedBorder)
                    Button("Choose…") { chooseLauncher() }
                }
                Text("Path to your `clawed` command, or a `python3` interpreter. "
                     + "Find it in Terminal with `which clawed` (or `which python3`). "
                     + "Leave empty and Claw-ED will look on your PATH.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } header: {
                Text("Claw-ED engine")
            }

            Section {
                Stepper(value: $port, in: 1024...65535) {
                    LabeledContent("Port", value: String(port))
                }
                Toggle("Open my browser when Claw-ED is ready", isOn: $autoOpen)
            } header: {
                Text("Server")
            } footer: {
                Text("Claw-ED runs only on this computer (127.0.0.1). No data leaves your machine, and there’s no telemetry.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 460, height: 360)
        .onAppear(perform: refreshDetected)
    }

    private func refreshDetected() {
        if let clawed = LaunchPlan.which("clawed") {
            detected = "clawed → \(clawed.path)"
        } else if let py = LaunchPlan.which("python3") ?? LaunchPlan.which("python") {
            detected = "python fallback → \(py.path)"
        } else {
            detected = "Not found on PATH — set a path below or `pip install clawed`."
        }
    }

    private func chooseLauncher() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.message = "Choose your `clawed` command or a `python3` interpreter"
        panel.prompt = "Use"
        // Default to a likely location.
        if let bin = LaunchPlan.which("clawed") ?? LaunchPlan.which("python3") {
            panel.directoryURL = bin.deletingLastPathComponent()
        }
        if panel.runModal() == .OK, let url = panel.url {
            launcherPath = url.path
        }
    }
}
