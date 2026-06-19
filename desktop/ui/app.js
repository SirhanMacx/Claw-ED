/* Claw-ED for Mac — agent chat UI.
 *
 * Talks to the local clawed sidecar over loopback:
 *   GET  /api/health                       → status + model pills (the REAL pill)
 *   POST /api/gateway/chat/stream          → SSE agent events
 *   POST /api/approvals/{id}/resolve       → Allow once / Always / Deny
 *
 * Runs inside the Tauri shell (window.__TAURI__ present) or, for dev,
 * in a plain browser pointed at the same loopback agent.
 */
"use strict";

const TAURI = window.__TAURI__ || null;
const invoke = TAURI ? TAURI.core.invoke : async () => { throw new Error("no tauri"); };

let BASE = "http://127.0.0.1:8000";

// ── DOM helpers ───────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** Minimal safe markdown: escape everything, then **bold** / *italic* / `code`. */
function renderProse(target, text) {
  target.textContent = "";
  const pattern = /(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;
  for (const part of String(text).split(pattern)) {
    if (!part) continue;
    if (part.startsWith("**") && part.endsWith("**")) {
      target.appendChild(el("b", "", part.slice(2, -2)));
    } else if (part.startsWith("`") && part.endsWith("`")) {
      target.appendChild(el("code", "", part.slice(1, -1)));
    } else if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      target.appendChild(el("i", "", part.slice(1, -1)));
    } else {
      target.appendChild(document.createTextNode(part));
    }
  }
}

// ── Connect / onboarding constants ────────────────────────────────────

const PROVIDER_LABELS = {
  anthropic: "Anthropic (Claude)",
  openai: "OpenAI",
  ollama: "Ollama",
  openrouter: "OpenRouter",
  google: "Google Gemini",
};

const DEFAULT_MODELS = {
  anthropic: "claude-sonnet-4-6",
  openai: "gpt-4.1",
  ollama: "",
  openrouter: "nvidia/nemotron-3-super-120b-a12b:free",
  google: "gemini-2.5-flash",
};

const onboardingState = {
  detected: null,
  selected: null,
  baseSettings: null,
  detectLoaded: false,
};
let onboardingDidAutoLaunch = false;

function show(el) { if (el) el.hidden = false; }
function hide(el) { if (el) el.hidden = true; }

/** status-box helper, mirrors the proven web flow (loading / ok / error). */
function showStatus(el, msg, type) {
  if (!el) return;
  el.hidden = false;
  el.textContent = msg;
  el.className = "status-box mat-result" + (type ? " status-" + type : "");
}

// ── Status pills (driven by REAL health probes) ───────────────────────

let lastSidecar = null; // latest sidecar-status event from the shell
let lastHealth = null;

function paintStatus() {
  const dot = $("statusDot");
  const text = $("statusText");
  const model = $("modelPill");
  const pill = $("statusPill");
  let needsSetup = false;

  if (lastHealth && lastHealth.status === "ok") {
    if (lastHealth.llm_connected) {
      dot.className = "dot ok";
      text.textContent = "Agent ready";
    } else {
      dot.className = "dot warn";
      text.textContent = "Provider needs setup";
      needsSetup = true;
    }
    model.textContent = lastHealth.llm_model || lastHealth.llm_provider || "—";
  } else if (lastSidecar && lastSidecar.state === "starting") {
    dot.className = "dot warn";
    text.textContent = "Agent starting…";
  } else if (lastSidecar && lastSidecar.state === "error") {
    dot.className = "dot stop";
    text.textContent = "Agent problem";
  } else {
    dot.className = "dot stop";
    text.textContent = "Agent offline";
  }

  $("setStatus").textContent = text.textContent +
    (lastSidecar && lastSidecar.state === "error" ? " — " + lastSidecar.detail : "");
  $("setProvider").textContent = lastHealth
    ? `${lastHealth.llm_provider || "—"} · ${lastHealth.llm_model || "—"}`
    : "—";
  if (lastSidecar) {
    $("setSupervision").textContent = lastSidecar.adopted
      ? "Adopted an agent already running on this Mac"
      : lastSidecar.pid
        ? `Supervised by this app (pid ${lastSidecar.pid})`
        : "Supervised by this app";
  }

  // Dead-end routing: surface the status pill as clickable and show the
  // inline "Connect your AI" banner in the empty chat state when the
  // provider isn't configured.
  if (pill) pill.classList.toggle("needs-setup", needsSetup);
  const banner = $("connectBanner");
  if (banner) banner.hidden = !needsSetup;

  // First-run gating: auto-open onboarding once when the agent is up but no
  // provider is connected. Only auto-launch a single time so we don't yank
  // the teacher out of Settings while they're mid-fix.
  if (needsSetup && !onboardingDidAutoLaunch) {
    onboardingDidAutoLaunch = true;
    enterOnboarding();
  }
}

async function pollHealth() {
  try {
    const res = await fetch(`${BASE}/api/health`, { signal: AbortSignal.timeout(3000) });
    lastHealth = res.ok ? await res.json() : null;
  } catch {
    lastHealth = null;
  }
  paintStatus();
}

// ── iPhone pairing ───────────────────────────────────────────────────

async function fetchPairing() {
  const status = $("pairStatus");
  const qr = $("pairQr");
  const wrap = $("pairQrWrap");
  const url = $("pairUrl");
  const help = $("pairHelp");
  if (!status || !qr || !wrap || !url || !help) return;

  status.className = "pair-status";
  status.textContent = "Checking pairing token...";
  help.textContent = "Scan with the iPhone Camera. The device token stays hidden inside the QR.";
  wrap.hidden = true;
  qr.textContent = "";

  if (!TAURI) {
    status.classList.add("warn");
    status.textContent = "Pairing QR is available in the Mac app.";
    help.textContent = "Open the packaged Claw-ED app to pair an iPhone.";
    return;
  }

  try {
    const info = await invoke("pairing_info");
    url.textContent = info.remote_url || "https://clawed.macxlabs.app";
    if (info.token_ready && info.qr_svg) {
      qr.innerHTML = info.qr_svg;
      const svg = qr.querySelector("svg");
      if (svg) {
        svg.setAttribute("role", "img");
        svg.setAttribute("aria-label", "Pairing QR code");
      }
      wrap.hidden = false;
      status.textContent = info.detail || "Ready to pair.";
      return;
    }
    status.classList.add("warn");
    status.textContent = info.detail || "Pairing token is not ready yet.";
    help.textContent = "Restart the agent, then refresh this page.";
  } catch {
    status.classList.add("err");
    status.textContent = "Could not load pairing information.";
    help.textContent = "Restart Claw-ED and try again.";
  }
}

// ── District/admin readiness report ──────────────────────────────────

