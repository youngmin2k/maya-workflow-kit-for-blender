# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Smart Duplicate / Smart Extrude: Shift+drag a Move/Rotate/Scale manipulator
duplicates the selected objects, or extrudes the selected faces/edges, and the drag
transforms the copies / new components (research/maya/interaction.md:107,
optionVars ``manipSmartDuplicate 1``, ``manipSmartExtrude 1``).

Blender's transform gizmo is C (research/blender/api_limits.md:62). Its keymap
(``Generic Gizmo Maybe Drag``) runs ``gizmogroup.gizmo_tweak`` for any Shift; the
Maya keyconfig puts ``allset.manip_duplicate`` in front of it
(keymap/maya_patches.py 21). This operator duplicates/extrudes and always passes the
event on, so the gizmo then transforms the selection, which is the new part. A timer
waits for the transform to end and takes the copy / extrusion back when nothing moved
(a Shift+click, a cancelled drag). Plans: docs/steps/step_22.md, docs/steps/step_26.md.
"""

import bmesh
import bpy

from .. import results
from .. import live_refs
from . import duplicate, keystate

# Gizmo groups of the transform manipulator (tool gizmo and the viewport's object gizmos);
# light/camera/spot gizmos share the keymap but are left alone (measured, step_26.md).
XFORM_GROUPS = {"VIEW3D_GGT_xform_gizmo", "VIEW3D_GGT_xform_gizmo_context",
                "ALLSET_GGT_xform"}   # ui/manipulator.py, the Maya-shaped manipulator (step 59)
POLL = 0.05
EPS = 1e-6


def _pref(context, name):
    from .. import preferences
    try:
        return getattr(preferences.get(context), name)
    except KeyError:
        return True


def from_xform_gizmo(context):
    """The press is on the transform manipulator (context set by the gizmo map handler)."""
    group = getattr(context, "gizmo_group", None)
    return group is not None and group.bl_idname in XFORM_GROUPS


def _edit_meshes(context):
    return [ob for ob in context.objects_in_mode_unique_data if ob.type == 'MESH']


def _selected_coords(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    return [v.co.copy() for v in bm.verts if v.select]


def kind(context):
    """'DUPLICATE', 'EXTRUDE' or None for a Shift+press on the manipulator."""
    if not from_xform_gizmo(context):
        return None
    if context.mode == 'OBJECT':
        if context.selected_objects and _pref(context, "smart_duplicate"):
            return 'DUPLICATE'
        return None
    if context.mode == 'EDIT_MESH' and _pref(context, "smart_extrude"):
        _vert, edge, face = context.tool_settings.mesh_select_mode
        if (edge or face) and any(_selected_coords(ob) for ob in _edit_meshes(context)):
            return 'EXTRUDE'
    return None


# --- what each kind did, and how to take it back ---------------------------------------

def start_duplicate(context):
    originals = list(context.selected_objects)
    active = context.view_layer.objects.active
    duplicate.duplicate(context)
    copies = list(context.selected_objects)
    return {"kind": 'DUPLICATE', "copies": [o.name for o in copies],
            "matrices": [o.matrix_world.copy() for o in copies],
            "originals": [o.name for o in originals], "active": active.name if active else None}


def start_extrude(context):
    """Extrude in place (Maya polyExtrudeFacet / polyExtrudeEdge, keepFacesTogether on [K]):
    edges extrude as a region too, so a connected edge strip stays connected (delegated)."""
    obs = _edit_meshes(context)
    saved = {}
    for ob in obs:
        ob.update_from_editmode()
        saved[ob.name] = ob.data.copy().name    # mesh before the extrusion (for a cancel)
    bpy.ops.mesh.extrude_region(use_normal_flip=False)
    return {"kind": 'EXTRUDE', "saved": saved,
            "coords": {ob.name: _selected_coords(ob) for ob in obs}}


def moved(state):
    if state["kind"] == 'DUPLICATE':
        for name, m in zip(state["copies"], state["matrices"]):
            ob = bpy.data.objects.get(name)
            if ob is not None and any(abs(a - b) > EPS for ra, rb in zip(ob.matrix_world, m)
                                      for a, b in zip(ra, rb)):
                return True
        return False
    for name, before in state["coords"].items():
        ob = bpy.data.objects.get(name)
        if ob is None or ob.mode != 'EDIT':
            return True    # left edit mode meanwhile: keep what is there
        now = _selected_coords(ob)
        if len(now) != len(before) or any((a - b).length > EPS for a, b in zip(now, before)):
            return True
    return False


def revert(state):
    """Take back a copy / extrusion whose transform was cancelled (no undo step exists)."""
    if state["kind"] == 'DUPLICATE':
        for name in state["copies"]:
            ob = bpy.data.objects.get(name)
            if ob is not None:
                bpy.data.objects.remove(ob)
        for name in state["originals"]:
            ob = bpy.data.objects.get(name)
            if ob is not None:
                ob.select_set(True)
        if state["active"] in bpy.data.objects:
            bpy.context.view_layer.objects.active = bpy.data.objects[state["active"]]
        return
    for name, mesh_name in state["saved"].items():
        ob, saved = bpy.data.objects.get(name), bpy.data.meshes.get(mesh_name)
        if ob is None or saved is None or ob.mode != 'EDIT':
            continue
        bm = bmesh.from_edit_mesh(ob.data)
        bm.clear()
        bm.from_mesh(saved)
        bmesh.update_edit_mesh(ob.data)


def cleanup(state):
    for mesh_name in state.get("saved", {}).values():
        me = bpy.data.meshes.get(mesh_name)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def _last_op():
    ops = bpy.context.window_manager.operators
    return ops[-1].as_pointer() if len(ops) else 0


def _transform_running(window):
    return any(op.bl_idname.startswith("TRANSFORM_OT_") or op.bl_idname in
               {'ALLSET_OT_pivot_translate', 'ALLSET_OT_pivot_rotate'} for op in window.modal_operators)


# --- the active handle (Maya MMB drag anywhere), step 28 -------------------------------

# Last handle per transform kind: research/maya/interaction.md:103 (manipsRememberActiveHandle,
# ...AfterToolSwitch true, defaults.json:63-65). Session only; a re-tap of the tool key resets.
HANDLES = {}
OP_KINDS = {"TRANSFORM_OT_translate": 'TRANSLATE', "TRANSFORM_OT_rotate": 'ROTATE',
            "TRANSFORM_OT_resize": 'RESIZE'}


def handle_from_op(bl_idname, props):
    """(kind, handle) for a transform the manipulator ran; handle None = free (centre)."""
    if bl_idname == 'ALLSET_OT_pivot_translate':
        from ..ui import manipulator
        axes = tuple(bool(a) for a in props.constraint_axis)
        return 'TRANSLATE', ({'constraint_axis': axes,
                             'orient_type': manipulator.slot_type(bpy.context.scene, 'TRANSLATE')} if any(axes) else None)
    kind = OP_KINDS.get(bl_idname)
    if kind is None:
        return None, None
    axes = tuple(bool(a) for a in props.constraint_axis)
    if kind == 'ROTATE':
        if props.orient_axis == 'VIEW' and not any(axes):
            return kind, None
        return kind, {"constraint_axis": axes, "orient_type": props.orient_type,
                      "orient_axis": props.orient_axis}
    if not any(axes):
        return kind, None
    return kind, {"constraint_axis": axes, "orient_type": props.orient_type}


def remember_last_op(since):
    """Remember the handle of a transform registered after ``since`` (an op pointer)."""
    ops = bpy.context.window_manager.operators
    if not len(ops) or ops[-1].as_pointer() == since:
        return
    kind, handle = handle_from_op(ops[-1].bl_idname, ops[-1].properties)
    if kind is not None:
        HANDLES[kind] = handle


def reset_handle(kind):
    HANDLES.pop(kind, None)


def finish(state, window, area, region):
    """After the transform: remember its handle; keep a moved copy / extrusion, take back
    one that didn't move."""
    if state["kind"] == 'PRESS' or moved(state):
        remember_last_op(state["last_op"])
    elif _last_op() != state["last_op"]:
        # Confirmed without moving (Shift+click): the transform pushed the only undo
        # step (the duplicate/extrude was a nested call), so one undo is the state before.
        with bpy.context.temp_override(window=window, area=area, region=region):
            bpy.ops.ed.undo()
    else:
        revert(state)    # cancelled: no undo step, take it back by hand
    cleanup(state)


