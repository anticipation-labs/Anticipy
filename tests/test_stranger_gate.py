"""MUTATION TESTS FOR THE STRANGER GATE (overnight/stranger_gate.py).

A gate leg nobody has watched fail is not a gate leg — and a leg nobody has
watched PASS is worse, because it is indistinguishable from a leg that cannot
be satisfied. On 2026-08-24 four rules in this repo were caught passing by
matching nothing, one of them satisfied by a guard three lines above the
sentence it meant to read.

So every leg here is driven both ways against a synthetic tree in a tmpdir:
made bad, watched go red; made good, watched go green. Where a leg has more
than one shape of fix (leg 4 accepts either an account-scoped key or a clear on
sign-out; leg 5 accepts either a direct presentation or an invite view), each
shape gets its own green.

These tests assert the MECHANISM, never the repo's current state. The real tree
is red on all nine legs today and should be; a test that pinned that would go
red the day somebody fixes one, which punishes the fix.

2026-08-25. Being watched both ways was not enough. A review drove five of the
nine legs GREEN without changing any behaviour — a `# TODO` comment, a `# NOTE`
comment, a key literal moved into a constant, a comment naming a file, a
sentence 200 characters past a call — and one leg RED on a correct repair. One
defect, six times: the leg searched for a TOKEN instead of establishing the
BEHAVIOUR, and prose about the bug contains the token. The section
"THE 2026-08-25 REVIEW — TOKEN VERSUS BEHAVIOUR" below is that review's exact
mutations, each pinned so the fix cannot come undone; the greens beside them
are the correct repairs the fixed legs must not block.

Run:  python3 -m pytest -q tests/test_stranger_gate.py
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "stranger_gate", os.path.join(ROOT, "overnight", "stranger_gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sg = _load()
HAVE_SWIFT = sg.have("swift")


# --------------------------------------------------------------------------
# A synthetic tree. Only the files a given leg reads are written, so a test
# that starts failing points at the leg rather than at repo churn.
# --------------------------------------------------------------------------
def write(root: str, rel: str, text) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(text, bytes) else "w"
    with open(path, mode, **({} if isinstance(text, bytes)
                             else {"encoding": "utf-8"})) as f:
        f.write(text)


def zip_of(root: str, names) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in names:
            with open(os.path.join(root, "extension", name), "rb") as f:
                z.writestr(name, f.read())
    return buf.getvalue()


def fetch_of(blob: bytes):
    return lambda url: blob


def fails(fn, *a, **kw) -> str:
    with pytest.raises(sg.LegFailed) as e:
        fn(*a, **kw)
    return str(e.value)


# ==========================================================================
# LEG 1 — THE HANDS ARE DOWNLOADABLE  (LIVE)
# ==========================================================================
EXT_FILES = ("manifest.json", "background.js", "agent_loop.js", "popup.html",
             "icons/icon16.png")


def manifest_of(version: str) -> str:
    """A manifest with the entry points Chrome actually loads, because that is
    what `sg.source_closure` follows to work out what a complete package
    contains. A manifest naming nothing is a tree the leg refuses to judge."""
    return json.dumps({
        "name": "Anticipy", "version": version,
        "background": {"service_worker": "background.js", "type": "module"},
        "action": {"default_popup": "popup.html"},
        "icons": {"16": "icons/icon16.png"}})


def extension_tree(tmp_path, version="1.2.3", pin=None) -> str:
    root = str(tmp_path)
    write(root, "extension/manifest.json", manifest_of(version))
    write(root, "extension/background.js",
          'import { run } from "./agent_loop.js";\nrun();\n')
    write(root, "extension/agent_loop.js", "export function run() {}\n")
    write(root, "extension/popup.html", "<html><body>hi</body></html>\n")
    write(root, "extension/icons/icon16.png", b"\x89PNG-not-really")
    write(root, sg.APP,
          '    static let expectedExtensionVersion = "%s"\n'
          % (pin if pin is not None else version))
    return root


def test_leg1_green_when_the_download_is_the_source(tmp_path):
    root = extension_tree(tmp_path)
    blob = zip_of(root, EXT_FILES)
    detail = sg.leg_1_hands_downloadable(root, fetch=fetch_of(blob),
                                         base="http://gate.test")
    assert "1.2.3" in detail


def test_leg1_red_when_the_served_version_is_behind_the_banner(tmp_path):
    root = extension_tree(tmp_path)
    blob = zip_of(root, EXT_FILES)
    write(root, "extension/manifest.json", manifest_of("9.9.9"))
    write(root, sg.APP,
          '    static let expectedExtensionVersion = "9.9.9"\n')
    why = fails(sg.leg_1_hands_downloadable, root, fetch=fetch_of(blob),
                base="http://gate.test")
    assert "press Reload to get 9.9.9" in why and "serves 1.2.3" in why


def test_leg1_red_when_the_version_matches_but_the_code_does_not(tmp_path):
    """The 0.8.2 failure: the number agreed and the bytes did not."""
    root = extension_tree(tmp_path)
    blob = zip_of(root, EXT_FILES)
    write(root, "extension/agent_loop.js",
          "export function run() { /* today's fix */ }\n")
    why = fails(sg.leg_1_hands_downloadable, root, fetch=fetch_of(blob),
                base="http://gate.test")
    assert "agent_loop.js" in why and "byte for byte" in why


def test_leg1_red_when_the_package_is_missing_a_module_it_imports(tmp_path):
    """2026-08-13: workflow_state.js left out, service worker dead at load."""
    root = extension_tree(tmp_path)
    blob = zip_of(root, ("manifest.json", "background.js", "popup.html",
                         "icons/icon16.png"))
    why = fails(sg.leg_1_hands_downloadable, root, fetch=fetch_of(blob),
                base="http://gate.test")
    assert "agent_loop.js" in why


def test_leg1_red_when_the_pin_has_rotted_behind_the_source(tmp_path):
    root = extension_tree(tmp_path, version="1.2.3", pin="1.0.0")
    blob = zip_of(root, EXT_FILES)
    write(root, "extension/manifest.json", manifest_of("1.0.0"))
    blob = zip_of(root, EXT_FILES)          # served == pin, source moved on
    write(root, "extension/manifest.json", manifest_of("1.2.3"))
    why = fails(sg.leg_1_hands_downloadable, root, fetch=fetch_of(blob),
                base="http://gate.test")
    assert "no banner at all" in why


def test_leg1_red_when_production_cannot_be_reached(tmp_path):
    """A leg that cannot be tested does not pass — least of all the LIVE one."""
    root = extension_tree(tmp_path)

    def boom(url):
        raise OSError("connection refused")

    why = fails(sg.leg_1_hands_downloadable, root, fetch=boom,
                base="http://gate.test")
    assert "cannot verify" in why and "fails rather than passing" in why


def test_leg1_red_when_the_app_no_longer_declares_a_pin(tmp_path):
    root = extension_tree(tmp_path)
    blob = zip_of(root, EXT_FILES)
    write(root, sg.APP, "// the constant was renamed and nobody said so\n")
    why = fails(sg.leg_1_hands_downloadable, root, fetch=fetch_of(blob),
                base="http://gate.test")
    assert "expectedExtensionVersion" in why


# ==========================================================================
# LEG 2 — A DEPLOY WOULD SHIP THE SOURCE
# ==========================================================================
def test_leg2_green_when_the_committed_zip_is_the_source(tmp_path):
    root = extension_tree(tmp_path)
    write(root, sg.REPO_ZIP, zip_of(root, EXT_FILES))
    assert "1.2.3" in sg.leg_2_deployable_is_source(root)


def test_leg2_red_when_the_zip_is_stale_against_its_own_source(tmp_path):
    """The two-layer staleness: manifest identical, code four files behind."""
    root = extension_tree(tmp_path)
    write(root, sg.REPO_ZIP, zip_of(root, EXT_FILES))
    write(root, "extension/agent_loop.js", "export function run() { fixed(); }\n")
    why = fails(sg.leg_2_deployable_is_source, root)
    assert "does not CONTAIN 1.2.3" in why and "agent_loop.js" in why


def test_leg2_red_when_there_is_no_committed_zip_at_all(tmp_path):
    root = extension_tree(tmp_path)
    why = fails(sg.leg_2_deployable_is_source, root)
    assert "cannot be tested" in why


# ==========================================================================
# LEG 3 — A FOREIGN NUMBER SURVIVES SIGN-UP  (runs the shipped Swift)
# ==========================================================================
SHIPPED_E164 = '''\
    nonisolated func e164(_ raw: String) -> String? {
        let digits = raw.filter(\\.isNumber)
        guard digits.count >= 10 else { return nil }
        if raw.hasPrefix("+") { return "+" + digits }
        if digits.count == 10 { return "+1" + digits }        // NANP local
        if digits.count == 11, digits.hasPrefix("1") { return "+" + digits }
        return "+" + digits
    }
'''

FIXED_E164 = '''\
    nonisolated func e164(_ raw: String) -> String? {
        let digits = raw.filter(\\.isNumber)
        guard digits.count >= 10 else { return nil }
        if raw.hasPrefix("+") { return "+" + digits }
        // We do not know their country, so we do not guess at it.
        return nil
    }
'''

REFUSES_EVERYTHING = '''\
    nonisolated func e164(_ raw: String) -> String? {
        return nil
    }
'''

STILL_PLUS_ZERO = '''\
    nonisolated func e164(_ raw: String) -> String? {
        let digits = raw.filter(\\.isNumber)
        guard digits.count >= 10 else { return nil }
        if raw.hasPrefix("+") { return "+" + digits }
        if digits.count == 10 { return nil }
        return "+" + digits
    }
'''


@pytest.mark.skipif(not HAVE_SWIFT, reason="swift is not on PATH")
def test_leg3_red_on_the_shipped_normalisation(tmp_path):
    root = str(tmp_path)
    write(root, sg.APP, SHIPPED_E164)
    why = fails(sg.leg_3_foreign_number, root)
    assert "'+12079460958'" in why and "never receive" not in why
    assert "United States" in why


@pytest.mark.skipif(not HAVE_SWIFT, reason="swift is not on PATH")
def test_leg3_green_when_it_refuses_to_guess_a_country(tmp_path):
    root = str(tmp_path)
    write(root, sg.APP, FIXED_E164)
    assert "+44" in sg.leg_3_foreign_number(root)


@pytest.mark.skipif(not HAVE_SWIFT, reason="swift is not on PATH")
def test_leg3_red_when_a_plus_zero_number_still_comes_out(tmp_path):
    root = str(tmp_path)
    write(root, sg.APP, STILL_PLUS_ZERO)
    why = fails(sg.leg_3_foreign_number, root)
    assert "'+07700900123'" in why and "begins with 0" in why


@pytest.mark.skipif(not HAVE_SWIFT, reason="swift is not on PATH")
def test_leg3_red_when_the_fix_is_to_refuse_every_foreign_number(tmp_path):
    """Refusing everything is not a fix for guessing — it is the same week."""
    root = str(tmp_path)
    write(root, sg.APP, REFUSES_EVERYTHING)
    why = fails(sg.leg_3_foreign_number, root)
    assert "typed IN FULL" in why


def test_leg3_red_when_the_function_is_gone(tmp_path):
    root = str(tmp_path)
    write(root, sg.APP, "// normalisation moved somewhere and nobody said so\n")
    why = fails(sg.leg_3_foreign_number, root)
    assert "cannot be tested" in why


# ==========================================================================
# LEG 4 — ONBOARDING BELONGS TO THE ACCOUNT
# ==========================================================================
def app_swift(decl: str, sign_out_body: str = "        authToken = \"\"\n"
              ) -> str:
    return ('@main\nstruct AnticipyApp: App {\n'
            f'{decl}'
            '    var body: some Scene {\n'
            '        WindowGroup {\n'
            '            Group {\n'
            '                if !session.isSignedIn {\n'
            '                    AuthView()\n'
            '                } else if hasOnboarded {\n'
            '                    HomeView()\n'
            '                } else {\n'
            '                    OnboardingView(onFinished: {})\n'
            '                }\n'
            '            }\n'
            '        }\n'
            '    }\n'
            '}\n\n'
            '    func signOut() {\n'
            f'{sign_out_body}'
            '        listener.stop()\n'
            '    }\n'
            '    func signIn(email: String) async -> String? { return nil }\n'
            '    func createAccount(email: String) async -> String? '
            '{ return nil }\n')


BARE = '    @AppStorage("hasOnboarded") private var hasOnboarded = false\n'
SCOPED = ('    @AppStorage("hasOnboarded-\\(accountID)") '
          'private var hasOnboarded = false\n')


def test_leg4_red_when_the_flag_is_one_value_for_the_whole_phone(tmp_path):
    root = str(tmp_path)
    write(root, sg.APP, app_swift(BARE))
    why = fails(sg.leg_4_onboarding_is_per_account, root)
    assert "one value for the whole PHONE" in why
    assert "hears nothing all week" in why


def test_leg4_green_when_the_key_is_scoped_to_the_account(tmp_path):
    root = str(tmp_path)
    write(root, sg.APP, app_swift(SCOPED))
    assert "not one string for the whole phone" in \
        sg.leg_4_onboarding_is_per_account(root)


def test_leg4_green_when_signing_out_clears_it(tmp_path):
    root = str(tmp_path)
    write(root, sg.APP, app_swift(
        BARE,
        sign_out_body='        authToken = ""\n'
                      '        UserDefaults.standard'
                      '.removeObject(forKey: "hasOnboarded")\n'))
    assert "clears it" in sg.leg_4_onboarding_is_per_account(root)


def test_leg4_is_not_satisfied_by_the_replay_button_in_settings(tmp_path):
    """SettingsView already writes `hasOnboarded = false` for "Replay the
    welcome tour". That is not an account boundary, and a leg that read the
    whole app rather than the lifecycle would have gone green on it."""
    root = str(tmp_path)
    write(root, sg.APP, app_swift(BARE))
    write(root, sg.SETTINGS,
          '@AppStorage("hasOnboarded") private var hasOnboarded = false\n'
          'Button("Replay it") { hasOnboarded = false }\n')
    why = fails(sg.leg_4_onboarding_is_per_account, root)
    assert "one value for the whole PHONE" in why


def test_leg4_red_when_the_routing_branch_cannot_be_found(tmp_path):
    root = str(tmp_path)
    write(root, sg.APP, "// routing was rewritten\n")
    why = fails(sg.leg_4_onboarding_is_per_account, root)
    assert "cannot find what to follow" in why


# ==========================================================================
# LEG 5 — ENROLLMENT IS OFFERED
# ==========================================================================
def enroll_tree(tmp_path, sites: dict) -> str:
    root = str(tmp_path)
    write(root, sg.ENROLL, "struct VoiceEnrollView: View { }\n")
    write(root, sg.SPEAKER_MODEL, b"onnx")
    write(root, sg.ONBOARDING,
          'private static let beatNames = ["Hello"]\n')
    write(root, sg.FINALE, "struct OnboardingFinale: View { }\n")
    write(root, sg.SETTINGS, "struct SettingsView: View { }\n")
    for rel, text in sites.items():
        write(root, rel, text)
    return root


def test_leg5_red_when_settings_is_the_only_door(tmp_path):
    root = enroll_tree(tmp_path, {
        sg.SETTINGS: 'Section("Your voice") { }\n'
                     '.sheet { VoiceEnrollView() }\n'})
    why = fails(sg.leg_5_enrollment_offered, root)
    assert "one presentation site" in why and "SettingsView.swift" in why


def test_leg5_green_when_first_run_presents_it_directly(tmp_path):
    root = enroll_tree(tmp_path, {
        sg.ONBOARDING: 'private static let beatNames = ["Hello"]\n'
                       '.sheet { VoiceEnrollView() }\n'})
    assert "directly" in sg.leg_5_enrollment_offered(root)


def test_leg5_green_when_first_run_offers_it_through_an_invite(tmp_path):
    root = enroll_tree(tmp_path, {
        "app/ios/Anticipy/Views/EnrollmentInvite.swift":
            "struct EnrollmentInvite: View { VoiceEnrollView() }\n",
        sg.ONBOARDING: 'private static let beatNames = ["Hello"]\n'
                       'EnrollmentInvite()\n'})
    assert "EnrollmentInvite" in sg.leg_5_enrollment_offered(root)


def test_leg5_red_when_nothing_presents_it_at_all(tmp_path):
    root = enroll_tree(tmp_path, {})
    why = fails(sg.leg_5_enrollment_offered, root)
    assert "NOTHING in the app presents it" in why


def test_leg5_red_when_the_model_does_not_ship(tmp_path):
    root = enroll_tree(tmp_path, {
        sg.ONBOARDING: 'private static let beatNames = ["Hello"]\n'
                       'VoiceEnrollView()\n'})
    os.unlink(os.path.join(root, sg.SPEAKER_MODEL))
    why = fails(sg.leg_5_enrollment_offered, root)
    assert "never produce a profile" in why


# ==========================================================================
# LEG 6 — THE FIRST WORDS RESPECT THE NIGHT
# ==========================================================================
def worker_py(welcome_body: str, before_call: str = "",
              call_indent: int = 8, preamble: str = "") -> str:
    return ("import time\n\n"
            "CLOCK_QUIET_START, CLOCK_QUIET_END = 22, 8\n\n\n"
            + preamble
            + "def maybe_welcome_new_owner(anticipy, state, now=None):\n"
            f"{welcome_body}"
            "\n\ndef loop():\n"
            "    while True:\n"
            + before_call
            + " " * call_indent
            + "maybe_welcome_new_owner(anticipy, _clock_state())\n")


def test_leg6_red_when_the_welcome_consults_no_clock(tmp_path):
    root = str(tmp_path)
    write(root, sg.WORKER, worker_py("    return anticipy.notify_owner(hi)\n"))
    why = fails(sg.leg_6_welcome_respects_the_night, root)
    assert "consults no clock" in why and "1am" in why


def test_leg6_green_when_the_guard_is_inside_the_function(tmp_path):
    root = str(tmp_path)
    write(root, sg.WORKER, worker_py(
        "    if CLOCK_QUIET_START <= hour or hour < CLOCK_QUIET_END:\n"
        "        return False\n"
        "    return anticipy.notify_owner(hi)\n"))
    assert "before it speaks" in sg.leg_6_welcome_respects_the_night(root)


def test_leg6_green_when_an_enclosing_if_holds_the_call(tmp_path):
    root = str(tmp_path)
    write(root, sg.WORKER, worker_py(
        "    return anticipy.notify_owner(hi)\n",
        before_call="        if not (CLOCK_QUIET_START <= hour "
                    "or hour < CLOCK_QUIET_END):\n",
        call_indent=12))
    assert "inside a quiet-hours guard" in \
        sg.leg_6_welcome_respects_the_night(root)


def test_leg6_is_not_satisfied_by_a_quiet_check_far_above_the_call(tmp_path):
    """worker.py consults CLOCK_QUIET in eight places. A generous window finds
    one by accident — which is exactly how a leg in this repo came to be
    satisfied by a guard three lines above the sentence it meant to read. The
    first draft of this leg took a twelve-line window and went green here."""
    root = str(tmp_path)
    filler = "".join(f"        step_{i}()\n" for i in range(30))
    write(root, sg.WORKER, worker_py(
        "    return anticipy.notify_owner(hi)\n",
        before_call="        if CLOCK_QUIET_START <= hour: "
                    "night_digest()\n" + filler))
    why = fails(sg.leg_6_welcome_respects_the_night, root)
    assert "consults no clock" in why


def test_leg6_is_not_satisfied_by_a_sibling_quiet_check_beside_the_call(
        tmp_path):
    """A CLOCK_QUIET line at the SAME indent as the call is a statement next to
    it, not a guard around it. Three lines is close enough to look convincing,
    which is why the indent, not the distance, is what this leg reads."""
    root = str(tmp_path)
    write(root, sg.WORKER, worker_py(
        "    return anticipy.notify_owner(hi)\n",
        before_call="        if CLOCK_QUIET_START <= hour: night_digest()\n"
                    "        housekeeping()\n"))
    why = fails(sg.leg_6_welcome_respects_the_night, root)
    assert "consults no clock" in why


def test_leg6_red_when_quiet_hours_no_longer_exist(tmp_path):
    root = str(tmp_path)
    write(root, sg.WORKER, "def maybe_welcome_new_owner(a, s, now=None):\n"
                           "    pass\n")
    why = fails(sg.leg_6_welcome_respects_the_night, root)
    assert "cannot tell what quiet hours are" in why


def test_leg6_red_when_the_welcome_itself_is_gone(tmp_path):
    root = str(tmp_path)
    write(root, sg.WORKER, "CLOCK_QUIET_START, CLOCK_QUIET_END = 22, 8\n")
    why = fails(sg.leg_6_welcome_respects_the_night, root)
    assert "cannot be tested" in why


# ==========================================================================
# LEG 7 — THE VERIFIED RECEIPT IS WHAT IS SHOWN
# ==========================================================================
GUARD_JS = ('if (!receipt.verified || receipt.effect_key !== effect) '
            'return reject("done needs a receipt");\n')

JOB_WITHOUT = ('struct AgentJob: Decodable {\n'
               '    let id: String\n'
               '    let result: String?\n'
               '    let lane: String?\n'
               '}\n')
JOB_WITH = ('struct AgentJob: Decodable {\n'
            '    let id: String\n'
            '    let result: String?\n'
            '    let receipt: String?\n'
            '    let lane: String?\n'
            '}\n')
CARD_RESULT = ('let card = JobReceiptPolicy.doneCard(goal: job.humanGoal, '
               'result: job.result)\n')
CARD_RECEIPT = ('let card = JobReceiptPolicy.doneCard(goal: job.humanGoal, '
                'result: job.result, receipt: job.receipt)\n')


def receipt_tree(tmp_path, job: str, card: str, guard: str = GUARD_JS) -> str:
    root = str(tmp_path)
    write(root, sg.GUARD, guard)
    write(root, sg.BACKEND_SWIFT, job)
    write(root, sg.CONTENT, card)
    return root


def test_leg7_red_when_the_app_never_decodes_the_receipt(tmp_path):
    root = receipt_tree(tmp_path, JOB_WITHOUT, CARD_RESULT)
    why = fails(sg.leg_7_receipt_is_what_is_shown, root)
    assert "never decodes the column" in why


def test_leg7_red_when_it_is_decoded_but_never_rendered(tmp_path):
    """Decoding a column nothing renders changes nothing a stranger sees."""
    root = receipt_tree(tmp_path, JOB_WITH, CARD_RESULT)
    why = fails(sg.leg_7_receipt_is_what_is_shown, root)
    assert "still fed only" in why


def test_leg7_green_when_the_receipt_reaches_the_card(tmp_path):
    root = receipt_tree(tmp_path, JOB_WITH, CARD_RECEIPT)
    assert "reaches the done card" in sg.leg_7_receipt_is_what_is_shown(root)


def test_leg7_red_when_the_server_stops_demanding_a_receipt(tmp_path):
    """If the column stops being the record of truth the leg must say so, not
    keep asking the app to render something nobody verifies."""
    root = receipt_tree(tmp_path, JOB_WITH, CARD_RECEIPT,
                        guard="// no receipt check any more\n")
    why = fails(sg.leg_7_receipt_is_what_is_shown, root)
    assert "Re-point the leg" in why


def test_leg7_red_when_the_render_site_moved(tmp_path):
    root = receipt_tree(tmp_path, JOB_WITH, "Text(job.result ?? \"\")\n")
    why = fails(sg.leg_7_receipt_is_what_is_shown, root)
    assert "Re-point it at the new render site" in why


# ==========================================================================
# LEG 8 — THE DONE-TEXT CAN CARRY THE PHOTO
# ==========================================================================
def voice_arm(data: str) -> str:
    return ("class VoiceArm:\n"
            "    def text(self, to, body):\n"
            "        return self._result(\n"
            "            requests.post(\n"
            '                f"{self.base}/Messages.json",\n'
            f"                data={data},\n"
            "            ), \"text\", to)\n\n"
            "    def call(self, plan):\n"
            "        pass\n")


def test_leg8_red_when_the_text_can_only_carry_words(tmp_path):
    root = str(tmp_path)
    write(root, sg.VOICE_ARM,
          voice_arm('{"From": self.from_number, "To": to, "Body": body}'))
    why = fails(sg.leg_8_done_text_can_carry_the_photo, root)
    assert "no way to carry a picture" in why


def test_leg8_green_when_the_media_parameter_is_plumbed(tmp_path):
    root = str(tmp_path)
    write(root, sg.VOICE_ARM,
          voice_arm('{"From": self.from_number, "To": to, "Body": body, '
                    '"MediaUrl": media}'))
    assert "can carry" in sg.leg_8_done_text_can_carry_the_photo(root)


def test_leg8_is_not_satisfied_by_a_media_url_in_a_neighbouring_method(
        tmp_path):
    """`call()` sits directly under `text()`. A span that ran to the end of the
    class would be satisfied by any mention anywhere in the file."""
    root = str(tmp_path)
    src = voice_arm('{"From": self.from_number, "To": to, "Body": body}')
    write(root, sg.VOICE_ARM, src.replace("        pass\n",
                                          '        MediaUrl = "unrelated"\n'))
    why = fails(sg.leg_8_done_text_can_carry_the_photo, root)
    assert "no way to carry a picture" in why


def test_leg8_red_when_the_send_moved(tmp_path):
    root = str(tmp_path)
    write(root, sg.VOICE_ARM, "class VoiceArm:\n    pass\n")
    why = fails(sg.leg_8_done_text_can_carry_the_photo, root)
    assert "Re-point it" in why


# ==========================================================================
# LEG 9 — THE GUIDE NAMES SCREENS THAT EXIST
# ==========================================================================
# The guide is the page that hands a stranger the download, so every fixture
# that stands in for it carries the link — leg 9 now refuses a 200 that is not
# recognisably the guide, because an empty body and an error page contain no
# dead pointers and used to be read as a clean guide.
DOWNLOAD = f'<a href="/{sg.ZIP_NAME}">Download</a>'
CLEAN_GUIDE = (DOWNLOAD
               + "<p>Open Settings and find <em>Your computer</em>.</p>\n")
DEAD_GUIDE = (DOWNLOAD
              + "<p>You're already on the right screen — the one headed "
                "<em>“Your hands on the computer.”</em></p>\n")


def guide_tree(tmp_path, guide: str, beats='["Hello", "Where to reach you"]',
               sections='Section("Your computer") { }') -> str:
    root = str(tmp_path)
    write(root, sg.SETUP_PAGE, guide)
    write(root, sg.EXT_ONBOARDING, DOWNLOAD + "<p>Your computer</p>\n")
    write(root, sg.ONBOARDING, f"private static let beatNames = {beats}\n")
    write(root, sg.SETTINGS, sections + "\n")
    return root


def test_leg9_green_when_the_guide_names_only_real_screens(tmp_path):
    root = guide_tree(tmp_path, CLEAN_GUIDE)
    detail = sg.leg_9_guide_names_real_screens(
        root, fetch=fetch_of(CLEAN_GUIDE.encode()), base="http://gate.test")
    assert "Where to reach you" in detail


def test_leg9_red_when_the_guide_points_at_a_deleted_screen(tmp_path):
    root = guide_tree(tmp_path, DEAD_GUIDE)
    why = fails(sg.leg_9_guide_names_real_screens, root,
                fetch=fetch_of(DEAD_GUIDE.encode()), base="http://gate.test")
    assert "Your hands on the computer" in why


def test_leg9_green_when_the_screen_comes_back(tmp_path):
    """The pointer is only dead while the screen is. Bringing the beat back
    retires the item honestly, without anybody editing this gate."""
    root = guide_tree(tmp_path, DEAD_GUIDE,
                      beats='["Hello", "Your hands on the computer"]')
    detail = sg.leg_9_guide_names_real_screens(
        root, fetch=fetch_of(DEAD_GUIDE.encode()), base="http://gate.test")
    assert "only screens the app has" in detail


def test_leg9_red_when_only_production_is_stale(tmp_path):
    """Law 3: the page a stranger reads is the deployed one. A clean tree is
    not the answer to the question."""
    root = guide_tree(tmp_path, CLEAN_GUIDE)
    why = fails(sg.leg_9_guide_names_real_screens, root,
                fetch=fetch_of(DEAD_GUIDE.encode()), base="http://gate.test")
    assert "DEPLOYED" in why


def test_leg9_red_when_production_cannot_be_reached(tmp_path):
    root = guide_tree(tmp_path, CLEAN_GUIDE)

    def boom(url):
        raise OSError("connection refused")

    why = fails(sg.leg_9_guide_names_real_screens, root, fetch=boom,
                base="http://gate.test")
    assert "cannot verify the deployed guide" in why


def test_leg9_red_when_the_app_screen_names_cannot_be_read(tmp_path):
    root = guide_tree(tmp_path, CLEAN_GUIDE)
    write(root, sg.ONBOARDING, "// beatNames was renamed\n")
    why = fails(sg.leg_9_guide_names_real_screens, root,
                fetch=fetch_of(CLEAN_GUIDE.encode()), base="http://gate.test")
    assert "cannot tell a dead pointer from a live one" in why


# ==========================================================================
# THE 2026-08-25 REVIEW — TOKEN VERSUS BEHAVIOUR
#
# A review drove five of these legs green without fixing anything and one of
# them red on a correct repair. Every case below is that review's exact
# mutation, applied to a synthetic stand-in for the real file, so the fix
# cannot quietly come undone. The shape is always the same: the leg was
# hunting a TOKEN, and a comment, a rename or a neighbouring sentence contains
# the token while the behaviour is unchanged.
# ==========================================================================

# -- legs 1 and 2: a byte-perfect SUBSET is not the source -----------------
def test_leg1_red_when_the_package_is_a_byte_perfect_subset(tmp_path):
    """A zip of nothing but manifest.json reported "byte for byte the source
    the app pins, 1 files". Every byte in it matched; it was still not the
    extension. That is 2026-08-13 with the import edge removed."""
    root = extension_tree(tmp_path)
    blob = zip_of(root, ("manifest.json",))
    why = fails(sg.leg_1_hands_downloadable, root, fetch=fetch_of(blob),
                base="http://gate.test")
    assert "SUBSET" in why and "background.js" in why


def test_leg2_red_when_the_committed_zip_is_a_byte_perfect_subset(tmp_path):
    root = extension_tree(tmp_path)
    write(root, sg.REPO_ZIP, zip_of(root, ("manifest.json",)))
    why = fails(sg.leg_2_deployable_is_source, root)
    assert "SUBSET" in why


def test_leg1_red_when_a_file_only_the_manifest_names_is_left_out(tmp_path):
    """popup.html is named by the manifest and imported by nothing, so the
    import belt cannot see it missing. Chrome can: the toolbar button opens a
    page that is not there."""
    root = extension_tree(tmp_path)
    blob = zip_of(root, ("manifest.json", "background.js", "agent_loop.js",
                         "icons/icon16.png"))
    why = fails(sg.leg_1_hands_downloadable, root, fetch=fetch_of(blob),
                base="http://gate.test")
    assert "SUBSET" in why and "popup.html" in why


def test_leg1_red_when_an_injected_file_is_left_out(tmp_path):
    """page_map.js is never imported — it is pushed into the page with
    executeScript({files:[…]}). Deriving from imports alone drops it and ships
    a package whose page mapping dies at the first step."""
    root = extension_tree(tmp_path)
    write(root, "extension/background.js",
          'import { run } from "./agent_loop.js";\n'
          'chrome.scripting.executeScript({ files: ["page_map.js"] });\n')
    write(root, "extension/page_map.js", "// the injected one\n")
    blob = zip_of(root, EXT_FILES)
    why = fails(sg.leg_1_hands_downloadable, root, fetch=fetch_of(blob),
                base="http://gate.test")
    assert "page_map.js" in why


def test_leg2_green_when_the_zip_carries_everything_chrome_reaches(tmp_path):
    root = extension_tree(tmp_path)
    write(root, "extension/onboarding.html",
          '<script src="onboarding.js"></script>\n')
    write(root, "extension/onboarding.js", "// first run\n")
    write(root, "extension/background.js",
          'import { run } from "./agent_loop.js";\n'
          'chrome.tabs.create({ url: chrome.runtime.getURL("onboarding.html") });\n')
    write(root, sg.REPO_ZIP, zip_of(root, EXT_FILES + ("onboarding.html",
                                                       "onboarding.js")))
    assert "nothing Chrome reaches is missing" in \
        sg.leg_2_deployable_is_source(root)


def test_the_completeness_check_fails_closed_on_a_manifest_naming_nothing(
        tmp_path):
    """No entry points means nothing to follow, which is a leg that cannot be
    tested — not a package that passes."""
    root = extension_tree(tmp_path)
    write(root, sg.REPO_ZIP, zip_of(root, EXT_FILES))
    write(root, "extension/manifest.json",
          json.dumps({"name": "Anticipy", "version": "1.2.3"}))
    why = fails(sg.leg_2_deployable_is_source, root)
    assert "cannot tell a complete package from an empty one" in why


# -- leg 3: a modifier must not make a fixed product look broken -----------
@pytest.mark.skipif(not HAVE_SWIFT, reason="swift is not on PATH")
def test_leg3_still_executes_the_shipped_function_when_it_is_private(tmp_path):
    """`private static func e164(` used to read as "the function is gone", so
    a repair that fixed the +1 guess AND marked it private left the gate red
    on a fixed product. The modifiers are stripped and the code still runs."""
    root = str(tmp_path)
    write(root, sg.APP, SHIPPED_E164.replace("nonisolated func e164(",
                                             "private static func e164("))
    why = fails(sg.leg_3_foreign_number, root)
    assert "'+12079460958'" in why and "cannot be tested" not in why


@pytest.mark.skipif(not HAVE_SWIFT, reason="swift is not on PATH")
def test_leg3_green_through_a_modifier_too(tmp_path):
    root = str(tmp_path)
    write(root, sg.APP, FIXED_E164.replace("nonisolated func e164(",
                                           "public func e164("))
    assert "+44" in sg.leg_3_foreign_number(root)


# -- leg 4: a constant is not a fix ----------------------------------------
KEYS_FILE = "app/ios/Anticipy/OnboardingKeys.swift"


def test_leg4_is_not_satisfied_by_moving_the_key_into_a_constant(tmp_path):
    """The failure leg 3's own comment predicts — "the grep goes green the day
    the literal moves into a constant" — reproduced inside the leg that was
    rewritten to fix it. The constant is resolved and the value is unchanged."""
    root = str(tmp_path)
    write(root, sg.APP, app_swift(
        "    @AppStorage(OnboardingKeys.hasOnboarded) "
        "private var hasOnboarded = false\n"))
    write(root, KEYS_FILE,
          'enum OnboardingKeys {\n'
          '    static let hasOnboarded = "hasOnboarded"\n}\n')
    why = fails(sg.leg_4_onboarding_is_per_account, root)
    assert "one value for the whole PHONE" in why


def test_leg4_green_when_the_constant_behind_the_key_is_account_scoped(
        tmp_path):
    root = str(tmp_path)
    write(root, sg.APP, app_swift(
        "    @AppStorage(OnboardingKeys.hasOnboarded) "
        "private var hasOnboarded = false\n"))
    write(root, KEYS_FILE,
          'enum OnboardingKeys {\n'
          '    static let hasOnboarded = "hasOnboarded-\\(accountID)"\n}\n')
    assert "not one string for the whole phone" in \
        sg.leg_4_onboarding_is_per_account(root)


def test_leg4_is_not_fooled_by_a_key_that_interpolates_another_constant(
        tmp_path):
    """`"onboarded-\\(Build.channel)"` interpolates, and is still one string
    for every install. A leg that stopped at "it interpolates" would pass it."""
    root = str(tmp_path)
    write(root, sg.APP, app_swift(
        "    @AppStorage(OnboardingKeys.hasOnboarded) "
        "private var hasOnboarded = false\n"))
    write(root, KEYS_FILE,
          'enum Build {\n    static let channel = "beta"\n}\n'
          'enum OnboardingKeys {\n'
          '    static let hasOnboarded = "onboarded-\\(Build.channel)"\n}\n')
    why = fails(sg.leg_4_onboarding_is_per_account, root)
    assert "onboarded-beta" in why


def test_leg4_is_not_satisfied_by_a_comment_in_the_lifecycle(tmp_path):
    """`// hasOnboarded is deliberately NOT cleared here` used to satisfy the
    lifecycle half — prose about the bug retiring the check for the bug."""
    root = str(tmp_path)
    write(root, sg.APP, app_swift(
        BARE,
        sign_out_body='        authToken = ""\n'
                      '        // hasOnboarded is deliberately NOT cleared '
                      'here.\n'))
    why = fails(sg.leg_4_onboarding_is_per_account, root)
    assert "one value for the whole PHONE" in why


def test_leg4_red_when_the_key_cannot_be_followed_at_all(tmp_path):
    """A key this leg cannot resolve is a leg that cannot be tested."""
    root = str(tmp_path)
    write(root, sg.APP, app_swift(
        "    @AppStorage(Keys.somethingNobodyDeclares) "
        "private var hasOnboarded = false\n"))
    why = fails(sg.leg_4_onboarding_is_per_account, root)
    assert "cannot follow" in why


def test_leg4_green_when_the_key_is_built_from_a_runtime_value(tmp_path):
    """`var accountID` is decided at run time; folding its `= ""` default into
    the key would report the account-scoped fix as device-global — red on the
    very repair the leg asks for."""
    root = str(tmp_path)
    write(root, sg.APP, app_swift(
        '    @AppStorage("accountID") var accountID = ""\n'
        '    @AppStorage(OnboardingKeys.hasOnboarded) '
        'private var hasOnboarded = false\n'))
    write(root, KEYS_FILE,
          'enum OnboardingKeys {\n'
          '    static let hasOnboarded = "hasOnboarded-\\(accountID)"\n}\n')
    assert "not one string for the whole phone" in \
        sg.leg_4_onboarding_is_per_account(root)


# -- leg 5: naming a view is not putting it on screen ----------------------
def test_leg5_is_not_satisfied_by_first_run_merely_naming_the_view(tmp_path):
    """Appending `// Enrollment still lives in SettingsView()` to first run
    turned this green while enrollment stayed three scrolls deep in Settings.
    The leg reporting `speaker` at 0% across 221 events retired itself."""
    root = enroll_tree(tmp_path, {
        sg.SETTINGS: 'Section("Your voice") { }\n'
                     '.sheet { VoiceEnrollView() }\n',
        sg.ONBOARDING: 'private static let beatNames = ["Hello"]\n'
                       '// Enrollment still lives in SettingsView() — not '
                       'offered here.\n'})
    why = fails(sg.leg_5_enrollment_offered, root)
    assert "first run is not among them" in why


def test_leg5_is_not_satisfied_by_a_file_that_only_mentions_enrollment(
        tmp_path):
    """A comment naming VoiceEnrollView is not a presentation site, so a file
    full of prose about it cannot stand in for the door nobody built."""
    root = enroll_tree(tmp_path, {
        sg.SETTINGS: '// VoiceEnrollView used to be presented here.\n',
        sg.ONBOARDING: 'private static let beatNames = ["Hello"]\n'
                       'SettingsView()\n'})
    why = fails(sg.leg_5_enrollment_offered, root)
    assert "NOTHING in the app presents it" in why


# -- leg 6: the clock, not the word ----------------------------------------
def test_leg6_is_not_satisfied_by_a_comment_saying_the_bug_is_still_there(
        tmp_path):
    """`# TODO: honour CLOCK_QUIET_START/END here before we ever text a
    stranger` turned this leg green. A note documenting the absence retired
    the leg that tracks it, and strangers still get the product's first words
    at 1am."""
    root = str(tmp_path)
    write(root, sg.WORKER, worker_py(
        "    # TODO: honour CLOCK_QUIET_START/END here before we ever text "
        "a stranger.\n"
        "    return anticipy.notify_owner(hi)\n"))
    why = fails(sg.leg_6_welcome_respects_the_night, root)
    assert "consults no clock" in why


def test_leg6_is_not_satisfied_by_a_docstring_either(tmp_path):
    root = str(tmp_path)
    write(root, sg.WORKER, worker_py(
        '    """Guardrails: CLOCK_QUIET_START/END are not consulted yet."""\n'
        "    return anticipy.notify_owner(hi)\n"))
    why = fails(sg.leg_6_welcome_respects_the_night, root)
    assert "consults no clock" in why


def test_leg6_green_when_the_guard_lives_behind_a_helper(tmp_path):
    """THE WRONG FIRE. A real, working guard written the way anyone would
    write it — worker.py consults these constants in eight places, so a named
    helper is the natural shape — used to go RED, which is a gate blocking a
    correct repair and teaching people to route around it."""
    root = str(tmp_path)
    write(root, sg.WORKER, worker_py(
        "    if _in_quiet_hours(now):\n        return False\n"
        "    return anticipy.notify_owner(hi)\n",
        preamble="def _in_quiet_hours(now=None) -> bool:\n"
                 "    hour = time.localtime(now).tm_hour\n"
                 "    return CLOCK_QUIET_START <= hour "
                 "or hour < CLOCK_QUIET_END\n\n\n"))
    assert "consults quiet hours" in sg.leg_6_welcome_respects_the_night(root)


def test_leg6_green_when_the_helper_is_two_calls_deep(tmp_path):
    root = str(tmp_path)
    write(root, sg.WORKER, worker_py(
        "    if not _may_speak(now):\n        return False\n"
        "    return anticipy.notify_owner(hi)\n",
        preamble="def _quiet(now=None) -> bool:\n"
                 "    hour = time.localtime(now).tm_hour\n"
                 "    if CLOCK_QUIET_START <= hour or hour < CLOCK_QUIET_END:\n"
                 "        return True\n"
                 "    return False\n\n\n"
                 "def _may_speak(now=None) -> bool:\n"
                 "    return not _quiet(now)\n\n\n"))
    assert "consults quiet hours" in sg.leg_6_welcome_respects_the_night(root)


def test_leg6_green_when_the_guard_goes_through_a_local(tmp_path):
    root = str(tmp_path)
    write(root, sg.WORKER, worker_py(
        "    hour = time.localtime(now).tm_hour\n"
        "    quiet = CLOCK_QUIET_START <= hour or hour < CLOCK_QUIET_END\n"
        "    if quiet:\n        return False\n"
        "    return anticipy.notify_owner(hi)\n"))
    assert "consults quiet hours" in sg.leg_6_welcome_respects_the_night(root)


def test_leg6_is_not_satisfied_by_a_branch_that_cannot_stop_the_send(tmp_path):
    """Consulting the clock and sending anyway is the same 1am buzz. The
    branch has to be able to stop it."""
    root = str(tmp_path)
    write(root, sg.WORKER, worker_py(
        "    hour = time.localtime(now).tm_hour\n"
        "    if CLOCK_QUIET_START <= hour:\n"
        "        print('sending late')\n"
        "    return anticipy.notify_owner(hi)\n"))
    why = fails(sg.leg_6_welcome_respects_the_night, root)
    assert "consults no clock" in why


def test_leg6_still_reads_true_enclosure_at_the_call_site(tmp_path):
    """The old leg read three lines of indentation above the call, which is a
    good approximation of enclosure. The syntax tree says it exactly — this is
    a guard eight lines up that really does hold the call."""
    root = str(tmp_path)
    filler = "".join(f"            step_{i}()\n" for i in range(8))
    write(root, sg.WORKER, worker_py(
        "    return anticipy.notify_owner(hi)\n",
        before_call="        if not (CLOCK_QUIET_START <= hour "
                    "or hour < CLOCK_QUIET_END):\n" + filler,
        call_indent=12))
    assert "inside a quiet-hours guard" in \
        sg.leg_6_welcome_respects_the_night(root)


def test_leg6_red_when_the_worker_does_not_parse(tmp_path):
    root = str(tmp_path)
    write(root, sg.WORKER, "CLOCK_QUIET_START = 22\ndef maybe_welcome_new_owner(\n")
    why = fails(sg.leg_6_welcome_respects_the_night, root)
    assert "does not parse" in why


# -- leg 7: an argument, not a nearby word ---------------------------------
def test_leg7_is_not_satisfied_by_a_comment_near_the_call(tmp_path):
    """A comment 200 characters past the call saying "the receipt column is
    not rendered yet" turned this green. The leg could not tell an argument
    from a neighbouring word; it now reads the call's own parentheses."""
    root = receipt_tree(tmp_path, JOB_WITH,
                        CARD_RESULT
                        + "// " + "x" * 150 + "\n"
                        + "// the receipt column is not rendered yet\n")
    why = fails(sg.leg_7_receipt_is_what_is_shown, root)
    assert "still fed only" in why


