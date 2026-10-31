"""Clip compositing and encoding: frames + timeline.json from tools/marketing/clips.py -> MP4 / GIF /
trailer.

    python tools/marketing/clip_compose.py [--only NAME,...] [--no-trailer] [--no-gif]

Each output frame (1920 x 1080, 30 fps) = the window picture in the shot rect (85 %) + a caption band below it (accent tick, clip title, the caption of the moment, key chips, one-line lockup)
+ the mouse cursor (drawn here: event simulation never moves the OS cursor). Frames are synthesised with Pillow and
piped raw into ffmpeg (no PNG sequence on disk). Motion:

- Speed: timeline time / ``speed`` (content.json clip field, default 1.35), per caption group, so a caption still stays
  >= CAPTION_MIN (1.2 s) on screen (a short group plays slower, never below 1x). Cursor moves stay eased (drags, i.e.
  entries < 0.15 s, linear so a drag doesn't stutter).
- Virtual camera (Ken Burns): per frame a crop rect of the full-res 1920 x 1080 window picture, scaled into the shot
  rect (zoomed UI stays sharp). Target = the bounding box of what happens in the next LOOKAHEAD*2 s (cursor path,
  clicks, the clip's ``focus`` points) plus MARGIN, zoom 1.0 .. ``zoom_max`` (1.35), wide in the clip's ``wide``
  ranges (layout changes, top-bar switch) and at the start / end of a clip; a critically damped spring (OMEGA) smooths
  it, a slow drift keeps it alive, clicks give a +3 % punch. The crop never leaves the picture and always keeps the
  cursor inside. Cursor, ripple and key chip follow the camera.
- Band: an intro (tick grows, title and caption slide in, <= 0.7 s, over the first frames) and an outro (OUTRO s:
  band text out, one-line lockup in). Captions change by sliding up (old out, then new in: never two at once). Key
  chips pop in (scale 0.85 -> 1 with overshoot + fade), the pressed key flashes ``highlight`` (Hello Yellow) and eases
  to ``accent``, then fades out; the newest key also shows for <= CURSOR_CHIP_MAX s as a small chip next to the
  cursor (above-right, flipped at the shot edges). Clicks: a ``highlight`` ring ripple + soft glow; a held button = an ``accent`` ring.
- Outputs: docs/distribution/marketing/clips/<nn>_<name>.mp4 (H.264 High, yuv420p, 30 fps, +faststart, no audio,
  <= 8 MB); docs/distribution/marketing/gif/<nn>_<name>.gif from a lossless 960 px intermediate
  (tmp/marketing/gif_src/), fps / width / colours stepped down until <= 4 MB (GitHub README; never on
  extensions.blender.org); docs/distribution/marketing/clips/00_trailer.mp4 (30 - 45 s, <= 20 MB): a moving key-visual
  title card (frame 0 = the finished key visual = the store poster; screens drift with parallax) -> a zoom-through ->
  a part of every clip joined by alternating push / zoom-through transitions inside the shot rect (the band text
  switches cleanly at the transition's middle, the brand mark stays) -> a zoom-through -> an animated end card (icon
  and lockup rise in, headline, the ``highlight`` CTA pill pops, then a held, gently breathing state).
- Check: per output the longest near-static run (mean |frame - previous| < STATIC_DIFF of 255) is reported; >= 2 s
  fails, as do the size / length limits. First frames go to tmp/marketing/posters/.
ffmpeg: PATH, or $FFMPEG, or the hermes build.
"""

import argparse
import bisect
import collections
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compose import (ROOT, credit_line, flatten, font, key_visual_layers, lockup, rgb, shadow, text_w,  # noqa: E402
                     vertical_gradient)

HERE = Path(__file__).resolve().parent
FRAMES = ROOT / "tmp" / "marketing" / "clips"
OUT = ROOT / "docs" / "distribution" / "marketing"
GIF_SRC = ROOT / "tmp" / "marketing" / "gif_src"
POSTERS = ROOT / "tmp" / "marketing" / "posters"
CONTENT = json.loads((HERE / "content.json").read_text(encoding="utf-8"))
W, H, FPS = 1920, 1080, 30
SHOT = (144, 22, 1632, 918)          # x, y, w, h of the window picture (85 %)
BAND_Y = SHOT[1] + SHOT[3]            # caption band below it
BAND_H = H - BAND_Y
LIMIT_MP4, LIMIT_TRAILER, LIMIT_GIF = 8e6, 20e6, 4e6
FFMPEG_FALLBACK = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes/tools/ffmpeg-9.0.1-win32-x64/bin/ffmpeg.exe"

SPEED = 1.35            # default playback speed (content.json clip "speed")
CAPTION_MIN = 1.2       # s a caption stays at least (output time)
INTRO, OUTRO = 0.7, 0.6
ZOOM_MAX = 1.35
LOOKAHEAD = 0.5         # s: the camera looks at [t, t + 2 * LOOKAHEAD]
MARGIN = (360, 270)     # window px kept round the action (menus open next to the cursor)
SAFE = 110              # window px the cursor always keeps from the crop edge
OMEGA = 5.0             # spring stiffness (rad/s), critically damped
DRIFT = 0.025           # slow Ken Burns zoom drift over a clip
PUNCH = 0.03            # click zoom punch
TRANSITION = 10         # frames of a trailer transition between clips
CARD_TRANSITION = 12    # frames title card -> first clip, last clip -> end card
CURSOR_CHIP_MAX = 1.1   # s a key chip stays next to the cursor
STATIC_DIFF = 0.5       # mean abs diff (0..255) below which a frame counts as static
STATIC_MAX = 2.0        # s


