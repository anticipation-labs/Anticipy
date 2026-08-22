#!/bin/bash
# The whole product on one Mac: PocketBase + the brain + the phone app, with the
# phone standing in for the pendant.
#
#   sh proof/local_rig.sh up        # backend + brain, seeded, ready
#   sh proof/local_rig.sh say "look up the lunch menu at the place I always go"
#   sh proof/local_rig.sh jobs      # what the browser arm would claim
#   sh proof/local_rig.sh phone     # build, install and sign into the simulator
#   sh proof/local_rig.sh down
#
# WHY THIS EXISTS AS A SCRIPT: standing this up by hand costs an afternoon and
# every trap below was paid for once already.
#
# SAFETY, and this is the important part. It sets NO TWILIO_* VARIABLES, ever.
# brain/worker.py:2222 needs all three before it builds TwilioTransport, so with
# none of them the worker uses MockTransport and cannot text a real person. That
# also keeps ensure_inbound_webhook() from running — and on 2026-08-19 a laptop
# worker that HAD inherited the production Twilio credentials repointed the
# owner's live number at http://127.0.0.1:8090, where Twilio cannot reach it, so
# every text he sent would have been dropped. `unset` here is not tidiness; it is
# the guard. (worker.py now also refuses to write an unreachable URL, but do not
# rely on a second lock for a door you can simply not open.)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
RIG="${ANTICIPY_RIG_DIR:-$HOME/.anticipy-rig}"
PB_VERSION=0.30.4
PB_URL="http://127.0.0.1:8090"
OWNER_EMAIL=dev@local.test
OWNER_PASS=devpassword1234
LEGACY_UUID=local-dev
# The PocketBase admin UI account. Per-instance and local-only — this is not a
# shared Anticipy login and nothing in the product authenticates with it.
PB_ADMIN_EMAIL="${ANTICIPY_PB_ADMIN:-admin@anticipy.local}"
PB_ADMIN_PASS="${ANTICIPY_PB_ADMIN_PASS:-anticipy-dev-2026}"
SIM_NAME="${ANTICIPY_SIM:-iPhone 16e}"
BUNDLE=ai.anticipy.app

mkdir -p "$RIG/state"

say_step() { printf '\n=== %s ===\n' "$1"; }
env_value() { grep -E "^$1=" "$REPO/.env.local" | head -1 | cut -d= -f2- | tr -d '"'"'"''; }

# ----------------------------------------------------------------- pocketbase
fetch_pocketbase() {
    [ -x "$RIG/pocketbase" ] && return 0
    # backend/Dockerfile pulls linux_amd64; a Mac needs darwin_arm64 and the
    # binary is gitignored, so nothing in the repo fetches it for you.
    local arch=arm64
    [ "$(uname -m)" = "x86_64" ] && arch=amd64
    say_step "fetching pocketbase $PB_VERSION (darwin_$arch)"
    curl -sL -o "$RIG/pb.zip" \
      "https://github.com/pocketbase/pocketbase/releases/download/v${PB_VERSION}/pocketbase_${PB_VERSION}_darwin_${arch}.zip"
    (cd "$RIG" && unzip -oq pb.zip && rm -f pb.zip)
    chmod +x "$RIG/pocketbase"
}

