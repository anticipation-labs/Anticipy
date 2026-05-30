# scripts/install/

Installation utilities for the Anticipy Bridge v6 Chrome extension on end-user machines.

## What's here

| File | Purpose |
|---|---|
| `external-extensions-setup.sh` | Drops a Chrome External Extensions policy JSON into the user's Chrome user-data-dir so Chrome auto-installs Anticipy Bridge v6 without requiring Developer Mode. |
| `external-extensions-template.json` | The JSON template the setup script copies in place. Currently references a placeholder hosted-CRX URL; replace before going wide. |

## Why this script exists

Chrome 137+ silently disables unpacked extensions loaded via `--load-extension` unless the user has manually toggled Developer Mode on `chrome://extensions/`. That toggle cannot be set programmatically, and the warning surface is bad UX for a shipping product.

Chrome's officially supported alternative is the External Extensions policy. When Chrome starts, it scans `~/Library/Application Support/Google/Chrome/External Extensions/` for JSON files named `<extension_id>.json`. Each file declares either:

- A local `.crx` path (`external_crx` + `external_version`), or
- A hosted update URL (`external_update_url`) pointing to a Chrome-protocol update XML

Chrome then auto-installs the referenced extension on next launch. No Developer Mode toggle. No install warning. This is the same pattern Bitwarden and 1Password use to sideload their browser extensions from their native installers.

See `planning/00-handoff/RESEARCH/chrome-apis.md` section 5 for full background on why `--load-extension` is not viable for shipping.

## How to use it

End-user flow (will be invoked by the Anticipy installer):

```bash
bash scripts/install/external-extensions-setup.sh
```

Then the user fully quits Chrome (Cmd+Q, NOT just closing the window) and relaunches. The script prints these instructions at the end.

Developer flow (dry run, prints intended action without writing):

```bash
bash scripts/install/external-extensions-setup.sh --dry-run
```

## When to use Web Store instead

Once Anticipy is approved on the Chrome Web Store, this script becomes optional. CWS-published extensions auto-install via Chrome Sync into every profile the user is signed into, with no installer step required at all. The recommended migration is:

1. Publish Anticipy Bridge v6 to the Chrome Web Store under the same pinned ID (`npnpagopediecennpleihemoochikggb`).
2. Update `external-extensions-template.json` `external_update_url` to point to `https://clients2.google.com/service/update2/crx` (the official CWS update endpoint), so existing installs migrate to the CWS-managed copy.
3. New users skip the installer step entirely — install via CWS one-click.

Until then, this script is the supported path.

## Limitations

- **macOS only.** The script hardcodes the macOS Chrome user-data-dir path (`~/Library/Application Support/Google/Chrome/`). Linux and Windows need their own variants (different policy paths).
- **Chrome stable only.** Chrome Beta, Canary, Dev, and Chromium use different policy directories (`Google Chrome Beta`, `Google Chrome Canary`, etc.). Brave and Edge use entirely different paths. The script only writes to Chrome stable.
- **No multi-profile fanout.** External Extensions policy is per-Chrome-installation, not per-profile, so a single JSON file installs the extension into every profile. Profiles created later inherit it automatically.
- **Owner must restart Chrome.** Chrome only reads External Extensions JSON on startup. The script will NOT restart Chrome for the user; the user (or the wrapping installer UI) must do so.
- **Placeholder hosting URL.** The template currently references `REPLACE_WITH_HOSTED_CRX_DOMAIN`. Until a real .crx is hosted at an HTTPS URL, the policy file sits dormant. Once Web Store approval lands, replace the template with the CWS update URL.

## Pinned extension ID

`npnpagopediecennpleihemoochikggb`

This ID is derived deterministically from the `key` field in `manifest.json` of the Anticipy Bridge v6 extension. Pinning the ID lets us issue updates without breaking existing installs. The script verifies the pinned ID matches the current source manifest on each run and warns if they have diverged (e.g., if someone rebuilt the extension with a new key).

## File paths the script touches

| Action | Path |
|---|---|
| Reads (verify) | `~/.anticipy/extension/anticipy-v6/EXTENSION-LOAD-THIS-IN-CHROME/manifest.json` |
| Reads (template) | `scripts/install/external-extensions-template.json` |
| Writes | `~/Library/Application Support/Google/Chrome/External Extensions/npnpagopediecennpleihemoochikggb.json` |

That last path is created via `mkdir -p` if missing.
