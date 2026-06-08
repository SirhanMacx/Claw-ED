/*
 * Claw-ED iOS thin client — CONNECT screen logic.
 *
 * Dependency-free vanilla JS. No build step, no framework. This file owns the
 * one job of the native shell: collect the teacher's own Claw-ED server URL
 * (typed or scanned), remember it, and hand the WebView over to that server.
 * Everything after navigation is the teacher's real Claw-ED web app.
 *
 * Storage key holds the last-good base URL, e.g. "http://192.168.1.42:8000".
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'clawed.serverUrl';
  var TOKEN_KEY = 'clawed.serverToken'; // device token for the paired server (remote/tunnel)
  var DEFAULT_PORT = '8000'; // matches `clawed app` / mac-app AppEnvironment.swift

  // Once true, we've committed the WebView to a server (navigation scheduled).
  // Every entry point checks this so a late health-check or warm deep-link can
  // never double-navigate or yank the teacher back to the connect screen.
  var committed = false;
  var autoController = null; // AbortController for the in-flight launch probe

  // ---- tiny DOM helpers -------------------------------------------------
  function $(id) {
    return document.getElementById(id);
  }

  var els = {
    form: $('connect-form'),
    input: $('server-url'),
    error: $('connect-error'),
    connectBtn: $('connect-btn'),
    scanBtn: $('scan-btn'),
    connectCard: $('connect-card'),
    reconnectCard: $('reconnect-card'),
    reconnectBtn: $('reconnect-btn'),
    reconnectUrl: $('reconnect-url'),
    forgetBtn: $('forget-btn'),
    autoCard: $('auto-card'),
    autoTarget: $('auto-target'),
    autoCancelBtn: $('auto-cancel'),
  };

  // ---- storage (guarded; private mode / disabled storage must not crash) -
  function loadSavedUrl() {
    try {
      return window.localStorage.getItem(STORAGE_KEY) || '';
    } catch (err) {
      console.warn('[clawed] localStorage read failed:', err);
      return '';
    }
  }

  function saveUrl(url) {
    try {
      window.localStorage.setItem(STORAGE_KEY, url);
    } catch (err) {
      console.warn('[clawed] localStorage write failed:', err);
    }
  }

  function clearSavedUrl() {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
      console.warn('[clawed] localStorage clear failed:', err);
    }
  }

  // ---- device token (for a remote/tunnel server that requires auth) -------
  // Paired once via the Mac's QR (clawed://connect?url=…&token=…). Stays on this
  // device; delivered to the server as an HttpOnly cookie at connect time (see
  // navigateToServer). A local/LAN server needs none.
  function loadToken() {
    try {
      return window.localStorage.getItem(TOKEN_KEY) || '';
    } catch (err) {
      return '';
    }
  }

  function saveToken(token) {
    try {
      window.localStorage.setItem(TOKEN_KEY, token);
    } catch (err) {
      console.warn('[clawed] token write failed:', err);
    }
  }

  function clearToken() {
    try {
      window.localStorage.removeItem(TOKEN_KEY);
    } catch (err) {
      /* no-op */
    }
  }

  // ---- navigation into the server ---------------------------------------
  // With a token (remote/tunnel server that requires auth): set the auth cookie
  // via a top-level form POST to /api/auth/bootstrap — the token rides in the
  // POST body (never the URL), the server sets a first-party HttpOnly cookie and
  // 303-redirects into the app, and the WebView's same-origin /api calls then
  // carry the cookie automatically. Without a token (local/LAN): just navigate.
  function navigateToServer(url, token) {
    if (token) {
      var form = document.createElement('form');
      form.method = 'POST';
      form.action = url + '/api/auth/bootstrap';
      form.style.display = 'none';
      var field = document.createElement('input');
      field.type = 'hidden';
      field.name = 'token';
      field.value = token;
      form.appendChild(field);
      document.body.appendChild(form);
      form.submit();
    } else {
      window.location.replace(url);
    }
  }

  // ---- URL normalization + validation -----------------------------------
  // Accepts forms a teacher might type or a QR might carry:
  //   192.168.1.42            -> http://192.168.1.42:8000
  //   192.168.1.42:8000       -> http://192.168.1.42:8000
  //   http://192.168.1.42:8000
  //   https://my-mac.local:8000
  // Returns a normalized origin string, or null if it can't be made sense of.
  function normalizeUrl(raw) {
    if (!raw) {
      return null;
    }
    var text = String(raw).trim();
    if (text === '') {
      return null;
    }

    // Decide whether the teacher typed a real URL scheme.
    //
    // A network scheme is "<name>://…". If one is present, only http/https are
    // valid here — reject ftp://, file://, etc. rather than mangling them.
    //
    // Tricky case: a bare "host:port" (e.g. "my-mac.local:8000") also looks like
    // "<name>:…" but is NOT a scheme — the colon is followed by a port, not "//".
    // So we key on the "//" that follows a real scheme's colon.
    var authorityScheme = /^([a-z][a-z0-9+.-]*):\/\//i.exec(text);
    if (authorityScheme) {
      var scheme = authorityScheme[1].toLowerCase();
      if (scheme !== 'http' && scheme !== 'https') {
        return null;
      }
      // else: it's http:// or https:// — use as-is.
    } else if (/^[a-z][a-z0-9+.-]*:(?!\d)/i.test(text)) {
      // A non-"//" scheme with a non-numeric body, e.g. "javascript:…",
      // "data:…", "mailto:…". Never a LAN server address — reject.
      return null;
    } else {
      // No scheme present (bare host, or host:port) — default to http://.
      text = 'http://' + text;
    }

    var url;
    try {
      url = new URL(text);
    } catch (err) {
      return null;
    }

    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      return null;
    }
    if (!url.hostname) {
      return null;
    }

    // If no explicit port and plain http on the LAN, assume the Claw-ED default.
    if (!url.port && url.protocol === 'http:') {
      url.port = DEFAULT_PORT;
    }

    // Preserve any path the teacher pasted, but drop a bare trailing slash so the
    // remembered string stays tidy. Most servers are served at the root.
    var origin = url.origin;
    var path = url.pathname && url.pathname !== '/' ? url.pathname : '';
    return origin + path;
  }

  function showError(message) {
    if (!els.error) {
      return;
    }
    els.error.textContent = message;
    els.error.hidden = false;
    if (els.input) {
      els.input.setAttribute('aria-invalid', 'true');
    }
  }

  function clearError() {
    if (!els.error) {
      return;
    }
    els.error.hidden = true;
    els.error.textContent = '';
    if (els.input) {
      els.input.removeAttribute('aria-invalid');
    }
  }

  // ---- navigation -------------------------------------------------------
  // Hand the WebView over to the teacher's server. We save first so a relaunch
  // can offer "Reconnect", then replace the current document so the back gesture
  // doesn't bounce between the server and this CONNECT screen.
  function connectTo(url, token) {
    if (committed) {
      return true; // already handing off to a server — ignore late callers
    }
    var normalized = normalizeUrl(url);
    if (!normalized) {
      revealConnectScreen();
      showError('That does not look like a server address. Try something like http://192.168.1.42:8000');
      return false;
    }
    clearError();
    saveUrl(normalized);
    // A non-empty token (from QR pairing) is remembered; an explicit null
    // (manual entry, typically a local server) clears any stale token; an
    // omitted token (undefined: reconnect / auto-connect) keeps the saved one.
    if (token) {
      saveToken(token);
    } else if (token === null) {
      clearToken();
    }
    committed = true;
    setBusy(true);
    showConnectingTo(normalized);
    // Defer the actual navigation a tick so the interstitial paints first.
    window.setTimeout(function () {
      navigateToServer(normalized, loadToken());
    }, 60);
    return true;
  }

  // ---- card visibility --------------------------------------------------
  // Exactly one of {auto, reconnect+connect} is shown at a time. The brand
  // header is always visible so the screen never looks blank while deciding.
  function hideAllCards() {
    [els.autoCard, els.connectCard, els.reconnectCard].forEach(function (card) {
      if (card) {
        card.hidden = true;
      }
    });
  }

  function showConnectingTo(url) {
    hideAllCards();
    if (els.autoTarget) {
      els.autoTarget.textContent = url;
    }
    if (els.autoCard) {
      els.autoCard.hidden = false;
    }
  }

  // Reveal the manual connect form (used on first run, on cancel, or when a
  // remembered server can't be reached). renderReconnect() then decides whether
  // the "Welcome back" shortcut also appears above it.
  function revealConnectScreen() {
    if (els.autoCard) {
      els.autoCard.hidden = true;
    }
    if (els.connectCard) {
      els.connectCard.hidden = false;
    }
  }

  function setBusy(isBusy) {
    [els.connectBtn, els.scanBtn, els.reconnectBtn].forEach(function (btn) {
      if (btn) {
        btn.disabled = isBusy;
      }
    });
    document.body.classList.toggle('is-busy', !!isBusy);
  }

  // ---- QR scan (Capacitor plugin if present; graceful stub otherwise) ----
  // We avoid a hard import so the web build runs anywhere. If the
  // @capacitor/barcode-scanner plugin is installed in the native project, this
  // calls it; otherwise it explains how to connect by hand. This is the
  // documented stub the build plan calls for.
  function getBarcodePlugin() {
    var cap = window.Capacitor;
    if (!cap || !cap.Plugins) {
      return null;
    }
    // Capacitor's official scanner registers as "CapacitorBarcodeScanner".
    return cap.Plugins.CapacitorBarcodeScanner || cap.Plugins.BarcodeScanner || null;
  }

  function scanQr() {
    var plugin = getBarcodePlugin();
    if (!plugin || typeof plugin.scanBarcode !== 'function') {
      showError(
        'QR scanning needs the camera plugin (a follow-up). For now, type the LAN URL shown in the Mac menu-bar app.'
      );
      if (els.input) {
        els.input.focus();
      }
      return;
    }

    clearError();
    setBusy(true);
    // Capacitor barcode scanner returns { ScanResult: "<decoded text>" }.
    plugin
      .scanBarcode({ hint: 17 /* ALL */ })
      .then(function (result) {
        setBusy(false);
        var value = result && (result.ScanResult || result.scanResult || result.value);
        if (!value) {
          showError('No QR code detected. Try again, or type the URL.');
          return;
        }
        // The Mac QR is a clawed:// deep link carrying url (+ optional token);
        // a hand-made QR may just be a plain URL.
        if (/^clawed:/i.test(value)) {
          var paired = serverFromDeepLink(value);
          if (paired) {
            connectTo(paired.url, paired.token);
            return;
          }
        }
        if (els.input) {
          els.input.value = value;
        }
        connectTo(value, null);
      })
      .catch(function (err) {
        setBusy(false);
        // A user cancel is normal, not an error worth shouting about.
        var msg = err && err.message ? String(err.message) : '';
        if (/cancel/i.test(msg)) {
          return;
        }
        console.warn('[clawed] QR scan failed:', err);
        showError('Could not open the camera. Type the URL instead.');
      });
  }

  // ---- remembered-URL "Reconnect" path ----------------------------------
  function renderReconnect(savedUrl) {
    if (!els.reconnectCard) {
      return;
    }
    if (savedUrl) {
      if (els.reconnectUrl) {
        els.reconnectUrl.textContent = savedUrl;
      }
      els.reconnectCard.hidden = false;
      // Prefill the manual field too, so editing is one tap away.
      if (els.input && !els.input.value) {
        els.input.value = savedUrl;
      }
    } else {
      els.reconnectCard.hidden = true;
    }
  }

  // ---- deep-link pairing (clawed://connect?url=<server>) ----------------
  // The Mac's QR encodes a clawed:// URL. Scanning it with the phone's normal
  // camera opens this app and hands the URL to us here — so the teacher pairs
  // in ONE tap, with no typing and no in-app scanner. Works on cold launch
  // (app opened by the link) and warm open (link tapped while running).
  function serverFromDeepLink(urlStr) {
    try {
      var u = new URL(urlStr);
      var s = u.searchParams.get('url') || u.searchParams.get('server');
      if (!s) {
        return null;
      }
      // The Mac QR may also carry the device token for a remote/tunnel server.
      return { url: s, token: u.searchParams.get('token') || '' };
    } catch (err) {
      return null;
    }
  }

  function capApp() {
    var cap = window.Capacitor;
    return (cap && cap.Plugins && cap.Plugins.App) || null;
  }

  // Warm deep-link: app already open, teacher scans the Mac QR. Always live so a
  // pairing link wins over whatever screen is showing.
  function wireWarmDeepLink() {
    var app = capApp();
    if (!app || typeof app.addListener !== 'function') {
      return;
    }
    app.addListener('appUrlOpen', function (data) {
      var s = data && data.url ? serverFromDeepLink(data.url) : null;
      if (s) {
        connectTo(s.url, s.token);
      }
    });
  }

  // ---- auto-connect on launch -------------------------------------------
  // The "just works like Codex" path: if we already know the teacher's server,
  // don't make them tap anything. Probe it first so we can fail gracefully (a
  // friendly retry) instead of replacing the WebView with a dead error page,
  // then open straight in. Probe uses GET /api/health; the server allow-lists
  // this app's capacitor:// origin so the cross-origin check is readable.
  function healthCheck(baseUrl, timeoutMs) {
    var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    autoController = ctrl;
    var timer = window.setTimeout(function () {
      if (ctrl) {
        ctrl.abort();
      }
    }, timeoutMs || 8000);
    var opts = { method: 'GET', cache: 'no-store' };
    if (ctrl) {
      opts.signal = ctrl.signal;
    }
    return fetch(baseUrl + '/api/health', opts)
      .then(function (res) {
        window.clearTimeout(timer);
        return !!(res && res.ok);
      })
      .catch(function () {
        window.clearTimeout(timer);
        return false;
      })
      .then(function (ok) {
        autoController = null;
        return ok;
      });
  }

  function startAutoConnect(url) {
    var normalized = normalizeUrl(url);
    if (!normalized) {
      revealConnectScreen();
      renderReconnect('');
      return;
    }
    showConnectingTo(normalized);
    // 8s, not 3.5s: a remote/tunnel server adds real round-trip latency (the
    // agent's /api/health was ~4.2s over Cloudflare), so a tight timeout would
    // falsely fall back on a perfectly reachable Mac.
    healthCheck(normalized, 8000).then(function (ok) {
      if (committed) {
        return; // a deep-link or manual tap already took over
      }
      if (ok) {
        connectTo(normalized);
      } else {
        revealConnectScreen();
        renderReconnect(normalized);
        showError(
          'Couldn’t reach ' + normalized + '. Make sure Claw-ED is running on ' +
          'your Mac (and on the same network or your tunnel), then reconnect.'
        );
      }
    });
  }

  function cancelAutoConnect() {
    if (autoController) {
      try {
        autoController.abort();
      } catch (err) {
        /* no-op */
      }
    }
    if (committed) {
      return;
    }
    var saved = loadSavedUrl();
    revealConnectScreen();
    renderReconnect(saved);
  }

  // Decide what to show the instant the app opens: a pairing deep-link wins;
  // else auto-connect to the remembered server; else the manual form.
  function decideInitialAction() {
    var app = capApp();
    if (app && typeof app.getLaunchUrl === 'function') {
      app
        .getLaunchUrl()
        .then(function (res) {
          var s = res && res.url ? serverFromDeepLink(res.url) : null;
          if (s) {
            connectTo(s.url, s.token);
            return;
          }
          autoOrForm();
        })
        .catch(autoOrForm);
    } else {
      autoOrForm();
    }
  }

  function autoOrForm() {
    if (committed) {
      return;
    }
    var saved = loadSavedUrl();
    if (saved) {
      startAutoConnect(saved);
    } else {
      revealConnectScreen();
      renderReconnect('');
    }
  }

  // ---- wire up ----------------------------------------------------------
  function init() {
    wireWarmDeepLink();

    if (els.form) {
      els.form.addEventListener('submit', function (event) {
        event.preventDefault();
        // Manual entry is the local/LAN path — clear any stale paired token.
        connectTo(els.input ? els.input.value : '', null);
      });
    }

    if (els.input) {
      els.input.addEventListener('input', clearError);
    }

    if (els.scanBtn) {
      els.scanBtn.addEventListener('click', scanQr);
    }

    if (els.reconnectBtn) {
      els.reconnectBtn.addEventListener('click', function () {
        connectTo(loadSavedUrl());
      });
    }

    if (els.forgetBtn) {
      els.forgetBtn.addEventListener('click', function () {
        clearSavedUrl();
        clearToken();
        renderReconnect('');
        revealConnectScreen();
        if (els.input) {
          els.input.value = '';
          els.input.focus();
        }
      });
    }

    if (els.autoCancelBtn) {
      els.autoCancelBtn.addEventListener('click', cancelAutoConnect);
    }

    // Decide the opening screen: pairing deep-link → auto-connect → form.
    decideInitialAction();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
