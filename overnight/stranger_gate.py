"""THE STRANGER GATE. The cold stranger's week, as prerequisites a machine checks.

`overnight/done_gate.py` leg 6 is the finish line: a real person who is not Omar,
on their own accounts, carried through a real day. It cannot be faked and it
should not be — it needs a human week.

But a human week is expensive, and on 2026-08-24 an audit walked that week
through the code first and found nine dead ends before anybody spent one
(`research/2026-08-24-cold-stranger-walkthrough.md`). Six of the nine were not
logic bugs at all: they were drift between what is deployed and what is in the
tree, and between what the documentation says and what the screens are called.

The problem with an audit is that it is true on the day it was written. This
file is the half of that audit a machine can re-check every time it is run, so
the next person does not rediscover it by burning a stranger's week.

Rules, the same as done_gate.py, tejas_gate.py and tape_gate.py:

  * A leg that CANNOT be tested FAILS. No model key, no network, no `swift` on
    PATH, a symbol renamed out from under a leg — all of those are red, and the
    message says so rather than passing by default.
  * A leg that cannot FAIL is worse than no leg. Four gate rules in this repo
    were caught on 2026-08-24 passing by matching nothing, including one
    satisfied by a guard three lines above the sentence it meant to read. Every
    leg here was watched going red against the real tree and green against a
    mutated copy — `tests/test_stranger_gate.py` is that record.
  * Legs run in order and the FIRST failure sets the verdict; later legs still
    run, so the whole picture is visible in one screen.
  * LIVE where LIVE is what bites (HARNESS-LAWS.md Law 3). Repo-green is not
    done: prod has served stale code twice. Legs 1 and 9 read production. Every
    other leg reads the tree and says so.

--------------------------------------------------------------------------
WHAT THIS GATE CANNOT SEE — stated out loud, so green is never read as safe
--------------------------------------------------------------------------
Everything the walkthrough could only settle with a device and a person:
whether the cable install succeeds on the stranger's phone at all, whether the
provisioning profile outlives the week, whether the Twilio account is trial
(on a trial account every unverified number fails silently), whether the
speaker engine actually judges correctly once enrolled, and whether the worker
running in production is this worker.

And four of the nine dead ends are deliberately NOT pinned here, because a leg
built on a name nobody has agreed to yet fires wrongly at 3am. They are listed
in `research/2026-08-24-stranger-gate.md` with the reason for each: the missing
consent artifact (STOP / 10DLC live outside the repo), MockTransport reporting
mock sends as delivered (the honest fix is a visible signal, not a return
value this gate could pin), the browser being offered only after an errand is
already stuck (a documented design decision, not drift), and UNDO plus the
clean-day counter (WIRE IT ALL names them, no code does — there is no symbol,
no column and no external API to anchor a leg to, so a leg here would only be
pinning a name this gate invented).

Run:  python3 overnight/stranger_gate.py
      python3 overnight/stranger_gate.py --verbose
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

BASE = os.environ.get("ANTICIPY_BACKEND_URL",
                      "https://backend-production-61e0a.up.railway.app")

# The one URL the setup page hands a stranger. Three names are served from the
# same bytes (`extension/build-zip.sh` copies the zip to all three); this is the
# one `backend/pb_public/setup.html` actually links.
ZIP_NAME = "anticipy-claude-version-extension.zip"

APP = "app/ios/Anticipy/AnticipyApp.swift"
BACKEND_SWIFT = "app/ios/Anticipy/Backend/AnticipyBackend.swift"
CONTENT = "app/ios/Anticipy/Views/ContentView.swift"
ONBOARDING = "app/ios/Anticipy/Views/OnboardingView.swift"
FINALE = "app/ios/Anticipy/Views/OnboardingFinale.swift"
SETTINGS = "app/ios/Anticipy/Views/SettingsView.swift"
ENROLL = "app/ios/Anticipy/Views/VoiceEnrollView.swift"
SPEAKER_MODEL = "app/ios/Anticipy/Resources/speaker-embedding.onnx"
WORKER = "brain/worker.py"
VOICE_ARM = "brain/voice_arm.py"
GUARD = "backend/pb_hooks/workflow_guard.pb.js"
SETUP_PAGE = "backend/pb_public/setup.html"
EXT_ONBOARDING = "extension/onboarding.html"
MANIFEST = "extension/manifest.json"
REPO_ZIP = "backend/pb_public/" + ZIP_NAME

WALKTHROUGH = "research/2026-08-24-cold-stranger-walkthrough.md"


class LegFailed(Exception):
    """The message is what the owner reads. Name the consequence, not the rule."""


def note(msg: str) -> None:
    if VERBOSE:
        print(f"      {msg}")


# --------------------------------------------------------------------------
# Reading the tree. Everything takes an explicit root so the mutation tests in
# tests/test_stranger_gate.py can point a leg at a synthetic copy — a gate leg
# nobody has watched fail is not a gate leg.
# --------------------------------------------------------------------------
def read(root: str, rel: str) -> str:
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        raise LegFailed(
            f"{rel} is not in this tree, so this leg cannot be tested — which "
            "counts as failing. If the file moved, move the leg with it; do "
            "not delete the leg, the check rots silently without it.")
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def read_bytes(root: str, rel: str) -> bytes:
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        raise LegFailed(
            f"{rel} is not in this tree, so this leg cannot be tested.")
    with open(path, "rb") as f:
        return f.read()


def http_get(url: str, timeout: int = 30) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def swift_span(source: str, signature_re: str) -> str:
    """The full text of a Swift declaration, from its signature to the `}` that
    closes it, by counting braces. Used to lift a real shipped function out and
    RUN it, rather than believing a comment about what it does."""
    m = re.search(signature_re, source, re.M)
    if not m:
        return ""
    open_at = source.find("{", m.start())
    if open_at < 0:
        return ""
    depth = 0
    for i in range(open_at, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[m.start():i + 1]
    return ""


def py_def(source: str, name: str) -> str:
    """The text of a Python def, top-level or a method, from its `def` line to
    the next line at the same or shallower indent. Indentation is how Python
    says where a body ends, so that is what this reads — a brace counter or a
    fixed window would slice the wrong thing and a leg would then be testing a
    span nobody chose."""
    m = re.search(rf"^([ \t]*)def {re.escape(name)}\s*\(", source, re.M)
    if not m:
        return ""
    indent = len(m.group(1))
    # Search from the LINE AFTER the signature. `^` also matches at position 0
    # of the slice, so searching from just past the `(` finds the signature's
    # own tail and every span comes back one line long — which is a leg reading
    # an empty body and reporting whatever the empty body does not contain.
    line_end = source.find("\n", m.end())
    if line_end < 0:
        return source[m.start():]
    rest = source[line_end + 1:]
    nxt = re.search(rf"^[ \t]{{0,{indent}}}(?:def |class |@|\S)", rest, re.M)
    return source[m.start():line_end + 1
                  + (nxt.start() if nxt else len(rest))]


def swift_appstorage_key(source: str, flag: str) -> str:
    """The key expression an @AppStorage-backed property is stored under, with
    its parentheses balanced.

    `[^)]*` is the obvious way to write this and it is wrong in exactly the case
    that matters: an account-scoped key is `"hasOnboarded-\\(accountID)"`, whose
    first `)` closes the interpolation. A leg using the lazy pattern reports
    "cannot find the declaration" against the very fix it is asking for, which
    is a red at 3am for work somebody already did."""
    for m in re.finditer(r"@AppStorage\(", source):
        depth = 0
        for j in range(m.end() - 1, len(source)):
            if source[j] == "(":
                depth += 1
            elif source[j] == ")":
                depth -= 1
                if depth == 0:
                    tail = source[j + 1:j + 96]
                    if re.match(rf"\s*(?:private\s+)?var\s+{re.escape(flag)}\b",
                                tail):
                        return source[m.end():j].strip()
                    break
    return ""


def have(prog: str) -> bool:
    from shutil import which
    return which(prog) is not None


# --------------------------------------------------------------------------
# Comparing an extension zip against the source it claims to be. Shared by the
# LIVE leg and the deployable-artifact leg, because the two failures are the
# same failure a deploy apart.
# --------------------------------------------------------------------------
IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*(?:import[^"']*|export[^"']*from\s*)["']\./([^"']+)["']""")


