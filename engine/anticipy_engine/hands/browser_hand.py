"""The browser hand — the per-person 10% with no API.

Engine-side worker that delegates execution to the MV3 extension over the
authenticated WS (BrowserLink). It sends a browse job, awaits the result +
screenshot proof with a per-job TIMEOUT, and never hangs or fakes a success:
  - extension not connected            -> needs_human ("browser helper isn't connected")
  - timeout                            -> failed (orchestrator retries/reroutes)
  - disconnected mid-job               -> needs_human
  - login-wall / captcha (from ext)    -> needs_human (handed back to the user)
  - success without a screenshot       -> failed (no proof, not done)
  - success with screenshot            -> success + proof

Vision verify (smart model on the screenshot) plugs in at the model gateway;
cost stays disciplined (smart only at the verify/decision point, not every step).
"""
from __future__ import annotations

import asyncio
import re
import urllib.parse
from typing import List

from ..core.browser_link import BrowserLink
from ..core.envelopes import Job, JobStatus, Result
from ..core.worker import Worker

_URL_RE = re.compile(r"https?://\S+")
# A URL-less browse task ("find the exchange rate") is a GOAL, not a destination. The extension
# navigates to a concrete URL, so without one it dead-ends at "no url/task to browse". General
# fallback: turn any URL-less task into a real search-results navigation. Engine-side on purpose —
# the already-loaded extension is unchanged; it just receives a url and navigates + screenshots.
# DuckDuckGo over Google: it rarely throws the consent/captcha walls that would force a hand-off.
_SEARCH = "https://duckduckgo.com/?q={q}"


def _with_target(args: dict) -> dict:
    """Ensure a browse job has a navigable target. No url + a non-empty task with no inline URL
    -> search for the task. Leaves an explicit url / inline-URL task / empty args untouched."""
    if not isinstance(args, dict) or args.get("url"):
        return args
    task = str(args.get("task") or "").strip()
    if not task or _URL_RE.search(task):
        return args
    out = dict(args)
    out["url"] = _SEARCH.format(q=urllib.parse.quote_plus(task))
    return out


class BrowserHand(Worker):
    def __init__(self, link: BrowserLink, timeout: float = 30.0) -> None:
        self.link = link
        self.timeout = timeout

    def handles(self) -> List[str]:
        return ["browse_task", "read_page"]

    async def handle(self, job: Job) -> Result:
        if not self.link.connected:
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": "the browser helper isn't connected"})
        try:
            resp = await self.link.send_browse(job.id, job.intent, _with_target(job.args), timeout=self.timeout)
        except asyncio.TimeoutError:
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error="browser timed out")
        except ConnectionError:
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": "browser disconnected mid-job"})

        status = resp.get("status")
        if status == "success":
            proof = resp.get("proof") or {}
            if not (proof.get("screenshot") or proof.get("id")):
                return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                              error="browser returned no screenshot/proof")
            return Result(job_id=job.id, status=JobStatus.success, proof=proof,
                          output=resp.get("output", {}))
        if status == "needs_human":
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output=resp.get("output", {"reason": "handed back to you"}))
        return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                      error=(resp.get("output", {}) or {}).get("reason", "browser failed"))
