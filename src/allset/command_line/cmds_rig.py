# SPDX-License-Identifier: GPL-3.0-or-later
"""maya.cmds look-alike 3 (Issue #122): freeze, constraints, joints, connections.

Numbers follow the rest of the look-alike (cmds_shim.py): lengths in Maya units, Blender's axes as they are.

- makeIdentity = Modify > Freeze / Reset Transformations (``operators/freeze.py``: channels 0 / 0 / 1, the pivot kept
  in ``delta_location``, children frozen too).
- Constraints = Blender constraints like Constrain > ... (``ui/channel_box`` shows them as INPUTS nodes): one Maya
  node = one Blender constraint per target (influence w_i / (w_1 + ... + w_i), so the stack gives Maya's weighted
  blend). Maya's node name ``<constrained>_<type>N`` is fixed at creation (a rename doesn't follow), so it
  is kept in the object's ID property ``NODES`` with the targets' weight / alias index. Without Maintain Offset:
  point = Copy Location, orient = Copy Rotation, scale = Copy Scale, parent = Child Of with the inverse matrix that
  puts the object on the target; with it a Child Of on the node's channels whose inverse is the target's current
  matrix (Maya's offset is composed as a matrix: orient mo). aim = Track To (aim / up vectors along
  axes) evaluated in a hidden helper's space whose Z is Maya's world up vector — Blender's Track To ups to world Z.
- joint = a joint of a kit skeleton (``operators/joints.py``): a bone, ``jointN`` named scene-wide; the
  selected joint is the parent, a selected transform parents a new skeleton keeping the joint's world position.
- connectAttr / disconnectAttr = the Connection Editor's connections (``ui/connection_editor.py``: drivers
  with variable ``cn``, Maya unit conversion).

Constraint nodes and joints are not Blender objects, so the DAG commands of cmds_shim / cmds_dag (getAttr, setAttr,
xform, listRelatives, ls, select, delete, objExists) reach them through ``intercept``.
"""

import math
import types

import bpy
from mathutils import Matrix, Vector

from .cmds_shim import (_Flags, _flatten, _object, _objects, _selection, _view_layer, _to_bu, _from_bu, _from_rad,
                        linear_factor)

PASS = object()                      # intercept: not a joint / constraint matter, run the command itself
NODES = "allset_cmds_nodes"          # object ID property: Maya constraint nodes {name: {type, targets, ...}}
JOINT_RADIUS = "allset_radius"       # bone ID property: Maya joint radius (default 1)
JOINT_ORIENT = "allset_joint_orient"  # bone ID property: Maya jointOrient in radians (cmds.joint makes 0 0 0)
UP_PREFIX = ".allset_up_"            # hidden helper (no scene, fake user): an aim node's world-up space

CHANNELS = {"parentConstraint": "tr", "pointConstraint": "t", "orientConstraint": "r", "scaleConstraint": "s",
            "aimConstraint": "r"}
CONSTRAINT_TYPES = tuple(CHANNELS)
MAIN_KEYS = tuple(c + a for c in "trs" for a in "xyz")

# Maya attribute names <-> Connection Editor leaves (ui/connection_editor.SIMPLE / COMPOUNDS)
_LONG = {"tx": "translateX", "ty": "translateY", "tz": "translateZ", "rx": "rotateX", "ry": "rotateY",
         "rz": "rotateZ", "sx": "scaleX", "sy": "scaleY", "sz": "scaleZ", "v": "visibility", "t": "translate",
         "r": "rotate", "s": "scale"}
_KEY = {"translateX": "tx", "translateY": "ty", "translateZ": "tz", "rotateX": "rx", "rotateY": "ry",
        "rotateZ": "rz", "scaleX": "sx", "scaleY": "sy", "scaleZ": "sz", "visibility": "v"}


def _ce():
    from ..ui import connection_editor
    return connection_editor


def _cb():
    from ..ui import channel_box
    return channel_box


# --- makeIdentity --------------------------------------------------------------------------------------------------

def makeIdentity(*args, **kwargs):
    """``makeIdentity -apply 1 -t -r -s`` = Freeze Transformations (channels 0 / 0 / 1, world pivots and shapes stay,
    the hierarchy below frozen too); without ``-apply`` = the channels back to identity (the objects jump). No t / r /
    s flag = all three. Returns None."""
    from ..operators import freeze
    f = _Flags("makeIdentity", kwargs)
    apply = f.get("apply", "a", False)
    t = f.get("translate", "t", False)
    r = f.get("rotate", "r", False)
    s = f.get("scale", "s", False)
    f.get("normal", "n", 0)
    f.get("preserveNormals", "pn", True)
    f.get("jointOrient", "jo", False)
    f.done()
    obs = _objects(args)
    if not (t or r or s):
        t = r = s = True
    _view_layer()
    if apply:
        freeze.freeze(obs, translate=bool(t), rotate=bool(r), scale=bool(s))
    else:
        freeze.reset(freeze.hierarchy(obs), translate=bool(t), rotate=bool(r), scale=bool(s))
    _view_layer()
    return None


# --- constraint nodes ----------------------------------------------------------------------------------------------

def _registry(ob):
    d = ob.get(NODES)
    return d.to_dict() if d is not None and hasattr(d, "to_dict") else {}


def _store(ob, reg):
    if reg:
        ob[NODES] = reg
    elif NODES in ob.keys():
        del ob[NODES]


def _owners():
    return [o for o in bpy.data.objects if NODES in o.keys()]


def nodes_of(ob):
    """[(node name, entry)] of ``ob`` in creation order (Maya lists them after the shape)."""
    return list(_registry(ob).items())


def find_node(name):
    """(owner, node name, entry) of the Maya constraint node ``name``, else None."""
    short = str(name).rsplit("|", 1)[-1]
    for ob in _owners():
        entry = _registry(ob).get(short)
        if entry is not None:
            return ob, short, entry
    return None


def _node_of_type(ob, mtype):
    return next((n for n, e in nodes_of(ob) if e["type"] == mtype), None)


def _cons(ob, entry):
    """The node's Blender constraints, in target order."""
    return [c for c in (ob.constraints.get(n) for n in entry["targets"]) if c is not None]


def _target(con):
    return getattr(con, "target", None)


def _aliases(ob, entry):
    out = []
    for cname, info in entry["targets"].items():
        con = ob.constraints.get(cname)
        tgt = _target(con) if con is not None else None
        out.append(f"{tgt.name if tgt is not None else ''}W{info['i']}")
    return out


