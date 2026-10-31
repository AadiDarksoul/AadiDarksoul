#!/usr/bin/env python3
"""Style test: opening hook of "What If You Could Hear 10,000x Better?"

Original characters and art (Kai: orange hoodie + cyan headphones). Renders:
  out/hook_SDR.mp4   H.264, BT.709, 8-bit (what most phone viewers see)
  out/hook_HDR10.mp4 HEVC Main10, BT.2020 + PQ, HDR10 static metadata
Emissive elements (sound rings, neon HUD, title) live on a separate glow layer so the
HDR master can push them to ~800 nits while diffuse white stays at 203 nits (BT.2408).

Run: /opt/ai_video_studio/venv/bin/python render_hook.py [--preview]
"""
import math
import os
import subprocess
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "../../..")))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

from studio import mix, synth, tts  # noqa: E402
from studio.audio_io import load  # noqa: E402
from studio.config import SAMPLE_RATE as SR, require  # noqa: E402
from studio.media import describe, ffmpeg  # noqa: E402

PREVIEW = "--preview" in sys.argv
W, H = (960, 540) if PREVIEW else (1920, 1080)
FPS = 24
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
F_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
F_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

# ------------------------------------------------------------------------------ palette (vivid)
C = {
    "kai": (255, 122, 0), "headphones": (0, 229, 255), "man": (123, 47, 247), "skin": (22, 26, 48),
    "wall_top": (15, 181, 174), "wall_bot": (29, 63, 191), "floor": (255, 138, 61), "table": (224, 40, 125),
    "sky_top": (58, 12, 163), "sky_mid": (247, 37, 133), "sky_low": (255, 158, 0),
    "heart": (255, 40, 80), "voice": (255, 255, 255), "machine": (255, 214, 10), "nature": (60, 160, 255),
    "title_bg": (30, 10, 90),
}
ROOM_COLS = [(255, 190, 11), (251, 86, 7), (255, 0, 110), (131, 56, 236), (58, 134, 255), (6, 214, 160),
             (17, 138, 178), (239, 71, 111), (255, 209, 102), (0, 187, 249)]

# ------------------------------------------------------------------------------------ timeline
T = {"cafe": 1.4, "man_line": 1.6, "vo1": 2.6, "pull": 6.0, "pull_end": 8.0, "isolate": 8.3,
     "whisper": 8.5, "kai_close": 9.0, "vo3": 9.2}  # silence/title filled in after TTS


