#!/usr/bin/env bash
# Integration test: vision-only surface labeling for a canvas app (tldraw).
# tldraw renders its drawing surface as a single HTML5 canvas; the DOM is
# opaque, so this exercises the VisionSurface adapter end-to-end:
# bridge-navigate, screencapture, label clickables via Kimi K2.6 vision,
# then resolve a description ("rectangle tool") to a label.
# Proofs land in state/v7/integration_runs/canvas_vision_<timestamp>/.
# Exit codes: 0 PASS, 0 SKIP (bridge/perms missing), 1 FAIL.

set -uo pipefail

REPO_ROOT="/Users/omarebrahim/Developer/Anticipy-V7"
BRIDGE_URL="http://127.0.0.1:7777"
BRIDGE_SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"
TARGET_URL="https://www.tldraw.com"
TARGET_NAME="tldraw"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${REPO_ROOT}/state/v7/integration_runs/canvas_vision_${TS}"
mkdir -p "${RUN_DIR}"
RAW_PNG="${RUN_DIR}/raw_screenshot.png"
VISION_JSON="${RUN_DIR}/vision_response.json"
LOOKUP_JSON="${RUN_DIR}/rectangle_lookup.json"
SUMMARY="${RUN_DIR}/summary.json"
LOG="${RUN_DIR}/run.log"

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*" | tee -a "${LOG}"; }

# 1. Source .env.local (V7 first, fall back to DEV-FINAL).
for ENV_FILE in "${REPO_ROOT}/.env.local" "/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local"; do
  [ -f "${ENV_FILE}" ] && { set -a; . "${ENV_FILE}"; set +a; log "sourced ${ENV_FILE}"; break; }
done

if [ -z "${OPENROUTER_API_KEY:-}" ]; then
  log "SKIP: OPENROUTER_API_KEY not set after sourcing env"
  printf '{"status":"skip","reason":"OPENROUTER_API_KEY missing"}\n' > "${SUMMARY}"
  exit 0
fi

# 2. Probe bridge.
log "probing bridge at ${BRIDGE_URL}/status"
STATUS_BODY="$(curl -sS --max-time 5 "${BRIDGE_URL}/status" || true)"
if ! printf '%s' "${STATUS_BODY}" | python3 -c "import json,sys; d=json.loads(sys.stdin.read() or '{}'); sys.exit(0 if d.get('ok') else 1)"; then
  log "SKIP: bridge not alive (body=${STATUS_BODY:0:200})"
  printf '{"status":"skip","reason":"bridge not alive"}\n' > "${SUMMARY}"
  exit 0
fi
log "bridge alive"

# 3. Navigate Chrome's active tab to tldraw via the bridge, then activate
#    Chrome + focus the tldraw tab so screencapture catches the live canvas.
log "navigating Chrome to ${TARGET_URL}"
curl -sS --max-time 20 -X POST -H 'Content-Type: application/json' \
  -d "{\"secret\":\"${BRIDGE_SECRET}\",\"command\":\"navigate\",\"url\":\"${TARGET_URL}\"}" \
  "${BRIDGE_URL}/surface-command" > "${RUN_DIR}/navigate_response.json" 2>>"${LOG}" || true
osascript <<APPLE >>"${LOG}" 2>&1 || true
tell application "Google Chrome"
  activate
  repeat with w in windows
    set ti to 0
    repeat with t in tabs of w
      set ti to ti + 1
      if URL of t contains "tldraw" then
        set index of w to 1
        set active tab index of w to ti
        exit repeat
      end if
    end repeat
  end repeat
end tell
APPLE

# 4. Wait for canvas render.
log "sleeping 5s for canvas to render"
sleep 5

# 5. Capture the main display. (Crop happens below in Python.)
log "screencapture -> ${RAW_PNG}"
if ! screencapture -x -D 1 "${RAW_PNG}" 2>>"${LOG}"; then
  log "SKIP: screencapture failed (Screen Recording permission?)"
  printf '{"status":"skip","reason":"screencapture failed"}\n' > "${SUMMARY}"; exit 0
fi
if [ ! -s "${RAW_PNG}" ]; then
  log "FAIL: screenshot is empty"
  printf '{"status":"fail","reason":"empty screenshot"}\n' > "${SUMMARY}"
  exit 1
fi
SHOT_BYTES="$(stat -f%z "${RAW_PNG}")"
log "screenshot captured (${SHOT_BYTES} bytes)"

# 6. Drive the VisionSurface adapter (label + description lookup).
log "invoking VisionSurface (Kimi K2.6 primary, Gemini 2.5 fallback)"
export ANTICIPY_VISION_SCREENSHOTS="${RUN_DIR}/labeled"
mkdir -p "${ANTICIPY_VISION_SCREENSHOTS}"
export V7_CANVAS_SHOT="${RAW_PNG}"
export V7_CANVAS_VJSON="${VISION_JSON}"
export V7_CANVAS_LJSON="${LOOKUP_JSON}"
export V7_CANVAS_TARGET="${TARGET_NAME}"

PYTHONPATH="${REPO_ROOT}/engine" python3 - <<'PY' >>"${LOG}" 2>&1
import io, json, os, time
from PIL import Image
from app.product.surface_runtime_vision import VisionSurface

