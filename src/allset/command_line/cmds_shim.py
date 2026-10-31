# SPDX-License-Identifier: GPL-3.0-or-later
"""A ``maya.cmds`` look-alike for the command line (steps 7, 208).

Re-implemented from Maya's documented command behaviour (flag long/short
names, return values and Maya's results) — no Maya code. Numbers are in the
scene's display units like Maya's current linear unit (cm by default) and angles in degrees (radians if
the scene's rotation unit is radians). Attribute names match the Channel Box (``ui/channel_box.py`` MAIN). Channel
numbers are Blender's axes as they are (the Channel Box's convention); Maya's Y-up is not converted.

Supported: ls, select, move, rotate, scale, setAttr, getAttr, addAttr, xform, polyCube, polySphere, polyCylinder,
polyPlane, delete, rename, objExists, listRelatives, parent, group, duplicate, spaceLocator (``cmds_dag.py``),
currentTime, setKeyframe, cutKey, keyframe, playbackOptions (``cmds_anim.py``), file (``cmds_file.py``).
Anything else raises AttributeError.
"""

import fnmatch
import functools
import math
import re

import bpy
from mathutils import Matrix, Vector

from ..operators import units as _units

__all__ = ["ls", "select", "move", "rotate", "scale", "setAttr", "getAttr", "addAttr", "xform",
           "polyCube", "polySphere", "polyCylinder", "polyPlane", "delete", "rename",
           "objExists", "listRelatives", "currentTime",
           "parent", "group", "duplicate", "spaceLocator",
           "setKeyframe", "cutKey", "keyframe", "playbackOptions", "file",
           # step 216 (cmds_rig.py, cmds_misc.py)
           "makeIdentity", "parentConstraint", "pointConstraint", "orientConstraint", "scaleConstraint",
           "aimConstraint", "joint", "connectAttr", "disconnectAttr", "isConnected", "listConnections",
           "connectionInfo", "nodeType", "objectType", "attributeQuery", "currentUnit", "sets", "shadingNode",
           "polyExtrudeFacet", "polyEvaluate", "exactWorldBoundingBox", "listHistory", "camera"]


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    raise AttributeError(f"maya.cmds.{name} is not available in Maya Workflow Kit (cmds_shim)")


# --- units, flags, objects ----------------------------------------------------------

def linear_factor(scene=None):
    """Blender units per Maya linear unit (= one scene display unit)."""
    return _units.maya_unit(scene)


def _to_bu(v):
    return v * linear_factor()


def _from_bu(v):
    return v / linear_factor()


def _degrees():
    return bpy.context.scene.unit_settings.system_rotation != 'RADIANS'


def _to_rad(v):
    return math.radians(v) if _degrees() else v


def _from_rad(v):
    return math.degrees(v) if _degrees() else v


class _Flags:
    """Maya flags have a long and a short name; unknown flags are an error."""

    def __init__(self, cmd, kwargs):
        self.cmd = cmd
        self.kw = dict(kwargs)

    def get(self, long, short=None, default=None):
        for key in (long, short):
            if key and key in self.kw:
                return self.kw.pop(key)
        return default

    def done(self):
        if self.kw:
            raise TypeError(f"{self.cmd}: Invalid flag '{next(iter(self.kw))}'")


def _flatten(args):
    for a in args:
        if isinstance(a, (list, tuple)):
            yield from _flatten(a)
        else:
            yield a


# Maya locators: a kit Empty marked by ``create.LOCATOR_PROP`` (Create > Locator, spaceLocator); its shape name
# follows the transform like Maya's rename (Maya: box10 -> boxShape10, hero -> heroShape)
_TRAIL = re.compile(r"^(.*?)(\d+)$")


def shape_name_for(name):
    m = _TRAIL.match(name)
    return f"{m.group(1)}Shape{m.group(2)}" if m and m.group(1) else f"{name}Shape"


def is_locator(ob):
    from ..operators import create
    return ob.type == 'EMPTY' and bool(ob.get(create.LOCATOR_PROP))


def shape_of(ob):
    """Maya shape name under ``ob`` (its data, or a locator's), None for a plain transform."""
    if ob.data is not None:
        return ob.data.name
    if not is_locator(ob):
        return None
    from ..operators import create
    return f"{ob.name}Shape" if ob.get(create.LOCATOR_PROP) == PLAIN_SHAPE else shape_name_for(ob.name)


PLAIN_SHAPE = 2       # a locator whose shape is "<name>Shape" (after a rename from a name without digits)


