// Anticipy Mac app. Menu bar primary surface (no dock icon).
//
// US-011: tray icon scaffold.
// US-012: 480x600 popover anchored under tray icon, three columns,
//         click-outside hides, Esc hides, Cmd+Q quits, Past column
//         pulls action_engine_tasks rows from Supabase.
// US-015: anticipy:// deep-link claims a session via /api/auth/exchange,
//         stores refresh_token in macOS Keychain via the keyring crate,
//         restores the session from Keychain on subsequent launches, and
//         shows an auth-error window then quits on exchange failure.
// Legacy US-016 Chrome bootstrap. V7 uses the user's actual Chrome profile
// through the installed extension and native bridge. The old cloned-profile
// CDP bootstrap is available only when ANTICIPY_ENABLE_LEGACY_CLONE_CDP=1.
// US-019: macOS microphone permission. NSMicrophoneUsageDescription ships
//         in Info.plist. On launch we attempt a one-shot mic-access read
//         which, on first launch, surfaces the canonical macOS Allow/Deny
//         dialog through AVCaptureDevice. We poll the status afterwards;
//         if the user denies (or has previously denied) we emit
//         `mic-permission-denied` so the popover raises a "Microphone
//         access required" card with a button that calls
//         open_mic_system_settings, which opens System Settings to
//         Privacy and Security > Microphone. As soon as the status flips
//         to Authorized we emit `mic-permission-granted` and the popover
//         dismisses the card.

use std::ffi::OsStr;
use std::fs;
use std::fs::OpenOptions;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::image::Image;
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{
    AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder, Window, WindowEvent,
};
use tauri_plugin_deep_link::DeepLinkExt;
use tauri_plugin_positioner::{Position, WindowExt as PositionerWindowExt};

const ENGINE_DIR: &str = "/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine";
const VENV_PY: &str =
    "/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine/.venv/bin/python";

const POPOVER_LABEL: &str = "popover";
const POPOVER_WIDTH: f64 = 480.0;
const POPOVER_HEIGHT: f64 = 600.0;

const AUTH_ERROR_LABEL: &str = "auth-error";
const AUTH_ERROR_WIDTH: f64 = 420.0;
const AUTH_ERROR_HEIGHT: f64 = 240.0;

const DEEP_LINK_SCHEME: &str = "anticipy";
const DEEP_LINK_HOST: &str = "session";
const DEFAULT_API_BASE: &str = "https://anticipy.ai";
const KEYCHAIN_SERVICE: &str = "ai.anticipy.app";
const ANTICIPY_DIR_NAME: &str = ".anticipy";
const USER_ID_FILE: &str = "session_user.json";

// Legacy US-016 Chrome bootstrap constants. This path is off by default in
// V7 because cloned Chrome cannot count as product proof.
const CHROME_PROFILE_DIR_NAME: &str = "chrome-real-clone";
const CHROME_REMOTE_DEBUG_PORT: u16 = 9222;
const CHROME_BINARY_PATH: &str =
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const USER_CHROME_DEFAULT_REL: &str =
    "Library/Application Support/Google/Chrome/Default";
const CHROME_CDP_TIMEOUT_SECS: u64 = 15;
const CHROME_SETUP_COPY_MESSAGE: &str =
    "Setting up Anticipy. This takes about 30 seconds and only happens once.";
const CHROME_SIGNIN_MESSAGE: &str =
    "Sign in to Gmail and Calendar in this Chrome window so Anticipy can act on your behalf.";

// US-019 microphone permission constants. The usage string is also the
// exact NSMicrophoneUsageDescription value in Info.plist.
const MIC_PERMISSION_USAGE: &str =
    "Anticipy listens for ambient conversational intent. Microphone access is required for the product to work.";
// Plain-English copy shown in the popover one beat before the macOS Allow
// or Deny dialog renders. Apple-quality polish item 8: explain the prompt
// to the user BEFORE the system dialog appears.
const MIC_PERMISSION_PRE_PROMPT_MESSAGE: &str =
    "Anticipy needs to hear what people ask you to do. macOS will ask you to allow microphone access in a moment.";
const MIC_SYSTEM_SETTINGS_URL: &str =
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone";
const MIC_GRACE_PERIOD_MS: u64 = 1_200;
const MIC_POLL_INTERVAL_MS: u64 = 1_500;
const MIC_POLL_MAX_SECS: u64 = 1_800;
const MIC_PROMPT_DELAY_MS: u64 = 1_000;
// Window in which the popover can render the pre-prompt explainer before
// the actual macOS Allow/Deny dialog fires.
const MIC_PRE_PROMPT_LEAD_MS: u64 = 1_400;
const MIC_DENIED_MESSAGE: &str = "Microphone access required";

// US-023 dossier section constants. The popover invokes these commands
// to drive the mock call layer in engine/app/dossier/call.py via the
// engine's HTTP routes. ENGINE_PORT_FILE points at the random port
// written by the PyInstaller sidecar on startup; when the file is
// missing (dev runs) we fall back to the default 8731 the engine uses
// when launched from the venv.
const ENGINE_PORT_FILE: &str = "engine.port";
const DEFAULT_ENGINE_PORT: u16 = 8731;
const DOSSIER_DEFAULT_USER_ID: &str = "anticipy-mac-user";

static ENGINE_CHILD: OnceLock<Mutex<Option<Child>>> = OnceLock::new();

// Embed Supabase coordinates at compile time when available. Falls back to
// runtime env vars; both being absent yields an empty Past column instead of
// a crash, which is the right ambient-UI behavior.
const COMPILE_SUPABASE_URL: Option<&str> = option_env!("NEXT_PUBLIC_SUPABASE_URL");
const COMPILE_SUPABASE_ANON_KEY: Option<&str> =
    option_env!("NEXT_PUBLIC_SUPABASE_ANON_KEY");

fn supabase_url() -> Option<String> {
    if let Some(v) = COMPILE_SUPABASE_URL {
        if !v.is_empty() {
            return Some(v.to_string());
        }
    }
    std::env::var("NEXT_PUBLIC_SUPABASE_URL")
        .ok()
        .or_else(|| std::env::var("SUPABASE_URL").ok())
}