def watch(state, window, area, region):
    """Poll until the gizmo's transform ends, then ``finish``."""
    state["last_op"] = _last_op()
    # pointers, looked up each tick: a Window / Area / Region kept after its window closed crashes (#36)
    win_ptr, area_ptr, region_ptr = live_refs.pointer(window), live_refs.pointer(area), live_refs.pointer(region)

    def tick():
        window = live_refs.window(win_ptr)
        try:
            if window is None:
                cleanup(state)
                return None
            if _transform_running(window):
                state["seen"] = True
                return POLL
            # The gizmo starts its transform only once the mouse moves past the drag threshold ("Maybe Drag"):
            # a press held still has no transform yet, so wait while the button is down (step 97).
            if not state.get("seen") and keystate.is_down('LEFTMOUSE'):
                return POLL
            area = live_refs.area(area_ptr, window)
            finish(state, window, area, live_refs.region(area, region_ptr))
        except ReferenceError:
            cleanup(state)
        return None

    bpy.app.timers.register(tick, first_interval=POLL)


class ALLSET_OT_manip_duplicate(bpy.types.Operator):
    """Shift+drag a manipulator: duplicate the selected objects or extrude the selected
    faces/edges, then the drag moves, rotates or scales them (Maya Smart Duplicate /
    Smart Extrude)"""
    bl_idname = "allset.manip_duplicate"
    bl_label = "Smart Duplicate / Extrude"
    bl_options = {'INTERNAL'}

    def invoke(self, context, _event):
        return self.execute(context)

    def execute(self, context):
        what = kind(context)
        if what is not None:
            state = start_duplicate(context) if what == 'DUPLICATE' else start_extrude(context)
            if context.window is not None:
                watch(state, context.window, context.area, context.region)
            else:
                cleanup(state)
        # Always pass the event on: the gizmo's own tweak transforms the selection.
        return {'PASS_THROUGH'}


