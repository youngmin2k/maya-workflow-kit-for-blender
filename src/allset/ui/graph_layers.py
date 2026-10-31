# SPDX-License-Identifier: GPL-3.0-or-later
"""Graph Editor with several selected animation layers.

Maya: the Graph Editor lists each selected layer under
the object and draws every selected layer's curves in their own values. Blender's Graph Editor draws and edits one
action per object: the last picked layer stays the active action (operators/anim_layers.show, editable); the other
selected layers' curves are drawn here (Graph Editor WINDOW POST_VIEW, Maya channel colours dimmed, read only) and
listed as rows in the kit outliner (ui/editor_chrome.py rows); picking such a row or a drawn curve makes that layer
the last picked one, so its curves become Blender's editable ones.

Drawing follows Blender's Graph Editor mapping (ANIM_unit_mapping_get_factor): rotation curves in degrees while the
scene's rotation unit is degrees, and View > Normalize maps a curve's key range onto -1..1 (keys and handles
like Blender's normalization_factor_get, without its cache).
"""

import math

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

KINDS = ("LAYER", "LAYER_ATTR")     # kit outliner rows: a selected layer's name, its curves
DIM = 0.6                           # other selected layers: Maya colours, dimmer
PICK_PX = 8                         # curve pick distance in region pixels
_ROTATIONS = ("rotation_euler", "delta_rotation_euler", "rotation_axis_angle")


def _al():
    from ..operators import anim_layers
    return anim_layers


# --- model -------------------------------------------------------------------------------------------------------

def extra_layers(scene, ob):
    """Selected layers of ``ob`` other than the one Blender shows (its active action), stack order top first."""
    al = _al()
    sel = al.selected_layers(scene)
    if len(sel) < 2:
        return []
    have = al.tracks(ob)
    shown = al.display_layer(scene, ob)
    return [e.name for e in reversed(sel) if e.name in have and e.name != shown]


def extra_curves(scene, ob):
    """[(layer name, F-curve)] the kit draws for ``ob``."""
    al = _al()
    return [(name, fc) for name in extra_layers(scene, ob) for fc in al.layer_curves(ob, name)]


def outliner_rows(scene, ob):
    """Kit outliner rows under an object: per other selected layer a LAYER row (node = the object, third item = the
    layer's action) and a LAYER_ATTR row per curve (third item = the F-curve)."""
    from .editor_chrome import maya_order
    al = _al()
    out = []
    for name in extra_layers(scene, ob):
        act = al._strip(al.tracks(ob)[name]).action
        out.append(("LAYER", ob, act))
        out += [("LAYER_ATTR", ob, fc) for fc in maya_order(al.layer_curves(ob, name))]
    return out


def layer_of_row(row):
    kind, _ob, item = row
    act = item if kind == "LAYER" else getattr(item, "id_data", None)
    return act.get(_al().MARK) if act is not None else None


def row_id(row):
    kind, ob, item = row
    if kind == "LAYER":
        return (ob.name, "LAYER", layer_of_row(row))
    return (ob.name, "LAYER_ATTR", layer_of_row(row), item.data_path, item.array_index)


def activate_row(context, row):
    from ..operators import anim_layers_204
    name = layer_of_row(row)
    ok = name is not None and anim_layers_204.activate(context.scene, name)
    anim_layers_204.redraw(context)
    return ok


# --- curve lines -------------------------------------------------------------------------------------------------

def value_factor(scene, fc):
    """Blender's Graph Editor unit factor: rotations in degrees unless the scene's rotation unit is radians."""
    tail = fc.data_path.rsplit(".", 1)[-1]
    if tail in _ROTATIONS and not (tail == "rotation_axis_angle" and fc.array_index == 0) \
            and scene.unit_settings.system_rotation == 'DEGREES':
        return 180.0 / math.pi
    return 1.0


def normalization(fc):
    """(offset, factor) of View > Normalize: value' = (value + offset) * factor (keys and handles span -1..1)."""
    ys = []
    for kp in fc.keyframe_points:
        ys.append(kp.co.y)
        if kp.interpolation == 'BEZIER':
            ys += [kp.handle_left.y, kp.handle_right.y]
    if not ys:
        return 0.0, 1.0
    lo, hi = min(ys), max(ys)
    rng = hi - lo
    if rng <= 1.192e-7:
        return -lo, 1.0
    return -lo - rng / 2.0, 2.0 / rng


def polyline(fc, x0, x1, n, factor=1.0, offset=0.0):
    """``n`` + 1 points of the curve between frames ``x0`` and ``x1`` in Graph Editor view space."""
    n = max(1, int(n))
    step = (x1 - x0) / n
    return [(x0 + i * step, (fc.evaluate(x0 + i * step) + offset) * factor) for i in range(n + 1)]


