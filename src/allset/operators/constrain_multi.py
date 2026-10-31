# SPDX-License-Identifier: GPL-3.0-or-later
"""L4: Maya multi-target constraints (weighted average).

Maya: a point / orient / parent / scale constraint with several targets is
one node ``<owner>_<type><n>`` with one weight attribute ``<target>W<i>`` per target (default 1.0), the result is the
weighted average with the weights normalised w_i / Σw; every weight 0 = the equal-weight average.

The kit (one Blender constraint reads one target):
- One Blender constraint per target, stacked in Maya's target order, named ``<group>:<i>:<target>`` (parent: one
  Copy Location + one Copy Rotation ``... R`` per target). The owner (Object / PoseBone) keeps the group in the ID
  property ``allset_cgroups`` ({group: Maya type}) and Maya's weight per target in ``allset_w_<first member name>``
  (float 1.0 — keyable and drivable, Set Driven Key drives exactly these).
- Point / Orient / Parent: influence of member i = driver ``w_i / S_i if S_i > 0 else 1 / (i + 1)`` with
  S_i = w_0 + ... + w_i (Blender mixes the stack in order, so these influences give exactly the weighted average of
  the positions; all 0 = the equal average and W0 0.5 · W1 0 = target A, both Maya). Simple expressions only:
  no Python auto-run needed (``driver.is_simple_expression``).
- Parent with Maintain Offset (the default, like Maya) / Point / Orient / Scale with Maintain Offset: each target gets a hidden
  helper empty holding the owner's offset from that target (point: Copy Location with offset; else Child Of the
  target with the offset as its own channels). The helpers live in the hidden collection ``.AllsetConstraintHelpers``
  (no scene: not in the Outliner, not exported, still evaluated as constraint targets) and go when their
  constraint goes (``cleanup``, from a depsgraph handler through a timer).
- Scale: Maya's multi-target scale is the weighted geometric mean: member i = Copy Scale with
  ``power = w_i / Σw`` (equal split when Σw = 0), the first replaces, the others multiply (``use_offset``) — exact.
- Rotation: Maya's interpType (orient / parent) — #168, operators/constrain_interp.py: Shortest is the
  rotation members' influence w_i / W_total, the other types (default Average) a kit-computed blend.
"""

import re

import bpy
from mathutils import Matrix

GROUPS = "allset_cgroups"          # owner ID property: {group: Maya node type}
WEIGHT = "allset_w_"               # owner ID property prefix: Maya target weight (allset_w_<member name>)
HELPERS = ".AllsetConstraintHelpers"
H_OWNER = "allset_cmulti_owner"    # helper empty: the owner object (armature for a pose bone owner)
H_BONE = "allset_cmulti_bone"      # helper empty: the owner pose bone name ("" = object)
H_CON = "allset_cmulti_con"        # helper empty: the member constraint that reads it

MAYA_TYPE = {'CHILD_OF': "parentConstraint", 'COPY_LOCATION': "pointConstraint",
             'COPY_ROTATION': "orientConstraint", 'COPY_SCALE': "scaleConstraint"}
TYPES = tuple(MAYA_TYPE)
DEFAULT_OFFSET = {'CHILD_OF': True}      # default Maintain Offset: parent on, point / orient / scale off
ROT = " R"                               # suffix of a parent group's Copy Rotation member
_NAME = re.compile(r"^(?P<group>[^:]+):(?P<index>\d+):(?P<label>.*?)(?P<rot> R)?$")


# --- owners ---------------------------------------------------------------------------------------------------------

def _id_and_prefix(owner):
    """(ID object, data path prefix) of an Object or PoseBone owner."""
    if isinstance(owner, bpy.types.PoseBone):
        return owner.id_data, f'pose.bones["{bpy.utils.escape_identifier(owner.name)}"]'
    return owner, ""


