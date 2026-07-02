from __future__ import annotations

import math
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
RENDERS = ROOT / "renders"
VOICE = ASSETS / "voice.wav"
MUSIC = ASSETS / "music_bed.wav"
MIX = ASSETS / "mix.wav"
OUT = RENDERS / "anticipy-card-stop-v2.mp4"

W, H = 1080, 1920
FPS = 30
DURATION = 12.8
TOTAL = int(FPS * DURATION)
SR = 48000

INK = (9, 9, 8)
PAPER = (244, 239, 231)
CREAM = (255, 248, 234)
RED = (224, 82, 61)
ACID = (217, 255, 91)
BRASS = (200, 168, 106)
MUTED = (129, 120, 106)
BLACK = (0, 0, 0)

FONT_DIR = Path("/System/Library/Fonts/Supplemental")
SANS = FONT_DIR / "Arial.ttf"
BOLD = FONT_DIR / "Arial Bold.ttf"
BLACK_FONT = FONT_DIR / "Arial Black.ttf"
SERIF_BOLD = FONT_DIR / "Georgia Bold.ttf"


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size=size)


F = {
    "tiny": font(BOLD, 25),
    "small": font(BOLD, 31),
    "body": font(SANS, 34),
    "body_bold": font(BOLD, 38),
    "caption": font(BLACK_FONT, 64),
    "caption2": font(BLACK_FONT, 78),
    "mega": font(BLACK_FONT, 138),
    "mega2": font(BLACK_FONT, 156),
    "stamp": font(BLACK_FONT, 118),
    "serif": font(SERIF_BOLD, 106),
}


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def ease_out(x: float) -> float:
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_in(x: float) -> float:
    x = clamp(x)
    return x ** 3


def ease_io(x: float) -> float:
    x = clamp(x)
    return 0.5 - 0.5 * math.cos(math.pi * x)


def rgba(c: tuple[int, int, int], a: float | int) -> tuple[int, int, int, int]:
    return (*c, int(a if isinstance(a, int) else clamp(a) * 255))


def text_size(d: ImageDraw.ImageDraw, s: str, f: ImageFont.FreeTypeFont) -> tuple[int, int]:
    b = d.textbbox((0, 0), s, font=f)
    return b[2] - b[0], b[3] - b[1]