def test_leg7_green_when_the_receipt_reaches_the_card_through_a_local(
        tmp_path):
    """`let rendered = format(job.receipt)` passed as `evidence: rendered` IS
    the receipt reaching the card. A leg demanding the word `receipt` inside
    the argument list would go red on it — the wrong fire, again."""
    root = receipt_tree(tmp_path, JOB_WITH,
                        "let rendered = format(job.receipt)\n"
                        "let card = JobReceiptPolicy.doneCard("
                        "goal: job.humanGoal, result: job.result, "
                        "evidence: rendered)\n")
    assert "reaches the done card" in sg.leg_7_receipt_is_what_is_shown(root)


def test_leg7_is_not_satisfied_by_a_commented_out_server_check(tmp_path):
    """If the server stops demanding a receipt the leg must say so. A
    commented-out check is not the server demanding anything."""
    root = receipt_tree(tmp_path, JOB_WITH, CARD_RECEIPT,
                        guard="// if (!receipt.verified) return reject();\n")
    why = fails(sg.leg_7_receipt_is_what_is_shown, root)
    assert "Re-point the leg" in why


# -- leg 8: the payload, not the file --------------------------------------
def test_leg8_is_not_satisfied_by_a_note_saying_it_is_not_wired(tmp_path):
    """`# NOTE: MediaUrl is not wired yet; see WIRE IT ALL step 1` turned this
    green. A note documenting the absence retired the leg that tracks it."""
    root = str(tmp_path)
    src = voice_arm('{"From": self.from_number, "To": to, "Body": body}')
    write(root, sg.VOICE_ARM, src.replace(
        "    def text(self, to, body):\n",
        "    def text(self, to, body):\n"
        "        # NOTE: MediaUrl is not wired yet; see WIRE IT ALL step 1.\n"))
    why = fails(sg.leg_8_done_text_can_carry_the_photo, root)
    assert "no way to carry a picture" in why


