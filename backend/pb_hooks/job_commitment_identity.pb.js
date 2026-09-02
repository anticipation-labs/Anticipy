/// <reference path="../pb_data/types.d.ts" />

// `commitment_key` is occupied only while a workflow is active. The database
// unique index refuses two occupied rows for the same durable promise. Clear
// the auxiliary key before any terminal row is persisted so its history stays
// available and an intentional later retry can acquire the identity.
//
// These are model hooks, not HTTP-only hooks: browser, worker, dashboard and
// internal saves all cross the same boundary.
const releaseTerminalCommitment = (e) => {
  const status = String(e.record.getString("status") || "");
  if (status === "done" || status === "failed" || status === "cancelled") {
    e.record.set("commitment_key", "");
  }
  e.next();
};

onRecordCreate(releaseTerminalCommitment, "jobs");
onRecordUpdate(releaseTerminalCommitment, "jobs");