def renamed_shape(old_name, old_shape, new_name):
    """Maya's shape name after renaming its transform ``old_name`` -> ``new_name`` (Maya's rule): a
    shape named like the old transform's ``<base>Shape<N>`` follows as ``shape_name_for(new)`` (pCube1 -> box10:
    boxShape10, -> hero: heroShape); any other shape becomes ``<new>Shape`` (ctrl / ctrlShape -> ctrl2: ctrl2Shape)."""
    return shape_name_for(new_name) if old_shape == shape_name_for(old_name) and _TRAIL.match(old_name)         else f"{new_name}Shape"


_LIGHT_TYPES = {'POINT': "pointLight", 'SUN': "directionalLight", 'SPOT': "spotLight", 'AREA': "areaLight"}
_OBJECT_SHAPE = {'MESH': "mesh", 'CAMERA': "camera", 'CURVE': "nurbsCurve", 'SURFACE': "nurbsSurface",
                 'LATTICE': "lattice"}


def shape_type(ob):
    """Maya node type of ``ob``'s shape ("mesh", "locator", "pointLight", ...), None without one."""
    if is_locator(ob):
        return "locator"
    if ob.type == 'LIGHT' and ob.data is not None:
        return _LIGHT_TYPES.get(ob.data.type, "light")
    return _OBJECT_SHAPE.get(ob.type) if ob.data is not None else None


def type_matches(maya_type, kind, ob):
    """Does a DAG item ('T' transform / 'S' shape of ``ob``) count as ``maya_type`` (``ls -type`` / ``listRelatives
    -type``)?"""
    if kind == 'T':
        return maya_type in ("transform", "dagNode") or (maya_type == "joint" and ob.type == 'ARMATURE')
    st = shape_type(ob)
    return st is not None and (maya_type in (st, "shape", "dagNode") or
                               (maya_type == "light" and st.endswith("Light")))


def _object(name):
    if isinstance(name, bpy.types.Object):
        return name
    short = str(name).rsplit("|", 1)[-1]
    if "." in short or "[" in short:
        raise RuntimeError(f"Components are not supported: {name}")
    ob = bpy.data.objects.get(short)
    if ob is None:  # a shape name ("pCubeShape1", "locatorShape1") -> its transform
        ob = next((o for o in bpy.data.objects if shape_of(o) == short), None)
    if ob is None:
        raise ValueError(f"No object matches name: {name}")
    return ob


def _is_shape_name(name):
    short = str(name).rsplit("|", 1)[-1]
    return bpy.data.objects.get(short) is None and any(shape_of(o) == short for o in bpy.data.objects)


def _objects(args, default_selection=True):
    names = list(_flatten(args))
    if names:
        return [_object(n) for n in names]
    if default_selection:
        sel = _selection()
        if not sel:
            raise RuntimeError("Nothing selected")
        return sel
    return []


def _view_layer():
    vl = bpy.context.view_layer
    vl.update()  # objects added/removed by earlier commands
    return vl


def _selection():
    """Selected objects in Maya order: the active (lead) object last."""
    vl = _view_layer()
    sel = [o for o in vl.objects if o is not None and o.select_get()]
    active = vl.objects.active
    if active in sel:
        sel.remove(active)
        sel.append(active)
    return sel


def _select_only(obs):
    """Maya commands that make nodes select them (Maya: polyCube, group, duplicate, parent, spaceLocator)."""
    vl = _view_layer()
    for o in vl.objects:
        if o is not None and o.select_get():
            o.select_set(False)
    for o in obs:
        try:
            o.select_set(True)
        except RuntimeError:     # not in this view layer
            continue
        vl.objects.active = o


# Maya's startup cameras: the kit draws them as Outliner rows, Maya's names are taken (Maya: group -n top
# -> top1)
DEFAULT_CAMERAS = ("persp", "top", "front", "side")


def unique_name(name, exclude=None):
    """``name`` if no other object has it, else Maya's increment (Maya: rename to a taken "hero" -> hero1,
    polyCube -n pCube1 with pCube1 taken -> pCube2)."""
    from ..operators import naming
    taken = {o.name for o in bpy.data.objects if o is not exclude} | set(DEFAULT_CAMERAS)
    if name not in taken:
        return name
    base = naming.base_name(name)
    return f"{base}{naming.next_number(base, taken)}"


