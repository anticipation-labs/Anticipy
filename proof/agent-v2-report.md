# Anticipy extension v0.2 — rebuilt on the real Claude/Codex architecture

I unpacked Anthropic's **Claude 1.0.81** and OpenAI's **ChatGPT/Codex
1.2.27221** Chrome extensions and read their actual code. Findings:

- Both request `debugger` + `scripting` + `tabs` + `tabGroups` + `alarms` +
  `notifications` + `webNavigation`. (Claude's manifest, verbatim, and
  ChatGPT's, verbatim — in the research folder.)
- Claude injects an **accessibility-tree** content script that walks the DOM,
  assigns each interactive element an index, and **redacts password /
  one-time-code / credit-card fields** (`[value redacted]`) before sending
  anything to the model.
- Acting is done through the **`debugger` (Chrome DevTools Protocol)**:
  `Input.dispatchMouseEvent`, `Input.insertText`, `Page.captureScreenshot`.
- Tabs go into a color-coded, collapsed **tab group** so agent tabs are
  separate from yours.

## What I changed in Anticipy to match (kept everything else)

New files: `page_map.js` (indexed element map + same sensitive-field
redaction), `agent_loop.js` (LLM step loop → CDP trusted input → background
"Anticipy" tab group). `manifest.json` now requests `debugger` + `tabGroups`.
The old URL-template actions still work for prefill flows; the new
`agent_goal` job type runs the autonomous loop.

## Live proof (recorded, my Chrome)

Loaded v0.2.0 unpacked, saved the OpenRouter key in extension storage, queued
one `agent_goal` job with a plain-English task. Chrome then displayed:

> **"Anticipy" started debugging this browser**

— the same banner Claude in Chrome triggers, confirming we're on the real
`debugger` API, not script injection.

![debugger banner](/home/ubuntu/screenshots/ss_701f9dd6.png)

The agent then, with no templates, decided each step (map page → LLM →
click/type via CDP) and finished at the Secure Area:

![secure area reached autonomously](/home/ubuntu/screenshots/ss_3a2653c5.png)

Backend job result:

```
done | Logged in successfully. The green success banner text says:
'You logged into a secure area!'
```

## Safety preserved
- Password fields are redacted in the page map (model never sees them).
- The loop returns `needs_user` for login walls, CAPTCHAs, and any
  irreversible step (send/pay/book/delete) → job goes to `awaiting_confirm`,
  released only by your SMS/app confirm. Gate is in the backend, not the model.
- We still never bypass bot-detection.
