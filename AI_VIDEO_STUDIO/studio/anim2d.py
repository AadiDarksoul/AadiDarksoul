"""Cinematic 2D scene renderer (CPU, multi-process).

Scene spec (dict / JSON):
  width, height, fps, duration, seed
  location: preset name (backgrounds.LOCATIONS) or list of layer specs
  camera:  [{t, x, y, zoom, ease}] keyframes (+ "shake": amplitude px)
  actors:  [{character: sheet, ground_y, scale, keys:[{t, x, action, facing, expression}],
             speech:[{t, cues:[rhubarb cues]}], depth}]
  lighting: {ambient, tint, vignette, flicker, lightning:[t...], lights:[{follow|x,y, radius, color, intensity}]}
  fx: {grain, rain, chromatic, letterbox, dust}
  texts: [{text, t0, t1, size, y, color}]
"""
import hashlib
import json
import math
import os
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import backgrounds
from .character import CYCLE_LENGTH, Puppet
from .lipsync import shape_at
from .media import FrameWriter

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
FONT_SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def ease(u, kind="inout"):
    u = min(1.0, max(0.0, u))
    if kind == "linear":
        return u
    if kind == "in":
        return u * u
    if kind == "out":
        return 1 - (1 - u) ** 2
    return u * u * (3 - 2 * u)


def interp_keys(keys, t, field, default=0.0):
    ks = [k for k in keys if field in k]
    if not ks:
        return default
    if t <= ks[0]["t"]:
        return ks[0][field]
    for a, b in zip(ks, ks[1:]):
        if a["t"] <= t <= b["t"]:
            u = (t - a["t"]) / max(1e-6, b["t"] - a["t"])
            return a[field] + (b[field] - a[field]) * ease(u, b.get("ease", "inout"))
    return ks[-1][field]


def step_key(keys, t, field, default):
    v = default
    for k in keys:
        if k["t"] <= t and field in k:
            v = k[field]
    return v


def font(size, sans=False):
    try:
        return ImageFont.truetype(FONT_SANS if sans else FONT, size)
    except OSError:
        return ImageFont.load_default()