fn supabase_anon_key() -> Option<String> {
    if let Some(v) = COMPILE_SUPABASE_ANON_KEY {
        if !v.is_empty() {
            return Some(v.to_string());
        }
    }
    std::env::var("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        .ok()
        .or_else(|| std::env::var("SUPABASE_ANON_KEY").ok())
}

#[derive(Serialize, Deserialize, Debug, Clone, Default)]
struct PastTask {
    #[serde(default)]
    task_id: String,
    #[serde(default)]
    goal: String,
    #[serde(default)]
    status: String,
    #[serde(default)]
    n_iterations: i64,
    #[serde(default)]
    task_name: Option<String>,
    #[serde(default)]
    created_at: String,
    #[serde(default)]
    updated_at: String,
}

#[tauri::command]
fn run_task(window: Window, task: String) {
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

#[tauri::command]
fn hide_popover(app: AppHandle) {
    if let Some(w) = app.get_webview_window(POPOVER_LABEL) {
        let _ = w.hide();
    }
}

#[tauri::command]
fn quit_app(app: AppHandle) {
    app.exit(0);
}

#[tauri::command]
fn fetch_active_task() -> Option<PastTask> {
    // Reserved for the engine sidecar (US-013). Until that ships, Now is idle.
    None
}

#[tauri::command]
fn fetch_next_tasks(_limit: Option<u32>) -> Vec<serde_json::Value> {
    // Reserved for the proactive-day cron surface. Empty list keeps the
    // popover honest until that wire is live.
    Vec::new()
}

#[tauri::command]
fn fetch_past_tasks(limit: Option<u32>) -> Vec<PastTask> {
    let n = limit.unwrap_or(5).clamp(1, 25);
    let url = match supabase_url() {
        Some(v) => v,
        None => return Vec::new(),
    };
    let key = match supabase_anon_key() {
        Some(v) => v,
        None => return Vec::new(),
    };
    let endpoint = format!(
        "{}/rest/v1/action_engine_tasks?select=task_id,goal,status,n_iterations,task_name,created_at,updated_at&order=updated_at.desc&limit={}",
        url.trim_end_matches('/'),
        n
    );
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(6))
        .build();
    let resp = agent
        .get(&endpoint)
        .set("apikey", &key)
        .set("Authorization", &format!("Bearer {}", key))
        .set("Accept", "application/json")
        .call();
    let resp = match resp {
        Ok(r) => r,
        Err(_) => return Vec::new(),
    };
    resp.into_json::<Vec<PastTask>>().unwrap_or_default()
}

// ---------------------------------------------------------------------------
// US-015: anticipy:// deep-link session claim and Keychain-backed restore.
// ---------------------------------------------------------------------------

fn api_base() -> String {
    std::env::var("ANTICIPY_API_BASE")
        .ok()
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| DEFAULT_API_BASE.to_string())
        .trim_end_matches('/')
        .to_string()
}

fn anticipy_dir() -> Option<PathBuf> {
    let home = std::env::var_os("HOME").map(PathBuf::from)?;
    Some(home.join(ANTICIPY_DIR_NAME))
}

fn engine_port_path() -> Option<PathBuf> {
    anticipy_dir().map(|d| d.join(ENGINE_PORT_FILE))
}

fn write_engine_port(port: u16) {
    if let Some(path) = engine_port_path() {
        if let Some(parent) = path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        let _ = fs::write(path, port.to_string());
    }
}

fn user_id_path() -> Option<PathBuf> {
    anticipy_dir().map(|d| d.join(USER_ID_FILE))
}

fn write_user_id(user_id: &str) -> std::io::Result<()> {
    let dir = anticipy_dir().ok_or_else(|| {
        std::io::Error::new(std::io::ErrorKind::NotFound, "HOME not set")
    })?;
    fs::create_dir_all(&dir)?;
    let path = dir.join(USER_ID_FILE);
    let body = serde_json::json!({ "user_id": user_id }).to_string();
    fs::write(path, body)?;
    Ok(())
}

fn read_user_id() -> Option<String> {
    let path = user_id_path()?;
    let raw = fs::read_to_string(&path).ok()?;
    let v: serde_json::Value = serde_json::from_str(&raw).ok()?;
    v.get("user_id")
        .and_then(|s| s.as_str())
        .map(|s| s.to_string())
}

#[cfg(target_os = "macos")]
fn keychain_store_refresh_token(user_id: &str, refresh_token: &str) -> Result<(), String> {
    let entry =
        keyring::Entry::new(KEYCHAIN_SERVICE, user_id).map_err(|e| e.to_string())?;
    entry.set_password(refresh_token).map_err(|e| e.to_string())
}

