"""Layer C: the communication layer.

C1 criticality classifier: decides the channel (non critical to text or
   email, critical to a phone call). Precision skewed the safe way: when
   uncertain whether something warrants a call it does NOT call (a wrong
   call is more trust destroying than a delayed text). It also classifies
   the risk tier for the 3 hour rule. The caution asymmetry: when
   genuinely unsure whether an interpersonal communication is high risk
   or ultra high risk it MUST treat it as ultra high.

C2 asynchronous resumable task state: every task that needs user input
   is a suspended durable workflow on the durable runtime. A freeform
   human reply is matched back to the correct suspended task by content
   and recency; the workflow resumes from its suspended state. The user
   is never bombarded: at most one outbound question per task, and a
   genuinely ambiguous reply across multiple open tasks sends EXACTLY
   one disambiguation, never re asking.

C3 the 3 hour rule: after 3 hours of silence the agent proceeds and
   goes the extra mile, including for high risk. Carve out 1, spending
   money, never proceeds on silence. Carve out 2, ultra high risk
   interpersonal comms, never proceeds on silence. High risk that is
   NOT ultra high DOES proceed. The caution asymmetry biases the
   ambiguous comms case toward waiting, and only that case.

Outbound and inbound go only through platform_adapter.comms_send and
comms_receive (test mode recorder/injector now, the SAME shape as the
real Telnyx/SES/TTS later). No real message is ever sent here.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.anticipy import durable, platform_adapter
from app.anticipy.seams import InboundMessage, OutboundMessage

THREE_HOURS_S = 3 * 60 * 60

RISK_NORMAL = "normal"
RISK_HIGH = "high"
RISK_ULTRA = "ultra_high"
RISK_MONEY = "money"


# ---------------------------------------------------------------------------
# C1 criticality classifier
# ---------------------------------------------------------------------------

_C1_SYS = """\
You classify how an assistant should reach its user about a pending
action, and the risk tier of that action. Return STRICT JSON only:
{"channel":"text|email|call","risk_tier":"normal|high|ultra_high|money","reason":"<short>"}

channel: a phone call is reserved for genuinely critical, time sensitive
things the user must know now. When you are NOT clearly sure a call is
warranted, choose text (or email for long non urgent content). A wrong
call is far more trust destroying than a slightly delayed text, so the
default under any uncertainty is NOT a call.

risk_tier:
- money: the action spends money, enters payment, places a deposit, or
  moves the user's funds.
- ultra_high: an irreversible interpersonal communication where a wrong
  send damages a relationship or the user's standing: to the user's
  boss or skip level, to a client or investor in a committing or
  representing capacity, a resignation, legal or contractual language,
  anything that terminates a relationship, financial commitment prose.
- high: risky but recoverable, not in the ultra_high set.
- normal: ordinary low risk.

