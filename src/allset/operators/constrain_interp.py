# SPDX-License-Identifier: GPL-3.0-or-later
"""#168: Maya orient / parent constraint Interp Type for the kit's multi-target groups (constrain_multi).

Maya: every target gives a quaternion
q_i = canon(rotation(targetParent · constraintParent⁻¹)) ⊗ q_Euler(rotate) [⊗ q_Euler(targetOffsetRotate), parent
constraint with offset, applied first]; the matrix part has w >= 0, the Euler parts keep their sign. Then
- Average (1, the default, like Maya): normalize(Σ w_i q_i), no hemisphere alignment;
- Shortest (2) / Longest (3): acc = q_0, acc = slerp(acc, q_i, w_i / W_total) the short / long way;
- No Flip (0): Shortest and Longest are both built, the one turning (1, 1, 1) closer to where the previous output
  turned it wins (tie: Longest); the previous output starts as the output when the constraint was made;
- Cache (4): uses interpCache, which only ``cmds.orientConstraint(createCache=...)`` writes (the kit has no cache: 0 =
  No Flip);
- fewer than 2 targets with No Flip / Cache = Average; total weight <= 1e-10 = restRotate (the output at creation).
Worst 2e-6 deg against 22 Maya rows for every type.

The kit (Blender constraints only blend by influence = a shortest slerp):
- Shortest: the group's rotation members get influence w_i / W_total (member 0 = 1) — Blender alone, exact.
- the other types: the rotation members get influence 0 and one Copy Rotation ``<group> blend`` (after the group) reads
  a hidden empty ``<owner>_<group>Blend`` whose world rotation the kit computes from the targets (depsgraph / frame
  handlers, like the pole helper). Frames are the Maya node frames: an object's Maya axes are its Blender X / Z /
  -Y (joints.MAYA_WORLD), a joint's are its bone's Y / Z / X (joints.JOINT_AXES); the own rotation is the node's
  rotation channels (the sign of q_Euler).
- per-group state on the owner (Object / PoseBone): ``allset_interp_<group>`` (Maya enum value), ``allset_last_<group>``
  (No Flip memory), ``allset_rest_<group>`` (zero-weight output), ``allset_ooff_<group>`` (orient offset).
- a parent constraint's offset Euler = Maya's offset Euler: the
  standard solution or the alternate
  (first + 180, 180 − middle, last + 180, not wrapped), whichever has the smaller sum of |angles| (ties: standard);
  the branch decides the offset quaternion's sign, which Average / No Flip read. A bone target's rest (Maya
  jointOrient) joins its parent part (canonical sign).
"""

import math

import bpy
from bpy.app.handlers import persistent
from mathutils import Quaternion, Vector

NO_FLIP, AVERAGE, SHORTEST, LONGEST, CACHE = range(5)
NAMES = ("No Flip", "Average", "Shortest", "Longest", "Cache")
INTERP = "allset_interp_"
LAST = "allset_last_"
REST = "allset_rest_"
OFFSET = "allset_ooff_"
BLEND = " blend"
H_GROUP = "allset_cblend_group"
EPS_W = 1e-10


# --- quaternion maths: tuples (w, x, y, z) in double precision (mathutils is float32: 0.05 deg off on near-opposite
# targets) ------------------------------------------------------------------------------------------------

def q_tuple(q):
    return (float(q[0]), float(q[1]), float(q[2]), float(q[3]))


def qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2)


def qinv(q):
    w, x, y, z = q
    return (w, -x, -y, -z)


def qneg(q):
    return tuple(-c for c in q)


def qdot(a, b):
    return sum(x * y for x, y in zip(a, b))


def qnorm(q):
    n = math.sqrt(qdot(q, q))
    return tuple(c / n for c in q) if n > 0.0 else (1.0, 0.0, 0.0, 0.0)


def canon(q):
    q = q_tuple(q)
    return q if q[0] >= 0.0 else qneg(q)


def qrot(q, v):
    return qmul(qmul(q, (0.0, *v)), qinv(q))[1:]


