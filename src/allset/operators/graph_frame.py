# SPDX-License-Identifier: GPL-3.0-or-later
"""Graph Editor F / A framing the Maya way (#192).

Maya's Graph Editor frames a rectangle Blender's ``graph.view_selected`` / ``graph.view_all`` don't make:

* **Bounds.** F with keys selected: for every selected key the union of the key and the boxes of both curve segments
  touching it. A segment box spans the segment's two key times; its values are the two key values widened by the
  segment's control polygon (a Bezier segment's out handle of the first key and in handle of the second key).
  F with no key selected, and A: the whole box of every curve the editor draws (same segment rule).
* **Zero spans.** Time: one frame centred on the key (t ± 0.5). Value: 0 gives [-0.5, 0.5], v gives [0.5 v, 1.5 v].
* **Margins.** 10 % of the time span before and after, 25 % of the value span below and above, whatever the window
  size. The value range fills the canvas between the time ruler strip at the top and the scroll bar (or the marker
  row) at the bottom; the time range fills the canvas width.
* **Auto Frame** (``ui/graph_view.py``): the same rectangle, value axis only (time range kept), and the time axis
  too with Auto Frame Time.

Python can't write ``View2D.cur``. The kit reaches the rectangle with ``view2d.zoom_border`` (EXEC: no smooth view):
the region-pixel corners of the wanted view are computed from ``region_to_view``; a first border zoom brings the view
near the target, a zoom into a 2 px box makes the view tiny, and the last border zoom then lands within a small
fraction of a pixel (its corners are whole pixels of the tiny view).

The editor's value axis shows rotation curves in degrees (scene rotation unit), so their values are converted the same
way. A normalised view (Blender's Normalize) and the Drivers editor keep Blender's own frame operators.
The bottom pad = Blender's scroll bar / marker row height, margins applied after the zero-span rule.
"""

import math

import bpy
from bpy.props import EnumProperty

TIME_MARGIN = 0.1
VALUE_MARGIN = 0.25
ZERO = 1e-10

SCRUB_PX = 23.0             # Blender's time ruler strip at the top of the Graph Editor canvas (x UI scale)
MARKER_PX = 42.0            # Blender's marker row at the bottom (x UI scale), when markers show
SCROLL_UNITS = 0.6          # Blender's horizontal scroll bar height in widget units
INT_LIMIT = 2 ** 30


# --- bpy-free maths -------------------------------------------------------------------------------------------------
# A key = (time, value, in-handle value, out-handle value, bezier): ``bezier`` = the segment after this key is a
# Bezier segment (Blender's interpolation is stored on the key that starts the segment).

def segment_box(a, b):
    """(t0, t1, v0, v1) of the segment from key ``a`` to key ``b``."""
    vals = [a[1], b[1]]
    if a[4]:
        vals += [a[3], b[2]]
    return a[0], b[0], min(vals), max(vals)


def union(boxes):
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), max(b[1] for b in boxes), min(b[2] for b in boxes), max(b[3] for b in boxes))


def key_box(keys, i):
    """The key ``i`` and both segments touching it."""
    t, v = keys[i][0], keys[i][1]
    boxes = [(t, t, v, v)]
    if i > 0:
        boxes.append(segment_box(keys[i - 1], keys[i]))
    if i + 1 < len(keys):
        boxes.append(segment_box(keys[i], keys[i + 1]))
    return union(boxes)


def curve_box(keys):
    """Every key and segment of one curve; None without keys."""
    if not keys:
        return None
    return union([key_box(keys, i) for i in range(len(keys))])


def selected_box(curves):
    """``curves`` = [(keys, selected key indices)]: the union of the selected keys' boxes; None if none selected."""
    return union([key_box(keys, i) for keys, sel in curves for i in sel])


def all_box(curves):
    return union([curve_box(keys) for keys, _sel in curves])


