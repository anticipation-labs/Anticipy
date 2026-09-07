/** Warm health reads must not re-enter the container startup lifecycle. */
export async function observeRunning<T>(running: () => boolean,
    start: () => Promise<void>, observe: () => Promise<T>): Promise<T> {
  if (!running()) await start();
  // A failed observation is a failed observation. It must never restart a
  // live worker, whose in-flight action or memory snapshot may still be active.
  return await observe();
}
