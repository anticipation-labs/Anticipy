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


@dataclass
class StackDecision:
    outcome: str              # ACTIONABLE | LIFE_LOG | CONFIRM | DEGRADED_LOG
    reason: str
    degraded_declared: bool = False
    emitted_text: str = ""
    confirm_question: str = ""


# layer hook points. P0 ships safe stubs; P1..P3 replace each.
def _layer1_membership(utts, anchor, episode):
    """P1 fills this. Returns the subset of utterances that are part
    of the wearer's conversation. P0 stub: unknown -> empty (safe).
    """
    return []


def _layer2_directed_or_degraded(utts, anchor, episode):
    """P2 fills this. Returns (directed_utts, degraded_bool). P0 stub:
    nothing directed, not degraded.
    """
    return [], False


def _layer3_slot_trust(utt):
    """P3 fills this. Returns ('FIRE'|'CONFIRM', reason). P0 stub:
    never blind-fire -> CONFIRM is the safe placeholder, but P0 never
    reaches here because L1/L2 stubs admit nothing.
    """
    return "CONFIRM", "p0-stub"


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
            isw = E.is_wearer(emb, self.anchor) if self.anchor else False
            out.append(Utterance(
                speaker_label="WEARER" if isw else "UNK",
                text=asr.text, start=s, end=e,
                mean_conf=asr.mean_conf(), tokens=asr.tokens, is_wearer=isw,
            ))
        return out

    # --- the pipeline ------------------------------------------------
    def process(self, wav: np.ndarray, episode: Optional[dict] = None
                ) -> tuple[StackDecision, list[Utterance]]:
        episode = episode or {}
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

        # a candidate exists: Layer 3 decides fire vs confirm. Never
        # blind-fire a low-confidence load-bearing slot.
        for u in candidates:
            verdict, why = _layer3_slot_trust(u)
            if verdict == "FIRE":
                self._emit(u, episode)
                return (StackDecision("ACTIONABLE", f"member+slots_ok:{why}",
                                      emitted_text=u.text), utts)
            return (StackDecision("CONFIRM", f"low_conf_slot:{why}",
                                   confirm_question=f"did you mean: {u.text}?"),
                    utts)
        self._demote_all(utts, "no_fireable_candidate", episode)
        return (StackDecision("LIFE_LOG", "no_fireable_candidate"), utts)

    # --- sinks -------------------------------------------------------
    def _emit(self, u: Utterance, episode: dict) -> None:
        from app.anticipy import platform_adapter

        platform_adapter.transcript_source().push(
            {"speaker_id": "WEARER" if u.is_wearer else u.speaker_label,
             "text": u.text, "ts": episode.get("ts", time.time())})

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
