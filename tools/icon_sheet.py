"""Contact sheets of the kit-drawn icons (#23): docs/icons/*.png.

    python tools/icon_sheet.py [--out DIR]

Runs itself in a background Blender (``blender -b --factory-startup``; numpy, blf and imbuf live there): every
factory shelf button at 2x and 1x with its label, one sheet per shelf, and the Status Line / panel toolbar glyphs at
16 / 24 / 32 px. Kit icons only.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build  # noqa: E402

BLENDER = os.environ.get("BLENDER", build.DEFAULT_BLENDER)
FONT = r"C:\Windows\Fonts\segoeui.ttf"
BG = (0x44 / 255, 0x44 / 255, 0x44 / 255, 1.0)       # Maya shelf / Status Line grey
CELL_W, CELL_H, COLS = 150, 100, 8


def _out_dir():
    if "--out" in sys.argv:
        return os.path.abspath(sys.argv[sys.argv.index("--out") + 1])
    return os.path.join(ROOT, "docs", "icons")


def _launch():
    out = _out_dir()
    os.makedirs(out, exist_ok=True)
    cfg = os.path.join(ROOT, "tmp", "icon_sheet_cfg")
    os.makedirs(cfg, exist_ok=True)
    env = dict(os.environ, BLENDER_USER_CONFIG=cfg, BLENDER_USER_SCRIPTS=cfg, BLENDER_USER_EXTENSIONS=cfg)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", os.path.abspath(__file__), "--", "--out", out],
                       stdin=subprocess.DEVNULL, env=env, capture_output=True, text=True, errors="replace")
    tail = [line for line in r.stdout.splitlines() if line.startswith(("SHEET", "Traceback", "Error"))]
    print("\n".join(tail) or r.stdout[-2000:])
    return 0 if r.returncode == 0 and any(line.startswith("SHEET") for line in tail) else 1


# --- inside Blender -----------------------------------------------------------------------------------------

def _modules():
    sys.path.insert(0, os.path.join(ROOT, "src"))      # a tool, not the package: the source tree as is
    from allset.ui import graph_icons, panel_toolbar, shelf_data, shelf_icons, status_icons
    for name, fn in panel_toolbar.GLYPHS.items():
        status_icons.EXTRA.setdefault("pt_" + name, fn)
    graph_icons.register()
    return shelf_data, shelf_icons, status_icons, panel_toolbar


def _paste(canvas, px, x, y):
    """Alpha-blend icon ``px`` (top-down RGBA) onto ``canvas`` (top-down) at x, y (top-left)."""
    h, w = px.shape[:2]
    dst = canvas[y:y + h, x:x + w]
    a = px[..., 3:4]
    dst[..., :3] = px[..., :3] * a + dst[..., :3] * (1 - a)


def _save(canvas, labels, path):
    """Write ``canvas`` (top-down RGBA float) to ``path`` with ``labels`` [(x, y_top, text)] drawn by blf."""
    import blf
    import bpy
    import imbuf
    h, w = canvas.shape[:2]
    img = bpy.data.images.new("sheet", w, h, alpha=True)
    img.pixels.foreach_set(canvas[::-1].ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    ib = imbuf.load(path)
    fid = blf.load(FONT)
    with blf.bind_imbuf(fid, ib, display_name="sRGB"):
        blf.color(fid, 0.86, 0.86, 0.86, 1.0)
        for x, y, text, size in labels:
            blf.size(fid, size)
            while size < 16 and len(text) > 3 and blf.dimensions(fid, text)[0] > CELL_W - 6:
                text = text[:-2] + "…"
            blf.position(fid, x, h - y - size, 0)
            blf.draw_buffer(fid, text)
    imbuf.write(ib, filepath=path)
    print("SHEET", path)


def _grid(items, title):
    """items: [(label, [px, ...])] -> canvas, labels."""
    import numpy as np
    rows = (len(items) + COLS - 1) // COLS
    top = 34
    h, w = top + rows * CELL_H + 8, COLS * CELL_W + 8
    canvas = np.empty((h, w, 4), np.float32)
    canvas[:] = BG
    labels = [(10, 8, title, 16)]
    for k, (label, images) in enumerate(items):
        r, c = divmod(k, COLS)
        x0, y0 = 8 + c * CELL_W, top + r * CELL_H
        x = x0
        for px in images:
            _paste(canvas, px, x, y0 + 68 - px.shape[0])
            x += px.shape[1] + 8
        labels.append((x0, y0 + 74, f"{k + 1}. {label}", 11))
    return canvas, labels


def _inside():
    out = _out_dir()
    shelf_data, shelf_icons, status_icons, panel_toolbar = _modules()
    for shelf, title, buttons in shelf_data.SHELVES:
        items = [(label, [shelf_icons.draw(label, shelf, size=64, index=i),
                          shelf_icons.draw(label, shelf, size=32, index=i)])
                 for i, (label, _command) in enumerate(buttons)]
        canvas, labels = _grid(items, f"Shelf: {title} — kit-drawn icons (2x, 1x)")
        _save(canvas, labels, os.path.join(out, f"shelf_{shelf}.png"))
    groups = (("status_line", "Status Line / menu bar", list(status_icons.GLYPHS)),
              ("panel_toolbar", "Viewport panel toolbar", ["pt_" + n for n in panel_toolbar.GLYPHS]))
    for name, title, glyphs in groups:
        items = [(g.removeprefix("pt_"), [status_icons.image(g, s) for s in (48, 32, 24, 16)]) for g in glyphs]
        canvas, labels = _grid(items, f"{title} — kit-drawn glyphs (48, 32, 24, 16 px)")
        _save(canvas, labels, os.path.join(out, f"{name}.png"))
    # #277: Graph Editor / Dope Sheet toolbar pictures, labelled with the button's Maya tooltip
    from allset.ui import editor_chrome, graph_icons
    for editor, fname in (("Graph Editor", "graph_editor_toolbar"), ("Dope Sheet", "dope_sheet_toolbar")):
        specs = [it for it in editor_chrome.ICONS[editor] if isinstance(it, tuple)]
        items = [(it[3], [status_icons.image(graph_icons.name(it[0]), s) for s in (48, 32, 20, 16)])
                 for it in specs if it[0] in graph_icons.GLYPHS]
        canvas, labels = _grid(items, f"{editor} toolbar — kit-drawn pictures (48, 32, 20, 16 px)")
        _save(canvas, labels, os.path.join(out, f"{fname}.png"))
    # #54: menu-only drawings, one sheet per drawing module (menus drawn at 16 / 20 / 24 px)
    from allset.ui import menu_drawings
    by_module = {}
    for name, fn in menu_drawings.DRAWINGS.items():
        by_module.setdefault(fn.__module__.rsplit(".", 1)[1], []).append(name)
    for module, names in sorted(by_module.items()):
        tops = sorted({n.split("/", 1)[0] for n in names}, key=lambda t: min(names.index(n) for n in names
                                                                              if n.startswith(t + "/")))
        items = [(n.split("/", 1)[1], [menu_drawings.draw(n, s) for s in (32, 24, 16)]) for n in names]
        canvas, labels = _grid(items, f"Menu icons: {', '.join(tops)} — kit-drawn (32, 24, 16 px)")
        _save(canvas, labels, os.path.join(out, f"{module if '_' in module else module + '_deform'}.png"))


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
    except ImportError:
        sys.exit(_launch())
    _inside()