async function currentToolFacts() {
  let toolCount = skillsCache.length;
  let runCommandRisk = "unknown";
  try {
    const res = await fetch(`${BASE}/api/agent/tools`, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error(String(res.status));
    const data = await res.json();
    const tools = Array.isArray(data.tools) ? data.tools : [];
    toolCount = tools.length;
    const runCommand = tools.find((t) => t.name === "run_command");
    runCommandRisk = runCommand && runCommand.risk_level
      ? runCommand.risk_level
      : runCommandRisk;
  } catch {
    // Keep the report export useful even when the registry call is transiently down.
  }
  return { toolCount, runCommandRisk };
}

async function exportReadinessReport() {
  const result = $("readinessResult");
  result.hidden = false;
  result.className = "mat-result";
  result.textContent = "Collecting live agent facts...";

  if (!TAURI) {
    result.className = "mat-result err";
    result.textContent = "Readiness export is available in the packaged Mac app.";
    return;
  }

  $("readinessBtn").disabled = true;
  try {
    await pollHealth();
    const facts = await currentToolFacts();
    const path = await invoke("export_readiness_report", {
      provider: lastHealth && lastHealth.llm_provider ? String(lastHealth.llm_provider) : "unknown",
      model: lastHealth && lastHealth.llm_model ? String(lastHealth.llm_model) : "unknown",
      llmConnected: !!(lastHealth && lastHealth.llm_connected),
      toolCount: facts.toolCount,
      runCommandRisk: facts.runCommandRisk,
    });
    addToWorkspace(path);
    result.className = "mat-result ok";
    result.textContent = `Saved ${path.replace(/^\/Users\/[^/]+/, "~")} and added it to Workspace.`;
  } catch (err) {
    result.className = "mat-result err";
    result.textContent = err && err.message ? err.message : "Could not export readiness report.";
  } finally {
    $("readinessBtn").disabled = false;
  }
}

// ── Sessions (local, lightweight) ─────────────────────────────────────

const SESS_KEY = "clawed.sessions.v1";
let sessions = [];
let current = null; // {id,title,ts,entries:[…]}

function loadSessions() {
  try { sessions = JSON.parse(localStorage.getItem(SESS_KEY) || "[]"); }
  catch { sessions = []; }
}
function saveSessions() {
  try {
    const slim = sessions.slice(0, 30);
    localStorage.setItem(SESS_KEY, JSON.stringify(slim));
  } catch { /* full disk / private mode — sessions are a convenience */ }
}
function paintSessionList() {
  const list = $("sessionList");
  list.textContent = "";
  for (const s of sessions) {
    const a = el("a", current && s.id === current.id ? "on" : "", s.title);
    a.href = "#";
    a.onclick = (e) => { e.preventDefault(); openSession(s.id); };
    list.appendChild(a);
  }
}
function newSession() {
  current = null;
  $("feed").querySelectorAll(".row, .errnote").forEach((n) => n.remove());
  $("emptyState").hidden = false;
  $("ctxBar").textContent = "✦  New conversation  ·  full Mac access · approvals on";
  paintSessionList();
}
function ensureSession(firstMessage) {
  if (current) return;
  current = {
    id: String(Date.now()),
    title: firstMessage.length > 42 ? firstMessage.slice(0, 42) + "…" : firstMessage,
    ts: Date.now(),
    entries: [],
  };
  sessions.unshift(current);
  $("ctxBar").textContent = `✦  ${current.title}  ·  full Mac access · approvals on`;
  paintSessionList();
}
function record(entry) {
  if (!current) return;
  current.entries.push(entry);
  saveSessions();
}
function openSession(id) {
  const s = sessions.find((x) => x.id === id);
  if (!s) return;
  current = s;
  $("emptyState").hidden = true;
  const feed = $("feed");
  feed.querySelectorAll(".row, .errnote").forEach((n) => n.remove());
  for (const entry of s.entries) {
    if (entry.kind === "user") addUserRow(entry.text);
    else if (entry.kind === "voice") addVoiceRow().finish(entry.text);
    else if (entry.kind === "action") {
      const row = addVoiceRow();
      const card = row.addAction(entry.tool, entry.label);
      card.finish(entry.ok, entry.summary || "");
      row.done();
    } else if (entry.kind === "artifact") {
      const row = addVoiceRow();
      row.addArtifact(entry.path);
      row.done();
    }
  }
  $("ctxBar").textContent = `✦  ${s.title}  ·  full Mac access · approvals on`;
  paintSessionList();
  feed.scrollTop = feed.scrollHeight;
}

// ── Chat rendering ────────────────────────────────────────────────────

function scrollFeed() {
  const feed = $("feed");
  feed.scrollTop = feed.scrollHeight;
}

function addUserRow(text) {
  $("emptyState").hidden = true;
  const row = el("div", "row");
  const av = el("div", "av me", "JM");
  const msg = el("div", "msg");
  msg.appendChild(el("div", "who", "You"));
  const bubble = el("div", "bubble me", text);
  msg.appendChild(bubble);
  row.append(av, msg);
  $("feed").appendChild(row);
  scrollFeed();
}

/** One agent turn: a row that accumulates progress, tool cards,
 *  approval cards, and finally the serif voice reply. */
function addVoiceRow() {
  $("emptyState").hidden = true;
  const row = el("div", "row");
  const av = el("div", "av ai", "c");
  const msg = el("div", "msg");
  msg.appendChild(el("div", "who", "Claw-ED"));
  const stream = el("div", "stream");
  stream.append(el("i"), el("i"), el("i"));
  msg.appendChild(stream);
  row.append(av, msg);
  $("feed").appendChild(row);
  scrollFeed();

  const api = {
    node: row,
    addProgress(message) {
      msg.insertBefore(el("div", "progress-note", message), stream);
      scrollFeed();
    },
    addAction(toolName, label) {
      const card = el("div", "card");
      const act = el("div", "act");
      act.appendChild(el("span", "ic", iconFor(toolName)));
      act.appendChild(document.createTextNode(actionVerb(toolName) + " "));
      const run = el("span", "run", label);
      run.title = label;
      act.appendChild(run);
      const spin = el("span", "spin");
      act.appendChild(spin);
      card.appendChild(act);
      msg.insertBefore(card, stream);
      scrollFeed();
      let out = null;
      return {
        node: card,
        appendOutput(chunk) {
          if (!out) { out = el("pre", "cmd-out"); card.appendChild(out); }
          out.textContent = (out.textContent + chunk).slice(-6000);
          out.scrollTop = out.scrollHeight;
          scrollFeed();
        },
        finish(ok, summary) {
          spin.remove();
          const tick = el("span", ok ? "tick ok" : "tick err", ok ? "✓" : "✗");
          if (summary) tick.title = summary;
          act.appendChild(tick);
        },
      };
    },
    addApproval(data, onResolve) {
      const card = el("div", "card approve");
      const top = el("div", "top");
      top.appendChild(el("span", "", "⛉"));
      top.appendChild(document.createTextNode(approvalTitle(data)));
      card.appendChild(top);
      const what = el("div", "what", data.description || data.tool_name);
      card.appendChild(what);
      const details = el("pre", "what details", JSON.stringify(data.params || {}, null, 2));
      card.appendChild(details);

      const btns = el("div", "btns");
      const once = el("button", "btn primary", "Allow once");
      const always = el("button", "btn", "Always allow");
      const det = el("button", "btn ghost", "Details");
      const deny = el("button", "btn stop", "Deny");
      btns.append(once, always, det, deny);
      card.appendChild(btns);

      det.onclick = () => card.classList.toggle("show-details");
      const resolve = (approved, alwaysFlag) => {
        once.disabled = always.disabled = deny.disabled = true;
        onResolve(approved, alwaysFlag);
      };
      once.onclick = () => resolve(true, false);
      always.onclick = () => resolve(true, true);
      deny.onclick = () => resolve(false, false);

      msg.insertBefore(card, stream);
      scrollFeed();
      return {
        node: card,
        markResolved(approved, alwaysFlag, reason) {
          btns.remove();
          const note = el(
            "div",
            "resolved " + (approved ? "ok" : "no"),
            approved
              ? (alwaysFlag ? "Always allowed — this exact action won't ask again" : "Allowed once")
              : (reason === "timeout" ? "Timed out — not run" : "Denied — not run"),
          );
          card.appendChild(note);
        },
      };
    },
    addArtifact(path) {
      msg.insertBefore(buildArtifactCard(path), stream);
      addToWorkspace(path);
      scrollFeed();
    },
    finish(text) {
      stream.remove();
      const voice = el("div", "bubble voice");
      renderProse(voice, text);
      msg.appendChild(voice);
      scrollFeed();
    },
    fail(message) {
      stream.remove();
      msg.appendChild(el("div", "errnote", message));
      scrollFeed();
    },
    done() { stream.remove(); },
  };
  return api;
}

function iconFor(tool) {
  if (tool === "run_command") return "❯";
  if (tool === "read_file" || tool === "list_directory") return "▣";
  if (tool === "write_file" || tool === "edit_file") return "✎";
  if (tool && tool.startsWith("brain_")) return "◑";
  if (tool === "curriculum_index" || tool === "search_my_materials") return "⌕";
  if (tool && tool.startsWith("self_")) return "◇";
  if (tool && tool.startsWith("generate")) return "✦";
  if (tool && tool.startsWith("drive")) return "▤";
  return "◆";
}
function actionVerb(tool) {
  const verbs = {
    run_command: "Running",
    read_file: "Reading",
    list_directory: "Listing",
    write_file: "Writing",
    edit_file: "Editing",
    research: "Researching",
    curriculum_index: "Searching",
  };
  if (verbs[tool]) return verbs[tool];
  if (tool && tool.startsWith("brain_")) return "Updating";
  if (tool && tool.startsWith("self_")) return "Improving";
  if (tool && tool.startsWith("generate")) return "Generating";
  return "Using";
}
function actionLabel(tool, params) {
  const p = params || {};
  if (tool === "run_command") return p.command || "command";
  if (p.path) return p.path;
  if (p.topic) return p.topic;
  const first = Object.values(p).find((v) => typeof v === "string");
  return first || tool;
}
function approvalTitle(data) {
  if (data.tool_name === "run_command") return "Claw-ED wants to run a command on your Mac";
  if (data.tool_name === "write_file" || data.tool_name === "edit_file") {
    return "Claw-ED wants to change a file";
  }
  if (data.tool_name === "brain_capture" || data.tool_name === "brain_dream" || data.tool_name === "self_distill") {
    return "Claw-ED wants to update its local teaching brain";
  }
  return "Claw-ED wants to act on your Mac";
}

// ── Artifact cards (Direction C — generated work as inline objects) ──

/** What kind of classroom artifact is this file? → label + accent. */
function artifactKind(path) {
  const name = path.split("/").pop().toLowerCase();
  const ext = name.includes(".") ? name.split(".").pop() : "";
  const n = name;
  let kind = "File";
  if (ext === "pptx" || ext === "key") kind = "Slides";
  else if (n.includes("assessment") || n.includes("quiz") || n.includes("test") || n.includes("exam") || n.includes("crq")) kind = "Assessment";
  else if (n.includes("handout") || n.includes("packet") || n.includes("worksheet")) kind = "Handout";
  else if (n.includes("lesson") || n.includes("unit") || n.includes("plan")) kind = "Lesson";
  else if (n.includes("game")) kind = "Game";
  else if (ext === "docx" || ext === "doc" || ext === "rtf") kind = "Document";
  else if (ext === "pdf") kind = "PDF";
  else if (ext === "html" || ext === "htm") kind = "Interactive";
  else if (ext === "md" || ext === "txt") kind = "Notes";
  else if (ext === "csv" || ext === "xlsx") kind = "Data";
  else if (["png", "jpg", "jpeg", "gif", "svg", "webp"].includes(ext)) kind = "Image";
  else if (["mp4", "mov", "webm"].includes(ext)) kind = "Video";
  const accents = {
    Slides: "#C9893F", Assessment: "#8C6FB8", Lesson: "#C96442",
    Handout: "#2F8F6B", Game: "#4A8FBF", PDF: "#B4493A",
    Interactive: "#4A8FBF", Data: "#2F8F6B", Video: "#8C6FB8",
  };
  return { kind, ext: (ext || "file").slice(0, 5), accent: accents[kind] || "" };
}

/** One artifact card: doc glyph + name + kind chip + Open / Show in Finder. */
function buildArtifactCard(path) {
  const name = path.split("/").pop();
  const { kind, ext, accent } = artifactKind(path);
  const card = el("div", "card artifact");
  const doc = el("div", "doc");
  const extTag = el("span", "ext", ext);
  if (accent) extTag.style.setProperty("--doc-accent", accent);
  doc.appendChild(extTag);
  card.appendChild(doc);
  const meta = el("div", "meta");
  meta.appendChild(el("b", "", name));
  const sub = el("div");
  sub.appendChild(el("span", "kind", kind));
  const pathSpan = el("span", "path", path.replace(/^\/Users\/[^/]+/, "~"));
  pathSpan.title = path;
  sub.appendChild(pathSpan);
  meta.appendChild(sub);
  card.appendChild(meta);
  const acts = el("div", "acts");
  const open = el("button", "open", "Open");
  open.title = "Open in the default app";
  open.onclick = () => invoke("open_path", { path }).catch(() => {});
  const reveal = el("button", "open quiet", "Finder");
  reveal.title = "Show in Finder";
  reveal.onclick = () => invoke("reveal_path", { path }).catch(() => {});
  acts.append(open, reveal);
  card.appendChild(acts);
  return card;
}

// ── Workspace collection ──────────────────────────────────────────────

const workspacePaths = new Set();
function addToWorkspace(path) {
  if (workspacePaths.has(path)) return;
  workspacePaths.add(path);
  $("workspaceEmpty").hidden = true;
  $("workspaceList").appendChild(buildArtifactCard(path));
}

// ── SSE chat plane ────────────────────────────────────────────────────

let busy = false;

async function resolveApproval(approvalId, approved, always) {
  try {
    await fetch(`${BASE}/api/approvals/${encodeURIComponent(approvalId)}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved, always }),
    });
  } catch { /* the stream's approval_resolved event is the source of truth */ }
}

// Matches StreamChatRequest.max_length on the server. Guard here so an
// over-long message gets a clear explanation instead of a cryptic HTTP 422.
const MAX_MESSAGE_CHARS = 10000;

async function sendMessage(text) {
  const trimmed = (text || "").trim();
  if (busy || !trimmed) return;
  // Gate: no provider yet → route to onboarding instead of a confusing failure.
  if (lastHealth && lastHealth.status === "ok" && !lastHealth.llm_connected) {
    enterOnboarding();
    return;
  }
  if (trimmed.length > MAX_MESSAGE_CHARS) {
    addUserRow(trimmed.slice(0, 280) + "…");
    addVoiceRow().addProgress(
      `That message is ${trimmed.length.toLocaleString()} characters — the limit is ` +
      `${MAX_MESSAGE_CHARS.toLocaleString()}. Please shorten it and send again.`,
    );
    return;
  }
  busy = true;
  $("sendBtn").disabled = true;

  ensureSession(text.trim());
  addUserRow(text.trim());
  record({ kind: "user", text: text.trim() });

  const turn = addVoiceRow();
  const actionCards = [];      // open tool cards, newest last
  const approvalCards = new Map(); // approval_id → card api
  const seenFiles = new Set(); // dedupe: tool_end + final both list files
  const addArtifactOnce = (path) => {
    if (!path || seenFiles.has(path)) return;
    seenFiles.add(path);
    turn.addArtifact(path);
    record({ kind: "artifact", path });
  };

  const handle = (event, data) => {
    if (event === "progress") {
      turn.addProgress(data.message || "");
    } else if (event === "tool_start") {
      const label = actionLabel(data.tool_name, data.params);
      const card = turn.addAction(data.tool_name, label);
      card.toolName = data.tool_name;
      card.label = label;
      actionCards.push(card);
    } else if (event === "command_output") {
      const open = [...actionCards].reverse().find((c) => !c.finished);
      if (open) open.appendOutput(data.chunk || "");
    } else if (event === "artifact") {
      // Core-first delivery: a finished file streamed mid-build. addArtifactOnce
      // dedupes it against the file list in the turn's tool_end/final.
      if (data.path) addArtifactOnce(data.path);
    } else if (event === "tool_end") {
      const card = [...actionCards].reverse()
        .find((c) => !c.finished && c.toolName === data.tool_name)
        || [...actionCards].reverse().find((c) => !c.finished);
      if (card) {
        card.finished = true;
        card.finish(!!data.ok, data.summary || "");
        record({
          kind: "action", tool: data.tool_name,
          label: card.label || data.tool_name,
          ok: !!data.ok, summary: (data.summary || "").slice(0, 200),
        });
      }
      for (const f of data.files || []) addArtifactOnce(f);
    } else if (event === "approval_required") {
      const card = turn.addApproval(data, (approved, always) => {
        resolveApproval(data.approval_id, approved, always);
      });
      approvalCards.set(data.approval_id, card);
    } else if (event === "approval_resolved") {
      const card = approvalCards.get(data.approval_id);
      if (card) card.markResolved(!!data.approved, !!data.always, data.reason);
    } else if (event === "final") {
      turn.finish(data.text || "");
      record({ kind: "voice", text: data.text || "" });
      for (const f of data.files || []) addArtifactOnce(f);
    } else if (event === "error") {
      turn.fail(data.message || "Something went wrong.");
    }
  };

  try {
    const res = await fetch(`${BASE}/api/gateway/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text.trim() }),
    });
    if (!res.ok || !res.body) {
      throw new Error(`Agent answered ${res.status}`);
    }
    await readSSE(res.body, handle);
  } catch (err) {
    turn.fail(
      "Couldn't reach the agent — it may still be starting. " +
      "Check the status pill, then try again. (" + err.message + ")",
    );
  } finally {
    turn.done();
    busy = false;
    $("sendBtn").disabled = false;
    $("input").focus();
  }
}

