"""Marketing images: captioned feature screens, key visuals and the icon, composited with Pillow from the
GUI shots of tools/marketing/shots.py and the copy in tools/marketing/content.json.

    python tools/marketing/compose.py [--only NAME,...]

Inputs: tmp/marketing/raw/<name>.png + meta.json (1920 x 1080 window shots, rects in top-down window pixels),
tools/marketing/style.json (tokens), tools/marketing/content.json (copy), the Inter font from the local assets folder (tools/marketing/
fetch_assets.py). Outputs: docs/distribution/marketing/screens/<n>_<name>.png, key_visual.png, key_visual_square.png,
icon_256.png. Pure Pillow (no numpy) so it runs with any Python that has Pillow.
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = ROOT / "tmp" / "marketing" / "raw"
OUT = ROOT / "docs" / "distribution" / "marketing"
FONTS = ROOT / "research" / "marketing_assets" / "font_inter"

STYLE = json.loads((HERE / "style.json").read_text(encoding="utf-8"))
P = STYLE["primitive"]
PALETTE = os.environ.get("ALLSET_MARKETING_PALETTE") or STYLE["palette"]
S = {**STYLE["semantic"], **{k: v for k, v in STYLE["palettes"][PALETTE].items() if not k.startswith("_")}}


def colour(token):
    """Hex of a semantic or primitive token (or a raw hex)."""
    token = S.get(token, token)
    return P.get(token, token)


def rgb(token, alpha=None):
    h = colour(token).lstrip("#")
    c = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return c if alpha is None else (*c, alpha)


_FONT_CACHE = {}


def font(key, size):
    name = P.get(key, key)
    k = (name, size)
    if k not in _FONT_CACHE:
        hits = list(FONTS.rglob(name))
        if not hits:
            sys.exit(f"font {name} not found under {FONTS} (run tools/marketing/fetch_assets.py)")
        _FONT_CACHE[k] = ImageFont.truetype(str(hits[0]), size)
    return _FONT_CACHE[k]


def text_w(draw, text, fnt):
    return draw.textlength(text, font=fnt)


def vertical_gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        img.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return img.resize((w, h))


def rounded(img, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.size[0] - 1, img.size[1] - 1), radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def shadow(canvas, box, radius, blur, alpha):
    x0, y0, x1, y1 = box
    pad = blur * 3
    sh = Image.new("RGBA", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + blur // 2, pad + x1 - x0, pad + y1 - y0 + blur // 2), radius,
                                         fill=(0, 0, 0, alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(sh, (x0 - pad, y0 - pad))


def arrow(draw, start, end, col, width, head):
    draw.line((start, end), fill=col, width=width)
    ang = math.atan2(end[1] - start[1], end[0] - start[0])
    for s in (-1, 1):
        a = ang + math.pi + s * math.radians(28)
        draw.line((end, (end[0] + head * math.cos(a), end[1] + head * math.sin(a))), fill=col, width=width)


def lockup(draw, x, y, name_px, one_line=False, anchor_right=False, colours=None, alpha=255):
    """The lockup: the name (``component.lockup.name``, Bold) + the line (``lockup.line``,
    SemiBold at ``for_ratio`` x the name size), two lines on one left edge, or one line on one baseline. ``(x, y)`` =
    top-left of the name's em box (top right with ``anchor_right``). Returns the box (x0, y0, x1, y1) of the drawn
    ink rows."""
    lk = STYLE["component"]["lockup"]
    name, line = lk["name"], lk["line"]
    fpx = round(name_px * lk["for_ratio"])
    nf, ff = font(lk["name_font"], name_px), font(lk["for_font"], fpx)
    ncol, fcol = colours or (lk["name_color"], lk["for_color"])
    nw, fw = text_w(draw, name, nf), text_w(draw, line, ff)
    if one_line:
        gap = name_px * lk["one_line_gap"]
        width = nw + gap + fw
        x0 = x - width if anchor_right else x
        base = y + nf.getmetrics()[0]
        draw.text((x0, base), name, font=nf, fill=rgb(ncol, alpha), anchor="ls")
        draw.text((x0 + nw + gap, base), line, font=ff, fill=rgb(fcol, alpha), anchor="ls")
        return (x0, y, x0 + width, base + nf.getmetrics()[1])
    width = max(nw, fw + name_px * 0.02)
    x0 = x - width if anchor_right else x
    base1 = y + nf.getmetrics()[0]
    base2 = base1 + round(fpx * (1.0 + lk["line_gap"]) + fpx * 0.12)
    draw.text((x0, base1), name, font=nf, fill=rgb(ncol, alpha), anchor="ls")
    draw.text((x0 + name_px * 0.02, base2), line, font=ff, fill=rgb(fcol, alpha), anchor="ls")
    return (x0, y, x0 + width, base2 + ff.getmetrics()[1])


def lockup_ink(name_px, one_line=False):
    """(width, height) of the lockup's ink at ``name_px`` (drawn once on a scratch image)."""
    im = Image.new("RGB", (int(name_px * 20) + 16, int(name_px * 3) + 16))
    lockup(ImageDraw.Draw(im), 8, 8, name_px, one_line=one_line, colours=("white", "white"))
    x0, y0, x1, y1 = im.getbbox()
    return x1 - x0, y1 - y0


