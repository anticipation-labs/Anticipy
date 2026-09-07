# Live loading-delay investigation — September 7, 2026

**The API was up; the owner's conversation processing fell minutes behind.** Checks completed at 13:56 Vancouver time. No restart, code change, model test, message or production data mutation was performed.

The owner reported nothing loading around “147.” The records show relevant activity at 13:47, so that time is the working interpretation, not a confirmed meaning of the number.

## Verified observations

- API health returned HTTP 200 in 68 ms using the requests client. Authenticated owner-scoped event, job and browser-agent reads returned HTTP 200 in 162–243 ms.
- Brain status returned HTTP 200 in 219 ms. The owner's process was running on the expected source with a current memory snapshot. The fleet reported eight served owners and no failed owners. Process liveness alone does not measure input backlog.
- Twenty-eight phone transcript records from 13:43:56 through 13:49:20 recorded **140 hearing model calls**, totaling **498.679 seconds** of instrumented hearing time. This total is elapsed hearing work, not model billing or a claim that every millisecond was provider latency.
- Those records' median creation-to-saved-decision interval was **179.913 seconds**; maximum **395.338 seconds**. These intervals use server timestamps, not an observed physical-screen render time.
- A dinner-related input arrived at **13:47:22.811**. Its task was created at **13:53:09.905**, roughly **347 seconds later**, and subsequently held for clarification. A following location detail was not finalized until 13:53:50. The saved clarification still asked about location even though the saved goal included the city; that context/clarification defect needs separate review.
- Fifteen calendar profile events arrived at approximately 13:47:42–45. Their saved decisions progressed one by one from 13:49:42 to 13:50:42. The backlog was already growing before this import, so calendar ingestion is an additional delay, not the sole cause.
- At **13:56:14**, an owner-scoped query for transcript/app/text inputs with empty or `processing` decisions returned **zero pending inputs**. The captured backlog had drained. That does not mean all tasks completed or that the performance defect is repaired.

## Source explanation

`brain/worker.py:5210` processes fetched speech records in a serial loop; `hear()` completes before the next record is handled. The loop has a time budget between records, but that does not interrupt an in-progress multi-call hearing operation or make throughput match incoming speech.

`brain/worker.py:655` loops through profile imports and calls `memory.remember_fact` for each. The main loop invokes it before reaching speech processing on a profile-refresh turn. The observed calendar timing is consistent with this serial structure.

The transcript transport also delivered very short successive revisions and a later cumulative transcript. All had `seq=0` and empty `boot_id` in these records. This is evidence to investigate capture finality/revision identity; it is not permission to deduplicate or ignore human speech by word count or text similarity.

## Repair direction

1. Correct capture/finality plumbing using stable utterance and revision identities so interim recognition fragments do not each become independent expensive decisions. Preserve full conversation evidence.
2. Make model reasoning operate over coherent context through the shared approval/execution path. Do not replace it with keyword gates or remove authority checks to improve latency.
3. Bound and schedule background profile/memory ingestion so it cannot monopolize the interactive input loop. Preserve owner isolation, ordering and SQLite access discipline; do not add unmanaged parallel threads to shared brain state.
4. Report oldest-pending-input age and active processing progress alongside process health, and reflect delayed processing in the app. The current green process probe did not expose this user-visible failure.

The physical iPhone screen and its owner-token fetch/render path were not observed in this investigation. The backend backlog is proven; a separate client loading failure is not excluded.

Sanitized measurements: [loading-incident-evidence.json](loading-incident-evidence.json). Raw owner records were retained only in ignored local `work/audit/loading-incident-private.json`, not copied into the tracked report. No production content was changed or replayed.
