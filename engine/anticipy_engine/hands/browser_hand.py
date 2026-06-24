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

MOCK mode (the same ANTICIPY_HANDS_MODE contract as ApiHand, wired by
ControlCore; direct constructions default LIVE): no browser, no model — but the
live path's own deterministic gates still rule first, so a job live would
refuse (an action-shaped task with no resolved real site) is refused
identically, and only a live-navigable job returns a loudly-labeled mock
artifact. That lets the orchestrator drive browser-routed goals to
done-with-proof in the stub tier with zero real-world side effects.

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
from ..agent.form_prepare import FormPrepareAgent
from .api_hand import MODE_LIVE, MODE_MOCK


def _form_fields(args: dict) -> dict:
    """Pull the owner's requested {label: value} field map off the job args."""
    fields = (args or {}).get("fields")
    return fields if isinstance(fields, dict) else {}

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
_ACTION_TASK_NEEDS_SITE_RE = re.compile(
    r"\b(?:add|put|get|grab|snag|order|buy|book|reserve|submit|fill|send|post|message|email|cancel|delete|update)\b"
    r"[\w' ,.-]{0,140}\b(?:cart|basket|bag|checkout|form|account|reservation|appointment|message|email|order)\b|"
    r"\b(?:cart|basket|bag|checkout)\b|"
    r"\b(?:that|the)\s+(?:thing|one|item|product)\b|"
    r"\b(?:earlier|last time|before|was looking at|looked at)\b",
    re.I,
)


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


def _action_task_needs_site(task: str) -> bool:
    return _ACTION_TASK_NEEDS_SITE_RE.search(task or "") is not None