def credit_line(content, names):
    """The attribution text (content.json ``credits``, CC-BY etc.) for the shots / clips ``names``; '' if none."""
    cr = content.get("credits") or {}
    seen = []
    for n in names:
        t = cr.get(n)
        if t and t not in seen:
            seen.append(t)
    return " · ".join(seen)


def fine_size(width):
    """Fine-print size (trademark note, credits) for a canvas ``width`` px wide: 17 px at 1920, at least 14."""
    return max(14, round(17 * width / 1920))


def fine_print(draw, content, names, x, y, width, anchor="l", top=False):
    """The small muted lines of a brand image: the credits of ``names`` (content.json) and the trademark note.
    ``top`` = first line's top at ``y`` (stacked down: credit, note), else the note's bottom at ``y`` (stacked up:
    note, credit above). ``anchor`` l / m / r = horizontal anchor at ``x``. Returns the far y (bottom / top)."""
    f = font("font-regular", fine_size(width))
    # one row per distinct credit (two CC BY credits on one row ran into the key visual's screens)
    credits = [t for t in credit_line(content, names).split(" · ") if t]
    lines = credits + [t for t in (content.get("trademark_note", ""),) if t]
    step = round(f.size * 1.45)
    if not top:
        lines = lines[::-1]
    for t in lines:
        draw.text((x, y), t, font=f, fill=rgb("text-muted"), anchor=anchor + ("a" if top else "d"))
        y += step if top else -step
    return y


def outlined_rect(draw, box, radius, colour, width, outline):
    """A stroke with a thin dark edge on both sides, so the accent reads on light and dark UI alike."""
    if outline:
        x0, y0, x1, y1 = box
        draw.rounded_rectangle((x0 - outline, y0 - outline, x1 + outline, y1 + outline), radius + outline,
                               outline=rgb("outline"), width=width + 2 * outline)
    draw.rounded_rectangle(box, radius, outline=rgb(colour), width=width)


