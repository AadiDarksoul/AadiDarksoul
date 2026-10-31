"""2D cut-out puppet characters with a bone rig, procedural cycles, expressions and visemes.

A character sheet (JSON/dict) fully defines appearance; the same sheet always renders identically,
which is how identity, outfit and proportions stay consistent across every shot of a film.
"""
import math

from PIL import Image, ImageDraw, ImageFilter

from .lipsync import MOUTH

SS = 2  # supersampling factor for anti-aliased edges

DEFAULT_SHEET = {
    "id": "hero", "name": "Hero", "height": 430, "build": 1.0, "head_ratio": 0.17,
    "skin": "#d8b49a", "hair": "#2a1a12", "hair_style": "long", "eyes": "#3a5a40",
    "top": "#3b4a5a", "outfit": "coat", "bottom": "#24242c", "shoes": "#101010",
    "accessory": None, "style": "human",
}

EXPRESSIONS = {
    #             eye_open, pupil, brow_angle, brow_raise, mouth_curve
    "neutral":   (1.0, 0.45, 0.0, 0.0, 0.0),
    "happy":     (0.8, 0.45, -0.1, 0.05, 0.6),
    "scared":    (1.35, 0.28, 0.35, 0.25, -0.4),
    "terrified": (1.5, 0.22, 0.45, 0.35, -0.7),
    "angry":     (0.75, 0.5, -0.5, -0.1, -0.5),
    "sad":       (0.8, 0.5, 0.5, 0.1, -0.6),
    "surprised": (1.4, 0.35, 0.2, 0.35, 0.0),
    "suspicious": (0.55, 0.5, -0.25, -0.05, -0.2),
    "evil":      (0.6, 0.35, -0.6, -0.1, 0.8),
}


def rgb(c, k=1.0):
    c = c.lstrip("#")
    return tuple(max(0, min(255, int(int(c[i:i + 2], 16) * k))) for i in (0, 2, 4)) + (255,)


def merge_sheet(sheet):
    s = dict(DEFAULT_SHEET)
    s.update(sheet or {})
    if s["style"] == "creature":
        s.setdefault("glow", "#ff3b2f")
    return s


# --------------------------------------------------------------------------------------- poses
def pose_for(action, t, phase, rng_seed=0):
    """Return joint angles (radians, 0 = straight down, + = forward) for an action."""
    p = 2 * math.pi * phase
    breathe = math.sin(2 * math.pi * t / 3.6)
    base = dict(lean=0.0, thigh_f=0.05, shin_f=0.02, thigh_b=-0.05, shin_b=-0.07,
                arm_f=0.08 + 0.02 * breathe, fore_f=0.15, arm_b=-0.05, fore_b=0.1,
                head=0.02 * breathe, shake=0.0, torso_scale=1 + 0.008 * breathe)
    if action in ("walk", "sneak"):
        amp, bend = (0.42, 0.85) if action == "walk" else (0.32, 1.1)
        base.update(thigh_f=amp * math.sin(p), thigh_b=amp * math.sin(p + math.pi),
                    arm_f=-0.38 * math.sin(p), arm_b=-0.38 * math.sin(p + math.pi), fore_f=0.3, fore_b=0.3,
                    lean=0.06 if action == "walk" else 0.28)
        base["shin_f"] = base["thigh_f"] - bend * max(0.0, math.cos(p))
        base["shin_b"] = base["thigh_b"] - bend * max(0.0, math.cos(p + math.pi))
        if action == "sneak":
            base["fore_f"], base["fore_b"] = 1.2, 1.0
    elif action == "run":
        base.update(thigh_f=0.8 * math.sin(p), thigh_b=0.8 * math.sin(p + math.pi), lean=0.28,
                    arm_f=-0.9 * math.sin(p), arm_b=-0.9 * math.sin(p + math.pi), fore_f=1.5, fore_b=1.5)
        base["shin_f"] = base["thigh_f"] - 1.6 * max(0.0, math.cos(p))
        base["shin_b"] = base["thigh_b"] - 1.6 * max(0.0, math.cos(p + math.pi))
    elif action in ("scared", "cower"):
        sh = math.sin(t * 47) * 0.04 + math.sin(t * 31) * 0.03
        base.update(lean=-0.12, arm_f=2.3 + sh, fore_f=1.4, arm_b=2.0 - sh, fore_b=1.5,
                    thigh_f=0.25, shin_f=-0.15, thigh_b=0.1, shin_b=-0.3, shake=3.0, head=-0.08)
    elif action == "point":
        base.update(arm_f=1.55, fore_f=0.0)
    elif action == "reach":  # creature / zombie
        base.update(arm_f=1.45 + 0.05 * breathe, fore_f=0.1, arm_b=1.35, fore_b=0.15, lean=0.12)
    elif action == "float":
        base.update(thigh_f=0.15, shin_f=0.05, thigh_b=0.05, shin_b=-0.05, arm_f=0.5 + 0.1 * breathe,
                    arm_b=0.35, fore_f=0.4, fore_b=0.3)
    elif action == "look_back":
        base.update(head=-0.25, lean=-0.05)
    elif action == "talk":
        base.update(arm_f=0.35 + 0.15 * math.sin(t * 2.3), fore_f=0.9 + 0.2 * math.sin(t * 1.7))
    return base


