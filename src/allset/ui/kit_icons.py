# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit-drawn Maya-style icons for the Tool Box, the Layer Editor toolbar and the Outliner rows the kit draws
(issue #23).

No Maya icon files. Each glyph is a few vector shapes in a Maya-style icon palette (light grey #bdbdbd line
art, teal #48aab5 accents, a dark #3a3a3a rim) that follow the Maya
icon's silhouette, colour and composition, rasterised with numpy (``status_icons.Canvas``, 4x supersampled) at the
exact pixel size the icon is shown at, so nothing is resampled:

- shapes are written on a design grid (``base`` units: 32 for Tool Box tools, 16 for button / row icons) and
  every rectangle edge and axis-aligned line is snapped to whole pixels of the target size (pixel hinting at
  16 / 20 / 24 / 32 / 40 / 48 px = UI scale 1.0 / 1.25 / 1.5 and the 32-grid tools);
- a one-pixel dark rim is added around the glyph like Maya's icons (keeps light glyphs readable on light
  buttons, e.g. the embossed quick layout buttons).

Button / row icons reach layouts as ``bpy.utils.previews`` images (``icon_value``), one per (glyph, pixel size);
the Outliner rows (``outliner_sets``) draw ``pixels`` as GPU textures. The Tool Box tools are Blender vector icons
instead (``Geo`` -> ``bpy.app.icons.new_triangles``): Blender draws a preview icon in a toolbar button at the small
button size, a vector icon at the toolbar's tool size. They reach Blender's toolbar through
``ToolSelectPanelHelper``'s icon cache under kit-only names (``tool_icon_name``); unregister removes the names and
releases the icons.
"""

import math

import numpy as np

from .status_icons import SS, Canvas

LIGHT = (0.741, 0.741, 0.741)      # #bdbdbd  Maya icon grey
TEAL = (0.282, 0.667, 0.710)       # #48aab5  Maya icon accent
RIM = (0.227, 0.227, 0.227)        # #3a3a3a  Maya icon rim
DARK = (0.165, 0.165, 0.165)
DIMMED = (0.42, 0.42, 0.42)
RIM_ALPHA = 0.85

TOOL_BASE = 32      # design grid of the Tool Box tool icons
SMALL_BASE = 16     # design grid of button / row icons
# raster size of the tool glyphs at UI scale 1 (the sheets / tests; Blender's toolbar uses the vector version and
# sizes it itself)
TOOL_PX = 32
SMALL_PX = 16


class Pen:
    """Draw on a ``Canvas`` of ``n`` pixels in design units (0..base, y down), hinting edges to whole pixels."""

    def __init__(self, n, base):
        # the Pen does its own hinting: a Canvas that also snaps (status_icons) is
        # asked not to
        try:
            self.cv = Canvas(n, hint=False)
        except TypeError:
            self.cv = Canvas(n)
        self.n = n
        self.k = n / base

    # unit conversions ------------------------------------------------------------------------------------
    def u(self, v):                       # design units -> canvas units (no snapping)
        return v * self.k / self.n

    def edge(self, v):                    # snapped to a pixel boundary
        return round(v * self.k) / self.n

    def wpx(self, w):                     # stroke width in whole pixels (>= 1)
        return max(1, round(w * self.k))

    def centre(self, v, w):
        """Centre of a stroke of design width ``w`` at ``v``: on a pixel centre for odd pixel widths, on a boundary
        for even ones (so the stroke covers whole pixels)."""
        p = self.wpx(w)
        c = v * self.k
        c = math.floor(c) + 0.5 if p % 2 else round(c)
        return c / self.n

    # shapes ----------------------------------------------------------------------------------------------
    def rect(self, x0, y0, x1, y1, colour):
        cv = self.cv
        a, b, c, d = self.edge(x0), self.edge(y0), self.edge(x1), self.edge(y1)
        if c - a < 1 / self.n:
            c = a + 1 / self.n
        if d - b < 1 / self.n:
            d = b + 1 / self.n
        cv.fill((cv.x >= a) & (cv.x < c) & (cv.y >= b) & (cv.y < d), colour)

    def frame(self, x0, y0, x1, y1, w, colour):
        p = self.wpx(w) / self.n
        a, b, c, d = self.edge(x0), self.edge(y0), self.edge(x1), self.edge(y1)
        cv = self.cv
        outer = (cv.x >= a) & (cv.x < c) & (cv.y >= b) & (cv.y < d)
        inner = (cv.x >= a + p) & (cv.x < c - p) & (cv.y >= b + p) & (cv.y < d - p)
        cv.fill(outer & ~inner, colour)

    def hline(self, x0, x1, y, w, colour):
        h = self.wpx(w) / self.n / 2
        cy = self.centre(y, w)
        cv = self.cv
        cv.fill((cv.x >= self.edge(x0)) & (cv.x < self.edge(x1)) & (cv.y >= cy - h) & (cv.y < cy + h), colour)

    def vline(self, x, y0, y1, w, colour):
        h = self.wpx(w) / self.n / 2
        cx = self.centre(x, w)
        cv = self.cv
        cv.fill((cv.y >= self.edge(y0)) & (cv.y < self.edge(y1)) & (cv.x >= cx - h) & (cv.x < cx + h), colour)

    def line(self, ax, ay, bx, by, w, colour):
        self.cv.line(self.u(ax), self.u(ay), self.u(bx), self.u(by), self.wpx(w) / self.n, colour)

    def poly(self, pts, colour):
        self.cv.poly([(self.u(x), self.u(y)) for x, y in pts], colour)

    def circle(self, cx, cy, r, colour):
        self.cv.circle(self.u(cx), self.u(cy), self.u(r), colour)

    def ring(self, cx, cy, r, w, colour, a0=None, a1=None):
        self.cv.ring(self.u(cx), self.u(cy), self.u(r), self.wpx(w) / self.n, colour, a0, a1)

    def ellipse_ring(self, cx, cy, rx, ry, w, colour, tilt=0.0, dashes=0, duty=0.55, phase=0.0):
        """Ellipse outline (``tilt`` degrees, counter-clockwise on screen), optionally dashed."""
        cv = self.cv
        t = math.radians(tilt)
        dx, dy = cv.x - self.u(cx), cv.y - self.u(cy)
        ex = dx * math.cos(t) - dy * math.sin(t)
        ey = dx * math.sin(t) + dy * math.cos(t)
        rx, ry = self.u(rx), self.u(ry)
        q = np.sqrt((ex / rx) ** 2 + (ey / ry) ** 2)
        m = np.abs(q - 1) * min(rx, ry) <= self.wpx(w) / self.n / 2
        if dashes:
            ang = (np.arctan2(ey / ry, ex / rx) / (2 * math.pi) + phase) % 1.0
            m &= ((ang * dashes) % 1.0) < duty
        cv.fill(m, colour)

    def clear(self, mask_fn):
        self.cv.clear(mask_fn(self.cv))

    # result ----------------------------------------------------------------------------------------------
    def result(self, rim=True):
        """(n, n, 4) float32 RGBA, top row first, with Maya's dark rim around the glyph."""
        n = self.n
        ss = getattr(self.cv, "ss", SS)     # supersampling (per size in newer status_icons)
        p = self.cv.px.reshape(n, ss, n, ss, 4)
        a = p[..., 3].mean(axis=(1, 3))
        rgb = (p[..., :3] * p[..., 3:4]).mean(axis=(1, 3)) / np.maximum(a, 1e-6)[..., None]
        if rim:
            pad = np.pad(a, 1)
            grown = np.max([pad[1 + dy:1 + dy + n, 1 + dx:1 + dx + n] for dy in (-1, 0, 1) for dx in (-1, 0, 1)],
                           axis=0)
            ra = np.clip(grown, 0, 1) * RIM_ALPHA
            out_a = a + ra * (1 - a)
            safe = np.maximum(out_a, 1e-6)[..., None]
            rgb = (rgb * a[..., None] + np.array(RIM) * (ra * (1 - a))[..., None]) / safe
            a = out_a
        return np.concatenate([rgb, a[..., None]], axis=2).astype(np.float32)


def _triangulate(pts):
    """Ear clipping of a simple polygon -> [(a, b, c)] points."""
    pts = list(pts)
    area = sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts)))
    if area < 0:
        pts.reverse()

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(p, a, b, c):
        return cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0

    out = []
    idx = list(range(len(pts)))
    guard = 0
    while len(idx) > 3 and guard < 1000:
        guard += 1
        for i in range(len(idx)):
            a, b, c = pts[idx[i - 1]], pts[idx[i]], pts[idx[(i + 1) % len(idx)]]
            if cross(a, b, c) <= 0:
                continue
            if any(inside(pts[j], a, b, c) for j in idx if pts[j] not in (a, b, c)):
                continue
            out.append((a, b, c))
            idx.pop(i)
            break
        else:
            break
    if len(idx) == 3:
        out.append(tuple(pts[j] for j in idx))
    return out


