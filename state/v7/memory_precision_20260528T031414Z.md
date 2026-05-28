# Memory precision scorer run 20260528T031414Z

- Transcripts scored: 20
- Alignment: 13/58 gold keys matched to dossier
- Judge cost: $0.0032 of $2.00 budget
- Judge calls: 20; tokens in/out: 10718/6849

## Aggregate per-dimension means

| Dimension | Mean | Count | Min | Max |
| --- | ---: | ---: | ---: | ---: |
| intent_precision | 0.400 | 20 | 0.00 | 1.00 |
| entity_precision | 0.227 | 20 | 0.00 | 0.80 |
| action_faithfulness | 0.320 | 20 | 0.00 | 1.00 |
| memory_write | 0.600 | 15 | 0.00 | 1.00 |
| memory_write_skip | 0.800 | 5 | 0.00 | 1.00 |

## By difficulty tier

| Difficulty | intent | entity | action | mem_write | mem_skip |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.750 | 0.208 | 0.225 | 0.333 | 1.000 |
| 2 | 0.000 | 0.133 | 0.225 | 0.667 | 1.000 |
| 3 | 0.375 | 0.229 | 0.400 | 0.667 | 1.000 |
| 4 | 0.500 | 0.375 | 0.400 | 1.000 | N/A |
| 5 | 0.375 | 0.188 | 0.350 | 0.000 | 0.500 |

## Top 3 transcripts (highest composite scores)

| id | diff | outcome | composite | intent | entity | action | mem_write | mem_skip | one-line reason |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| T04 | 4 | CONFIRMED | 0.95 | 1.00 | 0.80 | 1.00 | 1.00 | - | Plan fully captures all user constraints: two sessions, order, gaps, day restric |
| T03 | 3 | CONFIRMED | 0.81 | 1.00 | 0.25 | 1.00 | 1.00 | - | Plan correctly creates two evening blocks next week for speech writing as reques |
| T19 | 4 | CONFIRMED | 0.59 | 1.00 | 0.17 | 0.20 | 1.00 | - | Engine asks an unnecessary clarifying question instead of directly ordering and  |

## Bottom 10 transcripts (lowest composite scores)

| id | diff | outcome | composite | intent | entity | action | mem_write | mem_skip | one-line reason |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| T05 | 5 | CONFIRMED | 0.05 | 0.00 | 0.00 | 0.20 | 0.00 | - | Engine asked for email address instead of scheduling lunch and sending tentative |
| T08 | 3 | CONFIRMED | 0.05 | 0.00 | 0.00 | 0.20 | 0.00 | - | Asked for email address instead of drafting the follow-up email as requested. |
| T10 | 5 | CONFIRMED | 0.05 | 0.00 | 0.00 | 0.20 | 0.00 | - | Engine asked for clarification instead of drafting the email as requested. |
| T07 | 2 | CONFIRMED | 0.10 | 0.00 | 0.20 | 0.20 | 0.00 | - | Plan asks a clarifying question instead of acting on the clear user request to n |
| T12 | 2 | CONFIRMED | 0.25 | 0.00 | 0.00 | 0.00 | 1.00 | - | Empty plan does nothing; user asked to check bug status and ping if open. |
| T09 | 4 | CONFIRMED | 0.35 | 0.00 | 0.20 | 0.20 | 1.00 | - | Engine asked a clarifying question instead of acting on the detailed instruction |
| T01 | 1 | CONFIRMED | 0.38 | 1.00 | 0.00 | 0.50 | 0.00 | - | Plan creates a calendar placeholder but misses the named clinic and user's inten |
| T02 | 2 | CONFIRMED | 0.38 | 0.00 | 0.00 | 0.50 | 1.00 | - | Planned to confirm but didn't book reservation with the specific restaurant, tim |
| T16 | 1 | CANCELLED | 0.38 | 0.50 | 0.00 | 0.00 | - | 1.00 | Engine tried to act by asking for email, but user explicitly said not to act now |
| T14 | 4 | CONFIRMED | 0.38 | 0.00 | 0.33 | 0.20 | 1.00 | - | Engine asked a clarifying question instead of setting the quiet check as instruc |