/** Parse a text/event-stream body, invoking handle(event, data) per event. */
async function readSSE(body, handle) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue; // comments / keep-alives
      let parsed = {};
      try { parsed = JSON.parse(data); } catch { continue; }
      handle(event, parsed);
    }
  }
}

// ── Skills gallery (the agent's REAL tool registry, grouped) ─────────

/** Group + icon + try-it prompt rules, matched in order against tool names. */
const SKILL_RULES = [
  [/^run_command$/, "Your Mac", "❯", "Run a command for me: "],
  [/^mac_files|^file_manager|^read_workspace/, "Your Mac", "▣", null],
  [/^brain_|^self_|^update_soul|^schedule_task/, "Memory & growth", "◑", null],
  [/^curriculum_index|^search_my_materials|^ingest_materials/, "Indexed materials", "⌕", null],
  [/^generate_lesson_bundle$/, "Create for class", "✦",
    "Make me a complete lesson bundle on "],
  [/^generate_(lesson|unit|materials)/, "Create for class", "✦", "Make me a lesson on "],
  [/^generate_assessment|^sub_packet|^parent_comm/, "Create for class", "✎", null],
  [/^generate_(game|simulation|animation|video)/, "Create for class", "▶", null],
  [/^portfolio_build$/, "Create for class", "▣", null],
  [/^improve_lesson|^differentiate/, "Create for class", "◆", null],
  [/^curriculum|^gap_analysis|^standards|^search_standards/, "Plan & align", "▤", null],
  [/^search_lessons|^student_insights/, "Plan & align", "⌕", null],
  [/style_profile|^set_active_profile/, "Plan & align", "☰", null],
  [/^drive_/, "Google Drive", "▦", null],
  [/^research$|^browser|^wiki/, "Research & web", "⌕", null],
  [/^export_document/, "Create for class", "▣", null],
  [/.*/, "Agent abilities", "◆", null],
];

