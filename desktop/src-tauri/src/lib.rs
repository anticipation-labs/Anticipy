// Anticipy Mac app (Phase V4-9). The Rust backend spawns the Python
// DSv4 action-engine runner with --stream and forwards each JSON
// stdout line to the frontend as an "agent-event". Idle -> Running
// -> Done is driven entirely by those events.

use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use tauri::{Emitter, Window};

// Canonical local paths (see CLAUDE.md). The engine runs from its
// venv; absolute paths match how the engine's LaunchAgents work.
const ENGINE_DIR: &str = "/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine";
const VENV_PY: &str =
    "/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine/.venv/bin/python";

#[tauri::command]
fn run_task(window: Window, task: String) {
    // Run the agent off-thread so the UI stays responsive; each
    // stdout line is a JSON event emitted to the frontend.
    std::thread::spawn(move || {
        let mut child = match Command::new(VENV_PY)
            .args([
                "-m",
                "app.action_engine.dsv4_skill_runner",
                "--task",
                &task,
                "--stream",
            ])
            .current_dir(ENGINE_DIR)
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
        {
            Ok(c) => c,
            Err(e) => {
                let _ = window.emit(
                    "agent-event",
                    serde_json::json!({"kind":"done","status":"ERROR",
                        "error": format!("spawn failed: {e}")}),
                );
                return;
            }
        };

        if let Some(out) = child.stdout.take() {
            let reader = BufReader::new(out);
            for line in reader.lines().map_while(Result::ok) {
                let line = line.trim();
                if line.is_empty() {
                    continue;
                }
                match serde_json::from_str::<serde_json::Value>(line) {
                    Ok(ev) => {
                        let _ = window.emit("agent-event", ev);
                    }
                    Err(_) => {
                        // Non-JSON noise: forward as a log line.
                        let _ = window.emit(
                            "agent-event",
                            serde_json::json!({"kind":"log","line":line}),
                        );
                    }
                }
            }
        }
        let _ = child.wait();
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![run_task])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