def zip_against_source(root: str, blob: bytes) -> dict:
    """What is in this zip that is not the source, and what does it import that
    it does not contain. Returns a dict of lists, all empty when the artifact
    IS the source."""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except Exception as e:  # noqa: BLE001
        raise LegFailed(f"the downloaded artifact is not a readable zip: {e}")
    entries = {}
    for info in z.infolist():
        if info.is_dir():
            continue
        name = info.filename.lstrip("./")
        entries[name] = z.read(info)

    differing, orphaned = [], []
    for name, packed in sorted(entries.items()):
        src = os.path.join(root, "extension", name)
        if not os.path.exists(src):
            orphaned.append(name)
            continue
        with open(src, "rb") as f:
            if f.read() != packed:
                differing.append(name)

    # A package can match its version and still be missing a limb — that is
    # 2026-08-13, when workflow_state.js was left out and every fresh install
    # sat forever with no pair code and no error anywhere. Same belt as
    # extension/build-zip.sh: resolve every relative import inside the package.
    broken = []
    for name, packed in sorted(entries.items()):
        if not name.endswith(".js"):
            continue
        text = packed.decode("utf-8", "replace")
        for hit in IMPORT_RE.finditer(text):
            target = hit.group(1)
            if target not in entries:
                broken.append(f"{name} imports ./{target}, which is not packaged")

    version = ""
    if "manifest.json" in entries:
        try:
            version = json.loads(entries["manifest.json"])["version"]
        except Exception:  # noqa: BLE001
            version = ""
    return {"entries": sorted(entries), "differing": differing,
            "orphaned": orphaned, "broken": broken, "version": version}


def app_pin(root: str) -> str:
    src = read(root, APP)
    m = re.search(r'static let expectedExtensionVersion = "([^"]+)"', src)
    if not m:
        raise LegFailed(
            f"{APP} no longer declares `expectedExtensionVersion`, so there is "
            "no number the stale-extension banner compares against and this "
            "leg cannot be tested. If the constant was renamed, re-point this "
            "leg and tests/test_extension_version_pin.py at the new name.")
    return m.group(1)


def source_version(root: str) -> str:
    try:
        return json.loads(read(root, MANIFEST))["version"]
    except Exception as e:  # noqa: BLE001
        raise LegFailed(f"{MANIFEST} has no usable version string: {e}")


