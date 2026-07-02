# Anticipy Proof Video Batch Delivery

Created: 2026-06-21

This folder contains ten faceless, animated vertical proof videos for Anticipy. They are built to test preorder demand around concrete life-admin moments instead of abstract AI claims.

## Rendered Videos

All videos are 1080x1920, 30fps, 12 seconds.

1. `renders/final/01-email-i-did-not-write.mp4`
2. `renders/final/02-chatbot-is-inbox.mp4`
3. `renders/final/03-creepy-boundary.mp4`
4. `renders/final/04-not-ceo-toy.mp4`
5. `renders/final/05-money-go-ahead.mp4`
6. `renders/final/06-dinner-booking.mp4`
7. `renders/final/07-lawyer-deadline.mp4`
8. `renders/final/08-doctor-admin.mp4`
9. `renders/final/09-founder-intro.mp4`
10. `renders/final/10-parent-admin.mp4`

## QC

- `npx hyperframes lint .` passed with a GSAP Studio edit warning only.
- `npx hyperframes inspect . --samples 8 --json` passed without overflow.
- `ffprobe` verified every final render as 1080x1920, 30fps, 12.0 seconds.
- Contact sheet: `renders/qc/final/all-ten-contact.jpg`

## Creative Spine

Each video follows the same structure:

1. First 1.5 seconds: receipt or tension, not brand.
2. Seconds 2-4: concrete thing Anticipy handled.
3. Seconds 5-8: guardrail or mechanism.
4. Seconds 9-12: assistant-style message and quiet Anticipy reveal.

These are silent proof drafts. They are ready for platform-native audio, voiceover, or caption-only posting tests.
