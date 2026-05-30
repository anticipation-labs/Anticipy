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

// Note: the prior dev-mode ENGINE_DIR + VENV_PY constants hardcoded
// Omar's local checkout path and were used only by the legacy
// run_task command + index.html UI which the polished popover does
// not load. Per CLAUDE.md "Hardcoded Omar-specific paths in shipped
// code are scale bugs to fix." Removed in cycle 122; production
// stranger users use the packaged sidecar binary via /api/* endpoints
// through popover.html.

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
// Per STRANGER_INSTALL_AUDIT W6 cycle 130: support Chromium-family
// browsers beyond Google Chrome so stranger users who installed
// Brave / Arc / Edge / Chromium / Vivaldi can still run the agent
// without a separate Google Chrome install. _resolve_chrome_binary
// returns the first one that exists on disk.
const CHROME_BINARY_CANDIDATES: &[&str] = &[
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Arc.app/Contents/MacOS/Arc",
    "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
];
const CHROME_BINARY_PATH: &str =
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

fn _resolve_chrome_binary() -> Option<&'static str> {
    for candidate in CHROME_BINARY_CANDIDATES {
        if std::path::Path::new(candidate).exists() {
            return Some(*candidate);
        }
    }
    None
}
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

// First-launch bootstrap constants. Self-bootstrap replicates what
// public/install.sh does so a stranger who only drags the .app into
// /Applications still gets a working bridge + Chrome CDP + venv. The
// marker file pins idempotence; wiping it triggers re-bootstrap.
const BOOTSTRAP_MARKER_FILE: &str = ".bootstrap-done";
const BOOTSTRAP_LOG_FILE: &str = "bootstrap.log";
const BRIDGE_LOG_FILE: &str = "anticipy-bridge.log";
const BRIDGE_PID_FILE: &str = "anticipy-bridge.pid";
const BRIDGE_LAUNCHER_NAME: &str = "anticipy-agent";
const BRIDGE_PORT: u16 = 7777;
const ANTICIPY_EXTENSION_ID: &str = "npnpagopediecennpleihemoochikggb";
const NATIVE_MESSAGING_HOSTS_REL: &str =
    "Library/Application Support/Google/Chrome/NativeMessagingHosts";
const NATIVE_MESSAGING_HOST_NAME: &str = "com.anticipy.agent.json";
const SYSTEM_PYTHON3_PATH: &str = "/usr/bin/python3";
const BRIDGE_RESOURCE_NAME: &str = "anticipy-bridge.py";
const EXTENSION_RESOURCE_NAME: &str = "anticipy-extension.zip";
// Pip packages mirror public/install.sh install_native_bridge(). websockets
// is what the CDP bridge needs at runtime; the others are inherited from the
// shipped agent so the same venv works for the full native-host agent later.
const BRIDGE_PIP_PACKAGES: &[&str] = &[
    "websockets>=12",
    "httpx>=0.25",
    "cryptography>=41",
    "python-dotenv>=1.0",
];

static ENGINE_CHILD: OnceLock<Mutex<Option<Child>>> = OnceLock::new();
static BRIDGE_CHILD: OnceLock<Mutex<Option<Child>>> = OnceLock::new();

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

// Legacy run_task Tauri command removed in cycle 122. It spawned a
// dev-only Python process at Omar's hardcoded path and was only
// reachable from the unused index.html UI. The polished popover.html
// drives the engine sidecar over HTTP via /api/listen/inject and
// /api/act, which works for any user with the packaged binary
// installed. Per the scale-by-distribution directive in CLAUDE.md.

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
    // Find the first Chromium-family browser the user has installed.
    // Falls back to the hardcoded Google Chrome path if none detected
    // (Tauri spawn will then surface ENOENT which the caller logs).
    let bin = _resolve_chrome_binary().unwrap_or(CHROME_BINARY_PATH);
    Command::new(bin)
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

