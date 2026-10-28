# SPDX-License-Identifier: GPL-3.0-or-later
"""The Maya pivot concept on top of Blender's origin (docs/steps/step_59.md 「계획」 1-3).

Measured in Maya 2022 (research/maya/workflows/pivot_snap.md):

- P1/P3: moving the pivot (D hold / Insert, ``cmds.xform(pivots=...)``) changes neither translate nor
  the vertices nor the children; snapping applies while editing.
- P8: orienting the pivot doesn't touch the channels either: the Move tool's axis mode
  becomes Custom; Modify > Bake Pivot puts that orientation into rotate (geometry stays).
- P6/P7: Reset Pivot = pivot back to the object's own origin (translate), Match Pivots =
  the others' pivots onto the lead's.
- P10/P11: the manipulator sits at the lead object's pivot, or at the bounding-box centre
  of a component selection.

The kit's pivot is the Blender origin and ``delta_location`` is Maya's pivot offset
(step 10, ``freeze.shift_pivot``). D / Insert turn on Blender's Affect Only Origins (and
Affect Only Parents, so children stay); Blender then writes the new origin into the
location / rotation channels. ``watch()`` waits for each such transform to end and
rewrites the result the Maya way: channels back, the new pivot position into
``delta_location``, a new pivot orientation into the "Maya Pivot" transform orientation
(the Move and Rotate tools' Custom axes), geometry and children where they are.
"""

import bpy
from bpy.props import BoolProperty
from mathutils import Matrix, Quaternion, Vector

from .. import results
from . import freeze

ORIENT_NAME = "Maya Pivot"
# Object-space orientation (quaternion w, x, y, z) of the object's custom pivot (Bake Pivot input).
PROP = "allset_pivot_orient"
MOVE_SLOT = 1
ROTATE_SLOT = 2
PIVOT_SLOTS = (MOVE_SLOT, ROTATE_SLOT)
EPS = 1e-6
POLL = 0.1

# Maya manipulator position (P10/P11): Blender pivot point per mode. Only switched when the
# current value is one of these two, so a user's cursor / individual-origins choice stays.
MAYA_PIVOT_POINT = {'OBJECT': 'ACTIVE_ELEMENT', 'EDIT_MESH': 'BOUNDING_BOX_CENTER'}


def axes_for(ob):
    """Orthonormal world axes of an object's pivot, including its saved custom rotation."""
    rotation = ob.matrix_world.to_quaternion()
    if PROP in ob:
        rotation = rotation @ Quaternion(ob[PROP])
    return rotation.to_matrix()


# --- pure helpers (headless-testable) ---------------------------------------------------------

def snapshot(ob):
    """Channels and basis of ``ob`` before a pivot edit."""
    return {
        "basis": ob.matrix_basis.copy(),
        "location": Vector(ob.location), "delta_location": Vector(ob.delta_location),
        "rotation_euler": ob.rotation_euler.copy(), "rotation_quaternion": ob.rotation_quaternion.copy(),
        "rotation_axis_angle": tuple(ob.rotation_axis_angle),
        "delta_rotation_euler": ob.delta_rotation_euler.copy(),
        "delta_rotation_quaternion": ob.delta_rotation_quaternion.copy(),
        "scale": Vector(ob.scale), "delta_scale": Vector(ob.delta_scale),
    }


def _restore_channels(ob, snap):
    ob.location = snap["location"]
    ob.rotation_euler = snap["rotation_euler"]
    ob.rotation_quaternion = snap["rotation_quaternion"]
    ob.rotation_axis_angle = snap["rotation_axis_angle"]
    ob.delta_rotation_euler = snap["delta_rotation_euler"]
    ob.delta_rotation_quaternion = snap["delta_rotation_quaternion"]
    ob.scale = snap["scale"]
    ob.delta_scale = snap["delta_scale"]


def _close(a, b):
    return all(abs(a[i][j] - b[i][j]) < EPS for i in range(4) for j in range(4))


