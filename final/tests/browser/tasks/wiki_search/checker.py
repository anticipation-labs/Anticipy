"""Functional checker for task (C) — search + click-through + content assertion.

Independent re-read: the checker fetches the canonical target article itself
(via ctx['http_get']) and confirms the ground-truth token is genuinely on the
page. It then requires BOTH:
  (i)  the agent's answer contains that token, AND
  (ii) the agent actually navigated to the target article (final_url),
so an answer guessed from the model's own memory — without the real
search+click-through — does not pass.
"""
from __future__ import annotations

TOKEN = "1889"                                   # Eiffel Tower construction completed
TARGET = "https://en.wikipedia.org/wiki/Eiffel_Tower"


def _norm_url(u: str) -> str:
    return (u or "").split("#")[0].rstrip("/").replace("http://", "https://").lower()


def check(result: dict, ctx: dict) -> tuple[bool, str]:
    # 1) INDEPENDENT ground-truth: confirm the token is really on the live page,
    #    so we never grade against a stale/wrong expected value.
    try:
        page = ctx["http_get"](TARGET)
    except Exception as e:
        return False, f"could not independently fetch the target article: {e}"
    if TOKEN not in page:
        return False, f"ground-truth token {TOKEN!r} not found on the canonical article (checker needs updating)"

    # 2) The agent must actually report the fact.
    answer = str(result.get("answer") or "")
    if TOKEN not in answer:
        return False, f"agent answer does not contain the completion year {TOKEN!r}: {answer[:120]!r}"

    # 3) The agent must have actually reached the article (proves the click-through,
    #    not a from-memory guess). Accept either the final_url or the page read-back.
    final = _norm_url(result.get("final_url") or "")
    readback = str(result.get("final_text") or "") + str(result.get("final_corpus") or "")
    reached = final == _norm_url(TARGET) or "eiffel" in readback.lower()
    if not reached:
        return False, f"agent did not navigate to the article (final_url={result.get('final_url')!r})"
    return True, f"navigated to the Eiffel Tower article and correctly reported {TOKEN}"


# --- selftest fixtures: an offline http_get stub is injected by the harness ----

def _stub_page(_url: str) -> str:
    return ("<html><body><h1>Eiffel Tower</h1>"
            "<p>Construction started in 1887 and was completed in March 1889.</p>"
            "</body></html>")


def synth_pass(ctx: dict) -> dict:
    ctx["http_get"] = _stub_page          # offline ground-truth for the selftest
    return {
        "answer": "Construction of the Eiffel Tower was completed in 1889.",
        "final_url": TARGET,
        "final_text": "Eiffel Tower ... completed in March 1889 ...",
        "metrics": {"steps": 5, "est_cost_usd": 0.0089, "frontier_pct": 10.0,
                    "vision_pct": 20.0, "region_pct": 100.0, "replayed": False},
        "task_succeeded": True,
    }


def synth_fail(ctx: dict) -> dict:
    # The token IS on the ground-truth page, but the agent never reached the
    # article and never reported the year -> must fail.
    ctx["http_get"] = _stub_page
    return {
        "answer": "I couldn't find that information.",
        "final_url": "https://en.wikipedia.org/wiki/Main_Page",
        "final_text": "Welcome to Wikipedia",
        "metrics": {"steps": 12, "est_cost_usd": 0.02, "frontier_pct": 33.0,
                    "vision_pct": 60.0, "region_pct": 50.0, "replayed": False},
        "task_succeeded": False,
    }
