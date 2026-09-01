# Unit 001 artifact delivery boundary

This draft-PR directory is the reviewable source, manufacturing decision,
procurement, assembly, and release record for the XIAO ordered-shell recovery.
It remains **HOLD** until the physical and app record passes.

The complete builder archive delivered with this change is:

- `Anticipy_Investor_Unit_001_2026-09-01.zip`
- Size: 2,438,034 bytes
- SHA-256: `da4b7a849dc6fa40d3b0f7d2f94bbfbae95e72cbcaf7a5f5111b12389630cad8`

That archive contains the binary STLs, the single held UF2 candidate, compiled
configuration, reference STEP files, and archived manufacturer PDFs. Those
opaque manufacturing/release binaries are not represented by old repo
artifacts and must never be substituted by filename similarity.

The single held UF2 inside the builder archive is 528,384 bytes with SHA-256
`f246fc79ff9925fb427585e8babf4fe106ea1ad1c32a82b2c4351d3cc55ea5d6`.
It is not a released firmware image until `05_RELEASE/QA_RELEASE.md` passes on
the actual serial-numbered hardware and intended TestFlight build.