def set_name(ob, name, shape=True):
    """Rename ``ob`` the Maya way: unique, and a single-user shape follows (``renamed_shape``)."""
    old, old_shape = ob.name, shape_of(ob)
    ob.name = unique_name(str(name), exclude=ob)
    if shape and old_shape is not None:
        new_shape = renamed_shape(old, old_shape, ob.name)
        if ob.data is not None and ob.data.users == 1:
            ob.data.name = new_shape
        elif is_locator(ob):
            from ..operators import create
            ob[create.LOCATOR_PROP] = PLAIN_SHAPE if new_shape == f"{ob.name}Shape" and                 new_shape != shape_name_for(ob.name) else True
    return ob.name


# --- ls / select ------------------------------------------------------------------

def _match(pattern):
    """Objects named by ``pattern`` (``*`` / ``?`` wildcards on transform or shape names) as (kind, ob) items."""
    if any(c in str(pattern) for c in "*?") and "." not in str(pattern):
        out = []
        for o in bpy.context.scene.objects:
            if fnmatch.fnmatchcase(o.name, pattern):
                out.append(('T', o))
            sh = shape_of(o)
            if sh is not None and fnmatch.fnmatchcase(sh, pattern):
                out.append(('S', o))
        return out
    return [('S' if _is_shape_name(pattern) else 'T', _object(pattern))]


def ls(*args, **kwargs):
    f = _Flags("ls", kwargs)
    sl = f.get("selection", "sl", False)
    typ = f.get("type", "typ")
    long = f.get("long", "l", False)
    transforms = f.get("transforms", "tr", False)
    shapes = f.get("shapes", "s", False)
    f.get("dag", None, False)
    f.done()
    if args:
        items = [it for n in _flatten(args) for it in _match(n)]
    elif sl:
        items = [('T', o) for o in _selection()]
    else:
        items = [it for o in bpy.context.scene.objects for it in ([('T', o)] + ([('S', o)] if shape_of(o) else []))]
    if transforms:
        typ = "transform"
    if shapes:
        typ = "shape"
    if typ is not None:     # Maya filters what is named; ``ls -sl -type mesh`` with a transform selected is empty
        types = typ if isinstance(typ, (list, tuple)) else [typ]
        items = [(k, o) for k, o in items if any(type_matches(t, k, o) for t in types)]
    out = []
    for k, o in items:
        name = _item_name(k, o, long)
        if name not in out:
            out.append(name)
    return out


def _item_name(kind, ob, long=False):
    if kind == 'S':
        return f"{_long_name(ob)}|{shape_of(ob)}" if long else shape_of(ob)
    return _long_name(ob) if long else ob.name


def _long_name(ob):
    parts = []
    while ob is not None:
        parts.append(ob.name)
        ob = ob.parent
    return "|" + "|".join(reversed(parts))


def select(*args, **kwargs):
    f = _Flags("select", kwargs)
    clear = f.get("clear", "cl", False)
    add = f.get("add", None, False) or f.get("addFirst", "af", False)
    deselect = f.get("deselect", "d", False)
    toggle = f.get("toggle", "tgl", False)
    f.get("replace", "r", False)
    f.done()
    vl = _view_layer()
    obs = [o for n in _flatten(args) for _k, o in _match(n)]
    if clear or not obs:  # select with nothing given clears the selection
        for o in vl.objects:
            if o is not None:
                o.select_set(False)
        return None
    if not (add or deselect or toggle):
        for o in vl.objects:
            if o is not None:
                o.select_set(False)
    for o in obs:
        state = not o.select_get() if toggle else not deselect
        o.select_set(state)
        if state:
            vl.objects.active = o
    return None


# --- transforms --------------------------------------------------------------------

def _split_values(args, count=3):
    values, rest = [], []
    for a in _flatten(args):
        if isinstance(a, (int, float)) and not isinstance(a, bool) and len(values) < count and not rest:
            values.append(float(a))
        else:
            rest.append(a)
    if len(values) != count:
        raise ValueError(f"Expected {count} values, got {len(values)}")
    return values, rest


def move(*args, **kwargs):
    f = _Flags("move", kwargs)
    relative = f.get("relative", "r", False)
    f.get("absolute", "a", True)
    f.get("worldSpace", "ws", True)
    os_ = f.get("objectSpace", "os", False)
    f.done()
    values, names = _split_values(args)
    v = Vector([_to_bu(x) for x in values])
    for ob in _objects(names):
        if os_ and relative:      # along the object's own axes (its rotate), in its parent's units
            ob.location = ob.location + ob.rotation_euler.to_matrix() @ v
            continue
        # Maya ``move -a`` puts the rotate pivot at the point: the kit's pivot is the origin (step 10)
        mw = ob.matrix_world.copy()
        mw.translation = mw.translation + v if relative else v
        ob.matrix_world = mw
    return None