def _angle(u, v):
    c = sum(a * b for a, b in zip(u, v)) / math.sqrt(sum(a * a for a in u) * sum(b * b for b in v))
    return math.acos(max(-1.0, min(1.0, c)))


def slerp(a, b, t, long=False):
    """Maya's slerp: the short way (dot < 0 flips b) or the long way (dot > 0 flips b)."""
    d = qdot(a, b)
    if (d < 0.0 and not long) or (d > 0.0 and long):
        b, d = qneg(b), -d
    d = max(-1.0, min(1.0, d))
    th = math.acos(d)
    s = math.sin(th)
    if abs(s) < 1e-12:
        return qnorm(tuple(x * (1.0 - t) + y * t for x, y in zip(a, b)))
    fa, fb = math.sin((1.0 - t) * th) / s, math.sin(t * th) / s
    return qnorm(tuple(x * fa + y * fb for x, y in zip(a, b)))


def _sequence(qs, ws, total, long):
    acc = qs[0]
    for q, w in zip(qs[1:], ws[1:]):
        acc = slerp(acc, q, w / total, long)
    return qnorm(acc)


TEST = (1.0, 1.0, 1.0)
IDENTITY = (1.0, 0.0, 0.0, 0.0)


def blend(qs, ws, mode, last=None, rest=None):
    """Maya's blended rotation of target quaternions ``qs`` with weights ``ws`` (constraint parent frame)."""
    qs = [q_tuple(q) for q in qs]
    pairs = [(q, float(w)) for q, w in zip(qs, ws) if abs(w) > EPS_W]
    total = sum(w for _q, w in pairs)
    if total <= EPS_W or not pairs:
        return q_tuple(rest) if rest is not None else IDENTITY
    if mode in (NO_FLIP, CACHE) and len(qs) < 2:
        mode = AVERAGE
    q_s, w_s = [p[0] for p in pairs], [p[1] for p in pairs]
    if mode == AVERAGE:
        s = tuple(sum(w * q[k] for q, w in pairs) for k in range(4))
        return qnorm(s) if qdot(s, s) > 1e-24 else q_s[0]
    if mode in (SHORTEST, LONGEST):
        return _sequence(q_s, w_s, total, mode == LONGEST)
    short, longer = _sequence(q_s, w_s, total, False), _sequence(q_s, w_s, total, True)
    ref = qrot(q_tuple(last) if last is not None else IDENTITY, TEST)
    return short if _angle(qrot(short, TEST), ref) < _angle(qrot(longer, TEST), ref) else longer


ORDERS = {'XYZ': (0, 1, 2), 'YZX': (1, 2, 0), 'ZXY': (2, 0, 1), 'XZY': (0, 2, 1), 'YXZ': (1, 0, 2), 'ZYX': (2, 1, 0)}


def euler_quat(angles, order='XYZ'):
    """q_Euler: the product of the axis rotations (first axis of ``order`` first), signs kept."""
    q = IDENTITY
    for ax in ORDERS[order]:
        h = 0.5 * float(angles[ax])
        v = [0.0, 0.0, 0.0]
        v[ax] = math.sin(h)
        q = qmul((math.cos(h), *v), q)
    return q


def decompose(m, order='XYZ'):
    """Standard Euler of rotation matrix ``m`` in ``order`` (middle angle from asin, in [-90, 90] deg)."""
    i, j, k = ORDERS[order]
    s = 1.0 if (i, j, k) in ((0, 1, 2), (1, 2, 0), (2, 0, 1)) else -1.0
    b = math.asin(max(-1.0, min(1.0, -s * m[k][i])))
    a = math.atan2(s * m[k][j], m[k][k])
    g = math.atan2(s * m[j][i], m[i][i])
    r = [0.0, 0.0, 0.0]
    r[i], r[j], r[k] = a, b, g
    return r


_EPS = 1e-10


