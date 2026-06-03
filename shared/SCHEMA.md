# Shared Data Language (decide once — every room uses these shapes)

Canonical definition for all rooms (Python engine, SwiftUI app, browser
extension). The Python mirror lives in `engine/anticipy_engine/shared/schema.py`;
Swift/JS mirrors are added when those rooms need them. Keep them boring and
identical.

## memory item
| field | type | notes |
|---|---|---|
| `id` | string | unique |
| `kind` | enum | `profile_fact` \| `open_loop` \| `history` |
| `text` | string | the content |
| `people` | string[] | names/handles referenced |
| `timestamp` | number | epoch seconds |
| `status` | string | e.g. `open`, `done` |

## capture event
| field | type | notes |
|---|---|---|
| `id` | string | unique |
| `source` | enum | `mac_mic` \| `pendant_phone` |
| `text` | string | transcribed/typed content |
| `timestamp` | number | epoch seconds |

## action request
| field | type | notes |
|---|---|---|
| `id` | string | unique |
| `intent` | string | what to do |
| `risk` | enum | `low` \| `needs_confirm` \| `ask_human` |
| `path` | enum | `connector` \| `browser` |
| `payload` | object | intent-specific data |