#[cfg(target_os = "macos")]
fn keychain_load_refresh_token(user_id: &str) -> Result<Option<String>, String> {
    let entry =
        keyring::Entry::new(KEYCHAIN_SERVICE, user_id).map_err(|e| e.to_string())?;
    match entry.get_password() {
        Ok(s) => Ok(Some(s)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

#[cfg(not(target_os = "macos"))]
fn keychain_store_refresh_token(_user_id: &str, _refresh_token: &str) -> Result<(), String> {
    Err("Keychain only available on macOS".to_string())
}

#[cfg(not(target_os = "macos"))]
fn keychain_load_refresh_token(_user_id: &str) -> Result<Option<String>, String> {
    Ok(None)
}

fn parse_session_token(url: &url::Url) -> Option<String> {
    if url.scheme() != DEEP_LINK_SCHEME {
        return None;
    }
    if url.host_str() != Some(DEEP_LINK_HOST) {
        return None;
    }
    for (k, v) in url.query_pairs() {
        if k == "token" {
            let t = v.trim().to_string();
            if !t.is_empty() {
                return Some(t);
            }
        }
    }
    None
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct ExchangeResponse {
    access_token: String,
    refresh_token: String,
    #[serde(default)]
    user: serde_json::Value,
}

fn exchange_handoff_token(token: &str) -> Result<ExchangeResponse, String> {
    let endpoint = format!("{}/api/auth/exchange", api_base());
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(10))
        .build();
    let resp = agent
        .post(&endpoint)
        .set("Content-Type", "application/json")
        .send_json(serde_json::json!({ "token": token }));
    let resp = match resp {
        Ok(r) => r,
        Err(ureq::Error::Status(code, r)) => {
            let body = r.into_string().unwrap_or_default();
            return Err(format!("HTTP {} from /api/auth/exchange: {}", code, body));
        }
        Err(e) => return Err(format!("/api/auth/exchange transport error: {e}")),
    };
    resp.into_json::<ExchangeResponse>()
        .map_err(|e| format!("/api/auth/exchange decode error: {e}"))
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct SupabaseTokenResponse {
    access_token: String,
    refresh_token: String,
    #[serde(default)]
    user: serde_json::Value,
}

fn supabase_refresh(refresh_token: &str) -> Result<SupabaseTokenResponse, String> {
    let url = match supabase_url() {
        Some(u) => u,
        None => return Err("NEXT_PUBLIC_SUPABASE_URL not configured".to_string()),
    };
    let key = match supabase_anon_key() {
        Some(k) => k,
        None => return Err("NEXT_PUBLIC_SUPABASE_ANON_KEY not configured".to_string()),
    };
    let endpoint = format!(
        "{}/auth/v1/token?grant_type=refresh_token",
        url.trim_end_matches('/')
    );
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(10))
        .build();
    let resp = agent
        .post(&endpoint)
        .set("Content-Type", "application/json")
        .set("apikey", &key)
        .send_json(serde_json::json!({ "refresh_token": refresh_token }));
    let resp = match resp {
        Ok(r) => r,
        Err(ureq::Error::Status(code, r)) => {
            let body = r.into_string().unwrap_or_default();
            return Err(format!("HTTP {} from supabase refresh: {}", code, body));
        }
        Err(e) => return Err(format!("supabase refresh transport error: {e}")),
    };
    resp.into_json::<SupabaseTokenResponse>()
        .map_err(|e| format!("supabase refresh decode error: {e}"))
}

fn extract_user_id(user: &serde_json::Value) -> Option<String> {
    user.get("id")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

fn ensure_auth_error_window(
    app: &AppHandle,
    message: &str,
) -> tauri::Result<tauri::WebviewWindow> {
    if let Some(w) = app.get_webview_window(AUTH_ERROR_LABEL) {
        let _ = w.show();
        let _ = w.set_focus();
        let _ = w.emit("auth-error-message", message.to_string());
        return Ok(w);
    }
    let initial = serde_json::json!({ "message": message }).to_string();
    let url = format!("auth-error.html?payload={}", urlencode(&initial));
    let window = WebviewWindowBuilder::new(app, AUTH_ERROR_LABEL, WebviewUrl::App(url.into()))
        .title("Anticipy")
        .inner_size(AUTH_ERROR_WIDTH, AUTH_ERROR_HEIGHT)
        .min_inner_size(AUTH_ERROR_WIDTH, AUTH_ERROR_HEIGHT)
        .resizable(false)
        .maximizable(false)
        .minimizable(false)
        .fullscreen(false)
        .decorations(true)
        .transparent(false)
        .background_color(tauri::webview::Color(0x0C, 0x0C, 0x0C, 0xFF))
        .always_on_top(true)
        .skip_taskbar(false)
        .focused(true)
        .visible(true)
        .center()
        .build()?;
    let _ = window.emit("auth-error-message", message.to_string());
    Ok(window)
}

fn urlencode(input: &str) -> String {
    // Tiny encoder that covers what we need (JSON payloads in a query string).
    // We avoid pulling percent_encoding just for this single call site.
    let mut out = String::with_capacity(input.len() * 3);
    for b in input.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'.' | b'_' | b'~' => {
                out.push(b as char);
            }
            _ => {
                out.push_str(&format!("%{:02X}", b));
            }
        }
    }
    out
}

fn show_auth_error_and_quit(app: &AppHandle, message: String) {
    let _ = app.emit("session-claim-failed", message.clone());
    let _ = ensure_auth_error_window(app, &message);
    let handle = app.clone();
    std::thread::spawn(move || {
        // Give the window a moment to render and the user a moment to read it.
        std::thread::sleep(Duration::from_secs(8));
        handle.exit(0);
    });
}

fn claim_session(app: &AppHandle, token: &str) {
    let _ = app.emit("session-claim-start", token.to_string());
    let resp = match exchange_handoff_token(token) {
        Ok(r) => r,
        Err(e) => {
            eprintln!("[auth] exchange failed: {e}");
            show_auth_error_and_quit(
                app,
                "Sign in failed, please reinstall.".to_string(),
            );
            return;
        }
    };
    let user_id = match extract_user_id(&resp.user) {
        Some(id) => id,
        None => {
            eprintln!("[auth] exchange response missing user.id");
            show_auth_error_and_quit(
                app,
                "Sign in failed, please reinstall.".to_string(),
            );
            return;
        }
    };
    if let Err(e) = keychain_store_refresh_token(&user_id, &resp.refresh_token) {
        eprintln!("[auth] keychain write failed: {e}");
        show_auth_error_and_quit(app, "Sign in failed, please reinstall.".to_string());
        return;
    }
    if let Err(e) = write_user_id(&user_id) {
        eprintln!("[auth] write_user_id failed: {e}");
    }
    let _ = app.emit(
        "session-claimed",
        serde_json::json!({
            "user_id": user_id,
            "access_token": resp.access_token,
        }),
    );
}

fn try_restore_session(app: &AppHandle) {
    let user_id = match read_user_id() {
        Some(id) => id,
        None => {
            let _ = app.emit("session-restore-skipped", "no stored user_id");
            return;
        }
    };
    let refresh = match keychain_load_refresh_token(&user_id) {
        Ok(Some(t)) => t,
        Ok(None) => {
            let _ = app.emit(
                "session-restore-skipped",
                "no Keychain entry for stored user_id",
            );
            return;
        }
        Err(e) => {
            eprintln!("[auth] keychain read failed: {e}");
            let _ = app.emit("session-restore-failed", e);
            return;
        }
    };
    match supabase_refresh(&refresh) {
        Ok(tok) => {
            if let Err(e) = keychain_store_refresh_token(&user_id, &tok.refresh_token) {
                eprintln!("[auth] keychain rotate failed: {e}");
            }
            let _ = app.emit(
                "session-restored",
                serde_json::json!({
                    "user_id": user_id,
                    "access_token": tok.access_token,
                }),
            );
        }
        Err(e) => {
            eprintln!("[auth] supabase refresh failed: {e}");
            let _ = app.emit("session-restore-failed", e);
        }
    }
}

fn handle_deep_link_urls(app: &AppHandle, urls: Vec<url::Url>) {
    for url in urls {
        if let Some(token) = parse_session_token(&url) {
            let h = app.clone();
            std::thread::spawn(move || {
                claim_session(&h, &token);
            });
            return;
        }
    }
}

#[tauri::command]
fn dismiss_auth_error(app: AppHandle) {
    app.exit(0);
}

// ---------------------------------------------------------------------------
// Legacy US-016: first-launch Anticipy Chrome bootstrap.
//
// This cloned-profile CDP path is retained only as an explicit legacy escape
// hatch. The default V7 surface is the user's actual Chrome profile through
// the installed extension and native-messaging bridge.
// ---------------------------------------------------------------------------

fn chrome_profile_dir() -> Option<PathBuf> {
    anticipy_dir().map(|d| d.join(CHROME_PROFILE_DIR_NAME))
}

fn user_default_chrome_dir() -> Option<PathBuf> {
    let home = std::env::var_os("HOME").map(PathBuf::from)?;
    Some(home.join(USER_CHROME_DEFAULT_REL))
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> std::io::Result<()> {
    // `cp -R` is the macOS-native way to clone a Chrome profile. It
    // preserves symlinks, file modes, and resource forks (some Chrome
    // assets carry them) that a naive walk would miss. The Anticipy
    // profile must stay byte-identical to the original or Chrome will
    // re-prompt for sign-in.
    if let Some(parent) = dst.parent() {
        fs::create_dir_all(parent)?;
    }
    let status = Command::new("cp")
        .args([OsStr::new("-R"), src.as_os_str(), dst.as_os_str()])
        .status()?;
    if !status.success() {
        return Err(std::io::Error::other(format!(
            "cp -R failed with status {status}"
        )));
    }
    Ok(())
}

fn chrome_cdp_json_version(port: u16) -> Result<String, String> {
    let endpoint = format!("http://127.0.0.1:{port}/json/version");
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(2))
        .build();
    let resp = agent
        .get(&endpoint)
        .set("Accept", "application/json")
        .call()
        .map_err(|e| e.to_string())?;
    let body = resp.into_string().map_err(|e| e.to_string())?;
    if body.trim().is_empty() {
        return Err("empty body".to_string());
    }
    serde_json::from_str::<serde_json::Value>(&body)
        .map_err(|e| format!("invalid JSON: {e}"))?;
    Ok(body)
}

fn wait_for_chrome_cdp(port: u16, timeout: Duration) -> Result<String, String> {
    let deadline = std::time::Instant::now() + timeout;
    let mut last_err = String::from("CDP did not come up");
    while std::time::Instant::now() < deadline {
        match chrome_cdp_json_version(port) {
            Ok(body) => return Ok(body),
            Err(e) => last_err = e,
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    Err(last_err)
}

fn launch_anticipy_chrome(profile_dir: &Path) -> std::io::Result<()> {
    let port_arg = format!("--remote-debugging-port={CHROME_REMOTE_DEBUG_PORT}");
    let user_data_arg = format!("--user-data-dir={}", profile_dir.display());
    Command::new(CHROME_BINARY_PATH)
        .args([
            port_arg.as_str(),
            user_data_arg.as_str(),
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .stdin(Stdio::null())
        .spawn()?;
    Ok(())
}

fn emit_string(app: &AppHandle, name: &str, message: &str) {
    let _ = app.emit(name, message.to_string());
}

fn bootstrap_anticipy_chrome(app: &AppHandle) {
    let profile = match chrome_profile_dir() {
        Some(p) => p,
        None => {
            eprintln!("[chrome] HOME not set, skipping bootstrap");
            return;
        }
    };
    let default_profile = match user_default_chrome_dir() {
        Some(p) => p,
        None => {
            eprintln!("[chrome] HOME not set, skipping bootstrap");
            return;
        }
    };

    let needs_copy = !profile.exists();
    if needs_copy {
        if default_profile.exists() {
            emit_string(app, "chrome-setup-start", CHROME_SETUP_COPY_MESSAGE);
            emit_string(app, "chrome-setup-progress", CHROME_SETUP_COPY_MESSAGE);
            if let Some(parent) = profile.parent() {
                if let Err(e) = fs::create_dir_all(parent) {
                    eprintln!("[chrome] mkdir {} failed: {e}", parent.display());
                    emit_string(app, "chrome-setup-error", &e.to_string());
                    return;
                }
            }
            if let Err(e) = fs::create_dir_all(&profile) {
                eprintln!("[chrome] mkdir {} failed: {e}", profile.display());
                emit_string(app, "chrome-setup-error", &e.to_string());
                return;
            }
            let dest_default = profile.join("Default");
            if let Err(e) = copy_dir_recursive(&default_profile, &dest_default) {
                eprintln!("[chrome] copy failed: {e}");
                emit_string(app, "chrome-setup-error", &e.to_string());
                return;
            }
        } else {
            // Corner case: user has no Chrome default profile. Create
            // an empty Anticipy profile so Chrome will launch cleanly,
            // then raise the sign-in card in the popover.
            if let Err(e) = fs::create_dir_all(&profile) {
                eprintln!("[chrome] mkdir {} failed: {e}", profile.display());
                emit_string(app, "chrome-setup-error", &e.to_string());
                return;
            }
            emit_string(app, "chrome-setup-no-default-profile", CHROME_SIGNIN_MESSAGE);
        }
    }

    if let Err(e) = launch_anticipy_chrome(&profile) {
        eprintln!("[chrome] launch failed: {e}");
        emit_string(app, "chrome-setup-error", &e.to_string());
        return;
    }

    match wait_for_chrome_cdp(
        CHROME_REMOTE_DEBUG_PORT,
        Duration::from_secs(CHROME_CDP_TIMEOUT_SECS),
    ) {
        Ok(body) => emit_string(app, "chrome-setup-ready", &body),
        Err(e) => {
            eprintln!("[chrome] CDP verify failed: {e}");
            emit_string(app, "chrome-setup-error", &e);
        }
    }
}

// ---------------------------------------------------------------------------
// US-019: macOS microphone permission flow.
//
// The Rust side drives three things: it triggers the system Allow/Deny
// prompt via tauri-plugin-macos-permissions' request command (which calls
// AVCaptureDevice's requestAccessForMediaType), it polls the current
// authorization status and emits `mic-permission-granted` /
// `mic-permission-denied` events as that status flips, and it exposes
// `open_mic_system_settings` so the popover button can route the user
// straight to Privacy and Security > Microphone in System Settings.
//
// The 1-second mic capture in the PRD description is what
// requestAccessForMediaType does internally; it is the canonical way to
// raise the macOS prompt without leaving an open audio stream lying
// around.
// ---------------------------------------------------------------------------

#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
enum MicPermissionState {
    #[default]
    Unknown,
    Granted,
    Denied,
}

impl MicPermissionState {
    fn as_str(self) -> &'static str {
        match self {
            MicPermissionState::Unknown => "unknown",
            MicPermissionState::Granted => "granted",
            MicPermissionState::Denied => "denied",
        }
    }
}

#[derive(Default)]
struct MicPermissionStore(Mutex<MicPermissionState>);

impl MicPermissionStore {
    fn set(&self, state: MicPermissionState) -> bool {
        let mut guard = self.0.lock().unwrap();
        if *guard == state {
            return false;
        }
        *guard = state;
        true
    }

    fn get(&self) -> MicPermissionState {
        *self.0.lock().unwrap()
    }
}

fn check_microphone_permission_blocking() -> bool {
    #[cfg(target_os = "macos")]
    {
        tauri::async_runtime::block_on(async {
            tauri_plugin_macos_permissions::check_microphone_permission().await
        })
    }
    #[cfg(not(target_os = "macos"))]
    {
        true
    }
}

fn request_microphone_permission_blocking() {
    #[cfg(target_os = "macos")]
    {
        let _ = tauri::async_runtime::block_on(async {
            tauri_plugin_macos_permissions::request_microphone_permission().await
        });
    }
}

fn emit_mic_state(app: &AppHandle, state: MicPermissionState) {
    let message = match state {
        MicPermissionState::Granted => "",
        MicPermissionState::Denied => MIC_DENIED_MESSAGE,
        MicPermissionState::Unknown => "",
    };
    let payload = serde_json::json!({
        "state": state.as_str(),
        "message": message,
        "usage": MIC_PERMISSION_USAGE,
    });
    let event_name = match state {
        MicPermissionState::Granted => "mic-permission-granted",
        MicPermissionState::Denied => "mic-permission-denied",
        MicPermissionState::Unknown => "mic-permission-unknown",
    };
    let _ = app.emit(event_name, payload.clone());
    let _ = app.emit("mic-permission-changed", payload);
}

fn record_and_emit(
    app: &AppHandle,
    store: &MicPermissionStore,
    new_state: MicPermissionState,
) {
    let changed = store.set(new_state);
    if changed || new_state == MicPermissionState::Denied {
        // Re-emit denied even on no-change so the popover, if it opens late,
        // still picks up the most recent state through its event listeners.
        emit_mic_state(app, new_state);
    }
}

fn bootstrap_mic_permission(app: &AppHandle) {
    let store = app.state::<MicPermissionStore>();

    // Fast path: the user already granted permission. Skip the prompt
    // entirely so we never show a card on every launch after the first.
    if check_microphone_permission_blocking() {
        record_and_emit(app, &store, MicPermissionState::Granted);
        return;
    }

    // Apple-quality polish item 8: pre-prompt explainer. Emit a clear,
    // plain-English heads-up so the popover can show a one-line banner
    // BEFORE macOS surfaces its own opaque Allow/Deny dialog. Then sleep
    // briefly so the user actually has a chance to read it.
    let _ = app.emit(
        "mic-permission-about-to-prompt",
        serde_json::json!({
            "message": MIC_PERMISSION_PRE_PROMPT_MESSAGE,
            "usage": MIC_PERMISSION_USAGE,
        }),
    );
    std::thread::sleep(Duration::from_millis(MIC_PRE_PROMPT_LEAD_MS));

    // Trigger the system Allow/Deny dialog. If status is NotDetermined
    // the user sees the prompt; if it is Denied/Restricted the request
    // is a no-op and we fall straight through to the polling loop, which
    // raises the recovery card.
    request_microphone_permission_blocking();

    // Brief grace period so a quick click on Allow does not flash the
    // recovery card before we re-check the OS state.
    std::thread::sleep(Duration::from_millis(MIC_PROMPT_DELAY_MS));

    let start = std::time::Instant::now();
    let mut announced_denied = false;
    let mut grace_consumed = false;
    while start.elapsed() < Duration::from_secs(MIC_POLL_MAX_SECS) {
        if check_microphone_permission_blocking() {
            record_and_emit(app, &store, MicPermissionState::Granted);
            return;
        }
        if !grace_consumed {
            // First non-granted observation after the initial prompt
            // delay. Give the user one more short window before showing
            // the recovery card, in case they are mid-click on Allow.
            std::thread::sleep(Duration::from_millis(MIC_GRACE_PERIOD_MS));
            grace_consumed = true;
            continue;
        }
        if !announced_denied {
            record_and_emit(app, &store, MicPermissionState::Denied);
            announced_denied = true;
        }
        std::thread::sleep(Duration::from_millis(MIC_POLL_INTERVAL_MS));
    }
}

#[tauri::command]
fn fetch_mic_permission_state(store: tauri::State<'_, MicPermissionStore>) -> String {
    store.get().as_str().to_string()
}

#[tauri::command]
fn recheck_mic_permission(
    app: AppHandle,
    store: tauri::State<'_, MicPermissionStore>,
) -> String {
    let granted = check_microphone_permission_blocking();
    let new_state = if granted {
        MicPermissionState::Granted
    } else {
        MicPermissionState::Denied
    };
    if store.set(new_state) {
        emit_mic_state(&app, new_state);
    }
    new_state.as_str().to_string()
}

#[tauri::command]
fn open_mic_system_settings() -> Result<(), String> {
    // `open` is the canonical macOS entry point for x-apple-systempreferences
    // URLs and does not require a Tauri permission allowance the way the
    // shell plugin does. Spawning is fine; we do not need to wait for the
    // System Settings window to render.
    Command::new("open")
        .arg(MIC_SYSTEM_SETTINGS_URL)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .stdin(Stdio::null())
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}

// ---------------------------------------------------------------------------
// US-023: Dossier section in the popover.
//
// The popover renders a Dossier section below Past with the last call
// time, the entry count, and a "Start a quick chat" button. Clicking
// the button invokes start_dossier_call; the Now column flips to
// "On a call with Anticipy" with a Hang Up button on the JS side. The
// Hang Up button invokes hangup_dossier_call which records a stop
// event with the engine, then the popover refreshes the Dossier
// section via fetch_dossier_summary.
//
// The engine routes are POST /api/dossier/outbound and POST
// /api/dossier/inbound (mocked in MOCK_MODE=true) plus
// GET /api/dossier/events for observability. The Mac app talks to the
// engine sidecar at 127.0.0.1:<port>, where <port> is read from the
// ~/.anticipy/engine.port file written by the PyInstaller binary, or
// the default 8731 when running against a dev engine.
// ---------------------------------------------------------------------------

#[derive(Serialize, Deserialize, Debug, Clone, Default)]
struct DossierSummary {
    /// ISO 8601 timestamp of the most recent completed call. Empty
    /// when there are no calls yet.
    #[serde(default)]
    last_call_at: String,
    /// Number of dossier writes the user has accumulated.
    #[serde(default)]
    entry_count: i64,
    /// Whether a call is currently in progress, as observed via the
    /// most recent status event.
    #[serde(default)]
    call_in_progress: bool,
    /// Whether the engine is in mock mode. The popover does not branch
    /// on this; it is included for observability and future copy.
    #[serde(default)]
    mock_mode: bool,
}

fn engine_port() -> u16 {
    if let Some(port_path) = engine_port_path() {
        if let Ok(raw) = fs::read_to_string(port_path) {
            if let Ok(p) = raw.trim().parse::<u16>() {
                if p > 0 {
                    return p;
                }
            }
        }
    }
    if let Ok(raw) = std::env::var("ANTICIPY_ENGINE_PORT") {
        if let Ok(p) = raw.trim().parse::<u16>() {
            if p > 0 {
                return p;
            }
        }
    }
    DEFAULT_ENGINE_PORT
}

fn engine_base_url() -> String {
    format!("http://127.0.0.1:{}", engine_port())
}

fn engine_health_ok(port: u16) -> bool {
    let endpoint = format!("http://127.0.0.1:{port}/health");
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(1))
        .build();
    match agent.get(&endpoint).set("Accept", "application/json").call() {
        Ok(resp) if resp.status() == 200 => resp
            .into_json::<serde_json::Value>()
            .map(|v| {
                v.get("ok").and_then(|x| x.as_bool()) == Some(true)
                    && v.get("service").and_then(|x| x.as_str())
                        == Some("anticipy-local-engine")
            })
            .unwrap_or(false),
        _ => false,
    }
}

fn engine_sidecar_path() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let dir = exe.parent()?;
    let candidates = [
        dir.join("anticipy-engine-aarch64-apple-darwin"),
        dir.join("anticipy-engine"),
    ];
    candidates.into_iter().find(|p| p.exists())
}

fn start_engine_sidecar(app: &AppHandle) {
    if engine_health_ok(DEFAULT_ENGINE_PORT) {
        write_engine_port(DEFAULT_ENGINE_PORT);
        let _ = app.emit("engine-ready", DEFAULT_ENGINE_PORT);
        return;
    }

    let sidecar = match engine_sidecar_path() {
        Some(path) => path,
        None => {
            let msg = "engine sidecar binary not found next to app binary";
            eprintln!("[engine] {msg}");
            let _ = app.emit("engine-error", msg);
            return;
        }
    };

    let dir = match anticipy_dir() {
        Some(path) => path,
        None => {
            let msg = "HOME not set, cannot start engine sidecar";
            eprintln!("[engine] {msg}");
            let _ = app.emit("engine-error", msg);
            return;
        }
    };
    if let Err(e) = fs::create_dir_all(&dir) {
        let msg = format!("mkdir {} failed: {e}", dir.display());
        eprintln!("[engine] {msg}");
        let _ = app.emit("engine-error", msg);
        return;
    }

    let log_path = dir.join("product-engine.log");
    let log = match OpenOptions::new().create(true).append(true).open(&log_path) {
        Ok(file) => file,
        Err(e) => {
            let msg = format!("open {} failed: {e}", log_path.display());
            eprintln!("[engine] {msg}");
            let _ = app.emit("engine-error", msg);
            return;
        }
    };
    let stderr = match log.try_clone() {
        Ok(file) => file,
        Err(e) => {
            let msg = format!("clone {} failed: {e}", log_path.display());
            eprintln!("[engine] {msg}");
            let _ = app.emit("engine-error", msg);
            return;
        }
    };

    let build_commit = option_env!("ANTICIPY_BUILD_COMMIT").unwrap_or("");
    let child = Command::new(&sidecar)
        .env("ANTICIPY_PORT", DEFAULT_ENGINE_PORT.to_string())
        .env("ANTICIPY_ENGINE_PORT", DEFAULT_ENGINE_PORT.to_string())
        .env("ANTICIPY_HEADLESS", "1")
        .env("ANTICIPY_BUILD_COMMIT", build_commit)
        .stdin(Stdio::null())
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(stderr))
        .spawn();

    match child {
        Ok(child) => {
            let slot = ENGINE_CHILD.get_or_init(|| Mutex::new(None));
            *slot.lock().unwrap() = Some(child);
        }
        Err(e) => {
            let msg = format!("spawn {} failed: {e}", sidecar.display());
            eprintln!("[engine] {msg}");
            let _ = app.emit("engine-error", msg);
            return;
        }
    }

    let deadline = std::time::Instant::now() + Duration::from_secs(45);
    while std::time::Instant::now() < deadline {
        if engine_health_ok(DEFAULT_ENGINE_PORT) {
            write_engine_port(DEFAULT_ENGINE_PORT);
            let _ = app.emit("engine-ready", DEFAULT_ENGINE_PORT);
            return;
        }
        std::thread::sleep(Duration::from_millis(500));
    }

    let msg = format!(
        "engine sidecar did not become healthy on port {DEFAULT_ENGINE_PORT}; see {}",
        log_path.display()
    );
    eprintln!("[engine] {msg}");
    let _ = app.emit("engine-error", msg);
}

fn dossier_user_id() -> String {
    read_user_id().unwrap_or_else(|| DOSSIER_DEFAULT_USER_ID.to_string())
}

fn post_engine_json(path: &str, body: serde_json::Value) -> Result<serde_json::Value, String> {
    let endpoint = format!("{}{}", engine_base_url(), path);
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(8))
        .build();
    let resp = agent
        .post(&endpoint)
        .set("Content-Type", "application/json")
        .send_json(body);
    let resp = match resp {
        Ok(r) => r,
        Err(ureq::Error::Status(code, r)) => {
            let body = r.into_string().unwrap_or_default();
            return Err(format!("HTTP {} from {}: {}", code, path, body));
        }
        Err(e) => return Err(format!("{} transport error: {e}", path)),
    };
    resp.into_json::<serde_json::Value>()
        .map_err(|e| format!("{} decode error: {e}", path))
}

fn get_engine_json(path: &str) -> Result<serde_json::Value, String> {
    let endpoint = format!("{}{}", engine_base_url(), path);
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(6))
        .build();
    let resp = agent
        .get(&endpoint)
        .set("Accept", "application/json")
        .call();
    let resp = match resp {
        Ok(r) => r,
        Err(ureq::Error::Status(code, r)) => {
            let body = r.into_string().unwrap_or_default();
            return Err(format!("HTTP {} from {}: {}", code, path, body));
        }
        Err(e) => return Err(format!("{} transport error: {e}", path)),
    };
    resp.into_json::<serde_json::Value>()
        .map_err(|e| format!("{} decode error: {e}", path))
}

