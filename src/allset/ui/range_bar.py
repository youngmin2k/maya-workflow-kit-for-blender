# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's Range Slider bar in the timeline header: drag the playback range.

The bar: a dark
track (#373737) spans the animation range, the playback range is a rounded segment (#5d5d5d) on it with
a handle square (#919191) inside each end and the start / end frames next to the handles. Dragging the
segment moves the playback range, dragging a handle moves that end.

Blender has no such widget and Python can't tell where a header layout put an item, so
``time_slider.draw_range_slider`` leaves an empty label where the bar goes (a button would take the
mouse) and the header POST_PIXEL handler here finds that gap by reading one row of the header it has
just drawn (``bar_span``), draws the bar there and remembers the rectangle for
``allset.range_bar_drag`` ("Screen" keymap: a click on an empty label reaches the window keymaps).
Only in timelines whose transport buttons sit in the sidebar (the Maya Workflow Kit layout), where nothing
stretches before the bar.
"""

import bpy

# --- sizes and colours ----------------------------------------------------------------
TRACK_RGB = (0x37 / 255, 0x37 / 255, 0x37 / 255, 1.0)
SEGMENT_RGB = (0x5d / 255, 0x5d / 255, 0x5d / 255, 1.0)
HANDLE_RGB = (0x91 / 255, 0x91 / 255, 0x91 / 255, 1.0)
TEXT_RGB = (0.8, 0.8, 0.8, 1.0)            # light grey of the frame numbers
MAYA_BAR_H = 23.0                          # track height
SEG_INSET = 2.0                            # segment inside the track
HANDLE = (13.0, 14.0)                      # handle square w, h
HANDLE_INSET = 5.0                         # from the segment end
TEXT_PX = 11.0
BAR_UNITS = 18                             # ui_units_x of the placeholder label

_bars = {}       # area pointer -> rectangle and range, region-local (filled while drawing)
_handle = []


# --- pure helpers (tests/test_step73_time_slider.py) --------------------------------------------------

def bar_span(row, bg, min_w, skip=2):
    """(x0, x1) of the first run of ``bg`` at least ``min_w`` wide that follows ``skip`` non-``bg`` runs
    in ``row`` (a list of colours), or None."""
    runs, start = [], 0
    for i in range(1, len(row) + 1):
        if i == len(row) or (row[i] == bg) != (row[start] == bg):
            runs.append((start, i, row[start] == bg))
            start = i
    seen = 0
    for a, b, is_bg in runs:
        if not is_bg:
            seen += 1
        elif seen >= skip and b - a >= min_w and b < len(row):
            return a, b
    return None


def frame_x(f, x0, x1, s, e):
    """x of frame ``f`` on a track x0..x1 that spans the animation range s..e."""
    return x0 + (f - s) / max(e - s, 1) * (x1 - x0)


def segment(bar, ps, pe):
    """(xs, xe) of the playback range on ``bar`` = dict(x0, x1, s, e), kept on the track."""
    x0, x1 = bar["x0"], bar["x1"]
    return tuple(max(x0, min(x1, frame_x(f, x0, x1, bar["s"], bar["e"]))) for f in (ps, pe))


def zone(x, xs, xe, handle_w):
    """What a press at ``x`` grabs: 'START' / 'END' handle, 'MOVE' the segment, or None."""
    if x < xs - 1 or x > xe + 1:
        return None
    if x <= xs + handle_w:
        return 'START'
    if x >= xe - handle_w:
        return 'END'
    return 'MOVE'


def drag_range(kind, ps, pe, d, s, e):
    """New (start, end) playback range after dragging ``kind`` by ``d`` whole frames inside s..e."""
    if kind == 'MOVE':
        d = max(s - ps, min(e - pe, d))
        return ps + d, pe + d
    if kind == 'START':
        return max(s, min(pe - 1, ps + d)), pe
    if kind == 'END':
        return ps, min(e, max(ps + 1, pe + d))
    return ps, pe


def playback(scene):
    if scene.use_preview_range:
        return scene.frame_preview_start, scene.frame_preview_end
    return scene.frame_start, scene.frame_end


def toggle_whole(scene):
    """Maya double-click on the Range Slider: the whole animation range <-> the playback range.
    Blender keeps the preview range while it is off, so this is the preview range toggle."""
    scene.use_preview_range = not scene.use_preview_range


def set_playback(scene, a, b):
    scene.use_preview_range = True
    # Blender pushes the other end when start > end: order the writes so neither clamps.
    if a > scene.frame_preview_end:
        scene.frame_preview_end = b
        scene.frame_preview_start = a
    else:
        scene.frame_preview_start = a
        scene.frame_preview_end = b


# --- drawing -------------------------------------------------------------------------------------------

def active(context):
    from . import time_slider
    space = context.space_data
    # the Maya Workflow Kit layout's timeline (sidebar on; on 5.x it can't open — the bar stays in the header)
    return (space is not None and getattr(space, "mode", None) == 'TIMELINE'
            and time_slider.has_slider_panel(space))


def _rounded(x0, y0, x1, y1, r, colour):
    import math
    import gpu
    from gpu_extras.batch import batch_for_shader
    r = max(0.0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    pts = []
    for cx, cy, a0 in ((x1 - r, y1 - r, 0.0), (x0 + r, y1 - r, 90.0), (x0 + r, y0 + r, 180.0),
                       (x1 - r, y0 + r, 270.0)):
        for i in range(5):
            a = math.radians(a0 + 22.5 * i)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    verts = [((x0 + x1) / 2.0, (y0 + y1) / 2.0)] + pts
    n = len(pts)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": verts},
                             indices=[(0, 1 + i, 1 + (i + 1) % n) for i in range(n)])
    shader.uniform_float("color", colour)
    batch.draw(shader)


def _read_row(region, y):
    import gpu
    fb = gpu.state.active_framebuffer_get()
    from .. import compat
    buf = compat.read_region_row(fb, region, y)
    if buf is None:
        return []
    return [tuple(buf[0][i][:3]) for i in range(region.width)]


def draw():
    """POST_PIXEL of Dope Sheet HEADER regions."""
    context = bpy.context
    area, region = context.area, context.region
    if area is None or region is None or not active(context):
        return
    scale = context.preferences.system.ui_scale or 1.0
    unit = round(20 * scale)
    row = _read_row(region, region.height // 2)
    if len(row) < 3:
        return
    span = bar_span(row, row[2], min_w=BAR_UNITS * unit * 0.6)
    if span is None:
        _bars.pop(area.as_pointer(), None)
        return
    pad = round(4 * scale)
    x0, x1 = span[0] + pad, span[1] - pad
    y0 = (region.height - unit) / 2.0
    y1 = y0 + unit
    scene = context.scene
    s, e = scene.frame_start, scene.frame_end
    bar = dict(x0=x0, x1=x1, y0=y0, y1=y1, s=s, e=e, window=context.window.as_pointer(),
               region=region.as_pointer())
    _bars[area.as_pointer()] = bar

    import blf
    import gpu
    k = unit / MAYA_BAR_H
    gpu.state.blend_set('ALPHA')
    _rounded(x0, y0, x1, y1, 4 * k, TRACK_RGB)
    ps, pe = playback(scene)
    xs, xe = segment(bar, ps, pe)
    inset = SEG_INSET * k
    _rounded(xs, y0 + inset, xe, y1 - inset, 4 * k, SEGMENT_RGB)
    hw, hh = HANDLE[0] * k, HANDLE[1] * k
    hy0 = (y0 + y1 - hh) / 2.0
    hx0, hx1 = xs + HANDLE_INSET * k, xe - HANDLE_INSET * k - hw
    _rounded(hx0, hy0, hx0 + hw, hy0 + hh, 3 * k, HANDLE_RGB)
    _rounded(hx1, hy0, hx1 + hw, hy0 + hh, 3 * k, HANDLE_RGB)
    blf.size(0, TEXT_PX * scale)
    blf.color(0, *TEXT_RGB)
    ty = (y0 + y1) / 2.0 - TEXT_PX * scale * 0.35
    a_txt, b_txt = f"{ps:g}", f"{pe:g}"
    blf.position(0, hx0 + hw + 3 * k, ty, 0)
    blf.draw(0, a_txt)
    blf.position(0, hx1 - 3 * k - blf.dimensions(0, b_txt)[0], ty, 0)
    blf.draw(0, b_txt)
    gpu.state.blend_set('NONE')
    bar["handle_w"] = (HANDLE_INSET + HANDLE[0]) * k


# --- the drag -----------------------------------------------------------------------------------------

def hit(context, event):
    """(area, region, bar) of a timeline Range Slider bar under the mouse, or None."""
    window = context.window
    if window is None:
        return None
    for area in window.screen.areas:
        bar = _bars.get(area.as_pointer())
        if bar is None or bar["window"] != window.as_pointer() or area.type != 'DOPESHEET_EDITOR':
            continue
        if area.spaces.active.mode != 'TIMELINE':
            continue
        region = next((r for r in area.regions if r.type == 'HEADER'), None)
        if region is None or region.as_pointer() != bar["region"]:
            continue
        x, y = event.mouse_x - region.x, event.mouse_y - region.y
        if bar["x0"] <= x <= bar["x1"] and bar["y0"] <= y <= bar["y1"] and 0 <= y < region.height:
            return area, region, bar
    return None


class ALLSET_OT_range_bar_drag(bpy.types.Operator):
    """Maya Range Slider: drag the playback range, or one of its ends; double-click toggles the whole
    animation range"""
    bl_idname = "allset.range_bar_drag"
    bl_label = "Range Slider"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        found = hit(context, event)
        if found is None:
            return {'PASS_THROUGH'}
        area, region, bar = found
        scene = context.scene
        if event.value == 'DOUBLE_CLICK':
            toggle_whole(scene)
            area.tag_redraw()
            return {'FINISHED'}
        ps, pe = playback(scene)
        xs, xe = segment(bar, ps, pe)
        kind = zone(event.mouse_x - region.x, xs, xe, bar.get("handle_w", 18))
        if kind is None:
            return {'PASS_THROUGH'}
        self._kind, self._area, self._x = kind, area, event.mouse_x
        self._old = (scene.use_preview_range, scene.frame_preview_start, scene.frame_preview_end)
        self._range = (ps, pe)
        self._ppf = (bar["x1"] - bar["x0"]) / max(bar["e"] - bar["s"], 1)
        self._bounds = (bar["s"], bar["e"])
        self._moved = False
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        scene = context.scene
        if event.type == 'MOUSEMOVE':
            d = round((event.mouse_x - self._x) / max(self._ppf, 1e-6))
            a, b = drag_range(self._kind, *self._range, d, *self._bounds)
            if (a, b) != playback(scene) or not scene.use_preview_range:
                if d or self._moved:
                    set_playback(scene, a, b)
                    self._moved = True
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'} if self._moved else {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            scene.frame_preview_start, scene.frame_preview_end = self._old[1], self._old[2]
            scene.use_preview_range = self._old[0]
            self._area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


classes = (ALLSET_OT_range_bar_drag,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    _handle.append(bpy.types.SpaceDopeSheetEditor.draw_handler_add(draw, (), 'HEADER', 'POST_PIXEL'))


def unregister():
    while _handle:
        bpy.types.SpaceDopeSheetEditor.draw_handler_remove(_handle.pop(), 'HEADER')
    _bars.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
