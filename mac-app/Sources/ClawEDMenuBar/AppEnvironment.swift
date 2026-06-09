import Foundation

/// Static facts about how Claw-ED runs locally.
///
/// The heavy engine lives in Python. This Mac app only *launches* and
/// *monitors* it. The server binds to 127.0.0.1:8000 by default (see
/// `clawed/commands/bot.py` → `app` command, which runs
/// `uvicorn.run("clawed.api.server:app", host="127.0.0.1", port=8000)`).
enum ClawED {
    /// Default port the `clawed app` server binds to.
    static let defaultPort = 8000

    /// Loopback host the server binds to. Never exposed to the LAN by default.
    static let loopbackHost = "127.0.0.1"

    /// Liveness endpoint. `GET /api/health` returns `{"status":"ok",...}` with
    /// NO auth and NO DB/LLM calls (see `clawed/api/routes/settings.py`). This
    /// is the correct probe for "is the server up?". We also accept a 2xx/3xx
    /// from `/` as a fallback (it redirects depending on onboarding state).
    static let healthPath = "/api/health"

    /// Display name.
    static let appName = "Claw-ED"
}

/// User-configurable settings, persisted in `UserDefaults`.
///
/// Deliberately minimal. The UI never exposes a free-form command field —
/// only the *interpreter/launcher path* (so a teacher on a non-PATH Python
/// can point us at it) and the port. Everything else is fixed to the known,
/// safe `clawed app` invocation.
enum SettingsKey {
    /// Path to the `clawed` executable, OR a `python3`/`python` interpreter
    /// used to run the documented module fallback. Empty string ⇒ resolve
    /// `clawed` (then `python3`) from PATH.
    static let launcherPath = "clawed.launcherPath"

    /// Port the server should listen on.
    static let port = "clawed.port"

    /// Whether to automatically open the browser when the server reports healthy.
    static let autoOpenOnStart = "clawed.autoOpenOnStart"

    /// Whether to bind the server to the LAN (0.0.0.0) so other devices on the
    /// same Wi-Fi (e.g. the teacher's phone, via the QR code) can open it.
    /// Off by default — this is opt-in network exposure.
    static let shareOnLan = "clawed.shareOnLan"
}

extension UserDefaults {
    /// Configured launcher path, or `nil` to mean "resolve from PATH".
    var clawedLauncherPath: String? {
        let raw = (string(forKey: SettingsKey.launcherPath) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return raw.isEmpty ? nil : raw
    }

    var clawedPort: Int {
        let stored = integer(forKey: SettingsKey.port)
        return stored == 0 ? ClawED.defaultPort : stored
    }

    var clawedAutoOpenOnStart: Bool {
        // Default true on first run (object(forKey:) is nil ⇒ teacher-friendly).
        object(forKey: SettingsKey.autoOpenOnStart) as? Bool ?? true
    }

    /// Whether to share the app on the local Wi-Fi (bind 0.0.0.0). Defaults to
    /// false — opt-in network exposure, surfaced with a warning in Settings.
    var clawedShareOnLan: Bool {
        bool(forKey: SettingsKey.shareOnLan)
    }
}

/// Network helpers for building the URLs a teacher sees.
enum NetworkInfo {
    /// The localhost URL for the running app, e.g. `http://127.0.0.1:8000`.
    static func localURL(port: Int) -> URL {
        URL(string: "http://\(ClawED.loopbackHost):\(port)")!
    }

    /// The health-probe URL.
    static func healthURL(port: Int) -> URL {
        URL(string: "http://\(ClawED.loopbackHost):\(port)\(ClawED.healthPath)")!
    }

    /// The LAN URL a phone on the same Wi-Fi can open, e.g.
    /// `http://192.168.1.42:8000`, or `nil` if no usable LAN address is found.
    ///
    /// NOTE: This is only reachable if the server is bound to `0.0.0.0`. By
    /// default `clawed app` binds to `127.0.0.1` (localhost-only), so the LAN
    /// URL is shown for convenience but will not connect unless the teacher
    /// explicitly opts into LAN exposure. We surface that caveat in the UI.
    static func lanURL(port: Int) -> URL? {
        guard let ip = primaryLANIPv4() else { return nil }
        return URL(string: "http://\(ip):\(port)")
    }

    /// Best-effort primary IPv4 LAN address.
    ///
    /// Walks the interface list and prefers the common Wi-Fi/Ethernet
    /// interfaces (`en0`, `en1`, …). Skips loopback and link-local. Uses only
    /// the C `getifaddrs` API from `<ifaddrs.h>` (no third-party deps).
    static func primaryLANIPv4() -> String? {
        var candidates: [(name: String, address: String)] = []

        var ifaddrPtr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddrPtr) == 0, let first = ifaddrPtr else { return nil }
        defer { freeifaddrs(ifaddrPtr) }

        var cursor: UnsafeMutablePointer<ifaddrs>? = first
        while let ptr = cursor {
            defer { cursor = ptr.pointee.ifa_next }

            let flags = Int32(ptr.pointee.ifa_flags)
            // Must be up and running, and not loopback.
            guard (flags & IFF_UP) == IFF_UP,
                  (flags & IFF_RUNNING) == IFF_RUNNING,
                  (flags & IFF_LOOPBACK) == 0 else { continue }

            guard let addr = ptr.pointee.ifa_addr,
                  addr.pointee.sa_family == sa_family_t(AF_INET) else { continue }

            let name = String(cString: ptr.pointee.ifa_name)

            var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            let result = getnameinfo(
                addr,
                socklen_t(addr.pointee.sa_len),
                &host, socklen_t(host.count),
                nil, 0,
                NI_NUMERICHOST
            )
            guard result == 0 else { continue }

            let address = String(cString: host)
            // Skip link-local (169.254.x.x) which isn't useful for a phone.
            if address.hasPrefix("169.254.") { continue }

            candidates.append((name: name, address: address))
        }

        // Prefer en* interfaces (Wi-Fi/Ethernet) in numeric order, then any.
        let preferred = candidates
            .filter { $0.name.hasPrefix("en") }
            .sorted { $0.name < $1.name }
        if let best = preferred.first { return best.address }
        return candidates.first?.address
    }
}
