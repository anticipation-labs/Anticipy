"""Anticipy whole-system V1.

One portable Python engine. Local single user today is the multi tenant
system with tenant count one. At scale it is one isolated engine instance
per user. Same code, tenant count is the only difference.

Hard structural rule: every environment specific thing lives behind
``app.anticipy.platform_adapter``. No other module in this package, nor
the preserved cascade modules it drives, may contain paths, model
endpoints, comms transports, the action engine invocation, subprocess
calls, or platform branches. Porting to a home base device is writing a
new adapter, never rewriting the engine.

This package does NOT contain the audio front end. The proactive engine
consumes a diarized text transcript. Microphone, VAD, ASR, diarization,
and voiceprint are a separate later build that requires hardware that
does not exist yet.
"""

__all__ = []