def ease(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def lerp(a, b, u):
    return a + (b - a) * u


def lerp_box(a, b, u):
    return tuple(lerp(x, y, u) for x, y in zip(a, b))


# --------------------------------------------------------------------------------- world (city)
WW, WH = 5760, 3240
GROUND = 3000
CAFE = (1150, 2150, 2700, GROUND)
TABLE_Y = 2800
MAN = (1700, TABLE_Y)
KAI = (2150, TABLE_Y)
DOOR = (3420, 2420, 3600, GROUND)
SOURCES = []  # (x, y, kind, appear_t)


def vgrad(w, h, top, bot, mid=None):
    g = np.linspace(0, 1, h)[:, None]
    if mid is None:
        arr = np.array(top) * (1 - g) + np.array(bot) * g
    else:
        a = np.clip(g * 2, 0, 1)
        b = np.clip(g * 2 - 1, 0, 1)
        arr = np.where(g < 0.5, np.array(top) * (1 - a) + np.array(mid) * a, np.array(mid) * (1 - b) + np.array(bot) * b)
    arr = np.repeat(arr[:, None, :], w, axis=1).astype(np.uint8)
    return Image.fromarray(arr, "RGB").convert("RGBA")


def tiny_person(d, x, y, col, s=1.0):
    d.ellipse([x - 16 * s, y - 120 * s, x + 16 * s, y - 88 * s], fill=C["skin"])
    d.rounded_rectangle([x - 18 * s, y - 86 * s, x + 18 * s, y - 30 * s], radius=10 * s, fill=col)
    d.line([x - 8 * s, y - 32 * s, x - 10 * s, y], fill=C["skin"], width=int(7 * s))
    d.line([x + 8 * s, y - 32 * s, x + 10 * s, y], fill=C["skin"], width=int(7 * s))


def build_world():
    rng = np.random.default_rng(7)
    img = vgrad(WW, WH, C["sky_top"], C["sky_low"], C["sky_mid"])
    d = ImageDraw.Draw(img)
    # stars + moon
    for _ in range(400):
        x, y = rng.uniform(0, WW), rng.uniform(0, 1200)
        r = rng.choice([1.5, 2, 3])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 240, 255))
    glow = Image.new("RGBA", (WW, WH), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([4500, 250, 5100, 850], fill=(255, 220, 255, 140))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(120)))
    d.ellipse([4650, 400, 4950, 700], fill=(255, 245, 230))
    # far skyline
    x = 0
    while x < WW:
        bw, bh = rng.uniform(150, 350), rng.uniform(500, 1300)
        d.rectangle([x, GROUND - bh, x + bw, GROUND], fill=(70, 20, 140))
        x += bw + rng.uniform(10, 60)
    # cut-away buildings (front)
    buildings = [(-50, 1050, 1300), (1100, 2750, 900), (2800, 4000, 1150), (4050, 4900, 700), (4950, 5800, 1400)]
    for bi, (x0, x1, top) in enumerate(buildings):
        d.rectangle([x0, top, x1, GROUND], fill=(18, 14, 52))
        fy = GROUND
        floor = 0
        while fy - 850 >= top - 10:
            ry0 = fy - 850
            # rooms in this floor
            rx = x0 + 30
            widths = [x1 - x0 - 60] if (bi in (1, 2) and floor == 0) else []
            if not widths:
                n = 2 if (x1 - x0) > 900 else 1
                widths = [(x1 - x0 - 30 * (n + 1)) / n] * n
            for wi, rw in enumerate(widths):
                col = ROOM_COLS[int(rng.integers(len(ROOM_COLS)))]
                room = (rx, ry0 + 30, rx + rw, fy - 20)
                if not (bi == 1 and floor == 0) and not (bi == 2 and floor == 0):
                    rimg = vgrad(int(rw), int(room[3] - room[1]), col, tuple(int(c * 0.55) for c in col))
                    img.alpha_composite(rimg, (int(rx), int(room[1])))
                    # a lamp + people
                    d.rectangle([rx + rw * 0.5 - 4, room[1], rx + rw * 0.5 + 4, room[1] + 120], fill=(30, 20, 40))
                    d.ellipse([rx + rw * 0.5 - 40, room[1] + 110, rx + rw * 0.5 + 40, room[1] + 150], fill=(255, 250, 210))
                    for p in range(int(rng.integers(0, 3))):
                        px = rx + rng.uniform(100, rw - 100)
                        tiny_person(d, px, room[3], ROOM_COLS[int(rng.integers(len(ROOM_COLS)))], 1.6)
                        kind = "heart" if rng.random() < 0.6 else "voice"
                        SOURCES.append((px, room[3] - 150, kind, 7.0 + rng.uniform(0, 1.0)))
                    if rng.random() < 0.25:
                        SOURCES.append((rx + rw * 0.3, room[3] - 60, "machine", 6.6 + rng.uniform(0, 1.2)))
                rx += rw + 30
            fy -= 870
            floor += 1
    # café interior (building 1, ground floor)
    x0, y0, x1, y1 = CAFE
    img.alpha_composite(vgrad(x1 - x0, y1 - y0, C["wall_top"], C["wall_bot"]), (x0, y0))
    d.rectangle([x0, 2900, x1, y1], fill=C["floor"])
    for fx in range(x0, x1, 80):
        d.line([fx, 2900, fx - 40, y1], fill=(230, 110, 40), width=4)
    # classroom: chalkboard, teacher, wall clock, pendant lamps
    d.rounded_rectangle([1230, 2210, 2050, 2560], radius=10, fill=(120, 60, 20))
    d.rectangle([1250, 2230, 2030, 2540], fill=(22, 128, 90))
    for i, (cx, cy) in enumerate([(1330, 2300), (1480, 2380), (1640, 2290), (1800, 2420), (1900, 2320)]):
        d.line([cx, cy, cx + 90, cy + 10 + 8 * i], fill=(230, 255, 240), width=5)
    d.ellipse([1500, 2440, 1580, 2520], outline=(230, 255, 240), width=5)
    tiny_person(d, 2460, 2900, (255, 0, 110), 3.2)  # teacher at the front
    d.ellipse([2470, 2260, 2590, 2380], fill=(255, 255, 255), outline=(30, 20, 60), width=10)  # clock
    d.line([2530, 2320, 2530, 2280], fill=(30, 20, 60), width=6)
    d.line([2530, 2320, 2565, 2330], fill=(30, 20, 60), width=6)
    for lx in (1500, 1920, 2340):
        d.line([lx, y0, lx, 2200], fill=(20, 20, 30), width=6)
        d.chord([lx - 70, 2160, lx + 70, 2240], 180, 360, fill=(255, 214, 10))
    # table
    d.rounded_rectangle([1540, TABLE_Y - 10, 2310, TABLE_Y + 30], radius=12, fill=C["table"])
    d.rectangle([1900, TABLE_Y + 30, 1940, 2900], fill=(150, 20, 80))
    d.polygon([(1800, TABLE_Y - 12), (1880, TABLE_Y - 12), (1870, TABLE_Y - 40), (1810, TABLE_Y - 40)], fill=(255, 255, 255))  # papers
    d.polygon([(1990, TABLE_Y - 12), (2070, TABLE_Y - 12), (2060, TABLE_Y - 40), (2000, TABLE_Y - 40)], fill=(255, 255, 255))
    SOURCES.append((2530, 2320, "machine", 6.3))  # ticking clock
    SOURCES.append((2460, 2560, "voice", 6.5))    # teacher
    SOURCES.append((1400, 2380, "nature", 7.3))   # fly near window
    # whisper source room (building 2 ground floor): plain hallway + door
    bx0, by0, bx1, by1 = 2830, 2150, 3970, GROUND
    img.alpha_composite(vgrad(bx1 - bx0, by1 - by0, (6, 214, 160), (17, 90, 120)), (bx0, by0))
    d.rectangle([3150, by0, 3180, by1], fill=(18, 14, 52))  # inner wall (the third wall)
    d.rectangle(DOOR, fill=(120, 40, 20))
    d.rectangle([DOOR[0] + 15, DOOR[1] + 15, DOOR[2] - 15, DOOR[3]], fill=(200, 80, 30))
    d.ellipse([DOOR[2] - 45, 2700, DOOR[2] - 25, 2720], fill=(255, 214, 10))
    SOURCES.append((4400, 1900, "machine", 6.8))  # phone buzzing
    # street
    d.rectangle([0, GROUND, WW, WH], fill=(40, 10, 70))
    for sx in range(0, WW, 260):
        d.rectangle([sx, GROUND + 110, sx + 140, GROUND + 125], fill=(255, 214, 10))
    return img


