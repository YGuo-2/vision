use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::ffi::c_void;
use std::ffi::OsString;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{mpsc, Arc, Mutex};
use std::time::Duration;
use tauri::{ipc::Response, AppHandle, Emitter, State};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(not(debug_assertions))]
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

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LatestFrameRequest {
    pub session_id: String,
    pub frame_port: u16,
    pub frame_token: String,
}

#[tauri::command]
fn bridge_protocol_manifest() -> serde_json::Value {
    serde_json::json!({
        "version": "1.0",
        "commands": {
            "bridge.ping": { "description": "Return bridge liveness and protocol version.", "long_running": false },
            "camera.list": { "description": "Enumerate Windows camera devices.", "long_running": false },
            "model.status": { "description": "Return MediaPipe model install status.", "long_running": false },
            "model.download": { "description": "Download one model or all missing models.", "long_running": true, "stoppable": true },
            "session.start": { "description": "Start realtime camera or offline video preview.", "long_running": true, "stoppable": true },
            "session.stop": { "description": "Stop a running preview session.", "long_running": false },
            "record.toggle": { "description": "Toggle idle, recording, and paused state.", "long_running": false },
            "record.stop": { "description": "Finalize the current recording segment.", "long_running": false },
            "template.create": { "description": "Create a pose template from a reference video.", "long_running": true, "stoppable": true },
            "analysis.run": { "description": "Run template comparison and/or tech evaluation.", "long_running": true, "stoppable": true },
            "job.stop": { "description": "Stop any long-running bridge job.", "long_running": false }
        },
        "messageContract": {
            "request": ["type", "command", "requestId", "jobId", "sessionId", "payload"],
            "response": ["type", "requestId", "ok", "jobId", "sessionId", "payload", "error", "timestamp"],
            "event": ["type", "event", "jobId", "sessionId", "payload", "error", "timestamp"],
            "optional": {
                "request": ["jobId", "sessionId"],
                "response": ["jobId", "sessionId"],
                "event": ["jobId", "sessionId"]
            },
            "nullable": {
                "request": ["jobId", "sessionId"],
                "response": ["jobId", "sessionId", "error"],
                "event": ["jobId", "sessionId", "error"]
            }
        }
    })
}

#[tauri::command]
fn select_directory() -> Option<String> {
    pick_windows_directory()
}

#[cfg(windows)]
fn pick_windows_directory() -> Option<String> {
    const BIF_RETURNONLYFSDIRS: u32 = 0x0000_0001;
    const BIF_NEWDIALOGSTYLE: u32 = 0x0000_0040;

    #[repr(C)]
    struct BrowseInfoW {
        hwnd_owner: *mut c_void,
        pidl_root: *mut c_void,
        psz_display_name: *mut u16,
        lpsz_title: *const u16,
        ul_flags: u32,
        lpfn: *mut c_void,
        l_param: isize,
        i_image: i32,
    }

    #[link(name = "shell32")]
    extern "system" {
        fn SHBrowseForFolderW(lpbi: *mut BrowseInfoW) -> *mut c_void;
        fn SHGetPathFromIDListW(pidl: *mut c_void, psz_path: *mut u16) -> i32;
    }

    #[link(name = "ole32")]
    extern "system" {
        fn OleInitialize(pv_reserved: *mut c_void) -> i32;
        fn OleUninitialize();
        fn CoTaskMemFree(pv: *mut c_void);
    }

    const S_OK: i32 = 0;
    const S_FALSE: i32 = 1;
    const RPC_E_CHANGED_MODE: i32 = 0x8001_0106u32 as i32;

    let ole_result = unsafe { OleInitialize(std::ptr::null_mut()) };
    let should_uninitialize = ole_result == S_OK || ole_result == S_FALSE;
    if !should_uninitialize && ole_result != RPC_E_CHANGED_MODE {
        return None;
    }

    let title: Vec<u16> = "选择录制目录\0".encode_utf16().collect();
    let mut display_name = [0u16; 260];
    let flags = if should_uninitialize {
        BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE
    } else {
        BIF_RETURNONLYFSDIRS
    };
    let mut browse_info = BrowseInfoW {
        hwnd_owner: std::ptr::null_mut(),
        pidl_root: std::ptr::null_mut(),
        psz_display_name: display_name.as_mut_ptr(),
        lpsz_title: title.as_ptr(),
        ul_flags: flags,
        lpfn: std::ptr::null_mut(),
        l_param: 0,
        i_image: 0,
    };

    let pidl = unsafe { SHBrowseForFolderW(&mut browse_info) };
    if pidl.is_null() {
        if should_uninitialize {
            unsafe { OleUninitialize() };
        }
        return None;
    }

    let mut path = [0u16; 260];
    let ok = unsafe { SHGetPathFromIDListW(pidl, path.as_mut_ptr()) != 0 };
    unsafe { CoTaskMemFree(pidl) };
    if should_uninitialize {
        unsafe { OleUninitialize() };
    }
    if !ok {
        return None;
    }

    let len = path
        .iter()
        .position(|item| *item == 0)
        .unwrap_or(path.len());
    if len == 0 {
        None
    } else {
        Some(String::from_utf16_lossy(&path[..len]))
    }
}

