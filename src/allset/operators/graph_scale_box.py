# SPDX-License-Identifier: GPL-3.0-or-later
"""Graph Editor Scale Keys manipulator: a box around the selected keys while the Scale Keys tool (r) is on.

Like Maya's scale manipulator for keys: dragging a side of the box scales the selected keys (and their tangents)
in time (left / right side) or value (bottom / top side) about the opposite side; a corner scales both about the
opposite corner. With time snap on the keys land on whole frames. One drag = one undo step; Esc / right click puts
the keys back. Clicks inside the box or away from it are the Graph Editor's own (select, drag).

The box is drawn in region pixels from the selected keys' control points (display values: degrees, normalized view);
a side whose keys all sit on one frame / value has no extent and doesn't scale. Add-on pref
``graph_scale_manipulator`` (on by default) turns the box off. Pure rules: ``box_of``, ``hit``, ``pivot_of``,
``factor``.
"""

import bpy

from . import graph_move

HANDLE_PX = 4.0          # half size of a handle square (x UI scale)
HIT_PX = 6.0             # how close to a side / handle a press must be (x UI scale)
MIN_EXTENT = 0.5         # px: a side shorter than this doesn't scale
BOX_RGBA = (1.0, 1.0, 1.0, 0.75)
HANDLE_RGBA = (1.0, 0.85, 0.2, 1.0)
CORNERS = ("LB", "RB", "LT", "RT")
SIDES = ("L", "R", "B", "T")


# --- pure rules -------------------------------------------------------------------------------------------------

def box_of(points):
    """(x0, y0, x1, y1) around region points [(x, y)], None for fewer than two keys."""
    pts = list(points)
    if len(pts) < 2:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def handle_points(box):
    """{handle: (x, y)}: four corners and the four side middles."""
    x0, y0, x1, y1 = box
    xm, ym = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return {"LB": (x0, y0), "RB": (x1, y0), "LT": (x0, y1), "RT": (x1, y1),
            "L": (x0, ym), "R": (x1, ym), "B": (xm, y0), "T": (xm, y1)}


def hit(box, x, y, tol=HIT_PX):
    """The handle a press at region (x, y) grabs: a corner, else a side (anywhere along it), else None. A side with
    no extent along the axis it scales is never grabbed."""
    if box is None:
        return None
    x0, y0, x1, y1 = box
    wide, tall = x1 - x0 >= MIN_EXTENT, y1 - y0 >= MIN_EXTENT
    for name in CORNERS:
        hx, hy = handle_points(box)[name]
        if abs(x - hx) <= tol and abs(y - hy) <= tol and (wide or tall):
            return name
    inside_y = y0 - tol <= y <= y1 + tol
    inside_x = x0 - tol <= x <= x1 + tol
    if wide and inside_y:
        if abs(x - x0) <= tol:
            return "L"
        if abs(x - x1) <= tol:
            return "R"
    if tall and inside_x:
        if abs(y - y0) <= tol:
            return "B"
        if abs(y - y1) <= tol:
            return "T"
    return None


def pivot_of(box, name):
    """(pivot x, pivot y, grabbed edge x, grabbed edge y, scales time, scales value) for a handle: the opposite
    side / corner stays."""
    x0, y0, x1, y1 = box
    ex = x0 if "L" in name else x1 if "R" in name else None
    ey = y0 if "B" in name else y1 if "T" in name else None
    px = x1 if "L" in name else x0 if "R" in name else (x0 + x1) / 2.0
    py = y1 if "B" in name else y0 if "T" in name else (y0 + y1) / 2.0
    time = ex is not None and abs(x1 - x0) >= MIN_EXTENT
    value = ey is not None and abs(y1 - y0) >= MIN_EXTENT
    return px, py, ex, ey, time, value


def factor(edge, pivot, delta, min_span=MIN_EXTENT):
    """Scale that carries ``edge`` by ``delta`` while ``pivot`` stays (1 when the edge sits on the pivot)."""
    span = edge - pivot
    if abs(span) < min_span:
        return 1.0
    return (span + delta) / span


# --- the box in a Graph Editor ------------------------------------------------------------------------------------

def enabled(context):
    if getattr(context.window_manager, "allset_graph_key_tool", 'MOVE') != 'SCALE':
        return False
    from .. import preferences
    try:
        return bool(preferences.get(context).graph_scale_manipulator)
    except (KeyError, AttributeError):
        return False


