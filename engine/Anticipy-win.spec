# -*- mode: python ; coding: utf-8 -*-
# Windows PyInstaller spec, built in parallel with the Mac .app on a
# GitHub-hosted windows-latest runner. Honest platform note: mlx /
# parakeet_mlx (the macOS local ASR) are Apple-Silicon only and are
# excluded here; the Windows local-ASR backend is a flagged, tagged
# platform follow-up and does not block packaging. The UI, onboarding
# (OpenRouter cloud), memory, the CDP browser action engine, and
# reasoning are all cross-platform and included.

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("webview", "uvicorn", "fastapi", "starlette", "pydantic",
            "anyio", "numpy", "sounddevice", "soundfile", "httpx",
            "websockets", "requests", "app"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["app/product/main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["mlx", "parakeet_mlx", "torch", "torchaudio"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Anticipy",
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Anticipy")