def _taken_names():
    names = {o.name for o in bpy.data.objects} | set(joint_names())
    for ob in _owners():
        names |= set(_registry(ob))
    return names


def _new_node_name(owner, mtype, name=None):
    from ..operators import naming
    taken = _taken_names()
    if name:
        if name not in taken:
            return name
        base = naming.base_name(name)
        return f"{base}{naming.next_number(base, taken)}"
    base = f"{owner.name}_{mtype}"
    return f"{base}{naming.next_number(base, taken)}"


def _keys_of(cons):
    """Channel keys the Blender constraints ``cons`` drive (the Channel Box's rule)."""
    return set(_cb().constrained_keys(types.SimpleNamespace(constraints=list(cons))))


def _foreign_keys(ob, node=None):
    """Channels of ``ob`` that something other than ``node`` drives: other constraints, connections / drivers."""
    own = set(_registry(ob).get(node, {}).get("targets", {})) if node else set()
    keys = _keys_of(c for c in ob.constraints if c.name not in own)
    cb = _cb()
    keys |= {k for k in MAIN_KEYS + ("v",) if cb.driver(ob, k) is not None}
    return keys


def _requested_keys(mtype, skip=(), skip_t=(), skip_r=()):
    out = set()
    for c in CHANNELS[mtype]:
        sk = set(skip) | set(skip_t if c == "t" else skip_r if c == "r" else ())
        out |= {c + a for a in "xyz" if a not in sk}
    return out


def _axes(value):
    if value in (None, False):
        return ()
    vals = value if isinstance(value, (list, tuple)) else [value]
    out = set()
    for v in vals:
        v = str(v).lower()
        if v == "none":
            continue
        out.add(v)
    return tuple(out)


def _raw_frame(ob):
    """World matrix of ``ob``'s parent space (the constraint stack works after it)."""
    if ob.parent is not None and ob.parent_type == 'OBJECT':
        return ob.parent.matrix_world @ ob.matrix_parent_inverse
    return Matrix.Identity(4)


def _own_world(ob):
    """``ob``'s world matrix without its constraints."""
    return _raw_frame(ob) @ ob.matrix_basis


def _no_scale(m):
    t, q, _s = m.decompose()
    return Matrix.LocRotScale(t, q, None)


def evaluated_local(ob):
    """Maya's local matrix of ``ob`` after its constraints (without the pivot offset): what Maya's channels read."""
    return Matrix.Translation(-Vector(ob.delta_location)) @ _raw_frame(ob).inverted_safe() @ ob.matrix_world


def maya_euler(m3, order='XYZ'):
    """Maya's Euler angles of a rotation: the middle axis within +-90 degrees (Maya: aim (0 1 0) / up (1 0 0) ->
    -180 0 135, where Blender's ``to_euler`` gives -0 180 -45, the smaller angle sum)."""
    e = list(m3.to_euler(order))
    mid = "XYZ".index(order[1])
    if abs(e[mid]) > math.pi / 2 + 1e-6:
        for i in range(3):
            if i == mid:
                e[i] = math.pi - e[i]
                e[i] = e[i] - 2 * math.pi if e[i] > math.pi else e[i] + 2 * math.pi if e[i] <= -math.pi else e[i]
            else:
                e[i] = e[i] - math.pi if e[i] >= 0 else e[i] + math.pi
    return e


def _channel_values(ob, m):
    """{key: Maya value} of the local matrix ``m`` (BU)."""
    t, _q, s = m.decompose()
    order = ob.rotation_mode if ob.rotation_mode in ('XYZ', 'YZX', 'ZXY', 'XZY', 'YXZ', 'ZYX') else 'XYZ'
    e = maya_euler(m.to_3x3().normalized(), order)
    out = {}
    for i, a in enumerate("xyz"):
        out["t" + a] = _from_bu(t[i])
        out["r" + a] = _from_rad(e[i])
        out["s" + a] = s[i]
    return out


def constrained_values(ob):
    """{key: Maya channel value} for the channels of ``ob`` its constraints drive (Maya's channels hold the
    constraint's output; Blender's keep the object's own values under the constraint)."""
    keys = _keys_of(ob.constraints) & set(MAIN_KEYS)
    if not keys:
        return {}
    _view_layer()
    vals = _channel_values(ob, evaluated_local(ob))
    return {k: vals[k] for k in keys}


def _bake(ob, keys):
    """Write the constrained values of ``keys`` into ``ob``'s own channels (Maya: a deleted constraint leaves the
    channels at their last value)."""
    if not keys:
        return
    _view_layer()
    m = evaluated_local(ob)
    t, _q, s = m.decompose()
    order = ob.rotation_mode if ob.rotation_mode in ('XYZ', 'YZX', 'ZXY', 'XZY', 'YXZ', 'ZYX') else 'XYZ'
    e = m.to_3x3().normalized().to_euler(order, ob.rotation_euler)
    for i, a in enumerate("xyz"):
        if "t" + a in keys:
            ob.location[i] = t[i]
        if "r" + a in keys and ob.rotation_mode == order:
            ob.rotation_euler[i] = e[i]
        if "s" + a in keys:
            ob.scale[i] = s[i]


def _up_helper(node, world_up):
    """A hidden empty (no scene, fake user) whose Z axis is ``world_up``: the space an aim node's Track To runs in."""
    h = bpy.data.objects.get(UP_PREFIX + node) or bpy.data.objects.new(UP_PREFIX + node, None)
    h.use_fake_user = True
    h.rotation_mode = 'QUATERNION'
    w = Vector(world_up)
    h.rotation_quaternion = Vector((0.0, 0.0, 1.0)).rotation_difference(w.normalized() if w.length else w)
    h.matrix_world = h.matrix_basis.copy()
    return h


def _axis(v, what):
    from ..operators import rig_tools
    a = rig_tools.axis_of(v)
    if a is None:
        raise RuntimeError(f"aimConstraint: Blender aims along an axis: the {what} vector must be +-X, +-Y or +-Z")
    return a