def rotate(*args, **kwargs):
    f = _Flags("rotate", kwargs)
    relative = f.get("relative", "r", False)
    f.get("absolute", "a", True)
    f.get("objectSpace", "os", True)
    f.done()
    values, names = _split_values(args)
    rad = [_to_rad(x) for x in values]
    for ob in _objects(names):
        for i in range(3):
            ob.rotation_euler[i] = ob.rotation_euler[i] + rad[i] if relative else rad[i]
    return None


def scale(*args, **kwargs):
    f = _Flags("scale", kwargs)
    relative = f.get("relative", "r", False)
    f.get("absolute", "a", True)
    f.done()
    values, names = _split_values(args)
    for ob in _objects(names):
        for i in range(3):
            ob.scale[i] = ob.scale[i] * values[i] if relative else values[i]
    return None


# --- Maya matrices (no pivot offset: the kit's delta_location is Maya's pivot, step 10) ---------------------------

def _frame(ob):
    """Matrix taking ``ob.matrix_basis`` to world (parent, parent inverse, bone / vertex parents)."""
    return ob.matrix_world @ ob.matrix_basis.inverted_safe()


def maya_local(ob):
    """Maya's local matrix of ``ob`` (translate / rotate / scale, without the pivot offset)."""
    return Matrix.Translation(-Vector(ob.delta_location)) @ ob.matrix_basis


def maya_world(ob):
    return _frame(ob) @ maya_local(ob)


def set_maya_world(ob, m):
    """Give ``ob`` the Maya world matrix ``m`` (BU). A local matrix with shear (rotated child of a non-uniformly
    scaled parent) keeps the residual in the parent inverse like ``parenting.set_parent_maya``."""
    dl = Vector(ob.delta_location)
    if ob.parent is not None and ob.parent_type == 'OBJECT':
        local = ob.parent.matrix_world.inverted_safe() @ m
        t, q, s = local.decompose()
        trs = Matrix.LocRotScale(t, q, s)
        residual = local @ trs.inverted_safe()
        exact = all(abs(residual[i][j] - (1.0 if i == j else 0.0)) < 1e-6 for i in range(4) for j in range(4))
        ob.matrix_parent_inverse = Matrix.Identity(4) if exact else residual
        ob.matrix_basis = Matrix.Translation(dl) @ trs
    else:
        ob.matrix_basis = Matrix.Translation(dl) @ (_frame(ob).inverted_safe() @ m)


def _flat_matrix(m):
    """The 16 numbers of a Maya matrix: row-major with the translation in the last row (= Blender's columns), lengths in Maya
    units."""
    k = linear_factor()
    return [m[i][j] / k if (i < 3 and j == 3) else m[i][j] for j in range(4) for i in range(4)]


def _matrix_from_maya(values):
    v = [float(x) for x in _flatten(values)]
    if len(v) != 16:
        raise ValueError(f"Expected 16 matrix values, got {len(v)}")
    k = linear_factor()
    m = Matrix([[v[j * 4 + i] for j in range(4)] for i in range(4)])
    for i in range(3):
        m[i][3] *= k
    return m


def _euler_deg(ob, m):
    order = ob.rotation_mode if ob.rotation_mode in ROTATE_ORDERS else 'XYZ'
    return [_from_rad(a) for a in m.to_3x3().normalized().to_euler(order)]


