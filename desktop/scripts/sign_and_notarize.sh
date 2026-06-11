#!/bin/bash
# Sign + notarize + staple Claw-ED.app and build the distributable DMG.
#
#   desktop/scripts/sign_and_notarize.sh /path/to/DeveloperID.cer
#
# Pre-req (the ONE Jon-gated step): a "Developer ID Application" certificate.
# The ASC API refuses to mint one (Account-Holder-only operation — verified
# 2026-06-11 with both team keys), so Jon mints it once in the portal:
#   1. developer.apple.com → Certificates → "+" → Developer ID Application
#   2. Upload the CSR at ~/.appstoreconnect/devid/devid.csr
#      (its private key is already on this Mac: ~/.appstoreconnect/devid/devid.key)
#   3. Download the .cer and run this script with its path.
#
# KEYCHAIN RULE (docs/product/HANDOFF.md): NEVER touches the login keychain.
# Everything happens in a throwaway /tmp keychain with a known password.
set -euo pipefail

CER="${1:?usage: sign_and_notarize.sh /path/to/DeveloperID.cer}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
APP="$REPO/desktop/src-tauri/target/release/bundle/macos/Claw-ED.app"
ENTITLEMENTS="$REPO/desktop/src-tauri/entitlements.plist"
DEVID_KEY="$HOME/.appstoreconnect/devid/devid.key"
ASC_KEY_ID="K5RKF383QT"
ASC_ISSUER="6a02d8d5-4d1e-4f92-9936-18d05e663ff2"
ASC_KEY_PATH="$HOME/.appstoreconnect/private_keys/AuthKey_${ASC_KEY_ID}.p8"
KC=/tmp/clawed-devid-signing.keychain-db
KC_PASS="clawed-signing-$(date +%s)"
OUT_DMG="$HOME/Documents/MacxLabs/web/downloads/Claw-ED.dmg"

[ -d "$APP" ] || { echo "Build the app first: cd desktop && npx tauri build"; exit 1; }
[ -f "$DEVID_KEY" ] || { echo "Missing $DEVID_KEY (the CSR's private key)"; exit 1; }

echo "── 1/7 throwaway keychain (login keychain untouched)"
security delete-keychain "$KC" 2>/dev/null || true
security create-keychain -p "$KC_PASS" "$KC"
security set-keychain-settings -lut 7200 "$KC"
security unlock-keychain -p "$KC_PASS" "$KC"

# Identity = minted cert + our private key, as a fresh p12
P12=/tmp/clawed-devid.p12
P12_PASS="p12-$(date +%s)"
openssl pkcs12 -export -inkey "$DEVID_KEY" \
  -in <(openssl x509 -inform DER -in "$CER" 2>/dev/null || cat "$CER") \
  -out "$P12" -passout "pass:$P12_PASS" -name "Claw-ED Developer ID"
security import "$P12" -k "$KC" -P "$P12_PASS" -T /usr/bin/codesign
rm -f "$P12"

# Apple intermediates (Developer ID chain)
for url in \
  https://www.apple.com/certificateauthority/DeveloperIDG2CA.cer \
  https://www.apple.com/certificateauthority/AppleWWDRCAG3.cer; do
  f="/tmp/$(basename "$url")"
  [ -s "$f" ] || curl -sfL "$url" -o "$f"
  security import "$f" -k "$KC" -T /usr/bin/codesign || true
done

security set-key-partition-list -S apple-tool:,apple: -s -k "$KC_PASS" "$KC" >/dev/null
# Search list: our keychain ONLY for this resolution (restore is automatic —
# we never modify the user's keychain search list; -keychain flags below
# address the /tmp keychain explicitly).
IDENTITY="$(security find-identity -v -p codesigning "$KC" | awk '/Developer ID Application/{print $2; exit}')"
[ -n "$IDENTITY" ] || { echo "No Developer ID identity in $KC"; exit 1; }
echo "identity: $IDENTITY"

echo "── 2/7 deep-sign every Mach-O (inside-out)"
# PyInstaller agent: all dylibs/sos first, then its executable, then the app.
find "$APP/Contents/Resources/agent" -type f \( -name "*.dylib" -o -name "*.so" \) -print0 |
  while IFS= read -r -d '' f; do
    codesign --force --options runtime --timestamp \
      --entitlements "$ENTITLEMENTS" --keychain "$KC" -s "$IDENTITY" "$f"
  done
find "$APP/Contents/Resources/agent" -type f -perm +111 ! -name "*.dylib" ! -name "*.so" -print0 |
  while IFS= read -r -d '' f; do
    file -b "$f" | grep -q Mach-O || continue
    codesign --force --options runtime --timestamp \
      --entitlements "$ENTITLEMENTS" --keychain "$KC" -s "$IDENTITY" "$f"
  done
codesign --force --options runtime --timestamp \
  --entitlements "$ENTITLEMENTS" --keychain "$KC" -s "$IDENTITY" \
  "$APP/Contents/MacOS/clawed-desktop"
codesign --force --options runtime --timestamp \
  --entitlements "$ENTITLEMENTS" --keychain "$KC" -s "$IDENTITY" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "── 3/7 notarize the app"
ZIP=/tmp/Claw-ED-notarize.zip
ditto -c -k --keepParent "$APP" "$ZIP"
xcrun notarytool submit "$ZIP" \
  --key "$ASC_KEY_PATH" --key-id "$ASC_KEY_ID" --issuer "$ASC_ISSUER" --wait
xcrun stapler staple "$APP"

echo "── 4/7 build the DMG"
STAGE="$(mktemp -d /tmp/clawed-dmg.XXXX)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG=/tmp/Claw-ED.dmg
rm -f "$DMG"
hdiutil create -volname "Claw-ED" -srcfolder "$STAGE" -ov -format UDZO "$DMG"

echo "── 5/7 sign + notarize + staple the DMG"
codesign --force --timestamp --keychain "$KC" -s "$IDENTITY" "$DMG"
xcrun notarytool submit "$DMG" \
  --key "$ASC_KEY_PATH" --key-id "$ASC_KEY_ID" --issuer "$ASC_ISSUER" --wait
xcrun stapler staple "$DMG"

echo "── 6/7 Gatekeeper verify"
spctl -a -t open --context context:primary-signature -v "$DMG"
FRESH="$(mktemp -d /tmp/clawed-gk.XXXX)"
hdiutil attach "$DMG" -mountpoint "$FRESH/mnt" -nobrowse -quiet
cp -R "$FRESH/mnt/Claw-ED.app" "$FRESH/"
hdiutil detach "$FRESH/mnt" -quiet
spctl -a -vv "$FRESH/Claw-ED.app"

echo "── 7/7 deliver"
mkdir -p "$(dirname "$OUT_DMG")"
cp "$DMG" "$OUT_DMG"
security delete-keychain "$KC" || true
echo "DONE: $OUT_DMG"