class Geo:
    """The same drawing calls as ``Pen``, recorded as coloured triangles in design units (y down) for Blender's
    vector icons (``bpy.app.icons.new_triangles``): Blender rasterises those at the toolbar's own icon size, which
    is larger than a button icon (a preview icon in a toolbar button is drawn at 16 px x UI scale)."""

    SEG = 40

    def __init__(self, base):
        self.base = base
        self.tris = []      # [((x, y) * 3, colour)]

    def _quad(self, a, b, c, d, colour):
        self.tris.append(((a, b, c), colour))
        self.tris.append(((a, c, d), colour))

    def rect(self, x0, y0, x1, y1, colour):
        self._quad((x0, y0), (x1, y0), (x1, y1), (x0, y1), colour)

    def frame(self, x0, y0, x1, y1, w, colour):
        self.rect(x0, y0, x1, y0 + w, colour)
        self.rect(x0, y1 - w, x1, y1, colour)
        self.rect(x0, y0 + w, x0 + w, y1 - w, colour)
        self.rect(x1 - w, y0 + w, x1, y1 - w, colour)

    def hline(self, x0, x1, y, w, colour):
        self.rect(x0, y - w / 2, x1, y + w / 2, colour)

    def vline(self, x, y0, y1, w, colour):
        self.rect(x - w / 2, y0, x + w / 2, y1, colour)

    def line(self, ax, ay, bx, by, w, colour):
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1e-9
        nx, ny = -dy / L * w / 2, dx / L * w / 2
        self._quad((ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny), colour)

    def poly(self, pts, colour):
        for tri in _triangulate(pts):
            self.tris.append((tri, colour))

    def circle(self, cx, cy, r, colour):
        pts = [(cx + r * math.cos(2 * math.pi * i / self.SEG), cy + r * math.sin(2 * math.pi * i / self.SEG))
               for i in range(self.SEG)]
        for i in range(self.SEG):
            self.tris.append((((cx, cy), pts[i], pts[(i + 1) % self.SEG]), colour))

    def _strip(self, pt_in, pt_out, colour):
        for i in range(len(pt_in) - 1):
            self._quad(pt_in[i], pt_in[i + 1], pt_out[i + 1], pt_out[i], colour)

    def ring(self, cx, cy, r, w, colour, a0=None, a1=None):
        """Same angles as ``Canvas.ring``: degrees counter-clockwise on screen (y down), from a0 to a1."""
        if a0 is None:
            a0, span = 0.0, 360.0
        else:
            span = (a1 - a0) % 360 or 360.0
        n = max(2, int(self.SEG * span / 360) + 1)
        angs = [math.radians(a0 + span * i / (n - 1)) for i in range(n)]
        ri, ro = r - w / 2, r + w / 2
        self._strip([(cx + ri * math.cos(a), cy - ri * math.sin(a)) for a in angs],
                    [(cx + ro * math.cos(a), cy - ro * math.sin(a)) for a in angs], colour)

    def ellipse_ring(self, cx, cy, rx, ry, w, colour, tilt=0.0, dashes=0, duty=0.55, phase=0.0):
        t = math.radians(tilt)

        def at(u, grow):
            # parameter u (turns) of the ellipse in the frame Pen uses: (ex, ey) = R(t) (dx, dy)
            a = 2 * math.pi * (u - phase)
            ex, ey = (rx + grow) * math.cos(a), (ry + grow) * math.sin(a)
            return cx + ex * math.cos(t) + ey * math.sin(t), cy - ex * math.sin(t) + ey * math.cos(t)

        runs = [(i / dashes, (i + duty) / dashes) for i in range(dashes)] if dashes else [(0.0, 1.0)]
        for u0, u1 in runs:
            n = max(3, int(self.SEG * (u1 - u0)) + 2)
            us = [u0 + (u1 - u0) * i / (n - 1) for i in range(n)]
            self._strip([at(u, -w / 2) for u in us], [at(u, w / 2) for u in us], colour)

    def clear(self, mask_fn):
        pass

    def data(self, saturation=1.0):
        """(coords, colours) bytes for ``bpy.app.icons.new_triangles`` with range (0, 255): x right, y up.
        ``saturation`` = the theme's Icon Saturation, which Blender applies to toolbar vector icons
        (out = s * in + (1 - s) * luma, luma = 0.3 R + 0.59 G + 0.11 B; teal
        #48aab5 comes out #6a9ba1 at the default 0.5): colours are pre-compensated so the Maya teal shows."""
        k = 255.0 / self.base
        coords, cols = bytearray(), bytearray()
        for tri, colour in self.tris:
            rgb = compensate(colour[:3], saturation)
            for x, y in tri:
                coords += bytes((max(0, min(255, round(x * k))), max(0, min(255, round((self.base - y) * k)))))
                cols += bytes((*(max(0, min(255, round(c * 255))) for c in rgb), 255))
        return bytes(coords), bytes(cols)