def _add_blender(owner, node, entry, target, mtype, mo, skip):
    """The Blender constraint for one more target of ``node``; returns it."""
    cons = owner.constraints
    _view_layer()
    tw = target.matrix_world.copy()
    if mtype == "aimConstraint":
        a = _axis(entry["aim"], "aim")
        track = ("TRACK_" if a[1] > 0 else "TRACK_NEGATIVE_") + a[0]
        if entry["wut"] == "none":
            con = cons.new('DAMPED_TRACK')
            con.track_axis = track
        else:
            u = _axis(entry["up"], "up")
            if u[1] < 0 or u[0] == a[0]:
                raise RuntimeError("aimConstraint: Blender's Track To needs an up vector along a positive axis other "
                                   "than the aim vector's")
            con = cons.new('TRACK_TO')
            con.track_axis, con.up_axis, con.use_target_z = track, "UP_" + u[0], False
            con.owner_space = con.target_space = 'CUSTOM'
            con.space_object = _up_helper(node, entry["wu"])
        con.target = target
        return con
    if not mo and mtype == "pointConstraint":
        con = cons.new('COPY_LOCATION')
    elif not mo and mtype == "orientConstraint":
        con = cons.new('COPY_ROTATION')
    elif not mo and mtype == "scaleConstraint":
        con = cons.new('COPY_SCALE')
    else:
        con = cons.new('CHILD_OF')
    con.target = target
    if con.type in ('COPY_LOCATION', 'COPY_ROTATION', 'COPY_SCALE'):
        for a in "xyz":
            setattr(con, "use_" + a, a not in skip.get(CHANNELS[mtype], ()))
        return con
    # Child Of: parent (t r), or the one channel group of a point / orient / scale node with Maintain Offset
    groups = CHANNELS[mtype]
    for c, prop in (("t", "use_location_"), ("r", "use_rotation_"), ("s", "use_scale_")):
        for a in "xyz":
            setattr(con, prop + a, c in groups and a not in skip.get(c, ()))
    if mtype == "parentConstraint":
        con.inverse_matrix = _no_scale(tw if mo else _own_world(owner)).inverted_safe()
    elif mtype == "pointConstraint":
        con.inverse_matrix = Matrix.Translation(-tw.translation)
    elif mtype == "orientConstraint":
        con.inverse_matrix = tw.to_quaternion().to_matrix().to_4x4().inverted_safe()
    else:
        con.inverse_matrix = Matrix.Diagonal(Vector([*tw.to_scale(), 1.0])).inverted_safe()
    con.set_inverse_pending = False
    return con


def _reweigh(owner, entry):
    """Influence of target i = w_i / (w_1 + ... + w_i): the stack gives Maya's weighted blend."""
    total = 0.0
    for cname, info in entry["targets"].items():
        con = owner.constraints.get(cname)
        if con is None:
            continue
        total += max(0.0, float(info["w"]))
        con.influence = (float(info["w"]) / total) if total > 0 else 0.0


def _remove_node(owner, node, bake=True):
    reg = _registry(owner)
    entry = reg.pop(node, None)
    if entry is None:
        return
    cons = _cons(owner, entry)
    if bake:
        _bake(owner, _keys_of(cons))
    for con in cons:
        owner.constraints.remove(con)
    h = bpy.data.objects.get(UP_PREFIX + node)
    if h is not None:
        bpy.data.objects.remove(h)
    _store(owner, reg)
    _view_layer()


def delete_node(name):
    """Delete a Maya constraint node (Maya: the channels keep their last value). True if it was one."""
    hit = find_node(name)
    if hit is None:
        return False
    _remove_node(hit[0], hit[1])
    return True


def _resolve(mtype, names):
    """(constrained object, its ``mtype`` node or None, target objects) of a constraint command's objects."""
    if len(names) == 1:
        hit = find_node(names[0])
        if hit is not None:
            return hit[0], hit[1], []
        ob = _object(names[0])
        return ob, _node_of_type(ob, mtype), []
    obs = [_object(n) for n in names]
    return obs[-1], _node_of_type(obs[-1], mtype), obs[:-1]


def _con_of_target(owner, entry, target):
    for cname in entry["targets"]:
        con = owner.constraints.get(cname)
        if con is not None and _target(con) is target:
            return cname
    return None


def _vec(v, default):
    return [float(x) for x in (v if v is not None else default)]