def _keep_children(ob, w_old, b_new_world):
    """Children keep their world matrix when ``ob``'s world becomes ``b_new_world``."""
    w_new = {ob: b_new_world}
    for ch in ob.children:
        frame = freeze.parent_frame(ch, w_old, w_new)
        ch.matrix_basis = frame.inverted_safe() @ w_old[ch]


def rewrite(ob, snap):
    """Turn an origin-only transform of ``ob`` (made after ``snap``) into a Maya pivot edit.

    Returns the new world orientation of the pivot (a 3x3) if the pivot was turned, else None."""
    b1 = ob.matrix_basis.copy()
    b0 = snap["basis"]
    if _close(b0, b1):
        return None
    w_old = {ob: ob.matrix_world.copy()}
    for ch in ob.children:
        w_old[ch] = ch.matrix_world.copy()
    frame = w_old[ob] @ b1.inverted_safe()           # parent space -> world
    turned = (b1.to_3x3().normalized().to_quaternion().rotation_difference(
        b0.to_3x3().normalized().to_quaternion()).angle > 1e-5)
    world_axes = (frame @ b1).to_3x3().normalized() if turned else None

    _restore_channels(ob, snap)
    ob.delta_location = snap["delta_location"] + (b1.translation - b0.translation)
    b_final = ob.matrix_basis.copy()
    d = b_final.inverted_safe() @ b1
    if ob.type in freeze.BAKE_TYPES and ob.data is not None and not _close(d, Matrix.Identity(4)):
        freeze.bake_into_data(ob, d)
    if not _close(b_final, b1):
        _keep_children(ob, w_old, frame @ b_final)
    if world_axes is not None:
        obj_rot = (frame @ b_final).to_3x3().normalized().to_quaternion()
        ob[PROP] = tuple(obj_rot.inverted() @ world_axes.to_quaternion())
    return world_axes


def reset_pivot(ob, position=True, orientation=True):
    """Maya Reset Pivot (P6): pivot back to the object's own origin (delta_location 0)."""
    done = False
    if position and Vector(ob.delta_location).length > EPS:
        lin = ob.matrix_basis.to_3x3()
        c = lin.inverted_safe() @ -Vector(ob.delta_location)
        freeze.shift_pivot(ob, c)
        done = True
    if orientation and PROP in ob:
        del ob[PROP]
        done = True
    return done


def bake_pivot(ob):
    """Maya Bake Pivot (P8): the custom pivot orientation becomes the rotation; geometry and
    children stay. Returns True if something was baked."""
    if PROP not in ob:
        return False
    q = Quaternion(ob[PROP])
    del ob[PROP]
    if q.angle < 1e-6:
        return False
    w_old = {ob: ob.matrix_world.copy()}
    for ch in ob.children:
        w_old[ch] = ch.matrix_world.copy()
    b_old = ob.matrix_basis.copy()
    frame = w_old[ob] @ b_old.inverted_safe()
    t, r, s = b_old.decompose()
    freeze.set_rotation(ob, r @ q)
    ob.location = t - Vector(ob.delta_location)
    b_new = ob.matrix_basis.copy()
    if ob.type in freeze.BAKE_TYPES and ob.data is not None:
        freeze.bake_into_data(ob, b_new.inverted_safe() @ b_old)
    _keep_children(ob, w_old, frame @ b_new)
    return True


def match_pivot(ob, world_point):
    """Maya Match Pivots (P7): ``ob``'s pivot moves to ``world_point``; nothing else moves."""
    c = ob.matrix_world.inverted_safe() @ Vector(world_point)
    if c.length < EPS:
        return False
    freeze.shift_pivot(ob, c)
    return True


# --- the "Maya Pivot" transform orientation (Move and Rotate Custom axes) --------------------

