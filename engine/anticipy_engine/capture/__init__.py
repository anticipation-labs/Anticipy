"""Room 2: the capture seam.

The engine reads input ONLY through the ``CaptureSource`` interface — never from
a microphone or device directly. Today there is one stub source (``MacMicSource``)
and one clearly-named empty slot (``PendantPhoneSource``). The pendant
(pendant -> phone -> this engine) plugs into the same socket later with zero
engine changes.
"""
