Known limitation: cross-frame interaction is not exercised. The live fallback
bridge supports only `navigate` + `/surface-proof`; it cannot drill into the
nested frames at /frame_top, /frame_left, /frame_middle, /frame_right,
/frame_bottom. Only the parent frameset render is asserted here.
