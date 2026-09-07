/** Gracefully retire an image left behind by a completed platform rollout. */
interface RefreshState {
  get<T>(key: string): Promise<T | undefined>;
  put(key: string, value: unknown): Promise<void>;
}
export async function requireRuntimeSource(
  expected: string, actual: string | undefined, state: RefreshState,
  durableSnapshot: () => Promise<{ uploaded: Date; size: number } | null>,
  stop: () => Promise<void>, now = Date.now(),
): Promise<void> {
  if (!/^[a-f0-9]{64}$/.test(expected)) throw new Error("expected runtime source is not configured");
  if (actual === expected) return;
  // Never repeatedly signal a Python handler that is already flushing state.
  if (await state.get<string>("runtime_refresh_requested") === expected) {
    throw new Error("old runtime is still draining; replacement not yet observed");
  }
  const snapshot = await durableSnapshot();
  if (!snapshot || snapshot.size === 0 || now - snapshot.uploaded.getTime() > 180_000) {
    throw new Error("old runtime has no recent durable snapshot; refusing automatic restart");
  }
  await state.put("runtime_refresh_requested", expected);
  await stop(); // SIGTERM, never destroy/SIGKILL: Python flushes its final snapshot.
  throw new Error("old runtime signalled for graceful replacement; awaiting next observation");
}
