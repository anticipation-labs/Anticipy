/** Operational status is an observation, never a request to start a fleet. */
export interface WorkerObservation {
  ok: boolean;
  child_running: boolean;
  owner: string;
  source_sha256?: string;
  snapshot_age_seconds?: number | null;
  snapshot_error?: boolean;
  snapshot_current?: boolean;
  models?: Record<string, string | null>;
  gemini_configured?: boolean;
}
export interface FleetObservation {
  checked_at: number;
  served: number;
  unserved: string[];
  failed: string[];
  workers: WorkerObservation[];
  cleanup_failed: number;
}
export function fleetStatus(observation: FleetObservation | undefined, now = Date.now()) {
  const current = !!observation && now - observation.checked_at <= 180_000;
  return { ...observation, current,
    ok: !!(current && observation && !observation.failed.length && !observation.unserved.length),
    scope: "last scheduled fleet reconciliation; archive cleanup reported separately" };
}
