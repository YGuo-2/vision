use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::ffi::OsString;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{mpsc, Arc, Mutex};
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, State};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

const BRIDGE_SIDECAR_NAME: &str = "vision-ui-backend.exe";

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BridgeError {
    pub code: String,
    pub message: String,
    pub detail: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BridgeEnvelope {
    pub r#type: String,
    pub request_id: Option<String>,
    pub event: Option<String>,
    pub ok: Option<bool>,
    pub job_id: Option<String>,
    pub session_id: Option<String>,
    pub payload: serde_json::Value,
    pub error: Option<BridgeError>,
    pub timestamp: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BridgeCommandRequest {
    pub r#type: String,
    pub command: String,
    pub request_id: String,
    pub job_id: Option<String>,
    pub session_id: Option<String>,
    pub payload: serde_json::Value,
}

struct BridgeProcess {
    child: Child,
    stdin: ChildStdin,
    pending: Arc<Mutex<HashMap<String, mpsc::Sender<BridgeEnvelope>>>>,
}

struct BridgeLaunch {
    program: PathBuf,
    args: Vec<OsString>,
    cwd: PathBuf,
}

#[derive(Default)]
struct BridgeState {
    process: Mutex<Option<BridgeProcess>>,
}

#[tauri::command]
fn bridge_protocol_manifest() -> serde_json::Value {
    serde_json::json!({
        "version": "1.0",
        "commands": [
            "bridge.ping",
            "camera.list",
            "model.status",
            "model.download",
            "session.start",
            "session.stop",
            "record.toggle",
            "record.stop",
            "template.create",
            "analysis.run",
            "job.stop"
        ],
        "messageContract": {
            "request": ["type", "command", "requestId", "payload"],
            "response": ["type", "requestId", "ok", "payload", "error", "timestamp"],
            "event": ["type", "event", "payload", "error", "timestamp"]
        }
    })
}

#[tauri::command]
fn bridge_command(
    app: AppHandle,
    state: State<'_, BridgeState>,
    request: BridgeCommandRequest,
) -> Result<BridgeEnvelope, String> {
    let request_id = request.request_id.clone();
    let line = serde_json::to_string(&request).map_err(|err| err.to_string())?;
    let (tx, rx) = mpsc::channel();

    {
        let mut guard = state
            .process
            .lock()
            .map_err(|_| "bridge process lock poisoned".to_string())?;
        if bridge_needs_start(guard.as_mut()) {
            *guard = Some(start_bridge_process(app.clone())?);
        }
        let process = guard
            .as_mut()
            .ok_or_else(|| "bridge process is unavailable".to_string())?;
        process
            .pending
            .lock()
            .map_err(|_| "bridge pending lock poisoned".to_string())?
            .insert(request_id.clone(), tx);
        if let Err(err) = writeln!(process.stdin, "{line}") {
            let _ = process
                .pending
                .lock()
                .map_err(|_| "bridge pending lock poisoned".to_string())?
                .remove(&request_id);
            return Err(format!("failed to write bridge command: {err}"));
        }
        if let Err(err) = process.stdin.flush() {
            let _ = process
                .pending
                .lock()
                .map_err(|_| "bridge pending lock poisoned".to_string())?
                .remove(&request_id);
            return Err(format!("failed to flush bridge command: {err}"));
        }
    }

    rx.recv_timeout(Duration::from_secs(30))
        .map_err(|err| format!("bridge response timeout for {request_id}: {err}"))
}

fn bridge_needs_start(process: Option<&mut BridgeProcess>) -> bool {
    match process {
        None => true,
        Some(process) => match process.child.try_wait() {
            Ok(Some(_)) => true,
            Ok(None) => false,
            Err(_) => true,
        },
    }
}

fn start_bridge_process(app: AppHandle) -> Result<BridgeProcess, String> {
    let repo_root = repo_root();
    let launch = bridge_launch(&app, &repo_root);
    let mut command = Command::new(&launch.program);
    command
        .args(&launch.args)
        .current_dir(&launch.cwd)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    command.creation_flags(0x08000000);

    let mut child = command.spawn().map_err(|err| {
        format!(
            "failed to start python bridge with {}: {err}",
            launch.program.display()
        )
    })?;

    let stdin = child
        .stdin
        .take()
        .ok_or_else(|| "failed to open bridge stdin".to_string())?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "failed to open bridge stdout".to_string())?;
    let stderr = child.stderr.take();
    let pending: Arc<Mutex<HashMap<String, mpsc::Sender<BridgeEnvelope>>>> =
        Arc::new(Mutex::new(HashMap::new()));

    let pending_reader = Arc::clone(&pending);
    let app_reader = app.clone();
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            if line.trim().is_empty() {
                continue;
            }
            match serde_json::from_str::<BridgeEnvelope>(&line) {
                Ok(envelope) => {
                    let is_response = envelope.r#type == "response";
                    if is_response {
                        if let Some(request_id) = envelope.request_id.clone() {
                            if let Ok(mut pending) = pending_reader.lock() {
                                if let Some(sender) = pending.remove(&request_id) {
                                    let _ = sender.send(envelope.clone());
                                    continue;
                                }
                            }
                        }
                    }
                    let _ = app_reader.emit("bridge-event", envelope);
                }
                Err(err) => {
                    let _ = app_reader.emit(
                        "bridge-event",
                        serde_json::json!({
                            "type": "event",
                            "event": "bridge.decode_error",
                            "payload": { "line": line, "error": err.to_string() },
                            "error": null,
                            "timestamp": ""
                        }),
                    );
                }
            }
        }
    });

    if let Some(stderr) = stderr {
        let app_stderr = app.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                let _ = app_stderr.emit("bridge-stderr", line);
            }
        });
    }

    Ok(BridgeProcess {
        child,
        stdin,
        pending,
    })
}

fn bridge_launch(app: &AppHandle, repo_root: &Path) -> BridgeLaunch {
    if let Some(sidecar) = packaged_bridge_executable(app) {
        return BridgeLaunch {
            cwd: sidecar
                .parent()
                .map(Path::to_path_buf)
                .unwrap_or_else(|| repo_root.to_path_buf()),
            program: sidecar,
            args: Vec::new(),
        };
    }

    let python = python_executable(repo_root);
    let script = repo_root.join("apps").join("ui_backend.py");
    BridgeLaunch {
        program: python,
        args: vec![OsString::from("-u"), script.into_os_string()],
        cwd: repo_root.to_path_buf(),
    }
}

fn packaged_bridge_executable(app: &AppHandle) -> Option<PathBuf> {
    let resource_dir = app.path().resource_dir().ok()?;
    let candidate = resource_dir.join(BRIDGE_SIDECAR_NAME);
    if candidate.exists() {
        Some(candidate)
    } else {
        None
    }
}

fn repo_root() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .join("..")
        .join("..")
        .canonicalize()
        .unwrap_or_else(|_| manifest_dir.join("..").join(".."))
}

fn python_executable(repo_root: &Path) -> PathBuf {
    let venv_python = repo_root.join(".venv").join("Scripts").join("python.exe");
    if venv_python.exists() {
        return venv_python;
    }
    PathBuf::from("python")
}

pub fn run() {
    tauri::Builder::default()
        .manage(BridgeState::default())
        .invoke_handler(tauri::generate_handler![
            bridge_protocol_manifest,
            bridge_command
        ])
        .run(tauri::generate_context!())
        .expect("error while running Vision Tauri application");
}
