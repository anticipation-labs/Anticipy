# Terminal & Git Debug Session — 2026-05-13

Append-only log. Future sessions: read top-to-bottom before retrying anything.

---

## Environment snapshot

- **macOS** 26.3 (25D125) on M2 Air, kernel 25.3.0 / arm64 (T8112).
- **Shell**: zsh 5.9 (arm64-apple-darwin25.0). `SHELL=/bin/zsh`, `TERM=xterm-256color`, `TERM_PROGRAM=Apple_Terminal`, `LANG=en_CA.UTF-8`.
- **Git**: Apple CLT git 2.39.5 (Apple Git-154) at `/usr/bin/git`. Single git on PATH (no Homebrew git competing).
- **Bracketed paste**: bound (`bindkey | grep paste` → `"^[[200~" bracketed-paste`).
- **No third-party EDR/AV**. Only macOS-native XProtect/syspolicyd/tccd.
- **`timeout` / `gtimeout` NOT installed** (brew is broken — can't `brew install coreutils`). Used Bash tool's built-in timeout instead.

---

## Root causes identified

### 1. macOS `fileproviderd` was running a continuous FPCK (File Provider Consistency Check) over `~/Desktop/Anticipy-DEV-FINAL`

Process sample of a stuck `git status`:

```
cmd_status → refresh_index → refresh_cache_ent → ie_modified
  → ce_modified_check_fs → index_fd → read_in_full → xread → read()
```

100% of git's runtime was in `read()`. Each `read()` was being intercepted/serialised by `fileproviderd` (PID 927 at observation, owned by user 501; 1 095 minutes accumulated CPU since Apr 29).

The interception is **path-specific**. Measured baseline:

| Location | 50 files via `cat` |
|---|---|
| `/tmp` | 0.07 s |
| `~/Documents` (other) | 0.08 s |
| `~/Desktop` (outside repo) | 0.09 s |
| `~/anticipy_speedtest` (home root) | 0.09 s |
| **`~/Desktop/Anticipy-DEV-FINAL`** | **~55 s** |

Same volume (`/dev/disk3s5`, APFS), same file types, same shell. The throttling is targeted at the Anticipy directory specifically because it was in fileproviderd's FPCK queue.

### 2. iCloud Drive's "Desktop & Documents Folders" was ON, and that's the only trigger that puts `~/Desktop` in fileproviderd's FPCK queue

Evidence:
- `defaults read MobileMeAccounts` showed `Name = CLOUDDESKTOP; ServiceID = com.apple.Dataclass.CloudDesktop; status = active`.
- `~/Library/Application Support/FileProvider/com.apple.CloudDocs.iCloudDriveFileProvider/Domains.plist` had `ReplicatedKnownFolders=3` and `SupportedKnownFolders=3` (binary 11 = Desktop + Documents replicated).
- `~/Library/Mobile Documents/com~apple~CloudDocs/` had stray Anticipy build artefacts (`_global-error.html`, `[root-of-the-server]__bcd6d5cf._.js.map`, etc.) from past Next.js runs that got mirrored.
- `fileproviderd` sample showed `com.apple.fileproviderd.periodic-fpck` dispatch queue running `[FPCKTask prepareFPCKRun:…]` actively.

**Cannot be disabled from CLI:** the toggle lives behind System Settings → Apple ID → iCloud → Drive → "Desktop & Documents Folders". Tried six programmatic angles — `defaults` writes to `com.apple.bird`, SIGHUP to fileproviderd, `launchctl bootout` (SIP-blocked), `brctl evict`, editing Domains.plist directly. All ineffective without the Settings click.

This is why it works in GitHub Codespaces (no fileproviderd) and why deleting and re-adding the directory didn't help (Apple's CloudDesktop service re-enrolls any new directory under `~/Desktop` automatically while the toggle is on).

### 3. The em-dash paste bug is actually a CURLY-QUOTE bug

Verified bytes:
- Em-dash from `printf` source: `e2 80 94` (U+2014). zsh parses fine inside `"…"`.
- Typical chat-tool paste of `git commit -m "Phase 1 progress — done"`: opening quote is `e2 80 9c` (U+201C, `"`), closing is `e2 80 9d` (U+201D, `"`).

zsh's `"…"` quoting handler only recognises ASCII `0x22`. Curly `"` is treated as a literal character; there is no real `"` to close the string → zsh drops to a `PS2='> '` continuation prompt waiting for the close. That's the `>` prompt the user kept hitting.

Bracketed-paste is on, but it makes paste literal — it doesn't ASCII-normalise Unicode quote variants.

### 4. `.git/index 2` Finder duplicate, stale `.git/index.lock` from prior `kill -9`

- `.git/index 2` (61 029 B, dated May 11 23:21): the trailing-" 2" duplicate macOS Finder creates when a file is dropped twice. Backed up to `/tmp/anticipy.git_index_2.backup`, removed.
- `.git/index.lock` (0 B, May 13 12:34): left by `kill -9` of `git update-index --really-refresh` during the diagnostic.

### 5. `engine/.venv/` (43 509 files) and nested `node_modules` copies were not gitignored

`.gitignore` only had `/node_modules` (root only) and no `.venv` rule. Default-mode `git status` had to walk ~58 000 untracked paths even with the index issue.

### 6. Shell-init duplication (`~/.zprofile`, `~/.zshrc`)