def compensate(rgb, saturation):
    """Colour that Blender's icon desaturation (``saturation`` < 1) turns back into ``rgb`` (clamped)."""
    if saturation >= 0.999 or saturation <= 0.05:
        return tuple(rgb)
    luma = 0.3 * rgb[0] + 0.59 * rgb[1] + 0.11 * rgb[2]
    return tuple(min(1.0, max(0.0, luma + (c - luma) / saturation)) for c in rgb)


# --- Tool Box tools (32 grid; Maya Select / Lasso / Paint Selection / Move / Rotate / Scale) ----------

def _cursor(p, x, y, s, colour=LIGHT):
    """Maya's select pointer: tip at (x, y), ``s`` high, the tail to the lower right."""
    k = s / 26.0
    p.poly([(x, y), (x, y + 22 * k), (x + 5 * k, y + 17 * k), (x + 9.5 * k, y + 26 * k), (x + 13.5 * k, y + 24 * k),
            (x + 9 * k, y + 15.5 * k), (x + 16 * k, y + 15.5 * k)], colour)


def t_select(p):
    _cursor(p, 9, 3, 26)


def t_lasso(p):
    # a teal dashed lasso loop round the upper left, its knot over the pointer, the pointer lower right
    p.ellipse_ring(12.5, 13, 12, 5.5, 2.2, TEAL, tilt=40, dashes=10, duty=0.6, phase=0.02)
    _cursor(p, 15, 9, 21)