# --------------------------------------------------------------------------
# LEG 1 — THE HANDS ARE DOWNLOADABLE, AND THEY ARE THE ONES THE APP DEMANDS
#         *** LIVE — this leg reads production, not the tree ***
#
# The extension is the only executor in the product. A stranger installs
# whatever the one download URL serves; the app then compares what Chrome
# reports against `expectedExtensionVersion` and, when Chrome is behind, tells
# them: "Open chrome://extensions and press Reload to get 0.11.0."
#
# On 2026-08-24 that URL served 0.8.4 while the app demanded 0.11.0. Reload
# re-reads the folder already on disk — it cannot fetch a version nobody is
# serving — so the instruction was guaranteed not to work, with no next step
# anywhere. That ends day one.
#
# Version equality is not enough on its own and never was: 0.8.2 was once
# served with none of that day's code in it, which no version check could
# catch. So this compares the BYTES of every packaged file against the source,
# which is also the only honest way to see that the live package is missing
# supervised_read.js, config.js, side_trip.js and four more — the reason the
# supervised mail read can never complete in production no matter what the app
# does.
# --------------------------------------------------------------------------
def leg_1_hands_downloadable(root: str = ROOT, fetch=None, base: str = "") -> str:
    fetch = fetch or http_get
    base = (base or BASE).rstrip("/")
    pin = app_pin(root)
    src_version = source_version(root)
    url = f"{base}/{ZIP_NAME}"
    try:
        blob = fetch(url)
    except Exception as e:  # noqa: BLE001
        raise LegFailed(
            f"cannot verify: {url} did not answer ({str(e)[:90]}). This leg is "
            "the one that reads LIVE, so with production unreachable there is "
            "nothing to check and it fails rather than passing. Re-run when "
            "the backend is up, or point ANTICIPY_BACKEND_URL at it.")

    found = zip_against_source(root, blob)
    served = found["version"]
    note(f"served {served}, pinned {pin}, source {src_version}, "
         f"{len(found['entries'])} packaged file(s)")

    if not served:
        raise LegFailed(
            f"{url} answered, but the package has no readable manifest "
            "version. A stranger would install it and the app could not tell "
            "how old it is.")
    if served != pin:
        raise LegFailed(
            f"the app tells the stranger to press Reload to get {pin}; the "
            f"only download in the product serves {served}. Reload re-reads "
            "the folder already on their disk — it cannot fetch a version "
            "nobody is serving, so the banner is a permanent warning with no "
            "exit. Rebuild it (`sh extension/build-zip.sh`), commit, deploy the "
            "backend, and re-run THIS gate rather than the tests — "
            "HARNESS-LAWS Law 3: repo-green is not done.")
    if pin != src_version:
        raise LegFailed(
            f"{MANIFEST} ships {src_version} but {APP} pins {pin}. The banner "
            "can only fire for someone BEHIND the pin, so a pin left in the "
            "past produces no banner at all, for everyone, forever — which is "
            "indistinguishable from a fleet that is up to date. That is how "
            "0.8.3-vs-0.11.0 went unnoticed for three minor versions.")
    if found["orphaned"]:
        raise LegFailed(
            "the served package carries files that are not in extension/ at "
            "all: " + ", ".join(found["orphaned"][:8])
            + ". Either the deploy is older than this tree or somebody edited "
              "the artifact by hand. Rebuild it from source.")
    if found["differing"]:
        raise LegFailed(
            f"the served package says {served} and is NOT that source. "
            f"{len(found['differing'])} file(s) differ byte for byte: "
            + ", ".join(found["differing"][:8])
            + ". A version that matches while the code does not is the exact "
              "failure this comparison exists for — 0.8.2 shipped that way. "
              "The stranger installs instructions nobody wrote.")
    if found["broken"]:
        raise LegFailed(
            "the served package is missing modules its own code imports: "
            + "; ".join(found["broken"][:6])
            + ". Chrome's service worker dies at load, so a fresh install sits "
              "forever with no pair code and no error anywhere.")
    return (f"{url} serves {served}, byte for byte the source the app pins, "
            f"{len(found['entries'])} files")


# --------------------------------------------------------------------------
# LEG 2 — THE ARTIFACT A DEPLOY WOULD SHIP IS THE SOURCE
#         (tree only — this is the leg that makes leg 1 fixable)
#
# Leg 1's answer is "redeploy". This leg asks what a redeploy would actually
# put in a stranger's hands. On 2026-08-24 the committed zip was itself four
# files stale against its own source — agent_loop.js, config.js, side_trip.js
# and supervised_read.js — while its manifest.json was byte-identical, so both
# reported 0.11.0. `staleExtension()` only speaks when Chrome is BEHIND a
# literal, so it could never notice.
#
# Deploying that zip would turn leg 1 green while shipping code nobody wrote.
# --------------------------------------------------------------------------
def leg_2_deployable_is_source(root: str = ROOT) -> str:
    src_version = source_version(root)
    found = zip_against_source(root, read_bytes(root, REPO_ZIP))
    note(f"{REPO_ZIP}: {found['version']}, {len(found['entries'])} file(s)")
    if found["version"] != src_version:
        raise LegFailed(
            f"{REPO_ZIP} packs {found['version'] or 'no version'} while "
            f"{MANIFEST} says {src_version}. Run `sh extension/build-zip.sh` — "
            "it refuses to emit a zip whose manifest disagrees with source, "
            "which is the one failure it exists to make impossible.")
    if found["orphaned"]:
        raise LegFailed(
            f"{REPO_ZIP} contains files that no longer exist in extension/: "
            + ", ".join(found["orphaned"][:8])
            + ". Rebuild it rather than editing it.")
    if found["differing"]:
        raise LegFailed(
            f"{REPO_ZIP} reports {found['version']} and does not CONTAIN "
            f"{found['version']}. {len(found['differing'])} file(s) differ from "
            "extension/: " + ", ".join(found["differing"][:8])
            + ".\n        manifest.json is byte-identical, so the zip and the "
              "source agree on the number and disagree on the code — and "
              "staleExtension() compares numbers, so nothing in the product "
              "can see it. Deploying this would turn leg 1 green while handing "
              "the stranger code nobody wrote. `sh extension/build-zip.sh`, "
              "commit the result, then deploy.")
    if found["broken"]:
        raise LegFailed(
            f"{REPO_ZIP} is missing modules its own code imports: "
            + "; ".join(found["broken"][:6])
            + ". This is 2026-08-13 exactly: the MV3 service worker dies at "
              "load and every fresh install sits with no pair code.")
    return (f"{REPO_ZIP} is extension/ at {src_version}, "
            f"{len(found['entries'])} files, imports complete")


