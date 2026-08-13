from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_key_route_never_returns_server_credentials():
    source = (ROOT / "backend/pb_hooks/agent_key.pb.js").read_text()
    key_route = source.split('routerAdd("POST", "/agent/llm"', 1)[0]
    assert "llm_proxy: true" in key_route
    assert "openrouter_key" not in key_route.lower()
    assert "service_token" not in key_route.lower()
    assert '"Authorization": "Bearer "' not in key_route


def test_model_proxy_requires_private_agent_credential_and_allowlist():
    source = (ROOT / "backend/pb_hooks/agent_key.pb.js").read_text()
    proxy = source.split('routerAdd("POST", "/agent/llm"', 1)[1]
    assert "X-Anticipy-Agent-ID" in proxy
    assert "X-Anticipy-Agent-Token" in proxy
    assert "paired = true" in proxy
    assert "model is not enabled for browser agents" in proxy
    assert '"Authorization": "Bearer " + key' in proxy


def test_extension_uses_opaque_proxy_marker_for_production_calls():
    background = (ROOT / "extension/background.js").read_text()
    loop = (ROOT / "extension/agent_loop.js").read_text()
    assert 'const BACKEND_LLM = "backend-proxy"' in background
    assert "openrouterKey: BACKEND_LLM" in background
    assert "fetch(`${base}/agent/llm`" in loop
    assert "X-Anticipy-Agent-Token" in loop
    assert loop.count("await modelFetch(") >= 5


def test_browser_certification_uses_the_paired_backend_proxy_too():
    rig = (ROOT / "proof/day_zero_20.py").read_text()
    assert "wait_for_registered_agent(rig_tag)" in rig
    assert "pair_registered_agent" in rig
    assert '"agentToken":' not in rig
    assert '"openrouterKey":' not in rig
    assert "backendUrl: DEFAULT_BASE" in rig
    assert 'agent_model = vision_model = "server-selected"' in rig
    assert '"openrouterKey": api_key' not in rig
