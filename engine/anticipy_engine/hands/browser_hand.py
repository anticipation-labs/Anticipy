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
import os
import re
import urllib.parse
from typing import Any, List, Optional

from ..core.browser_link import BrowserLink
from ..core.envelopes import Job, JobStatus, Result
from ..core.worker import Worker
from ..agent.webvoyager import WebVoyagerAgent

_URL_RE = re.compile(r"https?://[^\s<>\]})\"']+")
_BARE_DOMAIN_RE = re.compile(
    r"\b(?:on|at|from|using|via)\s+((?:[a-z0-9-]+\.)+[a-z]{2,})(/[^\s<>\]})\"']*)?",
    re.I,
)
# A URL-less browse task ("find the exchange rate") is a GOAL, not a destination. The extension
# navigates to a concrete URL, so without one it dead-ends at "no url/task to browse". General
# fallback: turn any URL-less task into a real search-results navigation. Engine-side on purpose —
# the already-loaded extension is unchanged; it just receives a url and navigates + screenshots.
# DuckDuckGo over Google: it rarely throws the consent/captcha walls that would force a hand-off.
_SEARCH = "https://duckduckgo.com/?q={q}"


def _clean_url(raw: str) -> str:
    return (raw or "").strip().rstrip(".,;:!?)\"]}'")


def _start_url(args: dict, *, allow_search: bool = True) -> str:
    if not isinstance(args, dict):
        return ""
    explicit = _clean_url(str(args.get("url") or ""))
    if explicit:
        return explicit
    task = str(args.get("task") or "").strip()
    m = _URL_RE.search(task)
    if m:
        return _clean_url(m.group(0))
    bare = _BARE_DOMAIN_RE.search(task)
    if bare:
        return "https://" + _clean_url((bare.group(1) or "") + (bare.group(2) or ""))
    if allow_search and task:
        return _SEARCH.format(q=urllib.parse.quote_plus(task))
    return ""


def _with_target(args: dict) -> dict:
    """Ensure a browse job has a navigable target. No url + a non-empty task with no inline URL
    -> search for the task. Leaves an explicit url / inline-URL task / empty args untouched."""
    if not isinstance(args, dict) or args.get("url"):
        return args
    task = str(args.get("task") or "").strip()
    if not task or _URL_RE.search(task):
        return args
    out = dict(args)
    out["url"] = _start_url(out)
    return out


class BrowserHand(Worker):
    def __init__(
        self,
        link: BrowserLink,
        timeout: float = 30.0,
        gateway: Optional[Any] = None,
        max_steps: Optional[int] = None,
        agent_timeout: Optional[float] = None,
        notifier=None,
        agent_factory=WebVoyagerAgent,
    ) -> None:
        self.link = link
        self.timeout = timeout
        self.gateway = gateway
        self.max_steps = max_steps or int(os.environ.get("ANTICIPY_AGENT_MAX_STEPS", "18"))
        self.agent_timeout = agent_timeout or float(os.environ.get("ANTICIPY_AGENT_TIMEOUT", "240"))
        self.notifier = notifier
        self.agent_factory = agent_factory

    def handles(self) -> List[str]:
        return ["browse_task", "read_page"]

    async def handle(self, job: Job) -> Result:
        if not self.link.connected:
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": "the browser helper isn't connected"})
        if job.intent == "browse_task" and self.gateway is not None:
            return await self._handle_agent(job)
        return await self._handle_once(job)

    async def _handle_once(self, job: Job) -> Result:
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

    async def _handle_agent(self, job: Job) -> Result:
        args = job.args if isinstance(job.args, dict) else {}
        task = str(args.get("task") or args.get("query") or job.intent).strip()
        start = _start_url(args, allow_search=False)
        if not task:
            task = f"Complete the browser task at {start}" if start else "Complete the browser task."
        if not start:
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": "browser task has no start URL or searchable task"})

        agent = self.agent_factory(
            self.link,
            self.gateway,
            max_steps=self.max_steps,
            notifier=self.notifier,
        )
        try:
            result = await asyncio.wait_for(agent.run(task, start), timeout=self.agent_timeout)
        except asyncio.TimeoutError:
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error="browser agent timed out")
        except RuntimeError as exc:
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": f"browser planner unavailable: {exc}"})
        except ConnectionError:
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": "browser disconnected mid-agent-run"})
        except Exception as exc:
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error=f"browser agent failed: {type(exc).__name__}: {exc}")

        shot = result.pop("final_shot", None)
        if result.get("needs_human") or result.get("paused"):
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output=result)
        if result.get("stopped_for_safety"):
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output=result)
        if result.get("exhausted"):
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          output=result, error="browser agent exhausted its step budget")
        if not result.get("answer"):
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          output=result, error=result.get("reason") or "browser agent did not finish")

        proof = {
            "browser_agent": "webvoyager",
            "url": result.get("final_url"),
            "screenshot": shot,
            "steps": result.get("steps"),
            "history": (result.get("history") or [])[-10:],
            "page_states": (result.get("page_states") or [])[-8:],
            "commerce_recipe": bool(result.get("commerce_recipe")),
        }
        if not (proof.get("screenshot") or proof.get("url")):
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          output=result, error="browser agent returned no final screenshot or URL")
        return Result(job_id=job.id, status=JobStatus.success, proof=proof, output=result)