# ------------------------------------------------------------------------------- characters
def seated(d, x, y, s, hoodie, facing, wide=False, headphones=False, smile=False, look=0.0):
    """Original seated stick character drawn in screen space (x,y = point on table under chest)."""
    hx, hy, r = x, y - 270 * s, 58 * s
    # hood + torso
    d.rounded_rectangle([x - 52 * s, y - 205 * s, x + 52 * s, y + 10 * s], radius=28 * s, fill=hoodie)
    d.chord([x - 70 * s, y - 250 * s, x + 70 * s, y - 150 * s], 180, 360, fill=tuple(int(c * 0.8) for c in hoodie))
    # arm on table
    d.line([x + facing * 20 * s, y - 170 * s, x + facing * 95 * s, y - 40 * s, x + facing * 150 * s, y - 25 * s],
           fill=hoodie, width=int(30 * s), joint="curve")
    d.ellipse([x + facing * 150 * s - 16 * s, y - 41 * s, x + facing * 150 * s + 16 * s, y - 9 * s], fill=C["skin"])
    # head
    d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=C["skin"])
    if headphones:  # cyan cups resting around the neck
        d.arc([hx - 70 * s, hy + 20 * s, hx + 70 * s, hy + 130 * s], 20, 160, fill=C["headphones"], width=int(12 * s))
        for side in (-1, 1):
            cx = hx + side * 64 * s
            d.rounded_rectangle([cx - 18 * s, hy + 50 * s, cx + 18 * s, hy + 100 * s], radius=10 * s, fill=C["headphones"])
        # hair tuft (Kai's silhouette mark)
        d.polygon([(hx - 20 * s, hy - r + 6 * s), (hx + 5 * s, hy - r - 30 * s), (hx + 15 * s, hy - r + 4 * s)], fill=C["skin"])
    # eyes
    ew, eh = (16 * s, 22 * s) if not wide else (21 * s, 30 * s)
    for k, ox in enumerate((-14, 22)):
        ex = hx + facing * ox * s + facing * 6 * s
        ey = hy - 8 * s
        d.ellipse([ex - ew, ey - eh, ex + ew, ey + eh], fill=(255, 255, 255))
        pr = 8 * s if not wide else 6 * s
        px = ex + facing * (5 + look * 8) * s
        d.ellipse([px - pr, ey - pr, px + pr, ey + pr], fill=(10, 10, 20))
    if smile:
        d.arc([hx + facing * 4 * s - 22 * s, hy + 12 * s, hx + facing * 4 * s + 22 * s, hy + 36 * s], 20, 160,
              fill=(255, 255, 255), width=int(5 * s))
    elif wide:
        d.ellipse([hx + facing * 8 * s - 8 * s, hy + 22 * s, hx + facing * 8 * s + 8 * s, hy + 40 * s], fill=(255, 255, 255))


