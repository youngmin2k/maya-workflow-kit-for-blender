# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya-style viewport grid: finite, 12 units each way, a line every unit, thicker every 5, axes thicker.

Default grid (size 12, spacing 5, divisions 5): lines from -12 to +12 every 1 unit, every
5th line (and the axes through the origin) thicker, all the same grey #404040 (a kit colour: no
theme), aliased. The view shows only the background and #404040, minor lines 1 px, major lines and axes 2 px.

Blender's floor is infinite with unit-system steps of x10 (no 5-unit lines), so
the kit draws its own grid with a POST_VIEW handler in the 3D views that use it: on the ground in perspective and
user views, ±size.

Maya's ortho cameras draw the grid in their own view plane and across the whole panel, not ±size
(in Maya's four view the top, front and side panels are gridded edge to edge). Axis ortho views (``is_orthographic_side_view``) get
lines in their plane over the visible span (``span_segments``), in chunks so panning rebuilds the batch rarely.

Per-view state: a 3D View uses the Maya grid when Blender's floor and ortho grid are off and
``overlay.grid_lines`` (not used by Blender 4.x, not in its UI) is 0. The grid unit is one Maya length
(``units.maya_unit``), which ``units.grid_scale`` also makes Blender's finest perspective
grid step, so X-hold grid snapping lands on these lines.

#101: Display > Grid ❒ = Maya's Grid Options (operators/option_windows_display.py): length and width,
grid lines every, subdivisions, the three colours and the Display check boxes change what is drawn here
(``settings()``; the defaults = the constants below).
"""

import math
import time

import bpy

# Default grid.
SIZE = 12
SPACING = 5
DIVISIONS = 5
# Line widths in px: minor, major (every SPACING), axes.
WIDTHS = (1.0, 2.0, 2.0)
# Line colour of grid, axis and highlight lines: #404040.
# A kit colour, not the theme's grid colour: the kit ships no theme
# and Blender's (#545454) all but vanished on the #5c5c5c background (#59).
# The axes are the same grey, only thicker.
LINE_RGB = (64 / 255, 64 / 255, 64 / 255)
OFF_LINES = 16          # Blender's default grid_lines: "not the Maya grid"

_handle = []
_batches = {}
_times = []


# --- maths (no bpy) ----------------------------------------------------------------------

MAX_LINES = 2000          # per direction and side: a tiny spacing must not build a huge batch


def segments(size=SIZE, spacing=SPACING, divisions=DIVISIONS):
    """Grid lines in Maya units on a plane (u, v): {"minor"|"major"|"axis": [((u0, v0), (u1, v1)), ...]}.

    One line every ``spacing / divisions`` unit from -size to +size in both directions (Maya Grid Options: Length
    and width, Grid lines every, Subdivisions); every ``divisions``-th line is major, the two through the origin
    are the axes. Lines stop at ±size; a last step that doesn't fit is left out.
    """
    size = max(float(size), 1e-6)
    divisions = max(1, int(divisions))
    step = max(float(spacing), 1e-6) / divisions
    n = min(int(size / step + 1e-9), MAX_LINES)
    out = {"minor": [], "major": [], "axis": []}
    for i in range(-n, n + 1):
        t = i * step
        if i == 0:
            kind = "axis"
        elif i % divisions == 0:
            kind = "major"
        else:
            kind = "minor"
        out[kind].append(((t, -size), (t, size)))     # along v
        out[kind].append(((-size, t), (size, t)))     # along u
    return out


def styles(opts):
    """What each kind of line is drawn as for Maya Grid Options ``opts`` (``settings()``): {kind: (width px, rgb)}
    for the kinds shown. Axes off = the origin lines are ordinary grid lines; Thicker line for axes off = axes as
    thin as subdivision lines."""
    out = {}
    if opts["show_divisions"]:
        out["minor"] = (WIDTHS[0], tuple(opts["division_color"]))
    if opts["show_lines"]:
        out["major"] = (WIDTHS[1], tuple(opts["line_color"]))
    if opts["show_axes"]:
        out["axis"] = (WIDTHS[2] if opts["thick_axes"] else WIDTHS[0], tuple(opts["axis_color"]))
    elif opts["show_lines"]:
        out["axis"] = out["major"]
    return out


def settings():
    """The applied Maya Grid Options (Maya units, factory values until the window applied others)."""
    from ..operators import option_windows_display
    return option_windows_display.grid_settings()


# plane -> how (u, v) map to Blender (x, y, z). Maya is Y-up: its ground XZ is Blender's XY.
PLANES = {
    "FLOOR": lambda u, v: (u, v, 0.0),     # Blender top / user views
    "XZ": lambda u, v: (u, 0.0, v),       # Blender front / back (Maya front)
    "YZ": lambda u, v: (0.0, u, v),       # Blender left / right (Maya side)
}


def plane_points(segs, plane="FLOOR", unit=1.0):
    """Line segment end points in Blender units (flat list, 2 per line)."""
    f = PLANES[plane]
    pts = []
    for (u0, v0), (u1, v1) in segs:
        pts.append(f(u0 * unit, v0 * unit))
        pts.append(f(u1 * unit, v1 * unit))
    return pts


def plane_for_view(perspective, side_view, view_dir):
    """Grid plane of a view: Maya's ground plane, or the view plane of an axis ortho view (Maya's top / front /
    side cameras grid their own plane). ``view_dir`` = the view's looking
    direction in world space (x, y, z)."""
    if perspective == 'ORTHO' and side_view:
        axis = max(range(3), key=lambda k: abs(view_dir[k]))
        return ("YZ", "XZ", "FLOOR")[axis]
    return "FLOOR"


def fills_view(perspective, side_view):
    """Maya's ortho cameras grid the whole panel; other views stop at ±size."""
    return perspective == 'ORTHO' and bool(side_view)