def offset_euler(m, order='XYZ'):
    """Maya's parent-constraint offset Euler: the standard Euler or its alternate (first + 180, 180 − middle, last + 180;
    only when cos² middle > 1e-10, not wrapped), whichever has the smaller sum of |angles| (strictly)."""
    i, j, k = ORDERS[order]
    r = decompose(m, order)
    a, b, c = r[i], r[j], r[k]
    if math.cos(b) ** 2 <= _EPS:
        return r
    a2 = a - math.pi if a > math.pi - _EPS else a + math.pi
    b2 = -math.pi - b if b < -math.pi + _EPS else math.pi - b
    c2 = c - math.pi if c > math.pi - _EPS else c + math.pi
    if abs(a2) + abs(b2) + abs(c2) < abs(a) + abs(b) + abs(c):
        out = [0.0, 0.0, 0.0]
        out[i], out[j], out[k] = a2, b2, c2
        return out
    return r


def q_matrix(q):
    return Quaternion(q).to_matrix()


# --- Maya node frames ------------------------------------------------------------------------------------------------

def _axes(node):
    from .joints import JOINT_AXES, MAYA_WORLD
    return JOINT_AXES if isinstance(node, bpy.types.PoseBone) else MAYA_WORLD


def _own_blender(node):
    mode = node.rotation_mode
    if mode == 'QUATERNION':
        q = qnorm(q_tuple(node.rotation_quaternion))
    elif mode == 'AXIS_ANGLE':
        a = node.rotation_axis_angle
        q = q_tuple(Quaternion(Vector(a[1:]).normalized() if Vector(a[1:]).length > 1e-12 else Vector((0, 0, 1)),
                               a[0]))
    else:
        e = node.rotation_euler
        q = euler_quat((e.x, e.y, e.z), mode)
    if isinstance(node, bpy.types.Object):
        dm = node.rotation_mode
        if dm in ORDERS:
            d = node.delta_rotation_euler
            q = qmul(euler_quat((d.x, d.y, d.z), dm), q)
        else:
            q = qmul(qnorm(q_tuple(node.delta_rotation_quaternion)), q)
    return q


def own_maya(node):
    """The node's own rotation as Maya's q_Euler (its Blender channels turned into the node's Maya axes)."""
    x = q_tuple(_axes(node).to_quaternion())
    return qmul(qmul(qinv(x), _own_blender(node)), x)


def world_rotation(node):
    if isinstance(node, bpy.types.PoseBone):
        m = node.id_data.matrix_world @ node.matrix
    else:
        m = node.matrix_world
    return m.to_3x3().normalized()


def frame(node):
    """The node's Maya frame (columns = its Maya axes in Blender world coordinates)."""
    return world_rotation(node) @ _axes(node)


def parent_frame(node):
    """Maya constraint parent frame of the owner (its parent's Maya frame; a root joint's = the armature's)."""
    from .joints import MAYA_WORLD
    if isinstance(node, bpy.types.PoseBone):
        arm = node.id_data
        if node.parent is not None:
            return frame(node.parent)
        return arm.matrix_world.to_3x3().normalized() @ MAYA_WORLD
    p = node.parent
    if p is None:
        return MAYA_WORLD.copy()
    if node.parent_type == 'BONE' and node.parent_bone and p.type == 'ARMATURE' and node.parent_bone in p.pose.bones:
        pw = p.matrix_world @ p.pose.bones[node.parent_bone].matrix
    else:
        pw = p.matrix_world
    return (pw @ node.matrix_parent_inverse).to_3x3().normalized() @ MAYA_WORLD


def joint_orient(owner):
    """Maya jointOrient of the owner in its constraint parent frame (identity for objects; a bone's rest turn)."""
    if not isinstance(owner, bpy.types.PoseBone):
        return IDENTITY
    from .joints import JOINT_AXES, MAYA_WORLD
    b = owner.bone
    if b.parent is not None:
        jo = JOINT_AXES.inverted() @ (b.parent.matrix_local.to_3x3().normalized().inverted()
                                      @ b.matrix_local.to_3x3().normalized()) @ JOINT_AXES
    else:
        jo = MAYA_WORLD.inverted() @ b.matrix_local.to_3x3().normalized() @ JOINT_AXES
    return q_tuple(jo.to_quaternion())


