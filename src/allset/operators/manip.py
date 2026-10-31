# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Smart Duplicate / Smart Extrude: Shift+drag a Move/Rotate/Scale manipulator
duplicates the selected objects, or extrudes the selected faces/edges/vertices, and the drag
transforms the copies / new components (Maya's smart duplicate / smart extrude).

Blender's transform gizmo is C. Its keymap
(``Generic Gizmo Maybe Drag``) runs ``gizmogroup.gizmo_tweak`` for any Shift; the
Maya keyconfig puts ``allset.manip_duplicate`` in front of it
(keymap/maya_patches.py 21). This operator duplicates/extrudes and always passes the
event on, so the gizmo then transforms the selection, which is the new part. A timer
waits for the transform to end and takes the copy / extrusion back when nothing moved
(a Shift+click, a cancelled drag).
"""

import bmesh
import bpy

from .. import results
from .. import live_refs
from . import duplicate, keystate

# Gizmo groups of the transform manipulator (tool gizmo and the viewport's object gizmos);
# light/camera/spot gizmos share the keymap but are left alone.
XFORM_GROUPS = {"VIEW3D_GGT_xform_gizmo", "VIEW3D_GGT_xform_gizmo_context",
                "ALLSET_GGT_xform"}   # ui/manipulator.py, the Maya-shaped manipulator
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
        if any(_selected_coords(ob) for ob in _edit_meshes(context)):
            return 'EXTRUDE'      # faces, edges and vertices (Maya 2026 behaviour; #183)
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


# Maya 2026 (#183): Shift+drag with vertices selected runs polyExtrudeVertex with Width 0.5 and Length 0,
# and the drag moves the vertex together with the new base vertices around it
VERTEX_DRAG = {"width": 0.5, "length": 0.0, "divisions": 1}


def _vertex_mode(context):
    vert, edge, face = context.tool_settings.mesh_select_mode
    return vert and not (edge or face)


def _extrude_vertices(context, ob):
    """Kit polyExtrudeVertex (``VERTEX_DRAG``) on the selected vertices of ``ob``; the vertices and their new base
    vertices end up selected, so the manipulator drag moves them together."""
    from . import extrude, units
    bm = bmesh.from_edit_mesh(ob.data)
    tips = [v for v in bm.verts if v.select]
    if not tips:
        return
    before = set(bm.verts)
    extrude.record_new(context, ob, bm, extrude.VERTEX, dict(VERTEX_DRAG), units.maya_unit(context.scene))
    for v in tips + [v for v in bm.verts if v not in before]:
        if v.is_valid:
            v.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)


def start_extrude(context):
    """Extrude in place (Maya polyExtrudeFacet / polyExtrudeEdge, keepFacesTogether on):
    edges extrude as a region too, so a connected edge strip stays connected; vertices extrude Maya's
    polyExtrudeVertex way (``VERTEX_DRAG``)."""
    obs = _edit_meshes(context)
    saved = {}
    for ob in obs:
        ob.update_from_editmode()
        saved[ob.name] = ob.data.copy().name    # mesh before the extrusion (for a cancel)
    if _vertex_mode(context):
        for ob in obs:
            _extrude_vertices(context, ob)
    else:
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
    from .manip_scale import TRANSFORM_MODALS
    return any(op.bl_idname.startswith(TRANSFORM_MODALS) for op in window.modal_operators)


# --- the active handle (Maya MMB drag anywhere) -------------------------------------

# Last handle per transform kind (Maya manipsRememberActiveHandle,
# ...AfterToolSwitch true). Session only; a re-tap of the tool key resets.
HANDLES = {}
OP_KINDS = {"TRANSFORM_OT_translate": 'TRANSLATE', "TRANSFORM_OT_rotate": 'ROTATE',
            "TRANSFORM_OT_resize": 'RESIZE', "ALLSET_OT_component_scale": 'RESIZE', 'ALLSET_OT_live_translate': 'TRANSLATE'}


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
    if bl_idname in {'ALLSET_OT_component_scale', 'ALLSET_OT_live_translate'}:
        return kind, {"constraint_axis": axes, "orient_type": 'GLOBAL',
                      "orient_matrix_type": 'GLOBAL', "orient_matrix": props.orient_matrix.copy()}
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


def button_held(state):
    """Is the left button that started ``state`` still held? Asked of the OS where it can tell; elsewhere until
    the ``allset.manip_release`` keymap items hear the release (``state["listening"]``)."""
    down = keystate.is_down('LEFTMOUSE')
    if down is None:
        return bool(state.get("listening")) and not state.get("released")
    return down


_LISTEN = []     # the press whose release the kit waits for where the OS can't tell (``listen``)


def listen(state):
    """Where the OS can't tell whether the button is held (not Windows), hear its release through the
    ``allset.manip_release`` keymap items (a modal handler would cancel the gizmo's pending drag)."""
    state["listening"] = True
    _LISTEN[:] = [state]


class ALLSET_OT_manip_release(bpy.types.Operator):
    """Left button released: a Smart Duplicate / Extrude press that never became a drag was a click"""
    bl_idname = "allset.manip_release"
    bl_label = "Manipulator Release"
    bl_options = {'INTERNAL'}

    def invoke(self, context, _event):
        return self.execute(context)

    def execute(self, _context):
        for state in _LISTEN:
            if not state.get("seen") and not state.get("done"):
                state["released"] = True
        _LISTEN.clear()
        return {'PASS_THROUGH'}


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
            # a press held still has no transform yet, so wait while the button is down.
            if not state.get("seen") and button_held(state):
                return POLL
            state["done"] = True
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
        self._start(context)
        return {'PASS_THROUGH'}

    @staticmethod
    def _start(context):
        """Duplicate / extrude and start watching the gizmo's transform; the state, or None. The event always
        goes on: the gizmo's own tweak transforms the selection."""
        what = kind(context)
        if what is None:
            return None
        state = start_duplicate(context) if what == 'DUPLICATE' else start_extrude(context)
        if context.window is None:
            cleanup(state)
            return None
        held = keystate.is_down('LEFTMOUSE')      # None: this OS can't tell
        if held is None:
            listen(state)
        watch(state, context.window, context.area, context.region)
        return state


class ALLSET_OT_manip_press(bpy.types.Operator):
    """LMB on the manipulator: remember which handle the drag used (Maya active handle)"""
    bl_idname = "allset.manip_press"
    bl_label = "Manipulator Press"
    bl_options = {'INTERNAL'}

    def invoke(self, context, _event):
        from . import snap_align
        snap_align.apply_active(context)       # this tool's Step Snap Relative / Absolute
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
        snap_align.apply_tool(context.scene.tool_settings, self.mode)   # per-tool Step Snap
        kwargs = {"release_confirm": True}
        handle = HANDLES.get(self.mode)
        if self.mode == 'TRANSLATE':
            from . import xform_constraint
            if xform_constraint.active(context):     # Maya Transform Constraint: MMB slides the components
                res = bpy.ops.allset.component_slide('INVOKE_DEFAULT')
                return {'FINISHED'} if res & {'RUNNING_MODAL', 'FINISHED'} else {'CANCELLED'}
        if self.mode == 'RESIZE':
            res = self._maya_scale(handle)
            if res is not None:
                return res
        if handle:
            kwargs.update(handle)
        op = getattr(bpy.ops.transform, TRANSFORM_OPS[self.mode])
        try:
            if self.mode == 'RESIZE':
                from . import component_scale
                res = component_scale.start(context, kwargs, 'MIDDLEMOUSE')
            elif self.mode == 'TRANSLATE':
                from . import live_translate
                res = live_translate.start(context, kwargs, 'MIDDLEMOUSE')
            else:
                res = op('INVOKE_DEFAULT', **kwargs)
        except RuntimeError:     # nothing to transform (poll failed)
            return {'PASS_THROUGH'}
        return {'FINISHED'} if res & {'RUNNING_MODAL', 'FINISHED'} else {'CANCELLED'}

    @staticmethod
    def _maya_scale(handle):
        """#200: the active Scale handle drags Maya's way (operators/manip_scale.py); an axis or plane
        handle at half speed there."""
        axes = tuple(bool(a) for a in handle.get("constraint_axis", ())) if handle else ()
        kwargs = {"button": 'MIDDLEMOUSE'}
        if handle and sum(axes) == 1:
            kwargs.update(mode='AXIS', axis='XYZ'[axes.index(True)])
        elif handle and sum(axes) == 2:
            kwargs.update(mode='PLANE', plane="".join(a for a, on in zip('XYZ', axes) if on))
        elif handle and any(axes):
            return None
        if handle:
            kwargs["orient_type"] = handle.get("orient_type", "")
        try:
            res = bpy.ops.allset.manip_scale('INVOKE_DEFAULT', **kwargs)
        except RuntimeError:
            return {'PASS_THROUGH'}
        return {'FINISHED'} if res & {'RUNNING_MODAL', 'FINISHED'} else {'CANCELLED'}


# --- Ctrl+LMB on a handle, Shift+MMB = automatic axis -------------------------
# Move tool: a drag started with Ctrl held on an axis arrow / plane / the centre moves that handle's way with
# grid snapping (the same as pressing Ctrl after the drag started), Ctrl+click on the centre frees the active
# handle; Scale tool: Ctrl+LMB on an axis scales the other two axes; Shift+MMB drag moves along the axis closest
# to the drag direction.

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
    """Ctrl+LMB on the manipulator: a Move handle drag moves along that handle with grid snapping, Ctrl+click on
    the Move centre frees the active handle, a Scale axis handle scales the other two axes"""
    bl_idname = "allset.manip_ctrl"
    bl_label = "Manipulator Ctrl Handle"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        from ..ui import manipulator
        from . import snap_align
        gz = _highlighted(context)
        kind = manipulator.tool_kind(context)
        if gz is None or kind not in TRANSFORM_OPS:
            return {'PASS_THROUGH'}
        role, axis = getattr(gz, "handle_role", None), getattr(gz, "handle_axis", None)
        if kind == 'TRANSLATE' and role == 'CENTER':
            # Ctrl+click frees the active handle; the press is kept here (passed on, a Ctrl+click would
            # deselect), so a drag past the threshold starts the centre's free move itself
            reset_handle(kind)
            context.area.tag_redraw()
            snap_align.apply_active(context)
            self._editing = getattr(context.gizmo_group, "_built_for", None) == ('TRANSLATE', True)
            self._press = (event.mouse_x, event.mouse_y)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        if kind == 'TRANSLATE':
            # The press goes on to the handle's own drag (the Generic Gizmo keymaps allow Ctrl there): the
            # transform starts with Ctrl held, so it snaps from the start and Ctrl stays its snap toggle.
            snap_align.apply_active(context)
            if context.window is not None:
                watch({"kind": 'PRESS'}, context.window, context.area, context.region)
            return {'PASS_THROUGH'}
        if kind != 'RESIZE' or role != 'AXIS' or axis not in ('X', 'Y', 'Z'):
            return {'PASS_THROUGH'}
        otype = manipulator.slot_type(context.scene, kind)
        HANDLES[kind] = {"constraint_axis": plane_of(axis), "orient_type": otype}
        # the other two axes by this handle's own drag factor (operators/manip_scale.py)
        try:
            bpy.ops.allset.manip_scale('INVOKE_DEFAULT', mode='AXIS', axis=axis, others=True, orient_type=otype)
        except RuntimeError:
            return {'PASS_THROUGH'}
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            return {'CANCELLED'}
        if event.type != 'MOUSEMOVE':
            return {'PASS_THROUGH'}
        limit = context.preferences.inputs.drag_threshold_mouse * context.preferences.system.ui_scale
        if max(abs(event.mouse_x - self._press[0]), abs(event.mouse_y - self._press[1])) < limit:
            return {'RUNNING_MODAL'}
        # the centre's own drag (ui/manipulator.py _bind_ops), started while Ctrl is held: snapped
        try:
            if self._editing:
                bpy.ops.allset.pivot_translate('INVOKE_DEFAULT')
            else:
                from . import live_translate
                live_translate.start(context, {"release_confirm": True})
        except RuntimeError:
            return {'CANCELLED'}
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
                # confirmed by the MMB release below it
                kwargs = dict(constraint_axis=tuple(k == i for k in range(3)), orient_type=self._otype,
                              release_confirm=True)
                if self.mode == 'RESIZE':
                    from . import component_scale
                    component_scale.start(context, kwargs, 'MIDDLEMOUSE')
                else:
                    if self.mode == 'TRANSLATE':
                        from . import pivot
                        pivot.origins_for_groups(context)
                    op('INVOKE_DEFAULT', **kwargs)
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

    # Maya's = / - keys grow / shrink the manipulator; here 1.25x steps within
    # Blender's gizmo size range 10-200 px. This scales the kit's
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


classes = (ALLSET_OT_manip_duplicate, ALLSET_OT_manip_release, ALLSET_OT_manip_option, ALLSET_OT_manip_size,
           ALLSET_OT_manip_press, ALLSET_OT_manip_mmb, ALLSET_OT_manip_ctrl, ALLSET_OT_manip_mmb_auto)
