# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya 2024+ Paint Skin Weights > Visualization > Numeric: the painted influence's weight at every vertex
(Issue #134 / #126 A3).

Settings: Show Numbers off by default, Decimal Places 2 (1-4), Number Color yellow (1, 1, 0), optional Color Ramp
(0 white -> 1 black), back-facing vertices drawn too. Blender has no such display, so the kit draws it: a 3D View
WINDOW POST_PIXEL handler projects the (deformed) vertices with numpy and draws ``blf`` labels.

No mesh-size limit; the cost is the labels on screen (blf 2.2 us each, weight
read ~1 us), so at most ``LIMIT`` = 2,000 labels are drawn; with more vertices in view only those within twice the
brush radius of the pointer are drawn and the Help Line says how many are in view (Maya draws all — kit
difference). Projections and weights are cached and refreshed after a depsgraph update — not while a paint stroke runs
(the numbers follow when the stroke ends).
"""

import time

import blf
import bpy
import numpy as np

LIMIT = 2000
FONT = 0
_handles = []
_cache = {"key": None, "co": None, "weights": {}, "dirty": False}
STATS = {"drawn": 0, "in_view": 0, "capped": False, "ms": 0.0, "mouse": None, "history": [], "refreshed": False}


def settings(context):
    from ..operators import weight_paint
    return weight_paint.state(context)


def _stroke_running(context):
    win = context.window
    return win is not None and any(op.bl_idname in {"PAINT_OT_weight_paint", "PAINT_OT_weight_gradient"}
                                   for op in win.modal_operators)


def format_weight(w, places):
    return f"{w:.{max(1, min(4, int(places)))}f}"


def ramp_color(w, low, high):
    """Maya Color Ramp of the numbers: weight 0 = the min colour (white), 1 = the max colour (black)."""
    w = min(1.0, max(0.0, w))
    return tuple(low[i] + (high[i] - low[i]) * w for i in range(3))


def project(co, matrix, width, height):
    """(x, y, on screen) of world points ``co`` (N, 3) through a perspective matrix, region pixels."""
    h = np.c_[co, np.ones(len(co))] @ np.asarray(matrix, dtype=np.float64).T
    w = h[:, 3]
    ok = w > 1e-9
    w = np.where(ok, w, 1.0)
    x = (h[:, 0] / w + 1.0) * 0.5 * width
    y = (h[:, 1] / w + 1.0) * 0.5 * height
    return x, y, ok & (x >= 0) & (x < width) & (y >= 0) & (y < height)


def pick(x, y, inside, mouse, radius, limit=LIMIT):
    """Indices of the labels to draw: every vertex in view up to ``limit``, else those within ``radius`` px of the
    pointer (none while the pointer is outside the view). Returns (indices, vertices in view)."""
    idx = np.flatnonzero(inside)
    n = len(idx)
    if n <= limit:
        return idx, n
    if mouse is None:
        return idx[:0], n
    d2 = (x[idx] - mouse[0]) ** 2 + (y[idx] - mouse[1]) ** 2
    near = idx[d2 <= radius * radius]
    return near[:limit], n


def _positions(context, ob):
    me = ob.data
    key = (ob.as_pointer(), me.as_pointer(), len(me.vertices))
    if _cache["key"] == key and _cache["co"] is not None:
        return _cache["co"]
    ev = ob.evaluated_get(context.evaluated_depsgraph_get())
    try:
        em = ev.data
        n = len(em.vertices)
        src = em if n == len(me.vertices) else me          # a subdivided preview can't be matched: rest points
    except (AttributeError, RuntimeError):
        src, n = me, len(me.vertices)
    co = np.empty(len(src.vertices) * 3)
    src.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    mw = np.array(ob.matrix_world)
    co = co @ mw[:3, :3].T + mw[:3, 3]
    _cache.update(key=key, co=co, weights={})
    return co


def _weights(ob, vg, indices):
    cache = _cache["weights"].setdefault(vg.index, {})
    out = np.empty(len(indices))
    for k, i in enumerate(indices.tolist()):
        w = cache.get(i)
        if w is None:
            try:
                w = vg.weight(i)
            except RuntimeError:          # not in the group = weight 0
                w = 0.0
            cache[i] = w
        out[k] = w
    return out


def _brush_radius(context):
    from .. import compat
    ts = context.tool_settings
    brush = ts.weight_paint.brush
    ups = compat.unified_paint_settings(ts)
    owner = ups if (ups.use_unified_size or brush is None) else brush
    return float(getattr(owner, "size", 50))


def draw():
    context = bpy.context
    if context.mode != 'PAINT_WEIGHT':
        return
    ob = context.active_object
    if ob is None or ob.type != 'MESH' or ob.vertex_groups.active is None:
        return
    s = settings(context)
    if not s.show_numbers:
        STATS.update(drawn=0, in_view=0, capped=False)
        return
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return
    from . import toolbox
    if toolbox.is_toolbox(context.space_data):
        return
    t0 = time.perf_counter()
    refreshed = _cache["key"] is None
    if _cache["dirty"] and not _stroke_running(context):
        _cache.update(key=None, dirty=False)
        refreshed = True
    co = _positions(context, ob)
    x, y, inside = project(co, rv3d.perspective_matrix, region.width, region.height)
    mouse = STATS["mouse"]
    if mouse is not None:
        mouse = (mouse[0] - region.x, mouse[1] - region.y)
        if not (0 <= mouse[0] < region.width and 0 <= mouse[1] < region.height):
            mouse = None
    idx, n = pick(x, y, inside, mouse, 2.0 * _brush_radius(context))
    weights = _weights(ob, ob.vertex_groups.active, idx)
    scale = context.preferences.system.ui_scale
    blf.size(FONT, 11.0 * scale)
    places = s.number_places
    tw, th = blf.dimensions(FONT, format_weight(0.0, places))
    hw, hh = tw * 0.5, th * 0.5
    low, high = tuple(s.number_min_color), tuple(s.number_max_color)
    if not s.number_color_ramp:
        r, g, b = s.number_color
        blf.color(FONT, r, g, b, 1.0)
    for k, i in enumerate(idx.tolist()):
        w = float(weights[k])
        if s.number_color_ramp:
            r, g, b = ramp_color(w, low, high)
            blf.color(FONT, r, g, b, 1.0)
        blf.position(FONT, x[i] - hw, y[i] - hh, 0)
        blf.draw(FONT, format_weight(w, places))
    ms = (time.perf_counter() - t0) * 1000.0
    STATS.update(drawn=len(idx), in_view=n, capped=n > LIMIT, ms=ms, refreshed=refreshed)
    STATS["history"] = (STATS["history"] + [(ms, refreshed)])[-30:]


def help_note():
    """Help Line text while the labels are capped."""
    if STATS["capped"]:
        return f"{STATS['in_view']} vertices in view — zoom in to see all weights (numbers shown around the brush)"
    return ""


class ALLSET_OT_weight_numbers_hover(bpy.types.Operator):
    """Remembers the pointer for the brush-local labels (first MOUSEMOVE item of "Weight Paint", passes through)"""
    bl_idname = "allset.weight_numbers_hover"
    bl_label = "Weight Numbers Hover"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        STATS["mouse"] = (event.mouse_x, event.mouse_y)
        if STATS["capped"] and context.area is not None:
            context.area.tag_redraw()
        return {'PASS_THROUGH'}


@bpy.app.handlers.persistent
def _on_depsgraph(scene, depsgraph):
    for u in depsgraph.updates:
        if isinstance(u.id, (bpy.types.Object, bpy.types.Mesh)) and (u.is_updated_geometry or u.is_updated_transform):
            _cache["dirty"] = True
            return


def register():
    bpy.utils.register_class(ALLSET_OT_weight_numbers_hover)
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL'))
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    while _handles:
        bpy.types.SpaceView3D.draw_handler_remove(_handles.pop(), 'WINDOW')
    _cache.update(key=None, co=None, weights={}, dirty=False)
    bpy.utils.unregister_class(ALLSET_OT_weight_numbers_hover)