def test_leg8_is_not_satisfied_by_a_docstring_in_the_payload_builder(tmp_path):
    root = str(tmp_path)
    write(root, sg.VOICE_ARM,
          "class VoiceArm:\n"
          "    def _payload(self, to, body):\n"
          '        """MediaUrl is not wired yet."""\n'
          '        return {"From": self.from_number, "To": to, "Body": body}\n\n'
          "    def text(self, to, body):\n"
          "        return self._result(\n"
          "            requests.post(\n"
          '                f"{self.base}/Messages.json",\n'
          "                data=self._payload(to, body),\n"
          '            ), "text", to)\n')
    why = fails(sg.leg_8_done_text_can_carry_the_photo, root)
    assert "no way to carry a picture" in why


def test_leg8_green_when_the_payload_is_built_before_the_post(tmp_path):
    root = str(tmp_path)
    write(root, sg.VOICE_ARM,
          "class VoiceArm:\n"
          "    def text(self, to, body, media=None):\n"
          '        payload = {"From": self.from_number, "To": to, '
          '"Body": body}\n'
          "        if media:\n"
          '            payload["MediaUrl"] = media\n'
          "        return self._result(\n"
          "            requests.post(\n"
          '                f"{self.base}/Messages.json",\n'
          "                data=payload,\n"
          '            ), "text", to)\n')
    assert "can carry" in sg.leg_8_done_text_can_carry_the_photo(root)