# --------------------------------------------------------------------------
# LEG 3 — A NUMBER FROM OUTSIDE NORTH AMERICA SURVIVES SIGN-UP
#         (tree — but it RUNS the shipped Swift, it does not read it)
#
# SMS is the only channel the product has outside the app. `AnticipySession
# .e164` normalises what a person typed, and it prepends "+1" to any bare
# 10-digit number. A stranger in London or Bangalore types their own number,
# sign-up succeeds, and a US number is written to their account. Nothing
# validates it, nothing tests deliverability, and no error appears anywhere —
# they simply never receive a single text for the rest of the week.
#
# This leg lifts the real function out of the real file and EXECUTES it, so it
# tests what ships rather than what a comment claims. A leg that grepped for
# `"+1"` would go green the day somebody moved the literal into a constant.
# --------------------------------------------------------------------------
LONDON_LOCAL = "2079460958"          # a real London landline, typed bare
LONDON_FULL = "+442079460958"        # the same number, fully qualified
DELHI_LOCAL = "07700900123"          # 11 digits, leading 0, not NANP


def _run_e164(root: str, cases: list[str]) -> dict:
    src = read(root, APP)
    fn = swift_span(src, r"^[ \t]*(?:nonisolated\s+)?func e164\(")
    if not fn:
        raise LegFailed(
            f"could not find `func e164` in {APP}, so the leg that proves a "
            "foreign number survives sign-up cannot be tested — which counts "
            "as failing. If normalisation moved, move this leg with it.")
    if not have("swift"):
        raise LegFailed(
            "cannot verify: `swift` is not on PATH, so the shipped "
            "normalisation cannot be executed. This leg refuses to fall back "
            "to reading the source for a `+1` literal — that check goes green "
            "the day the literal moves into a constant, while the stranger's "
            "number is still being rewritten. A leg that cannot be tested "
            "does not pass.")
    body = re.sub(r"^\s*nonisolated\s+", "", fn)
    program = body + "\nfor a in CommandLine.arguments.dropFirst() " \
                     "{ print(e164(a) ?? \"nil\") }\n"
    tmp = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".swift",
                                         delete=False) as f:
            f.write(program)
            tmp = f.name
        r = subprocess.run(["swift", tmp, *cases], capture_output=True,
                           text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise LegFailed("running the shipped e164() timed out after 5 minutes")
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    if r.returncode != 0:
        tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-4:]
        raise LegFailed(
            "the shipped e164() would not compile on its own: "
            + " / ".join(t.strip() for t in tail)
            + ". If it now depends on the session around it, this leg needs "
              "re-pointing — it must keep EXECUTING the real thing.")
    out = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    if len(out) != len(cases):
        raise LegFailed(
            f"expected {len(cases)} answers from e164() and got {len(out)}")
    return dict(zip(cases, out))


def leg_3_foreign_number(root: str = ROOT) -> str:
    got = _run_e164(root, [LONDON_LOCAL, LONDON_FULL, DELHI_LOCAL])
    note("  ".join(f"{k} -> {v}" for k, v in got.items()))

    london = got[LONDON_LOCAL]
    if london.startswith("+1"):
        raise LegFailed(
            f"e164({LONDON_LOCAL!r}) returns {london!r}. A stranger outside "
            "North America types their own ten-digit number, sign-up succeeds, "
            "and a US number is written to their account. SMS is the only "
            "channel the product has outside the app, so they receive nothing "
            "for the whole week and no error appears anywhere.\n"
            "        Returning nil for a bare local number is a legitimate fix "
            "— refusing to guess is honest. Guessing the United States is not.")

    delhi = got[DELHI_LOCAL]
    if delhi.startswith("+0"):
        raise LegFailed(
            f"e164({DELHI_LOCAL!r}) returns {delhi!r}. No country code in "
            "E.164 begins with 0, so this number cannot be dialled by anyone; "
            "Twilio rejects it and the failure reaches a print() on worker "
            "stdout and nowhere else. Same stranger, same silent week.")

    if got[LONDON_FULL] != LONDON_FULL:
        raise LegFailed(
            f"e164({LONDON_FULL!r}) returns {got[LONDON_FULL]!r} — a number "
            "the person typed IN FULL, with its country code, no longer "
            "survives normalisation. Refusing every foreign number is not a "
            "fix for guessing at them.")
    return (f"{LONDON_LOCAL} -> {london}, {DELHI_LOCAL} -> {delhi}, "
            f"and a fully-typed +44 survives")


