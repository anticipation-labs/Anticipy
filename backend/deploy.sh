#!/bin/sh

# Deploy the backend from an isolated directory. The repository-level
# .railwayignore intentionally excludes backend/, so deploying the repository
# root can otherwise upload an empty or stale backend image.
set -eu

project_id="${ANTICIPY_RAILWAY_PROJECT:-c0a0f512-6ce0-43aa-b338-781d912e5ae3}"
service="${ANTICIPY_RAILWAY_SERVICE:-backend}"
environment="${ANTICIPY_RAILWAY_ENVIRONMENT:-production}"
message="${1:-deploy backend from isolated release context}"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
stage_dir=$(mktemp -d /tmp/anticipy-backend-deploy.XXXXXX)

cleanup() {
  find "$stage_dir" -depth -delete
}
trap cleanup EXIT HUP INT TERM

cp -R "$script_dir"/. "$stage_dir"/

test -f "$stage_dir/Dockerfile"
test -f "$stage_dir/pb_public/mac/Anticipy-for-Mac.zip"

railway up "$stage_dir" \
  --path-as-root \
  --project "$project_id" \
  --service "$service" \
  --environment "$environment" \
  --message "$message" \
  --detach \
  --yes