def test_leg8_green_when_a_helper_builds_the_payload(tmp_path):
    """Plumbing the parameter through a builder is plumbing it. A leg that
    only read the text of `text()` would go red on this."""
    root = str(tmp_path)
    write(root, sg.VOICE_ARM,
          "class VoiceArm:\n"
          "    def _payload(self, to, body, media):\n"
          '        data = {"From": self.from_number, "To": to, "Body": body}\n'
          "        if media:\n"
          '            data["MediaUrl0"] = media\n'
          "        return data\n\n"
          "    def text(self, to, body, media=None):\n"
          "        return self._result(\n"
          "            requests.post(\n"
          '                f"{self.base}/Messages.json",\n'
          "                data=self._payload(to, body, media),\n"
          '            ), "text", to)\n')
    assert "can carry" in sg.leg_8_done_text_can_carry_the_photo(root)


# -- leg 9: a 200 is not an answer -----------------------------------------
def test_leg9_red_when_production_answers_with_an_empty_body(tmp_path):
    """Nothing dead can be found in a page containing nothing, so an empty 200
    used to be read as a clean guide. Leg 1 has no such hole — it PARSES what
    it downloads. This is the same shape check."""
    root = guide_tree(tmp_path, CLEAN_GUIDE)
    why = fails(sg.leg_9_guide_names_real_screens, root,
                fetch=fetch_of(b""), base="http://gate.test")
    assert "is not the install guide" in why


