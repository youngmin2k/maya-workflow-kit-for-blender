# SPDX-License-Identifier: GPL-3.0-or-later
"""UV pre-selection in the UV Editor, like Maya's pre-selection highlight.

While UV shells are picked whole (the kit's UV Shell selection mask, or Blender's island selection with UV Sync
off) the shell under the mouse is filled in the pre-selection red before the click, so you see which shell a click
will take. A "UV Editor" MOUSEMOVE item (``allset.uv_shell_hover``, always PASS_THROUGH) remembers the mouse per
editor; an Image Editor WINDOW POST_PIXEL handler draws the shell. Shell labels and triangles are cached per object
and dropped on every mesh / object depsgraph update. Add-on preference ``uv_shell_preview`` turns it off.

Single components get the same highlight: with UVs / UV edges / UV faces picked (UV Sync off: the UV select mode;
UV Sync on: the mesh select mode) the UV, edge or face a click would take is drawn in the pre-selection red: the
nearest UV or edge within ``PICK_PX`` pixels, the face under the mouse.
"""

import bmesh
import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from .. import compat
from ..operators import uv_arrays, uv_shell_select

FILL = (0.85, 0.26, 0.25, 0.35)       # pre-selection red, as a translucent fill (3D View face pre-selection)
EDGE = (1.0, 0.0, 0.0, 1.0)
EDGE_PX = 1.5
POINT_PX = 7.0                        # a pre-selected UV (UI scale 1.0)
EDGE_HOVER_PX = 2.5                   # a pre-selected UV edge
PICK_PX = 20.0                        # how near a UV / edge must be to the mouse (UI scale 1.0)

_mouse = {}          # image editor area pointer -> region (x, y), or None when the mouse left
_cache = {}          # object pointer -> (labels, arrays)
_handle = []


def enabled(context):
    from .. import preferences
    try:
        prefs = preferences.get(context)
    except AttributeError:
        return False
    return bool(prefs.maya_mode and prefs.uv_shell_preview)


def shell_mode(context):
    """Clicks in the UV Editor pick whole shells."""
    if context.mode != 'EDIT_MESH':
        return False
    ts = context.scene.tool_settings
    if uv_shell_select.active(context):
        return True
    return compat.uv_island_mode(ts) and not ts.use_uv_select_sync


def component_mode(context):
    """'VERTEX' / 'EDGE' / 'FACE': what a UV Editor click picks when it does not pick whole shells, else None."""
    if context.mode != 'EDIT_MESH' or shell_mode(context):
        return None
    ts = context.scene.tool_settings
    if ts.use_uv_select_sync:
        vert, edge, face = ts.mesh_select_mode
        return 'VERTEX' if vert else 'EDGE' if edge else 'FACE' if face else None
    return ts.uv_select_mode if ts.uv_select_mode in ('VERTEX', 'EDGE', 'FACE') else None


def nearest_point(points, xy, limit):
    """Index of the row of ``points`` (n, 2) nearest to ``xy`` within ``limit``, else None."""
    if not len(points):
        return None
    d = np.hypot(points[:, 0] - xy[0], points[:, 1] - xy[1])
    i = int(np.argmin(d))
    return i if d[i] <= limit else None


def segment_distances(p, q, xy):
    """Distance from ``xy`` to each segment p[i]-q[i] ((n, 2) each)."""
    m = np.asarray(xy, np.float64)
    d = q - p
    ll = (d * d).sum(axis=1)
    with np.errstate(divide='ignore', invalid='ignore'):
        t = np.where(ll > 0, ((m - p) * d).sum(axis=1) / np.where(ll > 0, ll, 1.0), 0.0)
    t = np.clip(t, 0.0, 1.0)
    c = p + d * t[:, None]
    return np.hypot(c[:, 0] - m[0], c[:, 1] - m[1])


def nearest_segment(p, q, xy, limit):
    """Index of the segment p[i]-q[i] nearest to ``xy`` within ``limit``, else None."""
    if not len(p):
        return None
    dist = segment_distances(p, q, xy)
    i = int(np.argmin(dist))
    return i if dist[i] <= limit else None


