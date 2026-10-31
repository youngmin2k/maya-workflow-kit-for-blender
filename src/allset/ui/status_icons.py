# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit-drawn Maya-style icons for the Status Line, the menu bar and the viewport panel toolbar
(#23).

No Maya icons. The Status Line (20 px) and panel toolbar (16 px) glyphs are flat light-grey #bcbcbc line art
with teal #48a9b4 accents, a dark outline around every shape and no button frame.
Every glyph here is a few vector shapes in unit coordinates, rasterised
with numpy (supersampled, no files) and handed to Blender as a ``bpy.utils.previews`` image (``icon_value``).

Pixel hinting: ``Canvas`` snaps rectangle edges to the target size's pixel grid, rounds line widths to whole pixels
(at least one) and centres odd-width strokes and odd-diameter discs on pixel centres, so the same drawing is crisp at
16, 20, 24, 32 and 48 px. ``image(name, size)`` is that picture (top-down straight-alpha RGBA) with the dark
outline added at the final size. Blender draws a button icon at 16 px x UI scale; ``icon(name)`` hands it a picture
of exactly that size (one image pixel per screen pixel) and rebuilds the previews when the UI scale changes.
"""

import math

import numpy as np

SIZE = 32          # default drawing size (``Canvas`` / ``render``)
SS = 4             # minimum supersampling
GREY = (0.74, 0.74, 0.74)      # glyph grey #bcbcbc
LIGHT = (0.88, 0.88, 0.88)     # pointer / highlight
DIM = (0.55, 0.55, 0.55)
TEAL = (0.28, 0.66, 0.71)      # accent #48a9b4
TEAL_DARK = (0.18, 0.47, 0.52)
TEAL_LIGHT = (0.55, 0.84, 0.88)
BLUE = (0.40, 0.62, 0.86)
ORANGE = (0.90, 0.58, 0.30)
DARK = (0.20, 0.20, 0.20)
OUTLINE = (0.13, 0.13, 0.13)   # the #3a3a3a outline, darker so it also shows on Blender's darker header


class Canvas:
    """RGBA canvas in unit coordinates (0..1, y down), supersampled, with pixel hinting for ``size``."""

    def __init__(self, size=SIZE, hint=True):
        self.size = size
        self.ss = max(SS, -(-128 // size))
        n = size * self.ss
        c = (np.arange(n) + 0.5) / n
        self.x, self.y = np.meshgrid(c, c)
        self.px = np.zeros((n, n, 4), np.float32)
        self.hint = hint

    # hinting -----------------------------------------------------------------------------------------
    def edge(self, v):
        """``v`` on the nearest pixel boundary."""
        return round(v * self.size) / self.size if self.hint else v

    def width(self, w):
        """A stroke width of whole pixels (at least one)."""
        return max(1, round(w * self.size)) / self.size if self.hint else w

    def centre(self, v, w):
        """Centre of a stroke / disc ``w`` wide: odd pixel counts sit on a pixel centre, even ones on a boundary."""
        if not self.hint:
            return v
        n = round(w * self.size)
        if n % 2:
            return (math.floor(v * self.size) + 0.5) / self.size
        return round(v * self.size) / self.size

    # compositing -------------------------------------------------------------------------------------
    def fill(self, mask, colour, alpha=1.0):
        a = mask.astype(np.float32) * alpha
        out = self.px
        oa = out[..., 3]
        na = a + oa * (1 - a)
        safe = np.where(na > 0, na, 1)
        for i in range(3):
            out[..., i] = (colour[i] * a + out[..., i] * oa * (1 - a)) / safe
        out[..., 3] = na

    def clear(self, mask):
        self.px[..., 3] *= 1 - mask.astype(np.float32)

    # shapes ------------------------------------------------------------------------------------------
    def rect_mask(self, x0, y0, x1, y1):
        x0, y0, x1, y1 = self.edge(x0), self.edge(y0), self.edge(x1), self.edge(y1)
        if self.hint:
            p = 1 / self.size
            x1, y1 = max(x1, x0 + p), max(y1, y0 + p)
        return (self.x >= x0) & (self.x <= x1) & (self.y >= y0) & (self.y <= y1)

    def rect(self, x0, y0, x1, y1, colour):
        self.fill(self.rect_mask(x0, y0, x1, y1), colour)

    def frame(self, x0, y0, x1, y1, w, colour):
        w = self.width(w)
        x0, y0, x1, y1 = self.edge(x0), self.edge(y0), self.edge(x1), self.edge(y1)
        outer = (self.x >= x0) & (self.x <= x1) & (self.y >= y0) & (self.y <= y1)
        inner = (self.x > x0 + w) & (self.x < x1 - w) & (self.y > y0 + w) & (self.y < y1 - w)
        self.fill(outer & ~inner, colour)

    def seg_mask(self, ax, ay, bx, by, w):
        w = self.width(w)
        if self.hint and (abs(ax - bx) < 1e-6 or abs(ay - by) < 1e-6):
            # axis-aligned: a pixel-exact bar with square caps (joins of polylines stay closed)
            if abs(ax - bx) < 1e-6:
                c = self.centre(ax, w)
                y0, y1 = sorted((ay, by))
                return self.rect_mask(c - w / 2, y0 - w / 2, c + w / 2, y1 + w / 2)
            c = self.centre(ay, w)
            x0, x1 = sorted((ax, bx))
            return self.rect_mask(x0 - w / 2, c - w / 2, x1 + w / 2, c + w / 2)
        ax, ay, bx, by = self.centre(ax, w), self.centre(ay, w), self.centre(bx, w), self.centre(by, w)
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy or 1e-9
        t = np.clip(((self.x - ax) * dx + (self.y - ay) * dy) / L, 0, 1)
        return (self.x - ax - t * dx) ** 2 + (self.y - ay - t * dy) ** 2 <= (w / 2) ** 2

    def line(self, ax, ay, bx, by, w, colour):
        self.fill(self.seg_mask(ax, ay, bx, by, w), colour)

    def polyline(self, pts, w, colour):
        m = np.zeros_like(self.x, bool)
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            m |= self.seg_mask(ax, ay, bx, by, w)
        self.fill(m, colour)

    def disc_mask(self, cx, cy, r):
        d = self.width(2 * r)
        cx, cy = self.centre(cx, d), self.centre(cy, d)
        r = d / 2
        return (self.x - cx) ** 2 + (self.y - cy) ** 2 <= r * r

    def circle(self, cx, cy, r, colour):
        self.fill(self.disc_mask(cx, cy, r), colour)

    def ring_mask(self, cx, cy, r, w, a0=None, a1=None):
        w = self.width(w)
        d = self.width(2 * r + w)
        cx, cy = self.centre(cx, d), self.centre(cy, d)
        r = d / 2 - w / 2
        dist = np.sqrt((self.x - cx) ** 2 + (self.y - cy) ** 2)
        m = np.abs(dist - r) <= w / 2
        if a0 is not None:
            ang = np.degrees(np.arctan2(-(self.y - cy), self.x - cx)) % 360
            m &= ((ang - a0) % 360) <= ((a1 - a0) % 360)
        return m

    def ring(self, cx, cy, r, w, colour, a0=None, a1=None):
        self.fill(self.ring_mask(cx, cy, r, w, a0, a1), colour)

    def poly_mask(self, pts):
        pts = [(self.edge(x), self.edge(y)) for x, y in pts]
        inside = np.zeros_like(self.x, bool)
        n = len(pts)
        for i in range(n):
            (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
            cond = (y1 > self.y) != (y2 > self.y)
            with np.errstate(divide='ignore', invalid='ignore'):
                xi = (x2 - x1) * (self.y - y1) / ((y2 - y1) if y2 != y1 else 1e-9) + x1
            inside ^= cond & (self.x < xi)
        return inside

    def poly(self, pts, colour):
        self.fill(self.poly_mask(pts), colour)

    # output ------------------------------------------------------------------------------------------
    def array(self):
        """(size, size, 4) float32, top row first, straight alpha (premultiplied box filter)."""
        s, k = self.size, self.ss
        p = self.px.reshape(s, k, s, k, 4)
        a = p[..., 3].mean(axis=(1, 3))
        rgb = (p[..., :3] * p[..., 3:4]).mean(axis=(1, 3)) / np.maximum(a, 1e-6)[..., None]
        return np.concatenate([rgb, a[..., None]], axis=2).astype(np.float32)

    def pixels(self):
        """Flat RGBA floats, bottom row first (Blender image order)."""
        return self.array()[::-1].ravel()


def outlined(img, colour=OUTLINE, alpha=0.9):
    """Maya's dark outline: the shape's alpha grown by one pixel (8-neighbourhood), drawn behind it."""
    a = img[..., 3]
    p = np.pad(a, 1)
    h, w = a.shape
    grown = np.max([p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1)], axis=0)
    ha = grown * alpha
    na = a + ha * (1 - a)
    safe = np.where(na > 0, na, 1)[..., None]
    rgb = (img[..., :3] * a[..., None] + np.array(colour, np.float32) * (ha * (1 - a))[..., None]) / safe
    return np.concatenate([rgb, na[..., None]], axis=2).astype(np.float32)


# --- shared parts -----------------------------------------------------------------------------------

def arrow_cursor(cv, x, y, s, colour=LIGHT):
    """Mouse pointer with its tip at (x, y), height s."""
    cv.poly([(x, y), (x, y + s), (x + s * 0.28, y + s * 0.75), (x + s * 0.5, y + s * 1.05),
             (x + s * 0.62, y + s * 0.98), (x + s * 0.42, y + s * 0.68), (x + s * 0.72, y + s * 0.68)], colour)


def magnet(cv, colour=GREY):
    """Maya's snap magnet: a horseshoe whose bend is upper left, legs pointing to the lower right, teal pole tips."""
    cx, cy, r, w = 0.36, 0.36, 0.20, 0.15
    cv.ring(cx, cy, r, w, colour, 45, 225)
    c, s = math.cos(math.radians(45)), math.sin(math.radians(45))
    for (ex, ey) in ((cx + r * c, cy - r * s), (cx - r * c, cy + r * s)):
        mx, my = ex + 0.12, ey + 0.12
        cv.line(ex, ey, mx, my, w, colour)
        cv.line(mx, my, mx + 0.09, my + 0.09, w, TEAL)


def gear(cv, cx, cy, r, colour):
    for k in range(8):
        a = k * math.pi / 4
        cv.line(cx + math.cos(a) * r * 0.6, cy + math.sin(a) * r * 0.6,
                cx + math.cos(a) * r, cy + math.sin(a) * r, r * 0.42, colour)
    cv.circle(cx, cy, r * 0.72, colour)
    cv.circle(cx, cy, r * 0.30, DARK)


def clapper(cv, colour=GREY, top=0.06):
    """Maya's clapperboard: a striped clapstick over the board (Render View)."""
    cv.rect(0.06, top, 0.94, top + 0.20, colour)
    for i in range(4):
        x = 0.14 + i * 0.22
        cv.poly([(x, top), (x + 0.09, top), (x + 0.03, top + 0.20), (x - 0.06, top + 0.20)], DARK)
    cv.rect(0.06, top + 0.27, 0.94, 0.94, colour)


def stack(cv, cx, cy, s, colour, gap=DARK):
    """Layer stack: three flat diamonds (Render Setup / Channel Box layers)."""
    for k in (2, 1, 0):
        y = cy + (k - 1) * s * 0.42
        cv.poly([(cx - s, y), (cx, y - s * 0.55), (cx + s, y), (cx, y + s * 0.55)], gap)
        cv.poly([(cx - s * 0.86, y), (cx, y - s * 0.46), (cx + s * 0.86, y), (cx, y + s * 0.46)],
                LIGHT if k == 0 else colour)


def letter(cv, ch, x, y, h, w, colour):
    """Block capitals for badges: I P R O N F T, top-left at (x, y), height h, stroke w."""
    hw = h * 0.55
    if ch == "I":
        cv.line(x + hw / 2, y, x + hw / 2, y + h, w, colour)
    elif ch == "T":
        cv.line(x, y, x + hw * 1.2, y, w, colour)
        cv.line(x + hw * 0.6, y, x + hw * 0.6, y + h, w, colour)
    elif ch in "PR":
        cv.line(x, y, x, y + h, w, colour)
        cv.polyline([(x, y), (x + hw, y), (x + hw, y + h * 0.5), (x, y + h * 0.5)], w, colour)
        if ch == "R":
            cv.line(x + hw * 0.4, y + h * 0.5, x + hw, y + h, w, colour)
    elif ch == "F":
        cv.line(x, y, x, y + h, w, colour)
        cv.line(x, y, x + hw, y, w, colour)
        cv.line(x, y + h * 0.5, x + hw * 0.8, y + h * 0.5, w, colour)
    elif ch == "O":
        cv.polyline([(x, y), (x + hw, y), (x + hw, y + h), (x, y + h), (x, y)], w, colour)
    elif ch == "N":
        cv.line(x, y, x, y + h, w, colour)
        cv.line(x + hw, y, x + hw, y + h, w, colour)
        cv.line(x, y, x + hw, y + h, w, colour)


# --- Status Line glyphs (20 px) ------------------------------

def g_bar(cv):
    cv.line(0.5, 0.15, 0.5, 0.85, 0.08, DIM)


def g_open(cv):
    cv.polyline([(0.38, 0.28), (0.64, 0.5), (0.38, 0.72), (0.38, 0.28)], 0.06, DIM)


def g_closed(cv):
    cv.poly([(0.36, 0.24), (0.68, 0.5), (0.36, 0.76)], DIM)


def g_new(cv):
    cv.poly([(0.20, 0.06), (0.56, 0.06), (0.82, 0.32), (0.82, 0.94), (0.20, 0.94)], GREY)
    cv.poly([(0.56, 0.06), (0.56, 0.32), (0.82, 0.32)], DIM)
    cv.line(0.56, 0.32, 0.82, 0.32, 0.06, DARK)
    cv.line(0.56, 0.06, 0.56, 0.32, 0.06, DARK)


def g_open_scene(cv):
    cv.poly([(0.06, 0.18), (0.36, 0.18), (0.44, 0.28), (0.84, 0.28), (0.84, 0.86), (0.06, 0.86)], DIM)
    cv.poly([(0.22, 0.44), (0.96, 0.44), (0.80, 0.86), (0.06, 0.86)], GREY)


def g_save(cv):
    cv.poly([(0.08, 0.08), (0.80, 0.08), (0.92, 0.20), (0.92, 0.92), (0.08, 0.92)], GREY)
    cv.rect(0.26, 0.08, 0.70, 0.36, DARK)
    cv.rect(0.54, 0.14, 0.64, 0.30, GREY)
    cv.rect(0.22, 0.52, 0.78, 0.92, DARK)
    cv.rect(0.30, 0.60, 0.70, 0.84, DIM)


def _hook(cv, mirror):
    """Maya undo: arrowhead upper left, shaft right, bending down and back to the middle."""
    f = (lambda x: 1 - x) if mirror else (lambda x: x)
    w = 0.15
    cv.line(f(0.30), 0.34, f(0.62), 0.34, w, GREY)
    cv.ring(f(0.62), 0.55, 0.21, w, GREY, *((270, 90) if not mirror else (90, 270)))
    cv.line(f(0.62), 0.76, f(0.40), 0.76, w, GREY)
    cv.poly([(f(0.04), 0.34), (f(0.34), 0.08), (f(0.34), 0.60)], GREY)


def g_undo(cv):
    _hook(cv, False)


def g_redo(cv):
    _hook(cv, True)


def g_sel_hierarchy(cv):
    cv.rect(0.06, 0.06, 0.34, 0.32, GREY)
    cv.rect(0.06, 0.62, 0.34, 0.88, GREY)
    cv.polyline([(0.34, 0.19), (0.58, 0.19), (0.58, 0.40)], 0.08, TEAL)
    cv.line(0.20, 0.32, 0.20, 0.62, 0.08, GREY)
    arrow_cursor(cv, 0.50, 0.42, 0.52)


def g_sel_object(cv):
    cv.rect(0.34, 0.06, 0.74, 0.44, TEAL)
    cv.circle(0.30, 0.62, 0.24, GREY)
    arrow_cursor(cv, 0.52, 0.40, 0.54)


def g_sel_component(cv):
    for i in range(2):
        for j in range(2):
            cv.rect(0.06 + i * 0.30, 0.06 + j * 0.30, 0.30 + i * 0.30, 0.30 + j * 0.30, TEAL if i == j == 0 else GREY)
    arrow_cursor(cv, 0.54, 0.42, 0.52)


def g_mask_handles(cv):
    cv.line(0.5, 0.10, 0.5, 0.90, 0.11, TEAL)
    cv.line(0.10, 0.5, 0.90, 0.5, 0.11, TEAL)


def g_mask_joints(cv):
    cv.poly([(0.74, 0.20), (0.82, 0.30), (0.34, 0.58), (0.28, 0.48)], TEAL_DARK)
    cv.poly([(0.30, 0.56), (0.40, 0.52), (0.68, 0.84), (0.60, 0.88)], TEAL_DARK)
    for x, y, r in ((0.78, 0.22, 0.13), (0.30, 0.52, 0.13), (0.66, 0.86, 0.10)):
        cv.circle(x, y, r, TEAL)


def g_mask_curves(cv):
    pts = []
    for t in np.linspace(0, 1, 28):
        # cubic from the upper-left CV to the lower-right CV (an S)
        p0, p1, p2, p3 = (0.20, 0.22), (0.90, 0.10), (0.10, 0.90), (0.80, 0.78)
        u = 1 - t
        pts.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    cv.polyline(pts, 0.09, TEAL)
    for x, y in ((0.14, 0.16), (0.74, 0.72)):
        cv.rect(x, y, x + 0.16, y + 0.16, TEAL)
        cv.rect(x + 0.05, y + 0.05, x + 0.11, y + 0.11, DARK)


def g_mask_surfaces(cv):
    """NURBS quilt: a teal diamond patch of 2 x 2 diamonds."""
    cv.poly([(0.5, 0.06), (0.94, 0.5), (0.5, 0.94), (0.06, 0.5)], TEAL)
    cv.line(0.28, 0.28, 0.72, 0.72, 0.08, TEAL_DARK)
    cv.line(0.72, 0.28, 0.28, 0.72, 0.08, TEAL_DARK)
    for x, y in ((0.5, 0.25), (0.25, 0.5), (0.75, 0.5), (0.5, 0.75)):
        cv.circle(x, y, 0.07, TEAL_LIGHT)


def g_mask_deformers(cv):
    """Lattice: teal square with corner points and a bent inner shape."""
    cv.frame(0.12, 0.12, 0.88, 0.88, 0.08, TEAL)
    cv.poly([(0.30, 0.30), (0.70, 0.26), (0.66, 0.70), (0.34, 0.66)], TEAL_DARK)
    for x, y in ((0.06, 0.06), (0.76, 0.06), (0.06, 0.76), (0.76, 0.76)):
        cv.rect(x, y, x + 0.18, y + 0.18, TEAL)
        cv.rect(x + 0.06, y + 0.06, x + 0.12, y + 0.12, DARK)


def g_mask_dynamics(cv):
    for x, y, r in ((0.70, 0.30, 0.15), (0.40, 0.56, 0.12), (0.76, 0.70, 0.10), (0.20, 0.30, 0.07),
                    (0.44, 0.18, 0.06), (0.18, 0.80, 0.08), (0.52, 0.88, 0.05)):
        cv.circle(x, y, r, TEAL)


def g_mask_rendering(cv):
    clapper(cv, TEAL_DARK, top=0.04)
    cv.circle(0.32, 0.66, 0.26, TEAL)
    cv.circle(0.26, 0.58, 0.08, TEAL_LIGHT)


def g_mask_misc(cv):
    cv.ring(0.5, 0.32, 0.20, 0.13, TEAL, 330, 180)
    cv.polyline([(0.66, 0.42), (0.5, 0.56), (0.5, 0.66)], 0.13, TEAL)
    cv.circle(0.5, 0.85, 0.08, TEAL)


def g_vertex(cv):
    cv.frame(0.18, 0.18, 0.82, 0.82, 0.10, GREY)
    cv.rect(0.38, 0.38, 0.62, 0.62, GREY)


def g_edge(cv):
    cv.line(0.20, 0.20, 0.80, 0.80, 0.10, GREY)
    cv.circle(0.20, 0.20, 0.05, DIM)
    cv.circle(0.80, 0.80, 0.05, DIM)


def g_face(cv):
    for x, y, filled in ((0.08, 0.08, False), (0.08, 0.52, True), (0.52, 0.52, False)):
        cv.frame(x, y, x + 0.40, y + 0.40, 0.08, GREY)
        if filled:
            cv.rect(x + 0.08, y + 0.08, x + 0.32, y + 0.32, DIM)
        cv.circle(x + 0.20, y + 0.20, 0.05, GREY)


def _snap(target):
    def draw(cv):
        magnet(cv)
        target(cv)
    draw.__name__ = "snap_" + target.__name__
    return draw


def _t_grid(cv):
    for k in (0.68, 0.86):
        cv.line(k, 0.54, k, 0.98, 0.07, TEAL)
        cv.line(0.54, k, 0.98, k, 0.07, TEAL)


def _t_curve(cv):
    cv.ring(0.40, 0.34, 0.58, 0.09, TEAL, 255, 345)


def _t_point(cv):
    cv.circle(0.80, 0.80, 0.14, TEAL)


def _t_projected(cv):
    cv.ring(0.74, 0.76, 0.14, 0.07, TEAL)
    cv.circle(0.74, 0.76, 0.05, TEAL)
    cv.line(0.50, 0.76, 0.58, 0.76, 0.06, TEAL)
    cv.line(0.74, 0.92, 0.74, 0.98, 0.06, TEAL)
    cv.frame(0.80, 0.04, 0.96, 0.20, 0.06, TEAL)


def _t_plane(cv):
    cv.poly([(0.50, 0.80), (0.80, 0.52), (0.98, 0.70), (0.68, 0.98)], TEAL)
    cv.line(0.65, 0.66, 0.83, 0.84, 0.05, TEAL_DARK)


def _t_live(cv):
    """Make Live uses the bare magnet, without a snapping target glyph."""
    pass


def g_history(cv):
    cv.circle(0.30, 0.30, 0.25, GREY)
    cv.line(0.30, 0.30, 0.30, 0.14, 0.06, DARK)
    cv.line(0.30, 0.30, 0.42, 0.30, 0.06, DARK)
    for y in (0.40, 0.62, 0.84):
        cv.rect(0.60 if y < 0.5 else 0.40, y - 0.05, 0.94, y + 0.05, GREY)
    for y in (0.62, 0.84):
        cv.rect(0.10, y - 0.05, 0.28, y + 0.05, GREY)


def g_render_view(cv):
    clapper(cv)
    cv.poly([(0.16, 0.66), (0.34, 0.50), (0.66, 0.50), (0.84, 0.66), (0.66, 0.82), (0.34, 0.82)], DARK)
    cv.poly([(0.24, 0.66), (0.38, 0.55), (0.62, 0.55), (0.76, 0.66), (0.62, 0.77), (0.38, 0.77)], GREY)
    cv.circle(0.5, 0.66, 0.11, DARK)


def g_render(cv):
    clapper(cv)


def g_ipr(cv):
    clapper(cv)
    for i, ch in enumerate("IPR"):
        letter(cv, ch, 0.20 + i * 0.23, 0.48, 0.34, 0.08, DARK)


def g_render_settings(cv):
    clapper(cv)
    gear(cv, 0.70, 0.70, 0.27, TEAL)


def g_hypershade(cv):
    cv.circle(0.5, 0.5, 0.44, TEAL_DARK)
    cv.circle(0.46, 0.46, 0.36, TEAL)
    cv.circle(0.5, 0.5, 0.18, GREY)
    cv.circle(0.46, 0.45, 0.07, LIGHT)


def g_render_setup(cv):
    clapper(cv)
    stack(cv, 0.68, 0.70, 0.30, TEAL)


def g_light_editor(cv):
    # spot lamp pointing to the lower left, its rays teal, and Maya's teal gear at the lower right
    cv.line(0.66, 0.10, 0.40, 0.36, 0.22, GREY)
    cv.poly([(0.26, 0.34), (0.42, 0.18), (0.56, 0.46), (0.48, 0.54)], GREY)
    for (ax, ay, bx, by) in ((0.22, 0.48, 0.08, 0.62), (0.34, 0.58, 0.26, 0.74), (0.14, 0.36, 0.04, 0.40)):
        cv.line(ax, ay, bx, by, 0.07, TEAL)
    gear(cv, 0.72, 0.72, 0.25, TEAL)


def g_pause(cv):
    cv.rect(0.24, 0.14, 0.42, 0.86, GREY)
    cv.rect(0.58, 0.14, 0.76, 0.86, GREY)


def g_modeling_toolkit(cv):
    cv.poly([(0.04, 0.46), (0.32, 0.32), (0.60, 0.46), (0.32, 0.60)], LIGHT)
    cv.poly([(0.04, 0.46), (0.32, 0.60), (0.32, 0.96), (0.04, 0.82)], DIM)
    cv.poly([(0.32, 0.60), (0.60, 0.46), (0.60, 0.82), (0.32, 0.96)], GREY)
    cv.rect(0.50, 0.06, 0.96, 0.22, GREY)
    cv.line(0.80, 0.22, 0.80, 0.94, 0.11, GREY)


def g_character(cv):
    cv.circle(0.5, 0.13, 0.10, GREY)
    cv.rect(0.06, 0.28, 0.94, 0.38, GREY)
    cv.rect(0.34, 0.28, 0.66, 0.62, GREY)
    cv.rect(0.44, 0.40, 0.56, 0.52, DARK)
    cv.rect(0.34, 0.62, 0.45, 0.94, GREY)
    cv.rect(0.55, 0.62, 0.66, 0.94, GREY)


def g_attribute_editor(cv):
    for k, y in enumerate((0.20, 0.50, 0.80)):
        cv.rect(0.04, y - 0.04, 0.26, y + 0.04, GREY)
        cv.frame(0.32, y - 0.11, 0.96, y + 0.11, 0.06, GREY)
        kx = (0.46, 0.66, 0.84)[k]
        cv.rect(kx - 0.06, y - 0.06, kx + 0.06, y + 0.06, LIGHT)


def g_tool_settings(cv):
    for y in (0.24, 0.50, 0.76):
        cv.rect(0.04, y - 0.05, 0.18, y + 0.05, GREY)
        cv.rect(0.26, y - 0.05, 0.58, y + 0.05, GREY)
    cv.rect(0.62, 0.06, 0.98, 0.24, GREY)
    cv.line(0.84, 0.24, 0.84, 0.94, 0.11, GREY)


def g_channel_box(cv):
    stack(cv, 0.5, 0.52, 0.46, GREY)
    for y in (0.28, 0.36):
        cv.line(0.36, y, 0.64, y, 0.05, DIM)


def g_workspace(cv):
    cv.frame(0.10, 0.18, 0.90, 0.82, 0.06, GREY)
    cv.line(0.36, 0.18, 0.36, 0.82, 0.06, GREY)


GLYPHS = {
    "bar": g_bar, "open": g_open, "closed": g_closed,
    "new": g_new, "open_scene": g_open_scene, "save": g_save, "undo": g_undo, "redo": g_redo,
    "sel_hierarchy": g_sel_hierarchy, "sel_object": g_sel_object, "sel_component": g_sel_component,
    "mask_HANDLES": g_mask_handles, "mask_JOINTS": g_mask_joints, "mask_CURVES": g_mask_curves,
    "mask_SURFACES": g_mask_surfaces, "mask_DEFORMERS": g_mask_deformers, "mask_DYNAMICS": g_mask_dynamics,
    "mask_RENDERING": g_mask_rendering, "mask_MISC": g_mask_misc,
    "vertex": g_vertex, "edge": g_edge, "face": g_face,
    "snap_GRID": _snap(_t_grid), "snap_CURVE": _snap(_t_curve), "snap_POINT": _snap(_t_point),
    "snap_PROJECTED": _snap(_t_projected), "snap_PLANE": _snap(_t_plane), "snap_LIVE": _snap(_t_live),
    "history": g_history,
    "render_view": g_render_view, "render": g_render, "ipr": g_ipr, "render_settings": g_render_settings,
    "hypershade": g_hypershade, "render_setup": g_render_setup, "light_editor": g_light_editor, "pause": g_pause,
    "ed_MODELING_TOOLKIT": g_modeling_toolkit, "ed_CHARACTER": g_character, "ed_ATTRIBUTE": g_attribute_editor,
    "ed_TOOL_SETTINGS": g_tool_settings, "ed_CHANNEL_BOX": g_channel_box,
    "workspace": g_workspace,
}

# Status Line chrome (group bar, collapse handles): drawn without Maya's outline.
CHROME = {"bar", "open", "closed"}

EXTRA = {}     # name -> drawing function, added by other modules (panel toolbar glyphs) before first use


def _glyph(name):
    return GLYPHS.get(name) or EXTRA[name]


def render(name, size=SIZE):
    cv = Canvas(size)
    _glyph(name)(cv)
    return cv


def image(name, size=SIZE):
    """Glyph ``name`` at ``size`` px: (size, size, 4) float32, top row first, straight alpha, Maya outline added."""
    img = render(name, size).array()
    if name in CHROME:
        return img
    return outlined(img)


# --- previews ---------------------------------------------------------------------------------------
#
# Blender draws a button icon at round(16 x UI scale) px and resamples a preview of another size; a preview of the
# drawn size shows the hinted pixels 1:1. Previews are keyed by
# name and size ("undo@20"): a UI scale change makes new previews (from a timer, never inside a header draw while
# an old-size preview can stand in) instead of rewriting pixels Blender may have cached on the GPU.

_pcoll = []
_size = []      # the icon size the previews were last made for


def _collection():
    if not _pcoll:
        import bpy.utils.previews
        _pcoll.append(bpy.utils.previews.new())
    return _pcoll[0]


def icon_px():
    """Pixel size Blender draws a 16 px button icon at, for the current UI scale."""
    import bpy
    s = bpy.context.preferences.system.ui_scale or 1.0      # 0 in background
    return max(16, int(round(16 * s)))


def _make(pc, name, size):
    key = f"{name}@{size}"
    p = pc.get(key)
    if p is None:
        px = image(name, size)[::-1].ravel()
        p = pc.new(key)
        p.icon_size = (size, size)
        p.icon_pixels_float = px
        p.image_size = (size, size)
        p.image_pixels_float = px
    return p


def icon(name):
    """icon_value of glyph ``name`` at the current UI scale's icon size."""
    pc = _collection()
    size = icon_px()
    p = pc.get(f"{name}@{size}")
    if p is not None:
        return p.icon_id
    old = _size[0] if _size else None
    if old is not None and old != size:
        q = pc.get(f"{name}@{old}")
        if q is not None:           # stand-in until the timer has made this size
            _schedule()
            return q.icon_id
    return _make(pc, name, size).icon_id


def _schedule():
    import bpy
    if not bpy.app.timers.is_registered(make_all):
        bpy.app.timers.register(make_all, first_interval=0.0)


def _redraw():
    import bpy
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    try:
        from . import status_line
        status_line.redraw_top_bars()
    except Exception:
        pass


def make_all():
    """Create every glyph preview for the current icon size outside drawing (a timer after register and after a UI
    scale change): previews made while a header draws are avoided."""
    try:
        size = icon_px()
        pc = _collection()
        for name in list(GLYPHS) + list(EXTRA):
            _make(pc, name, size)
        changed = bool(_size) and _size[0] != size
        _size[:] = [size]
        if changed:
            _redraw()
    except Exception:   # never leave a timer raising
        pass
    return None


def register():
    import bpy
    if not bpy.app.background:
        bpy.app.timers.register(make_all, first_interval=0.0)


def unregister():
    import bpy
    if bpy.app.timers.is_registered(make_all):
        bpy.app.timers.unregister(make_all)
    _size.clear()
    if _pcoll:
        import bpy.utils.previews
        bpy.utils.previews.remove(_pcoll.pop())