/// Start the voice-onboarding flow: validate the user-entered phone,
/// hit the local engine's /api/onboarding/call_start endpoint, and
/// emit a `voice-onboarding-status` event so the popover reflects the
/// transition immediately. The engine is the authority on whether the
/// outbound Twilio call actually placed; this command just forwards.
///
/// Returns the engine's JSON response verbatim so the popover can
/// surface the call SID and any broker-side error detail.
#[tauri::command]
fn start_voice_onboarding(
    app: AppHandle,
    phone_e164: String,
) -> Result<serde_json::Value, String> {
    let phone = phone_e164.trim().to_string();
    // Mirror the broker's E.164 + +1-only gate so a typo never wastes a
    // network round-trip. The engine re-validates.
    if !phone.starts_with("+1") || phone.len() < 11 || phone.len() > 16 {
        let err = "phone must be a +1 US/CA E.164 number".to_string();
        let _ = app.emit(
            "voice-onboarding-status",
            serde_json::json!({
                "phase": "error",
                "phone": phone,
                "error": err.clone(),
                "ts": current_unix_seconds(),
            }),
        );
        return Err(err);
    }
    let _ = app.emit(
        "voice-onboarding-status",
        serde_json::json!({
            "phase": "calling",
            "phone": phone.clone(),
            "ts": current_unix_seconds(),
        }),
    );
    let payload = serde_json::json!({
        "phone_e164": phone,
    });
    match post_engine_json("/api/onboarding/call_start", payload) {
        Ok(body) => {
            let ok = body.get("ok").and_then(|v| v.as_bool()).unwrap_or(false);
            if !ok {
                let err = body
                    .get("error")
                    .and_then(|v| v.as_str())
                    .unwrap_or("engine declined the call")
                    .to_string();
                let _ = app.emit(
                    "voice-onboarding-status",
                    serde_json::json!({
                        "phase": "error",
                        "phone": phone,
                        "error": err,
                        "ts": current_unix_seconds(),
                    }),
                );
                return Ok(body);
            }
            // Kick off a background poller so the popover sees the
            // question_N transitions and the final completion event
            // without the popover needing to wake up. Aborts after 8
            // minutes (longer than the worst-case 7-question call) so
            // a dropped call eventually frees the thread.
            let call_sid = body
                .get("call_sid")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let account_id = body
                .get("account_id")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let app_clone = app.clone();
            let phone_clone = phone.clone();
            std::thread::spawn(move || {
                spawn_voice_status_poller(
                    app_clone, call_sid, account_id, phone_clone,
                );
            });
            Ok(body)
        }
        Err(e) => {
            let _ = app.emit(
                "voice-onboarding-status",
                serde_json::json!({
                    "phase": "error",
                    "phone": phone,
                    "error": e.clone(),
                    "ts": current_unix_seconds(),
                }),
            );
            Err(e)
        }
    }
}

/// Long-poll the engine's /api/onboarding/voice_status endpoint and
/// emit `voice-onboarding-status` events on every phase transition so
/// the popover renders live progress. Caps at 8 minutes so a dropped
/// call eventually frees the polling thread.
fn spawn_voice_status_poller(
    app: AppHandle,
    call_sid: String,
    account_id: String,
    phone: String,
) {
    let deadline = std::time::Instant::now()
        + std::time::Duration::from_secs(8 * 60);
    let mut last_phase: String = String::new();
    let mut last_index: i64 = -1;
    loop {
        if std::time::Instant::now() >= deadline {
            let _ = app.emit(
                "voice-onboarding-status",
                serde_json::json!({
                    "phase": "error",
                    "phone": phone,
                    "error": "voice onboarding poller timed out after 8 minutes",
                    "ts": current_unix_seconds(),
                }),
            );
            return;
        }
        let path = if !call_sid.is_empty() {
            format!(
                "/api/onboarding/voice_status?call_sid={}",
                urlencode_minimal(&call_sid),
            )
        } else {
            format!(
                "/api/onboarding/voice_status?account_id={}",
                urlencode_minimal(&account_id),
            )
        };
        match get_engine_json(&path) {
            Ok(body) => {
                let phase = body
                    .get("phase")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                let q_index = body
                    .get("question_index")
                    .and_then(|v| v.as_i64())
                    .unwrap_or(0);
                let q_total = body
                    .get("question_total")
                    .and_then(|v| v.as_i64())
                    .unwrap_or(7);
                let completed = body
                    .get("completed")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                let error_msg = body
                    .get("error")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                // Emit on transition. The "question" phase fires once
                // per index increment; "completed" and "error" fire
                // once each. "calling" never overrides itself.
                let should_emit =
                    phase != last_phase || q_index != last_index;
                if should_emit {
                    last_phase = phase.clone();
                    last_index = q_index;
                    // Map the website's "in_progress" with a question
                    // index > 0 to the popover's "question" phase so
                    // the UI shows "Question N of 7" cleanly.
                    let ui_phase = if completed {
                        "completed"
                    } else if !error_msg.is_empty()
                        || phase == "error"
                        || phase == "failed"
                    {
                        "error"
                    } else if phase == "in_progress" && q_index > 0 {
                        "question"
                    } else if phase == "calling" {
                        "calling"
                    } else {
                        phase.as_str()
                    };
                    let _ = app.emit(
                        "voice-onboarding-status",
                        serde_json::json!({
                            "phase": ui_phase,
                            "phone": phone,
                            "question_index": q_index,
                            "question_total": q_total,
                            "completed": completed,
                            "error": if error_msg.is_empty() {
                                serde_json::Value::Null
                            } else {
                                serde_json::Value::String(error_msg.clone())
                            },
                            "ts": current_unix_seconds(),
                        }),
                    );
                }
                if completed || phase == "error" || phase == "failed" {
                    return;
                }
            }
            Err(_) => {
                // Transient: keep polling, the engine may be a beat
                // behind a deferred-attach reload.
            }
        }
        std::thread::sleep(std::time::Duration::from_secs(3));
    }
}