class ALLSET_OT_manip_press(bpy.types.Operator):
    """LMB on the manipulator: remember which handle the drag used (Maya active handle)"""
    bl_idname = "allset.manip_press"
    bl_label = "Manipulator Press"
    bl_options = {'INTERNAL'}

    def invoke(self, context, _event):
        from . import snap_align
        snap_align.apply_active(context)       # step 263: this tool's Step Snap Relative / Absolute
        if from_xform_gizmo(context) and context.window is not None:
            watch({"kind": 'PRESS'}, context.window, context.area, context.region)
        return {'PASS_THROUGH'}


TRANSFORM_OPS = {'TRANSLATE': "translate", 'ROTATE': "rotate", 'RESIZE': "resize"}


class ALLSET_OT_manip_mmb(bpy.types.Operator):
    """MMB drag anywhere: move/rotate/scale along the last picked manipulator handle
    (free when none, Maya)"""
    bl_idname = "allset.manip_mmb"
    bl_label = "Drag Active Handle"
    bl_options = {'INTERNAL'}

    mode: bpy.props.EnumProperty(items=[(k, k.title(), "") for k in TRANSFORM_OPS])

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, _event):
        from . import snap_align
        snap_align.apply_tool(context.scene.tool_settings, self.mode)   # step 263: per-tool Step Snap
        kwargs = {"release_confirm": True}
        handle = HANDLES.get(self.mode)
        if handle:
            kwargs.update(handle)
        op = getattr(bpy.ops.transform, TRANSFORM_OPS[self.mode])
        try:
            res = op('INVOKE_DEFAULT', **kwargs)
        except RuntimeError:     # nothing to transform (poll failed)
            return {'PASS_THROUGH'}
        return {'FINISHED'} if res & {'RUNNING_MODAL', 'FINISHED'} else {'CANCELLED'}