# --------------------------------------------------------------------------
# LEG 4 — ONBOARDING BELONGS TO THE ACCOUNT, NOT TO THE PHONE
#
# `@AppStorage("hasOnboarded")` is device-global and nothing in the account
# lifecycle clears it. A cable install means the phone passed through somebody
# else's hands first — that is the ONLY way to install this app today — so the
# realistic case is: the installer opened it once to check it, and the
# stranger's sign-up lands them straight on the feed. They never see the mic
# primer, listening is never started, and she hears nothing all week. The four
# -step tour is then reachable only as "Replay the welcome tour", buried in
# Settings, which nobody knows to look for.
#
# Two shapes of fix both pass here: key the flag by account, or clear it when
# the account changes. Neither is guessed at — the leg reads which flag the App
# actually routes on and follows it to its declaration.
# --------------------------------------------------------------------------
def leg_4_onboarding_is_per_account(root: str = ROOT) -> str:
    src = read(root, APP)
    m = re.search(r"\}\s*else if (\w+)\s*\{\s*\n\s*HomeView\(\)", src)
    if not m:
        raise LegFailed(
            f"{APP} no longer routes to HomeView on a single onboarding flag, "
            "so this leg cannot find what to follow — which counts as failing. "
            "Re-point it at whatever now decides that a signed-in person skips "
            "the tour.")
    flag = m.group(1)
    key = swift_appstorage_key(src, flag)
    if not key:
        raise LegFailed(
            f"{APP} routes on `{flag}` but this leg cannot find its "
            "@AppStorage declaration, so it cannot tell whether the flag "
            "belongs to the account or to the phone. Re-point the leg.")
    if not re.fullmatch(r'"[^"$\\]*"', key):
        return (f"the onboarding flag `{flag}` is stored under {key} — a key "
                "that is not a device-global constant")

    literal = key.strip('"')
    lifecycle = ""
    for sig in (r"^[ \t]*func signOut\(", r"^[ \t]*func signIn\(",
                r"^[ \t]*func createAccount\("):
        lifecycle += swift_span(src, sig)
    if not lifecycle:
        raise LegFailed(
            f"{APP} has no signOut/signIn/createAccount for this leg to read, "
            "so it cannot tell whether a change of account clears the "
            "onboarding flag. Re-point the leg at the account lifecycle.")
    if key in lifecycle or literal in lifecycle:
        return (f"`{flag}` is stored under {key} but the account lifecycle "
                "clears it, so a new account still sees the tour")

    raise LegFailed(
        f"`{flag}` is stored under {key} — one value for the whole PHONE, and "
        "nothing in signOut, signIn or createAccount clears it. A stranger "
        "handed a phone anybody has opened this app on before signs up and "
        "lands straight on the feed: no microphone primer, so listening is "
        "never started and she hears nothing all week. The tour survives only "
        "as \"Replay the welcome tour\" in Settings, which nobody knows to "
        "look for.\n"
        "        Cable install is the only way onto a device today "
        f"({WALKTHROUGH} Step 0), so the phone having a previous owner is the "
        "normal case, not the edge one. Fix by keying the flag to the account "
        f"id, or by clearing {key} when the account changes.")


# --------------------------------------------------------------------------
# LEG 5 — ENROLLMENT IS OFFERED, NOT MERELY FINDABLE
#
# VoiceEnrollView is complete, its 26MB model ships in every build, and the
# whole app presents it from exactly one place: a sheet inside Settings, under
# "Your voice", below Listening / Pendant / You. Nothing ever suggests it.
#
# The consequence is measured, not speculated: `research/2026-08-24-engine-
# options.md:254` records `speaker` at 0% across 221 events, cause "enrollment
# unreachable", confidence "Certain." With no owner profile the tagger returns
# nil and every line anyone says is attributed to nobody — which is the named
# cause of four of the six bad acts on the only call ever scored.
#
# The planned fix is EnrollmentInvite.swift plus an onboarding page (Task 4 of
# docs/superpowers/plans/2026-08-24-voice-capture.md, still unlanded). This leg
# accepts either the invite or a direct presentation from first run.
# --------------------------------------------------------------------------
FIRST_RUN = (ONBOARDING, FINALE)