def _constrain(mtype, args, kwargs):
    f = _Flags(mtype, kwargs)
    query = f.get("query", "q", False)
    edit = f.get("edit", "e", False)
    remove = f.get("remove", "rm", False)
    mo = f.get("maintainOffset", "mo", False)
    weight = f.get("weight", "w")
    name = f.get("name", "n")
    tl = f.get("targetList", "tl", False)
    wal = f.get("weightAliasList", "wal", False)
    offset = f.get("offset", "o")
    skip = _axes(f.get("skip", "sk"))
    skip_t = _axes(f.get("skipTranslate", "st")) if mtype == "parentConstraint" else ()
    skip_r = _axes(f.get("skipRotate", "sr")) if mtype == "parentConstraint" else ()
    aim = f.get("aimVector", "aim") if mtype == "aimConstraint" else None
    up = f.get("upVector", "u") if mtype == "aimConstraint" else None
    wu = f.get("worldUpVector", "wu") if mtype == "aimConstraint" else None
    wut = f.get("worldUpType", "wut") if mtype == "aimConstraint" else None
    f.get("layer", "l")
    f.done()
    names = [str(n) for n in _flatten(args)] or [o.name for o in _selection()]
    if not names:
        raise RuntimeError(f"{mtype}: Nothing selected")
    owner, node, targets = _resolve(mtype, names)

    if query:
        if node is None:
            return None
        entry = _registry(owner)[node]
        if tl:
            out = []
            for con in _cons(owner, entry):
                tgt = _target(con)
                out.append(tgt.name if tgt is not None else "")
            return out
        if wal:
            return _aliases(owner, entry)
        if weight:
            infos = list(entry["targets"].items())
            if targets:
                picked = [entry["targets"][c]["w"] for c in (_con_of_target(owner, entry, t) for t in targets)
                          if c is not None]
                return float(picked[0]) if len(picked) == 1 else [float(w) for w in picked]
            return [float(i["w"]) for _c, i in infos]
        if offset:
            return [float(x) for x in entry.get("offset", (0.0, 0.0, 0.0))]
        if aim:
            return [float(x) for x in entry["aim"]]
        if up:
            return [float(x) for x in entry["up"]]
        if wu:
            return [float(x) for x in entry["wu"]]
        if wut:
            return entry["wut"]
        if mo:
            return bool(entry.get("mo", False))
        return node

    if remove:
        if node is None:
            raise RuntimeError(f"{mtype}: {owner.name} has no {mtype}")
        reg = _registry(owner)
        entry = reg[node]
        for t in targets:
            cname = _con_of_target(owner, entry, t)
            if cname is None:
                continue
            if len(entry["targets"]) == 1:          # the last target: the node goes, the channels stay
                _remove_node(owner, node)
                return None
            owner.constraints.remove(owner.constraints[cname])
            del entry["targets"][cname]
        _reweigh(owner, entry)
        reg[node] = entry
        _store(owner, reg)
        _view_layer()
        return [node]

    if edit:
        if node is None:
            raise RuntimeError(f"{mtype}: {owner.name} has no {mtype}")
        reg = _registry(owner)
        entry = reg[node]
        if weight is not None:
            for t in (targets or [_target(c) for c in _cons(owner, entry)]):
                cname = _con_of_target(owner, entry, t)
                if cname is not None:
                    entry["targets"][cname]["w"] = float(weight)
        _reweigh(owner, entry)
        reg[node] = entry
        _store(owner, reg)
        _view_layer()
        return [node]

    if not targets:
        raise RuntimeError(f"{mtype}: Select the target(s) and then the object to constrain")
    if mo and mtype == "aimConstraint":
        raise RuntimeError("aimConstraint -maintainOffset is not supported in Maya Workflow Kit")
    want = _requested_keys(mtype, skip, skip_t, skip_r)
    busy = want & _foreign_keys(owner, node)
    if busy:
        key = sorted(busy)[0]
        long = {"t": "translate", "r": "rotate", "s": "scale"}[key[0]] + key[1].upper()
        raise RuntimeError(f"{mtype}: '{owner.name}.{long}' is already connected: Object is already connected.")
    reg = _registry(owner)
    if node is None:
        node = _new_node_name(owner, mtype, name)
        entry = {"type": mtype, "targets": {}, "next": 0, "mo": bool(mo)}
        if mtype == "aimConstraint":
            entry.update(aim=_vec(aim, (1, 0, 0)), up=_vec(up, (0, 1, 0)), wu=_vec(wu, (0, 1, 0)),
                         wut=str(wut or "vector").lower())
            if entry["wut"] == "scene":
                entry["wu"] = [0.0, 1.0, 0.0]
            elif entry["wut"] not in ("vector", "none"):
                raise RuntimeError(f"aimConstraint: world up type '{wut}' is not supported in Maya Workflow Kit")
    else:
        entry = reg[node]
    skip_by = {"t": tuple(set(skip) | set(skip_t)), "r": tuple(set(skip) | set(skip_r)), "s": tuple(skip)}
    _view_layer()
    for t in targets:
        if t is owner:
            raise RuntimeError(f"{mtype}: an object can't constrain itself")
        if _con_of_target(owner, entry, t) is not None:
            continue
        i = int(entry["next"])
        if mtype == "orientConstraint" and mo and not entry["targets"]:
            off = (t.matrix_world.to_quaternion().to_matrix().inverted() @
                   _own_world(owner).to_quaternion().to_matrix()).to_euler('XYZ')
            entry["offset"] = [off.x, off.y, off.z]        # Maya's q -offset reads radians
        con = _add_blender(owner, node, entry, t, mtype, mo, skip_by)
        con.name = node if not entry["targets"] else f"{node} {i}"
        entry["targets"][con.name] = {"i": i, "w": float(1.0 if weight is None else weight)}
        entry["next"] = i + 1
    _reweigh(owner, entry)
    reg[node] = entry
    _store(owner, reg)
    _view_layer()
    return [node]


def parentConstraint(*args, **kwargs):
    """``parentConstraint target... object``: the object follows the targets' translate / rotate (Child Of).
    Returns ['<object>_parentConstraintN']; ``-q`` / ``-e`` / ``-rm`` / ``-w`` / ``-mo`` / ``-n`` like Maya."""
    return _constrain("parentConstraint", args, kwargs)


def pointConstraint(*args, **kwargs):
    """``pointConstraint``: the object's pivot on the targets' weighted pivot (Copy Location)."""
    return _constrain("pointConstraint", args, kwargs)


def orientConstraint(*args, **kwargs):
    """``orientConstraint``: the targets' world rotation (Copy Rotation; with ``-mo`` the offset as a rotation)."""
    return _constrain("orientConstraint", args, kwargs)


def scaleConstraint(*args, **kwargs):
    """``scaleConstraint``: the targets' scale (Copy Scale)."""
    return _constrain("scaleConstraint", args, kwargs)


def aimConstraint(*args, **kwargs):
    """``aimConstraint``: the aim vector at the target, the up vector towards the world up vector (defaults
    like Maya: aim 1 0 0, up 0 1 0, world up type vector 0 1 0)."""
    return _constrain("aimConstraint", args, kwargs)


# --- joints --------------------------------------------------------------------------------------------------------

def _skeletons():
    return [o for o in bpy.context.scene.objects if o is not None and o.type == 'ARMATURE']


def joint_names():
    return [b.name for arm in _skeletons() for b in arm.data.bones]


def find_joint(name):
    """(armature object, bone) of the Maya joint ``name``, else None."""
    short = str(name).rsplit("|", 1)[-1]
    for arm in _skeletons():
        b = arm.data.bones.get(short)
        if b is not None:
            return arm, b
    return None


def joint_world(arm, bone):
    """Maya world matrix of a joint: its position, the pose turn (jointOrient 0: the bone's rest axis is not Maya's)."""
    pb = arm.pose.bones[bone.name]
    turn = (pb.matrix @ bone.matrix_local.inverted()).to_3x3()
    m = turn.to_4x4()
    m.translation = pb.head
    return arm.matrix_world @ m


def _joint_parent_world(arm, bone):
    if bone.parent is not None:
        return joint_world(arm, bone.parent)
    from .cmds_shim import _frame
    return _frame(arm) @ Matrix.Translation(-Vector(arm.delta_location))


def joint_local(arm, bone):
    return _joint_parent_world(arm, bone).inverted_safe() @ joint_world(arm, bone)


