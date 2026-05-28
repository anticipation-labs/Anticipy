#!/usr/bin/env bash

load_anticipy_env() {
  local env_file="${ANTICIPY_ENV_FILE:-.env.local}"

  if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
  fi

  if [ -z "${SUPABASE_URL:-}" ] && [ -n "${NEXT_PUBLIC_SUPABASE_URL:-}" ]; then
    export SUPABASE_URL="$NEXT_PUBLIC_SUPABASE_URL"
  fi

  if [ -z "${SUPABASE_SERVICE_KEY:-}" ] && [ -n "${SUPABASE_SERVICE_ROLE_KEY:-}" ]; then
    export SUPABASE_SERVICE_KEY="$SUPABASE_SERVICE_ROLE_KEY"
  fi

  if [ -z "${SUPABASE_ANON_KEY:-}" ] && [ -n "${NEXT_PUBLIC_SUPABASE_ANON_KEY:-}" ]; then
    export SUPABASE_ANON_KEY="$NEXT_PUBLIC_SUPABASE_ANON_KEY"
  fi
}