/// Minimal percent-encoding for the query string. Covers the subset
/// that appears in a Twilio call SID (alnum) and an account_id
/// (alnum + dash + underscore), so the only real escapes are spaces
/// and the literal "+" in case an account_id ever holds one.
fn urlencode_minimal(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for ch in s.chars() {
        if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' || ch == '.' {
            out.push(ch);
        } else {
            for b in ch.to_string().into_bytes() {
                out.push_str(&format!("%{:02X}", b));
            }
        }
    }
    out
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

// ---------------------------------------------------------------------------
// First-launch bootstrap. Self-contained replacement for public/install.sh
// so a stranger who only drags Anticipy.app into /Applications still gets a
// working bridge (port 7777), a venv at ~/.anticipy/venv/, the Chrome native
// messaging host JSON wired up, and Chrome relaunched on the CDP port.
// Idempotent: skipped after the marker file is written. Reversible: deleting
// ~/.anticipy/.bootstrap-done forces a re-run on next launch.
// ---------------------------------------------------------------------------

fn bootstrap_marker_path() -> Option<PathBuf> {
    anticipy_dir().map(|d| d.join(BOOTSTRAP_MARKER_FILE))
}

fn bootstrap_log_path() -> Option<PathBuf> {
    anticipy_dir().map(|d| d.join(BOOTSTRAP_LOG_FILE))
}

fn bridge_log_path() -> Option<PathBuf> {
    anticipy_dir().map(|d| d.join(BRIDGE_LOG_FILE))
}

fn bridge_pid_path() -> Option<PathBuf> {
    anticipy_dir().map(|d| d.join(BRIDGE_PID_FILE))
}

fn bridge_launcher_path() -> Option<PathBuf> {
    anticipy_dir().map(|d| d.join(BRIDGE_LAUNCHER_NAME))
}

fn venv_dir() -> Option<PathBuf> {
    anticipy_dir().map(|d| d.join("venv"))
}

fn venv_python_path() -> Option<PathBuf> {
    venv_dir().map(|v| v.join("bin").join("python"))
}

fn venv_pip_path() -> Option<PathBuf> {
    venv_dir().map(|v| v.join("bin").join("pip"))
}

fn bridge_target_script_path() -> Option<PathBuf> {
    anticipy_dir().map(|d| d.join("anticipy-bridge.py"))
}

fn native_messaging_host_path() -> Option<PathBuf> {
    let home = std::env::var_os("HOME").map(PathBuf::from)?;
    Some(
        home.join(NATIVE_MESSAGING_HOSTS_REL)
            .join(NATIVE_MESSAGING_HOST_NAME),
    )
}

/// Append a line to the bootstrap log. Best-effort; never panics.
fn bootstrap_log(line: &str) {
    if let Some(path) = bootstrap_log_path() {
        if let Some(parent) = path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(&path) {
            use std::io::Write;
            let stamp = current_unix_seconds();
            let _ = writeln!(f, "[{:.0}] {}", stamp, line);
        }
    }
}

fn emit_bootstrap_progress(app: &AppHandle, phase: &str, message: &str) {
    bootstrap_log(&format!("{}: {}", phase, message));
    let _ = app.emit(
        "bootstrap-progress",
        serde_json::json!({
            "phase": phase,
            "message": message,
            "ts": current_unix_seconds(),
        }),
    );
}

fn emit_bootstrap_error(app: &AppHandle, phase: &str, message: &str) {
    bootstrap_log(&format!("ERROR {}: {}", phase, message));
    let _ = app.emit(
        "bootstrap-error",
        serde_json::json!({
            "phase": phase,
            "message": message,
            "ts": current_unix_seconds(),
        }),
    );
}

fn emit_bootstrap_done(app: &AppHandle) {
    bootstrap_log("bootstrap-done");
    let _ = app.emit(
        "bootstrap-done",
        serde_json::json!({ "ts": current_unix_seconds() }),
    );
}