def target_quat(cp_inv, node):
    """q_i of target ``node`` in the constraint parent frame (parent part canonical, own part signed)."""
    own = own_maya(node)
    part = cp_inv @ frame(node) @ q_matrix(own).inverted()
    return qmul(canon(part.to_quaternion()), own)


# --- groups ----------------------------------------------------------------------------------------------------------

def group_kind(owner, group):
    from . import constrain_multi
    return constrain_multi._groups(owner).get(group)


def mode_of(owner, group):
    """Maya interpType of a group; older groups have none (their cumulative stack ~ Shortest)."""
    v = owner.get(INTERP + group)
    return int(v) if v is not None else None


def rotation_members(owner, group):
    from . import constrain_multi
    kind = group_kind(owner, group)
    out = []
    for c in constrain_multi.members(owner, group):
        if kind == "orientConstraint" and c.type == 'COPY_ROTATION':
            out.append(c)
        elif kind == "parentConstraint" and c.name.endswith(constrain_multi.ROT):
            out.append(c)
    return out


def _real_target(con):
    """(node, offset matrix or None, is offset helper) of a member: a kit helper stands for its own target."""
    from . import constrain_multi
    t = con.target
    sub = getattr(con, "subtarget", "")
    h = constrain_multi.helper_of(con)
    if h is not None and h.constraints:
        hc = h.constraints[0]
        rt, rsub = hc.target, getattr(hc, "subtarget", "")
        node = rt.pose.bones.get(rsub) if (rsub and rt is not None and rt.type == 'ARMATURE') else rt
        offset = h.matrix_basis.to_3x3().normalized() if h.name.endswith("Offset") else None
        return node, offset
    node = t.pose.bones.get(sub) if (sub and t is not None and t.type == 'ARMATURE') else t
    return node, None


def _weights(owner, group):
    from . import constrain_multi
    return [float(owner.get(prop, 1.0)) for prop, _label in constrain_multi.weights(owner, group)]


def _offset_quat(owner, node, offset):
    """Maya targetOffsetRotate of a parent-constraint target as q_Euler (``offset_euler`` in the owner's order, C8)."""
    x_t, x_o = _axes(node), _axes(owner)
    m = x_t.inverted() @ offset @ x_o
    order = owner.rotation_mode if owner.rotation_mode in ORDERS else 'XYZ'
    return euler_quat(offset_euler(m, order), order)


def target_quats(owner, group):
    frame = parent_frame(owner)
    if abs(frame.to_3x3().determinant()) < 1e-12:      # a zero-scaled parent: no rotation to blend in
        return None
    cp_inv = frame.inverted()
    qs = []
    for c in rotation_members(owner, group):
        node, offset = _real_target(c)
        if node is None:
            return None
        q = target_quat(cp_inv, node)
        if offset is not None and group_kind(owner, group) == "parentConstraint":
            q = qmul(q, _offset_quat(owner, node, offset))
        qs.append(q)
    return qs


def _get_q(owner, key):
    v = owner.get(key)
    return q_tuple(v) if v is not None and len(v) == 4 else None


def compute(owner, group):
    """The group's blended rotation r (constraint parent frame), the No Flip memory updated."""
    qs = target_quats(owner, group)
    if not qs:
        return None
    mode = mode_of(owner, group)
    r = blend(qs, _weights(owner, group), AVERAGE if mode is None else mode,
              _get_q(owner, LAST + group), _get_q(owner, REST + group))
    off = _get_q(owner, OFFSET + group)
    if off is not None:
        r = qmul(r, off)
    # lastTargetRotate = the output rotate (after the offset, without the owner's jointOrient)
    rotate = qmul(qinv(joint_orient(owner)), r)
    last = _get_q(owner, LAST + group)
    if last is None or qdot(last, rotate) < 1.0 - 1e-12:
        owner[LAST + group] = tuple(rotate)
    return r


