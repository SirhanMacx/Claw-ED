// Claw-ED for Mac — Tauri 2 shell.
// Opens the agent chat window and supervises the local clawed sidecar.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod sidecar;

use sidecar::Supervisor;
use tauri::Manager;

fn main() {
    // A spawned sidecar must never outlive the app, even on SIGTERM.
    sidecar::install_signal_handlers();

    let supervisor = Supervisor::new();

    tauri::Builder::default()
        .manage(supervisor.clone())
        .invoke_handler(tauri::generate_handler![
            sidecar::sidecar_state,
            sidecar::restart_sidecar,
            sidecar::agent_base_url,
            sidecar::open_path,
        ])
        .setup(move |app| {
            supervisor.spawn_loop(app.handle().clone());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Claw-ED")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                // Kill a spawned sidecar child; adopted external agents
                // (the launchd service) are left alone.
                app.state::<Supervisor>().shutdown();
            }
        });
}