def leg_5_enrollment_offered(root: str = ROOT) -> str:
    read(root, ENROLL)                       # exists, or the leg is untestable
    if not os.path.exists(os.path.join(root, SPEAKER_MODEL)):
        raise LegFailed(
            f"{SPEAKER_MODEL} is not in this tree. Offering enrollment without "
            "the model behind it would give the stranger a twelve-second read "
            "that can never produce a profile.")

    views = os.path.join(root, "app", "ios", "Anticipy")
    sites = []
    for dirpath, dirnames, filenames in os.walk(views):
        dirnames[:] = [d for d in dirnames
                       if d not in ("build", "DerivedData")
                       and not d.endswith(".xcarchive")]
        for fn in sorted(filenames):
            if not fn.endswith(".swift"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            if rel == ENROLL:
                continue
            with open(os.path.join(dirpath, fn), encoding="utf-8",
                      errors="replace") as f:
                if "VoiceEnrollView" in f.read():
                    sites.append(rel)
    note(f"presentation sites: {sites or 'none'}")
    if not sites:
        raise LegFailed(
            f"{ENROLL} exists and NOTHING in the app presents it. The model "
            "ships in every build and can never be reached.")

    first_run_text = "".join(read(root, rel) for rel in FIRST_RUN
                             if os.path.exists(os.path.join(root, rel)))
    if not first_run_text:
        raise LegFailed(
            "neither " + " nor ".join(FIRST_RUN) + " is in this tree, so this "
            "leg cannot tell what first run offers. Re-point it.")

    for rel in sites:
        if rel in FIRST_RUN:
            return f"first run presents enrollment directly ({rel})"
        # One hop: an invite view that first run puts on screen.
        type_name = os.path.basename(rel)[:-len(".swift")]
        if re.search(rf"\b{re.escape(type_name)}\b", first_run_text):
            return (f"first run offers enrollment through {type_name} "
                    f"({rel})")

    raise LegFailed(
        "enrollment has " + ("one presentation site" if len(sites) == 1
                             else f"{len(sites)} presentation sites")
        + " and first run is not among them: " + ", ".join(sites)
        + ".\n        To reach it a stranger must, with nobody suggesting it, "
          "tap the slider glyph in the Home toolbar and scroll past Listening, "
          "Pendant and You. Nobody does. That is why `speaker` is 0% across "
          "221 production events with the cause recorded as \"enrollment "
          "unreachable\" — mechanical, not mysterious, and the named cause of "
          "four of six bad acts on the only call ever scored.\n"
          "        Land the invite: EnrollmentInvite.swift plus an onboarding "
          "page (Task 4 of docs/superpowers/plans/2026-08-24-voice-capture.md). "
          "This leg passes when " + " or ".join(FIRST_RUN) + " presents "
          "VoiceEnrollView, directly or through a view it puts on screen.")


# --------------------------------------------------------------------------
# LEG 6 — THE PRODUCT'S FIRST WORDS CANNOT ARRIVE AT 1AM
#
# `maybe_welcome_new_owner` is the very first text a stranger ever receives.
# It is called from a 60-second polling beat and consults no clock. Every other
# lane in worker.py honours CLOCK_QUIET_START/END — the night digest, the clock
# lane, the nudges — and this one, the only one that fires for somebody who has
# never heard from her before, does not.
#
# People set up new things late at night. The first thing this product would
# ever say to a stranger can be a phone buzz at 1am, which is exactly the
# "makes them say WHAT?" failure the definition of done forbids.
# --------------------------------------------------------------------------
def leg_6_welcome_respects_the_night(root: str = ROOT) -> str:
    src = read(root, WORKER)
    if "CLOCK_QUIET_START" not in src:
        raise LegFailed(
            f"{WORKER} no longer declares CLOCK_QUIET_START, so this leg "
            "cannot tell what quiet hours are — which counts as failing. If "
            "the constants were renamed, re-point this leg.")
    body = py_def(src, "maybe_welcome_new_owner")
    if not body:
        raise LegFailed(
            f"{WORKER} has no top-level `maybe_welcome_new_owner`, so the "
            "first text a stranger receives cannot be found and this leg "
            "cannot be tested. Re-point it at whatever sends the welcome.")
    if "CLOCK_QUIET" in body:
        return "the welcome consults quiet hours before it speaks"

    # A guard at the call site is accepted, but only when it demonstrably
    # ENCLOSES the call: on the call's own line, or within three lines above it
    # at a strictly shallower indent, which in Python means the call is inside
    # it. worker.py consults CLOCK_QUIET in eight places, and the first draft of
    # this leg accepted any of them within twelve lines — the mutation test in
    # tests/test_stranger_gate.py caught it going green on a night-digest check
    # thirty lines away. That is how a leg in this repo came to be satisfied by
    # a guard three lines above the sentence it meant to read.
    lines = src.splitlines()
    for m in re.finditer(r"^([ \t]*)(?!def )[^\n]*maybe_welcome_new_owner\(",
                         src, re.M):
        call_indent = len(m.group(1))
        line_no = src.count("\n", 0, m.start())
        if "CLOCK_QUIET" in lines[line_no]:
            return f"the welcome is held outside quiet hours on the call itself"
        for k in range(max(0, line_no - 3), line_no):
            row = lines[k]
            if "CLOCK_QUIET" not in row:
                continue
            if len(row) - len(row.lstrip()) < call_indent:
                return ("the call to the welcome sits inside a quiet-hours "
                        f"guard ({WORKER}:{k + 1})")

    raise LegFailed(
        "the very first text a stranger ever receives consults no clock. "
        "`maybe_welcome_new_owner` runs off the 60-second profile beat, and "
        "worker.py honours CLOCK_QUIET_START/END in the night digest, the "
        "clock lane and the nudges — everywhere except the one message that "
        "goes to somebody who has never heard from her before.\n"
        "        A stranger who finishes onboarding at 1am, which is when "
        "people set up new things, gets the product's first ever words as a "
        "phone buzz in the middle of the night.\n"
        "        Put the guard INSIDE maybe_welcome_new_owner, next to its "
        "other two guardrails (young profile, one durable stamp per number), "
        "or immediately on the call. A held welcome must still be sent in the "
        "morning — dropping it silently trades one bad first impression for "
        "no first impression at all.")


# --------------------------------------------------------------------------
# LEG 7 — WHAT THE SERVER VERIFIED IS WHAT THE PERSON READS
#
# `workflow_guard.pb.js` refuses any transition to `done` unless the job
# carries a receipt with verified === true, a matching effect_key, and a
# non-empty evidence array. The column exists, the migration adds it, and the
# server enforces it on every single completion.
#
# The app never decodes it. `AgentJob` stops at `lane`, and the done card feeds
# `job.result` — free text the browser happened to write — into
# JobReceiptPolicy. So the structured, server-enforced evidence exists in the
# database and the stranger never sees a byte of it; what they see is whatever
# sentence the extension composed. That is the difference between a receipt and
# a claim, on the one card whose entire job is to be a receipt.
# --------------------------------------------------------------------------
def leg_7_receipt_is_what_is_shown(root: str = ROOT) -> str:
    guard = read(root, GUARD)
    if "receipt.verified" not in guard.replace("!receipt.verified",
                                               "receipt.verified"):
        raise LegFailed(
            f"{GUARD} no longer demands a verified receipt before a job may go "
            "done, so the column this leg tracks may no longer be the record "
            "of truth. Re-point the leg — do not delete it. The alternative is "
            "the app rendering the browser's own prose as evidence again.")

    swift = read(root, BACKEND_SWIFT)
    struct = swift_span(swift, r"^struct AgentJob\b")
    if not struct:
        raise LegFailed(
            f"{BACKEND_SWIFT} has no `struct AgentJob`, so this leg cannot "
            "tell what the app decodes. Re-point it.")
    if not re.search(r"^\s*(?:let|var)\s+receipt\b", struct, re.M):
        raise LegFailed(
            "the backend refuses to mark ANY job done without a receipt whose "
            "`verified` is true and whose `evidence` is non-empty — and "
            "`AgentJob` never decodes the column. The app writes `\"receipt\": "
            "\"\"` on approve and cancel and never reads it back.\n"
            "        So the done card renders `result`, which is free text the "
            "extension composed, while the evidence the server actually "
            "checked sits unread in the row. The stranger cannot tell a "
            "receipt from a sentence, which is the whole promise of the card.\n"
            f"        Add `let receipt: String?` to AgentJob in {BACKEND_SWIFT} "
            "and render it.")

    content = read(root, CONTENT)
    i = content.find("JobReceiptPolicy.doneCard(")
    if i < 0:
        raise LegFailed(
            f"{CONTENT} no longer builds the done card through "
            "JobReceiptPolicy.doneCard, so this leg cannot see what it is fed. "
            "Re-point it at the new render site.")
    call = content[i:i + 400]
    if "receipt" not in call:
        raise LegFailed(
            "AgentJob decodes `receipt` and the done card is still fed only "
            f"`result`: {call.splitlines()[0].strip()!r}. Decoding a column "
            "nothing renders changes nothing a stranger can see — the card "
            "still leads with whatever sentence the browser wrote.")
    return "the server-verified receipt is decoded and reaches the done card"


# --------------------------------------------------------------------------
# LEG 8 — THE DONE-TEXT CAN CARRY THE PHOTO IT PROMISES
#
# WIRE IT ALL's verify loop is act -> evidence -> done-text WITH PHOTO. There
# is no photo. `VoiceArm.text` posts From, To and Body; `MediaUrl` appears
# nowhere in any .py, .js or .swift in this repository.
#
# The anchor here is not a name this gate invented: MediaUrl is Twilio's own
# parameter, and it is the only way an image reaches a phone over the channel
# this product uses. Evidence exists browser-side and server-side as URLs in
# receipt.evidence; it reaches neither the text nor the app.
# --------------------------------------------------------------------------
def leg_8_done_text_can_carry_the_photo(root: str = ROOT) -> str:
    src = read(root, VOICE_ARM)
    if "Messages.json" not in src:
        raise LegFailed(
            f"{VOICE_ARM} no longer posts to Twilio's Messages.json, so this "
            "leg cannot find the send it is about. Re-point it.")
    body = py_def(src, "text")
    if not body or "Messages.json" not in body:
        raise LegFailed(
            f"{VOICE_ARM} has no `text(` method that posts to Messages.json, "
            "so this leg cannot see what an outgoing text carries — which "
            "counts as failing. Re-point it at whatever sends an SMS now.")
    if "MediaUrl" not in body:
        raise LegFailed(
            "the outgoing text has no way to carry a picture. "
            f"{VOICE_ARM}'s text() posts From, To and Body and nothing else, "
            "and `MediaUrl` — Twilio's own parameter, the only way an image "
            "reaches a phone on this channel — appears in no .py, .js or "
            ".swift in the repository.\n"
            "        WIRE IT ALL step 1 describes the loop as act -> evidence "
            "-> done-text WITH PHOTO. Two of those three exist: the browser "
            "captures evidence and workflow_guard.pb.js refuses `done` without "
            "it, as URLs in receipt.evidence. Nothing carries them onward, so "
            "the stranger's confirmation is a sentence about a screenshot they "
            "will never see.\n"
            "        This leg asks only that the parameter be plumbed. Whether "
            "the picture is the right one is a human's judgement, not a gate's.")
    return "the outgoing text can carry the evidence picture"


# --------------------------------------------------------------------------
# LEG 9 — THE INSTALL GUIDE NAMES SCREENS THAT EXIST
#         *** the live half of this leg reads production ***
#
# `setup.html` is the only guide in the product, and a stranger reads it while
# doing the five-minute Chrome ceremony. Step 5 tells them: "Still setting the
# app up? You're already on the right screen — the one headed 'Your hands on
# the computer.'" That screen was DELETED when the browser left first run;
# onboarding is four beats and none of them is it. The same page then says to
# find "Browser agent" in Settings; the section is called "Your computer".
#
# A stranger following correct instructions concludes they have broken
# something. This is held the way tape_gate holds the audited five: BY NAME,
# because a leg that tried to detect dead pointers in prose by pattern would
# match nothing and pass in silence. Each name is cross-checked against the app
# on every run, so re-introducing the screen retires the item honestly.
# --------------------------------------------------------------------------
DEAD_POINTERS = (
    ("Your hands on the computer", ONBOARDING,
     "a first-run screen deleted when the browser left first run"),
    ("Browser agent", SETTINGS,
     'a Settings section since renamed to "Your computer"'),
)
GUIDE_FILES = (SETUP_PAGE, EXT_ONBOARDING)


def _app_names(root: str) -> tuple[set, str]:
    """Every name first run and Settings actually put on screen, read out of the
    app so this leg updates itself when the app is renamed."""
    onb = read(root, ONBOARDING)
    m = re.search(r"beatNames\s*=\s*\[([^\]]*)\]", onb)
    if not m:
        raise LegFailed(
            f"{ONBOARDING} no longer declares `beatNames`, so this leg cannot "
            "read what first run's screens are called and cannot tell a dead "
            "pointer from a live one. Re-point it.")
    names = set(re.findall(r'"([^"]*)"', m.group(1)))
    settings = read(root, SETTINGS)
    sections = set(re.findall(r'Section\("([^"]*)"\)', settings))
    if not sections:
        raise LegFailed(
            f"{SETTINGS} no longer declares any `Section(\"...\")`, so this "
            "leg cannot read what Settings' sections are called. Re-point it.")
    return names | sections, ", ".join(sorted(names))


def leg_9_guide_names_real_screens(root: str = ROOT, fetch=None,
                                   base: str = "") -> str:
    fetch = fetch or http_get
    base = (base or BASE).rstrip("/")
    on_screen, beats = _app_names(root)

    bad = []
    for rel in GUIDE_FILES:
        if not os.path.exists(os.path.join(root, rel)):
            continue
        text = read(root, rel)
        for phrase, home, what in DEAD_POINTERS:
            if phrase in text and phrase not in on_screen:
                bad.append(f"{rel} sends the stranger to “{phrase}” "
                           f"— {what}, and no longer anywhere in {home}")

    url = f"{base}/setup.html"
    try:
        live = fetch(url).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        raise LegFailed(
            f"cannot verify the deployed guide: {url} did not answer "
            f"({str(e)[:80]}). The page a stranger actually reads is the live "
            "one, so this leg fails rather than settling for the tree. "
            + ("The tree is wrong too: " + bad[0] if bad else
               "The copy in the tree is clean."))
    for phrase, home, what in DEAD_POINTERS:
        if phrase in live and phrase not in on_screen:
            bad.append(f"the DEPLOYED {url} sends the stranger to "
                       f"“{phrase}” — {what}, and no longer anywhere "
                       f"in {home}")

    if bad:
        raise LegFailed(
            "the install guide points at things that are not in the app:\n"
            "        - " + "\n        - ".join(bad)
            + f"\n        First run is four beats: {beats}. A stranger "
              "mid-onboarding reads “you're already on the right "
              "screen”, looks at a screen asking for their phone number, "
              "and concludes they have done something wrong — while holding "
              "the six-digit code that pairs the only executor in the product."
              "\n        Fix the guide (or bring the screen back); then deploy "
              "pb_public, because the live half of this leg reads production.")
    return (f"the guide names only screens the app has; first run is: {beats}")


# --------------------------------------------------------------------------

LEGS = [
    (1, "THE HANDS ARE DOWNLOADABLE", "LIVE", leg_1_hands_downloadable),
    (2, "A DEPLOY WOULD SHIP THE SOURCE", "tree", leg_2_deployable_is_source),
    (3, "A FOREIGN NUMBER SURVIVES SIGN-UP", "runs", leg_3_foreign_number),
    (4, "ONBOARDING BELONGS TO THE ACCOUNT", "tree",
     leg_4_onboarding_is_per_account),
    (5, "ENROLLMENT IS OFFERED", "tree", leg_5_enrollment_offered),
    (6, "THE FIRST WORDS RESPECT THE NIGHT", "tree",
     leg_6_welcome_respects_the_night),
    (7, "THE VERIFIED RECEIPT IS WHAT IS SHOWN", "tree",
     leg_7_receipt_is_what_is_shown),
    (8, "THE DONE-TEXT CAN CARRY THE PHOTO", "tree",
     leg_8_done_text_can_carry_the_photo),
    (9, "THE GUIDE NAMES SCREENS THAT EXIST", "LIVE",
     leg_9_guide_names_real_screens),
]


def main() -> int:
    print()
    print(f"  STRANGER GATE   tree: {ROOT}")
    print(f"                  live: {BASE}")
    print(f"                  from: {WALKTHROUGH}")
    print("  " + "-" * 66)
    first = None
    for num, name, where, fn in LEGS:
        try:
            detail = fn()
            print(f"  [{num}] PASS  {name}  ({where})")
            print(f"        {detail}")
        except LegFailed as e:
            mark = "FAIL" if first is None else "fail"
            print(f"  [{num}] {mark}  {name}  ({where})")
            print(f"        {e}")
            if first is None:
                first = (num, name, str(e))
        except Exception as e:  # noqa: BLE001
            print(f"  [{num}] FAIL  {name}  ({where})")
            print(f"        gate itself errored: {e}")
            if first is None:
                first = (num, name, f"gate errored: {e}")
    print("  " + "-" * 66)
    if first is None:
        print("  READY — every prerequisite a machine can check is standing.")
        print("  That is NOT done. done_gate.py leg 6 still needs a real person")
        print("  on their own accounts, carried through a real day.")
    else:
        num, name, _ = first
        print(f"  NOT READY FOR A STRANGER — first failing leg: {num} ({name})")
        print("  Fix this before spending somebody's week discovering it.")
    print()
    print("  What this gate cannot see: everything that needs a device and a")
    print("  person — whether the cable install succeeds at all, whether the")
    print("  provisioning profile outlives the week, whether the Twilio account")
    print("  is trial (unverified numbers fail silently on one), and whether")
    print("  the worker in production is this worker. Four of the nine dead")
    print("  ends are deliberately unpinned; the reasons are in")
    print("  research/2026-08-24-stranger-gate.md.")
    print()
    return 1 if first else 0


if __name__ == "__main__":
    sys.exit(main())
