import Foundation

/// Reasons launching can fail, with teacher-readable messages.
struct LaunchError: Error {
    let message: String
}

/// A fully-resolved, *fixed* plan for launching the Claw-ED server.
///
/// There is exactly one logical command this app ever runs: start the
/// documented `clawed app` server. We resolve it to one of two concrete
/// forms, in priority order:
///
///   1. **`clawed app`** — preferred. Uses the `clawed` console script
///      (from `pip install clawed`). Resolved from a teacher-configured
///      path if set, else from `PATH`.
///
///   2. **Python module fallback** — if `clawed` isn't found, run:
///        python3 -c "import sys; sys.argv=['clawed','app']; \
///                    from clawed._entry_router import main; main()"
///      using a teacher-configured interpreter path if set, else `python3`
///      from `PATH`. This matches the invocation documented in the task and
///      drives the same entry point as the console script.
///
/// Crucially, the arguments are *constructed by us* — never assembled from
/// free-form user input — so the UI can never be coaxed into running an
/// arbitrary command.
struct LaunchPlan {
    let executableURL: URL
    let arguments: [String]
    let environment: [String: String]
    /// Human-readable form for the log/UI.
    let displayCommand: String

    // The documented module-fallback one-liner.
    static let moduleFallbackCode =
        "import sys; sys.argv=['clawed','app']; " +
        "from clawed._entry_router import main; main()"

    /// Resolve the plan for the given port, honoring the configured launcher
    /// path (if any). Throws `LaunchError` if nothing runnable is found.
    static func resolve(port: Int) throws -> LaunchPlan {
        let env = baseEnvironment(port: port)
        let configured = UserDefaults.standard.clawedLauncherPath

        // 1) Teacher pointed us at a specific binary/interpreter.
        if let configured {
            let url = URL(fileURLWithPath: (configured as NSString).expandingTildeInPath)
            guard FileManager.default.isExecutableFile(atPath: url.path) else {
                throw LaunchError(message:
                    "The configured launcher isn’t executable:\n\(url.path)\n" +
                    "Pick the `clawed` command or a `python3` from your terminal " +
                    "(run `which clawed` or `which python3`).")
            }
            return plan(for: url, port: port, environment: env)
        }

        // 2) `clawed` on PATH (preferred).
        if let clawed = which("clawed") {
            return clawedPlan(executable: clawed, port: port, environment: env)
        }

        // 3) python3 / python module fallback.
        if let python = which("python3") ?? which("python") {
            return pythonFallbackPlan(python: python, port: port, environment: env)
        }

        throw LaunchError(message:
            "Couldn’t find Claw-ED. Install it with `pip install clawed`, " +
            "or open Settings and point Claw-ED at your `clawed` command " +
            "or `python3` (find them with `which clawed` / `which python3`).")
    }

    // MARK: - Plan builders

    /// Decide whether a configured executable is `clawed` itself or a Python
    /// interpreter, by its filename.
    private static func plan(for url: URL, port: Int, environment: [String: String]) -> LaunchPlan {
        let name = url.lastPathComponent.lowercased()
        if name.hasPrefix("python") {
            return pythonFallbackPlan(python: url, port: port, environment: environment)
        }
        // Treat anything else (typically `clawed`) as the console script.
        return clawedPlan(executable: url, port: port, environment: environment)
    }

    private static func clawedPlan(executable: URL, port: Int, environment: [String: String]) -> LaunchPlan {
        // `clawed app --port <port>` — `--no-open` because the Mac app opens
        // the browser itself (only once the server is verified healthy).
        let args = ["app", "--port", String(port), "--no-open"]
        return LaunchPlan(
            executableURL: executable,
            arguments: args,
            environment: environment,
            displayCommand: "\(executable.path) " + args.joined(separator: " ")
        )
    }

    private static func pythonFallbackPlan(python: URL, port: Int, environment: [String: String]) -> LaunchPlan {
        // The documented module fallback drives `main()` with argv ['clawed','app'].
        // `clawed app` reads the port from --port; the entry router forwards
        // argv to the typer app, so we append the port flag to argv too.
        let code =
            "import sys; sys.argv=['clawed','app','--port','\(port)','--no-open']; " +
            "from clawed._entry_router import main; main()"
        let args = ["-c", code]
        return LaunchPlan(
            executableURL: python,
            arguments: args,
            environment: environment,
            displayCommand: "\(python.path) -c \"…clawed app --port \(port) --no-open…\""
        )
    }

    // MARK: - Environment

    /// Build the child environment. We inherit the user's environment so that
    /// `pip`/`pyenv`/`venv` setups keep working, and ensure a sane PATH that
    /// includes the common install locations for `clawed` and `python3`.
    private static func baseEnvironment(port: Int) -> [String: String] {
        var env = ProcessInfo.processInfo.environment

        // GUI apps launched outside a shell often get a minimal PATH. Augment
        // it with the usual suspects so PATH lookups (and the child's own
        // subprocess calls, e.g. ffmpeg) succeed.
        let extras = [
            "/opt/homebrew/bin",          // Apple-silicon Homebrew
            "/usr/local/bin",             // Intel Homebrew / pipx
            "/usr/bin", "/bin",
            "\(NSHomeDirectory())/.local/bin", // pip --user / pipx
        ]
        let existing = env["PATH"]?.split(separator: ":").map(String.init) ?? []
        var merged = existing
        for p in extras where !merged.contains(p) { merged.append(p) }
        env["PATH"] = merged.joined(separator: ":")

        // The `clawed app` command sets this itself, but setting it here too
        // is harmless and keeps behavior identical regardless of entry path:
        // trust same-machine requests so a teacher never hits a token wall.
        env["EDUAGENT_LOCAL_AUTH_BYPASS"] = "1"

        // Don't buffer Python stdout/stderr so our log tail is live.
        env["PYTHONUNBUFFERED"] = "1"
        return env
    }

    // MARK: - PATH resolution

    /// Resolve a command to an absolute executable URL using the augmented
    /// PATH, without invoking a shell.
    static func which(_ command: String) -> URL? {
        let fm = FileManager.default
        let path = baseEnvironment(port: ClawED.defaultPort)["PATH"] ?? ""
        for dir in path.split(separator: ":") {
            let candidate = URL(fileURLWithPath: String(dir)).appendingPathComponent(command)
            if fm.isExecutableFile(atPath: candidate.path) {
                return candidate
            }
        }
        return nil
    }
}
