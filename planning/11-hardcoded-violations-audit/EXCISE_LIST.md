# Hardcoded violations. Excise list. Anticipy V7.

Audit drafted 2026-05-29. Audited tree: `/Users/omarebrahim/Developer/Anticipy-V7/`.

Anticipy is a universal action agent. Hardcoded skill libraries, per-app recipe registries, regex verb whitelists, and hand-written intent enums are architectural violations because they cap what the product can do at the set of patterns Omar (or a planner) thought to enumerate. The Claude-grade ceiling is reached only when the planner reasons over the live DOM + screenshot + dossier with an LLM and decides each step at runtime. Below is every violation I found, ranked, with a replacement spec.

Severity legend. P0 blocks the universal-agent architecture. Must excise before any "30 verticals" demo. P1 brittle. Survives a demo, kills generalization. P2 stylistic.

## V1. `_is_actionish` verb-regex whitelist. P0.

File: `engine/app/product/server.py:2548-2566`.

```python
def _is_actionish(text: str) -> bool:
    low = (text or "").lower()
    return bool(re.search(
        r"\b(should|need|needs|owe|owes|owed|"
        r"draft|drafts|drafted|drafting|"
        r"email|emails|emailed|emailing|"
        r"mail|mails|mailed|mailing|"
        r"send|sends|sent|sending|"
        r"share|shares|shared|sharing|"
        r"forward|forwards|forwarded|forwarding|"
        r"told|tell|tells|telling|"
        r"ask|asks|asked|asking|"
        r"remind|reminds|reminded|reminding|"
        r"schedule|schedules|scheduled|scheduling|"
        r"book|books|booked|booking|"
        r"calendar|"
        r"waiting|pending|outstanding|due|"
        r"sitting in (my )?drafts?|still in (my )?drafts?|"
        r"get .* over|follow up|let .* know)\b", low))
```

Why this is a violation. The prior planner expanded a small whitelist into a 40-verb regex with three idiom patterns ("sitting in my drafts", "let .* know"). Any utterance that lawyer / doctor / construction-PM verticals naturally produce ("file the motion", "order the labs", "draw the lien waiver", "pull the trust deed") gets dropped on the floor because the verb isn't in the table. We cannot enumerate every domain's verbs. The function is the gate between "ambient capture" and "would-anticipy-do-something-about-this," so a missed verb means the agent is silently blind.

Replacement. One LLM call to a fast model. Haiku 4.5 (Anthropic) or DeepSeek V4 Flash with prompt caching on the system prompt. Returns `{is_actionish: bool, confidence: float, kind: "request"|"latent_intent"|"chatter"|"third_party"}`. Latency target < 100 ms with cache hit (cache the system prompt, vary only the user utterance + last 3 transcript lines). Prompt shape: "Decide whether this utterance plausibly contains an action the user wants Anticipy to complete on their behalf. Latent wishes ('I should email Karen') count. Third-party requests ('he asked if she could') do not. Output only JSON." With prompt caching the input tokens collapse to the user delta on every call after the first, so cost is essentially the output tokens (1-2 JSON fields, ~20 tokens).

Effort: 1 hour (write prompt, write JSON-parse, wire fallback when LLM errors → assume true, never drop an utterance).

## V2. `_fastpath_plan_from_memory` deterministic name match. P0.

File: `engine/app/product/server.py:5276-5357`.

```python
def _fastpath_plan_from_memory(instruction: str,
                                profile_obj: dict) -> dict | None:
    ...
    for name, email, aliases in candidates:
        haystack_tokens = []
        first = name.split()[0] if name.split() else ""
        if first and len(first) >= 3:
            haystack_tokens.append(first.lower())
        for alias in aliases:
            if alias and len(alias) >= 3:
                haystack_tokens.append(alias.lower())
        if any(t in text_lower for t in haystack_tokens):
            ...
    ...
    plan = {
        "mode": "act", "person": person, ...
        "intent": "email_draft",
        "task": (f"Open Gmail and create a draft email to {recipient} "
                 f"about: {instruction.strip()[:240]}. "
                 f"Do not send it; leave it as a draft."),
        ...
    }
```

