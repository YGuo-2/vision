use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::ffi::c_void;
use std::ffi::OsString;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{mpsc, Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tauri::{ipc::Response, AppHandle, Emitter, State};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(not(debug_assertions))]
use tauri::Manager;

#[cfg(not(debug_assertions))]
const BRIDGE_SIDECAR_DIR: &str = "vision-ui-backend";
#[cfg(not(debug_assertions))]
const BRIDGE_SIDECAR_EXE: &str = "vision-ui-backend.exe";

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

#[derive(Clone)]
struct LatestFrameSlot {
    frame_id: u64,
    frame_handle: String,
    bytes: Vec<u8>,
    payload_bytes: usize,
    updated_at: Instant,
}

struct LatestFrameChannel {
    token: String,
    port: u16,
    store: Arc<Mutex<HashMap<String, LatestFrameSlot>>>,
    dropped_frames: Arc<Mutex<u64>>,
    served_frames: Arc<Mutex<u64>>,
}

impl LatestFrameChannel {
    fn payload(&self) -> serde_json::Value {
        serde_json::json!({
            "frameHost": "127.0.0.1",
            "framePort": self.port,
            "frameToken": self.token,
            "frameId": 0,
            "frameBytes": 0,
            "publishedFrames": 0,
            "droppedFrames": 0,
            "servedFrames": 0,
            "lastFrameAgeMs": null,
            "frameTransport": "tcp-length-prefixed"
        })
    }

    fn close_for_session(&self, session_id: &str) {
        if let Ok(mut store) = self.store.lock() {
            store.remove(session_id);
        }
        if let Ok(mut stream) = TcpStream::connect(("127.0.0.1", self.port)) {
            let _ = writeln!(stream, "CLOSE {} {}", session_id, self.token);
            let _ = stream.flush();
        }
    }
}