def ffmpeg():
    exe = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or (str(FFMPEG_FALLBACK) if FFMPEG_FALLBACK.exists()
                                                                    else None)
    if not exe:
        sys.exit("ffmpeg not found (PATH, $FFMPEG)")
    return exe


# --------------------------------------------------------------------------------------------- easing
def clamp(v, a=0.0, b=1.0):
    return a if v < a else b if v > b else v


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = clamp(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_back(t, s=1.4):
    t = clamp(t)
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


def mix(c0, c1, k):
    return tuple(round(a + (b - a) * k) for a, b in zip(c0, c1))


# --------------------------------------------------------------------------------------------- drawing primitives
_BG = None
_MASK = None


def background():
    global _BG
    if _BG is None:
        _BG = vertical_gradient((W, H), rgb("grey-900"), rgb("grey-950")).convert("RGBA")
        shadow(_BG, (SHOT[0], SHOT[1], SHOT[0] + SHOT[2], SHOT[1] + SHOT[3]), 10, 28, 150)
    return _BG


def shot_mask():
    global _MASK
    if _MASK is None:
        _MASK = Image.new("L", SHOT[2:], 0)
        ImageDraw.Draw(_MASK).rounded_rectangle((0, 0, SHOT[2] - 1, SHOT[3] - 1), 10, fill=255)
    return _MASK


def fade(img, a):
    """``img`` (RGBA) with its alpha multiplied by ``a``."""
    if a >= 0.999:
        return img
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return out


def put(dst, img, cx, cy, alpha=1.0, scale=1.0):
    """Alpha-composite ``img`` centred on (cx, cy) with alpha / scale."""
    if alpha <= 0.01 or scale <= 0.01:
        return
    if abs(scale - 1) > 0.005:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.BICUBIC)
    img = fade(img, alpha)
    x, y = round(cx - img.width / 2), round(cy - img.height / 2)
    if dst.mode == "RGBA":
        dst.alpha_composite(img, (x, y)) if x >= 0 and y >= 0 else _composite_clipped(dst, img, x, y)
    else:
        dst.paste(img, (x, y), img)


def _composite_clipped(dst, img, x, y):
    cx0, cy0 = max(0, -x), max(0, -y)
    dst.alpha_composite(img.crop((cx0, cy0, img.width, img.height)), (x + cx0, y + cy0))


_TXT = {}


