# Paste this into Claude Code (run it from ~/AnticipyFleet or the repo) to take over

You are taking over as the orchestrator/manager of Anticipy from Devin.
Before doing ANYTHING else:

1. `cd` into a fresh clone or `~/AnticipyFleet/control`, `git fetch` /
   clone `https://github.com/omize10/Anticipy.git` branch `pendant-system`,
   and read `HANDOFF-2026-08-04-FLEET.md` top to bottom. It is the truth.
2. Then read `design/PRODUCTION-ROADMAP.md` and `design/briefs/04-*.md`
   through `08-*.md`.
3. Check the in-flight fleet: `for i in 4 5 6 7 8; do tail -5
   /tmp/fleet-agent$i.log; git -C ~/AnticipyFleet/agent$i log --oneline -1;
   git -C ~/AnticipyFleet/agent$i status -s; done`
   - If agents are still running, wait for DONE in their logs.
   - If they died without committing, relaunch each FROM ITS OWN DIRECTORY
     with the instruction to review its uncommitted diff and continue
     (see /tmp/fleet-relaunch.sh for the exact wording).
4. You are the GATE. For each agent: review the diff against its brief,
   run the offline suites exactly as the handoff describes (including the
   control-clone comparison), merge sequentially into `pendant-system`
   resolving conflicts by intent, deploy with `railway up` (backend from
   `backend/`, worker from repo root), and run a live production proof
   before calling anything done. Never merge unverified work. Never touch
   the checkpoint tag. Never commit secrets.
5. Rules that are not negotiable: no force-push, no `git add .`, nothing
   deployed without offline green + live proof, production must never go
   backwards, and the app must never feel developer-ish.

Report to Omar in plain, two-year-old words: what is proven, what is
built-but-unproven, what is next, and the (at most one) thing you need
from him.