def maya_rect(box):
    """(t0, t1, v0, v1) Maya frames for the bounds ``box``: zero spans widened, then the margins."""
    t0, t1, v0, v1 = box
    if t1 - t0 <= ZERO:
        t0, t1 = t0 - 0.5, t0 + 0.5
    if v1 - v0 <= ZERO:
        v = v0
        if v == 0.0:
            v0, v1 = -0.5, 0.5
        else:
            v0, v1 = sorted((0.5 * v, 1.5 * v))
    dt, dv = (t1 - t0) * TIME_MARGIN, (v1 - v0) * VALUE_MARGIN
    return t0 - dt, t1 + dt, v0 - dv, v1 + dv


def view_for(rect, width, height, pad_bottom, pad_top):
    """(x0, x1, y0, y1) the region must map onto pixels 0 .. ``width`` / 0 .. ``height`` so ``rect``'s time fills the
    width and its values fill the canvas between ``pad_bottom`` and ``height - pad_top`` px."""
    t0, t1, v0, v1 = rect
    inner = max(height - pad_bottom - pad_top, 1.0)
    per_px = (v1 - v0) / inner
    return t0, t1, v0 - pad_bottom * per_px, v1 + pad_top * per_px


def to_pixels(view, mapping):
    """Region pixels (x0, x1, y0, y1) of the view rect ``view`` under ``mapping`` = (vx0, sx, vy0, sy), where view x
    = vx0 + sx * px."""
    vx0, sx, vy0, sy = mapping
    x0, x1, y0, y1 = view
    return (x0 - vx0) / sx, (x1 - vx0) / sx, (y0 - vy0) / sy, (y1 - vy0) / sy


def _clamp(v):
    return int(max(-INT_LIMIT, min(INT_LIMIT, round(v))))


# --- Blender side ---------------------------------------------------------------------------------------------------

def _scale(context):
    s = context.preferences.system
    return (s.ui_scale or 1.0), (s.pixel_size or 1.0)


def pads(context, space):
    """(bottom, top) region px the value range keeps clear: Blender's scroll bar or marker row / time ruler strip."""
    s, px = _scale(context)
    top = SCRUB_PX * s
    markers = bool(getattr(space, "show_markers", False)) and len(context.scene.timeline_markers) > 0
    if markers:
        return MARKER_PX * s, top
    widget = math.floor(18.0 * s + 0.5) + 2 * px
    return SCROLL_UNITS * widget, top


def _mapping(region):
    """(vx0, sx, vy0, sy): view x = vx0 + sx * region px. The slope is sampled a million px apart: the view rect
    is single precision, so near samples would round it."""
    v = region.view2d
    far = 1048576.0
    x0, y0 = v.region_to_view(-far, -far)
    x1, y1 = v.region_to_view(far, far)
    ox, oy = v.region_to_view(0.0, 0.0)
    return ox, (x1 - x0) / (2 * far), oy, (y1 - y0) / (2 * far)


def span_px(region):
    """(x, y) pixel distance between the region's first and last pixel: Blender's View2D maps its view rect onto
    pixels 0 .. width - 1 / height - 1."""
    return max(region.width - 1, 1), max(region.height - 1, 1)


def current_view(region):
    """(x0, x1, y0, y1) the region shows now."""
    vx0, sx, vy0, sy = _mapping(region)
    w, h = span_px(region)
    return vx0, vx0 + sx * w, vy0, vy0 + sy * h


def _rotation_factor(context):
    us = context.scene.unit_settings
    return 1.0 if us.system_rotation == 'RADIANS' else 180.0 / math.pi


def _factors(context, fcurves):
    from ..ui import graph_units
    rot = _rotation_factor(context)
    return [rot if u == 'ROTATION' else 1.0 for u in graph_units.curve_units(fcurves)]


def drawn_curves(context):
    """F-curves the Graph Editor of ``context`` draws (its visible curves, hidden ones left out)."""
    return [fc for fc in (getattr(context, "visible_fcurves", None) or ()) if not fc.hide]


def curve_data(context, fcurves=None):
    """[(keys, selected key indices)] of the drawn curves, values in the editor's display units."""
    fcs = drawn_curves(context) if fcurves is None else fcurves
    out = []
    for fc, k in zip(fcs, _factors(context, fcs)):
        pts = sorted(fc.keyframe_points, key=lambda p: p.co.x)
        keys = [(p.co.x, p.co.y * k, p.handle_left.y * k, p.handle_right.y * k, p.interpolation == 'BEZIER')
                for p in pts]
        sel = [i for i, p in enumerate(pts) if p.select_control_point]
        out.append((keys, sel))
    return out