start_backend() {
    if curl -sf -m 3 "$PB_URL/api/health" >/dev/null 2>&1; then
        echo "backend already up"
        return 0
    fi

    # CREATE THE ADMIN BEFORE SERVING, or PocketBase greets whoever opens
    # 127.0.0.1:8090 with its first-run installer and a "create your first
    # superuser" form. That screen made it look as though there were a shared
    # Anticipy login to be handed out; there is not. This is a per-instance
    # local account on the owner's own machine, and NOTHING in the product uses
    # it: the app, the brain and the extension all authenticate with
    # ANTICIPY_SERVICE_TOKEN or an owners JWT. The admin UI is only for
    # eyeballing rows by hand, so the credentials are fixed and boring on
    # purpose — one less thing to decide.
    #
    # `upsert` rather than `create`: re-running `up` on an existing rig must not
    # fail because the account is already there.
    if [ ! -f "$RIG/.superuser" ]; then
        "$RIG/pocketbase" superuser upsert "$PB_ADMIN_EMAIL" "$PB_ADMIN_PASS" \
            --dir "$RIG/pb_data" >/dev/null 2>&1 \
            && touch "$RIG/.superuser" \
            && echo "admin created: $PB_ADMIN_EMAIL / $PB_ADMIN_PASS"
    fi
    say_step "starting backend"
    # Deliberately NO ANTICIPY_SERVICE_TOKEN: guard.pb.js:19 returns e.next()
    # when it is unset, which is the documented local-dev mode and lets the
    # phone app talk to this rig without minting agent credentials by hand.
    #
    # OPENROUTER_API_KEY is on the BACKEND, not just the brain, and that is not a
    # duplicate. The extension never holds a vendor key: ensureLLMKey stores the
    # literal marker "backend-proxy" and every model call goes through
    # POST /agent/llm. So without a key here, GET /agent/key answers 503 "backend
    # has no model configured" (agent_key.pb.js), a real Chrome paired to this rig
    # fetches no model, and every job it claims dies at "no LLM key" — which looks
    # like a broken extension and is a missing environment variable.
    # HOOKS ARE SERVED FROM A COPY, not from the working tree.
    #
    # PocketBase watches --hooksDir and restarts on any change. Pointed at the
    # repo, that means the rig reboots itself while the tree is being edited -
    # which is the whole day, since this is the tree under test. Measured
    # 2026-08-20: 199 restarts, all naming sms.pb.js, whose mtime had not moved
    # in 24 hours; one health probe in six was REFUSED, and the worker's job
    # writes died mid-flight with ConnectionRefusedError, so real act decisions
    # silently became no-card. A test rig that reboots when you edit the code
    # you are testing produces numbers nobody should trust.
    #
    # The copy is re-synced on every `up` and the sync is announced, so this
    # cannot become the third kind of stale-code bug found today: hooks that are
    # live are hooks that were copied, and `up` says which.
    if ! diff -rq "$REPO/backend/pb_hooks" "$RIG/pb_hooks" >/dev/null 2>&1; then
        rm -rf "$RIG/pb_hooks"
        cp -R "$REPO/backend/pb_hooks" "$RIG/pb_hooks"
        echo "hooks synced from the tree ($(ls "$RIG/pb_hooks" | wc -l | tr -d ' ') files)"
    fi
    env -u ANTICIPY_SERVICE_TOKEN -u GEMINI_API_KEY \
        OPENROUTER_API_KEY="$(env_value OPENROUTER_API_KEY)" \
        ANTICIPY_BROWSER_MODEL="$(env_value ANTICIPY_BROWSER_MODEL)" \
        ANTICIPY_VISION_MODEL="$(env_value ANTICIPY_VISION_MODEL)" \
        nohup "$RIG/pocketbase" serve --http 127.0.0.1:8090 \
          --dir "$RIG/pb_data" \
          --migrationsDir "$REPO/backend/pb_migrations" \
          --publicDir "$REPO/backend/pb_public" \
          --hooksDir "$RIG/pb_hooks" \
        > "$RIG/pb.log" 2>&1 &
    for _ in $(seq 1 40); do
        curl -sf -m 2 "$PB_URL/api/health" >/dev/null 2>&1 && break
        sleep 0.5
    done
    curl -sf -m 2 "$PB_URL/api/health" >/dev/null || { tail -20 "$RIG/pb.log"; exit 1; }
    echo "backend healthy (log: $RIG/pb.log)"
}

# ---------------------------------------------------------------------- owner
ensure_owner() {
    if [ -s "$RIG/state/owner_ref" ]; then
        echo "owner_ref $(cat "$RIG/state/owner_ref")"
        return 0
    fi
    say_step "creating the local owner"
    # owners.createRule is "" (open signup), so this needs no auth.
    curl -s -X POST "$PB_URL/api/collections/owners/records" -H 'Content-Type: application/json' \
      -d "{\"email\":\"$OWNER_EMAIL\",\"password\":\"$OWNER_PASS\",\"passwordConfirm\":\"$OWNER_PASS\",\"legacy_uuid\":\"$LEGACY_UUID\"}" \
      > "$RIG/state/owner.json"
    python3 - "$RIG/state" <<'PY'
import json, sys, pathlib
d = json.load(open(pathlib.Path(sys.argv[1]) / "owner.json"))
if "id" not in d:
    sys.exit(f"could not create the owner: {str(d)[:200]}")
(pathlib.Path(sys.argv[1]) / "owner_ref").write_text(d["id"])
print("owner_ref", d["id"])
PY
    local ref; ref=$(cat "$RIG/state/owner_ref")
    curl -s -X POST "$PB_URL/api/collections/owner_profile/records" -H 'Content-Type: application/json' \
      -d "{\"owner_id\":\"$LEGACY_UUID\",\"owner_ref\":\"$ref\",\"first_name\":\"Omar\",\"email\":\"$OWNER_EMAIL\",\"phone\":\"+16045550142\",\"timezone\":\"America/Vancouver\"}" >/dev/null
    echo "owner_profile created"
}

