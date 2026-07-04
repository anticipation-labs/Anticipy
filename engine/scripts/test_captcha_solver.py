"""S6 captcha solver — unit test.

Pins detection + sitekey extraction (reCAPTCHA v2/v3, hCaptcha, Turnstile, image), the
CapSolver createTask/getTaskResult client, the 2Captcha fallback, token injection, and the
recovery-ladder bridge — all OFFLINE with a fake HTTP (no network, deterministic). Then a
LIVE smoke test: a tiny CapSolver getBalance against the real API (no full solve), skipped
cleanly if the key/network is unavailable.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_captcha_solver.py
     (add --live to force the live getBalance to hard-fail instead of skip)
"""
import json
import sys

from anticipy_engine.hands.captcha_solver import (
    CAPTCHA_HCAPTCHA,
    CAPTCHA_IMAGE,
    CAPTCHA_RECAPTCHA_V2,
    CAPTCHA_RECAPTCHA_V3,
    CAPTCHA_TURNSTILE,
    CaptchaSolver,
    SolveResult,
    detect_captcha,
    from_env,
    injection_script,
    resolve_captcha,
)


class FakeResp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d

    @property
    def text(self):
        return json.dumps(self._d)


class QueueHttp:
    """Fake HTTP: match a substring of the URL to a FIFO queue of response dicts."""

    def __init__(self, queues):
        self.queues = {k: list(v) for k, v in queues.items()}
        self.log = []

    def __call__(self, method, url, **kw):
        self.log.append((method, url, kw))
        for key, q in self.queues.items():
            if key in url:
                return FakeResp(q.pop(0) if q else {})
        return FakeResp({})


def _noop(_s=0):
    return None


# ── detection ─────────────────────────────────────────────────────────────────
def test_detection():
    v2 = {"url": "https://site.test/login",
          "html": '<script src="https://www.google.com/recaptcha/api.js"></script>'
                  '<div class="g-recaptcha" data-sitekey="6Lc_V2_KEY"></div>'}
    c = detect_captcha(v2)
    assert c and c.kind == CAPTCHA_RECAPTCHA_V2 and c.sitekey == "6Lc_V2_KEY", c

    v3 = {"url": "https://site.test/",
          "html": '<script src="https://www.google.com/recaptcha/api.js?render=6Lc_V3_KEY">'
                  '</script><button data-action="signup">go</button>'}
    c = detect_captcha(v3)
    assert c and c.kind == CAPTCHA_RECAPTCHA_V3 and c.sitekey == "6Lc_V3_KEY" \
        and c.page_action == "signup", c

    hc = {"url": "https://site.test/",
          "html": '<script src="https://hcaptcha.com/1/api.js"></script>'
                  '<div class="h-captcha" data-sitekey="HCAP-KEY"></div>'}
    c = detect_captcha(hc)
    assert c and c.kind == CAPTCHA_HCAPTCHA and c.sitekey == "HCAP-KEY", c

    ts = {"url": "https://site.test/",
          "html": '<div class="cf-turnstile" data-sitekey="0x4AAAAAAABkMY"></div>'}
    c = detect_captcha(ts)
    assert c and c.kind == CAPTCHA_TURNSTILE and c.sitekey == "0x4AAAAAAABkMY", c

    img = {"url": "https://site.test/",
           "html": 'Enter the captcha: <img src="data:image/png;base64,'
                   'iVBORw0KGgoAAAANSUhEUgAA">'}
    c = detect_captcha(img)
    assert c and c.kind == CAPTCHA_IMAGE and c.image_b64.startswith("iVBOR"), c

    assert detect_captcha({"url": "u", "html": "<p>no challenge here</p>"}) is None
    print("PASS detection: v2/v3/hCaptcha/Turnstile/image classified; sitekeys extracted")


# ── CapSolver client ──────────────────────────────────────────────────────────
def test_capsolver_solve():
    http = QueueHttp({
        "/createTask": [{"errorId": 0, "taskId": "T1"}],
        "/getTaskResult": [
            {"errorId": 0, "status": "processing"},
            {"errorId": 0, "status": "ready", "solution": {"gRecaptchaResponse": "CS_TOKEN"}},
        ],
    })
    s = CaptchaSolver(capsolver_key="ck", http=http, sleep=_noop, poll_interval=0.01)
    ch = detect_captcha({"url": "https://x.test",
                         "html": '<div class="g-recaptcha" data-sitekey="K"></div>'})
    res = s.solve(ch)
    assert res.ok and res.provider == "capsolver" and res.token == "CS_TOKEN", res
    # createTask payload carried the right proxyless task type + key.
    ct = next(c for c in http.log if "/createTask" in c[1])
    assert ct[2]["json"]["task"]["type"] == "ReCaptchaV2TaskProxyLess"
    assert ct[2]["json"]["task"]["websiteKey"] == "K"
    print("PASS capsolver: createTask -> poll -> ready -> gRecaptchaResponse token")