def owner_of(con):
    """The Object / PoseBone holding constraint ``con``."""
    ob = con.id_data
    try:
        path = con.path_from_id()
    except (ValueError, AttributeError):
        return ob
    if path.startswith("pose.bones["):
        return ob.path_resolve(path.rsplit(".constraints[", 1)[0])
    return ob


def world(owner):
    if isinstance(owner, bpy.types.PoseBone):
        return owner.id_data.matrix_world @ owner.matrix
    return owner.matrix_world.copy()


def _target_world(ob, sub):
    if sub and ob.type == 'ARMATURE' and sub in ob.pose.bones:
        return ob.matrix_world @ ob.pose.bones[sub].matrix
    return ob.matrix_world.copy()


def _groups(owner):
    g = owner.get(GROUPS)
    return dict(g) if g is not None else {}


# --- group membership -----------------------------------------------------------------------------------------------

class Member:
    __slots__ = ("group", "index", "label", "rot", "con", "owner")

    def __init__(self, m, con, owner):
        self.group, self.index, self.label = m["group"], int(m["index"]), m["label"]
        self.rot, self.con, self.owner = bool(m["rot"]), con, owner

    @property
    def weight_prop(self):
        return weight_prop(self.group, self.index, self.label)


def weight_prop(group, index, label):
    return f"{WEIGHT}{group}:{index}:{label}"


def member(con, owner=None):
    """``Member`` when ``con`` belongs to a kit multi-target group, else None."""
    m = _NAME.match(con.name)
    if m is None:
        return None
    owner = owner if owner is not None else owner_of(con)
    if m["group"] not in _groups(owner):
        return None
    return Member(m, con, owner)


def members(owner, group):
    """Constraints of ``group`` on ``owner`` in stack order."""
    out = []
    for c in owner.constraints:
        m = _NAME.match(c.name)
        if m is not None and m["group"] == group:
            out.append(c)
    return out


def is_head(con, owner=None):
    """True for a constraint that stands for a Maya node: an ungrouped one, or the first member of its group."""
    mb = member(con, owner)
    if mb is None:
        return True
    ms = members(mb.owner, mb.group)
    return bool(ms) and ms[0] == con


def head_of(con, owner=None):
    """The constraint that stands for ``con``'s Maya node: a group's first member; an Interp Type blend's
    group head; an aim's Object up turn (``rig_tools.UP_SUFFIX``) = that aim."""
    mb = member(con, owner)
    if mb is None:
        from . import constrain_interp, rig_tools
        owner = owner if owner is not None else owner_of(con)
        if constrain_interp.is_blend(con):
            ms = members(owner, con.name[:-len(constrain_interp.BLEND)])
            return ms[0] if ms else con
        if rig_tools.is_up_companion(con):
            return owner.constraints.get(con.name[:-len(rig_tools.UP_SUFFIX)]) or con
        return con
    ms = members(mb.owner, mb.group)
    return ms[0] if ms else con


def group_type(con, owner=None):
    """Maya node type of a grouped constraint (a parent group's Copy Location = parentConstraint), else None."""
    mb = member(con, owner)
    return _groups(mb.owner).get(mb.group) if mb is not None else None


def weights(owner, group):
    """[(weight property, Maya weight attribute label <target>W<i>)] of a group, in target order."""
    seen, out = set(), []
    for c in members(owner, group):
        m = _NAME.match(c.name)
        i = int(m["index"])
        if i in seen:
            continue
        seen.add(i)
        out.append((weight_prop(group, i, m["label"]), f"{m['label']}W{i}"))
    return out


def set_enabled(owner, group, on):
    from . import constrain_interp
    blend = constrain_interp.blend_constraint(owner, group)
    for c in members(owner, group) + ([blend] if blend is not None else []):
        if hasattr(c, "enabled"):
            c.enabled = on
        else:
            c.mute = not on


# --- helpers --------------------------------------------------------------------------------------------------------

def _helper_collection():
    coll = bpy.data.collections.get(HELPERS)
    if coll is None:
        coll = bpy.data.collections.new(HELPERS)
        coll.use_fake_user = True         # in no scene: kept by its fake user, not in the Outliner / exports
    return coll


