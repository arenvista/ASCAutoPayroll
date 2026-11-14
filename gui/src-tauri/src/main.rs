// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;

use tauri::{Manager, RunEvent};

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(backend::Backend::default())
        .invoke_handler(tauri::generate_handler![
            backend::backend_start,
            backend::backend_send,
            backend::backend_restart,
        ])
        .build(tauri::generate_context!())
        .expect("error while building the application")
        .run(|app, event| {
            // Let the bridge close Firefox before we go.
            if let RunEvent::Exit = event {
                app.state::<backend::Backend>().stop();
            }
        });
}
