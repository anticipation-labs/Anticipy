# The pendant's onboarding — design, read off Oura and off the hardware

2026-09-06. Written before any code, because the shape of this flow is a set of
decisions and they belong in the repo rather than in a chat (law 4).

Two reference sets were studied: 25 screens of Oura's iOS onboarding and 3 of
its "set up a new ring" flow, plus 11 photographs of the Anticipy pendant
prototype.

---

## 1. What the hardware actually is

From the photographs, not from a spec sheet:

* A **brushed stainless-steel capsule** — a rounded rectangle with fully
  rounded ends, roughly 1.3:1, about the size of an AirPods Pro case but
  flatter. Warm silver, fine directional brush grain, softly domed faces.
* **One small circular hole** on the face, upper third, off-centre: the
  microphone port. It is the only interruption in the surface.
* **"Anticipy" engraved** on the reverse.
* Worn on a **fine two-strand silver chain**; a braided black cord exists as an
  alternative in one photo.
* Two-piece construction — one photo shows the shell and inner separated.

**The thing worth noticing:** the app's mark is a capsule outline with a single
dot inside it. The pendant is a capsule with a single hole in it. The product
and the logo are the same object. Every image and every screen below leans on
that rather than explaining it.

## 2. What Oura does, and which parts are worth taking

### Worth taking

* **The welcome screen is a photograph, not a diagram.** Full-bleed lifestyle
  image, wordmark small in the top-left, one sentence of promise over it, and
  the buttons stacked at the very bottom.
* **"No Oura Ring yet?" is a first-class control on that first screen**, an
  outlined pill directly under the filled one. They assume a large share of
  arrivals do not own the hardware and they do not make those people feel
  like they took a wrong turn.
* **The same escape appears again on the pairing screen**, that time as a plain
  text link under the button. It is offered twice, quietly, and never as an
  error.
* **The product hero is a floating render on a vignette**, three-quarter angle,
  55–65% of screen width, with a soft contact shadow and no ground plane. On
  the "congrats" screen it sits between the copy above and the button below.
* **On the connect screen the render moves to the top** and the copy sits under
  it, because at that moment the person is looking at the object in their hand
  and matching it to the picture.
* **The pairing screen is honest and technical**: the device's own name as the
  headline, its identifier in small mono type beneath, the product dimmed
  behind, and iOS's native pairing dialog on top. It does not pretend to be
  prettier than it is.
* **Copy states duration up front** — "Setup will take approximately 10
  minutes" — before asking for the first tap.

### Not worth taking

* Oura is **dark**: near-black grounds, dark photography, white pills. Anticipy
  is cream and champagne, and the owner has said plainly that the light scheme
  is the one to optimise for. Every borrowed composition gets re-lit.
* Oura's setup is **ten minutes and mandatory**. Ours is optional and should
  read as a two-minute detour that most people skip.
* Oura's onboarding **asks for the ring before the account**. Ours already has
  a settled first run; the pendant must attach to it without disturbing it.

## 3. The decision that shapes everything: most people do not have one

There is no shipping pendant yet, and even when there is, the phone is the
primary ear. So the flow is built for the person who does **not** have one, and
the person who does takes a short branch off it.

Concretely:

* The pendant beat offers **one primary action and one secondary**, and the
  primary is the ordinary path: *Continue without one*. Owning a pendant is the
  **quiet** option — a smaller, lighter control beneath it reading
  *I have a pendant*.
* This inverts Oura deliberately. Oura sells rings, so "Start" is owning one.
  Anticipy works fully on the phone, so continuing without is not a downgrade
  and must not be dressed as one.
* Nothing in the beat may imply the product is diminished without the hardware.
  The pendant is **better ears in more places**, not the price of entry.
* The beat is **skippable and re-enterable**: Settings → Connectors → Pendant
  reaches the same flow forever after, so nobody has to decide at setup time.

## 4. The screens

Six, and only two of them are ever seen by somebody without hardware.

| # | Screen | Who sees it | Shape |
|---|---|---|---|
| 1 | **The offer** | everyone | Floating hero render on cream. One sentence. `Continue without one` (filled) then `I have a pendant` (quiet). |
| 2 | **Wake it** | owners | Product resting with the chain, a champagne glow at its base. "Hold the pendant until the light breathes." |
| 3 | **Looking for it** | owners | Live Bluetooth scan. Found devices as rows, signal strength as a quiet glyph. An escape link stays visible. |
| 4 | **Pairing** | owners | Device name as headline, identifier in mono beneath, iOS's own dialog on top. Oura's honesty, kept. |
| 5 | **Wear it** | owners | Lifestyle photograph, chain around the neck, one line about where it hears best. |
| 6 | **Done** | owners | Champagne finale, same as first run's, one sentence naming what changed. |

A person without hardware sees screen 1 and goes on. That is the whole point.

## 5. The images, and how they are positioned

Generated with Higgsfield (`nano_banana_pro`, 4K), using the prototype
photographs as references so the object is the real one rather than an
invention.

| Image | Aspect | Where it sits | Composition borrowed from |
|---|---|---|---|
| Floating hero | 3:4 | screen 1, centred, ~60% width, copy above and buttons below | Oura "Congrats on your new ring" |
| Resting with chain, lit | 3:4 | screen 2, **top** third, copy underneath | Oura "Connect your Oura Ring" |
| Worn on the chain | 9:16 | screen 5, full-bleed behind the copy | Oura's welcome photograph |

Every one is re-lit into the Anticipy palette: warm cream ground `#F2EEE7`, a
champagne bloom low in the frame, soft high-key light from the upper left, a
gentle contact shadow far below the object, and nothing else in the frame. No
text is baked into any image — every word on screen is live SwiftUI, so it
scales with Dynamic Type and can be corrected without a re-render.

## 6. What gets built now, before the hardware exists

The point of doing this early is that the screens are finished when the
hardware lands. So:

* **`PendantOnboardingPolicy`** — pure Foundation. Which beat is up, what each
  says, what a scan result means, and what happens when the person has no
  pendant. Walked by a suite, exactly like `DashboardPolicy`.
* **The radio behind a protocol.** A `PendantScanner` protocol with a
  CoreBluetooth implementation and a rehearsal implementation that emits
  invented devices on a timer. The screens are driven by the protocol, so every
  state — scanning, found, none found, refused permission, Bluetooth off — is
  reachable and photographable today.
* **No Bluetooth permission is requested until screen 3.** Same rule as the
  microphone: the ask happens where it is explained, and never before somebody
  has chosen to look for hardware.
* **The service UUID is a constant with a `TAPE:` marker**, because the real
  firmware does not have one yet. Law 2 — it ships with an expiry, not as a
  quiet guess.

## 7. Open, and honestly so

* The pendant's real BLE service and characteristic UUIDs are unknown until the
  firmware defines them. The scanner is written to filter on a constant that is
  marked as provisional.
* Battery level, firmware version and charge state are all shown as unknown
  rather than faked. A screen that invents a battery percentage is a screen
  that will be wrong on the first real device.
* `firmware_gate.py` is still UNPROVEN and the pendant's capture path has never
  been compiled or flashed. Nothing in this flow may claim the pendant is
  hearing anything until that gate is green.