def target_rect(context, mode):
    """Maya's (t0, t1, v0, v1) for F ('SELECTED') or A ('ALL'); None when no curve has keys."""
    curves = curve_data(context)
    box = selected_box(curves) if mode == 'SELECTED' else None
    if box is None:
        box = all_box(curves)
    return maya_rect(box) if box is not None else None


def _zoom(region, px):
    x0, x1, y0, y1 = px
    bpy.ops.view2d.zoom_border(xmin=_clamp(x0), xmax=_clamp(x1), ymin=_clamp(y0), ymax=_clamp(y1),
                               wait_for_input=False)


def apply_view(context, region, view):
    """Make ``region`` show the view rect ``view`` (x0, x1, y0, y1); run under a Graph Editor override."""
    w, h = span_px(region)
    for _ in range(3):                         # bring the view near the target (a far / tiny target first)
        px = to_pixels(view, _mapping(region))
        if w / 8 <= px[1] - px[0] <= 8 * w and h / 8 <= px[3] - px[2] <= 8 * h:
            break
        cx, cy = (px[0] + px[1]) / 2, (px[2] + px[3]) / 2           # at least 2 px: a sub-pixel target
        _zoom(region, (min(px[0], cx - 1), max(px[1], cx + 1), min(px[2], cy - 1), max(px[3], cy + 1)))
    px = to_pixels(view, _mapping(region))
    cx, cy = (px[0] + px[1]) / 2, (px[2] + px[3]) / 2
    _zoom(region, (cx - 1, cx + 1, cy - 1, cy + 1))       # tiny view around the target's centre
    _zoom(region, to_pixels(view, _mapping(region)))
    return current_view(region)


def frame(context, region, mode='ALL', time=True, value=True):
    """Frame this Graph Editor (context = its override) Maya's way. ``time`` / ``value`` = which axes change.
    Returns the view rect reached, or None when there was nothing to frame."""
    rect = target_rect(context, mode)
    if rect is None:
        return None
    bottom, top = pads(context, context.space_data)
    want = view_for(rect, *span_px(region), bottom, top)
    now = current_view(region)
    want = (want[0] if time else now[0], want[1] if time else now[1],
            want[2] if value else now[2], want[3] if value else now[3])
    return apply_view(context, region, want)


def _window_region(context):
    region = context.region
    if region is not None and region.type == 'WINDOW':
        return region
    area = context.area
    return next((r for r in area.regions if r.type == 'WINDOW'), None) if area is not None else None


class ALLSET_OT_graph_frame(bpy.types.Operator):
    """Frame the selected keys (or every curve shown) the Maya way"""
    bl_idname = "allset.graph_frame"
    bl_label = "Frame"
    bl_options = {'REGISTER'}

    mode: EnumProperty(name="Mode", items=(('SELECTED', "Frame Selection", "Frame the selected keys (every curve "
                                                         "when no key is selected)"),
                                           ('ALL', "Frame All", "Frame every curve shown")),
                       default='ALL', options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.type == 'GRAPH_EDITOR' and context.area is not None

    @classmethod
    def description(cls, _context, props):
        return ("Frame the selected keys (every curve when no key is selected)" if props.mode == 'SELECTED'
                else "Frame every curve shown")

    def _blender(self, context, region):
        with context.temp_override(region=region):
            op = bpy.ops.graph.view_selected if self.mode == 'SELECTED' else bpy.ops.graph.view_all
            return op()

    def execute(self, context):
        region = _window_region(context)
        if region is None:
            return {'CANCELLED'}
        space = context.space_data
        if space.mode != 'FCURVES' or space.use_normalization:
            return self._blender(context, region)
        with context.temp_override(region=region):
            done = frame(bpy.context, region, self.mode)
        return {'FINISHED'} if done is not None else {'CANCELLED'}


classes = (ALLSET_OT_graph_frame,)