const TRY_PROMPTS = {
  run_command: "Run a command for me: list what's in my Downloads folder",
  mac_files: "Look in my Desktop folder and tell me what's there",
  generate_lesson: "Make me a lesson on ",
  generate_lesson_bundle: "Make me a complete lesson bundle on ",
  generate_assessment: "Build me a 10-question quiz with an answer key on ",
  generate_unit: "Plan me a full unit on ",
  generate_game: "Make a review game for my class on ",
  differentiate: "Differentiate my last lesson for ENL students",
  improve_lesson: "Improve my last lesson — tighten the timing and add a hook",
  curriculum_map: "Map out my curriculum for the next month",
  gap_analysis: "Run a gap analysis on my curriculum against the standards",
  search_standards: "Which standards cover ",
  research: "Research this and bring back sources: ",
  parent_comm: "Draft a positive parent email about a student who ",
  sub_packet: "Make me a sub packet for tomorrow",
  drive_list: "List what's in my Google Drive",
  search_my_materials: "Search my materials for ",
  ingest_materials: "Learn my style from the lesson files in ",
  get_style_profile: "Show me what you've learned about my teaching style",
  set_active_profile: "Switch my style profile",
  brain_stats: "Show me the teaching brain stats",
  brain_search: "Search the teaching brain for ",
  brain_read: "Read this brain page: ",
  brain_capture: "Capture this as a durable teaching insight: ",
  brain_dream: "Run a dry-run dream cycle and summarize the gaps",
  curriculum_index: "Check my curriculum index status",
  portfolio_build: "Build an advertising-safe sample portfolio from the bundled sample curriculum",
  self_distill: "Analyze my past outputs and improve your teaching rules",
  install_package: "Install a package needed for this task: ",
  create_custom_tool: "Create a custom teacher-assistant skill for ",
  schedule_task: "Every weekday at 6am, prep a Do-Now for my first class",
  switch_model: "Switch to a different AI model",
};

function skillMeta(name) {
  for (const [re, group, icon] of SKILL_RULES) {
    if (re.test(name)) return { group, icon };
  }
  return { group: "Agent abilities", icon: "◆" };
}
function prettySkillName(name) {
  const words = name.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
function firstSentence(text, max = 140) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  if (!clean) return "One of the agent's abilities.";
  const period = clean.indexOf(". ");
  const cut = period > 20 && period < max ? clean.slice(0, period + 1) : clean;
  return cut.length > max ? cut.slice(0, max - 1).trimEnd() + "…" : cut;
}

const GROUP_ORDER = [
  "Your Mac", "Indexed materials", "Memory & growth", "Create for class", "Plan & align",
  "Research & web", "Google Drive", "Agent abilities",
];
let skillsCache = []; // [{name, title, desc, group, icon, asks, try}]