def _joint_attr(arm, bone, attr, time=None):
    """getAttr on a joint (translate / rotate / scale / radius / jointOrient / visibility)."""
    _view_layer()
    vals = _channel_values(arm, joint_local(arm, bone))
    comp = {"translate": "t", "t": "t", "rotate": "r", "r": "r", "scale": "s", "s": "s"}
    if attr in comp:
        return [tuple(vals[comp[attr] + a] for a in "xyz")]
    key = _KEY.get(attr, attr)
    if key in vals:
        return vals[key]
    if attr in ("radius", "rad"):
        return float(bone.get(JOINT_RADIUS, 1.0))
    if attr in ("jointOrient", "jo"):
        jo = bone.get(JOINT_ORIENT, (0.0, 0.0, 0.0))
        return [tuple(_from_rad(float(x)) for x in jo)]
    if attr in ("jointOrientX", "jox", "jointOrientY", "joy", "jointOrientZ", "joz"):
        jo = bone.get(JOINT_ORIENT, (0.0, 0.0, 0.0))
        return _from_rad(float(jo["XYZ".index(attr[-1].upper())]))
    if attr in ("visibility", "v"):
        return not bone.hide
    raise ValueError(f"No attribute '{attr}' on {bone.name}")


def _joint_name(name):
    from ..operators import joints, naming
    taken = _taken_names()
    if name:
        if name not in taken:
            return str(name)
        base = naming.base_name(str(name))
        return f"{base}{naming.next_number(base, taken)}"
    return joints.next_joint_name(extra=taken)


def _selected_joint(context):
    """(armature, bone name) of the selected (lead) joint, else None."""
    act = context.view_layer.objects.active
    if act is None or act.type != 'ARMATURE' or act.mode != 'POSE' or not act.select_get():
        return None
    cb = _cb()
    picked = [pb for pb in act.pose.bones if cb.bone_selected(pb)]
    if not picked:
        return None
    active = act.data.bones.active
    lead = next((pb for pb in picked if active is not None and pb.name == active.name), picked[-1])
    return act, lead.name


def _object_mode(context):
    act = context.view_layer.objects.active
    if act is not None and act.mode != 'OBJECT':
        with context.temp_override(active_object=act, object=act):
            bpy.ops.object.mode_set(mode='OBJECT')


def joint(*args, **kwargs):
    """``joint -p x y z`` = Skeleton > Create Joints for one click: a joint at the world position ``p`` under the
    selected joint (a new skeleton when no joint is selected; a selected transform becomes the new skeleton's parent,
    the joint keeping its world position). Maya names (joint1, -n tip), radius 1, jointOrient 0 0 0 (no auto orient);
    the new joint is the selection (pose mode). Returns its name (a string)."""
    from ..operators import joints, parenting
    f = _Flags("joint", kwargs)
    query = f.get("query", "q", False)
    edit = f.get("edit", "e", False)
    pos = f.get("position", "p")
    name = f.get("name", "n")
    rad = f.get("radius", "rad")
    relative = f.get("relative", "r", False)
    f.get("absolute", "a", False)
    f.get("zeroScaleOrient", "zso", False)
    f.get("scaleCompensate", "sc", True)
    f.done()
    context = bpy.context
    if query or edit:
        names = [str(n) for n in _flatten(args)]
        hit = find_joint(names[0]) if names else (lambda s: find_joint(s[1]) if s else None)(_selected_joint(context))
        if hit is None:
            raise RuntimeError("joint: no joint given")
        arm, bone = hit
        if query:
            if rad:
                return float(bone.get(JOINT_RADIUS, 1.0))
            if pos:
                _view_layer()
                return [_from_bu(x) for x in joint_world(arm, bone).translation]
            if name:
                return bone.name
            raise TypeError("joint -query needs -position, -radius or -name")
        if rad is not None:
            bone[JOINT_RADIUS] = float(rad)
        return None
    if args:
        raise TypeError("joint takes no objects (it works on the selection)")
    _view_layer()
    point = Vector([_to_bu(float(x)) for x in pos]) if pos is not None else Vector()
    picked = _selected_joint(context)
    under = None
    if picked is None:
        sel = _selection()
        if sel and sel[-1].type != 'ARMATURE':
            under = sel[-1]
    jname = _joint_name(name)
    if picked is not None:
        arm, parent = picked
        if relative:
            point = joint_world(arm, arm.data.bones[parent]).translation + point
        for o in [o for o in context.view_layer.objects if o is not None and o.select_get()]:
            if o is not arm:
                o.select_set(False)
        context.view_layer.objects.active = arm
        with context.temp_override(active_object=arm, object=arm):
            bpy.ops.object.mode_set(mode='EDIT')
    else:
        _object_mode(context)
        arm, parent = joints.new_skeleton(context), None
    made = joints.add_joint(arm, point, parent, length=linear_factor())
    ebs = arm.data.edit_bones
    if made == parent:                     # Maya makes a joint on its parent's position too
        eb = ebs.new(jname)
        eb.head = arm.matrix_world.inverted() @ point
        eb.tail = eb.head + Vector((0.0, 0.0, linear_factor()))
        eb.parent = ebs[parent]
    else:
        ebs[made].name = jname
    with context.temp_override(active_object=arm, object=arm):
        joints.finish(context, arm, [jname])
    bone = arm.data.bones[jname]
    if rad is not None:
        bone[JOINT_RADIUS] = float(rad)
    bone[JOINT_ORIENT] = (0.0, 0.0, 0.0)
    if under is not None:
        _view_layer()
        parenting.set_parent_maya(arm, under)
    _view_layer()
    return jname


def _select_joints(names, add=False):
    context = bpy.context
    hits = [find_joint(n) for n in names]
    arm = hits[-1][0]
    act = context.view_layer.objects.active
    if act is not None and act is not arm and act.mode != 'OBJECT':
        _object_mode(context)
    if not add:
        for o in context.view_layer.objects:
            if o is not None and o is not arm and o.select_get():
                o.select_set(False)
    arm.select_set(True)
    context.view_layer.objects.active = arm
    if arm.mode != 'POSE':
        with context.temp_override(active_object=arm, object=arm):
            bpy.ops.object.mode_set(mode='POSE')
    cb = _cb()
    if not add:
        for pb in arm.pose.bones:
            cb.set_bone_selected(pb, False)
    for a, b in hits:
        if a is arm:
            cb.set_bone_selected(arm.pose.bones[b.name], True)
    arm.data.bones.active = hits[-1][1]


def _delete_joints(hits):
    context = bpy.context
    by_arm = {}
    for arm, bone in hits:
        by_arm.setdefault(arm, []).append(bone.name)
    for arm, names in by_arm.items():
        _object_mode(context)
        context.view_layer.objects.active = arm
        with context.temp_override(active_object=arm, object=arm):
            bpy.ops.object.mode_set(mode='EDIT')
            ebs = arm.data.edit_bones
            for n in names:
                eb = ebs.get(n)
                if eb is not None:
                    for b in [*eb.children_recursive, eb]:
                        ebs.remove(b)
            bpy.ops.object.mode_set(mode='OBJECT')


