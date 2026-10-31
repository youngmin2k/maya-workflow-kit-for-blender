# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Graph Editor Retime Tool (Edit > Transformation Tools > Retime Tool, Issue #105).

- Double-click in the curve area adds a retime marker (whole frame with Snap On Frame).
- Dragging a marker's handle (mid height) retimes every key of the displayed curves: the keys between the moved
  marker and its neighbours scale linearly, keys before a moved first marker / after a moved last marker ripple by the
  move, a lone marker shifts every key; keys outside the neighbours of an inner marker stay. Values are unchanged.
- Dragging the marker line outside the handle moves only the marker; the ✕ circle at the bottom deletes it.
- Markers live while the tool runs (kept per Graph Editor area pointer).

Kit choices:
- A marker can't pass or reach a neighbour: the drag target is clamped strictly inside (m[i-1], m[i+1]) with a gap of
  ``MIN_GAP`` frames (1 frame with Snap On Frame) — Maya's behaviour there was unknown.
- Bézier handles are mapped through the same piecewise-linear time map as the keys (so a handle keeps its place in
  the scaled segment; auto handles are recomputed by ``FCurve.update``).
- Times are the curves' own (action) times; NLA strip time mapping is ignored.
- The tool ends with CANCELLED: every committed drag already pushed its own "Retime" undo step, so the end of the
  tool doesn't add an empty one.
