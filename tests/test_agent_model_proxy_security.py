from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_key_route_never_returns_server_credentials():
    source = (ROOT / "migration/workers/src/routes/agent.ts").read_text()
    answer = source[source.index("llm_proxy: true"):]
    answer = answer[:answer.index("});")]
    assert "openrouter" not in answer.lower()
    assert "service_token" not in answer.lower()
    assert "Bearer" not in answer
    code = "\n".join(l.split("//", 1)[0] for l in answer.splitlines())
    for credential in ("openrouter", "gemini", "api_key", "apikey", "secret", "token", "bearer"):
        assert credential not in code.lower(), f"{credential} in the key route's answer"
    assert "providerKeys(env)" in source, "the route checks a provider exists, and answers llm_proxy"
    assert "paired(env, agentId, token)" in source, "and only a paired agent gets that answer"


def test_model_proxy_requires_private_agent_credential_and_allowlist():
    source = (ROOT / "migration/workers/src/llm.ts").read_text()
    proxy = source.split("export async function llmProxy", 1)[1]
    agent = (ROOT / "migration/workers/src/routes/agent.ts").read_text()
    assert "X-Anticipy-Agent-ID" in agent and "X-Anticipy-Agent-Token" in agent
    assert "AND paired = 1" in agent, "the credential must resolve to a PAIRED row"
    assert "not a paired agent" in agent
    assert "model is not enabled for browser agents" in proxy
    assert "Bearer" in source and "x-goog-api-key" in proxy
    assert "generateContent" in proxy
    assert "systemInstruction" in proxy
    assert "inlineData" in source
    assert 'provider: "google"' in proxy
    assert "max_tokens: boundedMax" in proxy
    # 2026-09-05: the floor is 512, not 64 — the browser model thinks before it
    # answers and the thinking counts against the cap; at 64 its one-token
    # verdicts came back cut off (research/evals/login-wall-2026-09-05/).
    # The extension floors at the same number; this pins the proxy's lock.
    assert "export const REPLY_FLOOR = 512;" in source
    assert "export const REPLY_CEILING = 4096;" in source
    assert "Math.max(REPLY_FLOOR," in source
    assert "Math.max(64," not in source
    assert "Math.min(REPLY_CEILING" in source
    assert "maxOutputTokens: boundedMax" in source
    assert "const gemini3 = isGemini3(" in source
    assert "/^gemini-3" in source
    assert 'thinkingLevel: "low"' in source
    assert "thinkingBudget: 0" in source
    assert "if (!gemini3) cfg.temperature = 0" in source
    assert 'responseMimeType = "application/json"' in source


def test_model_proxy_routes_the_selected_model_instead_of_the_available_key():
    source = (ROOT / "migration/workers/src/llm.ts").read_text()
    proxy = source.split("export async function llmProxy", 1)[1]
    assert "if (keys.gemini && directGeminiModel)" in proxy
    assert "provider_model: directGeminiModel" in proxy
    assert "OpenRouter receives the selected non-Google model unchanged" in proxy
    assert "if (keys.gemini) {" not in proxy


def test_extension_uses_opaque_proxy_marker_for_production_calls():
    background = (ROOT / "extension/background.js").read_text()
    loop = (ROOT / "extension/agent_loop.js").read_text()
    assert 'const BACKEND_LLM = "backend-proxy"' in background
    assert "openrouterKey: BACKEND_LLM" in background
    # The proxy URL is built from backendBase() at call time — pinned as the
    # expression, not the old inline fetch(...) spelling, which a 2026-09-05
    # retry refactor moved into a `url` variable. This is the stronger pin:
    # it also proves the base is resolved, never hardcoded.
    assert "`${await backendBase()}/agent/llm`" in loop
    assert "fetch(url, { signal, method: \"POST\", headers, body })" in loop
    assert "X-Anticipy-Agent-Token" in loop
    assert loop.count("await modelFetch(") >= 5
    assert "const boundedPayload" in loop
    assert "max_tokens: Math.min(4096" in loop


def test_browser_certification_keeps_model_goal_out_of_exact_authority():
    runner = (ROOT / "proof/engine_certification/browser_runner.py").read_text()
    rig = (ROOT / "proof/day_zero_20.py").read_text()
    background = (ROOT / "extension/background.js").read_text()
    assert '"authority_text": source or goal' in runner
    assert '"approved_scope": source or goal' in runner
    assert 'authority_text=case.get("authority_text") or approved_scope' in rig
    assert "params._workflow?.authority_text" in background


def test_browser_certification_uses_the_paired_backend_proxy_too():
    rig = (ROOT / "proof/day_zero_20.py").read_text()
    assert "wait_for_registered_agent(rig_tag)" in rig
    assert "pair_registered_agent" in rig
    assert '"agentToken":' not in rig
    assert '"openrouterKey":' not in rig
    assert "backendUrl: DEFAULT_BASE" in rig
    assert 'agent_model = vision_model = "server-selected"' in rig
    assert '"openrouterKey": api_key' not in rig