def _with_target(args: dict, *, allow_search: bool = True) -> dict:
    """Ensure a read-style browse job has a navigable target.

    URL-less action tasks must arrive with a resolved real site from the
    planner/memory layer. Sending the whole instruction to search is the exact
    failure mode the M3 loop is trying to eliminate.
    """
    if not isinstance(args, dict) or args.get("url"):
        return args
    task = str(args.get("task") or "").strip()
    if not task or _URL_RE.search(task):
        return args
    if not allow_search or _action_task_needs_site(task):
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
        fallback_link: Optional[Any] = None,
        mode: str = MODE_LIVE,
        form_agent_factory=FormPrepareAgent,
    ) -> None:
        self.mode = mode
        self.link = link
        self.fallback_link = fallback_link
        self.timeout = timeout
        self.gateway = gateway
        self.max_steps = max_steps or int(os.environ.get("ANTICIPY_AGENT_MAX_STEPS", "18"))
        self.agent_timeout = agent_timeout or float(os.environ.get("ANTICIPY_AGENT_TIMEOUT", "240"))
        self.notifier = notifier
        self.agent_factory = agent_factory
        self.form_agent_factory = form_agent_factory

    def handles(self) -> List[str]:
        # prepare_form is the safe browser WRITE arm: fill a form up to the submit
        # screen, stop, and hand the filled state back for the owner to submit.
        return ["browse_task", "read_page", "prepare_form"]

    def _active_link(self):
        if getattr(self.link, "connected", False):
            return self.link
        if self.fallback_link is not None and getattr(self.fallback_link, "connected", False):
            return self.fallback_link
        return None

    async def handle(self, job: Job) -> Result:
        if self.mode == MODE_MOCK:
            return self._handle_mock(job)
        link = self._active_link()
        if link is None:
            reason = "the browser helper isn't connected"
            if self.fallback_link is not None:
                err = getattr(self.fallback_link, "last_error", lambda: "")()
                if err:
                    reason = f"{reason}; native bridge unavailable: {err}"
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": reason})
        if job.intent == "prepare_form":
            return await self._handle_prepare_form(job, link)
        if job.intent == "browse_task" and self.gateway is not None:
            return await self._handle_agent(job, link)
        return await self._handle_once(job, link)

    async def _handle_prepare_form(self, job: Job, link) -> Result:
        """Safe browser WRITE: fill the form to the submit screen, then hand off.

        NEVER returns a plain success — preparing a form is not finishing it. A
        clean prepare returns needs_human (the owner confirms + submits); the
        result carries the filled-field read-back proof + screenshot so the owner
        sees exactly what is staged. No submit, no login, no money are ever taken.
        """
        args = job.args if isinstance(job.args, dict) else {}
        url = str(args.get("url") or "").strip()
        fields = _form_fields(args)
        if not url or not _URL_RE.search(url):
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error="prepare_form needs a concrete form url")
        if not fields:
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error="prepare_form needs a fields map of {label: value}")
        agent = self.form_agent_factory(link)
        try:
            result = await asyncio.wait_for(agent.run(url, fields), timeout=self.timeout * 4)
        except asyncio.TimeoutError:
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error="form prepare timed out")
        except ConnectionError:
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": "browser disconnected mid-form-prepare"})

        if result.get("submitted"):
            # impossible by construction; a hard guard, never trust the loop alone
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error="form-prepare must never submit; refusing to report a submit")
        if not result.get("filled_fields"):
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": result.get("reason") or "nothing could be prepared",
                                  **result})
        proof = {
            "form_prepare": True,
            "submitted": False,
            "url": result.get("final_url"),
            "screenshot": result.get("final_shot"),
            "filled_fields": result.get("filled_fields"),
            "pending_fields": result.get("pending_fields"),
            "submit_control": result.get("submit_control"),
        }
        # prepared, never submitted -> hand back for the owner's confirm + submit
        return Result(job_id=job.id, status=JobStatus.needs_human, proof=proof,
                      output=result)

    def _handle_mock(self, job: Job) -> Result:
        """Mock tier: the live path's deterministic gates first, then a labeled
        mock artifact — never a success for a job live would refuse."""
        args = job.args if isinstance(job.args, dict) else {}
        task = str(args.get("task") or "").strip()
        target_args = _with_target(args, allow_search=job.intent == "read_page" or not _action_task_needs_site(task))
        if job.intent == "browse_task" and task and not _start_url(target_args, allow_search=False):
            if _action_task_needs_site(task):
                return Result(
                    job_id=job.id,
                    status=JobStatus.failed,
                    proof=None,
                    output={"reason": "browser action task has no resolved real site; refusing search fallback",
                            "mock": True},
                    error="browser action task has no resolved real site",
                )
        url = _start_url(target_args)
        if not url:
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          output={"mock": True}, error="no url/task to browse")
        proof = {"id": f"mock-{job.id[:8]}", "mock": True, "url": url,
                 "screenshot": f"mock://shot/{job.id[:8]}.png"}
        return Result(job_id=job.id, status=JobStatus.success, proof=proof,
                      output={"mock": True, "url": url, "task": task})

    async def _handle_once(self, job: Job, link=None) -> Result:
        link = link or self.link
        args = job.args if isinstance(job.args, dict) else {}
        task = str(args.get("task") or "").strip()
        target_args = _with_target(args, allow_search=job.intent == "read_page" or not _action_task_needs_site(task))
        if job.intent == "browse_task" and task and not _start_url(target_args, allow_search=False):
            if _action_task_needs_site(task):
                return Result(
                    job_id=job.id,
                    status=JobStatus.failed,
                    proof=None,
                    output={"reason": "browser action task has no resolved real site; refusing search fallback"},
                    error="browser action task has no resolved real site",
                )
        if job.intent == "browse_task" and task and _action_task_needs_site(task) and self.gateway is None:
            return Result(
                job_id=job.id,
                status=JobStatus.needs_human,
                proof=None,
                output={
                    "reason": (
                        "browser action needs the live browser planner; read-only "
                        "page proof is not action proof"
                    )
                },
            )
        try:
            resp = await link.send_browse(job.id, job.intent, target_args, timeout=self.timeout)
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

    async def _handle_agent(self, job: Job, link=None) -> Result:
        link = link or self.link
        args = job.args if isinstance(job.args, dict) else {}
        task = str(args.get("task") or args.get("query") or job.intent).strip()
        start = _start_url(args, allow_search=False)
        if not task:
            task = f"Complete the browser task at {start}" if start else "Complete the browser task."
        if not start:
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": "browser task has no resolved real site; refusing search fallback"})

        agent = self.agent_factory(
            link,
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
            mutation_attempted = bool(
                result.get("commerce_recipe")
                and any(
                    ((state.get("mutation") or {}).get("changed"))
                    for state in (result.get("page_states") or [])
                    if isinstance(state, dict)
                )
            )
            if mutation_attempted:
                result["non_retryable_real_mutation"] = True
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
        # M4 HONESTY (audit #2 — never fake done): the agent's non-empty answer is its SELF-REPORT, not
        # proof. On the real model a JUDGE must verify the result before we call it success; an
        # unverified/failed task is handed back to the human, never reported as a fake success. (Stub/mock
        # — the test path with no real browser — keeps prior behavior so the suite is unaffected.)
        from ..core.gateway import PROVIDER_OPENROUTER
        if getattr(self.gateway, "provider", None) == PROVIDER_OPENROUTER:
            try:
                from ..agent.webvoyager import judge as _judge
                verdict = await _judge(self.gateway, task, result, image=shot)
            except Exception:
                verdict = {"success": False, "reason": "judge unavailable"}
            result["judgment"] = verdict
            if not verdict.get("success"):
                return Result(job_id=job.id, status=JobStatus.needs_human, proof=proof, output=result)
        return Result(job_id=job.id, status=JobStatus.success, proof=proof, output=result)