"""

import math
import time

import bpy

from .. import live_refs

MIN_GAP = 0.01            # frames; Blender merges keys closer than 0.01 in x
SNAP_GAP = 1.0
YELLOW = (0.85, 0.85, 0.0, 1.0)
GREY = (0.55, 0.55, 0.55, 1.0)
HANDLE_BAND = (0.40, 0.67)          # fraction of the region height (look)
HIT_PX = 6                          # × UI scale
X_RADIUS = 6                        # ✕ circle radius, × UI scale
X_Y = 12                            # ✕ circle centre above the region bottom, × UI scale


# --- pure maths (no bpy) ------------------------------------------------------------------------------------------

def clamp_target(markers, index, new_time, snap=False):
    """``new_time`` for marker ``index`` of the sorted ``markers``, snapped to a whole frame when ``snap`` and kept
    strictly between its neighbours."""
    b = float(round(new_time)) if snap else float(new_time)
    gap = SNAP_GAP if snap else MIN_GAP
    if index > 0:
        b = max(b, markers[index - 1] + gap)
    if index < len(markers) - 1:
        b = min(b, markers[index + 1] - gap)
    return b


def retime_map(markers, index, new_time):
    """The time map t -> t' of moving marker ``index`` of the sorted ``markers`` to ``new_time``.
    ``new_time`` is used as given (call ``clamp_target`` first)."""
    m = [float(x) for x in markers]
    a, b = m[index], float(new_time)
    d = b - a
    lo = m[index - 1] if index > 0 else None
    hi = m[index + 1] if index < len(m) - 1 else None

    def f(t):
        if t <= a:
            if lo is None:
                return t + d                                  # first / lone marker: ripple
            if t <= lo:
                return t
            return lo + (t - lo) * (b - lo) / (a - lo)
        if hi is None:
            return t + d                                      # last / lone marker: ripple
        if t >= hi:
            return t
        return b + (t - a) * (hi - b) / (hi - a)
    return f


def retime_times(times, markers, index, new_time):
    f = retime_map(markers, index, new_time)
    return [f(t) for t in times]


# --- F-curves -----------------------------------------------------------------------------------------------------

def snapshot(curves):
    """[(fcurve, [(handle_left.x, co.x, handle_right.x), ...]), ...] — the original times a drag maps from."""
    return [(fc, [(kp.handle_left.x, kp.co.x, kp.handle_right.x) for kp in fc.keyframe_points]) for fc in curves]


def apply(snap, f):
    """Write ``f`` of the snapshot times into the curves (values untouched)."""
    for fc, rows in snap:
        kps = fc.keyframe_points
        if len(kps) != len(rows):
            continue
        for kp, (hl, co, hr) in zip(kps, rows):
            kp.co.x = f(co)
            kp.handle_left.x = f(hl)
            kp.handle_right.x = f(hr)
        fc.update()


def restore(snap):
    apply(snap, lambda t: t)


def retime_curves(curves, markers, index, new_time):
    """Retime ``curves`` in one go (headless entry used by tests): returns the new marker time."""
    b = clamp_target(sorted(markers), index, new_time)
    apply(snapshot(curves), retime_map(sorted(markers), index, b))
    return b


# --- tool state / drawing -----------------------------------------------------------------------------------------

_MARKERS = {}              # Graph Editor area pointer -> sorted marker times, while the tool runs there
_DRAG = {}                 # area pointer -> index of the marker being dragged (drawn grey)
_HANDLE = {"draw": None}


def markers_of(area_ptr):
    return _MARKERS.setdefault(area_ptr, [])


def _scale():
    return bpy.context.preferences.system.ui_scale or 1.0


def _region_x(region, frame):
    return region.view2d.view_to_region(frame, 0, clip=False)[0]


def _draw():
    area, region = bpy.context.area, bpy.context.region
    if area is None or region is None:
        return
    marks = _MARKERS.get(area.as_pointer())
    if not marks:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    s = _scale()
    h = region.height
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    dragged = _DRAG.get(area.as_pointer())
    xs = [_region_x(region, t) for t in marks]
    top = h - 4 * s
    gpu.state.blend_set('ALPHA')

    def draw(kind, coords, color, width=1.0):
        gpu.state.line_width_set(width)
        shader.uniform_float("color", color)
        batch_for_shader(shader, kind, {"pos": coords}).draw(shader)

    # bracket over the tops of neighbouring markers
    if len(xs) > 1:
        draw('LINES', [p for x0, x1 in zip(xs, xs[1:]) for p in ((x0, top), (x1, top))], YELLOW, 2.0)
    for k, x in enumerate(xs):
        col = GREY if k == dragged else YELLOW
        cy, r = X_Y * s, X_RADIUS * s
        draw('LINES', [(x, cy + r), (x, top)], col, 1.0)
        draw('LINES', [(x, h * HANDLE_BAND[0]), (x, h * HANDLE_BAND[1])], col, max(4.0, 5 * s))
        circle = []
        n = 16
        for j in range(n):
            a0, a1 = 2 * math.pi * j / n, 2 * math.pi * (j + 1) / n
            circle += [(x + r * math.cos(a0), cy + r * math.sin(a0)), (x + r * math.cos(a1), cy + r * math.sin(a1))]
        q = r * 0.5
        circle += [(x - q, cy - q), (x + q, cy + q), (x - q, cy + q), (x + q, cy - q)]
        draw('LINES', circle, col, 1.5)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


# Maya's Retime Tool works in the Graph Editor and the Dope Sheet (both Edit menus)
SPACES = ("SpaceGraphEditor", "SpaceDopeSheetEditor")
AREA_TYPES = {'GRAPH_EDITOR', 'DOPESHEET_EDITOR'}


def _ensure_draw():
    if _HANDLE["draw"] is None:
        _HANDLE["draw"] = [(name, getattr(bpy.types, name).draw_handler_add(_draw, (), 'WINDOW', 'POST_PIXEL'))
                           for name in SPACES]


def _remove_draw():
    for name, h in _HANDLE["draw"] or ():
        getattr(bpy.types, name).draw_handler_remove(h, 'WINDOW')
    _HANDLE["draw"] = None


def _drop_draw():
    if _HANDLE["draw"] is not None and not _MARKERS:
        _remove_draw()


def hit(marks, xs, x, y, height, scale):
    """What a press at region (x, y) hits: (index, part) with part 'DELETE' / 'HANDLE' / 'LINE', or (None, None).
    ``xs`` = the markers' region x."""
    best = None
    for k, mx in enumerate(xs):
        dx = abs(x - mx)
        if dx <= HIT_PX * scale and (best is None or dx < abs(x - xs[best])):
            best = k
    if best is None:
        # the ✕ circle is a little wider than the line hit zone
        for k, mx in enumerate(xs):
            if (x - mx) ** 2 + (y - X_Y * scale) ** 2 <= ((X_RADIUS + 2) * scale) ** 2:
                return k, 'DELETE'
        return None, None
    mx = xs[best]
    if (x - mx) ** 2 + (y - X_Y * scale) ** 2 <= ((X_RADIUS + 2) * scale) ** 2:
        return best, 'DELETE'
    if height * HANDLE_BAND[0] <= y <= height * HANDLE_BAND[1]:
        return best, 'HANDLE'
    return best, 'LINE'


def _window_region(area):
    return next((r for r in area.regions if r.type == 'WINDOW'), None)


