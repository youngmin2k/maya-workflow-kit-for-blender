# SPDX-License-Identifier: GPL-3.0-or-later
"""Set Key on components: S with points selected keys their positions, like Maya.

Maya keys the shape's point channels of the selected components (a mesh vertex's X / Y / Z tweak, a curve /
surface / lattice CV's X / Y / Z); edges and faces key the vertices they use. Blender keeps these on the object
data:

* mesh vertex  -> ``vertices[i].co`` (X / Y / Z) on the Mesh,
* NURBS / poly CV -> ``splines[s].points[p].co`` indices 0 / 1 / 2 (not the weight),
* Bezier point -> ``splines[s].bezier_points[p].co`` plus both handles (a selected handle alone keys that handle),
* lattice point -> ``points[i].co_deform``.

Curves and lattices edit their data in place, so their keys play in edit mode too. A mesh in edit mode works on a
separate edit copy: before keying it is written back to the mesh (``update_from_editmode``), and on a frame change
the keyed vertices of edit-mode meshes take their animated positions (``frame_change_post``), so the points move
with time in component mode like Maya.
"""

import re

import bmesh
import bpy
from bpy.app.handlers import persistent

COMPONENT_MODES = {'EDIT_MESH', 'EDIT_CURVE', 'EDIT_SURFACE', 'EDIT_LATTICE'}
TYPES = {'MESH', 'CURVE', 'SURFACE', 'LATTICE'}
_VERT_PATH = re.compile(r"^vertices\[(\d+)\]\.co$")


def applies(context):
    """S keys points: the lead is a mesh / curve / surface / lattice in edit mode (Maya component mode)."""
    return context.mode in COMPONENT_MODES


def component_objects(context):
    """Every object in the current edit mode that has keyable points."""
    obs = list(getattr(context, "objects_in_mode", None) or [])
    if not obs:
        ob = context.active_object
        obs = [ob] if ob is not None and ob.mode == 'EDIT' else []
    return [ob for ob in obs if ob.type in TYPES]


def point_paths(ob):
    """[(data path, array index)] of ``ob``'s selected points (index -1 = every component)."""
    data = ob.data
    out = []
    if ob.type == 'MESH':
        bm = bmesh.from_edit_mesh(data) if ob.mode == 'EDIT' else None
        if bm is not None:
            sel = [v.index for v in bm.verts if v.select]
        else:
            sel = [v.index for v in data.vertices if v.select]
        out = [(f"vertices[{i}].co", -1) for i in sel]
    elif ob.type in {'CURVE', 'SURFACE'}:
        for s, spline in enumerate(data.splines):
            for p, pt in enumerate(spline.points):
                if pt.select:
                    out += [(f"splines[{s}].points[{p}].co", i) for i in range(3)]
            for p, bp in enumerate(spline.bezier_points):
                base = f"splines[{s}].bezier_points[{p}]."
                if bp.select_control_point:
                    out += [(base + n, -1) for n in ("co", "handle_left", "handle_right")]
                    continue
                if bp.select_left_handle:
                    out.append((base + "handle_left", -1))
                if bp.select_right_handle:
                    out.append((base + "handle_right", -1))
    elif ob.type == 'LATTICE':
        out = [(f"points[{i}].co_deform", -1) for i, p in enumerate(data.points) if p.select]
    return out


def selected_point_curves(ob):
    """F-curves of ``ob``'s selected points (edit mode): the keys the Time Slider shows for selected components."""
    if ob is None or ob.type not in TYPES or ob.mode != 'EDIT':
        return []
    from .. import compat
    paths = point_paths(ob)
    if not paths:
        return []
    want = {(p, i) for p, i in paths}
    whole = {p for p, i in paths if i < 0}
    return [fc for fc in compat.id_fcurves(ob.data)
            if fc.data_path in whole or (fc.data_path, fc.array_index) in want]


def key_points(context, keytype='KEYFRAME'):
    """Key the selected points of every component-mode object at the current frame. Count of curves keyed."""
    from . import graph_key_menu
    frame = context.scene.frame_current
    count = 0
    for ob in component_objects(context):
        paths = point_paths(ob)
        if not paths:
            continue
        if ob.type == 'MESH':
            ob.update_from_editmode()       # the edit copy -> the mesh, so the keys read the shown positions
        data = ob.data
        for path, index in paths:
            try:
                ok = data.keyframe_insert(path, index=index, frame=frame, keytype=keytype)
            except (TypeError, RuntimeError):
                ok = False
            if ok:
                graph_key_menu.after_insert(data, path, index, frame)
                count += 3 if index < 0 else 1
    return count


# --- edit-mode meshes follow their vertex keys on a frame change ------------------------------------------------

def _vertex_curves(me):
    from .. import compat
    out = {}
    for fc in compat.id_fcurves(me):
        m = _VERT_PATH.match(fc.data_path)
        if m and not fc.mute and 0 <= fc.array_index < 3:
            out.setdefault(int(m.group(1)), []).append(fc)
    return out


def apply_frame(scene):
    """Edit-mode meshes: the keyed vertices take their positions at the current frame. Count of vertices moved."""
    frame = scene.frame_current_final
    moved = 0
    seen = set()
    for ob in scene.objects:
        if ob.type != 'MESH' or ob.mode != 'EDIT' or ob.data in seen:
            continue
        me = ob.data
        seen.add(me)
        ad = me.animation_data
        if ad is None or ad.action is None:
            continue
        curves = _vertex_curves(me)
        if not curves:
            continue
        try:
            bm = bmesh.from_edit_mesh(me)
        except (ValueError, RuntimeError, ReferenceError):
            continue
        bm.verts.ensure_lookup_table()
        n = len(bm.verts)
        for i, fcs in curves.items():
            if i >= n:
                continue
            co = bm.verts[i].co
            for fc in fcs:
                co[fc.array_index] = fc.evaluate(frame)
            moved += 1
        if moved:
            bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
    return moved


@persistent
def _on_frame(scene, _depsgraph=None):
    from . import anim_snapshot
    if getattr(anim_snapshot, "_busy", False):
        return
    try:
        apply_frame(scene)
    except ReferenceError:
        pass


def register_handlers():
    if _on_frame not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(_on_frame)


def unregister_handlers():
    if _on_frame in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_on_frame)
