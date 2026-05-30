#!/usr/bin/env bash
# external-extensions-setup.sh
#
# Anticipy Bridge v6 — Chrome External Extensions policy installer.
#
# Why this script exists:
#   Chrome 137+ silently disables unpacked extensions loaded via --load-extension
#   unless the user manually toggles Developer Mode on chrome://extensions/.
#   We cannot set that toggle programmatically. But Chrome WILL auto-install any
#   extension referenced from ~/Library/Application Support/Google/Chrome/External
#   Extensions/<id>.json without Developer Mode and without the install warning,
#   as long as the file points to either (a) a Chrome Web Store ID, or (b) a
#   hosted .crx via external_update_url. This is the same pattern Bitwarden and
#   1Password use.
#
#   Until our .crx is hosted (or Anticipy ships through the Web Store), this
#   script lays down the External Extensions JSON in the correct location and
#   reports the path. The current template references a placeholder hosted-CRX
#   URL; replace with the real CDN before going wide.
#
# Usage:
#   bash external-extensions-setup.sh [--dry-run]
#
# Owner action after running:
#   1. Replace REPLACE_WITH_HOSTED_CRX_DOMAIN in the written JSON with the real
#      .crx hosting domain (anticipy.ai or chosen CDN).
#   2. Fully quit Chrome (Cmd+Q, not just close window) and relaunch.
#   3. Visit chrome://extensions/ to confirm Anticipy Bridge v6 is enabled.

set -euo pipefail

# ----- constants -----------------------------------------------------------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE_PATH="${REPO_ROOT}/scripts/install/external-extensions-template.json"
EXTENSION_SOURCE_DIR="${HOME}/.anticipy/extension/anticipy-v6/EXTENSION-LOAD-THIS-IN-CHROME"
EXTENSION_MANIFEST="${EXTENSION_SOURCE_DIR}/manifest.json"

# Pinned extension ID derived from the manifest.json `key` field.
# The deterministic derivation (base64-decode key, sha256, take first 16 bytes,
# map 0..15 -> a..p) yields this ID for the Anticipy Bridge v6 manifest. Pinned
# here to avoid requiring openssl + sha256 every run, and to make this script
# operable even if the source extension dir is missing.
PINNED_EXTENSION_ID="npnpagopediecennpleihemoochikggb"

CHROME_EXTERNAL_DIR="${HOME}/Library/Application Support/Google/Chrome/External Extensions"
TARGET_JSON_PATH="${CHROME_EXTERNAL_DIR}/${PINNED_EXTENSION_ID}.json"

DRY_RUN="false"
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN="true" ;;
    -h|--help)
      cat <<EOF
external-extensions-setup.sh — install Anticipy Bridge v6 via Chrome External
Extensions policy (no Developer Mode toggle required).

Usage:
  bash external-extensions-setup.sh             # write the JSON
  bash external-extensions-setup.sh --dry-run   # show intended action, write nothing

Files this script touches:
  WRITES:  ~/Library/Application Support/Google/Chrome/External Extensions/${PINNED_EXTENSION_ID}.json
  READS:   ${TEMPLATE_PATH}
  READS:   ${EXTENSION_MANIFEST} (verifies pinned ID matches)
EOF
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: ${arg}" >&2
      echo "Run with --help for usage." >&2
      exit 2
      ;;
  esac
done

# ----- helpers -------------------------------------------------------------

log()  { printf '[anticipy-install] %s\n' "$*"; }
warn() { printf '[anticipy-install] WARN: %s\n' "$*" >&2; }
err()  { printf '[anticipy-install] ERROR: %s\n' "$*" >&2; }

# ----- preflight -----------------------------------------------------------

log "Anticipy Bridge v6 — External Extensions setup"
log ""

# 1. Detect Chrome profile dir parent (the user-data-dir).
CHROME_USER_DATA="${HOME}/Library/Application Support/Google/Chrome"
if [[ -d "${CHROME_USER_DATA}" ]]; then
  log "Detected Chrome user-data-dir: ${CHROME_USER_DATA}"
else
  warn "Chrome user-data-dir not found at: ${CHROME_USER_DATA}"
  warn "Chrome may not be installed, or this user has never launched Chrome."
  warn "Continuing anyway — the External Extensions dir will be created."
fi