# --- connections (drivers with variable ``cn``, ui/connection_editor.py) -------------------------------------------

def _plug(text):
    """(object, Maya long attribute name) of ``node.attr``."""
    text = str(text)
    if "." not in text:
        raise RuntimeError(f"Expected node.attribute, got '{text}'")
    node, attr = text.split(".", 1)
    attr = attr.rsplit(".", 1)[-1]               # pCube1.translate.translateX
    ob = _object(node)
    long = _LONG.get(attr, attr)
    ce = _ce()
    if long not in ce.COMPOUNDS and ce.resolve(ob, long) is None:
        raise RuntimeError(f"No attribute '{attr}' on {ob.name}")
    return ob, long


def _plug_text(ob, long):
    """Maya's message form: a compound child with its parent (pCube1.translate.translateX)."""
    for comp, leaves in _ce().COMPOUNDS.items():
        if long in leaves:
            return f"{ob.name}.{comp}.{long}"
    return f"{ob.name}.{long}"


def connections():
    """Every kit connection in the scene: [(source object, source leaf, destination object, destination leaf)]."""
    ce = _ce()
    out = []
    for ob in bpy.context.scene.objects:
        if ob is None or ob.animation_data is None:
            continue
        for fc in ob.animation_data.drivers:
            leaf = next((n for n, (p, i, _k) in ce.SIMPLE.items() if p == fc.data_path and
                         (i < 0 or i == fc.array_index)), None)
            if leaf is None and fc.data_path.startswith('["') and fc.data_path.endswith('"]'):
                leaf = fc.data_path[2:-2]
            if leaf is None:
                continue
            src = ce.source_of(ob, leaf)
            if src is not None:
                out.append((src[0], src[1], ob, leaf))
    return out


def _leaf_key(ob, leaf):
    return _KEY.get(leaf) or (_cb().CUSTOM_PREFIX + leaf)


def connectAttr(*args, **kwargs):
    """``connectAttr src.attr dst.attr``: ``dst`` follows ``src`` (a compound child by child, Maya's unit
    conversion). A connected or constrained destination is an error unless ``-f`` (which replaces the connection).
    Returns Maya's message "Connected a.translate.translateX to b.translate.translateY."."""
    f = _Flags("connectAttr", kwargs)
    force = f.get("force", "f", False)
    f.get("lock", "l", False)
    f.get("nextAvailable", "na", False)
    f.done()
    plugs = [str(a) for a in _flatten(args)]
    if len(plugs) != 2:
        raise RuntimeError("connectAttr: Expected a source and a destination attribute")
    from . import cmds_misc
    texture = cmds_misc.connect_texture(plugs[0], plugs[1])     # file1.outColor -> lambert2.color (shading network)
    if texture is not None:
        return texture
    src, s_attr = _plug(plugs[0])
    dst, d_attr = _plug(plugs[1])
    ce = _ce()
    s_leaves, d_leaves = ce.leaves(s_attr), ce.leaves(d_attr)
    if len(s_leaves) != len(d_leaves):
        raise RuntimeError(f"connectAttr: The attribute '{_plug_text(src, s_attr)}' cannot be connected to "
                           f"'{_plug_text(dst, d_attr)}'.")
    busy = _foreign_keys(dst)
    for d in d_leaves:
        key = _leaf_key(dst, d)
        if (key in busy or _cb().driver(dst, key) is not None) and not force:
            raise RuntimeError(f"connectAttr: The destination attribute '{dst.name}.{d}' is already connected.")
    try:
        ce.connect(bpy.context.scene, src, s_attr, dst, d_attr)
    except ValueError as ex:
        raise RuntimeError(f"connectAttr: {ex}") from None
    _view_layer()
    return f"Connected {_plug_text(src, s_attr)} to {_plug_text(dst, d_attr)}."


def disconnectAttr(*args, **kwargs):
    """``disconnectAttr src.attr dst.attr``: the destination keeps its current value. Returns "Disconnect a.attr
    from b.attr."; no such connection is an error."""
    f = _Flags("disconnectAttr", kwargs)
    f.get("nextAvailable", "na", False)
    f.done()
    plugs = [str(a) for a in _flatten(args)]
    if len(plugs) != 2:
        raise RuntimeError("disconnectAttr: Expected a source and a destination attribute")
    src, s_attr = _plug(plugs[0])
    dst, d_attr = _plug(plugs[1])
    ce = _ce()
    if not ce.connected(src, s_attr, dst, d_attr):
        raise RuntimeError(f"disconnectAttr: There is no connection from '{_plug_text(src, s_attr)}' to "
                           f"'{_plug_text(dst, d_attr)}' to disconnect.")
    _view_layer()
    ce.disconnect(dst, d_attr)
    _view_layer()
    return f"Disconnect {_plug_text(src, s_attr)} from {_plug_text(dst, d_attr)}."


def isConnected(*args, **kwargs):
    f = _Flags("isConnected", kwargs)
    f.get("ignoreUnitConversion", "iuc", False)
    f.done()
    plugs = [str(a) for a in _flatten(args)]
    if len(plugs) != 2:
        raise RuntimeError("isConnected: Expected a source and a destination attribute")
    src, s_attr = _plug(plugs[0])
    dst, d_attr = _plug(plugs[1])
    return bool(_ce().connected(src, s_attr, dst, d_attr))


def _matching(node_text):
    """(object, leaves or None for the whole node) of a listConnections / connectionInfo argument."""
    text = str(node_text)
    if "." in text:
        ob, long = _plug(text)
        return ob, set(_ce().leaves(long))
    return _object(text), None


