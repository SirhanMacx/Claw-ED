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

use serde::Serialize;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
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
        libc::signal(libc::SIGTERM, on_terminate as libc::sighandler_t);
        libc::signal(libc::SIGINT, on_terminate as libc::sighandler_t);
        libc::signal(libc::SIGHUP, on_terminate as libc::sighandler_t);
    }
}

/// Default agent port (`clawed serve` default; launchd service uses it too).
const DEFAULT_PORT: u16 = 8000;
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
///   1. `$CLAWED_LAUNCHER` — explicit `clawed` binary or python interpreter;
///   2. `clawed` on the augmented PATH (pip/pipx install);
///   3. `python3` module fallback (`clawed serve` via clawed._entry_router),
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
    if let Some(cwd) = &plan.cwd {
        cmd.current_dir(cwd);
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
