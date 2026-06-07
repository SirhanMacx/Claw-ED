import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Claw-ED iOS thin client.
 *
 * This app ships only the local CONNECT screen (`www/`). It does NOT bundle the
 * Claw-ED web app or any Python — the engine stays on the teacher's Mac. After
 * the teacher enters (or scans) their server's LAN URL, the WebView navigates to
 * that URL and renders the teacher's own running Claw-ED instance.
 *
 * The default Mac server binds to http://<lan-ip>:8000 (see
 * `docs/product/CLAWED_DESKTOP_PLAN.md` and `mac-app/`). LAN sharing must be
 * enabled on the Mac side ("Allow phones on my Wi-Fi to connect") for the phone
 * to actually reach it; until then the CONNECT screen explains the caveat.
 */
const config: CapacitorConfig = {
  appId: 'app.macxlabs.clawed',
  appName: 'Claw-ED',
  webDir: 'www',
  // Teacher servers are plain http:// on the LAN (no public TLS), so the WebView
  // must be allowed to load cleartext + mixed content for those LAN origins.
  server: {
    androidScheme: 'https',
    iosScheme: 'capacitor',
    cleartext: true,
  },
  ios: {
    // Let the native scroll/bounce feel calm rather than rubber-banding hard.
    contentInset: 'always',
    // A cream background avoids a white flash before the CONNECT screen paints.
    backgroundColor: '#FAF9F5',
  },
};

export default config;
