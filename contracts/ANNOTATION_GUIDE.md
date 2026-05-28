# Anticipy Want Annotation Guide

Annotate the user's actual want, not the literal wording.

Label `contains_actionable_want` true only when a competent assistant should act, ask, or decline based on the user's context. Label it false for quoted speech, jokes, media references, hypotheticals, past memories, third-party wants, and already-satisfied wants.

Every positive example must include evidence spans, missing slots, risk tier, expected decision mode, expected surface, and the reason a competent person would choose that action, ask, or decline.

Every hard negative must name the blocking interpretation flag: `quoted_speech`, `hypothetical`, `joke`, `media_reference`, `third_party`, or `already_satisfied`.

A decline is correct only when the surface, account, identity, permission, transcript, or safety boundary is insufficient for a competent person to act.