def rings(d, cx, cy, col, t, speed, maxr, n=4, width=6, alpha=1.0, inward=False):
    for i in range(n):
        ph = (t * speed + i / n) % 1.0
        r = (1 - ph) * maxr if inward else ph * maxr
        a = (ph if inward else (1 - ph)) ** 1.3 * 255 * alpha
        if r < 2 or a < 3:
            continue
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col + (int(a),), width=max(2, int(width)))


# --------------------------------------------------------------------------------- renderer
_WORLD = None
_SRC = None


def init():
    global _WORLD, _SRC
    _WORLD = build_world()
    _SRC = list(SOURCES)


def to_screen(box, x, y):
    s = W / (box[2] - box[0])
    return (x - box[0]) * s, (y - box[1]) * s, s


def cafe_camera(t):
    start = (1500, 2350, 2340, 2822.5)
    push = (1700 - 280, 2640 - 157.5, 1700 + 280, 2640 + 157.5)
    wide = (0, 0, WW, WH)
    if t < T["vo1"] + 0.4:
        return start
    if t < T["pull"]:
        return lerp_box(start, push, ease((t - T["vo1"] - 0.4) / (T["pull"] - T["vo1"] - 0.4)))
    if t < T["pull_end"]:
        u = (t - T["pull"]) / (T["pull_end"] - T["pull"])
        return lerp_box(push, wide, ease(u) ** 0.8)
    u = ease((t - T["pull_end"]) / 1.5)
    return lerp_box(wide, (300, 900, 4300, 3150), u * 0.4)