def text_img(text, key, size, colour):
    """RGBA image of a text line; its (0, 0) = Pillow's default text anchor (left, ascender)."""
    k = (text, key, size, colour)
    if k not in _TXT:
        f = font(key, size)
        x0, y0, x1, y1 = f.getbbox(text)
        im = Image.new("RGBA", (int(x1) + 4, int(y1) + 6), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((0, 0), text, font=f, fill=rgb(colour, 255) if isinstance(colour, str)
                                else (*colour, 255))
        _TXT[k] = im
    return _TXT[k]


_LOCK = {}


def lockup_img(name_px, one_line=True, colours=None):
    k = (name_px, one_line, colours)
    if k not in _LOCK:
        im = Image.new("RGBA", (int(name_px * 20) + 8, int(name_px * 3)), (0, 0, 0, 0))
        lockup(ImageDraw.Draw(im), 4, 4, name_px, one_line=one_line, colours=colours)
        _LOCK[k] = im.crop(im.getbbox())
    return _LOCK[k]


_CHIP = {}


def chip_img(text, fill, size=28, h=50, pad=18, radius=10, edge=0):
    """A key chip: ``fill`` RGB, black ink (on-accent = on-highlight), optional black edge."""
    k = (text, fill, size, h, pad, edge)
    if k not in _CHIP:
        f = font("font-semibold", size)
        tw = math.ceil(f.getlength(text))
        w = tw + 2 * pad + 2 * edge
        im = Image.new("RGBA", (w, h + 2 * edge), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if edge:
            d.rounded_rectangle((0, 0, w - 1, h + 2 * edge - 1), radius + edge, fill=rgb("outline", 255))
        d.rounded_rectangle((edge, edge, w - 1 - edge, h - 1 + edge), radius, fill=(*fill, 255))
        d.text((edge + pad, edge + h / 2), text, font=f, fill=rgb("on-accent", 255), anchor="lm")
        _CHIP[k] = im
    return _CHIP[k]


_GLOW = {}


def glow_sprite(radius, token):
    k = (radius, token)
    if k not in _GLOW:
        n = radius * 4
        im = Image.new("RGBA", (n, n), (*rgb(token), 0))
        a = Image.new("L", (n, n), 0)
        ImageDraw.Draw(a).ellipse((n / 2 - radius, n / 2 - radius, n / 2 + radius, n / 2 + radius), fill=150)
        im.putalpha(a.filter(ImageFilter.GaussianBlur(radius / 2)))
        _GLOW[k] = im
    return _GLOW[k]


ARROW = [(0, 0), (0, 22), (5.5, 17), (9.5, 26), (13, 24.5), (9, 16), (16, 16)]   # kit-drawn pointer, 26 px tall


def chip_fill(age):
    """Chip colour at ``age`` s after its key went down: Hello Yellow flash, then teal."""
    k = clamp((age - 0.18) / 0.18)
    return mix(rgb("highlight"), rgb("accent"), round(k * 6) / 6)


def chip_anim(age, gone):
    """(alpha, scale) of a chip ``age`` s after it appeared, ``gone`` s after it was released (None = held)."""
    a = ease_out(age / 0.15)
    s = 0.85 + 0.15 * ease_out_back(age / 0.22)
    if gone is not None:
        g = clamp(gone / 0.18)
        a *= 1 - g
        s *= 1 - 0.1 * g
    return a, s


def cursor_label(text, skip=()):
    """The short form of a chip next to the cursor (None = not shown there): keys and key + mouse combos only; a
    plain mouse button already shows as the ripple / ring, and a chip there would sit on the menu it opens."""
    t = text.split("›")[0].strip()
    if (not t or text in skip or "shelf" in t.lower() or t.startswith(("Click", "LMB", "RMB", "MMB", "Drag"))
            or len(t) > 22):
        return None
    return t


# --------------------------------------------------------------------------------------------- one clip
def clip_info(name):
    return next(c for c in CONTENT["clips"] if c["name"] == name)


class Frame:
    """One composed frame as parts: ``shot`` (RGB, shot size, overlays drawn), ``band`` (RGBA band text layer) and
    whether the brand mark shows (+ the clip's attribution ``credit``, content.json credits); or a ``full`` RGB frame
    (cards)."""
    __slots__ = ("shot", "band", "brand", "full", "credit")

    def __init__(self, shot=None, band=None, brand=1.0, full=None, credit=""):
        self.shot, self.band, self.brand, self.full, self.credit = shot, band, brand, full, credit

    def image(self):
        if self.full is not None:
            return self.full
        canvas = background().copy()
        canvas.paste(self.shot, SHOT[:2], shot_mask())
        if self.band is not None:
            canvas.alpha_composite(self.band, (0, BAND_Y))
        if self.brand > 0:
            lk = lockup_img(26, True, ("text", "accent"))
            right = SHOT[0] + SHOT[2]
            put(canvas, lk, right - lk.width / 2, BAND_Y + 104, self.brand)
            if self.credit:   # small, muted, the band's bottom-right corner under the brand mark
                ci = text_img(self.credit, "font-regular", 15, "text-muted")
                put(canvas, ci, right - ci.width / 2, BAND_Y + 128, self.brand)
        return canvas.convert("RGB")


class Clip:
    def __init__(self, name, gif=False):
        """``gif``: the GIF camera — no drift / punch, the target held until it really changes and the spring snapped
        when settled, so frames between camera moves are identical (a moving GIF frame costs ~80 KB)."""
        self.name = name
        self.gif = gif
        self.info = info = clip_info(name)
        self.folder = FRAMES / name
        tl = json.loads((self.folder / "timeline.json").read_text(encoding="utf-8"))
        self.logo = tl.get("logo")
        self.title = info["title"]
        self.credit = credit_line(CONTENT, [name])
        self.entries = tl["entries"]
        speed = info.get("speed", SPEED)
        self.zoom_max = info.get("zoom_max", ZOOM_MAX)
        self.starts, s = [], 0.0
        for e in self.entries:
            self.starts.append(s)
            s += e["dur"]
        self.tl_total = s
        # time map: per caption group, timeline / speed, but a caption keeps >= CAPTION_MIN (never slower than 1x)
        knots, out, i = [(0.0, 0.0)], 0.0, 0
        self.captions = []                     # (output on time, text)
        while i < len(self.entries):
            j = i
            while j + 1 < len(self.entries) and self.entries[j + 1]["caption"] == self.entries[i]["caption"]:
                j += 1
            a, b = self.starts[i], self.starts[j] + self.entries[j]["dur"]
            d = max((b - a) / speed, min(b - a, CAPTION_MIN))
            self.captions.append((out, self.entries[i]["caption"]))
            out += d
            knots.append((b, out))
            i = j + 1
        self.knots = knots
        self.body = out
        self.n_body = int(round(out * FPS))
        self.n = self.n_body + int(round(OUTRO * FPS))
        self.clicks = [(self.tl2out(self.starts[k]), e["to"]) for k, e in enumerate(self.entries) if e["click"]]
        self._chips()
        self._camera()
        self._pics = collections.OrderedDict()

    # time ---------------------------------------------------------------------------------------------
    def tl2out(self, x):
        ks = self.knots
        for (a, oa), (b, ob) in zip(ks, ks[1:]):
            if x <= b:
                return oa + (x - a) * (ob - oa) / max(b - a, 1e-9)
        return ks[-1][1]

    def out2tl(self, t):
        ks = self.knots
        for (a, oa), (b, ob) in zip(ks, ks[1:]):
            if t <= ob:
                return a + (t - oa) * (b - a) / max(ob - oa, 1e-9)
        return ks[-1][0]

    def entry_at(self, x):
        return max(0, min(bisect.bisect_right(self.starts, x) - 1, len(self.entries) - 1))

    def pos(self, x):
        k = self.entry_at(x)
        e = self.entries[k]
        u = clamp((x - self.starts[k]) / max(e["dur"], 1e-6))
        if e["dur"] >= 0.15:                      # a move: eased; drag steps stay linear
            u = smooth(u)
        return (e["from"][0] + (e["to"][0] - e["from"][0]) * u, e["from"][1] + (e["to"][1] - e["from"][1]) * u)

    # chips --------------------------------------------------------------------------------------------
    def _chips(self):
        self.chip_iv = []                         # [text, on, off]
        open_ = {}
        self.entry_chips = []                     # per entry: interval indices in display order
        for k, e in enumerate(self.entries):
            o = self.tl2out(self.starts[k])
            for text in list(open_):
                if text not in e["chips"]:
                    self.chip_iv[open_.pop(text)][2] = o
            ids = []
            for text in e["chips"]:
                if text not in open_:
                    open_[text] = len(self.chip_iv)
                    self.chip_iv.append([text, o, None])
                ids.append(open_[text])
            self.entry_chips.append(ids)
        for idx in open_.values():
            self.chip_iv[idx][2] = self.body
        # band layout per entry: right-aligned, in entry order; x = centre
        self.entry_layout = []
        right = SHOT[0] + SHOT[2]
        for ids in self.entry_chips:
            lay, r = {}, right
            for idx in reversed(ids):
                w = chip_img(self.chip_iv[idx][0], rgb("accent")).width
                lay[idx] = r - w / 2
                r -= w + 12
            self.entry_layout.append(lay)
        self.last_layout = {}
        for lay in self.entry_layout:
            self.last_layout.update(lay)

    # camera -------------------------------------------------------------------------------------------
    def _target(self, t):
        if t >= self.body:
            return 1.0, W / 2, H / 2
        a, b = self.out2tl(t), self.out2tl(min(t + 2 * LOOKAHEAD, self.body))
        for w0, w1 in self.info.get("wide", []):
            if w0 < b and a < w1:
                return 1.0, W / 2, H / 2
        pts = [self.pos(a + (b - a) * i / 12) for i in range(13)]
        for f in self.info.get("focus", []):
            if f["t"][0] < b and a < f["t"][1]:
                pts.append(tuple(f["pt"]))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        z = min(W / (x1 - x0 + 2 * MARGIN[0]), H / (y1 - y0 + 2 * MARGIN[1]))
        env = smooth(t / 0.9) * smooth((self.body - t) / 1.1)
        z = 1 + (clamp(z, 1.0, self.zoom_max) - 1) * env
        return z, (x0 + x1) / 2, (y0 + y1) / 2

    def _camera(self):
        dt = 1 / FPS
        z, cx, cy = self._target(0)
        v = [0.0, 0.0, 0.0]
        x = [z, cx, cy]
        shots = self._gif_shots() if self.gif else None
        self.cam = []
        for i in range(self.n):
            t = i * dt
            if shots:
                x = self._gif_cam(shots, t)
            else:
                tgt = self._target(t)
                for j in range(3):
                    acc = OMEGA * OMEGA * (tgt[j] - x[j]) - 2 * OMEGA * v[j]
                    v[j] += acc * dt
                    x[j] += v[j] * dt
            zz = max(1.0, x[0])
            if not self.gif:
                zz *= 1 + DRIFT * smooth(t / max(self.body, 1e-6)) * (1 - smooth((t - self.body) / OUTRO))
                for tc, _p in self.clicks:
                    age = t - tc
                    if 0 <= age < 0.3:
                        zz *= 1 + PUNCH * math.sin(math.pi * age / 0.3)
            cw, ch = W / zz, H / zz
            x0, y0 = x[1] - cw / 2, x[2] - ch / 2
            px, py = self.pos(self.out2tl(min(t, self.body)))
            x0 = min(max(x0, px + SAFE - cw), px - SAFE)          # the cursor stays inside
            y0 = min(max(y0, py + SAFE - ch), py - SAFE)
            x0, y0 = clamp(x0, 0, W - cw), clamp(y0, 0, H - ch)
            self.cam.append((x0, y0, cw, ch))

    def _gif_shots(self):
        """GIF camera: one framing per caption group ([(t_from, t_to, (z, cx, cy))], moves eased between them),
        wide at the start and the end, so most GIF frames repeat the previous one's camera."""
        wide = (1.0, W / 2, H / 2)
        keys = [(0.0, wide)]
        ons = [c[0] for c in self.captions] + [self.body]
        for g in range(len(self.captions)):
            a, b = self.out2tl(ons[g]), self.out2tl(ons[g + 1])
            if any(w0 < b and a < w1 for w0, w1 in self.info.get("wide", [])):
                keys.append((ons[g], wide))
                continue
            pts = [self.pos(a + (b - a) * i / 24) for i in range(25)]
            pts += [tuple(f["pt"]) for f in self.info.get("focus", []) if f["t"][0] < b and a < f["t"][1]]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            z = clamp(min(W / (max(xs) - min(xs) + 2 * MARGIN[0]), H / (max(ys) - min(ys) + 2 * MARGIN[1])), 1.0,
                      self.zoom_max)
            framing = (z, (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2) if z >= 1.12 else wide
            keys.append((max(ons[g], 0.5), framing))
        keys.append((self.body - 0.2, wide))
        return keys

    @staticmethod
    def _gif_cam(keys, t, move=0.45):
        cur = keys[0][1]
        for (t0, f0), (t1, f1) in zip(keys, keys[1:]):
            if t < t1 - move:
                return f0 if t >= t0 else cur
            u = ease_in_out((t - (t1 - move)) / move)
            cur = tuple(a + (b - a) * u for a, b in zip(f0, f1))
            if u < 1:
                return cur
        return keys[-1][1]

    # pictures -----------------------------------------------------------------------------------------
    def picture(self, img_name):
        if img_name not in self._pics:
            img = Image.open(self.folder / img_name).convert("RGB")
            if self.logo:  # no Blender logo in the pictures (extensions.blender.org terms 2.2), like shots.hide_logo
                x, y, w, h = self.logo
                img.paste(img.getpixel((x + w, y + 1)), (x, y, x + w, y + h))
            self._pics[img_name] = img
            while len(self._pics) > 3:
                self._pics.popitem(last=False)
        return self._pics[img_name]

    # one frame ----------------------------------------------------------------------------------------
    def frame(self, i, band_start=0.0, outro=True, brand_static=False):
        """Frame ``i`` (output index). The band intro starts at ``band_start`` s (band empty before)."""
        t = i / FPS
        tb = min(t, self.body)
        x = self.out2tl(tb)
        k = self.entry_at(x if t < self.body else self.tl_total - 1e-6)
        e = self.entries[k]
        x0, y0, cw, ch = self.cam[min(i, self.n - 1)]
        shot = self.picture(e["img"]).resize(SHOT[2:], Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))
        sc = SHOT[2] / cw

        def to_shot(p):
            return (p[0] - x0) * sc, (p[1] - y0) * sc

        pos = to_shot(self.pos(x))
        d = ImageDraw.Draw(shot, "RGBA")
        for tc, p in self.clicks:                      # click: Hello Yellow ripple + glow
            age = t - tc
            if 0 <= age < 0.5:
                u = age / 0.5
                cx, cy = to_shot(p)
                put(shot, glow_sprite(26, "highlight"), cx, cy, (1 - u) * 0.9, 0.8 + 0.6 * u)
                r = 12 + 40 * ease_out(u)
                wd = max(2, round(6 - 3 * u))
                al = int(255 * (1 - u))
                d.ellipse((cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), outline=rgb("outline", al // 2),
                          width=wd + 4)
                d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=rgb("highlight", al), width=wd)
        cx, cy = pos
        if e["down"] and t < self.body:              # a held button: teal ring at the tip
            d.ellipse((cx - 15, cy - 15, cx + 15, cy + 15), outline=rgb("outline", 200), width=7)
            d.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), outline=rgb("accent", 240), width=4)
        pts = [(cx + a, cy + b) for a, b in ARROW]
        d.polygon(pts, fill=(255, 255, 255, 255))
        d.line(pts + [pts[0]], fill=(0, 0, 0, 255), width=2, joint="curve")
        self._cursor_chip(shot, t, k, pos)
        band = self._band(t, k, band_start, outro, brand_static)
        brand = 1.0
        if not brand_static:
            brand = ease_out((t - band_start - 0.25) / 0.3) * (1 - clamp((t - self.body) / 0.2) if outro else 1)
        return Frame(shot, band, brand, credit=self.credit)

    def _cursor_chip(self, shot, t, k, pos):
        skip = self.info.get("no_cursor_chip", ())
        best = None
        for idx, (text, on, off) in enumerate(self.chip_iv):
            off = min(off, on + CURSOR_CHIP_MAX)
            if on <= t < off + 0.18 and cursor_label(text, skip) and (best is None or on >= self.chip_iv[best][1]):
                best = idx
        if best is None:
            return
        text, on, off = self.chip_iv[best]
        off = min(off, on + CURSOR_CHIP_MAX)       # the press moment only: a held key doesn't sit on menus
        alpha, scale = chip_anim(t - on, t - off if t >= off else None)
        p0 = self.pos(self.out2tl(on))                # the cursor walked away from where the key went down
        p1 = self.pos(self.out2tl(min(t, self.body)))
        alpha *= clamp(1 - (math.hypot(p1[0] - p0[0], p1[1] - p0[1]) - 40) / 80)
        if alpha <= 0.01:
            return
        img = chip_img(cursor_label(text, skip), chip_fill(t - on), 22, 38, 12, 8, edge=2)
        cx, cy = pos
        x = cx + 26 + img.width / 2
        y = cy - 30 - img.height / 2
        if y - img.height / 2 < 8:
            y = cy + 44 + img.height / 2
        if x + img.width / 2 > SHOT[2] - 8:
            x = cx - 14 - img.width / 2
        put(shot, img, x, y, alpha, scale)

    def _band(self, t, k, band_start, outro, brand_static):
        band = Image.new("RGBA", (W, BAND_H), (0, 0, 0, 0))
        x = SHOT[0]
        u = t - band_start
        if u < 0:
            return band
        out_a = 1 - clamp((t - self.body) / 0.2) if outro else 1.0
        # tick
        th = round(46 * ease_out(u / 0.3) * out_a)
        if th > 1:
            ImageDraw.Draw(band).rectangle((x, 26 + (46 - th) // 2, x + 5, 26 + (46 - th) // 2 + th),
                                           fill=rgb("accent", 255))
        # title
        ti = text_img(self.title, "font-semibold", 40, "text-strong")
        a = ease_out((u - 0.05) / 0.3)
        if a * out_a > 0.01:
            band.alpha_composite(fade(ti, a * out_a), (round(x + 24 - 30 * (1 - a)), 20))
        # caption: slide up; the old one leaves before the new one comes in
        ci = max(0, bisect.bisect_right([c[0] for c in self.captions], t) - 1)
        on, text = self.captions[ci]
        age = t - on
        intro_a = ease_out((u - 0.15) / 0.3)
        if ci > 0 and age < 0.11 and on > band_start:
            v = age / 0.11
            img, a, dy = text_img(self.captions[ci - 1][1], "font-regular", 28, "text"), 1 - v, -14 * v
        else:
            v = ease_out((age - (0.11 if ci > 0 and on > band_start else 0)) / 0.16) if ci > 0 and on > band_start \
                else 1.0
            img, a, dy = text_img(text, "font-regular", 28, "text"), v, 14 * (1 - v)
        a *= intro_a * out_a
        if a > 0.01:
            band.alpha_composite(fade(img, a), (x + 24, round(74 + dy + 10 * (1 - intro_a))))
        # chips
        for idx, (ctext, con, coff) in enumerate(self.chip_iv):
            if not (con <= t < coff + 0.18):
                continue
            gone = t - coff if t >= coff else None
            alpha, scale = chip_anim(t - con, gone)
            lay = self.entry_layout[k]
            cx = lay.get(idx, self.last_layout.get(idx))
            put(band, chip_img(ctext, chip_fill(t - con)), cx, 52, alpha * out_a * intro_a, scale)
        # outro: the lockup rises into the band
        if outro and t > self.body + 0.15:
            v = ease_out((t - self.body - 0.15) / 0.3)
            lk = lockup_img(40, True, ("text-strong", "accent"))
            put(band, lk, W / 2, BAND_H / 2 + 12 * (1 - v), v)
        return band

    def frames(self, start=0, end=None, band_start=0.0, outro=True, brand_static=False):
        end = self.n if end is None else end
        for i in range(start, end):
            yield self.frame(i, band_start, outro, brand_static)


# --------------------------------------------------------------------------------------------- encoding
def mean_diff(a, b):
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


RAW_IN = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]