Why this is a violation. Two layers of programming-by-string: (a) hardcoded substring match on first names + aliases, (b) hardcoded intent string "email_draft" with a hardcoded Gmail draft task template. The function explicitly hardcodes the surface ("Open Gmail"), the operation ("create a draft"), and the safety guard ("Do not send it"). A lawyer's matter-management system, a sales rep's Salesforce, a doctor's Epic chart all want the same "name → action" resolution but cannot use this code path; they'd silently fall through to the slower LLM path that was supposed to handle the general case anyway. So this is not even a performance win for non-Gmail flows. It is a Gmail special case dressed up as a fast path.

Replacement. Same single LLM call as V1 but expanded. Input: `(utterance, recent_3_lines, dossier_people[], active_surface_url_if_any)`. Output: `{mode: "act"|"clarify"|"ignore", person: {name, email, id}|null, surface_hint: "gmail"|"google_calendar"|"epic"|<free-form>, intent_verb: <free-form snake_case>, task_description: <one sentence>, ambiguity_reasons: []}`. The model decides the surface from the utterance, the dossier, and whatever active-tab context is available. NO hardcoded Gmail template. Latency budget: 200 ms with prompt caching on the system prompt + dossier (the dossier changes only when onboarding updates fire, so it caches cleanly). Combine with V1 in a single call; one LLM trip does is-actionish + person-resolution + plan-shape.

Effort: 2 hours combined with V1.

## V3. `_fastpath_pronoun_resolve` pronoun match. P0.

File: `engine/app/product/server.py:5399-5476`. Plus the helper hardcoded pronoun tuples at `:5360-5396`.

```python
_FEMALE_PRONOUNS = ("she", "her", "hers", "herself")
_MALE_PRONOUNS = ("he", "him", "his", "himself")
_NEUTRAL_PRONOUNS = ("they", "them", "their", "theirs", "themself", "themselves")
...
def _pronoun_matches(person_pronouns: str, gender: str) -> bool:
    ...
    if gender == "female":
        return "she" in raw or "her" in raw
    if gender == "male":
        return "he" in raw or "him" in raw
    if gender == "neutral":
        return "they" in raw or "them" in raw
    return False
```

Why this is a violation. Bins humans into three buckets by tokenizing pronouns with regex. Misses ze/zir, xe/xem, neopronouns, language-mixed pronouns, possessive idioms ("hisself" in dialect), and silently mis-classifies anyone whose dossier `pronouns` field doesn't contain the substring "she" or "he" or "they". Also redundant: the dossier already carries the literal `pronouns` string per person, so the right behavior is to ask the LLM "does utterance pronoun match this person's pronoun string" and let the LLM reason rather than substring-search.

Replacement. Folded into V2's single LLM call. The dossier line for each person already has `pronouns: "she/her"`, so the prompt feeds the model `{name, role, pronouns}` per person and asks it to resolve the reference. Zero hardcoded pronoun tables.

Effort: covered by V2.

## V4. `_PRONOUN_GENDER` map duplicated in 3 files. P1.

Files:
- `engine/app/product/dossier_active_loader.py:26-30`
- `engine/app/product/scoped_memory.py:36-40`
- `engine/app/product/person_resolver.py:15-18`

```python
_PRONOUN_GENDER = {
    "she": "f", "her": "f", "hers": "f", "herself": "f",
    "he": "m", "him": "m", "his": "m", "himself": "m",
    "they": "n", "them": "n", "their": "n", "theirs": "n", "themself": "n",
}
```

