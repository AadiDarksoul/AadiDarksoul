"""Procedural multilayer parallax backgrounds (deterministic per seed => consistent locations).

A location is a list of layer specs; each layer is rendered once to an RGBA PIL image and cached.
Layer depth: 0 = infinitely far (static), 1 = actor plane, >1 = foreground (moves faster).
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def hexrgb(c, a=255):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def _noise1d(n, seed, octaves=4, scale=0.004):
    rng = np.random.default_rng(seed)
    x = np.arange(n)
    out = np.zeros(n)
    for o in range(octaves):
        f = scale * 2 ** o
        pts = rng.uniform(-1, 1, int(n * f) + 3)
        out += np.interp(x * f, np.arange(len(pts)), pts) / 2 ** o
    return out


# --------------------------------------------------------------------------------- layer painters
def sky(w, h, s, rng):
    top, bottom = hexrgb(s.get("top", "#05070f")), hexrgb(s.get("bottom", "#1c2333"))
    g = np.linspace(0, 1, h)[:, None, None]
    arr = (np.array(top[:3]) * (1 - g) + np.array(bottom[:3]) * g).astype(np.uint8)
    img = Image.fromarray(np.repeat(arr, w, axis=1), "RGB").convert("RGBA")
    d = ImageDraw.Draw(img)
    for _ in range(int(s.get("stars", 260) * w / 1920)):
        x, y = rng.uniform(0, w), rng.uniform(0, h * 0.6)
        b = int(rng.uniform(90, 230))
        r = rng.choice([0.6, 0.8, 1.2])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(b, b, b + 15 if b < 240 else b, 255))
    if s.get("clouds", 0.5):
        cl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        cd = ImageDraw.Draw(cl)
        col = hexrgb(s.get("cloud_color", "#2a3142"))
        for _ in range(int(14 * w / 1920 * s.get("clouds", 0.5) * 2)):
            cx, cy = rng.uniform(0, w), rng.uniform(h * 0.05, h * 0.45)
            for _k in range(6):
                rx, ry = rng.uniform(80, 220), rng.uniform(20, 50)
                ox, oy = rng.uniform(-150, 150), rng.uniform(-20, 20)
                cd.ellipse([cx + ox - rx, cy + oy - ry, cx + ox + rx, cy + oy + ry], fill=col[:3] + (120,))
        img = Image.alpha_composite(img, cl.filter(ImageFilter.GaussianBlur(18)))
    return img


def moon(w, h, s, rng):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x, y, r = s.get("x", 0.72) * w, s.get("y", 0.2) * h, s.get("r", 70)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    col = hexrgb(s.get("color", "#e8e4d0"))
    gd.ellipse([x - r * 3, y - r * 3, x + r * 3, y + r * 3], fill=col[:3] + (60,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(r)))
    d = ImageDraw.Draw(img)
    d.ellipse([x - r, y - r, x + r, y + r], fill=col)
    for _ in range(7):  # craters
        cx, cy, cr = x + rng.uniform(-r * .6, r * .6), y + rng.uniform(-r * .6, r * .6), rng.uniform(5, r * .25)
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=tuple(int(c * 0.88) for c in col[:3]) + (255,))
    return img


def hills(w, h, s, rng):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    base = s.get("y", 0.62) * h
    amp = s.get("amp", 90)
    nz = _noise1d(w, rng.integers(1 << 30), 4, s.get("scale", 0.002))
    pts = [(0, h)] + [(x, base - amp * nz[x]) for x in range(0, w, 4)] + [(w, h)]
    d.polygon(pts, fill=hexrgb(s.get("color", "#111725")))
    return img


def _branch(d, x, y, ang, length, width, depth, rng, col):
    if depth == 0 or length < 4:
        return
    x2, y2 = x + math.cos(ang) * length, y - math.sin(ang) * length
    d.line([x, y, x2, y2], fill=col, width=max(1, int(width)))
    for _ in range(2 if depth > 1 else 3):
        _branch(d, x2, y2, ang + rng.uniform(-0.75, 0.75), length * rng.uniform(0.6, 0.78),
                width * 0.66, depth - 1, rng, col)


def trees(w, h, s, rng):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = hexrgb(s.get("color", "#090b12"))
    base = s.get("y", 0.8) * h
    size = s.get("size", 1.0)
    x = rng.uniform(0, 120)
    while x < w:
        tall = rng.uniform(220, 420) * size
        tw = rng.uniform(10, 22) * size
        d.polygon([(x - tw, base + 10), (x + tw, base + 10), (x + tw * 0.35, base - tall * 0.55),
                   (x - tw * 0.35, base - tall * 0.55)], fill=col)
        _branch(d, x, base - tall * 0.5, math.pi / 2 + rng.uniform(-0.2, 0.2), tall * 0.45, tw * 0.8, 6, rng, col)
        x += rng.uniform(140, 380) * size * s.get("spacing", 1.0)
    return img


def house(w, h, s, rng):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = hexrgb(s.get("color", "#0b0d15"))
    win = hexrgb(s.get("window", "#e8a33c"))
    cx, base, sc = s.get("x", 0.5) * w, s.get("y", 0.8) * h, s.get("scale", 1.0)
    bw, bh = 520 * sc, 300 * sc
    x0 = cx - bw / 2
    d.rectangle([x0, base - bh, x0 + bw, base], fill=col)
    d.polygon([(x0 - 30 * sc, base - bh), (cx, base - bh - 200 * sc), (x0 + bw + 30 * sc, base - bh)], fill=col)
    tx = x0 + bw * 0.78
    d.rectangle([tx, base - bh - 260 * sc, tx + 90 * sc, base - bh + 10], fill=col)  # tower
    d.polygon([(tx - 15 * sc, base - bh - 260 * sc), (tx + 45 * sc, base - bh - 400 * sc),
               (tx + 105 * sc, base - bh - 260 * sc)], fill=col)
    d.rectangle([x0 + 60 * sc, base - bh - 230 * sc, x0 + 95 * sc, base - bh - 100 * sc], fill=col)  # chimney
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    lit = s.get("lit", [1, 0, 1, 0, 0, 1, 1])
    k = 0
    for row in range(2):
        for colx in range(3):
            wx = x0 + 70 * sc + colx * 160 * sc
            wy = base - bh + 40 * sc + row * 130 * sc
            on = lit[k % len(lit)]
            k += 1
            fill = win if on else (20, 24, 34, 255)
            d.rectangle([wx, wy, wx + 70 * sc, wy + 90 * sc], fill=fill)
            d.line([wx + 35 * sc, wy, wx + 35 * sc, wy + 90 * sc], fill=col, width=max(2, int(5 * sc)))
            d.line([wx, wy + 45 * sc, wx + 70 * sc, wy + 45 * sc], fill=col, width=max(2, int(5 * sc)))
            if on:
                gd.rectangle([wx - 20, wy - 20, wx + 70 * sc + 20, wy + 90 * sc + 20], fill=win[:3] + (110,))
    d.rectangle([tx + 25 * sc, base - bh - 200 * sc, tx + 65 * sc, base - bh - 140 * sc], fill=win)
    gd.rectangle([tx + 5, base - bh - 220 * sc, tx + 85 * sc, base - bh - 120 * sc], fill=win[:3] + (90,))
    d.rectangle([cx - 40 * sc, base - 130 * sc, cx + 40 * sc, base], fill=(25, 18, 14, 255))
    return Image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(25)), img)


def graveyard(w, h, s, rng):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = hexrgb(s.get("color", "#1a1e29"))
    base = s.get("y", 0.86) * h
    x = rng.uniform(0, 200)
    while x < w:
        tw, th = rng.uniform(40, 70), rng.uniform(60, 120)
        tilt = rng.uniform(-8, 8)
        d.rectangle([x, base - th + tw / 2, x + tw, base], fill=col)
        d.ellipse([x, base - th, x + tw, base - th + tw], fill=col)
        if rng.random() < 0.3:
            d.rectangle([x + tw / 2 - 5, base - th - 50, x + tw / 2 + 5, base - th + 10], fill=col)
            d.rectangle([x + tw / 2 - 25, base - th - 30, x + tw / 2 + 25, base - th - 20], fill=col)
        x += rng.uniform(150, 400) + tilt
    # iron fence
    fy = base - 20
    fc = hexrgb(s.get("fence", "#07080c"))
    d.line([0, fy - 90, w, fy - 90], fill=fc, width=5)
    d.line([0, fy - 20, w, fy - 20], fill=fc, width=5)
    for fx in range(0, w, 34):
        d.line([fx, fy, fx, fy - 120], fill=fc, width=5)
        d.polygon([(fx - 7, fy - 120), (fx + 7, fy - 120), (fx, fy - 138)], fill=fc)
    return img


def ground(w, h, s, rng):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    y0 = int(s.get("y", 0.84) * h)
    top, bot = hexrgb(s.get("top", "#141a17")), hexrgb(s.get("bottom", "#060807"))
    g = np.linspace(0, 1, h - y0)[:, None, None]
    arr = (np.array(top[:3]) * (1 - g) + np.array(bot[:3]) * g).astype(np.uint8)
    band = Image.fromarray(np.repeat(arr, w, axis=1), "RGB").convert("RGBA")
    img.paste(band, (0, y0))
    d = ImageDraw.Draw(img)
    gc = hexrgb(s.get("grass", "#0c110e"))
    for _ in range(int(w / 6)):
        x = rng.uniform(0, w)
        hh = rng.uniform(6, 22)
        d.line([x, y0 + 2, x + rng.uniform(-6, 6), y0 - hh], fill=gc, width=2)
    if s.get("path"):
        pc = hexrgb(s.get("path_color", "#1f1d1a"))
        d.rectangle([0, y0 + 10, w, y0 + 60], fill=pc)
    return img


def fog(w, h, s, rng):
    y0, y1 = s.get("y0", 0.55) * h, s.get("y1", 1.0) * h
    small = (max(8, w // 16), max(8, h // 16))
    nz = rng.random((small[1], small[0])).astype(np.float32)
    img = Image.fromarray((nz * 255).astype(np.uint8), "L").resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(40))
    a = np.asarray(img, np.float32) / 255.0
    ys = np.arange(h)[:, None]
    mask = np.clip((ys - y0) / max(1, (y1 - y0) * 0.4), 0, 1) * np.clip((y1 - ys) / max(1, (y1 - y0) * 0.2), 0, 1)
    alpha = (np.clip(a * 1.6 - 0.3, 0, 1) * mask * 255 * s.get("density", 0.5)).astype(np.uint8)
    col = hexrgb(s.get("color", "#9aa6b8"))
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., :3] = col[:3]
    rgba[..., 3] = alpha
    return Image.fromarray(rgba, "RGBA")


def interior(w, h, s, rng):
    """Victorian hallway back wall with wallpaper, wainscot, doors, frames and a moonlit window."""
    img = Image.new("RGBA", (w, h), hexrgb(s.get("wall", "#2a2420")))
    d = ImageDraw.Draw(img)
    stripe = hexrgb(s.get("stripe", "#241f1b"))
    for x in range(0, w, 60):
        d.rectangle([x, 0, x + 28, h], fill=stripe)
    for x in range(30, w, 120):
        for y in range(40, int(h * 0.6), 110):
            d.ellipse([x - 8, y - 12, x + 8, y + 12], outline=hexrgb("#3a2f27"), width=2)
    floor_y = int(s.get("floor_y", 0.84) * h)
    wy = int(h * 0.6)
    d.rectangle([0, wy, w, floor_y], fill=hexrgb(s.get("wainscot", "#1c1410")))
    for x in range(0, w, 140):
        d.rectangle([x + 15, wy + 20, x + 125, floor_y - 20], outline=hexrgb("#2b1f17"), width=3)
    d.rectangle([0, wy - 8, w, wy + 4], fill=hexrgb("#120d0a"))
    fl = hexrgb(s.get("floor", "#191210"))
    d.rectangle([0, floor_y, w, h], fill=fl)
    for y in range(floor_y, h, 18):
        d.line([0, y, w, y], fill=hexrgb("#0f0a08"), width=2)
    beam = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(beam)
    for i, x in enumerate(np.arange(w * 0.12, w, s.get("door_spacing", 900))):
        if i % 2 == 0:
            d.rectangle([x, h * 0.22, x + 190, floor_y], fill=hexrgb("#0f0a08"))
            d.rectangle([x + 15, h * 0.24, x + 175, floor_y], fill=hexrgb(s.get("door", "#2e1d14")))
            for py in (0.3, 0.55):
                d.rectangle([x + 35, h * py, x + 155, h * py + 120], outline=hexrgb("#1b110b"), width=4)
            d.ellipse([x + 145, h * 0.55, x + 160, h * 0.55 + 15], fill=hexrgb("#8a6a3a"))
        else:
            d.rectangle([x, h * 0.18, x + 220, h * 0.52], fill=hexrgb("#0d1018"))
            d.rectangle([x + 10, h * 0.19, x + 210, h * 0.51], fill=hexrgb("#4a5a78"))
            d.line([x + 110, h * 0.19, x + 110, h * 0.51], fill=hexrgb("#0d1018"), width=8)
            d.line([x + 10, h * 0.35, x + 210, h * 0.35], fill=hexrgb("#0d1018"), width=8)
            bd.polygon([(x + 10, h * 0.19), (x + 210, h * 0.19), (x + 420, h), (x - 60, h)], fill=(140, 160, 200, 40))
            fx = x + 420
            d.rectangle([fx, h * 0.25, fx + 130, h * 0.45], fill=hexrgb("#4a3520"))
            d.rectangle([fx + 12, h * 0.25 + 12, fx + 118, h * 0.45 - 12], fill=hexrgb("#1a1714"))
            d.ellipse([fx + 45, h * 0.29, fx + 85, h * 0.36], fill=hexrgb("#2c2722"))
    return Image.alpha_composite(img, beam.filter(ImageFilter.GaussianBlur(30)))


def pillars(w, h, s, rng):
    """Foreground framing elements (dark pillars / branches) for depth."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = hexrgb(s.get("color", "#030304"))
    x = rng.uniform(100, 400)
    while x < w:
        pw = rng.uniform(70, 140)
        d.rectangle([x, 0, x + pw, h], fill=col)
        x += rng.uniform(1100, 1800)
    return img.filter(ImageFilter.GaussianBlur(s.get("blur", 6)))


