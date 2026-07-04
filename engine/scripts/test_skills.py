"""S8 skills pipeline — unit test (no browser, no LLM, no live I/O).

Pins the four stages of the acquire-before-task pipeline that evolves ``recipes.py``:
  * LIFT      — a verified trace → parameterized typed-slot skill; index dropped; no literals.
  * anti-cheat — ``find_hardcoded`` rejects selectors + un-parameterized values.
  * ADMIT     — re-execute (injected world) → the skill's own verify passes across HELD-OUT
                cases with DIFFERENT values; a hardcoded value fails re-execution (un-gameable).
  * RETRIEVE  — classify (action-shape, NO site rules) → intent-match → HARD rerank (drop a
                distractor) → 1-3 bodies, site-tag first.
  * LIFECYCLE — record_outcome + prune (demote low success-rate + dedup-merge; versioned, never
                hard-deleted) — and the recipe replay self-heal (match_index) is preserved.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_skills.py
"""
import json
import pathlib
import tempfile

from anticipy_engine.agent.skills import (
    Skill,
    Slot,
    SkillBindError,
    SkillStore,
    admit,
    bind,
    build_verifier,
    builtin_skills,
    classify_task,
    find_hardcoded,
    lift,
    prune,
    record_outcome,
    replay_indices,
    retrieve,
)


# a verified success trace, exactly the shape webvoyager.py records (action + stable descriptor).
DEMO_TRACE = [
    {"action": {"action": "navigate", "url": "https://shop.test/checkout", "index": 5}, "descriptor": {}},
    {"action": {"action": "type", "text": "alice@demo.test", "index": 12},
     "descriptor": {"role": "textbox", "name": "email"}},
    {"action": {"action": "type", "text": "Widget Pro", "index": 13},
     "descriptor": {"role": "textbox", "name": "product"}},
    {"action": {"action": "click", "index": 20}, "descriptor": {"role": "button", "name": "place order"}},
]
DEMO_SLOTS = [Slot("email", "email"), Slot("product", "string")]
DEMO_VALUES = {"email": "alice@demo.test", "product": "Widget Pro"}
DEMO_VERIFY = {"expect": ["ordered {product} for {email}"], "reject": ["error", "out of stock"]}


def _good_skill() -> Skill:
    return lift(skill_id="shop-order", name="place an order",
               description="add a product to the cart and check out place an order buy",
               task="order Widget Pro", url="https://shop.test/checkout",
               trace=DEMO_TRACE, slots=DEMO_SLOTS, values=DEMO_VALUES, verify=DEMO_VERIFY,
               site_tags=["shop.test"], tier="site")


def test_lift_parameterizes_and_drops_index():
    s = _good_skill()
    # concretes became typed slots
    assert s.steps[1]["action"]["text"] == "{email}", s.steps[1]
    assert s.steps[2]["action"]["text"] == "{product}", s.steps[2]
    # the volatile per-observe index is never baked into a skill (re-resolved at replay)
    assert all("index" not in st["action"] for st in s.steps), s.steps
    # NOT ONE literal demo value survives anywhere in the body
    blob = json.dumps(s.steps)
    assert "alice@demo.test" not in blob and "Widget Pro" not in blob, blob
    # a clean, portable skill has zero hardcoded findings
    assert find_hardcoded(s) == [], find_hardcoded(s)
    print("PASS lift: concretes -> typed slots, index dropped, zero literals, anti-cheat clean")