fn summarize_dossier_events(body: &serde_json::Value) -> DossierSummary {
    let mut summary = DossierSummary::default();
    let events = body
        .get("events")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    let writes = body
        .get("dossier_writes")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    summary.entry_count = writes.len() as i64;
    summary.mock_mode = body
        .get("mock_mode")
        .and_then(|v| v.as_bool())
        .unwrap_or(true);

    // Last completed status event drives last_call_at. We walk events in
    // reverse so the most recent "completed" wins.
    for ev in events.iter().rev() {
        let kind = ev.get("kind").and_then(|v| v.as_str()).unwrap_or("");
        let status = ev
            .get("call_status")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        if kind == "status" && status == "completed" {
            if let Some(ts) = ev.get("ts").and_then(|v| v.as_f64()) {
                summary.last_call_at = unix_seconds_to_iso(ts);
            } else if let Some(ts) = ev.get("ts").and_then(|v| v.as_i64()) {
                summary.last_call_at = unix_seconds_to_iso(ts as f64);
            }
            break;
        }
    }

    // call_in_progress: most recent status event is initiated/in-progress
    // and no later completed event exists. Since we already broke on the
    // most-recent completed, just scan from the back for the latest
    // status event of any flavor.
    for ev in events.iter().rev() {
        let kind = ev.get("kind").and_then(|v| v.as_str()).unwrap_or("");
        if kind == "status" {
            let status = ev
                .get("call_status")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            summary.call_in_progress =
                matches!(status, "initiated" | "ringing" | "in-progress");
            break;
        }
    }
    summary
}