def _find_view3d(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return window, area, region
    return None, None, None


def set_custom_orientation(context, axes):
    """Create / update the picked pivot axes for both Move and Rotate."""
    scene = context.scene
    slots = scene.transform_orientation_slots
    orient = _orientation(scene)
    if orient is None:
        window, area, region = _find_view3d(context)
        kw = {"window": window, "area": area, "region": region} if area is not None else {}
        prev = slots[0].type
        try:
            with context.temp_override(**kw):
                bpy.ops.transform.create_orientation(name=ORIENT_NAME, use=True, overwrite=True)
        except RuntimeError:
            # edit mode builds it from the selection, which can fail (nothing / a closed shell selected);
            # the view's axes always work (the matrix is replaced below) — step 77
            try:
                with context.temp_override(**kw):
                    bpy.ops.transform.create_orientation(name=ORIENT_NAME, use=True, use_view=True,
                                                         overwrite=True)
            except RuntimeError:
                return False
        orient = _orientation(scene)
        slots[0].type = prev if prev != ORIENT_NAME else 'GLOBAL'
        if orient is None:
            return False
    orient.matrix = axes
    for index in PIVOT_SLOTS:
        slots[index].type = ORIENT_NAME
    return True


def _orientation(scene):
    for slot in scene.transform_orientation_slots:
        co = slot.custom_orientation
        if co is not None and co.name == ORIENT_NAME:
            return co
    try:
        slot = scene.transform_orientation_slots[MOVE_SLOT]
        old = slot.type
        slot.type = ORIENT_NAME
        co = slot.custom_orientation
        slot.type = old
        return co
    except TypeError:
        return None


def leave_custom_orientation(scene, to='GLOBAL'):
    for index in PIVOT_SLOTS:
        slot = scene.transform_orientation_slots[index]
        if slot.type == ORIENT_NAME:
            slot.type = to


# --- watcher ---------------------------------------------------------------------------------

_watch = {"running": False, "snaps": {}, "last_op": None}


def _op_key():
    ops = bpy.context.window_manager.operators
    if not len(ops):
        return None
    return (ops[-1].as_pointer(), len(ops), ops[-1].bl_idname)


def _transform_running():
    for window in bpy.context.window_manager.windows:
        if any(op.bl_idname.startswith("TRANSFORM_OT_") for op in window.modal_operators):
            return True
    return False


def pivot_mode(context=None):
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    return scene is not None and context.mode == 'OBJECT' and scene.tool_settings.use_transform_data_origin


def _selected(context):
    return [ob for ob in context.selected_objects]


def process(context=None):
    """Rewrite the selected objects if a transform registered since the last call; re-snapshot."""
    context = context or bpy.context
    key = _op_key()
    snaps = _watch["snaps"]
    turned = None
    if key != _watch["last_op"] and key is not None and key[2].startswith("TRANSFORM_OT_") and context.mode == 'OBJECT':
        for ob in _selected(context):
            snap = snaps.get(ob.name)
            if snap is not None:
                axes = rewrite(ob, snap)
                if axes is not None:
                    turned = axes
        if turned is not None:
            set_custom_orientation(context, turned)
        context.view_layer.update()
    _watch["last_op"] = key
    _watch["snaps"] = {ob.name: snapshot(ob) for ob in _selected(context)}
    return turned


def _tick():
    try:
        if _transform_running():
            return POLL / 2
        context = bpy.context
        if context.mode == 'OBJECT':
            process(context)
        if pivot_mode(context):
            return POLL
    except (ReferenceError, AttributeError, RuntimeError):
        pass
    _watch["running"] = False
    return None


def watch():
    """Start watching origin-only transforms (idempotent)."""
    if _watch["running"]:
        return
    _watch["running"] = True
    _watch["last_op"] = _op_key()
    try:
        _watch["snaps"] = {ob.name: snapshot(ob) for ob in _selected(bpy.context)}
    except AttributeError:
        _watch["snaps"] = {}
    bpy.app.timers.register(_tick, first_interval=POLL)


def stop():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _watch.update(running=False, snaps={}, last_op=None)


# --- pivot point per mode (P10/P11) ------------------------------------------------------------

_last_mode = [None]


def maya_pivot_point(ts, mode):
    """Switch Blender's pivot point to the Maya one of ``mode`` (only from the other Maya value)."""
    want = MAYA_PIVOT_POINT.get(mode)
    if want is None or ts.transform_pivot_point == want:
        return False
    if ts.transform_pivot_point in MAYA_PIVOT_POINT.values():
        ts.transform_pivot_point = want
        return True
    return False


_last_lead = [None]


def follow_lead(context, scene):
    """The "Maya Pivot" axes belong to the object whose pivot was turned (Maya keeps pivot axes per object):
    a new lead with a turned pivot gets its own axes, one without goes back to Object axes (step 97: the next
    object was moved along the previous object's pivot axes)."""
    ob = context.view_layer.objects.active if context.mode == 'OBJECT' else None
    key = ob.as_pointer() if ob is not None else None
    if key == _last_lead[0]:
        return
    _last_lead[0] = key
    if ob is None or not any(scene.transform_orientation_slots[index].type == ORIENT_NAME for index in PIVOT_SLOTS):
        return
    if PROP in ob:
        orient = _orientation(scene)
        if orient is not None:
            rot = ob.matrix_world.to_3x3().normalized().to_quaternion() @ Quaternion(ob[PROP])
            orient.matrix = rot.to_matrix()
    else:
        leave_custom_orientation(scene, 'LOCAL')


@bpy.app.handlers.persistent
def _on_depsgraph(scene, _depsgraph):
    try:
        context = bpy.context
        mode = context.mode
    except AttributeError:
        return
    if mode != _last_mode[0]:
        _last_mode[0] = mode
        maya_pivot_point(scene.tool_settings, mode)
    try:
        follow_lead(context, scene)
    except (AttributeError, ReferenceError, TypeError):
        pass


# --- operators -------------------------------------------------------------------------------

class _PivotOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)