def test_find_hardcoded_catches_selectors_and_values():
    # a CSS/XPath selector smuggled into element identity is rejected (skills are DATA, not site code)
    sel = Skill(skill_id="x", name="x", description="d",
                steps=[{"action": {"action": "click"}, "descriptor": {"role": "button", "name": "#submit-btn"}}])
    assert any("selector-shaped" in r for r in find_hardcoded(sel)), find_hardcoded(sel)
    # a literal email typed into a field (should have been a slot) is rejected
    lit = Skill(skill_id="y", name="y", description="d",
                steps=[{"action": {"action": "type", "text": "bob@real.test"}, "descriptor": {"name": "email"}}])
    assert any("literal value" in r for r in find_hardcoded(lit)), find_hardcoded(lit)
    # an un-lifted known demo value that survived LIFT is rejected when the concretes are known
    partial = lift(skill_id="p", name="p", description="d", task="t", url="https://shop.test",
                   trace=DEMO_TRACE, slots=[Slot("email", "email")],
                   values={"email": "alice@demo.test"}, verify={})  # product NOT lifted
    assert find_hardcoded(partial, known_values=["Widget Pro"]), "should flag the un-lifted product"
    # a navigate URL is structure, not a selector — it must NOT false-positive
    nav = Skill(skill_id="n", name="n", description="d",
                steps=[{"action": {"action": "navigate", "url": "https://a.b/c.d?x=1"}, "descriptor": {}}])
    assert find_hardcoded(nav) == [], find_hardcoded(nav)
    print("PASS anti-cheat: selectors + literal/un-lifted values flagged; navigate URLs exempt")


def test_bind_typed_and_required():
    s = _good_skill()
    b = bind(s, {"email": "zoe@holdout.test", "product": "Gadget X"})
    assert b.steps[1]["action"]["text"] == "zoe@holdout.test"
    assert b.steps[2]["action"]["text"] == "Gadget X"
    # a missing required slot fails closed
    try:
        bind(s, {"product": "Gadget X"})
        assert False, "missing required email should raise"
    except SkillBindError:
        pass
    # a value that fails its declared type fails closed
    try:
        bind(s, {"email": "not-an-email", "product": "Gadget X"})
        assert False, "bad email type should raise"
    except SkillBindError:
        pass
    print("PASS bind: typed + required slots validated; substitution correct")


# ── the injected 'world' for ADMIT: fills the form and reports what the account shows. This is
#    the EXTERNAL, deterministic read-back — it never asks the skill whether it succeeded. ──
def _executor(steps, values):
    recorded = {}
    changes = []
    for st in steps:
        act = st.get("action") or {}
        a = act.get("action")
        if a == "type":
            name = (st.get("descriptor") or {}).get("name") or ""
            if "email" in name:
                recorded["email"] = act.get("text")
            if "product" in name:
                recorded["product"] = act.get("text")
            changes.append(True)
        elif a in ("click", "submit", "navigate", "check", "select"):
            changes.append(True)
    # the account page echoes what was ACTUALLY entered — a hardcoded value shows the wrong thing.
    obs = {"text": f"ordered {recorded.get('product', '')} for {recorded.get('email', '')}",
           "url": "https://shop.test/thanks"}
    return obs, changes


def test_admit_reexecutes_and_verifies_on_holdout():
    s = _good_skill()
    holdout = [
        {"values": {"email": "zoe@holdout.test", "product": "Gadget X"}, "expect_ok": True},
        {"values": {"email": "moe@holdout.test", "product": "Thing Y"}, "expect_ok": True},
    ]
    v = admit(s, _executor, holdout=holdout)
    assert v.admitted and v.status == "admitted", v
    assert v.holdout_passed == 2 and v.holdout_total == 2, v
    print("PASS admit: re-execute -> verify passes on held-out sibling params -> admitted")


def test_admit_rejects_hardcoded_dynamically():
    # A cheat that bypasses the STATIC scan: bake a short literal username-style value the heuristic
    # won't flag. It must still be caught by HELD-OUT re-execution (the un-gameable gate) because the
    # world echoes the baked value, not the bound one.
    s = _good_skill()
    cheat = Skill(skill_id="cheat", name="cheat", description=s.description,
                  slots=s.slots, verify=s.verify, site_tags=s.site_tags,
                  steps=[dict(st) for st in s.steps])
    # replace the {product} slot with a hardcoded short literal that static scan won't flag
    cheat.steps[2] = {"action": {"action": "type", "text": "Widget"},
                      "descriptor": {"role": "textbox", "name": "product"}}
    assert not any("literal value" in r for r in find_hardcoded(cheat)), \
        "the short literal must slip the STATIC scan so the DYNAMIC gate is what catches it"
    v = admit(cheat, _executor, holdout=[
        {"values": {"email": "zoe@holdout.test", "product": "Gadget X"}, "expect_ok": True}])
    assert not v.admitted and v.status == "quarantined", v
    assert any("verify=" in r for r in v.reasons), v.reasons  # caught by the read-back, not static
    # And a selector-hardcoded skill is caught STATICALLY, before any execution.
    sel = Skill(skill_id="sel", name="sel", description="d", slots=[],
                steps=[{"action": {"action": "click"}, "descriptor": {"name": "#buy"}}],
                verify={"expect": ["ok"]})
    v2 = admit(sel, _executor, holdout=[{"values": {}, "expect_ok": True}])
    assert not v2.admitted and any("hardcoded" in r for r in v2.reasons), v2
    print("PASS admit: hardcoded value caught by held-out re-execution; selector caught statically")


