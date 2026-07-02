from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "renders" / "anticipy-money-stop.mp4"
AUDIO = ROOT / "assets" / "narration.wav"

W, H = 1080, 1920
FPS = 30
DURATION = 16
TOTAL_FRAMES = FPS * DURATION

BG = (17, 16, 13)
SURFACE = (244, 239, 231)
INK = (25, 23, 19)
MUTED = (118, 111, 98)
BRASS = (200, 168, 106)
RED = (200, 100, 79)
GREEN = (110, 167, 119)
BLACK = (12, 12, 12)

FONT_DIR = Path("/System/Library/Fonts/Supplemental")
FONT_ARIAL = FONT_DIR / "Arial.ttf"
FONT_ARIAL_BOLD = FONT_DIR / "Arial Bold.ttf"
FONT_ARIAL_BLACK = FONT_DIR / "Arial Black.ttf"
FONT_GEORGIA_BOLD = FONT_DIR / "Georgia Bold.ttf"


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size=size)


F = {
    "small": font(FONT_ARIAL_BOLD, 26),
    "body": font(FONT_ARIAL, 31),
    "body_bold": font(FONT_ARIAL_BOLD, 34),
    "mid": font(FONT_ARIAL_BOLD, 44),
    "card": font(FONT_ARIAL_BLACK, 56),
    "blocked": font(FONT_ARIAL_BLACK, 58),
    "headline": font(FONT_GEORGIA_BOLD, 103),
    "headline_big": font(FONT_GEORGIA_BOLD, 124),
    "quote": font(FONT_GEORGIA_BOLD, 73),
    "boundary": font(FONT_GEORGIA_BOLD, 130),
}


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def ease_out(x: float) -> float:
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_in_out(x: float) -> float:
    x = clamp(x)
    return 0.5 - 0.5 * math.cos(math.pi * x)


def with_alpha(color: tuple[int, int, int], alpha: float | int) -> tuple[int, int, int, int]:
    a = int(alpha if isinstance(alpha, int) else clamp(alpha) * 255)
    return (*color, a)


def layer() -> Image.Image:
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def paste(base: Image.Image, over: Image.Image, alpha: float = 1.0) -> None:
    if alpha < 1:
        over = over.copy()
        a = over.getchannel("A").point(lambda p: int(p * alpha))
        over.putalpha(a)
    base.alpha_composite(over)


def text_size(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=face)
    return box[2] - box[0], box[3] - box[1]


def wrap(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = word if not current else f"{current} {word}"
        if text_size(draw, trial, face)[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    face: ImageFont.FreeTypeFont,
    color: tuple[int, int, int],
    max_width: int,
    line_gap: int,
    alpha: float = 1.0,
) -> int:
    x, y = xy
    for line in wrap(draw, text, face, max_width):
        draw.text((x, y), line, font=face, fill=with_alpha(color, alpha))
        y += text_size(draw, line, face)[1] + line_gap
    return y


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill, outline=None, width: int = 1, radius: int = 8) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def pill(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, face, fill, fg, pad_x=24, pad_y=16, alpha=1.0) -> tuple[int, int, int, int]:
    tw, th = text_size(draw, text, face)
    x, y = xy
    box = (x, y, x + tw + pad_x * 2, y + th + pad_y * 2)
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=with_alpha(fill, alpha), outline=with_alpha(SURFACE, 0.16))
    draw.text((x + pad_x, y + pad_y - 1), text, font=face, fill=with_alpha(fg, alpha))
    return box


def base_frame(t: float) -> Image.Image:
    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img, "RGBA")
    drift = math.sin(t * 0.35) * 18
    d.polygon([(-240, 156 + drift), (W + 200, -26 + drift), (W + 220, 150 + drift), (-240, 332 + drift)], fill=with_alpha(BRASS, 0.18))
    d.polygon([(-210, H - 246 - drift), (W + 180, H - 52 - drift), (W + 180, H + 126 - drift), (-210, H - 70 - drift)], fill=with_alpha(RED, 0.18))
    for i in range(0, H, 38):
        if i % 114 == 0:
            d.line((0, i, W, i + 1), fill=(244, 239, 231, 8), width=1)
    return img