def dim(rgba):
    r, g, b, _a = rgba
    return (r * DIM, g * DIM, b * DIM, 0.9)


def lines(scene, obs, x0, x1, n, normalize=False):
    """[(rgba, object, layer, points)] of every other selected layer's curves of ``obs``, in stack order bottom first
    (drawn in that order: an upper layer's curve lies over a lower one's)."""
    from .editor_chrome import attr_color
    out = []
    for ob in obs:
        al = _al()
        for name, fc in [(n_, f) for n_ in reversed(extra_layers(scene, ob)) for f in al.layer_curves(ob, n_)]:
            if not len(fc.keyframe_points):
                continue
            off, k = normalization(fc) if normalize else (0.0, value_factor(scene, fc))
            out.append((dim(attr_color(fc)), ob, name, polyline(fc, x0, x1, n, k, off)))
    return out


def _objects(context, space):
    from . import editor_chrome
    try:
        return editor_chrome.listed_objects(context, space)
    except (AttributeError, ReferenceError, TypeError):
        return [ob for ob in context.scene.objects if _al().has_layers(ob)]


def view_lines(context, region, space):
    v2d = region.view2d
    x0, _y = v2d.region_to_view(0, 0)
    x1, _y = v2d.region_to_view(region.width, 0)
    n = min(2000, max(16, region.width // 2))
    return lines(context.scene, _objects(context, space), x0, x1, n, bool(getattr(space, "use_normalization", False)))


def _shows(context):
    from . import editor_chrome
    space = context.space_data
    if not editor_chrome.is_graph(space) or not editor_chrome.enabled(context):
        return False
    return len(getattr(context.scene, "allset_anim_layers", ())) > 1 and len(_al().selected_layers(context.scene)) > 1


def draw():
    context = bpy.context
    region = context.region
    if region is None or region.type != 'WINDOW':
        return
    try:
        if not _shows(context):
            return
        items = view_lines(context, region, context.space_data)
    except (AttributeError, ReferenceError):
        return
    if not items:
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(1.5)
    for rgba, _ob, _name, pts in items:
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": pts})
        shader.uniform_float("color", rgba)
        batch.draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    t = 0.0 if d2 <= 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / d2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def hit(items, to_region, mx, my, limit=PICK_PX):
    """(object, layer) of the drawn curve nearest the mouse within ``limit`` px, else None. ``to_region`` maps a view
    point to region pixels."""
    best = None
    for _rgba, ob, name, pts in items:
        prev = None
        for p in pts:
            q = to_region(*p)
            if prev is not None:
                d = _seg_dist(mx, my, prev[0], prev[1], q[0], q[1])
                if d <= limit and (best is None or d < best[0]):
                    best = (d, ob, name)
            prev = q
    return None if best is None else (best[1], best[2])


class ALLSET_OT_graph_layer_pick(bpy.types.Operator):
    """Click a curve of another selected animation layer: that layer becomes the last picked one (its curves become
    editable)"""
    bl_idname = "allset.graph_layer_pick"
    bl_label = "Pick Layer Curve"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        region = context.region
        return region is not None and region.type == 'WINDOW' and context.space_data is not None \
            and context.space_data.type == 'GRAPH_EDITOR'

    def invoke(self, context, event):
        try:
            if not _shows(context):
                return {'PASS_THROUGH'}
            region = context.region
            v2d = region.view2d
            got = hit(view_lines(context, region, context.space_data),
                      lambda x, y: v2d.view_to_region(x, y, clip=False), event.mouse_region_x, event.mouse_region_y)
        except (AttributeError, ReferenceError):
            return {'PASS_THROUGH'}
        if got is None:
            return {'PASS_THROUGH'}
        from ..operators import anim_layers_204
        anim_layers_204.activate(context.scene, got[1])
        anim_layers_204.redraw(context)
        return {'FINISHED'}


# --- outliner rows (drawn by editor_chrome.draw_channels) -----------------------------------------------------------

def draw_row(row, y, h, s, font, width):
    import blf
    from .editor_chrome import TEXT, attr_color, attr_label
    kind, _ob, item = row
    if kind == "LAYER":
        blf.color(font, *TEXT)
        blf.position(font, 22 * s, y - h + 6 * s, 0)
        blf.draw(font, layer_of_row(row) or "")
    else:
        blf.color(font, *dim(attr_color(item)))
        blf.position(font, 44 * s, y - h + 6 * s, 0)
        blf.draw(font, attr_label(item))


_handle = []


def register():
    bpy.utils.register_class(ALLSET_OT_graph_layer_pick)
    _handle.append(bpy.types.SpaceGraphEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_VIEW'))


def unregister():
    while _handle:
        bpy.types.SpaceGraphEditor.draw_handler_remove(_handle.pop(), 'WINDOW')
    bpy.utils.unregister_class(ALLSET_OT_graph_layer_pick)