def wrap(d: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = word if not current else current + " " + word
        if text_size(d, trial, f)[0] <= max_w:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_wrap(d: ImageDraw.ImageDraw, xy, text, f, fill, max_w, gap=8, alpha=1.0) -> int:
    x, y = xy
    for line in wrap(d, text, f, max_w):
        d.text((x, y), line, font=f, fill=rgba(fill, alpha))
        y += text_size(d, line, f)[1] + gap
    return y


def rect(d: ImageDraw.ImageDraw, box, fill, outline=None, width=1, r=6) -> None:
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def fit_line(d: ImageDraw.ImageDraw, text: str, font_path: Path, max_w: int, start: int) -> ImageFont.FreeTypeFont:
    size = start
    while size > 40:
        f = font(font_path, size)
        if text_size(d, text, f)[0] <= max_w:
            return f
        size -= 4
    return font(font_path, size)


def base(t: float) -> Image.Image:
    bg = RED if t < 0.16 else INK
    img = Image.new("RGBA", (W, H), bg + (255,))
    d = ImageDraw.Draw(img, "RGBA")
    for y in range(0, H, 96):
        d.line((0, y + int(18 * math.sin(t * 5 + y)), W, y + int(18 * math.sin(t * 5 + y)) + 1), fill=rgba(CREAM, 0.16), width=1)
    for x in range(-240, W + 180, 180):
        d.line((x + int(t * 30) % 180, 0, x - 500 + int(t * 30) % 180, H), fill=rgba(BRASS, 0.11), width=3)
    return img


def caption_bar(d: ImageDraw.ImageDraw, text: str, y: int, accent=ACID, alpha=1.0) -> None:
    lines = wrap(d, text.upper(), F["caption"], 900)
    h = len(lines) * 74 + 48
    rect(d, (48, y, W - 48, y + h), rgba(BLACK, 0.86 * alpha), outline=rgba(accent, 0.95 * alpha), width=3, r=8)
    ty = y + 25
    for line in lines:
        f = fit_line(d, line, BLACK_FONT, 880, 64)
        d.text((72, ty), line, font=f, fill=rgba(CREAM, alpha))
        ty += 74


def warning_scene(t: float) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    shake = int(math.sin(t * 80) * 10 * (1 - clamp(t / 0.75)))
    d.rectangle((0, 0, W, 318), fill=rgba(RED, 1))
    draw_wrap(d, (58 + shake, 214), "DON'T GIVE YOUR AI YOUR CARD", F["mega"], CREAM, 970, 0)
    x, y = 92 + shake, 900
    rect(d, (x, y, x + 896, y + 510), rgba(PAPER, 1), outline=rgba(RED, 1), width=7, r=22)
    d.text((x + 44, y + 42), "CARD ENDING 0427", font=F["small"], fill=rgba(MUTED, 1))
    d.text((x + 44, y + 176), "AI AGENT", font=F["caption2"], fill=rgba(INK, 1))
    d.text((x + 44, y + 288), "permission?", font=F["body_bold"], fill=rgba(MUTED, 1))
    d.line((x + 36, y + 380, x + 860, y + 130), fill=rgba(RED, 1), width=24)
    d.line((x + 36, y + 130, x + 860, y + 380), fill=rgba(RED, 1), width=24)
    return img


def receipt_scene(t: float) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    p = ease_out((t - 1.15) / 0.42)
    y = int(248 + (1 - p) * 80)
    d.text((58, 118), "2:47 AM", font=F["caption2"], fill=rgba(ACID, p))
    rect(d, (58, y, 1022, y + 612), rgba(PAPER, p), outline=rgba(BRASS, p), width=3, r=10)
    d.text((100, y + 58), "voice note", font=F["small"], fill=rgba(MUTED, p))
    d.text((100, y + 150), "black umbrella", font=F["mega"], fill=rgba(INK, p))
    d.text((100, y + 314), "before Seattle", font=F["mega"], fill=rgba(INK, p))
    d.text((100, y + 486), "one stupid errand", font=F["body_bold"], fill=rgba(RED, p))
    caption_bar(d, "I did. uh, for one stupid errand.", 1148, alpha=p)
    return img


def checkout_scene(t: float) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    p = ease_out((t - 2.55) / 0.45)
    rect(d, (58, 208, 1022, 1334), rgba(PAPER, p), outline=rgba(RED, 0.95 * p), width=3, r=14)
    d.text((96, 258), "checkout opened", font=F["caption"], fill=rgba(INK, p))
    d.line((96, 372, 984, 372), fill=rgba(INK, 0.18 * p), width=3)
    rows = [("black travel umbrella", "$28.00"), ("shipping before Seattle", "$8.94"), ("card field", "LOCKED")]
    y = 458
    for left, right in rows:
        color = RED if right == "LOCKED" else INK
        d.text((96, y), left, font=F["body_bold"], fill=rgba(INK, p))
        tw = text_size(d, right, F["body_bold"])[0]
        d.text((984 - tw, y), right, font=F["body_bold"], fill=rgba(color, p))
        y += 112
    bx, by = 126, 1000
    rect(d, (bx, by, bx + 828, by + 132), rgba(RED, p), r=12)
    d.text((bx + 168, by + 34), "PAY $36.94", font=F["caption"], fill=rgba(CREAM, p))
    cursor_x = int(860 - 90 * math.sin(t * 4))
    d.polygon([(cursor_x, by + 164), (cursor_x + 70, by + 238), (cursor_x + 26, by + 238)], fill=rgba(ACID, p))
    caption_bar(d, "checkout opened.", 1440, accent=RED, alpha=p)
    return img


def stopped_scene(t: float) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    p = ease_out((t - 4.12) / 0.20)
    flash = 1 if t < 4.32 else 0
    if flash:
        d.rectangle((0, 0, W, H), fill=rgba(PAPER, 0.92 * (1 - ease_in((t - 4.12) / 0.2))))
    d.rectangle((0, 470, W, 895), fill=rgba(RED, p))
    d.text((60, 565), "IT", font=F["mega2"], fill=rgba(CREAM, p))
    d.text((60, 730), "STOPPED.", font=fit_line(d, "STOPPED.", BLACK_FONT, 980, 170), fill=rgba(CREAM, p))
    d.text((62, 1020), "not declined. stopped.", font=F["caption2"], fill=rgba(ACID, p))
    return img


def boundary_scene(t: float) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    items = [("NO CARD FIELD", 5.34), ("NO SEND BUTTON", 5.88), ("NO GUESSING", 6.42)]
    y = 376
    for label, start in items:
        p = ease_out((t - start) / 0.28)
        x = int(58 + (1 - p) * -80)
        rect(d, (x, y, x + 964, y + 202), rgba(PAPER, p), outline=rgba(ACID, p), width=4, r=10)
        d.text((x + 40, y + 50), label, font=F["caption2"], fill=rgba(INK, p))
        y += 248
    p = ease_out((t - 6.98) / 0.34)
    d.text((58, 1268), "that's the line", font=F["serif"], fill=rgba(CREAM, p))
    d.text((58, 1390), "I trust.", font=F["serif"], fill=rgba(CREAM, p))
    return img


def product_scene(t: float) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    p = ease_out((t - 8.05) / 0.45)
    d.text((58, 178), "Anticipy", font=F["caption2"], fill=rgba(CREAM, p))
    d.text((58, 286), "AI that knows", font=F["serif"], fill=rgba(CREAM, p))
    d.text((58, 410), "where the line is.", font=F["serif"], fill=rgba(CREAM, p))
    rect(d, (58, 760, 1022, 1160), rgba(PAPER, p), outline=rgba(ACID, p), width=4, r=12)
    d.text((98, 820), "task", font=F["small"], fill=rgba(MUTED, p))
    d.text((98, 910), "finish reversible work", font=F["caption"], fill=rgba(INK, p))
    d.text((98, 1020), "stop before permission", font=F["caption"], fill=rgba(RED, p))
    caption_bar(d, "not a helper. a boundary.", 1310, accent=ACID, alpha=p)
    return img


def cta_scene(t: float) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    p = ease_out((t - 10.24) / 0.35)
    d.text((58, 190), "comment", font=F["caption2"], fill=rgba(CREAM, p))
    d.text((58, 316), "STOP", font=F["mega2"], fill=rgba(ACID, p))
    d.text((58, 512), "I'll send the", font=F["serif"], fill=rgba(CREAM, p))
    d.text((58, 642), "private build.", font=F["serif"], fill=rgba(CREAM, p))
    rect(d, (58, 1180, 1022, 1394), rgba(RED, p), r=12)
    d.text((92, 1240), "DO NOT GIVE AI YOUR CARD", font=fit_line(d, "DO NOT GIVE AI YOUR CARD", BLACK_FONT, 900, 70), fill=rgba(CREAM, p))
    loop = clamp((t - 12.15) / 0.45)
    if loop:
        d.rectangle((0, 0, W, H), fill=rgba(RED, loop * 0.94))
        d.text((58, 760), "DO NOT", font=F["mega2"], fill=rgba(CREAM, loop))
    return img


def overlay(img: Image.Image, over: Image.Image, alpha=1.0) -> None:
    if alpha < 1:
        over = over.copy()
        a = over.getchannel("A").point(lambda v: int(v * alpha))
        over.putalpha(a)
    img.alpha_composite(over)


def scene_id(t: float) -> int:
    if t < 1.15:
        return 0
    if t < 2.55:
        return 1
    if t < 4.12:
        return 2
    if t < 5.34:
        return 3
    if t < 8.05:
        return 4
    if t < 10.24:
        return 5
    return 6


SCENES = [warning_scene, receipt_scene, checkout_scene, stopped_scene, boundary_scene, product_scene, cta_scene]


def frame(t: float) -> Image.Image:
    img = base(t)
    overlay(img, SCENES[scene_id(t)](t))
    return img.convert("RGB")


def generate_music() -> None:
    MUSIC.parent.mkdir(parents=True, exist_ok=True)
    samples = int(DURATION * SR)
    left = [0.0] * samples
    right = [0.0] * samples

    def add_sine(start, dur, freq, amp, pan=0.0, decay=True):
        a = int(start * SR)
        b = min(samples, int((start + dur) * SR))
        for i in range(a, b):
            x = (i - a) / SR
            env = math.exp(-x * 4.2) if decay else 1.0
            v = math.sin(2 * math.pi * freq * x) * amp * env
            left[i] += v * (1 - max(0, pan))
            right[i] += v * (1 + min(0, pan))

    def add_noise(start, dur, amp, pan=0.0):
        a = int(start * SR)
        b = min(samples, int((start + dur) * SR))
        seed = 97
        for i in range(a, b):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            n = ((seed / 0x7FFFFFFF) * 2 - 1)
            x = (i - a) / max(1, b - a)
            env = math.sin(math.pi * x)
            v = n * amp * env
            left[i] += v * (1 - max(0, pan))
            right[i] += v * (1 + min(0, pan))

    for beat in [0.0, 0.55, 1.10, 1.65, 2.20, 2.75, 3.30, 3.85, 4.12, 4.67, 5.22, 5.77, 6.32, 6.87, 7.42, 7.97, 8.52, 9.07, 9.62, 10.17, 10.72, 11.27, 11.82]:
        add_sine(beat, 0.20, 52, 0.42)
    for tick in [i * 0.275 for i in range(int(DURATION / 0.275))]:
        add_noise(tick, 0.035, 0.045, pan=0.35 if int(tick * 10) % 2 else -0.35)
    for hit in [0.0, 1.15, 2.55, 4.12, 5.34, 8.05, 10.24, 12.15]:
        add_noise(hit, 0.12, 0.28)
        add_sine(hit, 0.35, 88, 0.34)
    add_sine(0.0, DURATION, 34, 0.09, decay=False)
    add_sine(4.12, 0.55, 160, 0.24)
    add_noise(4.10, 0.22, 0.36)

    peak = max(0.01, max(abs(v) for v in left + right))
    scale = 0.84 / peak
    with wave.open(str(MUSIC), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        frames = bytearray()
        for l, r in zip(left, right):
            for v in (l * scale, r * scale):
                iv = max(-32767, min(32767, int(v * 32767)))
                frames.extend(iv.to_bytes(2, "little", signed=True))
        w.writeframes(frames)


def mix_audio() -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(VOICE),
            "-i",
            str(MUSIC),
            "-filter_complex",
            "[0:a]aresample=48000,volume=1.95,acompressor=threshold=-16dB:ratio=2.5:attack=8:release=80[v];"
            "[1:a]volume=0.34,afade=t=out:st=11.9:d=0.8[m];"
            "[v][m]amix=inputs=2:duration=longest:weights=1 1,"
            "dynaudnorm=f=75:g=17:p=0.95,volume=1.8,alimiter=limit=0.98,apad=pad_dur=2[a]",
            "-map",
            "[a]",
            "-t",
            str(DURATION),
            "-ac",
            "2",
            "-ar",
            "48000",
            str(MIX),
        ],
        check=True,
    )


def render_video() -> None:
    RENDERS.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-i",
        str(MIX),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-t",
        str(DURATION),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(OUT),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for n in range(TOTAL):
        proc.stdin.write(frame(n / FPS).tobytes())
        if n % FPS == 0:
            print(f"rendered {n // FPS:02d}s/{DURATION:.1f}s", flush=True)
    proc.stdin.close()
    code = proc.wait()
    if code:
        raise SystemExit(code)


def main() -> None:
    if not VOICE.exists():
        raise SystemExit(f"missing voice file: {VOICE}")
    generate_music()
    mix_audio()
    render_video()
    print(OUT)


if __name__ == "__main__":
    main()
