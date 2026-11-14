//! Owns the Python bridge process (`autopayroll.bridge`) and relays its traffic.
//!
//! The bridge speaks one JSON object per line on stdin/stdout. Each stdout line
//! is forwarded to the webview as a `backend://message` event, and the webview
//! writes requests through `backend_send`. Request/response matching lives in
//! the frontend; nothing here inspects or logs outgoing lines, since they can
//! carry the user's password.

use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde_json::Value;
use tauri::{AppHandle, Emitter, Manager, State};

/// File name of the bundled PyInstaller build (see `tauri.bundle.conf.json`).
const SIDECAR: &str = "autopayroll-backend";

/// How long the bridge gets to close Firefox and exit before it is killed.
const SHUTDOWN_GRACE: Duration = Duration::from_secs(8);

#[derive(Default)]
pub struct Backend {
    process: Mutex<Option<Process>>,
    generation: AtomicU64,
}

struct Process {
    generation: u64,
    child: Child,
    stdin: ChildStdin,
}

impl Backend {
    /// Spawn the bridge unless it is already running.
    fn start(&self, app: &AppHandle) -> Result<(), String> {
        let mut slot = self.process.lock().unwrap();
        if let Some(process) = slot.as_mut() {
            if matches!(process.child.try_wait(), Ok(None)) {
                return Ok(());
            }
        }

        let mut command = bridge_command()?;
        command
            .env("PYTHONUTF8", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            command.creation_flags(CREATE_NO_WINDOW);
        }
        let mut child = command
            .spawn()
            .map_err(|e| format!("Could not start the payroll backend: {e}"))?;
        let stdin = child.stdin.take().expect("stdin is piped");
        let stdout = child.stdout.take().expect("stdout is piped");
        let stderr = child.stderr.take().expect("stderr is piped");
        let generation = self.generation.fetch_add(1, Ordering::SeqCst) + 1;

        let handle = app.clone();
        thread::spawn(move || {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                if line.trim().is_empty() {
                    continue;
                }
                match serde_json::from_str::<Value>(&line) {
                    Ok(message) => {
                        let _ = handle.emit("backend://message", message);
                    }
                    Err(_) => {
                        let _ = handle.emit("backend://stderr", line);
                    }
                }
            }
            // stdout closed: the bridge is exiting. Report it unless we were
            // the ones who stopped it.
            if let Some(code) = handle.state::<Backend>().reap(generation) {
                let _ = handle.emit("backend://exit", code);
            }
        });

        let handle = app.clone();
        thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                eprintln!("[backend] {line}");
                let _ = handle.emit("backend://stderr", line);
            }
        });

        *slot = Some(Process {
            generation,
            child,
            stdin,
        });
        Ok(())
    }

    fn send(&self, message: &Value) -> Result<(), String> {
        let mut slot = self.process.lock().unwrap();
        let process = slot.as_mut().ok_or("The payroll backend is not running.")?;
        let mut line = message.to_string();
        line.push('\n');
        process
            .stdin
            .write_all(line.as_bytes())
            .and_then(|()| process.stdin.flush())
            .map_err(|e| format!("Lost contact with the payroll backend: {e}"))
    }

    /// Ask the bridge to exit (it quits Firefox first), killing it if it hangs.
    pub fn stop(&self) {
        let Some(process) = self.process.lock().unwrap().take() else {
            return;
        };
        let Process {
            mut child,
            mut stdin,
            ..
        } = process;
        let _ = stdin.write_all(b"{\"method\":\"shutdown\"}\n");
        let _ = stdin.flush();
        drop(stdin);
        wait_or_kill(&mut child, SHUTDOWN_GRACE);
    }

    /// Collect an exited process. Returns `None` if it was already replaced or
    /// stopped on purpose, otherwise its exit code.
    fn reap(&self, generation: u64) -> Option<Option<i32>> {
        let process = {
            let mut slot = self.process.lock().unwrap();
            match slot.as_ref() {
                Some(process) if process.generation == generation => slot.take(),
                _ => None,
            }
        }?;
        let Process { mut child, .. } = process;
        Some(wait_or_kill(&mut child, SHUTDOWN_GRACE))
    }
}

fn wait_or_kill(child: &mut Child, grace: Duration) -> Option<i32> {
    let deadline = Instant::now() + grace;
    loop {
        match child.try_wait() {
            Ok(Some(status)) => return status.code(),
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(50)),
            _ => break,
        }
    }
    let _ = child.kill();
    child.wait().ok().and_then(|status| status.code())
}

/// The command that runs the bridge.
///
/// Release builds run the bundled sidecar next to the executable. Debug builds
/// run the repository's own Python environment, so Python edits take effect on
/// the next restart without rebuilding anything.
fn bridge_command() -> Result<Command, String> {
    let mut command = if cfg!(debug_assertions) {
        dev_command()
    } else {
        let exe = std::env::current_exe().map_err(|e| e.to_string())?;
        let sidecar = exe
            .parent()
            .ok_or("Could not locate the application directory.")?
            .join(format!("{SIDECAR}{}", std::env::consts::EXE_SUFFIX));
        if !sidecar.exists() {
            return Err(format!(
                "The payroll backend is missing from this build ({}).",
                sidecar.display()
            ));
        }
        Command::new(sidecar)
    };
    if std::env::var_os("AUTOPAYROLL_VERBOSE").is_some() {
        command.arg("--verbose");
    }
    Ok(command)
}

fn dev_command() -> Command {
    // gui/src-tauri -> repository root
    let root: PathBuf = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let venv_python = if cfg!(windows) {
        root.join(".venv/Scripts/python.exe")
    } else {
        root.join(".venv/bin/python")
    };
    // Prefer the venv's interpreter: killing a `uv run` wrapper can orphan the
    // Python process under it.
    let mut command = if venv_python.exists() {
        Command::new(venv_python)
    } else {
        let mut uv = Command::new("uv");
        uv.args(["run", "python"]);
        uv
    };
    command.args(["-m", "autopayroll.bridge"]).current_dir(root);
    command
}

#[tauri::command]
pub async fn backend_start(app: AppHandle, backend: State<'_, Backend>) -> Result<(), String> {
    backend.start(&app)
}

#[tauri::command]
pub async fn backend_send(backend: State<'_, Backend>, message: Value) -> Result<(), String> {
    backend.send(&message)
}

#[tauri::command]
pub async fn backend_restart(app: AppHandle, backend: State<'_, Backend>) -> Result<(), String> {
    backend.stop();
    backend.start(&app)
}
