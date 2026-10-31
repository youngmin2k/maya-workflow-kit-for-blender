# SPDX-License-Identifier: GPL-3.0-or-later
"""UV shell pre-selection in the UV Editor, like Maya's pre-selection highlight.

While UV shells are picked whole (the kit's UV Shell selection mask, or Blender's island selection with UV Sync
off) the shell under the mouse is filled in the pre-selection red before the click, so you see which shell a click
will take. A "UV Editor" MOUSEMOVE item (``allset.uv_shell_hover``, always PASS_THROUGH) remembers the mouse per
editor; an Image Editor WINDOW POST_PIXEL handler draws the shell. Shell labels and triangles are cached per object
and dropped on every mesh / object depsgraph update. Add-on preference ``uv_shell_preview`` turns it off.
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
        if xy is None or not enabled(context) or not shell_mode(context):
            return
        if uv_arrays.editing_now(context.window_manager):
            return
        u, v = region.view2d.region_to_view(*xy)
        found = shell_under(context, u, v)
        if found is None:
            return
        tris, edges = shell_triangles(*found)
        if not len(tris):
            return
        v2d = region.view2d
        p0 = np.array(v2d.view_to_region(0.0, 0.0, clip=False), np.float32)
        p1 = np.array(v2d.view_to_region(1.0, 1.0, clip=False), np.float32)
        if p0[0] == p1[0] or p0[1] == p1[1]:
            return
        tri_px = (tris.reshape(-1, 2) * (p1 - p0) + p0).tolist()
        edge_px = (edges.reshape(-1, 2) * (p1 - p0) + p0).tolist()
        gpu.state.blend_set('ALPHA')
        flat = gpu.shader.from_builtin('UNIFORM_COLOR')
        flat.uniform_float("color", FILL)
        batch_for_shader(flat, 'TRIS', {"pos": tri_px}).draw(flat)
        line = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        line.uniform_float("viewportSize", (region.width, region.height))
        line.uniform_float("lineWidth", EDGE_PX * (context.preferences.system.ui_scale or 1.0))
        line.uniform_float("color", EDGE)
        batch_for_shader(line, 'LINES', {"pos": edge_px}).draw(line)
        gpu.state.blend_set('NONE')
    except (ReferenceError, AttributeError, ValueError, IndexError):
        _cache.clear()


class ALLSET_OT_uv_shell_hover(bpy.types.Operator):
    """UV Editor: remember the mouse for the UV shell pre-selection highlight"""
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
        if (inside or before is not None) and enabled(context) and shell_mode(context):
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