def t_paint_select(p):
    # a teal dashed loop with a grey paint brush lying across it, handle to the upper right
    p.ellipse_ring(14, 19, 12, 8, 2.2, TEAL, tilt=-28, dashes=11, duty=0.6)
    p.line(29.5, 2.5, 20.5, 12, 3.6, LIGHT)
    p.poly([(21.5, 10.5), (23, 13.5), (18, 18.5), (11, 20.5), (13.5, 14.5), (18.5, 11)], LIGHT)


def t_move(p):
    p.rect(10, 10, 22, 22, LIGHT)
    for (ax, ay), (bx, by), (cx, cy) in (((16, 1.5), (11.5, 6.5), (20.5, 6.5)), ((16, 30.5), (11.5, 25.5), (20.5, 25.5)),
                                         ((1.5, 16), (6.5, 11.5), (6.5, 20.5)), ((30.5, 16), (25.5, 11.5), (25.5, 20.5))):
        p.poly([(ax, ay), (bx, by), (cx, cy)], TEAL)


def t_rotate(p):
    # a teal circular arrow open at the lower right, arrowhead pointing down at the right; a grey diamond inside
    p.ring(15, 16, 13, 2.2, TEAL, 345, 265)
    p.poly([(23.5, 16.5), (32, 16.5), (27.75, 22)], TEAL)
    p.poly([(15, 7), (24, 16), (15, 25), (6, 16)], LIGHT)


