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

// ── Status pills (driven by REAL health probes) ───────────────────────

let lastSidecar = null; // latest sidecar-status event from the shell
let lastHealth = null;

function paintStatus() {
  const dot = $("statusDot");
  const text = $("statusText");
  const model = $("modelPill");

  if (lastHealth && lastHealth.status === "ok") {
    if (lastHealth.llm_connected) {
      dot.className = "dot ok";
      text.textContent = "Agent ready";
    } else {
      dot.className = "dot warn";
      text.textContent = "Provider needs setup";
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
      const name = path.split("/").pop();
      const card = el("div", "card artifact");
      card.appendChild(el("div", "doc"));
      const meta = el("div", "meta");
      meta.appendChild(el("b", "", name));
      meta.appendChild(el("span", "", path));
      card.appendChild(meta);
      const open = el("button", "open", "Open");
      open.onclick = () => invoke("open_path", { path }).catch(() => {});
      card.appendChild(open);
      msg.insertBefore(card, stream);
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
  };
  if (verbs[tool]) return verbs[tool];
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
  return "Claw-ED wants to act on your Mac";
}

// ── Workspace collection ──────────────────────────────────────────────

const workspacePaths = new Set();
function addToWorkspace(path) {
  if (workspacePaths.has(path)) return;
  workspacePaths.add(path);
  $("workspaceEmpty").hidden = true;
  const name = path.split("/").pop();
  const card = el("div", "card artifact");
  card.appendChild(el("div", "doc"));
  const meta = el("div", "meta");
  meta.appendChild(el("b", "", name));
  meta.appendChild(el("span", "", path));
  card.appendChild(meta);
  const open = el("button", "open", "Open");
  open.onclick = () => invoke("open_path", { path }).catch(() => {});
  card.appendChild(open);
  $("workspaceList").appendChild(card);
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

async function sendMessage(text) {
  if (busy || !text.trim()) return;
  busy = true;
  $("sendBtn").disabled = true;

  ensureSession(text.trim());
  addUserRow(text.trim());
  record({ kind: "user", text: text.trim() });

  const turn = addVoiceRow();
  const actionCards = [];      // open tool cards, newest last
  const approvalCards = new Map(); // approval_id → card api

  const handle = (event, data) => {
    if (event === "progress") {
      turn.addProgress(data.message || "");
    } else if (event === "tool_start") {
      const label = actionLabel(data.tool_name, data.params);
      const card = turn.addAction(data.tool_name, label);
      card.toolName = data.tool_name;
      actionCards.push(card);
    } else if (event === "command_output") {
      const open = [...actionCards].reverse().find((c) => !c.finished);
      if (open) open.appendOutput(data.chunk || "");
    } else if (event === "tool_end") {
      const card = [...actionCards].reverse()
        .find((c) => !c.finished && c.toolName === data.tool_name)
        || [...actionCards].reverse().find((c) => !c.finished);
      if (card) {
        card.finished = true;
        card.finish(!!data.ok, data.summary || "");
        record({
          kind: "action", tool: data.tool_name,
          label: actionLabel(data.tool_name, {}) === data.tool_name ? data.tool_name : data.tool_name,
          ok: !!data.ok, summary: (data.summary || "").slice(0, 200),
        });
      }
      for (const f of data.files || []) turn.addArtifact(f);
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
      for (const f of data.files || []) {
        turn.addArtifact(f);
        record({ kind: "artifact", path: f });
      }
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

// ── Skills gallery (curated — surfacing the agent's real tools) ──────

const SKILLS = [
  ["❯", "Act on this Mac", "Run commands, move files, organize folders — every action asks you first."],
  ["✦", "Generate a lesson", "A full classroom-ready lesson on any topic, in your style."],
  ["✎", "Build an assessment", "Quizzes, tests, and CRQs with answer keys."],
  ["▤", "Curriculum map", "Plan a unit or a whole course, aligned to your standards."],
  ["◆", "Differentiate", "Adapt any material for ENL, IEP, or advanced students."],
  ["🔎", "Research", "Look something up on the web and bring back sources."],
  ["▣", "Read your files", "Pull data from CSVs, docs, and folders anywhere in your home."],
  ["✉", "Parent communication", "Draft professional parent emails in the right tone."],
  ["📄", "Sub packet", "A complete substitute-teacher packet in one ask."],
  ["▦", "Google Drive", "List, read, organize, and upload your Drive files."],
];
function paintSkills() {
  const grid = $("skillGrid");
  for (const [icon, title, desc] of SKILLS) {
    const card = el("div", "skill");
    card.appendChild(el("div", "s-ic", icon));
    card.appendChild(el("b", "", title));
    card.appendChild(el("p", "", desc));
    grid.appendChild(card);
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
  for (const chip of document.querySelectorAll(".chip")) {
    chip.onclick = () => sendMessage(chip.dataset.suggest);
  }

  $("restartBtn").onclick = () => invoke("restart_sidecar").catch(() => {});

  paintSkills();
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
  })();

  input.focus();
}

document.addEventListener("DOMContentLoaded", init);
