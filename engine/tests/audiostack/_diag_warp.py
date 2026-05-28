"""Does time-warp consensus separate the deliberately-confusable
LOADBEARING slot (should -> CONFIRM, zero blind fire) from clean
WEARER_DIRECT/BOSS instructions (should -> FIRE, true-pass kept)?
Run the REAL Layer-3 verdict on the instruction utterance per item.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from app.audiostack import audio as A
from app.audiostack import corpus as C
from app.audiostack import enrollment
from app.audiostack.stack import AudioStack, _layer3_slot_trust


def main() -> int:
    enrollment.enroll_synthetic_wearer("wearer")
    st = AudioStack("wearer")
    for cat in ("LOADBEARING_WORD_STRESS", "WEARER_DIRECT_COMMAND",
                "BOSS_INSTRUCTION_IN_CONVERSATION"):
        spec = C.SPEC_BY_NAME[cat]
        fire = conf = other = 0
        for i in range(6):
            wav_arr, it = C._assemble_item(spec, i, 20260516 + i)
            utts = st._utterances(wav_arr)
            cand = [u for u in utts if not u.is_wearer] or utts
            # the instruction-bearing utterance: the one with a verb
            verdicts = []
            for u in cand:
                v, why = _layer3_slot_trust(u)
                verdicts.append((v, why))
            v = "FIRE" if any(x[0] == "FIRE" for x in verdicts) else (
                "CONFIRM" if any(x[1] != "no_confident_action_verb"
                                 for x in verdicts) else "NONE")
            if v == "FIRE":
                fire += 1
            elif v == "CONFIRM":
                conf += 1
            else:
                other += 1
            ex = next((x for x in verdicts if x[0] == "FIRE"), verdicts[0]
                      if verdicts else ("NONE", ""))
            print(f"  [{it.item_id}] -> {v}  ({ex[1][:70]})")
        print(f"{cat}: FIRE={fire} CONFIRM={conf} NONE={other} (n=6)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
