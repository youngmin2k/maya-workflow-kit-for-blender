# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya 2022 Hypershade window layout as Blender area splits (no bpy: tested headless).

Maya's standard Hypershade is a
menu bar over five docked panels: Browser top-left, Material Viewer top-right, Create
bottom-left, the Graph work area (node editor) between Create and the right column, Property Editor bottom-right.
``MAYA_RECTS`` are those panels (x, y, w, h; y down, window px); ``plan`` turns them into
``screen.area_split`` calls on one area (the whole new window), ``simulate`` replays a plan on a rectangle with
Blender's split rules:

- HORIZONTAL, factor > 0.5: the new area is the top part, ``1 - factor`` of the height;
- VERTICAL, factor > 0.5: the new area is the right part, ``1 - factor`` of the width;
- VERTICAL, factor < 0.5: the new area is the left part, ``factor`` of the width.
"""

MAYA_SIZE = (1440, 900)
# Hypershade panels in a 1440 x 900 window
MAYA_RECTS = {
    "MENU": (0, 0, 1440, 24),
    "BROWSER": (0, 24, 987, 237),
    "VIEWER": (987, 24, 453, 383),
    "CREATE": (0, 261, 414, 639),
    "GRAPH": (414, 261, 573, 639),
    "PROPERTY": (987, 407, 453, 493),
}
ROLES = ("MENU", "BROWSER", "CREATE", "GRAPH", "VIEWER", "PROPERTY")


def shares():
    """Maya's proportions: right column / window width, Material Viewer / column height, Browser / left block
    height, Create / left block width (all below the menu bar)."""
    w, h = MAYA_SIZE
    body = h - MAYA_RECTS["MENU"][3]
    left = MAYA_RECTS["BROWSER"][2]
    return {"right": MAYA_RECTS["VIEWER"][2] / w,
            "viewer": MAYA_RECTS["VIEWER"][3] / body,
            "browser": MAYA_RECTS["BROWSER"][3] / body,
            "create": MAYA_RECTS["CREATE"][2] / left}


def plan(height, menu_px):
    """Split steps for a window ``height`` px tall whose menu strip is ``menu_px`` tall:
    [(area to split, direction, factor, role of the new area)]. The area being split keeps its role; the first area
    is "GRAPH" (it ends as the work area)."""
    s = shares()
    menu = min(0.45, menu_px / max(height, 1))
    return [
        ("GRAPH", 'HORIZONTAL', 1.0 - menu, "MENU"),            # menu bar strip across the top
        ("GRAPH", 'VERTICAL', 1.0 - s["right"], "PROPERTY"),     # right column ...
        ("PROPERTY", 'HORIZONTAL', 1.0 - s["viewer"], "VIEWER"),  # ... Material Viewer over the Property Editor
        ("GRAPH", 'HORIZONTAL', 1.0 - s["browser"], "BROWSER"),  # Browser over Create + Graph
        ("GRAPH", 'VERTICAL', s["create"], "CREATE"),            # Create left of the Graph
    ]


def split_rect(rect, direction, factor):
    """(new area rect, old area rect) after ``area_split`` (Blender's rules in the module docstring)."""
    x, y, w, h = rect
    if direction == 'HORIZONTAL':
        if factor <= 0.5:
            raise ValueError("the layout uses top splits only")
        top = round(h * (1.0 - factor))
        return (x, y, w, top), (x, y + top, w, h - top)
    if factor > 0.5:
        right = round(w * (1.0 - factor))
        return (x + w - right, y, right, h), (x, y, w - right, h)
    left = round(w * factor)
    return (x, y, left, h), (x + left, y, w - left, h)


def simulate(steps, width, height):
    """Replay ``steps`` on a ``width`` x ``height`` window: {role: (x, y, w, h)} (y down)."""
    rects = {"GRAPH": (0, 0, width, height)}
    for src, direction, factor, new in steps:
        rects[new], rects[src] = split_rect(rects[src], direction, factor)
    return rects


def normalized(rects, width, height):
    """Rects as fractions of the window (for comparing windows of different sizes)."""
    return {k: (x / width, y / height, w / width, h / height) for k, (x, y, w, h) in rects.items()}


def compare(rects, width, height, menu_px=None):
    """Largest difference (fraction of the window) between ``rects`` and Maya's, panel by panel below the menu
    strip (the strip's height follows Blender's header, so the body is compared on its own)."""
    def body(r, top, total_h):
        out = {}
        for k, (x, y, w, h) in r.items():
            if k == "MENU":
                continue
            out[k] = (x, (y - top) / (total_h - top), w, h / (total_h - top))
        return out
    mw, mh = MAYA_SIZE
    mt = MAYA_RECTS["MENU"][3]
    top = rects["MENU"][3] if menu_px is None else menu_px
    maya = {k: (x / mw, y, w / mw, h) for k, (x, y, w, h) in body(MAYA_RECTS, mt, mh).items()}
    kit = {k: (x / width, y, w / width, h) for k, (x, y, w, h) in body(rects, top, height).items()}
    return {k: max(abs(a - b) for a, b in zip(maya[k], kit[k])) for k in maya if k in kit}
