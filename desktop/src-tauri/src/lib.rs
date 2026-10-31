//! Medot desktop shell.
//!
//! Responsibilities (Milestone 1):
//!   * supervise the local Python runtime as a long-lived sidecar (AC5);
//!   * forward OAuth deep links (`medot://auth/callback?code=…`) to the
//!     console, which completes sign-in against the runtime (AC1);
//!   * keep Medot alive when the window closes (hide; Quit ends the process
//!     and, with it, the sidecar);
//!   * single-instance: a second launch forwards its deep-link argv to the
//!     running app instead of spawning a duplicate.

use tauri::{AppHandle, Emitter, Manager, WindowEvent};
use tauri_plugin_deep_link::DeepLinkExt;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

const RUNTIME_READY_EVENT: &str = "runtime-ready";
const DEEP_LINK_EVENT: &str = "deep-link";

#[tauri::command]
fn runtime_status(state: tauri::State<RuntimeState>) -> String {
    state
        .0
        .lock()
        .unwrap()
        .clone()
        .unwrap_or_else(|| "starting".into())
}

#[derive(Default)]
struct RuntimeState(std::sync::Mutex<Option<String>>);

fn spawn_runtime(app: &AppHandle) {
    let shell = app.shell();
    let spawned = if std::env::var("MEDOT_DEV_RUNTIME").is_ok() {
        // Development: run the Python runtime from the repo via uv.
        let runtime_dir = std::env::var("MEDOT_DEV_RUNTIME_DIR")
            .unwrap_or_else(|_| "../runtime".to_string());
        shell
            .command("uv")
            .args(["--directory", &runtime_dir, "run", "python", "-m", "medot"])
            .spawn()
    } else {
        // Production: the bundled PyInstaller sidecar.
        match shell.sidecar("medot-runtime") {
            Ok(sidecar) => sidecar.spawn(),
            Err(err) => Err(err),
        }
    };

    match spawned {
        Ok((mut rx, _child)) => {
            let handle = app.clone();
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    if let CommandEvent::Stdout(line) = event {
                        if let Ok(text) = String::from_utf8(line) {
                            if let Ok(payload) =
                                serde_json::from_str::<serde_json::Value>(text.trim())
                            {
                                if payload["event"] == "runtime_ready" {
                                    let state = handle.state::<RuntimeState>();
                                    *state.0.lock().unwrap() = Some("ready".into());
                                    let _ = handle.emit(RUNTIME_READY_EVENT, payload);
                                }
                            }
                        }
                    }
                }
                let state = handle.state::<RuntimeState>();
                *state.0.lock().unwrap() = Some("stopped".into());
            });
        }
        Err(err) => eprintln!("failed to spawn runtime: {err}"),
    }
}

fn forward_deep_link(app: &AppHandle, url: &str) {
    let _ = app.emit(DEEP_LINK_EVENT, serde_json::json!({ "url": url }));
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
            // Windows delivers deep links to a second process as argv.
            if let Some(url) = argv.iter().find(|a| a.starts_with("medot://")) {
                forward_deep_link(app, url);
            }
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_deep_link::init())
        .manage(RuntimeState::default())
        .invoke_handler(tauri::generate_handler![runtime_status])
        .on_window_event(|window, event| {
            // Closing the window hides Medot; the runtime keeps running
            // (scheduled messages, WhatsApp connection). Quit ends the process.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .setup(|app| {
            spawn_runtime(app.handle());

            // Deep links received by the *running* instance (warm start).
            let handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                for url in event.urls() {
                    forward_deep_link(&handle, url.as_str());
                }
            });

            // Cold start: the process itself was launched with the deep link.
            if let Some(url) = std::env::args().find(|a| a.starts_with("medot://")) {
                forward_deep_link(app.handle(), &url);
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Medot");
}
