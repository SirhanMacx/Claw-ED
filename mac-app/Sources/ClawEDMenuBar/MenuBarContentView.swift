import SwiftUI
import AppKit

/// The popover panel shown when the teacher clicks the menu-bar icon.
///
/// Layout, top to bottom:
///   • Header (mascot-ish glyph + name + tagline)
///   • Status card (dot + state + primary Start/Stop button)
///   • Open button (enabled when running)
///   • Addresses card: localhost URL, LAN URL, and a QR code of the LAN URL
///   • A quiet disclosure with the recent server log + Settings/Quit
///
/// Tone: warm, calm, trustworthy. No flashy motion. No terminal.
struct MenuBarContentView: View {
    @ObservedObject var server: ServerController
    @State private var showLog = false
    @State private var copied: String?
    @Environment(\.openURL) private var openURL

    private var autoOpen: Bool { UserDefaults.standard.clawedAutoOpenOnStart }
    private var shareOnLan: Bool { UserDefaults.standard.clawedShareOnLan }

    /// The always-on remote address: the named Cloudflare tunnel. The agent is
    /// reachable here from anywhere over https; pairing carries the device token
    /// so only the teacher's own phone can connect.
    private let remoteURL = URL(string: "https://clawed.macxlabs.app")!

    /// The agent's device token, read from `~/.eduagent/api_token`. It STAYS on
    /// this Mac — it only ever leaves by being encoded into the on-screen pairing
    /// QR that the teacher scans with their own phone. Returns nil before the
    /// agent has run (no token file yet).
    private func deviceToken() -> String? {
        let path = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".eduagent/api_token")
        guard let raw = try? String(contentsOf: path, encoding: .utf8) else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// The pairing deep link the QR encodes. Scanning it with the iPhone's
    /// normal camera opens the Claw-ED app and connects it to this Mac in one
    /// tap — no typing, no in-app scanner. The connect screen parses
    /// `clawed://connect?url=<server>&token=<device-token>`. The token is
    /// included for any non-loopback server (the tunnel, or a LAN address),
    /// which the agent requires auth for; a local server needs none.
    private func deepLink(for server: URL) -> String {
        let encodedURL = server.absoluteString.addingPercentEncoding(
            withAllowedCharacters: .alphanumerics
        ) ?? server.absoluteString
        var link = "clawed://connect?url=\(encodedURL)"
        if let token = deviceToken() {
            let encodedToken = token.addingPercentEncoding(
                withAllowedCharacters: .alphanumerics
            ) ?? token
            link += "&token=\(encodedToken)"
        }
        return link
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            Divider()
            statusCard
            openButton
            addressesCard
            Divider()
            footer
        }
        .padding(16)
        .frame(width: 320)
        .onAppear {
            // Let the app delegate reach the server for clean teardown on quit.
            AppDelegate.server = server
        }
        .onChange(of: server.status) { _, newValue in
            // Auto-open the browser once, when the server first becomes healthy.
            if newValue == .running, autoOpen {
                openURL(server.localURL)
            }
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "graduationcap.fill")
                .font(.title2)
                .foregroundStyle(.tint)
            VStack(alignment: .leading, spacing: 1) {
                Text("Claw-ED")
                    .font(.headline)
                Text("Made by a teacher, for teachers.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
    }

    // MARK: - Status

    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                StatusDot(colorName: server.status.dotColorName, pulsing: server.status.isBusy)
                Text(server.status.label)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(server.status == .running ? .primary : .secondary)
                Spacer()
            }