class ALLSET_OT_reset_pivot(_PivotOp, bpy.types.Operator):
    """Put the pivot back on the object's own origin and reset its orientation, without moving
    the geometry (Maya pivot edit RMB > Reset Pivot)"""
    bl_idname = "allset.reset_pivot"
    bl_label = "Reset Pivot"

    position: BoolProperty(name="Position", default=True)
    orientation: BoolProperty(name="Orientation", default=True)

    def execute(self, context):
        for ob in freeze.parents_first(_selected(context)):
            context.view_layer.update()
            reset_pivot(ob, self.position, self.orientation)
        if self.orientation:
            leave_custom_orientation(context.scene)
        if _watch["running"]:
            process(context)
        return {'FINISHED'}


class ALLSET_OT_bake_pivot(_PivotOp, bpy.types.Operator):
    """Put the custom pivot orientation into the object's rotation; the geometry stays
    (Maya Modify > Bake Pivot)"""
    bl_idname = "allset.bake_pivot"
    bl_label = "Bake Pivot"

    def execute(self, context):
        n = 0
        for ob in freeze.parents_first(_selected(context)):
            context.view_layer.update()
            n += bake_pivot(ob)
        leave_custom_orientation(context.scene, 'LOCAL')   # Maya: axis mode back to Object (P8)
        if not n:
            results.result(self, "No custom pivot orientation to bake")
        if _watch["running"]:
            process(context)
        return {'FINISHED'}


class ALLSET_OT_match_pivots(_PivotOp, bpy.types.Operator):
    """Move the pivots of the selected objects onto the last selected object's pivot
    (Maya Modify > Match Transformations > Match Pivots)"""
    bl_idname = "allset.match_pivots"
    bl_label = "Match Pivots"

    def execute(self, context):
        lead = context.view_layer.objects.active
        others = [ob for ob in _selected(context) if ob is not lead]
        if lead is None or not others:
            self.report({'WARNING'}, "Select the objects, then the target last")
            return {'CANCELLED'}
        p = lead.matrix_world.translation.copy()
        for ob in freeze.parents_first(others):
            context.view_layer.update()
            match_pivot(ob, p)
        if _watch["running"]:
            process(context)
        return {'FINISHED'}


classes = (ALLSET_OT_reset_pivot, ALLSET_OT_bake_pivot, ALLSET_OT_match_pivots)


def register_handler():
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister_handler():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    stop()