def component_under(context, u, v, scale_uv, limit_px, mode):
    """What a click at UV (u, v) would pre-select: ('VERTEX', uv (1, 2)), ('EDGE', segment (1, 2, 2)) or
    ('FACE', (triangles, outline)), or None. ``scale_uv`` = pixels per UV unit (x, y)."""
    synced = context.scene.tool_settings.use_uv_select_sync
    scale = np.asarray(scale_uv, np.float64)
    m = np.array((u, v), np.float64) * scale
    best = None
    for ob in uv_shell_select.edit_meshes(context):
        _labels, a = _arrays(context, ob)
        if a is None:
            continue
        shown = uv_arrays.shown_faces(a, synced)
        if mode == 'FACE':
            hit = uv_shell_select.uv_faces_at(a, shown, u, v)
            if len(hit):
                return 'FACE', shell_triangles(a, hit[:1])
            continue
        loops = uv_arrays._face_loops(a, np.nonzero(shown)[0])
        if not len(loops):
            continue
        p = a.uv[loops] * scale
        if mode == 'VERTEX':
            i = nearest_point(p, m, limit_px)
            if i is not None:
                d = float(np.hypot(*(p[i] - m)))
                found = ('VERTEX', a.uv[loops[i]][None, :].astype(np.float32))
        else:
            q = a.uv[a.corner_next[loops]] * scale
            i = nearest_segment(p, q, m, limit_px)
            if i is not None:
                d = float(segment_distances(p[i:i + 1], q[i:i + 1], m)[0])
                found = ('EDGE', np.stack([a.uv[loops[i]], a.uv[a.corner_next[loops[i]]]])[None].astype(np.float32))
        if i is not None and (best is None or d < best[0]):
            best = (d, found)
    return best[1] if best else None


def _arrays(context, ob):
    hit = _cache.get(ob.as_pointer())
    if hit is not None:
        return hit
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    if uv is None:
        hit = (None, None)
    else:
        a = uv_arrays.read(ob, bm, uv, context.view_layer.depsgraph)
        hit = (uv_shell_select.shell_labels(a), a)
    _cache[ob.as_pointer()] = hit
    return hit


def shell_under(context, u, v):
    """(arrays, face indices of the shell) under UV point (u, v) among the faces the editor shows, or None."""
    synced = context.scene.tool_settings.use_uv_select_sync
    for ob in uv_shell_select.edit_meshes(context):
        labels, a = _arrays(context, ob)
        if a is None:
            continue
        shown = uv_arrays.shown_faces(a, synced)
        hit = uv_shell_select.uv_faces_at(a, shown, u, v)
        if len(hit) and labels[hit[0]] >= 0:
            faces = np.nonzero((labels == labels[hit[0]]) & shown)[0]
            return a, faces
    return None


def shell_triangles(a, faces):
    """UV triangles (t, 3, 2) fanned from each face's first corner, and the shell's outline segments (s, 2, 2)."""
    loops = uv_arrays._face_loops(a, faces)
    start = a.loop_start[faces]
    total = a.loop_total[faces]
    ntri = np.maximum(total - 2, 0)
    if ntri.sum() == 0:
        return np.zeros((0, 3, 2), np.float32), np.zeros((0, 2, 2), np.float32)
    first = np.repeat(start, ntri)
    offs = np.arange(ntri.sum()) - np.repeat(np.cumsum(ntri) - ntri, ntri) + 1
    tris = np.stack([a.uv[first], a.uv[first + offs], a.uv[first + offs + 1]], axis=1)
    edges = np.stack([a.uv[loops], a.uv[a.corner_next[loops]]], axis=1)
    return tris.astype(np.float32), edges.astype(np.float32)