# --- Ctrl+LMB axis = plane, Shift+MMB = automatic axis (docs/steps/step_85.md) -------------------------
# research/maya/interaction.md:104-106 [K]: Ctrl+LMB on an axis handle makes the plane perpendicular to it the active
# handle (move / scale in the other two), Ctrl+click on the Move centre frees the active handle; Shift+MMB drag moves
# along the axis closest to the drag direction.

def plane_of(axis):
    """constraint_axis of the plane perpendicular to ``axis`` ('X' -> (False, True, True))."""
    return tuple(a != axis for a in 'XYZ')


def pick_axis(drag, dirs, min_len=1e-3):
    """Index of the axis whose screen direction is closest to ``drag`` (largest |cos|), or None. ``dirs`` = screen
    vectors of the axes (None or ~0 for an axis pointing at the viewer)."""
    dx, dy = drag
    dl = (dx * dx + dy * dy) ** 0.5
    if dl < min_len:
        return None
    best, best_cos = None, -1.0
    for i, d in enumerate(dirs):
        if d is None:
            continue
        ln = (d[0] * d[0] + d[1] * d[1]) ** 0.5
        if ln < min_len:
            continue
        c = abs(d[0] * dx + d[1] * dy) / (ln * dl)
        if c > best_cos + 1e-9:
            best, best_cos = i, c
    return best


def _highlighted(context):
    """The kit manipulator handle under the mouse (gizmo keymap context), or None."""
    from ..ui import manipulator
    group = getattr(context, "gizmo_group", None)
    if group is None or group.bl_idname != manipulator.GROUP:
        return None
    return next((gz for gz in group.gizmos if gz.is_highlight and hasattr(gz, "handle_role")), None)


class ALLSET_OT_manip_ctrl(bpy.types.Operator):
    """Ctrl+LMB on the manipulator: an axis handle moves / scales in the plane of the other two axes and makes
    that plane the active handle; the Move centre frees the active handle (Maya)"""
    bl_idname = "allset.manip_ctrl"
    bl_label = "Manipulator Ctrl Handle"
    bl_options = {'INTERNAL'}

    def invoke(self, context, _event):
        from ..ui import manipulator
        gz = _highlighted(context)
        kind = manipulator.tool_kind(context)
        if gz is None or kind not in TRANSFORM_OPS:
            return {'PASS_THROUGH'}
        role, axis = getattr(gz, "handle_role", None), getattr(gz, "handle_axis", None)
        if role == 'CENTER' and kind == 'TRANSLATE':
            reset_handle(kind)
            context.area.tag_redraw()
            return {'FINISHED'}
        if role != 'AXIS' or axis not in ('X', 'Y', 'Z'):
            return {'PASS_THROUGH'}
        otype = manipulator.slot_type(context.scene, kind)
        axes = plane_of(axis)
        HANDLES[kind] = {"constraint_axis": axes, "orient_type": otype}
        op = getattr(bpy.ops.transform, TRANSFORM_OPS[kind])
        try:
            op('INVOKE_DEFAULT', constraint_axis=axes, orient_type=otype, release_confirm=True)
        except RuntimeError:
            return {'PASS_THROUGH'}
        return {'FINISHED'}


AUTO_PX = 6          # movement that decides the Shift+MMB axis (x UI scale)