def _selected_points(context):
    """[(view x, display value)] of the selected keys' control points."""
    fcs = [fc for fc in (getattr(context, "editable_fcurves", None) or ())
           if not fc.hide and any(kp.select_control_point for kp in fc.keyframe_points)]
    if not fcs:
        return []
    out = []
    for fc, scale in zip(fcs, graph_move._value_scales(context, fcs)):
        off = graph_move._offset(context, fc)
        for kp in fc.keyframe_points:
            if kp.select_control_point:
                out.append((kp.co.x, (kp.co.y + off) / scale))
    return out


def current_boxes(context):
    """(box in region pixels, box in view units) of this Graph Editor region, None when it isn't shown."""
    if not graph_move._graph_window(context) or not enabled(context):
        return None
    view = box_of(_selected_points(context))
    if view is None:
        return None
    v2d = context.region.view2d
    x0, y0 = v2d.view_to_region(view[0], view[1], clip=False)
    x1, y1 = v2d.view_to_region(view[2], view[3], clip=False)
    return (x0, y0, x1, y1), view


def current_box(context):
    """The box of this Graph Editor region (region pixels), None when it isn't shown."""
    boxes = current_boxes(context)
    return boxes[0] if boxes else None


def _ui(context):
    return context.preferences.system.ui_scale or 1.0


def _draw():
    context = bpy.context
    try:
        box = current_box(context)
    except (AttributeError, ReferenceError, RuntimeError):
        return
    if box is None:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    x0, y0, x1, y1 = box
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.uniform_float("color", BOX_RGBA)
    batch_for_shader(shader, 'LINE_LOOP', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]}).draw(shader)
    s = HANDLE_PX * _ui(context)
    tris = []
    for hx, hy in handle_points(box).values():
        a, b, c, d = (hx - s, hy - s), (hx + s, hy - s), (hx + s, hy + s), (hx - s, hy + s)
        tris += [a, b, c, a, c, d]
    shader.uniform_float("color", HANDLE_RGBA)
    batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)
    gpu.state.blend_set('NONE')


class ALLSET_OT_graph_scale_box(bpy.types.Operator):
    """Scale the selected keys by dragging a side or corner of the Scale Keys box (Graph Editor, r)"""
    bl_idname = "allset.graph_scale_box"
    bl_label = "Scale Keys"
    bl_options = {'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        region = context.region
        try:
            boxes = current_boxes(context)
        except (AttributeError, ReferenceError, RuntimeError):
            boxes = None
        if boxes is None:
            return {'PASS_THROUGH'}
        box, view = boxes
        x, y = event.mouse_x - region.x, event.mouse_y - region.y
        name = hit(box, x, y, HIT_PX * _ui(context))
        if name is None:
            return {'PASS_THROUGH'}
        time, value = pivot_of(box, name)[4:]
        if not (time or value):
            return {'PASS_THROUGH'}
        # the scaling itself runs in view units (frames, display values): exact pivots whatever the zoom
        px, py, ex, ey, _t, _v = pivot_of(view, name)
        self._keys = graph_move.KeySet(context)
        if not self._keys:
            return {'PASS_THROUGH'}
        self._region = region
        self._press = region.view2d.region_to_view(x, y)
        self._edge = (ex, ey)
        self._axes = (time, value)
        self._pivot = (px, py)
        self._snap = graph_move.time_snap_on(context.scene)
        self._moved = False
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _apply(self, x, y):
        (ex, ey), (time, value) = self._edge, self._axes
        mx, my = self._region.view2d.region_to_view(x, y)
        sx = factor(ex, self._pivot[0], mx - self._press[0], 1e-9) if time else 1.0
        sy = factor(ey, self._pivot[1], my - self._press[1], 1e-9) if value else 1.0
        self._keys.apply_scale(self._pivot, sx, sy, self._snap)

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._keys.restore()
            self._keys.finish()
            graph_move._redraw(context)
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._apply(event.mouse_x - self._region.x, event.mouse_y - self._region.y)
            self._moved = True
            graph_move._redraw(context)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if not self._moved:
                return {'CANCELLED'}
            self._keys.finish()
            graph_move._redraw(context)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


classes = (ALLSET_OT_graph_scale_box,)
_handles = []


def register_handlers():
    _handles.append(bpy.types.SpaceGraphEditor.draw_handler_add(_draw, (), 'WINDOW', 'POST_PIXEL'))


def unregister_handlers():
    while _handles:
        bpy.types.SpaceGraphEditor.draw_handler_remove(_handles.pop(), 'WINDOW')
