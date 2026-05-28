# Anticipy Surface Runtime

Anticipy cannot rely on a giant global skills library. Real users have too many tools, too many private workflows, and too many hostile or canvas-only surfaces. The product instead needs a small universal runtime:

1. Read the current surface.
2. Choose the safest primitive action.
3. Execute one bounded step.
4. Verify the visible result.
5. Learn a small user-specific recipe only after a real receipt exists.

## Runtime Primitives

The engine works through primitives, not hard-coded app scripts:

| Primitive | Meaning |
|---|---|
| read | Observe DOM, AX tree, screenshot, terminal buffer, or file metadata. |
| open | Bring a user surface into view. |
| click | Click a visible affordance. |
| type | Type into a visible focused control. |
| shortcut | Use a deterministic keyboard shortcut when safer than mouse. |
| wait | Wait for a bounded state transition. |
| verify | Read the surface again and compare against expected state. |
| ask | Surface a clarification or confirmation. |
| decline | Stop without damaging state when confidence is too low. |

## Surface Ladder

The runtime chooses the cheapest reliable evidence for each surface:

| Surface | Primary evidence | Fallback |
|---|---|---|
| Browser DOM | CDP DOM snapshot | Screenshot plus vision |
| Canvas web app | Screenshot plus vision | Shell DOM metadata |
| Native Mac app | AXUIElement tree | Screenshot plus vision |
| Terminal | Terminal text buffer | Screenshot plus vision |
| Files | File metadata/content | Finder AX tree |
| Notifications | Provider callback plus user-visible record | Decline if no receipt |

## Proof Rule

Engine logs are not proof. A completed action requires a receipt from the same surface the user would inspect: DOM, AX tree, screenshot/vision, terminal buffer, file state, or a user-visible notification record. A provider callback can prove a notification was attempted, but it cannot prove a browser, canvas, CRM, or native-app task was completed.

For the user's actual Chrome on macOS, the visible-surface bridge can be either the installed Anticipy Chrome extension/native-messaging path or Chrome Apple Events plus screenshot. Direct hidden CDP against a cloned profile is not a product receipt. If JavaScript from Apple Events is disabled, URL/title metadata plus a screenshot is enough to prove that Anticipy is attached to the real visible Chrome surface; action-specific receipts still need the strongest available surface evidence for that task.

## Recipe Rule

Recipes are user-local and tiny. A recipe is created only after the runtime has a successful trace receipt for that user and surface. Recipes are retrieved by surface, task category, confidence, and recency. Anticipy must never load a huge global list of every app on Earth into runtime context.

## Hostile Surface Rule

If a page blocks automation, shows a captcha, lacks a readable state, or requires a risky action without enough confidence, the correct behavior is ask or decline. Anticipy must not evade bot defenses or leave half-filled forms.