class ALLSET_OT_retime_tool(bpy.types.Operator):
    """Maya Retime Tool: double-click in the curve area to add retime markers, drag a marker's handle to scale and
    ripple the keys of the displayed curves, the ✕ deletes a marker. Esc or Q/W/E/R/T ends the tool"""
    bl_idname = "allset.retime_tool"
    bl_label = "Retime Tool"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        area = getattr(context, "area", None)
        return area is not None and area.type in AREA_TYPES and context.window is not None

    def invoke(self, context, event):
        return self._start(context)

    def execute(self, context):
        return self._start(context)

    def _start(self, context):
        area = context.area
        region = _window_region(area)
        if region is None:
            return {'CANCELLED'}
        self._win_ptr = context.window.as_pointer()
        self._area_ptr = area.as_pointer()
        self._region_ptr = region.as_pointer()
        self._last_press = None     # (time, x, y) of the last press on empty curve area
        self._drag = None           # (index, part, snapshot or None, original marker time)
        markers_of(self._area_ptr)
        _ensure_draw()
        context.window_manager.modal_handler_add(self)
        area.tag_redraw()
        return {'RUNNING_MODAL'}

    # -- helpers --
    def _live(self):
        win, area = live_refs.find_area(self._area_ptr, self._win_ptr)
        if area is None:
            return None, None, None
        region = live_refs.region(area, self._region_ptr)
        return win, area, region

    def _end(self, context, area=None):
        if self._drag is not None and self._drag[2] is not None:
            restore(self._drag[2])
        self._drag = None
        _MARKERS.pop(self._area_ptr, None)
        _DRAG.pop(self._area_ptr, None)
        _drop_draw()
        if area is not None:
            area.tag_redraw()
        return {'CANCELLED'}

    @staticmethod
    def _curves(win, area, region):
        with bpy.context.temp_override(window=win, area=area, region=region):
            return [fc for fc in (getattr(bpy.context, "editable_fcurves", None) or ()) if len(fc.keyframe_points)]

    def _snap(self, context):
        from .. import preferences
        try:
            return bool(preferences.get(context).retime_snap_on_frame)
        except (KeyError, AttributeError):
            return False

    # -- modal --
    def modal(self, context, event):
        win, area, region = self._live()
        if region is None:
            return self._end(context)
        marks = markers_of(self._area_ptr)
        x, y = event.mouse_x - region.x, event.mouse_y - region.y
        inside = 0 <= x < region.width and 0 <= y < region.height

        if self._drag is not None:
            return self._modal_drag(context, event, win, area, region, marks, x)

        if event.type == 'ESC' and event.value == 'PRESS':
            return self._end(context, area)
        if event.type in {'Q', 'W', 'E', 'R', 'T'} and event.value == 'PRESS' and not (event.ctrl or event.alt):
            self._end(context, area)
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.type != 'LEFTMOUSE' or event.value not in {'PRESS', 'DOUBLE_CLICK'} or not inside:
            return {'PASS_THROUGH'}
        if event.shift or event.ctrl or event.alt:
            return {'PASS_THROUGH'}
        s = context.preferences.system.ui_scale or 1.0
        xs = [_region_x(region, t) for t in marks]
        k, part = hit(marks, xs, x, y, region.height, s)
        if k is None:
            if not self._double(context, event):
                return {'PASS_THROUGH'}
            t = region.view2d.region_to_view(x, y)[0]
            if self._snap(context):
                t = float(round(t))
            if any(abs(t - m) < MIN_GAP for m in marks):
                return {'RUNNING_MODAL'}
            marks.append(t)
            marks.sort()
            area.tag_redraw()
            return {'RUNNING_MODAL'}
        if part == 'DELETE':
            del marks[k]
            area.tag_redraw()
            return {'RUNNING_MODAL'}
        snap = snapshot(self._curves(win, area, region)) if part == 'HANDLE' else None
        self._drag = (k, part, snap, marks[k])
        _DRAG[self._area_ptr] = k
        area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _double(self, context, event):
        """A double-click on empty curve area: Blender's DOUBLE_CLICK, or a second PRESS within the double-click
        time near the first (simulated events never become DOUBLE_CLICK)."""
        now = time.monotonic()
        last, self._last_press = self._last_press, (now, event.mouse_x, event.mouse_y)
        if event.value == 'DOUBLE_CLICK':
            self._last_press = None
            return True
        limit = getattr(context.preferences.inputs, "mouse_double_click_time", 350) / 1000.0
        if last is not None and now - last[0] <= limit and abs(event.mouse_x - last[1]) <= 4                 and abs(event.mouse_y - last[2]) <= 4:
            self._last_press = None
            return True
        return False

    def _target(self, context, region, marks, k, x):
        t = region.view2d.region_to_view(x, 0)[0]
        return clamp_target(marks, k, t, self._snap(context))

    def _modal_drag(self, context, event, win, area, region, marks, x):
        k, part, snap, orig = self._drag
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            if snap is not None:
                restore(snap)
            marks[k] = orig
            self._drag = None
            _DRAG.pop(self._area_ptr, None)
            area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            b = self._target(context, region, [*marks[:k], orig, *marks[k + 1:]], k, x)
            if snap is not None:
                apply(snap, retime_map([*marks[:k], orig, *marks[k + 1:]], k, b))
            marks[k] = b
            area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            ref = [*marks[:k], orig, *marks[k + 1:]]
            b = self._target(context, region, ref, k, x)
            if snap is not None:
                apply(snap, retime_map(ref, k, b))
            marks[k] = b
            self._drag = None
            _DRAG.pop(self._area_ptr, None)
            if snap is not None and b != orig:
                bpy.ops.ed.undo_push(message="Retime")
            area.tag_redraw()
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}


classes = (ALLSET_OT_retime_tool,)


def register_handlers():
    pass


def unregister_handlers():
    _MARKERS.clear()
    _DRAG.clear()
    if _HANDLE["draw"] is not None:
        _remove_draw()
