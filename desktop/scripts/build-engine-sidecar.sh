#!/usr/bin/env bash
# Build the PyInstaller-bundled Anticipy engine sidecar for Tauri.
#
# Output: desktop/src-tauri/bin/anticipy-engine-aarch64-apple-darwin
# (this is the path tauri-bundler picks up because tauri.conf.json
# lists "bin/anticipy-engine" under bundle.externalBin and tauri
# appends the target triple).
#
# Adhoc-signed only. Notarization is out of scope (per PRD non-goals).
# Story: US-013.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$HERE/.." && pwd)"
REPO_DIR="$(cd "$DESKTOP_DIR/.." && pwd)"
ENGINE_DIR="$REPO_DIR/engine"
VENV_BIN="$ENGINE_DIR/.venv/bin"
OUT_DIR="$DESKTOP_DIR/src-tauri/bin"
OUT_FILE="$OUT_DIR/anticipy-engine-aarch64-apple-darwin"

if [[ ! -x "$VENV_BIN/pyinstaller" ]]; then
  echo "FATAL: $VENV_BIN/pyinstaller not found. Run 'uv sync' inside engine/." >&2
  exit 2
fi

export PATH="$VENV_BIN:$PATH"

cd "$ENGINE_DIR"
rm -rf build dist anticipy-engine.spec

MLX_LIB_DIR="$("$VENV_BIN/python" - <<'PY'
from pathlib import Path
import importlib.util
spec = importlib.util.find_spec("mlx")
if not spec:
    raise SystemExit("mlx package not found")
if spec.origin:
    package_dir = Path(spec.origin).resolve().parent
else:
    locations = list(spec.submodule_search_locations or [])
    if not locations:
        raise SystemExit("mlx package directory not found")
    package_dir = Path(locations[0]).resolve()
print(package_dir / "lib")
PY
)"
MLX_JACCL="$MLX_LIB_DIR/libjaccl.dylib"
if [[ ! -f "$MLX_JACCL" ]]; then
  echo "FATAL: MLX dependency libjaccl.dylib not found at $MLX_JACCL" >&2
  exit 2
fi

EXCLUDES=(
  # Transitive deps that the engine never imports. Dropping them shrinks
  # the PyInstaller bundle and reduces peak RAM during the final CArchive
  # build step (which was OOM-killing the box).
  # NOTE: sklearn is NOT excluded because app/memory_v2/draw.py imports
  # _local_embed (TF-IDF) at memory-lookup time and the caller does not
  # catch ImportError. Exclude it only after that path is hardened.
  --exclude-module skimage
  --exclude-module matplotlib
  --exclude-module IPython
  --exclude-module jupyter
  --exclude-module notebook
  --exclude-module pytest
  --exclude-module tkinter
  --exclude-module PyQt5
  --exclude-module PyQt6
  --exclude-module PySide2
  --exclude-module PySide6
)

pyinstaller \
  --onefile \
  --noupx \
  --target-arch arm64 \
  --collect-all mlx \
  --collect-all parakeet_mlx \
  --add-binary "$MLX_JACCL:." \
  --name anticipy-engine \
  "${EXCLUDES[@]}" \
  app/product/server.py

if [[ ! -f "$ENGINE_DIR/dist/anticipy-engine" ]]; then
  echo "FATAL: PyInstaller did not produce dist/anticipy-engine" >&2
  exit 3
fi

mkdir -p "$OUT_DIR"
cp "$ENGINE_DIR/dist/anticipy-engine" "$OUT_FILE"
codesign --force --sign - "$OUT_FILE"
codesign --verify --verbose "$OUT_FILE"

size_bytes=$(stat -f %z "$OUT_FILE")
printf "engine sidecar built: %s (%.1f MiB)\n" \
  "$OUT_FILE" "$(echo "$size_bytes / 1048576" | bc -l)"
