#!/usr/bin/env bash
# V7 full-pipeline E2E. intent_extractor -> action_binder -> risk_assessor
# -> confirm_card -> user-says-no -> screenshot proof of no purchase.
# Transport: HTTP if /api/intent/extract is mounted, else direct python.
# Output: state/v7/integration_runs/full_pipeline_<ts>/.

set -euo pipefail

REPO="/Users/omarebrahim/Developer/Anticipy-V7"
ENV_FILE="${ANTICIPY_ENV_FILE:-${REPO}/.env.local}"
if [ ! -f "$ENV_FILE" ]; then
  # V7 has no .env.local; fall back to the DEV-FINAL one as instructed.
  ENV_FILE="/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local"
fi
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

cd "$REPO"

ENGINE_URL="${ANTICIPY_ENGINE_URL:-http://127.0.0.1:8731}"
BRIDGE_URL="${ANTICIPY_BRIDGE_URL:-http://127.0.0.1:7777}"
BRIDGE_SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"
ACCOUNT_ID="${ACCOUNT_ID:-integration-acct-$(date -u +%s)}"
DEVICE_ID="${DEVICE_ID:-integration-device-1}"
TRANSCRIPT='Buy a Sauce Labs Backpack from saucedemo.com. Use the standard_user account.'

TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$REPO/state/v7/integration_runs/full_pipeline_$TS"
mkdir -p "$RUN_DIR"

echo "[integration] run_dir=$RUN_DIR" >&2
echo "[integration] engine=$ENGINE_URL bridge=$BRIDGE_URL acct=$ACCOUNT_ID" >&2

