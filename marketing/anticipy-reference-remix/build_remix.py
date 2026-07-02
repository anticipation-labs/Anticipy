from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent
SOURCE = Path("/Users/omarebrahim/anticipy-reel/reference/reference.mp4")
FRAMES = ROOT / "overlay_frames"
ASSETS = ROOT / "assets"
OUT_OVERLAY = ROOT / "overlay.mov"
OUT_VIDEO = ROOT / "anticipy-reference-remix.mp4"

WIDTH = 1440
HEIGHT = 1080
FPS = 2997 / 125
DURATION = 32.619
TOTAL = math.ceil(DURATION * FPS)

FONT_DIR = Path("/Users/omarebrahim/Anticipy/marketing/anticipy-social-network-card-reel/assets/fonts")
SERIF = FONT_DIR / "-nFnOHM81r4j6k0gjAW3mujVU2B2K_c.ttf"
SANS_REG = FONT_DIR / "zYXGKVElMYYaJe8bpLHnCwDKr932-G7dytD-Dmu1swZSAXcomDVmadSD6llzAA.ttf"
SANS_BOLD = FONT_DIR / "zYXGKVElMYYaJe8bpLHnCwDKr932-G7dytD-Dmu1swZSAXcomDVmadSDDV5zAA.ttf"

CREAM = (245, 240, 235, 255)
BRASS = (210, 177, 105, 255)
CHARCOAL = (17, 16, 13, 220)
GREEN = (115, 176, 126, 255)


def ease_out_cubic(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def ease_in_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def between(t: float, start: float, end: float) -> float:
    if t < start or t > end:
        return 0.0
    edge = min(0.22, (end - start) / 3)
    if t < start + edge:
        return ease_out_cubic((t - start) / edge)
    if t > end - edge:
        return ease_out_cubic((end - t) / edge)
    return 1.0


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def draw_text_block(
    canvas: Image.Image,
    text: str,
    xy: tuple[int, int],
    size: int,
    alpha: float,
    color=CREAM,
    max_width: int | None = None,
    line_gap: int = 8,
    family: Path = SERIF,
) -> None:
    if alpha <= 0:
        return
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = font(family, size)
    x, y = xy
    lines: list[str] = []
    if max_width:
        words = text.split()
        current = ""
        for word in words:
            trial = (current + " " + word).strip()
            if d.textbbox((0, 0), trial, font=f)[2] <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    else:
        lines = text.split("\n")
    fill = (color[0], color[1], color[2], int(color[3] * alpha))
    shadow = (0, 0, 0, int(150 * alpha))
    for line in lines:
        d.text((x + 3, y + 5), line, font=f, fill=shadow)
        d.text((x, y), line, font=f, fill=fill)
        y += size + line_gap
    canvas.alpha_composite(layer)


def rounded_panel(canvas: Image.Image, box: tuple[int, int, int, int], alpha: float) -> None:
    if alpha <= 0:
        return
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    fill = (17, 16, 13, int(188 * alpha))
    outline = (245, 240, 235, int(50 * alpha))
    d.rounded_rectangle(box, radius=26, fill=fill, outline=outline, width=1)
    canvas.alpha_composite(layer)


def make_card() -> Image.Image:
    w, h = 800, 250
    rng = np.random.default_rng(4)
    x = np.linspace(0, 1, w)
    y = np.linspace(0, 1, h)[:, None]
    base = 190 + 34 * x + 22 * np.sin(x * math.pi * 2.2) + 16 * np.cos(y * math.pi * 1.4)
    noise = rng.normal(0, 4.5, (h, w))
    metal = np.clip(base + noise, 130, 238).astype(np.uint8)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(metal + 15, 0, 255)
    arr[:, :, 1] = np.clip(metal + 10, 0, 255)
    arr[:, :, 2] = np.clip(metal - 4, 0, 255)
    arr[:, :, 3] = 255
    card = Image.fromarray(arr, "RGBA")
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, w - 1, h - 1), radius=34, fill=255)
    card.putalpha(mask)

    d = ImageDraw.Draw(card)
    ink = (22, 20, 18, 236)
    icon_x = w // 2
    d.rounded_rectangle((icon_x - 17, 32, icon_x + 17, 91), radius=18, outline=ink, width=5)
    d.ellipse((icon_x - 5, 73, icon_x + 5, 83), fill=ink)
    title = "Anticipy."
    f_title = font(SERIF, 94)
    tw = d.textbbox((0, 0), title, font=f_title)[2]
    d.text(((w - tw) // 2, 100), title, font=f_title, fill=ink)
    tag = "Vibe your life."
    f_tag = font(SERIF, 32)
    tw = d.textbbox((0, 0), tag, font=f_tag)[2]
    d.text(((w - tw) // 2, 196), tag, font=f_tag, fill=(70, 62, 46, 210))
    return card


def perspective_coeffs(src: list[tuple[float, float]], dst: list[tuple[float, float]]) -> list[float]:
    matrix = []
    vector = []
    for (x, y), (u, v) in zip(dst, src):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        vector.append(u)
        vector.append(v)
    return np.linalg.solve(np.array(matrix, dtype=float), np.array(vector, dtype=float)).tolist()


def paste_perspective(
    canvas: Image.Image,
    img: Image.Image,
    quad: list[tuple[int, int]],
    alpha: float,
    half: float = 1.0,
) -> None:
    if alpha <= 0:
        return
    src = [(0, 0), (img.width, 0), (img.width, img.height), (0, img.height)]
    coeffs = perspective_coeffs(src, quad)
    card = img.copy()
    if half < 0.999:
        mask = card.getchannel("A")
        wipe = Image.new("L", card.size, 0)
        d = ImageDraw.Draw(wipe)
        cut = int(card.width * half)
        d.rectangle((0, 0, cut, card.height), fill=255)
        edge = 18
        for i in range(edge):
            a = int(255 * (1 - i / edge))
            d.rectangle((cut + i, 0, cut + i, card.height), fill=a)
        card.putalpha(Image.composite(mask, Image.new("L", card.size, 0), wipe))
    warped = card.transform((WIDTH, HEIGHT), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC)
    if alpha < 1:
        a = warped.getchannel("A").point(lambda p: int(p * alpha))
        warped.putalpha(a)
    canvas.alpha_composite(warped)


def draw_scan_line(canvas: Image.Image, quad: list[tuple[int, int]], half: float, alpha: float) -> None:
    if alpha <= 0:
        return
    top = np.array(quad[0]) * (1 - half) + np.array(quad[1]) * half
    bottom = np.array(quad[3]) * (1 - half) + np.array(quad[2]) * half
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.line((tuple(top), tuple(bottom)), fill=(235, 203, 126, int(230 * alpha)), width=5)
    d.line((tuple(top + np.array([7, 0])), tuple(bottom + np.array([7, 0]))), fill=(255, 255, 255, int(70 * alpha)), width=2)
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(0.4)))


def draw_particles(canvas: Image.Image, t: float, alpha: float) -> None:
    if alpha <= 0:
        return
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(28):
        phase = (i * 0.137 + t * 0.72) % 1
        x = 270 + i * 19 + phase * 60
        y = 585 + math.sin(i * 1.7 + t * 4) * 46 + phase * 45
        r = 1.6 + (i % 4) * 0.45
        d.ellipse((x - r, y - r, x + r, y + r), fill=(236, 205, 128, int(160 * alpha * (1 - phase * 0.45))))
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(0.25)))


