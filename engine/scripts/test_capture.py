"""Room 2 test: the capture seam holds.

Proves:
  - MacMicSource emits a CaptureEvent (shared data language) INTO the engine intake
  - the engine receives it ONLY through the CaptureSource interface
  - PendantPhoneSource is a real CaptureSource subclass but an empty future slot

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_capture.py
"""
from anticipy_engine.capture.base import CaptureSource
from anticipy_engine.capture.mac_mic import MacMicSource
from anticipy_engine.capture.pendant_phone import PendantPhoneSource
from anticipy_engine.capture.intake import Intake
from anticipy_engine.shared.schema import CaptureEvent

intake = Intake()

# Mic source emits through the seam into the engine's intake.
mic = MacMicSource(sink=intake.receive)
assert isinstance(mic, CaptureSource), "MacMicSource must implement the seam"
mic.start()
event = mic.emit_stub("hello from the mic")

assert isinstance(event, CaptureEvent)
assert event.source == "mac_mic"
assert event.text == "hello from the mic"
assert event.id and event.timestamp > 0
assert intake.events, "engine intake received nothing"
assert intake.last.id == event.id, "engine got the event via the CaptureSource seam"

# Pendant slot: same interface, intentionally unimplemented.
assert issubclass(PendantPhoneSource, CaptureSource)
pendant = PendantPhoneSource(sink=intake.receive)
try:
    pendant.start()
    raise AssertionError("PendantPhoneSource should be an empty future slot")
except NotImplementedError:
    pass

print("PASS room 2: capture seam")
print("  intake received:", intake.last.model_dump())
print("  sources sharing CaptureSource:", [MacMicSource.name, PendantPhoneSource.name])
