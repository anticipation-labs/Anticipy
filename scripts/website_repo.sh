#!/usr/bin/env bash
# Where the website lives, now that it is not here.
#
# The site was split out to anticipation-labs/Aniticpy_Website on 2026-09-04.
# src/, public/ and state/builds/manifest.json went with it. Several scripts in
# THIS repo still produce things the site serves -- the Mac DMG and its manifest,
# the packaged Chrome extension -- so they need to know where to put them.
#
# Usage:
#   . scripts/website_repo.sh
#   website_repo            # prints the path, or exits 1 with instructions
#   website_repo --optional # prints the path, or prints nothing and returns 1
#
# Override with WEBSITE_REPO=/path/to/Aniticpy_Website.

website_repo() {
  local optional=0
  [ "${1:-}" = "--optional" ] && optional=1

  local root
  root="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
  local candidate="${WEBSITE_REPO:-$root/../Aniticpy_Website}"

  if [ -d "$candidate/.git" ]; then
    (cd "$candidate" && pwd -P)
    return 0
  fi

  if [ "$optional" = "1" ]; then
    return 1
  fi

  echo "[website_repo] not a git checkout: $candidate" >&2
  echo "[website_repo] The website moved to anticipation-labs/Aniticpy_Website on" >&2
  echo "[website_repo] 2026-09-04; src/, public/ and state/builds/ went with it." >&2
  echo "[website_repo]   git clone https://github.com/anticipation-labs/Aniticpy_Website.git" >&2
  echo "[website_repo]   WEBSITE_REPO=/path/to/Aniticpy_Website $0" >&2
  return 1
}