def test_leg9_red_when_production_answers_with_an_unrelated_page(tmp_path):
    root = guide_tree(tmp_path, CLEAN_GUIDE)
    why = fails(sg.leg_9_guide_names_real_screens, root,
                fetch=fetch_of(b"<html><body>Application Error</body></html>"),
                base="http://gate.test")
    assert "is not the install guide" in why


def test_leg9_red_when_a_guide_file_is_missing_from_the_tree(tmp_path):
    """This used to `continue`, so renaming setup.html made the tree half of
    the leg check nothing and say nothing."""
    root = guide_tree(tmp_path, CLEAN_GUIDE)
    os.unlink(os.path.join(root, sg.SETUP_PAGE))
    why = fails(sg.leg_9_guide_names_real_screens, root,
                fetch=fetch_of(CLEAN_GUIDE.encode()), base="http://gate.test")
    assert "is not in this tree" in why


def test_leg9_is_not_satisfied_by_a_commented_out_beat_name(tmp_path):
    """A commented-out `beatNames` would otherwise put a deleted screen back
    on the list of screens the app has, retiring the pointer that names it."""
    root = guide_tree(tmp_path, DEAD_GUIDE,
                      beats='["Hello"]\n'
                            '// private static let beatNames = '
                            '["Your hands on the computer"]')
    why = fails(sg.leg_9_guide_names_real_screens, root,
                fetch=fetch_of(DEAD_GUIDE.encode()), base="http://gate.test")
    assert "Your hands on the computer" in why



