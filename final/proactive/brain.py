"""final/proactive/brain.py — THE final proactive. One surface. Nothing else is live.

This is the ONLY entry the rest of the product should call for proactive. If you are looking for
"the proactive system," it is this. It wraps the canonical spine (control_core) — one door in,
cards out. Proven by final/tests/proactive_eval.py (14/15 as of last run; done at 15/15).

    brain = Brain(); await brain.start()
    cards = await brain.hear("remind me to email the landlord, ugh what a day")
    # -> catches 'email the landlord', stays silent on the vent
"""
from anticipy_engine.core.control_core import ControlCore


class Brain:
    def __init__(self):
        self.core = ControlCore()

    async def start(self):
        await self.core.bus.start()

    async def stop(self):
        await self.core.bus.stop()

    async def hear(self, text: str) -> list:
        """One sentence in → the real tasks caught, vents left silent, decisions made."""
        res = await self.core.owner_ingest("owner", text, {}, execute_actions=True)
        return res.get("cards") or []