#[derive(Default)]
struct BridgeState {
    process: Mutex<Option<BridgeProcess>>,
    frame_channels: Arc<Mutex<HashMap<String, Arc<LatestFrameChannel>>>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LatestFrameRequest {
    pub session_id: String,
    pub frame_token: String,
    pub frame_id: u64,
    pub frame_handle: String,
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
    mut request: BridgeCommandRequest,
) -> Result<BridgeEnvelope, String> {
    if request.command == "session.start" {
        ensure_latest_frame_channel(&state, &mut request)?;
    }
    let request_id = request.request_id.clone();
    let line = serde_json::to_string(&request).map_err(|err| err.to_string())?;
    let (tx, rx) = mpsc::channel();

    {
        let mut guard = state
            .process
            .lock()
            .map_err(|_| "bridge process lock poisoned".to_string())?;
        if bridge_needs_start(guard.as_mut()) {
            *guard = Some(start_bridge_process(
                app.clone(),
                Arc::clone(&state.frame_channels),
            )?);
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
fn latest_frame(
    state: State<'_, BridgeState>,
    request: LatestFrameRequest,
) -> Result<Response, String> {
    let channel = {
        let channels = state
            .frame_channels
            .lock()
            .map_err(|_| "latest-frame channel lock poisoned".to_string())?;
        channels
            .get(&request.session_id)
            .cloned()
            .ok_or_else(|| "latest-frame channel not found".to_string())?
    };
    if request.frame_token != channel.token {
        return Err("latest-frame token mismatch".to_string());
    }
    let slot = {
        let store = channel
            .store
            .lock()
            .map_err(|_| "latest-frame store lock poisoned".to_string())?;
        store
            .get(&request.session_id)
            .cloned()
            .ok_or_else(|| "latest-frame store is empty".to_string())?
    };
    if request.frame_id > slot.frame_id {
        return Err(format!(
            "latest-frame request is ahead of store: requested={} stored={} bytes={} ageMs={}",
            request.frame_id,
            slot.frame_id,
            slot.payload_bytes,
            slot.updated_at.elapsed().as_millis()
        ));
    }
    if request.frame_id == slot.frame_id && slot.frame_handle != request.frame_handle {
        return Err(format!(
            "latest-frame handle mismatch: requested={} stored={} bytes={} ageMs={}",
            request.frame_handle,
            slot.frame_handle,
            slot.payload_bytes,
            slot.updated_at.elapsed().as_millis()
        ));
    }
    if let Ok(mut served) = channel.served_frames.lock() {
        *served += 1;
    }
    let mut response = Vec::with_capacity(8 + slot.bytes.len());
    response.extend_from_slice(&slot.frame_id.to_be_bytes());
    response.extend_from_slice(&slot.bytes);
    Ok(Response::new(response))
}

fn ensure_latest_frame_channel(
    state: &State<'_, BridgeState>,
    request: &mut BridgeCommandRequest,
) -> Result<(), String> {
    let session_id = match request.session_id.clone() {
        Some(value) if !value.trim().is_empty() => value,
        _ => match request.payload.get("sessionId").and_then(|value| value.as_str()) {
            Some(value) if !value.trim().is_empty() => {
                request.session_id = Some(value.to_string());
                value.to_string()
            }
            _ => return Err("session.start requires sessionId for latest-frame channel".to_string()),
        },
    };
    let previous = {
        let mut channels = state
            .frame_channels
            .lock()
            .map_err(|_| "latest-frame channel lock poisoned".to_string())?;
        channels.remove(&session_id)
    };
    if let Some(old_channel) = previous {
        old_channel.close_for_session(&session_id);
    }
    let channel = {
        let created = Arc::new(start_latest_frame_channel(session_id.clone())?);
        let mut channels = state
            .frame_channels
            .lock()
            .map_err(|_| "latest-frame channel lock poisoned".to_string())?;
        channels.insert(session_id.clone(), Arc::clone(&created));
        created
    };
    if !request.payload.is_object() {
        request.payload = serde_json::json!({});
    }
    if let Some(map) = request.payload.as_object_mut() {
        map.insert("frameChannel".to_string(), channel.payload());
    }
    Ok(())
}

fn start_latest_frame_channel(session_id: String) -> Result<LatestFrameChannel, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0))
        .map_err(|err| format!("failed to bind latest-frame listener: {err}"))?;
    let port = listener
        .local_addr()
        .map_err(|err| format!("failed to read latest-frame port: {err}"))?
        .port();
    let channel = LatestFrameChannel {
        token: random_token(),
        port,
        store: Arc::new(Mutex::new(HashMap::new())),
        dropped_frames: Arc::new(Mutex::new(0)),
        served_frames: Arc::new(Mutex::new(0)),
    };
    let token = channel.token.clone();
    let store = Arc::clone(&channel.store);
    let dropped_frames = Arc::clone(&channel.dropped_frames);
    let served_frames = Arc::clone(&channel.served_frames);
    std::thread::spawn(move || loop {
        match listener.accept() {
            Ok((stream, _addr)) => {
                let _ = stream.set_nodelay(true);
                let should_close = handle_latest_frame_connection(
                    stream,
                    &session_id,
                    &token,
                    &store,
                    &dropped_frames,
                    &served_frames,
                );
                if should_close {
                    break;
                }
            }
            Err(_) => break,
        }
    });
    Ok(channel)
}

fn handle_latest_frame_connection(
    stream: TcpStream,
    expected_session_id: &str,
    expected_token: &str,
    store: &Arc<Mutex<HashMap<String, LatestFrameSlot>>>,
    dropped_frames: &Arc<Mutex<u64>>,
    served_frames: &Arc<Mutex<u64>>,
) -> bool {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(2)));
    let writer = match stream.try_clone() {
        Ok(value) => value,
        Err(_) => return false,
    };
    let mut reader = BufReader::new(stream);
    let mut writer = writer;
    loop {
        let mut line = String::new();
        match reader.read_line(&mut line) {
            Ok(0) => return false,
            Ok(_) => {}
            Err(_) => {
                let _ = writer.write_all(b"ERR header\n");
                return false;
            }
        }
        if line.len() > 4096 {
            let _ = writer.write_all(b"ERR header_too_large\n");
            return false;
        }
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() >= 3 && parts[0] == "CLOSE" {
            if parts[1] == expected_session_id && parts[2] == expected_token {
                if let Ok(mut guard) = store.lock() {
                    guard.remove(expected_session_id);
                }
            }
            return parts[1] == expected_session_id && parts[2] == expected_token;
        }
        if parts.len() < 5 || parts[0] != "PUT" {
            let _ = writer.write_all(b"ERR bad_request\n");
            return false;
        }
        let session_id = parts[1];
        let token = parts[2];
        let frame_id = match parts[3].parse::<u64>() {
            Ok(value) => value,
            Err(_) => {
                let _ = writer.write_all(b"ERR bad_frame_id\n");
                return false;
            }
        };
        let frame_handle = parts[4].to_string();
        if session_id != expected_session_id || token != expected_token {
            let _ = writer.write_all(b"ERR unauthorized\n");
            return false;
        }
        let mut len_buf = [0u8; 4];
        if reader.read_exact(&mut len_buf).is_err() {
            let _ = writer.write_all(b"ERR length\n");
            return false;
        }
        let len = u32::from_be_bytes(len_buf) as usize;
        let mut bytes = vec![0u8; len];
        if len > 0 && reader.read_exact(&mut bytes).is_err() {
            let _ = writer.write_all(b"ERR payload\n");
            return false;
        }
        let mut dropped = 0;
        if let Ok(mut guard) = store.lock() {
            if guard.contains_key(session_id) {
                if let Ok(mut count) = dropped_frames.lock() {
                    *count += 1;
                    dropped = *count;
                }
            }
            guard.insert(
                session_id.to_string(),
                LatestFrameSlot {
                    frame_id,
                    frame_handle,
                    payload_bytes: len,
                    bytes,
                    updated_at: Instant::now(),
                },
            );
        }
        let served = served_frames.lock().map(|value| *value).unwrap_or(0);
        let ack = format!("OK droppedFrames={dropped} servedFrames={served}\n");
        let _ = writer.write_all(ack.as_bytes());
    }
}