def frame(fi):
    t = fi / FPS
    base = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    k = W / 1920
    if t < T["cafe"]:  # ---------------- S1: ear close-up
        z = 1 + 0.05 * t / T["cafe"]
        bg = vgrad(W, H, (255, 0, 110), (255, 158, 0))
        bd = ImageDraw.Draw(bg)
        rng = np.random.default_rng(3)
        for _ in range(28):  # café bokeh
            x, y, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(30, 110) * k
            bd.ellipse([x - r, y - r, x + r, y + r], fill=tuple(int(c) for c in ROOM_COLS[int(rng.integers(10))]) + (140,))
        base = bg.filter(ImageFilter.GaussianBlur(18 * k))
        d = ImageDraw.Draw(base)
        hx, hy, hr = W * 0.78, H * 0.55, 620 * k * z
        d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=C["skin"])
        ex, ey = hx - hr * 0.86, hy - 20 * k
        d.ellipse([ex - 70 * k * z, ey - 110 * k * z, ex + 70 * k * z, ey + 110 * k * z], fill=(40, 46, 80))
        gd.arc([ex - 70 * k * z, ey - 110 * k * z, ex + 70 * k * z, ey + 110 * k * z], 90, 300, fill=C["headphones"] + (255,), width=int(8 * k))
        gd.arc([ex - 35 * k * z, ey - 60 * k * z, ex + 35 * k * z, ey + 60 * k * z], 100, 280, fill=C["headphones"] + (200,), width=int(5 * k))
        rings(gd, ex, ey, C["heart"], t, 112 / 60, 900 * k, n=5, width=10 * k, inward=True)
        hud(gd, k, t, "♥ HEART RATE  112 ↑", C["heart"])
    elif t < T["kai_close"]:  # ------- S2/S3: café → pull back to city cross-section
        box = cafe_camera(t)
        base = _WORLD.resize((W, H), Image.BILINEAR, box=box)
        blur = max(0.0, 1 - (box[2] - box[0]) / 2400) * 7 * k  # shallow depth of field in close-ups
        if blur > 0.3:
            base = base.filter(ImageFilter.GaussianBlur(blur))
        chars = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(chars)
        mx, my, s = to_screen(box, *MAN)
        seated(d, mx, my, s, C["man"], 1, smile=t < T["vo1"] + 1.5)
        kx, ky, _ = to_screen(box, *KAI)
        seated(d, kx, ky, s, C["kai"], -1, headphones=True)
        rim_light(chars, glow, (255, 190, 120), s)
        base.alpha_composite(chars)
        d = ImageDraw.Draw(base)
        # man's lying heart
        cx, cy, _ = to_screen(box, MAN[0], MAN[1] - 120)
        hb = 112 / 60 * (1.25 if t > T["vo1"] + 1.8 else 1.0)
        fade_iso = 1 - ease((t - T["isolate"]) / 0.5) if t > T["isolate"] else 1
        rings(gd, cx, cy, C["heart"], t, hb, 260 * s, n=4, width=7 * s, alpha=fade_iso)
        if T["vo1"] + 0.6 < t < T["pull"] + 0.3:
            a = min(1, (t - T["vo1"] - 0.6) / 0.3)
            f = ImageFont.truetype(F_MONO, int(26 * k))
            gd.text((cx + 70 * s, cy - 60 * s), "SOURCE: HEART · 112 BPM", font=f, fill=C["heart"] + (int(230 * a),))
        if t > T["pull"]:
            for (sx, sy, kind, t0) in _SRC:
                if t < t0:
                    continue
                px, py, _ = to_screen(box, sx, sy)
                pop = min(1, (t - t0) / 0.25)
                alpha = pop * fade_iso
                sp = {"heart": 1.3, "voice": 0.9, "machine": 2.2, "nature": 3.0}[kind]
                rings(gd, px, py, C[kind], t + sx * 0.001, sp, 220 * s, n=3, width=6 * s, alpha=alpha)
        if t > T["isolate"]:  # the whisper behind the door
            px, py, _ = to_screen(box, (DOOR[0] + DOOR[2]) / 2, 2650)
            a = ease((t - T["isolate"]) / 0.3)
            rings(gd, px, py, C["voice"], t, 0.7, 1500 * s, n=5, width=8 * s, alpha=a)
        if t < T["pull"]:
            hud(gd, k, t, "♥ 112 BPM ↑", C["heart"])
        else:
            hud(gd, k, t, f"SOURCES: {min(99, int(8 + (t - T['pull']) * 30))}", C["headphones"])
    elif t < T["silence"]:  # ---------- S4: Kai close-up, turns toward the whisper
        u = ease((t - T["kai_close"]) / (T["silence"] - T["kai_close"]))
        bw = lerp(760, 640, u)
        box = (KAI[0] + 40 - bw / 2, 2560 - bw * 9 / 32, KAI[0] + 40 + bw / 2, 2560 + bw * 9 / 32)
        base = _WORLD.resize((W, H), Image.BILINEAR, box=box).filter(ImageFilter.GaussianBlur(9 * k))
        dim = Image.new("RGBA", (W, H), (10, 0, 40, 90))
        base.alpha_composite(dim)
        kx, ky, s = to_screen(box, *KAI)
        turned = t > T["kai_close"] + 0.35
        jolt = 6 * s * math.exp(-max(0, t - T["kai_close"] - 0.35) * 12) if turned else 0
        chars = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        seated(ImageDraw.Draw(chars), kx, ky - jolt, s, C["kai"], 1 if turned else -1, wide=turned, headphones=True, look=0.6)
        rim_light(chars, glow, (200, 240, 255), s)
        base.alpha_composite(chars)
        px, py, _ = to_screen(box, 3510, 2650)
        rings(gd, px, py, C["voice"], t, 0.7, 1500 * s, n=5, width=8 * s)
        hud(gd, k, t, "VOICE · 3 WALLS · \"KAI\"", C["voice"])
    elif t < T["title"]:  # ------------ black silence
        pass
    else:  # ------------------------------ title card
        tt = t - T["title"]
        base = vgrad(W, H, C["title_bg"], (90, 10, 120))
        d = ImageDraw.Draw(base)
        f1 = ImageFont.truetype(F_BOLD, int(92 * k))
        f2 = ImageFont.truetype(F_BOLD, int(150 * k))
        a = ease(tt / 0.35)
        l1, l2 = "WHAT IF YOU COULD HEAR", "10,000× BETTER?"
        b1, b2 = d.textbbox((0, 0), l1, font=f1), d.textbbox((0, 0), l2, font=f2)
        y1 = H * 0.30
        x1 = (W - b1[2]) / 2
        d.text((x1, y1), l1, font=f1, fill=(255, 255, 255, int(255 * a)))
        sc = 1 + 0.06 * (1 - ease(tt / 0.5))
        gd.text(((W - b2[2] * sc) / 2 + (b2[2] * (sc - 1)) / 2, y1 + 130 * k), l2, font=f2,
                fill=C["headphones"] + (int(255 * a),))
        yb = d.textbbox((x1, y1), "WHAT IF ", font=f1)
        yw = d.textbbox((0, 0), "YOU", font=f1)
        ox = yb[2] + yw[2] * 0.55
        oy = y1 + yw[3] * 0.6
        r = tt * 900 * k
        gd.ellipse([ox - r, oy - r, ox + r, oy + r], outline=C["kai"] + (int(255 * max(0, 1 - tt / 1.6)),), width=int(10 * k))
        if tt > 0.4:
            rings(gd, ox, oy, C["kai"], tt, 0.6, 700 * k, n=3, width=5 * k, alpha=0.5)
    return composite(base, glow)