def span_segments(span_u, span_v, spacing=SPACING, divisions=DIVISIONS):
    """Grid lines (Maya units, kinds like ``segments``) covering the rectangle ``span_u`` x ``span_v`` (lo, hi):
    every line of the infinite grid inside it, each across the whole rectangle."""
    divisions = max(1, int(divisions))
    step = max(float(spacing), 1e-6) / divisions
    out = {"minor": [], "major": [], "axis": []}
    for along, (lo, hi), (olo, ohi) in ((0, span_u, span_v), (1, span_v, span_u)):
        i0, i1 = math.ceil(lo / step - 1e-9), math.floor(hi / step + 1e-9)
        if i1 - i0 > 2 * MAX_LINES:
            continue
        for i in range(i0, i1 + 1):
            t = i * step
            kind = "axis" if i == 0 else "major" if i % divisions == 0 else "minor"
            out[kind].append(((t, olo), (t, ohi)) if along == 0 else ((olo, t), (ohi, t)))
    return out


def view_span(center, half, chunk):
    """(lo, hi) around ``center`` covering ±``half``, widened to whole ``chunk``s (a cache key while panning)."""
    lo = math.floor((center - half) / chunk) * chunk - chunk
    hi = math.ceil((center + half) / chunk) * chunk + chunk
    return lo, hi


def project(matrix, point, width, height):
    """Region pixel (x, y) of a world point for a 4x4 ``perspective_matrix`` (rows), or None behind
    the view; the same as bpy_extras.view3d_utils.location_3d_to_region_2d."""
    x, y, z = point
    v = [sum(matrix[r][c] * p for c, p in enumerate((x, y, z, 1.0))) for r in range(4)]
    if v[3] <= 0.0:
        return None
    return (width / 2 + width / 2 * v[0] / v[3], height / 2 + height / 2 * v[1] / v[3])


def corners(plane="FLOOR", unit=1.0, size=None):
    """The grid's four corners in Blender units (for the projection checks)."""
    f = PLANES[plane]
    s = (SIZE if size is None else size) * unit
    return [f(-s, -s), f(s, -s), f(s, s), f(-s, s)]


# --- per-view state ------------------------------------------------------------------------

def is_on(space):
    ov = space.overlay
    return ov.grid_lines == 0 and not ov.show_floor and not ov.show_ortho_grid


def visible(space):
    """Any grid shown in this view (the Maya grid or Blender's)."""
    ov = space.overlay
    return is_on(space) or ov.show_floor or ov.show_ortho_grid


def set_grid(space, on):
    """Maya grid on (Blender's floor, ortho grid and red/green axis lines off) or no grid at all."""
    ov = space.overlay
    ov.show_floor = False
    ov.show_ortho_grid = False
    ov.show_axis_x = ov.show_axis_y = False
    ov.grid_lines = 0 if on else OFF_LINES


