import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const STORE_DIR = path.join(process.cwd(), ".anticipy-data", "phase-zero");
const STORE_FILE = path.join(STORE_DIR, "state.json");

// FIX-4.1 (honesty): a brand-new user must see NO invented facts about themselves. The default
// profile is empty — every summary/panel then reads real engine/memory data or shows a calm
// empty state. Mirrors EMPTY_PROFILE in PhaseZeroApp.js. Nothing here is a fabricated person,
// tool, or open loop.
export const DEFAULT_PROFILE = {
  name: "",
  summary: "",
  phone: "",
  timezone: "America/Vancouver",
  trustDial: "Regular",
  textFirst: true,
  doNotTouch: "",
  people: [],
  roleContext: "",
  tools: [],
  openLoops: [],
  communicationStyle: "",
  rules: [],
  openQuestions: [],
};

export const DEFAULT_SETTINGS = {
  autonomy: "Regular",
  confirmBefore: {
    money: true,
    sendToPerson: true,
    deleteOrShare: true,
    irreversible: true,
  },
  textCall: {
    textFirst: true,
    proofMirror: "coming_soon",
    phone: "",
  },
  listening: {
    browserMic: true,
    localMacMic: false,
    activeByDefault: false,
  },
  retention: {
    rawTranscriptDays: 7,
    promoteToMemory: "ask",
    redaction: "private-by-default",
  },
  browserHelper: {
    status: "checking",
  },
  security: {
    trustDial: "Regular",
    doNotTouch: "",
  },
};

export const DEFAULT_ONBOARDING = {
  currentStep: "welcome",
  completed: [],
  statusByStep: {},
  lastUpdatedAt: null,
};

export const DEFAULT_TASK_STATE = {
  comments: {},
  sort: { mode: "priority" },
  textMirror: {},
};

function defaultState() {
  return {
    profile: DEFAULT_PROFILE,
    settings: DEFAULT_SETTINGS,
    onboarding: DEFAULT_ONBOARDING,
    tasks: DEFAULT_TASK_STATE,
  };
}

async function readState() {
  try {
    const raw = await readFile(STORE_FILE, "utf8");
    return { ...defaultState(), ...JSON.parse(raw) };
  } catch {
    return defaultState();
  }
}

async function writeState(next) {
  await mkdir(STORE_DIR, { recursive: true });
  await writeFile(STORE_FILE, JSON.stringify(next, null, 2));
  return next;
}

export async function getPhaseZeroState(key) {
  const state = await readState();
  return key ? state[key] : state;
}

export async function updatePhaseZeroState(key, value) {
  const state = await readState();
  const next = {
    ...state,
    [key]: {
      ...(state[key] || {}),
      ...(value || {}),
    },
  };
  await writeState(next);
  return next[key];
}

export async function updateTaskState(partial) {
  const state = await readState();
  const next = {
    ...state,
    tasks: {
      ...(state.tasks || DEFAULT_TASK_STATE),
      ...(partial || {}),
    },
  };
  await writeState(next);
  return next.tasks;
}