#[cfg(not(windows))]
fn pick_windows_directory() -> Option<String> {
    None
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

#[tauri::command]
fn latest_frame(request: LatestFrameRequest) -> Result<Response, String> {
    let mut stream = TcpStream::connect(("127.0.0.1", request.frame_port))
        .map_err(|err| format!("failed to connect latest-frame channel: {err}"))?;
    stream
        .set_read_timeout(Some(Duration::from_secs(2)))
        .map_err(|err| format!("failed to set latest-frame read timeout: {err}"))?;
    stream
        .set_write_timeout(Some(Duration::from_secs(2)))
        .map_err(|err| format!("failed to set latest-frame write timeout: {err}"))?;
    let line = format!("GET {} {}\n", request.session_id, request.frame_token);
    stream
        .write_all(line.as_bytes())
        .map_err(|err| format!("failed to request latest frame: {err}"))?;
    let mut len_buf = [0u8; 4];
    stream
        .read_exact(&mut len_buf)
        .map_err(|err| format!("failed to read latest-frame length: {err}"))?;
    let len = u32::from_be_bytes(len_buf) as usize;
    if len == 0 {
        return Err("latest-frame channel returned no bytes".to_string());
    }
    let mut bytes = vec![0u8; len];
    stream
        .read_exact(&mut bytes)
        .map_err(|err| format!("failed to read latest-frame bytes: {err}"))?;
    Ok(Response::new(bytes))
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
        .env("PYTHONPATH", python_path_env(&repo_root))
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
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
                            "jobId": null,
                            "sessionId": null,
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
    #[cfg(debug_assertions)]
    {
        let _ = app;
        return None;
    }

    #[cfg(not(debug_assertions))]
    {
        let resource_dir = app.path().resource_dir().ok()?;
        let candidate = resource_dir.join(BRIDGE_SIDECAR_NAME);
        if candidate.exists() {
            Some(candidate)
        } else {
            None
        }
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

fn python_path_env(repo_root: &Path) -> OsString {
    let mut paths = vec![repo_root.to_path_buf()];
    if let Some(existing) = env::var_os("PYTHONPATH") {
        paths.extend(env::split_paths(&existing));
    }
    env::join_paths(paths).unwrap_or_else(|_| repo_root.as_os_str().to_os_string())
}

pub fn run() {
    tauri::Builder::default()
        .manage(BridgeState::default())
        .invoke_handler(tauri::generate_handler![
            bridge_protocol_manifest,
            bridge_command,
            latest_frame,
            select_directory
        ])
        .run(tauri::generate_context!())
        .expect("error while running Vision Tauri application");
}
