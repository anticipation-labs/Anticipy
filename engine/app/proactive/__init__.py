"""
Anticipy proactive engine.

Five-layer AI cascade. Every layer that detects user intent is an LLM call,
not a rule. No regex, no keyword tables, no structural-pattern matchers.

  L1 SalienceClassifier      — actionable yes/no
  L2 Interpreter (extract)   — free-form verbs + intent text + parameters
  L3 ReversibilityClassifier — reversible / irreversible / unknown
  L4 UrgencyScorer           — 1..5
  L5 DonnaPass               — should the agent push back?

Audio never enters this package — only diarized user-voice transcript chunks
from the phone's on-device pipeline.

Entry point: ProactiveEngine. See engine.py and README.md.
"""

from .dispatcher import AdmitVerdict, Dispatcher
from .donna import DonnaPass, DonnaVerdict
from .engine import ProactiveEngine
from .interpreter import (
    ExtractedIntent,
    Interpreter,
    SalienceClassifier,
    SalienceVerdict,
)
from .reversibility import ReversibilityClassifier, ReversibilityVerdict
from .speaker_id import SpeakerIDClassifier, SpeakerVerdict
from .types import (
    Confidence,
    Decision,
    DecisionKind,
    Intent,
    IntentPayload,
    NotificationChannel,
    Reversibility,
    TranscriptChunk,
    Urgency,
)
from .urgency import UrgencyScorer

__all__ = [
    "AdmitVerdict",
    "Confidence",
    "Decision",
    "DecisionKind",
    "Dispatcher",
    "DonnaPass",
    "DonnaVerdict",
    "ExtractedIntent",
    "Intent",
    "IntentPayload",
    "Interpreter",
    "NotificationChannel",
    "ProactiveEngine",
    "Reversibility",
    "ReversibilityClassifier",
    "ReversibilityVerdict",
    "SalienceClassifier",
    "SalienceVerdict",
    "SpeakerIDClassifier",
    "SpeakerVerdict",
    "TranscriptChunk",
    "Urgency",
    "UrgencyScorer",
]
