"""Background check for promotional captures (#41; was a gradient check): every Maya-mode 3D
viewport in a screenshot / key visual / clip frame must show the flat background #5c5c5c.
The kit ships no theme (#40): the captures use Blender's
factory theme and the flat grey is view / scene data (tools/marketing/scene.py ``maya_look``), so Blender's factory
theme background (#3d3d3d) or a theme gradient (the old #889db3 top) fail here.

    python tools/marketing/bg_check.py <png> <x,y,w,h> [<x,y,w,h> ...]     (rects: 3D View WINDOW regions, top-down
                                                                         window pixels, as shots.py / clips.py record)

Pure Python (no bpy, no numpy): the pixels come from Pillow outside Blender, from OpenImageIO inside Blender
(Blender's Python has no Pillow; ``load_rgb``). For each rect, thin horizontal strips are sampled near the top and
further down the view and split into colour clusters; a background candidate is a cluster covering >= MIN_SHARE
of its strip (grid lines, HUD text, menus and objects form other clusters and don't decide the colour). The top
background must be the flat grey; the deepest strip that still shows it is reported (sets whose ground covers
the lower part of the view, like the DOGWALK snow, pass on the part above the horizon).
"""

import math
import sys

MAYA_FLAT = (0x5c, 0x5c, 0x5c)         # Maya-style flat viewport background
BLENDER_FACTORY = (0x3d, 0x3d, 0x3d)   # Blender 4.5 factory theme 3D View background (what a missed view shows)

# Thresholds. A capture passes when the top background (searched in the top TOP_BAND) is within DE_FLAT_MAX of
# #5c5c5c. Solid views with the view colour show #5c5c5c / #5d5d5d, Material Preview with the
# marketing world #5a5a5a under AgX (dE00 0.8). Blender's factory #3d3d3d is dE00 10.6 away, a light grey
# #a1a1a1 26, the old gradient top #889db3 27.
DE_FLAT_MAX = 3.0
TOP_BAND = 0.15
STRIP_STEP = 10              # px between sampled strips (each strip = 2 rows)
X_STEP = 3                   # px between samples along a strip
TOL = 5                      # max channel difference of a pixel to a cluster's colour (Blender dithers by +-1)
MIN_SHARE = 0.15             # a background candidate covers at least this share of a strip (objects / UI the rest)
MIN_SIZE = 80                # rects smaller than this (px) are not checked