def t_scale(p):
    # a grey square at the lower left inside a larger teal dashed square (scaled up) with a teal corner mark
    for x in (4, 10, 16, 22):
        p.hline(x, x + 3.5, 3.5, 2, TEAL)
    for y in (3, 9, 15, 21, 27):
        p.vline(28.5, y, y + 3.5, 2, TEAL)
    for x in (16, 22):
        p.hline(x, x + 3.5, 28.5, 2, TEAL)
    p.vline(3.5, 3, 6, 2, TEAL)
    p.hline(12, 20, 13, 2, TEAL)
    p.vline(19, 12, 20, 2, TEAL)
    p.rect(3, 18, 14, 29, LIGHT)


TOOLS = {
    "builtin.select_box": t_select, "builtin.select_lasso": t_lasso, "builtin.select_circle": t_paint_select,
    "builtin.move": t_move, "builtin.rotate": t_rotate, "builtin.scale": t_scale,
}


# --- quick layout buttons (16 grid; Maya Single Perspective / Four View / Two Side by Side / Outliner) ----

def _persp_mark(p, cx, cy, r, colour):
    """Maya's perspective panel mark: a quilt of four small diamonds round a light cross."""
    p.poly([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], colour)
    if r >= 3:      # room for the light diagonal cross that splits it into four
        h = r / 2
        p.line(cx - h, cy - h, cx + h, cy + h, 1, LIGHT)
        p.line(cx - h, cy + h, cx + h, cy - h, 1, LIGHT)


def _ortho_mark(p, x0, y0, x1, y1):
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    s = (x1 - x0) * 0.28
    p.hline(cx - s, cx + s, cy, 1, LIGHT)
    p.vline(cx, cy - s, cy + s, 1, LIGHT)


def l_single(p):
    p.frame(0, 0, 16, 16, 1, LIGHT)
    p.rect(2, 2, 14, 14, LIGHT)
    _persp_mark(p, 8, 8, 4, DARK)


def l_four(p):
    for (x0, y0) in ((0, 0), (0, 9), (9, 9)):
        p.frame(x0, y0, x0 + 7, y0 + 7, 1, LIGHT)
        _ortho_mark(p, x0, y0, x0 + 7, y0 + 7)
    p.rect(9, 0, 16, 7, LIGHT)
    _persp_mark(p, 12.5, 3.5, 2.2, DARK)


def l_two(p):
    p.frame(0, 0, 7, 16, 1, LIGHT)
    _ortho_mark(p, 0, 4, 7, 12)
    p.rect(9, 0, 16, 16, LIGHT)
    _persp_mark(p, 12.5, 8, 2.4, DARK)


