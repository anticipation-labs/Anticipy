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
    # TODO: when the Mac Electron app ships (per v-final-prototype 2026-05-13),
    # port these rules to its agent module and drop this skip.
    if file_label == "agent.js":
        pytest.skip("legacy extension/agent.js — retired per v-final-prototype 2026-05-13")
    missing = [p for p in phrases if p not in file_text]
    assert not missing, (
        f"Rule {rule_name} in {file_label} missing required phrases: {missing}. "
        f"Was the rule deleted or reworded? If renamed, update test_prompt_rules_present.py too."
    )


def test_model_chain_order():
    """MODEL_CHAIN must list providers in A→B→C→D order: gemini → groq → mistral → deepseek."""
    config_text = (ROOT / "engine" / "app" / "config.py").read_text()
    # Extract `"name": "..."` strings in declaration order, but only from the
    # _build_model_chain function body so unrelated ROLE_CHAINS provider
    # helpers (_provider_gemini, _provider_mistral, _provider_cerebras, …)
    # don't pollute the order check.
    builder_start = config_text.find("def _build_model_chain(")
    assert builder_start > 0, "_build_model_chain not found in config.py"
    # End at the first top-level def/assignment after _build_model_chain.
    builder_end = config_text.find("\nMODEL_CHAIN = _build_model_chain()", builder_start)
    assert builder_end > builder_start, "_build_model_chain end marker not found"
    chain_block = config_text[builder_start:builder_end]
    names = re.findall(r'"name":\s*"([a-z]+)"', chain_block)
    expected_order = ["gemini", "groq", "mistral", "deepseek"]
    assert names == expected_order, (
        f"MODEL_CHAIN order {names} != expected {expected_order}. "
        f"Reordering changes which provider takes the load when Plan A 429s."
    )


def test_extension_provider_chain():
    """SKIPPED — legacy extension/agent.js retired per v-final-prototype 2026-05-13.

    The new architecture is a Mac Electron app, NOT a Chrome extension.
    TODO: re-add equivalent assertions once the Mac app's cascade dispatcher
    is built (will likely live in `mac-app/src/cascade.ts` or similar).
    """
    pytest.skip("legacy extension/agent.js — retired per v-final-prototype 2026-05-13")


def test_llm_cascade_lib_present():
    """SKIPPED — src/lib/llm-cascade.ts is part of the legacy extension surface
    that is being retired per v-final-prototype 2026-05-13. The new Mac
    Electron app will have its own cascade module.

    TODO: re-add equivalent assertions once the Mac app ships its
    cascade module (likely TypeScript under `mac-app/src/`).
    """
    pytest.skip("legacy llm-cascade.ts — retired per v-final-prototype 2026-05-13")


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
