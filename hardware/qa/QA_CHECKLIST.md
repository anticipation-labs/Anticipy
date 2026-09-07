# Per-unit QA — every unit passes ALL steps before it ships

Unit #____  Date ____  Tester ____

1. [ ] Visual: solder joints insulated, no battery lead strain, foam pads in,
       lid seats flush, button clicks, chain hole clean.
2. [ ] Charge: USB-C in → charge LED on; charges from a normal 5 V brick.
3. [ ] Boot + advertise: powers on, "Anticipy" visible in the app's scan list.
4. [ ] Pair + live stream: connect on iPhone, speak 30 s, transcript appears.
5. [ ] Haptic: connect buzz (1×), then Bluetooth off on phone → 2× buzz
       (offline mode) within 30 s.
6. [ ] Button: single tap and long-press events register in the app.
7. [ ] Backlog: phone away 30 min while speaking periodically → reconnect →
       backlog syncs, offline speech appears. (Unit #001 only: repeat with
       a 20 h offline soak.)
8. [ ] Battery (unit #001–#002 only): measured average current while
       streaming ____ mA → projected runtime ____ h (must be ≥ 16 h, or
       escalate per EXECUTION_PLAN risk table).
9. [ ] Storage integrity: after sync, no gaps/corruption in the recovered
       audio; flash/SD remounts cleanly after a hard power cut.
10. [ ] Wear test: 10 min on a chain — no rattles, no heat, mic not muffled
        by clothing position.
11. [ ] Final: charge to ~50 %, factory-reset pairing, pack with quick-start
        card (TestFlight link + consent note).

Fail anything → fix and rerun the full list. No partial passes ship.