def _blend_name(group):
    return f"{group}{BLEND}"


def blend_constraint(owner, group):
    return owner.constraints.get(_blend_name(group))


def is_blend(con):
    """The kit Copy Rotation that applies a computed group blend (not a Maya node of its own)."""
    t = getattr(con, "target", None)
    return con.type == 'COPY_ROTATION' and con.name.endswith(BLEND) and t is not None and H_GROUP in t.keys()


def _remove_blend(owner, group):
    c = blend_constraint(owner, group)
    if c is None:
        return
    h = c.target
    owner.constraints.remove(c)
    if h is not None and H_GROUP in h.keys():
        bpy.data.objects.remove(h, do_unlink=True)


def _owner_world_r(owner):
    """The owner's current Maya rotation in its constraint parent frame."""
    return q_tuple((parent_frame(owner).inverted() @ frame(owner)).to_quaternion())


def write_helper(owner, group, r):
    c = blend_constraint(owner, group)
    h = c.target if c is not None else None
    if h is None:
        return False
    want = (parent_frame(owner) @ q_matrix(r) @ _axes(owner).inverted()).to_4x4()
    cur = h.matrix_world.to_3x3().normalized()
    if max(abs(cur[i][j] - want[i][j]) for i in range(3) for j in range(3)) < 1e-9:
        return False
    h.matrix_world = want
    return True


def set_mode(context, owner, group, mode):
    """Rebuild a group for Maya interpType ``mode`` (orient / parent groups only)."""
    from . import constrain_multi
    kind = group_kind(owner, group)
    if kind not in ("orientConstraint", "parentConstraint"):
        raise ValueError(kind)
    mode = int(mode)
    rms = rotation_members(owner, group)
    if not rms:
        return
    before = _owner_world_r(owner)
    first_time = REST + group not in owner.keys()      # creation (or an older group)
    owner[INTERP + group] = mode
    _remove_blend(owner, group)
    names = [p for p, _l in constrain_multi.weights(owner, group)]
    for i, c in enumerate(rms):
        try:
            c.driver_remove("influence")
        except TypeError:
            pass
        c.influence = 1.0 if (i == 0 or mode != SHORTEST) else c.influence
    if mode == SHORTEST:
        for i, c in enumerate(rms):
            if i > 0:
                _drive_total(c, owner, names, i)
        owner.id_data.update_tag()
        context.view_layer.update()
        return
    for c in rms:
        c.influence = 0.0
    h = bpy.data.objects.new(f"{owner.name}_{group}Blend", None)
    h.empty_display_size = 0.0
    h.hide_viewport = h.hide_render = h.hide_select = True
    constrain_multi._helper_collection().objects.link(h)
    id_ob, _prefix = constrain_multi._id_and_prefix(owner)
    h[constrain_multi.H_OWNER] = id_ob
    h[constrain_multi.H_BONE] = owner.name if isinstance(owner, bpy.types.PoseBone) else ""
    h[constrain_multi.H_CON] = _blend_name(group)
    h[H_GROUP] = group
    c = owner.constraints.new('COPY_ROTATION')
    c.name = _blend_name(group)
    c.target = h
    ms = constrain_multi.members(owner, group)
    last_index = max(list(owner.constraints).index(m) for m in ms)
    owner.constraints.move(len(owner.constraints) - 1, last_index + 1)
    # Maya: the constraint evaluates once when it is made (interpType Average): that output is
    # restRotate (all weights 0) and the first No Flip memory; an orient offset (Maintain Offset) is one rotation after
    # the blend computed then (out = offset * result). They are node
    # attributes: a later Interp Type change keeps them.
    qs = target_quats(owner, group) or []
    base = blend(qs, _weights(owner, group), AVERAGE) if qs else IDENTITY
    if (kind == "orientConstraint" and OFFSET + group not in owner.keys()
            and any(_real_target(m)[1] is not None for m in rms)):
        off_m = q_matrix(qmul(qinv(base), before))
        order = owner.rotation_mode if owner.rotation_mode in ORDERS else 'XYZ'
        owner[OFFSET + group] = tuple(euler_quat(decompose(off_m, order), order))
    off = _get_q(owner, OFFSET + group)
    out = qmul(base, off) if off is not None else base
    if REST + group not in owner.keys():
        owner[REST + group] = tuple(base)
    jo_inv = qinv(joint_orient(owner))
    owner[LAST + group] = qmul(jo_inv, out if first_time else before)
    update(owner, group)
    owner.id_data.update_tag()
    context.view_layer.update()
    _state["armed"] = True


