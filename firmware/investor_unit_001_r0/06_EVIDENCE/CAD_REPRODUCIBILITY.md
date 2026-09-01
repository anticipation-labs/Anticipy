# Corrected shell-recovery CAD evidence

- Generator SHA-256:
  `d130fd01768dda4a2fbb0e67d92af01603e421d989bd3bb508cae7882540ff38`
- Packaged historical body/face references byte-match the pulled repository
  source.
- Two clean generator runs produce byte-identical `FIT_REPORT.json` and all 19
  STL files.
- All 19 STLs are closed/watertight, manifold, outward-oriented, and contain no
  degenerate triangles.
- All 25 STEP files import as valid OCC geometry; repeated solid/face/edge
  counts, volume, area, and bounds match. STEP bytes themselves can vary because
  the exporter writes timestamp/presentation metadata.
- The enforced report contains 1,045 intersection values: body/bands, 13 face
  drop positions, 21 face lock-slide positions, every part against body/band/
  locked face, every part pair, and the full face motion against all five parts
  across the primary and four coin-motor layouts.
- Maximum modeled overlap: `0.0 mm3`; abort tolerance: `1e-6 mm3`.

This is **CAD PASS / physical qualification required**. The driver island has
only 0.2 mm nominal wall margin; the 15 mm-cell layout has 0.3 mm motor gap;
24–25 mm cells occupy the conservative antenna zone. Actual nylon, print,
battery body/leads, solder/wires, and closure must pass gauges and RF/no-load
tests.