def draw_receipt_scene(t: float) -> Image.Image:
    p = ease_out((t - 0.10) / 0.85)
    img = layer()
    d = ImageDraw.Draw(img, "RGBA")
    y_shift = int((1 - p) * 54)
    alpha = p
    pill(d, (78, 188 + y_shift), "payment boundary", F["small"], BLACK, BRASS, alpha=alpha)
    d.ellipse((82, 204 + y_shift, 102, 224 + y_shift), fill=with_alpha(RED, alpha))
    x, y, w, h = 78, 390 + y_shift, 924, 330
    rounded(d, (x, y, x + w, y + h), fill=with_alpha(SURFACE, alpha), outline=with_alpha(BRASS, 0.45 * alpha), width=2)
    d.text((x + 34, y + 34), "checkout", font=F["small"], fill=with_alpha(MUTED, alpha))
    d.text((x + w - 150, y + 34), "2:47 am", font=F["small"], fill=with_alpha(MUTED, alpha))
    d.text((x + 34, y + 108), "black travel umbrella", font=F["body_bold"], fill=with_alpha(INK, alpha))
    d.text((x + w - 156, y + 108), "$28.00", font=F["body_bold"], fill=with_alpha(INK, alpha))
    d.line((x + 34, y + 172, x + w - 34, y + 172), fill=with_alpha(INK, 0.16 * alpha), width=2)
    d.text((x + 34, y + 204), "STOPPED BEFORE PAYMENT", font=F["blocked"], fill=with_alpha(RED, alpha))
    d.text((x + 34, y + 274), "card field never touched", font=F["body"], fill=with_alpha(MUTED, alpha))
    draw_wrapped(d, (78, 800 + y_shift), "the first AI I trust refused to finish.", F["headline"], SURFACE, 910, 10, alpha)
    return img


def draw_voice_scene(t: float) -> Image.Image:
    p = ease_out((t - 2.92) / 0.85)
    img = layer()
    d = ImageDraw.Draw(img, "RGBA")
    y_shift = int((1 - p) * 66)
    alpha = p
    x, y, w, h = 78, 420 + y_shift, 924, 600
    rounded(d, (x, y, x + w, y + h), fill=with_alpha(SURFACE, alpha), outline=with_alpha(BRASS, 0.45 * alpha), width=2)
    d.text((x + 42, y + 42), "voice note", font=F["small"], fill=with_alpha(MUTED, alpha))
    d.text((x + w - 104, y + 42), "0:06", font=F["small"], fill=with_alpha(MUTED, alpha))
    for i in range(10):
        bar_h = 48 + 96 * abs(math.sin(t * 4.0 + i * 0.7))
        bx = x + 46 + i * 48
        by = y + 240 - bar_h / 2
        d.rounded_rectangle((bx, by, bx + 18, by + bar_h), radius=9, fill=with_alpha(BRASS, alpha))
    draw_wrapped(d, (x + 42, y + 346), "“uh, grab the black umbrella before Seattle”", F["quote"], INK, 810, 12, alpha)
    pill(d, (78, 1090 + y_shift), "messy sentence in. actual task out.", F["body_bold"], BLACK, SURFACE, alpha=alpha)
    return img


def draw_cards_scene(t: float) -> Image.Image:
    img = layer()
    d = ImageDraw.Draw(img, "RGBA")
    cards = [
        ("01", "found the item", "matched “black umbrella” to the open loop", 6.20, BRASS),
        ("02", "cart prepared", "reversible work only", 6.68, BRASS),
        ("03", "payment stopped", "you press the final button", 7.16, RED),
    ]
    y = 372
    for idx, title, body, start, accent in cards:
        p = ease_out((t - start) / 0.55)
        a = p
        dx = int((1 - p) * (-54 if idx == "01" else 54 if idx == "02" else 0))
        dy = int((1 - p) * (54 if idx == "03" else 0))
        x = 78 + dx
        rounded(d, (x, y + dy, x + 924, y + dy + 282), fill=with_alpha(SURFACE, a), outline=with_alpha(accent, 0.7 * a), width=2)
        d.text((x + 38, y + dy + 74), idx, font=F["mid"], fill=with_alpha(BRASS, a))
        d.text((x + 156, y + dy + 62), title, font=F["card"], fill=with_alpha(INK, a))
        draw_wrapped(d, (x + 156, y + dy + 136), body, F["body"], MUTED, 710, 8, a)
        y += 318
    return img