def pump(frames, cmd, poster=None):
    """Pipe frames (Frame or RGB images) into the ffmpeg ``cmd``; returns (count, longest static run in s)."""
    proc = subprocess.Popen([ffmpeg(), "-y", "-loglevel", "error", *RAW_IN, *cmd], stdin=subprocess.PIPE)
    count, run, longest, prev = 0, 0, 0, None
    for f in frames:
        img = f.image() if isinstance(f, Frame) else f
        if count == 0 and poster:
            poster.parent.mkdir(parents=True, exist_ok=True)
            img.save(poster)
        if prev is not None and mean_diff(prev, img) < STATIC_DIFF:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
        prev = img
        proc.stdin.write(img.tobytes())
        count += 1
    proc.stdin.close()
    if proc.wait():
        sys.exit(f"ffmpeg failed for {cmd[-1]}")
    return count, (longest + 1) / FPS if longest else 0.0


def encode(frames, out, crf=20, poster=None):
    """H.264 High / yuv420p / 30 fps / faststart MP4."""
    out.parent.mkdir(parents=True, exist_ok=True)
    return pump(frames, ["-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-profile:v", "high", "-pix_fmt",
                         "yuv420p", "-movflags", "+faststart", "-an", str(out)], poster)


def encode_gif_src(frames, out):
    """Lossless 960 px intermediate for the GIF (an MP4's compression noise costs GIF bytes)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    return pump(frames, ["-vf", "scale=960:-2:flags=lanczos", "-c:v", "ffv1", str(out)])


GIF_STEPS = [(960, 15, 160, "sierra2_4a"), (960, 12, 128, "bayer:bayer_scale=3"), (800, 12, 128,
             "bayer:bayer_scale=3"), (800, 12, 96, "bayer:bayer_scale=2"), (800, 10, 96, "bayer:bayer_scale=2")]


def gif(src, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    for width, fps, colours, dither in GIF_STEPS:
        vf = (f"fps={fps},scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors={colours}:"
              f"stats_mode=diff[p];[b][p]paletteuse=dither={dither}:diff_mode=rectangle")
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(src), "-filter_complex", vf, "-loop", "0",
                        str(out)], check=True, stdin=subprocess.DEVNULL)
        if out.stat().st_size <= LIMIT_GIF:
            break
    return {"px": width, "fps": fps, "colours": colours}


# --------------------------------------------------------------------------------------------- trailer
def title_card(n):
    """The key visual, then its screens drift (parallax) and the text rises a little; frame 0 = the key visual."""
    bg, screens, text = key_visual_layers(CONTENT, CONTENT["key_visual_shots"])
    drift = [(-26, -8), (-56, -14)]                           # back screen, front screen (px over the card)
    for i in range(n):
        u = smooth(i / max(n - 1, 1)) * 0.5 + 0.5 * (i / max(n - 1, 1))
        offs = [(dx * u, dy * u) for dx, dy in drift[:len(screens)]]
        yield flatten(bg, screens, text, offsets=offs, text_offset=(0, -10 * u)).convert("RGB")


class EndCard:
    def __init__(self):
        tr = CONTENT["trailer"]
        self.bg = vertical_gradient((W, H), rgb("grey-850"), rgb("grey-950")).convert("RGBA")
        g = Image.new("RGBA", (W, H), (*rgb("accent-deep"), 0))
        a = Image.new("L", (W, H), 0)
        ImageDraw.Draw(a).ellipse((W / 2 - 620, 470 - 380, W / 2 + 620, 470 + 380), fill=255)
        g.putalpha(a.filter(ImageFilter.GaussianBlur(170)))
        self.glow = g
        self.icon = Image.open(OUT / "icon_256.png").convert("RGBA").resize((150, 150), Image.LANCZOS)
        self.lock = lockup_img(112, False)
        self.head = text_img(tr["end_headline"], "font-semibold", 46, "text-strong")
        self.line = text_img(tr["end_line"], "font-regular", 30, "text")
        cta = tr.get("cta") or tr["download"]
        f = font("font-bold", 36)
        tw = math.ceil(f.getlength(cta))
        pill = Image.new("RGBA", (tw + 72, 76), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pill)
        pd.rounded_rectangle((0, 0, pill.width - 1, 75), 38, fill=rgb("highlight", 255))
        pd.text((pill.width / 2, 38), cta, font=f, fill=rgb("on-highlight", 255), anchor="mm")
        self.pill = pill
        self.pill_glow = glow_sprite(110, "highlight")
        fine = [*tr.get("end_card_credits", []), CONTENT.get("trademark_note", "")]   # bottom up: note last
        self.credits = [text_img(t, "font-regular", 17, "text-muted") for t in fine if t]

    def frame(self, t):
        out = self.bg.copy()
        breathe = 0.5 - 0.5 * math.cos(2 * math.pi * t / 2.2)
        out.alpha_composite(fade(self.glow, 0.32 + 0.16 * breathe))
        drift = -8 * smooth(t / 3.0)                               # the whole group floats up a little
        cx = W / 2
        a = ease_out(t / 0.3)
        put(out, self.icon, cx, 190 + drift, a, 0.8 + 0.2 * ease_out_back(t / 0.35))
        for img, y, t0 in ((self.lock, 395, 0.1), (self.head, 600, 0.25), (self.line, 668, 0.35)):
            v = ease_out((t - t0) / 0.4)
            put(out, img, cx, y + 36 * (1 - v) + drift, v)
        v = (t - 0.55) / 0.3
        if v > 0:
            put(out, self.pill_glow, cx, 800 + drift, clamp(v) * (0.16 + 0.12 * breathe), 1.4)   # a halo, not a wash: yellow over the teal glow turns olive
            put(out, self.pill, cx, 800 + drift, ease_out(v), 0.8 + 0.2 * ease_out_back(v))
        a = ease_out((t - 0.6) / 0.4)
        for i, img in enumerate(reversed(self.credits)):        # attribution lines, bottom up, still
            put(out, img, cx, H - 36 - i * 26, a)
        return out.convert("RGB")


def zoom_full(img, s, centre=(W / 2, H / 2)):
    """``img`` scaled by ``s`` about ``centre`` (s > 1 crops in, s < 1 shrinks onto black is avoided by callers)."""
    cw, ch = W / s, H / s
    x0, y0 = centre[0] - cw / 2, centre[1] - ch / 2
    return img.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))


def zoom_through_full(a, b, j, n):
    p = ease_in_out((j + 1) / (n + 1))
    a2 = zoom_full(a, 1 + 0.18 * p)
    b2 = zoom_full(b, 1.12 - 0.12 * p)
    return Image.blend(a2, b2, p)


def shot_transition(fa, fb, j, n, kind):
    """Frame ``j`` of an in-shot transition from Frame ``fa`` to ``fb``: only the picture moves; the band text
    switches cleanly at the middle (outgoing fades, incoming begins its own intro), the brand mark stays."""
    p = ease_in_out((j + 1) / (n + 1))
    A, B = fa.shot, fb.shot
    sw, sh = SHOT[2], SHOT[3]
    if kind == "push":
        shot = Image.new("RGB", (sw, sh))
        off = round(p * sw)
        shot.paste(A, (-off, 0))
        shot.paste(B, (sw - off, 0))
        ImageDraw.Draw(shot).rectangle((sw - off - 3, 0, sw - off + 2, sh), fill=rgb("accent"))
    else:
        s = 1 + 0.2 * p
        cw, ch = sw / s, sh / s
        A2 = A.resize((sw, sh), Image.BICUBIC, box=((sw - cw) / 2, (sh - ch) / 2, (sw + cw) / 2, (sh + ch) / 2))
        s2 = 0.85 + 0.15 * p
        B2 = B.resize((round(sw * s2), round(sh * s2)), Image.BICUBIC)
        layer = A2.copy()
        layer.paste(B2, ((sw - B2.width) // 2, (sh - B2.height) // 2))
        shot = Image.blend(A2, layer, smooth((p - 0.3) / 0.35))   # a short dissolve, no long double exposure
    half = n / 2
    if j < half:
        band = fade(fa.band, 1 - (j + 1) / half) if fa.band is not None else None
    else:
        band = fb.band
    return Frame(shot, band, 1.0, credit=fa.credit if j < n / 2 else fb.credit)


def trailer_parts():
    """Yields Frame / RGB images of the trailer."""
    tr = CONTENT["trailer"]
    n_title = int(round(tr["title_seconds"] * FPS))
    clips = [(Clip(c["name"]), c["trailer"]) for c in CONTENT["clips"]]
    # title card, all but the transition frames
    gen = title_card(n_title)
    for _ in range(n_title - CARD_TRANSITION):
        yield next(gen)
    tail = list(gen)
    kinds = ["push", "zoom"]
    for ci, (clip, (a, b)) in enumerate(clips):
        i0, i1 = int(round(clip.tl2out(a) * FPS)), int(round(clip.tl2out(b) * FPS))
        nt = CARD_TRANSITION if ci == 0 else TRANSITION
        start = i0 / FPS + (nt / 2) / FPS
        it = clip.frames(i0, i1, band_start=start, outro=False, brand_static=True)
        head = [next(it) for _ in range(nt)]
        if ci == 0:
            for j in range(nt):
                yield zoom_through_full(tail[j], head[j].image(), j, nt)
        else:
            kind = kinds[(ci - 1) % 2]
            for j in range(nt):
                yield shot_transition(tail[j], head[j], j, nt, kind)
        last = ci == len(clips) - 1
        keep = CARD_TRANSITION if last else TRANSITION
        buf = collections.deque()
        for f in it:
            buf.append(f)
            if len(buf) > keep:
                yield buf.popleft()
        tail = list(buf)
    end = EndCard()
    n_end = int(round(tr["end_seconds"] * FPS))
    for j in range(CARD_TRANSITION):              # into the bare card: its text starts after the transition
        yield zoom_through_full(tail[j].image(), end.frame(-1.0), j, CARD_TRANSITION)
    for j in range(n_end):
        yield end.frame(j / FPS)


# --------------------------------------------------------------------------------------------- main
def mb(path):
    return path.stat().st_size / 1e6


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", default="")
    ap.add_argument("--no-trailer", action="store_true")
    ap.add_argument("--no-gif", action="store_true")
    ap.add_argument("--trailer-only", action="store_true")
    args = ap.parse_args(argv)
    only = [n for n in args.only.split(",") if n]
    ok = True
    report = []
    for c in CONTENT["clips"]:
        if args.trailer_only or (only and c["name"] not in only):
            continue
        if not (FRAMES / c["name"] / "timeline.json").exists():
            print("missing frames:", c["name"])
            ok = False
            continue
        clip = Clip(c["name"])
        mp4 = OUT / "clips" / f"{c['file']}.mp4"
        n, static = encode(clip.frames(), mp4, poster=POSTERS / f"{c['file']}.png")
        sec = n / FPS
        report.append({"file": mp4.relative_to(ROOT).as_posix(), "seconds": round(sec, 2), "MB": round(mb(mp4), 2),
                       "static_s": round(static, 2),
                       "ok": mb(mp4) * 1e6 <= LIMIT_MP4 and sec <= 15 and static < STATIC_MAX})
        if not args.no_gif:
            src = GIF_SRC / f"{c['file']}.mkv"
            _n, gstatic = encode_gif_src(Clip(c["name"], gif=True).frames(), src)
            g = OUT / "gif" / f"{c['file']}.gif"
            info = gif(src, g)
            report.append({"file": g.relative_to(ROOT).as_posix(), **info, "MB": round(mb(g), 2),
                           "static_s": round(gstatic, 2),
                           "ok": mb(g) * 1e6 <= LIMIT_GIF and gstatic < STATIC_MAX})
    if not args.no_trailer and not only:
        mp4 = OUT / "clips" / f"{CONTENT['trailer']['file']}.mp4"
        n, static = encode(trailer_parts(), mp4, crf=22, poster=POSTERS / "00_trailer.png")
        sec = n / FPS
        report.append({"file": mp4.relative_to(ROOT).as_posix(), "seconds": round(sec, 2), "MB": round(mb(mp4), 2),
                       "static_s": round(static, 2),
                       "ok": mb(mp4) * 1e6 <= LIMIT_TRAILER and 30 <= sec <= 45 and static < STATIC_MAX})
    for r in report:
        print("PASS" if r["ok"] else "FAIL", json.dumps(r))
        ok &= r["ok"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
