"""The brutal dirty-day corpus assembler. Synthetic speech,
weaponized adversarially, on REAL recorded acoustics.

Six MANDATORY gate-enforced properties (self_check FAILS the build
if any is soft, so an easy corpus can never inflate a pass):

  R1 ONE fixed wearer identity. A single Kokoro voice + fixed synth
     params, hashed once (WEARER_IDENTITY). Every wearer turn carries
     that hash; self_check fails on any drift.
  R2 Max non-wearer diversity + REAL acoustics. A wide non-wearer
     voice roster with per-utterance pitch/rate spread; REAL recorded
     noise/media (ESC-50) mixed UNDER the synthetic speech (never
     synthetic noise); hard low-SNR mass; real reverb; real overlap.
  R3 Adversarial, over-weighted. Near-wearer confusable voices on the
     negatives, perfect-actionable content from the wrong source,
     drive-by and about-you cases, deliberately over-weighted.
  R4 Explicit realistic turn-taking. Genuine alternation, real gap
     distribution, backchannels, response latency for wearer
     conversation; plausible but non-coordinated timing for
     distractors. self_check fails if timing is too clean/patterned.
  R5 Honest ceiling. Headline numbers are an assembled-synthetic
     corpus ceiling; the P7 report states real-room/hardware will
     score lower and the gap is unmeasured. (Enforced in reporting.)
  R6 All other build rules bind (false-trust <= 0.02 binding,
     adversarial second-model recheck, frozen systems untouched).
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from app.audiostack import audio as A

SR = A.SR

# --- R1: the ONE fixed wearer identity -----------------------------------
WEARER_VOICE = "am_michael"
_WEARER_SYNTH = {"speed": 1.0, "lang_code": "en"}
WEARER_IDENTITY = hashlib.sha256(
    (WEARER_VOICE + json.dumps(_WEARER_SYNTH, sort_keys=True)).encode()
).hexdigest()[:16]


def wearer_identity() -> str:
    return WEARER_IDENTITY


# --- R2: wide non-wearer roster (disjoint from the wearer) ---------------
_NONWEARER_VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_liam", "am_onyx",
    "bf_emma", "bf_isabella", "bf_alice", "bm_george", "bm_lewis",
    "bm_daniel", "bm_fable",
]
# R3: near-wearer pool = same male register as the wearer, used on
# negatives and pitch-nudged toward the wearer to be CONFUSABLE.
_NEAR_WEARER_VOICES = ["am_adam", "am_eric", "am_liam", "bm_george", "bm_daniel"]
assert WEARER_VOICE not in _NONWEARER_VOICES


# --- fixed difficulty floors (anti-gaming) -------------------------------
@dataclass(frozen=True)
class CatSpec:
    name: str
    min_count: int
    label: str
    wearer_turntaking: bool
    snr_db: tuple
    overlap: float
    adversarial_floor: float = 0.0   # min fraction that must be hardest-variant
    note: str = ""


CATEGORY_SPEC: list[CatSpec] = [
    CatSpec("BOSS_INSTRUCTION_IN_CONVERSATION", 80, "ACTIONABLE", True,
            (3.0, 14.0), 0.05, 0.0, "partner truly turn-taking w/ wearer"),
    CatSpec("BOSS_DRIVEBY", 50, "ACTIONABLE", False,
            (3.0, 14.0), 0.0, 0.6, "directive at wearer, NO return turn"),
    CatSpec("WEARER_DIRECT_COMMAND", 60, "ACTIONABLE", True,
            (4.0, 16.0), 0.0, 0.0, "wearer commands the agent"),
    CatSpec("STRANGER_LOUD", 80, "REJECT", False,
            (6.0, 18.0), 0.0, 0.65, "perfect command, near-wearer voice, no TT"),
    CatSpec("TV_PODCAST_PHONE", 70, "REJECT", False,
            (4.0, 16.0), 0.0, 0.6, "media/phone, fire-worthy content"),
    CatSpec("ABOUT_YOU_NOT_TO_YOU", 50, "REJECT", False,
            (3.0, 14.0), 0.05, 0.6, "others discuss a wearer task"),
    CatSpec("WEARER_SILENT_DEGRADED", 50, "DEGRADED_LOG", False,
            (3.0, 14.0), 0.05, 0.0, "long stretch, wearer silent"),
    CatSpec("NOISY_REAL_ROOM", 60, "ACTIONABLE", True,
            (-5.0, 5.0), 0.05, 0.0, "valid instruction, hard low SNR"),
    CatSpec("LOADBEARING_WORD_STRESS", 50, "CONFIRM", True,
            (-3.0, 6.0), 0.0, 0.0, "name/date/amount acoustically ambiguous"),
    CatSpec("SILENCE_AND_MEDIA_ONLY", 40, "REJECT", False,
            (6.0, 18.0), 0.0, 0.0, "no wearer conversation at all"),
]
SPEC_BY_NAME = {c.name: c for c in CATEGORY_SPEC}

# --- content. Negatives are MAXIMALLY tempting (R3). ---------------------
_PARTNER_TASKS = [
    "can you send the Q3 deck to {name} by {date}",
    "book a table for {amount} at the usual place {date}",
    "email {name} the signed contract before {date}",
    "move the standup to {date} and tell {name}",
    "please forward the budget to {name} {date}",
]
_WEARER_CMDS = [
    "send {name} the deck now", "book the {amount} pm flight to Boston",
    "reply to {name} that {date} works", "add {amount} units to the reorder",
    "schedule the review for {date}",
]
_DRIVEBY = ["send me the deck", "forward that to {name}",
            "book it for {date}", "wire the {amount}", "remind {name} about it"]
# perfect actionable commands from the WRONG source (strangers/TV)
_PERFECT_CMD = [
    "send the Q3 deck to Dana by Friday",
    "book a table for four at the usual place tonight",
    "email the signed contract before five",
    "wire fifteen thousand to the vendor account today",
    "reply to Priya that Tuesday works and add it to my calendar",
]
_MEDIA = [
    "send the deck to your team before the deadline, link in the description",
    "tell your assistant to book the table for four tonight",
    "breaking: officials say wire the funds before close of business",
    "on the show today, email us and schedule your free consultation",
]
_ABOUT_YOU = [
    "we should get {name} to send the Q3 deck, do not tell them yet",
    "someone needs {name} to wire the {amount} by {date}",
    "{name} could book the venue by {date} probably",
]
_BACKCHANNELS = ["mhm", "yeah", "right", "okay", "got it", "sure"]
# Substantive, realistic wearer turns. Real task conversations have
# the wearer saying real sentences, not 0.5s monosyllables; degenerate
# grunts are the unrealistic-easy failure AND unembeddable under
# noise. ~1.5-2.5s natural phrases: realistic (R4) and speaker-ID-able.
_WEARER_OPENERS = [
    "hey can I grab you for a second I need a hand with something",
    "okay so there is one thing I wanted to ask you about today",
    "before you run off can I get your help on a quick task",
    "hey while I have you there is something I need handled",
]
_WEARER_CLOSERS = [
    "okay got it I will take care of that this afternoon thanks a lot",
    "perfect yeah that works for me I appreciate you doing that",
    "alright sounds good I will follow up on that later today thanks",
    "great that is exactly what I needed thank you so much for that",
]
_NAMES = ["Aaron", "Erin", "Priya", "Dana", "Sean", "Shawn", "Cara", "Kara"]
_DATES = ["Friday", "the fifteenth", "the fiftieth", "Tuesday", "next week"]
_AMOUNTS = ["15", "50", "fifteen", "fifty", "two", "ten", "fifty thousand"]
_AMBIG_NAME = [("Aaron", "Erin"), ("Sean", "Shawn"), ("Cara", "Kara")]
_AMBIG_AMT = [("15", "50"), ("fifteen", "fifty")]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


# --- R2: REAL recorded backgrounds (ESC-50) ------------------------------
_esc_index: Optional[dict] = None


def _esc_dir() -> Path:
    from app.anticipy import platform_adapter
    return platform_adapter.data_dir() / "backgrounds" / "ESC-50"


def _load_esc_index() -> dict:
    global _esc_index
    if _esc_index is not None:
        return _esc_index
    base = _esc_dir()
    meta = base / "meta" / "esc50.csv"
    idx: dict = {"all": [], "media": [], "ambient": []}
    if meta.exists():
        media_cats = {"clock_tick", "vacuum_cleaner", "engine", "train",
                      "airplane", "washing_machine", "helicopter",
                      "chainsaw", "siren"}
        with meta.open() as fh:
            for row in csv.DictReader(fh):
                wav = base / "audio" / row["filename"]
                if not wav.exists():
                    continue
                idx["all"].append(str(wav))
                cat = row.get("category", "")
                (idx["media"] if cat in media_cats else idx["ambient"]).append(str(wav))
    _esc_index = idx
    return idx


def _real_bg(n: int, rng: random.Random, kind: str = "ambient") -> np.ndarray:
    """A REAL recorded-noise bed of length n samples (ESC-50). Loops/
    crops real clips. Never synthetic. Returns zeros only if the bed
    is genuinely absent (the gate forbids that path from passing).
    """
    idx = _load_esc_index()
    pool = idx.get(kind) or idx.get("all") or []
    if not pool:
        return np.zeros(n, dtype=np.float32)
    buf = np.zeros(0, dtype=np.float32)
    while len(buf) < n:
        clip = A.load_wav(rng.choice(pool))
        buf = np.concatenate([buf, clip])
    start = rng.randint(0, max(0, len(buf) - n))
    seg = buf[start:start + n]
    m = np.max(np.abs(seg))
    return (seg / m).astype(np.float32) if m > 0 else seg.astype(np.float32)


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)) + 1e-12))


def _mix_at_snr(speech: np.ndarray, bg: np.ndarray, snr_db: float) -> np.ndarray:
    s, n = _rms(speech), _rms(bg)
    if n < 1e-9:
        return speech
    out = speech + bg * ((s / (10 ** (snr_db / 20.0))) / n)
    m = np.max(np.abs(out))
    return (out / m * 0.97).astype(np.float32) if m > 1.0 else out.astype(np.float32)


def _reverb(x: np.ndarray, rng: random.Random, amount: float) -> np.ndarray:
    if amount <= 0:
        return x
    L = int(0.05 * SR)
    t = np.arange(L)
    g = np.random.default_rng(rng.randrange(1 << 30))
    ir = (np.exp(-t / (0.02 * SR)) * g.standard_normal(L)).astype(np.float32)
    ir[0] = 1.0
    y = np.convolve(x, ir)[: len(x)]
    return (x * (1 - amount) + y / (np.max(np.abs(y)) + 1e-9) * amount).astype(np.float32)


def _phone_codec(x: np.ndarray) -> np.ndarray:
    """REAL telephone path: 300-3400 Hz band + ITU G.711 mu-law
    companding (the actual phone codec, not synthetic noise).
    """
    from scipy.signal import butter, sosfilt

    sos = butter(6, [300, 3400], btype="band", fs=SR, output="sos")
    y = sosfilt(sos, x).astype(np.float32)
    mu = 255.0
    comp = np.sign(y) * np.log1p(mu * np.abs(y)) / np.log1p(mu)
    q = np.round(comp * 128) / 128.0
    exp = np.sign(q) * (1.0 / mu) * ((1 + mu) ** np.abs(q) - 1.0)
    return exp.astype(np.float32)


def _pitch_shift(x: np.ndarray, semitones: float) -> np.ndarray:
    if abs(semitones) < 0.1:
        return x
    import librosa
    return librosa.effects.pitch_shift(x, sr=SR, n_steps=semitones).astype(np.float32)


def _realized_snr_db(speech: np.ndarray, mixed: np.ndarray) -> float:
    m = min(len(speech), len(mixed))
    noise = mixed[:m] - speech[:m]
    return float(20.0 * np.log10((_rms(speech[:m]) + 1e-9) / (_rms(noise) + 1e-9)))


# --- TTS (lazy, pluggable) ----------------------------------------------

_KOKORO = None
_KOKORO_REPO = "prince-canuma/Kokoro-82M"


def _kokoro():
    """Load the Kokoro TTS model ONCE (per-call reload would be far
    too slow). Cached module-global, passed to generate_audio.
    """
    global _KOKORO
    if _KOKORO is None:
        A._models_dir()
        from mlx_audio.tts.utils import load_model

        _KOKORO = load_model(model_path=_KOKORO_REPO)
    return _KOKORO


def _tts(text: str, voice: str, speed: float = 1.0,
         pitch: float = 0.0) -> np.ndarray:
    """Synthesize one utterance. Fails LOUDLY: a TTS failure raises
    rather than silently returning silence, because a corpus of
    silent items would corrupt the test (no fabrication).
    """
    from mlx_audio.tts.generate import generate_audio

    model = _kokoro()
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "u"
        generate_audio(text=text, model=model, voice=voice, speed=speed,
                        lang_code="en", file_prefix=str(out),
                        audio_format="wav", join_audio=True, verbose=False)
        cand = sorted(Path(td).glob("*.wav"))
        if not cand:
            raise RuntimeError(f"TTS produced no audio for voice={voice!r} "
                               f"text={text[:40]!r}")
        w = A.load_wav(cand[0])
    if len(w) < int(0.15 * SR) or float(np.sqrt(np.mean(w ** 2))) < 0.005:
        raise RuntimeError(f"TTS produced silence for voice={voice!r} "
                           f"text={text[:40]!r}")
    return _pitch_shift(w, pitch) if pitch else w


def _wearer_tts(text: str) -> np.ndarray:
    return _tts(text, WEARER_VOICE, speed=_WEARER_SYNTH["speed"], pitch=0.0)


# --- R4: explicit realistic turn-taking ----------------------------------

def _gap(rng: random.Random, conversational: bool) -> np.ndarray:
    if conversational:
        d = max(0.08, rng.gauss(0.34, 0.20))
        if rng.random() < 0.12:
            d += rng.uniform(0.6, 1.6)            # occasional long pause
    else:
        d = rng.uniform(0.05, 2.2)                 # non-coordinated
    return np.zeros(int(d * SR), dtype=np.float32)


@dataclass
class CorpusItem:
    item_id: str
    category: str
    label: str
    wav_path: str
    expected_text: str
    slots: dict = field(default_factory=dict)
    ambiguous_slot: Optional[str] = None
    timeline: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    realized_snr_db: float = 0.0
    realized_overlap: float = 0.0
    wearer_turntaking: bool = False
    wearer_identity: Optional[str] = None
    nonwearer_voices: list = field(default_factory=list)
    bg_source: str = ""
    adversarial: bool = False


def _fill(t: str, rng: random.Random) -> tuple[str, dict]:
    s, slots = t, {}
    for key, pool in (("name", _NAMES), ("date", _DATES), ("amount", _AMOUNTS)):
        tok = "{" + key + "}"
        if tok in s:
            slots[key] = rng.choice(pool)
            s = s.replace(tok, slots[key])
    return s, slots


def _assemble_item(spec: CatSpec, idx: int, seed: int) -> tuple[np.ndarray, CorpusItem]:
    rng = _rng(seed)
    cat, iid = spec.name, f"{spec.name}-{idx:03d}"
    timeline: list = []
    gaps: list[float] = []
    parts: list[np.ndarray] = []
    nonwearer: list[str] = []
    adv = rng.random() < max(spec.adversarial_floor, 0.0) + 0.05
    exp_text, slots, ambig = "", {}, None
    wid: Optional[str] = None

    def add(label: str, wav: np.ndarray):
        parts.append(wav)
        timeline.append(label)

    def conv_gap():
        g = _gap(rng, True)
        gaps.append(round(len(g) / SR, 3)); parts.append(g); timeline.append("GAP")

    def free_gap():
        g = _gap(rng, False)
        gaps.append(round(len(g) / SR, 3)); parts.append(g); timeline.append("GAP")

    def nw_voice(near: bool) -> str:
        v = rng.choice(_NEAR_WEARER_VOICES if near else _NONWEARER_VOICES)
        nonwearer.append(v)
        return v

    def nw(text: str, near: bool, speed=None, phone=False, pitch=None):
        v = nw_voice(near)
        sp = speed if speed is not None else rng.uniform(0.85, 1.3)
        pt = pitch if pitch is not None else (
            rng.uniform(-1.0, 1.0) if not near else rng.uniform(-2.5, -1.0))
        w = _tts(text, v, speed=sp, pitch=pt)
        return _phone_codec(w) if phone else w

    if cat == "BOSS_INSTRUCTION_IN_CONVERSATION":
        txt, slots = _fill(rng.choice(_PARTNER_TASKS), rng)
        add("WEARER", _wearer_tts(rng.choice(_WEARER_OPENERS)))
        wid = WEARER_IDENTITY
        conv_gap(); add("S1", nw("yeah sure go ahead what do you need", False))
        conv_gap(); add("S1", nw(txt, False)); exp_text = txt
        conv_gap()
        add("WEARER", _wearer_tts(rng.choice(_WEARER_CLOSERS)))
    elif cat == "BOSS_DRIVEBY":
        txt, slots = _fill(rng.choice(_DRIVEBY), rng)
        add("S1", nw(txt, adv)); exp_text = txt          # no return turn
    elif cat == "WEARER_DIRECT_COMMAND":
        txt, slots = _fill(rng.choice(_WEARER_CMDS), rng)
        add("WEARER", _wearer_tts(txt)); wid = WEARER_IDENTITY; exp_text = txt
    elif cat == "STRANGER_LOUD":
        add("S2", nw(rng.choice(_PERFECT_CMD), adv, speed=1.05))
    elif cat == "TV_PODCAST_PHONE":
        add("MEDIA", nw(rng.choice(_MEDIA), adv,
                        phone=rng.random() < 0.5))
    elif cat == "ABOUT_YOU_NOT_TO_YOU":
        txt, slots = _fill(rng.choice(_ABOUT_YOU), rng)
        add("S2", nw(txt, adv)); free_gap(); add("S3", nw("yeah maybe", False))
    elif cat == "WEARER_SILENT_DEGRADED":
        for _ in range(rng.randint(3, 6)):
            add(rng.choice(["S1", "S2"]),
                nw(rng.choice(_PERFECT_CMD + ["nothing important here"]), False))
            free_gap()
    elif cat == "NOISY_REAL_ROOM":
        txt, slots = _fill(rng.choice(_PARTNER_TASKS), rng)
        add("WEARER", _wearer_tts(rng.choice(_WEARER_OPENERS)))
        wid = WEARER_IDENTITY
        conv_gap(); add("S1", nw(txt, False)); exp_text = txt
        conv_gap(); add("WEARER", _wearer_tts(rng.choice(_WEARER_CLOSERS)))
    elif cat == "LOADBEARING_WORD_STRESS":
        if rng.random() < 0.5:
            a, _b = rng.choice(_AMBIG_NAME)
            txt, slots, ambig = f"send the contract to {a} by Friday", {"name": a}, "name"
        else:
            a, _b = rng.choice(_AMBIG_AMT)
            txt, slots, ambig = f"wire {a} thousand to the vendor", {"amount": a}, "amount"
        add("WEARER", _wearer_tts(rng.choice(_WEARER_OPENERS)))
        wid = WEARER_IDENTITY
        conv_gap(); add("S1", nw(txt, False, speed=1.3)); exp_text = txt
    elif cat == "SILENCE_AND_MEDIA_ONLY":
        free_gap()
        if rng.random() < 0.5:
            add("MEDIA", nw(rng.choice(_MEDIA), False, phone=rng.random() < 0.3))
        free_gap()

    speech = np.concatenate(parts) if parts else np.zeros(int(0.5 * SR), np.float32)

    overlap = 0.0
    spk_parts = [p for p, l in zip(parts, timeline) if l not in ("GAP",)]
    if spec.overlap > 0 and len(spk_parts) >= 2:
        ov = int(min(len(spk_parts[0]), len(spk_parts[-1]),
                     int(spec.overlap * 1.7 * len(speech))))
        if ov > 0:
            speech[:ov] = (speech[:ov] + spk_parts[-1][:ov] * 0.85).astype(np.float32)
            overlap = ov / len(speech)

    snr = rng.uniform(*spec.snr_db)
    kind = "media" if cat in ("TV_PODCAST_PHONE", "SILENCE_AND_MEDIA_ONLY") else "ambient"
    bg_pool = _load_esc_index().get(kind) or []
    bg_src = rng.choice(bg_pool) if bg_pool else ""
    bg = _real_bg(len(speech), rng, kind)
    mixed = _mix_at_snr(speech, bg, snr)
    mixed = _reverb(mixed, rng, 0.28 if cat == "NOISY_REAL_ROOM" else 0.10)
    realized = _realized_snr_db(speech, mixed)

    it = CorpusItem(
        item_id=iid, category=cat, label=spec.label, wav_path="",
        expected_text=exp_text, slots=slots, ambiguous_slot=ambig,
        timeline=timeline, gaps=gaps, realized_snr_db=round(realized, 2),
        realized_overlap=round(overlap, 4),
        wearer_turntaking=("WEARER" in timeline),
        wearer_identity=wid, nonwearer_voices=sorted(set(nonwearer)),
        bg_source=Path(bg_src).name if bg_src else "", adversarial=bool(adv),
    )
    return mixed, it


def assemble(out_dir: str | Path, scale: float = 1.0,
             seed: int = 20260516) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    for spec in CATEGORY_SPEC:
        n = max(3, int(round(spec.min_count * scale)))
        for i in range(n):
            wav, it = _assemble_item(spec, i, seed + (hash(spec.name) % 9973) + i)
            wp = out / f"{it.item_id}.wav"
            A.write_wav(wp, wav)
            it.wav_path = str(wp)
            items.append(vars(it))
    manifest = {
        "seed": seed, "scale": scale, "n": len(items),
        "wearer_identity": WEARER_IDENTITY, "wearer_voice": WEARER_VOICE,
        "spec": {c.name: vars(c) for c in CATEGORY_SPEC},
        "items": items,
    }
    (out / "manifest.jsonl").write_text("\n".join(json.dumps(x) for x in items))
    (out / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def self_check(manifest: dict) -> tuple[bool, list[str]]:
    """FAIL if the realized corpus is softer than the fixed spec OR if
    any of R1..R4 is not actually realized. An easy corpus cannot pass.
    """
    rep: list[str] = []
    ok = True
    items = manifest["items"]
    by_cat: dict[str, list[dict]] = {}
    for it in items:
        by_cat.setdefault(it["category"], []).append(it)

    # R1: one fixed wearer identity everywhere a wearer turn exists
    wids = {it["wearer_identity"] for it in items if it.get("wearer_identity")}
    r1 = wids == {manifest["wearer_identity"]} if wids else True
    rep.append(f"R1 wearer-identity single+fixed {sorted(wids)} -> {r1}")
    ok &= r1

    # R2a: non-wearer voice diversity
    nwv = set()
    for it in items:
        nwv.update(it.get("nonwearer_voices") or [])
    r2a = len(nwv) >= 12
    rep.append(f"R2 non-wearer distinct voices = {len(nwv)} (need >=12) -> {r2a}")
    ok &= r2a

    # R2b: REAL background actually used on noised items
    noised = [it for it in items if it["category"] != "SILENCE_AND_MEDIA_ONLY"]
    with_bg = [it for it in noised if it.get("bg_source")]
    r2b = len(with_bg) >= int(0.95 * len(noised)) if noised else False
    rep.append(f"R2 real ESC-50 bg on {len(with_bg)}/{len(noised)} noised -> {r2b}")
    ok &= r2b

    # R2c: hard low-SNR mass present
    snrs = [it["realized_snr_db"] for it in items]
    hard = [s for s in snrs if s <= 6.0]
    r2c = len(hard) >= int(0.20 * len(snrs)) if snrs else False
    spread = (float(np.std(snrs)) if snrs else 0.0)
    rep.append(f"R2 low-SNR mass {len(hard)}/{len(snrs)}<=6dB spread={spread:.1f} "
               f"-> {r2c and spread >= 3.0}")
    ok &= (r2c and spread >= 3.0)

    # R3: adversarial over-weight on the negative categories that need it
    for spec in CATEGORY_SPEC:
        if spec.adversarial_floor <= 0:
            continue
        its = by_cat.get(spec.name, [])
        if not its:
            ok = False; rep.append(f"R3 {spec.name}: MISSING"); continue
        frac = sum(1 for it in its if it.get("adversarial")) / len(its)
        good = frac >= spec.adversarial_floor - 0.10
        rep.append(f"R3 {spec.name} adversarial={frac:.2f} "
                   f"(floor {spec.adversarial_floor}) -> {good}")
        ok &= good

    # R4: turn-taking realistic, not too clean / too patterned
    conv_gaps = [g for it in items if it["wearer_turntaking"]
                 for g in (it.get("gaps") or [])]
    gvar = float(np.std(conv_gaps)) if conv_gaps else 0.0
    r4 = gvar >= 0.12 and len(conv_gaps) >= 10
    rep.append(f"R4 conv-gap stdev={gvar:.3f}s n={len(conv_gaps)} "
               f"(need stdev>=0.12) -> {r4}")
    ok &= r4

    # spec floors: counts, SNR band not too easy, wearer-TT presence
    for spec in CATEGORY_SPEC:
        its = by_cat.get(spec.name, [])
        need = max(3, int(round(spec.min_count * manifest["scale"])))
        if len(its) < need:
            ok = False; rep.append(f"{spec.name}: count {len(its)}<{need}"); continue
        msnr = float(np.mean([it["realized_snr_db"] for it in its]))
        wt = sum(1 for it in its if it["wearer_turntaking"]) / len(its)
        soft = msnr > spec.snr_db[1] + 4.0
        if soft:
            ok = False
            rep.append(f"{spec.name}: TOO EASY snr {msnr:.1f} > {spec.snr_db[1]}+4")
        if spec.wearer_turntaking and wt < 0.9:
            ok = False; rep.append(f"{spec.name}: wearerTT {wt:.2f}<0.9")
        if not spec.wearer_turntaking and wt > 0.1:
            ok = False; rep.append(f"{spec.name}: unwanted wearerTT {wt:.2f}>0.1")
        rep.append(f"{spec.name}: n={len(its)} snr~{msnr:.1f} wearerTT={wt:.2f}")

    return ok, rep