def _corners(ob):
    if ob.type == 'EMPTY':
        r = ob.empty_display_size
        return [ob.matrix_world @ Vector((x, y, z)) for x in (-r, r) for y in (-r, r) for z in (-r, r)]
    if ob.type in {'MESH', 'CURVE', 'SURFACE', 'LATTICE', 'FONT', 'META', 'ARMATURE'}:
        return [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return [ob.matrix_world.translation.copy()]


def bounding_box(ob):
    """World bounding box of ``ob`` and everything under it, Maya units (xmin ymin zmin xmax ymax zmax)."""
    pts = [p for o in [ob, *ob.children_recursive] for p in _corners(o)]
    k = linear_factor()
    return [min(p[i] for p in pts) / k for i in range(3)] + [max(p[i] for p in pts) / k for i in range(3)]


def pivot_object_space(ob):
    """Maya rotate pivot in object space: the pivot offset through the inverse rotate / scale."""
    lin = ob.matrix_basis.to_3x3()
    return [_from_bu(x) for x in lin.inverted_safe() @ Vector(ob.delta_location)]


def xform(*args, **kwargs):
    f = _Flags("xform", kwargs)
    query = f.get("query", "q", False)
    t = f.get("translation", "t")
    ro = f.get("rotation", "ro")
    s = f.get("scale", "s")
    m = f.get("matrix", "m")
    bb = f.get("boundingBox", "bb")
    rp = f.get("rotatePivot", "rp")
    sp = f.get("scalePivot", "sp")
    piv = f.get("pivots", "piv")
    cp = f.get("centerPivots", "cp", False)
    sh = f.get("shear", "sh")
    ws = f.get("worldSpace", "ws", False)
    f.get("objectSpace", "os", False)
    relative = f.get("relative", "r", False)
    f.get("absolute", "a", False)
    f.get("preserve", "p", False)
    f.get("euler", "eu", False)
    f.done()
    obs = _objects(args)
    if query:
        ob = obs[0]
        bpy.context.view_layer.update()          # matrix_world after earlier channel edits
        if m:
            return _flat_matrix(maya_world(ob) if ws else maya_local(ob))
        if bb:
            return bounding_box(ob)
        if rp or sp:
            return [_from_bu(x) for x in ob.matrix_world.translation] if ws else pivot_object_space(ob)
        if piv:
            p = [_from_bu(x) for x in ob.matrix_world.translation] if ws else pivot_object_space(ob)
            return p + p   # the kit has one pivot for rotate and scale
        if t:
            loc = maya_world(ob).translation if ws else ob.location
            return [_from_bu(x) for x in loc]
        if ro:
            return _euler_deg(ob, maya_world(ob)) if ws else [_from_rad(x) for x in ob.rotation_euler]
        if s:
            return list(maya_world(ob).to_scale()) if ws else list(ob.scale)
        if sh:
            return [0.0, 0.0, 0.0]
        raise TypeError("xform -query needs -translation, -rotation, -scale, -matrix, -boundingBox or a pivot flag")
    from ..operators import freeze, pivot
    for ob in obs:
        if piv is not None:
            p = Vector([_to_bu(x) for x in piv])
            pivot.match_pivot(ob, p if ws else maya_world(ob) @ p)
        if cp:
            freeze.center_pivot(bpy.context, [ob])
        if m is not None:
            mat = _matrix_from_maya(m)
            if ws:
                set_maya_world(ob, mat)
            else:
                ob.matrix_basis = Matrix.Translation(Vector(ob.delta_location)) @ mat
        if t is not None:
            v = Vector([_to_bu(x) for x in t])
            if ws:
                bpy.context.view_layer.update()
                mw = maya_world(ob)
                mw.translation = mw.translation + v if relative else v
                set_maya_world(ob, mw)
            else:
                ob.location = ob.location + v if relative else v
        if ro is not None:
            for i in range(3):
                r = _to_rad(ro[i])
                ob.rotation_euler[i] = ob.rotation_euler[i] + r if relative else r
        if s is not None:
            for i in range(3):
                ob.scale[i] = ob.scale[i] * s[i] if relative else s[i]
        bpy.context.view_layer.update()
    return None


# --- attributes ---------------------------------------------------------------------------

# Maya attribute -> (Channel Box key or compound keys).
_COMPOUND = {"translate": ("tx", "ty", "tz"), "t": ("tx", "ty", "tz"),
             "rotate": ("rx", "ry", "rz"), "r": ("rx", "ry", "rz"),
             "scale": ("sx", "sy", "sz"), "s": ("sx", "sy", "sz")}
_SCALAR = {"translateX": "tx", "translateY": "ty", "translateZ": "tz",
           "rotateX": "rx", "rotateY": "ry", "rotateZ": "rz",
           "scaleX": "sx", "scaleY": "sy", "scaleZ": "sz", "visibility": "v",
           **{k: k for k in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "v")}}
# Maya rotateOrder enum (xyz yzx zxy xzy yxz zyx) = Blender's Euler modes of the same names
ROTATE_ORDERS = ('XYZ', 'YZX', 'ZXY', 'XZY', 'YXZ', 'ZYX')


def _split_attr(attr):
    if "." not in str(attr):
        raise ValueError(f"Expected node.attribute, got {attr!r}")
    node, name = str(attr).split(".", 1)
    return _object(node), name


def _cb():
    from ..ui import channel_box
    return channel_box


def channel_keys(ob, name):
    """Channel Box keys behind Maya attribute ``name`` of ``ob`` (custom attributes as ``cp:<name>``), or None."""
    if name in _COMPOUND:
        return _COMPOUND[name]
    if name in _SCALAR:
        return (_SCALAR[name],)
    if name in ob.keys() and not name.startswith("_"):
        return (_cb().CUSTOM_PREFIX + name,)
    return None


