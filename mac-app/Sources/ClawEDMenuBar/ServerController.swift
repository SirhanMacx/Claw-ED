import Foundation
import Combine

/// High-level state of the local Claw-ED server, as the menu-bar UI sees it.
enum ServerStatus: Equatable {
    /// Not started (or fully stopped).
    case stopped
    /// We've launched the process and are waiting for the health endpoint.
    case starting
    /// Health endpoint is answering — the app is usable.
    case running
    /// The process exited or failed; carries a human-readable reason.
    case error(String)

    var isBusy: Bool { self == .starting }

    /// Color name for the status dot, mapped to SwiftUI colors in the view.
    var dotColorName: String {
        switch self {
        case .stopped: return "secondary"
        case .starting: return "yellow"
        case .running: return "green"
        case .error: return "red"
        }
    }

    var label: String {
        switch self {
        case .stopped: return "Stopped"
        case .starting: return "Starting…"
        case .running: return "Running"
        case .error(let reason): return "Problem: \(reason)"
        }
    }
}

/// Owns the Claw-ED server subprocess and its health.
///
/// Responsibilities (and *only* these — no arbitrary command execution):
///   1. Launch the known `clawed app` server as a child `Process`.
///   2. Poll `GET /api/health` and publish `status`.
///   3. Terminate the child cleanly on Stop and on app exit.
///
/// The launch invocation is fixed. The only thing a teacher can configure is
/// the *path* to `clawed` (or a Python interpreter for the documented module
/// fallback) and the port. We never pass user-supplied shell strings.
@MainActor
final class ServerController: ObservableObject {
    @Published private(set) var status: ServerStatus = .stopped
    /// A short rolling tail of stdout/stderr from the server, for a
    /// "what's it doing?" disclosure. This is *read-only output*, never an
    /// interactive terminal.
    @Published private(set) var recentLog: String = ""

    private var process: Process?
    private var healthTimer: Timer?
    private var logBuffer: [String] = []
    private let maxLogLines = 40

    private var port: Int { UserDefaults.standard.clawedPort }

    // MARK: - Public API

    var localURL: URL { NetworkInfo.localURL(port: port) }
    var lanURL: URL? { NetworkInfo.lanURL(port: port) }

    /// Launch the server if it isn't already up.
    func start() {
        guard process == nil else { return }
        status = .starting
        appendLog("Starting Claw-ED on port \(port)…")

        let launch: LaunchPlan
        do {
            launch = try LaunchPlan.resolve(port: port)
        } catch {
            status = .error((error as? LaunchError)?.message ?? "Could not find Claw-ED")
            appendLog("✗ \( (error as? LaunchError)?.message ?? "\(error)" )")
            return
        }
        appendLog("→ \(launch.displayCommand)")

        let proc = Process()
        proc.executableURL = launch.executableURL
        proc.arguments = launch.arguments
        proc.environment = launch.environment

        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe
        // Stream output lines into the rolling log (off the main thread, then
        // hop back to the main actor to publish).
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor [weak self] in
                for line in text.split(whereSeparator: \.isNewline) {
                    self?.appendLog(String(line))
                }
            }
        }

        // When the process exits, reflect it in the UI.
        proc.terminationHandler = { [weak self] finished in
            Task { @MainActor [weak self] in
                self?.handleTermination(of: finished)
            }
        }

        do {
            try proc.run()
        } catch {
            status = .error("Couldn't launch: \(error.localizedDescription)")
            appendLog("✗ launch failed: \(error.localizedDescription)")
            return
        }

        process = proc
        startHealthPolling()
    }

    /// Stop the server and clear state.
    func stop() {
        appendLog("Stopping…")
        stopHealthPolling()
        terminateProcess()
        status = .stopped
    }

    /// Toggle convenience for a single button.
    func toggle() {
        switch status {
        case .running, .starting:
            stop()
        case .stopped, .error:
            start()
        }
    }

    /// Best-effort synchronous teardown for app termination. Safe to call from
    /// `applicationWillTerminate`.
    func terminateForAppExit() {
        stopHealthPolling()
        guard let proc = process, proc.isRunning else { return }
        proc.terminationHandler = nil // avoid touching `self` during teardown
        proc.terminate()              // SIGTERM
        // Give uvicorn a brief moment to shut down its workers gracefully.
        let deadline = Date().addingTimeInterval(3.0)
        while proc.isRunning && Date() < deadline {
            RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.05))
        }
        if proc.isRunning { proc.interrupt() } // SIGINT as a follow-up nudge
    }

    // MARK: - Process lifecycle

    private func terminateProcess() {
        guard let proc = process else { return }
        proc.terminationHandler = nil
        if proc.isRunning {
            proc.terminate()
        }
        // Detach the readability handler so the pipe can be released.
        (proc.standardOutput as? Pipe)?.fileHandleForReading.readabilityHandler = nil
        process = nil
    }

    private func handleTermination(of finished: Process) {
        // Ignore stale callbacks from a process we've already replaced/cleared.
        guard finished === process else { return }
        stopHealthPolling()
        (finished.standardOutput as? Pipe)?.fileHandleForReading.readabilityHandler = nil
        process = nil

        let code = finished.terminationStatus
        switch status {
        case .stopped:
            break // user-initiated stop already set the state
        default:
            if code == 0 {
                status = .stopped
                appendLog("Server exited.")
            } else {
                status = .error("Server exited (code \(code)). Check the log.")
                appendLog("✗ Server exited with code \(code).")
            }
        }
    }

    // MARK: - Health polling

    private func startHealthPolling() {
        stopHealthPolling()
        let timer = Timer(timeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in await self?.probeHealth() }
        }
        RunLoop.main.add(timer, forMode: .common)
        healthTimer = timer
        // Kick one off immediately so the dot updates fast.
        Task { @MainActor [weak self] in await self?.probeHealth() }
    }

    private func stopHealthPolling() {
        healthTimer?.invalidate()
        healthTimer = nil
    }

    private func probeHealth() async {
        // Only meaningful while we have a process and aren't stopped.
        guard process != nil else { return }

        let healthy = await Self.isHealthy(port: port)
        guard process != nil else { return } // may have stopped during await

        if healthy {
            if status != .running {
                status = .running
                appendLog("✓ Healthy at \(localURL.absoluteString)")
            }
        } else if status == .running {
            // Was up, now not answering — likely shutting down.
            status = .starting
        }
        // While `.starting` and not yet healthy, we simply keep polling.
    }

    /// One-shot health check against `GET /api/health`.
    nonisolated static func isHealthy(port: Int) async -> Bool {
        var request = URLRequest(url: NetworkInfo.healthURL(port: port))
        request.timeoutInterval = 2.0
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else { return false }
            return (200...299).contains(http.statusCode)
        } catch {
            return false
        }
    }

    // MARK: - Logging

    private func appendLog(_ line: String) {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        logBuffer.append(trimmed)
        if logBuffer.count > maxLogLines {
            logBuffer.removeFirst(logBuffer.count - maxLogLines)
        }
        recentLog = logBuffer.joined(separator: "\n")
    }
}