# 2. Verify the extension source dir exists, and that the pinned ID matches
#    its manifest.json `key` field. We do a best-effort check; if the openssl
#    derivation differs from the pinned ID, we warn (the source extension may
#    have been rebuilt with a new key), but we still proceed with the pinned ID
#    because that is the ID Chrome will recognize for existing installs.
if [[ -f "${EXTENSION_MANIFEST}" ]]; then
  log "Verifying manifest.json at: ${EXTENSION_MANIFEST}"
  # Best-effort ID derivation. The Chrome rule:
  #   - take the manifest.json `key` field (base64-encoded SPKI),
  #   - base64-decode it to raw bytes,
  #   - sha256 those bytes,
  #   - take first 16 bytes (32 hex chars),
  #   - map each hex digit 0..15 to character a..p.
  if command -v openssl >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
    KEY_B64="$(python3 -c "
import json, sys
with open('${EXTENSION_MANIFEST}') as f:
    data = json.load(f)
sys.stdout.write(data.get('key', '').strip())
")"
    if [[ -n "${KEY_B64}" ]]; then
      DERIVED_ID="$(printf '%s' "${KEY_B64}" \
        | openssl base64 -A -d 2>/dev/null \
        | openssl dgst -sha256 -binary \
        | xxd -p -c 256 \
        | cut -c1-32 \
        | tr '0123456789abcdef' 'abcdefghijklmnop')"
      if [[ "${DERIVED_ID}" == "${PINNED_EXTENSION_ID}" ]]; then
        log "Derived extension ID matches pinned ID: ${PINNED_EXTENSION_ID}"
      else
        warn "Derived ID (${DERIVED_ID}) does not match pinned ID (${PINNED_EXTENSION_ID})."
        warn "If the source extension was rebuilt with a new key, update PINNED_EXTENSION_ID in this script."
      fi
    else
      warn "manifest.json has no 'key' field — cannot verify ID derivation."
    fi
  else
    warn "openssl or python3 not available; skipping derivation check (using pinned ID directly)."
  fi
else
  warn "Extension source manifest not found at: ${EXTENSION_MANIFEST}"
  warn "Continuing with pinned ID; verify the extension is installed separately."
fi

# 3. Verify the template exists.
if [[ ! -f "${TEMPLATE_PATH}" ]]; then
  err "Template not found at: ${TEMPLATE_PATH}"
  err "Cannot continue without the External Extensions JSON template."
  exit 1
fi
log "Template present: ${TEMPLATE_PATH}"

# ----- plan ----------------------------------------------------------------

log ""
log "Plan:"
log "  Target file: ${TARGET_JSON_PATH}"
log "  Content (from template):"
log "  ----- BEGIN JSON -----"
sed 's/^/  /' "${TEMPLATE_PATH}"
log "  ----- END JSON -----"
log ""

# ----- execute -------------------------------------------------------------

if [[ "${DRY_RUN}" == "true" ]]; then
  log "DRY RUN — no files were written."
  log "Re-run without --dry-run to install."
  exit 0
fi

log "Creating External Extensions directory if missing..."
mkdir -p "${CHROME_EXTERNAL_DIR}"

log "Writing JSON to: ${TARGET_JSON_PATH}"
cp "${TEMPLATE_PATH}" "${TARGET_JSON_PATH}"

# Verify the write.
if [[ -f "${TARGET_JSON_PATH}" ]]; then
  WRITTEN_SIZE="$(wc -c < "${TARGET_JSON_PATH}" | tr -d ' ')"
  log "Wrote ${WRITTEN_SIZE} bytes to: ${TARGET_JSON_PATH}"
else
  err "Failed to write ${TARGET_JSON_PATH}"
  exit 1
fi

# ----- next steps ----------------------------------------------------------

cat <<EOF

[anticipy-install] SUCCESS.

NEXT STEPS (manual — this script will NOT do these for you):

  1. Replace placeholder in JSON:
       Open: ${TARGET_JSON_PATH}
       Edit: replace REPLACE_WITH_HOSTED_CRX_DOMAIN with the real .crx
       hosting domain (e.g. anticipy.ai or the chosen CDN).

  2. Restart Chrome to activate:
       Fully quit Chrome with Cmd+Q (NOT just closing the window).
       Wait 2 seconds, then relaunch Chrome.

  3. Verify install:
       Visit chrome://extensions/ — "Anticipy Bridge v6" should appear
       as enabled, with NO Developer Mode toggle required.

Until the .crx is hosted at a real URL, Chrome will log a fetch failure
for the update XML but will not display an error to the user. The policy
file just sits dormant until the hosted .crx is reachable.

EOF