# ---------------------------------------------------------------------------------------------------- colour maths
def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lab(rgb):
    """sRGB 0..255 -> CIE Lab (D65)."""
    r, g, b = (_lin(float(v)) for v in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def de00(rgb1, rgb2):
    """CIEDE2000 colour difference of two sRGB colours (0..255)."""
    L1, a1, b1 = lab(rgb1)
    L2, a2, b2 = lab(rgb2)
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7)))
    a1p, a2p = a1 * (1 + G), a2 * (1 + G)
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
    Lpm, Cpm = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0:
        hpm = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hpm = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hpm = (h1p + h2p + 360) / 2
    else:
        hpm = (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hpm - 30)) + 0.24 * math.cos(math.radians(2 * hpm))
         + 0.32 * math.cos(math.radians(3 * hpm + 6)) - 0.20 * math.cos(math.radians(4 * hpm - 63)))
    dtheta = 30 * math.exp(-(((hpm - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cpm ** 7 / (Cpm ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lpm - 50) ** 2 / math.sqrt(20 + (Lpm - 50) ** 2)
    Sc = 1 + 0.045 * Cpm
    Sh = 1 + 0.015 * Cpm * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def hexs(rgb):
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in rgb)


# ---------------------------------------------------------------------------------------------------- pixels
class Pixels:
    """Top-down RGB pixel rows: ``row(y)`` -> list of (r, g, b) 0..255 (cached), ``size`` = (w, h)."""

    def __init__(self, size, row):
        self.size, self._row, self._cache = size, row, {}

    def row(self, y):
        r = self._cache.get(y)
        if r is None:
            r = self._cache[y] = self._row(y)
        return r


def load_rgb(path):
    """A PNG as Pixels: Pillow when available, else OpenImageIO (inside Blender: its Python has no Pillow)."""
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image is not None:
        img = Image.open(path).convert("RGB")
        w, h = img.size
        raw = img.tobytes()

        def row(y):
            b = raw[y * w * 3:(y + 1) * w * 3]
            return list(zip(b[0::3], b[1::3], b[2::3]))
        return Pixels((w, h), row)
    import OpenImageIO as oiio
    inp = oiio.ImageInput.open(str(path))
    spec = inp.spec()
    data = inp.read_image(0, 0, 0, min(spec.nchannels, 3), "uint8")
    inp.close()
    return Pixels((spec.width, spec.height), lambda y: [tuple(p) for p in data[y].tolist()])


def _near(p, c):
    return abs(p[0] - c[0]) <= TOL and abs(p[1] - c[1]) <= TOL and abs(p[2] - c[2]) <= TOL


def _median_colour(pts):
    return tuple(sorted(q[i] for q in pts)[len(pts) // 2] for i in range(3))


def clusters(pixels, most=4):
    """Colour clusters of a pixel list, largest first: [(share, median colour)]. A cluster = the pixels within TOL of
    the most common coarse colour of what is left (a background row is one colour across the view, give or take
    the dither; thin grid lines, text and objects make their own small clusters)."""
    left, out, n = list(pixels), [], len(pixels)
    while left and len(out) < most:
        counts = {}
        for p in left:
            k = (p[0] >> 3, p[1] >> 3, p[2] >> 3)
            counts[k] = counts.get(k, 0) + 1
        k = max(counts, key=counts.get)
        c = _median_colour([p for p in left if (p[0] >> 3, p[1] >> 3, p[2] >> 3) == k])
        inside = [p for p in left if _near(p, c)]
        if not inside:
            break
        out.append((len(inside) / n, _median_colour(inside)))
        left = [p for p in left if not _near(p, c)]
    return out


def _strip(px, x, w, y):
    pts = []
    for yy in (y, y + 1):
        pts += px.row(yy)[x + 4:x + w - 4:X_STEP]
    return [c for share, c in clusters(pts) if share >= MIN_SHARE]


def _strips(px, x, y, w, h, from_top, band=None):
    """Background candidates of the strips of one band (``band`` = fraction of the height, default TOP_BAND),
    nearest the edge first: (offset from that edge, [colour])."""
    limit = int(h * (band if band is not None else TOP_BAND))
    off = 3
    while off + 2 <= limit:
        yield off, _strip(px, x, w, y + off if from_top else y + h - off - 2)
        off += STRIP_STEP


def check_rect(px, rect, scale=1.0):
    """Flat-grey check of one viewport rect [x, y, w, h] (top-down window px; ``scale`` = image px per window px).
    Returns a dict: ok (True / False / None = not checked), reason, top (the background found near the top),
    bottom (the deepest background strip still the flat grey), de (ΔE00 of the top to #5c5c5c), depth (bottom's t)."""
    x, y, w, h = (int(round(v * scale)) for v in rect)
    W, H = px.size
    x, y = max(0, x), max(0, y)
    w, h = min(w, W - x), min(h, H - y)
    res = {"rect": list(rect), "ok": None, "reason": "", "top": None, "bottom": None, "de": None, "depth": None}
    if w < MIN_SIZE or h < MIN_SIZE:
        res["reason"] = f"rect {w}x{h} too small, not checked"
        return res
    first, top = None, None
    for _off, cands in _strips(px, x, y, w, h, True):
        if cands and first is None:
            first = cands[0]
        hit = [c for c in cands if de00(c, MAYA_FLAT) <= DE_FLAT_MAX]
        if hit:
            top = hit[0]
            break
    if top is None:
        res["ok"] = False
        if first is None:
            res["reason"] = "no clear background near the top (covered by objects / UI)"
            return res
        de = de00(first, MAYA_FLAT)
        res.update(top=hexs(first), de=round(de, 1))
        hint = " (Blender's factory theme background)" if de00(first, BLENDER_FACTORY) <= DE_FLAT_MAX else ""
        res["reason"] = f"top {hexs(first)} is not Maya's flat {hexs(MAYA_FLAT)}{hint} (dE00 {de:.1f} > {DE_FLAT_MAX})"
        return res
    deepest = None
    for off, cands in _strips(px, x, y, w, h, False, 1.0):     # deepest first
        on = [c for c in cands if de00(c, MAYA_FLAT) <= DE_FLAT_MAX]
        if on:
            deepest = ((h - off - 2) / h, on[0])
            break
    de = de00(top, MAYA_FLAT)
    res.update(ok=True, top=hexs(top), de=round(de, 1))
    if deepest:
        res.update(bottom=hexs(deepest[1]), depth=round(deepest[0], 2))
    res["reason"] = (f"flat {hexs(top)} (dE00 {de:.1f} from Maya)"
                     + (f", still {hexs(deepest[1])} at {deepest[0]:.0%} of the view" if deepest else ""))
    return res


def check_image(path, rects, window=None):
    """Check every rect of a capture. ``window`` = (w, h) the rects were read in (default: the image size).
    Returns (ok, [per-rect results]); rects not checked (too small) don't count, at least one must be checked."""
    px = load_rgb(path)
    scale = px.size[0] / window[0] if window else 1.0
    results = [check_rect(px, r, scale) for r in rects]
    checked = [r for r in results if r["ok"] is not None]
    return bool(checked) and all(r["ok"] for r in checked), results


def summary(name, ok, results):
    parts = "; ".join(r["reason"] for r in results)
    return f"{name}: viewport background {'Maya flat grey' if ok else 'NOT Maya flat grey'} ({parts})"


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    rects = [[float(v) for v in a.split(",")] for a in argv[1:]]
    ok, results = check_image(argv[0], rects)
    for r in results:
        print("PASS" if r["ok"] else ("SKIP" if r["ok"] is None else "FAIL"), r["rect"], r["reason"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