fn random_token() -> String {
    let mut bytes = [0u8; 16];
    if fill_random_bytes(&mut bytes) {
        return bytes.iter().map(|byte| format!("{byte:02x}")).collect();
    }
    let mut seed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_nanos())
        .unwrap_or(0);
    seed ^= (std::process::id() as u128) << 64;
    let thread_id = format!("{:?}", std::thread::current().id());
    for byte in thread_id.as_bytes() {
        seed = seed.rotate_left(5) ^ (*byte as u128);
    }
    format!("{seed:032x}")
}

#[cfg(windows)]
fn fill_random_bytes(bytes: &mut [u8]) -> bool {
    #[link(name = "advapi32")]
    extern "system" {
        #[link_name = "SystemFunction036"]
        fn rtl_gen_random(random_buffer: *mut u8, random_buffer_length: u32) -> i32;
    }
    unsafe { rtl_gen_random(bytes.as_mut_ptr(), bytes.len() as u32) != 0 }
}

#[cfg(not(windows))]
fn fill_random_bytes(_bytes: &mut [u8]) -> bool {
    false
}

fn schedule_terminal_frame_channel_cleanup(
    frame_channels: &Arc<Mutex<HashMap<String, Arc<LatestFrameChannel>>>>,
    envelope: &BridgeEnvelope,
) {
    let event = match envelope.event.as_deref() {
        Some(value) => value,
        None => return,
    };
    let terminal = match event {
        "session.status" => envelope
            .payload
            .get("state")
            .and_then(|value| value.as_str())
            .is_some_and(|state| matches!(state, "completed" | "stopped")),
        "job.completed" | "job.stopped" | "job.failed" => true,
        _ => false,
    };
    if !terminal {
        return;
    }
    let Some(session_id) = envelope.session_id.clone() else {
        return;
    };
    let expected_channel = {
        let Ok(channels) = frame_channels.lock() else {
            return;
        };
        channels.get(&session_id).cloned()
    };
    let Some(expected_channel) = expected_channel else {
        return;
    };
    let channels_for_cleanup = Arc::clone(frame_channels);
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(2));
        let removed = {
            let Ok(mut channels) = channels_for_cleanup.lock() else {
                return;
            };
            match channels.get(&session_id) {
                Some(current) if Arc::ptr_eq(current, &expected_channel) => channels.remove(&session_id),
                _ => None,
            }
        };
        if let Some(channel) = removed {
            channel.close_for_session(&session_id);
        }
    });
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

fn start_bridge_process(
    app: AppHandle,
    frame_channels: Arc<Mutex<HashMap<String, Arc<LatestFrameChannel>>>>,
) -> Result<BridgeProcess, String> {
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
    let frame_channels_reader = Arc::clone(&frame_channels);
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            if line.trim().is_empty() {
                continue;
            }
            match serde_json::from_str::<BridgeEnvelope>(&line) {
                Ok(envelope) => {
                    schedule_terminal_frame_channel_cleanup(&frame_channels_reader, &envelope);
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
        let candidate = packaged_bridge_candidate(&resource_dir);
        if candidate.exists() {
            Some(candidate)
        } else {
            None
        }
    }
}

#[cfg(not(debug_assertions))]
fn packaged_bridge_candidate(resource_dir: &Path) -> PathBuf {
    resource_dir.join(BRIDGE_SIDECAR_DIR).join(BRIDGE_SIDECAR_EXE)
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