def test_leg4_is_not_satisfied_by_a_test_of_the_flag_in_sign_out(tmp_path):
    """`if hasOnboarded == true` names the flag and contains an equals sign.
    A leg reading "the name and an `=` on one line" would call that a clear."""
    root = str(tmp_path)
    write(root, sg.APP, app_swift(
        BARE,
        sign_out_body='        if hasOnboarded == true { log("was onboarded") }\n'))
    why = fails(sg.leg_4_onboarding_is_per_account, root)
    assert "one value for the whole PHONE" in why


def test_leg4_green_when_sign_out_assigns_the_flag_back(tmp_path):
    root = str(tmp_path)
    write(root, sg.APP, app_swift(
        BARE, sign_out_body='        hasOnboarded = false\n'))
    assert "clears it" in sg.leg_4_onboarding_is_per_account(root)


def test_leg5_is_not_satisfied_by_an_xcode_preview(tmp_path):
    """A PreviewProvider builds every view in the app and ships to nobody. A
    preview constructing VoiceEnrollView is not a door a stranger can find."""
    root = enroll_tree(tmp_path, {
        sg.SETTINGS: 'Section("Your voice") { }\n'
                     '.sheet { VoiceEnrollView() }\n',
        sg.ONBOARDING: 'private static let beatNames = ["Hello"]\n'
                       'struct OnboardingView_Previews: PreviewProvider {\n'
                       '    static var previews: some View '
                       '{ VoiceEnrollView() }\n}\n'})
    why = fails(sg.leg_5_enrollment_offered, root)
    assert "first run is not among them" in why