def l_outliner(p):
    p.frame(0, 0, 16, 16, 1, LIGHT)
    p.rect(3, 3, 5, 5, LIGHT)
    p.hline(6, 12, 3, 1, LIGHT)
    p.vline(3, 5, 13, 1, DIMMED)
    for y, w in ((7, 13), (10, 11), (13, 12)):
        p.hline(4, 6, y - 1, 1, DIMMED)
        p.rect(6, y - 1, 8, y + 1, LIGHT)
        p.hline(9, w, y - 1, 1, LIGHT)


# --- Layer Editor toolbar (16 grid; Maya Move Up / Move Down / New Empty Layer / New Layer from Selected) ----------

def _layer(p):
    """Maya's display layer: a light grey sheet seen edge-on, pointing left."""
    p.poly([(0.5, 9.5), (6.5, 5), (13, 9.5), (6.5, 14)], LIGHT)


def le_up(p):
    _layer(p)
    p.poly([(11.5, 1), (15.5, 5.5), (7.5, 5.5)], TEAL)
    p.rect(10, 5.5, 13, 11, TEAL)


def le_down(p):
    _layer(p)
    p.rect(10, 2, 13, 8, TEAL)
    p.poly([(11.5, 12.5), (15.5, 8), (7.5, 8)], TEAL)


def le_new_empty(p):
    _layer(p)
    p.rect(9, 4, 15, 6, TEAL)
    p.rect(11, 2, 13, 8, TEAL)


def le_new_selected(p):
    _layer(p)
    p.circle(11.5, 4.5, 3.5, TEAL)


# --- Outliner rows the kit draws (16 grid; Maya out_objectSet / out_camera) ------------------------------------

def o_set(p):
    """Maya's set node: a grey ring round a dark disc holding a light ball and a teal flag."""
    p.circle(8, 8, 7.5, DARK)
    p.ring(8, 8, 6.75, 1.5, LIGHT)
    p.circle(6, 10, 2.6, LIGHT)
    p.rect(8, 4, 11, 12, TEAL)
    p.rect(9, 4, 11, 5.5, TEAL)


def o_camera(p):
    p.rect(1, 5, 10, 12, LIGHT)
    p.poly([(11, 7.5), (15.5, 4.5), (15.5, 12.5), (11, 9.5)], LIGHT)


GLYPHS = {
    # Tool Box tools: 32 grid
    **{f"tool:{k}": (fn, TOOL_BASE) for k, fn in TOOLS.items()},
    # quick layouts
    "layout:SINGLE": (l_single, SMALL_BASE), "layout:FOUR": (l_four, SMALL_BASE),
    "layout:FRONT_PERSP": (l_two, SMALL_BASE), "layout:OUTLINER": (l_outliner, SMALL_BASE),
    # Layer Editor toolbar
    "layer:UP": (le_up, SMALL_BASE), "layer:DOWN": (le_down, SMALL_BASE),
    "layer:NEW_EMPTY": (le_new_empty, SMALL_BASE), "layer:NEW_SELECTED": (le_new_selected, SMALL_BASE),
    # Outliner rows
    "outliner:SET": (o_set, SMALL_BASE), "outliner:CAMERA": (o_camera, SMALL_BASE),
}

# the Maya command / icon each glyph stands for
MAYA = {
    "tool:builtin.select_box": "Select Tool (aselect)", "tool:builtin.select_lasso": "Lasso Tool (lassoSelect)",
    "tool:builtin.select_circle": "Paint Selection Tool (artSelect)", "tool:builtin.move": "Move Tool (move_M)",
    "tool:builtin.rotate": "Rotate Tool (rotate_M)", "tool:builtin.scale": "Scale Tool (scale_M)",
    "layout:SINGLE": "Single Perspective View (singlePerspLayout)", "layout:FOUR": "Four View (fourViewLayout)",
    "layout:FRONT_PERSP": "Front/Persp (twoViewVerticalLayout)", "layout:OUTLINER": "Outliner (outliner)",
    "layer:UP": "Move layer up (moveLayerUp)", "layer:DOWN": "Move layer down (moveLayerDown)",
    "layer:NEW_EMPTY": "Create Empty Layer (newLayerEmpty)",
    "layer:NEW_SELECTED": "Create Layer from Selected (newLayerSelected)",
    "outliner:SET": "objectSet (out_objectSet)", "outliner:CAMERA": "camera (out_camera)",
}