def listConnections(*args, **kwargs):
    """Sources / destinations of a node or plug's connections (``-s`` / ``-d`` default on, ``-p`` = plugs).
    None when there are none."""
    f = _Flags("listConnections", kwargs)
    s = f.get("source", "s", True)
    d = f.get("destination", "d", True)
    plugs = f.get("plugs", "p", False)
    f.get("connections", "c", False)
    f.get("skipConversionNodes", "scn", False)
    typ = f.get("type", "t")
    f.done()
    names = [str(a) for a in _flatten(args)] or [o.name for o in _selection()]
    from . import cmds_misc
    if len(names) == 1:
        shading = cmds_misc.shading_sources(names[0])       # a kit material plug: its texture node
        if shading is not None:
            return (shading if plugs else [p.split(".")[0] for p in shading]) or None
        if typ == "shadingEngine":
            try:
                kind = cmds_misc.nodeType(names[0].split(".")[0])
            except RuntimeError:
                kind = None
            if "shadingDependNode" in cmds_misc.CHAINS.get(kind, ()):
                return None                                 # kit materials have no shading group nodes
    out = []
    for n in names:
        ob, leaves = _matching(n)
        for so, sl, do, dl in connections():
            if s and do is ob and (leaves is None or dl in leaves):
                out.append(f"{so.name}.{sl}" if plugs else so.name)
            if d and so is ob and (leaves is None or sl in leaves):
                out.append(f"{do.name}.{dl}" if plugs else do.name)
    if typ is not None:
        out = [o for o in out if typ == "transform"]
    return out or None


def connectionInfo(*args, **kwargs):
    """``-sfd`` = the source plug ('' when none), ``-dfs`` = destination plugs, ``-id`` / ``-is`` = bools."""
    f = _Flags("connectionInfo", kwargs)
    sfd = f.get("sourceFromDestination", "sfd", False)
    dfs = f.get("destinationFromSource", "dfs", False)
    is_dst = f.get("isDestination", "id", False)
    is_src = f.get("isSource", "is", False)
    f.get("isExactDestination", "ied", False)
    f.get("isExactSource", "ies", False)
    f.done()
    names = [str(a) for a in _flatten(args)]
    if len(names) != 1 or "." not in names[0]:
        raise RuntimeError("connectionInfo: Expected one attribute")
    ob, leaves = _matching(names[0])
    conns = connections()
    srcs = [f"{so.name}.{sl}" for so, sl, do, dl in conns if do is ob and dl in leaves]
    dsts = [f"{do.name}.{dl}" for so, sl, do, dl in conns if so is ob and sl in leaves]
    if sfd:
        return srcs[0] if srcs else ""
    if dfs:
        return dsts
    if is_dst:
        return bool(srcs)
    if is_src:
        return bool(dsts)
    raise TypeError("connectionInfo needs -sourceFromDestination, -destinationFromSource, -isDestination or "
                    "-isSource")


# --- the DAG commands' view of joints and constraint nodes -------------------------------------------------------

def node_type(name):
    """Maya node type of a joint / kit constraint node ('joint', 'pointConstraint' ...), else None (nodeType)."""
    if find_joint(name) is not None and bpy.data.objects.get(str(name).rsplit("|", 1)[-1]) is None:
        return "joint"
    hit = find_node(name)
    return hit[2]["type"] if hit is not None else None


def _is_joint(name):
    return isinstance(name, str) and bpy.data.objects.get(name.rsplit("|", 1)[-1]) is None and \
        find_joint(name) is not None


def _flag(kwargs, long, short=None, default=None):
    for k in (long, short):
        if k and k in kwargs:
            return kwargs[k]
    return default


def _get_attr(fn, args, kwargs):
    attr = str(args[0]) if args else ""
    if "." not in attr:
        return PASS
    node, name = attr.split(".", 1)
    hit = find_node(node)
    if hit is not None:
        owner, n, entry = hit
        aliases = _aliases(owner, entry)
        if name in aliases:
            info = list(entry["targets"].values())[aliases.index(name)]
            return float(info["w"])
        if name in ("offset", "o") and "offset" in entry:
            return [tuple(_from_rad(float(x)) for x in entry["offset"])]
        raise ValueError(f"No attribute '{name}' on {n}")
    if _is_joint(node):
        arm, bone = find_joint(node)
        return _joint_attr(arm, bone, name)
    try:
        ob = _object(node)
    except (ValueError, RuntimeError):
        return PASS
    _view_layer()                 # connections and constraints show their result
    if any(k in kwargs for k in ("lock", "l", "keyable", "k", "channelBox", "cb", "type", "typ", "time", "t")):
        return PASS
    vals = constrained_values(ob)
    if not vals:
        return PASS
    from .cmds_shim import channel_keys
    keys = channel_keys(ob, name)
    if not keys or not any(k in vals for k in keys):
        return PASS
    res = fn(*args, **kwargs)
    if len(keys) == 3:
        return [tuple(vals.get(k, v) for k, v in zip(keys, res[0]))]
    return vals.get(keys[0], res)


def _set_attr(fn, args, kwargs):
    attr = str(args[0]) if args else ""
    if "." not in attr:
        return PASS
    node, name = attr.split(".", 1)
    values = list(_flatten(args[1:]))
    hit = find_node(node)
    if hit is not None:
        owner, n, entry = hit
        aliases = _aliases(owner, entry)
        if name not in aliases or not values:
            raise RuntimeError(f"setAttr: '{n}.{name}' can't be set in Maya Workflow Kit")
        reg = _registry(owner)
        cname = list(entry["targets"])[aliases.index(name)]
        reg[n]["targets"][cname]["w"] = float(values[0])
        _reweigh(owner, reg[n])
        _store(owner, reg)
        _view_layer()
        return None
    if _is_joint(node):
        arm, bone = find_joint(node)
        if name in ("radius", "rad") and values:
            bone[JOINT_RADIUS] = float(values[0])
            return None
        raise RuntimeError(f"setAttr: '{node}.{name}' of a joint can't be set by script in Maya Workflow Kit")
    if not values:
        return PASS
    try:
        ob = _object(node)
    except (ValueError, RuntimeError):
        return PASS
    from .cmds_shim import channel_keys
    keys = channel_keys(ob, name) or ()
    busy = _foreign_keys(ob)
    if any(k in busy for k in keys):
        raise RuntimeError(f"setAttr: The attribute '{ob.name}.{name}' is locked or connected and cannot be "
                           f"modified.")
    return PASS


def _xform(fn, args, kwargs):
    names = [n for n in _flatten(args) if isinstance(n, str)]
    if not names or not _is_joint(names[0]):
        return PASS
    arm, bone = find_joint(names[0])
    if not _flag(kwargs, "query", "q", False):
        raise RuntimeError("xform: moving a joint by script is not supported in Maya Workflow Kit")
    _view_layer()
    ws = _flag(kwargs, "worldSpace", "ws", False)
    m = joint_world(arm, bone) if ws else joint_local(arm, bone)
    if _flag(kwargs, "rotatePivot", "rp") or _flag(kwargs, "scalePivot", "sp") or \
            _flag(kwargs, "translation", "t"):
        return [_from_bu(x) for x in m.translation]
    if _flag(kwargs, "rotation", "ro"):
        return [_from_rad(x) for x in maya_euler(m.to_3x3().normalized())]
    if _flag(kwargs, "matrix", "m"):
        k = linear_factor()
        return [m[i][j] / k if (i < 3 and j == 3) else m[i][j] for j in range(4) for i in range(4)]
    raise TypeError("xform -query on a joint needs -translation, -rotation, -matrix or a pivot flag")