/// Resolve the bundled resource directory. In a built .app this is
/// Contents/Resources. In dev builds we fall back to the source tree under
/// desktop/src-tauri/resources/. Falls through to a current_exe()/../Resources
/// lookup so we still work even if app.path().resource_dir() trips on
/// canonicalize on copied .app bundles.
fn bootstrap_resource_dir(app: &AppHandle) -> Option<PathBuf> {
    // Path 1: Tauri's PathResolver. Canonical for production .app bundles.
    match app.path().resource_dir() {
        Ok(p) => {
            if p.exists() {
                bootstrap_log(&format!("resource_dir(): {}", p.display()));
                return Some(p);
            } else {
                bootstrap_log(&format!(
                    "resource_dir() returned {} but does not exist on disk",
                    p.display()
                ));
            }
        }
        Err(e) => {
            bootstrap_log(&format!("resource_dir() failed: {e}"));
        }
    }
    // Path 2: derive from current_exe(). On macOS the canonical layout is
    // ${.app}/Contents/MacOS/Anticipy with resources at
    // ${.app}/Contents/Resources. Use literal join("..") so we do not need
    // canonicalize (which fails on missing intermediate symlinks).
    if let Ok(exe) = std::env::current_exe() {
        if let Some(macos_dir) = exe.parent() {
            if let Some(contents_dir) = macos_dir.parent() {
                let resources = contents_dir.join("Resources");
                if resources.exists() {
                    bootstrap_log(&format!(
                        "resource fallback (exe parent): {}",
                        resources.display()
                    ));
                    return Some(resources);
                }
            }
        }
    }
    // Path 3: dev fallback. Walk up from current_exe() to find the source
    // tree under desktop/src-tauri/resources/.
    let exe = std::env::current_exe().ok()?;
    let mut cur = exe.as_path();
    while let Some(parent) = cur.parent() {
        let candidate = parent.join("desktop").join("src-tauri").join("resources");
        if candidate.exists() {
            bootstrap_log(&format!("resource fallback (dev tree): {}", candidate.display()));
            return Some(candidate);
        }
        cur = parent;
    }
    bootstrap_log("resource_dir: all three lookup paths failed");
    None
}

fn chrome_binary_present() -> bool {
    _resolve_chrome_binary().is_some()
}

/// Confirm /usr/bin/python3 (stock macOS Sonoma / Tahoe ship Python 3.9). If
/// absent the stranger needs Xcode Command Line Tools; we surface a clear
/// error instead of silently failing.
fn ensure_system_python3() -> Result<PathBuf, String> {
    let path = PathBuf::from(SYSTEM_PYTHON3_PATH);
    if !path.exists() {
        return Err(format!(
            "{} not found. Install Xcode Command Line Tools: run xcode-select --install in Terminal.",
            SYSTEM_PYTHON3_PATH
        ));
    }
    // Sanity check: ensure it actually runs and reports a version >= 3.9.
    let out = Command::new(&path)
        .args(["-c", "import sys; print('%d.%d' % sys.version_info[:2])"])
        .output()
        .map_err(|e| format!("{} probe failed: {e}", SYSTEM_PYTHON3_PATH))?;
    if !out.status.success() {
        return Err(format!(
            "{} did not return a version string",
            SYSTEM_PYTHON3_PATH
        ));
    }
    Ok(path)
}

/// Stage the bundled bridge script into ~/.anticipy/anticipy-bridge.py.
fn install_bridge_script(app: &AppHandle) -> Result<PathBuf, String> {
    let res_dir = bootstrap_resource_dir(app)
        .ok_or_else(|| "bundled resource dir not found".to_string())?;
    let src = res_dir.join(BRIDGE_RESOURCE_NAME);
    if !src.exists() {
        return Err(format!("bundled bridge script missing at {}", src.display()));
    }
    let dst = bridge_target_script_path()
        .ok_or_else(|| "HOME not set".to_string())?;
    if let Some(parent) = dst.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("mkdir {}: {e}", parent.display()))?;
    }
    fs::copy(&src, &dst).map_err(|e| format!("copy bridge script: {e}"))?;
    Ok(dst)
}

/// Unzip the bundled Chrome extension to ~/.anticipy/extension/ so the user
/// can load-unpacked from a stable on-disk path if needed, and so install.sh
/// can pick up the same payload. Also stages native_host helpers next to the
/// agent script in ~/.anticipy/ for future native-messaging upgrades.
fn install_chrome_extension_assets(app: &AppHandle) -> Result<(), String> {
    let res_dir = bootstrap_resource_dir(app)
        .ok_or_else(|| "bundled resource dir not found".to_string())?;
    let src = res_dir.join(EXTENSION_RESOURCE_NAME);
    if !src.exists() {
        return Err(format!("bundled extension zip missing at {}", src.display()));
    }
    let dst_dir = anticipy_dir()
        .ok_or_else(|| "HOME not set".to_string())?
        .join("extension");
    fs::create_dir_all(&dst_dir).map_err(|e| format!("mkdir {}: {e}", dst_dir.display()))?;
    let status = Command::new("/usr/bin/unzip")
        .args(["-o", "-q"])
        .arg(&src)
        .arg("-d")
        .arg(&dst_dir)
        .status()
        .map_err(|e| format!("unzip spawn: {e}"))?;
    if !status.success() {
        return Err(format!("unzip failed with status {status}"));
    }
    Ok(())
}

/// Write the Chrome native messaging host JSON pointing at the launcher
/// shim. The launcher shim re-execs the venv python on anticipy_agent.py
/// shipped inside the bundled extension zip; if the agent is missing the
/// shim exits and Chrome falls back to the loopback bridge on 7777.
fn install_native_messaging_host(launcher_path: &Path) -> Result<(), String> {
    let host_path = native_messaging_host_path()
        .ok_or_else(|| "HOME not set".to_string())?;
    if let Some(parent) = host_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("mkdir {}: {e}", parent.display()))?;
    }
    let payload = serde_json::json!({
        "name": "com.anticipy.agent",
        "description": "Anticipy local agent daemon",
        "path": launcher_path.display().to_string(),
        "type": "stdio",
        "allowed_origins": [
            format!("chrome-extension://{}/", ANTICIPY_EXTENSION_ID)
        ],
    });
    let body = serde_json::to_string_pretty(&payload)
        .map_err(|e| format!("serialize host json: {e}"))?;
    fs::write(&host_path, body + "\n")
        .map_err(|e| format!("write {}: {e}", host_path.display()))?;
    Ok(())
}