owner_token() {
    curl -s -X POST "$PB_URL/api/collections/owners/auth-with-password" -H 'Content-Type: application/json' \
      -d "{\"identity\":\"$OWNER_EMAIL\",\"password\":\"$OWNER_PASS\"}" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token",""))'
}

# --------------------------------------------------------------------- python
ensure_venv() {
    [ -x "$RIG/venv/bin/python" ] && return 0
    say_step "creating the python env"
    # The only RUNTIME dependency declaration in the repo is brain/Dockerfile:12
    # (requests, httpx). README.md's list is stale and omits requests, which
    # brain/pb.py imports.
    #
    # pytest and numpy are here because this venv is also the one anybody runs
    # the brain suite with, and rebuilding the rig silently removed them twice —
    # which surfaces as "No module named pytest" and looks like a broken repo
    # rather than a fresh sandbox. numpy is needed only by
    # tests/test_roster_parity.py, via proof/voice_roster.py.
    python3 -m venv "$RIG/venv"
    "$RIG/venv/bin/pip" -q install requests httpx pytest numpy
}

# ---------------------------------------------------------------------- brain
start_brain() {
    # "Already running" is not the same as "running the code I have", and the
    # difference has cost three debugging sessions in one day: production served
    # extension 0.8.3 while the tree built 0.9.0; the production worker predated
    # app_reply and silently swallowed every in-app answer; and this rig served a
    # 24-hour-old worker while a fix sat in the tree, so a test measured stale
    # code and would have reported a false pass. `pgrep` answers "is a process
    # alive", which is the wrong question.
    #
    # So compare the RUNNING brain's fingerprint to the tree's and restart on a
    # mismatch. worker.py already computes _brain_fingerprint() and prints it in
    # the `worker up` banner, so the answer is on disk - it was just never read.
    if pgrep -f "brain.worker" >/dev/null 2>&1; then
        local want have
        want=$(cd "$REPO" && "$RIG/venv/bin/python" -c \
            'from brain.worker import _brain_fingerprint; print(_brain_fingerprint())' \
            2>/dev/null)
        have=$(grep -o 'brain=[0-9a-f]*' "$RIG/brain.log" 2>/dev/null | tail -1 | cut -d= -f2)
        if [ -n "$want" ] && [ -n "$have" ] && [ "$want" != "$have" ]; then
            echo "brain running is STALE (live $have, tree $want) - restarting it"
            pkill -f "brain.worker" 2>/dev/null
            sleep 2
        else
            echo "brain already running (brain=${have:-unknown}, matches tree)"
            return 0
        fi
    fi
    say_step "starting the brain"
    local ref; ref=$(cat "$RIG/state/owner_ref")
    cd "$REPO"
    # unset BRAVE_API_KEY: with it set, job_lane() routes read-only goals to
    # lane="research" and research_lane.pb.js then hides them from the
    # extension's poll, so the browser would never see the job.
    #
    # EVERY Twilio credential goes, and the list has to grow with the code:
    # outbound now PREFERS TWILIO_API_KEY_SID/SECRET over the auth token, so
    # unsetting only the four old names would leave a rig worker able to text a
    # real person the moment the owner mints an API key. TWILIO_MOCK=true is a
    # second lock, and voice_arm refuses outright while ANTICIPY_PB is loopback —
    # three independent reasons, because the failure mode here is texting a real
    # human from a laptop experiment.
    env -u BRAVE_API_KEY -u GEMINI_API_KEY -u ANTICIPY_SERVICE_TOKEN \
        -u TWILIO_ACCOUNT_SID -u TWILIO_AUTH_TOKEN -u TWILIO_PHONE_NUMBER -u TWILIO_FROM \
        -u TWILIO_API_KEY_SID -u TWILIO_API_KEY_SECRET \
        TWILIO_MOCK=true \
        ANTICIPY_PB="$PB_URL" \
        ANTICIPY_OWNER_REF="$ref" \
        ANTICIPY_OWNER_ID="$LEGACY_UUID" \
        ANTICIPY_TZ=America/Vancouver \
        OPENROUTER_API_KEY="$(env_value OPENROUTER_API_KEY)" \
        ANTICIPY_MODEL="$(env_value ANTICIPY_MODEL)" \
        ANTICIPY_MEMORY_DB="$RIG/state/memory.db" \
        ANTICIPY_CLOCK_STATE="$RIG/state/clock_state.json" \
        ANTICIPY_SEGMENTS=1 \
        nohup "$RIG/venv/bin/python" -u -m brain.worker >> "$RIG/brain.log" 2>&1 &
    sleep 4
    # APPEND, NEVER TRUNCATE. `> brain.log` destroyed the log of the run you
    # were in the middle of measuring: restart-brain is what you reach for when
    # a run looks wrong, and it deleted the only record of why. Found
    # 2026-08-20 after it ate rows 1-214 of a 320-line corpus run. Same family
    # as the three staleness bugs - the artefact you would diagnose with is
    # destroyed by the act of fixing the thing.
    #
    # Appending means old banners are still in the file, so readiness and the
    # sms=live assertion MUST read only this generation's output. `grep -m1`
    # over the whole file would match a previous boot and report a worker that
    # never started as up.
    local boot; boot=$(tail -40 "$RIG/brain.log" 2>/dev/null)
    printf '%s\n' "$boot" | grep -m1 'worker up' || { tail -20 "$RIG/brain.log"; exit 1; }
    # sms=mock is the safety assertion, not a nicety. Fail loudly if it is live.
    if printf '%s\n' "$boot" | grep -q 'sms=live'; then
        echo "REFUSING TO CONTINUE: this worker has live Twilio credentials and"
        echo "could text a real person and repoint a real phone number."
        pkill -f 'brain.worker' || true
        exit 1
    fi
    echo "brain up, sms=mock (log: $RIG/brain.log)"
}