def pixels(name, n, greyed=False):
    """(n, n, 4) RGBA float32 of glyph ``name`` at ``n`` pixels, top row first."""
    fn, base = GLYPHS[name]
    p = Pen(n, base)
    fn(p)
    px = p.result()
    if greyed:
        lum = px[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)
        px[..., :3] = (lum * 0.85)[..., None]
        px[..., 3] *= 0.6
    return px


def size_for(name, ui_scale):
    """Pixel size the glyph is shown at for this effective UI scale (preferences.system.ui_scale)."""
    base = TOOL_PX if name.startswith("tool:") else SMALL_PX
    return max(8, round(base * ui_scale))


# --- previews -----------------------------------------------------------------------------------------------------

_pcoll = []
_pending = set()


def _collection():
    if not _pcoll:
        import bpy.utils.previews
        _pcoll.append(bpy.utils.previews.new())
    return _pcoll[0]


def _key(name, n):
    return f"{name}@{n}"


def make(name, n):
    """Create the preview of ``name`` at ``n`` px; returns its icon id."""
    pc = _collection()
    key = _key(name, n)
    pv = pc.get(key)
    if pv is None:
        flat = pixels(name, n)[::-1].ravel()     # Blender images are bottom row first
        pv = pc.new(key)
        pv.icon_size = (n, n)
        pv.icon_pixels_float = flat
        pv.image_size = (n, n)
        pv.image_pixels_float = flat
    return pv.icon_id


def _make_pending():
    try:
        for name, n in list(_pending):
            make(name, n)
        _pending.clear()
        import bpy
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                area.tag_redraw()
    except Exception:    # a timer that raises is dropped
        _pending.clear()
    return None


def icon_id(name, context=None):
    """icon_value of ``name`` at the current UI scale, or 0 while it isn't made yet (made from a timer: previews
    aren't created while a region draws). Callers fall back to Blender's icon on 0."""
    import bpy
    context = context or bpy.context
    n = size_for(name, context.preferences.system.ui_scale)
    if _pcoll:
        pv = _pcoll[0].get(_key(name, n))
        if pv is not None:
            return pv.icon_id
    if bpy.app.background:
        return make(name, n)
    _pending.add((name, n))
    if not bpy.app.timers.is_registered(_make_pending):
        bpy.app.timers.register(_make_pending, first_interval=0.0)
    return 0


def button(layout, op, name, fallback, **kw):
    """``layout.operator`` with the kit glyph (Blender's ``fallback`` icon until the glyph is made)."""
    v = icon_id(name)
    if v:
        return layout.operator(op, icon_value=v, **kw)
    return layout.operator(op, icon=fallback, **kw)


# --- Tool Box: kit icons in Blender's toolbar ------------------------------------------------------------------

_cache_keys = set()     # names the kit put into ToolSelectPanelHelper's icon cache


_geom_ids = {}          # glyph name -> icon value of its vector (triangle) icon


def triangles(name, saturation=1.0):
    """(coords, colours) of glyph ``name`` as triangles (``Geo.data``)."""
    fn, base = GLYPHS[name]
    g = Geo(base)
    fn(g)
    return g.data(saturation)


def icon_saturation(context=None):
    import bpy
    try:
        return float((context or bpy.context).preferences.themes[0].user_interface.icon_saturation)
    except (AttributeError, IndexError):
        return 1.0