class SceneRenderer:
    def __init__(self, spec, cache_dir=None):
        self.spec = spec
        self.W, self.H = spec.get("width", 1920), spec.get("height", 1080)
        self.fps = spec.get("fps", 24)
        self.dur = spec["duration"]
        self.seed = spec.get("seed", 0)
        self.cam = spec.get("camera") or [{"t": 0, "x": 0, "y": 0, "zoom": 1}]
        self.cache = cache_dir
        loc = spec.get("location", "haunted_exterior")
        layers = backgrounds.LOCATIONS[loc] if isinstance(loc, str) else loc
        for L in layers:
            L.setdefault("depth", 1.0)
        self.layers = [self._build_layer(L, i) for i, L in enumerate(layers)]
        self.actors = []
        for a in spec.get("actors", []):
            a = dict(a)
            a["puppet"] = Puppet(a["character"])
            a["keys"] = sorted(a.get("keys", [{"t": 0, "x": self.W / 2}]), key=lambda k: k["t"])
            self.actors.append(a)
        lt = spec.get("lighting", {})
        self.light = lt
        yy, xx = np.mgrid[0:self.H // 4, 0:self.W // 4]
        self._grid = (xx * 4.0, yy * 4.0)
        cx, cy = self.W / 2, self.H / 2
        r = np.sqrt(((xx * 4 - cx) / cx) ** 2 + ((yy * 4 - cy) / cy) ** 2)
        self._vig = np.clip(1 - lt.get("vignette", 0.6) * np.clip(r - 0.35, 0, None) ** 1.5, 0, 1)
        rng = np.random.default_rng(self.seed + 99)
        self._grain = [rng.normal(0, 1, (self.H // 2, self.W // 2)).astype(np.float32) for _ in range(6)]

    # -------------------------------------------------------------------------------- layers
    def _cam_range(self, axis):
        vals = [k.get(axis, 0) for k in self.cam]
        return min(vals), max(vals)

    def _build_layer(self, L, idx):
        d = L["depth"]
        x0, x1 = self._cam_range("x")
        y0, y1 = self._cam_range("y")
        mx, my = int(self.W * 0.35), int(self.H * 0.25)
        drift = abs(L.get("drift", 0)) * self.dur
        w = int((x1 - x0) * d + self.W + 2 * mx + drift)
        h = int((y1 - y0) * d + self.H + 2 * my)
        key = hashlib.md5(json.dumps([L, w, h, self.seed + idx, self.H], sort_keys=True).encode()).hexdigest()[:16]
        img = None
        path = os.path.join(self.cache, f"layer_{key}.png") if self.cache else None
        if path and os.path.exists(path):
            img = Image.open(path).convert("RGBA")
        if img is None:
            rng = np.random.default_rng(self.seed * 1000 + idx + int(L.get("seed", 0)))
            pyrng = rng  # painters accept numpy rng
            spec = dict(L)
            # painters use fractions of *screen* height; shift by margin so screen y maps correctly
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            core = backgrounds.PAINTERS[L["type"]](w, self.H, spec, pyrng)
            canvas.alpha_composite(core, (0, int(my - y0 * d)))
            if L["type"] in ("sky", "interior", "ground"):  # extend fills above/below
                top = core.crop((0, 0, w, 1)).resize((w, int(my - y0 * d) + 1))
                canvas.alpha_composite(top, (0, 0))
                bot_h = h - (int(my - y0 * d) + self.H)
                if bot_h > 0:
                    canvas.alpha_composite(core.crop((0, self.H - 1, w, self.H)).resize((w, bot_h)), (0, h - bot_h))
            img = canvas
            if path:
                os.makedirs(self.cache, exist_ok=True)
                img.save(path)
        return {"spec": L, "img": img, "ox": int(self.W * 0.35 - x0 * d), "oy": int(self.H * 0.25 - y0 * d)}

    # -------------------------------------------------------------------------------- camera
    def camera(self, t):
        x = interp_keys(self.cam, t, "x", 0.0)
        y = interp_keys(self.cam, t, "y", 0.0)
        z = interp_keys(self.cam, t, "zoom", 1.0)
        sh = self.spec.get("camera_shake", 0) + step_key(self.cam, t, "shake", 0)
        if sh:
            x += sh * (math.sin(t * 13.1) * 0.6 + math.sin(t * 29.7 + 1) * 0.4)
            y += sh * (math.sin(t * 17.3 + 2) * 0.6 + math.sin(t * 23.9) * 0.4)
        return x, y, max(0.5, z)

    # -------------------------------------------------------------------------------- actors
    def actor_state(self, a, t):
        keys = a["keys"]
        x = interp_keys(keys, t, "x", self.W / 2)
        action = step_key(keys, t, "action", "idle")
        facing = step_key(keys, t, "facing", 1)
        expr = step_key(keys, t, "expression", "neutral")
        dist = 0.0
        prev = keys[0].get("x", x)
        for k in keys[1:]:
            if k["t"] <= t:
                dist += abs(k.get("x", prev) - prev)
                prev = k.get("x", prev)
            else:
                break
        dist += abs(x - prev)
        H = a["puppet"].H * a.get("scale", 1.0)
        cyc = CYCLE_LENGTH.get(action)
        phase = (dist / (H * cyc)) % 1.0 if cyc else 0.0
        if action in ("walk", "run", "sneak") and abs(interp_keys(keys, t + 0.05, "x", x) - x) < 0.05:
            action = "idle"  # arrived: stop the cycle so feet don't paddle in place
        mouth = "X"
        for sp in a.get("speech", []):
            m = shape_at(sp["cues"], t - sp["t"])
            if m != "X":
                mouth = m
        blink_period = 3.7 + (hash(a["character"].get("id", "")) % 7) * 0.3
        blink = (t % blink_period) < 0.12
        return dict(x=x, action=action, facing=facing, expression=expr, phase=phase, mouth=mouth, blink=blink)

    # -------------------------------------------------------------------------------- frame
    def render(self, fi):
        t = fi / self.fps
        W, H = self.W, self.H
        cx, cy, z = self.camera(t)
        vw, vh = W / z, H / z
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        actors_drawn = False
        anchors = {}
        for L in self.layers:
            d = L["spec"]["depth"]
            if d > 1.0 and not actors_drawn:
                anchors = self._draw_actors(frame, t, cx, cy, z)
                actors_drawn = True
            v = L["spec"].get("drift", 0)
            doff = (abs(v) * self.dur - v * t) if v > 0 else (-v * t)  # stays within the extra width
            x0 = L["ox"] + cx * d + W / 2 - vw / 2 + doff
            y0 = L["oy"] + cy * d + H / 2 - vh / 2
            crop = L["img"].resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + vw, y0 + vh))
            frame.alpha_composite(crop)
        if not actors_drawn:
            anchors = self._draw_actors(frame, t, cx, cy, z)
        arr = np.asarray(frame.convert("RGB"), np.float32) / 255.0
        arr = self._lighting(arr, t, anchors)
        arr = self._fx(arr, t, fi)
        out = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGB")
        self._texts(out, t)
        lb = self.spec.get("fx", {}).get("letterbox", 0)
        if lb:
            bar = int(H * lb)
            dr = ImageDraw.Draw(out)
            dr.rectangle([0, 0, W, bar], fill=(0, 0, 0))
            dr.rectangle([0, H - bar, W, H], fill=(0, 0, 0))
        return out

    def _draw_actors(self, frame, t, cx, cy, z):
        W, H = self.W, self.H
        vx0, vy0 = cx + W / 2 - W / z / 2, cy + H / 2 - H / z / 2
        anchors = {}
        for a in sorted(self.actors, key=lambda a: a.get("depth", 1.0)):
            st = self.actor_state(a, t)
            sc = a.get("scale", 1.0) * z
            img, (fx, fy), anc = a["puppet"].draw(st["action"], t, st["phase"], st["facing"], st["expression"],
                                                st["mouth"], st["blink"], sc)
            gx = (st["x"] - vx0) * z
            gy = (a.get("ground_y", H * 0.87) - vy0) * z
            px, py = int(gx - fx), int(gy - fy)
            # contact shadow
            sh = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(sh)
            rw = a["puppet"].H * 0.18 * sc
            sd.ellipse([gx - rw, gy - rw * 0.12, gx + rw, gy + rw * 0.12], fill=(0, 0, 0, 110))
            frame.alpha_composite(sh)
            frame.alpha_composite(img, (px, py)) if 0 <= px and 0 <= py else frame.paste(img, (px, py), img)
            aid = a["character"].get("id", "actor")
            for k, (axp, ayp) in anc.items():
                anchors[f"{aid}.{k}"] = (px + axp, py + ayp)
            anchors[aid] = (gx, gy - a["puppet"].H * sc * 0.6)
        return anchors

    def _lighting(self, arr, t, anchors):
        lt = self.light
        amb = lt.get("ambient", 0.6)
        fl = lt.get("flicker", 0)
        if fl:
            n = math.sin(t * 7.3) * 0.5 + math.sin(t * 17.1) * 0.3 + math.sin(t * 41.7) * 0.2
            amb *= 1 - fl * (0.5 + 0.5 * n)
        gx, gy = self._grid
        light = np.full(gx.shape, amb, np.float32)[..., None] * np.ones(3, np.float32)
        for Ls in lt.get("lights", []):
            if "follow" in Ls:
                if Ls["follow"] not in anchors:
                    continue
                lx, ly = anchors[Ls["follow"]]
                lx += Ls.get("offset", [0, 0])[0]
                ly += Ls.get("offset", [0, 0])[1]
            else:
                lx, ly = Ls.get("x", 0.5) * self.W, Ls.get("y", 0.5) * self.H
            inten = Ls.get("intensity", 0.8) * (1 - Ls.get("flicker", 0) * (0.5 + 0.5 * math.sin(t * 23 + lx)))
            r2 = ((gx - lx) ** 2 + (gy - ly) ** 2) / (Ls.get("radius", 400) ** 2)
            fall = (np.exp(-r2 * 2.2) * inten).astype(np.float32)
            light += fall[..., None] * np.array(Ls.get("color", [1.0, 0.8, 0.55]), np.float32)
        for lt0 in lt.get("lightning", []):
            dt = t - lt0
            if 0 <= dt < 0.6:
                flash = math.exp(-dt * 9) * (1.0 if (dt < 0.06 or 0.12 < dt < 0.2) else 0.45)
                light += flash * 1.6 * np.array([0.8, 0.9, 1.1], np.float32)
        light *= self._vig[..., None]
        tint = np.array(lt.get("tint", [0.85, 0.92, 1.1]), np.float32)
        light = light * tint
        big = np.asarray(Image.fromarray((np.clip(light / 3.0, 0, 1) * 255).astype(np.uint8), "RGB")
                         .resize((self.W, self.H), Image.BILINEAR), np.float32) / 255.0 * 3.0
        return arr * big

    def _fx(self, arr, t, fi):
        fx = self.spec.get("fx", {})
        if fx.get("rain"):
            ov = Image.new("L", (self.W, self.H), 0)
            d = ImageDraw.Draw(ov)
            rng = np.random.default_rng(fi)
            for _ in range(int(500 * fx["rain"])):
                x, y = rng.uniform(-100, self.W), rng.uniform(0, self.H)
                d.line([x, y, x + 12, y + 45], fill=int(rng.uniform(60, 140)), width=1)
            arr = arr + (np.asarray(ov, np.float32) / 255.0)[..., None] * np.array([0.7, 0.75, 0.85])
        if fx.get("chromatic"):
            s = int(fx["chromatic"])
            arr[..., 0] = np.roll(arr[..., 0], s, axis=1)
            arr[..., 2] = np.roll(arr[..., 2], -s, axis=1)
        g = fx.get("grain", 0.05)
        if g:
            tile = self._grain[fi % len(self._grain)]
            big = np.repeat(np.repeat(tile, 2, axis=0), 2, axis=1)[: self.H, : self.W]
            arr = arr + big[..., None] * g * 0.5
        return arr

    def _texts(self, img, t):
        for tx in self.spec.get("texts", []):
            if not (tx["t0"] <= t <= tx["t1"]):
                continue
            fade = min(1, (t - tx["t0"]) / 0.6, (tx["t1"] - t) / 0.6)
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            f = font(tx.get("size", 96), tx.get("sans", False))
            bb = d.textbbox((0, 0), tx["text"], font=f)
            x = (self.W - (bb[2] - bb[0])) / 2
            y = tx.get("y", 0.42) * self.H
            col = tuple(int(tx.get("color", "#d8c8b0").lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
            d.text((x, y), tx["text"], font=f, fill=col + (int(255 * fade),))
            base = img.convert("RGBA")
            base.alpha_composite(layer)
            img.paste(base.convert("RGB"))


_R = None


def _init(spec, cache):
    global _R
    _R = SceneRenderer(spec, cache)


def _frame(fi):
    return _R.render(fi).tobytes()


def render_scene(spec, out_mp4, cache_dir=None, workers=None, preview_scale=None, crf=18):
    """Render a scene spec to a silent H.264 MP4. preview_scale (e.g. 0.5) for fast drafts."""
    spec = json.loads(json.dumps(spec))
    if preview_scale:
        spec["width"] = int(spec.get("width", 1920) * preview_scale) // 2 * 2
        spec["height"] = int(spec.get("height", 1080) * preview_scale) // 2 * 2
        sc = preview_scale
        for k in spec.get("camera", []):
            k["x"] = k.get("x", 0) * sc
            k["y"] = k.get("y", 0) * sc
        for a in spec.get("actors", []):
            a["character"] = dict(a["character"], height=a["character"].get("height", 430) * sc)
            if "ground_y" in a:
                a["ground_y"] *= sc
            for k in a.get("keys", []):
                if "x" in k:
                    k["x"] *= sc
        for tx in spec.get("texts", []):
            tx["size"] = int(tx.get("size", 96) * sc)
    W, H, fps = spec.get("width", 1920), spec.get("height", 1080), spec.get("fps", 24)
    n = int(round(spec["duration"] * fps))
    cache_dir = cache_dir or os.path.join(os.path.dirname(os.path.abspath(out_mp4)), ".layer_cache")
    SceneRenderer(spec, cache_dir)  # warm the layer cache once in the parent process
    writer = FrameWriter(out_mp4, W, H, fps, crf=crf)
    workers = workers or max(1, (os.cpu_count() or 2))
    with Pool(workers, initializer=_init, initargs=(spec, cache_dir)) as pool:
        for buf in pool.imap(_frame, range(n), chunksize=4):
            writer.write(buf)
    writer.close()
    return out_mp4


def still(spec, t, path, cache_dir=None, scale=1.0):
    """Render a single frame (used for storyboards and previews)."""
    r = SceneRenderer(spec, cache_dir)
    img = r.render(int(t * r.fps))
    if scale != 1.0:
        img = img.resize((int(r.W * scale), int(r.H * scale)), Image.LANCZOS)
    img.save(path)
    return path