def test_leg7_is_not_satisfied_by_the_word_receipt_inside_a_string(tmp_path):
    root = receipt_tree(tmp_path, JOB_WITH,
                        'let card = JobReceiptPolicy.doneCard('
                        'goal: job.humanGoal, result: job.result, '
                        'placeholder: "no receipt yet")\n')
    why = fails(sg.leg_7_receipt_is_what_is_shown, root)
    assert "still fed only" in why



def test_leg5_is_not_satisfied_by_first_run_linking_to_settings(tmp_path):
    """A "Settings" button in onboarding puts Settings on screen, and Settings
    is where enrollment already is — three scrolls down, past Listening,
    Pendant and You. That is the complaint, not the repair. Without this the
    hop would retire the leg the day somebody adds the button."""
    root = enroll_tree(tmp_path, {
        sg.SETTINGS: 'struct SettingsView: View {\n'
                     '    var body: some View { VoiceEnrollView() }\n}\n',
        sg.ONBOARDING: 'private static let beatNames = ["Hello"]\n'
                       'SettingsView()\n'})
    why = fails(sg.leg_5_enrollment_offered, root)
    assert "first run is not among them" in why


# ==========================================================================
# THE GATE'S OWN SPINE
# ==========================================================================
def test_every_leg_is_wired_into_the_scoreboard():
    """A leg written and never added to LEGS runs in the tests and nowhere
    else, which is the most comfortable way to have coverage and no gate."""
    declared = {fn for _, _, _, fn in sg.LEGS}
    written = {v for k, v in vars(sg).items()
               if k.startswith("leg_") and callable(v)}
    assert written == declared, (
        "these legs exist but are not on the scoreboard: "
        f"{sorted(f.__name__ for f in written - declared)}")


