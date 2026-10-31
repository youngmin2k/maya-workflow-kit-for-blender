# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya IK / FK switching on kit IK handles (Issue #133).

A kit IK handle is the ``ikHandleN`` empty an IK constraint targets (operators/skin.create_ik). Maya's handle
attribute **Ik Blend** (keyable, default 1) is the handle's custom property
``ikBlend``, and the IK constraint's Influence is driven by it — so the Channel Box shows "Ik Blend" on the handle, S
and Set IK/FK Key key it on the handle like Maya. Like Maya's ``ikFK`` the chain joints get
an ``ikBlend`` property connected (driven) from the handle.

Maya 2026 rules:

- Maya writes the IK solution into the joints' rotate attributes while IK is on; at Ik Blend 0 the joints use those
  rotate values. Blender's IK constraint leaves the bone channels alone, so every kit command below first writes the
  bones' *visual* rotation (the solved pose) into their channels — the kit equivalent of Maya's rotate values.
- **Set IK/FK Key** (``ikFK(0, sel)``): keys on the handle every keyable channel (translate / rotate / scale /
  visibility, Ik Blend — in auto / out clamped), the chain joints' rotate X / Y / Z (= the solved pose), the chain
  root's translate and preferred angle (out step). Maya also keys the handle's Twist and Pole Vector — or, when a Pole
  Vector constraint drives it, the pole object's translate: the kit RP handle's ``twist`` /
  ``poleVectorX/Y/Z`` channels and the pole object's
  location. Maya's Offset / Roll exist on the kit's spline handles only, not on RP handles.
- **Enable IK Solver**: a global check (default off); each use flips it and sets Ik Blend of
  the selected handles — or of the handles whose chain holds a selected joint — to the new state, keeping the
  joints' rotation (so switching IK off keeps the IK pose). Nothing selected: Maya's error.
- **Move IK to FK**: the handle moves to the FK end joint (the chain evaluated without IK); Ik Blend
  stays as it is.
