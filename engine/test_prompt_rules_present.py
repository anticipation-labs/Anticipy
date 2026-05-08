"""
Deterministic regression test — verifies that the named prompt rules
EXIST in their respective files. Catches accidental deletion or
rewording during refactors. No LLM required.

This is the cheap floor. The actual semantic test (does the rule
PRODUCE the expected behavior?) lives in test_prompt_rules.py
(LLM-driven, runs on the cascade).
"""
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parent.parent

PROACTIVE_INTERPRETER = (ROOT / "engine" / "app" / "proactive" / "interpreter.py").read_text()
EXTENSION_AGENT = (ROOT / "extension" / "agent.js").read_text()


# Format: (rule_name, file_label, file_text, required_phrases)
# Each phrase MUST appear (case-sensitive) in the file. If any is missing,
# the rule was lost in a refactor and the LLM no longer sees it.
RULES = [
    (
        "ASPIRATION_VS_COMMITMENT",
        "interpreter.py",
        PROACTIVE_INTERPRETER,
        [
            "ASPIRATION vs COMMITMENT",
            "I should book a flight tonight",
            "vague future time",
            "commitment signal",
        ],
    ),
    (
        "META_INTENT_SUPPRESSION",
        "interpreter.py",
        PROACTIVE_INTERPRETER,
        [
            "META-INTENT SUPPRESSION",
            "remember_to_do_list",
            "errand item list",
            "meta recital",
        ],
    ),
    (
        "VAGUE_INTENT_RULE_6",
        "interpreter.py",
        PROACTIVE_INTERPRETER,
        [
            "parameters dict is EMPTY",
            "user wants to look something up",
            "Vague candidates",
        ],
    ),
    (
        "QUOTE_VERBATIM",
        "agent.js",
        EXTENSION_AGENT,
        [
            "QUOTE VERBATIM",
            "EXACT on-page strings",
            "Single-example answers count as failure",
        ],
    ),
    (
        "MULTI_SOURCE_TASKS",
        "agent.js",
        EXTENSION_AGENT,
        [
            "MULTI-SOURCE TASKS",
            "two or more sources",
            "you MUST visit each named source",
        ],
    ),
    (
        "ANCHOR_ON_ENTITY",
        "agent.js",
        EXTENSION_AGENT,
        [
            "ANCHOR ON THE NAMED ENTITY",
            "explicitly identifies that entity",
            "Wrong-anchor extractions",
        ],
    ),
    (
        "GEOGRAPHIC_DISTANCE",
        "agent.js",
        EXTENSION_AGENT,
        [
            "GEOGRAPHIC / DISTANCE",
            "explicitly cite the reference point",
        ],
    ),
    (
        "FORM_FILL_PROGRESS",
        "agent.js",
        EXTENSION_AGENT,
        [
            "FORM-FILL PROGRESS",
            "TWO consecutive fields fail",
            "force_type",
            "naming the field",
        ],
    ),
    (
        "ACTUALLY_TAKE_ACTION",
        "agent.js",
        EXTENSION_AGENT,
        [
            "ACTUALLY TAKE ACTION",
            "observed the page state CHANGE",
            "Drafting / composing / generating text is NOT done",
        ],
    ),
    (
        "PROVIDER_REDUNDANCY",
        "agent.js",
        EXTENSION_AGENT,
        [
            "_callKimi",
            "_callDeepSeek",
            "Plan C",
            "Plan D",
        ],
    ),
]


@pytest.mark.parametrize("rule_name,file_label,file_text,phrases", RULES, ids=[r[0] for r in RULES])
def test_rule_present(rule_name, file_label, file_text, phrases):
    """The named rule must still exist verbatim in its file."""
    missing = [p for p in phrases if p not in file_text]
    assert not missing, (
        f"Rule {rule_name} in {file_label} missing required phrases: {missing}. "
        f"Was the rule deleted or reworded? If renamed, update test_prompt_rules_present.py too."
    )


def test_model_chain_order():
    """MODEL_CHAIN must list providers in A→B→C→D order: gemini → groq → kimi → deepseek."""
    config_text = (ROOT / "engine" / "app" / "config.py").read_text()
    # Extract `"name": "..."` strings in declaration order
    names = re.findall(r'"name":\s*"([a-z]+)"', config_text)
    expected_order = ["gemini", "groq", "kimi", "deepseek"]
    assert names == expected_order, (
        f"MODEL_CHAIN order {names} != expected {expected_order}. "
        f"Reordering changes which provider takes the load when Plan A 429s."
    )


def test_extension_provider_chain():
    """extension/agent.js _callLLM must try Gemini → Groq → Kimi → DeepSeek in that order."""
    text = EXTENSION_AGENT
    # Find the _callLLM function body
    start = text.find("async _callLLM(")
    assert start > 0, "_callLLM method not found in agent.js"
    # Look in the next 3000 chars for the chain
    body = text[start:start + 5000]
    # Each provider should appear in order
    pos_gemini = body.find("_callGemini(")
    pos_groq = body.find("_callGroq(")
    pos_kimi = body.find("_callKimi(")
    pos_deepseek = body.find("_callDeepSeek(")
    assert pos_gemini > 0, "_callGemini missing from _callLLM"
    assert pos_groq > pos_gemini, f"_callGroq should follow _callGemini (gemini@{pos_gemini}, groq@{pos_groq})"
    assert pos_kimi > pos_groq, f"_callKimi should follow _callGroq (groq@{pos_groq}, kimi@{pos_kimi})"
    assert pos_deepseek > pos_kimi, f"_callDeepSeek should follow _callKimi (kimi@{pos_kimi}, deepseek@{pos_deepseek})"


def test_llm_cascade_lib_present():
    """src/lib/llm-cascade.ts must export callLlm + callLlmCascade."""
    cascade_text = (ROOT / "src" / "lib" / "llm-cascade.ts").read_text()
    assert "export async function callLlm(" in cascade_text
    assert "export async function callLlmCascade(" in cascade_text
    # All four plans wired
    for plan_marker in ['"gemini"', '"groq"', '"kimi"', '"deepseek"']:
        assert plan_marker in cascade_text, f"Plan marker {plan_marker} missing from llm-cascade.ts"


def test_no_callgemini_in_intent_path():
    """The intent-extract / gates / memory-extract / preference-record path
    must use callLlm (cascade) — NOT callGemini directly. Otherwise a 429
    on Gemini silently fails the whole intent pipeline."""
    paths = [
        ROOT / "src" / "lib" / "intent-extract.ts",
        ROOT / "src" / "lib" / "intent-gates.ts",
        ROOT / "src" / "lib" / "memory-extract.ts",
        ROOT / "src" / "lib" / "preference-record.ts",
    ]
    leaks = []
    for p in paths:
        text = p.read_text()
        # callGemini may still appear in a comment or import — match the call
        # site `await callGemini(`
        if re.search(r"\bawait\s+callGemini\(", text):
            leaks.append(str(p.relative_to(ROOT)))
    assert not leaks, (
        f"These files still call callGemini directly (no cascade): {leaks}. "
        "Replace with `await callLlm(...)` from @/lib/llm-cascade so 429s fall through."
    )
