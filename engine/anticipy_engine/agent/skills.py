"""S8 — the acquire-before-task SKILLS pipeline (evolves ``recipes.py``).

``recipes.py`` is Voyager-lite: it records a verified action-trace keyed by (domain, task)
and REPLAYS it with stable descriptors + ``match_index`` self-heal. That is the cost-bend
lever, but it has four gaps (PLAN §4.7). This module closes them **without replacing** the
recipe replay engine — it reuses ``recipes.descriptor`` / ``recipes.match_index`` verbatim so
a bound skill self-heals to the live loop exactly like a recipe does.

The four stages, each un-gameable and selector-free:

1. **LIFT** — turn a *verified* success into a **parameterized** skill: every concrete demo
   value (``alice@x.com`` → ``{email}``) becomes a TYPED SLOT; the volatile per-observe index
   is dropped (re-resolved at replay). Reject any candidate that keeps a hardcoded selector or
   an un-parameterized value — the skill bank is *data*, never site-specific trunk code.
2. **ADMIT** — the whole ballgame. Admit only through a **deterministic external harness**:
   re-execute the skill (bind → run via an *injected* world executor) and require the skill's
   own ``verify`` contract to pass on the resulting state, across **held-out** sibling cases
   with *different* param values. A hardcoded value survives static scanning at your peril: a
   held-out case with a new value re-executes and the read-back — which expects the *bound*
   value — fails it. Admission is the SAME functional read-back that gates task-done; never a
   self-claim.
3. **RETRIEVE (acquire-before-task)** — the agent decides *when* to fetch by **task
   classification** (action-shape, NO site rules), then intent-matches the resident skill
   *descriptions* (L1 only), **hard-reranks for precision** (one distractor degrades — drop it),
   and loads the full body for the **1–3** survivors (site-tagged first, generic fallback).
4. **LIFECYCLE** — usage/success-rate pruning + embedding-dedup merge; versioned, **never
   hard-deleted** (a demoted skill is quarantined, not destroyed).

Everything is deterministic and injectable: the "embedding" is a token-overlap proxy and the
ADMIT executor is supplied by the caller, so the whole pipeline is unit-testable with fakes and
touches nothing live during the build.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# Reuse the recipe primitives verbatim — a bound skill replays with the SAME stable-descriptor
# self-heal, so we never fork the replay engine (PLAN §4.7: "evolve, don't replace").
from .recipes import _domain, _norm_task, descriptor, match_index, recipe_key  # noqa: F401

# NOTE — the S6 signup-and-verify core is imported LAZILY inside builtin_skills() (below), not at
# module top level. Registering it here is the acquire-before-task LOOP REGISTRATION the FIX-20
# debt line pointed at (the workflow-class skill is no longer test-only — it is seeded into this
# registry, which the agent loads). It must be lazy because signup_verify → hands.captcha_solver
# pulls the hands package, and hands.browser_hand imports webvoyager, which imports THIS module:
# a top-level import would form a cycle. Deferring to SkillStore()-construction time (runtime,
# after every module is loaded) breaks the cycle while keeping the import statically detectable.

__all__ = [
    "Slot",
    "Skill",
    "BoundSkill",
    "AdmitVerdict",
    "SkillBindError",
    "SkillStore",
    "lift",
    "bind",
    "admit",
    "build_verifier",
    "classify_task",
    "retrieve",
    "record_outcome",
    "prune",
    "replay_indices",
    "find_hardcoded",
    "builtin_skills",
]

# Master flag: the whole point is the compounding warm-flow. Flip to 0 to measure the no-skill cost.
SKILLS_ENABLED = (os.environ.get("ANTICIPY_SKILLS", "1") or "").strip().lower() not in (
    "0", "false", "no", "off")
_DIR = pathlib.Path(
    os.environ.get("ANTICIPY_SKILL_DIR", str(pathlib.Path.home() / ".anticipy" / "skills")))

_SLOT_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")

# A skill body is DATA. These are the shapes a real CSS/XPath/DOM-query selector takes — none of
# them belong in a portable skill (recipes/skills locate elements by role+visible-name, never by
# selector). Applied to data-entry text + descriptor names, NOT to navigate URLs (URLs are legit).
_SELECTOR_RE = re.compile(
    r"(#[A-Za-z][\w-]*"                      # #id
    r"|\.[A-Za-z][\w-]{2,}(?:\s|$|\[|\.)"    # .class (2+ chars, not a file/host dot)
    r"|//[A-Za-z*@]"                          # //xpath
    r"|\[[a-zA-Z][\w-]*\s*[~|^$*]?="          # [attr=...] / [data-x~=...]
    r"|::[a-z][a-z-]+"                          # ::pseudo
    r"|\bquerySelector\b|\bgetElementById\b|\bcss=|\bxpath=)")

# The data-entry actions whose text is a literal VALUE that must be a typed slot, never baked in.
_VALUE_ACTIONS = ("type", "select", "check")
_STRUCT_ACTIONS = ("navigate", "scroll", "back", "click", "submit")


class SkillBindError(ValueError):
    """A skill was asked to bind params it cannot satisfy (missing required / wrong type)."""


# ── typed slots ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Slot:
    name: str
    type: str = "string"          # string | email | url | number
    required: bool = True

    def to_json(self) -> dict:
        return {"name": self.name, "type": self.type, "required": self.required}

    @staticmethod
    def from_json(d: dict) -> "Slot":
        return Slot(str(d.get("name") or ""), str(d.get("type") or "string"),
                    bool(d.get("required", True)))


def valid_value(value, typ: str) -> bool:
    v = "" if value is None else str(value)
    if typ == "email":
        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v))
    if typ == "url":
        return v.startswith("http://") or v.startswith("https://")
    if typ == "number":
        return bool(re.match(r"^-?\d+(\.\d+)?$", v.strip()))
    return v.strip() != ""


# ── the skill ─────────────────────────────────────────────────────────────────
@dataclass
class Skill:
    skill_id: str
    name: str
    description: str                                   # the retrieval key — ONLY thing resident at L1
    slots: List[Slot] = field(default_factory=list)
    steps: List[dict] = field(default_factory=list)    # parameterized {action, descriptor}, no literals
    verify: dict = field(default_factory=dict)          # {"expect": [...], "reject": [...]} — the read-back
    site_tags: List[str] = field(default_factory=list)
    tier: str = "site"                                  # site | generic
    version: str = "0.1.0"
    status: str = "quarantined"                         # quarantined | shadow | admitted
    usage_count: int = 0
    success_count: int = 0
    kind: str = "recipe"                                # recipe | workflow (code-backed)
    start_url: str = ""

    @property
    def success_rate(self) -> float:
        return (self.success_count / self.usage_count) if self.usage_count else 0.0

    @property
    def required_slots(self) -> List[str]:
        return [s.name for s in self.slots if s.required]

    def to_json(self) -> dict:
        return {
            "skill_id": self.skill_id, "name": self.name, "description": self.description,
            "slots": [s.to_json() for s in self.slots], "steps": self.steps,
            "verify": self.verify, "site_tags": list(self.site_tags), "tier": self.tier,
            "version": self.version, "status": self.status, "usage_count": self.usage_count,
            "success_count": self.success_count, "kind": self.kind, "start_url": self.start_url,
        }

    @staticmethod
    def from_json(d: dict) -> "Skill":
        return Skill(
            skill_id=str(d.get("skill_id") or d.get("name") or ""),
            name=str(d.get("name") or d.get("skill_id") or ""),
            description=str(d.get("description") or ""),
            slots=[Slot.from_json(s) for s in (d.get("slots") or [])],
            steps=list(d.get("steps") or []),
            verify=dict(d.get("verify") or {}),
            site_tags=list(d.get("site_tags") or []),
            tier=str(d.get("tier") or "site"),
            version=str(d.get("version") or "0.1.0"),
            status=str(d.get("status") or "quarantined"),
            usage_count=int(d.get("usage_count") or 0),
            success_count=int(d.get("success_count") or 0),
            kind=str(d.get("kind") or "recipe"),
            start_url=str(d.get("start_url") or ""),
        )


@dataclass
class BoundSkill:
    skill: Skill
    steps: List[dict]           # {slot} substituted → concrete; index-free (re-resolved at replay)
    values: dict


# ── anti-cheat (static): no hardcoded selector, no un-parameterized value ──────
def _step_text_fields(step: dict) -> List[tuple]:
    """(field-label, string) pairs a selector could hide in — descriptor name + data-entry text.
    URL fields are deliberately excluded (a navigate URL is structure, not a selector)."""
    act = (step or {}).get("action") or {}
    desc = (step or {}).get("descriptor") or {}
    out: List[tuple] = []
    if isinstance(desc.get("name"), str):
        out.append(("descriptor.name", desc["name"]))
    if act.get("action") in _VALUE_ACTIONS and isinstance(act.get("text"), str):
        out.append(("action.text", act["text"]))
    return out


def _looks_like_literal_value(s: str) -> bool:
    """A data-entry string that is clearly a concrete VALUE (should have been a slot): an email,
    a long number, a URL, or 4+ words of free text. A pure ``{slot}`` (optionally with fixed
    connective words) is fine."""
    bare = _SLOT_RE.sub("", s).strip()
    if not bare:                                      # entirely slot(s)
        return False
    return bool(re.search(r"[^@\s]+@[^@\s]+\.\w+|\d{3,}|https?://", bare)) or len(bare.split()) >= 4


def find_hardcoded(skill: Skill, known_values: Optional[List[str]] = None) -> List[str]:
    """Reasons this skill is NOT portable data. Empty list = clean. Two checks:
    (1) selector-shaped strings in element identity / data-entry (never a navigate URL);
    (2) an un-parameterized concrete value — either a known demo value that survived LIFT, or a
        data-entry field that still reads as a literal instead of a ``{slot}``."""
    reasons: List[str] = []
    known = [k for k in (known_values or []) if k]
    for i, step in enumerate(skill.steps):
        for lbl, val in _step_text_fields(step):
            if _SELECTOR_RE.search(val):
                reasons.append(f"step[{i}].{lbl}: selector-shaped literal {val!r}")
            for kv in known:
                if kv and kv.lower() in val.lower():
                    reasons.append(f"step[{i}].{lbl}: un-lifted demo value {kv!r}")
            act = (step.get("action") or {}).get("action")
            if lbl == "action.text" and act in _VALUE_ACTIONS and _looks_like_literal_value(val):
                reasons.append(f"step[{i}].{lbl}: literal value not a typed slot: {val!r}")
    return reasons


# ── LIFT (acquire on a verified success) ──────────────────────────────────────
def lift(*, skill_id: str, name: str, description: str, task: str, url: str,
         trace: List[dict], slots: List[Slot], values: dict, verify: dict,
         site_tags: Optional[List[str]] = None, tier: str = "site",
         version: str = "0.1.0", kind: str = "recipe") -> Skill:
    """Parameterize a verified action-trace into a skill.

    ``values`` maps each slot name → the concrete value demonstrated in this success; every
    occurrence of that concrete (in data-entry text and — for tagging — navigate URLs) is
    replaced by ``{slot}``. The volatile per-observe ``index`` is dropped so replay re-resolves
    against the live DOM via ``match_index``. No literal selectors are ever introduced (the
    trace already carries only role+name descriptors)."""
    # longest concretes first so a value that contains another doesn't leave a fragment behind.
    subs = sorted(((str(v), sn) for sn, v in (values or {}).items() if str(v)),
                  key=lambda kv: len(kv[0]), reverse=True)
    out_steps: List[dict] = []
    for st in trace or []:
        act = dict((st or {}).get("action") or {})
        desc = dict((st or {}).get("descriptor") or {})
        for concrete, slot in subs:
            ph = "{" + slot + "}"
            for k in ("text", "url"):
                if isinstance(act.get(k), str):
                    act[k] = re.sub(re.escape(concrete), ph, act[k], flags=re.IGNORECASE)
            if isinstance(desc.get("name"), str):
                desc["name"] = re.sub(re.escape(concrete), ph, desc["name"], flags=re.IGNORECASE)
        act.pop("index", None)                        # re-resolved at replay — never baked in
        out_steps.append({"action": act, "descriptor": desc})
    return Skill(
        skill_id=skill_id, name=name, description=description or task,
        slots=list(slots or []), steps=out_steps, verify=dict(verify or {}),
        site_tags=list(site_tags or ([_domain(url)] if _domain(url) else [])),
        tier=tier, version=version, status="quarantined", kind=kind, start_url=url,
    )


# ── bind + the verify contract (the un-gameable read-back) ────────────────────
def _subst(s: str, values: dict) -> str:
    return _SLOT_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), s)


def bind(skill: Skill, values: dict) -> BoundSkill:
    """Substitute typed params into the skill body. Raises ``SkillBindError`` on a missing
    required slot or a value that fails its declared type."""
    for slot in skill.slots:
        if slot.name not in values:
            if slot.required:
                raise SkillBindError(f"missing required slot {slot.name!r}")
            continue
        if not valid_value(values[slot.name], slot.type):
            raise SkillBindError(f"slot {slot.name!r} wants type {slot.type!r}, got {values[slot.name]!r}")
    steps: List[dict] = []
    for st in skill.steps:
        act = dict((st or {}).get("action") or {})
        desc = dict((st or {}).get("descriptor") or {})
        for k in ("text", "url"):
            if isinstance(act.get(k), str):
                act[k] = _subst(act[k], values)
        if isinstance(desc.get("name"), str):
            desc["name"] = _subst(desc["name"], values)
        steps.append({"action": act, "descriptor": desc})
    return BoundSkill(skill=skill, steps=steps, values=dict(values))


def build_verifier(skill: Skill, values: dict) -> Callable[[dict], bool]:
    """The skill's deterministic post-condition, BOUND to these params. Passes only when every
    expected token (with ``{slot}`` filled to the concrete value — so the read-back checks the
    account-specific receipt) is present and no reject token remains. Read from the page, never
    from the model. This is the SAME contract used to gate admission AND runtime done."""
    expect = [_subst(str(t), values).lower() for t in (skill.verify.get("expect") or [])]
    reject = [str(t).lower() for t in (skill.verify.get("reject") or [])]

    def _verify(observation: dict) -> bool:
        obs = observation or {}
        text = (str(obs.get("text") or "") + " " + str(obs.get("url") or "")).lower()
        if any(r and r in text for r in reject):
            return False
        return all(e in text for e in expect)

    return _verify


# ── ADMIT (CI for skills — re-execute → verify.py passes; reject hardcoded) ────
@dataclass
class AdmitVerdict:
    admitted: bool
    status: str                       # admitted | quarantined
    reasons: List[str] = field(default_factory=list)
    holdout_passed: int = 0
    holdout_total: int = 0


# executor(bound_steps, values) -> (final_observation, [state_changed per step])
Executor = Callable[[List[dict], dict], tuple]


def admit(skill: Skill, executor: Executor, *, holdout: List[dict],
          min_action_steps: int = 1) -> AdmitVerdict:
    """Admit a lifted skill ONLY through a deterministic external harness. Held-out cases carry
    *different* param values than the demo, so a hardcoded value fails re-execution even if it
    slipped past the static scan. Quarantine on any failure — versioned, never destroyed."""
    reasons: List[str] = []

    # (a) anti-cheat — reject a hardcoded selector or an un-parameterized value outright.
    hc = find_hardcoded(skill)
    if hc:
        return AdmitVerdict(False, "quarantined", ["hardcoded: " + "; ".join(hc)], 0, len(holdout or []))

    # (b) usage/validity — the skill must actually DO something (non-trivial).
    n_action = sum(1 for s in skill.steps
                   if ((s.get("action") or {}).get("action")) in ("click", "type", "select", "check", "submit"))
    if n_action < min_action_steps:
        reasons.append(f"trivial: {n_action} action step(s) < {min_action_steps}")

    # (c) correctness + held-out — re-execute each sibling case → the skill's own verify passes.
    passed = 0
    cases = holdout or []
    for case in cases:
        vals = dict(case.get("values") or {})
        want = bool(case.get("expect_ok", True))
        try:
            bound = bind(skill, vals)
        except SkillBindError as e:
            reasons.append(f"bind failed {vals}: {e}")
            continue
        try:
            obs, changes = executor(bound.steps, vals)
        except Exception as e:                        # a real executor error is a real failure
            reasons.append(f"execute raised {vals}: {e}")
            continue
        if changes is not None and not all(bool(c) for c in changes):
            reasons.append(f"a step caused no state change for {vals}")
        verdict = build_verifier(skill, vals)(obs or {})
        if verdict == want:
            passed += 1
        else:
            reasons.append(f"verify={verdict} wanted {want} for {vals}")

    ok = (len(cases) >= 1) and (passed == len(cases)) and (n_action >= min_action_steps) and not reasons
    return AdmitVerdict(ok, "admitted" if ok else "quarantined", reasons, passed, len(cases))


# ── RETRIEVE: acquire-before-task (classify → intent-match → hard rerank) ──────
# ACTION verbs make a task skill-eligible. NO site names appear here — the agent decides WHEN to
# fetch a skill by the SHAPE of the task, never by a hardcoded per-domain rule.
_ACTION_VERBS = frozenset((
    "sign", "signup", "register", "create", "book", "reserve", "order", "buy", "purchase",
    "add", "cart", "checkout", "fill", "submit", "compose", "send", "reply", "schedule",
    "apply", "subscribe", "pay", "upload", "post", "message", "enroll", "join", "rsvp",
    "download", "install", "cancel", "renew", "update", "change", "set", "enable",
))
_ACTION_PHRASES = re.compile(r"\b(sign ?up|log ?in|check ?out|add to cart|make (me )?an account)\b")


def classify_task(task: str) -> dict:
    """Decide autonomously whether this task warrants a learned skill — by action-shape, not by
    any site rule. Pure reads ("how many…", "what is…") are NOT skill-eligible."""
    t = _norm_task(task)
    toks = set(t.split())
    eligible = bool(toks & _ACTION_VERBS) or bool(_ACTION_PHRASES.search(t))
    return {"eligible": eligible, "intent_tokens": toks, "norm": t}


def _intent_score(intent_tokens: set, skill: Skill) -> float:
    """Deterministic stand-in for an intent embedding: cosine-style token overlap over the skill's
    resident description + name + tags (L1 fields only)."""
    words = set(_norm_task(
        " ".join([skill.description or "", skill.name or "", " ".join(skill.site_tags or [])])).split())
    if not words or not intent_tokens:
        return 0.0
    inter = intent_tokens & words
    return len(inter) / ((len(intent_tokens) * len(words)) ** 0.5)


# hard rerank knobs: precision ≫ recall. A candidate survives only if it is a site-tag hit OR it
# clears BOTH an absolute floor and a strong fraction of the best score (so a lone distractor,
# which scores well below the true match, is dropped).
RERANK_FLOOR = 0.12
RERANK_KEEP_FRAC = 0.6


def retrieve(task: str, url: str, store: "SkillStore", *, k: int = 3) -> List[Skill]:
    """Acquire-before-task. Returns the 1–3 best skill BODIES for this task, or [] when the task
    is not skill-eligible or nothing clears the precision bar. Site-tagged matches rank first;
    generic skills are the fallback."""
    if not SKILLS_ENABLED:
        return []
    cls = classify_task(task)
    if not cls["eligible"]:
        return []
    host = _domain(url)
    pool = [s for s in store.all() if s.status in ("admitted", "shadow")]
    scored = sorted(((_intent_score(cls["intent_tokens"], s), s) for s in pool),
                    key=lambda x: x[0], reverse=True)
    candidates = [(sc, s) for sc, s in scored if sc > 0][: max(k * 2, 6)]
    if not candidates:
        return []
    best = candidates[0][0]
    survivors: List[tuple] = []
    for sc, s in candidates:
        site_hit = bool(host) and any(tag and (tag in host or host in tag) for tag in s.site_tags)
        if site_hit or (sc >= RERANK_FLOOR and sc >= best * RERANK_KEEP_FRAC):
            survivors.append((1 if site_hit else 0, sc, s))
    # site-tagged first, then score; load only the 1..k survivor bodies.
    survivors.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [s for _h, _sc, s in survivors[:k]]


# ── replay (reuse the recipe self-heal verbatim) ──────────────────────────────
def replay_indices(bound: BoundSkill, live_elements: List[dict]) -> Optional[List[Optional[int]]]:
    """Resolve each bound step's descriptor to a live element index via ``recipes.match_index``.
    Returns None on ANY divergence (a recorded element is gone) so the caller self-heals to the
    full live loop — a bad replay can never make the agent wrong, only fall back to thinking."""
    idxs: List[Optional[int]] = []
    for st in bound.steps:
        act = (st.get("action") or {})
        if act.get("action") in ("navigate", "scroll", "back"):
            idxs.append(None)                         # url/structural — no element to resolve
            continue
        idx = match_index(st.get("descriptor") or {}, live_elements)
        if idx is None:
            return None
        idxs.append(idx)
    return idxs


# ── LIFECYCLE: usage/success-rate prune + embedding-dedup merge ────────────────
def record_outcome(store: "SkillStore", skill_id: str, success: bool) -> None:
    s = store.get(skill_id)
    if not s:
        return
    s.usage_count += 1
    if success:
        s.success_count += 1
    store.put(s)


def prune(store: "SkillStore", *, min_usage: int = 5, min_success_rate: float = 0.5,
          dedup: bool = True) -> dict:
    """Deterministic (non-LLM) curator: demote chronically-failing skills and merge near-duplicate
    ones. Demotion = quarantine (versioned, recoverable), NEVER a hard delete — so a bad prune is
    reversible and the LLM-rewrite collapse (18,282→122 tokens) can't happen here."""
    demoted: List[str] = []
    merged: List[str] = []
    for s in list(store.all()):
        if s.status == "admitted" and s.usage_count >= min_usage and s.success_rate < min_success_rate:
            s.status = "quarantined"
            store.put(s)
            demoted.append(s.skill_id)

    if dedup:
        live = [s for s in store.all() if s.status in ("admitted", "shadow")]
        seen: List[Skill] = []
        for s in sorted(live, key=lambda x: (x.success_rate, x.usage_count), reverse=True):
            dup = next((k for k in seen if _desc_jaccard(k, s) >= 0.9
                        and set(k.site_tags) == set(s.site_tags)), None)
            if dup is not None:
                s.status = "quarantined"              # the weaker twin is parked, not destroyed
                store.put(s)
                merged.append(s.skill_id)
            else:
                seen.append(s)
    return {"demoted": demoted, "merged": merged}


