"""Check: the turned screens of the key visual / kit cards keep the capture's aspect.

    python tools/marketing/perspective_check.py [OUT_DIR]   (default tmp/marketing)

For each raw shot used turned (key visual, square, kit cards) the screen is turned with compose.tilted at the size its
layout uses; the alpha mask is read (near edge height, far edge height, projected width) and compared with the
expected projection of the capture's own W x H rectangle turned TILT_DEG about its near edge (compose.tilt_quad).
The projected width must stay below the unturned width (= near height x capture aspect). Writes perspective_check.txt
(numbers, exit 1 on a FAIL) and perspective_check.png (the capture unturned at the same height next to it, to look at).
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compose import RAW, ROOT, TILT_DEG, TILT_DEPTH, font, tilt_quad, tilted  # noqa: E402

CASES = [("key visual front", "hero", 1160), ("key visual back", "rigging", 1000), ("square", "hero", 1400),
         ("readme hero", "hero", 1080), ("reddit square", "hotbox", 1400)]


def column_extent(alpha, x):
    ys = [y for y in range(alpha.height) if alpha.getpixel((x, y)) > 128]
    return (min(ys), max(ys)) if ys else (0, -1)


def main(argv=None):
    out = Path((argv or sys.argv[1:] or [str(ROOT / "tmp" / "marketing")])[0])
    out.mkdir(parents=True, exist_ok=True)
    lines = [f"tilt {TILT_DEG} deg, camera distance {TILT_DEPTH} x width (same for every screen)", ""]
    ok = True
    tiles = []
    for label, shot, width in CASES:
        img = Image.open(RAW / f"{shot}.png").convert("RGB")
        w, h = img.size
        t = tilted(img, width)
        a = t.getchannel("A")
        near = column_extent(a, 20)              # inside the 18 px rounded corners
        far = column_extent(a, t.width - 21)
        xs = [x for x in range(t.width) if a.getpixel((x, t.height // 2)) > 128]
        hn, hf, u = near[1] - near[0] + 1, far[1] - far[0] + 1, max(xs) - min(xs) + 1
        quad, (uw, uh) = tilt_quad(w, h, width)
        # expected heights at the sampled columns (linear in the projected x)
        k = (quad[2][1] - quad[1][1]) / uh
        e_near = uh * (1 - (1 - k) * 20 / uw)
        e_far = uh * (1 - (1 - k) * (t.width - 21) / uw)
        unturned = hn * w / h * (uh / e_near)    # the capture's width at the near edge's scale
        ratio = u / unturned
        exp_ratio = uw / width
        good = abs(hn - e_near) <= 2 and abs(hf - e_far) <= 2 and abs(u - uw) <= 2 and u < unturned
        ok &= good
        lines.append(f"{'PASS' if good else 'FAIL'} {label:18s} capture {w}x{h} ({w / h:.3f}), plane width {width}: "
                     f"near edge {hn} px (expected {e_near:.1f}), far edge {hf} px (expected {e_far:.1f}), "
                     f"projected width {u} px (expected {uw:.1f}) = {ratio:.3f} x the unturned width "
                     f"(expected cos t * d/(d + W sin t) = {exp_ratio:.3f}; must be < 1)")
        flat = img.resize((round(uh * w / h), round(uh)), Image.LANCZOS)
        tiles.append((label, flat, t))
    (out / "perspective_check.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    scale = 0.5
    rows = [(lb, f.resize((round(f.width * scale), round(f.height * scale)), Image.LANCZOS),
             t.resize((round(t.width * scale), round(t.height * scale)), Image.LANCZOS)) for lb, f, t in tiles]
    W = max(f.width + t.width for _lb, f, t in rows) + 60
    H = sum(max(f.height, t.height) + 50 for _lb, f, t in rows) + 20
    sheet = Image.new("RGB", (W, H), (37, 37, 37))
    d = ImageDraw.Draw(sheet)
    y = 10
    for lb, f, t in rows:
        d.text((20, y), f"{lb}: capture unturned (left) | turned {TILT_DEG:.0f} deg (right), same height",
               font=font("font-medium", 20), fill=(220, 220, 220))
        y += 32
        sheet.paste(f, (20, y))
        sheet.paste(t, (40 + f.width, y), t)
        y += max(f.height, t.height) + 18
    sheet.save(out / "perspective_check.png")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