def toggle(space):
    """Maya Show > Grid: hide whatever grid is shown, else show the Maya grid. Returns the new state."""
    on = not visible(space)
    set_grid(space, on)
    return on


class ALLSET_OT_toggle_grid(bpy.types.Operator):
    """Show or hide the grid in this view (Maya grid: Display > Grid options set its size, lines and colours)"""
    bl_idname = "allset.toggle_grid"
    bl_label = "Grid"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == 'VIEW_3D'

    def execute(self, context):
        toggle(context.space_data)
        for area in context.screen.areas if context.screen else ():
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}


# --- drawing -------------------------------------------------------------------------------

def line_colour():
    """RGBA of the grid lines (Grid lines & numbers colour; display space, drawn as is like Blender's overlay
    colours)."""
    return (*settings()["line_color"], 1.0)


def frame_ms():
    """Average time (ms) of the last grid draws (frame-time record)."""
    return sum(_times) / len(_times) * 1000.0 if _times else 0.0


def _batch_set(plane, unit, opts, span=None):
    """``span`` = ((u lo, hi), (v lo, hi)) in Maya units for a grid filling an ortho view, else None (±size)."""
    key = (plane, round(unit, 9), float(opts["size"]), float(opts["spacing"]), int(opts["divisions"]), span)
    if key not in _batches:
        import gpu
        from gpu_extras.batch import batch_for_shader
        if len(_batches) > 16:
            _batches.clear()
        shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        segs = (segments(opts["size"], opts["spacing"], opts["divisions"]) if span is None
                else span_segments(span[0], span[1], opts["spacing"], opts["divisions"]))
        _batches[key] = (shader, {k: batch_for_shader(shader, 'LINES', {"pos": plane_points(segs[k], plane, unit)})
                                  for k in ("minor", "major", "axis") if segs[k]})
    return _batches[key]


def _view_plane(rv3d):
    from mathutils import Vector
    d = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))
    return plane_for_view(rv3d.view_perspective, rv3d.is_orthographic_side_view, tuple(d))


def _draw():
    context = bpy.context
    space, rv3d, region = context.space_data, context.region_data, context.region
    if space is None or rv3d is None or not space.overlay.show_overlays or not is_on(space):
        return
    t0 = time.perf_counter()
    import gpu
    from .. operators import units
    plane = _view_plane(rv3d)
    opts = settings()
    unit = units.maya_unit(context.scene)
    span = None
    if fills_view(rv3d.view_perspective, rv3d.is_orthographic_side_view):
        # visible half width along the longer side: view_distance x 72 / lens / 2
        half = rv3d.view_distance * 36.0 / max(space.lens, 1e-6) / unit
        ix, iy = {"FLOOR": (0, 1), "XZ": (0, 2), "YZ": (1, 2)}[plane]
        loc = rv3d.view_location
        spacing = max(float(opts["spacing"]), 1e-6)
        chunk = spacing * 2 ** max(0, math.ceil(math.log2(max(half / 2.0 / spacing, 1e-9))))   # few distinct keys
        span = (view_span(loc[ix] / unit, half, chunk), view_span(loc[iy] / unit, half, chunk))
    shader, batches = _batch_set(plane, unit, opts, span)
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(False)
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_bool("lineSmooth", False)
    for kind, (width, rgb) in styles(opts).items():
        if kind not in batches:
            continue
        shader.uniform_float("color", (*rgb, 1.0))
        shader.uniform_float("lineWidth", width)
        batches[kind].draw(shader)
    gpu.state.blend_set('NONE')
    gpu.state.depth_test_set('NONE')
    _times.append(time.perf_counter() - t0)
    if len(_times) > 120:
        del _times[0]


def _callback():
    try:
        _draw()
    except Exception:  # never let a draw error repeat every frame
        import traceback
        traceback.print_exc()
        unregister_draw()


def unregister_draw():
    while _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle.pop(), 'WINDOW')


classes = (ALLSET_OT_toggle_grid,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    _handle.append(bpy.types.SpaceView3D.draw_handler_add(_callback, (), 'WINDOW', 'POST_VIEW'))


def unregister():
    unregister_draw()
    _batches.clear()
    _times.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