seed_memory() {
    [ -s "$RIG/state/memory.db" ] && return 0
    say_step "seeding what she already knows"
    ANTICIPY_MEMORY_DB="$RIG/state/memory.db" "$RIG/venv/bin/python" - <<PY
import sys; sys.path.insert(0, "$REPO")
import os
from brain.memory import Memory
m = Memory(path=os.environ["ANTICIPY_MEMORY_DB"])
for f in ["he always books the Coal Harbour location, never the downtown one",
          "he prefers a table by the window",
          "dinner is usually the two of them, not a group"]:
    m.remember_fact(f, importance=5, source="interview", confidence=0.95)
print("facts:", len(m.profile_facts()))
PY
}

# ----------------------------------------------------------------- the phone
phone() {
    say_step "building the phone app"
    command -v xcodegen >/dev/null || { echo "brew install xcodegen"; exit 1; }
    cd "$REPO/app/ios"
    xcodegen generate >/dev/null
    xcodebuild -project Anticipy.xcodeproj -scheme Anticipy \
      -destination "platform=iOS Simulator,name=$SIM_NAME" \
      -configuration Debug -derivedDataPath "$RIG/dd" build \
      | grep -E '(error:|BUILD)' || true
    local app="$RIG/dd/Build/Products/Debug-iphonesimulator/Anticipy.app"
    [ -d "$app" ] || { echo "no app bundle produced"; exit 1; }

    xcrun simctl boot "$SIM_NAME" 2>/dev/null || true
    open -a Simulator
    xcrun simctl bootstatus "$SIM_NAME" -b >/dev/null 2>&1 || true
    xcrun simctl install booted "$app"

    say_step "signing the app into the local rig"
    local token ref data plist
    token=$(owner_token); ref=$(cat "$RIG/state/owner_ref")
    [ -n "$token" ] || { echo "could not authenticate the local owner"; exit 1; }
    xcrun simctl terminate booted "$BUNDLE" 2>/dev/null || true
    data=$(xcrun simctl get_app_container booted "$BUNDLE" data)
    plist="$data/Library/Preferences/$BUNDLE.plist"
    mkdir -p "$data/Library/Preferences"
    python3 - "$plist" "$token" "$ref" "$PB_URL" <<'PY'
import os, plistlib, sys
path, token, ref, base = sys.argv[1:5]
d = {}
if os.path.exists(path):
    with open(path, "rb") as f:
        try: d = plistlib.load(f)
        except Exception: d = {}
d.update({"backendURL": base, "authToken": token, "accountID": ref,
          "ownerID": "local-dev", "ownerEmail": "dev@local.test",
          "ownerFirstName": "Omar", "ownerPhone": "+16045550142",
          "hasOnboarded": True, "unsentLines": ""})
with open(path, "wb") as f: plistlib.dump(d, f)
print("session written")
PY
    # cfprefsd caches this container's preferences and will happily serve the
    # OLD values to the app even though the file on disk is correct — which
    # looks exactly like a rejected login. Only a device reboot clears it.
    say_step "rebooting the simulator so cfprefsd re-reads the session"
    local udid; udid=$(xcrun simctl list devices | grep -m1 "$SIM_NAME (" | sed -E 's/.*\(([0-9A-F-]{36})\).*/\1/')
    xcrun simctl shutdown "$udid"; sleep 3
    xcrun simctl boot "$udid" 2>/dev/null || true
    # bootstatus BLOCKS until SpringBoard is actually up. A fixed sleep raced it
    # and `launch` came back "denied by service delegate (SBMainWorkspace)",
    # which reads like a signing or entitlement failure and is neither.
    xcrun simctl bootstatus "$udid" -b >/dev/null 2>&1 || true
    xcrun simctl launch booted "$BUNDLE" >/dev/null
    echo
    echo "The phone is up and signed in. Tap 'Listen with phone' and talk;"
    echo "the Mac's microphone is the simulator's microphone."
}