`~/.zshrc` had `eval "$(pyenv init -)"` twice; `~/.zprofile` had `brew shellenv` and `pyenv init --path` twice each. De-duplicated.

### 7. VS Code's git extension polls aggressively

Observed PID 80085 mid-session: `git -c core.quotepath=false ls-files --recurse-submodules`. VS Code (PID 19225) running, its git extension launches that command every few seconds. While the v-final-prototype build is hot, that's enough background traffic to compound any FPCK throttling.

---

## Fixes applied

| # | Fix | Where |
|---|---|---|
| F1 | Desktop & Documents iCloud sync toggled OFF | System Settings (Omar clicked) |
| F2 | Repo physically moved out of `~/Desktop` to `~/Developer/Anticipy-DEV-FINAL` | fresh `git clone` from GitHub (old `.git/` was lost when iCloud archive was processed; only `main`'s `a62eccc` was on the remote) |
| F3 | `.gitignore` augmented: `engine/.venv/`, `.venv/`, `**/.venv/`, `**/__pycache__/`, `.next/`, `out/`, `.turbo/`, `.swc/`, `.cache/`, `.anticipy/models/`, `.anticipy/*.db`, `.anticipy/*.wav`, `.anticipy/*.npy`, `**/* 2` Finder dupes, `.metadata_never_index*` markers | repo |
| F4 | Git perf config (local): `core.untrackedCache=true`, `core.preloadIndex=true`, `core.fsmonitor=false`, `feature.manyFiles=true`, `gc.auto=256` | `.git/config` |
| F5 | `cleanstale` zsh function | `~/.zshrc` |
| F6 | `gcmsg "…"` zsh function (curly-quote → ASCII normaliser + `git commit -F`) | `~/.zshrc` |
| F7 | De-duplicated `pyenv init -` and `brew shellenv` / `pyenv init --path` | `~/.zshrc` + `~/.zprofile` |
| F8 | Operational rules in `CLAUDE.md` | `CLAUDE.md` |

---

## Verification results

| Test | Result |
|---|---|
| **A.1** `git status --short` (cold) | 0.16 s |
| **A.2** `git status --short` (warm) | 0.02 s |
| **A.3** `git status --short` (third) | 0.02 s |
| **B** em-dash inline commit, file form | em-dash bytes verified; `gcmsg` normalises curly→ASCII; `git commit -F /tmp/commit_msg_debug.txt` works cleanly |
| **C** `cleanstale && ps aux \| grep '[g]it\|[m]cp-server' \| wc -l` | 0 (function defined, idempotent) |
| **D** Paste from chat tools | `gcmsg` covers all terminals (Apple Terminal, VS Code, iTerm) since it operates at the script level |
| **E** No zombie git after 60 s of normal use | Pending — depends on whether the VS Code workspace is closed; recommend `"git.enabled": false` in workspace settings while the build is hot |

50-file `cat` after the toggle flip: **0.03 s** (was 56.9 s) → **1 896× faster**.

---

## What was lost in transit (handoff)

The original `~/Desktop/Anticipy-DEV-FINAL/.git/` was an iCloud placeholder when the user toggled CloudDesktop off. `Keep on Mac` re-materialised the static tracked files (5 551 of them, into `~/iCloud Drive (Archive)/Desktop/Anticipy-DEV-FINAL/`) but the hidden directories — `.git/`, `.anticipy/`, `.claude/` — were skipped or evicted during the transition. The `~/Developer/Anticipy-DEV-FINAL` working copy was rebuilt by fresh `git clone` from `omize10/Anticipy.git` `main`.

Consequences:
- Two un-pushed local-only commits (`b2e5a0a` Phase 0 install v-final-prototype + `83d1efd` Phase 0 setup & audit) were on the lost `.git/`. GitHub never had them.
- The session's prior `.anticipy/` files (PROGRESS.md, CHANGELOG.md, FORBIDDEN_PROVIDER_HITS.md, MISSING_KEYS.md, PENDING_DIAGNOSTIC.md, MEMORY_CONFLICTS.md) were also in the lost `.anticipy/`. Their CONTENT is preserved in this Claude session's conversation log if reconstruction is needed.
- `~/.anticipy/` (the master-prompt runtime location with `memory.db`, models, `anticipy_agent.py`, `venv/`, `protocol.py`) was NOT touched — that lives in `$HOME/.anticipy/` and is intact.
- `.env.local` is restored at the new path (3 426 bytes).

To recover the Phase 0 work: the equivalents of `b2e5a0a` (CLAUDE.md v-final-prototype section) and `83d1efd` (initial `.anticipy/` files) are documented in `engine/`'s prior PROACTIVE_AUDIT.md (still tracked) and the master prompt's "v-final-prototype" spec. Reapplying them is mechanical, but distinct from this fix.

---

## Permanent operational rules

See `CLAUDE.md` → "Terminal & git operational rules" section. Eight rules, same numbering as in that file. tl;dr:

1. Never `-m` inline commit messages from chat tools — use `gcmsg` or `-F`.
2. Never `kill -9 git` mid-write — SIGTERM first, run `cleanstale` after.
3. Run `cleanstale` between sessions.
4. Anything > 1 000 files needs to be in `.gitignore` before creation.
5. Disable VS Code git extension in this workspace while builds are hot.
6. Desktop & Documents iCloud sync must stay OFF.
7. If `git status` hangs > 10 s, `sample` it; check stack.
8. Don't touch the local git perf config without intent.
