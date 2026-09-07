// Queue traffic must not hold the MV3 poll lock indefinitely. This is a
// per-request network deadline, not a limit on how long a task may take.
// AbortSignal.timeout remains attached while fetch reads the response body,
// so receiving headers alone cannot turn a stalled response into a live one.
export const BACKEND_REQUEST_TIMEOUT_MS = 20_000;

export function backendFetch(input, init = {}, timeoutMs = BACKEND_REQUEST_TIMEOUT_MS) {
  const deadline = AbortSignal.timeout(timeoutMs);
  const signal = init.signal ? AbortSignal.any([init.signal, deadline]) : deadline;
  // Never retry here. A timed-out write may already have reached the server;
  // the existing claim/lease and effect-reconciliation paths own recovery.
  return globalThis.fetch(input, { ...init, signal });
}
