# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Anticipy desktop app (STEP 2 plan).
# Entry: app/desktop_app.py (Tkinter, no server, no Terminal).
# Big models = cloud via OpenRouter exactly as the engine does;
# small audio models fetched first-run into the user-writable data
# dir (NOT baked read-only). No hardcoded /Users/ paths.

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("mlx", "parakeet_mlx", "torch", "torchaudio",
            "silero_vad", "soundfile", "sounddevice", "numpy",
            "scipy", "sklearn", "webview", "uvicorn", "fastapi",
            "starlette", "pydantic", "anyio", "objc",
            "WebKit", "Foundation", "AppKit", "app"):
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
    excludes=[],
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
    target_arch="arm64",
)
coll = COLLECT(exe, a.binaries, a.datas, name="Anticipy")
app = BUNDLE(
    coll,
    name="Anticipy.app",
    icon=None,
    bundle_identifier="ai.anticipy.app",
    info_plist={
        "NSMicrophoneUsageDescription":
            "Anticipy listens to run its pipeline locally.",
        "LSMinimumSystemVersion": "13.0",
        "CFBundleShortVersionString": "1.0.0",
    },
)