def _drive_total(con, owner, names, k):
    """Influence of rotation member k (>= 1) = w_k / W_total (Maya Shortest: slerp(acc, q_k, w_k / W_total))."""
    from . import constrain_multi
    id_ob, prefix = constrain_multi._id_and_prefix(owner)
    fc = con.driver_add("influence")
    d = fc.driver
    d.type = 'SCRIPTED'
    while d.variables:
        d.variables.remove(d.variables[0])
    for j, wp in enumerate(names):
        v = d.variables.new()
        v.name = f"w{j}"
        v.type = 'SINGLE_PROP'
        v.targets[0].id = id_ob
        v.targets[0].data_path = prefix + f'["{bpy.utils.escape_identifier(wp)}"]'
    s = "+".join(f"w{j}" for j in range(len(names)))
    d.expression = f"w{k} / ({s}) if ({s}) > 0 else {1.0 / (k + 1)!r}"
    for m in list(fc.modifiers):
        fc.modifiers.remove(m)


def update(owner, group):
    r = compute(owner, group)
    return write_helper(owner, group, r) if r is not None else False


def blend_helpers():
    from . import constrain_multi
    return [h for h in constrain_multi.helpers() if H_GROUP in h.keys()]


def owner_of_helper(h):
    from . import constrain_multi
    ob = h.get(constrain_multi.H_OWNER)
    if ob is None:
        return None
    bone = h.get(constrain_multi.H_BONE, "")
    if bone:
        return ob.pose.bones.get(bone) if ob.pose is not None else None
    return ob


_busy = []
_state = {"armed": False}


@persistent
def _on_update(*_args):
    if _busy or not _state["armed"]:
        return
    _busy.append(1)
    try:
        for h in blend_helpers():
            owner = owner_of_helper(h)
            if owner is not None and blend_constraint(owner, h[H_GROUP]) is not None:
                update(owner, h[H_GROUP])
    except (ReferenceError, AttributeError, RuntimeError, KeyError, TypeError):
        pass
    finally:
        _busy.clear()


@persistent
def _on_load(*_args):
    _state["armed"] = bool(blend_helpers())


def register_handlers():
    for hs in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.frame_change_post):
        if _on_update not in hs:
            hs.append(_on_update)
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)
    _state["armed"] = bool(blend_helpers())


def unregister_handlers():
    for hs in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.frame_change_post):
        if _on_update in hs:
            hs.remove(_on_update)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)


class ALLSET_OT_constraint_interp(bpy.types.Operator):
    """Maya Interp Type of an orient / parent constraint node (how several targets' rotations are blended)"""
    bl_idname = "allset.constraint_interp"
    bl_label = "Interp Type"
    bl_options = {'UNDO', 'INTERNAL'}

    object: bpy.props.StringProperty()
    bone: bpy.props.StringProperty()
    group: bpy.props.StringProperty()
    mode: bpy.props.EnumProperty(items=[(str(i), n, "") for i, n in enumerate(NAMES)])

    def execute(self, context):
        ob = bpy.data.objects.get(self.object)
        owner = ob.pose.bones.get(self.bone) if ob is not None and self.bone and ob.pose is not None else ob
        if owner is None or group_kind(owner, self.group) not in ("orientConstraint", "parentConstraint"):
            return {'CANCELLED'}
        set_mode(context, owner, self.group, int(self.mode))
        return {'FINISHED'}


classes = (ALLSET_OT_constraint_interp,)
