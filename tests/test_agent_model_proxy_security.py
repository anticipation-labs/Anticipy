from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_key_route_never_returns_server_credentials():
    source = (ROOT / "backend/pb_hooks/agent_key.pb.js").read_text()
    key_route = source.split('routerAdd("POST", "/agent/llm"', 1)[0]
    assert "llm_proxy: true" in key_route
    assert "openrouter_key" not in key_route.lower()
    assert "service_token" not in key_route.lower()
    assert '"Authorization": "Bearer "' not in key_route
    assert "GEMINI_API_KEY" in key_route


def test_model_proxy_requires_private_agent_credential_and_allowlist():
    source = (ROOT / "backend/pb_hooks/agent_key.pb.js").read_text()
    proxy = source.split('routerAdd("POST", "/agent/llm"', 1)[1]
    assert "X-Anticipy-Agent-ID" in proxy
    assert "X-Anticipy-Agent-Token" in proxy
    assert "paired = true" in proxy
    assert "model is not enabled for browser agents" in proxy
    assert '"Authorization": "Bearer " + openrouterKey' in proxy
    assert '"x-goog-api-key": geminiKey' in proxy
    assert "generateContent" in proxy
    assert "systemInstruction" in proxy
    assert "inlineData" in proxy
    assert 'provider: "google"' in proxy
    assert "max_tokens: boundedMax" in proxy
    # 2026-09-05: the floor is 512, not 64 — the browser model thinks before it
    # answers and the thinking counts against the cap; at 64 its one-token
    # verdicts came back cut off (research/evals/login-wall-2026-09-05/).
    # The extension floors at the same number; this pins the proxy's lock.
    assert "const REPLY_FLOOR = 512;" in proxy
    assert "Math.max(REPLY_FLOOR," in proxy
    assert "Math.max(64," not in proxy
    assert "Math.min(4096" in proxy
    assert "maxOutputTokens: boundedMax" in proxy
    assert "const gemini3" in proxy
    assert "/^gemini-3" in proxy
    assert 'thinkingLevel: "low"' in proxy
    assert "thinkingBudget: 0" in proxy
    assert "if (!gemini3) generationConfig.temperature = 0" in proxy
    assert 'responseMimeType = "application/json"' in proxy


def test_model_proxy_routes_the_selected_model_instead_of_the_available_key():
    source = (ROOT / "backend/pb_hooks/agent_key.pb.js").read_text()
    proxy = source.split('routerAdd("POST", "/agent/llm"', 1)[1]
    assert 'model.indexOf("google/") === 0' in proxy
    assert "if (geminiKey && directGeminiModel)" in proxy
    assert 'provider_model: directGeminiModel' in proxy
    assert 'provider_model: model' in proxy
    assert 'body: serialized' in proxy
    assert 'if (geminiKey) {' not in proxy


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