def to_internal(key, value):
    """Maya value of channel ``key`` -> the value Blender stores (property / F-curve)."""
    kind = _cb().channel_path(key)[2]
    if kind == "LOC":
        return _to_bu(value)
    if kind == "ROT":
        return _to_rad(value)
    if kind == "VIS":
        return 0.0 if value else 1.0          # hide_viewport
    return value


def from_internal(key, value):
    kind = _cb().channel_path(key)[2]
    if kind == "LOC":
        return _from_bu(value)
    if kind == "ROT":
        return _from_rad(value)
    if kind == "VIS":
        return value < 0.5
    return value


def _get_key(ob, key, time=None):
    if time is not None:
        fc = _cb().fcurve(ob, key)
        if fc is not None:
            v = from_internal(key, fc.evaluate(float(time)))
            return v if not key.startswith(_cb().CUSTOM_PREFIX) else type(_cb().get_value(ob, key))(v)
    value = _cb().get_value(ob, key)
    kind = _cb().channel_path(key)[2]
    if kind == "LOC":
        return _from_bu(value)
    if kind == "ROT":
        return _from_rad(value)
    return bool(value) if kind == "VIS" else value


def _set_key(ob, key, value):
    kind = _cb().channel_path(key)[2]
    if kind == "LOC":
        value = _to_bu(value)
    elif kind == "ROT":
        value = _to_rad(value)
    _cb().set_value(ob, key, value)


def _limits(ob, name):
    from ..operators import rig_tools
    _kind, use_min, lo, use_max, hi, _default = rig_tools.limits(ob, name)
    return (lo if use_min else None), (hi if use_max else None)


def _keyable(ob, key):
    cb = _cb()
    return cb.is_keyable(ob, key) and not cb.is_hidden(ob, key)


def _set_channel_state(ob, key, keyable=None, channel_box=None):
    """Maya Channel Control: keyable (shown), nonkeyable displayed (``-cb 1``) or hidden (``-k 0``)."""
    cb = _cb()
    hidden = [k for k in cb._flag_list(ob, cb.HIDDEN_PROP) if k != key]
    nonkey = [k for k in cb._flag_list(ob, cb.NONKEYABLE_PROP) if k != key]
    if keyable is False:
        hidden.append(key)
        nonkey.append(key)
    elif keyable is None:
        if cb.is_hidden(ob, key):
            hidden.append(key)
        if not cb.is_keyable(ob, key):
            nonkey.append(key)
    if channel_box is not None:
        hidden = [k for k in hidden if k != key] if channel_box else hidden + [key]
        if channel_box:
            nonkey.append(key)
    cb._set_flag_list(ob, cb.HIDDEN_PROP, hidden)
    cb._set_flag_list(ob, cb.NONKEYABLE_PROP, nonkey)


_MATRIX_ATTRS = {"worldMatrix": True, "wm": True, "matrix": False, "m": False}


def getAttr(attr, **kwargs):
    f = _Flags("getAttr", kwargs)
    lock = f.get("lock", "l", False)
    keyable = f.get("keyable", "k", False)
    in_cb = f.get("channelBox", "cb", False)
    typ = f.get("type", "typ", False)
    time = f.get("time", "t")
    f.get("asString", "asString", False)
    f.done()
    ob, name = _split_attr(attr)
    keys = channel_keys(ob, name)
    first = keys[0] if keys else None
    if lock:
        return bool(first and _cb().is_locked(ob, first))
    if keyable:
        return bool(first) and _keyable(ob, first)
    if in_cb:
        cb = _cb()
        return bool(first) and not cb.is_keyable(ob, first) and not cb.is_hidden(ob, first)
    if name in _MATRIX_ATTRS:
        bpy.context.view_layer.update()
        return "matrix" if typ else _flat_matrix(maya_world(ob) if _MATRIX_ATTRS[name] else maya_local(ob))
    if name in ("rotateOrder", "ro"):
        return "enum" if typ else (ROTATE_ORDERS.index(ob.rotation_mode) if ob.rotation_mode in ROTATE_ORDERS else 0)
    if name in ("inheritsTransform", "it"):
        return "bool" if typ else True
    if keys is None:
        raise ValueError(f"No attribute '{name}' on {ob.name}")
    if typ:
        if len(keys) == 3:
            return "double3"
        v = _get_key(ob, first)
        return "bool" if isinstance(v, bool) else "long" if isinstance(v, int) else \
            "string" if isinstance(v, str) else "doubleLinear" if name in ("tx", "ty", "tz") or \
            name.startswith("translate") else "doubleAngle" if name.startswith(("r", "rotate")) and len(name) <= 7 \
            else "double"
    if len(keys) == 3:
        return [tuple(_get_key(ob, k, time) for k in keys)]
    return _get_key(ob, first, time)