"""

import bpy
from mathutils import Vector

from .. import results

IK_BLEND = "ikBlend"
NO_HANDLE = "Select a handle, joint or an ikfk connected object."     # Maya's error text


# --- handles and chains -------------------------------------------------------------------------------------------

def ik_constraints(context):
    """[(armature, constrained pose bone, IK constraint)] of the selected handles, or of the IK chains holding a
    selected joint (pose bones of the active armature in pose mode)."""
    from . import skin
    out, seen = [], set()

    def add(arm, pb, con):
        if con.as_pointer() not in seen:
            seen.add(con.as_pointer())
            out.append((arm, pb, con))

    for ob in context.selected_objects:
        if ob.type != 'ARMATURE':
            for arm, pb, con in skin.ik_constraints_on(ob):
                add(arm, pb, con)
    arm = context.active_object
    if arm is not None and arm.type == 'ARMATURE' and arm.mode == 'POSE':
        picked = {pb.name for pb in (context.selected_pose_bones or ())}
        for pb in arm.pose.bones:
            for con in pb.constraints:
                if con.type == 'IK' and con.target is not None and con.target.type != 'ARMATURE':
                    if picked & {b.name for b in chain(pb, con)}:
                        add(arm, pb, con)
    return out


def chain(pb, con):
    """The pose bones an IK constraint moves, root first."""
    out, cur = [], pb
    while cur is not None and (con.chain_count == 0 or len(out) < con.chain_count):
        out.append(cur)
        cur = cur.parent
    return out[::-1]


# --- Ik Blend -----------------------------------------------------------------------------------------------------

def _drive(owner, path, handle):
    fc = owner.driver_add(path)
    drv = fc.driver
    drv.type = 'AVERAGE'
    for v in list(drv.variables):
        drv.variables.remove(v)
    var = drv.variables.new()
    var.name = "ikBlend"
    var.type = 'SINGLE_PROP'
    var.targets[0].id_type = 'OBJECT'
    var.targets[0].id = handle
    var.targets[0].data_path = f'["{IK_BLEND}"]'
    return fc


def _driven(arm, path):
    ad = arm.animation_data
    return ad is not None and ad.drivers.find(path) is not None


def ensure_blend(arm, pb, con):
    """Give the constraint's handle its Ik Blend property and drive the Influence (and the chain joints' ikBlend)
    from it. Returns the handle (None = the target is no handle object)."""
    handle = con.target
    if handle is None or handle.type == 'ARMATURE':
        return None
    if IK_BLEND not in handle.keys():
        handle[IK_BLEND] = float(con.influence)
        handle.id_properties_ui(IK_BLEND).update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0, default=1.0)
    path = con.path_from_id("influence")
    if not _driven(arm, path):
        _drive(con, "influence", handle)
    for bone in chain(pb, con):
        if IK_BLEND not in bone.keys():
            bone[IK_BLEND] = float(handle[IK_BLEND])
            bone.id_properties_ui(IK_BLEND).update(min=0.0, max=1.0, default=1.0)
        if not _driven(arm, bone.path_from_id(f'["{IK_BLEND}"]')):
            _drive(bone, f'["{IK_BLEND}"]', handle)
    return handle


def set_blend(arm, pb, con, value):
    """Ik Blend = ``value`` (the handle property when the constraint has a handle, else the Influence itself)."""
    handle = ensure_blend(arm, pb, con)
    if handle is not None:
        handle[IK_BLEND] = float(value)
        handle.update_tag()
    con.influence = float(value)
    arm.update_tag()


def blend_of(con):
    handle = con.target
    if handle is not None and IK_BLEND in handle.keys():
        return float(handle[IK_BLEND])
    return float(con.influence)


# --- pose helpers -------------------------------------------------------------------------------------------------

def visual_bases(arm, bones):
    """{bone name: matrix_basis giving the bone's current (constrained) pose} — Maya's rotate values under IK."""
    return {pb.name: arm.convert_space(pose_bone=pb, matrix=pb.matrix, from_space='POSE', to_space='LOCAL')
            for pb in bones}


def write_rotation(pb, basis):
    q = basis.to_quaternion()
    if pb.rotation_mode == 'QUATERNION':
        if q.dot(pb.rotation_quaternion) < 0.0:
            q.negate()
        pb.rotation_quaternion = q
    elif pb.rotation_mode == 'AXIS_ANGLE':
        axis, angle = q.to_axis_angle()
        pb.rotation_axis_angle = (angle, *axis)
    else:
        pb.rotation_euler = q.to_euler(pb.rotation_mode, pb.rotation_euler)


def rotation_path(pb):
    return {'QUATERNION': "rotation_quaternion", 'AXIS_ANGLE': "rotation_axis_angle"}.get(pb.rotation_mode,
                                                                                           "rotation_euler")


def fk_end(arm, pb, con):
    """World position of the chain's end joint with the chain posed by its own channels (no IK)."""
    bones = chain(pb, con)
    root = bones[0]
    if root.parent is not None:
        m = root.parent.matrix @ (root.parent.bone.matrix_local.inverted() @ root.bone.matrix_local)
    else:
        m = root.bone.matrix_local.copy()
    m = m @ root.matrix_basis
    for prev, b in zip(bones, bones[1:]):
        m = m @ (prev.bone.matrix_local.inverted() @ b.bone.matrix_local) @ b.matrix_basis
    end = bones[-1]
    tip = m @ Vector((0.0, end.bone.length, 0.0)) if con.use_tail else m.translation
    return arm.matrix_world @ tip


# --- keys ---------------------------------------------------------------------------------------------------------

def _key(owner, path, frame, group, index=-1, interp=None):
    """Key ``path`` with Maya's auto tangents (Auto Clamped + Continuous Acceleration) or ``interp``."""
    owner.keyframe_insert(path, index=index, frame=frame, group=group)
    from .. import compat
    full = owner.path_from_id(path) if owner is not owner.id_data else path
    for fc in compat.id_fcurves(owner.id_data):
        if fc.data_path == full and (index < 0 or fc.array_index == index):
            fc.auto_smoothing = 'CONT_ACCEL'
            if interp is not None:
                for kp in fc.keyframe_points:
                    if abs(kp.co.x - frame) < 1e-6:
                        kp.interpolation = interp
            fc.update()


def _key_rp_channels(handle, frame):
    """Twist + Pole Vector of a kit RP handle, or the pole object's translate when a Pole Vector
    constraint drives the vector (Maya keys the constraint's target then, not the driven poleVector)."""
    from . import ik_rp
    if ik_rp.HELPER not in handle.keys():
        return
    if ik_rp.TWIST in handle.keys():
        _key(handle, f'["{ik_rp.TWIST}"]', frame, handle.name)
    pole = handle.get(ik_rp.POLE_OBJECT)
    if isinstance(pole, bpy.types.Object):
        _key(pole, "location", frame, pole.name)
        return
    for name in ik_rp.PV:
        if name in handle.keys():
            _key(handle, f'["{name}"]', frame, handle.name)


def set_ik_fk_key(context, found, frame=None):
    """Maya Set IK/FK Key on ``found`` (ik_constraints). Returns the handles keyed."""
    from . import rig_maya
    frame = context.scene.frame_current if frame is None else frame
    done = []
    for arm, pb, con in found:
        handle = ensure_blend(arm, pb, con)
        bones = chain(pb, con)
        bases = visual_bases(arm, bones)
        for b in bones:
            write_rotation(b, bases[b.name])
        if handle is not None:
            for path in ("location", "rotation_euler" if handle.rotation_mode not in ('QUATERNION', 'AXIS_ANGLE')
                         else rotation_path(handle), "scale"):
                _key(handle, path, frame, handle.name)
            _key(handle, "hide_viewport", frame, handle.name, interp='CONSTANT')
            _key(handle, f'["{IK_BLEND}"]', frame, handle.name)
            _clamped_out(handle, frame)
            _key_rp_channels(handle, frame)
            done.append(handle)
        for b in bones:
            _key(b, rotation_path(b), frame, b.name)
            if rig_maya.PREFERRED_PROP in b.keys():
                _key(b, f'["{rig_maya.PREFERRED_PROP}"]', frame, b.name, interp='CONSTANT')
        _key(bones[0], "location", frame, bones[0].name)
        arm.update_tag()
    return done


def clamped_slope(keys, i):
    """Maya clamped tangent slope at key ``i`` of [(frame, value)]: the spline slope (to the one neighbour at an
    end, else across both neighbours), flat where the key is a local extreme (no overshoot). Checked on the Maya
    Set IK/FK Key curve 1 -> 0 over frames 1 / 10: Ik Blend 0.44582 at frame 5."""
    f, v = keys[i]
    if len(keys) < 2:
        return 0.0
    if i == 0:
        return (keys[1][1] - v) / (keys[1][0] - f)
    if i == len(keys) - 1:
        return (v - keys[i - 1][1]) / (f - keys[i - 1][0])
    (pf, pv), (nf, nv) = keys[i - 1], keys[i + 1]
    if (v >= pv and v >= nv) or (v <= pv and v <= nv):
        return 0.0
    return (nv - pv) / (nf - pf)


def _clamped_out(handle, frame):
    """Ik Blend keys: in auto / out clamped (Maya IK/FK keys). Auto = Auto Clamped with Continuous Acceleration
   ; the clamped out side is a free handle on Maya's clamped slope, recomputed for every
    key because a clamped tangent follows its neighbours."""
    from .. import compat
    for fc in compat.id_fcurves(handle):
        if fc.data_path != f'["{IK_BLEND}"]':
            continue
        fc.auto_smoothing = 'CONT_ACCEL'
        pts = sorted(fc.keyframe_points, key=lambda k: k.co.x)
        keys = [(k.co.x, k.co.y) for k in pts]
        for i, kp in enumerate(pts):
            kp.handle_left_type = 'AUTO_CLAMPED'
            if i + 1 < len(pts):
                d = (keys[i + 1][0] - keys[i][0]) / 3.0
                kp.handle_right_type = 'FREE'
                kp.handle_right = (keys[i][0] + d, keys[i][1] + clamped_slope(keys, i) * d)
            else:
                kp.handle_right_type = 'AUTO_CLAMPED'
        fc.update()


# --- operators ----------------------------------------------------------------------------------------------------

class ALLSET_OT_ik_fk_key(bpy.types.Operator):
    """Maya Set IK/FK Key: key the selected IK handles (Ik Blend included) and their joints' rotation"""
    bl_idname = "allset.ik_fk_key"
    bl_label = "Set IK/FK Key"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        found = ik_constraints(context)
        if not found:
            self.report({'ERROR'}, NO_HANDLE)
            return {'CANCELLED'}
        set_ik_fk_key(context, found)
        context.view_layer.update()
        results.result(self, f"Set IK/FK key on {len(found)} handle(s)")
        return {'FINISHED'}


# IK/FK switch menu check (off by default; kit session state, not saved)
_STATE = {"on": False}


class ALLSET_OT_ik_solver_toggle(bpy.types.Operator):
    """Maya Enable IK Solver: switch the selected IK handles between IK (Ik Blend 1) and FK (Ik Blend 0) keeping
    the pose"""
    bl_idname = "allset.ik_solver_toggle"
    bl_label = "Enable IK Solver"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        state = _STATE["on"] = not _STATE["on"]        # Maya flips the check first, then looks for handles
        found = ik_constraints(context)
        if not found:
            self.report({'ERROR'}, NO_HANDLE)
            return {'CANCELLED'}
        for arm, pb, con in found:
            bones = chain(pb, con)
            bases = visual_bases(arm, bones)
            set_blend(arm, pb, con, 1.0 if state else 0.0)
            for b in bones:
                write_rotation(b, bases[b.name])
        context.view_layer.update()
        results.result(self, f"Updated {len(found)} handle{'s' if len(found) != 1 else ''}.")
        return {'FINISHED'}


class ALLSET_OT_move_ik_to_fk(bpy.types.Operator):
    """Maya Move IK to FK: move the selected IK handles to the end of their FK chains"""
    bl_idname = "allset.move_ik_to_fk"
    bl_label = "Move IK to FK"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        found = [(a, p, c) for a, p, c in ik_constraints(context) if c.target is not None]
        if not found:
            from .maya_errors import MOVE_IK_TO_FK
            self.report({'ERROR'}, MOVE_IK_TO_FK)       # Maya 2026
            return {'CANCELLED'}
        for arm, pb, con in found:
            mw = con.target.matrix_world.copy()
            mw.translation = fk_end(arm, pb, con)
            con.target.matrix_world = mw
        context.view_layer.update()
        results.result(self, f"Moved {len(found)} IK handle(s) to FK")
        return {'FINISHED'}


# Issue #146: Maya draws Enable IK Solver as a check item, so the hand
# sees the state. The menu draws it as this WindowManager property (``("prop", ...)`` kind, ui/menu_map.py); a click
# runs the operator above (undo step, report) instead of only flipping the value.
def _get_solver(_self):
    return _STATE["on"]


def _set_solver(_self, value):
    if bool(value) == _STATE["on"]:
        return
    try:
        bpy.ops.allset.ik_solver_toggle('EXEC_DEFAULT', True)
    except RuntimeError:
        pass                     # nothing selected: Maya's error, the check flips anyway (Maya flips first)


def register_props():
    bpy.types.WindowManager.allset_ik_solver = bpy.props.BoolProperty(
        name="Enable IK Solver", get=_get_solver, set=_set_solver,
        description="Switch the selected IK handles between IK (Ik Blend 1) and FK (Ik Blend 0) keeping the pose "
                    "(Maya Key > IK/FK Keys > Enable IK Solver)")


def unregister_props():
    del bpy.types.WindowManager.allset_ik_solver


classes = (ALLSET_OT_ik_fk_key, ALLSET_OT_ik_solver_toggle, ALLSET_OT_move_ik_to_fk)
