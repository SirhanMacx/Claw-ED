//! Sidecar supervision for the clawed Python agent.
//!
//! Port of the proven Swift logic in
//! `mac-app/Sources/ClawEDMenuBar/{ServerController,LaunchPlan,AppEnvironment}.swift`
//! with one addition: **adoption**. On Jon's always-on Mac the agent already
//! runs as a launchd service on 127.0.0.1:8000 — if a healthy agent is
//! already answering, we adopt it instead of fighting over the port. On a
//! fresh Mac we spawn and supervise our own child process.
//!
//! Status is derived from REAL health probes (`GET /api/health`), never from
//! "did the process start" — the old menu-bar status lied precisely because
//! it didn't ask the server. The UI additionally probes /api/health itself,
//! so the pill can't drift from reality.
//!
//! Hard rules carried forward (docs/product/HANDOFF.md):
//! - the child always gets `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`
//!   (the login keychain is radioactive on this machine);
//! - the launch invocation is FIXED — never assembled from user input.

use qrcode::{render::svg, EcLevel, QrCode};
use serde::Serialize;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager};

/// Pid of the spawned sidecar child (0 = none). Mirrors `Inner.child` so the
/// async-signal-safe handler below can clean up without taking a lock.
static CHILD_PID: AtomicU32 = AtomicU32::new(0);

/// Signal handler: a SIGTERM/SIGINT/SIGHUP at the shell bypasses Tauri's
/// RunEvent::Exit, which would orphan a spawned sidecar. kill() and _exit()
/// are async-signal-safe.
extern "C" fn on_terminate(_sig: libc::c_int) {
    let pid = CHILD_PID.swap(0, Ordering::SeqCst);
    if pid != 0 {
        unsafe { libc::kill(pid as libc::pid_t, libc::SIGTERM) };
    }
    unsafe { libc::_exit(0) };
}

/// Install the terminate handlers (called once from main).
pub fn install_signal_handlers() {
    unsafe {
        let handler = on_terminate as *const () as libc::sighandler_t;
        libc::signal(libc::SIGTERM, handler);
        libc::signal(libc::SIGINT, handler);
        libc::signal(libc::SIGHUP, handler);
    }
}

/// Default agent port (`clawed serve` default; launchd service uses it too).
const DEFAULT_PORT: u16 = 8000;
const REMOTE_PAIR_URL: &str = "https://clawed.macxlabs.app";
const POLL_INTERVAL: Duration = Duration::from_secs(2);
/// Consecutive failed spawn attempts before we give up and show an error.
const MAX_RESTARTS: u32 = 5;

#[derive(Clone, Serialize, Default, PartialEq)]
pub struct SidecarStatus {
    /// "checking" | "starting" | "running" | "error" | "stopped"
    pub state: String,
    /// True when a pre-existing agent (launchd service / `clawed serve` in a
    /// terminal) answered health before we spawned anything.
    pub adopted: bool,
    pub pid: Option<u32>,
    pub port: u16,
    pub detail: String,
}

#[derive(Clone, Serialize)]
pub struct PairingInfo {
    pub remote_url: String,
    pub token_ready: bool,
    pub qr_svg: Option<String>,
    pub detail: String,
}

struct Inner {
    child: Option<Child>,
    status: SidecarStatus,
    restarts: u32,
    /// Set by the `restart_sidecar` command; the supervisor loop honors it.
    restart_requested: bool,
    shutting_down: bool,
}

#[derive(Clone)]
pub struct Supervisor {
    inner: Arc<Mutex<Inner>>,
    port: u16,
}

impl Supervisor {
    pub fn new() -> Self {
        let port = std::env::var("CLAWED_PORT")
            .ok()
            .and_then(|p| p.parse().ok())
            .unwrap_or(DEFAULT_PORT);
        Supervisor {
            inner: Arc::new(Mutex::new(Inner {
                child: None,
                status: SidecarStatus {
                    state: "checking".into(),
                    adopted: false,
                    pid: None,
                    port,
                    detail: "Looking for the agent…".into(),
                },
                restarts: 0,
                restart_requested: false,
                shutting_down: false,
            })),
            port,
        }
    }

