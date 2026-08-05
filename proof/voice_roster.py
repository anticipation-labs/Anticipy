"""The voice roster — who is in his life, learned on the device.

Two jobs, one shared rule set (this module is the reference the Swift
implementation mirrors; keep them in step):

  1. IS IT HIM? match against the enrolled owner profile.
  2. WHO ELSE IS IT? recurring voices get a stable local id the first time
     they are heard and are RECOGNISED again days later — so "my friend"
     stops being a stranger every single conversation, and a name can be
     attached later ("that's Sarah") without re-learning the voice.

Thresholds are set by MEASUREMENT, not vibes, and corrected once already:
an earlier pass used 0.60 because owner-vs-owner scored 0.92 and
owner-vs-one-other scored 0.24. Adding a THIRD voice broke it — a
different person scored 0.667 against the owner, i.e. 0.60 would have
called a stranger "Omar" and attributed their promises to him. Measured
on 2026-08-05 (three voices, five cross-session comparisons):

    same person, different day : 0.897 – 0.911
    different people           : 0.181 – 0.667   <-- the 0.667 is the trap

So: MATCH at 0.78, and the winner must also beat the runner-up by
MARGIN 0.05. Anything short of both is "unknown", which the brain treats
as no verdict at all — exactly yesterday's behaviour. The asymmetry is
deliberate: a missed match costs nothing (she just doesn't use the hint),
while a false match puts someone else's commitments in his mouth.

Nothing here talks to a network. Embeddings and the roster file stay on
the device; only the CONCLUSION ("owner" / "other:v2") ever travels.
"""
from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np

MATCH = 0.78      # a genuine same-person score sits well above this
MARGIN = 0.05     # …and must clearly beat whoever came second


def cosine(a, b) -> float:
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


class VoiceRoster:
    """Owner profile + the people he actually talks to. Local file, local
    decisions, no network, no cloud copy."""

    def __init__(self, path: str):
        self.path = path
        self.owner: Optional[np.ndarray] = None
        self.people: dict[str, dict] = {}   # id -> {vec, name, heard}
        self._load()

    # ---------------------------------------------------------------- io
    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            raw = json.load(open(self.path))
        except Exception:
            return
        if raw.get("owner"):
            self.owner = np.array(raw["owner"], dtype=np.float32)
        for pid, rec in (raw.get("people") or {}).items():
            self.people[pid] = {"vec": np.array(rec["vec"], dtype=np.float32),
                                "name": rec.get("name"),
                                "heard": int(rec.get("heard", 1))}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        json.dump({
            "owner": self.owner.tolist() if self.owner is not None else None,
            "people": {pid: {"vec": r["vec"].tolist(), "name": r["name"],
                             "heard": r["heard"]}
                       for pid, r in self.people.items()},
        }, open(self.path, "w"))

    # ------------------------------------------------------------ enroll
    def enroll_owner(self, vec) -> None:
        self.owner = np.asarray(vec, dtype=np.float32)
        self.save()

    def name_person(self, pid: str, name: str) -> None:
        """Attach a human name to a voice already known ("that's Sarah")."""
        if pid in self.people:
            self.people[pid]["name"] = name
            self.save()

    # ------------------------------------------------------------ decide
    def identify(self, vec, learn: bool = True) -> dict:
        """Who spoke? -> {tag, id, name, score, confident}

        tag is what travels to the brain: "owner", "other:<id>", or
        "unknown" when the evidence is not clean enough to claim anyone.
        """
        vec = np.asarray(vec, dtype=np.float32)
        scores: list[tuple[float, str]] = []
        if self.owner is not None:
            scores.append((cosine(self.owner, vec), "owner"))
        for pid, rec in self.people.items():
            scores.append((cosine(rec["vec"], vec), pid))
        scores.sort(reverse=True)

        best_score, best_id = scores[0] if scores else (0.0, "")
        runner = scores[1][0] if len(scores) > 1 else 0.0
        confident = bool(scores) and best_score >= MATCH and \
            (best_score - runner) >= MARGIN

        if confident and best_id == "owner":
            return {"tag": "owner", "id": "owner", "name": None,
                    "score": best_score, "confident": True}
        if confident:
            rec = self.people[best_id]
            rec["heard"] += 1
            # Drift with them: a voice changes with mood, phone, room.
            rec["vec"] = (0.85 * rec["vec"] + 0.15 * vec).astype(np.float32)
            if learn:
                self.save()
            return {"tag": f"other:{best_id}", "id": best_id,
                    "name": rec["name"], "score": best_score, "confident": True}

        # Nobody known. Clearly-not-the-owner voices become new people so
        # they can be recognised tomorrow; genuinely ambiguous audio stays
        # unknown and teaches the roster nothing (a bad row poisons every
        # future match).
        owner_score = next((s for s, i in scores if i == "owner"), 0.0)
        ambiguous = owner_score >= (MATCH - 0.15)
        if learn and not ambiguous and best_score < MATCH:
            pid = f"v{len(self.people) + 1}"
            self.people[pid] = {"vec": vec.astype(np.float32), "name": None,
                                "heard": 1}
            self.save()
            return {"tag": f"other:{pid}", "id": pid, "name": None,
                    "score": best_score, "confident": False}
        return {"tag": "unknown", "id": None, "name": None,
                "score": best_score, "confident": False}