def setAttr(attr, *values, **kwargs):
    f = _Flags("setAttr", kwargs)
    lock = f.get("lock", "l")
    keyable = f.get("keyable", "k")
    in_cb = f.get("channelBox", "cb")
    f.get("type", "typ")
    f.done()
    ob, name = _split_attr(attr)
    keys = channel_keys(ob, name)
    if name in ("rotateOrder", "ro"):
        v = list(_flatten(values))
        if v:
            euler = tuple(ob.rotation_euler)
            ob.rotation_mode = ROTATE_ORDERS[int(v[0])]
            ob.rotation_euler = euler       # Maya keeps the rotate values (Blender would convert them)
        return None
    if keys is None and (lock is not None or keyable is not None or in_cb is not None):
        raise ValueError(f"No attribute '{name}' on {ob.name}")
    if lock is not None and keys:
        for k in keys:
            if k != "v":
                _cb().set_locked(ob, k, bool(lock))
    if (keyable is not None or in_cb is not None) and keys:
        for k in keys:
            _set_channel_state(ob, k, None if keyable is None else bool(keyable),
                               None if in_cb is None else bool(in_cb))
    if not values:
        return None
    values = list(_flatten(values))
    if keys is None:
        raise ValueError(f"No attribute '{name}' on {ob.name}")
    if len(values) != len(keys):
        raise ValueError(f"setAttr {attr}: expected {len(keys)} value(s), got {len(values)}")
    for k, v in zip(keys, values):
        if _cb().is_locked(ob, k):
            raise RuntimeError(f"The attribute '{ob.name}.{name}' is locked or connected and cannot be modified.")
        if k.startswith(_cb().CUSTOM_PREFIX) and isinstance(v, (int, float)) and not isinstance(v, bool):
            # Maya refuses a value outside the attribute's limits (Maya: "past its maximum value of 10")
            lo, hi = _limits(ob, k[len(_cb().CUSTOM_PREFIX):])
            if hi is not None and v > hi:
                raise RuntimeError(f"setAttr: Cannot set the attribute '{ob.name}.{name}' past its maximum value "
                                   f"of {hi:g}.")
            if lo is not None and v < lo:
                raise RuntimeError(f"setAttr: Cannot set the attribute '{ob.name}.{name}' past its minimum value "
                                   f"of {lo:g}.")
        _set_key(ob, k, v)
    return None


_ATTR_TYPES = {"double": 'FLOAT', "float": 'FLOAT', "doubleLinear": 'FLOAT', "doubleAngle": 'FLOAT',
               "long": 'INT', "short": 'INT', "byte": 'INT', "bool": 'BOOL'}


def addAttr(*args, **kwargs):
    """``addAttr -ln speed -at double -min 0 -max 10 -dv 2 -k 1``: a custom property (Channel Box extra attribute,
    like Modify > Add Attribute). Without ``-k`` the attribute is hidden and not keyable, as in Maya."""
    f = _Flags("addAttr", kwargs)
    long = f.get("longName", "ln")
    f.get("shortName", "sn")
    f.get("niceName", "nn")
    at = f.get("attributeType", "at")
    dt = f.get("dataType", "dt")
    lo = f.get("minValue", "min")
    hi = f.get("maxValue", "max")
    dv = f.get("defaultValue", "dv")
    keyable = f.get("keyable", "k", False)
    f.get("hidden", "h", False)
    f.done()
    if not long:
        raise RuntimeError("addAttr: a long name (ln) is needed")
    from ..operators import rig_tools
    for ob in _objects(args):
        if long in ob.keys():
            raise RuntimeError(f"Found a duplicate attribute name '{long}' on {ob.name}")
        if dt in ("string",):
            ob[long] = str(dv or "")
            continue
        kind = _ATTR_TYPES.get(at or "double")
        if kind is None:
            raise RuntimeError(f"addAttr: attribute type '{at}' is not supported (double, long, bool)")
        cast = bool if kind == 'BOOL' else int if kind == 'INT' else float
        ob[long] = cast(dv if dv is not None else 0)
        rig_tools.set_limits(ob, long, kind, lo is not None, lo or 0, hi is not None, hi or 0, cast(dv or 0))
        _set_channel_state(ob, _cb().CUSTOM_PREFIX + long, bool(keyable))
    return None


# --- creation (Maya naming: pCube1 / pCubeShape1 / polyCube1) ----------------------