def test_capsolver_then_twocaptcha_fallback():
    http = QueueHttp({
        "/createTask": [{"errorId": 1, "errorDescription": "ERROR_SERVICE_UNAVAILABLE"}],
        "/in.php": [{"status": 1, "request": "CID99"}],
        "/res.php": [{"status": 0, "request": "CAPCHA_NOT_READY"},
                     {"status": 1, "request": "TWO_TOKEN"}],
    })
    s = CaptchaSolver(capsolver_key="ck", twocaptcha_key="tk", http=http,
                      sleep=_noop, poll_interval=0.01)
    ch = detect_captcha({"url": "https://x.test",
                         "html": '<div class="h-captcha" data-sitekey="HK"></div>'
                                 '<script src="https://hcaptcha.com/1/api.js"></script>'})
    res = s.solve(ch)
    assert res.ok and res.provider == "twocaptcha" and res.token == "TWO_TOKEN", res
    inp = next(c for c in http.log if "/in.php" in c[1])
    assert inp[2]["data"]["method"] == "hcaptcha" and inp[2]["data"]["sitekey"] == "HK"
    print("PASS fallback: CapSolver error -> 2Captcha in.php/res.php -> token")


def test_both_providers_fail():
    http = QueueHttp({
        "/createTask": [{"errorId": 1, "errorDescription": "ERROR_KEY_DENIED"}],
        "/in.php": [{"status": 0, "request": "ERROR_WRONG_USER_KEY"}],
    })
    s = CaptchaSolver(capsolver_key="ck", twocaptcha_key="tk", http=http, sleep=_noop)
    ch = detect_captcha({"url": "u", "html": '<div class="g-recaptcha" data-sitekey="K"></div>'})
    res = s.solve(ch)
    assert not res.ok and "capsolver" in res.error and "twocaptcha" in res.error, res
    print("PASS both-fail: no token, both provider errors surfaced honestly")


def test_injection_script():
    ch = detect_captcha({"url": "u", "html": '<div class="g-recaptcha" data-sitekey="K"></div>'})
    js = injection_script(ch, "TOK123")
    assert "TOK123" in js and "g-recaptcha-response" in js, js
    ts = detect_captcha({"url": "u", "html": '<div class="cf-turnstile" data-sitekey="0xK"></div>'})
    assert "cf-turnstile-response" in injection_script(ts, "T")
    img = detect_captcha({"url": "u", "html": 'captcha <img src="data:image/png;base64,'
                          'iVBORw0KGgoAAAANSUhEUgAA">'})
    assert img and img.kind == CAPTCHA_IMAGE, img
    assert injection_script(img, "T") == "", "image captcha has no hidden receiver field"
    print("PASS injection: provider-standard response field, token embedded; image -> none")


def test_resolve_captcha_bridge():
    http = QueueHttp({
        "/createTask": [{"errorId": 0, "taskId": "T"}],
        "/getTaskResult": [{"errorId": 0, "status": "ready",
                            "solution": {"gRecaptchaResponse": "RTOK"}}],
    })
    s = CaptchaSolver(capsolver_key="ck", http=http, sleep=_noop, poll_interval=0.01)
    page = {"url": "https://x.test", "html": '<div class="g-recaptcha" data-sitekey="K"></div>'}
    out = resolve_captcha(page, s)
    assert out.solved and out.token == "RTOK" and "RTOK" in out.injection, out
    # no captcha -> not solved (ladder falls to handoff), no crash
    assert resolve_captcha({"url": "u", "html": "<p>clean</p>"}, s).solved is False
    # captcha present but no solver -> not solved, challenge still reported
    none_out = resolve_captcha(page, None)
    assert none_out.solved is False and none_out.challenge is not None, none_out
    print("PASS resolve_captcha: detect->solve->token+injection; graceful no-op paths")


# ── LIVE smoke: CapSolver getBalance (no full solve) ──────────────────────────
def test_live_getbalance(force_live=False):
    solver = from_env(timeout=20)
    if not solver.capsolver_key:
        print("SKIP live getBalance: no CAPSOLVER_API_KEY in env")
        return
    try:
        bal = solver.balance()
    except Exception as e:  # network blocked / transient — don't fail the offline suite
        if force_live:
            raise
        print(f"SKIP live getBalance (network/key): {e}")
        return
    assert isinstance(bal, float) and bal >= 0.0, bal
    print(f"PASS live getBalance: CapSolver reachable, balance=${bal:.4f}")


def main():
    force_live = "--live" in sys.argv
    test_detection()
    test_capsolver_solve()
    test_capsolver_then_twocaptcha_fallback()
    test_both_providers_fail()
    test_injection_script()
    test_resolve_captcha_bridge()
    test_live_getbalance(force_live=force_live)
    print("ALL CAPTCHA-SOLVER TESTS PASSED")


if __name__ == "__main__":
    main()