shot_path = os.environ["V7_CANVAS_SHOT"]
vision_out = os.environ["V7_CANVAS_VJSON"]
lookup_out = os.environ["V7_CANVAS_LJSON"]
target = os.environ.get("V7_CANVAS_TARGET", "canvas-app")

raw = open(shot_path, "rb").read()
# Crop out macOS menu bar (top), Chrome chrome (tabs+bookmarks bar) and any
# desktop wallpaper on the right. This keeps the vision model focused on the
# tldraw canvas + toolbar so it does not waste 30 labels on Chrome menus.
with Image.open(io.BytesIO(raw)) as im:
    w, h = im.size
    top = int(h * 0.18); right = max(0, w - int(w * 0.15))
    cropped = im.crop((0, top, right, h))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG", optimize=True)
    png = buf.getvalue()
crop_path = shot_path.replace(".png", "_cropped.png")
open(crop_path, "wb").write(png)
print(f"cropped {w}x{h} -> {cropped.size} -> {crop_path}")
vs = VisionSurface()

t0 = time.time()
labeled = vs.label_clickables(png)
labeled_wall = time.time() - t0

with open(vision_out, "w") as fh:
    json.dump(labeled, fh, indent=2, default=str)

elements = labeled.get("elements", [])
print(f"vision target={target} elements={len(elements)} wall={labeled_wall:.1f}s")
print(f"labeled overlay: {labeled.get('labeled_screenshot_path')}")
for el in elements[:8]:
    print(f"  #{el['label_id']} role={el['role']} hint={el['hint_text']!r}")
queries = [
    "a tool button for drawing a rectangle",
    "rectangle or square shape tool in the tldraw toolbar",
    "the shape, geometry, or rectangle drawing tool icon",
]
hit = None
t1 = time.time()
for q in queries:
    hit = vs.find_element_by_description(png, q)
    if hit and hit.get("confidence", 0.0) > 0.5:
        hit["query_used"] = q
        break
lookup_wall = time.time() - t1

with open(lookup_out, "w") as fh:
    json.dump(hit or {"hit": None, "queries_tried": queries},
              fh, indent=2, default=str)

print(f"rectangle-lookup wall={lookup_wall:.1f}s queries_tried={len(queries)}")
if hit:
    print(f"  hit label={hit['label_id']} role={hit['role']} "
          f"hint={hit['hint_text']!r} confidence={hit['confidence']:.2f} "
          f"query={hit.get('query_used','')!r}")
else:
    print("  no hit across any query")
PY
PY_RC=$?
if [ ${PY_RC} -ne 0 ]; then
  log "FAIL: VisionSurface invocation exited ${PY_RC}"
  printf '{"status":"fail","reason":"VisionSurface error"}\n' > "${SUMMARY}"
  exit 1
fi

# 7. Assertions.
ELEMENT_COUNT=$(python3 -c "import json; print(len(json.load(open('${VISION_JSON}')).get('elements', [])))")
log "labeled element count: ${ELEMENT_COUNT}"
if [ "${ELEMENT_COUNT}" -lt 5 ]; then
  log "FAIL: vision labeled fewer than 5 elements"
  printf '{"status":"fail","reason":"too few labeled elements","count":%s}\n' "${ELEMENT_COUNT}" > "${SUMMARY}"
  exit 1
fi

CONFIDENCE=$(python3 -c "import json; d=json.load(open('${LOOKUP_JSON}')); print(d.get('confidence', 0.0))")
log "rectangle-tool confidence: ${CONFIDENCE}"
ABOVE_THRESHOLD=$(python3 -c "print(1 if float('${CONFIDENCE}') > 0.5 else 0)")
if [ "${ABOVE_THRESHOLD}" -ne 1 ]; then
  log "FAIL: rectangle-tool confidence <= 0.5 (got ${CONFIDENCE})"
  printf '{"status":"fail","reason":"low confidence","confidence":%s}\n' "${CONFIDENCE}" > "${SUMMARY}"
  exit 1
fi

OVERLAY=$(python3 -c "import json; print(json.load(open('${VISION_JSON}')).get('labeled_screenshot_path', ''))")
if [ -n "${OVERLAY}" ] && [ -f "${OVERLAY}" ]; then
  cp "${OVERLAY}" "${RUN_DIR}/labeled_overlay.png"
  log "labeled overlay copied -> ${RUN_DIR}/labeled_overlay.png"
fi

python3 -c "import json; open('${SUMMARY}','w').write(json.dumps({'status':'pass','target_url':'${TARGET_URL}','target_name':'${TARGET_NAME}','screenshot_path':'${RAW_PNG}','labeled_overlay_path':'${RUN_DIR}/labeled_overlay.png','vision_response_path':'${VISION_JSON}','rectangle_lookup_path':'${LOOKUP_JSON}','labeled_element_count':${ELEMENT_COUNT},'rectangle_confidence':${CONFIDENCE},'timestamp_utc':'${TS}'}, indent=2))"

log "PASS canvas-vision integration (${ELEMENT_COUNT} elements, rect conf=${CONFIDENCE})"
log "run dir: ${RUN_DIR}"
exit 0