def _draw():
    context = bpy.context
    space, region, area = context.space_data, context.region, context.area
    try:
        if area is None or space is None or space.mode != 'UV' or not space.uv_editor.show_uv:
            return
        xy = _mouse.get(area.as_pointer())
        if xy is None or not enabled(context):
            return
        shells = shell_mode(context)
        mode = None if shells else component_mode(context)
        if not shells and mode is None:
            return
        if uv_arrays.editing_now(context.window_manager):
            return
        v2d = region.view2d
        p0 = np.array(v2d.view_to_region(0.0, 0.0, clip=False), np.float32)
        p1 = np.array(v2d.view_to_region(1.0, 1.0, clip=False), np.float32)
        if p0[0] == p1[0] or p0[1] == p1[1]:
            return
        u, v = v2d.region_to_view(*xy)
        ui = context.preferences.system.ui_scale or 1.0
        if shells:
            found = shell_under(context, u, v)
            if found is None:
                return
            kind, shape = 'FACE', shell_triangles(*found)
        else:
            found = component_under(context, u, v, tuple((p1 - p0).tolist()), PICK_PX * ui, mode)
            if found is None:
                return
            kind, shape = found
        _paint(region, kind, shape, p0, p1, ui)
    except (ReferenceError, AttributeError, ValueError, IndexError):
        _cache.clear()


def _paint(region, kind, shape, p0, p1, ui):
    def to_px(a):
        return (np.asarray(a, np.float32).reshape(-1, 2) * (p1 - p0) + p0).tolist()
    gpu.state.blend_set('ALPHA')
    flat = gpu.shader.from_builtin('UNIFORM_COLOR')
    line = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    line.uniform_float("viewportSize", (region.width, region.height))
    line.uniform_float("color", EDGE)
    if kind == 'FACE':
        tris, edges = shape
        if len(tris):
            flat.uniform_float("color", FILL)
            batch_for_shader(flat, 'TRIS', {"pos": to_px(tris)}).draw(flat)
            line.uniform_float("lineWidth", EDGE_PX * ui)
            batch_for_shader(line, 'LINES', {"pos": to_px(edges)}).draw(line)
    elif kind == 'EDGE':
        line.uniform_float("lineWidth", EDGE_HOVER_PX * ui)
        batch_for_shader(line, 'LINES', {"pos": to_px(shape)}).draw(line)
    else:
        gpu.state.point_size_set(max(1.0, round(POINT_PX * ui)))
        flat.uniform_float("color", EDGE)
        batch_for_shader(flat, 'POINTS', {"pos": to_px(shape)}).draw(flat)
        gpu.state.point_size_set(1.0)
    gpu.state.blend_set('NONE')


class ALLSET_OT_uv_shell_hover(bpy.types.Operator):
    """UV Editor: remember the mouse for the UV pre-selection highlight"""
    bl_idname = "allset.uv_shell_hover"
    bl_label = "UV Shell Hover"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        area, region = context.area, context.region
        if area is None or area.type != 'IMAGE_EDITOR':
            return {'PASS_THROUGH'}
        key = area.as_pointer()
        inside = region is not None and region.type == 'WINDOW'
        before = _mouse.get(key)
        _mouse[key] = (event.mouse_region_x, event.mouse_region_y) if inside else None
        if ((inside or before is not None) and enabled(context)
                and (shell_mode(context) or component_mode(context) is not None)):
            area.tag_redraw()
        return {'PASS_THROUGH'}


@bpy.app.handlers.persistent
def _invalidate(_scene=None, depsgraph=None):
    if depsgraph is not None and not any(isinstance(u.id, (bpy.types.Mesh, bpy.types.Object))
                                         for u in depsgraph.updates):
        return
    _cache.clear()


classes = (ALLSET_OT_uv_shell_hover,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    _handle.append(bpy.types.SpaceImageEditor.draw_handler_add(_draw, (), 'WINDOW', 'POST_PIXEL'))
    bpy.app.handlers.depsgraph_update_post.append(_invalidate)


def unregister():
    if _invalidate in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_invalidate)
    while _handle:
        bpy.types.SpaceImageEditor.draw_handler_remove(_handle.pop(), 'WINDOW')
    _mouse.clear()
    _cache.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
