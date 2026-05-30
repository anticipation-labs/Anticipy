# Anticipy Design Brief

This brief distills design principles from primary sources and applies them to Anticipy specifically. Each principle is one sentence, followed by one sentence on what it means for Anticipy.

## Source access note

WebFetch and WebSearch returned `400 This model does not support the effort parameter` for every URL attempted in this session (Apple HIG root, the menu bar page, notifications page, calmtech.com). Where a source could not be fetched live, the principle is cited from prior knowledge of that source's published guidance and labeled accordingly. The reasoning is: Apple's HIG and the calm tech canon are stable and well known, but a fresh fetch was the original ask and that capability was not available in this session.

## Sources used

1. Apple Human Interface Guidelines, top-level themes (deference, clarity, depth) plus the "Designing for macOS" and platform pages. Cited from prior knowledge. Fetch failed in this session.
2. Apple HIG, "The menu bar" and menu bar extras guidance. Cited from prior knowledge. Fetch failed.
3. Apple HIG, "Notifications" guidance for macOS and iOS. Cited from prior knowledge. Fetch failed.
4. Don Norman, "The Design of Everyday Things" (revised 2013): discoverability, feedback, conceptual model, affordances, signifiers, mapping, constraints. Cited from the book.
5. Mark Weiser and John Seely Brown, "The Coming Age of Calm Technology" (1996), and Amber Case, "Calm Technology" (O'Reilly 2015): center vs periphery, minimum attention, technology informs and encalms. Cited from prior knowledge; calmtech.com fetch failed.
6. Jony Ive, interviews, on subtraction and inevitability. Cited from public interviews (Vanity Fair 2014, Wallpaper, the Apple Design book). No fresh web fetch.

## The principles, distilled for Anticipy

### P1. Deference. The product should defer to the user's content, not the other way around.
Source: Apple HIG iOS 7 design themes, retained in macOS HIG.
Means for Anticipy: the menubar popover shows tasks and people, not chrome. The popover is 480x600 with one brand word in the header and three columns of the user's own life (Now, Next, Past). Anything that draws the eye toward Anticipy and away from the user's day is a violation.

### P2. Clarity. Every element earns its place; legibility, precision, focus.
Source: Apple HIG core themes.
Means for Anticipy: status text in the popover is one word ("Listening"), not a paragraph. Receipt SMS is one sentence and one verb. No internal IDs, no JSON, no model names ever leak.

### P3. Depth. Visual layers and realistic motion convey hierarchy and connect interactions.
Source: Apple HIG core themes.
Means for Anticipy: popover open uses a 200ms fade plus 4px translate with a 0.32, 0.72, 0.18, 1.00 cubic bezier (already in popover.html). Voice over with a real human-sounding TTS provider supplies the auditory depth that a CLI "say" voice cannot.

### P4. Restraint. Show less. Cut what you can. The right amount, not the maximum amount.
Source: Apple HIG "Avoid making your app feel demanding" guidance plus Jony Ive on subtraction.
Means for Anticipy: a notification is rare enough that when one fires, the user reads it. Calendar prep fires once per meeting (already enforced via fired_event_ids dedup). Inhaler runs once per cold start, never on a schedule.

### P5. Real human voice. If the product speaks, it must sound like a person.
Source: Apple HIG "VoiceOver" and "audio" guidance plus internal Anticipy spec (Apple-like polish).
Means for Anticipy: trivia delivery already prefers ElevenLabs or Polly and falls back to macOS `say` only as a "failsafe". The failsafe should be the rare case, not the default for a stranger who installed the DMG.

### P6. Communicate before you interrupt. Notifications should be useful, timely, and welcome.
Source: Apple HIG Notifications, "Use notifications to deliver helpful information that users find welcome".
Means for Anticipy: every banner needs a reason the user can name in one sentence. The current notifier passes a generic "Anticipy" title when DecisionKind is None (notifier.py line 341). That is a violation that lands as "Anticipy" with no context.

### P7. Periphery first, center on demand. Calm tech sits at the edge of attention until needed.
Source: Weiser and Brown, "The Coming Age of Calm Technology", section "The Periphery".
Means for Anticipy: a brief delivered to the popover feed is periphery; a Twilio voice call is center. The notifier already caps EXECUTE decisions at PUSH (notifier.py `_cap_channel`), which is correct. But opening a visible Chrome tab is center, and the inhaler does this dozens of times silently.

### P8. Inform and encalm. Calm tech makes you more aware without making you anxious.
Source: Weiser and Brown.
Means for Anticipy: the receipt SMS confirms the action ran. Good. The recovery SMS apologizes and promises a retry. Good. The unkilled "Anticipy is not running" banner that flashes on engine restart is anxiety, not calm.

### P9. Discoverability and signifiers. The user should know what is possible and what to do next.
Source: Don Norman, "Design of Everyday Things" chapter 1.
Means for Anticipy: the onboarding popover lists four ways to start (call, audio, chat, ambient) with one-line subtexts. That is a textbook signifier. The download page's three numbered install steps are also strong. The popover's "Now" card with two buttons (Yes do it, No) is also good. The cdp_walker opening a Drive search tab with no signifier of why is not.

### P10. Feedback. Every action must produce a perceivable response within a perceivable time.
Source: Don Norman, "Design of Everyday Things" chapter 1.
Means for Anticipy: receipt firing (SMS plus self-email) is the post-action feedback for "I just do". The popover should also surface the same receipt in the Past column. Today the Past column polls every 5s, so feedback is up to 5s late. Acceptable but not Ferrari.

### P11. Conceptual model. The product should match the model the user is forming in their head.
Source: Don Norman.
Means for Anticipy: the user's mental model is "Anticipy hears me and quietly does things in the background". Visible tabs flicking in and out of their Chrome window violate that model. The inhaler opening Gmail inbox, Gmail sent, and Calendar in turn is jarring even though it works.

### P12. Inevitability over decoration. Each element should feel like it could not be otherwise.
Source: Jony Ive interviews, principle of subtraction; also Dieter Rams "Good design is as little design as possible".
Means for Anticipy: the popover's brand color is gold (#C8A97E) and the background is near-black (#0C0C0C). That is restrained. The dot status indicator (7px, glow on state change) is inevitable. The status text "Setting things up" when the dossier is empty is decorative; the real signal is the dot color.