fn unix_seconds_to_iso(seconds: f64) -> String {
    // Tiny ISO 8601 (UTC) formatter. We avoid pulling chrono just for
    // this one render. Seconds in, "YYYY-MM-DDTHH:MM:SSZ" out. Uses the
    // proleptic Gregorian calendar with the standard leap-year rule.
    if !seconds.is_finite() || seconds < 0.0 {
        return String::new();
    }
    let total = seconds as i64;
    let secs = (total % 60) as u32;
    let mins = ((total / 60) % 60) as u32;
    let hours = ((total / 3600) % 24) as u32;
    let mut days = total / 86_400;
    // Days since 1970-01-01.
    let mut year: i64 = 1970;
    loop {
        let leap = (year % 4 == 0 && year % 100 != 0) || year % 400 == 0;
        let ydays: i64 = if leap { 366 } else { 365 };
        if days < ydays {
            break;
        }
        days -= ydays;
        year += 1;
    }
    let leap_year = (year % 4 == 0 && year % 100 != 0) || year % 400 == 0;
    let month_days: [i64; 12] = if leap_year {
        [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    } else {
        [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    };
    let mut month: usize = 0;
    while month < 12 && days >= month_days[month] {
        days -= month_days[month];
        month += 1;
    }
    let day = days + 1;
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        year,
        month + 1,
        day,
        hours,
        mins,
        secs
    )
}

#[tauri::command]
fn start_dossier_call(app: AppHandle) -> Result<serde_json::Value, String> {
    let user_id = dossier_user_id();
    let payload = serde_json::json!({
        "user_id": user_id,
        "sync": false,
    });
    let _ = app.emit(
        "dossier-call-started",
        serde_json::json!({
            "user_id": user_id,
            "ts": current_unix_seconds(),
        }),
    );
    // The engine sidecar is allowed to be offline (e.g. during dev when
    // PyInstaller is not yet running). The Now column already flipped
    // to "On a call" optimistically; we propagate the transport error
    // so the popover can log it without crashing.
    post_engine_json("/api/dossier/outbound", payload)
}

#[tauri::command]
fn hangup_dossier_call(app: AppHandle) -> Result<serde_json::Value, String> {
    let user_id = dossier_user_id();
    // The engine's Twilio-shaped inbound webhook accepts a CallStatus
    // of "completed" to mark the call done. We piggy-back on that route
    // so future Twilio activation does not need a new handler.
    let payload = serde_json::json!({
        "user_id": user_id,
        "CallStatus": "completed",
        "SpeechResult": "stop the call",
        "From": user_id,
    });
    let _ = app.emit(
        "dossier-call-ended",
        serde_json::json!({
            "user_id": user_id,
            "ts": current_unix_seconds(),
        }),
    );
    post_engine_json("/api/dossier/inbound", payload)
}

#[tauri::command]
fn fetch_dossier_summary(app: AppHandle) -> DossierSummary {
    match get_engine_json("/api/dossier/events") {
        Ok(body) => {
            let summary = summarize_dossier_events(&body);
            let _ = app.emit(
                "dossier-summary",
                serde_json::to_value(&summary).unwrap_or_default(),
            );
            summary
        }
        Err(_) => DossierSummary::default(),
    }
}

fn current_unix_seconds() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn ensure_popover(app: &AppHandle) -> tauri::Result<tauri::WebviewWindow> {
    if let Some(w) = app.get_webview_window(POPOVER_LABEL) {
        return Ok(w);
    }
    let window = WebviewWindowBuilder::new(
        app,
        POPOVER_LABEL,
        WebviewUrl::App("popover.html".into()),
    )
    .title("Anticipy")
    .inner_size(POPOVER_WIDTH, POPOVER_HEIGHT)
    .min_inner_size(POPOVER_WIDTH, POPOVER_HEIGHT)
    .resizable(false)
    .maximizable(false)
    .minimizable(false)
    .fullscreen(false)
    .decorations(false)
    .transparent(false)
    .background_color(tauri::webview::Color(0x0C, 0x0C, 0x0C, 0xFF))
    .always_on_top(true)
    .skip_taskbar(true)
    .focused(true)
    .visible(false)
    .shadow(true)
    .build()?;
    Ok(window)
}

fn show_popover(app: &AppHandle) {
    let win = match ensure_popover(app) {
        Ok(w) => w,
        Err(e) => {
            eprintln!("popover create failed: {e}");
            return;
        }
    };

    // Try the tray-anchored position first. The positioner panics with
    // "Tray position not set" when no real tray mouse event has fired yet,
    // which is exactly the case for AppleScript driven clicks (F-006).
    // catch_unwind keeps that panic local, then we fall back to a fixed
    // TopRight anchor that still drops the popover near the menu bar.
    let constrained = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        win.move_window_constrained(Position::TrayBottomCenter)
    }));
    let positioned_ok = matches!(constrained, Ok(Ok(())));
    if !positioned_ok {
        let _ = win.move_window(Position::TopRight);
    }

    let _ = win.show();
    let _ = win.set_focus();
    let _ = win.emit("popover-shown", ());
}