# A RUNNING WORKER CAN GO STALE WITHOUT ANYONE TOUCHING IT.
#
# start_brain compares fingerprints, but only when `up` runs. Python binds its
# imports at process start, so editing brain/ while the rig is already up
# changes nothing about the process serving your test - and nothing says so.
# Measured 2026-08-20: a prompt fix landed at 14:38 against a worker booted at
# 14:15, and an 80-minute corpus run silently scored the OLD prompt. That is the
# third variant of one bug in a single day, so it gets a check of its own.
#
# mtime against process start is the only question that catches it.
warn_if_brain_edited_since_boot() {
    local pid started newer
    pid=$(pgrep -f "brain.worker" | head -1) || return 0
    [ -n "$pid" ] || return 0
    started=$(ps -o lstart= -p "$pid" 2>/dev/null) || return 0
    newer=$(find "$REPO/brain" -name '*.py' -newermt "$started" 2>/dev/null | head -3)
    [ -n "$newer" ] || return 0
    echo "WARNING: brain/ has been edited since the worker started ($started)."
    echo "  The process being tested does NOT contain these files:"
    echo "$newer" | sed 's|.*/brain/|    brain/|'
    echo "  Run: sh proof/local_rig.sh restart-brain"
}

case "${1:-up}" in
  up)
    fetch_pocketbase; start_backend; ensure_owner; ensure_venv; seed_memory; start_brain
    say_step "ready"
    echo "backend  $PB_URL   (log $RIG/pb.log)"
    echo "brain    sms=mock         (log $RIG/brain.log)"
    echo "owner    $(cat "$RIG/state/owner_ref")"
    echo "admin    $PB_URL/_/  ->  $PB_ADMIN_EMAIL / $PB_ADMIN_PASS"
    echo "         (only for eyeballing rows; nothing in the product uses it)"
    echo
    echo "Next: sh proof/local_rig.sh phone"
    echo "Chrome arm (manual — Chrome 151 ignores --load-extension on stable):"
    echo "  1. chrome://extensions -> Developer mode -> Load unpacked -> $REPO/extension"
    echo "  2. click Details -> Extension options, or open the popup and follow"
    echo "     'Setup & advanced' -> Advanced, and paste $PB_URL as the backend."
    echo "     (The console call is no longer needed; there is a field for it.)"
    echo "  3. the setup page shows a 6-digit code — type it into the iPhone app:"
    echo "     Anticipy -> Settings -> Your computer. The page flips itself."
    echo
    echo "Chrome arm (AUTOMATED — Chrome for Testing 147 DOES honour --load-extension,"
    echo "  unlike branded stable, so the whole browser arm can be driven headless):"
    echo "    CFT=~/.cache/puppeteer/chrome/mac_arm-147.0.7727.57/chrome-mac-arm64/'Google Chrome for Testing.app'/Contents/MacOS/'Google Chrome for Testing'"
    echo "    \"\$CFT\" --user-data-dir=\$(mktemp -d) --load-extension=$REPO/extension \\"
    echo "      --disable-extensions-except=$REPO/extension --remote-debugging-port=29344"
    echo "  THE PROFILE MUST BE FRESH FOR EVERY CODE CHANGE. An extension service"
    echo "  worker's MODULE GRAPH is cached in the profile: restarting the browser,"
    echo "  or even chrome.runtime.reload(), re-runs the OLD agent_loop.js while"
    echo "  fetch(getURL('agent_loop.js')) happily returns the NEW file. That gap"
    echo "  cost four rounds of fixes on 2026-08-20 — each one verified green in"
    echo "  unit tests and invisible in the live run. A throwaway --user-data-dir"
    echo "  is the only reliable way to know which code you are measuring."
    echo "  Also: kill EVERY old instance first. Two browsers sharing one paired"
    echo "  identity both poll, and the older one wins the claim race."
    ;;
  restart-brain)
    # The whole point is that this is ONE command. Telling somebody to pkill and
    # then re-run `up` invites them to skip the second half.
    pkill -f "brain.worker" 2>/dev/null && echo "stopped the old worker"
    sleep 2
    start_brain
    grep -o 'brain=[0-9a-f]*' "$RIG/brain.log" | tail -1
    ;;
  say)
    [ -n "${2:-}" ] || { echo 'usage: local_rig.sh say "<what he said>"'; exit 1; }
    # Feeding a line to a stale worker is how a whole run gets measured against
    # code nobody is running. Warn, do not block: a single ad-hoc `say` while
    # mid-edit is legitimate.
    warn_if_brain_edited_since_boot
    ref=$(cat "$RIG/state/owner_ref")
    # source=phone_mic marks this as the phone standing in for the pendant.
    # Pass pendant as $3 to compare the same errand heard by the other ear.
    src="${3:-phone_mic}"
    python3 - "$PB_URL" "$ref" "$2" "$src" <<'PY'