def test_the_gate_says_which_legs_read_production():
    """HARNESS-LAWS Law 3. A gate that mixes source-green and live-green
    without labelling them is how repo-green got mistaken for done twice."""
    live = {num for num, _, where, _ in sg.LEGS if where == "LIVE"}
    assert live == {1, 9}, (
        "the set of legs that read production changed. Update this test AND "
        "the module docstring together — the label is the only thing telling "
        "a reader which greens survive a deploy.")


def test_the_ready_message_says_the_greens_are_against_a_tree():
    """Every leg prints (LIVE) or (tree), and the footer names the blind spots
    that need a device. But READY said only "every prerequisite a machine can
    check is standing" and then talked about devices and people — it never said
    that SEVEN of the nine legs went green against a tree which may not be what
    production is running. Two stale-prod incidents and Law 3 say that sentence
    belongs in the gate, not only in the report."""
    import contextlib
    import io as _io

    saved = list(sg.LEGS)
    try:
        sg.LEGS[:] = [(1, "LIVE ONE", "LIVE", lambda: "ok"),
                      (2, "TREE ONE", "tree", lambda: "ok"),
                      (3, "TREE TWO", "runs", lambda: "ok")]
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sg.main()
    finally:
        sg.LEGS[:] = saved
    text = out.getvalue()
    assert code == 0 and "READY" in text
    assert "2 of these 3 legs (legs 2, 3) read THIS" in text, text
    assert "prove the repo" in text
    assert "Only legs 1 survive" in text or "legs 1 survive" in text
    assert "stale" in text.lower() or "may not" in text


def test_the_ready_message_counts_the_legs_rather_than_remembering_them():
    """The report this gate shipped with said "five of nine prove the repo"
    when seven did, and left leg 8 out of the enumeration entirely. A number
    written down by hand rots; this one is computed from LEGS."""
    import contextlib
    import io as _io

    saved = list(sg.LEGS)
    try:
        sg.LEGS[:] = [(1, "A", "LIVE", lambda: "ok"),
                      (2, "B", "LIVE", lambda: "ok"),
                      (3, "C", "tree", lambda: "ok")]
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            sg.main()
    finally:
        sg.LEGS[:] = saved
    assert "1 of these 3 legs (legs 3) read THIS" in out.getvalue()