def rim_light(chars, glow, col, s):
    """Thin glowing outline around characters (adds depth; goes to the HDR emissive layer)."""
    a = chars.getchannel("A")
    size = max(3, int(5 * s) | 1)
    edge = Image.eval(Image.fromarray(np.clip(np.asarray(a.filter(ImageFilter.MaxFilter(size)), np.int16)
                                              - np.asarray(a, np.int16), 0, 255).astype(np.uint8)), lambda v: int(v * 0.55))
    layer = Image.new("RGBA", chars.size, col + (0,))
    layer.putalpha(edge)
    glow.alpha_composite(layer)


def hud(gd, k, t, text, col):
    f = ImageFont.truetype(F_MONO, int(30 * k))
    blink = 1.0 if int(t * 3) % 6 else 0.6
    gd.rounded_rectangle([40 * k, 36 * k, 40 * k + 14 * k * len(text) + 80 * k, 96 * k], radius=12 * k,
                         outline=col + (int(200 * blink),), width=int(3 * k))
    gd.text((60 * k, 46 * k), text, font=f, fill=col + (int(255 * blink),))


# ----------------------------------------------------------------------------- colour science
def srgb_to_lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


M709_2020 = np.array([[0.6274, 0.3293, 0.0433], [0.0691, 0.9195, 0.0114], [0.0164, 0.0880, 0.8956]], np.float32)


def pq(nits):
    m1, m2, c1, c2, c3 = 0.1593017578125, 78.84375, 0.8359375, 18.8515625, 18.6875
    y = np.clip(nits / 10000.0, 0, 1) ** m1
    return ((c1 + c2 * y) / (1 + c3 * y)) ** m2


def composite(base, glow):
    b = np.asarray(base.convert("RGB"), np.float32) / 255.0
    g = np.asarray(glow, np.float32) / 255.0
    ga = g[..., :3] * g[..., 3:4]
    bloom = np.asarray(glow.filter(ImageFilter.GaussianBlur(14 * W / 1920)), np.float32) / 255.0
    ba = bloom[..., :3] * bloom[..., 3:4]
    emissive = ga + ba * 1.6
    # SDR: screen-add emissive on top of base, slight vibrance boost
    sdr = 1 - (1 - b) * (1 - np.clip(emissive, 0, 1))
    sdr8 = (np.clip(sdr, 0, 1) * 255 + 0.5).astype(np.uint8)
    # HDR10: diffuse at 203 nits, emissive highlights up to ~850 nits, BT.709 -> BT.2020, PQ, 16-bit
    lin = srgb_to_lin(b) * 203.0 + srgb_to_lin(np.clip(emissive, 0, 1.5)) * 650.0
    lin2020 = lin @ M709_2020.T
    hdr16 = (pq(lin2020) * 65535 + 0.5).astype(np.uint16)
    return sdr8.tobytes(), hdr16.tobytes()


