# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya in-view messages: a short fading message box in the 3D View.

The kit's box: a rounded grey box
(#484848 at opacity 0.75), light text at opacity 0.9 with ``<hl>`` words in yellow #eded08, 25 px lines,
10 px padding. The default position is the view's top left (10, 11) px in; ``topCenter`` messages sit
centred at the same height. Fade in about 0.3 s, show 2.0 s, fade
out about 1.5 s. One message at a time: a new one replaces the old one.

``show(context, text, pos)``: ``text`` may use ``<hl>...</hl>`` and ``\\n``. The message goes to the 3D View
the calling operator ran in, else to the window's main 3D View. Turned off with the add-on preference
``in_view_messages``.
"""

import re
import time

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

# --- Maya sizes and colours ----------------------------------------------------------------
FADE_IN = 0.3
HOLD = 2.0          # message display time 2.0 s, like Maya
FADE_OUT = 1.5
BOX_RGBA = (0.282, 0.282, 0.282, 0.75)   # inViewMessageOpacity 75
TEXT_RGBA = (0.95, 0.95, 0.95, 0.9)
HL_RGB = (0.93, 0.93, 0.03)
LINE_PX = 25.0
FONT_PX = 17.0
PAD = 10.0
INSET = (10.0, 11.0)   # from the view's left / top
RADIUS = 6.0           # corner radius

POSITIONS = ('TOP_LEFT', 'TOP_CENTER')

_HL = re.compile(r"<hl>(.*?)</hl>", re.S)
_state = {"text": "", "pos": 'TOP_LEFT', "start": 0.0, "window": 0, "area": 0, "region": 0, "handle": None}


# --- pure helpers (no bpy, tests/test_step72_view_message.py) ----------------------------------------

def parse(text):
    """Lines of (segment, highlighted) pieces from ``text`` with ``<hl>`` markup and newlines."""
    lines = []
    for line in text.split("\n"):
        pieces, pos = [], 0
        for m in _HL.finditer(line):
            if m.start() > pos:
                pieces.append((line[pos:m.start()], False))
            if m.group(1):
                pieces.append((m.group(1), True))
            pos = m.end()
        if pos < len(line):
            pieces.append((line[pos:], False))
        lines.append(pieces)
    return lines


def alpha(t):
    """Opacity factor 0..1 of a message ``t`` seconds after it was shown (0 = gone)."""
    if t < 0.0 or t >= FADE_IN + HOLD + FADE_OUT:
        return 0.0
    if t < FADE_IN:
        return t / FADE_IN
    if t < FADE_IN + HOLD:
        return 1.0
    return 1.0 - (t - FADE_IN - HOLD) / FADE_OUT


def box_rect(bounds, size, pos, scale=1.0):
    """(x0, y0, x1, y1) of a ``size`` = (w, h) box in region-local ``bounds`` (x0, y0, x1, y1)."""
    w, h = size
    top = bounds[3] - INSET[1] * scale
    if pos == 'TOP_CENTER':
        x0 = (bounds[0] + bounds[2] - w) / 2.0
    else:
        x0 = bounds[0] + INSET[0] * scale
    return (x0, top - h, x0 + w, top)


# --- state ---------------------------------------------------------------------------------------------

def enabled(context=None):
    from .. import preferences
    try:
        return preferences.get(context or bpy.context).in_view_messages
    except (KeyError, AttributeError):
        return False


def current():
    """(text, pos) of the message on screen, or None."""
    t = time.monotonic() - _state["start"]
    if _state["text"] and 0.0 <= t < FADE_IN + HOLD + FADE_OUT:   # alpha is 0 at t = 0, still on screen
        return _state["text"], _state["pos"]
    return None


def _target(context):
    """(window, area, region) the message goes to."""
    from . import status_line, toolbox
    window = context.window
    area, region = context.area, context.region
    if area is None or area.type != 'VIEW_3D' or toolbox.is_toolbox(area.spaces.active) \
            or region is None or region.type != 'WINDOW':
        screen = window.screen if window else None
        area, region = status_line.main_view3d(screen) if screen else (None, None)
    return window, area, region


def show(context, text, pos='TOP_LEFT'):
    """Show ``text`` as a Maya in-view message (replaces the one on screen). Returns True if shown."""
    if not enabled(context) or bpy.app.background:
        return False
    window, area, region = _target(context)
    if area is None or region is None:
        return False
    _state.update(text=text, pos=pos if pos in POSITIONS else 'TOP_LEFT', start=time.monotonic(),
                  window=window.as_pointer() if window else 0, area=area.as_pointer(),
                  region=region.as_pointer())
    area.tag_redraw()
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.05)
    return True


def _area():
    for window in bpy.context.window_manager.windows:
        if window.as_pointer() != _state["window"]:
            continue
        for area in window.screen.areas:
            if area.as_pointer() == _state["area"]:
                return area
    return None


def _tick():
    area = _area()
    if area is not None:
        area.tag_redraw()
    if area is None or current() is None:
        _state["text"] = ""
        return None
    return 0.05


# --- drawing -------------------------------------------------------------------------------------------

def _rounded(x0, y0, x1, y1, r, steps=4):
    import math
    r = max(0.0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    pts = []
    for cx, cy, a0 in ((x1 - r, y1 - r, 0.0), (x0 + r, y1 - r, 90.0), (x0 + r, y0 + r, 180.0),
                       (x1 - r, y0 + r, 270.0)):
        for i in range(steps + 1):
            a = math.radians(a0 + 90.0 * i / steps)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    centre = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    verts = [centre] + pts
    n = len(pts)
    return verts, [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]


def placement(pos, space):
    """Where a message shown at ``pos`` goes in ``space``: Blender's text info sits in the top left (the Maya Workflow Kit
    template hides it), so a TOP_LEFT message moves to the top centre where it is on."""
    overlay = getattr(space, "overlay", None)
    if pos == 'TOP_LEFT' and overlay is not None and overlay.show_overlays and overlay.show_text:
        return 'TOP_CENTER'
    return pos


def draw():
    """POST_PIXEL of 3D View WINDOW regions: the message, only in the region it was shown for."""
    context = bpy.context
    region = context.region
    if not _state["text"] or region is None or region.as_pointer() != _state["region"]:
        return
    from ..marking import draw as marking_draw
    if marking_draw.menu_up():   # Maya's hotbox / marking menus cover in-view messages
        return
    a = alpha(time.monotonic() - _state["start"])
    if a <= 0.0:
        return
    from ..operators import view
    scale = context.preferences.system.ui_scale or 1.0
    lines = parse(_state["text"])
    blf.size(0, FONT_PX * scale)
    widths = [sum(blf.dimensions(0, s)[0] for s, _hl in line) for line in lines]
    line_h = LINE_PX * scale
    size = (max(widths or [0.0]) + 2 * PAD * scale, len(lines) * line_h + 2 * PAD * scale)
    bounds = view.visible_bounds(context.area, region)
    pos = placement(_state["pos"], context.space_data)
    x0, y0, x1, y1 = box_rect(bounds, size, pos, scale)

    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    verts, tris = _rounded(x0, y0, x1, y1, RADIUS * scale)
    batch = batch_for_shader(shader, 'TRIS', {"pos": verts}, indices=tris)
    shader.uniform_float("color", BOX_RGBA[:3] + (BOX_RGBA[3] * a,))
    batch.draw(shader)

    descent = (line_h - FONT_PX * scale) / 2.0 + 2.0 * scale
    for i, line in enumerate(lines):
        x = x0 + PAD * scale
        y = y1 - PAD * scale - (i + 1) * line_h + descent
        for s, hl in line:
            rgb = HL_RGB if hl else TEXT_RGBA[:3]
            blf.color(0, *rgb, TEXT_RGBA[3] * a)
            blf.position(0, x, y, 0)
            blf.draw(0, s)
            x += blf.dimensions(0, s)[0]
    gpu.state.blend_set('NONE')


def register():
    _state["handle"] = bpy.types.SpaceView3D.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    if _state["handle"] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_state["handle"], 'WINDOW')
        _state["handle"] = None
    _state["text"] = ""