def test_admit_rejects_trivial():
    empty = Skill(skill_id="t", name="t", description="d", steps=[
        {"action": {"action": "navigate", "url": "https://x.test"}, "descriptor": {}}], verify={"expect": []})
    v = admit(empty, _executor, holdout=[{"values": {}, "expect_ok": True}])
    assert not v.admitted and any("trivial" in r for r in v.reasons), v
    print("PASS admit: a no-action (trivial) skill is rejected")


def test_classify_no_site_rules():
    assert classify_task("please make me an account on the service")["eligible"] is True
    assert classify_task("add the widget to my cart and check out")["eligible"] is True
    assert classify_task("compose and send an email to bob")["eligible"] is True
    # pure reads are NOT skill-eligible
    assert classify_task("how many results are on the page")["eligible"] is False
    assert classify_task("what is the price of the widget")["eligible"] is False
    # the classifier itself contains no domain names (a smoke check on the source)
    import anticipy_engine.agent.skills as _sk
    src = pathlib.Path(_sk.__file__).read_text()
    for banned in ("amazon", "gmail.com", "shop.test", "railway", "notion"):
        assert banned not in src.split("__all__")[0].lower(), f"no hardcoded site name allowed: {banned}"
    print("PASS classify: action-shape decides eligibility; zero hardcoded site rules")


def _admit_into(store, skill, holdout):
    v = admit(skill, _executor, holdout=holdout)
    assert v.admitted, v
    skill.status = "admitted"
    store.save(skill)
    return skill


def test_retrieve_intent_match_rerank():
    d = tempfile.mkdtemp()
    store = SkillStore(pathlib.Path(d), seed_builtins=False)
    order = _admit_into(store, _good_skill(), [
        {"values": {"email": "z@h.test", "product": "G"}, "expect_ok": True}])
    # a clear DISTRACTOR: unrelated intent, no shared site.
    distractor = Skill(skill_id="email-compose", name="compose and send email",
                       description="compose write and send an email message reply to a recipient",
                       steps=[{"action": {"action": "type", "text": "{body}"},
                               "descriptor": {"name": "message body"}},
                              {"action": {"action": "click"}, "descriptor": {"name": "send"}}],
                       slots=[Slot("body", "string")], verify={"expect": ["sent"]},
                       site_tags=[], tier="generic", status="admitted")
    store.save(distractor)

    # a checkout task ON shop.test → the site-tagged order skill wins; the email distractor is DROPPED.
    got = retrieve("add the widget to my cart and check out the order", "https://shop.test/cart", store, k=3)
    ids = [s.skill_id for s in got]
    assert order.skill_id in ids, ids
    assert "email-compose" not in ids, f"hard rerank must drop the distractor: {ids}"
    assert 1 <= len(got) <= 3, got
    assert got[0].skill_id == order.skill_id, "site-tag hit ranks first"

    # a compose task → the generic email skill is retrieved; the checkout distractor is dropped.
    got2 = retrieve("compose and send an email message to bob", "https://mail.test/new", store, k=3)
    ids2 = [s.skill_id for s in got2]
    assert "email-compose" in ids2 and order.skill_id not in ids2, ids2

    # a pure read → nothing is fetched (classifier gate).
    assert retrieve("how many messages are unread", "https://mail.test", store) == []
    print("PASS retrieve: classify-gate + intent-match + hard rerank (distractor dropped), 1-3 bodies")


