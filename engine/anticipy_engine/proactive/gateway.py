"""Plan Baby Steps proactive gateway ledger.

This module is intentionally small and append-only. It does not decide what the
assistant should do; it records how existing lanes moved through the product
circuit so browser, memory, voice/text, brain, UI, proof, and follow-up can point
to one shared event contract.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .contracts import (
    GatewayActionPlan,
    GatewayBrainAssessment,
    GatewayBrowserRun,
    GatewayChannelMirror,
    GatewayFollowUp,
    GatewayMemoryMutation,
    GatewayProof,
    ProactiveGatewayEnvelope,
)


_BASE_TAGS = [
    "WB-PROACTIVE",
    "ST-ACT-PREPARE-ASK-SILENT",
    "OPS-BASIC-PLUMBING",
    "ST-NO-FAKE-DONE",
]


def _short(text: Any, limit: int = 700) -> str:
    s = str(text or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "..."


def _compact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _compact(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [_compact(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _source_kind(source: str) -> str:
    s = (source or "").strip().lower()
    if any(x in s for x in ("listen", "mic", "deepgram", "pendant")):
        return "mic"
    if any(x in s for x in ("upload", "mp3", "audio", "file")):
        return "upload"
    if s in {"sms", "text", "twilio"}:
        return "sms"
    if any(x in s for x in ("call", "voice", "conversation_relay")):
        return "call"
    if any(x in s for x in ("browser", "chrome", "web", "extension")):
        return "browser" if "extension" not in s else "extension"
    if any(x in s for x in ("memory", "remember")):
        return "memory"
    if any(x in s for x in ("brain", "model", "proactive")):
        return "brain"
    if any(x in s for x in ("app", "phase_zero", "transcript", "typed")):
        return "app"
    return "manual"


def _tags_for_source(source: str, *, has_browser: bool = False, has_memory: bool = False,
                     needs_approval: bool = False, follow_up: bool = False) -> list[str]:
    tags = list(_BASE_TAGS)
    kind = _source_kind(source)
    if kind in {"mic", "upload", "app"}:
        tags.extend(["ST-ACTIVE-LISTENING", "ST-INFER-REAL-TASKS", "ST-IGNORE-VENTS"])
    if kind in {"sms", "call"}:
        tags.append("UX-TEXT-FIRST")
    if kind in {"browser", "extension"} or has_browser:
        tags.append("ST-BROWSER-REAL-SYSTEMS")
    if kind == "memory" or has_memory:
        tags.append("ST-MEMORY-COMPOUNDS")
    if needs_approval:
        tags.append("ST-MONEY-IRREVERSIBLE-CONFIRM")
    if follow_up:
        tags.append("ST-FOLLOW-THROUGH")
    out: list[str] = []
    for tag in tags:
        if tag not in out:
            out.append(tag)
    return out


def _merge_tags(*groups: Any) -> list[str]:
    out: list[str] = []
    for group in groups:
        if group is None:
            continue
        if isinstance(group, str):
            items = [group]
        elif isinstance(group, (list, tuple, set)):
            items = group
        else:
            continue
        for item in items:
            tag = str(item or "").strip()
            if tag and tag not in out:
                out.append(tag)
    return out


def _card_needs_approval(card: dict[str, Any]) -> bool:
    execution = card.get("execution") if isinstance(card.get("execution"), dict) else {}
    return (
        card.get("disposition") == "ask"
        or card.get("status") == "waiting"
        or execution.get("decision") in {"ask", "held"}
        or bool(execution.get("ask_id"))
    )


def _status_from_cards(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return "ignored"
    if any(c.get("status") in {"running", "preparing"} for c in cards):
        return "working"
    if any(_card_needs_approval(c) for c in cards):
        return "needs_approval"
    if all(c.get("disposition") == "remember" or c.get("status") == "done" for c in cards):
        return "remembered" if all(c.get("disposition") == "remember" for c in cards) else "done"
    if any(c.get("status") == "blocked" or c.get("disposition") == "blocked" for c in cards):
        return "blocked"
    return "understood"


def _brain_assessment_for_cards(cards: list[dict[str, Any]],
                                observed: list[dict[str, Any]]) -> GatewayBrainAssessment:
    if not cards:
        return GatewayBrainAssessment(
            classification="ignored" if observed else "unknown",
            realness="ambient" if observed else "unknown",
            should_ignore=bool(observed),
            ignored_reasons=["no_actionable_owner_task"] if observed else [],
            evidence=[
                {"line_no": o.get("line_no"), "text_preview": _short(o.get("text"), 180)}
                for o in observed[:8]
            ],
        )

    dispositions = {str(c.get("disposition") or "") for c in cards}
    has_memory = "remember" in dispositions
    has_work = any(d in {"do", "ask"} for d in dispositions)
    has_blocked = "blocked" in dispositions or any(c.get("status") == "blocked" for c in cards)
    needs_ask = any(_card_needs_approval(c) for c in cards)
    if has_blocked:
        classification = "blocked"
    elif has_memory and has_work:
        classification = "mixed"
    elif has_memory:
        classification = "memory"
    elif has_work or needs_ask:
        classification = "actionable"
    else:
        classification = "unknown"
    return GatewayBrainAssessment(
        classification=classification,  # type: ignore[arg-type]
        realness="mixed" if has_blocked and (has_memory or has_work) else "real",
        should_act=any(str(c.get("disposition") or "") == "do" for c in cards),
        should_ask=needs_ask,
        should_remember=has_memory,
        should_ignore=False,
        evidence=[
            {
                "card_id": c.get("id"),
                "title": c.get("title"),
                "source_text": _short(c.get("source_text"), 220),
                "disposition": c.get("disposition"),
                "route": c.get("route"),
            }
            for c in cards[:10]
        ],
    )


def _attach_pipeline_brain_assessment(assessment: GatewayBrainAssessment,
                                      brain_decisions: Any) -> GatewayBrainAssessment:
    """Merge the canonical decision-pipeline evidence into the gateway record."""
    if not isinstance(brain_decisions, dict):
        return assessment
    decisions = [d for d in (brain_decisions.get("decisions") or []) if isinstance(d, dict)]
    if not decisions:
        return assessment
    evidence = [
        {
            "speaker": d.get("speaker"),
            "addressee": d.get("addressee"),
            "actor": d.get("actor"),
            "realness": d.get("realness"),
            "decision": d.get("decision"),
            "task_text": _short(d.get("task_text"), 180),
            "evidence_span": _short(d.get("evidence_span"), 220),
            "confidence": d.get("confidence"),
            "reason": _short(d.get("reason"), 220),
            "source_truth_case_id": d.get("source_truth_case_id"),
        }
        for d in decisions[:30]
    ]
    actionable = [d for d in decisions if d.get("decision") in {"ask", "act", "block", "follow_up"}]
    ignored = [d for d in decisions if d.get("decision") == "ignore"]
    if actionable:
        if any(d.get("decision") == "block" for d in actionable):
            assessment.classification = "blocked"
        elif any(d.get("decision") == "ask" for d in actionable):
            assessment.classification = "actionable"
        else:
            assessment.classification = "actionable"
        realnesses = {str(d.get("realness") or "") for d in decisions}
        assessment.realness = "mixed" if len(realnesses) > 1 else (next(iter(realnesses)) or "real")  # type: ignore[assignment]
        assessment.should_ask = assessment.should_ask or any(d.get("decision") == "ask" for d in actionable)
        assessment.should_act = assessment.should_act or any(d.get("decision") == "act" for d in actionable)
    elif ignored:
        assessment.classification = "ignored"
        assessment.should_ignore = True
        assessment.ignored_reasons = [
            str(d.get("reason") or d.get("realness") or "ignored")[:180]
            for d in ignored[:8]
        ]
        realnesses = [str(d.get("realness") or "") for d in ignored if d.get("realness")]
        if realnesses:
            assessment.realness = "mixed" if len(set(realnesses)) > 1 else realnesses[0]  # type: ignore[assignment]
    assessment.evidence = evidence + assessment.evidence
    assessment.reuse_refs = _merge_tags(
        assessment.reuse_refs,
        brain_decisions.get("reuse_refs"),
        ["live:anticipy_engine.proactive.decision_pipeline"],
    )
    return assessment


class ProactiveGatewayLedger:
    """Append-only JSONL ledger for the canonical gateway envelope."""

    def __init__(self, data_dir: str | Path, glassbox=None) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "proactive_gateway.jsonl"
        self.glassbox = glassbox

    def emit(self, envelope: ProactiveGatewayEnvelope) -> dict[str, Any]:
        payload = envelope.to_wire()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, sort_keys=True) + "\n")
        if self.glassbox:
            try:
                self.glassbox.log("proactive_gateway_event", {
                    "event_id": envelope.event_id,
                    "source": envelope.source,
                    "status": envelope.status,
                    "tasks": len(envelope.possible_tasks),
                })
            except Exception:
                pass
        return payload

    def recent(self, limit: int = 50) -> dict[str, Any]:
        if not self.path.exists():
            return {"events": [], "count": 0, "path": str(self.path)}
        rows: list[dict[str, Any]] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return {"events": [], "count": 0, "path": str(self.path)}
        for line in reversed(lines[-max(1, limit * 3):]):
            if len(rows) >= limit:
                break
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return {"events": rows, "count": len(rows), "path": str(self.path)}

    def record_owner_ingest(self, *, event_id: str, source: str, text: str,
                            meta: dict[str, Any] | None, result: dict[str, Any],
                            execute_actions: bool) -> dict[str, Any]:
        cards = [c for c in (result.get("cards") or []) if isinstance(c, dict)]
        observed = [o for o in (result.get("observed_lines") or []) if isinstance(o, dict)]
        possible_tasks = []
        actions: list[GatewayActionPlan] = []
        mutations: list[GatewayMemoryMutation] = []
        proofs: list[GatewayProof] = []
        has_browser = False
        follow_up_at = None

        for card in cards:
            execution = card.get("execution") if isinstance(card.get("execution"), dict) else {}
            route = str(card.get("route") or execution.get("route") or "")
            action = str(card.get("action") or "")
            has_browser = has_browser or route == "browser" or action == "browser_action"
            ask_id = execution.get("ask_id") or card.get("ask_id")
            possible_tasks.append({
                "card_id": card.get("id"),
                "title": card.get("title"),
                "status": card.get("status"),
                "disposition": card.get("disposition"),
                "route": route,
                "action": action,
                "approval_required": _card_needs_approval(card),
            })
            actions.append(GatewayActionPlan(
                route=route,
                action=action,
                title=str(card.get("title") or ""),
                status=str(card.get("status") or card.get("disposition") or "observed"),
                approval_required=_card_needs_approval(card),
                card_id=card.get("id"),
                ask_id=ask_id,
                args=_compact(card.get("args") if isinstance(card.get("args"), dict) else {}),
            ))
            for p in card.get("proof") or []:
                if not isinstance(p, dict):
                    continue
                ptype = str(p.get("type") or "")
                proofs.append(GatewayProof(
                    type=ptype,
                    scope=str(p.get("drawer") or p.get("status") or p.get("goal_state") or ""),
                    summary=_short(p.get("text") or p.get("answer") or ptype, 260),
                    ref=p.get("memory_id") or p.get("goal_id") or p.get("path"),
                    data=_compact(p),
                ))
                if ptype == "memory_write":
                    mutations.append(GatewayMemoryMutation(
                        drawer=p.get("drawer") or "unknown",
                        operation="written",
                        memory_id=p.get("memory_id"),
                        text=str(card.get("source_text") or ""),
                        confidence=float(card.get("confidence") or 1.0),
                        proof=_compact(p),
                    ))
                if ptype == "memory_read_back":
                    mutations.append(GatewayMemoryMutation(
                        drawer="unknown",
                        operation="read_back",
                        memory_id=p.get("memory_id"),
                        text=str(p.get("text") or ""),
                        proof=_compact(p),
                    ))
            fu = card.get("follow_up")
            if isinstance(fu, dict):
                follow_up_at = fu.get("when_ts") or follow_up_at

        needs_approval = any(_card_needs_approval(c) for c in cards)
        has_memory = bool(mutations)
        source_tags = _merge_tags(
            _tags_for_source(
                source, has_browser=has_browser, has_memory=has_memory,
                needs_approval=needs_approval, follow_up=follow_up_at is not None),
            (meta or {}).get("source_of_truth_tags"),
        )
        brain_assessment = _attach_pipeline_brain_assessment(
            _brain_assessment_for_cards(cards, observed),
            result.get("brain_decisions"),
        )
        envelope = ProactiveGatewayEnvelope(
            event_id=event_id,
            user_id=str((meta or {}).get("user_id") or "default"),
            source=_source_kind(source),  # type: ignore[arg-type]
            source_label=source,
            raw_input_ref={
                "text_preview": _short(text, 500),
                "text_chars": len(text or ""),
                "meta": _compact(meta or {}),
                "execute_actions": bool(execute_actions),
            },
            structured_summary=self._summary_for_cards(source, cards, observed),
            facts=[
                {"text": c.get("source_text"), "card_id": c.get("id")}
                for c in cards if c.get("disposition") == "remember"
            ],
            open_loops=[
                {"text": c.get("source_text"), "title": c.get("title"), "card_id": c.get("id"),
                 "status": c.get("status") or c.get("disposition")}
                for c in cards if c.get("disposition") != "remember"
            ],
            possible_tasks=possible_tasks,
            brain_assessment=brain_assessment,
            suggested_actions=actions,
            memory_mutations=mutations,
            approval_required=needs_approval,
            channel_mirrors=self._channel_mirrors(source, needs_approval),
            proof=proofs[:50],
            follow_up=GatewayFollowUp(
                status="scheduled" if follow_up_at is not None else "none",
                at=follow_up_at if isinstance(follow_up_at, (int, float)) else None,
                reason="card_follow_up" if follow_up_at is not None else "",
            ),
            follow_up_at=follow_up_at if isinstance(follow_up_at, (int, float)) else None,
            source_of_truth_tags=source_tags,
            confidence=min([float(c.get("confidence") or 1.0) for c in cards], default=1.0),
            status=_status_from_cards(cards),  # type: ignore[arg-type]
        )
        return self.emit(envelope)

    def record_browser_result(self, *, ask_id: str, task: str, success: bool, answer: str,
                              url: str | None, screenshot: bool,
                              screenshot_path: str | None = None,
                              trace: dict[str, Any] | None = None,
                              source_event_id: str | None = None) -> dict[str, Any]:
        envelope = ProactiveGatewayEnvelope(
            source="browser",
            source_label="browser_result",
            raw_input_ref={"ask_id": ask_id, "source_gateway_event_id": source_event_id},
            structured_summary=(
                f"Browser completed: {_short(answer, 180)}"
                if success and answer else f"Browser could not complete: {_short(task, 180)}"
            ),
            possible_tasks=[{"card_id": ask_id, "title": task, "route": "browser", "status": "done" if success else "failed"}],
            brain_assessment=GatewayBrainAssessment(
                classification="actionable",
                realness="real",
                should_act=True,
                evidence=[{"ask_id": ask_id, "task": task, "success": bool(success)}],
            ),
            suggested_actions=[GatewayActionPlan(
                route="browser",
                action="browser_action",
                title=task,
                status="done" if success else "failed",
                card_id=ask_id,
            )],
            browser_run=GatewayBrowserRun(
                task=task,
                final_url=url,
                success=bool(success),
                answer=_short(answer, 1000),
                screenshot=bool(screenshot),
                screenshot_path=screenshot_path,
                trace=_compact(trace or {}),
            ),
            proof=[GatewayProof(
                type="browser_receipt",
                scope="browser",
                summary=_short(answer or task, 260),
                ref=url,
                data={"ask_id": ask_id, "success": bool(success), "screenshot": bool(screenshot)},
            )],
            source_of_truth_tags=_tags_for_source("browser", has_browser=True),
            confidence=1.0 if success else 0.4,
            status="done" if success else "failed",
        )
        return self.emit(envelope)

    def record_approval(self, *, ask_id: str, approved: bool, source: str = "app",
                        result: dict[str, Any] | None = None,
                        action: str | None = None) -> dict[str, Any]:
        state = str((result or {}).get("state") or ("working" if approved else "declined"))
        envelope = ProactiveGatewayEnvelope(
            source=_source_kind(source),  # type: ignore[arg-type]
            source_label=source,
            raw_input_ref={"ask_id": ask_id, "result": _compact(result or {})},
            structured_summary=("Approved" if approved else "Declined") + f" {ask_id}",
            possible_tasks=[{"ask_id": ask_id, "status": state, "approved": bool(approved)}],
            suggested_actions=[GatewayActionPlan(
                action=action or "",
                status=state,
                approval_required=False,
                ask_id=ask_id,
            )],
            brain_assessment=GatewayBrainAssessment(
                classification="actionable",
                realness="real",
                should_act=bool(approved),
                should_ask=False,
                evidence=[{"ask_id": ask_id, "approved": bool(approved), "state": state}],
            ),
            channel_mirrors=self._channel_mirrors(source, needs_approval=False),
            proof=[GatewayProof(
                type="resolution",
                scope="approval",
                summary="Owner approved the task." if approved else "Owner declined the task.",
                ref=ask_id,
                data={"approved": bool(approved), "state": state},
            )],
            source_of_truth_tags=_tags_for_source(source, needs_approval=True),
            status="working" if approved else "stopped",
        )
        return self.emit(envelope)

    def record_listen_status(self, *, source: str, listening: bool,
                             status: str | None = None,
                             details: dict[str, Any] | None = None) -> dict[str, Any]:
        envelope = ProactiveGatewayEnvelope(
            source="mic",
            source_label=source,
            raw_input_ref=_compact(details or {}),
            structured_summary="Listening started." if listening else "Listening stopped.",
            brain_assessment=GatewayBrainAssessment(
                classification="unknown",
                realness="unknown",
                evidence=[{"source": source, "listening": bool(listening), **_compact(details or {})}],
            ),
            channel_mirrors=[GatewayChannelMirror(channel="app", status="available")],
            source_of_truth_tags=_tags_for_source(source),
            status=("listening" if listening else (status or "stopped")),  # type: ignore[arg-type]
        )
        return self.emit(envelope)

    def record_voice_turn(self, *, prompt: str, handoff: dict[str, Any],
                          channel: str = "voice") -> dict[str, Any]:
        verdict = str((handoff or {}).get("verdict") or (handoff or {}).get("event") or "observed")
        envelope = ProactiveGatewayEnvelope(
            source="call",
            source_label=channel,
            raw_input_ref={"text_preview": _short(prompt, 500), "handoff": _compact(handoff)},
            structured_summary=f"Voice turn heard and judged: {verdict}.",
            brain_assessment=GatewayBrainAssessment(
                classification="actionable" if verdict.lower() in {"act", "ask", "notify"} else "ignored",
                realness="unknown",
                should_ask=verdict.lower() == "ask",
                should_ignore=verdict.lower() in {"silent", "ignore", "ignored"},
                evidence=[{"verdict": verdict, "handoff": _compact(handoff)}],
            ),
            channel_mirrors=[
                GatewayChannelMirror(channel="voice", status="delivered", message=verdict),
                GatewayChannelMirror(channel="app", status="available"),
            ],
            source_of_truth_tags=_tags_for_source(channel),
            confidence=1.0,
            status="understood",
        )
        return self.emit(envelope)

    @staticmethod
    def _summary_for_cards(source: str, cards: list[dict[str, Any]],
                           observed: list[dict[str, Any]]) -> str:
        if cards:
            first = cards[0]
            more = "" if len(cards) == 1 else f" plus {len(cards) - 1} more"
            return f"{source} produced {len(cards)} card(s): {_short(first.get('title'), 160)}{more}."
        if observed:
            return f"{source} was heard, but no task needed action."
        return f"{source} produced no actionable output."

    @staticmethod
    def _channel_mirrors(source: str, needs_approval: bool) -> list[GatewayChannelMirror]:
        mirrors = [GatewayChannelMirror(channel="app", status="available")]
        kind = _source_kind(source)
        if kind in {"sms", "call"}:
            mirrors.append(GatewayChannelMirror(
                channel="text" if kind == "sms" else "voice",
                status="delivered",
            ))
        elif needs_approval:
            mirrors.append(GatewayChannelMirror(channel="text", status="queued"))
        return mirrors