/// Write the venv-aware launcher shim used by both the native messaging host
/// and the bridge daemon. Idempotent rewrite.
fn install_launcher_shim() -> Result<PathBuf, String> {
    let launcher = bridge_launcher_path()
        .ok_or_else(|| "HOME not set".to_string())?;
    let venv_py = venv_python_path()
        .ok_or_else(|| "HOME not set".to_string())?;
    let agent_script = anticipy_dir()
        .ok_or_else(|| "HOME not set".to_string())?
        .join("anticipy_agent.py");
    let body = format!(
        "#!/usr/bin/env bash\n# Anticipy agent launcher generated by Anticipy.app first-launch bootstrap.\n# Chrome speaks native messaging over stdio; do not print anything here.\nexport PYTHONUNBUFFERED=1\nif [ -x \"{venv}\" ] && [ -f \"{agent}\" ]; then\n  exec \"{venv}\" \"{agent}\"\nfi\n# Fallback: exit cleanly so Chrome native messaging does not loop.\nexit 0\n",
        venv = venv_py.display(),
        agent = agent_script.display(),
    );
    fs::write(&launcher, body).map_err(|e| format!("write launcher: {e}"))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perm = fs::metadata(&launcher)
            .map_err(|e| format!("stat launcher: {e}"))?
            .permissions();
        perm.set_mode(0o755);
        fs::set_permissions(&launcher, perm)
            .map_err(|e| format!("chmod launcher: {e}"))?;
    }
    Ok(launcher)
}

/// Create ~/.anticipy/venv/ and pip-install the bridge dependencies. Skipped
/// when the venv already exists and the websockets package imports cleanly.
fn setup_python_venv(app: &AppHandle) -> Result<PathBuf, String> {
    let py = ensure_system_python3()?;
    let venv = venv_dir().ok_or_else(|| "HOME not set".to_string())?;
    let venv_py = venv_python_path().ok_or_else(|| "HOME not set".to_string())?;

    // Fast path: venv exists and websockets imports. Nothing to do.
    if venv_py.exists() {
        let probe = Command::new(&venv_py)
            .args(["-c", "import websockets, sys; print(sys.version_info[:2])"])
            .output();
        if let Ok(out) = probe {
            if out.status.success() {
                emit_bootstrap_progress(
                    app,
                    "venv",
                    "Python environment already in place. Skipping install.",
                );
                return Ok(venv);
            }
        }
    }

    if !venv.exists() {
        emit_bootstrap_progress(app, "venv", "Creating Python environment...");
        let out = Command::new(&py)
            .args(["-m", "venv"])
            .arg(&venv)
            .output()
            .map_err(|e| format!("venv spawn: {e}"))?;
        if !out.status.success() {
            let stderr = String::from_utf8_lossy(&out.stderr).into_owned();
            return Err(format!("python -m venv failed: {stderr}"));
        }
    }

    emit_bootstrap_progress(app, "venv", "Upgrading pip...");
    let _ = Command::new(&venv_py)
        .args(["-m", "pip", "install", "--upgrade", "pip"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    emit_bootstrap_progress(app, "venv", "Installing bridge dependencies...");
    let pip = venv_pip_path().ok_or_else(|| "HOME not set".to_string())?;
    let mut cmd = Command::new(&pip);
    cmd.arg("install").arg("--quiet");
    for pkg in BRIDGE_PIP_PACKAGES {
        cmd.arg(pkg);
    }
    let out = cmd
        .output()
        .map_err(|e| format!("pip install spawn: {e}"))?;
    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr).into_owned();
        return Err(format!("pip install failed: {stderr}"));
    }
    Ok(venv)
}

fn bridge_port() -> u16 {
    std::env::var("ANTICIPY_TRIGGER_PORT")
        .ok()
        .and_then(|v| v.trim().parse::<u16>().ok())
        .filter(|p| *p > 0)
        .unwrap_or(BRIDGE_PORT)
}

fn bridge_health_ok() -> bool {
    let endpoint = format!("http://127.0.0.1:{}/status", bridge_port());
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(1))
        .build();
    match agent.get(&endpoint).set("Accept", "application/json").call() {
        Ok(r) => r.status() == 200,
        Err(_) => false,
    }
}

