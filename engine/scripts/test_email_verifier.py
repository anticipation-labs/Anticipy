"""S6 email verification-code tool — unit test.

Pins the pure code-extraction (labeled codes, Google G-######, "is 123456", bare 6-digit,
year/non-code rejection), the optional LLM fallback, service matching, latest-of-many
selection, and the Gmail REST adapter's payload decode — all OFFLINE with fixtures and a
fake HTTP. No real Gmail login (S6 must not sign in / read a live inbox here).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_email_verifier.py
"""
import base64

from anticipy_engine.hands.email_verifier import (
    GmailReader,
    VerificationEmail,
    extract_code,
    latest_code_for_service,
    match_service,
    read_verification_code,
    service_tokens,
)


def test_extract_code():
    assert extract_code("Your verification code is 483920. It expires soon.") == "483920"
    assert extract_code("Enter this security code: 71042 to continue") == "71042"
    assert extract_code("G-558193 is your Google verification code") == "558193"
    assert extract_code("Use one-time passcode 9KJ4T2 now") == "9KJ4T2"
    assert extract_code("Your OTP is 4821") == "4821"
    # A bare year is not a 4-digit code; a real 6-digit token in the same mail wins.
    assert extract_code("Copyright 2026. Your code is 220487 today.") == "220487"
    # Nothing code-like.
    assert extract_code("Welcome aboard! Thanks for joining our newsletter.") is None
    print("PASS extract_code: labeled / Google / alnum / short OTP; rejects year & prose")


def test_llm_fallback():
    weird = "we have provisioned your one time entry pass, quote it back verbatim"
    assert extract_code(weird) is None
    got = extract_code(weird, llm_extract=lambda _t: "606188")
    assert got == "606188", got
    # LLM is only asked when regex misses; a garbage LLM answer is rejected by _looks_like_code.
    assert extract_code(weird, llm_extract=lambda _t: "not-a-code") is None
    print("PASS llm fallback: consulted only when regex misses; validated before returning")


def test_service_match():
    assert service_tokens("https://railway.app/signup") == {"railway.app", "railway"}
    assert "notion" in service_tokens("Notion")
    e = VerificationEmail(from_addr="Railway <noreply@railway.app>",
                          subject="Verify your email", body="code 123456")
    assert match_service(e, "https://railway.app/signup") == "railway.app"
    assert match_service(e, "notion") == ""
    print("PASS service match: url/name/domain -> tokens; from-address preferred")


def test_latest_selection():
    emails = [
        VerificationEmail(id="old", from_addr="noreply@railway.app",
                          subject="code", body="Your code is 111111", internal_ts=100),
        VerificationEmail(id="new", from_addr="noreply@railway.app",
                          subject="code", body="Your code is 222222", internal_ts=900),
        VerificationEmail(id="other", from_addr="noreply@notion.so",
                          subject="code", body="Your code is 333333", internal_ts=999),
    ]
    hit = latest_code_for_service(emails, "railway.app")
    assert hit and hit.code == "222222" and hit.email.id == "new", hit
    assert read_verification_code("railway.app", emails=emails) == "222222"
    # A service with no matching mail -> None (never a wrong code).
    assert read_verification_code("stripe.com", emails=emails) is None
    print("PASS latest: newest matching mail wins; wrong-service returns nothing")


def _gmail_msg(mid, frm, subj, body, ts):
    data = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return {
        "id": mid, "internalDate": str(ts), "snippet": subj,
        "payload": {"headers": [{"name": "From", "value": frm},
                                {"name": "Subject", "value": subj}],
                    "mimeType": "text/plain", "body": {"data": data}},
    }


class FakeGmailResp:
    def __init__(self, d):
        self._d = d

    def json(self):
        return self._d


def test_gmail_adapter():
    msgs = {
        "M1": _gmail_msg("M1", "noreply@railway.app", "Verify", "Your code is 424242", 500),
    }

    def http(method, url, **kw):
        if url.endswith("/messages"):
            return FakeGmailResp({"messages": [{"id": "M1"}]})
        return FakeGmailResp(msgs["M1"])

    reader = GmailReader("fake-token", http=http)
    got = read_verification_code("railway.app", reader=reader)
    assert got == "424242", got
    print("PASS gmail adapter: list+get, base64url body decode, code read end-to-end")


def main():
    test_extract_code()
    test_llm_fallback()
    test_service_match()
    test_latest_selection()
    test_gmail_adapter()
    print("ALL EMAIL-VERIFIER TESTS PASSED")


if __name__ == "__main__":
    main()