import json, sys, urllib.request
base, ref, text, src = sys.argv[1:5]
body = {"kind": "transcript", "device_id": "iphone-rig", "owner_ref": ref,
        "decision": "", "source": src, "explicit": True, "speaker": "owner",
        "text": text}
r = urllib.request.Request(f"{base}/api/collections/events/records", method="POST",
                           data=json.dumps(body).encode(),
                           headers={"Content-Type": "application/json"})
print("event", json.load(urllib.request.urlopen(r))["id"], "source", src)
PY
    echo "watch: tail -f $RIG/brain.log"
    ;;
  jobs)
    ref=$(cat "$RIG/state/owner_ref")
    # The extension's EXACT claim filter (background.js:359), so this answers
    # "would the browser arm actually pick this up" and not merely "does a row
    # exist" — those differ, silently, and only a console warning says which.
    python3 - "$PB_URL" "$ref" <<'PY'
import json, sys, urllib.parse, urllib.request
base, ref = sys.argv[1:3]
cond = f'status="queued" && owner_ref="{ref}" && workflow_id!="" && lane!="research"'
url = f"{base}/api/collections/jobs/records?filter={urllib.parse.quote(cond)}&perPage=10&sort=created"
items = json.load(urllib.request.urlopen(url)).get("items", [])
print(f"{len(items)} job(s) the browser arm would claim")
for j in items:
    p = json.loads(j.get("params") or "{}")
    print("  -", j["goal"])
    print("      heard by :", p.get("capture_source", "(unknown)"))
    print("      memory   :", (p.get("memory") or "(none)")[:120])
PY
    ;;
  phone) phone ;;
  down)
    pkill -f 'brain.worker' 2>/dev/null || true
    pkill -f "$RIG/pocketbase" 2>/dev/null || true
    echo "stopped. State kept in $RIG (delete it to start clean)."
    ;;
  *) sed -n '2,12p' "$0"; exit 1 ;;
esac