    pub fn status(&self) -> SidecarStatus {
        self.inner.lock().expect("sidecar lock").status.clone()
    }

    pub fn request_restart(&self) {
        let mut inner = self.inner.lock().expect("sidecar lock");
        inner.restart_requested = true;
        inner.restarts = 0;
    }

    /// Kill a spawned child (no-op for an adopted external agent).
    pub fn shutdown(&self) {
        let mut inner = self.inner.lock().expect("sidecar lock");
        inner.shutting_down = true;
        if let Some(mut child) = inner.child.take() {
            CHILD_PID.store(0, Ordering::SeqCst);
            let _ = child.kill();
            let _ = child.wait();
        }
        inner.status.state = "stopped".into();
        inner.status.pid = None;
    }

    /// Run the supervision loop on a background thread. Emits
    /// `sidecar-status` events to the UI on every state change.
    pub fn spawn_loop(&self, app: AppHandle) {
        let sup = self.clone();
        std::thread::spawn(move || sup.run_loop(app));
    }

    fn run_loop(&self, app: AppHandle) {
        let mut last_emitted: Option<SidecarStatus> = None;
        loop {
            {
                let inner = self.inner.lock().expect("sidecar lock");
                if inner.shutting_down {
                    return;
                }
            }

            let healthy = http_health_ok(self.port);
            let next = self.step(healthy);

            if last_emitted.as_ref() != Some(&next) {
                let _ = app.emit("sidecar-status", &next);
                last_emitted = Some(next);
            }
            std::thread::sleep(POLL_INTERVAL);
        }
    }

    /// One supervision step: reconcile health + child state, maybe spawn.
    fn step(&self, healthy: bool) -> SidecarStatus {
        let mut inner = self.inner.lock().expect("sidecar lock");

        if inner.restart_requested {
            inner.restart_requested = false;
            if let Some(mut child) = inner.child.take() {
                CHILD_PID.store(0, Ordering::SeqCst);
                let _ = child.kill();
                let _ = child.wait();
            }
            inner.status.state = "starting".into();
            inner.status.detail = "Restarting the agent…".into();
            inner.status.pid = None;
            inner.status.adopted = false;
            return inner.status.clone();
        }

        // Reap a dead child so `child.is_some()` means "actually running".
        let child_running = match inner.child.as_mut() {
            Some(child) => match child.try_wait() {
                Ok(Some(exit)) => {
                    inner.status.detail = format!("Agent exited ({exit})");
                    inner.child = None;
                    CHILD_PID.store(0, Ordering::SeqCst);
                    false
                }
                Ok(None) => true,
                Err(_) => false,
            },
            None => false,
        };

        if healthy {
            inner.restarts = 0;
            inner.status.state = "running".into();
            inner.status.adopted = !child_running;
            inner.status.pid = inner.child.as_ref().map(|c| c.id());
            inner.status.detail = if child_running {
                "Agent healthy (supervised)".into()
            } else {
                "Agent healthy (already running on this Mac)".into()
            };
            return inner.status.clone();
        }

        if child_running {
            // We spawned it; it just hasn't answered health yet.
            inner.status.state = "starting".into();
            inner.status.detail = "Agent starting…".into();
            return inner.status.clone();
        }

        // Not healthy and no child → spawn (with a restart budget).
        if inner.restarts >= MAX_RESTARTS {
            inner.status.state = "error".into();
            inner.status.adopted = false;
            inner.status.pid = None;
            inner.status.detail = format!(
                "Couldn't keep the agent running after {MAX_RESTARTS} attempts. \
                 Check `pip install clawed` / the launcher path, then Restart."
            );
            return inner.status.clone();
        }

        match resolve_launch_plan(self.port) {
            Ok(plan) => {
                inner.restarts += 1;
                match spawn_plan(&plan) {
                    Ok(child) => {
                        CHILD_PID.store(child.id(), Ordering::SeqCst);
                        inner.status.state = "starting".into();
                        inner.status.adopted = false;
                        inner.status.pid = Some(child.id());
                        inner.status.detail =
                            format!("Launched: {}", plan.display_command);
                        inner.child = Some(child);
                    }
                    Err(err) => {
                        inner.status.state = "error".into();
                        inner.status.detail = format!("Couldn't launch the agent: {err}");
                    }
                }
            }
            Err(message) => {
                inner.status.state = "error".into();
                inner.status.detail = message;
            }
        }
        inner.status.clone()
    }
}