/// Spawn the bridge as a detached child of Anticipy.app. The bridge speaks
/// the same HTTP surface install.sh expects (port 7777). The child inherits
/// the venv Python and writes its log + PID under ~/.anticipy/.
fn start_bridge_daemon(app: &AppHandle) -> Result<(), String> {
    if bridge_health_ok() {
        emit_bootstrap_progress(
            app,
            "bridge",
            &format!("Bridge already running on {}.", bridge_port()),
        );
        return Ok(());
    }
    let venv_py = venv_python_path().ok_or_else(|| "HOME not set".to_string())?;
    if !venv_py.exists() {
        return Err(format!(
            "venv python missing at {}; cannot start bridge",
            venv_py.display()
        ));
    }
    let script = bridge_target_script_path().ok_or_else(|| "HOME not set".to_string())?;
    if !script.exists() {
        return Err(format!("bridge script missing at {}", script.display()));
    }
    let log_path = bridge_log_path().ok_or_else(|| "HOME not set".to_string())?;
    if let Some(parent) = log_path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("mkdir log dir: {e}"))?;
    }
    let log = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|e| format!("open bridge log: {e}"))?;
    let log_err = log
        .try_clone()
        .map_err(|e| format!("clone bridge log: {e}"))?;
    emit_bootstrap_progress(
        app,
        "bridge",
        &format!("Starting bridge daemon on {}...", bridge_port()),
    );
    let child = Command::new(&venv_py)
        .arg(&script)
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(log_err))
        .spawn()
        .map_err(|e| format!("spawn bridge: {e}"))?;
    let pid = child.id();
    if let Some(pid_path) = bridge_pid_path() {
        let _ = fs::write(&pid_path, pid.to_string());
    }
    {
        let slot = BRIDGE_CHILD.get_or_init(|| Mutex::new(None));
        *slot.lock().unwrap() = Some(child);
    }

    // Wait up to 8 seconds for the bridge to bind 7777 (or the
    // ANTICIPY_TRIGGER_PORT override) and answer /status.
    let deadline = std::time::Instant::now() + Duration::from_secs(8);
    while std::time::Instant::now() < deadline {
        if bridge_health_ok() {
            emit_bootstrap_progress(
                app,
                "bridge",
                &format!("Bridge healthy on {}.", bridge_port()),
            );
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    Err(format!(
        "bridge did not become healthy on port {}; see {}",
        bridge_port(),
        log_path.display()
    ))
}

/// INVESTOR-DEMO HARDENING (cycle "live-demo"): keep the engine sidecar
/// alive without human intervention. Polls `engine_health_ok` every 2
/// seconds; on the first failure it logs and re-runs `start_engine_sidecar`
/// which will respawn the binary. A successful probe resets the failure
/// counter so the watchdog stays quiet during steady state.
///
/// The popover already swallows transient engine errors and shows
/// "Getting ready" while we recover. End-to-end recovery time after a
/// `kill -9` of the engine: ~2-4 seconds (one watchdog tick to notice,
/// one start cycle).
///
/// Deliberately does NOT cap the restart count. A broken sidecar binary
/// would hot-loop here at 2s intervals; that is acceptable for the
/// investor demo (a broken binary would be caught before the demo
/// started) and adding a cap risks the watchdog quietly giving up
/// during the demo, which is worse than a tight respawn loop nobody
/// sees.
fn spawn_engine_watchdog(app: &AppHandle) {
    let handle = app.clone();
    std::thread::spawn(move || {
        // Give the initial start_engine_sidecar call time to land
        // before the watchdog starts checking. Otherwise the watchdog
        // tries to respawn the engine before the first start has even
        // begun, which double-spawns the sidecar binary.
        std::thread::sleep(Duration::from_secs(5));
        let mut consecutive_fail = 0u32;
        loop {
            std::thread::sleep(Duration::from_secs(2));
            if engine_health_ok(DEFAULT_ENGINE_PORT) {
                if consecutive_fail > 0 {
                    // Recovered. Notify the popover so the calm
                    // "Getting ready" pill flips back to "Listening".
                    let _ = handle.emit("engine-ready", DEFAULT_ENGINE_PORT);
                }
                consecutive_fail = 0;
                continue;
            }
            consecutive_fail += 1;
            eprintln!(
                "[watchdog] engine sidecar unhealthy (fail #{consecutive_fail}); respawning"
            );
            start_engine_sidecar(&handle);
        }
    });
}

/// INVESTOR-DEMO HARDENING (cycle "live-demo"): the menu bar tray
/// tooltip mirrors what the popover pill shows. The pendant's LED is
/// the canonical "we are listening" hardware signal; the tray tooltip
/// is the calm laptop-only fallback. A real breathing-icon animation
/// (regenerating the NSStatusItem image every ~600ms) is a bigger
/// surface than this cycle can absorb safely; the tooltip is the
/// 90% answer that still reassures a stranger reading the menu bar.
///
/// Polls /api/listen/status every 3 seconds. Tooltip transitions:
///   - listening on, recent acted within 8s -> "Anticipy: just acted"
///   - listening on, pending steps -> "Anticipy: working"
///   - listening on -> "Anticipy: listening"
///   - listening off or unreachable -> "Anticipy" (steady state)
///
/// Set-tooltip is a thin AppKit call (NSStatusItem.button.toolTip);
/// safe to call repeatedly. Failures are logged and swallowed so the
/// watchdog never crashes the app.
fn spawn_tray_tooltip_updater(app: &AppHandle) {
    let handle = app.clone();
    std::thread::spawn(move || {
        // Give the tray time to actually exist before the first probe.
        std::thread::sleep(Duration::from_secs(3));
        let agent = ureq::AgentBuilder::new()
            .timeout(Duration::from_secs(2))
            .build();
        let mut last_tooltip: Option<String> = None;
        loop {
            std::thread::sleep(Duration::from_secs(3));
            let url = format!(
                "http://127.0.0.1:{}/api/listen/status",
                DEFAULT_ENGINE_PORT
            );
            let tooltip = match agent.get(&url).set("Accept", "application/json").call() {
                Ok(resp) if resp.status() == 200 => {
                    match resp.into_json::<serde_json::Value>() {
                        Ok(v) => {
                            let on = v.get("on").and_then(|x| x.as_bool()).unwrap_or(false);
                            let pending_len = v
                                .get("pending")
                                .and_then(|p| p.as_array())
                                .map(|a| a.len())
                                .unwrap_or(0);
                            let acted_recent = v
                                .get("acted")
                                .and_then(|a| a.as_array())
                                .and_then(|a| a.first().cloned())
                                .and_then(|first| {
                                    first
                                        .get("ts")
                                        .or_else(|| first.get("at"))
                                        .and_then(|t| t.as_f64())
                                })
                                .map(|ts| {
                                    let now = std::time::SystemTime::now()
                                        .duration_since(std::time::UNIX_EPOCH)
                                        .map(|d| d.as_secs_f64())
                                        .unwrap_or(0.0);
                                    now - ts < 8.0
                                })
                                .unwrap_or(false);
                            if !on {
                                "Anticipy".to_string()
                            } else if acted_recent {
                                "Anticipy: just acted".to_string()
                            } else if pending_len > 0 {
                                "Anticipy: working".to_string()
                            } else {
                                "Anticipy: listening".to_string()
                            }
                        }
                        Err(_) => "Anticipy".to_string(),
                    }
                }
                _ => "Anticipy".to_string(),
            };
            if last_tooltip.as_deref() != Some(tooltip.as_str()) {
                if let Some(tray) = handle.tray_by_id("main") {
                    if let Err(e) = tray.set_tooltip(Some(tooltip.clone())) {
                        eprintln!("[tray-tooltip] set_tooltip failed: {e}");
                    } else {
                        last_tooltip = Some(tooltip);
                    }
                }
            }
        }
    });
}

/// INVESTOR-DEMO HARDENING (cycle "live-demo"): same shape as the
/// engine watchdog, but for the bridge daemon on port 7777 (or the
/// `ANTICIPY_TRIGGER_PORT` override). The bridge mediates between the
/// browser extension and the engine; if it goes down the popover loses
/// all action-execution affordances. Respawn within ~2 seconds.
fn spawn_bridge_watchdog(app: &AppHandle) {
    let handle = app.clone();
    std::thread::spawn(move || {
        // Same warm-up logic: bridge takes ~8 seconds to come up on a
        // cold start, so wait at least that long before the first
        // watchdog tick.
        std::thread::sleep(Duration::from_secs(10));
        let mut consecutive_fail = 0u32;
        loop {
            std::thread::sleep(Duration::from_secs(2));
            if bridge_health_ok() {
                consecutive_fail = 0;
                continue;
            }
            consecutive_fail += 1;
            eprintln!(
                "[watchdog] bridge daemon unhealthy on port {} (fail #{consecutive_fail}); respawning",
                bridge_port()
            );
            if let Err(e) = start_bridge_daemon(&handle) {
                eprintln!("[watchdog] bridge respawn failed: {e}");
            }
        }
    });
}

/// Run the full first-launch setup pipeline. Marker-gated: a successful run
/// writes ~/.anticipy/.bootstrap-done and short-circuits subsequent launches
/// (the existing behavior). Restartable: subsequent launches still call
/// start_bridge_daemon and bootstrap_anticipy_chrome through the launcher,
/// so the bridge respawns after a reboot or after the user quit the app.
fn first_launch_bootstrap(app: &AppHandle) {
    let dir = match anticipy_dir() {
        Some(d) => d,
        None => {
            emit_bootstrap_error(app, "init", "HOME env var not set");
            return;
        }
    };
    if let Err(e) = fs::create_dir_all(&dir) {
        emit_bootstrap_error(app, "init", &format!("mkdir {}: {e}", dir.display()));
        return;
    }

    let marker = match bootstrap_marker_path() {
        Some(p) => p,
        None => {
            emit_bootstrap_error(app, "init", "marker path not resolvable");
            return;
        }
    };
    let already_done = marker.exists();

    if !already_done {
        emit_bootstrap_progress(
            app,
            "init",
            "Setting up Anticipy. This takes about 30 seconds and only happens once.",
        );
        if !chrome_binary_present() {
            emit_bootstrap_error(
                app,
                "chrome",
                "Anticipy needs Chrome. Install from google.com/chrome and reopen Anticipy.",
            );
            // Still continue: bridge can install even without Chrome. The
            // chrome-setup-error event lets the popover raise a recovery
            // banner, but we should not leave the venv half-built.
        }
    }

    // Step A: stage the bundled bridge script. Always runs so the
    // shipped script tracks the .app version on every launch.
    if let Err(e) = install_bridge_script(app) {
        emit_bootstrap_error(app, "bridge-script", &e);
        return;
    }
    emit_bootstrap_progress(app, "bridge-script", "Bridge script staged.");

    // Step B: unzip the bundled extension into ~/.anticipy/extension/.
    // Failures here are non-fatal (the extension is installed separately
    // through the Chrome Web Store), but we still log and emit so the
    // installer-style flow keeps parity with public/install.sh.
    if let Err(e) = install_chrome_extension_assets(app) {
        emit_bootstrap_error(app, "extension", &e);
    } else {
        emit_bootstrap_progress(app, "extension", "Chrome extension assets staged.");
    }

    // Step C: create the Python venv and install dependencies.
    if let Err(e) = setup_python_venv(app) {
        emit_bootstrap_error(app, "venv", &e);
        return;
    }

    // Step D: write the launcher shim now that the venv exists, then the
    // Chrome native messaging host JSON that points at it.
    let launcher = match install_launcher_shim() {
        Ok(p) => p,
        Err(e) => {
            emit_bootstrap_error(app, "launcher", &e);
            return;
        }
    };
    emit_bootstrap_progress(app, "launcher", "Launcher installed.");
    if let Err(e) = install_native_messaging_host(&launcher) {
        emit_bootstrap_error(app, "native-host", &e);
    } else {
        emit_bootstrap_progress(app, "native-host", "Chrome native messaging host wired.");
    }

    // Step E: spawn the bridge daemon. Best-effort: failures emit
    // bridge errors but should not block the welcome view from
    // rendering.
    if let Err(e) = start_bridge_daemon(app) {
        emit_bootstrap_error(app, "bridge", &e);
    }

    // Step F: bootstrap Chrome on the CDP port. The existing
    // bootstrap_anticipy_chrome handles the cloned-profile launch and
    // emits its own chrome-setup-* events. Skipped when Chrome is not
    // installed.
    if chrome_binary_present() {
        emit_bootstrap_progress(app, "chrome", "Starting Chrome on debug port 9222...");
        bootstrap_anticipy_chrome(app);
    } else {
        emit_bootstrap_progress(
            app,
            "chrome",
            "Chrome not installed; skipping Chrome bootstrap. Anticipy will still listen.",
        );
    }

    // Marker: write only after the bridge + Chrome attempts. Subsequent
    // launches skip the venv install but still re-spawn the bridge via
    // start_bridge_daemon below in run().
    if !already_done {
        if let Err(e) = fs::write(&marker, b"ok\n") {
            emit_bootstrap_error(app, "marker", &format!("write {}: {e}", marker.display()));
        }
    }
    emit_bootstrap_done(app);
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
            start_voice_onboarding,
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

            // INVESTOR-DEMO HARDENING (cycle "live-demo"): start the
            // engine + bridge watchdogs. They sleep through the cold
            // start, then poll /health every 2 seconds and respawn the
            // sidecar / bridge daemon on the first failed probe so a
            // mid-demo crash recovers in 2-4 seconds without ever
            // surfacing a raw error to the room.
            spawn_engine_watchdog(app.handle());
            spawn_bridge_watchdog(app.handle());

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

            // First-launch self-bootstrap. Replicates public/install.sh so a
            // stranger who only drags Anticipy.app into /Applications still
            // gets the bridge on 7777, the venv at ~/.anticipy/venv/, the
            // Chrome native messaging host JSON, and Chrome relaunched on
            // the CDP port 9222. Idempotent: subsequent launches skip the
            // venv install but still re-spawn the bridge and Chrome via
            // start_bridge_daemon. Set ANTICIPY_SKIP_BOOTSTRAP=1 to opt out
            // (useful for the integration walker when isolating /tmp HOMEs
            // with no network).
            if std::env::var("ANTICIPY_SKIP_BOOTSTRAP").ok().as_deref() != Some("1") {
                let bootstrap_handle = app.handle().clone();
                std::thread::spawn(move || {
                    first_launch_bootstrap(&bootstrap_handle);
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

            // INVESTOR-DEMO HARDENING (cycle "live-demo"): drive the
            // tray tooltip from the engine's ambient listen state. The
            // pendant LED is the canonical "we are listening" signal;
            // the menu bar tooltip is the calm laptop-only fallback.
            spawn_tray_tooltip_updater(app.handle());

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
