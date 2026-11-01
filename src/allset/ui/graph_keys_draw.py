# SPDX-License-Identifier: GPL-3.0-or-later
"""Bigger keys in the Graph Editor.

Blender draws Graph Editor keys at the theme's Vertex Size (6 px at UI scale 1), which is hard to see and hard to
grab next to Maya's keys. The kit can't change the theme, so it draws over each key Blender draws, in the key's own
theme colour (Graph Editor WINDOW POST_PIXEL): an unselected key becomes one bigger dot; a selected key gets a rim
around Blender's own dot, so the active key keeps its colour in the middle. Preference ``graph_key_size`` = the key's diameter in pixels
at UI scale 1; 0 leaves Blender's keys alone.

Which keys: the curves Blender lists as visible (``context.visible_fcurves``) whose keys Blender draws: not locked,
keys usable with the curve's modifiers, and only selected curves when Blender's "Only Show Selected F-Curve
Keyframes" preference is on. Positions follow the Graph Editor mapping: NLA tweak time, rotation curves in degrees,
View > Normalize (``ui/graph_layers.py``).
"""

import math

import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

SEGMENTS = 16              # rim polygon sides
# modifier types whose curve keeps editable keys (generators only when additive)
_USABLE_MODIFIERS = {'CYCLES', 'STEPPED', 'NOISE'}


def key_size(context):
    """Kit key diameter in pixels at UI scale 1, 0 = off."""
    from .. import preferences
    try:
        return int(preferences.get(context).graph_key_size)
    except (KeyError, AttributeError):
        return 0


def keys_usable(fc):
    """Blender draws a curve's keys only while its modifiers leave them editable."""
    for m in fc.modifiers:
        if m.mute or not m.active:
            continue
        if m.type in _USABLE_MODIFIERS:
            continue
        if m.type in ('GENERATOR', 'FNGENERATOR') and getattr(m, "use_additive", False):
            continue
        return False
    return True


def draws_keys(fc, only_selected):
    if fc.hide or fc.lock or (fc.group is not None and fc.group.lock):
        return False
    if only_selected and not fc.select:
        return False
    return len(fc.keyframe_points) > 0 and keys_usable(fc)


def _owners(scene):
    """{action pointer: AnimData} of objects in NLA tweak mode (their keys are drawn at scene time)."""
    out = {}
    for ob in scene.objects:
        ad = ob.animation_data
        if ad is not None and ad.use_tweak_mode and ad.action is not None:
            out[ad.action.as_pointer()] = ad
    return out


def key_points(context, space):
    """(unselected, selected) arrays of key positions in Graph Editor view space (frame, value)."""
    from .graph_layers import normalization, value_factor
    curves = list(getattr(context, "visible_fcurves", None) or ())
    scene = context.scene
    only_selected = bool(getattr(context.preferences.edit, "show_only_selected_curve_keyframes", False))
    normalize = bool(getattr(space, "use_normalization", False))
    tweak = _owners(scene)
    unsel, sel = [], []
    for fc in curves:
        if not draws_keys(fc, only_selected):
            continue
        n = len(fc.keyframe_points)
        co = np.empty(n * 2, dtype=np.float64)
        fc.keyframe_points.foreach_get("co", co)
        co = co.reshape(n, 2)
        flags = np.empty(n, dtype=bool)
        fc.keyframe_points.foreach_get("select_control_point", flags)
        off, k = normalization(fc) if normalize else (0.0, value_factor(scene, fc))
        co[:, 1] = (co[:, 1] + off) * k
        ad = tweak.get(fc.id_data.as_pointer()) if fc.id_data is not None else None
        if ad is not None:
            co[:, 0] = [ad.nla_tweak_strip_time_to_scene(x) for x in co[:, 0]]
        unsel.append(co[~flags])
        sel.append(co[flags])
    empty = np.zeros((0, 2))
    return (np.concatenate(unsel) if unsel else empty), (np.concatenate(sel) if sel else empty)


def to_region(region, pts):
    """View-space points -> region pixels (the view is a linear map of the region)."""
    v2d = region.view2d
    x0, y0 = v2d.region_to_view(0, 0)
    x1, y1 = v2d.region_to_view(region.width, region.height)
    sx = region.width / (x1 - x0) if x1 != x0 else 0.0
    sy = region.height / (y1 - y0) if y1 != y0 else 0.0
    out = np.empty_like(pts)
    out[:, 0] = (pts[:, 0] - x0) * sx
    out[:, 1] = (pts[:, 1] - y0) * sy
    return out


def rims(centres, r_in, r_out, margin=0.0, width=None, height=None):
    """Triangles of a ring (r_in .. r_out) around every centre; centres outside the region (+ r_out) are skipped."""
    if width is not None and len(centres):
        m = r_out + margin
        keep = (centres[:, 0] > -m) & (centres[:, 0] < width + m) & (centres[:, 1] > -m) & (centres[:, 1] < height + m)
        centres = centres[keep]
    if not len(centres):
        return np.zeros((0, 2), dtype=np.float32)
    a = np.linspace(0.0, 2.0 * math.pi, SEGMENTS + 1)
    ca, sa = np.cos(a), np.sin(a)
    inner = np.stack([ca * r_in, sa * r_in], axis=1)          # (S+1, 2)
    outer = np.stack([ca * r_out, sa * r_out], axis=1)
    i0, i1, o0, o1 = inner[:-1], inner[1:], outer[:-1], outer[1:]
    quad = np.stack([i0, o0, o1, i0, o1, i1], axis=1).reshape(-1, 2)     # (S * 6, 2)
    tris = centres[:, None, :] + quad[None, :, :]
    return tris.reshape(-1, 2).astype(np.float32)


def radii(context, size):
    """(inner, outer) rim radius in pixels: inside = a little within Blender's own key, outside = the kit size."""
    scale = context.preferences.system.ui_scale or 1.0      # 0 in background
    theme = context.preferences.themes[0].graph_editor
    blender = theme.vertex_size * scale / 2.0
    return max(0.0, blender - 1.0), size * scale / 2.0


def _rgba(c):
    c = tuple(c)
    return c if len(c) == 4 else c + (1.0,)


def draw():
    context = bpy.context
    region = context.region
    space = context.space_data
    if region is None or region.type != 'WINDOW' or space is None or space.type != 'GRAPH_EDITOR' \
            or space.mode != 'FCURVES':
        return
    size = key_size(context)
    if size <= 0:
        return
    from . import editor_chrome
    if not editor_chrome.enabled(context):
        return
    try:
        r_in, r_out = radii(context, size)
        if r_out <= r_in:
            return
        unsel, sel = key_points(context, space)
    except (AttributeError, ReferenceError, TypeError, ValueError):
        return
    theme = context.preferences.themes[0].graph_editor
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    for pts, colour, inner in ((unsel, theme.vertex, 0.0), (sel, theme.vertex_select, r_in)):
        if not len(pts):
            continue
        tris = rims(to_region(region, pts), inner, r_out, width=region.width, height=region.height)
        if not len(tris):
            continue
        batch = batch_for_shader(shader, 'TRIS', {"pos": tris})
        shader.uniform_float("color", _rgba(colour))
        batch.draw(shader)
    gpu.state.blend_set('NONE')


_handle = []


def register():
    _handle.append(bpy.types.SpaceGraphEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    while _handle:
        bpy.types.SpaceGraphEditor.draw_handler_remove(_handle.pop(), 'WINDOW')
