"""One-time asset fetch (authorized P0 setup): the offline models and
the REAL recorded-noise/media bed. No credential. Device-local under
data_dir. Idempotent: re-running with assets present is a fast no-op.
"""
from __future__ import annotations

import io
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))


def log(m): print(m, flush=True)


def main() -> int:
    from app.anticipy import platform_adapter
    dd = platform_adapter.data_dir()
    (dd / "models").mkdir(parents=True, exist_ok=True)
    bg = dd / "backgrounds" / "ESC-50"
    t0 = time.time()

    # 1. ESC-50 real recorded environmental audio (public, no credential)
    if bg.exists() and len(list(bg.glob("audio/*.wav"))) > 1000:
        log(f"ESC-50: present ({len(list(bg.glob('audio/*.wav')))} wavs)")
    else:
        url = "https://github.com/karoldvl/ESC-50/archive/master.zip"
        log(f"ESC-50: downloading {url}")
        raw = urllib.request.urlopen(url, timeout=600).read()
        log(f"ESC-50: {len(raw)/1e6:.0f} MB, extracting")
        z = zipfile.ZipFile(io.BytesIO(raw))
        bg.parent.mkdir(parents=True, exist_ok=True)
        z.extractall(bg.parent)
        src = bg.parent / "ESC-50-master"
        if src.exists():
            src.rename(bg)
        log(f"ESC-50: extracted {len(list(bg.glob('audio/*.wav')))} wavs")

    # 2. wav2vec2-base speaker-embed weights (torchaudio, no credential)
    try:
        from app.audiostack import audio as A
        import numpy as np
        A._models_dir()
        _ = A.speaker_embed(np.zeros(int(0.5 * A.SR), dtype="float32"))
        v = A.speaker_embed(np.random.RandomState(0).randn(A.SR).astype("float32"))
        log(f"wav2vec2 speaker-embed: OK (dim={len(v)})")
    except Exception as e:
        log(f"wav2vec2 FAIL: {type(e).__name__}: {e}")
        return 1

    # 3. parakeet-mlx ASR weights
    try:
        from app.audiostack import audio as A
        import numpy as np
        r = A.asr_tokens((0.01 * np.random.RandomState(1).randn(A.SR)).astype("float32"))
        log(f"parakeet ASR: OK (text={r.text!r} tokens={len(r.tokens)})")
    except Exception as e:
        log(f"parakeet FAIL: {type(e).__name__}: {e}")
        return 1

    # 4. Kokoro TTS weights (corpus speaker synthesis)
    try:
        import numpy as np
        from app.audiostack import audio as A
        from app.audiostack import corpus as C
        w = C._tts("system check one two three four five", C.WEARER_VOICE)
        dur = len(w) / A.SR
        rms = float(np.sqrt(np.mean(w ** 2)))
        if dur < 1.0 or rms < 0.01:
            log(f"kokoro FAIL: silent/short (dur={dur:.2f}s rms={rms:.4f})")
            return 1
        log(f"kokoro TTS: OK REAL speech ({C.WEARER_VOICE}, "
            f"dur={dur:.2f}s rms={rms:.4f})")
    except Exception as e:
        log(f"kokoro FAIL: {type(e).__name__}: {e}")
        return 1

    log(f"ASSETS_READY in {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