def _helper(owner, name, target, sub, offset_world, point):
    """Hidden empty at the owner's offset from (target, sub): point = Copy Location (+ offset, Maya's point offset is a
    translation), else Child Of the target with the offset as its own channels (orient / parent / scale offset)."""
    h = bpy.data.objects.new(name, None)
    h.empty_display_size = 0.0
    h.hide_viewport = h.hide_render = h.hide_select = True
    _helper_collection().objects.link(h)
    id_ob, _prefix = _id_and_prefix(owner)
    h[H_OWNER] = id_ob
    h[H_BONE] = owner.name if isinstance(owner, bpy.types.PoseBone) else ""
    tw = _target_world(target, sub)
    if point:
        h.location = offset_world.translation - tw.translation
        c = h.constraints.new('COPY_LOCATION')
        c.use_offset = True
    else:
        h.matrix_basis = tw.inverted_safe() @ offset_world
        c = h.constraints.new('CHILD_OF')
        c.inverse_matrix = Matrix.Identity(4)
        c.set_inverse_pending = False
    c.target = target
    if sub:
        c.subtarget = sub
    return h


def helpers():
    # register() runs with Blender's restricted data while add-ons load at start-up / install (no ``collections``):
    # nothing to find then; load_post handlers look again once the file is loaded
    colls = getattr(bpy.data, "collections", None)
    coll = colls.get(HELPERS) if colls is not None else None
    return list(coll.objects) if coll is not None else []


def helper_of(con):
    t = getattr(con, "target", None)
    return t if t is not None and H_CON in t.keys() else None


# --- drivers --------------------------------------------------------------------------------------------------------

def _drive(con, prop, owner, names, k, scale=False):
    """Driver on ``con.<prop>`` from the weight properties ``names`` (target order) — cumulative influence of member k
    (point / orient / parent) or the geometric-mean power w_k / Σw (scale)."""
    id_ob, prefix = _id_and_prefix(owner)
    fc = con.driver_add(prop)
    d = fc.driver
    d.type = 'SCRIPTED'
    while d.variables:
        d.variables.remove(d.variables[0])
    used = names if scale else names[:k + 1]
    for j, wp in enumerate(used):
        v = d.variables.new()
        v.name = f"w{j}"
        v.type = 'SINGLE_PROP'
        v.targets[0].id = id_ob
        v.targets[0].data_path = prefix + f'["{bpy.utils.escape_identifier(wp)}"]'
    s = "+".join(f"w{j}" for j in range(len(used)))
    fallback = 1.0 / (len(names) if scale else k + 1)
    d.expression = f"w{k} / ({s}) if ({s}) > 0 else {fallback!r}"
    for m in list(fc.modifiers):          # driver_add makes a Generator: the expression alone is the value
        fc.modifiers.remove(m)
    return fc


def _unique_group(owner, mtype):
    taken = set(_groups(owner))
    for c in owner.constraints:
        m = _NAME.match(c.name)
        if m is not None:
            taken.add(m["group"])
    n = 1
    while f"{mtype}{n}" in taken:
        n += 1
    return f"{mtype}{n}"


def target_label(target, sub):
    return sub if sub and target.type == 'ARMATURE' else target.name


def _joint_from_object():
    from .joints import JOINT_AXES, MAYA_WORLD
    return (MAYA_WORLD @ JOINT_AXES.transposed()).to_4x4()


# an object's Maya axes are its Blender X / Z / -Y (joints.MAYA_WORLD), a joint's are its bone's Y / Z / X
# (joints.JOINT_AXES), so a bone copying an object's rotation has to copy the object's frame turned by
# MAYA_WORLD JOINT_AXES^-1 (Maya orientConstraint / parentConstraint without offset: the joint's axes = the target's;
# 90 deg off before). A bone target needs nothing.