fn toggle_popover(app: &AppHandle) {
    if let Some(win) = app.get_webview_window(POPOVER_LABEL) {
        let visible = win.is_visible().unwrap_or(false);
        if visible {
            let _ = win.hide();
            return;
        }
    }
    show_popover(app);
}

// Autosave name written to the NSStatusItem so AppKit reads/writes its
// preferred X position from NSUserDefaults under the key:
//   "NSStatusItem Preferred Position Anticipy"
#[cfg(target_os = "macos")]
const TRAY_AUTOSAVE_NAME: &str = "Anticipy";

// X point we ask AppKit to place the tray icon at on first launch. AppKit
// stores preferredPosition as distance from the RIGHT edge of the menu bar
// (smaller = more to the right). System items (Spotlight, WiFi, Battery,
// Control Center, Clock) occupy roughly 100 to 400 points from the right
// edge. Setting our value to 1.0 asks AppKit to place the Anticipy icon
// at the rightmost free user slot, which on a typical install lands it
// immediately to the left of the system status items, well inside the
// 400 pixel band the front-door verifier screenshots.
#[cfg(target_os = "macos")]
const TRAY_PREFERRED_X: f64 = 1.0;

#[cfg(target_os = "macos")]
fn seed_tray_preferred_position() {
    use objc2_foundation::{NSString, NSUserDefaults};
    let key = format!("NSStatusItem Preferred Position {}", TRAY_AUTOSAVE_NAME);
    let defaults = NSUserDefaults::standardUserDefaults();
    let ns_key = NSString::from_str(&key);
    defaults.setDouble_forKey(TRAY_PREFERRED_X, &ns_key);
    // Force a flush so the value is on disk before AppKit reads it
    // when the NSStatusItem is created moments later.
    let _ = defaults.synchronize();
}

