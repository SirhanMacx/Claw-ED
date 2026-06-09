import SwiftUI
import CoreImage
import CoreImage.CIFilterBuiltins
import AppKit

/// Generates a crisp QR-code image from a string using CoreImage's
/// `CIQRCodeGenerator`. No third-party dependencies.
enum QRCode {
    /// Shared context — reused across calls (creating one per render is wasteful).
    private static let context = CIContext()

    /// Render `string` as a QR code sized to `side` points.
    ///
    /// CoreImage emits a tiny bitmap (one module per pixel); we scale it up
    /// with nearest-neighbor so the modules stay sharp instead of blurry.
    /// Returns `nil` if generation fails (e.g. empty/too-long input).
    static func image(from string: String, side: CGFloat = 180) -> NSImage? {
        guard !string.isEmpty, let data = string.data(using: .utf8) else { return nil }

        let filter = CIFilter.qrCodeGenerator()
        filter.message = data
        // "M" = ~15% error correction: a good balance for a short URL.
        filter.correctionLevel = "M"

        guard let output = filter.outputImage else { return nil }

        // Scale the small generated image up to the requested side length.
        let scale = side / output.extent.width
        let scaled = output.transformed(by: CGAffineTransform(scaleX: scale, y: scale))

        guard let cgImage = context.createCGImage(scaled, from: scaled.extent) else { return nil }
        return NSImage(cgImage: cgImage, size: NSSize(width: side, height: side))
    }
}

/// SwiftUI view wrapping a generated QR code with a graceful fallback.
struct QRCodeView: View {
    let string: String
    var side: CGFloat = 180

    var body: some View {
        if let nsImage = QRCode.image(from: string, side: side) {
            Image(nsImage: nsImage)
                .interpolation(.none) // keep modules crisp
                .resizable()
                .frame(width: side, height: side)
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .strokeBorder(Color.black.opacity(0.08), lineWidth: 1)
                )
                .accessibilityLabel("QR code for \(string)")
        } else {
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.secondary.opacity(0.12))
                .frame(width: side, height: side)
                .overlay(
                    Text("QR unavailable")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                )
        }
    }
}
