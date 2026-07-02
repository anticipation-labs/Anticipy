import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const STORE_DIR = path.join(process.cwd(), ".anticipy-data", "phase-zero");
const STORE_FILE = path.join(STORE_DIR, "state.json");

export const DEFAULT_PROFILE = {
  name: "",
  summary: "",
  phone: "",
  timezone: "America/Vancouver",
  trustDial: "Regular",
  textFirst: true,
  doNotTouch: "",
  people: [
    { name: "Priya", role: "important collaborator", cadence: "recurring", register: "short and direct" },
    { name: "Marcus", role: "client or deal contact", cadence: "active open loop", register: "full paragraphs" },
  ],
  roleContext: "Busy operator with work, people, and open loops spread across real systems.",
  tools: ["Gmail", "Calendar", "Chrome", "Drive", "Notion", "HubSpot"],
  openLoops: [
    "Confirm the important people Anticipy should watch.",
    "Review the first set of open loops after Layer-2 reading.",
  ],
  communicationStyle: "Warm, concise, human, never system-like.",
  rules: ["Money always asks.", "Anything irreversible always asks.", "Vents are never acted on."],
  openQuestions: [
    "Which people are never worth interrupting you about?",
    "Which systems are allowed during the deeper read?",
  ],
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