def axis_dirs(context, kind):
    """(screen directions of the manipulator axes, orientation type), or (None, None) when nothing is selected."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    from ..ui import manipulator
    center, frame, otype = manipulator.pivot_frame(context, kind)
    if center is None:
        return None, None
    region, rv3d = context.region, context.region_data
    p0 = location_3d_to_region_2d(region, rv3d, center)
    size = max(rv3d.view_distance * 0.1, 1e-6)
    dirs = []
    for i in range(3):
        p1 = location_3d_to_region_2d(region, rv3d, center + frame.col[i].normalized() * size)
        dirs.append(None if p0 is None or p1 is None else (p1[0] - p0[0], p1[1] - p0[1]))
    return dirs, otype


class ALLSET_OT_manip_mmb_auto(bpy.types.Operator):
    """Shift+MMB drag: move / scale along the manipulator axis closest to the drag direction (Maya)"""
    bl_idname = "allset.manip_mmb_auto"
    bl_label = "Drag Along Closest Axis"
    bl_options = {'INTERNAL'}

    mode: bpy.props.EnumProperty(items=[(k, k.title(), "") for k in TRANSFORM_OPS])

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.region_data is not None

    def invoke(self, context, event):
        dirs, otype = axis_dirs(context, self.mode)
        if dirs is None:
            return {'PASS_THROUGH'}
        self._dirs, self._otype = dirs, otype
        self._start = (event.mouse_x, event.mouse_y)
        self._px = AUTO_PX * (context.preferences.system.ui_scale or 1.0)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            drag = (event.mouse_x - self._start[0], event.mouse_y - self._start[1])
            if (drag[0] ** 2 + drag[1] ** 2) ** 0.5 < self._px:
                return {'RUNNING_MODAL'}
            i = pick_axis(drag, self._dirs)
            if i is None:
                return {'CANCELLED'}
            op = getattr(bpy.ops.transform, TRANSFORM_OPS[self.mode])
            try:
                # launched from this MOUSEMOVE: release_confirm can't see the MMB, so the transform is
                # confirmed by the MMB release below it (measured, docs/steps/step_85.md)
                op('INVOKE_DEFAULT', constraint_axis=tuple(k == i for k in range(3)), orient_type=self._otype,
                   release_confirm=True)
            except RuntimeError:
                return {'CANCELLED'}
            return {'FINISHED'}
        if event.type == 'MIDDLEMOUSE' and event.value == 'RELEASE':
            return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


OPTIONS = {'SMART_DUPLICATE': "smart_duplicate", 'SMART_EXTRUDE': "smart_extrude"}


class ALLSET_OT_manip_option(bpy.types.Operator):
    """Toggle a manipulator option (W/E/R hold menu: Smart Duplicate, Smart Extrude)"""
    bl_idname = "allset.manip_option"
    bl_label = "Manipulator Option"
    bl_options = {'INTERNAL'}

    option: bpy.props.EnumProperty(items=(('SMART_DUPLICATE', "Smart Duplicate", ""),
                                          ('SMART_EXTRUDE', "Smart Extrude", "")))

    def execute(self, context):
        from .. import preferences
        prefs = preferences.get(context)
        name = OPTIONS[self.option]
        setattr(prefs, name, not getattr(prefs, name))
        label = self.option.replace("_", " ").title()
        results.result(self, f"{label} {'on' if getattr(prefs, name) else 'off'}")
        return {'FINISHED'}


class ALLSET_OT_manip_size(bpy.types.Operator):
    """Make the manipulator bigger or smaller (Maya = / -)"""
    bl_idname = "allset.manip_size"
    bl_label = "Manipulator Size"
    bl_options = {'INTERNAL'}

    # Maya: manipOptions -r -s 2.0 / 0.5 (Maya default hotkeys, docs/keymap_mapping.md); 1.25x steps within
    # Blender's gizmo size range 10-200 px (docs/steps/step_27.md, delegated). Since step 130 this scales the kit's
    # Move / Scale manipulator only (ui/manipulator.SIZE): Blender's gizmo_size preference is never written, so
    # Blender's own gizmos (Rotate) keep their size.
    factor: bpy.props.FloatProperty(name="Factor", default=1.25, min=0.1, max=10.0,
                                    options={'SKIP_SAVE'})

    def execute(self, context):
        from ..ui import manipulator
        base = context.preferences.view.gizmo_size
        size = round(base * manipulator.SIZE[0])
        new = max(10, min(200, round(size * self.factor)))
        if new == size:
            new = max(10, min(200, size + (1 if self.factor > 1 else -1)))
        manipulator.SIZE[0] = new / max(base, 1)
        results.result(self, f"Manipulator size {new} px")
        for area in context.screen.areas if context.screen else ():
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}


def option_state(option):
    """Current value of a manip_option toggle (for the hold menus' check boxes)."""
    return bool(_pref(bpy.context, OPTIONS[option]))


classes = (ALLSET_OT_manip_duplicate, ALLSET_OT_manip_option, ALLSET_OT_manip_size,
           ALLSET_OT_manip_press, ALLSET_OT_manip_mmb, ALLSET_OT_manip_ctrl, ALLSET_OT_manip_mmb_auto)