# --------------------------------------------------------------------------------------------- feature screens
def screen(name, title, line, callouts, out_path, credit=""):
    st = STYLE["component"]["screen"]
    band = STYLE["component"]["band"]
    co = STYLE["component"]["callout"]
    W, H = st["canvas"]
    canvas = vertical_gradient((W, H), rgb("canvas-bg"), rgb("canvas-bg-2")).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    # title band: accent tick, title, one line; brand at the right
    mx = st["margin_x"]
    tfont, lfont = font(band["title_font"], band["title_size"]), font(band["line_font"], band["line_size"])
    ty = band["title_y"]
    draw.rounded_rectangle((mx, ty + 6, mx + band["tick_w"], ty + 6 + band["tick_h"] + band["line_gap"]
                            + band["line_size"]), 3, fill=rgb(band["tick_color"]))
    tx = mx + band["tick_w"] + band["tick_gap"]
    draw.text((tx, ty), title, font=tfont, fill=rgb(band["title_color"]))
    draw.text((tx, ty + band["title_size"] + band["line_gap"]), line, font=lfont, fill=rgb(band["line_color"]))
    bx = lockup(draw, W - mx, ty + 4, band["brand_size"], one_line=True, anchor_right=True,
                colours=(band["brand_color"], "accent"))[0]
    if tx + text_w(draw, title, tfont) > bx - band["brand_clear"]:
        print(f"WARNING {name}: title runs into the brand mark")
    if credit:   # attribution (content.json credits) right-aligned on the line row, under the brand
        cf = font(band["credit_font"], band["credit_size"])
        cy = ty + band["title_size"] + band["line_gap"] + band["line_size"] - band["credit_size"]
        rows = [credit]
        line_end = tx + text_w(draw, line, lfont) + band["brand_clear"]
        if line_end > W - mx - text_w(draw, credit, cf) and " | " in credit:
            # a long CC BY credit takes two rows (split after the author, " | "): the upper one sits
            # between the brand mark and the line row, right of the title
            a, b = credit.split(" | ", 1)
            rows = [a + " |", b]
        step = round(band["credit_size"] * 1.4)
        for i, row in enumerate(reversed(rows)):
            draw.text((W - mx, cy - i * step), row, font=cf, fill=rgb(band["credit_color"]), anchor="ra")
        widest = max(text_w(draw, r, cf) for r in rows)
        if line_end > W - mx - text_w(draw, rows[-1], cf):
            print(f"WARNING {name}: line runs into the credit")
        if len(rows) > 1 and tx + text_w(draw, title, tfont) + band["brand_clear"] > W - mx - widest:
            print(f"WARNING {name}: title runs into the credit")

    # the shot, scaled into the frame below the band
    raw = Image.open(RAW / f"{name}.png").convert("RGB")
    sx, sy = st["shot_w"] / raw.width, st["shot_h"] / raw.height
    shot = raw.resize((st["shot_w"], st["shot_h"]), Image.LANCZOS)
    ox, oy = mx, st["band_h"]
    shadow(canvas, (ox, oy, ox + st["shot_w"], oy + st["shot_h"]), st["shot_radius"], st["shot_shadow_blur"],
           st["shot_shadow_alpha"])
    canvas.alpha_composite(rounded(shot, st["shot_radius"]), (ox, oy))

    # callouts: accent box around a UI rect + a label pill joined by an arrow
    lab_font = font(co["label_font"], co["label_size"])
    for c in callouts:
        x, y, w, h = c["rect"]
        p = co["pad"]
        box = (ox + x * sx - p, oy + y * sy - p, ox + (x + w) * sx + p, oy + (y + h) * sy + p)
        outlined_rect(draw, box, co["radius"], co["stroke"], co["stroke_w"], co.get("outline_w", 0))
        if not c.get("label"):
            continue
        tw = text_w(draw, c["label"], lab_font)
        lw, lh = tw + 2 * co["label_pad_x"], co["label_size"] + 2 * co["label_pad_y"]
        side = c.get("side", "right")
        gap = c.get("gap", 70)
        at = c.get("at", 0.5)       # where along the box the arrow meets it (0 = left / top edge)
        cx, cy = box[0] + (box[2] - box[0]) * at, box[1] + (box[3] - box[1]) * at
        if side == "right":
            lx, ly = box[2] + gap, cy - lh / 2
            a0, a1 = (lx, cy), (box[2] + 4, cy)
        elif side == "left":
            lx, ly = box[0] - gap - lw, cy - lh / 2
            a0, a1 = (lx + lw, cy), (box[0] - 4, cy)
        elif side == "above":
            lx, ly = cx - lw / 2, box[1] - gap - lh
            a0, a1 = (cx, ly + lh), (cx, box[1] - 4)
        else:
            lx, ly = cx - lw / 2, box[3] + gap
            a0, a1 = (cx, ly), (cx, box[3] + 4)
        lx = min(max(lx, ox + 8), ox + st["shot_w"] - lw - 8)
        ly = min(max(ly, oy + 8), oy + st["shot_h"] - lh - 8)
        if co.get("outline_w"):
            arrow(draw, a0, a1, rgb("outline"), co["arrow_w"] + 2 * co["outline_w"], co["arrow_head"])
        arrow(draw, a0, a1, rgb(co["stroke"]), co["arrow_w"], co["arrow_head"])
        draw.rounded_rectangle((lx, ly, lx + lw, ly + lh), co["label_radius"], fill=rgb(co["label_bg"]))
        draw.text((lx + co["label_pad_x"], ly + co["label_pad_y"] - 2), c["label"], font=lab_font,
                  fill=rgb(co["label_fg"]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path)
    return out_path


# --------------------------------------------------------------------------------------------- key visuals
def perspective_coeffs(src, dst):
    """Coefficients for Image.transform(PERSPECTIVE) mapping dst quad -> src quad (solve 8x8 by Gauss)."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(dst, src):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); rhs.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y]); rhs.append(v)
    n = 8
    m = [r + [b] for r, b in zip(rows, rhs)]
    for i in range(n):
        piv = max(range(i, n), key=lambda r: abs(m[r][i]))
        m[i], m[piv] = m[piv], m[i]
        for r in range(n):
            if r != i:
                f = m[r][i] / m[i][i]
                m[r] = [a - f * b for a, b in zip(m[r], m[i])]
    return [m[i][n] / m[i][i] for i in range(n)]


TILT_DEG = 24.0      # every turned screen = the same plane rotation ...
TILT_DEPTH = 1.6     # ... seen by the same pinhole camera: distance to the near edge = TILT_DEPTH x the plane width


def tilt_quad(w, h, width, tilt_deg=TILT_DEG, depth=TILT_DEPTH):
    """Projected corners of a ``width`` x (``width`` h / w) screen turned ``tilt_deg`` about its near (left) vertical
    edge, away from a pinhole camera at ``depth`` x width whose focal length keeps the near edge at its own height.
    The old quad kept the full width (only tapered the far edge), so turned screens came out wider than the
    capture's aspect; a real rotation projects the width to width cos(t) d / (d + width sin(t)) < width cos(t)."""
    W, H = float(width), width * h / w
    t = math.radians(tilt_deg)
    d = depth * W
    k = d / (d + W * math.sin(t))              # far edge scale
    uf, hf = W * math.cos(t) * k, H * k
    return [(0.0, 0.0), (uf, (H - hf) / 2), (uf, (H + hf) / 2), (0.0, H)], (uf, H)


def tilted(img, width, tilt_deg=TILT_DEG, depth=TILT_DEPTH, ss=2):
    """``img`` as a real screen turned about its near vertical edge (tilt_quad), supersampled ``ss`` x then reduced
    with Lanczos so the UI text stays readable. ``width`` = the unturned screen width in output px."""
    w, h = img.size
    quad, (uw, uh) = tilt_quad(w, h, width, tilt_deg, depth)
    dst = [(x * ss, y * ss) for x, y in quad]
    size = (math.ceil(uw * ss), math.ceil(uh * ss))
    coeffs = perspective_coeffs([(0, 0), (w, 0), (w, h), (0, h)], dst)
    src = rounded(img.convert("RGBA"), 18)
    big = src.transform(size, Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    return big.resize((math.ceil(uw), math.ceil(uh)), Image.LANCZOS)


def key_visual_layers(content, shots, size=(1920, 1080), square=False):
    """The key visual as layers for the trailer's moving title card (clip_compose.title_card): background (gradient +
    glow), screens [(RGBA, x, y, shadowed RGBA box)] back to front, text (RGBA, full canvas)."""
    kv = STYLE["component"]["square" if square else "key_visual"]
    W, H = size
    bg = vertical_gradient((W, H), rgb("grey-850"), rgb("grey-950")).convert("RGBA")
    # soft accent glow behind the screens
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gx, gy, gr = (W * 0.68, H * 0.5, H * 0.55) if not square else (W * 0.55, H * 0.68, W * 0.45)
    gd.ellipse((gx - gr, gy - gr, gx + gr, gy + gr), fill=rgb("accent-deep", 70))
    bg.alpha_composite(glow.filter(ImageFilter.GaussianBlur(160)))

    imgs = [Image.open(RAW / f"{n}.png").convert("RGB") for n in shots]
    screens = []

    def add(t, x, y):
        pad = 120
        layer = Image.new("RGBA", (t.width + 2 * pad, t.height + 2 * pad), (0, 0, 0, 0))
        shadow(layer, (pad, pad, pad + t.width, pad + t.height), 18, 30, 170)
        layer.alpha_composite(t, (pad, pad))
        screens.append((layer, x - pad, y - pad))

    if not square:
        # back screen, then front screen, staggered to the right
        for img, wdt, (x, y) in zip((imgs[1], imgs[0]), (1000, 1160), kv["screens_xy"]):
            add(tilted(img, wdt), x, y)
    else:
        add(tilted(imgs[0], 1400), *kv["screens_xy"][0])   # projects to ~1020 px wide
    tx, ty = kv["text_xy"]
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text)
    tag_f = font("font-regular", kv["tagline_size"])
    box = lockup(draw, tx, ty, kv["name_size"])
    yy = box[3] + 44
    for ln in content["key_visual_lines"]:
        draw.text((tx + 4, yy), ln, font=tag_f, fill=rgb("text"))
        yy += round(kv["tagline_size"] * 1.35)
    foot_f = font("font-medium", 24 if not square else 22)
    draw.text((tx + 4, yy + 28), content["key_visual_footer"], font=foot_f, fill=rgb("text-muted"))
    if square:   # the screen fills the bottom: credit + trademark note under the footer
        fine_print(draw, content, shots, tx + 4, yy + 28 + round(foot_f.size * 2.2), W, top=True)
    else:        # bottom-left, under the text column (the screens are right of it)
        fine_print(draw, content, shots, tx + 4, H - 40, W)
    return bg, screens, text


def _paste_subpixel(out, layer, x, y):
    """Composite ``layer`` at a fractional (x, y): integer part as an offset, the remainder as a bicubic shift.
    Rounding to whole pixels made slow drifts (< 1 px per frame) step visibly in the trailer title card."""
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    if fx > 1e-6 or fy > 1e-6:   # zero shift = exact paste (stills); any drift goes through the same resample
        pad = Image.new("RGBA", (layer.width + 2, layer.height + 2), (0, 0, 0, 0))
        pad.paste(layer, (1, 1))
        layer = pad.transform(pad.size, Image.AFFINE, (1, 0, -fx, 0, 1, -fy), resample=Image.BICUBIC)
        ix, iy = ix - 1, iy - 1
    out.alpha_composite(layer, (ix, iy)) if ix >= 0 and iy >= 0 else _composite_clipped(out, layer, ix, iy)


def _composite_clipped(out, layer, x, y):
    sx, sy = max(0, -x), max(0, -y)
    out.alpha_composite(layer, (max(0, x), max(0, y)), (sx, sy))


def flatten(bg, screens, text, offsets=None, text_offset=(0, 0), text_alpha=1.0):
    """Composite key visual layers; ``offsets`` = per-screen (dx, dy)."""
    out = bg.copy()
    for i, (layer, x, y) in enumerate(screens):
        dx, dy = offsets[i] if offsets else (0, 0)
        _paste_subpixel(out, layer, x + dx, y + dy)
    if text_alpha >= 1.0 and text_offset == (0, 0):
        out.alpha_composite(text)
    elif text_alpha > 0:
        t = text if text_alpha >= 1.0 else Image.eval(text.getchannel("A"), lambda v: v * text_alpha)
        if t is not text:
            t = Image.merge("RGBA", (*text.split()[:3], t))
        _paste_subpixel(out, t, *text_offset)
    return out


def key_visual(content, shots, out_path, size=(1920, 1080), square=False):
    out = flatten(*key_visual_layers(content, shots, size, square))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.convert("RGB").save(out_path)
    return out_path


def icon(out_path, size=256):
    """The kit icon: an orange ring linked through a teal square link (Blender + Maya as one chain; kit-made, no
    Blender or Maya mark). Master art: docs/distribution/marketing/icon/icon.svg (+ a hand-hinted icon_32.svg);
    the PNGs here are scaled from the 1024 px render of that SVG."""
    master = ROOT / "docs/distribution/marketing/icon" / ("icon_32.png" if size <= 32 else "icon_1024.png")
    img = Image.open(master).convert("RGBA")
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


# --------------------------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", default="", help="comma-separated names (screens, key_visual, square, icon)")
    args = ap.parse_args(argv)
    only = {s for s in args.only.split(",") if s}
    content = json.loads((HERE / "content.json").read_text(encoding="utf-8"))
    meta = json.loads((RAW / "meta.json").read_text(encoding="utf-8")) if (RAW / "meta.json").exists() else {}
    made = []
    for i, sc in enumerate(content["screens"], 1):
        if only and sc["name"] not in only and "screens" not in only:
            continue
        if not (RAW / f"{sc['name']}.png").exists():
            print("missing shot:", sc["name"])
            continue
        callouts = []
        for c in sc.get("callouts", []):
            rect = meta.get(sc["name"], {}).get("rects", {}).get(c["rect"]) if isinstance(c["rect"], str) else c["rect"]
            if rect:
                callouts.append({**c, "rect": rect})
            else:
                print(f"{sc['name']}: no rect {c['rect']}")
        made.append(screen(sc["name"], sc["title"], sc["line"], callouts,
                           OUT / "screens" / f"{i:02d}_{sc['name']}.png", credit_line(content, [sc["name"]])))
    if not only or "key_visual" in only:
        made.append(key_visual(content, content["key_visual_shots"], OUT / "key_visual.png"))
    if not only or "square" in only:
        made.append(key_visual(content, content["key_visual_shots"][:1], OUT / "key_visual_square.png",
                               size=tuple(STYLE["component"]["square"]["canvas"]), square=True))
    if not only or "icon" in only:
        made.append(icon(OUT / "icon_256.png"))
    for m in made:
        print("wrote", m.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
