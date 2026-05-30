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