def _desc_jaccard(a: Skill, b: Skill) -> float:
    wa = set(_norm_task((a.description or "") + " " + (a.name or "")).split())
    wb = set(_norm_task((b.description or "") + " " + (b.name or "")).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


# ── builtin workflow skills (loop registration) ───────────────────────────────
def builtin_skills() -> List[Skill]:
    """Code-backed, service-agnostic workflow skills that ship with the engine. The S6
    signup-and-verify core is registered here — its abstract, selector-free steps + deterministic
    signed-in verify contract (``signup_verify.verify_signed_up``) are exactly a generic skill."""
    from . import signup_verify as _signup_verify  # lazy — see the module-top note (avoids a cycle)
    steps = [{"action": {"action": s.value}, "descriptor": {}} for s in _signup_verify.SIGNUP_STEPS]
    signup = Skill(
        skill_id="signup-and-verify",
        name="signup-and-verify",
        description=("create an account on an arbitrary web service and clear its email "
                     "verification code step end to end; sign up register make an account"),
        slots=[
            Slot("service_url", "url", required=True),
            Slot("email", "email", required=True),
            Slot("password", "string", required=False),
            Slot("username", "string", required=False),
        ],
        steps=steps,
        verify={"expect": [], "reject": ["verification code", "check your email", "enter your password"]},
        site_tags=[],                                  # service-agnostic → generic
        tier="generic", version=getattr(_signup_verify, "__version__", "0.1.0"),
        status="admitted", kind="workflow",
    )
    return [signup]


# ── the store (in-memory registry + on-disk JSON) ─────────────────────────────
class SkillStore:
    """A tiny registry. Builtin workflow skills are always present; lifted/admitted skills persist
    one JSON file per skill under ``ANTICIPY_SKILL_DIR``. Reads are cheap and side-effect-free;
    only ``save``/``put`` touch disk."""

    def __init__(self, directory: Optional[pathlib.Path] = None, *, seed_builtins: bool = True) -> None:
        self.dir = pathlib.Path(directory) if directory else _DIR
        self._mem: dict = {}
        if seed_builtins:
            for s in builtin_skills():
                self._mem[s.skill_id] = s
        self._load_disk()

    def _load_disk(self) -> None:
        try:
            if not self.dir.exists():
                return
            for p in sorted(self.dir.glob("*.json")):
                try:
                    self._mem_put(Skill.from_json(json.loads(p.read_text())))
                except Exception:
                    continue
        except Exception:
            pass

    def _mem_put(self, s: Skill) -> None:
        self._mem[s.skill_id] = s

    def all(self) -> List[Skill]:
        return list(self._mem.values())

    def get(self, skill_id: str) -> Optional[Skill]:
        return self._mem.get(skill_id)

    def put(self, skill: Skill) -> None:
        """Update in memory and persist (builtins stay in-memory only — they are code-backed)."""
        self._mem_put(skill)
        if skill.kind != "workflow":
            self._persist(skill)

    def save(self, skill: Skill) -> bool:
        """Persist a lifted/admitted skill. Returns False for a workflow (code-backed) skill."""
        self._mem_put(skill)
        if skill.kind == "workflow":
            return False
        return self._persist(skill)

    def _persist(self, skill: Skill) -> bool:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / f"{skill.skill_id}.json").write_text(json.dumps(skill.to_json(), indent=2))
            return True
        except Exception:
            return False
