# STATUS_LIVE — auto-updated every 3 min by background poller

**Last update: 2026-05-30 15:27:02 PDT**

## Live engine state
- Port: `49671`
- /health: `{"ok":true,"service":"anticipy-local-engine","version":"product-3","pid":7354,"port":49671,"onboarded":false,"listening":true,"profile_error":""}`
- key_ok: True
- listening: None
- browser_surface: extension_native_bridge

## Chrome Developer Mode
`developer_mode` in Secure Preferences: **False**
(True = unpacked extensions can run; False = unpacked disabled)

## anticipy-agent process (native messaging host)
```
none
```
If "none": extension has not connected to native messaging. Either Dev Mode off (see Blockers below) or extension dormant. Phase 1 gate cannot pass until this shows the agent process.

## Last 5 ASR transcripts (engine /api/listen/status)
  - None: ''
  - None: ''
  - LIFE_LOG: 'Prince Prince Prince Prince.'
  - LIFE_LOG: 'Prince. Prince.'
  - LIFE_LOG: "before but that's it. There's food here, I'll have it after. Yeah, bye. Yeah. Ok"

---

# BLOCKERS

# BLOCKERS_LIVE — owner-actionable items, read by poller, included in STATUS_LIVE

**Updated by claude when a blocker arises. Owner clears by completing the action.**

---

## ACTIVE BLOCKER (1)

### B-1: Chrome Developer Mode is OFF — extension cannot run

**Detected:** 2026-05-30 15:25 PDT via `~/Library/Application Support/Google/Chrome/Default/Secure Preferences` (`developer_mode: False`).

**Why blocking:** Chrome 148 enforces Chrome 137+ policy that disables unpacked extensions when Developer Mode is off. The Anticipy Bridge v6 extension is correctly registered with pinned ID `npnpagopediecennpleihemoochikggb` at the right path, but inactive. No `anticipy-agent` process spawns. No native messaging handshake. Phase 1 gate cannot pass.

**The one click:**
1. Open `chrome://extensions` in your Chrome
2. Top RIGHT corner, toggle **"Developer mode"** to ON (slider goes blue)
3. The "Anticipy Bridge v6" card should now show as enabled (its slider also on)
4. The native messaging agent will spawn within seconds
5. Poller will detect within 3 min, blocker auto-clears

**Why I can't do this for you:** Chrome's security model blocks programmatic toggling of Developer Mode from extensions and external apps. The long-term fix is shipping via Chrome Web Store, which doesn't require Dev Mode.

---

## RESOLVED (history)

(none yet)

---

## Phase progress
- Phase 0: DONE (commit 83691feb pushed to origin)
- Phase 1: IN PROGRESS (extension handshake) — see Blockers
- Phase 2-10: QUEUED per ARCHITECTURE.md §14

## Files of record
- [NORTH_STAR.md](NORTH_STAR.md), [ARCHITECTURE.md](ARCHITECTURE.md), [PROGRESS_LOG.md](PROGRESS_LOG.md), [RALPH_LOOP.md](RALPH_LOOP.md), [VERIFICATION_PROTOCOL.md](VERIFICATION_PROTOCOL.md), [CONTEXT_HANDOFF.md](CONTEXT_HANDOFF.md), [BLOCKERS_LIVE.md](BLOCKERS_LIVE.md)
- Research: [RESEARCH/](RESEARCH/)