def draw_boundary_scene(t: float) -> Image.Image:
    img = layer()
    d = ImageDraw.Draw(img, "RGBA")
    lines = [("no payment", 9.50, -58), ("no send", 10.02, 58), ("no guessing", 10.54, 0)]
    y = 522
    for text, start, offset in lines:
        p = ease_out((t - start) / 0.52)
        x = 78 + int((1 - p) * offset)
        d.text((x, y), text, font=F["boundary"], fill=with_alpha(SURFACE, p))
        y += 156
    p = ease_out((t - 11.08) / 0.45)
    d.text((78, y + 34), "just the line.", font=F["mid"], fill=with_alpha(BRASS, p))
    return img


def draw_final_scene(t: float) -> Image.Image:
    img = layer()
    d = ImageDraw.Draw(img, "RGBA")
    p = ease_out((t - 12.27) / 0.8)
    a = p
    y_shift = int((1 - p) * 62)
    x, y, w, h = 78, 420 + y_shift, 924, 292
    rounded(d, (x, y, x + w, y + h), fill=with_alpha(SURFACE, a), outline=with_alpha(GREEN, 0.55 * a), width=2)
    d.text((x + 34, y + 34), "Anticipy", font=F["small"], fill=with_alpha(MUTED, a))
    d.text((x + w - 92, y + 34), "local", font=F["small"], fill=with_alpha(MUTED, a))
    d.text((x + 34, y + 118), "ADMIN CAUGHT", font=F["blocked"], fill=with_alpha(GREEN, a))
    d.text((x + 34, y + 198), "reversible work done. money left to you.", font=F["body"], fill=with_alpha(MUTED, a))
    draw_wrapped(d, (78, 790 + y_shift), "that is the product.", F["headline_big"], SURFACE, 900, 12, a)
    pill(d, (78, 1118 + y_shift), "comment ADMIN for the private setup", F["body_bold"], BLACK, SURFACE, alpha=a)
    fade = clamp((t - 15.64) / 0.36)
    if fade:
        d.rectangle((0, 0, W, H), fill=with_alpha(BG, fade))
    return img


TRANSITIONS = [(2.70, 2.92), (5.85, 6.07), (9.15, 9.37), (12.05, 12.27)]


def scene_for_time(t: float) -> int:
    if t < 2.92:
        return 1
    if t < 6.07:
        return 2
    if t < 9.37:
        return 3
    if t < 12.27:
        return 4
    return 5


def draw_scene(t: float, scene: int) -> Image.Image:
    return {
        1: draw_receipt_scene,
        2: draw_voice_scene,
        3: draw_cards_scene,
        4: draw_boundary_scene,
        5: draw_final_scene,
    }[scene](t)


def draw_wipe(img: Image.Image, t: float) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    for start, end in TRANSITIONS:
        dur = end - start
        if start <= t <= end:
            p = ease_in_out((t - start) / dur)
            y = int(-H * 1.05 + p * H * 2.1)
            d.rectangle((0, y, W, y + int(H * 1.12)), fill=SURFACE + (255,))


def frame(t: float) -> Image.Image:
    img = base_frame(t)
    paste(img, draw_scene(t, scene_for_time(t)))
    draw_wipe(img, t)
    return img.convert("RGB")


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
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
        str(AUDIO),
        "-filter_complex",
        "[1:a]apad=pad_dur=2[a]",
        "-map",
        "0:v:0",
        "-map",
        "[a]",
        "-t",
        str(DURATION),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(OUT),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for n in range(TOTAL_FRAMES):
        proc.stdin.write(frame(n / FPS).tobytes())
        if n % FPS == 0:
            print(f"rendered {n // FPS:02d}s/{DURATION}s", flush=True)
    proc.stdin.close()
    code = proc.wait()
    if code:
        raise SystemExit(code)
    print(OUT)


if __name__ == "__main__":
    main()
