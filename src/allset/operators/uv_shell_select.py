# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya UV Shell selection in the 3D viewport and the UV Editor (#172).

Maya 2026:
- The mask is one global state (``cmds.selectType(meshUVShell=True)``), turned on by RMB > UV > UV Shell, Select >
  Components > UV Shell and Alt+F12 (`SelectMeshUVShell`): component mode, selection cleared, in-view message. Here: the
  WindowManager flag ``allset_uv_shell_mask`` + face select mode + UV Sync Selection on (one selection for the 3D View
  and the UV Editor, like Maya's one selection list). Any other component mode clears the flag
  (``uv_tools.leave_uv_mode`` / ``set_component``).
- A click selects **faces**: every face of the UV shell of the face under the cursor (3D: the face the pick returns at
  that pixel, so on an edge between two shells one shell wins; UV Editor: the UV face containing the point).
  Plain = replace, Shift = toggle the shell (by the clicked face's state), Ctrl = remove, Ctrl+Shift = add; a
  plain click on nothing clears.
- A box (or lasso) picks every face under it — occluded ones too in the 3D View (camera-based selection off; the kit's
  box already selects through) — and grows each to its shell: plain = replace, Shift = add, Ctrl = remove.
- Shell = UVs connected through faces in the **current UV set** (Maya's shell selection takes
  ``currentMapSetId`` and grows a UV bit field with ``extendToShell``; a shared corner UV joins faces, a second
  UV set has other shells). Blender's active UV layer is the current set; ``uv_arrays.uv_points`` + ``components``
  give the same shells as ``uv_hud.maya_shells``.
"""

import bmesh
import bpy
import numpy as np
from bpy.props import BoolProperty

from . import uv_arrays
from .. import compat

FLAG = "allset_uv_shell_mask"
BOX_OPS = ("VIEW3D_OT_select_box", "VIEW3D_OT_select_lasso", "UV_OT_select_box", "UV_OT_select_lasso",
           "VIEW3D_OT_select_circle", "UV_OT_select_circle")
SHELL_MESSAGE = "UV shell selection is now <hl>on</hl>. Press <hl>F8</hl> for object selection"


def flag(context):
    wm = context.window_manager
    return bool(getattr(wm, FLAG, False)) if wm is not None else False


def set_flag(context, on):
    wm = context.window_manager
    if wm is not None and hasattr(wm, FLAG) and getattr(wm, FLAG) != on:
        setattr(wm, FLAG, on)


def active(context):
    """Shell picking applies: the flag is on, a mesh is in edit mode in face select mode with UV Sync on."""
    if not flag(context) or context.mode != 'EDIT_MESH':
        return False
    ts = context.scene.tool_settings
    return tuple(ts.mesh_select_mode) == (False, False, True) and ts.use_uv_select_sync


def edit_meshes(context):
    return [o for o in (getattr(context, "objects_in_mode_unique_data", None) or ()) if o and o.type == 'MESH']


# --- shells (numpy) ---------------------------------------------------------------------------------------

def shell_labels(a):
    """Shell label per face of the arrays ``a`` (unhidden faces; hidden faces get -1)."""
    shown = ~a.face_hide
    faces = np.nonzero(shown)[0]
    lab = np.full(len(a.loop_start), -1, np.int64)
    if not len(faces):
        return lab
    loops = uv_arrays._face_loops(a, faces)
    pid, first = uv_arrays.uv_points(a, loops)
    comp = uv_arrays.components(len(a.loop_start), a.corner_face[loops], a.corner_face[first][pid])
    lab[faces] = comp[faces]
    return lab


def apply_rule(before, shell, shift, ctrl, clicked_selected=None):
    """Maya click / box rule on face index sets: plain replace, Ctrl+Shift add, Ctrl remove, Shift = toggle
    for a click (by the clicked face's state) / add for a box (``clicked_selected`` None)."""
    if shift and ctrl:
        return before | shell
    if ctrl:
        return before - shell
    if shift:
        if clicked_selected is None:
            return before | shell
        return (before - shell) if clicked_selected else (before | shell)
    return set(shell)


def write_selection(ob, bm, chosen):
    """Exactly the faces ``chosen`` (indices) selected on ``bm``."""
    bm.faces.ensure_lookup_table()
    for seq in (bm.verts, bm.edges, bm.faces):
        for el in seq:
            el.select = False
    for i in sorted(chosen):
        bm.faces[i].select_set(True)
    bm.select_flush_mode()
    compat.uv_sync_from_mesh(bm)
    bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)


def _arrays(context, ob):
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    if uv is None:          # no UV set: no shells (Maya: faces without UVs can't be picked)
        return bm, None, None
    a = uv_arrays.read(ob, bm, uv, context.view_layer.depsgraph)
    return bm, a, shell_labels(a)


# --- picking ------------------------------------------------------------------------------------------------

def _ray_face(context, region, rv3d, xy):
    """(object, face index) of the nearest unhidden edit-mesh face under region pixel ``xy`` in the 3D View."""
    from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
    from mathutils.bvhtree import BVHTree
    origin = region_2d_to_origin_3d(region, rv3d, xy)
    direction = region_2d_to_vector_3d(region, rv3d, xy)
    best = None
    for ob in edit_meshes(context):
        if not ob.visible_get():
            continue
        bm = bmesh.from_edit_mesh(ob.data)
        inv = ob.matrix_world.inverted_safe()
        o = inv @ origin
        d = (inv.to_3x3() @ direction).normalized()
        faces = [f for f in bm.faces if not f.hide]
        if not faces:
            continue
        bm.verts.index_update()
        tree = BVHTree.FromPolygons([v.co for v in bm.verts], [[v.index for v in f.verts] for f in faces])
        loc, _n, i, _dist = tree.ray_cast(o, d)
        if loc is None:
            continue
        dist = (ob.matrix_world @ loc - origin).length
        if best is None or dist < best[0]:
            best = (dist, ob, faces[i].index)
    return (best[1], best[2]) if best else (None, None)


def uv_faces_at(a, shown, u, v):
    """Indices of ``shown`` faces whose UV polygon contains (u, v) (even-odd rule over their UV edges)."""
    faces = np.nonzero(shown)[0]
    if not len(faces):
        return np.zeros(0, np.int64)
    loops = uv_arrays._face_loops(a, faces)
    p, q = a.uv[loops], a.uv[a.corner_next[loops]]
    straddle = (p[:, 1] > v) != (q[:, 1] > v)
    with np.errstate(divide='ignore', invalid='ignore'):
        x = p[:, 0] + (v - p[:, 1]) * (q[:, 0] - p[:, 0]) / (q[:, 1] - p[:, 1])
    cross = straddle & (u < x)
    count = np.zeros(len(a.loop_start), np.int64)
    np.add.at(count, a.corner_face[loops], cross.astype(np.int64))
    return faces[(count[faces] % 2) == 1]


def _uv_face(context, region, xy):
    """(object, face index) of the UV face under region pixel ``xy`` in the UV Editor (lowest face index wins where
    UV faces overlap — a kit choice)."""
    u, v = region.view2d.region_to_view(*xy)
    for ob in edit_meshes(context):
        bm = bmesh.from_edit_mesh(ob.data)
        uv = bm.loops.layers.uv.active
        if uv is None:
            continue
        a = uv_arrays.read(ob, bm, uv, context.view_layer.depsgraph)
        hit = uv_faces_at(a, ~a.face_hide, u, v)
        if len(hit):
            return ob, int(hit[0])
    return None, None


def pick(context, ob, face, shift, ctrl):
    """Apply a shell click on ``face`` of ``ob`` (None: a click on nothing) to every edit mesh."""
    changed = False
    for o in edit_meshes(context):
        bm, a, lab = _arrays(context, o)
        before = {f.index for f in bm.faces if f.select}
        if o == ob and lab is not None and face is not None and lab[face] >= 0:
            shell = set(np.nonzero(lab == lab[face])[0].tolist())
            after = apply_rule(before, shell, shift, ctrl, clicked_selected=face in before)
        elif shift or ctrl:
            continue                       # a modified click elsewhere leaves this mesh as it is
        else:
            after = set()                  # plain click: the other meshes (or nothing hit) clear
        if after != before:
            write_selection(o, bm, after)
            changed = True
    return changed


class ALLSET_OT_uv_shell_pick(bpy.types.Operator):
    """Maya UV Shell selection: a click picks the whole UV shell of the face under the cursor"""
    bl_idname = "allset.uv_shell_pick"
    bl_label = "Select UV Shell"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        region = context.region
        space = context.space_data
        if not active(context) or region is None or region.type != 'WINDOW' or space is None:
            return {'PASS_THROUGH'}
        xy = (event.mouse_region_x, event.mouse_region_y)
        if space.type == 'VIEW_3D':
            from ..ui import toolbox
            if toolbox.is_toolbox(space) or context.region_data is None:
                return {'PASS_THROUGH'}
            ob, face = _ray_face(context, region, context.region_data, xy)
        elif space.type == 'IMAGE_EDITOR' and space.mode == 'UV':
            ob, face = _uv_face(context, region, xy)
        else:
            return {'PASS_THROUGH'}
        pick(context, ob, face, event.shift, event.ctrl)
        return {'FINISHED'}


# --- box / lasso: Blender selects the faces under it, the kit grows them to shells afterwards ----------------

_box = {}


def _face_sets(context):
    out = {}
    for ob in edit_meshes(context):
        bm = bmesh.from_edit_mesh(ob.data)
        out[ob.name] = (len(bm.faces), {f.index for f in bm.faces if f.select})
    return out


def grow_box(context, before, shift, ctrl):
    """After Blender's box: the faces it changed (before vs now) grown to their shells with Maya's box rule."""
    for ob in edit_meshes(context):
        if ob.name not in before:
            continue
        n, was = before[ob.name]
        bm, a, lab = _arrays(context, ob)
        if lab is None or len(bm.faces) != n:
            continue
        now = {f.index for f in bm.faces if f.select}
        touched = (now ^ was) if (shift or ctrl) else now
        if not touched and (shift or ctrl):
            continue
        labels = {int(lab[i]) for i in touched if lab[i] >= 0}
        shell = set(np.nonzero(np.isin(lab, list(labels)))[0].tolist()) if labels else set()
        after = apply_rule(was, shell, shift, ctrl)
        if after != now:
            write_selection(ob, bm, after)


def _box_running():
    try:
        return any(op.bl_idname in BOX_OPS for w in bpy.context.window_manager.windows for op in w.modal_operators)
    except (AttributeError, ReferenceError):
        return False


def _box_tick():
    st = _box.get("state")
    if st is None:
        return None
    st["ticks"] += 1
    if _box_running() and st["ticks"] < 400:      # the gesture is still being drawn (20 s cap)
        return 0.05
    _box.pop("state", None)
    try:
        if active(bpy.context):
            grow_box(bpy.context, st["before"], st["shift"], st["ctrl"])
    except (ReferenceError, AttributeError, RuntimeError):
        pass
    return None


class ALLSET_OT_uv_shell_box(bpy.types.Operator):
    """Maya UV Shell selection: the faces a box / lasso picks grow to their whole UV shells (passes the drag on)"""
    bl_idname = "allset.uv_shell_box"
    bl_label = "Select UV Shells (Box)"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if active(context):
            _box["state"] = {"before": _face_sets(context), "shift": event.shift, "ctrl": event.ctrl, "ticks": 0}
            if not bpy.app.timers.is_registered(_box_tick):
                bpy.app.timers.register(_box_tick, first_interval=0.05)
        return {'PASS_THROUGH'}


# --- the mode -----------------------------------------------------------------------------------------------

def enter(context):
    """Maya SelectMeshUVShell: component mode, UV Shell mask, selection cleared, message."""
    ts = context.scene.tool_settings
    ts.use_uv_select_sync = True
    ts.mesh_select_mode = (False, False, True)
    for ob in edit_meshes(context):
        bm = bmesh.from_edit_mesh(ob.data)
        write_selection(ob, bm, set())
    set_flag(context, True)
    try:
        from ..ui import view_message
        view_message.show(context, SHELL_MESSAGE, 'TOP_CENTER')
    except (ImportError, AttributeError, RuntimeError):
        pass


classes = (ALLSET_OT_uv_shell_pick, ALLSET_OT_uv_shell_box)


def register_props():
    bpy.types.WindowManager.allset_uv_shell_mask = BoolProperty(
        name="UV Shell", description="Maya UV Shell selection mask: clicks pick whole UV shells", default=False)


def unregister_props():
    if bpy.app.timers.is_registered(_box_tick):
        bpy.app.timers.unregister(_box_tick)
    _box.clear()
    if hasattr(bpy.types.WindowManager, FLAG):
        del bpy.types.WindowManager.allset_uv_shell_mask