# -------------------------------------------------------------------------------------- audio
def build_audio(path):
    tmp = os.path.join(OUT, "tmp")
    os.makedirs(tmp, exist_ok=True)
    def speak(text, path, voice):
        if os.path.exists(path):  # reuse: Piper is stochastic, cached lines keep picture/sound in sync
            from studio.media import duration
            return path, duration(path), "cached"
        return tts.speak(text, path, voice)

    man, d_man, _ = speak("It wasn't me.", os.path.join(tmp, "man.wav"), {"preset": "male", "pitch": 2.5})
    vo1, d1, e1 = speak("He says it wasn't him. His heart just told you... it was.", os.path.join(tmp, "vo1.wav"), "narrator")
    wsp, dw, _ = speak("Kai?", os.path.join(tmp, "whisper.wav"), {"preset": "whisper", "gain_db": 2})
    vo3, d3, _ = speak("And through three walls... someone just whispered your name.", os.path.join(tmp, "vo3.wav"), "narrator")
    T["vo3"] = max(T["vo3"], T["vo1"] + d1 + 0.2)
    T["silence"] = T["vo3"] + d3 + 0.25
    T["title"] = T["silence"] + 0.8
    dur = T["title"] + 3.6
    print(f"[audio] engine={e1} vo1={d1:.2f}s vo3={d3:.2f}s total={dur:.2f}s")
    tl = mix.Timeline(dur)
    rng = np.random.default_rng(1)
    # the man's irregular, lying heartbeat (Kai-POV, close)
    hb = synth.heartbeat(T["pull"] + 2.0, bpm=112)
    tl.add(hb, 0.0, "sfx", gain_db=-2, fade_out=1.5)
    # classroom murmur (muffled)
    n = int((T["isolate"] - T["cafe"]) * SR)
    walla = synth.band(synth.noise(n, "pink", rng), 250, 2500, 2) * (0.6 + 0.4 * np.sin(np.arange(n) / SR * 2.1))
    tl.add(synth.band(walla, None, 3000, 2) * 0.25, T["cafe"], "ambience", fade_in=0.2, fade_out=0.4)
    tl.add(man, T["man_line"], "dialogue", pan=-0.25)
    tl.add(vo1, T["vo1"], "dialogue")
    # pull-back: whoosh + layered city sources popping in with 3D panning
    tl.add(synth.whoosh(1.8, rng), T["pull"] - 0.2, "sfx", gain_db=-4)
    t_ax = np.arange(int(2.2 * SR)) / SR
    tick = np.zeros(len(t_ax), np.float32)
    for i in range(0, len(t_ax), SR // 2):  # clock: tick every 0.5 s
        L = int(0.012 * SR)
        tick[i:i + L] += synth.band(synth.noise(L, "white", rng), 2000, 7000, 2) * np.exp(-np.arange(L) / (0.002 * SR))
    tl.add(tick, 6.3, "sfx", gain_db=-8, pan=0.5, fade_out=0.4)
    buzz = np.sign(np.sin(2 * np.pi * 150 * t_ax)) * (np.sin(2 * np.pi * 4 * t_ax) > 0) * 0.15
    tl.add(synth.band(buzz.astype(np.float32), 100, 2000, 2), 6.8, "sfx", gain_db=-12, pan=0.8, fade_out=0.3)
    fly = np.sin(2 * np.pi * (210 + 25 * np.sin(2 * np.pi * 3 * t_ax)) * t_ax) * 0.2
    flyst = np.stack([fly * (1 - t_ax / t_ax[-1]), fly * (t_ax / t_ax[-1])], axis=1).astype(np.float32)
    tl.add(flyst, 7.3, "sfx", gain_db=-14, fade_in=0.2, fade_out=0.3)
    tl.add(synth.whispers(1.2, rng), 7.0, "ambience", gain_db=-12, fade_out=0.3)
    # isolate: everything ducks, the whisper (close, right side)
    tl.add(wsp, T["whisper"], "dialogue", gain_db=-3, pan=0.65)
    # ---- BGM: soft but engaging, original score (stems automated per section)
    from studio.music import soft_engaging_stems
    stems = soft_engaging_stems(dur, bpm=112, key="D", seed=11)  # 112 bpm locks to the heartbeat
    tax = np.arange(int(dur * SR)) / SR

    def env(points):  # piecewise-linear gain (dB) over time; -90 = off
        ts, dbs = zip(*points)
        return (10 ** (np.interp(tax, ts, dbs) / 20)).astype(np.float32)[:, None]

    off = -90
    si, ti, iso, pu = T["silence"], T["title"], T["isolate"], T["pull"]
    automation = {
        "pad":      [(0, -14), (1.4, -8), (pu, -7), (iso, -6), (si - 0.05, -8), (si, off), (ti, off), (ti + 0.05, -5), (dur, -6)],
        "piano":    [(0, off), (0.3, -12), (1.4, -6), (pu, -5), (iso, -14), (iso + 0.6, off), (ti + 0.3, off), (ti + 0.6, -6), (dur, -6)],
        "piano_hi": [(0, off), (pu - 0.2, off), (pu + 0.4, -9), (iso, -12), (iso + 0.4, off), (dur, off)],
        "pulse":    [(0, off), (1.4, -10), (pu, -8), (iso, -12), (si - 0.05, -14), (si, off), (ti + 0.6, off), (ti + 1.0, -10), (dur, -10)],
        "shaker":   [(0, off), (1.6, -14), (pu, -10), (iso, off), (ti + 1.0, off), (ti + 1.4, -14), (dur, -14)],
    }
    bgm = sum(stems[k] * env(v) for k, v in automation.items())
    tl.add(bgm, 0.0, "music", gain_db=0)
    tl.add(vo3, T["vo3"], "dialogue")
    # title: clean high tone + headphone "pressure drop"
    tt = np.arange(int(3.0 * SR)) / SR
    tone = (np.sin(2 * np.pi * 1760 * tt) * 0.5 + np.sin(2 * np.pi * 880 * tt) * 0.3) * np.exp(-tt * 1.4) * np.minimum(1, tt / 0.005)
    tl.add(synth.reverb(tone.astype(np.float32), 2.5, 0.4), T["title"], "sfx", gain_db=-6)
    drop = synth.band(synth.noise(int(1.2 * SR), "brown", rng), None, 300, 2) * np.linspace(1, 0, int(1.2 * SR)) ** 2
    tl.add(drop * 0.8, T["title"] + 2.1, "sfx", gain_db=-6)
    tl.render(path, duck_db=-7, bus_gain={"music": -7.0}, lufs=-14.0, true_peak=-1.0)
    # enforce the digital silence window exactly
    a = load(path)
    s0, s1 = int(T["silence"] * SR), int(T["title"] * SR)
    a[s0:s1] = 0
    from studio.audio_io import save
    save(path, a)
    return dur


# --------------------------------------------------------------------------------------- main
def remux_audio_only():
    wav = os.path.join(OUT, "hook_mix.wav")
    build_audio(wav)
    for name in ("hook_SDR.mp4", "hook_HDR10.mp4"):
        src, tmp = os.path.join(OUT, name), os.path.join(OUT, "tmp_" + name)
        ffmpeg("-i", src, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
               "-ar", "48000", "-ac", "2", "-movflags", "+faststart", "-shortest", tmp)
        os.replace(tmp, src)
        print(describe(src))
    print("[audio] integrated LUFS / true peak:", mix.measure_lufs(os.path.join(OUT, "hook_SDR.mp4")))


def main():
    if "--audio-only" in sys.argv:
        return remux_audio_only()
    wav = os.path.join(OUT, "hook_mix.wav")
    dur = build_audio(wav)
    n = int(round(dur * FPS))
    tag = "_preview" if PREVIEW else ""
    sdr_v, hdr_v = os.path.join(OUT, f"sdr_video{tag}.mp4"), os.path.join(OUT, f"hdr_video{tag}.mp4")
    ff = [require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y"]
    sdr_p = subprocess.Popen(ff + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                                   "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
                                   "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high",
                                   "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", sdr_v],
                             stdin=subprocess.PIPE)
    x265 = ("colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:range=limited:hdr10=1:repeat-headers=1:"
            "master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1):max-cll=850,250:log-level=error")
    hdr_p = subprocess.Popen(ff + ["-f", "rawvideo", "-pix_fmt", "rgb48le", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                                   "-vf", "scale=out_color_matrix=bt2020nc:out_range=tv,format=yuv420p10le",
                                   "-c:v", "libx265", "-preset", "medium", "-crf", "16", "-x265-params", x265,
                                   "-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc",
                                   "-tag:v", "hvc1", hdr_v], stdin=subprocess.PIPE)
    with Pool(os.cpu_count(), initializer=init) as pool:
        for i, (s8, h16) in enumerate(pool.imap(frame, range(n), chunksize=3)):
            sdr_p.stdin.write(s8)
            hdr_p.stdin.write(h16)
            if i % 48 == 0:
                print(f"[video] frame {i}/{n}", flush=True)
    for p in (sdr_p, hdr_p):
        p.stdin.close()
        assert p.wait() == 0
    sdr_out, hdr_out = os.path.join(OUT, f"hook_SDR{tag}.mp4"), os.path.join(OUT, f"hook_HDR10{tag}.mp4")
    ffmpeg("-i", sdr_v, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
           "-ar", "48000", "-ac", "2", "-movflags", "+faststart", "-shortest", sdr_out)
    ffmpeg("-i", hdr_v, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
           "-ar", "48000", "-ac", "2", "-movflags", "+faststart", "-shortest", hdr_out)
    os.remove(sdr_v)
    os.remove(hdr_v)
    for p in (sdr_out, hdr_out):
        print(describe(p))
    print("[audio] integrated LUFS / true peak:", mix.measure_lufs(sdr_out))


if __name__ == "__main__":
    main()