def draw_frame(i: int, card: Image.Image) -> None:
    t = i / FPS
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))

    a = between(t, 0.18, 2.18)
    rounded_panel(canvas, (42, 764, 610, 958), a * 0.62)
    draw_text_block(canvas, "prompts\naren't cool.", (70, 790), 62, a, max_width=520)

    a = between(t, 4.45, 8.75)
    rounded_panel(canvas, (780, 742, 1370, 956), a * 0.52)
    draw_text_block(canvas, "AI that\nacts first is.", (812, 768), 62, a, color=BRASS, max_width=510)

    a = between(t, 9.35, 12.05)
    rounded_panel(canvas, (44, 58, 810, 184), a * 0.58)
    draw_text_block(canvas, "you don't need a forensic team.", (74, 78), 44, a, max_width=710, family=SANS_BOLD)

    a = between(t, 12.05, 16.72)
    rounded_panel(canvas, (52, 858, 806, 1006), a * 0.58)
    draw_text_block(canvas, "today's AI waits for you to ask.", (82, 884), 43, a, max_width=690, family=SANS_BOLD)

    # Business card insert. Keep the original card visible on the right; make the Anticipy card appear halfway.
    card_alpha = between(t, 16.86, 17.9)
    if card_alpha:
        p = ease_in_out((t - 16.86) / 0.42)
        half = 0.2 + 0.38 * min(1, p)
        quad = [(250, 588), (852, 612), (842, 787), (260, 756)]
        draw_particles(canvas, t, card_alpha)
        paste_perspective(canvas, card, quad, card_alpha * 0.96, half=half)
        draw_scan_line(canvas, quad, half, card_alpha)
        draw_text_block(canvas, "proactive AI", (904, 610), 32, card_alpha, color=BRASS, family=SANS_BOLD)
        draw_text_block(canvas, "safe part first", (904, 654), 32, card_alpha, family=SANS_BOLD)

    a = between(t, 21.1, 24.95)
    rounded_panel(canvas, (676, 724, 1356, 948), a * 0.52)
    draw_text_block(canvas, "not a chatbot.\nfollow-through.", (710, 752), 56, a, max_width=610)

    a = between(t, 26.72, 32.55)
    rounded_panel(canvas, (48, 706, 740, 1010), a * 0.72)
    draw_text_block(canvas, "drop the\nprompt.", (84, 735), 70, a, color=CREAM, max_width=610)
    draw_text_block(canvas, "just Anticipy.", (84, 896), 42, a, color=BRASS, max_width=560, family=SANS_BOLD)
    if t > 29.55:
        b = between(t, 29.55, 32.55)
        draw_text_block(canvas, "it's cleaner.", (84, 948), 33, b, family=SANS_BOLD)

    canvas.save(FRAMES / f"{i:04d}.png")


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)
    card = make_card()
    card.save(ASSETS / "anticipy-card-generated.png")
    for i in range(TOTAL):
        draw_frame(i, card)
        if i % 100 == 0:
            print(f"frame {i}/{TOTAL}")

    run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(FRAMES / "%04d.png"),
            "-c:v",
            "qtrle",
            str(OUT_OVERLAY),
        ]
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(SOURCE),
            "-i",
            str(OUT_OVERLAY),
            "-filter_complex",
            "[0:v][1:v]overlay=0:0:format=auto[v]",
            "-map",
            "[v]",
            "-map",
            "0:a",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "16",
            "-preset",
            "slow",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(OUT_VIDEO),
        ]
    )


if __name__ == "__main__":
    main()
