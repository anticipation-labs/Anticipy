"""Three security P0s from the 244-agent adversarial hunt, each confirmed by
two independent refuters, each with a complete attack chain.

1. The tokenless pairing PATCH accepted an attacker-chosen owner_ref. Pair
   codes are six digits with no rate limit, so a stranger could walk them,
   harvest a real owner id, register their own agent (no credential needed),
   and claim it against the victim's account — from which point their browser
   received the victim's jobs.
2. /agent/llm was an open, unmetered model proxy billed to us: register,
   self-pair, loop forever. The first symptom would be every genuine browser
   dying on provider 402s with nothing explaining why.
3. Every supervised child worker inherited the founder's phone number, so a
   second person's worker texted the founder about THEIR errands — and read
   his replies as answers to their tasks.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
GUARD = (ROOT / "backend/pb_hooks/guard.pb.js").read_text()
KEY = (ROOT / "backend/pb_hooks/agent_key.pb.js").read_text()


# ------------------------------------------------------- 1. pairing hijack

def test_tokenless_claim_refuses_an_owner_ref_it_cannot_verify():
    branch = GUARD.split("but owner_ref is NOT accepted here")[1][:2600]
    assert '"owner_ref" in b' in branch, "an unverifiable owner_ref must be refused"
    assert "pair from the signed-in app" in branch, "and refused with a reason"
    allowed = branch.split("const allowed = {")[1].split("}")[0]
    assert "owner_ref" not in allowed, "owner_ref must not be tokenlessly writable"
    for k in ("owner", "paired", "last_seen", "browser"):
        assert k in allowed, f"{k} must stay claimable so pairing still works"


def test_the_signed_in_path_still_binds_owner_ref_to_the_account():
    # The honest way to accept an owner_ref, and the only one left.
    assert "b.owner_ref === authId" in GUARD


# --------------------------------------------------- 2. open model proxy

def test_the_model_proxy_requires_a_real_account():
    assert 'this agent is not attached to an account' in KEY
    assert 'callerOwnerRef' in KEY
    # ...checked BEFORE any provider key is read INSIDE the /agent/llm
    # handler, so an unattached agent can never reach the billing path.
    llm = KEY[KEY.index('routerAdd("POST", "/agent/llm"'):]
    assert llm.index("callerOwnerRef") < llm.index('$os.getenv("GEMINI_API_KEY")')


def test_the_model_proxy_meters_every_account():
    assert "HOURLY_CALL_CEILING" in KEY
    assert "429" in KEY and "too many model calls" in KEY
    # The meter lives on the agent row: the audit ledger already filled the
    # 5GB volume once and took production down, so it may not grow per call.
    assert 'agentRecord.set("llm_calls"' in KEY
    mig = ROOT / "backend/pb_migrations/1700000035_agent_llm_meter.js"
    assert mig.exists() and "llm_calls" in mig.read_text()


def test_a_meter_failure_never_blocks_real_work():
    block = KEY.split("HOURLY_CALL_CEILING = ")[1][:1400]
    assert "catch" in block and "meter unavailable" in block


# ------------------------------------------------ 3. cross-account phone

def test_a_child_worker_never_inherits_the_founders_phone():
    from brain.supervisor import child_environment

    base = {
        "ANTICIPY_OWNER_PHONE": "+16045551111",   # the founder's
        "ANTICIPY_OWNER_ID": "FOUNDER-UUID",
        "ANTICIPY_MEMORY_DB": "/data/founder/memory.db",
        "ANTICIPY_STATE_ROOT": "/data",
    }
    stranger = child_environment({"id": "abc123def456ghi"}, base=dict(base))
    assert "ANTICIPY_OWNER_PHONE" not in stranger, \
        "a stranger's worker must not carry the founder's number"
    assert stranger["ANTICIPY_OWNER_REF"] == "abc123def456ghi"
    assert stranger["ANTICIPY_MEMORY_DB"] != base["ANTICIPY_MEMORY_DB"]

    # The founder's own worker keeps his number and his existing mind.
    founder = child_environment(
        {"id": "zzz111yyy222xxx", "legacy_uuid": "FOUNDER-UUID"}, base=dict(base))
    assert founder.get("ANTICIPY_OWNER_PHONE") == "+16045551111"
    assert founder["ANTICIPY_MEMORY_DB"] == base["ANTICIPY_MEMORY_DB"]


def test_a_supervised_worker_never_falls_back_to_an_inherited_number():
    src = (ROOT / "brain/worker.py").read_text()
    assert 'ANTICIPY_SUPERVISED") == "1"' in src
    seed = src.split("owner_phone=(")[1][:200]
    assert '""' in seed, "supervised children start with no phone at all"


# --------------------------------------- speech stranded by a restart

def test_events_claimed_but_never_finished_are_handed_back():
    """claim() stamps decision="processing" before any side effect, and
    fetch_unprocessed only ever selects decision="" — so a restart between
    the claim and the outcome stranded that event PERMANENTLY. There was no
    sweep, no lease and no expiry anywhere in the repo, and restarts are
    routine: every deploy is one. The words a person actually said were
    simply never understood, and nothing said so.
    """
    src = (ROOT / "brain/worker.py").read_text()
    assert "def release_stranded_claims" in src
    body = src.split("def release_stranded_claims", 1)[1][:1800]
    assert 'decision="processing"' in body and 'updated<=' in body, (
        "only claims older than a cutoff may be reclaimed, never live ones")
    assert '"decision": ""' in body, "a released event must return to the queue"
    assert "owner_ref" in body, "the sweep stays scoped to one account"
    # ...and it must run BEFORE new work is taken, or a deploy still eats
    # whatever was mid-understanding.
    loop = src.split("release_stranded_claims(anticipy.owner_ref)", 1)
    assert len(loop) == 2, "the sweep must be wired into the main loop"
    assert "fetch_unprocessed(owner_ref=anticipy.owner_ref)" in loop[1][:400]


# ------------------------------------ a transport with nobody to reach

def test_a_missing_phone_is_a_failure_not_a_dev_rig():
    """Live 2026-08-16: "he didn't text me once during our testing."

    Last night's cross-account fix correctly stopped a supervised worker
    inheriting the founder's number — but his OWN profile row carried an
    empty phone (the three rows holding his number are legacy rows with no
    account attached). owner_phone went empty, and notify_owner fell through
    to the "no transport" escape, which returns a TRUTHY dict. Every caller
    then recorded the message as SAID. She composed his questions, stamped
    them delivered, and sent nothing for ten hours.

    The escape is for rigs with no Twilio at all. A configured transport with
    no number for this person is a real failure to reach a real person.
    """
    from brain.anticipy_core import Anticipy
    from brain.memory import Memory

    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    a.owner_phone = ""

    # No transport anywhere: a rig. Silence is honest, and truthy.
    a.conversation = None
    a.voice = None
    assert a.notify_owner("anything") == {"skipped": "no transport"}

    # A transport exists and there is nobody to reach: that is a FAILURE, and
    # must be falsy so nothing downstream records it as said.
    a.conversation = object()
    assert a.notify_owner("which restaurant?") is None


def test_the_phone_falls_back_to_the_account_but_never_across_accounts():
    src = (ROOT / "brain/worker.py").read_text()
    body = src.split("def fetch_owner_phone", 1)[1][:1600]
    assert "collections/owners/records/{owner_ref}" in body, (
        "the account record is the second place a number lives")
    assert "if not owner_ref:" in body, (
        "with no account there is nobody to fall back to — never a shared var")
    assert "ANTICIPY_OWNER_PHONE" not in body, (
        "the founder's env var must never come back as a fallback")