async function fetchSkills() {
  try {
    const res = await fetch(`${BASE}/api/agent/tools`, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error(String(res.status));
    const { tools } = await res.json();
    skillsCache = tools.map((t) => {
      const { group, icon } = skillMeta(t.name);
      return {
        name: t.name,
        title: prettySkillName(t.name),
        desc: firstSentence(t.description),
        group, icon,
        asks: t.risk_level !== "read_only",
        try: TRY_PROMPTS[t.name] || null,
      };
    });
    paintSkills($("skillSearch").value);
  } catch {
    $("skillsEmpty").textContent =
      "Couldn't load the tool registry — is the agent running? It will retry when you reopen this page.";
  }
}

function paintSkills(filter) {
  const root = $("skillGroups");
  root.textContent = "";
  const q = (filter || "").trim().toLowerCase();
  const shown = skillsCache.filter((s) =>
    !q || s.name.includes(q) || s.title.toLowerCase().includes(q) || s.desc.toLowerCase().includes(q));
  if (!shown.length) {
    root.appendChild(el("p", "muted", skillsCache.length
      ? "No skills match that filter."
      : "Loading the agent’s tool registry…"));
    return;
  }
  for (const group of GROUP_ORDER) {
    const items = shown.filter((s) => s.group === group);
    if (!items.length) continue;
    const section = el("div", "skill-group");
    const h = el("h3", "", group);
    h.appendChild(el("span", "count", String(items.length)));
    section.appendChild(h);
    const grid = el("div", "skill-grid");
    for (const s of items) grid.appendChild(buildSkillCard(s));
    section.appendChild(grid);
    root.appendChild(section);
  }
}

function buildSkillCard(s) {
  const card = el("div", "skill");
  const top = el("div", "s-top");
  top.appendChild(el("span", "s-ic", s.icon));
  const title = el("b", "", s.title);
  title.title = s.name;
  top.appendChild(title);
  top.appendChild(el("span", s.asks ? "risk asks" : "risk", s.asks ? "asks first" : "read-only"));
  card.appendChild(top);
  card.appendChild(el("p", "", s.desc));
  const btn = el("button", "try", "Try it");
  btn.onclick = () => trySkill(s);
  card.appendChild(btn);
  return card;
}

/** Insert the skill's starter prompt into the composer and focus it. */
function trySkill(s) {
  const text = s.try || `Use your ${s.title.toLowerCase()} ability to `;
  showView("chat");
  const input = $("input");
  input.value = text;
  input.dispatchEvent(new Event("input"));
  input.focus();
  input.setSelectionRange(text.length, text.length);
}

// ── Your Materials (style profiles — the INGEST surface) ─────────────

let ingestPolling = null;
let activeProfileName = null;

function paintStyleChip() {
  const chip = $("styleChip");
  if (activeProfileName) {
    chip.textContent = `Style: ${activeProfileName}`;
    chip.classList.add("on");
  } else {
    chip.textContent = "Default style";
    chip.classList.remove("on");
  }
}

async function fetchProfiles() {
  try {
    const res = await fetch(`${BASE}/api/style/profiles`, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error(String(res.status));
    const { active, profiles } = await res.json();
    const activeProfile = profiles.find((p) => p.profile_id === active);
    activeProfileName = activeProfile ? activeProfile.name : null;
    paintStyleChip();
    paintProfiles(profiles, active);
  } catch {
    const empty = $("profilesEmpty");
    if (empty) empty.textContent =
      "Couldn't load style profiles — is the agent running?";
  }
}

function paintProfiles(profiles, activeId) {
  const root = $("profileList");
  root.textContent = "";
  if (!profiles.length) {
    root.appendChild(el("p", "muted",
      "No style profiles yet — choose a folder of your lesson files above and Claw-ED will learn how you write."));
    return;
  }
  for (const p of profiles) root.appendChild(buildProfileCard(p, p.profile_id === activeId));
  if (activeId) {
    const off = el("button", "btn ghost mat-off", "Use default MacxLabs style (turn profile off)");
    off.onclick = async () => {
      await fetch(`${BASE}/api/style/deactivate`, { method: "POST" }).catch(() => {});
      fetchProfiles();
    };
    root.appendChild(off);
  }
}

/** The STYLE PROFILE CARD: human-readable summary + structure diagram. */
function buildProfileCard(p, isActive) {
  const card = el("div", "card pad profile-card" + (isActive ? " active" : ""));

  const top = el("div", "p-top");
  top.appendChild(el("b", "", p.name));
  top.appendChild(el("span", isActive ? "p-state on" : "p-state", isActive ? "Active" : "Saved"));
  card.appendChild(top);

  const meta = el("div", "p-meta",
    `Learned from ${p.files_analyzed} file${p.files_analyzed === 1 ? "" : "s"}` +
    (p.files_skipped ? ` (${p.files_skipped} skipped)` : "") +
    ` · ${(p.source_path || "").replace(/^\/Users\/[^/]+/, "~")}`);
  card.appendChild(meta);

  if (p.voice_description) card.appendChild(el("p", "p-voice", p.voice_description));
  if (p.structure_summary) card.appendChild(el("p", "p-structure", p.structure_summary));

  // Structure diagram: the lesson flow as connected chips with frequency.
  const common = (p.lesson_structure || []).filter((s) => s.frequency >= 0.2 && s.name !== "Answer Key");
  if (common.length) {
    const flow = el("div", "p-flow");
    common.slice(0, 7).forEach((s, i) => {
      if (i) flow.appendChild(el("span", "p-arrow", "→"));
      const chipEl = el("span", "p-sec", s.name);
      chipEl.title = `${Math.round(s.frequency * 100)}% of your lessons`;
      chipEl.appendChild(el("i", "", ` ${Math.round(s.frequency * 100)}%`));
      flow.appendChild(chipEl);
    });
    card.appendChild(flow);
  }

  const facts = [];
  if ((p.question_types || []).length) facts.push(["Assessments", p.question_types.slice(0, 4).join(", ")]);
  if (p.answer_key_style) facts.push(["Answer keys", p.answer_key_style]);
  if (p.mc_letter_note) facts.push(["MC balance", p.mc_letter_note]);
  if ((p.scaffolds || []).length) facts.push(["Scaffolds", p.scaffolds.slice(0, 5).join(", ")]);
  if ((p.point_values || []).length) facts.push(["Point values", p.point_values.join(", ")]);
  for (const [k, v] of facts) {
    const rowEl = el("div", "p-fact");
    rowEl.appendChild(el("span", "p-k", k));
    rowEl.appendChild(el("span", "p-v", v));
    card.appendChild(rowEl);
  }

  if ((p.exemplars || []).length) {
    const ex = p.exemplars[0];
    const q = el("div", "p-exemplar", `“${ex.snippet.slice(0, 200)}”`);
    q.title = `From ${ex.source}`;
    card.appendChild(q);
  }

  const btns = el("div", "btns p-btns");
  if (!isActive) {
    const use = el("button", "btn primary", "Use this style");
    use.onclick = async () => {
      await fetch(`${BASE}/api/style/profiles/${encodeURIComponent(p.profile_id)}/activate`,
        { method: "POST" }).catch(() => {});
      fetchProfiles();
    };
    btns.appendChild(use);
  }
  const re = el("button", "btn", "Re-ingest");
  re.title = "Re-read the folder — only new or changed files are analyzed";
  re.onclick = () => startIngest(p.source_path, p.name);
  btns.appendChild(re);
  const rm = el("button", "btn stop", "Remove");
  rm.onclick = async () => {
    await fetch(`${BASE}/api/style/profiles/${encodeURIComponent(p.profile_id)}`,
      { method: "DELETE" }).catch(() => {});
    fetchProfiles();
  };
  btns.appendChild(rm);
  card.appendChild(btns);
  return card;
}

async function pickFolder() {
  try {
    const path = await invoke("pick_folder");
    if (path) {
      $("ingestPath").value = path;
      if (!$("ingestName").value) {
        const base = path.replace(/\/+$/, "").split("/").pop();
        $("ingestName").value = base || "";
      }
    }
  } catch { /* user cancelled, or not in the Tauri shell */ }
}

async function startIngest(path, name) {
  path = (path || "").trim();
  if (!path) { $("ingestPath").focus(); return; }
  $("ingestResult").hidden = true;
  $("ingestProgress").hidden = false;
  $("ingestProgressText").textContent = "Scanning folder…";
  $("ingestBtn").disabled = true;
  try {
    const res = await fetch(`${BASE}/api/style/ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, profile_name: (name || "").trim() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `Agent answered ${res.status}`);
    if (!ingestPolling) ingestPolling = setInterval(pollIngest, 1200);
  } catch (err) {
    $("ingestProgress").hidden = true;
    $("ingestBtn").disabled = false;
    const r = $("ingestResult");
    r.hidden = false;
    r.className = "mat-result err";
    r.textContent = err.message;
  }
}

async function pollIngest() {
  let job = null;
  try {
    const res = await fetch(`${BASE}/api/style/ingest/status`, { signal: AbortSignal.timeout(5000) });
    job = res.ok ? await res.json() : null;
  } catch { /* transient — keep polling */ }
  if (!job) return;
  if (job.status === "running") {
    $("ingestProgress").hidden = false;
    $("ingestProgressText").textContent = job.progress || "Reading your files…";
    return;
  }
  clearInterval(ingestPolling);
  ingestPolling = null;
  $("ingestProgress").hidden = true;
  $("ingestBtn").disabled = false;
  if (job.status === "done") {
    const r = $("ingestResult");
    r.hidden = false;
    r.className = "mat-result ok";
    r.textContent =
      `Done — learned from ${job.files_ingested} file(s)` +
      (job.files_skipped ? `, skipped ${job.files_skipped}` : "") +
      ". Your new lessons will match this style.";
    fetchProfiles();
  } else if (job.status === "error") {
    const r = $("ingestResult");
    r.hidden = false;
    r.className = "mat-result err";
    r.textContent = job.result_text || "Ingest failed.";
  }
}

// ── Theme (Direction B — dark "Console" is a theme, not a fork) ──────

const THEME_KEY = "clawed.theme.v1";
function applyTheme(name) {
  const theme = name === "console" ? "console" : "studio";
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* private mode */ }
  for (const b of document.querySelectorAll("[data-theme-pick]")) {
    b.classList.toggle("on", b.dataset.themePick === theme);
  }
}
function currentTheme() {
  return document.documentElement.dataset.theme === "console" ? "console" : "studio";
}
function toggleTheme() {
  applyTheme(currentTheme() === "console" ? "studio" : "console");
}

// ── ⌘K command palette ───────────────────────────────────────────────

let paletteSel = 0;

function paletteItems(query) {
  const q = query.trim().toLowerCase();
  const items = [];
  const cmd = (icon, label, run, kind = "command") => ({ icon, label, run, kind });

  items.push(cmd("✚", "New chat", () => { newSession(); showView("chat"); }));
  items.push(cmd("◑", currentTheme() === "console"
    ? "Switch to Studio (light) theme" : "Switch to Console (dark) theme", toggleTheme));
  items.push(cmd("✦", "Go to Chat", () => showView("chat")));
  items.push(cmd("◆", "Go to Skills", () => showView("skills")));
  items.push(cmd("☰", "Go to Your Materials (style profiles)", () => showView("materials")));
  items.push(cmd("▣", "Go to Workspace", () => showView("workspace")));
  items.push(cmd("▢", "Go to Pair iPhone", () => showView("pair")));
  items.push(cmd("⚙", "Go to Settings", () => showView("settings")));
  items.push(cmd("✧", "Connect your AI", () => enterOnboarding()));
  items.push(cmd("↻", "Restart agent", () => invoke("restart_sidecar").catch(() => {})));
  items.push(cmd("✓", "Export district readiness report", exportReadinessReport));

  for (const s of sessions.slice(0, 25)) {
    items.push({
      icon: "✉", label: s.title, kind: "session",
      run: () => { openSession(s.id); showView("chat"); },
    });
  }
  for (const s of skillsCache) {
    items.push({
      icon: s.icon, label: `${s.title} — ${s.desc}`, kind: "skill",
      run: () => trySkill(s),
    });
  }
  return q ? items.filter((i) => i.label.toLowerCase().includes(q)) : items.slice(0, 12);
}

function paintPalette() {
  const list = $("paletteList");
  const items = paletteItems($("paletteInput").value);
  list.textContent = "";
  if (!items.length) {
    list.appendChild(el("div", "palette-none", "Nothing matches."));
    return;
  }
  paletteSel = Math.max(0, Math.min(paletteSel, items.length - 1));
  items.forEach((item, i) => {
    const row = el("div", "palette-item" + (i === paletteSel ? " sel" : ""));
    row.appendChild(el("span", "p-ic", item.icon));
    row.appendChild(el("span", "p-label", item.label));
    row.appendChild(el("span", "p-kind", item.kind));
    row.onclick = () => { closePalette(); item.run(); };
    row.onmousemove = () => {
      if (paletteSel !== i) { paletteSel = i; paintPalette(); }
    };
    list.appendChild(row);
  });
  const sel = list.children[paletteSel];
  if (sel && sel.scrollIntoView) sel.scrollIntoView({ block: "nearest" });
}

function openPalette() {
  paletteSel = 0;
  $("paletteInput").value = "";
  $("paletteVeil").hidden = false;
  paintPalette();
  $("paletteInput").focus();
}
function closePalette() {
  $("paletteVeil").hidden = true;
  if (!$("view-chat").hidden) $("input").focus();
}
function paletteKeydown(e) {
  if (e.key === "Escape") { e.preventDefault(); closePalette(); }
  else if (e.key === "ArrowDown") { e.preventDefault(); paletteSel += 1; paintPalette(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); paletteSel -= 1; paintPalette(); }
  else if (e.key === "Enter") {
    e.preventDefault();
    const items = paletteItems($("paletteInput").value);
    const item = items[Math.max(0, Math.min(paletteSel, items.length - 1))];
    if (item) { closePalette(); item.run(); }
  }
}

// ── Connect / onboarding flow (ported from the proven web wizard) ─────
// EVERY fetch is BASE-prefixed — the native UI talks to an absolute
// loopback base, not relative paths.

/** Pull current settings once so a save preserves unrelated fields. */
function loadBaseSettings() {
  return fetch(`${BASE}/api/settings`)
    .then((r) => r.json())
    .then((s) => { onboardingState.baseSettings = s || {}; return onboardingState.baseSettings; })
    .catch(() => { onboardingState.baseSettings = {}; return onboardingState.baseSettings; });
}

function defaultModelFor(prov) {
  const d = onboardingState.detected;
  if (prov === "ollama" && d && d.provider === "ollama" && d.models && d.models.length) {
    return d.models[0];
  }
  return DEFAULT_MODELS[prov] || "";
}

/** POST /api/settings then GET /api/settings/test-connection. */
function saveAndTest(provider, apiKey, model, cb) {
  const bs = onboardingState.baseSettings || {};
  const body = {
    provider,
    api_key: apiKey || null,
    anthropic_model: bs.anthropic_model || DEFAULT_MODELS.anthropic,
    openai_model: bs.openai_model || DEFAULT_MODELS.openai,
    ollama_model: bs.ollama_model || "llama3.2",
    ollama_base_url: bs.ollama_base_url || "http://localhost:11434",
    openrouter_model: bs.openrouter_model || DEFAULT_MODELS.openrouter,
    google_model: bs.google_model || DEFAULT_MODELS.google,
    include_homework: (bs.include_homework !== undefined) ? bs.include_homework : true,
    export_format: bs.export_format || "markdown",
  };
  if (model) body[provider + "_model"] = model;

  fetch(`${BASE}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json().then((j) => ({ ok: r.ok, data: j })))
    .then((res) => {
      if (!res.ok || (res.data && res.data.error)) {
        cb(false, (res.data && res.data.error) || "Could not save settings.", null);
        return;
      }
      onboardingState.baseSettings = Object.assign({}, bs, { provider });
      onboardingState.baseSettings[provider + "_model"] = model || body[provider + "_model"];
      return fetch(`${BASE}/api/settings/test-connection`)
        .then((r) => r.json())
        .then((t) => {
          if (t && t.connected) {
            cb(true, t.message || "", t.model || model);
            return;
          }
          // The tester only validates ollama/anthropic/openai; openrouter and
          // google come back "Unknown provider" though the save succeeded.
          // Confirm via /health (key present) so we don't falsely block.
          const errText = (t && (t.error || t.message)) || "";
          if (/unknown provider/i.test(errText)) {
            return fetch(`${BASE}/api/health`)
              .then((r) => r.json())
              .then((h) => {
                if (h && h.llm_connected) {
                  cb(true, "", (h.llm_model || model), true);
                } else {
                  cb(false, "Saved, but Claw-ED could not confirm a working key. Double-check your key and model, then try again.", null);
                }
              });
          }
          cb(false, errText || "The provider rejected the connection. Double-check your key and model.", null);
        });
    }).catch((err) => {
      cb(false, "Connection error: " + err, null);
    });
}

function onboardingShowChooser() {
  hide($("onb-detected"));
  hide($("onb-success"));
  show($("onb-chooser"));
}

function onboardingDetect() {
  const detecting = $("onb-detecting");
  show(detecting);
  hide($("onb-detected"));
  hide($("onb-chooser"));
  hide($("onb-success"));

  fetch(`${BASE}/api/onboarding/detect`, { signal: AbortSignal.timeout(5000) })
    .then((r) => r.json())
    .then((data) => {
      hide(detecting);
      const list = (data && data.detected) || [];
      if (data && data.any && list.length) {
        let pick = null;
        for (let i = 0; i < list.length; i++) {
          if (list[i].ready) { pick = list[i]; break; }
        }
        if (!pick) pick = list[0];
        onboardingState.detected = pick;
        const label = $("onb-detected-label");
        const note = $("onb-detected-note");
        if (label) label.textContent = "We found " + (pick.label || PROVIDER_LABELS[pick.provider] || pick.provider) + " on your machine";
        if (note) note.textContent = pick.note || "Ready to use.";
        show($("onb-detected"));
      } else {
        onboardingShowChooser();
      }
    })
    .catch(() => {
      hide(detecting);
      onboardingShowChooser();
    });
}

function onboardingShowSuccess(provider, model, soft) {
  hide($("onb-detected"));
  hide($("onb-chooser"));
  hide($("onb-detecting"));
  const title = $("onb-success-title");
  const label = PROVIDER_LABELS[provider] || provider;
  if (title) {
    if (model) {
      title.textContent = soft
        ? (label + " is set up — using " + model + "!")
        : ("Connected — using " + model + "!");
    } else {
      title.textContent = soft
        ? (label + " is set up and ready!")
        : ("Connected to " + label + "!");
    }
  }
  show($("onb-success"));
  pollHealth();
}

/** Switch to the onboarding view and (re)run detection. */
function enterOnboarding() {
  if (!onboardingState.detectLoaded) {
    onboardingState.detectLoaded = true;
    loadBaseSettings().then(() => onboardingDetect());
  } else {
    onboardingDetect();
  }
  showView("onboarding");
}

function setupOnboardingCards() {
  const cards = $("onb-cards");
  const formWrap = $("onb-form-wrap");
  if (!cards) return;
  for (const card of cards.querySelectorAll(".connect-card")) {
    card.addEventListener("click", () => {
      const prov = card.dataset.provider;
      onboardingState.selected = prov;
      for (const c of cards.querySelectorAll(".connect-card")) c.classList.remove("active");
      card.classList.add("active");
      for (const p of ["anthropic", "openai", "ollama", "openrouter", "google"]) {
        const f = $("onb-" + p);
        if (f) f.hidden = (p !== prov);
      }
      const modelInput = $("onb-" + prov + "-model");
      if (modelInput && prov === "ollama" && !modelInput.value) {
        modelInput.value = defaultModelFor("ollama");
      }
      hide($("onb-status"));
      show(formWrap);
      if (formWrap && typeof formWrap.scrollIntoView === "function") {
        formWrap.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    });
  }
}

/** Wire every Show/Hide toggle next to a key field (onboarding + settings). */
function setupShowKeyToggles() {
  for (const btn of document.querySelectorAll(".connect-show-key")) {
    btn.addEventListener("click", () => {
      const input = btn.previousElementSibling;
      if (input && input.tagName === "INPUT") {
        input.type = input.type === "password" ? "text" : "password";
        btn.textContent = input.type === "password" ? "Show" : "Hide";
      }
    });
  }
}

function setupOnboardingButtons() {
  const useBtn = $("onb-use-detected");
  if (useBtn) {
    useBtn.addEventListener("click", () => {
      const d = onboardingState.detected;
      if (!d) { onboardingShowChooser(); return; }
      useBtn.disabled = true;
      useBtn.textContent = "Connecting…";
      const status = $("onb-detected-status");
      showStatus(status, "Connecting to " + (d.label || d.provider) + "…", "loading");

      let model = "";
      if (d.provider === "ollama") {
        model = defaultModelFor("ollama");
      } else {
        const bs = onboardingState.baseSettings || {};
        model = bs[d.provider + "_model"] || DEFAULT_MODELS[d.provider] || "";
      }
      saveAndTest(d.provider, "", model, (ok, msg, testedModel, soft) => {
        useBtn.disabled = false;
        useBtn.textContent = "Use it & continue";
        if (ok) onboardingShowSuccess(d.provider, testedModel || model, soft);
        else showStatus(status, msg || "Could not connect. Try a different provider.", "error");
      });
    });
  }

  const chooserBtn = $("onb-show-chooser");
  if (chooserBtn) chooserBtn.addEventListener("click", () => onboardingShowChooser());

  const submit = $("onb-submit");
  if (submit) {
    submit.addEventListener("click", () => {
      const prov = onboardingState.selected;
      if (!prov) { showStatus($("onb-status"), "Pick a provider first.", "error"); return; }

      const keyInput = $("onb-" + prov + "-key");
      const modelInput = $("onb-" + prov + "-model");
      const apiKey = keyInput ? keyInput.value.trim() : "";
      const model = modelInput ? modelInput.value.trim() : "";

      if (prov !== "ollama" && !apiKey) {
        const bs = onboardingState.baseSettings || {};
        if (!bs["has_" + prov + "_key"]) {
          showStatus($("onb-status"), "Please paste your API key above.", "error");
          if (keyInput) keyInput.focus();
          return;
        }
      }
      if (!model && prov === "ollama") {
        showStatus($("onb-status"), "Enter the Ollama model name you pulled (e.g. qwen3.5).", "error");
        if (modelInput) modelInput.focus();
        return;
      }

      submit.disabled = true;
      submit.textContent = "Connecting…";
      showStatus($("onb-status"), "Saving and testing your connection…", "loading");
      saveAndTest(prov, apiKey, model, (ok, msg, testedModel, soft) => {
        submit.disabled = false;
        submit.textContent = "Connect";
        if (ok) onboardingShowSuccess(prov, testedModel || model, soft);
        else showStatus($("onb-status"), msg || "Could not connect. Check your key and try again.", "error");
      });
    });
  }

  const cont = $("onb-continue");
  if (cont) {
    cont.addEventListener("click", () => {
      showView("chat");
      newSession();
    });
  }
}

// ── Settings view: editable provider/key/model ────────────────────────

function updateKeyRowVisibility(provider) {
  const keyRow = $("setKeyRow");
  if (keyRow) keyRow.style.display = provider === "ollama" ? "none" : "block";
}

function loadSettingsIntoForm() {
  fetch(`${BASE}/api/settings`)
    .then((r) => r.json())
    .then((settings) => {
      if (!settings) return;
      onboardingState.baseSettings = settings; // keep saveAndTest in sync
      const provSelect = $("setProviderSelect");
      const modelInput = $("setModelInput");
      if (provSelect && settings.provider) {
        provSelect.value = settings.provider;
        updateKeyRowVisibility(settings.provider);
      }
      if (modelInput) {
        const prov = settings.provider;
        modelInput.value = settings[prov + "_model"] || DEFAULT_MODELS[prov] || "";
      }
    })
    .catch(() => {});
}

function setupSettingsUI() {
  const provSelect = $("setProviderSelect");
  const testBtn = $("setTestConnBtn");
  const saveBtn = $("setSaveSettingsBtn");

  if (provSelect) {
    provSelect.addEventListener("change", function () {
      updateKeyRowVisibility(this.value);
      const modelInput = $("setModelInput");
      const bs = onboardingState.baseSettings || {};
      if (modelInput) modelInput.value = bs[this.value + "_model"] || DEFAULT_MODELS[this.value] || "";
    });
  }

  if (testBtn) {
    testBtn.addEventListener("click", () => {
      testBtn.disabled = true;
      const result = $("setSettingsResult");
      showStatus(result, "Testing connection…", "loading");
      fetch(`${BASE}/api/settings/test-connection`)
        .then((r) => r.json())
        .then((t) => {
          testBtn.disabled = false;
          if (t && t.connected) showStatus(result, "Connected! " + (t.message || ""), "ok");
          else showStatus(result, (t && (t.error || t.message)) || "Connection failed.", "error");
        })
        .catch((err) => { testBtn.disabled = false; showStatus(result, "Test error: " + err, "error"); });
    });
  }

  if (saveBtn) {
    saveBtn.addEventListener("click", () => {
      const provider = $("setProviderSelect").value;
      const apiKey = $("setKeyInput").value.trim();
      const model = $("setModelInput").value.trim();
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving…";
      const result = $("setSettingsResult");
      showStatus(result, "Saving settings…", "loading");
      saveAndTest(provider, apiKey, model, (ok, msg, testedModel, soft) => {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save settings";
        if (ok) {
          showStatus(result, "Settings saved and connection confirmed!", "ok");
          if ($("setKeyInput")) $("setKeyInput").value = "";
          pollHealth();
        } else {
          showStatus(result, msg || "Could not save settings.", "error");
        }
      });
    });
  }
}

// ── Views + composer wiring ───────────────────────────────────────────

function showView(name) {
  for (const v of document.querySelectorAll(".view")) v.hidden = true;
  $(`view-${name}`).hidden = false;
  for (const a of document.querySelectorAll(".nav a")) {
    a.classList.toggle("on", a.dataset.view === name);
  }
  if (name === "chat") $("input").focus();
  if (name === "skills" && !skillsCache.length) fetchSkills();
  if (name === "materials") fetchProfiles();
  if (name === "pair") fetchPairing();
  if (name === "settings") loadSettingsIntoForm();
}

function init() {
  // Nav
  for (const a of document.querySelectorAll(".nav a")) {
    a.onclick = (e) => { e.preventDefault(); showView(a.dataset.view); };
  }
  $("newChatBtn").onclick = newSession;

  // Composer
  const input = $("input");
  const autosize = () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  };
  input.addEventListener("input", autosize);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const text = input.value;
      input.value = "";
      autosize();
      sendMessage(text);
    }
  });
  $("sendBtn").onclick = () => {
    const text = input.value;
    input.value = "";
    autosize();
    sendMessage(text);
  };
  for (const chip of document.querySelectorAll(".chip[data-suggest]")) {
    chip.onclick = () => sendMessage(chip.dataset.suggest);
  }
  $("teachChip").onclick = () => showView("materials");

  // Connect / onboarding wiring
  setupOnboardingCards();
  setupOnboardingButtons();
  setupShowKeyToggles();
  setupSettingsUI();

  // Dead-end routing: the "Provider needs setup" pill and the inline empty-state
  // banner both open the in-window onboarding panel.
  $("statusPill").onclick = () => {
    if (lastHealth && lastHealth.status === "ok" && !lastHealth.llm_connected) enterOnboarding();
  };
  const connectBannerBtn = $("connectBannerBtn");
  if (connectBannerBtn) connectBannerBtn.onclick = () => enterOnboarding();

  // Your Materials (ingest + profiles)
  $("pickFolderBtn").onclick = pickFolder;
  $("ingestBtn").onclick = () => startIngest($("ingestPath").value, $("ingestName").value);
  $("ingestPath").addEventListener("keydown", (e) => {
    if (e.key === "Enter") startIngest($("ingestPath").value, $("ingestName").value);
  });
  $("styleChip").onclick = () => showView("materials");

  $("refreshPairBtn").onclick = fetchPairing;

  $("restartBtn").onclick = () => invoke("restart_sidecar").catch(() => {});
  $("readinessBtn").onclick = exportReadinessReport;

  // Theme (persisted; default Studio)
  let savedTheme = "studio";
  try { savedTheme = localStorage.getItem(THEME_KEY) || "studio"; } catch { /* default */ }
  applyTheme(savedTheme);
  for (const b of document.querySelectorAll("[data-theme-pick]")) {
    b.onclick = () => applyTheme(b.dataset.themePick);
  }

  // Skills gallery
  $("skillSearch").addEventListener("input", () => paintSkills($("skillSearch").value));

  // ⌘K command palette
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if ($("paletteVeil").hidden) openPalette(); else closePalette();
    } else if (e.key === "Escape" && !$("paletteVeil").hidden) {
      e.preventDefault();
      closePalette();
    }
  });
  $("paletteInput").addEventListener("input", () => { paletteSel = 0; paintPalette(); });
  $("paletteInput").addEventListener("keydown", paletteKeydown);
  $("paletteVeil").onclick = (e) => { if (e.target === $("paletteVeil")) closePalette(); };

  loadSessions();
  paintSessionList();

  // Shell integration
  (async () => {
    if (TAURI) {
      try { BASE = await invoke("agent_base_url"); } catch { /* default */ }
      $("setUrl").textContent = BASE;
      try {
        await TAURI.event.listen("sidecar-status", (e) => {
          lastSidecar = e.payload;
          paintStatus();
        });
        lastSidecar = await invoke("sidecar_state");
      } catch { /* events unavailable — health polling still drives the pill */ }
    }
    pollHealth();
    setInterval(pollHealth, 3000);
    fetchSkills(); // after BASE is resolved — feeds the gallery + palette
    fetchProfiles(); // drives the composer style chip
    // Resume polling if an ingest was already running when the app opened.
    pollIngest().then(() => {
      if (!ingestPolling && !$("ingestProgress").hidden) {
        ingestPolling = setInterval(pollIngest, 1200);
      }
    }).catch(() => {});
  })();

  input.focus();
}

document.addEventListener("DOMContentLoaded", init);
