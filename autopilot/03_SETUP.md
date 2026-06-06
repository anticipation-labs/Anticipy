# 03 SETUP — set yourself up (you run all of this yourself)

Do this once, before the loop. Run every command yourself. Do not ask the human to run anything. The only things that go to the human are real gates in `08_HUMAN_GATES.md` (for example a missing or unfunded API key). When setup passes its smoke test, create `logs/SETUP_DONE` and start the loop.

## 1. Confirm where you are
- `pwd`. You should be in the repo at `~/Desktop/Anticipy-executor-working` (confirm by the presence of `engine/`, `macapp/`, and `CODEX_BRIEF.md`). If you are not there, find it and cd in.
- `git status`, then create and switch to branch `autopilot/build` off the current HEAD. Never push to origin.

## 2. Learn the true current state
- Read `CODEX_BRIEF.md` fully. It is the honest map (every piece labeled REAL / STUB / ABSENT with file paths). Treat it as the starting truth, not as proof. Re-verify anything you will build on.
- Boot the engine and run the suite yourself to confirm the brief is still accurate:
  - engine run: `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`, then `curl http://127.0.0.1:8787/health`.
  - suite: `bash scripts/run_suite.sh` and record the real pass count. Note in your log that the suite force-stubs the live paths, so green here is not proof the product works.

## 3. Configure yourself (research the exact syntax first, do not guess)
You are running on GPT-5.5 with extra-high reasoning, in full send, with computer use. Before you write any config, open the official Codex docs (`developers.openai.com/codex`) and confirm the exact current key names and CLI flags. Do not guess config formats; that is Law 7.
Set, in your Codex config (`~/.codex/config.toml` or the current location the docs specify):
- model: GPT-5.5 (the most capable coding model available to this account).
- reasoning effort: xhigh.
- approval policy: never (full send).
- sandbox: full access (you need to touch the whole repo, the engine, Chrome, and the OS).
- computer use: enabled.
- any MCP servers already configured for this account stay configured.
Write down in your log the exact config you applied and where.

## 4. Confirm computer use works
- Using computer use, open Chrome to a real page and take a screenshot. Confirm the screenshot shows the page.
- Confirm Chrome is the real signed-in browser on this Mac (the same one the product's browser hand uses). Note the extension desktop-copy gotcha from the repo notes: Chrome loads the extension from a Desktop copy, so any extension edit needs an rsync to that copy plus a reload before it takes effect.
If computer use does not work, fix it yourself if you can; if it requires a setting only the human can toggle, that is a gate.

## 5. Dependencies
- Confirm Node 22+ (`node --version`), the Python venvs the engine uses, and any build tools `macapp/scripts/build_app.sh` needs (the build Mac may need the command-line-tools modulemap fix noted in the repo). Install or fix what you can.

## 6. Keys and live mode
- The product runs live only with real keys: OpenRouter (must be funded), Arcade (with the user id), Twilio (for the phone line). Check `.env.local` and the environment for each.
- Set the engine to live mode (the flags in the repo notes / `.env.local`).
- For any key that is missing, unfunded, or failing: do not stub around it silently. Add a specific item to `PENDING_FOR_OMAR.md` (which key, what it is for, how to provide it) and continue with everything that is not blocked by it.

## 7. Write the runner and the harness
Create the scripts the loop needs (full behavior in `04_LOOP.md`, `05_JUDGE.md`, `06_LOGGING.md`):
- `autopilot/loop.sh` — the fresh-context lap runner.
- `autopilot/build_lap` — launches a fresh builder session.
- `autopilot/judge_lap` — launches a fresh, separate judge session with computer use.
- `scripts/realday.sh` — runs the whole system end to end on one real day and writes a structured trace.
Confirm the exact command to launch a fresh non-interactive Codex session from the official docs before you rely on it. Each lap must be a fresh session reading state from files, not one long session.

## 8. Real-day material
- Create `realdays/raw/`, `realdays/holdout/`, `realdays/marked/` (see `realdays/README.md`). If the human has already dropped recordings or transcripts, leave the holdout set unread by the builder. If none exist yet, the first milestone uses a transcript and you note that real recordings make the judge real.

## 9. Smoke test, then go
- Run one dry pass: engine boots, suite green, computer use opens a real page, the realday harness runs on one sample day and writes a trace, the judge session starts and runs its planted-fake self-check (`05_JUDGE.md`).
- If all of that holds, write `logs/SETUP_DONE` with the date and the config you applied, then start `autopilot/loop.sh` and begin lap one.
- If something is blocked only by a human gate, record it in `PENDING_FOR_OMAR.md`, do every part that is not blocked, and start the loop on the unblocked work.