/// True iff `GET /api/health` on loopback answers HTTP 200. Dependency-free
/// (one short-lived TCP connection; 1s connect / 2s read timeouts).
fn http_health_ok(port: u16) -> bool {
    let addr = std::net::SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_secs(1)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(1)));
    let request = format!(
        "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = String::new();
    let _ = stream.take(1024).read_to_string(&mut response);
    response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200")
}

struct LaunchPlan {
    executable: PathBuf,
    args: Vec<String>,
    cwd: Option<PathBuf>,
    display_command: String,
}

/// Resolve the one fixed way we start the agent (mirror of LaunchPlan.swift):
///   1. `$CLAWED_LAUNCHER` — explicit override (`clawed` binary or python);
///   2. the PyInstaller agent BUNDLED inside this .app (M3 — the shipped
///      app needs no system Python at all);
///   3. `clawed` on the augmented PATH (pip/pipx install);
///   4. `python3` module fallback (`clawed serve` via clawed._entry_router),
///      run from the dev repo checkout when one exists (`$CLAWED_REPO`,
///      default `~/Projects/Claw-ED`) so `import clawed` resolves in dev.
/// Arguments are constructed HERE, never from user input.
fn resolve_launch_plan(port: u16) -> Result<LaunchPlan, String> {
    if let Ok(configured) = std::env::var("CLAWED_LAUNCHER") {
        let path = expand_tilde(&configured);
        if !is_executable(&path) {
            return Err(format!(
                "CLAWED_LAUNCHER isn't executable: {}",
                path.display()
            ));
        }
        let name = path
            .file_name()
            .map(|n| n.to_string_lossy().to_lowercase())
            .unwrap_or_default();
        if name.starts_with("python") {
            return Ok(python_fallback_plan(path, port));
        }
        return Ok(clawed_plan(path, port));
    }

    if let Some(bundled) = bundled_agent_path() {
        return Ok(clawed_plan(bundled, port));
    }

    if let Some(clawed) = which("clawed") {
        return Ok(clawed_plan(clawed, port));
    }

    if let Some(python) = which("python3").or_else(|| which("python")) {
        return Ok(python_fallback_plan(python, port));
    }

    Err("Couldn't find Claw-ED. Install it with `pip install clawed`, or set \
         CLAWED_LAUNCHER to your `clawed` command or `python3`."
        .to_string())
}

/// The PyInstaller sidecar shipped inside the .app:
/// `Claw-ED.app/Contents/Resources/agent/clawed-agent/clawed-agent`
/// (bundled from `desktop/src-tauri/agent/` — see desktop/agent-bundle/).
/// Returns None in dev builds (no Resources dir) → fallbacks apply.
fn bundled_agent_path() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let contents = exe.parent()?.parent()?; // MacOS/ → Contents/
    let candidate = contents
        .join("Resources")
        .join("agent")
        .join("clawed-agent")
        .join("clawed-agent");
    is_executable(&candidate).then_some(candidate)
}

fn clawed_plan(executable: PathBuf, port: u16) -> LaunchPlan {
    let args: Vec<String> = vec![
        "serve".into(),
        "--host".into(),
        "127.0.0.1".into(),
        "--port".into(),
        port.to_string(),
        "--skip-setup".into(),
    ];
    let display_command = format!("{} {}", executable.display(), args.join(" "));
    LaunchPlan {
        executable,
        args,
        cwd: None,
        display_command,
    }
}