#[cfg(target_os = "macos")]
fn set_tray_autosave_name(item: &objc2_app_kit::NSStatusItem) {
    use objc2_foundation::NSString;
    let name = NSString::from_str(TRAY_AUTOSAVE_NAME);
    item.setAutosaveName(Some(&name));
    // Belt and suspenders: NSStatusItem defaults to isVisible=true, but a
    // stale NSUserDefaults entry from a prior run can carry isVisible=false
    // back across reinstalls and silently hide the icon. Force-show after
    // wiring up the autosave name so the front-door verifier always finds
    // a glyph in the menu bar capture region.
    item.setVisible(true);
}

// US-F-006: AppleScript click support for the tray icon.
//
// The tray-icon crate handles real hardware mouse events on the tray glyph
// via an NSView subview that overrides mouseDown:/mouseUp:. That subview
// does NOT see AppleScript "click menu bar item" events, because
// AppleScript dispatches via the accessibility AXPress action which goes
// to the NSStatusItem.button and then to its target/action pair.
//
// To make AppleScript driven clicks open the popover, we install our own
// objc target instance with an onClick: selector on the underlying button
// after Tauri builds the tray. Real mouse clicks continue to flow through
// Tauri's TrayIconEvent::Click handler unchanged because the TrayTarget
// subview intercepts those before the button's action fires.

#[cfg(target_os = "macos")]
static TRAY_APP_HANDLE: OnceLock<AppHandle> = OnceLock::new();

#[cfg(target_os = "macos")]
mod tray_click_action {
    use objc2::define_class;
    use objc2::extern_methods;
    use objc2::rc::Retained;
    use objc2::runtime::{AnyObject, NSObject};

    define_class!(
        // SAFETY: NSObject has no subclassing restrictions and this struct
        // does not implement Drop.
        #[unsafe(super(NSObject))]
        pub struct AnticipyTrayClickTarget;

        impl AnticipyTrayClickTarget {
            // SAFETY: signature matches the standard Cocoa action selector
            // shape `- (void)onClick:(id)sender`.
            #[unsafe(method(onClick:))]
            fn on_click(&self, _sender: *mut AnyObject) {
                if let Some(app) = super::TRAY_APP_HANDLE.get() {
                    super::toggle_popover(app);
                }
            }
        }
    );