PAINTERS = {"sky": sky, "moon": moon, "hills": hills, "trees": trees, "house": house,
            "graveyard": graveyard, "ground": ground, "fog": fog, "interior": interior, "pillars": pillars}

# Reusable location presets (location bible). Depth ordering = draw order.
LOCATIONS = {
    "haunted_exterior": [
        {"type": "sky", "depth": 0.0}, {"type": "moon", "depth": 0.02},
        {"type": "hills", "depth": 0.15, "y": 0.6, "color": "#10151f"},
        {"type": "trees", "depth": 0.35, "y": 0.72, "size": 0.6, "color": "#0c0f18", "spacing": 0.7},
        {"type": "house", "depth": 0.55, "x": 0.62, "y": 0.8, "scale": 0.9},
        {"type": "fog", "depth": 0.6, "y0": 0.6, "y1": 0.86, "density": 0.35, "drift": 12},
        {"type": "graveyard", "depth": 0.85, "y": 0.86},
        {"type": "ground", "depth": 1.0, "y": 0.84, "path": True},
        {"type": "fog", "depth": 1.35, "y0": 0.75, "y1": 1.0, "density": 0.45, "drift": 30, "front": True},
    ],
    "forest_path": [
        {"type": "sky", "depth": 0.0, "top": "#03050a", "bottom": "#121a22"},
        {"type": "moon", "depth": 0.02, "x": 0.25, "r": 55},
        {"type": "trees", "depth": 0.25, "y": 0.75, "size": 0.55, "color": "#0e131b", "spacing": 0.4},
        {"type": "trees", "depth": 0.55, "y": 0.8, "size": 0.85, "color": "#080a10", "spacing": 0.6},
        {"type": "fog", "depth": 0.6, "y0": 0.5, "y1": 0.85, "density": 0.4, "drift": 10},
        {"type": "ground", "depth": 1.0, "y": 0.84, "path": True, "top": "#10140f"},
        {"type": "trees", "depth": 1.5, "y": 1.05, "size": 1.6, "color": "#020203", "spacing": 2.2, "front": True},
        {"type": "fog", "depth": 1.3, "y0": 0.78, "y1": 1.0, "density": 0.5, "drift": 25, "front": True},
    ],
    "interior_hallway": [
        {"type": "interior", "depth": 0.92, "floor_y": 0.84},
        {"type": "fog", "depth": 0.95, "y0": 0.3, "y1": 1.0, "density": 0.15, "drift": 6, "color": "#8090a8"},
        {"type": "pillars", "depth": 1.5, "front": True},
    ],
}
