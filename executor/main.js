// Anticipy Executor — Electron main process.
//
// Boot order:
//   1. Load env from .anticipy/.env (or .env.local in dev)
//   2. Verify Chrome :9222 is up (the LaunchAgent should already have
//      it running — see ~/Library/LaunchAgents/com.anticipy.chrome.plist)
//   3. Subscribe to Supabase Realtime task.dispatched.{userId}
//   4. For each Task: SkillExecutor.run() (CDP) or AnthropicComputerUse
//      fallback for canvas apps; INSERT anticipy_results_v2.

const { app, BrowserWindow } = require('electron');
const path = require('path');
const dotenv = require('dotenv');
const { createClient } = require('@supabase/supabase-js');

const { CDPClient } = require('./lib/cdp_client');
const { RealtimeSubscriber } = require('./lib/realtime_subscriber');
const { SkillExecutor } = require('./lib/skill_executor');

dotenv.config({ path: path.join(require('os').homedir(), '.anticipy', '.env') });

const SUPA_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPA_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const USER_ID = process.env.ANTICIPY_USER_ID || 'wearer';

let mainWin = null;
let subscriber = null;
let executor = null;

function createWindow() {
  mainWin = new BrowserWindow({
    width: 380,
    height: 240,
    show: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });
  mainWin.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  mainWin.on('closed', () => { mainWin = null; });
}

async function startSubscriber() {
  if (!SUPA_URL || !SUPA_KEY) {
    console.error('[executor] missing NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY');
    return;
  }
  const cdp = new CDPClient();
  try {
    const v = await cdp.ready();
    console.log('[executor] CDP attached:', v.Browser);
  } catch (e) {
    console.error('[executor] CDP not reachable on :9222 — start the LaunchAgent first');
    return;
  }
  const supabase = createClient(SUPA_URL, SUPA_KEY);
  executor = new SkillExecutor({ cdp, supabase });
  subscriber = new RealtimeSubscriber({
    supabaseUrl: SUPA_URL,
    supabaseServiceKey: SUPA_KEY,
    userId: USER_ID,
  })
    .onTask(async (task) => {
      console.log('[executor] received task', task.task_id, 'skill=', task.skill_id);
      const result = await executor.run(task);
      console.log('[executor] result', task.task_id, '->', result.status);
    })
    .start();
}

app.whenReady().then(async () => {
  createWindow();
  await startSubscriber();
});

app.on('window-all-closed', async () => {
  if (subscriber) await subscriber.stop();
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