fn python_fallback_plan(python: PathBuf, port: u16) -> LaunchPlan {
    // The documented module fallback — same invocation the launchd service
    // uses (scripts/launchd/install.sh), proven on this machine.
    let code = format!(
        "import sys; sys.argv=['clawed','serve','--host','127.0.0.1',\
'--port','{port}','--skip-setup']; \
from clawed._entry_router import main; main()"
    );
    // Dev convenience: run from the repo checkout when present so the
    // module import resolves without `pip install clawed`. (PyInstaller
    // bundling replaces this whole path in M3.)
    let repo = std::env::var("CLAWED_REPO")
        .map(|p| expand_tilde(&p))
        .unwrap_or_else(|_| home_dir().join("Projects").join("Claw-ED"));
    let cwd = repo.join("clawed").is_dir().then_some(repo);
    let display_command = format!(
        "{} -c \"…clawed serve --host 127.0.0.1 --port {} --skip-setup…\"",
        python.display(),
        port
    );
    LaunchPlan {
        executable: python,
        args: vec!["-c".into(), code],
        cwd,
        display_command,
    }
}

fn spawn_plan(plan: &LaunchPlan) -> std::io::Result<Child> {
    let mut cmd = Command::new(&plan.executable);
    cmd.args(&plan.args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        // Same-machine requests are trusted (loopback only — the public
        // tunnel still requires the device token; see clawed/api/deps.py).
        .env("EDUAGENT_LOCAL_AUTH_BYPASS", "1")
        .env("PYTHONUNBUFFERED", "1")
        // The keychain rule: the agent must NEVER touch the login keychain.
        .env(
            "PYTHON_KEYRING_BACKEND",
            "keyring.backends.null.Keyring",
        )
        .env("PATH", augmented_path());
    match &plan.cwd {
        Some(cwd) => {
            cmd.current_dir(cwd);
        }
        None => {
            // GUI children inherit cwd=/ — give them a writable home so
            // any relative-path fallback (e.g. ./clawed_data) can't crash
            // the agent on startup.
            cmd.current_dir(home_dir());
        }
    }
    cmd.spawn()
}

/// GUI apps get a minimal PATH; add the usual install locations
/// (mirror of AppEnvironment.baseEnvironment in the Swift app).
fn augmented_path() -> String {
    let existing = std::env::var("PATH").unwrap_or_default();
    let mut parts: Vec<String> = existing
        .split(':')
        .filter(|p| !p.is_empty())
        .map(String::from)
        .collect();
    for extra in [
        "/opt/homebrew/bin".to_string(),
        "/usr/local/bin".to_string(),
        "/usr/bin".to_string(),
        "/bin".to_string(),
        home_dir().join(".local/bin").display().to_string(),
    ] {
        if !parts.contains(&extra) {
            parts.push(extra);
        }
    }
    parts.join(":")
}

fn which(command: &str) -> Option<PathBuf> {
    augmented_path()
        .split(':')
        .map(|dir| PathBuf::from(dir).join(command))
        .find(|candidate| is_executable(candidate))
}

fn is_executable(path: &PathBuf) -> bool {
    use std::os::unix::fs::PermissionsExt;
    std::fs::metadata(path)
        .map(|m| m.is_file() && m.permissions().mode() & 0o111 != 0)
        .unwrap_or(false)
}

fn home_dir() -> PathBuf {
    PathBuf::from(std::env::var("HOME").unwrap_or_else(|_| "/tmp".into()))
}

fn expand_tilde(path: &str) -> PathBuf {
    if let Some(rest) = path.strip_prefix("~/") {
        home_dir().join(rest)
    } else {
        PathBuf::from(path)
    }
}

fn read_pairing_token() -> Option<String> {
    let token_path = home_dir().join(".eduagent").join("api_token");
    std::fs::read_to_string(token_path)
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

fn yes_no(value: bool) -> &'static str {
    if value {
        "yes"
    } else {
        "no"
    }
}

fn one_line(value: &str) -> String {
    let cleaned = value.replace('\n', " ").replace('\r', " ");
    let trimmed = cleaned.trim();
    if trimmed.is_empty() {
        "unknown".into()
    } else {
        trimmed.into()
    }
}

fn unix_timestamp() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

// ── Tauri commands ───────────────────────────────────────────────────

#[tauri::command]
pub fn sidecar_state(app: AppHandle) -> SidecarStatus {
    app.state::<Supervisor>().status()
}

#[tauri::command]
pub fn restart_sidecar(app: AppHandle) {
    app.state::<Supervisor>().request_restart();
}

#[tauri::command]
pub fn agent_base_url(app: AppHandle) -> String {
    format!("http://127.0.0.1:{}", app.state::<Supervisor>().port)
}

/// Pairing payload for the iPhone remote. The raw token is never returned to
/// the UI as text; it is encoded inside the QR SVG, matching the legacy
/// menu-bar pairing flow.
#[tauri::command]
pub fn pairing_info() -> PairingInfo {
    let remote_url = REMOTE_PAIR_URL.to_string();
    let token = read_pairing_token();

    let Some(token) = token else {
        return PairingInfo {
            remote_url,
            token_ready: false,
            qr_svg: None,
            detail: "Pairing token is not ready yet. Start or restart the agent, then refresh."
                .into(),
        };
    };

    let deep_link = format!(
        "clawed://connect?url={}&token={}",
        percent_encode(REMOTE_PAIR_URL),
        percent_encode(&token),
    );
    match render_qr_svg(&deep_link) {
        Ok(qr_svg) => PairingInfo {
            remote_url,
            token_ready: true,
            qr_svg: Some(qr_svg),
            detail: "Ready to pair.".into(),
        },
        Err(err) => PairingInfo {
            remote_url,
            token_ready: true,
            qr_svg: None,
            detail: format!("Could not render the pairing QR: {err}"),
        },
    }
}

/// Export a shareable district/admin readiness report. The UI passes live
/// health/tool facts from the loopback agent; this command adds shell-side
/// supervision, filesystem, and pairing facts without exposing secrets.
#[tauri::command]
pub fn export_readiness_report(
    app: AppHandle,
    provider: String,
    model: String,
    llm_connected: bool,
    tool_count: u32,
    run_command_risk: String,
) -> Result<String, String> {
    let status = app.state::<Supervisor>().status();
    let data_root = home_dir().join(".eduagent");
    let workspace = data_root.join("workspace");
    std::fs::create_dir_all(&workspace).map_err(|e| e.to_string())?;

    let report_path = workspace.join("clawed-readiness-report.md");
    let exe_path = std::env::current_exe()
        .map(|p| p.display().to_string())
        .unwrap_or_else(|_| "unknown".into());
    let provider = one_line(&provider);
    let model = one_line(&model);
    let run_command_risk = one_line(&run_command_risk);
    let token_ready = read_pairing_token().is_some();
    let supervision = if status.adopted {
        "adopted an already-running local agent".to_string()
    } else if let Some(pid) = status.pid {
        format!("supervised by this app, pid {pid}")
    } else {
        "supervised by this app".to_string()
    };

    let report = format!(
        r#"# Claw-ED District Readiness Report

Generated: {timestamp} Unix seconds
App version: {version}

## Runtime

- Agent URL: http://127.0.0.1:{port}
- Agent state: {state}
- Sidecar detail: {detail}
- Supervision: {supervision}
- LLM provider: {provider}
- LLM model: {model}
- LLM connected: {llm_connected}
- Tool registry count: {tool_count}
- `run_command` risk classification: {run_command_risk}

## Teacher And Student Data Boundary

- The Mac app talks to the agent over loopback only.
- Teacher files and generated work live on this Mac under `{workspace}` unless the teacher chooses another path.
- Style learning reads local materials first; only short excerpts are sent to the configured AI provider during analysis.
- The app never includes API keys, account tokens, or the iPhone pairing token in this report.

## Control And Approval Model

- Risky shell commands and file writes require teacher approval.
- "Always allow" is scoped to the exact command or file action, so changed parameters ask again.
- The agent process is launched with `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring` so it does not touch the login keychain.

## Remote Pairing

- Remote address: {remote_url}
- Pairing token present: {token_ready}
- The token is hidden inside the QR code and intentionally omitted here.

## Deployment Notes

- App executable: `{exe_path}`
- Data root: `{data_root}`
- Workspace: `{workspace}`
- Broad district distribution should use a Developer ID signed and notarized DMG before installation outside this developer Mac.
- For district fleets, deploy Mac minis through Apple School Manager or Apple Business Manager and enforce updates, permissions, and network policy through MDM.

## Readiness Verdict

This Mac is ready for a controlled teacher pilot when agent state is `running`, the LLM provider is connected, the tool count is nonzero, and risky tools still show approval-gated risk classifications.
"#,
        timestamp = unix_timestamp(),
        version = env!("CARGO_PKG_VERSION"),
        port = status.port,
        state = one_line(&status.state),
        detail = one_line(&status.detail),
        supervision = supervision,
        provider = provider,
        model = model,
        llm_connected = yes_no(llm_connected),
        tool_count = tool_count,
        run_command_risk = run_command_risk,
        workspace = workspace.display(),
        remote_url = REMOTE_PAIR_URL,
        token_ready = yes_no(token_ready),
        exe_path = exe_path,
        data_root = data_root.display(),
    );

    std::fs::write(&report_path, report).map_err(|e| e.to_string())?;
    Ok(report_path.display().to_string())
}

/// Open a file/folder the agent produced, in the default app (Finder etc.).
/// Refuses anything that isn't an existing path — no URL handling here.
#[tauri::command]
pub fn open_path(path: String) -> Result<(), String> {
    let p = expand_tilde(&path);
    if !p.exists() {
        return Err(format!("No such file: {}", p.display()));
    }
    std::process::Command::new("/usr/bin/open")
        .arg(&p)
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}

/// Native folder picker for "Your Materials" — runs AppleScript's
/// `choose folder` so we need no extra plugin crate. Returns the POSIX
/// path, or an empty string when the teacher cancels.
#[tauri::command]
pub async fn pick_folder() -> Result<String, String> {
    let output = std::process::Command::new("/usr/bin/osascript")
        .args([
            "-e",
            "POSIX path of (choose folder with prompt \"Choose the folder with your teaching materials\")",
        ])
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        // User cancelled (osascript exits non-zero) — not an error.
        return Ok(String::new());
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

/// Reveal a file in Finder (select it) — the artifact card's second action.
/// Same constraints as `open_path`: existing local paths only, no URLs.
#[tauri::command]
pub fn reveal_path(path: String) -> Result<(), String> {
    let p = expand_tilde(&path);
    if !p.exists() {
        return Err(format!("No such file: {}", p.display()));
    }
    std::process::Command::new("/usr/bin/open")
        .arg("-R")
        .arg(&p)
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}

fn render_qr_svg(payload: &str) -> Result<String, String> {
    let code = QrCode::with_error_correction_level(payload.as_bytes(), EcLevel::M)
        .map_err(|e| e.to_string())?;
    Ok(code
        .render::<svg::Color>()
        .min_dimensions(196, 196)
        .dark_color(svg::Color("#2A2722"))
        .light_color(svg::Color("#FFFFFF"))
        .build())
}

fn percent_encode(input: &str) -> String {
    let mut out = String::new();
    for byte in input.bytes() {
        let ch = byte as char;
        if ch.is_ascii_alphanumeric() {
            out.push(ch);
        } else {
            out.push_str(&format!("%{byte:02X}"));
        }
    }
    out
}