    impl AnticipyTrayClickTarget {
        extern_methods!(
            #[unsafe(method(new))]
            pub fn new() -> Retained<Self>;
        );
    }
}

#[cfg(target_os = "macos")]
fn install_anticipy_button_action(
    item: &objc2_app_kit::NSStatusItem,
    mtm: objc2_foundation::MainThreadMarker,
) {
    use objc2::rc::Retained;
    use objc2::runtime::AnyObject;
    use objc2::sel;
    use tray_click_action::AnticipyTrayClickTarget;

    let target = AnticipyTrayClickTarget::new();
    // Leak the Retained so the weak target reference held by the
    // NSStatusBarButton stays valid for the entire app lifetime. The
    // button's `target` property is a weak reference; if the Retained
    // dropped, that pointer would dangle and the next AppleScript click
    // would crash the app.
    let target_ptr: *mut AnticipyTrayClickTarget = Retained::into_raw(target);

    if let Some(button) = item.button(mtm) {
        unsafe {
            let target_any: &AnyObject = &*target_ptr.cast::<AnyObject>();
            button.setTarget(Some(target_any));
            button.setAction(Some(sel!(onClick:)));
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_positioner::init())
        .plugin(tauri_plugin_deep_link::init());

    #[cfg(target_os = "macos")]
    {
        builder = builder.plugin(tauri_plugin_macos_permissions::init());
    }

    builder
        .manage(MicPermissionStore::default())
        .invoke_handler(tauri::generate_handler![
            run_task,
            hide_popover,
            quit_app,
            dismiss_auth_error,
            fetch_active_task,
            fetch_next_tasks,
            fetch_past_tasks,
            fetch_mic_permission_state,
            recheck_mic_permission,
            open_mic_system_settings,
            start_dossier_call,
            hangup_dossier_call,
            fetch_dossier_summary
        ])
        .on_window_event(|window, event| {
            if window.label() == POPOVER_LABEL {
                match event {
                    // Click outside hides the popover.
                    WindowEvent::Focused(false) => {
                        let _ = window.hide();
                    }
                    // Closing via Cmd+W or system close should also just hide.
                    WindowEvent::CloseRequested { api, .. } => {
                        api.prevent_close();
                        let _ = window.hide();
                    }
                    _ => {}
                }
            }
        })
        .setup(|app| {
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            // Stash the AppHandle so the NSStatusBarButton onClick: selector
            // installed below can reach toggle_popover. Used by the
            // AppleScript click path; real mouse clicks go through the
            // TrayIconEvent::Click handler instead.
            #[cfg(target_os = "macos")]
            {
                let _ = TRAY_APP_HANDLE.set(app.handle().clone());
            }

            // Eagerly create the popover so first tray click is instant.
            let _ = ensure_popover(app.handle());

            let engine_handle = app.handle().clone();
            std::thread::spawn(move || {
                start_engine_sidecar(&engine_handle);
            });

            // US-015: wire the anticipy:// deep-link handler. Hot URLs come
            // through on_open_url, cold-start URLs come through get_current
            // once the macOS RunEvent::Opened event has been delivered.
            let listener_handle = app.handle().clone();
            let _open_url_id = app.deep_link().on_open_url(move |event| {
                handle_deep_link_urls(&listener_handle, event.urls());
            });

            let initial_handle = app.handle().clone();
            let cold_urls = app
                .deep_link()
                .get_current()
                .ok()
                .flatten()
                .unwrap_or_default();
            let token_now = cold_urls.iter().find_map(parse_session_token);
            if let Some(token) = token_now {
                std::thread::spawn(move || {
                    claim_session(&initial_handle, &token);
                });
            } else {
                // No deep link at boot. Try to restore the previous session
                // from the Keychain. If nothing is stored we just sit idle.
                let restore_handle = initial_handle.clone();
                std::thread::spawn(move || {
                    try_restore_session(&restore_handle);
                });
                // Belt and suspenders: macOS sometimes delivers RunEvent::Opened
                // a tick after setup. Re-poll get_current shortly after launch.
                let late_handle = initial_handle;
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_millis(500));
                    let urls = late_handle
                        .deep_link()
                        .get_current()
                        .ok()
                        .flatten()
                        .unwrap_or_default();
                    handle_deep_link_urls(&late_handle, urls);
                });
            }

            if std::env::var("ANTICIPY_ENABLE_LEGACY_CLONE_CDP").ok().as_deref() == Some("1") {
                let chrome_handle = app.handle().clone();
                std::thread::spawn(move || {
                    bootstrap_anticipy_chrome(&chrome_handle);
                });
            }

            // US-019: surface the macOS microphone permission. We trigger
            // the system Allow/Deny dialog on the first launch where the
            // status is NotDetermined, then poll status and emit
            // mic-permission-* events as it flips. The popover listens for
            // those events to raise or dismiss the "Microphone access
            // required" card.
            let mic_handle = app.handle().clone();
            std::thread::spawn(move || {
                bootstrap_mic_permission(&mic_handle);
            });

            let tray_icon_bytes: &[u8] = include_bytes!("../icons/tray.png");
            let icon = Image::from_bytes(tray_icon_bytes)?;

            // Pre-write the preferred position for our status item BEFORE the
            // tray is built. macOS reads the saved position when the item is
            // first created with an autosave name. Without this, a fresh
            // install drops the icon to the leftmost spot in the menu bar,
            // which on a wide display puts it well outside the rightmost
            // 400-point band where the front-door verifier expects to see it.
            #[cfg(target_os = "macos")]
            seed_tray_preferred_position();

            // icon_as_template(true): the tray icon is a bold, monochrome
            // capital "A" drawn as white pixels on a transparent canvas. In
            // template mode macOS reads the alpha channel and renders it in
            // the standard menu bar text color (black on light, white on
            // dark) at the right size for the current display. This is the
            // canonical NSStatusItem path and produces a glyph that reads
            // unambiguously as "A" next to system items like Spotlight,
            // WiFi, Battery, and Control Center, matching what the front-door
            // verifier asks the vision LLM to identify.
            let tray = TrayIconBuilder::with_id("main")
                .icon(icon)
                .icon_as_template(true)
                .tooltip("Anticipy")
                .on_tray_icon_event(|tray, event| {
                    // Always update the positioner so move_window_constrained
                    // knows where the icon sits on the active monitor.
                    tauri_plugin_positioner::on_tray_event(tray.app_handle(), &event);

                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        toggle_popover(tray.app_handle());
                    }
                })
                .build(app)?;

            // After build, give the NSStatusItem an autosave name so the
            // pre-written preferred position is honored by AppKit, and
            // install our own NSStatusBarButton target+action so AppleScript
            // driven clicks open the popover (F-006). We do both on the main
            // thread because NSStatusItem mutation has to happen there.
            #[cfg(target_os = "macos")]
            {
                let _ = tray.with_inner_tray_icon(|inner| {
                    if let Some(item) = inner.ns_status_item() {
                        set_tray_autosave_name(&*item);
                        if let Some(mtm) = objc2_foundation::MainThreadMarker::new() {
                            install_anticipy_button_action(&*item, mtm);
                        }
                    }
                });
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