            Button(action: { server.toggle() }) {
                HStack {
                    Image(systemName: primaryButtonIcon)
                    Text(primaryButtonTitle)
                    Spacer()
                    if server.status.isBusy {
                        ProgressView().controlSize(.small)
                    }
                }
                .frame(maxWidth: .infinity)
            }
            .controlSize(.large)
            .buttonStyle(.borderedProminent)
            .tint(server.status == .running || server.status.isBusy ? .red : .accentColor)
        }
        .padding(12)
        .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 10))
    }

    private var primaryButtonTitle: String {
        switch server.status {
        case .running: return "Stop Claw-ED"
        case .starting: return "Starting… (tap to cancel)"
        case .stopped, .error: return "Start Claw-ED"
        }
    }

    private var primaryButtonIcon: String {
        switch server.status {
        case .running, .starting: return "stop.fill"
        case .stopped, .error: return "play.fill"
        }
    }

    // MARK: - Open

    private var openButton: some View {
        Button(action: { openURL(server.localURL) }) {
            HStack {
                Image(systemName: "safari")
                Text("Open Claw-ED in your browser")
                Spacer()
            }
            .frame(maxWidth: .infinity)
        }
        .controlSize(.large)
        .buttonStyle(.bordered)
        .disabled(server.status != .running)
    }

    // MARK: - Addresses + QR

    private var addressesCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Open on this computer")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            addressRow(label: server.localURL.absoluteString,
                       url: server.localURL,
                       systemImage: "desktopcomputer")

            // Primary phone option: open from ANYWHERE over the named tunnel.
            // The QR carries the tunnel URL + the device token, so the teacher
            // scans once and the phone is paired and connects on any network.
            Divider().padding(.vertical, 2)
            Text("Open on your phone (anywhere)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            addressRow(label: remoteURL.absoluteString,
                       url: remoteURL,
                       systemImage: "globe")
            if deviceToken() != nil {
                HStack {
                    Spacer()
                    VStack(spacing: 6) {
                        QRCodeView(string: deepLink(for: remoteURL), side: 150)
                        Text("Scan with your phone’s camera — opens Claw-ED & connects from anywhere")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    Spacer()
                }
                .padding(.top, 4)
            } else {
                Text("Start Claw-ED once to generate your device token, then reopen this menu to see the pairing QR.")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            // Phone access only works when LAN sharing is ON (server bound to
            // 0.0.0.0). Showing a QR that points at a localhost-only server
            // would just fail to connect, so we only render the address + QR
            // when sharing is on; otherwise we nudge the teacher to enable it.
            Divider().padding(.vertical, 2)
            Text("Open on your phone (same Wi-Fi)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)

            if shareOnLan, let lan = server.lanURL {
                addressRow(label: lan.absoluteString,
                           url: lan,
                           systemImage: "iphone")

                HStack {
                    Spacer()
                    VStack(spacing: 6) {
                        QRCodeView(string: deepLink(for: lan), side: 150)
                        Text("Scan with your phone’s camera — opens Claw-ED & connects")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .padding(.top, 4)
            } else {
                Text(shareOnLan
                     ? "Couldn’t find a Wi-Fi/Ethernet address on this Mac. Connect to a network and reopen this menu."
                     : "Turn on “Share on my Wi-Fi” in Settings to show a QR code your phone can scan. It’s off by default — Claw-ED stays private to this computer until you enable it.")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 10))
    }

    private func addressRow(label: String, url: URL, systemImage: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: systemImage)
                .foregroundStyle(.secondary)
                .frame(width: 16)
            Text(label)
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .lineLimit(1)
                .truncationMode(.middle)
            Spacer(minLength: 4)
            Button {
                copy(url.absoluteString)
            } label: {
                Image(systemName: copied == url.absoluteString ? "checkmark" : "doc.on.doc")
                    .font(.caption)
            }
            .buttonStyle(.borderless)
            .help("Copy address")
        }
    }

    // MARK: - Footer

    private var footer: some View {
        VStack(alignment: .leading, spacing: 8) {
            DisclosureGroup(isExpanded: $showLog) {
                ScrollView {
                    Text(server.recentLog.isEmpty ? "No activity yet." : server.recentLog)
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                }
                .frame(height: 120)
                .padding(8)
                .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 6))
            } label: {
                Label("Activity", systemImage: "list.bullet.rectangle")
                    .font(.caption)
            }

            HStack {
                SettingsLink {
                    Label("Settings", systemImage: "gearshape")
                        .font(.caption)
                }
                .buttonStyle(.borderless)

                Spacer()

                Button {
                    NSApp.terminate(nil)
                } label: {
                    Label("Quit", systemImage: "power")
                        .font(.caption)
                }
                .buttonStyle(.borderless)
                .help("Quit Claw-ED (also stops the server)")
            }
        }
    }

    // MARK: - Helpers

    private func copy(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        copied = text
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) {
            if copied == text { copied = nil }
        }
    }
}

/// A small colored status dot, optionally pulsing while busy.
struct StatusDot: View {
    let colorName: String
    var pulsing: Bool = false
    @State private var animate = false

    private var color: Color {
        switch colorName {
        case "green": return .green
        case "yellow": return .yellow
        case "red": return .red
        default: return .secondary
        }
    }

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 10, height: 10)
            .overlay(
                Circle()
                    .stroke(color.opacity(0.35), lineWidth: 4)
                    .scaleEffect(animate && pulsing ? 1.8 : 1.0)
                    .opacity(animate && pulsing ? 0.0 : 0.6)
            )
            .onAppear {
                guard pulsing else { return }
                withAnimation(.easeOut(duration: 1.1).repeatForever(autoreverses: false)) {
                    animate = true
                }
            }
            .onChange(of: pulsing) { _, isPulsing in
                animate = isPulsing
                if isPulsing {
                    withAnimation(.easeOut(duration: 1.1).repeatForever(autoreverses: false)) {
                        animate = true
                    }
                }
            }
    }
}