def needs_joint_axes(owner, target, sub, ctype):
    """A joint (pose bone) copying the rotation of an object (not of a bone)."""
    return (isinstance(owner, bpy.types.PoseBone) and ctype in ('COPY_ROTATION', 'CHILD_OF')
            and not (sub and target.type == 'ARMATURE'))


def build(context, owner, targets, ctype, maintain_offset=None, weight=1.0):
    """Maya multi-target constraint on ``owner`` (Object / PoseBone) from ``targets`` [(object, subtarget)] in Maya
    target order. Returns the group's first constraint."""
    if ctype not in MAYA_TYPE:
        raise ValueError(ctype)
    if maintain_offset is None:
        maintain_offset = DEFAULT_OFFSET.get(ctype, False)
    mtype = MAYA_TYPE[ctype]
    group = _unique_group(owner, mtype)
    groups = _groups(owner)
    groups[group] = mtype
    owner[GROUPS] = groups
    ow = world(owner)
    owner_name = owner.name
    labels = []
    for i, (t, sub) in enumerate(targets):
        label = target_label(t, sub)
        labels.append(label)
        owner[weight_prop(group, i, label)] = float(weight)
    names = [weight_prop(group, i, lab) for i, lab in enumerate(labels)]
    cons = owner.constraints
    first = None
    for i, (t, sub) in enumerate(targets):
        base = f"{group}:{i}:{labels[i]}"
        src, src_sub = t, sub
        if maintain_offset:
            src = _helper(owner, f"{owner_name}_{group}_{labels[i]}Offset", t, sub, ow, ctype == 'COPY_LOCATION')
            src_sub = ""
        elif needs_joint_axes(owner, t, sub, ctype):
            # a joint takes the target's Maya axes, not its Blender ones (joints.JOINT_AXES)
            src = _helper(owner, f"{owner_name}_{group}_{labels[i]}Axes", t, sub,
                          _target_world(t, sub) @ _joint_from_object(), False)
            src_sub = ""
        kinds = (('COPY_LOCATION', base), ('COPY_ROTATION', base + ROT)) if ctype == 'CHILD_OF' else ((ctype, base),)
        for btype, name in kinds:
            c = cons.new(btype)
            c.name = name
            c.target = src
            if src_sub:
                c.subtarget = src_sub
            if src is not t:
                src[H_CON] = base if H_CON not in src.keys() else src[H_CON]
            if btype == 'COPY_SCALE':
                c.use_offset = i > 0              # the first replaces, the others multiply
                c.use_add = False
                _drive(c, "power", owner, names, i, scale=True)
            elif i > 0:
                _drive(c, "influence", owner, names, i)
            if first is None:
                first = c
    _state["armed"] = True
    if ctype in ('COPY_ROTATION', 'CHILD_OF') and len(targets) > 1:
        # #168: Maya interpType, default Average (operators/constrain_interp.py); one target = its own
        # rotation whatever the type (Maya: fewer than 2 targets blend as Average = that target)
        from . import constrain_interp
        constrain_interp.set_mode(context, owner, group, constrain_interp.AVERAGE)
    owner.id_data.update_tag()
    context.view_layer.update()
    return first


def remove_group(owner, group):
    """Delete a group: its constraints, their drivers, weight properties and helper empties."""
    id_ob, prefix = _id_and_prefix(owner)
    from . import constrain_interp
    constrain_interp._remove_blend(owner, group)
    for key in (constrain_interp.INTERP, constrain_interp.LAST, constrain_interp.REST, constrain_interp.OFFSET):
        if key + group in owner.keys():
            del owner[key + group]
    hs = []
    for c in members(owner, group):
        h = helper_of(c)
        if h is not None:
            hs.append(h)
        for prop in ("influence", "power"):
            try:
                c.driver_remove(prop)
            except TypeError:
                pass
        owner.constraints.remove(c)
    for k in [k for k in owner.keys() if k.startswith(f"{WEIGHT}{group}:")]:
        del owner[k]
    groups = _groups(owner)
    groups.pop(group, None)
    if groups:
        owner[GROUPS] = groups
    elif GROUPS in owner.keys():
        del owner[GROUPS]
    for h in dict.fromkeys(hs):
        try:
            bpy.data.objects.remove(h, do_unlink=True)
        except ReferenceError:
            pass


