export type PersonId = "omar" | "ari" | "jose";

export interface Person {
  id: PersonId;
  name: string;
  role: string;
  owns: string[];
  focus: string;
  email: string;
  phone: string;
  reminderPref: "In-app" | "Email" | "SMS" | "Email + SMS";
  calendarStatus: string;
}

export type TaskStatus =
  | "open"
  | "in_progress"
  | "waiting"
  | "blocked"
  | "done"
  | "cancelled";

export type Priority = "urgent" | "important" | "normal" | "later";

export type Project =
  | "Hardware"
  | "Software"
  | "Growth"
  | "Company"
  | "Fundraise";

export interface ChecklistItem {
  id: string;
  text: string;
  done: boolean;
}

export interface Comment {
  id: string;
  author: PersonId;
  text: string;
  at: string; // ISO
}

export interface ActivityEntry {
  id: string;
  text: string;
  at: string;
}

export interface Task {
  id: string;
  title: string;
  outcome: string;
  owner: PersonId | null;
  agentRunId: string | null;
  status: TaskStatus;
  priority: Priority;
  project: Project;
  due: string | null; // ISO
  recurrence: "none" | "daily" | "weekly" | "monthly";
  reminder: Reminder | null;
  notes: string;
  checklist: ChecklistItem[];
  dependsOn: string[];
  links: { label: string; href: string }[];
  comments: Comment[];
  activity: ActivityEntry[];
  scheduledAt: string | null; // deliberately placed on calendar
  proof: string | null;
  createdAt: string;
  order: number;
}

export interface Reminder {
  channel: "In-app" | "Email" | "SMS" | "Email + SMS";
  when: string; // ISO or description
  repeat: boolean;
  escalate: boolean;
}

export type AgentType =
  | "Claude Code"
  | "Browser agent"
  | "Research agent"
  | "Growth agent"
  | "General AI";

export type AgentStatus =
  | "queued"
  | "planning"
  | "working"
  | "waiting_input"
  | "waiting_approval"
  | "verifying"
  | "done"
  | "failed"
  | "cancelled";

export interface AgentStep {
  id: string;
  label: string;
  detail?: string;
  at: string;
  state: "done" | "active" | "pending";
  raw?: string;
}

export interface AgentQuestion {
  text: string;
  options: string[];
  answered?: string;
}

export interface AgentApproval {
  action: string;
  reason: string;
  decided?: "approved" | "rejected";
}

export interface AgentRun {
  id: string;
  taskId: string | null;
  taskName: string;
  agent: AgentType;
  requester: PersonId;
  startedAt: string;
  runtimeMin: number;
  tokens: number;
  costUsd: number;
  status: AgentStatus;
  liveStatus: string;
  steps: AgentStep[];
  question: AgentQuestion | null;
  approval: AgentApproval | null;
  proof: {
    summary: string;
    filesChanged?: string[];
    pullRequest?: string;
    sitesVisited?: string[];
    emailReceipt?: string;
    screenshots?: string[];
    tests?: string;
  } | null;
  budgetUsd: number;
  timeLimitMin: number;
}

export interface CalendarEvent {
  id: string;
  title: string;
  start: string; // ISO
  end: string;
  kind: "meeting" | "focus" | "deadline" | "agent" | "prep" | "followup";
  attendees?: PersonId[];
  source: "google" | "hq";
}

export type NotificationKind =
  | "mention"
  | "due_soon"
  | "overdue"
  | "agent_done"
  | "agent_failed"
  | "approval"
  | "calendar"
  | "followup";

export interface HQNotification {
  id: string;
  kind: NotificationKind;
  text: string;
  at: string;
  read: boolean;
  href?: string;
}

export type ViewName =
  | "My work"
  | "Company"
  | "Software"
  | "Hardware"
  | "Growth"
  | "Waiting"
  | "Completed";
