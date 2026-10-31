# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya buffer curves: Curves > Buffer Curve Snapshot /
Swap Buffer Curve and View > Show Buffer Curves.

Maya: Snapshot stores the selected curves; Swap exchanges a curve and its buffer —
times and values both come back (a key moved 5 → 6 then swapped is at 5 again), swapping twice restores the edit.

Storage: ``Action["allset_buffers"]["<data_path>|<array_index>"]`` = flat lists per key — "co" (x, y), "hl" / "hr"
(handle positions), "ipo" / "hlt" / "hrt" / "ease" (the enum values as ``foreach_get`` returns them). ID properties
are undoable and saved with the file. The Action is the F-curve's ``id_data`` (4.5 and 5.x layered actions).

Show Buffer Curves (add-on pref ``graph_show_buffers``, default off like Maya) = a Graph Editor WINDOW POST_VIEW
handler (view space = frame, displayed value) drawing each visible curve's buffer as a grey polyline: the stored
Bezier segments sampled by the kit (CONSTANT / LINEAR honoured, Blender's easing types drawn as straight lines),
Blender's handle correction applied like its evaluation (``_correct``), rotations in degrees when the scene shows degrees, constant
extrapolation to the view edges. Normalized views (``use_normalization``) draw nothing (the normalization
factor per curve isn't exposed to Python), NLA time mapping is ignored. The grey is not Maya's exact colour.
"""

import math

import bpy

from .. import results
from . import graph_weights

PROP = "allset_buffers"
COLOR = (0.55, 0.55, 0.55, 1.0)
STEPS = 16
FIELDS = (("co", "co", 2, float), ("hl", "handle_left", 2, float), ("hr", "handle_right", 2, float),
          ("ipo", "interpolation", 1, int), ("hlt", "handle_left_type", 1, int),
          ("hrt", "handle_right_type", 1, int), ("ease", "easing", 1, int))

_handles = []


def curve_key(fc):
    return graph_weights.curve_key(fc)


def _store(fc):
    """The curve's buffer data block (an ID property group) or None."""
    ob = graph_weights.owner(fc)
    if ob is None or PROP not in ob:
        return None
    return ob[PROP].get(curve_key(fc))


def has_buffer(fc):
    return _store(fc) is not None


def read_keys(fc):
    """{field: flat list} of the curve's keys."""
    pts = fc.keyframe_points
    n = len(pts)
    out = {}
    for name, attr, width, kind in FIELDS:
        values = [kind(0)] * (n * width)
        pts.foreach_get(attr, values)
        out[name] = values
    return out


def write_keys(fc, rec):
    """Replace the curve's keys with ``rec`` (selection kept by key index)."""
    pts = fc.keyframe_points
    selected = [kp.select_control_point for kp in pts]
    n = len(rec["co"]) // 2
    pts.clear()
    if n:
        pts.add(n)
        for name, attr, _width, _kind in FIELDS:
            if name in ("co", "hl", "hr"):
                continue
            pts.foreach_set(attr, [int(v) for v in rec[name]])
        for name, attr, _width, _kind in FIELDS:
            if name in ("co", "hl", "hr"):
                pts.foreach_set(attr, [float(v) for v in rec[name]])
        for i, kp in enumerate(pts):
            kp.select_control_point = selected[i] if i < len(selected) else False
            kp.select_left_handle = kp.select_right_handle = False
    fc.update()


def snapshot(fc):
    ob = graph_weights.owner(fc)
    if ob is None:
        return False
    if PROP not in ob:
        ob[PROP] = {}
    ob[PROP][curve_key(fc)] = read_keys(fc)
    return True


def buffer_keys(fc):
    """{field: list} of the stored buffer, or None."""
    data = _store(fc)
    if data is None:
        return None
    return {name: list(data.get(name, ())) for name, _a, _w, _k in FIELDS}


def swap(fc):
    """Exchange the curve's keys and its buffer. False when the curve has no buffer."""
    old = buffer_keys(fc)
    if old is None:
        return False
    now = read_keys(fc)
    write_keys(fc, old)
    graph_weights.owner(fc)[PROP][curve_key(fc)] = now
    return True


# --- sampling -----------------------------------------------------------------------------------------------

def _correct(p0, p1, p2, p3):
    """Blender 4.5's handle correction before evaluating a Bezier segment: a handle reaching past the segment's
    other key is shortened (direction kept) to end at that key's frame (``fc.evaluate`` follows
    this, not the older shorten-both-together rule)."""
    span = p3[0] - p0[0]
    h1 = (p1[0] - p0[0], p1[1] - p0[1])
    h2 = (p2[0] - p3[0], p2[1] - p3[1])
    if abs(h1[0]) > span > 0.0:
        f = span / abs(h1[0])
        p1 = (p0[0] + f * h1[0], p0[1] + f * h1[1])
    if abs(h2[0]) > span > 0.0:
        f = span / abs(h2[0])
        p2 = (p3[0] + f * h2[0], p3[1] + f * h2[1])
    return p1, p2


def _bezier(p0, p1, p2, p3, s):
    u = 1.0 - s
    a, b, c, d = u * u * u, 3 * u * u * s, 3 * u * s * s, s * s * s
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def sample(rec, steps=STEPS):
    """Polyline points (frame, value) of a buffer record: Bezier segments sampled ``steps`` times, CONSTANT a
    step, everything else a straight line between the keys."""
    co = rec["co"]
    n = len(co) // 2
    if n == 0:
        return []
    bezier = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["BEZIER"].value
    constant = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["CONSTANT"].value
    pts = [(co[0], co[1])]
    for i in range(n - 1):
        p0, p3 = (co[2 * i], co[2 * i + 1]), (co[2 * i + 2], co[2 * i + 3])
        ipo = int(rec["ipo"][i])
        if ipo == constant:
            pts += [(p3[0], p0[1]), p3]
        elif ipo == bezier:
            p1 = (rec["hr"][2 * i], rec["hr"][2 * i + 1])
            p2 = (rec["hl"][2 * i + 2], rec["hl"][2 * i + 3])
            p1, p2 = _correct(p0, p1, p2, p3)
            pts += [_bezier(p0, p1, p2, p3, k / steps) for k in range(1, steps + 1)]
        else:
            pts.append(p3)
    return pts


# --- drawing ------------------------------------------------------------------------------------------------

def _value_factor(context, owner_id, fc):
    """Graph Editor display factor of the curve's values: degrees for rotations when the scene shows degrees
    (C ``ANIM_unit_mapping_get_factor``)."""
    if owner_id is None or context.scene.unit_settings.system_rotation != 'DEGREES':
        return 1.0
    path = fc.data_path
    base, _dot, name = path.rpartition(".")
    try:
        holder = owner_id.path_resolve(base) if base else owner_id
        prop = holder.bl_rna.properties.get(name.split("[")[0])
    except (ValueError, AttributeError):
        return 1.0
    return 180.0 / math.pi if prop is not None and prop.unit == 'ROTATION' else 1.0


def buffer_lines(context):
    """[(points in view space)] of every visible curve's buffer."""
    curves = list(getattr(context, "visible_fcurves", None) or ())
    if not curves:
        return []
    users = {}
    for ob in context.scene.objects:
        ad = ob.animation_data
        if ad is not None and ad.action is not None:
            users.setdefault(ad.action.as_pointer(), ob)
    region = context.region
    lo = hi = None
    if region is not None:
        lo = region.view2d.region_to_view(0, 0)[0]
        hi = region.view2d.region_to_view(region.width, 0)[0]
    lines = []
    for fc in curves:
        rec = buffer_keys(fc)
        if not rec or not rec["co"]:
            continue
        action = graph_weights.owner(fc)
        f = _value_factor(context, users.get(action.as_pointer()) if action else None, fc)
        pts = [(x, y * f) for x, y in sample(rec)]
        if lo is not None:
            if lo < pts[0][0]:
                pts.insert(0, (lo, pts[0][1]))
            if hi > pts[-1][0]:
                pts.append((hi, pts[-1][1]))
        lines.append(pts)
    return lines


def _shown(context):
    from .. import preferences
    try:
        return bool(preferences.get(context).graph_show_buffers)
    except (KeyError, AttributeError):
        return False


def draw_buffers():
    """The POST_VIEW handler. Draws nothing in background (no GPU) or when Show Buffer Curves is off."""
    context = bpy.context
    space = context.space_data
    if bpy.app.background or space is None or space.type != 'GRAPH_EDITOR' or not _shown(context):
        return
    if getattr(space, "use_normalization", False):
        return
    lines = buffer_lines(context)
    if not lines:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.uniform_float("color", COLOR)
    for pts in lines:
        coords = [(x, y) for x, y in pts]
        batch_for_shader(shader, 'LINE_STRIP', {"pos": coords}).draw(shader)


# --- operators ----------------------------------------------------------------------------------------------

class ALLSET_OT_buffer_snapshot(bpy.types.Operator):
    """Store a copy of the selected curves to swap back to later (Maya Curves > Buffer Curve Snapshot)"""
    bl_idname = "allset.buffer_snapshot"
    bl_label = "Buffer Curve Snapshot"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        curves = [fc for fc in graph_weights.target_curves(context) if snapshot(fc)]
        if not curves:
            self.report({'WARNING'}, "No animation curves to snapshot")
            return {'CANCELLED'}
        for area in context.screen.areas if context.screen else ():
            if area.type == 'GRAPH_EDITOR':
                area.tag_redraw()
        results.result(self, f"Buffer of {len(curves)} curve{'s' if len(curves) != 1 else ''} stored")
        return {'FINISHED'}


class ALLSET_OT_buffer_swap(bpy.types.Operator):
    """Exchange the selected curves with their buffer curves (Maya Curves > Swap Buffer Curve)"""
    bl_idname = "allset.buffer_swap"
    bl_label = "Swap Buffer Curve"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        curves = [fc for fc in graph_weights.target_curves(context) if swap(fc)]
        if not curves:
            self.report({'WARNING'}, "No buffer curve to swap: take a Buffer Curve Snapshot first")
            return {'CANCELLED'}
        for area in context.screen.areas if context.screen else ():
            if area.type in {'GRAPH_EDITOR', 'VIEW_3D', 'DOPESHEET_EDITOR'}:
                area.tag_redraw()
        results.result(self, f"{len(curves)} curve{'s' if len(curves) != 1 else ''} swapped with the buffer")
        return {'FINISHED'}


classes = (ALLSET_OT_buffer_snapshot, ALLSET_OT_buffer_swap)


def register_handlers():
    if not _handles:
        _handles.append(bpy.types.SpaceGraphEditor.draw_handler_add(draw_buffers, (), 'WINDOW', 'POST_VIEW'))


def unregister_handlers():
    while _handles:
        bpy.types.SpaceGraphEditor.draw_handler_remove(_handles.pop(), 'WINDOW')