def test_replay_reuses_match_index_selfheal():
    b = bind(_good_skill(), {"email": "z@h.test", "product": "Gadget X"})
    live = [
        {"idx": 3, "role": "textbox", "name": "email"},
        {"idx": 4, "role": "textbox", "name": "product"},
        {"idx": 9, "role": "button", "name": "place order"},
    ]
    idxs = replay_indices(b, live)
    assert idxs == [None, 3, 4, 9], idxs  # navigate has no element; the rest resolve via match_index
    # divergence (a recorded element is gone) self-heals to None -> caller falls back to the live loop
    assert replay_indices(b, [{"idx": 3, "role": "textbox", "name": "email"}]) is None
    print("PASS replay: match_index self-heal preserved (None on divergence)")


def test_lifecycle_prune_versioned():
    d = tempfile.mkdtemp()
    store = SkillStore(pathlib.Path(d), seed_builtins=False)
    s = _good_skill()
    s.status = "admitted"
    store.save(s)
    # 5 uses, mostly failing → success_rate < 0.5 → demote (NOT delete)
    for ok in (True, False, False, False, False):
        record_outcome(store, s.skill_id, ok)
    rep = prune(store, min_usage=5, min_success_rate=0.5)
    assert s.skill_id in rep["demoted"], rep
    assert store.get(s.skill_id).status == "quarantined", "demote = quarantine"
    assert store.get(s.skill_id) is not None, "versioned, never hard-deleted"

    # dedup-merge: two near-identical admitted skills → the weaker twin is parked, both survive.
    a = _good_skill(); a.skill_id = "twin-a"; a.status = "admitted"; a.usage_count = 10; a.success_count = 9
    b = _good_skill(); b.skill_id = "twin-b"; b.status = "admitted"; b.usage_count = 2; b.success_count = 1
    store.save(a); store.save(b)
    rep2 = prune(store, min_usage=999)  # usage floor high so ONLY dedup fires
    assert "twin-b" in rep2["merged"] and store.get("twin-b").status == "quarantined", rep2
    assert store.get("twin-a").status == "admitted", "the stronger twin is kept live"
    print("PASS lifecycle: prune demotes low success-rate + dedup-merges; versioned, never deleted")


def test_store_roundtrip_and_builtin_clean():
    d = tempfile.mkdtemp()
    store = SkillStore(pathlib.Path(d), seed_builtins=False)
    s = _good_skill(); s.status = "admitted"
    assert store.save(s) is True
    reloaded = SkillStore(pathlib.Path(d), seed_builtins=False)
    r = reloaded.get(s.skill_id)
    assert r is not None and r.steps == s.steps and [x.name for x in r.slots] == ["email", "product"], r
    # the shipped/builtin bank is anti-cheat clean (the grep stays green)
    for bs in builtin_skills():
        assert find_hardcoded(bs) == [], (bs.skill_id, find_hardcoded(bs))
    # and the on-disk signup-and-verify manifest carries no selector-shaped step
    manifest = pathlib.Path(__file__).resolve().parents[2] / "skills" / "signup-and-verify" / "skill.json"
    if manifest.exists():
        from anticipy_engine.agent.skills import _SELECTOR_RE
        for step in json.loads(manifest.read_text()).get("steps", []):
            assert not _SELECTOR_RE.search(str(step)), step
    print("PASS store: JSON round-trip; builtin + shipped skill bank has zero hardcoded selectors")


def main():
    test_lift_parameterizes_and_drops_index()
    test_find_hardcoded_catches_selectors_and_values()
    test_bind_typed_and_required()
    test_admit_reexecutes_and_verifies_on_holdout()
    test_admit_rejects_hardcoded_dynamically()
    test_admit_rejects_trivial()
    test_classify_no_site_rules()
    test_retrieve_intent_match_rerank()
    test_replay_reuses_match_index_selfheal()
    test_lifecycle_prune_versioned()
    test_store_roundtrip_and_builtin_clean()
    print("ALL SKILLS PIPELINE TESTS PASSED")


if __name__ == "__main__":
    main()
