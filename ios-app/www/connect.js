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
  var TOKEN_ORIGIN_KEY = 'clawed.serverTokenOrigin'; // origin the token is bound to
  var DEFAULT_PORT = '8000'; // matches `clawed app` / mac-app AppEnvironment.swift

  // Once true, we're connecting to or controlling a server. Every entry point
  // checks this so a late health-check or warm deep-link can never yank the
  // teacher back to the connect screen.
  var committed = false;
  var autoController = null; // AbortController for the in-flight launch probe
  var activeServerUrl = '';
  var cmdOutNode = null; // growing node for the current tool's streamed output

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
    remoteCard: $('remote-card'),
    remoteServer: $('remote-server'),
    remoteSwitch: $('remote-switch'),
    remoteFeed: $('remote-feed'),
    remoteForm: $('remote-form'),
    remoteInput: $('remote-input'),
    remoteSend: $('remote-send'),
    remoteNew: $('remote-new'),
  };

  // Chat render state (reset per turn / per conversation).
  var actNode = null; // the current tool's action card
  var approvalNodes = {}; // approval_id -> card element, so approval_resolved finds it
  var emptyHtml = ''; // captured empty-state markup, re-injected on new conversation
  var turnGotFinal = false; // did this turn reach a terminal event (final/error/done)?

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
  // Paired once via the Mac's QR (clawed://connect?url=…&token=…). The token is
  // the Mac's device token; it is JS-resident in this WebView (localStorage) and
  // sent as `Authorization: Bearer` on the remote-control /api fetches. A
  // local/LAN server that doesn't require auth needs none.
  //
  // SECURITY — the token is ORIGIN-PINNED: it is released ONLY to the exact
  // origin it was paired with (tokenForOrigin), so a deep link / QR that points
  // the app at a different host can never make us hand the real token to that
  // host. See connectTo (binds) and authHeaders (release).
  function loadToken() {
    try {
      return window.localStorage.getItem(TOKEN_KEY) || '';
    } catch (err) {
      return '';
    }
  }

  function originOf(url) {
    try {
      return new URL(normalizeUrl(url) || url).origin;
    } catch (err) {
      return '';
    }
  }

  // Release the saved token ONLY to the origin it was paired with. A legacy
  // token saved before pinning (no bound origin) is honored only for the
  // currently-saved server's origin.
  function tokenForOrigin(targetOrigin) {
    var token = loadToken();
    if (!token || !targetOrigin) {
      return '';
    }
    var bound = '';
    try {
      bound = window.localStorage.getItem(TOKEN_ORIGIN_KEY) || '';
    } catch (err) {
      /* no-op */
    }
    if (bound) {
      return bound === targetOrigin ? token : '';
    }
    return targetOrigin === originOf(loadSavedUrl()) ? token : '';
  }

  function saveToken(token, origin) {
    try {
      window.localStorage.setItem(TOKEN_KEY, token);
      if (origin) {
        window.localStorage.setItem(TOKEN_ORIGIN_KEY, origin);
      }
    } catch (err) {
      console.warn('[clawed] token write failed:', err);
    }
  }

  function clearToken() {
    try {
      window.localStorage.removeItem(TOKEN_KEY);
      window.localStorage.removeItem(TOKEN_ORIGIN_KEY);
    } catch (err) {
      /* no-op */
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

  // ---- connection -------------------------------------------------------
  // Pair the phone with the teacher's server and switch into the remote-control
  // surface. The full Mac dashboard remains available as an explicit button.
  function connectTo(url, token) {
    if (committed) {
      return true; // already connected or connecting — ignore late callers
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
      saveToken(token, originOf(normalized));
    } else if (token === null) {
      clearToken();
    }
    committed = true;
    setBusy(true);
    showConnectingTo(normalized);

    healthCheck(normalized, 8000).then(function (ok) {
      if (!committed) {
        return;
      }
      setBusy(false);
      if (ok) {
        showRemote(normalized);
        return;
      }
      committed = false;
      revealConnectScreen();
      renderReconnect(normalized);
      showError(
        'Couldn’t reach ' + normalized + '. Make sure Claw-ED is running on ' +
        'your Mac and that your phone is paired with the QR code.'
      );
    });
    return true;
  }

  // A URL from a scanned QR / deep link is UNTRUSTED input. If it points at a
  // host we haven't already paired with, make the teacher confirm before we
  // connect or hand over any token — a malicious QR must not be able to silently
  // re-point the app at an attacker's server.
  function connectFromScannedCode(url, token) {
    var target = originOf(url);
    var saved = originOf(loadSavedUrl());
    if (target && !(saved && target === saved)) {
      var ok = true;
      try {
        ok = window.confirm(
          'Connect Claw-ED to:\n\n' + target + '\n\nOnly continue if this is your own Mac.'
        );
      } catch (err) {
        ok = true; // no dialog support → fall back to old behavior
      }
      if (!ok) {
        return false;
      }
    }
    return connectTo(url, token);
  }

  // ---- remote-control surface -------------------------------------------
  function authHeaders(json) {
    var headers = {};
    if (json) {
      headers['Content-Type'] = 'application/json';
    }
    var token = tokenForOrigin(originOf(activeServerUrl));
    if (token) {
      headers.Authorization = 'Bearer ' + token;
    }
    return headers;
  }

  function feedScroll() {
    if (els.remoteFeed) {
      els.remoteFeed.scrollTop = els.remoteFeed.scrollHeight;
    }
  }

  // Drop the empty state (chips) the first time a real message lands.
  function dropEmptyState() {
    if (!els.remoteFeed) {
      return;
    }
    var empty = els.remoteFeed.querySelector('.remote-empty');
    if (empty) {
      empty.remove();
    }
  }

  function appendCard(node) {
    if (!els.remoteFeed || !node) {
      return null;
    }
    dropEmptyState();
    els.remoteFeed.appendChild(node);
    feedScroll();
    return node;
  }

  // kind → chat component class. 'user'=clay bubble, 'agent'=serif voice,
  // 'progress'=quiet note, 'error'=red note, 'command-output'=mono block.
  var KIND_CLASS = {
    user: 'bubble me',
    agent: 'voice',
    progress: 'note',
    error: 'note error',
    'command-output': 'cmd-out',
  };

  function remoteAppend(kind, text) {
    var node = document.createElement('div');
    node.className = KIND_CLASS[kind] || 'note';
    node.textContent = text;
    return appendCard(node);
  }

  // An artifact (a file the agent produced on the Mac). On the phone we can't
  // open a Mac file, so this is informational — name + path, no open action.
  function appendArtifact(path) {
    var name = String(path).split('/').pop() || String(path);
    var ext = (name.split('.').pop() || 'file').toUpperCase().slice(0, 4);
    var card = document.createElement('div');
    card.className = 'artifact';
    var ic = document.createElement('div');
    ic.className = 'ic';
    ic.textContent = ext;
    var meta = document.createElement('div');
    meta.className = 'meta';
    var b = document.createElement('b');
    b.textContent = name;
    var p = document.createElement('div');
    p.className = 'path';
    p.textContent = path + ' · on your Mac';
    meta.appendChild(b);
    meta.appendChild(p);
    card.appendChild(ic);
    card.appendChild(meta);
    return appendCard(card);
  }

  // Restore the greeting + suggestion chips (new conversation / fresh connect).
  function resetFeedToEmpty() {
    if (!els.remoteFeed) {
      return;
    }
    actNode = null;
    cmdOutNode = null;
    approvalNodes = {};
    if (emptyHtml) {
      els.remoteFeed.innerHTML = emptyHtml;
    } else {
      els.remoteFeed.textContent = '';
    }
  }

  function setRemoteBusy(isBusy) {
    if (els.remoteSend) {
      els.remoteSend.disabled = isBusy;
    }
    if (els.remoteInput) {
      els.remoteInput.disabled = isBusy;
    }
    var buttons = document.querySelectorAll('.chip');
    for (var i = 0; i < buttons.length; i += 1) {
      buttons[i].disabled = isBusy;
    }
  }

  function setResolved(card, cls, text) {
    if (!card) {
      return;
    }
    var actions = card.querySelector('.approve-actions');
    if (actions) {
      actions.remove();
    }
    var line = card.querySelector('.resolved');
    if (!line) {
      line = document.createElement('div');
      line.className = 'resolved';
      card.appendChild(line);
    }
    line.className = 'resolved ' + (cls || '');
    line.textContent = text;
    feedScroll();
  }

  function resolveApproval(baseUrl, approvalId, approved, alwaysFlag, card) {
    setResolved(card, '', approved ? 'Sending approval…' : 'Sending…');
    return fetch(baseUrl + '/api/approvals/' + encodeURIComponent(approvalId) + '/resolve', {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({ approved: !!approved, always: !!alwaysFlag }),
    })
      .then(function (res) {
        if (res.status === 401) {
          setResolved(card, 'no', 'Not authenticated. Re-pair with the Mac QR code.');
          return;
        }
        // The server returns HTTP 200 with {ok:false,error} for real failures
        // (approval not found / already resolved). Don't treat that as success.
        return res
          .json()
          .catch(function () { return {}; })
          .then(function (body) {
            if (body && body.ok === false) {
              setResolved(card, 'no', body.error ? 'Couldn’t apply: ' + body.error
                : 'The Mac couldn’t apply that decision.');
            }
            // On ok:true the authoritative `approval_resolved` SSE event sets the
            // truthful resolved line (allowed once / always / denied).
          });
      })
      .catch(function () {
        setResolved(card, 'no', 'Could not send approval. Reconnect and try again.');
      });
  }

  function appendApproval(baseUrl, data) {
    var card = document.createElement('div');
    card.className = 'approve';

    var top = document.createElement('div');
    top.className = 'top';
    top.textContent = 'Approve this action?';
    card.appendChild(top);

    var what = document.createElement('div');
    what.className = 'what';
    what.textContent = data.description || ('Run ' + (data.tool_name || 'tool'));
    card.appendChild(what);

    var risk = document.createElement('div');
    risk.className = 'risk';
    risk.textContent = 'Risk: ' + (data.risk_level || 'unknown') + ' · runs on your Mac';
    card.appendChild(risk);

    var actions = document.createElement('div');
    actions.className = 'approve-actions';
    var allow = document.createElement('button');
    allow.className = 'allow';
    allow.type = 'button';
    allow.textContent = 'Allow once';
    var always = document.createElement('button');
    always.className = 'always';
    always.type = 'button';
    always.textContent = 'Always';
    var deny = document.createElement('button');
    deny.className = 'deny';
    deny.type = 'button';
    deny.textContent = 'Deny';
    actions.appendChild(allow);
    actions.appendChild(always);
    actions.appendChild(deny);
    card.appendChild(actions);

    appendCard(card);
    if (data.approval_id) {
      approvalNodes[data.approval_id] = card;
    }

    function finish(approved, alwaysFlag) {
      allow.disabled = always.disabled = deny.disabled = true;
      resolveApproval(baseUrl, data.approval_id, approved, alwaysFlag, card);
    }
    allow.addEventListener('click', function () { finish(true, false); });
    always.addEventListener('click', function () { finish(true, true); });
    deny.addEventListener('click', function () { finish(false, false); });
  }

  function markApprovalResolved(id, approved, alwaysFlag) {
    var card = approvalNodes[id];
    if (!card) {
      return;
    }
    if (!approved) {
      setResolved(card, 'no', 'Denied. Not running that action.');
    } else if (alwaysFlag) {
      setResolved(card, 'ok', 'Always allowed — won’t ask again for this exact action.');
    } else {
      setResolved(card, 'ok', 'Allowed once. Continuing…');
    }
  }

  // Tool name → a friendly "what it's doing" label for the action card.
  var TOOL_LABEL = {
    run_command: 'Running a command',
    read_file: 'Reading a file',
    write_file: 'Writing a file',
    edit_file: 'Editing a file',
    list_directory: 'Listing a folder',
    generate_lesson: 'Generating a lesson',
    generate_lesson_bundle: 'Building a lesson bundle',
    generate_assessment: 'Building an assessment',
    generate_materials: 'Generating materials',
    export_document: 'Exporting a document',
    research: 'Researching',
    search_lessons: 'Searching your lessons',
    search_my_materials: 'Searching your materials',
    brain_search: 'Searching the teaching brain',
    brain_stats: 'Reading the teaching brain',
    curriculum_map: 'Mapping the curriculum',
  };

  function makeActCard(toolName) {
    var card = document.createElement('div');
    card.className = 'act';
    var spin = document.createElement('span');
    spin.className = 'spin';
    var run = document.createElement('span');
    run.className = 'run';
    run.textContent = TOOL_LABEL[toolName] || ('Using ' + (toolName || 'a tool'));
    card.appendChild(spin);
    card.appendChild(run);
    return appendCard(card);
  }

  function finishActCard(card, data) {
    if (!card) {
      return;
    }
    var spin = card.querySelector('.spin');
    if (spin) {
      spin.remove();
    }
    var tick = document.createElement('span');
    var ok = !!data.ok;
    tick.className = 'tick ' + (ok ? 'ok' : 'err');
    tick.textContent = ok ? 'done' : 'failed';
    card.appendChild(tick);
    if (!ok && data.summary) {
      remoteAppend('error', data.summary);
    }
  }

  function parseSSEBlock(block) {
    var event = 'message';
    var data = '';
    block.split('\n').forEach(function (line) {
      if (line.indexOf('event:') === 0) {
        event = line.slice(6).trim();
      } else if (line.indexOf('data:') === 0) {
        data += line.slice(5).trim();
      }
    });
    if (!data) {
      return null;
    }
    try {
      return { event: event, data: JSON.parse(data) };
    } catch (err) {
      return null;
    }
  }

  function readEventStream(body, onEvent) {
    var reader = body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    function pump() {
      return reader.read().then(function (chunk) {
        if (chunk.done) {
          return;
        }
        buffer += decoder.decode(chunk.value, { stream: true });
        var idx = buffer.indexOf('\n\n');
        while (idx !== -1) {
          var block = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          var parsed = parseSSEBlock(block);
          if (parsed) {
            onEvent(parsed.event, parsed.data);
          }
          idx = buffer.indexOf('\n\n');
        }
        return pump();
      });
    }
    return pump();
  }

  function handleRemoteEvent(baseUrl, event, data) {
    if (event === 'progress') {
      remoteAppend('progress', data.message || 'Working…');
    } else if (event === 'tool_start') {
      cmdOutNode = null; // start a fresh output block for this tool run
      actNode = makeActCard(data.tool_name);
    } else if (event === 'command_output') {
      // Live shell output, streamed in chunks by run_command — append into a
      // single growing monospace block so the teacher sees it as it runs.
      if (data.chunk) {
        if (!cmdOutNode) {
          cmdOutNode = remoteAppend('command-output', '');
        }
        if (cmdOutNode) {
          cmdOutNode.textContent += data.chunk;
          feedScroll();
        }
      }
    } else if (event === 'tool_end') {
      cmdOutNode = null;
      finishActCard(actNode, data);
      actNode = null;
      (data.files || []).forEach(appendArtifact);
    } else if (event === 'approval_required') {
      appendApproval(baseUrl, data);
    } else if (event === 'approval_resolved') {
      // Report the EFFECTIVE policy the server applied (data.always is the
      // truth — a remote "Always" is downgraded to once server-side), updating
      // the approval card in place rather than appending a separate line.
      markApprovalResolved(data.approval_id, data.approved, data.always);
    } else if (event === 'final') {
      turnGotFinal = true;
      if (data.text) {
        remoteAppend('agent', data.text);
      }
      (data.files || []).forEach(appendArtifact);
    } else if (event === 'error') {
      turnGotFinal = true;
      remoteAppend('error', data.message || 'Something went wrong.');
    } else if (event === 'done') {
      turnGotFinal = true;
    }
  }

  // A dropped fetch/stream throws a raw engine message — WebKit says "Load
  // failed", Chromium "Failed to fetch". Never show that verbatim; explain it.
  function friendlyStreamError(err) {
    var m = (err && err.message) || '';
    if (/load failed|failed to fetch|networkerror|network connection was lost|the request timed out/i.test(m)) {
      return 'Lost the connection to your Mac. A long task can outrun the tunnel — ' +
        'the work may still be finishing on the Mac. Give it a moment, then send it again.';
    }
    return m || 'Could not reach the Mac agent.';
  }

  function sendRemoteTask(message) {
    var text = String(message || '').trim();
    if (!text || !activeServerUrl) {
      return;
    }
    turnGotFinal = false;
    remoteAppend('user', text);
    setRemoteBusy(true);
    fetch(activeServerUrl + '/api/gateway/chat/stream', {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({ message: text }),
    })
      .then(function (res) {
        if (!res.ok || !res.body) {
          if (res.status === 401) {
            throw new Error('This phone is not authenticated. Re-pair with the Mac QR code.');
          }
          throw new Error('The Mac agent answered ' + res.status + '.');
        }
        return readEventStream(res.body, function (event, data) {
          handleRemoteEvent(activeServerUrl, event, data);
        });
      })
      .catch(function (err) {
        // If the turn already produced its result (final/error/done), a stream
        // close that rejects afterward is benign — don't alarm the teacher.
        if (turnGotFinal) {
          return;
        }
        remoteAppend('error', friendlyStreamError(err));
      })
      .then(function () {
        setRemoteBusy(false);
        if (els.remoteInput) {
          els.remoteInput.focus();
        }
      });
  }

  function showRemote(url) {
    hideAllCards();
    activeServerUrl = url;
    document.body.classList.add('remote-on');
    if (els.remoteServer) {
      els.remoteServer.textContent = (url || '').replace(/^https?:\/\//, '');
    }
    if (els.remoteCard) {
      els.remoteCard.hidden = false;
    }
    // Show the greeting + suggestion chips (a fresh conversation).
    resetFeedToEmpty();
  }

  // ---- card visibility --------------------------------------------------
  // Exactly one of {auto, reconnect+connect} is shown at a time. The brand
  // header is always visible so the screen never looks blank while deciding.
  function hideAllCards() {
    [els.autoCard, els.connectCard, els.reconnectCard, els.remoteCard].forEach(function (card) {
      if (card) {
        card.hidden = true;
      }
    });
  }

  function showConnectingTo(url) {
    document.body.classList.remove('remote-on');
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
    document.body.classList.remove('remote-on');
    if (els.autoCard) {
      els.autoCard.hidden = true;
    }
    if (els.remoteCard) {
      els.remoteCard.hidden = true;
    }
    if (els.connectCard) {
      els.connectCard.hidden = false;
    }
  }

  function setBusy(isBusy) {
    [els.connectBtn, els.scanBtn, els.reconnectBtn, els.remoteSend].forEach(function (btn) {
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
        'Use the iPhone Camera to scan the Mac QR code, or type the address shown in the Mac menu-bar app.'
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
            connectFromScannedCode(paired.url, paired.token);
            return;
          }
        }
        if (els.input) {
          els.input.value = value;
        }
        connectFromScannedCode(value, null);
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
      // If the link has no token, clear any stale token from a previous pairing
      // instead of accidentally sending it to a different server.
      return {
        url: s,
        token: u.searchParams.has('token') ? (u.searchParams.get('token') || null) : null,
      };
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
        committed = false;
        activeServerUrl = '';
        connectFromScannedCode(s.url, s.token);
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
            connectFromScannedCode(s.url, s.token);
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

    // Capture the greeting + suggestion-chip markup so a new conversation can
    // restore it (resetFeedToEmpty re-injects this exact HTML).
    if (els.remoteFeed) {
      emptyHtml = els.remoteFeed.innerHTML;
    }

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

    if (els.remoteSwitch) {
      els.remoteSwitch.addEventListener('click', function () {
        committed = false;
        activeServerUrl = '';
        setRemoteBusy(false);
        revealConnectScreen();
        renderReconnect(loadSavedUrl());
      });
    }

    if (els.remoteForm) {
      els.remoteForm.addEventListener('submit', function (event) {
        event.preventDefault();
        var text = els.remoteInput ? els.remoteInput.value : '';
        if (els.remoteInput) {
          els.remoteInput.value = '';
          els.remoteInput.style.height = '';
        }
        sendRemoteTask(text);
      });
    }

    // Auto-grow the composer textarea up to its max-height.
    if (els.remoteInput) {
      els.remoteInput.addEventListener('input', function () {
        els.remoteInput.style.height = 'auto';
        els.remoteInput.style.height = Math.min(els.remoteInput.scrollHeight, 220) + 'px';
      });
    }

    // Suggestion chips live inside the feed and are re-injected on a new
    // conversation, so wire them by delegation rather than per-node listeners.
    if (els.remoteFeed) {
      els.remoteFeed.addEventListener('click', function (event) {
        var chip = event.target && event.target.closest ? event.target.closest('[data-prompt]') : null;
        if (chip) {
          sendRemoteTask(chip.getAttribute('data-prompt'));
        }
      });
    }

    // New conversation — clear the feed back to the greeting.
    if (els.remoteNew) {
      els.remoteNew.addEventListener('click', function () {
        setRemoteBusy(false);
        resetFeedToEmpty();
      });
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