CYCLE_LENGTH = {"walk": 0.78, "sneak": 0.55, "run": 1.25}  # metres-per-cycle in units of body height


# ----------------------------------------------------------------------------------- rendering
class Puppet:
    def __init__(self, sheet):
        self.s = merge_sheet(sheet)
        H = self.s["height"]
        b = self.s["build"]
        self.H = H
        self.head_r = H * self.s["head_ratio"] / 2
        self.thigh, self.shin = 0.245 * H, 0.235 * H
        self.upper, self.fore = 0.18 * H, 0.17 * H
        self.torso = 0.30 * H
        self.limb_w = 0.055 * H * b
        self.torso_w = 0.15 * H * b
        if self.s["style"] == "creature":
            self.thigh *= 1.15; self.shin *= 1.15; self.upper *= 1.35; self.fore *= 1.35
            self.limb_w *= 0.6; self.torso_w *= 0.75

    def draw(self, action="idle", t=0.0, phase=0.0, facing=1, expression="neutral", mouth="X",
             blink=False, scale=1.0, look=0.0):
        """Render to an RGBA image; returns (image, (feet_x, feet_y) anchor in image, anchors)."""
        s, f = self.s, 1 if facing >= 0 else -1
        k = SS * scale
        W, Hh = int(self.H * 1.3 * k), int(self.H * 1.3 * k)
        img = Image.new("RGBA", (W, Hh), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        P = pose_for(action, t, phase)
        ox, oy = W / 2, Hh - 0.08 * self.H * k

        def seg(x, y, ang, length):
            return x + f * math.sin(ang) * length * k, y + math.cos(ang) * length * k

        hip_y = oy - (self.thigh + self.shin) * k
        hip = (ox, hip_y)
        # grounding: lift body so lowest foot touches the ground line
        def leg_pts(th, sh):
            kx, ky = seg(*hip, th, self.thigh)
            fx, fy = seg(kx, ky, sh, self.shin)
            return (kx, ky), (fx, fy)
        lf = leg_pts(P["thigh_f"], P["shin_f"])
        lb = leg_pts(P["thigh_b"], P["shin_b"])
        drop = oy - max(lf[1][1], lb[1][1])
        if action == "float":
            drop -= (0.12 + 0.03 * math.sin(t * 2)) * self.H * k
        sx = P["shake"] * math.sin(t * 61) * k
        def mv(pt):
            return (pt[0] + sx, pt[1] + drop)
        hip = mv(hip)
        lf = (mv(lf[0]), mv(lf[1]))
        lb = (mv(lb[0]), mv(lb[1]))
        sh_x, sh_y = hip[0] + f * math.sin(P["lean"]) * self.torso * k, hip[1] - math.cos(P["lean"]) * self.torso * k * P["torso_scale"]
        shoulder = (sh_x, sh_y)
        lw = max(2, int(self.limb_w * k))
        creature = s["style"] == "creature"
        top, bottom, skin = rgb(s["top"]), rgb(s["bottom"]), rgb(s["skin"])
        if creature:
            top = bottom = skin = rgb(s.get("body", "#050506"))

        def limb(a, b, c, col, width):
            d.line([a, b], fill=col, width=width)
            d.line([b, c], fill=col, width=width)
            for pt in (a, b, c):
                r = width / 2
                d.ellipse([pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r], fill=col)

        def arm(a1, a2, dark):
            e = seg(*shoulder, a1, self.upper)
            h = seg(*e, a1 + a2, self.fore)  # forearm angle is relative to upper arm
            col = rgb(s["top"], 0.72) if dark else top
            if creature:
                col = top
            limb(shoulder, e, h, col, int(lw * 0.85))
            r = lw * 0.55
            hc = rgb(s["skin"], 0.75 if dark else 1.0) if not creature else top
            d.ellipse([h[0] - r, h[1] - r, h[0] + r, h[1] + r], fill=hc)
            return h

        def leg(pts, dark):
            col = rgb(s["bottom"], 0.72) if dark else bottom
            if creature:
                col = bottom
            limb(hip, pts[0], pts[1], col, lw)
            fx, fy = pts[1]
            shoe = rgb(s["shoes"], 0.8 if dark else 1.0) if not creature else col
            d.ellipse([fx - lw * 0.6 + f * lw * 0.3, fy - lw * 0.45, fx + lw * 0.6 + f * lw * 0.9, fy + lw * 0.35], fill=shoe)

        # back limbs
        hand_b = arm(P["arm_b"], P["fore_b"], True)
        leg(lb, True)
        leg(lf, False)  # legs before torso so coats/dresses overlap the thighs
        # torso / outfit
        tw = self.torso_w * k
        torso_poly = [(shoulder[0] - tw / 2, shoulder[1]), (shoulder[0] + tw / 2, shoulder[1]),
                      (hip[0] + tw * 0.42, hip[1]), (hip[0] - tw * 0.42, hip[1])]
        if s["outfit"] in ("coat", "dress", "robe") and not creature:
            length = {"coat": 0.16, "dress": 0.22, "robe": 0.42}[s["outfit"]] * self.H * k
            flare = tw * (0.7 if s["outfit"] != "robe" else 0.9)
            sway = math.sin(2 * math.pi * phase) * 0.15 * tw
            torso_poly = torso_poly[:2] + [(hip[0] + flare + sway, hip[1] + length),
                                           (hip[0] - flare + sway, hip[1] + length)]
        d.polygon(torso_poly, fill=top)
        if s.get("collar") and not creature:
            d.polygon([(shoulder[0] - tw * .25, shoulder[1]), (shoulder[0] + tw * .25, shoulder[1]),
                       (shoulder[0], shoulder[1] + tw * .5)], fill=rgb(s["collar"]))
        # head
        hr = self.head_r * k
        neck_top = (shoulder[0] + f * math.sin(P["lean"] + P["head"]) * hr * 0.6, shoulder[1] - hr * 0.35)
        d.line([shoulder, neck_top], fill=skin, width=int(lw * 0.7))
        hx = neck_top[0] + f * math.sin(P["head"]) * hr * 0.3
        hy = neck_top[1] - hr * 0.95
        if not creature and s["hair_style"] == "long":
            hc = rgb(s["hair"])
            d.polygon([(hx - f * hr * 1.0, hy - hr * 0.4), (hx + f * hr * 0.2, hy - hr * 0.9),
                       (hx - f * hr * 0.2, hy + hr * 1.9), (hx - f * hr * 1.15, hy + hr * 1.7)], fill=hc)
        d.ellipse([hx - hr * 0.92, hy - hr, hx + hr * 0.92, hy + hr], fill=skin)
        if not creature:
            hc = rgb(s["hair"])
            if s["hair_style"] in ("long", "short", "bob"):
                d.chord([hx - hr * 1.0, hy - hr * 1.12, hx + hr * 1.0, hy + hr * 0.6], 180, 360, fill=hc)
                d.polygon([(hx - f * hr * 0.95, hy - hr * 0.2), (hx - f * hr * 0.2, hy - hr * 0.95),
                           (hx - f * hr * 0.9, hy + hr * (0.9 if s["hair_style"] == "bob" else 0.4))], fill=hc)
            elif s["hair_style"] == "bald":
                pass
            elif s["hair_style"] == "hood":
                d.chord([hx - hr * 1.25, hy - hr * 1.3, hx + hr * 1.25, hy + hr * 1.3], 150, 390, fill=rgb(s["top"], 0.8))
            # face
            self._face(d, hx, hy, hr, f, expression, mouth, blink, look)
        else:
            self._creature_face(img, hx, hy, hr, f)
        hand_f = arm(P["arm_f"], P["fore_f"], False)
        if s.get("accessory") == "lantern":
            lx, ly = hand_f
            d.line([lx, ly, lx, ly + hr * 0.4], fill=(30, 30, 30, 255), width=max(2, int(k * 2)))
            d.rectangle([lx - hr * 0.3, ly + hr * 0.4, lx + hr * 0.3, ly + hr * 1.1], fill=(255, 200, 110, 255),
                        outline=(25, 22, 18, 255), width=max(2, int(k * 3)))
        out = img.resize((max(1, W // SS), max(1, Hh // SS)), Image.LANCZOS)
        anchors = {"hand_f": (hand_f[0] / SS, hand_f[1] / SS), "head": (hx / SS, hy / SS),
                   "hand_b": (hand_b[0] / SS, hand_b[1] / SS)}
        return out, (ox / SS, oy / SS), anchors

    def _face(self, d, hx, hy, hr, f, expression, mouth, blink, look):
        eo, pup, brow_a, brow_r, curve = EXPRESSIONS.get(expression, EXPRESSIONS["neutral"])
        eye_col = rgb(self.s["eyes"])
        for i, (ex, sc) in enumerate(((hx + f * hr * 0.48, 1.0), (hx + f * hr * 0.02, 0.82))):
            ey = hy - hr * 0.08
            ew, eh = hr * 0.2 * sc, hr * 0.24 * sc * eo
            if blink:
                d.line([ex - ew, ey, ex + ew, ey], fill=(30, 20, 18, 255), width=max(2, int(hr * 0.06)))
            else:
                d.ellipse([ex - ew, ey - eh, ex + ew, ey + eh], fill=(240, 236, 228, 255))
                pr = ew * pup * 1.6
                px = ex + f * ew * (0.25 + look * 0.4)
                d.ellipse([px - pr, ey - pr, px + pr, ey + pr], fill=eye_col)
                d.ellipse([px - pr * .45, ey - pr * .45, px + pr * .45, ey + pr * .45], fill=(10, 10, 10, 255))
            by = ey - eh - hr * (0.12 + brow_r * 0.4)
            inner = ex - f * ew * 1.1 if i == 0 else ex + f * ew * 1.1
            outer = ex + f * ew * 1.1 if i == 0 else ex - f * ew * 1.1
            d.line([inner, by - brow_a * hr * 0.18, outer, by + brow_a * hr * 0.18],
                   fill=rgb(self.s["hair"], 0.8), width=max(2, int(hr * 0.08)))
        # nose
        nx = hx + f * hr * 0.88
        d.line([hx + f * hr * 0.62, hy - hr * 0.05, nx, hy + hr * 0.22, hx + f * hr * 0.62, hy + hr * 0.25],
               fill=rgb(self.s["skin"], 0.75), width=max(2, int(hr * 0.06)))
        # mouth (viseme overrides expression shape while speaking)
        op, wd, rnd = MOUTH.get(mouth, MOUTH["X"])
        mx, my = hx + f * hr * 0.38, hy + hr * 0.52
        mw = hr * (0.18 + 0.28 * wd)
        if op < 0.08:
            c = curve * hr * 0.12
            d.line([mx - mw, my - c, mx, my + c * 0.2, mx + mw, my - c], fill=(90, 40, 38, 255),
                   width=max(2, int(hr * 0.07)), joint="curve")
        else:
            mh = hr * 0.32 * op
            d.ellipse([mx - mw, my - mh / 2, mx + mw, my + mh], fill=(55, 18, 20, 255),
                      outline=(110, 50, 48, 255), width=max(1, int(hr * 0.04)))
            if mouth in ("C", "D", "G"):
                d.rectangle([mx - mw * 0.7, my - mh / 2, mx + mw * 0.7, my - mh / 2 + hr * 0.06], fill=(235, 230, 220, 255))

    def _creature_face(self, img, hx, hy, hr, f):
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        col = rgb(self.s.get("glow", "#ff3b2f"))
        for ex in (hx + f * hr * 0.45, hx + f * hr * 0.0):
            ey = hy - hr * 0.1
            gd.ellipse([ex - hr * .45, ey - hr * .3, ex + hr * .45, ey + hr * .3], fill=col[:3] + (150,))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(hr * 0.25)))
        d = ImageDraw.Draw(img)
        for ex in (hx + f * hr * 0.45, hx + f * hr * 0.0):
            ey = hy - hr * 0.1
            d.ellipse([ex - hr * .16, ey - hr * .08, ex + hr * .16, ey + hr * .08], fill=(255, 235, 200, 255))


def turnaround(sheet, path):
    """Character reference sheet: poses x expressions, used to lock identity before animating."""
    pup = Puppet(sheet)
    cells = [("idle", "neutral", 1), ("idle", "neutral", -1), ("walk", "neutral", 1), ("run", "scared", 1),
             ("scared", "terrified", 1), ("talk", "happy", 1), ("idle", "angry", 1), ("idle", "sad", 1)]
    imgs = [pup.draw(a, 0.3, 0.25, fc, e, "C" if a == "talk" else "X")[0] for a, e, fc in cells]
    w, h = imgs[0].size
    sheet_img = Image.new("RGBA", (w * 4, h * 2 + 60), (28, 28, 34, 255))
    d = ImageDraw.Draw(sheet_img)
    for i, (im, (a, e, fc)) in enumerate(zip(imgs, cells)):
        x, y = (i % 4) * w, (i // 4) * h + 60
        sheet_img.alpha_composite(im, (x, y))
        d.text((x + 10, y + 5), f"{a}/{e}", fill=(200, 200, 200, 255))
    d.text((10, 15), f"CHARACTER SHEET: {pup.s['name']} ({pup.s['id']})", fill=(240, 240, 240, 255))
    sheet_img.convert("RGB").save(path)
    return path