def geom_icon(name, context=None):
    """icon value of glyph ``name`` as a Blender vector icon (made once per theme icon saturation; Blender draws it at
    any size, like its own toolbar icons, which are triangle icons too: datafiles/icons/*.dat)."""
    sat = round(icon_saturation(context), 3)
    v = _geom_ids.get((name, sat))
    if v is None:
        import bpy
        coords, cols = triangles(name, sat)
        # Blender 4.5 crashes freeing an icon made by ``new_triangles`` (released or at quit: "MEM_freeN on a
        # pointer created with MEM_new", also in -b); icons read by ``new_triangles_from_file`` free cleanly,
        # so the kit writes Blender's own .dat layout (datafiles/icons: "VCO", version 0, 255 x 255, offset 0,
        # coords, colours) into the extension's user folder and reads it back.
        path = _dat_path(name, sat)
        with open(path, "wb") as fh:
            fh.write(b"VCO\x00" + bytes((255, 255, 0, 0)) + coords + cols)
        v = _geom_ids[(name, sat)] = bpy.app.icons.new_triangles_from_file(path)
    return v


def _dat_path(name, sat):
    import os
    import bpy
    folder = bpy.utils.extension_path_user(__package__.rpartition(".")[0], path="icons", create=True)
    safe = "".join(c if c.isalnum() else "_" for c in name)
    return os.path.join(folder, f"{safe}_{int(sat * 1000)}.dat")


def tool_icon_name(idname, context=None):
    """A kit-only icon name for tool ``idname`` that Blender's toolbar resolves to the kit glyph through
    ``bl_ui.space_toolsystem_common._icon_cache`` (name -> icon value, looked up before any .dat file is read),
    or None for tools without a kit glyph."""
    name = f"tool:{idname}"
    if name not in GLYPHS:
        return None
    v = geom_icon(name, context)
    if not v:
        return None
    from bl_ui import space_toolsystem_common as stc
    key = f"allset.{name}@{round(icon_saturation(context), 3)}"
    if stc._icon_cache.get(key) != v:
        stc._icon_cache[key] = v
        _cache_keys.add(key)
    return key


# --- GPU textures (Outliner rows) ---------------------------------------------------------------------------------

_textures = {}


def texture(name, n, greyed=False):
    """GPU texture of ``name`` at ``n`` px (call from a draw handler). Display (sRGB) values: the Outliner's region
    draws the builtin 'IMAGE' shader's values as they are (unlike the shelf's image editor)."""
    key = (name, n, greyed)
    tex = _textures.get(key)
    if tex is None:
        import gpu
        px = pixels(name, n, greyed)[::-1].copy()
        buf = gpu.types.Buffer('FLOAT', n * n * 4, px.ravel().tolist())
        tex = _textures[key] = gpu.types.GPUTexture((n, n), format='RGBA32F', data=buf)
    return tex


def draw_texture(name, x, y, n, greyed=False):
    """Draw glyph ``name`` with its lower left corner at region pixel (x, y), unscaled."""
    import gpu
    from gpu_extras.batch import batch_for_shader
    x, y = round(x), round(y)
    sh = gpu.shader.from_builtin('IMAGE')
    coords = ((x, y), (x + n, y), (x + n, y + n), (x, y + n))
    batch = batch_for_shader(sh, 'TRI_FAN', {"pos": coords, "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1))})
    sh.uniform_sampler("image", texture(name, n, greyed))
    gpu.state.blend_set('ALPHA')
    batch.draw(sh)


def register():
    pass


def unregister():
    import bpy
    if bpy.app.timers.is_registered(_make_pending):
        bpy.app.timers.unregister(_make_pending)
    _pending.clear()
    try:
        from bl_ui import space_toolsystem_common as stc
        for key in _cache_keys:
            stc._icon_cache.pop(key, None)
    except ImportError:
        pass
    _cache_keys.clear()
    for v in _geom_ids.values():
        try:
            bpy.app.icons.release(v)
        except (RuntimeError, ValueError):
            pass
    _geom_ids.clear()
    _textures.clear()
    if _pcoll:
        import bpy.utils.previews
        bpy.utils.previews.remove(_pcoll.pop())
