# Memory+Context phase — BASELINE (measured before M-steps)

Suite: 100 passed, 12 failed. safety_mega_eval = PASS (0 breaches).
Pre-existing failures (NOT caused by this phase; on branch devin/full-frontend-ui before edits):
  owner_mode (expects 4 cards, gets 6 — over-carding on split clauses "put it in the cart"/"don't buy it")
  owner_ingest_event, owner_upload_ingest, messy_proactive_handoff
  retraction_silenced ("no actually hold off"/"scratch that" still acted/asked — retraction not honored)
  onboarding_frontdoor, owner_app_auth, owner_app_product_path, download_route (frontend/next)
  premium_copy, owner_test_day01, create_print_routing_selftest (physical sign -> print routing)

Relevant to this phase: owner_mode over-carding + retraction_silenced are capture/reconciliation
+ vent/retraction problems -> targeted by M2 (reconciliation) and the write-path vent/retraction gate.