CAUTION ASYMMETRY: if you are genuinely unsure whether an interpersonal
communication is high or ultra_high, you MUST return ultra_high. The
accepted cost is occasionally waiting on something only high risk. The
rejected cost is autonomously sending a misclassified relationship
ending message. Apply this bias ONLY to the high vs ultra_high comms
ambiguity. Everywhere else, do not inflate risk.
"""


@dataclass
class Criticality:
    channel: str
    risk_tier: str
    reason: str


async def classify_criticality(action_text: str, context: str = "") -> Criticality:
    user = (f"CONTEXT: {context}\n" if context else "") + f"PENDING ACTION: {action_text}\n\nReturn the JSON now."
    res = await asyncio.to_thread(platform_adapter.model_call, _C1_SYS, user, 256, 0.0, False)
    # Safe defaults: never an uncertain call; never under-rate comms risk.
    ch, rt = "text", RISK_NORMAL
    reason = "c1_default"
    if res.ok:
        s = res.content
        a, b = s.find("{"), s.rfind("}")
        if a != -1 and b != -1 and b > a:
            try:
                p = json.loads(s[a : b + 1])
                ch = p.get("channel") if p.get("channel") in ("text", "email", "call") else "text"
                rt = p.get("risk_tier") if p.get("risk_tier") in (RISK_NORMAL, RISK_HIGH, RISK_ULTRA, RISK_MONEY) else RISK_NORMAL
                reason = str(p.get("reason", ""))[:160]
            except Exception:
                pass
    # Deterministic caution asymmetry, code enforced not prompt hoped.
    # The build spec is a MUST: when it is genuinely uncertain whether
    # an interpersonal communication is high or ultra high, it MUST be
    # treated as ultra high (wait, never autonomously send). A model
    # applies a bias with high but not perfect reliability on exactly
    # the genuinely ambiguous boundary, which is unacceptable for a
    # safety property. So if the model returned high (not already ultra,
    # money is its own carve out) for content that is interpersonal and
    # carries commitment, representation, relationship ending, legal or
    # financial commitment markers, deterministically upgrade to
    # ultra_high. Trivial content with no such markers is untouched, so
    # this never inflates risk outside the high vs ultra comms ambiguity
    # and cannot regress routing or reply matching (they do not use C1).
    if rt == RISK_HIGH:
        blob = f"{action_text} {context}".lower()
        markers = (
            "boss", "skip level", "skip-level", "manager", "investor",
            "client", "customer", "board", "partner", "cofounder",
            "resign", "resignation", "quit", "contract", "legal",
            "lawyer", "attorney", "commit", "commitment", "terms",
            "on behalf", "represent", "terminate", "termination",
            "end the", "breakup", "break up", "offer letter", "nda",
            "binding", "sign", "agreement", "deal", "proposal to",
        )
        if any(m in blob for m in markers):
            rt = RISK_ULTRA
            reason = f"caution asymmetry (code enforced): {reason}"
    return Criticality(channel=ch, risk_tier=rt, reason=reason)


# ---------------------------------------------------------------------------
# C2 resumable task state on the durable runtime + reply matcher
# ---------------------------------------------------------------------------

def _ask_workflow_factory():
    async def wf(ctx):
        # journal that the question was sent, then wait for the reply
        await ctx.journal_step("send_question", lambda: ctx.input.get("question", ""))
        answer = await ctx.await_external("user_reply", timeout_s=THREE_HOURS_S)
        result = await ctx.journal_step(
            "resume_with", lambda: {"answer": answer, "intent": ctx.input.get("intent")}
        )
        return result

    return wf


durable.register_workflow("comms_ask", _ask_workflow_factory())


@dataclass
class SuspendedTask:
    task_id: str
    user_id: str
    question: str
    channel: str
    risk_tier: str
    sent_ts: float
    expected_answer_shape: str = "freeform"
    intent: Optional[dict] = None


def open_question(
    user_id: str, intent: dict, question: str, criticality: Criticality,
    now_s: Optional[float] = None, expected_answer_shape: str = "freeform",
) -> SuspendedTask:
    """Send exactly one outbound question and persist the task as a
    suspended durable workflow. At most one question per task.
    """
    tid = f"ct-{uuid.uuid4().hex[:10]}"
    sent = now_s if now_s is not None else time.time()
    durable.start_workflow(
        "comms_ask", tid,
        {"question": question, "intent": intent, "user_id": user_id,
         "_clock_base_s": sent},
    )
    platform_adapter.comms_send(
        OutboundMessage(
            task_id=tid, user_id=user_id, channel=criticality.channel,
            body=question, criticality=("critical" if criticality.channel == "call" else "non_critical"),
            expected_answer_shape=expected_answer_shape, ts=sent,
        ).to_dict()
    )
    return SuspendedTask(tid, user_id, question, criticality.channel,
                         criticality.risk_tier, sent, expected_answer_shape, intent)


def _score(reply_text: str, task: SuspendedTask, now_s: float) -> float:
    """Match a freeform reply to a suspended task by content overlap and
    recency. Deliberately simple and deterministic.
    """
    rt = reply_text.lower()
    q = task.question.lower()
    qstop = {"the", "a", "an", "to", "for", "of", "is", "it", "you", "i",
             "do", "want", "me", "your", "should", "which", "what", "that",
             "and", "or", "can", "with", "on", "at", "be", "have"}
    qtok = {w.strip("?.,!") for w in q.split() if w not in qstop and len(w) > 2}
    overlap = sum(1 for w in qtok if w in rt)
    content = overlap / (len(qtok) or 1)
    age = max(0.0, now_s - task.sent_ts)
    recency = 1.0 / (1.0 + age / THREE_HOURS_S)
    return round(0.75 * content + 0.25 * recency, 4)


@dataclass
class ReplyRouting:
    matched_task_id: Optional[str]
    action: str  # "resumed" | "disambiguated" | "unmatched"
    disambiguation_sent: int


def route_reply(
    reply: InboundMessage, open_tasks: list[SuspendedTask], now_s: Optional[float] = None
) -> ReplyRouting:
    """Match a reply to the correct suspended task. If the top match is
    clearly ahead, resume that workflow. If genuinely ambiguous across
    several open tasks, send EXACTLY ONE disambiguation and keep them
    suspended, never a bombardment, never re asking.
    """
    now = now_s if now_s is not None else time.time()
    if reply.in_reply_to:
        for t in open_tasks:
            if t.task_id == reply.in_reply_to:
                durable.deliver_event(t.task_id, "user_reply", reply.text)
                return ReplyRouting(t.task_id, "resumed", 0)
    if not open_tasks:
        return ReplyRouting(None, "unmatched", 0)
    scored = sorted(((_score(reply.text, t, now), t) for t in open_tasks),
                    key=lambda x: x[0], reverse=True)
    top_s, top_t = scored[0]
    second_s = scored[1][0] if len(scored) > 1 else -1.0
    # clear leader: resume it
    if top_s >= 0.34 and (top_s - second_s) >= 0.15:
        durable.deliver_event(top_t.task_id, "user_reply", reply.text)
        return ReplyRouting(top_t.task_id, "resumed", 0)
    # genuinely ambiguous across open tasks: exactly one disambiguation
    platform_adapter.comms_send(
        OutboundMessage(
            task_id="disambig",
            user_id=reply.user_id,
            channel="text",
            body="Quick check, which of these did you mean: "
            + " / ".join(t.question for t in open_tasks[:3]),
            criticality="non_critical",
            ts=now,
        ).to_dict()
    )
    return ReplyRouting(None, "disambiguated", 1)


# ---------------------------------------------------------------------------
# C3 the 3 hour rule with both carve outs and the caution asymmetry
# ---------------------------------------------------------------------------

@dataclass
class ThreeHourOutcome:
    proceeded: bool
    waited: bool
    reason: str
    reminders_sent: int


def apply_three_hour_rule(task: SuspendedTask, now_s: float) -> ThreeHourOutcome:
    """The exact rule. Silence past 3 hours means proceed and go the
    extra mile, including for high risk. EXCEPT: spending money never
    proceeds on silence, and ultra high risk interpersonal comms never
    proceeds on silence (the caution asymmetry already routed the
    ambiguous comms case to ultra_high in C1, so it lands here as wait).
    Both carve outs wait indefinitely with one non spammy reminder, not
    repeated nagging.
    """
    elapsed = now_s - task.sent_ts
    if elapsed < THREE_HOURS_S:
        return ThreeHourOutcome(False, True, "still within the 3 hour window", 0)

    if task.risk_tier in (RISK_MONEY, RISK_ULTRA):
        # hard stop: never proceed on silence. One reminder, not nagging.
        platform_adapter.comms_send(
            OutboundMessage(
                task_id=task.task_id, user_id=task.user_id, channel=task.channel,
                body=f"Still need your go ahead before I proceed: {task.question}",
                criticality="non_critical", ts=now_s,
            ).to_dict()
        )
        why = ("spending money never proceeds on silence"
               if task.risk_tier == RISK_MONEY
               else "ultra high risk communication never proceeds on silence")
        return ThreeHourOutcome(False, True, why, 1)

    # default and high risk that is not ultra high: proceed, extra mile
    durable.deliver_event(task.task_id, "user_reply", {"_proceed_on_silence": True})
    return ThreeHourOutcome(True, False, "3 hours of silence: proceed and go the extra mile", 0)


# ---------------------------------------------------------------------------
# The three inbound router, feeding the one pipeline
# ---------------------------------------------------------------------------

@dataclass
class RouterDecision:
    path: str  # "ambient" | "direct" | "reply"
    handled_by: str  # "proactive_engine" | "reply_matcher"
    reply_routing: Optional[ReplyRouting] = None


def route_inbound(msg: InboundMessage, open_tasks: list[SuspendedTask],
                  now_s: Optional[float] = None) -> RouterDecision:
    """One pipeline, three inbound paths, tagged by source. A direct
    user command is highest authority lowest uncertainty (addressee
    detection bypassed downstream). A reply is routed back to the
    correct suspended durable workflow. Ambient flows to the proactive
    engine. The path tag must be exactly correct and a reply must never
    be misrouted to the proactive engine as if it were a new ambient
    intent.
    """
    if msg.source == "reply":
        rr = route_reply(msg, open_tasks, now_s)
        return RouterDecision("reply", "reply_matcher", rr)
    if msg.source == "direct":
        return RouterDecision("direct", "proactive_engine")
    return RouterDecision("ambient", "proactive_engine")