# --- cleanup (a deleted owner / cleared constraints leave helpers, drivers and weights behind) -----------------------

def _owners():
    for ob in bpy.data.objects:
        if GROUPS in ob.keys():
            yield ob
        if ob.type == 'ARMATURE' and ob.pose is not None:
            for pb in ob.pose.bones:
                if GROUPS in pb.keys():
                    yield pb


def cleanup():
    """Drop helpers whose constraint is gone and groups with no constraint left. Returns the number of removals."""
    n = 0
    for h in helpers():
        owner = h.get(H_OWNER)
        con_name = h.get(H_CON, "")
        alive = False
        if owner is not None:
            bone = h.get(H_BONE, "")
            node = owner.pose.bones.get(bone) if bone and owner.pose is not None else (None if bone else owner)
            if node is not None:
                alive = any(helper_of(c) == h for c in node.constraints if c.name.startswith(con_name))
                partner = h.get("allset_aim_up")       # an aim's up helper goes with its aim
                if alive and partner and node.constraints.get(partner) is None:
                    alive = False
                    for c in [c for c in node.constraints if helper_of(c) == h]:
                        node.constraints.remove(c)
        if not alive:
            bpy.data.objects.remove(h, do_unlink=True)
            n += 1
    for owner in list(_owners()):
        for group in list(_groups(owner)):
            if not members(owner, group):
                id_ob, prefix = _id_and_prefix(owner)
                ad = id_ob.animation_data
                if ad is not None:
                    want = f'{prefix}{"." if prefix else ""}constraints["{group}:'
                    for fc in [f for f in ad.drivers if f.data_path.startswith(want)]:
                        ad.drivers.remove(fc)
                remove_group(owner, group)
                n += 1
    return n


_state = {"pending": False, "armed": False}


def _tick():
    _state["pending"] = False
    try:
        cleanup()
    except Exception:          # never break the timer loop
        pass
    return None


@bpy.app.handlers.persistent
def _on_depsgraph(_scene, _depsgraph):
    # armed once a group exists in this session (build / file load): at most one cleanup scan per 0.3 s
    if _state["pending"] or not (_state["armed"] or bpy.data.collections.get(HELPERS) is not None):
        return
    _state["pending"] = True
    bpy.app.timers.register(_tick, first_interval=0.3)


@bpy.app.handlers.persistent
def _on_load(*_args):
    _state["armed"] = bpy.data.collections.get(HELPERS) is not None or any(True for _ in _owners())


# --- Channel Box node state (one Maya node = every member) ----------------------------------------------------------

class ALLSET_OT_constraint_group_enable(bpy.types.Operator):
    """Turn the Maya constraint node on / off (every Blender constraint of the multi-target group)"""
    bl_idname = "allset.constraint_group_enable"
    bl_label = "Constraint Node State"
    bl_options = {'UNDO', 'INTERNAL'}

    object: bpy.props.StringProperty()
    bone: bpy.props.StringProperty()
    group: bpy.props.StringProperty()

    def execute(self, context):
        ob = bpy.data.objects.get(self.object)
        owner = ob.pose.bones.get(self.bone) if ob is not None and self.bone and ob.pose is not None else ob
        if owner is None:
            return {'CANCELLED'}
        ms = members(owner, self.group)
        if not ms:
            return {'CANCELLED'}
        on = not (ms[0].enabled if hasattr(ms[0], "enabled") else not ms[0].mute)
        set_enabled(owner, self.group, on)
        ob.update_tag()
        return {'FINISHED'}


classes = (ALLSET_OT_constraint_group_enable,)


def register_props():
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def unregister_props():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _state["pending"] = False