# Maya flags (long, short) -> creation node attribute; the bare command's defaults (polyCylinder caps 0, unlike
# the Create menu's 1)
_PRIM_FLAGS = {
    "polyCube": ('CUBE', {}, (("width", "w"), ("height", "h"), ("depth", "d"), ("subdivisionsX", "sx", "subdivisionsWidth"),
                             ("subdivisionsY", "sy", "subdivisionsHeight"), ("subdivisionsZ", "sz", "subdivisionsDepth"))),
    "polySphere": ('SPHERE', {}, (("radius", "r"), ("subdivisionsAxis", "sa"), ("subdivisionsX", "sx", "subdivisionsAxis"),
                                 ("subdivisionsHeight", "sh"), ("subdivisionsY", "sy", "subdivisionsHeight"))),
    "polyCylinder": ('CYLINDER', {"subdivisionsCaps": 0},
                     (("radius", "r"), ("height", "h"), ("subdivisionsAxis", "sa"), ("subdivisionsX", "sx", "subdivisionsAxis"),
                      ("subdivisionsHeight", "sh"), ("subdivisionsY", "sy", "subdivisionsHeight"),
                      ("subdivisionsCaps", "sc"), ("subdivisionsZ", "sz", "subdivisionsCaps"), ("roundCap", "rcp"))),
    "polyPlane": ('PLANE', {}, (("width", "w"), ("height", "h"), ("subdivisionsX", "sx", "subdivisionsWidth"),
                               ("subdivisionsY", "sy", "subdivisionsHeight"))),
}


def _primitive(cmd, kwargs):
    """Build a Maya primitive with its creation node (operators/prim_history.py, step 129): returns
    [transform, node] like Maya, or [transform] with constructionHistory off."""
    from ..operators import prim_history
    kind, values, flags = _PRIM_FLAGS[cmd]
    f = _Flags(cmd, kwargs)
    values = dict(values)
    for spec in flags:
        long, short = spec[0], spec[1]
        v = f.get(long, short)
        if v is not None:
            values[spec[2] if len(spec) > 2 else long] = v
    ax = f.get("axis", "ax")
    if ax is not None:
        values.update(axisX=ax[0], axisY=ax[1], axisZ=ax[2])
    name = f.get("name", "n")
    ch = f.get("constructionHistory", "ch", True)
    f.done()
    ob = prim_history.create_object(bpy.context, kind, values)
    node = prim_history.node_dict(prim_history.owner_of(ob))["name"]
    if name:
        # Maya: -n pCube with pCube1 present = pCube / pCubeShape; -n pCube1 taken -> pCube2 / pCube2Shape
        ob.name = unique_name(str(name), exclude=ob)
        ob.data.name = f"{ob.name}Shape"
    if not ch:
        prim_history.drop(ob)
        return [ob.name]
    return [ob.name, node]


def polyCube(**kwargs):
    return _primitive("polyCube", kwargs)


def polySphere(**kwargs):
    return _primitive("polySphere", kwargs)


def polyCylinder(**kwargs):
    return _primitive("polyCylinder", kwargs)


def polyPlane(**kwargs):
    return _primitive("polyPlane", kwargs)


# Scene, DAG, animation and file commands live in their own modules (they use the helpers above).
from .cmds_dag import (delete, rename, objExists, listRelatives, parent, group, duplicate,  # noqa: E402
                       spaceLocator)
from .cmds_anim import currentTime, setKeyframe, cutKey, keyframe, playbackOptions  # noqa: E402
from .cmds_file import file  # noqa: E402,A001
from .cmds_rig import (makeIdentity, parentConstraint, pointConstraint, orientConstraint,  # noqa: E402
                       scaleConstraint, aimConstraint, joint, connectAttr, disconnectAttr, isConnected,
                       listConnections, connectionInfo)
from .cmds_misc import (nodeType, objectType, attributeQuery, currentUnit, sets, shadingNode,  # noqa: E402
                        polyExtrudeFacet, polyEvaluate, exactWorldBoundingBox, listHistory, camera)


def _guarded(fn):
    """Run a command in the script's window when a ``cmds.file`` load left the context without one."""
    @functools.wraps(fn)
    def command(*args, **kwargs):
        from .cmds_file import script_window
        from . import cmds_rig

        def run():
            r = cmds_rig.intercept(fn.__name__, fn, args, kwargs)
            return fn(*args, **kwargs) if r is cmds_rig.PASS else r
        win = script_window()
        if win is None:
            return run()
        with bpy.context.temp_override(window=win, screen=win.screen):
            return run()
    return command


for _name in __all__:
    globals()[_name] = _guarded(globals()[_name])
del _name