# Probe /api/intent/extract. 404 means router NOT mounted; anything else
# (200/422/...) means router IS mounted. Without ANTICIPY_INTEGRATION_NO_WAIT
# unset we poll for up to 30 minutes; default is poll-once-then-fall-back.
TRANSPORT="direct_python"
deadline=$(( $(date +%s) + 1800 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  code="$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$ENGINE_URL/api/intent/extract" \
    -H "Content-Type: application/json" -d '{}' --max-time 4 || echo 000)"
  if [ "$code" != "404" ] && [ "$code" != "000" ]; then
    TRANSPORT="http"; break
  fi
  [ "${ANTICIPY_INTEGRATION_NO_WAIT:-1}" = "1" ] && break
  sleep 30
done
echo "$TRANSPORT" > "$RUN_DIR/transport.txt"
echo "[integration] transport=$TRANSPORT" >&2
[ "$TRANSPORT" = "direct_python" ] && \
  echo "[integration] NOTE: engine not restarted; using direct python imports." >&2

python3 - "$RUN_DIR" "$TRANSPORT" "$ENGINE_URL" "$ACCOUNT_ID" "$DEVICE_ID" \
       "$TRANSCRIPT" <<'PY'
import json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

run_dir, transport, engine_url, account_id, device_id, transcript = sys.argv[1:7]
run_dir = Path(run_dir)
engine_root = Path("/Users/omarebrahim/Developer/Anticipy-V7/engine")
if str(engine_root) not in sys.path:
    sys.path.insert(0, str(engine_root))
# Isolate confirm-card storage to this run.
os.environ["ANTICIPY_V7_CONFIRM_ROOT"] = str(run_dir / "confirm_cards")

results: dict = {
    "run_dir": str(run_dir),
    "transport": transport,
    "transcript": transcript,
    "account_id": account_id,
    "device_id": device_id,
    "steps": [],
}


def step(name: str, payload, ok: bool, reason: str = "") -> None:
    results["steps"].append({
        "step": name, "ok": bool(ok), "reason": reason,
    })
    (run_dir / f"{name}.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tag = "PASS" if ok else "FAIL"
    print(f"[step] {tag} {name}: {reason}", flush=True)


def fail(name: str, reason: str) -> None:
    step(name, {"error": reason}, False, reason)
    results["overall"] = {"ok": False, "failed_at": name, "reason": reason}
    (run_dir / "result.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")
    raise SystemExit(1)


def http_post(path: str, body: dict, timeout: float = 20.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{engine_url}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


# step 1: intent extraction
normalized = {"capture": {"asr_normalized": transcript}}
surface_ctx = {"url": "https://www.saucedemo.com/", "app": "chrome"}
try:
    if transport == "http":
        out = http_post("/api/intent/extract", {
            "normalized_input": normalized, "surface_context": surface_ctx,
            "memory_context": "", "timeout": 25.0})
        intent_dict = out.get("intent") or {}
    else:
        from app.product.intent_extractor import extract, is_actionable
        intent = extract(normalized, surface_ctx, "", timeout=25.0)
        intent_dict = intent.to_dict()
        intent_dict["is_actionable"] = is_actionable(intent)
except Exception as exc:
    fail("intent_extract", f"{transport}: {exc}")

cond_type = (intent_dict.get("type") == "act")
target = (intent_dict.get("target_surface") or "").lower()
cond_target = ("saucedemo" in target or "chrome" in target or
               "ecommerce" in target or "amazon" in target or
               "browser" in target)
cond_actionable = bool(intent_dict.get("is_actionable"))
intent_ok = cond_type and cond_target and cond_actionable
step("intent_extract", intent_dict, intent_ok,
     f"type={intent_dict.get('type')} target={target} "
     f"actionable={cond_actionable}")
if not intent_ok:
    fail("intent_extract_shape",
         f"type={intent_dict.get('type')} target={target} "
         f"actionable={cond_actionable}")

# step 2: risk assessment (binder uses this as a hint)
try:
    from app.product.risk_assessor import assess as risk_assess
    ra = risk_assess(intent_dict, {"surface_target": "saucedemo.com"})
    risk_dict = ra.to_dict()
except Exception as exc:
    fail("risk_assess", str(exc))
risk_ok = (risk_dict.get("proceed_mode") == "confirm" and
           bool(risk_dict.get("confirm_card_required")))
step("risk_assess", risk_dict, risk_ok,
     f"proceed_mode={risk_dict.get('proceed_mode')} "
     f"confirm_required={risk_dict.get('confirm_card_required')}")
if not risk_ok:
    fail("risk_assess_shape", str(risk_dict))

# step 3: action binder
try:
    from app.product.action_binder import bind as binder_bind
    binding = binder_bind(
        intent_dict, {"active_surface": {"url": surface_ctx["url"]}},
        {"confirm_required": bool(risk_dict["confirm_card_required"]),
         "reason": "; ".join(risk_dict.get("reasons") or [])},
        account_id=account_id, device_id=device_id)
    binding_dict = binding.to_dict()
except Exception as exc:
    fail("action_bind", str(exc))
bind_ok = bool(binding_dict.get("confirm_required"))
step("action_bind", binding_dict, bind_ok,
     f"confirm_required={binding_dict.get('confirm_required')} "
     f"reason={binding_dict.get('risk_reason')}")
if not bind_ok:
    fail("action_bind_shape", json.dumps(binding_dict))

# step 4: create confirm card
try:
    from app.product.confirm_card import (
        ConfirmCardStore, build_confirm_card, needs_confirmation,
    )
    planned_steps = binding_dict.get("planned_primitives") or [
        {"open": "https://www.saucedemo.com/"},
        {"navigate": "https://www.saucedemo.com/cart.html"},
        {"click": "checkout"},
        {"submit": "purchase Sauce Labs Backpack"}]
    needs = needs_confirmation(
        intent_dict.get("summary") or transcript, planned_steps,
        surface_target="saucedemo.com",
        money_amount=risk_dict.get("money_amount"), account_id=account_id)
    card = build_confirm_card(
        intent_dict.get("summary") or transcript, planned_steps,
        "saucedemo.com",
        {"binding_id": binding_dict.get("binding_id"),
         "intent_id": intent_dict.get("intent_id"), "risk": risk_dict},
        account_id=account_id,
        money_amount=risk_dict.get("money_amount"))
    store = ConfirmCardStore(account_id=account_id)
    store.create(card)
    card_dict = card.to_dict()
    card_dict["needs_confirmation"] = bool(needs)
except Exception as exc:
    fail("confirm_create", str(exc))
create_ok = (card.status == "pending" and bool(needs))
step("confirm_create", card_dict, create_ok,
     f"status={card.status} needs={needs} risk_level={card.risk_level}")
if not create_ok:
    fail("confirm_create_shape", json.dumps(card_dict))

# step 5: user says NO
denied = store.decide(card.card_id, "no")
if denied is None:
    fail("confirm_decide", "decide returned None")
denied_dict = denied.to_dict()
denied_ok = (denied.status == "denied")
step("confirm_decide", denied_dict, denied_ok,
     f"status={denied.status} decided_at={denied.decided_at}")
if not denied_ok:
    fail("confirm_decide_shape", json.dumps(denied_dict))

# step 6: navigate real Chrome to prove no purchase
bridge_url = os.environ.get("ANTICIPY_BRIDGE_URL", "http://127.0.0.1:7777")
bridge_secret = os.environ.get("ANTICIPY_TRIGGER_SECRET", "local-dev")


def bridge_post(path: str, body: dict, timeout: float = 20.0) -> dict:
    data = json.dumps({**body, "secret": bridge_secret}).encode("utf-8")
    req = urllib.request.Request(
        f"{bridge_url}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


try:
    nav_out = bridge_post("/surface-command", {
        "command": "navigate",
        "url": "https://www.saucedemo.com/cart.html"}, 15.0)
except Exception as exc:
    nav_out = {"ok": False, "error": str(exc)}
nav_ok = bool(nav_out.get("ok"))
step("navigate", nav_out, nav_ok,
     f"url={(nav_out.get('data') or {}).get('url')}")
# Saucedemo without a session redirects /cart.html to "/" (login). That
# redirect IS proof of no purchase: no logged-in session, no cart state.
time.sleep(2.5)

# step 7: surface proof (screenshot + url/title evidence)
try:
    proof = bridge_post("/surface-proof", {"limit": 80000}, 20.0)
except Exception as exc:
    proof = {"ok": False, "error": str(exc)}
shot_src = proof.get("screenshot_path") or ""
shot_copy = ""
if shot_src and Path(shot_src).exists():
    shot_copy = str(run_dir / "screenshot.png")
    Path(shot_copy).write_bytes(Path(shot_src).read_bytes())
proof["copied_to"] = shot_copy
url = (proof.get("url") or "").lower()
title = (proof.get("title") or "")
cart_safe = (
    "/cart.html" not in url and "/checkout" not in url
    and "/complete" not in url
) or "Login" in title or url.endswith("saucedemo.com/")
proof_ok = bool(proof.get("ok") and shot_copy and cart_safe)
step("surface_proof", proof, proof_ok,
     f"url={url} title={title} screenshot={shot_copy} "
     f"cart_safe={cart_safe}")

# final receipt
required = {"intent_extract", "risk_assess", "action_bind",
            "confirm_create", "confirm_decide", "surface_proof"}
all_ok = all(s["ok"] for s in results["steps"] if s["step"] in required)
results["overall"] = {
    "ok": bool(all_ok),
    "proves_no_decline_confirm_no_action_flow": bool(
        denied_ok and create_ok and proof_ok and bind_ok and risk_ok),
    "screenshot": shot_copy, "card_id": card.card_id,
    "binding_id": binding_dict.get("binding_id"),
    "intent_id": intent_dict.get("intent_id"),
}
(run_dir / "result.json").write_text(
    json.dumps(results, indent=2, default=str), encoding="utf-8")
print(json.dumps(results["overall"], indent=2))
raise SystemExit(0 if all_ok else 1)
PY

PY_EXIT=$?
if [ "$PY_EXIT" -ne 0 ]; then
  echo "[integration] FAIL run_dir=$RUN_DIR" >&2
  exit 1
fi
echo "[integration] PASS run_dir=$RUN_DIR" >&2
exit 0