Why this is a violation. Three near-identical (and subtly different — `dossier_active_loader` includes "herself" but `person_resolver` doesn't) copies of the same gender bucketing logic. Three places to forget to update when adding a pronoun. None of them actually need to exist: the dossier already stores each person's pronouns string, so dossier-driven resolution can compare strings directly without the lookup table. The single LLM call in V2/V3 eliminates the need entirely.

Replacement. Delete all three. The dossier's `Person.pronouns` field is the source of truth. Comparisons happen inside the LLM call from V2/V3.

Effort: 30 minutes (delete + verify nothing else imports them).

## V5. `safety.py` ALWAYS_BLOCKED / ALWAYS_CONFIRM keyword tables. P2 (intentional safety floor).

File: `engine/app/safety.py:34-143`.

```python
ALWAYS_BLOCKED: list[str] = [
    "delete account", "delete my account", "remove account", ...
    "wire transfer", "send money", "transfer funds", ...
    "format disk", "factory reset", "wipe disk", "rm -rf", "drop database", ...
]
ALWAYS_CONFIRM: list[str] = [
    "purchase", "buy", "order", "checkout", "pay", ...
    "cancel", "unsubscribe", "refund", ...
    "send email", "send message", "send dm", "send text", ...
]
```

Verdict. KEEP AS SAFETY FLOOR. The file's own docstring explicitly calls this "deterministic floor" and pairs it with an LLM verdict (`safety_check`) that overrides it. The defensive-depth rationale ("a single LLM regression cannot allow a clear delete-my-account through") is correct. A money-movement command should never depend on the LLM behaving today. Document this carve-out in the architecture doc but do not excise.

Caveat. `safety.py` is only imported by the legacy Browser Use stack (`engine/app/main.py` and friends). The shipping server (`engine/app/product/server.py`) uses `_IRREVERSIBLE_VERB_TRIGGERS` and `_IRREVERSIBLE_INTENT_KINDS` (V6 below). Decide which floor is canonical and ensure the shipping path imports it; right now both exist and only one is wired in.

Effort: 1 hour to consolidate the two floors into one canonical floor module that the shipping server imports.

## V6. `_IRREVERSIBLE_VERB_TRIGGERS` and `_IRREVERSIBLE_INTENT_KINDS`. P2 (safety floor) but with caveat.

File: `engine/app/product/server.py:2623-2643`.

```python
_IRREVERSIBLE_VERB_TRIGGERS = (
    " buy ", " purchase ", " pay ", " transfer ", " refund ", " subscribe ",
    " unsubscribe ", " wire ", " venmo ", " zelle ", " checkout ",
    " place order ", " send to ", " send email to ", " publish ",
    " post to ", " delete ", " cancel subscription ",
)

_IRREVERSIBLE_INTENT_KINDS = frozenset({
    "ecommerce_admin_surface_missing", "ecommerce_cart_prep",
    "send_external_email", "external_post", "purchase", "payment",
    "transfer", "subscription_change", "irreversible_delete",
    "refund", "buy_label", "void_label",
})
```

Verdict. KEEP the irreversibility floor (money + delete + send + publish). Excise the per-intent-kind enum (`_IRREVERSIBLE_INTENT_KINDS`) because it encodes a hardcoded intent taxonomy that the universal agent does not need. The agent should classify "irreversible" per-action via the LLM in `risk_assessor` (see V7) and only fall back to the verb floor when the LLM is unavailable.

Effort: 1 hour to delete the intent-kind frozenset and rewire callers.

## V7. `risk_assessor.py` verb tables + hardcoded irreversibility weights. P1.

File: `engine/app/product/risk_assessor.py:17-171`.

```python
MONEY_VERBS = {"pay", "paid", "payment", "purchase", "buy", ...}
IRREVERSIBLE_VERBS = {"send", "publish", "post", "tweet", "delete", ...}
THIRD_PARTY_VERBS = {"email", "text", "message", "dm", "call", ...}
ROUTINE_VERBS = {"note", "remind", "reminder", "draft", "create", ...}

def _irreversibility(tokens: set[str]) -> float:
    if "draft" in tokens and not (tokens & {"send", "publish", ...}):
        return 0.0
    score = 0.5 if (tokens & IRREVERSIBLE_VERBS) else 0.0
    if tokens & {"delete", "wipe", "destroy"}:
        score = 1.0
    elif "send" in tokens:
        score = max(score, 0.7)
    elif tokens & {"publish", "post"}:
        score = max(score, 0.8)
    elif "cancel" in tokens and (tokens & {"subscription", "membership"}):
        score = max(score, 0.8)
    return score
```

Why this is a violation. Token-set membership against 4 hand-curated verb dictionaries, then a hardcoded irreversibility score lookup with magic numbers (0.5, 0.7, 0.8, 1.0). The agent cannot evaluate "file for partial summary judgment" or "submit the prior auth to BCBS" because the verbs aren't in any bucket. Even commerce-only it misses "expense", "remit", "ach", "drawdown", "settle".

Replacement. Replace `assess()` with an LLM call: `risk_assess(intent_text, surface_target, binding, memory_context) -> RiskAssessment`. Same return shape so callers don't change. Prompt: "Score this intended action on (level, irreversibility, money_amount, third_party_impact). Output JSON." Single 200-token call. Cache on the prompt body (caller passes a stable hash). Keep `parse_money_amount()` (the deterministic dollar-string parser) as a helper the LLM cannot replicate cheaply; feed its output into the LLM as a hint. Fall back to the verb tables ONLY when the LLM is unavailable. Latency target: 150 ms cached.

Effort: 3 hours (write new assess() that wraps the LLM call, keep the data classes, keep the dollar parser, write the fallback path).

## V8. `roles/` role templates. P0 if used for cold start. P2 if dev-only.

Files: `roles/judge.md`, `roles/planner.md`, `roles/worker.md`, `roles/mp3_evaluator.md`.

Verdict. These are dev-loop role prompts for the V7 Ralph cycle (judge/planner/worker pattern that the human-ready loop and finish-overnight launchd jobs read). They do NOT define user-facing skills. They are not "the role library" the prior planner wanted; that was an alleged plan in the now-superseded ROADMAP.md, not a shipped registry.

KEEP. Confirm by grep: no production code path imports these `.md` files. They are read by `tools/anticipy_human_ready_loop.sh` and `tools/finish_overnight.sh` as cycle prompts for `claude --print`. They are developer scaffolding, not product code.

Effort: 0 (no excision needed). Note in the universal-agent design doc that "role" in `roles/*.md` refers to the dev loop, not to a user-facing skill library, so a future agent doesn't conflate them.

## V9. Per-app recipes search. Mostly clean.

Searched: `engine/**/*_recipe.py`, `*_skill.py`, `gmail_*`, `calendar_*`, `salesforce_*`, `notion_*`, `slack_*`, `drive_*`.

Hits:
- `engine/app/action_engine/gmail_compose.py`. P1 violation: 220-line module with a regex intent parser (`parse_draft_intent`), a Gmail-specific URL builder (`_compose_url`), and a hardcoded Gmail compose URL template `https://mail.google.com/mail/?...`. Built originally to make the resolvable-people fast-path work without going through the V4 skill runner. The shipping path now goes through `DSv4SkillRunner` over CDP (per MAP.md section 4a), so this module's `create_gmail_draft` is mostly bypassed for production. Keep ONLY the URL builder as a constant if absolutely needed for the demo, but its regex intent parsing (`parse_draft_intent`) at lines 102-114 must die. Replacement: LLM extracts `(to, subject, body)` from the utterance using V2's combined call.
- `engine/app/product/action_recipes.py`. P2: the `Recipe` dataclass and `RecipeStore` are a per-user LEARNED recipe cache, not a hardcoded registry. The docstring explicitly says "Lightweight, account-scoped, NOT a global skills library." Keep.
- No `*_skill.py` files outside `action_engine/dsv4_skill_runner.py`, which is the universal Ralph Loop (verified by reading lines 700-870; it decomposes any task with an LLM, then loops screenshot → AX tree → LLM-decide → CDP dispatch → vision-verify, generically).

Verdict on action_engine: clean. The name `dsv4_skill_runner` is misleading (there are no per-skill code paths), but the implementation is a universal loop.

## V10. `engine/config/` per-app config directory. ABSENT (good).

Searched: `engine/config/`. Does not exist.

The prior planner's ROADMAP.md item #9 proposed it ("engine/config/auth_profiles/<app>.json per supported SaaS"). The handoff doc flags this as the canonical violation Omar called out. Confirmed: no such directory exists today. Do not let any future PR introduce it.

## V11. action_binder hardcoded surface-domain table. P1.

File: `engine/app/product/action_binder.py:24-48`.

```python
_BROWSER_DOMAINS: list[tuple[str, str]] = [
    ("gmail", "gmail"), ("mail.google", "gmail"),
    ("calendar.google", "google_calendar"),
    ("docs.google", "google_docs"), ("sheets.google", "google_sheets"),
    ("drive.google", "google_drive"), ("opentable", "opentable"),
    ("doordash", "doordash"), ("ubereats", "uber_eats"),
    ("amazon", "amazon"), ("notion", "notion"), ("linear.app", "linear"),
    ("slack.com", "slack"), ("zoom.us", "zoom"),
]
_NATIVE: list[tuple[str, str]] = [
    ("reminder", "native_macos_reminders"),
    ("notes app", "native_macos_notes"),
    ("imessage", "native_macos_messages"),
    ("apple calendar", "native_macos_calendar"),
]
_VISION = ("figma", "sketch", "photoshop", ...)
_EMAIL = ("email", "draft", "send to", ...)
_CAL = ("calendar", "schedule", "book", "meeting", ...)
_PAY = ("pay", "venmo", "send $", ...)
_MSG = ("text ", "imessage", "slack", "dm ")
_REF_KWS = ("email ", "draft to ", "send to ", ...)
```

Why this is a violation. The binder's `_pick(intent, text, context)` function picks a `surface_target` by scanning the utterance for a known domain substring. Outside the 14 listed sites the binder always returns `"browser"` (generic). New verticals (Epic, Salesforce, Procore, Canvas) get no surface routing. Worse, the `_required()` function (lines 88-101) decides required slots by the same verb-table match, so a "file an expense" or "post to ChartChex" call gets no slot extraction at all.

Replacement. Single LLM call: `(intent_text, active_tab_url, recent_3_lines) -> {surface_target: str, required_slots: list[str]}`. Surface_target is free-form domain (the model picks `epic.com` if the utterance mentions Epic). Required slots are free-form too (`["matter_id", "client_name"]` for a legal task). The binder then composes the action via the universal dispatcher loop, which already operates on free-form surface_target. Latency budget: 150 ms cached on the system prompt (the prompt itself is invariant; only the user delta varies).

Effort: 4 hours (rewire `_pick`, `_required`, `_refs`).

## V12. `login_wall_responder.KNOWN_LOGIN_HOSTS` table. P1.

File: `engine/app/product/login_wall_responder.py:33-60`.

```python
KNOWN_LOGIN_HOSTS: dict[str, str] = {
    "accounts.google.com": "Google",
    "mail.google.com/mail/u/0/_/_/signin": "Gmail",
    "login.microsoftonline.com": "Microsoft",
    "slack.com/signin": "Slack",
    ...
}
```

Why this is a violation. 28-entry hardcoded login-host table. A doctor's hospital SSO, a lawyer's case management vendor, a construction PM's permit portal all hit unique login surfaces not in this list and the responder silently misses them. The `_TITLE_HINTS` fallback ("sign in", "log in", etc.) catches some but is fragile and English-only.

Replacement. Have the planner's screenshot+DOM evaluator pass on each step ("Is the current page a login wall? If so, name the service.") via an existing per-step LLM call rather than a separate detector. The LLM sees the page chrome generically and produces `{is_login_wall: bool, service_name: str}`. Login walls are already part of the universal-agent visual-reasoning loop; this special-case dispatcher should not exist as a separate file.

Effort: 2 hours (delete the file, move the check into the per-step planner prompt).

## V13. Intent extractor hardcoded type + surface enums. P1.

File: `engine/app/product/intent_extractor.py:32-34, 72-73`.

```python
INTENT_TYPES = ("act", "ask", "remind", "research", "create",
                "modify", "delete", "answer", "ignore")
RISK_LEVELS = ("low", "medium", "high")
...
"  target_surface: gmail|google_calendar|notion|native_calendar|"
"reminders|opentable|google_search|chrome|none.\n"
```

Why this is a violation. The intent extractor's prompt enumerates a closed set of intent types AND a closed list of valid `target_surface` values. The LLM is asked to choose from 9 intent types and 8 surfaces. Any utterance that wants a 10th type or a 9th surface (Epic, Salesforce, Workday, Procore) gets coerced into `"chrome"` or `"none"` and the downstream binder loses the routing signal.

Replacement. Drop the closed `target_surface` enum from the prompt. Allow free-form snake_case surface names ("epic_chart", "salesforce_opportunity", "procore_rfi"). Keep `INTENT_TYPES` as a soft hint but allow `"other"`. Document in the prompt: "Pick the smallest specific surface name you can. Free-form."

Effort: 1 hour (prompt edit + downstream tolerance for unknown surface strings).

## V14. Test recipients leaking into shipping code. NONE FOUND (good).

Searched: `omarkebrahim+anticipy-*` in `engine/app/`. Only hits are in `engine/tests/anticipy_acceptance.py:256-260` and `engine/tests/agent_reliability.py:18-20`, which is correct (tests only). No leak into production. CLAUDE.md's flag still stands as a watchout for future PRs.

## V15. Hardcoded Gmail / Calendar URLs in surface code. P2.

Hits:
- `engine/app/action_engine/gmail_compose.py:128`. `"https://mail.google.com/mail/?{params}"`. The compose-URL builder. Acceptable iff we agree Gmail compose-URL is a stable surface contract (it is, per Google's own docs). Document, keep.
- `engine/app/end_state_verifier.py:353`. `https://mail.google.com/mail/u/0/#sent` for the legacy verifier. Legacy Browser Use path, not shipping. Excise with the rest of the legacy stack.
- `engine/app/end_state_verifier.py:399`. `https://calendar.google.com`. Same. Legacy.

Verdict. Keep only the compose-URL constant inside `gmail_compose.py` if the demo needs it; everything else is in dead code. Effort: covered by the broader "delete legacy Browser Use stack" cleanup already documented in MAP.md section 11e.

## Total LLM-call budget analysis.

We are proposing to replace 7 hardcoded checks (V1, V2, V3, V7, V11, V12, V13) with LLM calls. Naively that adds 7 round trips per utterance. With prompt caching and combination:

- V1 + V2 + V3 + V13 combine into ONE call at the listen-loop boundary. Input: (utterance, recent 3 lines, dossier compressed). Output: `{is_actionish, person, surface_hint, intent_verb, required_slots, ambiguity_reasons, plan_shape}`. Latency 200-400 ms with cache hit on the system prompt and the dossier (both are stable across the session).
- V11 (action_binder surface pick) folds into V2 (the listen-loop call already returns surface_hint).
- V7 (risk assessor) is ONE call after the planner has a binding. 150 ms cached.
- V12 (login-wall detect) folds into the per-step planner call inside the universal action loop. Zero additional calls.

Net add per utterance: ONE combined call at ingest (200-400 ms) + ONE risk-assess call before dispatch (150 ms). With DeepSeek V4 Flash via prompt caching the input cost goes to ~$0.0001/call. Total added latency: ~500 ms worst case, hidden behind the ASR window so the user feels no delta.

Recommended fast model: DeepSeek V4 Flash via OpenRouter (already wired in `platform_adapter.model_call`, hard-pinned per CLAUDE.md). Anthropic Haiku 4.5 is the fallback when DeepSeek 429s; the website model broker can cascade. Prompt caching: OpenRouter supports `cache_control` on Anthropic; DeepSeek caches automatically for matching prefixes. Cache the system prompt + the dossier JSON + the people list; vary only the trailing user delta.

Batching note: do NOT batch across utterances. Each utterance is real-time. Batch internally within a single utterance by combining intent classification + person resolve + plan shape into one call (already counted above).

## Estimated total effort to excise (P0 + P1).

| ID | Item | Effort |
|---|---|---|
| V1 | _is_actionish | 1h |
| V2 | _fastpath_plan_from_memory | (folded with V1+V3) |
| V3 | _fastpath_pronoun_resolve | (folded with V1+V2) |
| V4 | _PRONOUN_GENDER duplicates | 30m |
| V6 | _IRREVERSIBLE_INTENT_KINDS frozenset | 1h |
| V7 | risk_assessor verb tables | 3h |
| V11 | action_binder surface map | 4h |
| V12 | login_wall_responder file | 2h |
| V13 | intent_extractor closed surface enum | 1h |
| Combined call (V1+V2+V3+V13) | one new module + wire | 3h |

Total: ~16 hours of focused engineering work. Verifier: re-run Z-001 (`scripts/v7/z001_e2e_harness.py`, expect 9/9 PASS) plus CHECK 16 (`engine/tests/agent_reliability.py`, expect resolvable ≥19/20 and ambiguous = 10/10) after each excision to confirm nothing regressed.

## Safety-floor exceptions (keep).

These stay because the architectural goal is "defense in depth," not "no hardcoded checks at all."

1. `engine/app/safety.py:ALWAYS_BLOCKED` for delete-account / wire-transfer / format-disk. The LLM verdict is the primary surface; the keyword table is the floor that a single LLM regression cannot blow through.
2. `engine/app/safety.py:PASSWORD_INTENT_PATTERNS` and `FINANCIAL_TRANSACTION_PATTERNS`. Same logic; these regexes back-stop the LLM.
3. `engine/app/product/server.py:_IRREVERSIBLE_VERB_TRIGGERS`. The "always show a confirm card" floor at the listen-loop boundary. Even if the LLM marks an action as low-risk, money/delete/publish/send verbs still force a confirm card. Per Omar's 2026-05-26 "never decline, always pause" directive.
4. `engine/app/anticipy/irreversible_intents.json`. Referenced by `server.py:5623` (though the JSON file may not ship; the loader falls back to empty set). If it ships, it's the canonical hardcoded list of intents that ALWAYS pause on a confirm card. Acceptable as a floor; the LLM should be deciding most cases but this catches regressions.

Document each of these in the universal-agent architecture doc as explicit, intentional floors. Anything else hardcoded is a violation.

## Action for the next planner / engineer.

1. Read this file. Do not add to any of the regex/verb tables above.
2. Open one PR per P0 violation (V1, V2, V3, V11) or one combined PR with the unified ingest LLM call. After each PR run Z-001 + CHECK 16, paste result.json into the commit message.
3. Decide whether V7's risk_assessor rewrite happens in the same combined PR or separately; recommend separate to keep PR diff small.
4. P1 violations (V4, V6, V12, V13) can be folded into a "deletion" PR after the combined LLM call is in.
5. Tag the universal-agent design doc (`planning/08-universal-action-agent/DESIGN.md`) with the new combined-call architecture once landed so future planners do not regenerate the old hardcoded shapes.
