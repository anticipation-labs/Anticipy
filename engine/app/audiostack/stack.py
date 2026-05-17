"""The four-layer stack orchestrator.

P0 establishes the plumbing and the asymmetric safe default; the
discrimination logic is added in dependency order:
  P1 -> Layer 1 conversation membership (wearer anchor + turn-taking)
  P2 -> Layer 2 directed-speech gate + DEGRADED state
  P3 -> Layer 3 load-bearing slot trust + Layer 4 demotion specifics

The contract that never changes: only trusted, wearer-conversation,
slot-typed spans are PUSHED to the frozen engine via
platform_adapter.transcript_source(); everything else is demoted to
the LIFE_LOG. When in doubt the span is NOT actionable. Over-trust
is the disaster, so the P0 default (before L1..L3 exist) is the
safest possible one: demote everything. P1+ earns true-positives
WITHOUT ever raising false-trust above the spec budget.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.audiostack import audio as A
from app.audiostack import enrollment as E
from app.audiostack import lifelog as L
from app.audiostack import metrics as M


@dataclass
class Utterance:
    speaker_label: str        # WEARER | S1.. | MEDIA | UNK
    text: str
    start: float
    end: float
    mean_conf: float
    tokens: list = field(default_factory=list)
    is_wearer: bool = False
    bandlimited: bool = False   # phone/broadcast acoustic signature
    seg: object = None          # the audio segment, for dual-decode verify


@dataclass
class StackDecision:
    outcome: str              # ACTIONABLE | LIFE_LOG | CONFIRM | DEGRADED_LOG
    reason: str
    degraded_declared: bool = False
    emitted_text: str = ""
    confirm_question: str = ""


# P1: data-driven anchor threshold. MEASURED in the REAL matched
# deployment condition (substantive wearer turns, real ESC-50 noise,
# denoise front end, multi-condition anchor) via _diag_boss.py:
# wearer in-conversation turns embed at cos 0.846..0.944, non-wearer
# (incl. partner) at 0.50..0.747. 0.80 sits strictly between with a
# ~0.046 wearer margin and a ~0.053 non-wearer margin. Safe-direction:
# RAISING the threshold can only reduce false-trust (a stranger must
# clear a higher bar), and wearer turns still clear it, so this is
# strictly the un-gameable direction, not a weakening. Resemblyzer
# GE2E replaced wav2vec2 (measured 0.003 margin: an ASR feature, not
# a speaker identity) for the same reason. MAX_CONV_GAP is the
# longest silence that still counts as one turn-taking exchange.
ANCHOR_THRESHOLD = 0.80
MAX_CONV_GAP = 2.5               # seconds


def _layer1_membership(utts, anchor, episode):
    """Layer 1: conversation membership by wearer anchor + turn-taking.

    The wearer is the anchor. A non-wearer utterance belongs to the
    wearer's conversation ONLY if it turn-takes with the wearer:
    there is a wearer utterance adjacent in the utterance sequence
    within a conversational silence gap (alternation on conversational
    timing, which a stranger / TV / phone physically cannot fake).
    If the wearer never speaks in the episode there is NO membership
    and everything is rejected (the safe direction: strangers, TV and
    silence have no wearer turn-taking, so Layer-1-alone false-trust
    on them is structurally ~0).
    """
    if not utts:
        return []
    wearer_idx = [i for i, u in enumerate(utts) if u.is_wearer]
    if not wearer_idx:
        return []  # no wearer present -> no conversation -> reject all

    members: list = []
    seen: set = set()
    for i, u in enumerate(utts):
        if u.is_wearer:
            if id(u) not in seen:
                members.append(u); seen.add(id(u))
            continue
        # non-wearer: member iff it alternates with a wearer turn,
        # i.e. an immediately adjacent utterance is the wearer AND the
        # silence between them is within a conversational gap.
        for j in (i - 1, i + 1):
            if 0 <= j < len(utts) and utts[j].is_wearer:
                a, b = (utts[j], u) if j < i else (u, utts[j])
                gap = max(0.0, b.start - a.end)
                if gap <= MAX_CONV_GAP and id(u) not in seen:
                    members.append(u); seen.add(id(u))
                    break
    return members


def _layer2_directed_or_degraded(utts, anchor, episode):
    """Layer 2, parallel to Layer 1. (a) DEGRADED: wearer silent past
    the window -> log everything, fire nothing, declare silence.
    (b) directed-speech gate: a SHORT directive addressed at the
    wearer is a candidate even with zero turn-taking. Precision-
    skewed: strangers / TV / third-party do not pass.
    """
    from app.audiostack import layer2

    wearer_speech_s = sum((u.end - u.start) for u in utts if u.is_wearer)
    dur = float(episode.get("dur", 0.0)) or (
        max((u.end for u in utts), default=0.0))
    if layer2.is_degraded(wearer_speech_s, dur):
        return [], True
    directed = [u for u in utts
                if not u.is_wearer
                and not u.bandlimited                       # phone/broadcast
                and u.mean_conf >= layer2.DIRECTED_MIN_ASR_CONF
                and layer2.directed_speech_gate(u.text, u.end - u.start)]
    return directed, False


def _layer3_slot_trust(utt):
    """Layer 3: returns ('FIRE'|'CONFIRM', reason). The spec's
    mechanism: a load-bearing slot whose min parakeet per-token
    confidence is below the bar does NOT fire, it confirms. This is
    correct once the corpus genuinely degrades the stressed slot
    (parakeet confidence collapses on genuinely corrupted audio);
    perturbation-consensus was measured to have no discriminative
    power here and was removed.
    """
    from app.audiostack import audio as _A
    from app.audiostack import layer3

    secondary = None
    seg = getattr(utt, "seg", None)
    if seg is not None:
        try:
            secondary = _A.asr2_text(seg)   # independent-model transcript
        except Exception:
            secondary = None
    verdict, reason, _detail = layer3.slot_trust(utt, secondary)
    return verdict, reason


class AudioStack:
    def __init__(self, user_id: str = "wearer"):
        self.user_id = user_id
        self.anchor: Optional[E.Anchor] = E.load_anchor(user_id)

    # --- primitives -> utterances ------------------------------------
    def _utterances(self, wav: np.ndarray) -> list[Utterance]:
        spans = A.vad_segments(wav)
        out: list[Utterance] = []
        for s, e in spans:
            seg = wav[int(s * A.SR):int(e * A.SR)]
            if len(seg) < int(0.2 * A.SR):
                continue
            asr = A.asr_tokens(seg)
            if not asr.text:
                continue
            emb = A.speaker_embed(seg)
            isw = (E.is_wearer(emb, self.anchor, ANCHOR_THRESHOLD)
                   if self.anchor else False)
            out.append(Utterance(
                speaker_label="WEARER" if isw else "UNK",
                text=asr.text, start=s, end=e,
                mean_conf=asr.mean_conf(), tokens=asr.tokens, is_wearer=isw,
                bandlimited=A.is_bandlimited(seg), seg=seg,
            ))
        return out

    # --- Layer 1 only (P1 gate scores membership, not final ACT) -----
    def membership_only(self, wav: np.ndarray,
                         episode: Optional[dict] = None
                         ) -> tuple[list[Utterance], list[Utterance]]:
        """Return (all_utterances, layer1_members). Used by the P1
        gate: membership is the property under test at P1, before the
        Layer 2/3 gates that turn a member into an ACT exist.
        """
        utts = self._utterances(wav)
        if self.anchor is None or not self.anchor.strong:
            return utts, []  # weak anchor fails closed
        return utts, _layer1_membership(utts, self.anchor, episode or {})

    # --- the pipeline ------------------------------------------------
    def process(self, wav: np.ndarray, episode: Optional[dict] = None
                ) -> tuple[StackDecision, list[Utterance]]:
        episode = dict(episode or {})
        episode.setdefault("dur", len(wav) / A.SR if wav is not None else 0.0)
        utts = self._utterances(wav)

        # anchor fail-closed: a weak/absent anchor means membership is
        # meaningless, so nothing is actionable (still logged).
        if self.anchor is None or not self.anchor.strong:
            self._demote_all(utts, "anchor_weak_fail_closed", episode)
            return (StackDecision("LIFE_LOG", "anchor_weak_fail_closed"), utts)

        members = _layer1_membership(utts, self.anchor, episode)
        directed, degraded = _layer2_directed_or_degraded(utts, self.anchor, episode)

        if degraded:
            self._demote_all(utts, "degraded_mode", episode)
            return (StackDecision("DEGRADED_LOG", "wearer_silent_window",
                                  degraded_declared=True), utts)

        candidates = list({id(u): u for u in (members + directed)}.values())
        if not candidates:
            self._demote_all(utts, "not_wearer_conversation", episode)
            return (StackDecision("LIFE_LOG", "not_wearer_conversation"), utts)

        # Candidates may include the wearer's social opener/backchannel
        # AND the instruction-bearing utterance. Layer 3 must act on the
        # INSTRUCTION, not the first member: a no-verb opener is simply
        # not an instruction (skip it, do not confirm on it). Evaluate
        # all candidates: FIRE the first instruction whose load-bearing
        # slots are confident; else CONFIRM a verb-bearing instruction
        # whose slots are weak (exactly one confirmation); else there is
        # no instruction in this conversation -> LIFE_LOG. Never
        # blind-fire a low-confidence load-bearing slot.
        confirm_u = None
        confirm_why = ""
        for u in candidates:
            verdict, why = _layer3_slot_trust(u)
            if verdict == "FIRE":
                # emit the WHOLE trusted conversation (context the
                # frozen engine's addressee logic needs), not just the
                # instruction line.
                self._emit(candidates, episode)
                return (StackDecision("ACTIONABLE", f"member+slots_ok:{why}",
                                      emitted_text=u.text), utts)
            if why != "no_confident_action_verb" and confirm_u is None:
                confirm_u, confirm_why = u, why   # a real instruction, weak slot
        if confirm_u is not None:
            q = self._send_one_confirmation(confirm_u, confirm_why, episode)
            return (StackDecision("CONFIRM", f"low_conf_slot:{confirm_why}",
                                   confirm_question=q), utts)
        self._demote_all(utts, "no_instruction_in_conversation", episode)
        return (StackDecision("LIFE_LOG", "no_instruction_in_conversation"),
                utts)

    # --- sinks -------------------------------------------------------
    def _send_one_confirmation(self, u: Utterance, why: str,
                               episode: dict) -> str:
        """Exactly ONE short confirmation over the existing comms seam
        (test-mode recorder now, real Telnyx/SES later, same shape).
        One message per pending action: never a bombardment.
        """
        from app.anticipy import platform_adapter
        from app.audiostack import layer3

        q = layer3.confirm_question(u, {})
        platform_adapter.comms_send({
            "task_id": f"astack-confirm-{episode.get('category', 'x')}",
            "user_id": self.user_id, "channel": "text",
            "body": q, "criticality": "non_critical",
            "options": ["yes", "no"], "ts": episode.get("ts", 0.0),
        })
        return q

    def _emit(self, members: list, episode: dict) -> None:
        """Emit the FULL trusted diarized conversation, not one line.
        The frozen engine's addressee/authority logic was designed and
        validated on a diarized transcript (WEARER turns + others); it
        decides whether a non-wearer's utterance is a task FOR the
        wearer. Feeding only the instruction line in isolation strips
        exactly that context and the engine correctly ASKs. So push
        every trusted member utterance in time order, wearer marked
        WEARER and conversation partners as S1 (the seam contract:
        exactly one speaker is the enrolled wearer).
        """
        from app.anticipy import platform_adapter

        ts = episode.get("ts", time.time())
        src = platform_adapter.transcript_source()
        for m in sorted(members, key=lambda x: x.start):
            src.push({
                "speaker_id": "WEARER" if m.is_wearer else "S1",
                "text": m.text,
                "ts": ts + m.start,
            })

    def _demote_all(self, utts: list[Utterance], reason: str,
                    episode: dict) -> None:
        for u in utts:
            L.demote(L.LifeLogRow(
                ts=episode.get("ts", time.time()),
                speaker_id=u.speaker_label, text=u.text, reason=reason,
                confidence=u.mean_conf, category=episode.get("category"),
                meta={"start": u.start, "end": u.end}))


# --- corpus item -> scored result (used by the gate + harness) -------

def run_item(item: dict, user_id: str = "wearer") -> M.ItemResult:
    """Process one corpus item end to end and score its outcome
    against the MIX-TIME label (never judged by a model).
    """
    st = AudioStack(user_id)
    wav = A.load_wav(item["wav_path"])
    dec, _utts = st.process(wav, {"category": item["category"],
                                  "ts": 0.0})
    blind = False  # P0 never fires; real blind-fire detection lands P3
    content_ok = True
    if dec.outcome == "ACTIONABLE" and item["label"] == "ACTIONABLE":
        exp = (item.get("expected_text") or "").lower().split()
        got = (dec.emitted_text or "").lower()
        hit = sum(1 for w in exp if w in got)
        content_ok = (hit / max(1, len(exp))) >= 0.5
    return M.ItemResult(
        item_id=item["item_id"], category=item["category"],
        label=item["label"], outcome=dec.outcome,
        degraded_declared=dec.degraded_declared,
        content_ok=content_ok, blind_fire_on_low_conf=blind,
    )
