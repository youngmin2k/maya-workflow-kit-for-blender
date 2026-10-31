# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit-made colour shelf icons, drawn by code, one drawing per button.

No Maya icons. A Maya shelf shows one colour pictogram per button; the kit (#23) gives every
factory shelf button its own kit drawing that follows the Maya icon's subject, main colour, composition and size
(clean-room descriptions of Maya's shared visual vocabulary). Shared vocabulary used here:

- one hue per kind (NURBS blue, poly orange, UV green, rigging lavender, key orange-red, render yellow, FX salmon,
  editors teal), two or three tones per hue, light from the upper left;
- a dark #3a3a3a outline round every shape (a post pass on the alpha at the target size, plus ``ol=True`` parts);
- poly primitives with black wire edges, NURBS primitives smooth without wire, tool parts light grey #bcbcbc,
  the action mark (plus, X, check, link, key, target) small in a corner; letters only where Maya's icon is text.

Drawing is in icon units (0..32, y down) and rasterised at the requested size (32 = 1x, 64 = 2x for UI scale
>= 1.25) with supersampling; edges and line widths are snapped to the target pixel grid ("hinting") so 1-unit
lines are one crisp pixel at 32 and two at 64. Pure numpy, no files, no bpy at import; ``texture()`` turns a
picture into a GPU texture for ``ui/shelf.py``'s icon row.
"""

import math

import numpy as np

SIZE = 32
SIZES = (32, 64)


def _hex(s):
    return tuple(int(s[i:i + 2], 16) / 255 for i in (1, 3, 5))


# Maya 2022 icon hues (colour values only).
BLUE = _hex("#57a4cb")       # Curves / Surfaces, NURBS
ORANGE = _hex("#da9355")     # Poly Modeling, Sculpting
GREEN = _hex("#5eac87")      # UV tools
TEAL = _hex("#48a9b4")       # editors, pivot, history
LAV = _hex("#ad9cd8")        # Rigging, constraint links
KEY = _hex("#df6e41")        # Animation keys
YELLOW = _hex("#bfb23a")     # Rendering
SALMON = _hex("#d6806d")     # FX, FX Caching
LIGHT = _hex("#bcbcbc")      # tool parts
DARK = _hex("#3a3a3a")       # outlines
BLACK = (0.06, 0.06, 0.06)
WHITE = (0.93, 0.93, 0.93)

SHELF_COLOURS = {
    "Curves": BLUE, "Surfaces": BLUE, "Polygons": ORANGE, "Sculpting": ORANGE, "UVEditing": GREEN, "Rigging": LAV,
    "Animation": KEY, "Rendering": YELLOW, "FX": SALMON, "FXCaching": SALMON,
}
USER_COLOUR = (0.63, 0.63, 0.63)
GREYED_ALPHA = 0.35     # greyed (unmapped) buttons: grey and faded, like a disabled Maya control

# 5x7 capitals and digits (pixel font: one cell = one icon unit = one pixel at 32 px).
FONT = {
    "A": ".###." "#...#" "#...#" "#####" "#...#" "#...#" "#...#", "B": "####.#...#####.#...##...##...#####.",
    "C": ".####" "#...." "#...." "#...." "#...." "#...." ".####", "D": "####.#...##...##...##...##...#####.",
    "E": "######....####.#....#....#....#####", "F": "######....####.#....#....#....#....",
    "G": ".####" "#...." "#...." "#..##" "#...#" "#...#" ".####", "H": "#...##...#######...##...##...##...#",
    "I": "#####..#....#....#....#....#..#####", "J": "....#....#....#....##...##...#.###.",
    "K": "#...##..#.###..#..#.#...##...##...#", "L": "#....#....#....#....#....#....#####",
    "M": "#...###.###.#.##...##...##...##...#", "N": "#...###..##.#.##..###...##...##...#",
    "O": ".###.#...##...##...##...##...#.###.", "P": "####.#...##...#####.#....#....#....",
    "Q": ".###.#...##...##...##.#.##..#..##.#", "R": "####.#...##...#####.#.#..#..#.#...#",
    "S": ".####" "#...." "#...." ".###." "....#" "....#" "####.", "T": "#####..#....#....#....#....#....#..",
    "U": "#...##...##...##...##...##...#.###.", "V": "#...##...##...##...#.#.#..#.#...#..",
    "W": "#...##...##...##.#.##.#.###.###...#", "X": "#...#.#.#...#...#.#.#...##...##...#",
    "Y": "#...#.#.#...#....#....#....#....#..", "Z": "#####....#...#...#...#...#....#####",
    "0": ".###.#..###.#.###..#.###.#..#..###.", "1": "..#..##....#....#....#....#...#####",
    "2": ".###.#...#....#...#...#...#...#####", "3": "####.....#..##.....#....#....#####.",
    "4": "#...##...##...######....#....#....#", "5": "######....####.....#....#....#####.",
    "6": ".###.#....####.#...##...##...#.###.", "7": "#####....#...#...#....#....#....#..",
    "8": ".###.#...#.###.#...##...##...#.###.", "9": ".###.#...##...#.####....#....#.###.",
    # 5x5 lower case for Maya's "svg" tag, 3x5 small digits and comma for "0,0,0"
    "s": ".#####.....###.....#####.", "v": "#...##...#.#.#..#.#...#..", "g": ".#####...#.####....#####.",
    "o": ".#.#.##.##.#.#.", ",": "...........#.#.",
}
_FONT_W = {"s": 5, "v": 5, "g": 5, "o": 3, ",": 3}


def shade(colour, k):
    """Lighter (k > 0) or darker (k < 0) version of a colour."""
    if k >= 0:
        return tuple(c + (1 - c) * k for c in colour[:3])
    return tuple(c * (1 + k) for c in colour[:3])


# --- canvas -----------------------------------------------------------------------------------

def _dilate(mask, d):
    """Square binary dilation by ``d`` samples (separable max)."""
    if d <= 0:
        return mask
    out = mask.copy()
    for s in range(1, d + 1):
        out[s:, :] |= mask[:-s, :]
        out[:-s, :] |= mask[s:, :]
    m2 = out.copy()
    for s in range(1, d + 1):
        out[:, s:] |= m2[:, :-s]
        out[:, :-s] |= m2[:, s:]
    return out


class Canvas:
    """RGBA canvas in icon units (0..32, y down), supersampled, with pixel hinting for the target ``size``."""

    def __init__(self, size=SIZE):
        self.size = size
        self.k = size / 32.0                       # target pixels per icon unit
        self.ss = 4 if size <= 32 else 3
        n = self.n = size * self.ss
        c = (np.arange(n, dtype=np.float32) + 0.5) * np.float32(32.0 / n)
        self.x, self.y = np.meshgrid(c, c)
        self.px = np.zeros((n, n, 4), np.float32)
        self.clip = None
        self.outline = True

    # hinting ---------------------------------------------------------------------------------
    # The hinting grid is the 1x pixel (one icon unit) for whole multiples of 32 px, so the 2x picture is the 1x
    # drawing with every crisp pixel doubled (scaled down it matches the 1x one); other sizes snap to their pixels.
    @property
    def g(self):
        return max(1, int(self.k)) / self.k

    def snap(self, v):
        """An edge on the hinting grid."""
        g = self.g
        return round(v / g) * g

    def lw(self, w):
        """A line width in whole grid pixels (at least one)."""
        g = self.g
        return max(1, round(w / g)) * g

    def centre(self, c, w):
        """Centre of an axis-aligned line of width ``w`` so that it covers whole grid pixels."""
        g = self.g
        if max(1, round(w / g)) % 2:
            return (math.floor(c / g) + 0.5) * g
        return round(c / g) * g

    # compositing -----------------------------------------------------------------------------
    def fill(self, mask, colour, alpha=1.0, ol=False):
        if self.clip is not None:
            mask = mask & self.clip
        if ol:
            d = max(1, round(self.k)) * self.ss
            self.fill(_dilate(mask, d) & ~mask, DARK)
        a = mask.astype(np.float32) * alpha
        col = np.asarray(colour, np.float32)
        out = self.px
        oa = out[..., 3]
        na = a + oa * (1 - a)
        safe = np.where(na > 0, na, 1)
        if col.ndim == 1:
            for i in range(3):
                out[..., i] = (col[i] * a + out[..., i] * oa * (1 - a)) / safe
        else:
            for i in range(3):
                out[..., i] = (col[..., i] * a + out[..., i] * oa * (1 - a)) / safe
        out[..., 3] = na

    def erase(self, mask):
        self.px[mask] = 0

    # masks -----------------------------------------------------------------------------------
    def m_rect(self, x0, y0, x1, y1):
        x0, x1 = self.snap(x0), self.snap(x1)
        y0, y1 = self.snap(y0), self.snap(y1)
        if x1 <= x0:
            x1 = x0 + self.g
        if y1 <= y0:
            y1 = y0 + self.g
        return (self.x >= x0) & (self.x < x1) & (self.y >= y0) & (self.y < y1)

    def m_circle(self, cx, cy, r):
        return (self.x - cx) ** 2 + (self.y - cy) ** 2 <= r * r

    def m_ellipse(self, cx, cy, rx, ry, rot=0.0):
        dx, dy = self.x - cx, self.y - cy
        if rot:
            c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            dx, dy = dx * c + dy * s, -dx * s + dy * c
        return (dx / rx) ** 2 + (dy / ry) ** 2 <= 1

    def m_ring(self, cx, cy, r, w):
        w = self.lw(w)
        d = (self.x - cx) ** 2 + (self.y - cy) ** 2
        return (d <= r * r) & (d >= (r - w) ** 2)

    def m_ering(self, cx, cy, rx, ry, w, rot=0.0):
        w = self.lw(w)
        return self.m_ellipse(cx, cy, rx, ry, rot) & ~self.m_ellipse(cx, cy, max(rx - w, 0.01), max(ry - w, 0.01), rot)

    def m_angle(self, cx, cy, a0, a1):
        """Angles in degrees, 0 = right, 90 = down (screen), from a0 to a1 going clockwise."""
        ang = np.degrees(np.arctan2(self.y - cy, self.x - cx)) % 360
        a0, a1 = a0 % 360, a1 % 360
        return (ang >= a0) & (ang <= a1) if a0 <= a1 else (ang >= a0) | (ang <= a1)

    def m_poly(self, pts):
        inside = np.zeros((self.n, self.n), bool)
        n = len(pts)
        for i in range(n):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
            if y1 == y0:
                continue
            cond = (self.y >= min(y0, y1)) & (self.y < max(y0, y1))
            xi = x0 + (self.y - y0) * (x1 - x0) / (y1 - y0)
            inside ^= cond & (self.x < xi)
        return inside

    def m_line(self, p0, p1, w, cap=True):
        (x0, y0), (x1, y1) = p0, p1
        if abs(y1 - y0) < 1e-6 or abs(x1 - x0) < 1e-6:     # axis aligned: crisp
            hw = self.lw(w) / 2
            ext = hw if cap else 0
            if abs(y1 - y0) < 1e-6:
                c = self.centre(y0, w)
                return self.m_rect(min(x0, x1) - ext, c - hw, max(x0, x1) + ext, c + hw)
            c = self.centre(x0, w)
            return self.m_rect(c - hw, min(y0, y1) - ext, c + hw, max(y0, y1) + ext)
        w = self.lw(w)
        dx, dy = x1 - x0, y1 - y0
        ll = dx * dx + dy * dy
        t = ((self.x - x0) * dx + (self.y - y0) * dy) / ll
        if cap:
            t = np.clip(t, 0, 1)
            d = (self.x - x0 - t * dx) ** 2 + (self.y - y0 - t * dy) ** 2
            return d <= (w / 2) ** 2
        d = (self.x - x0 - t * dx) ** 2 + (self.y - y0 - t * dy) ** 2
        return (d <= (w / 2) ** 2) & (t >= 0) & (t <= 1)

    def m_polyline(self, pts, w):
        m = np.zeros((self.n, self.n), bool)
        for a, b in zip(pts, pts[1:]):
            m |= self.m_line(a, b, w)
        return m

    def m_capsule_ring(self, p0, p1, r, w):
        (x0, y0), (x1, y1) = p0, p1
        dx, dy = x1 - x0, y1 - y0
        ll = dx * dx + dy * dy or 1e-9
        t = np.clip(((self.x - x0) * dx + (self.y - y0) * dy) / ll, 0, 1)
        d = np.sqrt((self.x - x0 - t * dx) ** 2 + (self.y - y0 - t * dy) ** 2)
        w = self.lw(w)
        return (d <= r) & (d >= r - w)

    # shapes ----------------------------------------------------------------------------------
    def rect(self, x0, y0, x1, y1, colour, alpha=1.0, ol=False):
        self.fill(self.m_rect(x0, y0, x1, y1), colour, alpha, ol)

    def frame(self, x0, y0, x1, y1, w, colour, ol=False):
        w = self.lw(w)
        m = self.m_rect(x0, y0, x1, y1) & ~self.m_rect(x0 + w, y0 + w, x1 - w, y1 - w)
        self.fill(m, colour, ol=ol)

    def circle(self, cx, cy, r, colour, alpha=1.0, ol=False):
        self.fill(self.m_circle(cx, cy, r), colour, alpha, ol)

    def ellipse(self, cx, cy, rx, ry, colour, rot=0.0, ol=False):
        self.fill(self.m_ellipse(cx, cy, rx, ry, rot), colour, ol=ol)

    def ring(self, cx, cy, r, w, colour, ol=False):
        self.fill(self.m_ring(cx, cy, r, w), colour, ol=ol)

    def arc(self, cx, cy, r, w, a0, a1, colour, ol=False):
        self.fill(self.m_ring(cx, cy, r, w) & self.m_angle(cx, cy, a0, a1), colour, ol=ol)

    def poly(self, pts, colour, alpha=1.0, ol=False):
        self.fill(self.m_poly(pts), colour, alpha, ol)

    def line(self, p0, p1, w, colour, alpha=1.0, ol=False, cap=True):
        self.fill(self.m_line(p0, p1, w, cap), colour, alpha, ol)

    def polyline(self, pts, w, colour, ol=False):
        self.fill(self.m_polyline(pts, w), colour, ol=ol)

    def text(self, s, colour, x0, y0, cell=1.0, ol=False, bold=False):
        """Pixel-font text, top left at (x0, y0), one cell = ``cell`` units (hinted to whole pixels); ``bold``
        widens every stroke by one unit."""
        cell = self.lw(cell)
        x0, y0 = self.snap(x0), self.snap(y0)
        m = np.zeros((self.n, self.n), bool)
        x = x0
        for ch in s:
            bits = FONT.get(ch) or FONT.get(ch.upper(), "")
            cw = _FONT_W.get(ch, 5)
            for k, bit in enumerate(bits):
                if bit == "#":
                    r, c = divmod(k, cw)
                    m |= self.m_rect(x + c * cell, y0 + r * cell, x + (c + 1) * cell + (1 if bold else 0),
                                     y0 + (r + 1) * cell)
            x += (cw + 1) * cell
        self.fill(m, colour, ol=ol)

    # result ----------------------------------------------------------------------------------
    def result(self):
        s, ss = self.size, self.ss
        a = self.px[..., 3:4]
        pm = np.concatenate([self.px[..., :3] * a, a], axis=-1).reshape(s, ss, s, ss, 4).mean(axis=(1, 3))
        alpha = pm[..., 3]
        rgb = pm[..., :3] / np.where(alpha > 1e-6, alpha, 1)[..., None]
        if self.outline:     # Maya's dark outline round every shape, one target pixel per 32 px
            r = max(1, round(self.k))
            dil = alpha.copy()
            pad = np.pad(alpha, r)
            for dy in range(-r, r + 1):          # the 1x 3x3 kernel scaled by r (diagonals 0.7)
                for dx in range(-r, r + 1):
                    wgt = 1.0 if (dx == 0 or dy == 0) else 0.7
                    dil = np.maximum(dil, wgt * pad[r + dy:r + dy + s, r + dx:r + dx + s])
            o = np.clip(dil, 0, 1) * 0.92
            na = alpha + o * (1 - alpha)
            safe = np.where(na > 1e-6, na, 1)[..., None]
            rgb = (rgb * alpha[..., None] + np.array(DARK, np.float32) * (o * (1 - alpha))[..., None]) / safe
            alpha = na
        out = np.empty((s, s, 4), np.float32)
        out[..., :3] = np.clip(rgb, 0, 1)
        out[..., 3] = np.clip(alpha, 0, 1)
        return out


# --- shading helpers --------------------------------------------------------------------------

_L = np.array([-0.55, -0.62, 0.56])
_L = _L / np.linalg.norm(_L)


def sphere_colour(cv, cx, cy, r, base, amb=0.62, dif=0.55, spec=0.0, power=20, hl=(1, 1, 1), bands=0):
    """Per-pixel colour of a lit sphere (light from the upper left)."""
    dx, dy = (cv.x - cx) / r, (cv.y - cy) / r
    nz = np.sqrt(np.clip(1 - dx * dx - dy * dy, 0, 1))
    lam = np.clip(dx * _L[0] + dy * _L[1] + nz * _L[2], 0, 1)
    if bands:
        lam = np.floor(lam * bands + 0.5) / bands
    col = np.stack([np.full_like(cv.x, c) for c in base], -1) * (amb + dif * lam)[..., None]
    if spec:
        h = _L + np.array([0, 0, 1.0])
        h = h / np.linalg.norm(h)
        sp = np.clip(dx * h[0] + dy * h[1] + nz * h[2], 0, 1) ** power * spec
        col = col * (1 - sp[..., None]) + np.array(hl, np.float32) * sp[..., None]
    return np.clip(col, 0, 1)


def hgrad(cv, x0, x1, base, lo=0.12, hi=-0.3, bands=0):
    """Horizontal shading across a solid (lighter left, darker right)."""
    t = np.clip((cv.x - x0) / max(x1 - x0, 1e-3), 0, 1)
    if bands:
        t = np.floor(t * bands) / max(bands - 1, 1)
        t = np.clip(t, 0, 1)
    k = lo + (hi - lo) * t
    b = np.array(base, np.float32)
    light = b + (1 - b) * np.clip(k, 0, None)[..., None]
    dark = b * (1 + np.clip(k, None, 0))[..., None]
    return np.where((k >= 0)[..., None], light, dark)


def lerp(p, q, t):
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


# --- shared parts -----------------------------------------------------------------------------

def cube(cv, cx, ty, hw, v, col, wire=0, edge=BLACK, faces=(0.28, 0.0, -0.25)):
    """Iso cube: top face centre (cx, ty), half width ``hw``, vertical edge ``v``. ``wire`` = n x n face grid."""
    hh = hw * 0.55
    top = [(cx, ty - hh), (cx + hw, ty), (cx, ty + hh), (cx - hw, ty)]
    left = [(cx - hw, ty), (cx, ty + hh), (cx, ty + hh + v), (cx - hw, ty + v)]
    right = [(cx, ty + hh), (cx + hw, ty), (cx + hw, ty + v), (cx, ty + hh + v)]
    for quad, k in zip((top, left, right), faces):
        cv.poly(quad, shade(col, k))
    if wire:
        for quad in (top, left, right):
            face_grid(cv, quad, wire, edge)
    return top, left, right


def face_grid(cv, quad, n, colour, w=1.0, border=True):
    a, b, c, d = quad
    for i in range(1, n):
        t = i / n
        cv.line(lerp(a, b, t), lerp(d, c, t), w, colour)
        cv.line(lerp(a, d, t), lerp(b, c, t), w, colour)
    if border:
        cv.polyline([a, b, c, d, a], w, colour)


def plus(cv, cx, cy, s=4.5, w=2.0, col=LIGHT):
    cv.fill(cv.m_line((cx - s, cy), (cx + s, cy), w, cap=False) | cv.m_line((cx, cy - s), (cx, cy + s), w, cap=False),
            col, ol=True)


def xmark(cv, cx, cy, s=4.0, w=2.2, col=LIGHT):
    cv.fill(cv.m_line((cx - s, cy - s), (cx + s, cy + s), w) | cv.m_line((cx + s, cy - s), (cx - s, cy + s), w),
            col, ol=True)


def check(cv, cx, cy, s=4.5, w=2.2, col=LIGHT):
    cv.fill(cv.m_polyline([(cx - s, cy), (cx - s * 0.3, cy + s * 0.7), (cx + s, cy - s * 0.8)], w), col, ol=True)


def nosign(cv, cx, cy, r=5.0, w=1.8, col=LIGHT):
    m = cv.m_ring(cx, cy, r, w) | cv.m_line((cx - r * 0.62, cy + r * 0.62), (cx + r * 0.62, cy - r * 0.62), w)
    cv.fill(m, col, ol=True)


def eye(cv, cx, cy, s=5.5, col=LIGHT):
    cv.fill(cv.m_ellipse(cx, cy, s, s * 0.6), col, ol=True)
    cv.circle(cx, cy, s * 0.38, DARK)
    cv.circle(cx - s * 0.1, cy - s * 0.1, s * 0.13, WHITE)


def link(cv, cx, cy, s=1.0, col=LAV):
    """Maya's chain link (constraints): two rounded links on a diagonal."""
    r, w = 2.4 * s, 1.6 * s
    a0, a1 = (cx - 3.6 * s, cy + 3.6 * s), (cx - 0.8 * s, cy + 0.8 * s)
    b0, b1 = (cx + 0.8 * s, cy - 0.8 * s), (cx + 3.6 * s, cy - 3.6 * s)
    m = cv.m_capsule_ring(a0, a1, r, w) | cv.m_capsule_ring(b0, b1, r, w)
    m |= cv.m_line((cx - 1.4 * s, cy + 1.4 * s), (cx + 1.4 * s, cy - 1.4 * s), w)
    cv.fill(m, col, ol=True)


def key_bar(cv, cx, cy, h=14.0, line=11.0, w=4.0, col=KEY):
    """Maya's key: an orange-red bar across a grey time line."""
    cv.line((cx - line, cy), (cx + line, cy), 2.0, LIGHT, ol=True, cap=False)
    cv.rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, col, ol=True)


def checker(cv, x0, y0, s=9.0, n=3):
    cv.rect(x0 - 1, y0 - 1, x0 + s + 1, y0 + s + 1, DARK)
    c = s / n
    for i in range(n):
        for j in range(n):
            cv.rect(x0 + i * c, y0 + j * c, x0 + (i + 1) * c, y0 + (j + 1) * c, WHITE if (i + j) % 2 == 0 else BLACK)


def target(cv, cx, cy, r=5.5):
    cv.circle(cx, cy, r, LIGHT, ol=True)
    cv.ring(cx, cy, r * 0.68, 1.0, DARK)
    cv.circle(cx, cy, r * 0.28, DARK)


def snowflake(cv, cx, cy, r, col=LIGHT, w=1.6, ol=True):
    m = np.zeros((cv.n, cv.n), bool)
    for a in (90, 30, 150):
        ra = math.radians(a)
        m |= cv.m_line((cx - r * math.cos(ra), cy - r * math.sin(ra)), (cx + r * math.cos(ra), cy + r * math.sin(ra)), w)
    for a in range(0, 360, 60):
        ra = math.radians(a + 90)
        tip = (cx + r * 0.62 * math.cos(ra), cy + r * 0.62 * math.sin(ra))
        for da in (-50, 50):
            rb = ra + math.radians(da)
            m |= cv.m_line(tip, (tip[0] + r * 0.35 * math.cos(rb), tip[1] + r * 0.35 * math.sin(rb)), w * 0.8)
    cv.fill(m, col, ol=ol)


def arrow(cv, p0, p1, w=2.4, col=LIGHT, head=4.5, ol=True):
    """A short thick arrow with a solid triangular head at ``p1``."""
    (x0, y0), (x1, y1) = p0, p1
    d = math.hypot(x1 - x0, y1 - y0) or 1
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    bx, by = x1 - ux * head, y1 - uy * head
    m = cv.m_line(p0, (bx + ux * 0.5, by + uy * 0.5), w, cap=False)
    m |= cv.m_poly([(x1, y1), (bx - uy * head * 0.75, by + ux * head * 0.75), (bx + uy * head * 0.75, by - ux * head * 0.75)])
    cv.fill(m, col, ol=ol)


def curved_arrow(cv, cx, cy, r, a0, a1, w=2.4, col=LIGHT, head=4.5, ol=True):
    """An arc from a0 to a1 (degrees, clockwise on screen) with a head at a1."""
    m = cv.m_ring(cx, cy, r + w / 2, w) & cv.m_angle(cx, cy, a0, a1 - 8)
    ra = math.radians(a1)
    tip = (cx + r * math.cos(ra), cy + r * math.sin(ra))
    tx, ty = -math.sin(ra), math.cos(ra)          # clockwise tangent
    nx, ny = math.cos(ra), math.sin(ra)
    base = (tip[0] - tx * head, tip[1] - ty * head)
    m |= cv.m_poly([(tip[0] + tx * 0.6, tip[1] + ty * 0.6), (base[0] + nx * head * 0.8, base[1] + ny * head * 0.8),
                    (base[0] - nx * head * 0.8, base[1] - ny * head * 0.8)])
    cv.fill(m, col, ol=ol)


def cv_box(cv, x, y, s=3.0, col=LIGHT, fill=None):
    if fill is not None:
        cv.rect(x - s / 2, y - s / 2, x + s / 2, y + s / 2, fill)
    cv.frame(x - s / 2, y - s / 2, x + s / 2, y + s / 2, 1.0, col)


def wave_pts(x0, x1, yc, amp, cycles=1.0, phase=0.0, n=40):
    return [(x0 + (x1 - x0) * t, yc - amp * math.sin(2 * math.pi * cycles * t + phase)) for t in np.linspace(0, 1, n)]


def bezier(p0, p1, p2, p3, n=40):
    out = []
    for t in np.linspace(0, 1, n):
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


S_CURVE = bezier((4, 26), (8, 2), (24, 30), (28, 5))


def pencil(cv, tip, end, w=5.0, col=LIGHT, lead=DARK):
    (x0, y0), (x1, y1) = tip, end
    d = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    px, py = -uy * w / 2, ux * w / 2
    cone = 5.0
    b = (x0 + ux * cone, y0 + uy * cone)
    body = [(b[0] + px, b[1] + py), (x1 + px, y1 + py), (x1 - px, y1 - py), (b[0] - px, b[1] - py)]
    cv.poly(body, col, ol=True)
    cv.poly([tip, (b[0] + px, b[1] + py), (b[0] - px, b[1] - py)], shade(col, -0.25), ol=True)
    cv.poly([tip, lerp(tip, (b[0] + px, b[1] + py), 0.4), lerp(tip, (b[0] - px, b[1] - py), 0.4)], lead)


def brush(cv, tip, end, w=3.0, col=LIGHT, bristle=None):
    """A paint brush: handle from ``end`` to a ferrule and a pointed tuft at ``tip``."""
    (x0, y0), (x1, y1) = tip, end
    d = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    px, py = -uy, ux
    f = (x0 + ux * 7, y0 + uy * 7)
    cv.line(f, end, w, col, ol=True)
    tuft = [tip, (f[0] + px * 2.6, f[1] + py * 2.6), (f[0] + ux * 1.5 + px * 2.2, f[1] + uy * 1.5 + py * 2.2),
            (f[0] + ux * 1.5 - px * 2.2, f[1] + uy * 1.5 - py * 2.2), (f[0] - px * 2.6, f[1] - py * 2.6)]
    cv.poly(tuft, bristle or shade(col, -0.2), ol=True)


def blade(cv, p0, p1, w=5.0, col=LIGHT):
    """A knife: a pointed blade at ``p0`` and a darker handle at ``p1``."""
    (x0, y0), (x1, y1) = p0, p1
    d = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    px, py = -uy * w / 2, ux * w / 2
    mid = (x0 + ux * d * 0.62, y0 + uy * d * 0.62)
    cv.poly([p0, (mid[0] + px * 2, mid[1] + py * 2), (mid[0], mid[1])], col, ol=True)
    cv.poly([p0, (mid[0], mid[1]), (mid[0] - px * 0.2, mid[1] - py * 0.2)], col)
    cv.line(mid, p1, w * 0.9, shade(col, -0.35), ol=True)


def window(cv, x0, y0, x1, y1, col, body=None, title=None):
    """An editor window: frame + title bar with three dots, ``body`` drawn inside."""
    cv.rect(x0, y0, x1, y1, col)
    cv.rect(x0, y0, x1, y0 + 5, title or shade(col, -0.45))
    for i in range(3):
        cv.rect(x0 + 2 + i * 3, y0 + 2, x0 + 3 + i * 3, y0 + 3, LIGHT)
    if body is not None:
        body(x0 + 2, y0 + 7, x1 - 2, y1 - 2)


def human(cv, cx, cy, s=1.0, col=LIGHT, joints=None, ol=True):
    """A standing figure, arms out (Maya's character icons)."""
    m = cv.m_circle(cx, cy - 9.5 * s, 3.0 * s)
    m |= cv.m_rect(cx - 3.2 * s, cy - 5.5 * s, cx + 3.2 * s, cy + 3.5 * s)
    m |= cv.m_rect(cx - 10 * s, cy - 5.5 * s, cx + 10 * s, cy - 2.5 * s)
    m |= cv.m_rect(cx - 3.2 * s, cy + 2 * s, cx - 0.6 * s, cy + 12 * s)
    m |= cv.m_rect(cx + 0.6 * s, cy + 2 * s, cx + 3.2 * s, cy + 12 * s)
    cv.fill(m, col, ol=ol)
    if joints:
        for p in ((cx, cy - 4), (cx - 8.5 * s, cy - 4 * s), (cx + 8.5 * s, cy - 4 * s), (cx - 2 * s, cy + 10 * s),
                  (cx + 2 * s, cy + 10 * s), (cx, cy + 2 * s)):
            cv.circle(p[0], p[1], 1.4 * s, joints)


def shirt(cv, cx, cy, s=1.0, col=SALMON, ol=False):
    p = [(-4, -10), (-1.5, -8.5), (1.5, -8.5), (4, -10), (12, -6), (9, 0), (6, -1.5), (6, 10), (-6, 10), (-6, -1.5),
         (-9, 0), (-12, -6)]
    pts = [(cx + a * s, cy + b * s) for a, b in p]
    cv.poly(pts, col, ol=ol)
    return pts


def film_strip(cv, x0, y0, x1, y1, col, cells=3, cell_col=None):
    """Maya's cache: a coloured film strip with sprocket holes and light frames."""
    cv.rect(x0, y0, x1, y1, col)
    h = y1 - y0
    n = int((x1 - x0) // 3)
    for i in range(n):
        x = x0 + 1 + i * 3
        cv.rect(x, y0 + 1, x + 1.5, y0 + 2.5, DARK)
        cv.rect(x, y1 - 2.5, x + 1.5, y1 - 1, DARK)
    if cells:
        cw = (x1 - x0 - 2) / cells
        for i in range(cells):
            cv.rect(x0 + 1.5 + i * cw, y0 + 3.5, x0 + i * cw + cw + 0.5, y1 - 3.5, cell_col or shade(col, 0.55))
    return h


def film_frame(cv, x0, y0, x1, y1, col):
    """A single upright film frame with sprocket holes down both sides."""
    cv.rect(x0, y0, x1, y1, col)
    for y in np.arange(y0 + 1.5, y1 - 2, 3):
        cv.rect(x0 + 1, y, x0 + 2.5, y + 1.5, DARK)
        cv.rect(x1 - 2.5, y, x1 - 1, y + 1.5, DARK)
    cv.rect(x0 + 3.5, y0 + 2, x1 - 3.5, y1 - 2, shade(col, -0.55))


def clapper(cv, x0, y0, x1, y1, col=LIGHT):
    """A clapperboard: striped hinged bar on a board."""
    cv.rect(x0, y0 + 4, x1, y1, col, ol=True)
    cv.poly([(x0, y0 + 1), (x1 - 1, y0 - 1.5), (x1, y0 + 2.5), (x0, y0 + 4)], col, ol=True)
    for i in range(4):
        x = x0 + 2 + i * (x1 - x0 - 3) / 4
        cv.line((x, y0 + 3.5), (x + 2, y0 + 0.2), 1.3, DARK)


def stack(cv, x0, y0, w, h, col, n=3, step=2.5):
    """Maya's batch: offset stack of cards (back to front)."""
    for i in range(n - 1, -1, -1):
        cv.rect(x0 + i * step, y0 - i * step, x0 + w + i * step, y0 + h - i * step, shade(col, -0.12 * i), ol=True)


def hair(cv, x0, y0, n=3, col=SALMON, h=18, lean=6, gap=4.0, w=1.6):
    for i in range(n):
        x = x0 + i * gap
        cv.polyline(bezier((x, y0), (x, y0 - h * 0.5), (x + lean * 0.3, y0 - h * 0.8), (x + lean, y0 - h), 20), w, col, ol=True)


def letter_disc(cv, cx, cy, r, ch, col, letter=DARK, ring=None):
    """Maya's hair-state letters: a big C / S / R on a disc (5x7 font at two units per cell)."""
    cv.circle(cx, cy, r, col, ol=True)
    if ring:
        cv.ring(cx, cy, r, 1.0, ring)
    cv.text(ch, letter, cx - 5.5, cy - 7, cell=2.0, bold=True)


def squiggle(cv, x0, y0, x1, y1, col=SALMON, w=1.6):
    cv.polyline(bezier((x0, y0), (x0 + (x1 - x0) * 0.6, y0 - 6), (x0 + (x1 - x0) * 0.2, y1 + 6), (x1, y1), 24), w, col, ol=True)


def ball(cv, cx=15, cy=17, r=12.5, col=ORANGE):
    """Maya's sculpt brushes: a lit orange ball."""
    cv.fill(cv.m_circle(cx, cy, r), sphere_colour(cv, cx, cy, r, col, amb=0.78, dif=0.32, bands=3))


def mat_ball(cv, base, spec=0.0, power=20, amb=0.5, dif=0.75, hl=(1, 1, 1), r=13.0):
    cv.fill(cv.m_circle(16, 16, r), sphere_colour(cv, 16, 16, r, base, amb=amb, dif=dif, spec=spec, power=power, hl=hl))


# --- icons ------------------------------------------------------------------------------------

ICONS = {}


def icon(*keys):
    def deco(fn):
        for k in keys:
            ICONS[k] = fn
        return fn
    return deco


# Curves, Surfaces ----------------------------------------------------------------------------------

@icon("Curves/NURBS Circle")
def i_nurbs_circle(cv):
    cv.ring(16, 16, 12.5, 2.0, BLUE)


@icon("Curves/NURBS Square")
def i_nurbs_square(cv):
    cv.frame(5, 5, 27, 27, 2.0, BLUE)


@icon("Curves/EP Curve Tool")
def i_ep_curve(cv):
    cv.polyline(S_CURVE, 1.6, BLUE)
    for t in (0, 13, 26, 39):
        cv_box(cv, *S_CURVE[t], s=4, col=LIGHT, fill=DARK)


@icon("Curves/Pencil Curve Tool")
def i_pencil_curve(cv):
    cv.polyline(bezier((3, 28), (6, 14), (14, 30), (16, 18), 24), 2.0, BLUE)
    pencil(cv, (15, 18), (29, 4))


@icon("Curves/Three Point Circular Arc")
def i_three_arc(cv):
    cv.arc(16, 20, 12, 2.0, 180, 360, BLUE)
    for p in ((5, 20), (16, 9), (27, 20)):
        cv_box(cv, *p, s=4, fill=DARK)
    cv.rect(15, 19, 17, 21, LIGHT)


@icon("Curves/Attach Curves")
def i_attach_curves(cv):
    cv.polyline(bezier((3, 22), (6, 8), (12, 8), (16, 16), 20), 2.0, BLUE)
    cv.polyline(bezier((16, 16), (20, 24), (26, 24), (29, 10), 20), 2.0, shade(BLUE, 0.3))
    cv.rect(13.5, 13.5, 18.5, 18.5, LIGHT, ol=True)


@icon("Curves/Detach Curves")
def i_detach_curves(cv):
    cv.polyline(bezier((3, 26), (6, 10), (11, 10), (13, 16), 16), 2.0, BLUE)
    cv.polyline(bezier((19, 16), (21, 22), (26, 22), (29, 6), 16), 2.0, BLUE)
    blade(cv, (10, 26), (27, 3), w=4)


@icon("Curves/Insert Knot")
def i_insert_knot(cv):
    cv.polyline(wave_pts(3, 29, 16, 7, 1.0), 2.0, BLUE)
    cv_box(cv, 16, 16, s=6, col=LIGHT, fill=DARK)


@icon("Curves/Extend Curve")
def i_extend_curve(cv):
    cv.polyline(bezier((3, 26), (5, 10), (14, 26), (17, 15), 20), 2.0, BLUE)
    arrow(cv, (17, 15), (29, 4), w=2.4, head=6)


@icon("Curves/Offset Curve")
def i_offset_curve(cv):
    cv.arc(20, 20, 16, 2.0, 180, 270, BLUE)
    cv.arc(20, 20, 9.5, 2.0, 180, 270, shade(BLUE, 0.35))
    cv.line((4, 20), (11, 20), 1.0, LIGHT)


@icon("Curves/Rebuild Curve")
def i_rebuild_curve(cv):
    pts = [(4, 27), (9, 19), (6, 12), (12, 5), (19, 9), (17, 17), (24, 22), (28, 14)]
    cv.polyline(pts, 1.6, BLUE)
    for p in pts:
        cv_box(cv, *p, s=3.6, fill=DARK)


@icon("Curves/Add Points Tool")
def i_add_points(cv):
    pts = bezier((3, 6), (14, 4), (10, 22), (20, 22), 20)
    cv.polyline(pts, 2.0, BLUE)
    for p in (pts[0], pts[10]):
        cv_box(cv, *p, s=4, fill=DARK)
    for t in np.linspace(0, 1, 3):
        cv.rect(20 + 5 * t - 0.5, 22 + 2 * t - 0.5, 20 + 5 * t + 0.5, 22 + 2 * t + 0.5, LIGHT)
    cv_box(cv, 27, 25, s=4.5, col=WHITE, fill=BLUE)
    plus(cv, 25, 8, s=3.5, w=2)


@icon("Curves/Curve Editing Tool")
def i_curve_edit(cv):
    cv.polyline(bezier((3, 24), (10, 4), (20, 30), (29, 6), 30), 2.0, BLUE)
    cv.line((4, 28), (28, 4), 1.0, LIGHT)
    cv.circle(16, 16, 2.6, LIGHT, ol=True)
    cv_box(cv, 6, 26, s=3.5, fill=DARK)
    cv_box(cv, 26, 6, s=3.5, fill=DARK)


@icon("Curves/Bezier Curve Tool")
def i_bezier(cv):
    cv.polyline(bezier((3, 26), (8, 6), (24, 6), (29, 26), 30), 2.0, BLUE)
    cv.line((5, 6), (27, 6), 1.0, LIGHT)
    cv.circle(16, 11, 2.0, LIGHT, ol=True)
    for p in ((5, 6), (27, 6)):
        cv_box(cv, *p, s=4, fill=DARK)


@icon("Surfaces/NURBS Sphere")
def i_nurbs_sphere(cv):
    cv.fill(cv.m_circle(16, 16, 13.5), sphere_colour(cv, 16, 16, 13.5, BLUE, amb=0.72, dif=0.45))


@icon("Surfaces/NURBS Cube")
def i_nurbs_cube(cv):
    cube(cv, 16, 9.5, 12.5, 14, BLUE)


def cylinder(cv, cx, top, bot, rx, ry, col, wire=0, edge=BLACK, smooth=True):
    body = cv.m_rect(cx - rx, top, cx + rx, bot) | cv.m_ellipse(cx, bot, rx, ry)
    cv.fill(body, hgrad(cv, cx - rx, cx + rx, col, 0.18, -0.32, bands=0 if smooth else max(wire, 4)))
    cv.fill(cv.m_ellipse(cx, top, rx, ry), shade(col, 0.32))
    if wire:
        for i in range(1, wire):
            x = cx - rx * math.cos(math.pi * i / wire)
            dy = ry * math.sin(math.pi * i / wire)
            cv.line((x, top + dy), (x, bot + dy), 1.0, edge)
        cv.fill(cv.m_ering(cx, top, rx, ry, 1.0), edge)
        cv.fill(cv.m_ering(cx, bot, rx, ry, 1.0) & (cv.y > bot), edge)


@icon("Surfaces/NURBS Cylinder")
def i_nurbs_cylinder(cv):
    cylinder(cv, 16, 8, 24, 11.5, 5, BLUE)


def cone(cv, cx, top, bot, rx, ry, col, wire=0, edge=BLACK, smooth=True):
    body = cv.m_poly([(cx, top), (cx + rx, bot), (cx - rx, bot)]) | (cv.m_ellipse(cx, bot, rx, ry) & (cv.y >= bot))
    cv.fill(body, hgrad(cv, cx - rx, cx + rx, col, 0.18, -0.32, bands=0 if smooth else max(wire, 4)))
    if wire:
        for i in range(1, wire):
            a = math.pi * i / wire
            cv.line((cx, top), (cx - rx * math.cos(a), bot + ry * math.sin(a)), 1.0, edge)


@icon("Surfaces/NURBS Cone")
def i_nurbs_cone(cv):
    cone(cv, 16, 3, 24, 12, 5, BLUE)


@icon("Surfaces/NURBS Plane")
def i_nurbs_plane(cv):
    cv.poly([(16, 4), (29, 16), (16, 28), (3, 16)], BLUE)
    cv.poly([(16, 4), (29, 16), (16, 16)], shade(BLUE, 0.15))


def torus(cv, cx, cy, rx, ry, rot, col, hole=0.45, wire=0, edge=BLACK):
    outer = cv.m_ellipse(cx, cy, rx, ry, rot)
    inner = cv.m_ellipse(cx, cy, rx * hole, ry * hole, rot)
    cv.fill(outer & ~inner, sphere_colour(cv, cx, cy, max(rx, ry), col, amb=0.75, dif=0.45, bands=0 if not wire else 3))
    if wire:
        body = outer & ~inner
        m = cv.m_ering(cx, cy, rx * (1 + hole) / 2 + 0.5, ry * (1 + hole) / 2 + 0.5, 1.0, rot)
        cr, sr = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        for k in range(wire):
            a = 2 * math.pi * k / wire
            ex, ey = math.cos(a), math.sin(a)
            p0 = (cx + (rx * ex * cr - ry * ey * sr) * hole, cy + (rx * ex * sr + ry * ey * cr) * hole)
            p1 = (cx + rx * ex * cr - ry * ey * sr, cy + rx * ex * sr + ry * ey * cr)
            m |= cv.m_line(p0, p1, 1.0)
        m |= cv.m_ering(cx, cy, rx * hole + 1, ry * hole + 1, 1.0, rot)
        cv.fill(m & body, edge)


@icon("Surfaces/NURBS Torus")
def i_nurbs_torus(cv):
    torus(cv, 16, 16, 13.5, 7.5, -55, BLUE, hole=0.42)


@icon("Surfaces/Revolve")
def i_revolve(cv):
    cup = [(9, 4), (23, 4), (22, 10), (18, 15), (17, 20), (21, 23), (11, 23), (15, 20), (14, 15), (10, 10)]
    cv.poly(cup, BLUE)
    cv.poly([(16, 4), (23, 4), (22, 10), (18, 15), (17, 20), (21, 23), (16, 23)], shade(BLUE, -0.25))
    cv.fill(cv.m_ering(16, 4, 7, 2, 1.0), shade(BLUE, 0.35))
    curved_arrow(cv, 16, 22, 11, 20, 160, w=2.2, head=4.5)


@icon("Surfaces/Loft")
def i_loft(cv):
    """Maya's loft (skin): upright S-shaped ribbons lofted through the profile curves."""
    for k, col in ((0, shade(BLUE, -0.2)), (1, BLUE)):
        x = 6 + k * 10
        left = bezier((x + 4, 3), (x - 6, 10), (x + 10, 20), (x, 29), 30)
        right = [(px + 7, py) for px, py in left]
        cv.poly(left + right[::-1], col, ol=True)
        cv.polyline([lerp(a, b, 0.5) for a, b in zip(left, right)], 1.0, shade(BLUE, 0.45))


@icon("Surfaces/Planar")
def i_planar(cv):
    cv.poly([(16, 3), (29, 16), (16, 29), (3, 16)], BLUE)
    cv.circle(16, 16, 6.5, shade(BLUE, 0.45))
    cv.ring(16, 16, 6.5, 1.6, LIGHT)


@icon("Surfaces/Extrude")
def i_extrude_curve(cv):
    cv.line((8, 24), (21, 11), 10, BLUE, cap=False)
    cv.fill(cv.m_line((8, 24), (21, 11), 10, cap=False) & (cv.x + cv.y > 32.5), shade(BLUE, -0.3))
    cv.ellipse(21, 11, 6.5, 4.0, shade(BLUE, 0.35), rot=-45)
    cv.fill(cv.m_ering(21, 11, 6.5, 4.0, 1.6, rot=-45), LIGHT)
    cv.ellipse(8, 24, 6.5, 4.0, shade(BLUE, -0.3), rot=-45)


@icon("Surfaces/Birail 1 Tool")
def i_birail(cv):
    a = bezier((3, 27), (6, 12), (14, 6), (29, 4), 24)
    b = bezier((3, 27), (14, 26), (22, 20), (29, 4), 24)
    cv.poly(a + b[::-1], BLUE)
    cv.polyline([lerp(p, q, 0.5) for p, q in zip(a, b)], 1.0, shade(BLUE, 0.4))
    cv.polyline(a, 1.6, LIGHT)
    cv.polyline(b, 1.6, LIGHT)


@icon("Surfaces/Bevel Plus")
def i_bevel_plus(cv):
    cube(cv, 16, 10, 12.5, 13, BLUE)
    cv.poly([(16, 4.0), (24, 8.5), (16, 13.5), (8, 8.5)], shade(BLUE, 0.5))
    cv.polyline([(8, 8.5), (16, 13.5), (24, 8.5)], 1.0, LIGHT)
    cv.line((16, 13.5), (16, 26), 1.0, LIGHT)


@icon("Surfaces/Project Curve on Surface")
def i_project_curve(cv):
    cv.rect(3, 9, 23, 29, BLUE)
    cv.poly([(3, 9), (23, 9), (3, 29)], shade(BLUE, 0.12))
    cv.ring(22, 10, 7.5, 2.0, LIGHT, ol=True)
    cv.fill(cv.m_ring(22, 10, 7.5, 2.0) & cv.m_rect(3, 9, 23, 29), shade(LIGHT, 0.3))


@icon("Surfaces/Intersect Surfaces")
def i_intersect(cv):
    cv.rect(3, 11, 21, 29, BLUE)
    cv.fill(cv.m_circle(21, 11, 8.5), sphere_colour(cv, 21, 11, 8.5, BLUE, amb=0.8, dif=0.4))
    cv.fill(cv.m_ring(21, 11, 8.5, 1.4) & cv.m_rect(3, 11, 21, 29), LIGHT)


@icon("Surfaces/Trim Tool")
def i_trim(cv):
    cv.rect(3, 7, 25, 29, BLUE)
    cv.erase(cv.m_circle(22, 10, 7))
    m = cv.m_ring(22, 10, 7, 1.6) & ((np.floor(np.degrees(np.arctan2(cv.y - 10, cv.x - 22)) / 30) % 2) == 0)
    cv.fill(m, LIGHT)


@icon("Surfaces/Untrim Surfaces")
def i_untrim(cv):
    cv.rect(3, 7, 25, 29, BLUE)
    cv.fill(cv.m_circle(22, 10, 7), shade(LIGHT, 0.0), ol=True)
    m = cv.m_ring(22, 10, 7, 1.0) & ((np.floor(np.degrees(np.arctan2(cv.y - 10, cv.x - 22)) / 30) % 2) == 0)
    cv.fill(m, DARK)


@icon("Surfaces/Attach Surfaces")
def i_attach_surfaces(cv):
    cv.poly([(3, 17), (15, 5), (19, 9), (7, 21)], BLUE)
    cv.poly([(13, 23), (25, 11), (29, 15), (17, 27)], shade(BLUE, -0.15))
    cv.poly([(7, 21), (19, 9), (25, 11), (13, 23)], LIGHT)


@icon("Surfaces/Detach Surfaces")
def i_detach_surfaces(cv):
    cv.poly([(2, 15), (13, 4), (19, 10), (8, 21)], BLUE)
    cv.poly([(13, 24), (24, 13), (30, 19), (19, 30)], shade(BLUE, -0.15))


@icon("Surfaces/Open/Close Surfaces")
def i_open_close(cv):
    cv.line((7, 25), (17, 15), 10, BLUE, cap=False)
    cv.ellipse(7, 25, 6.5, 4, shade(BLUE, -0.3), rot=-45)
    m = cv.m_ring(21, 11, 8, 3.0) & ~cv.m_angle(21, 11, 300, 350)
    cv.fill(m, LIGHT, ol=True)


@icon("Surfaces/Insert Isoparms")
def i_insert_isoparms(cv):
    cv.poly([(18, 6), (30, 18), (18, 30), (6, 18)], BLUE)
    cv.line((12, 12), (24, 24), 1.0, shade(BLUE, 0.5))
    arrow(cv, (3, 3), (14, 14), w=2.6, head=6)


@icon("Surfaces/Extend Surfaces")
def i_extend_surfaces(cv):
    cv.poly([(18, 6), (30, 18), (18, 30), (6, 18)], BLUE)
    arrow(cv, (14, 14), (3, 3), w=2.6, head=6)


@icon("Surfaces/Rebuild Surfaces")
def i_rebuild_surfaces(cv):
    for i, (h, col) in enumerate(((8, LIGHT), (13, BLUE), (10, LIGHT), (19, BLUE), (24, shade(BLUE, 0.2)))):
        x = 3 + i * 5.5
        cv.rect(x, 28 - h, x + 4, 28, col, ol=True)


@icon("Surfaces/Sculpt Geometry Tool")
def i_sculpt_geometry(cv):
    m = cv.m_circle(14, 15, 12) & (cv.y >= 15)
    cv.fill(m, sphere_colour(cv, 14, 15, 12, BLUE, amb=0.8, dif=0.4))
    cv.fill(cv.m_ellipse(14, 15, 12, 3.5), shade(BLUE, 0.35))
    brush(cv, (14, 14), (29, 2), w=3)


@icon("Surfaces/Surface Editing Tool")
def i_surface_edit(cv):
    cv.poly([(3, 20), (17, 6), (29, 12), (15, 26)], BLUE)
    cv.poly([(3, 20), (17, 6), (16, 16)], shade(BLUE, 0.15))
    cv.line((2, 29), (29, 3), 1.0, LIGHT)
    cv.circle(16, 16, 2.6, LIGHT, ol=True)


# Poly Modeling -----------------------------------------------------------------------------------

@icon("Polygons/Polygon Sphere")
def i_poly_sphere(cv):
    cv.fill(cv.m_circle(16, 16, 13.5), sphere_colour(cv, 16, 16, 13.5, ORANGE, amb=0.8, dif=0.35, bands=3))
    inside = cv.m_circle(16, 16, 13.0)
    m = np.zeros_like(inside)
    for k in (-7.5, 0, 7.5):
        m |= cv.m_line((2, 16 + k), (30, 16 + k), 1.0)
    for rx in (5.0, 10.5):
        m |= cv.m_ering(16, 16, rx, 13.5, 1.0)
    m |= cv.m_line((16, 2), (16, 30), 1.0)
    cv.fill(m & inside, BLACK)


@icon("Polygons/Polygon Cube")
def i_poly_cube(cv):
    cube(cv, 16, 9.5, 12.5, 14, ORANGE, wire=2)


@icon("Polygons/Polygon Cylinder")
def i_poly_cylinder(cv):
    cylinder(cv, 16, 7.5, 24, 11.5, 4.5, ORANGE, wire=4, smooth=False)


@icon("Polygons/Polygon Cone")
def i_poly_cone(cv):
    cone(cv, 16, 3, 24, 12, 4.5, ORANGE, wire=4, smooth=False)
    cv.fill(cv.m_ering(16, 24, 12, 4.5, 1.0) & (cv.y > 24), BLACK)


@icon("Polygons/Polygon Torus")
def i_poly_torus(cv):
    torus(cv, 16, 16, 13.5, 8.5, -35, ORANGE, hole=0.42, wire=8)


@icon("Polygons/Polygon Plane")
def i_poly_plane(cv):
    q = [(16, 4), (29, 16), (16, 28), (3, 16)]
    cv.poly(q, ORANGE)
    face_grid(cv, q, 2, BLACK)


@icon("Polygons/Polygon Disc")
def i_poly_disc(cv):
    cv.ellipse(16, 18, 13.5, 6.5, shade(ORANGE, -0.3))
    cv.ellipse(16, 16, 13.5, 6.5, ORANGE)
    for k in range(4):
        a = math.pi * k / 4
        cv.line((16 - 13 * math.cos(a), 16 - 6.2 * math.sin(a)), (16 + 13 * math.cos(a), 16 + 6.2 * math.sin(a)), 1.0, BLACK)


@icon("Polygons/Platonic Solid")
def i_platonic(cv):
    pts = [(16 + 13 * math.cos(math.radians(a)), 16 + 13 * math.sin(math.radians(a))) for a in range(-90, 270, 72)]
    inner = [(16 + 6.5 * math.cos(math.radians(a)), 16 + 6.5 * math.sin(math.radians(a))) for a in range(-54, 306, 72)]
    cv.poly(pts, ORANGE)
    cv.poly(inner, shade(ORANGE, 0.25))
    cv.poly([pts[1], pts[2], inner[1]], shade(ORANGE, -0.25))
    cv.poly([pts[2], pts[3], inner[2]], shade(ORANGE, -0.15))
    cv.polyline(inner + [inner[0]], 1.0, BLACK)
    for i in range(5):
        cv.line(inner[i], pts[(i + 1) % 5], 1.0, BLACK)


@icon("Polygons/Super Ellipse")
def i_super_shape(cv):
    t = np.linspace(0, 2 * math.pi, 80)
    pts = [(16 + 14 * math.copysign(abs(math.cos(a)) ** 3, math.cos(a)), 16 + 14 * math.copysign(abs(math.sin(a)) ** 3, math.sin(a)))
           for a in t]
    cv.poly(pts, ORANGE)
    cv.fill(cv.m_poly(pts) & (cv.x + cv.y > 32), shade(ORANGE, -0.22))


@icon("Polygons/Sweep Mesh")
def i_sweep(cv):
    """Maya's sweep: an orange ribbon spiralling down (back halves darker)."""
    for k in range(3):
        cx, cy = 13 + k * 3, 8 + k * 8
        band = cv.m_ering(cx, cy, 11, 5, 3.5)
        cv.fill(band & (cv.y < cy), shade(ORANGE, -0.35))
    for k in range(3):
        cx, cy = 13 + k * 3, 8 + k * 8
        band = cv.m_ering(cx, cy, 11, 5, 3.5)
        cv.fill(band & (cv.y >= cy), ORANGE)
        cv.fill(cv.m_ering(cx, cy, 11, 5, 1.0) & (cv.y >= cy), BLACK)


@icon("Polygons/Polygon Type")
def i_poly_type(cv):
    cv.rect(5, 4, 27, 8, ORANGE)
    cv.rect(13.5, 4, 18.5, 26, ORANGE)
    cv.rect(10, 25, 22, 28, ORANGE)
    cv.rect(5, 4, 7, 11, ORANGE)
    cv.rect(25, 4, 27, 11, ORANGE)
    cv.rect(17, 8, 18.5, 25, shade(ORANGE, -0.25))


@icon("Polygons/SVG")
def i_svg(cv):
    cv.rect(3, 8, 29, 24, ORANGE)
    cv.text("svg", BLACK, 6, 13)


def _content_tiles(cv, col):
    def body(x0, y0, x1, y1):
        cv.rect(x0, y0, x1, y1, shade(col, -0.5))
        w, h = (x1 - x0 - 1) / 3, (y1 - y0 - 1) / 2
        for i in range(3):
            for j in range(2):
                cv.rect(x0 + 1 + i * w, y0 + 1 + j * h, x0 + i * w + w, y0 + j * h + h, shade(col, 0.15))
    return body


@icon("Polygons/Content Browser", "Sculpting/Base Meshes")
def i_content_browser(cv):
    window(cv, 3, 4, 29, 28, TEAL, _content_tiles(cv, TEAL))


@icon("Polygons/Center Pivot")
def i_center_pivot(cv):
    cv.ring(16, 16, 11, 2.0, LIGHT)
    for a in (90, 210, 330):
        ra = math.radians(a)
        cv.line((16 + 4 * math.cos(ra), 16 + 4 * math.sin(ra)), (16 + 13.5 * math.cos(ra), 16 + 13.5 * math.sin(ra)), 2.4, LIGHT)
    cv.circle(16, 16, 3.5, TEAL, ol=True)


@icon("Polygons/Delete By Type: History")
def i_delete_history(cv):
    for y in (17, 22, 27):
        cv.rect(12, y - 1, 29, y + 1, LIGHT, ol=True)
    cv.circle(11, 11, 8.5, TEAL, ol=True)
    cv.circle(11, 11, 6.5, shade(TEAL, 0.55))
    cv.line((11, 11), (11, 6), 1.4, DARK)
    cv.line((11, 11), (14.5, 11), 1.4, DARK)
    xmark(cv, 25, 25, s=3.5)


@icon("Polygons/Freeze Transformations")
def i_freeze_transform(cv):
    snowflake(cv, 16, 10, 8.5)
    cv.text("o,o,o", TEAL, 5, 22)


@icon("Polygons/Combine")
def i_combine(cv):
    cv.ring(16, 16, 14, 2.0, LIGHT)
    for k, col in ((0, shade(ORANGE, -0.25)), (1, ORANGE)):
        y = 20 - k * 6
        cv.poly([(16, y - 6), (25, y), (16, y + 6), (7, y)], col)
        cv.polyline([(16, y - 6), (25, y), (16, y + 6), (7, y), (16, y - 6)], 1.0, BLACK)


@icon("Polygons/Extract")
def i_extract(cv):
    for i, j in ((0, 1), (1, 1), (0, 0)):
        cv.rect(3 + i * 9, 12 + j * 9, 11 + i * 9, 20 + j * 9, LIGHT, ol=True)
    cv.rect(18, 3, 28, 13, ORANGE, ol=True)
    arrow(cv, (13, 17), (18, 12), w=1.6, head=3.5)


@icon("Polygons/Mirror")
def i_mirror(cv):
    cv.poly([(3, 9), (13, 6), (13, 26), (3, 23)], ORANGE)
    cv.poly([(29, 9), (19, 6), (19, 26), (29, 23)], shade(ORANGE, -0.25))
    for y in range(2, 30, 5):
        cv.rect(15.5, y, 16.5, y + 3, LIGHT)


@icon("Polygons/Smooth")
def i_poly_smooth(cv):
    for i, j in ((0, 2), (1, 2), (0, 1)):
        cv.rect(3 + i * 7, 9 + j * 7, 9 + i * 7, 15 + j * 7, LIGHT, ol=True)
    m = cv.m_circle(20, 13, 10) & (cv.x >= 12) & (cv.y <= 21)
    cv.fill(cv.m_circle(20, 13, 10), sphere_colour(cv, 20, 13, 10, ORANGE, amb=0.8, dif=0.35))
    for k in (-3.5, 3.5):
        cv.fill(cv.m_line((10, 13 + k), (30, 13 + k), 1.0) & cv.m_circle(20, 13, 9.6), BLACK)
        cv.fill(cv.m_ering(20, 13, 4.5, 10, 1.0) & m, BLACK)


@icon("Polygons/Reduce")
def i_reduce(cv):
    q = [(3, 3), (19, 3), (19, 19), (3, 19)]
    cv.poly(q, ORANGE)
    face_grid(cv, q, 4, BLACK)
    q2 = [(15, 15), (29, 15), (29, 29), (15, 29)]
    cv.poly(q2, LIGHT, ol=True)
    face_grid(cv, q2, 2, DARK)


@icon("Polygons/Remesh")
def i_remesh(cv):
    q = [(3, 9), (23, 9), (23, 29), (3, 29)]
    cv.poly(q, ORANGE)
    face_grid(cv, q, 2, BLACK)
    for a, b in (((3, 9), (13, 19)), ((13, 9), (23, 19)), ((3, 19), (13, 29)), ((13, 19), (23, 29))):
        cv.line(a, b, 1.0, BLACK)
    curved_arrow(cv, 23, 9, 6, 200, 470, w=2.0, head=3.5)


@icon("Polygons/Retopologize")
def i_retopo(cv):
    q = [(3, 9), (23, 9), (23, 29), (3, 29)]
    cv.poly(q, ORANGE)
    face_grid(cv, q, 3, BLACK)
    cv.ring(24, 8, 6, 2.2, LIGHT, ol=True)
    cv.circle(24, 8, 1.5, LIGHT)


@icon("Polygons/Extrude")
def i_poly_extrude(cv):
    cv.poly([(16, 20), (30, 26), (16, 31), (2, 26)], LIGHT)
    cube(cv, 16, 7, 8, 16, ORANGE, wire=1)


@icon("Polygons/Bridge")
def i_bridge(cv):
    """Maya's bridge: two orange faces one above the other, grey faces bridging their facing edges."""
    low = [(16, 18), (29, 23), (16, 29), (3, 23)]
    high = [(16, 3), (29, 8), (16, 14), (3, 8)]
    cv.poly(low, ORANGE)
    face_grid(cv, low, 2, BLACK)
    for i in range(3):
        y = 9 + i * 4.5
        cv.poly([(3 + i * 0.0, y), (16, y + 6), (16, y + 9), (3, y + 3)], shade(LIGHT, -0.1 * i), ol=True)
        cv.poly([(16, y + 6), (29, y), (29, y + 3), (16, y + 9)], shade(LIGHT, -0.25 - 0.1 * i), ol=True)
    cv.poly(high, ORANGE)
    face_grid(cv, high, 2, BLACK)


@icon("Polygons/Bevel Components")
def i_poly_bevel(cv):
    top, left, right = cube(cv, 16, 9.5, 12.5, 14, ORANGE, wire=0)
    cv.poly([(16, 15.5), (25.5, 9.5), (28.5, 9.5), (28.5, 11.5), (16, 18.5), (3.5, 11.5), (3.5, 9.5), (6.5, 9.5)], LIGHT)
    cv.line((16, 18.5), (16, 30), 1.0, BLACK)
    cv.polyline([(6.5, 9.5), (16, 4), (25.5, 9.5)], 1.0, BLACK)


@icon("Polygons/Merge")
def i_merge(cv):
    cv.poly([(3, 16), (16, 16), (16, 29), (3, 29)], LIGHT, ol=True)
    cv.poly([(16, 3), (29, 3), (29, 16), (16, 16)], ORANGE)
    face_grid(cv, [(16, 3), (29, 3), (29, 16), (16, 16)], 2, BLACK)
    face_grid(cv, [(3, 16), (16, 16), (16, 29), (3, 29)], 2, DARK)
    cv.rect(13.5, 13.5, 18.5, 18.5, ORANGE, ol=True)


@icon("Polygons/Merge to Center")
def i_merge_center(cv):
    cv.circle(16, 16, 13.5, ORANGE)
    cv.fill(cv.m_circle(16, 16, 13.5) & (cv.x + cv.y > 32), shade(ORANGE, -0.2))
    for k in range(8):
        a = math.pi * k / 4
        cv.line((16 + 4 * math.cos(a), 16 + 4 * math.sin(a)), (16 + 12.5 * math.cos(a), 16 + 12.5 * math.sin(a)), 1.6, LIGHT)
    cv.circle(16, 16, 3, LIGHT, ol=True)


@icon("Polygons/Flip Triangle Edge")
def i_flip_edge(cv):
    cv.poly([(3, 3), (19, 3), (3, 19)], ORANGE)
    cv.poly([(19, 3), (19, 19), (3, 19)], shade(ORANGE, -0.25))
    cv.polyline([(3, 3), (19, 3), (19, 19), (3, 19), (3, 3), (19, 19)], 1.0, BLACK)
    cv.poly([(13, 13), (29, 13), (13, 29)], ORANGE, ol=True)
    cv.poly([(29, 13), (29, 29), (13, 29)], shade(ORANGE, -0.25))
    cv.polyline([(13, 13), (29, 13), (29, 29), (13, 29), (13, 13)], 1.0, BLACK)
    cv.line((29, 13), (13, 29), 1.6, LIGHT)


@icon("Polygons/Duplicate")
def i_duplicate(cv):
    cv.poly([(16, 15), (29, 21), (16, 28), (3, 21)], LIGHT, ol=True)
    cv.poly([(16, 4), (29, 10), (16, 17), (3, 10)], ORANGE, ol=True)
    face_grid(cv, [(16, 4), (29, 10), (16, 17), (3, 10)], 2, BLACK)
    arrow(cv, (25, 25), (25, 17), w=1.6, head=3.2)


@icon("Polygons/Collapse")
def i_collapse(cv):
    cv.frame(4, 4, 28, 28, 1.0, LIGHT)
    cv.rect(11, 11, 21, 21, ORANGE, ol=True)
    for x, y in ((4, 4), (28, 4), (4, 28), (28, 28)):
        cv.rect(x - 2, y - 2, x + 2, y + 2, LIGHT, ol=True)
        arrow(cv, (x + (16 - x) * 0.18, y + (16 - y) * 0.18), (x + (16 - x) * 0.45, y + (16 - y) * 0.45), w=1.4, head=3)


@icon("Polygons/Circularize")
def i_circularize(cv):
    q = [(3, 3), (29, 3), (29, 29), (3, 29)]
    cv.poly(q, shade(ORANGE, -0.15))
    face_grid(cv, q, 4, BLACK)
    cv.ring(16, 16, 10.5, 2.4, LIGHT, ol=True)
    for k in range(8):
        a = math.pi * k / 4
        cv.rect(16 + 9.3 * math.cos(a) - 1.5, 16 + 9.3 * math.sin(a) - 1.5, 16 + 9.3 * math.cos(a) + 1.5,
                16 + 9.3 * math.sin(a) + 1.5, ORANGE, ol=True)


@icon("Polygons/Multi-Cut")
def i_multicut(cv):
    q = [(3, 13), (19, 13), (19, 29), (3, 29)]
    cv.poly(q, ORANGE)
    cv.polyline(q + [q[0]], 1.0, BLACK)
    for i in range(0, 16, 3):
        cv.rect(4 + i * 0.95, 21 - 0.5, 5.5 + i * 0.95, 21 + 0.5, TEAL)
    blade(cv, (10, 22), (29, 3), w=5)


@icon("Polygons/Target Weld")
def i_target_weld(cv):
    for x0, x1, y in ((5, 27, 6), (5, 27, 26)):
        for x in np.arange(x0, x1, 3):
            cv.rect(x, y - 0.5, x + 1.5, y + 0.5, LIGHT)
    for x in (5, 27):
        for y in np.arange(6, 26, 3):
            cv.rect(x - 0.5, y, x + 0.5, y + 1.5, LIGHT)
    for p in ((5, 6), (5, 26), (27, 26)):
        cv.rect(p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2, LIGHT, ol=True)
    cv.ring(27, 6, 4, 1.6, ORANGE, ol=True)
    cv.rect(25.5, 4.5, 28.5, 7.5, ORANGE)
    arrow(cv, (8, 23), (21, 11), w=1.6, head=4)


@icon("Polygons/Quad Draw")
def i_quad_draw(cv):
    q = [(3, 3), (21, 3), (21, 21), (3, 21)]
    cv.poly(q, ORANGE)
    face_grid(cv, q, 3, BLACK)
    pencil(cv, (17, 17), (30, 30), w=5)


def _uv(cv, draw_shape):
    draw_shape()
    checker(cv, 20, 20, 9)


@icon("UVEditing/Planar Mapping")
def i_uv_planar(cv):
    _uv(cv, lambda: (cv.poly([(4, 8), (24, 4), (26, 22), (6, 26)], GREEN),
                     cv.poly([(4, 8), (24, 4), (14, 15)], shade(GREEN, 0.2))))


@icon("UVEditing/Cylindrical Mapping")
def i_uv_cylinder(cv):
    def shape():
        top = [(4 + 20 * t, 6 + 7 * math.sin(math.pi * t)) for t in np.linspace(0, 1, 30)]
        bot = [(x, y + 18) for x, y in top]
        cv.poly(top + bot[::-1], GREEN)
        cv.fill(cv.m_poly(top + bot[::-1]) & (cv.x > 16), shade(GREEN, -0.22))
        cv.polyline(top, 1.0, shade(GREEN, 0.45))
    _uv(cv, shape)


@icon("UVEditing/Spherical Mapping")
def i_uv_sphere(cv):
    def shape():
        m = cv.m_circle(14, 11, 12) & (cv.y >= 11)
        cv.fill(m, sphere_colour(cv, 14, 11, 12, GREEN, amb=0.8, dif=0.4))
        cv.fill(cv.m_ellipse(14, 11, 12, 3.5), shade(GREEN, -0.35))
        cv.fill(cv.m_ering(14, 11, 12, 3.5, 1.0), shade(GREEN, 0.4))
    _uv(cv, shape)


@icon("UVEditing/Automatic Mapping")
def i_uv_auto(cv):
    _uv(cv, lambda: cube(cv, 14, 8, 11, 12, GREEN))


@icon("UVEditing/Contour Stretch")
def i_uv_contour(cv):
    def shape():
        a = bezier((3, 26), (8, 12), (14, 22), (24, 3), 30)
        b = [(x + 5, y + 3) for x, y in a]
        cv.poly(a + b[::-1], GREEN)
        cv.polyline(a, 1.0, shade(GREEN, 0.45))
        arrow(cv, (6, 6), (13, 6), w=1.6, head=3, col=LIGHT)
    _uv(cv, shape)


@icon("UVEditing/UV Editor...")
def i_uv_editor(cv):
    def body(x0, y0, x1, y1):
        c = (x1 - x0) / 5
        for i in range(5):
            for j in range(4):
                cv.rect(x0 + i * c, y0 + j * c, x0 + (i + 1) * c, y0 + (j + 1) * c, WHITE if (i + j) % 2 else GREEN)
    window(cv, 3, 4, 29, 28, GREEN, body, title=DARK)


@icon("UVEditing/3D Grab UV Tool")
def i_uv_grab(cv):
    for a, b in (((12, 12), (3, 3)), ((12, 12), (21, 3)), ((12, 12), (3, 21)), ((12, 12), (21, 21))):
        arrow(cv, a, b, w=2.6, col=GREEN, head=5)
    cv.circle(12, 12, 3, GREEN, ol=True)
    checker(cv, 20, 20, 9)


@icon("UVEditing/3D Cut and Sew UV Tool")
def i_cut_sew(cv):
    cv.polyline(bezier((3, 28), (12, 20), (16, 30), (28, 22), 24), 2.0, GREEN)
    cv.line((5, 27), (27, 5), 2.0, GREEN, ol=True)
    cv.ring(26, 6, 2.5, 1.0, GREEN)
    blade(cv, (5, 5), (27, 27), w=5)


# Sculpting ---------------------------------------------------------------------------------------

@icon("Sculpting/Sculpt Tool")
def i_sculpt(cv):
    cube(cv, 16, 10, 10, 11, _hex("#4878a8"), faces=(0.45, 0.15, -0.15))
    m = cv.m_ering(16, 17, 14, 5.5, 2.0) & ~(cv.m_ellipse(16, 17, 12.5, 4.5) | ((cv.y < 17) & cv.m_poly(
        [(6, 10), (16, 4.5), (26, 10), (26, 21), (16, 26.5), (6, 21)])))
    cv.fill(m, _hex("#5bbf4a"), ol=True)


@icon("Sculpting/Smooth Tool")
def i_s_smooth(cv):
    ball(cv)
    cv.fill(cv.m_circle(17, 15, 12.5) & (cv.x - cv.y > -2), LIGHT, ol=True)
    cv.fill(cv.m_circle(17, 15, 12.5) & (cv.x - cv.y > -2) & (cv.x - cv.y < 2 + np.abs(np.sin(cv.x * 1.6)) * 2.5), ORANGE)


@icon("Sculpting/Relax Tool")
def i_s_relax(cv):
    ball(cv)
    m = cv.m_circle(15, 17, 12.5) & (cv.x > 13)
    lines = cv.m_ering(15, 17, 6, 12.5, 1.0) | cv.m_ering(15, 17, 10.5, 12.5, 1.0)
    for k in (-6, 0, 6):
        lines |= cv.m_line((10, 17 + k), (30, 17 + k), 1.0)
    cv.fill(m & lines, LIGHT)
    cv.fill(cv.m_line((15, 4), (15, 30), 1.0) & cv.m_circle(15, 17, 12.5), LIGHT)


@icon("Sculpting/Grab Tool")
def i_s_grab(cv):
    ball(cv, 14, 18, 12)
    cv.rect(21, 3, 29, 11, LIGHT, ol=True)
    arrow(cv, (15, 17), (23, 9), w=1.6, head=3.5, col=DARK, ol=False)


@icon("Sculpting/Pinch Tool")
def i_s_pinch(cv):
    ball(cv, 14, 18, 12)
    cv.poly([(16, 9), (30, 2), (23, 16)], LIGHT, ol=True)
    cv.poly([(19, 11), (30, 2), (23, 13)], shade(LIGHT, -0.25))


@icon("Sculpting/Flatten Tool")
def i_s_flatten(cv):
    ball(cv, 15, 17, 13)
    cv.erase(cv.y + (cv.x - 15) * 0.35 < 12)
    cv.line((2, 16.5), (30, 6.7), 2.0, LIGHT, ol=True)


@icon("Sculpting/Foamy Tool")
def i_s_foamy(cv):
    ball(cv, 15, 19, 12)
    for x, y, r in ((9, 9, 3.5), (15, 6.5, 4.5), (21.5, 8, 4), (26, 12, 3), (17, 12, 3)):
        cv.circle(x, y, r, LIGHT, ol=True)


@icon("Sculpting/Spray Tool")
def i_s_spray(cv):
    ball(cv, 14, 18, 12)
    for i, (x, y) in enumerate(((17, 15), (21, 12), (24, 8), (27, 4), (19.5, 6), (26, 14))):
        cv.circle(x, y, 1.6 if i % 2 else 1.2, LIGHT, ol=True)


@icon("Sculpting/Repeat Tool")
def i_s_repeat(cv):
    ball(cv, 14, 18, 12)
    for i in range(4):
        cv.ring(9 + i * 5, 25 - i * 5.5, 2.8, 1.4, LIGHT, ol=True)


@icon("Sculpting/Imprint Tool")
def i_s_imprint(cv):
    cv.poly(wave_pts(2, 30, 25, 1.5, 2.0, n=30) + [(30, 30), (2, 30)], ORANGE)
    cv.circle(16, 5, 3.2, LIGHT, ol=True)
    cv.rect(14.5, 7, 17.5, 15, LIGHT, ol=True)
    cv.rect(7, 15, 25, 20, LIGHT, ol=True)
    cv.rect(7, 18.5, 25, 20, shade(LIGHT, -0.3))


@icon("Sculpting/Wax Tool")
def i_s_wax(cv):
    ball(cv, 15, 18, 12)
    m = cv.m_circle(15, 18, 13.5) & ~cv.m_circle(11, 22, 11)
    cv.fill(m, LIGHT, ol=True)


@icon("Sculpting/Scrape Tool")
def i_s_scrape(cv):
    ball(cv, 14, 18, 12)
    cv.poly([(15, 9), (24, 3), (30, 11), (21, 17)], LIGHT, ol=True)
    cv.line((15, 9), (21, 17), 1.6, shade(LIGHT, -0.4))


@icon("Sculpting/Fill Tool")
def i_s_fill(cv):
    pts = []
    for k in range(32):
        a = 2 * math.pi * k / 32
        r = 14 if k % 2 == 0 else 10.5
        pts.append((16 + r * math.cos(a), 16 + r * math.sin(a)))
    cv.poly(pts, ORANGE)
    cv.fill(cv.m_poly(pts) & ~cv.m_circle(16, 16, 10.5) & (cv.x + cv.y < 32), LIGHT)


@icon("Sculpting/Knife Tool")
def i_s_knife(cv):
    ball(cv)
    cv.fill(cv.m_poly([(15, 17), (30, 3), (30, 9)]), LIGHT, ol=True)


@icon("Sculpting/Smear Tool")
def i_s_smear(cv):
    ball(cv, 14, 18, 12)
    cv.fill(cv.m_line((14, 18), (26, 6), 5.5), LIGHT, ol=True)
    cv.fill(cv.m_line((14, 18), (26, 6), 2.0), shade(LIGHT, -0.25))


@icon("Sculpting/Bulge Tool")
def i_s_bulge(cv):
    ball(cv, 13, 19, 11.5)
    cv.fill(cv.m_circle(22, 10, 7.5), sphere_colour(cv, 22, 10, 7.5, LIGHT, amb=0.85, dif=0.3), ol=True)


@icon("Sculpting/Amplify Tool")
def i_s_amplify(cv):
    ball(cv)
    pts = [(15, 17)]
    for k in range(13):
        a = math.radians(-100 + 105 * k / 12)
        r = 15.5 if k % 2 == 0 else 11
        pts.append((15 + r * math.cos(a), 17 + r * math.sin(a)))
    cv.poly(pts, LIGHT, ol=True)


@icon("Sculpting/Freeze Tool")
def i_s_freeze(cv):
    ball(cv)
    snowflake(cv, 16, 16, 8.5, col=LIGHT)


@icon("Sculpting/Convert To Frozen")
def i_convert_frozen(cv):
    m = cv.m_ring(16, 16, 14, 2.0) & ((np.floor(np.degrees(np.arctan2(cv.y - 16, cv.x - 16)) / 20) % 2) == 0)
    cv.fill(m, ORANGE)
    cv.circle(16, 16, 10, shade(ORANGE, -0.15))
    snowflake(cv, 16, 16, 8, col=WHITE)


@icon("Sculpting/Shape Editor")
def i_shape_editor(cv):
    def body(x0, y0, x1, y1):
        cv.circle(14, 18, 6, LIGHT, ol=True)
        cv.circle(19, 21, 6, shade(LAV, 0.35), ol=True)
    window(cv, 3, 4, 29, 28, LAV, body, title=DARK)


@icon("Sculpting/Pose Editor")
def i_pose_editor(cv):
    window(cv, 3, 4, 29, 28, LAV, lambda *r: human(cv, 16, 19.5, 0.62, LIGHT), title=DARK)


def _target_tool(cv, draw_shape):
    draw_shape()
    target(cv, 24, 24, 6)


@icon("Sculpting/Smooth Target Tool")
def i_smooth_target(cv):
    def shape():
        cv.circle(13, 13, 11, LAV)
        pts = [(13 + (11 if k % 2 else 13.5) * math.cos(math.radians(100 + 8 * k)),
                13 + (11 if k % 2 else 13.5) * math.sin(math.radians(100 + 8 * k))) for k in range(22)]
        cv.poly([(13, 13)] + pts, LAV)
        cv.fill(cv.m_circle(13, 13, 11) & (cv.x - cv.y > 0), shade(LAV, 0.4))
    _target_tool(cv, shape)


@icon("Sculpting/Clone Target Tool")
def i_clone_target(cv):
    def shape():
        cv.rect(9, 3, 25, 19, shade(LAV, -0.2), ol=True)
        cv.rect(3, 9, 19, 25, LAV, ol=True)
        cv.circle(11, 17, 4, shade(LAV, 0.45))
    _target_tool(cv, shape)


@icon("Sculpting/Mask Target Tool")
def i_mask_target(cv):
    def shape():
        cv.poly([(2, 18), (14, 8), (28, 12), (16, 24)], LIGHT, ol=True)
        cv.ellipse(15, 13, 8, 4.5, LAV, rot=-15, ol=True)
        cv.circle(15, 13, 2.2, DARK)
    _target_tool(cv, shape)


@icon("Sculpting/Erase Target Tool")
def i_erase_target(cv):
    def shape():
        cv.poly([(3, 17), (14, 6), (21, 13), (10, 24)], LIGHT, ol=True)
        cv.poly([(14, 6), (20, 0.5), (27, 7.5), (21, 13)], LAV, ol=True)
    _target_tool(cv, shape)


# Rigging / Animation -----------------------------------------------------------------------------

@icon("Rigging/Create Locator")
def i_locator(cv):
    cv.line((16, 3), (16, 29), 1.6, LAV)
    cv.line((3, 16), (29, 16), 1.6, LAV)
    cv.line((7, 25), (25, 7), 1.6, LAV)


def bone(cv, p0, p1, r0=4.0, col=LAV):
    """Maya joint: ball at ``p0`` and a tapered bone to ``p1``."""
    (x0, y0), (x1, y1) = p0, p1
    d = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    cv.poly([(x0 - uy * r0 * 0.9, y0 + ux * r0 * 0.9), (x1, y1), (x0 + uy * r0 * 0.9, y0 - ux * r0 * 0.9)],
            shade(col, -0.15), ol=True)
    cv.circle(x0, y0, r0, col, ol=True)
    cv.circle(x0 - 1, y0 - 1, r0 * 0.4, shade(col, 0.45))


@icon("Rigging/Create Joints")
def i_joints(cv):
    bone(cv, (22, 8), (6, 26), 5)
    cv.circle(6, 26, 2.6, LAV, ol=True)


@icon("Rigging/Create IK Handle")
def i_ik_handle(cv):
    bone(cv, (9, 6), (20, 15), 3.5)
    bone(cv, (20, 15), (11, 27), 3.5)
    cv.line((9, 6), (11, 27), 1.0, LIGHT)
    cv.rect(23, 3, 26, 29, LIGHT, ol=True)
    cv.line((11, 27), (24.5, 27), 1.0, LIGHT)


@icon("Rigging/Bind Skin")
def i_bind_skin(cv):
    a, b, c = (25, 6), (9, 16), (25, 26)
    cv.fill(cv.m_line(a, b, 10) | cv.m_line(b, c, 10), LIGHT)
    cv.fill(cv.m_line(a, b, 6.5) | cv.m_line(b, c, 6.5), DARK)
    cv.line(a, b, 2.0, LAV)
    cv.line(b, c, 2.0, LAV)
    for p in (a, b, c):
        cv.circle(*p, 2.6, LAV)


def cursor(cv, x, y, s=1.0):
    pts = [(0, 0), (0, 11), (3, 8.5), (5, 13), (7, 12), (5, 7.5), (9, 7.5)]
    cv.poly([(x + a * s, y + b * s) for a, b in pts], WHITE, ol=True)


@icon("Rigging/Quick Rig")
def i_quick_rig(cv):
    human(cv, 14, 15, 1.0, LAV)
    cursor(cv, 20, 17, 1.0)


@icon("Rigging/Human IK")
def i_human_ik(cv):
    human(cv, 16, 16, 1.05, LIGHT, joints=LAV)


@icon("Rigging/Paint Skin Weights")
def i_paint_weights(cv):
    for i in range(3):
        for j in range(3):
            cv.rect(3 + i * 7, 9 + j * 7, 9 + i * 7, 15 + j * 7, LAV if (i + 2 - j) <= 2 else shade(LAV, -0.5), ol=True)
    brush(cv, (17, 15), (30, 2), w=3, bristle=LAV)


@icon("Rigging/Blend Shapes")
def i_blend_shapes(cv):
    cv.rect(11, 3, 29, 21, LIGHT, ol=True)
    cv.circle(12, 19, 9.5, LAV, ol=True)
    cv.circle(10, 17, 3, shade(LAV, 0.5))


@icon("Rigging/Create Lattice")
def i_lattice(cv):
    f = [(4, 12), (20, 12), (20, 28), (4, 28)]
    b = [(12, 4), (28, 4), (28, 20), (12, 20)]
    for q in (b, f):
        face_grid(cv, q, 2, LAV, w=1.4)
    for p, q in zip(f, b):
        cv.line(p, q, 1.4, LAV)


@icon("Rigging/Create Cluster")
def i_cluster(cv):
    for k in range(8):
        a = math.pi * k / 4
        x, y = 16 + 11 * math.cos(a), 16 + 11 * math.sin(a)
        cv.rect(x - 2, y - 2, x + 2, y + 2, LAV, ol=True)
    cv.text("C", LIGHT, 13.5, 12.5, ol=True)


def _constraint(cv, draw_thing):
    draw_thing()
    link(cv, 24, 8, 1.05)


@icon("Rigging/Parent Constraint", "Animation/Parent Constraint")
def i_parent_constraint(cv):
    def thing():
        cv.polyline([(8, 14), (8, 23), (13, 23)], 2.0, LIGHT, ol=True)
        cv.rect(3, 8, 18, 14, LIGHT, ol=True)
        cv.rect(13, 20, 28, 27, LIGHT, ol=True)
    _constraint(cv, thing)


@icon("Rigging/Point Constraint", "Animation/Point Constraint")
def i_point_constraint(cv):
    def thing():
        arrow(cv, (6, 27), (6, 9), w=3.0, head=6)
        arrow(cv, (5, 26), (23, 26), w=3.0, head=6)
    _constraint(cv, thing)


@icon("Rigging/Orient Constraint", "Animation/Orient Constraint")
def i_orient_constraint(cv):
    _constraint(cv, lambda: curved_arrow(cv, 17, 19, 10, 95, 255, w=3.0, head=6))


@icon("Rigging/Scale Constraint", "Animation/Scale Constraint")
def i_scale_constraint(cv):
    def thing():
        for x in np.arange(3, 25, 3):
            cv.rect(x, 9, x + 1.5, 10, LIGHT)
            cv.rect(x, 28, x + 1.5, 29, LIGHT)
        for y in np.arange(9, 28, 3):
            cv.rect(3, y, 4, y + 1.5, LIGHT)
            cv.rect(24, y, 25, y + 1.5, LIGHT)
        cv.rect(4, 18, 14, 28, LIGHT, ol=True)
        arrow(cv, (12, 20), (20, 13), w=1.8, head=3.5)
    _constraint(cv, thing)


@icon("Rigging/Aim Constraint", "Animation/Aim Constraint")
def i_aim_constraint(cv):
    def thing():
        cv.ring(13, 19, 8.5, 2.0, LIGHT, ol=True)
        cv.line((13, 7), (13, 31), 2.0, LIGHT, ol=True)
        cv.line((1, 19), (25, 19), 2.0, LIGHT, ol=True)
    _constraint(cv, thing)


@icon("Rigging/Pole Vector Constraint", "Animation/Pole Vector Constraint")
def i_pole_vector(cv):
    _constraint(cv, lambda: arrow(cv, (4, 9), (24, 29), w=3.0, head=7))


@icon("Rigging/Set Key", "Animation/Set Key")
def i_set_key(cv):
    key_bar(cv, 16, 16, h=22, line=13, w=5)


@icon("Rigging/Set Driven Key")
def i_set_driven_key(cv):
    key_bar(cv, 13, 17, h=22, line=11, w=5)
    link(cv, 23, 9, 1.05)


@icon("Animation/Playblast")
def i_playblast(cv):
    cv.rect(2, 6, 30, 26, LIGHT)
    for x in np.arange(4, 29, 4):
        cv.rect(x, 7.5, x + 2, 9.5, DARK)
        cv.rect(x, 22.5, x + 2, 24.5, DARK)
    cv.rect(5, 11, 27, 21, DARK)
    cv.poly([(13, 12), (21, 16), (13, 20)], KEY)


@icon("Animation/Motion Trail")
def i_motion_trail(cv):
    for k in range(9):
        a = math.radians(180 + 22.5 * k)
        cv.line((16 + 9 * math.cos(a), 22 + 9 * math.sin(a)), (16 + 13.5 * math.cos(a), 22 + 13.5 * math.sin(a)), 2.0, KEY)
    cv.line((16, 22), (24, 13), 2.0, LIGHT, ol=True)
    cv.circle(16, 22, 2.5, LIGHT, ol=True)


@icon("Animation/Bake Animation")
def i_bake(cv):
    cv.rect(5, 2, 27, 21, KEY)
    cv.rect(7, 4, 25, 19, DARK)
    for x in (11, 15.5, 20):
        cv.rect(x - 1, 6, x + 1, 17, LIGHT)
    cv.poly([(10, 23), (22, 23), (16, 30)], KEY, ol=True)


@icon("Animation/Set Key on Animated")
def i_key_animated(cv):
    cv.line((2, 16), (30, 16), 2.0, LIGHT, ol=True, cap=False)
    cv.rect(6, 7, 10, 25, LIGHT, ol=True)
    cv.rect(22, 7, 26, 25, LIGHT, ol=True)
    cv.rect(13.5, 4, 18.5, 28, KEY, ol=True)


def _key_corner(cv):
    key_bar(cv, 24, 8, h=11, line=6, w=3)


@icon("Animation/Set Key on Translate")
def i_key_translate(cv):
    arrow(cv, (5, 29), (5, 12), w=3.0, head=6)
    arrow(cv, (4, 28), (21, 28), w=3.0, head=6)
    _key_corner(cv)


@icon("Animation/Set Key on Rotate")
def i_key_rotate(cv):
    curved_arrow(cv, 15, 20, 9.5, 95, 255, w=3.0, head=6)
    _key_corner(cv)


@icon("Animation/Set Key on Scale")
def i_key_scale(cv):
    for x in np.arange(3, 22, 3):
        cv.rect(x, 10, x + 1.5, 11, LIGHT)
        cv.rect(x, 28, x + 1.5, 29, LIGHT)
    for y in np.arange(10, 28, 3):
        cv.rect(3, y, 4, y + 1.5, LIGHT)
        cv.rect(21, y, 22, y + 1.5, LIGHT)
    cv.rect(4, 18, 13, 28, LIGHT, ol=True)
    _key_corner(cv)


# Rendering ---------------------------------------------------------------------------------------

def sun(cv, cx, cy, r, ray0, ray1, n=8, w=2.0, col=YELLOW, offset=0.0):
    for k in range(n):
        a = 2 * math.pi * k / n + offset
        cv.line((cx + ray0 * math.cos(a), cy + ray0 * math.sin(a)), (cx + ray1 * math.cos(a), cy + ray1 * math.sin(a)), w, col)
    cv.circle(cx, cy, r, col)
    cv.circle(cx - r * 0.2, cy - r * 0.2, r * 0.55, shade(col, 0.35))


@icon("Rendering/Ambient Light")
def i_ambient(cv):
    sun(cv, 16, 16, 7.5, 9.5, 14, n=16, w=1.4)


@icon("Rendering/Directional Light")
def i_directional(cv):
    for k in range(3):
        o = (k - 1) * 8
        arrow(cv, (5 + o * 0.7 - 2, 5 - o * 0.7 + 2), (25 + o * 0.7 - 2, 25 - o * 0.7 + 2), w=2.2, col=YELLOW, head=5.5, ol=False)


@icon("Rendering/Point Light")
def i_point(cv):
    sun(cv, 16, 16, 7, 9.5, 14.5, n=8, w=2.6)


@icon("Rendering/Spot Light")
def i_spot(cv):
    for a in (20, 45, 70):
        ra = math.radians(a)
        cv.line((14 + 6 * math.cos(ra), 14 + 6 * math.sin(ra)), (14 + 15 * math.cos(ra), 14 + 15 * math.sin(ra)), 2.4, YELLOW)
    cv.poly([(2, 9), (9, 2), (17, 10), (10, 17)], LIGHT, ol=True)
    cv.fill(cv.m_ellipse(13.5, 13.5, 5.5, 2.5, rot=-45), shade(YELLOW, 0.3), ol=True)


@icon("Rendering/Area Light")
def i_area(cv):
    for (x, y), (dx, dy) in (((8, 10), (-1, -1)), ((24, 10), (1, -1)), ((8, 22), (-1, 1)), ((24, 22), (1, 1))):
        cv.line((x + dx * 1.5, y + dy * 1.5), (x + dx * 5, y + dy * 5), 2.4, YELLOW)
    cv.rect(8, 10, 24, 22, YELLOW)
    cv.rect(8, 10, 16, 16, shade(YELLOW, 0.3))


@icon("Rendering/Volume Light")
def i_volume(cv):
    cv.frame(2, 2, 30, 30, 2.0, LIGHT)
    for (dx, dy) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        cv.line((16 + dx * 7.5, 16 + dy * 7.5), (16 + dx * 11, 16 + dy * 11), 2.2, YELLOW)
    sun(cv, 16, 16, 6, 0, 0, n=0)


@icon("Rendering/Create Camera")
def i_camera(cv):
    cv.rect(2, 8, 18, 20, YELLOW)
    cv.rect(2, 8, 18, 11, shade(YELLOW, 0.3))
    cv.poly([(18, 14), (26, 8), (26, 20)], shade(YELLOW, -0.15))
    cv.circle(6, 5, 3, YELLOW)
    cv.circle(13, 5, 3, YELLOW)
    plus(cv, 25, 26, s=4.5, w=2)


@icon("Rendering/Edit Material Attributes")
def i_edit_material(cv):
    cv.fill(cv.m_circle(10, 14, 8.5), sphere_colour(cv, 10, 14, 8.5, YELLOW, amb=0.75, dif=0.4))
    cv.rect(15, 6, 30, 28, LIGHT, ol=True)
    for y in (10, 16, 22):
        cv.rect(17, y, 28, y + 2.5, DARK)
        cv.rect(17, y, 22 + (y % 4), y + 2.5, YELLOW)


# Maya's shader balls are grey; the highlight tells the shader: Standard Surface dark and glossy
# with a hard highlight and a bright rim, Blinn a broad soft highlight, Lambert matte and lighter, Phong a small
# sharp dot, Phong E darker with a small soft highlight.
@icon("Rendering/Standard Surface Material")
def i_standard_surface(cv):
    mat_ball(cv, (0.10, 0.10, 0.10), amb=0.5, dif=0.9)
    cv.fill(cv.m_ring(16, 16, 13, 2.2) & cv.m_angle(16, 16, 0, 110), (0.62, 0.62, 0.62))
    cv.ellipse(11, 10, 4.5, 2.8, WHITE, rot=-35)


@icon("Rendering/Anisotropic Material")
def i_anisotropic(cv):
    mat_ball(cv, (0.36, 0.38, 0.55), amb=0.5, dif=0.7)
    m = cv.m_ering(19, 21, 13, 9, 2.0, rot=-20) & cv.m_circle(16, 16, 12) & (cv.y < 15)
    cv.fill(m, WHITE)


@icon("Rendering/Blinn Material")
def i_blinn(cv):
    mat_ball(cv, (0.32, 0.32, 0.32), spec=1.0, power=4, amb=0.45, dif=0.55)


@icon("Rendering/Lambert Material")
def i_lambert(cv):
    mat_ball(cv, (0.86, 0.86, 0.86), amb=0.3, dif=0.72)


@icon("Rendering/Phong Material")
def i_phong(cv):
    mat_ball(cv, (0.50, 0.50, 0.50), amb=0.45, dif=0.6)
    cv.circle(11, 10, 3.2, WHITE)


@icon("Rendering/Phong E Material")
def i_phong_e(cv):
    mat_ball(cv, (0.16, 0.16, 0.18), amb=0.5, dif=0.7)
    cv.ellipse(12, 10, 6.0, 3.2, (0.62, 0.62, 0.62), rot=-35)
    cv.ellipse(12, 10, 3.5, 1.8, (0.85, 0.85, 0.85), rot=-35)


@icon("Rendering/Layered Material")
def i_layered(cv):
    mat_ball(cv, (0.20, 0.20, 0.42), amb=0.55, dif=0.7)
    m = cv.m_line((3, 25), (27, 5), 5.5) & cv.m_circle(16, 16, 13)
    cv.fill(m, YELLOW)
    cv.fill(cv.m_line((3, 25), (27, 5), 1.6) & cv.m_circle(16, 16, 13), LIGHT)


@icon("Rendering/Ramp Material")
def i_ramp(cv):
    d = np.sqrt((cv.x - 13) ** 2 + (cv.y - 12) ** 2) / 17
    stops = np.array([[0.95, 0.15, 0.05], [0.98, 0.85, 0.1], [0.2, 0.75, 0.2], [0.15, 0.35, 0.85]], np.float32)
    t = np.clip(d, 0, 1) * 3
    i = np.clip(np.floor(t).astype(int), 0, 2)
    f = (t - i)[..., None]
    col = stops[i] * (1 - f) + stops[i + 1] * f
    cv.fill(cv.m_circle(16, 16, 13), col)


@icon("Rendering/Shading Map")
def i_shading_map(cv):
    cv.circle(16, 16, 13, (0.74, 0.74, 0.74))
    cv.fill(cv.m_circle(16, 16, 13) & (cv.x + cv.y > 32), (0.55, 0.55, 0.55))


@icon("Rendering/Surface Material")
def i_surface_material(cv):
    cv.circle(16, 16, 13, BLACK)
    cv.ring(16, 16, 13, 1.0, (0.45, 0.45, 0.45))


@icon("Rendering/Use Background")
def i_use_background(cv):
    cv.circle(16, 16, 13, BLACK)
    cv.circle(16, 16, 9.5, (0.74, 0.74, 0.74))


@icon("Rendering/Render Diagnostics")
def i_render_diag(cv):
    def body(x0, y0, x1, y1):
        cv.polyline([(x0, 19), (9, 19), (11, 13), (14, 25), (17, 15), (20, 21), (22, 19), (x1, 19)], 1.6, DARK)
    window(cv, 2, 4, 30, 28, YELLOW, body, title=DARK)


@icon("Rendering/Batch Render")
def i_batch_render(cv):
    stack(cv, 3, 15, 18, 13, YELLOW)
    clapper(cv, 12, 2, 29, 13)


@icon("Rendering/Cancel Batch Render")
def i_cancel_batch(cv):
    stack(cv, 3, 15, 18, 13, YELLOW)
    nosign(cv, 23, 9, r=6.5, w=2.2)


@icon("Rendering/Show Batch Render")
def i_show_batch(cv):
    stack(cv, 3, 15, 18, 13, YELLOW)
    eye(cv, 23, 9, s=7)


@icon("Rendering/Render Sequence")
def i_render_sequence(cv):
    for i in range(3):
        cv.rect(2 + i * 9, 18, 9 + i * 9, 27, shade(YELLOW, -0.12 * i), ol=True)
    arrow(cv, (3, 30), (29, 30), w=1.4, head=3)
    clapper(cv, 4, 3, 22, 14)


@icon("Rendering/3D Paint Tool")
def i_3d_paint(cv):
    cv.circle(13, 18, 11.5, LIGHT, ol=True)
    cv.circle(13, 18, 8, YELLOW)
    cv.ring(13, 18, 8, 1.0, DARK)
    brush(cv, (15, 16), (30, 2), w=3, bristle=YELLOW)


# FX ----------------------------------------------------------------------------------------------

@icon("FX/Emitter")
def i_emitter(cv):
    cv.ring(16, 16, 7.5, 2.0, LIGHT, ol=True)
    cv.line((16, 10), (16, 22), 1.6, LIGHT)
    cv.line((10, 16), (22, 16), 1.6, LIGHT)
    for k in range(10):
        a = 2 * math.pi * k / 10 + 0.3
        r = 12 if k % 2 else 13.5
        cv.circle(16 + r * math.cos(a), 16 + r * math.sin(a), 1.8 if k % 3 else 2.2, SALMON)


@icon("FX/Add Emitter")
def i_add_emitter(cv):
    cv.fill(cv.m_circle(12, 18, 10), sphere_colour(cv, 12, 18, 10, LIGHT, amb=0.8, dif=0.35))
    for x, y, r in ((24, 7, 2.6), (27, 14, 2.0), (19, 4, 1.8), (28, 22, 1.6), (23, 13, 1.5)):
        cv.circle(x, y, r, SALMON)


@icon("FX/3D Fluid Container with Emitter")
def i_fluid_3d(cv):
    top, left, right = cube(cv, 16, 9, 12.5, 14, SALMON, faces=(0.3, 0.0, -0.25))
    for q in (left, right):
        cv.fill(cv.m_poly(q) & (cv.y < 18), DARK)
    face_grid(cv, top, 2, shade(SALMON, -0.5))
    cv.polyline([(3.5, 9), (16, 15.9), (28.5, 9)], 1.0, LIGHT)
    cv.line((16, 15.9), (16, 30), 1.0, LIGHT)


@icon("FX/2D Fluid Container with Emitter")
def i_fluid_2d(cv):
    cv.rect(3, 3, 29, 29, SALMON)
    cv.rect(5, 5, 27, 27, DARK)
    pts = wave_pts(5, 27, 18, 2.5, 1.0)
    cv.poly(pts + [(27, 27), (5, 27)], LIGHT)


@icon("FX/Emit Fluid from Object")
def i_fluid_object(cv):
    cube(cv, 12, 17, 9, 10, SALMON)
    for k in range(3):
        cv.polyline(wave_pts(12 + k * 2, 30, 4 + k * 4, 1.5, 1.2, phase=k), 1.6, LIGHT, ol=True)


@icon("FX/Make Collide")
def i_make_collide(cv):
    cv.poly([(2, 27), (22, 21), (30, 25), (10, 31)], LIGHT, ol=True)
    for k in range(2):
        cv.polyline(bezier((3, 4 + k * 5), (12, 6 + k * 5), (13, 18), (15, 22), 16), 2.0, SALMON, ol=True)
    arrow(cv, (16, 21), (28, 8), w=2.0, head=4.5)


@icon("FX/Create Hair")
def i_create_hair(cv):
    hair(cv, 5, 29, 3, h=22, lean=8, gap=5)
    plus(cv, 25, 7, s=4, w=2.2)


@icon("FX/Paint Hair Tool Options")
def i_paint_hair(cv):
    cv.polyline(bezier((3, 29), (6, 20), (12, 26), (14, 18), 20), 2.0, SALMON, ol=True)
    brush(cv, (14, 18), (29, 2), w=3.4, bristle=SALMON)


@icon("FX/Make Selected Curves Dynamic")
def i_curves_dynamic(cv):
    cv.polyline(bezier((4, 29), (4, 14), (20, 22), (20, 8), 30), 2.0, LIGHT, ol=True)
    cv.frame(17, 2, 26, 11, 2.0, SALMON, ol=True)


def _hair_state(cv, ch):
    letter_disc(cv, 13, 18, 11.5, ch, LIGHT)
    squiggle(cv, 21, 9, 30, 2, SALMON, w=2.0)


@icon("FX/Current Position")
def i_hair_current(cv):
    _hair_state(cv, "C")


@icon("FX/Start Position")
def i_hair_start(cv):
    _hair_state(cv, "S")


@icon("FX/Rest Position")
def i_hair_rest(cv):
    _hair_state(cv, "R")


@icon("FX/To Hair Systems")
def i_to_hair_systems(cv):
    hair(cv, 13, 30, 3, h=20, lean=6, gap=5, w=2.0)
    curved_arrow(cv, 10, 12, 7, 180, 350, w=2.2, head=4.5)


@icon("FX/To Follicles")
def i_to_follicles(cv):
    curved_arrow(cv, 10, 12, 7, 180, 350, w=2.2, head=4.5)
    cv.ring(22, 22, 5, 2.0, SALMON, ol=True)
    cv.circle(22, 22, 1.6, SALMON)
    cv.polyline(bezier((22, 17), (22, 10), (28, 10), (30, 3), 16), 1.6, SALMON, ol=True)


def _to_curves(cv, ch, cvs=False):
    letter_disc(cv, 18, 20, 10, ch, SALMON)
    curved_arrow(cv, 10, 11, 7, 180, 345, w=2.2, head=4.5)
    if cvs:
        cv.frame(23, 1, 31, 9, 2.0, LIGHT, ol=True)


@icon("FX/To Start Curves")
def i_to_start_curves(cv):
    _to_curves(cv, "S")


@icon("FX/To Rest Curves")
def i_to_rest_curves(cv):
    _to_curves(cv, "R")


@icon("FX/To Start Curve End CVs")
def i_to_start_cvs(cv):
    _to_curves(cv, "S", cvs=True)


@icon("FX/To Rest Curve End CVs")
def i_to_rest_cvs(cv):
    _to_curves(cv, "R", cvs=True)


@icon("FX/Scale Hair Tool")
def i_scale_hair(cv):
    cv.polyline(bezier((6, 29), (6, 18), (16, 16), (12, 4), 20), 2.0, SALMON, ol=True)
    arrow(cv, (12, 12), (28, 28), w=2.6, head=6)


def _from_current(cv, ch):
    cv.text("C", SALMON, 3, 3, cell=2.0, ol=True)
    check(cv, 23, 7, s=4.5, w=2.0)
    letter_disc(cv, 20, 21, 9.5, ch, SALMON)


def _current_and(cv, ch):
    letter_disc(cv, 11, 11, 9.5, "C", SALMON)
    letter_disc(cv, 21, 21, 9.5, ch, shade(SALMON, -0.12))


@icon("FX/From Current", "FX/From Current#19")
def i_start_from_current(cv):
    _from_current(cv, "S")


@icon("FX/From Current#21")
def i_rest_from_current(cv):
    _from_current(cv, "R")


@icon("FX/Current and Start")
def i_current_and_start(cv):
    _current_and(cv, "S")


@icon("FX/Current and Rest")
def i_current_and_rest(cv):
    _current_and(cv, "R")


@icon("FX/Create nCloth")
def i_create_ncloth(cv):
    shirt(cv, 14, 18, 1.05)
    plus(cv, 26, 6, s=4, w=2.2)


@icon("FX/Create Passive")
def i_create_passive(cv):
    shirt(cv, 16, 13, 0.95)
    cv.poly([(2, 26), (16, 21), (30, 26), (16, 31)], LIGHT, ol=True)


@icon("FX/Remove nCloth")
def i_remove_ncloth(cv):
    shirt(cv, 14, 16, 1.05)
    xmark(cv, 25, 25, s=4)


@icon("FX/Display Input Mesh")
def i_display_input(cv):
    pts = shirt(cv, 16, 16, 1.15)
    m = cv.m_poly(pts)
    cell = ((np.floor(cv.x / 3) + np.floor(cv.y / 3)) % 2).astype(bool)
    cv.fill(m & cell, shade(SALMON, -0.35))


@icon("FX/Display Current Mesh")
def i_display_current(cv):
    shirt(cv, 18, 18, 1.0, SALMON)
    shirt(cv, 14, 14, 1.0, LIGHT, ol=True)


@icon("FX/Interactive playback")
def i_interactive_playback(cv):
    cv.poly([(9, 6), (26, 16), (9, 26)], LIGHT, ol=True)
    for x, y, r in ((4, 5, 2), (3, 14, 1.6), (5, 23, 2.2), (14, 28, 1.6), (20, 5, 1.8), (28, 26, 2)):
        cv.circle(x, y, r, SALMON)


# FX Caching --------------------------------------------------------------------------------------

@icon("FXCaching/Set Initial State")
def i_set_initial(cv):
    film_frame(cv, 6, 2, 26, 30, SALMON)
    cv.rect(11, 8, 21, 24, LIGHT)
    cv.text("1", DARK, 13.5, 12.5)


@icon("FXCaching/Clear Initial State")
def i_clear_initial(cv):
    film_frame(cv, 5, 2, 25, 30, SALMON)
    xmark(cv, 25, 25, s=4)


def _cache(cv, wisp=False):
    film_strip(cv, 2, 11, 26, 23, SALMON)
    if wisp:
        cv.polyline(wave_pts(3, 26, 27, 1.5, 1.5), 1.6, SALMON, ol=True)


@icon("FXCaching/Create Cache")
def i_create_cache(cv):
    _cache(cv, wisp=True)
    plus(cv, 26, 7, s=4.5, w=2.2)


@icon("FXCaching/Delete Cache", "FXCaching/Delete Cache#3")
def i_delete_fluid_cache(cv):
    _cache(cv, wisp=True)
    xmark(cv, 26, 7, s=4)


@icon("FXCaching/Create New Cache")
def i_create_new_cache(cv):
    _cache(cv)
    plus(cv, 26, 25, s=4.5, w=2.2)


@icon("FXCaching/Delete Cache#5")
def i_delete_cloth_cache(cv):
    _cache(cv)
    xmark(cv, 26, 25, s=4)


@icon("FXCaching/Enable All Caches On Selected")
def i_enable_caches(cv):
    _cache(cv)
    check(cv, 25, 7, s=5)


@icon("FXCaching/Disable All Caches On Selected")
def i_disable_caches(cv):
    _cache(cv)
    nosign(cv, 25, 25, r=5.5, w=2.0)


@icon("FXCaching/Merge Caches")
def i_merge_caches(cv):
    film_strip(cv, 2, 8, 22, 17, shade(SALMON, -0.15), cells=2)
    film_strip(cv, 6, 18, 26, 27, SALMON, cells=2)
    curved_arrow(cv, 23, 13, 6, 280, 450, w=2.2, head=4)


@icon("FXCaching/Replace Cache Frame")
def i_replace_frame(cv):
    film_strip(cv, 2, 15, 30, 27, SALMON)
    cv.rect(12, 3, 21, 13, LIGHT, ol=True)
    arrow(cv, (16.5, 9), (16.5, 18), w=1.6, head=3.5)


# Maya 2026 shelf buttons ---------------------------------------------------------------
# Buttons whose Maya menu item already has a kit drawing (``menu_drawings``) show that picture, like Maya, where a
# shelf button and its menu item share the runTimeCommand's icon.

def _menu_picture(path):
    def fn(cv):
        from . import menu_drawings
        menu_drawings.DRAWINGS[path](cv)
    return fn


for _key, _path in (("Polygons/Difference (A - B)", "Mesh/Booleans/Difference (A - B)"),
                    ("UVEditing/Auto Seams", "UV/Auto Seams"), ("UVEditing/Cut UV Edges", "UV/Cut UV Edges"),
                    ("UVEditing/Delete UVs", "UV/Delete UVs"), ("UVEditing/UV Set Editor", "UV/UV Set Editor")):
    ICONS[_key] = _menu_picture(_path)


@icon("Polygons/Smart Extrude")
def i_smart_extrude(cv):
    """Extrude's picture one step on: a second, smaller block grown from the first one's top face."""
    cv.poly([(16, 22), (30, 28), (16, 32), (2, 28)], LIGHT)
    cube(cv, 16, 13, 10, 10, ORANGE, wire=1)
    cube(cv, 16, 4, 6, 7, shade(ORANGE, 0.25), wire=1)


@icon("Animation/Motion Trail Editor")
def i_motion_trail_editor(cv):
    """The Motion Trail picture (an arc of key ticks) inside an editor window."""
    def body(x0, y0, x1, y1):
        cx, cy, r = (x0 + x1) / 2, y1 - 1, (x1 - x0) / 2 - 2
        for k in range(7):
            a = math.radians(180 + 30 * k)
            cv.circle(cx + r * math.cos(a), cy + r * math.sin(a), 1.4, KEY)
        cv.circle(cx, cy, 2.0, LIGHT)
    window(cv, 3, 4, 29, 28, TEAL, body, title=DARK)


def _ghosts(cv, cx, cy, s=1.0):
    """A figure with two fading copies trailing to its left (Maya ghosting)."""
    for k, fade in ((2, 0.62), (1, 0.38)):
        human(cv, cx - 6.5 * k * s, cy, s, shade(TEAL, fade), ol=False)
    human(cv, cx, cy, s, LIGHT)


@icon("Animation/Ghost Selected")
def i_ghost_selected(cv):
    _ghosts(cv, 21, 16)


@icon("Animation/Unghost Selected")
def i_unghost_selected(cv):
    _ghosts(cv, 19, 15)
    xmark(cv, 24, 24, s=4.5, col=SALMON)


@icon("Animation/Open Ghosting Editor")
def i_ghosting_editor(cv):
    """The ghosting picture inside an editor window."""
    def body(x0, y0, x1, y1):
        _ghosts(cv, (x0 + x1) / 2 + 4, (y0 + y1) / 2 + 1, 0.6)
    window(cv, 3, 4, 29, 28, TEAL, body, title=DARK)


@icon("Rendering/OpenPBR Surface Material")
def i_openpbr_surface(cv):
    """A grey shader ball like Standard Surface's, lighter, with a clear-coat band across the top."""
    mat_ball(cv, (0.42, 0.42, 0.44), spec=0.6, power=40, amb=0.5, dif=0.8)
    cv.fill(cv.m_ring(16, 16, 13, 2.6) & cv.m_angle(16, 16, 200, 340), WHITE)
    cv.ellipse(20, 11, 3.0, 1.8, WHITE, rot=35)


# --- user shelf fallback ------------------------------------------------------------------------

def initials(label):
    words = [w for w in label.replace("/", " ").replace("-", " ").split() if w[0].isalnum()]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def user_button(cv, label):
    """Maya's custom shelf button: the generic script icon with the button's icon label written on it."""
    cv.rect(3, 3, 29, 29, (0.30, 0.30, 0.30))
    cv.rect(3, 3, 29, 9, (0.42, 0.42, 0.42))
    text = initials(label)
    cv.text(text, LIGHT, 16 - (len(text) * 12 - 2) / 2, 12, cell=2.0)


# --- lookup ---------------------------------------------------------------------------------------

def icon_for(label, shelf=None, index=None):
    """The drawing of a button (or None: user / unknown label)."""
    if shelf is not None:
        if index is not None and f"{shelf}/{label}#{index}" in ICONS:
            return ICONS[f"{shelf}/{label}#{index}"]
        fn = ICONS.get(f"{shelf}/{label}")
        if fn is not None:
            return fn
    # a factory label on another shelf (or a user shelf): the command's own picture, like Maya
    return next((fn for key, fn in ICONS.items() if key.split("/", 1)[1] == label), None)


def draw(label, shelf=None, greyed=False, size=32, index=None):
    """``size`` x ``size`` RGBA (float, straight alpha, rows top-down) icon for a shelf button; ``greyed``: grey
    and faded. ``index`` (button position in its shelf) separates Maya buttons that share a label."""
    cv = Canvas(size)
    fn = icon_for(label, shelf, index)
    if fn is None:
        user_button(cv, label)
    else:
        fn(cv)
    px = cv.result()
    return grey(px) if greyed else px


def grey(px):
    """A greyed button's picture: grey and faded, like a disabled Maya control (in place; returns ``px``)."""
    lum = px[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)
    px[..., :3] = (lum * 0.8)[..., None]
    px[..., 3] *= GREYED_ALPHA
    return px


# --- GPU textures -----------------------------------------------------------------------------

_textures = {}


def texture_size(drawn_px):
    """Texture resolution for an icon drawn ``drawn_px`` pixels wide: the 2x picture above 32 px (UI scale >= 1.25)."""
    return 64 if drawn_px > 32 + 0.5 else 32


def texture(label, shelf=None, greyed=False, size=32, index=None):
    """Cached GPU texture of a button's icon (needs a GPU context: call from a draw handler)."""
    key = (label, shelf, greyed, size, index)
    tex = _textures.get(key)
    if tex is None:
        tex = _textures[key] = _upload(draw(label, shelf, greyed, size, index), size)
    return tex


def texture_of(key, make, greyed=False, size=32):
    """Cached GPU texture of another kit picture on the shelf (a menu item's drawing): ``make(n)`` gives
    the (n, n, 4) picture, top row first; ``key`` names it."""
    full = ("picture", key, greyed, size)
    tex = _textures.get(full)
    if tex is None:
        px = np.array(make(size), dtype=np.float32)
        tex = _textures[full] = _upload(grey(px) if greyed else px, size)
    return tex


def _upload(px, size):
    import gpu
    px = px[::-1].copy()   # GPU rows go bottom-up
    # the palette is sRGB; the image editor draws in linear and converts for display
    rgb = px[..., :3]
    px[..., :3] = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    buf = gpu.types.Buffer('FLOAT', size * size * 4, px.ravel().tolist())
    return gpu.types.GPUTexture((size, size), format='RGBA32F', data=buf)


def clear():
    _textures.clear()
