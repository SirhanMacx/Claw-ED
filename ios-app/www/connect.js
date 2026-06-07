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
  var DEFAULT_PORT = '8000'; // matches `clawed app` / mac-app AppEnvironment.swift

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
    reconnectCard: $('reconnect-card'),
    reconnectBtn: $('reconnect-btn'),
    reconnectUrl: $('reconnect-url'),
    forgetBtn: $('forget-btn'),
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
  function connectTo(url) {
    var normalized = normalizeUrl(url);
    if (!normalized) {
      showError('That does not look like a server address. Try something like http://192.168.1.42:8000');
      return false;
    }
    clearError();
    saveUrl(normalized);
    setBusy(true);
    // Defer the actual navigation a tick so the busy state paints first.
    window.setTimeout(function () {
      window.location.replace(normalized);
    }, 60);
    return true;
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
        if (els.input) {
          els.input.value = value;
        }
        connectTo(value);
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

  // ---- wire up ----------------------------------------------------------
  function init() {
    var saved = loadSavedUrl();
    renderReconnect(saved);

    if (els.form) {
      els.form.addEventListener('submit', function (event) {
        event.preventDefault();
        connectTo(els.input ? els.input.value : '');
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
        connectTo(saved);
      });
    }

    if (els.forgetBtn) {
      els.forgetBtn.addEventListener('click', function () {
        clearSavedUrl();
        saved = '';
        renderReconnect('');
        if (els.input) {
          els.input.value = '';
          els.input.focus();
        }
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