def _joint_children(arm, bone):
    return [b.name for b in bone.children]


def _joint_branch(arm, bone):
    out = []
    for c in bone.children:
        out += _joint_branch(arm, c)
    return out + [bone.name]


def _root_joints(ob):
    return [b.name for b in ob.data.bones if b.parent is None] if ob.type == 'ARMATURE' else []


def _list_relatives(fn, args, kwargs):
    names = [str(n) for n in _flatten(args)]
    parent_ = _flag(kwargs, "parent", "p", False) or _flag(kwargs, "allParents", "ap", False)
    all_desc = _flag(kwargs, "allDescendents", "ad", False)
    shapes = _flag(kwargs, "shapes", "s", False)
    typ = _flag(kwargs, "type", "typ")
    types_ = [typ] if isinstance(typ, str) else list(typ or [])
    if names and any(_is_joint(n) for n in names):
        out = []
        for n in names:
            arm, bone = find_joint(n)
            if parent_:
                rel = [bone.parent.name] if bone.parent is not None else \
                    ([arm.parent.name] if arm.parent is not None else [])
            elif shapes:
                rel = []
            elif all_desc:
                rel = [x for c in bone.children for x in _joint_branch(arm, c)]
            else:
                rel = _joint_children(arm, bone)
            if types_:
                rel = [r for r in rel if any(t in ("joint", "transform", "dagNode") for t in types_)]
            out += [r for r in rel if r not in out]
        return out or None
    res = fn(*args, **kwargs)
    if parent_ or shapes:
        return res
    out = list(res or [])
    # kit skeletons are their joints in Maya's DAG
    for ob in [o for o in _skeletons() if o.name in out]:
        i = out.index(ob.name)
        roots = _root_joints(ob)
        if all_desc:
            roots = [x for r in roots for x in _joint_branch(ob, ob.data.bones[r])]
        if types_ and not any(t in ("joint", "transform", "dagNode") for t in types_):
            roots = []
        out[i:i + 1] = roots
    if not all_desc:
        try:
            obs = [_object(n) for n in names] if names else _selection()
        except (ValueError, RuntimeError):
            obs = []
        for ob in obs:
            for node, entry in nodes_of(ob):
                if types_ and not any(t in ("constraint", entry["type"]) for t in types_):
                    continue
                if node not in out:
                    out.append(node)
    return out or None


def _ls(fn, args, kwargs):
    typ = _flag(kwargs, "type", "typ")
    types_ = [typ] if isinstance(typ, str) else list(typ or [])
    sl = _flag(kwargs, "selection", "sl", False)
    names = [str(n) for n in _flatten(args)]
    special = [t for t in types_ if t in ("joint", "constraint") + CONSTRAINT_TYPES]
    if special and len(special) == len(types_):
        out = []
        if "joint" in special:
            out += sorted(joint_names())
        for ob in bpy.context.scene.objects:
            if ob is None:
                continue
            for node, entry in nodes_of(ob):
                if "constraint" in special or entry["type"] in special:
                    out.append(node)
        if names:
            out = [n for n in out if n in names]
        if sl:
            chosen = set(_ls(fn, (), {"sl": True}) or [])
            out = [n for n in out if n in chosen]
        return out
    if sl and not names:
        res = fn(*args, **kwargs)
        out = []
        cb = _cb()
        for n in res:
            ob = bpy.data.objects.get(n.rsplit("|", 1)[-1])
            if ob is not None and ob.type == 'ARMATURE' and ob.mode == 'POSE':
                picked = [pb.name for pb in ob.pose.bones if cb.bone_selected(pb)]
                active = ob.data.bones.active
                if active is not None and active.name in picked:
                    picked.remove(active.name)
                    picked.append(active.name)
                out += picked
            else:
                out.append(n)
        return out
    if names and any(_is_joint(n) or find_node(n) for n in names):
        return [n for n in names if _is_joint(n) or find_node(n) or bpy.data.objects.get(n)]
    return PASS


def _select(fn, args, kwargs):
    names = [str(n) for n in _flatten(args)]
    joint_hits = [n for n in names if _is_joint(n)]
    if joint_hits:
        _select_joints(joint_hits, add=bool(_flag(kwargs, "add", None, False)))
        rest = [n for n in names if n not in joint_hits]
        if rest:
            fn(*rest, add=True)
        return None
    act = bpy.context.view_layer.objects.active
    if act is not None and act.type == 'ARMATURE' and act.mode == 'POSE':
        _object_mode(bpy.context)       # Maya: picking objects leaves joint selection
    return PASS


def _delete(fn, args, kwargs):
    names = [n for n in _flatten(args)]
    strs = [str(n) for n in names if isinstance(n, str)]
    nodes = [n for n in strs if find_node(n) is not None]
    jnts = [n for n in strs if _is_joint(n)]
    if not nodes and not jnts:
        return PASS
    for n in nodes:
        delete_node(n)
    if jnts:
        _delete_joints([find_joint(n) for n in jnts])
    rest = [n for n in names if n not in nodes and n not in jnts]
    if rest:
        return fn(*rest, **kwargs)
    _view_layer()
    return None


def _obj_exists(fn, args, kwargs):
    name = str(args[0]) if args else ""
    node = name.split(".", 1)[0]
    hit = find_node(node)
    if hit is not None:
        return "." not in name or name.split(".", 1)[1] in _aliases(hit[0], hit[2])
    if _is_joint(node):
        return True
    return PASS


_INTERCEPT = {"getAttr": _get_attr, "setAttr": _set_attr, "xform": _xform, "listRelatives": _list_relatives,
              "ls": _ls, "select": _select, "delete": _delete, "objExists": _obj_exists}


def intercept(command, fn, args, kwargs):
    """Run ``command`` (cmds_shim / cmds_dag function ``fn``) for joints and constraint nodes, which are not Blender
    objects; returns PASS when it isn't about them (the caller then runs ``fn`` itself)."""
    handler = _INTERCEPT.get(command)
    if handler is None:
        return PASS
    return handler(fn, args, kwargs)
