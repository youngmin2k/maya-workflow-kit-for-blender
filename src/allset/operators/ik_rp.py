# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya ikRPsolver on a kit IK handle (Issue #162).

Maya 2026:
- a new RP handle gets a **default pole vector**: with the chain at its preferred angles, the joint whose offset from
  the start joint has the largest |p × d| (d = start -> end; ties keep the first), pv = d × (p × d) normalised (= that
  joint's offset perpendicular to the chain), length 2 × jointDisplayScale, stored in the handle's parent space
  (world); a straight chain (every |p × d|² < 1e-10) falls back to e_k ⊥ d, k = the smallest |component| of d in the
  start joint's frame, pv = d × n;
- for an RP handle on exactly 3 joints whose middle joint has
  preferredAngle ≈ 0, jointOrient ≈ 0 (≤ 3e-5° bends, ≥ 1e-4° doesn't) and rotate 0 and a straight chain, ``ikHandle``
  first writes preferredAngle (0, 90, 0) on the middle joint, so the pv comes from that bent pose (along X with equal
  bones: (1.414, 0, 1.414)) and the chain bends that way; every other straight chain (4+ joints, a jointOrient on the
  middle joint) gets the fallback pv and a 3+ bone chain stays straight;
- the solve plane: v = pv perpendicular to u = root -> goal, turned about u by +twist (right-handed); Pole Vector
  constraint = pv follows (target − start joint).

Blender (4.5): the IK constraint's pole target at root + R(u, twist)·pv with
pole_angle = −signed_angle(base bone X -> rest bend direction about the rest chain axis) gives Maya's elbow for
reachable goals (out of reach Blender's IK keeps a sliver of bend). A straight chain
needs a starting bend (Blender's IK starts from the pose): the in-between joints get their preferred angle, else 1°
toward the pole (0.01 rad is enough, less is not).

Kit pieces: the handle's custom properties ``poleVectorX/Y/Z`` (Maya units, Maya axes) and ``twist`` (degrees) are
its Channel Box channels; a hidden empty ``<handle>Pole`` (at the chain's start joint + the turned pv, world, like
the skeleton) is the IK pole target, parented to the start joint's parent so it moves with the skeleton; ``update``
(depsgraph / frame handlers) keeps it at start joint + R(u, twist)·pv and, after Constrain > Pole Vector, pv = target −
start joint.
"""

import math

import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix, Quaternion, Vector

from . import units

PV = ("poleVectorX", "poleVectorY", "poleVectorZ")
TWIST = "twist"
HELPER = "allset_pole_helper"          # handle -> its pole helper empty
OWNER = "allset_pole_of"               # helper -> its handle
POLE_OBJECT = "allset_pole_object"     # handle -> the Pole Vector constraint's target
PREBEND = math.radians(1.0)
# Maya world axes in Blender world (joints.MAYA_WORLD): Maya X -> X, Y -> Z, Z -> -Y
_M2B = ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))


def to_blender(m):
    return Vector((m[0], -m[2], m[1]))


def to_maya(b):
    return Vector((b[0], b[2], -b[1]))


def _signed(a, b, axis):
    ang = a.angle(b)
    return ang if axis.dot(a.cross(b)) >= 0.0 else -ang


def chain_points(arm, bones, preferred=True):
    """World positions of the chain joints (start, in-between, end) with the in-between joints at their preferred
    angles (Maya computes the default pole vector that way) — FK from the start joint's pose."""
    from .rig_maya import PREFERRED_PROP
    root = bones[0]
    m = arm.matrix_world @ root.matrix
    pts = [m.translation.copy()]
    for prev, b in zip(bones, bones[1:]):
        local = prev.bone.matrix_local.inverted() @ b.bone.matrix_local
        # Maya sets every DOF to its preferred angle (default 0 = the rest)
        rot = Matrix.Identity(4) if preferred else b.matrix_basis.to_3x3().to_4x4()
        if preferred and PREFERRED_PROP in b:
            from mathutils import Euler
            rot = Euler([math.radians(a) for a in b[PREFERRED_PROP]], 'XYZ').to_matrix().to_4x4()
        m = m @ local @ rot
        pts.append(m.translation.copy())
    end = bones[-1]
    pts.append((m @ Vector((0.0, end.bone.length, 0.0))).copy())
    return pts


def straight_fallback(d_local):
    """Maya's straight-chain normal in the start joint's frame: the axis e_k of the smallest |component|
    of d, made perpendicular to d."""
    ax, ay, az = (abs(c) for c in d_local)
    if az <= ay:
        k = 0 if az > ax else 2
    else:
        k = 1 if ay <= ax else 0
    e = Vector((0.0, 0.0, 0.0))
    e[k] = 1.0
    return e * d_local.length_squared - d_local * d_local[k]


def default_pole_vector(points, length, start_frame=None):
    """The default pole vector (world, like Maya) for the chain ``points`` (start .. end): the in-between joint with the
    largest |p × d|, its offset perpendicular to d; a straight chain: the A2 fallback in ``start_frame`` (the start
    joint's Maya axes in world, a 3x3; world axes when None)."""
    p0 = points[0]
    d = points[-1] - p0
    best, best_n2 = None, 0.0
    for p in points[1:-1]:
        n = (p - p0).cross(d)
        if best is None or n.length_squared > best_n2 + 1e-10:
            best, best_n2 = n, n.length_squared
    if best is None or best_n2 < 1e-12 * max(d.length_squared, 1e-12) ** 2:
        frame = start_frame if start_frame is not None else Matrix(_M2B).transposed()
        n = frame @ straight_fallback(frame.inverted() @ d)
        v = d.cross(n)
    else:
        v = d.cross(best)
    return v.normalized() * length


# R4: Maya writes the middle joint's preferred angle (0, 90, 0) — 90° about its Maya Y = the bone's Z
# (joints.JOINT_AXES), as pose Euler XYZ in bone axes like rig_maya.PREFERRED_PROP — when the 3-joint chain is
# straight. Straightness: the kit takes 1e-3 of the chain length; jointOrient: 1e-6 rad (5.7e-5°).
AUTO_PREFERRED = (0.0, 0.0, 90.0)
STRAIGHT_TOL = 1e-3
JO_TOL = 1e-6


def maya_axes(arm, bone):
    """World rotation (3x3) of the joint's Maya axes at rest (joints.maya_frame for a Bone)."""
    from .joints import JOINT_AXES, MAYA_FRAME
    f = (arm.matrix_world.to_3x3().normalized() @ bone.matrix_local.to_3x3().normalized()) @ JOINT_AXES
    q = bone.get(MAYA_FRAME)
    return f @ Quaternion(q).to_matrix() if q is not None and len(q) == 4 else f


def auto_preferred(arm, bones):
    """True when Maya's ikHandle would write preferredAngle (0, 90, 0) on the middle joint (R4)."""
    from .rig_maya import PREFERRED_PROP
    if len(bones) != 2:
        return False
    mid = bones[1]
    if PREFERRED_PROP in mid and any(abs(a) > 1e-5 for a in mid[PREFERRED_PROP]):
        return False
    if mid.matrix_basis.to_quaternion().angle > 1e-9:
        return False
    rel = maya_axes(arm, bones[0].bone).inverted() @ maya_axes(arm, mid.bone)
    if rel.to_quaternion().angle > JO_TOL:
        return False
    p0, p1, p2 = bones[0].bone.head_local, mid.bone.head_local, mid.bone.tail_local
    d = p2 - p0
    if d.length < 1e-12:
        return False
    off = (p1 - p0).cross(d.normalized()).length
    return off <= STRAIGHT_TOL * d.length


def pole_angle(arm, bones, bend):
    """Blender pole_angle reproducing Maya's plane: −signed angle (about the rest chain axis) from the base bone's X
    to ``bend`` (armature-space rest direction of the elbow side), both made perpendicular to the axis."""
    root, end = bones[0].bone, bones[-1].bone
    u = (end.tail_local - root.head_local).normalized()
    x = root.matrix_local.to_3x3().col[0]
    x = (x - u * x.dot(u)).normalized()
    e = (bend - u * bend.dot(u)).normalized()
    return -_signed(x, e, u)


def _rest_bend(bones, fallback):
    """The rest chain's bend direction (armature space): the farthest in-between joint's perpendicular offset, else
    ``fallback`` (a straight rest chain)."""
    root, end = bones[0].bone, bones[-1].bone
    p0 = root.head_local
    d = end.tail_local - p0
    best, best_n2 = None, 0.0
    for b in bones[1:]:
        n = (b.bone.head_local - p0).cross(d)
        if best is None or n.length_squared > best_n2 + 1e-10:
            best, best_n2 = n, n.length_squared
    if best is None or best_n2 < 1e-10 * max(d.length_squared, 1e-12) ** 2:
        return fallback, True
    return d.cross(best), False


def _prebend(arm, bones, bend):
    """Give a straight chain's in-between joints a starting bend toward ``bend`` (armature space): their preferred
    angle when they have one (Maya bends a straight chain that way), else 1°. Only joints at rest."""
    from .rig_maya import PREFERRED_PROP
    from mathutils import Euler
    u = (bones[-1].bone.tail_local - bones[0].bone.head_local).normalized()
    axis = u.cross(bend - u * bend.dot(u))
    for b in bones[1:]:
        if b.matrix_basis.to_quaternion().angle > 1e-9:
            continue
        if PREFERRED_PROP in b and any(abs(a) > 1e-9 for a in b[PREFERRED_PROP]):
            q = Euler([math.radians(a) for a in b[PREFERRED_PROP]], 'XYZ').to_quaternion()
        else:
            local = b.bone.matrix_local.to_3x3().inverted() @ axis
            q = Quaternion(local.normalized(), -PREBEND)
        if b.rotation_mode == 'QUATERNION':
            b.rotation_quaternion = q
        elif b.rotation_mode == 'AXIS_ANGLE':
            ax, ang = q.to_axis_angle()
            b.rotation_axis_angle = (ang, *ax)
        else:
            b.rotation_euler = q.to_euler(b.rotation_mode)


def _start_frame(arm, root):
    """The start joint's Maya axes in world with its current pose (Maya evaluates at the start joint's rotation)."""
    rest = maya_axes(arm, root.bone)
    pose = (arm.matrix_world.to_3x3().normalized() @ root.matrix.to_3x3().normalized()
            @ root.bone.matrix_local.to_3x3().normalized().inverted() @ arm.matrix_world.to_3x3().normalized().inverted())
    return pose @ rest


def _has_preferred(bones):
    from .rig_maya import PREFERRED_PROP
    return any(PREFERRED_PROP in b and any(abs(a) > 1e-9 for a in b[PREFERRED_PROP]) for b in bones[1:])


def _maya_unit(context=None):
    scene = getattr(context or bpy.context, "scene", None)
    return units.maya_unit(scene) if scene is not None else 1.0


def setup(context, arm, ik_bone, con, handle, display_scale=1.0):
    """Maya RP handle: default pole vector + Twist channels on ``handle``, the hidden pole helper, pole_angle, and a
    starting bend for a straight chain. Returns the helper."""
    from .ik_fk import chain
    bones = chain(ik_bone, con)
    k = _maya_unit(context)
    context.view_layer.update()
    if auto_preferred(arm, bones):
        from .rig_maya import PREFERRED_PROP
        bones[1][PREFERRED_PROP] = list(AUTO_PREFERRED)        # Maya ikHandle (R4)
    pts = chain_points(arm, bones)
    start = _start_frame(arm, bones[0])
    pv = default_pole_vector(pts, 2.0 * display_scale * k, start)
    for i, name in enumerate(PV):
        handle[name] = float(to_maya(pv)[i] / k)
        handle.id_properties_ui(name).update(default=0.0)
    handle[TWIST] = 0.0
    handle.id_properties_ui(TWIST).update(default=0.0, subtype='NONE')
    helper = bpy.data.objects.new(f"{handle.name}Pole", None)
    for col in handle.users_collection or (context.scene.collection,):
        col.objects.link(helper)
        break
    helper.empty_display_type = 'SPHERE'
    helper.empty_display_size = 0.2 * k
    helper.hide_viewport = True
    helper.hide_select = True
    helper.hide_render = True
    helper[OWNER] = handle.name
    # parented to the start joint's parent (bone, or the skeleton object): the helper follows the skeleton without a
    # dependency on the IK chain itself (a Copy Location of the start joint made a cycle — the IK reads the helper —
    # and the GUI evaluated the pole stale)
    helper.parent = arm
    if bones[0].parent is not None:
        helper.parent_type = 'BONE'
        helper.parent_bone = bones[0].parent.name
    helper.matrix_world = Matrix.Translation(arm.matrix_world @ bones[0].head + pv)
    handle[HELPER] = helper
    # Blender's pole angle for Maya's plane (the rest bend; a straight rest chain: the pole direction)
    inv = (arm.matrix_world @ bones[0].matrix @ bones[0].bone.matrix_local.inverted()).to_3x3().inverted()
    bend, straight = _rest_bend(bones, inv @ pv)
    con.pole_target = helper
    con.pole_angle = pole_angle(arm, bones, bend)
    if straight and (len(bones) == 2 or (_has_preferred(bones) and multi_chain(handle) is None)):
        # Maya: a straight 3+ joint chain without preferred angles stays straight
        _prebend(arm, bones, bend)
    update_handle(handle)
    return helper


def handle_root(handle):
    """(armature, start pose bone) of the RP handle's chain (None when the chain is gone)."""
    from .skin import ik_constraints_on
    from .ik_fk import chain
    for arm, pb, con in ik_constraints_on(handle):
        return arm, chain(pb, con)[0]
    return None


def pole_vector(handle):
    return to_blender([float(handle.get(n, 0.0)) for n in PV]) * _maya_unit()


def update_handle(handle, depsgraph=None):
    """Put the handle's pole helper at root + R(u, twist)·pv (and pv = Pole Vector target − start joint)."""
    helper = handle.get(HELPER)
    if helper is None or not isinstance(helper, bpy.types.Object):
        return False
    found = handle_root(handle)
    if found is None:
        return False
    arm, root = found
    k = _maya_unit()
    root_w = arm.matrix_world @ root.head
    target = handle.get(POLE_OBJECT)
    if isinstance(target, bpy.types.Object):
        pv_m = to_maya(target.matrix_world.translation - root_w) / k
        for i, name in enumerate(PV):
            if abs(float(handle.get(name, 0.0)) - pv_m[i]) > 1e-7:
                handle[name] = float(pv_m[i])
    pv = pole_vector(handle)
    goal = handle.matrix_world.translation
    u = goal - root_w
    tw = math.radians(float(handle.get(TWIST, 0.0)))
    off = Quaternion(u.normalized(), tw) @ pv if (abs(tw) > 1e-12 and u.length > 1e-9) else pv
    want = root_w + off
    moved = False
    if (helper.matrix_world.translation - want).length > 1e-7 * max(k, 1e-6):
        helper.matrix_world = Matrix.Translation(want)
        moved = True
    return solve_multi(handle) or moved


def rp_handles():
    return [ob for ob in bpy.data.objects if HELPER in ob]


_busy = []
_count = [-1, 0]           # (last object count seen, the one before): drop orphaned 3+ bone pieces after a removal


@persistent
def _on_update(*_args):
    if _busy:
        return
    _busy.append(1)
    try:
        count = len(bpy.data.objects)
        if count != _count[0]:
            _count[0] = count
            if count < _count[1]:
                drop_orphan_rotations()    # a handle deleted some other way than the kit's Delete
            _count[1] = count
        for handle in rp_handles():
            update_handle(handle)
    except (ReferenceError, AttributeError, RuntimeError):
        pass
    finally:
        _busy.clear()


def set_pole_object(handle, target):
    """Constrain > Pole Vector on a kit RP handle: Maya pv = target − start joint, kept by ``update``."""
    handle[POLE_OBJECT] = target
    update_handle(handle)


def helpers_of(objs):
    """Pole helpers of the handles in ``objs`` (they go with their handle on Delete)."""
    out = []
    for ob in objs:
        try:
            h = ob.get(HELPER)
        except ReferenceError:
            continue
        if isinstance(h, bpy.types.Object) and h not in objs:
            out.append(h)
    return out


def register_handlers():
    for hs in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.frame_change_post):
        if _on_update not in hs:
            hs.append(_on_update)


def unregister_handlers():
    for hs in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.frame_change_post):
        if _on_update in hs:
            hs.remove(_on_update)
    _solvers.clear()


# --- #181: 3+ bone chains bend like Maya ------------------------------------------------------------------
# Maya splits the bend of a chain of three or more bones its own way (operators/ik_rp_multi.py); Blender's IK
# constraint spreads it differently. On such a chain the kit solves Maya's rule and hands each joint's result to a
# Copy Rotation constraint (world space) on its bone, reading a hidden helper empty the solve places: the FK channels
# stay as they are, like under Blender's IK. The IK constraint stays (the handle, Ik Blend, Solver Enable keep working)
# with its influence driven to Ik Blend x (1 - kit), the Copy Rotations to Ik Blend x kit (``MULTI`` on the handle = 1
# while the kit solves). Joint limits, IK stiffness or a second IK handle on the chain keep Blender's IK.

MULTI = "allset_rp_multi"              # handle: 1 while the kit solves its 3+ bone chain
ROT_OWNER = "allset_rp_rot_of"         # bone helper empty -> "<handle>\t<bone>"
ROT_NAME = "Maya IK RP"                # the Copy Rotation constraint on each chain bone
_solvers = {}                          # handle name -> (signature, ik_rp_multi.Solver)


def is_solver_constraint(con):
    """A Copy Rotation that carries the kit's Maya RP solve (not a Maya node of its own: hidden from INPUTS)."""
    t = getattr(con, "target", None)
    return con.type == 'COPY_ROTATION' and t is not None and ROT_OWNER in t.keys()


def multi_chain(handle):
    """(armature, chain pose bones, IK constraint) of a kit RP handle on 3+ bones that Maya's rule solves, else None
    (2 bones, joint limits, IK stiffness, another IK constraint on the chain)."""
    from .skin import ik_constraints_on
    from .ik_fk import chain
    found = ik_constraints_on(handle)
    if len(found) != 1:
        return None
    arm, pb, con = found[0]
    bones = chain(pb, con)
    if len(bones) < 3 or con.use_rotation or not con.use_tail:
        return None
    for b in bones:
        if b.use_ik_limit_x or b.use_ik_limit_y or b.use_ik_limit_z:
            return None
        if b.ik_stiffness_x or b.ik_stiffness_y or b.ik_stiffness_z:
            return None
        if any(c.type in ('IK', 'SPLINE_IK') and c != con for c in b.constraints):
            return None
    return arm, bones, con


def kit_chain(arm, bones, k):
    """(ik_rp_multi.Chain in armature space and Maya units, Maya axes per bone in bone coordinates, a signature of the
    rest data the solver tables depend on)."""
    import numpy as np
    from mathutils import Euler
    from . import ik_rp_multi
    from .joints import _maya_axes
    from .rig_maya import PREFERRED_PROP
    axes = [_maya_axes(b.bone).normalized() for b in bones]
    rest = [b.bone.matrix_local.to_3x3().normalized() @ a for b, a in zip(bones, axes)]
    root = bones[0]
    if root.parent is not None:
        p_rest = root.parent.bone.matrix_local.to_3x3().normalized()
        p_now = root.parent.matrix.to_3x3().normalized()
    else:
        p_rest = p_now = Matrix.Identity(3)
    orients = [p_rest.inverted() @ rest[0]] + [rest[i - 1].inverted() @ rest[i] for i in range(1, len(bones))]
    orients.append(Matrix.Identity(3))
    heads = [b.bone.head_local for b in bones] + [bones[-1].bone.tail_local]
    offsets = [Vector((0.0, 0.0, 0.0))] + [rest[i - 1].inverted() @ ((heads[i] - heads[i - 1]) / k)
                                           for i in range(1, len(heads))]
    preferred = []
    for b, a in zip(bones, axes):
        if PREFERRED_PROP in b and any(abs(v) > 1e-12 for v in b[PREFERRED_PROP]):
            rb = Euler([math.radians(v) for v in b[PREFERRED_PROP]], 'XYZ').to_matrix()
            preferred.append(ik_rp_multi.euler_from_matrix(np.array(a.inverted() @ rb @ a), 0))
        else:
            preferred.append([0.0, 0.0, 0.0])
    preferred.append([0.0, 0.0, 0.0])
    orients_np = [np.array(m) for m in orients]
    chain = ik_rp_multi.Chain(np.array(p_now), np.array(root.head / k), orients_np,
                              [np.array(t) for t in offsets], [0] * len(heads), preferred)
    sig = tuple(round(v, 9) for m in orients_np for v in m.flat) + tuple(round(v, 9) for t in offsets for v in t) \
        + tuple(round(v, 12) for p in preferred for v in p)
    return chain, axes, sig


def _solver(handle, chain, sig):
    """The handle's Maya tables (built once, again when the chain's rest data changes) on the current chain."""
    from . import ik_rp_multi
    got = _solvers.get(handle.name)
    if got is None or got[0] != sig:
        got = _solvers[handle.name] = (sig, ik_rp_multi.Solver(chain))
    solver = got[1]
    solver.chain.parent, solver.chain.origin = chain.parent, chain.origin
    return solver


def _blend_driver(con, handle, kit_part):
    """Influence = Ik Blend x kit (the kit's Copy Rotation) or x (1 - kit) (Blender's IK)."""
    from .ik_fk import IK_BLEND
    expr = "ikBlend * kit" if kit_part else "ikBlend * (1 - kit)"
    ad = con.id_data.animation_data
    old = ad.drivers.find(con.path_from_id("influence")) if ad is not None else None
    if old is not None and old.driver.type == 'SCRIPTED' and old.driver.expression == expr:
        return old
    fc = con.driver_add("influence")
    drv = fc.driver
    for v in list(drv.variables):
        drv.variables.remove(v)
    for name, prop in (("ikBlend", IK_BLEND), ("kit", MULTI)):
        var = drv.variables.new()
        var.name = name
        var.type = 'SINGLE_PROP'
        var.targets[0].id_type = 'OBJECT'
        var.targets[0].id = handle
        var.targets[0].data_path = f'["{prop}"]'
    drv.type = 'SCRIPTED'
    drv.expression = expr
    return fc


def ensure_multi(handle, arm, bones, con):
    """The kit's Maya RP pieces of a 3+ bone chain: a hidden helper empty and a Copy Rotation per bone, the influence
    drivers. Returns {bone name: helper}."""
    from . import ik_fk
    ik_fk.ensure_blend(arm, bones[-1], con)
    if MULTI not in handle:
        handle[MULTI] = 0
    _blend_driver(con, handle, False)
    out = {}
    for b in bones:
        rot = next((c for c in b.constraints if is_solver_constraint(c)), None)
        if rot is None:
            # in no collection (not a Maya node: no Outliner row, not in scene loops), kept by a fake user; a
            # constraint target outside the scene still evaluates
            helper = bpy.data.objects.new(f"{handle.name}_{b.name}Rot", None)
            helper.use_fake_user = True
            helper.empty_display_size = 0.1 * _maya_unit()
            helper.hide_viewport = helper.hide_select = helper.hide_render = True
            helper[ROT_OWNER] = f"{handle.name}\t{b.name}"
            rot = b.constraints.new('COPY_ROTATION')
            rot.name = ROT_NAME
            rot.target = helper
            rot.mix_mode = 'REPLACE'
            rot.target_space = rot.owner_space = 'WORLD'
        _blend_driver(rot, handle, True)
        if rot.mute != con.mute:            # Solver Enable off (or IK Solvers off) stops the kit's solve too
            rot.mute = con.mute
        out[b.name] = rot.target
    return out


def solve_multi(handle):
    """Solve a 3+ bone RP chain Maya's way and place its bone helpers. False when Blender's IK does the chain (the
    handle's ``MULTI`` follows) or nothing moved."""
    import numpy as np
    found = multi_chain(handle)
    if found is None:
        if handle.get(MULTI):
            handle[MULTI] = 0
            handle.update_tag()            # an ID property write tags nothing: the influence drivers read it
        return False
    arm, bones, con = found
    helpers = ensure_multi(handle, arm, bones, con)
    if not handle.get(MULTI):
        handle[MULTI] = 1
        handle.update_tag()
    k = _maya_unit()
    chain, axes, sig = kit_chain(arm, bones, k)
    solver = _solver(handle, chain, sig)
    goal = (arm.matrix_world.inverted() @ handle.matrix_world.translation) / k
    u = handle.matrix_world.translation - arm.matrix_world @ bones[0].head
    tw = math.radians(float(handle.get(TWIST, 0.0))) if u.length > 1e-9 else 0.0
    pv = arm.matrix_world.to_3x3().inverted() @ pole_vector(handle)
    x, turn, pos = solver.solve(np.array(goal), np.array(pv), tw)
    _p, frames = solver.chain.frames(x)
    world3 = arm.matrix_world.to_3x3()
    changed = False
    for i, b in enumerate(bones):
        w = Matrix((turn @ frames[i]).tolist())
        m = (world3 @ (w @ axes[i].transposed())).to_4x4()
        m.translation = arm.matrix_world @ Vector((pos[i] * k).tolist())
        helper = helpers[b.name]
        if any(abs(a - c) > 1e-9 for ra, rc in zip(helper.matrix_world, m) for a, c in zip(ra, rc)):
            helper.matrix_world = m
            changed = True
    return changed


def drop_orphan_rotations():
    """Remove the kit's Copy Rotations and bone helpers whose handle is gone (Delete of the handle)."""
    names = {ob.name for ob in bpy.data.objects}
    for ob in [o for o in bpy.data.objects if ROT_OWNER in o.keys()]:
        if str(ob[ROT_OWNER]).split("\t")[0] in names:
            continue
        for arm in bpy.data.objects:
            if arm.type != 'ARMATURE' or arm.pose is None:
                continue
            for pb in arm.pose.bones:
                for c in [c for c in pb.constraints if c.type == 'COPY_ROTATION' and c.target == ob]:
                    pb.constraints.remove(c)
        bpy.data.objects.remove(ob)
