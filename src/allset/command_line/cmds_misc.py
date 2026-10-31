# SPDX-License-Identifier: GPL-3.0-or-later
"""maya.cmds look-alike 3 (Issue #122): node types, attribute queries, units, sets, shading nodes, polygon
queries / extrude, camera.

Everything goes through the kit's own data so a script gives what the menus give:

- Maya nodes that aren't DAG objects (``_node``): materials = kit materials (``operators/material.py``, lambert1 =
  the ``DEFAULT_PROP`` material), a ``file`` texture = a Shader node group holding an Image Texture node (outputs
  ``outColor`` / ``outAlpha``; Blender has no free-standing shader node, a group can be shared by every
  material it is connected to like Maya's node), sets = kit sets (``operators/sets.py``), shading groups =
  initialShadingGroup / ``<material>SG`` (``material.shading_group_name``), creation nodes (``prim_history``),
  extrusions (``operators/extrude.py`` records + the per-mesh list ``HISTORY_PROP`` the commands keep), constraints
  (``channel_box.constraint_node_name``), bones = joints.
- ``currentUnit`` = the scene's unit settings / frame rate (Maya's working units are the scene's display units);
  ``ls`` / ``getAttr`` / ``setAttr`` / ``select`` / ``objExists`` learn these nodes in
  ``_extend_shim`` (the shim's versions handle DAG objects only).
"""

import re

import bmesh
import bpy
from mathutils import Vector

from . import cmds_shim as _shim

_Flags = _shim._Flags
_flatten = _shim._flatten

HISTORY_PROP = "allset_cmds_history"   # mesh data: [{name, type, values}] of the extrusions made by commands
TEXTURE_PROP = "allset_shading_node"   # node group: Maya node type ("file")
FILE_NAME_PROP = "allset_file_texture_name"
# Maya's standard scene nodes that aren't DAG objects (Maya: ls -type objectSet, nodeType time1)
DEFAULT_SETS = {"defaultLightSet": "objectSet", "defaultObjectSet": "objectSet",
                "initialParticleSE": "shadingEngine", "initialShadingGroup": "shadingEngine"}
DEFAULT_NODES = {"time1": "time"}

# nodeType -inherited (Maya's lists for joint and mesh; the others
# follow Maya's documented node hierarchy)
_DAG = ["containerBase", "entity", "dagNode"]
_SHAPE = _DAG + ["shape"]
_GEO = _SHAPE + ["geometryShape", "deformableShape", "controlPoint"]
_LAMBERT = ["shadingDependNode", "lambert"]
CHAINS = {
    "transform": _DAG + ["transform"],
    "joint": _DAG + ["transform", "joint"],
    "mesh": _GEO + ["surfaceShape", "mesh"],
    "nurbsCurve": _GEO + ["curveShape", "nurbsCurve"],
    "nurbsSurface": _GEO + ["surfaceShape", "nurbsSurface"],
    "lattice": _GEO + ["lattice"],
    "locator": _SHAPE + ["geometryShape", "locator"],
    "camera": _SHAPE + ["camera"],
    "lambert": _LAMBERT,
    "blinn": _LAMBERT + ["reflect", "blinn"],
    "phong": _LAMBERT + ["reflect", "phong"],
    "phongE": _LAMBERT + ["reflect", "phongE"],
    "anisotropic": _LAMBERT + ["reflect", "anisotropic"],
    "rampShader": ["shadingDependNode", "rampShader"],
    "file": ["shadingDependNode", "texture2d", "file"],
    "objectSet": ["entity", "objectSet"],
    "shadingEngine": ["entity", "objectSet", "shadingEngine"],
    "polyExtrudeFace": ["polyBase", "polyModifier", "polyModifierWorld", "polyMoveFace", "polyExtrudeFace"],
}
_LIGHT = _SHAPE + ["light", "renderLight"]
_CONSTRAINT = _DAG + ["transform", "constraint"]


def _cb():
    from ..ui import channel_box
    return channel_box


def _chain(maya_type):
    if maya_type in CHAINS:
        return list(CHAINS[maya_type])
    if maya_type.endswith("Light"):
        return _LIGHT + [maya_type]
    if maya_type.endswith("Constraint"):
        return _CONSTRAINT + [maya_type]
    if maya_type.startswith("poly"):
        return ["polyBase", "polyCreator", "polyPrimitive", maya_type]
    return [maya_type]


# --- non-DAG nodes ---------------------------------------------------------------------------------------------------

class Node:
    """A Maya node the kit keeps outside the object list: ``kind`` + Blender data + Maya node type."""

    def __init__(self, kind, name, maya_type, data=None, owner=None):
        self.kind, self.name, self.type, self.data, self.owner = kind, name, maya_type, data, owner


def _materials():
    return [m for m in bpy.data.materials if not m.is_grease_pencil and m.library is None]


def _material_type(mat):
    from ..ui import attribute_editor
    return attribute_editor.material_type(mat)


def _textures():
    return [g for g in bpy.data.node_groups if g.get(TEXTURE_PROP)]


def _used_materials():
    used = []
    for ob in bpy.context.scene.objects:
        for slot in getattr(ob, "material_slots", ()):
            if slot.material is not None and slot.material not in used:
                used.append(slot.material)
    return used


def _shading_groups():
    """Maya shading groups: initialShadingGroup (lambert1) and ``<material>SG`` of every assigned material."""
    from ..operators import material
    return {material.shading_group_name(m): m for m in _used_materials() if not material.is_default(m)}


def _extrusion_nodes(ob):
    """[(name, type, values)] of ``ob``'s extrusions, oldest first: the command list + the kit's live record."""
    from ..operators import extrude
    out = []
    data = ob.data if ob.type == 'MESH' else None
    if data is not None:
        for entry in data.get(HISTORY_PROP, ()):
            e = entry.to_dict() if hasattr(entry, "to_dict") else dict(entry)
            out.append((e["name"], e["type"], dict(e.get("values", {}))))
    rec = extrude.RECORDS.get(ob.name)
    if rec is not None and rec.pre is not None and not any(n == rec.name for n, _t, _v in out):
        out.append((rec.name, rec.spec.node_type, dict(rec.params)))
    return out


def _node(name):
    """The non-DAG Maya node called ``name``, or None."""
    from ..operators import material, prim_history, sets
    name = str(name)
    if name in (material.DEFAULT_NAME, material.DEFAULT_GROUP):
        mat = material.default_material()      # Maya's scene always has lambert1 / initialShadingGroup
        if name == material.DEFAULT_GROUP:
            return Node('SG', name, "shadingEngine", mat)
        return Node('MATERIAL', mat.name, "lambert", mat)
    mat = bpy.data.materials.get(name)
    if mat is not None and not mat.is_grease_pencil:
        return Node('MATERIAL', name, _material_type(mat), mat)
    group = bpy.data.node_groups.get(name)
    if group is not None and group.get(TEXTURE_PROP):
        return Node('TEXTURE', name, group[TEXTURE_PROP], group)
    coll = sets.get(name)
    if coll is not None:
        return Node('SET', name, "objectSet", coll)
    if name in DEFAULT_SETS:
        return Node('DEFAULT_SET', name, DEFAULT_SETS[name])
    if name in DEFAULT_NODES:
        return Node('DEFAULT', name, DEFAULT_NODES[name])
    sg = _shading_groups().get(name)
    if sg is not None:
        return Node('SG', name, "shadingEngine", sg)
    for ob in bpy.context.scene.objects:
        owner = prim_history.owner_of(ob)
        node = prim_history.node_dict(owner)
        if node is not None and node.get("name") == name:
            return Node('HISTORY', name, node["type"], owner, ob)
        if ob.type == 'MESH':
            for n, t, values in _extrusion_nodes(ob):
                if n == name:
                    return Node('EXTRUDE', name, t, values, ob)
        for target in [ob, *(ob.pose.bones if ob.pose is not None else ())]:
            for con in _cb().constraints(target):
                if con.name == name or _cb().constraint_node_name(target, con) == name:
                    return Node('CONSTRAINT', name, _cb().maya_constraint_type(con, "constraint"), con, target)
    for arm in bpy.data.armatures:
        if arm.users and name in arm.bones:
            return Node('BONE', name, "joint", arm.bones[name], arm)
    return None


def _dag(name):
    """(kind 'T' / 'S', object) of a DAG name (shim rules), or None."""
    short = str(name).rsplit("|", 1)[-1]
    try:
        ob = _shim._object(short)
    except (ValueError, RuntimeError):
        return None
    return ('S' if _shim._is_shape_name(short) else 'T', ob)


def _default_camera_type(name):
    """Maya's startup cameras when the scene has no such object: persp (transform) / perspShape (camera)."""
    if name in _shim.DEFAULT_CAMERAS:
        return "transform"
    if name.endswith("Shape") and name[:-5] in _shim.DEFAULT_CAMERAS:
        return "camera"
    return None


def _type_of(name):
    """Maya node type of a node / plug / component name; RuntimeError when nothing has that name."""
    text = str(name)
    node = text.rsplit("|", 1)[-1].split(".", 1)[0]
    component = "[" in text
    hook = getattr(_rig(), "node_type", None)     # cmds_rig may name nodes it makes
    if hook is not None and not component:
        found = hook(node)
        if found:
            return found
    dag = _dag(node)
    if dag is not None:
        kind, ob = dag
        if kind == 'S' or component:
            return _shim.shape_type(ob) or "shape"
        return "joint" if ob.type == 'ARMATURE' else "transform"
    found = _node(node)
    if found is not None:
        return found.type
    cam = _default_camera_type(node)
    if cam is not None:
        return cam
    raise RuntimeError(f"No object matches name: {name}")


def _rig():
    from . import cmds_rig
    return cmds_rig


def nodeType(*args, **kwargs):
    """``nodeType`` = the Maya type of a node, plug (its node) or component (its shape); ``-inherited`` = the class
    chain (Maya: joint containerBase entity dagNode transform joint). A missing node raises RuntimeError."""
    f = _Flags("nodeType", kwargs)
    inherited = f.get("inherited", "i", False)
    f.get("apiType", "api", False)
    f.done()
    names = list(_flatten(args))
    if len(names) != 1:
        raise RuntimeError("nodeType: one node name is needed")
    t = _type_of(names[0])
    return _chain(t) if inherited else t


def objectType(*args, **kwargs):
    """``objectType`` = nodeType; ``-isType`` is exact (a joint is not a "transform"), ``-isAType`` follows the
    class chain."""
    f = _Flags("objectType", kwargs)
    is_type = f.get("isType", "i")
    is_a = f.get("isAType", "isa")
    f.done()
    names = list(_flatten(args))
    if len(names) != 1:
        raise RuntimeError("objectType: one object name is needed")
    t = _type_of(names[0])
    if is_type is not None:
        return t == is_type
    if is_a is not None:
        return is_a in _chain(t)
    return t


# --- attributeQuery --------------------------------------------------------------------------------------------------

# Maya transform attributes: long -> (short, type, parent, default, min, max, keyable)
_XYZ = ("X", "Y", "Z")
TRANSFORM_ATTRS = {
    "visibility": ("v", "bool", None, 1.0, 0.0, 1.0, True),
    "rotateOrder": ("ro", "enum", None, 0.0, 0.0, 5.0, False),
}
for _long, _short, _type, _dv in (("translate", "t", "doubleLinear", 0.0), ("rotate", "r", "doubleAngle", 0.0),
                                  ("scale", "s", "double", 1.0)):
    TRANSFORM_ATTRS[_long] = (_short, "double3", None, _dv, None, None, False)
    for _a in _XYZ:
        TRANSFORM_ATTRS[_long + _a] = (_short + _a.lower(), _type, _long, _dv, None, None, True)
_SHORT = {v[0]: k for k, v in TRANSFORM_ATTRS.items()}


def nice_name(long):
    """Maya's nice name: camelCase split into capitalised words (translateX -> "Translate X", speed -> "Speed")."""
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", long)
    return words[:1].upper() + words[1:]


class _Attr:
    def __init__(self, long, short, typ, keyable, default, lo, hi, children=None, parent=None):
        self.long, self.short, self.type, self.keyable = long, short, typ, keyable
        self.default, self.min, self.max, self.children, self.parent = default, lo, hi, children, parent


def _attr_of(ob, name):
    """The Maya attribute ``name`` (long or short) of object ``ob``, or None."""
    cb = _cb()
    long = _SHORT.get(name, name)
    if long in TRANSFORM_ATTRS:
        short, typ, parent, dv, lo, hi, keyable = TRANSFORM_ATTRS[long]
        children = [long + a for a in _XYZ] if typ == "double3" else None
        if keyable:
            key = _shim.channel_keys(ob, long)
            keyable = bool(key) and _shim._keyable(ob, key[0])
        return _Attr(long, short, typ, keyable, dv, lo, hi, children, parent)
    if name in ob.keys() and not name.startswith("_"):
        value = ob[name]
        if isinstance(value, str):
            return _Attr(name, name, "typed", False, None, None, None)
        from ..operators import rig_tools
        kind, use_min, lo, use_max, hi, dv = rig_tools.limits(ob, name)
        typ = {"BOOL": "bool", "INT": "long"}.get(kind, "double")
        if kind == 'BOOL':
            use_min = use_max = True
            lo, hi = 0.0, 1.0
        keyable = _shim._keyable(ob, cb.CUSTOM_PREFIX + name)
        return _Attr(name, name, typ, keyable, float(dv), float(lo) if use_min else None,
                     float(hi) if use_max else None)
    return None


def attributeQuery(*args, **kwargs):
    """``attributeQuery <attr> -node <node>``: exists / keyable / names / type / limits / default of an attribute
    (Maya: lists for min / max / listDefault; a missing attribute answers exists False, other flags raise)."""
    f = _Flags("attributeQuery", kwargs)
    node = f.get("node", "n")
    flags = {}
    for long, short in (("exists", "ex"), ("keyable", "k"), ("shortName", "sn"), ("longName", "ln"),
                        ("niceName", "nn"), ("attributeType", "at"), ("minExists", "mne"), ("maxExists", "mxe"),
                        ("minimum", "min"), ("maximum", "max"), ("listDefault", "ld"), ("listChildren", "lc"),
                        ("listParent", "lp"), ("hidden", "h"), ("writable", "w"), ("readable", "r"),
                        ("numberOfChildren", "nc"), ("multi", "m")):
        v = f.get(long, short, False)
        if v:
            flags[long] = v
    f.get("type", "typ")
    f.done()
    names = list(_flatten(args))
    if len(names) != 1 or node is None:
        raise RuntimeError("attributeQuery: an attribute name and -node are needed")
    name = str(names[0])
    dag = _dag(node)
    if dag is None:
        found = _node(node)
        if found is None:
            raise RuntimeError(f"attributeQuery: No object matches name: {node}")
        attr = None
        if _node_attr_value(found, name) is not _MISSING:
            attr = _Attr(name, name, "double", True, None, None, None)
    else:
        attr = _attr_of(dag[1], name)
    if "exists" in flags:
        return attr is not None
    if attr is None:
        raise RuntimeError(f"attributeQuery: Node '{node}' does not have attribute '{name}'")
    for flag in flags:
        if flag == "keyable":
            return bool(attr.keyable)
        if flag == "shortName":
            return attr.short
        if flag == "longName":
            return attr.long
        if flag == "niceName":
            return nice_name(attr.long)
        if flag == "attributeType":
            return attr.type
        if flag == "minExists":
            return attr.min is not None
        if flag == "maxExists":
            return attr.max is not None
        if flag in ("minimum", "maximum"):
            v = attr.min if flag == "minimum" else attr.max
            if v is None:
                raise RuntimeError(f"attributeQuery: '{node}.{name}' has no {flag}")
            return [float(v)]
        if flag == "listDefault":
            if attr.default is None:
                return None
            n = 3 if attr.type == "double3" else 1
            return [float(attr.default)] * n
        if flag == "listChildren":
            return list(attr.children) if attr.children else None
        if flag == "listParent":
            return [attr.parent] if attr.parent else None
        if flag == "numberOfChildren":
            return len(attr.children or ())
        if flag == "multi":
            return False
        if flag == "hidden":
            return False
        return True              # readable / writable
    raise TypeError("attributeQuery needs a query flag (exists, keyable, shortName, ...)")


# --- currentUnit -----------------------------------------------------------------------------------------------------

# Maya linear unit -> (full name, Blender length unit, unit system); Blender has no yard
LINEAR = {"mm": ("millimeter", 'MILLIMETERS', 'METRIC'), "cm": ("centimeter", 'CENTIMETERS', 'METRIC'),
          "m": ("meter", 'METERS', 'METRIC'), "km": ("kilometer", 'KILOMETERS', 'METRIC'),
          "in": ("inch", 'INCHES', 'IMPERIAL'), "ft": ("foot", 'FEET', 'IMPERIAL'),
          "mi": ("mile", 'MILES', 'IMPERIAL')}
_LINEAR_BY_UNIT = {v[1]: k for k, v in LINEAR.items()}
ANGLE = {"deg": ("degree", 'DEGREES'), "rad": ("radian", 'RADIANS')}
# Maya time units (frames per second); "<n>fps" names work too
TIME = {"game": 15.0, "film": 24.0, "pal": 25.0, "ntsc": 30.0, "show": 48.0, "palf": 50.0, "ntscf": 60.0,
        "sec": 1.0, "millisec": 1000.0, "23.976fps": 24000 / 1001, "29.97fps": 30000 / 1001,
        "29.97df": 30000 / 1001, "47.952fps": 48000 / 1001, "59.94fps": 60000 / 1001}
_FPS = re.compile(r"^(\d+(?:\.\d+)?)fps$")


def _linear_key(text):
    text = str(text)
    if text in LINEAR:
        return text
    found = next((k for k, v in LINEAR.items() if v[0] == text), None)
    if found is None:
        raise RuntimeError(f"currentUnit: unknown or unsupported linear unit '{text}' (Blender has no yard)")
    return found


def _current_linear(scene):
    us = scene.unit_settings
    if us.system == 'NONE':
        return "cm"      # 1 BU = 1 Maya unit, cm
    if us.length_unit == 'ADAPTIVE':
        return "m" if us.system == 'METRIC' else "ft"
    return _LINEAR_BY_UNIT.get(us.length_unit, "cm")


def _fps(scene):
    return scene.render.fps / (scene.render.fps_base or 1.0)


def _time_name(fps):
    found = next((k for k, v in TIME.items() if abs(v - fps) < 1e-3 and not k.endswith("df")), None)
    return found or f"{fps:g}fps"


def _time_fps(text):
    text = str(text)
    if text in TIME:
        return TIME[text]
    m = _FPS.match(text)
    if m:
        return float(m.group(1))
    raise RuntimeError(f"currentUnit: unknown or unsupported time unit '{text}'")


def _set_range(scene, start_attr, end_attr, start, end):
    """Set a Blender frame range without Blender pushing the other end (start <= end)."""
    setattr(scene, end_attr, max(end, start, getattr(scene, start_attr)))
    setattr(scene, start_attr, start)
    setattr(scene, end_attr, max(end, start))


def _set_fps(scene, fps):
    """Maya keeps the time ranges in seconds when the time unit changes (Maya: 1 / 120 film -> 1.041667 / 125
    pal); Blender frames are whole, so the kit rounds (keys stay where they are)."""
    old = _fps(scene)
    ratio = fps / old if old else 1.0
    r = scene.render
    r.fps = max(1, int(round(fps)))
    r.fps_base = r.fps / fps
    if abs(ratio - 1.0) < 1e-9:
        return
    sc = scene
    _set_range(sc, "frame_start", "frame_end", int(round(sc.frame_start * ratio)), int(round(sc.frame_end * ratio)))
    _set_range(sc, "frame_preview_start", "frame_preview_end", int(round(sc.frame_preview_start * ratio)),
               int(round(sc.frame_preview_end * ratio)))
    sc.frame_set(int(round((sc.frame_current + sc.frame_subframe) * ratio)))


def currentUnit(*args, **kwargs):
    """Maya working units = the scene's display units: linear = ``unit_settings.length_unit`` (the kit's numbers
    follow it: 100 cm reads 1.0 in m), angle = ``system_rotation``, time = the frame rate. Setting returns the full
    linear / angle name or the time name; a multi-flag set returns the last one's."""
    f = _Flags("currentUnit", kwargs)
    query = f.get("query", "q", False)
    linear = f.get("linear", "l")
    angle = f.get("angle", "a")
    time = f.get("time", "t")
    full = f.get("fullName", "f", False)
    f.get("updateAnimation", "ua", True)
    f.done()
    if args:
        raise TypeError("currentUnit takes no objects")
    scene = bpy.context.scene
    if query:
        if angle:
            key = "rad" if scene.unit_settings.system_rotation == 'RADIANS' else "deg"
            return ANGLE[key][0] if full else key
        if time:
            return _time_name(_fps(scene))
        key = _current_linear(scene)
        return LINEAR[key][0] if full else key
    result = None
    if linear is not None:
        key = _linear_key(linear)
        full_name, unit, system = LINEAR[key]
        us = scene.unit_settings
        if us.system != system:
            us.system = system
        us.length_unit = unit
        result = full_name
    if angle is not None:
        key = str(angle)
        key = key if key in ANGLE else next((k for k, v in ANGLE.items() if v[0] == key), None)
        if key is None:
            raise RuntimeError(f"currentUnit: unknown angle unit '{angle}'")
        scene.unit_settings.system_rotation = ANGLE[key][1]
        result = ANGLE[key][0]
    if time is not None:
        _set_fps(scene, _time_fps(time))
        result = _time_name(_fps(scene))
    return result


# --- sets ------------------------------------------------------------------------------------------------------------

def _all_names():
    from ..operators import sets
    names = {o.name for o in bpy.data.objects} | {m.name for m in bpy.data.materials}
    names |= {g.name for g in bpy.data.node_groups} | {c.name for c in sets.all_sets()}
    names |= set(_shim.DEFAULT_CAMERAS) | set(DEFAULT_SETS) | set(DEFAULT_NODES)
    return names


def unique_node_name(name, taken=None):
    """``name`` when no Maya node has it, else one past the highest number of its base (Maya: -n set1 with set1 ..
    set3 taken -> set4)."""
    from ..operators import naming
    taken = _all_names() if taken is None else taken
    if name not in taken:
        return name
    base = naming.base_name(name)
    return f"{base}{naming.next_number(base, taken)}"


def _set_members(found):
    if found.kind == 'SET':
        from ..operators import sets
        return [o.name for o in sets.members(found.data, bpy.context.scene)]
    if found.kind == 'SG':
        mat = found.data
        return [_shim.shape_of(o) or o.name for o in bpy.context.scene.objects
                if any(s.material is mat for s in getattr(o, "material_slots", ()))]
    return []


def _set_node(name):
    found = _node(name)
    if found is None or found.kind not in ('SET', 'SG', 'DEFAULT_SET'):
        raise RuntimeError(f"sets: No object set matches name: {name}")
    return found


def sets(*args, **kwargs):
    """``sets`` = Create > Sets > Set: a kit set (``operators/sets.py``) named set1, set2 … (one past the highest);
    -add / -remove / -isMember / -q on a set. Making or editing a set doesn't change the selection."""
    from ..operators import sets as kit_sets
    f = _Flags("sets", kwargs)
    query = f.get("query", "q", False)
    f.get("edit", "e", False)
    add = f.get("addElement", "add") or f.get("include", "in") or f.get("forceElement", "fe")
    remove = f.get("remove", "rm")
    member = f.get("isMember", "im")
    empty = f.get("empty", "em", False)
    name = f.get("name", "n")
    text = f.get("text", "t")
    clear = f.get("clear", "cl")
    f.done()
    names = list(_flatten(args))
    if query:
        if len(names) != 1:
            raise RuntimeError("sets -q needs one set")
        return _set_members(_set_node(names[0])) or None
    if member is not None:
        found = _set_node(member)
        have = set(_set_members(found))
        obs = [_shim._object(n) for n in names] if names else _shim._selection()
        return bool(obs) and all(o.name in have or _shim.shape_of(o) in have for o in obs)
    for target, op in ((add, kit_sets.add), (remove, kit_sets.remove)):
        if target is not None:
            found = _set_node(target)
            if found.kind != 'SET':
                raise RuntimeError(f"sets: the kit can't edit the members of {target}")
            obs = [_shim._object(n) for n in names] if names else _shim._selection()
            # Maya: -add (c, a) lists a before c (members go in last given first)
            op(found.data, list(reversed(obs)))
            return found.name
    if clear is not None:
        found = _set_node(clear)
        if found.kind == 'SET':
            kit_sets.remove(found.data, list(found.data.objects))
        return found.name
    if empty:
        obs = []
    elif names:
        obs = [_shim._object(n) for n in names]
    else:
        obs = list(reversed(_shim._selection()))   # Maya: from the selection (b, c) -> [c, b]
    new_name = unique_node_name(str(name)) if name else kit_sets.next_name()
    coll = kit_sets.create(new_name, obs, text=str(text or ""))
    return coll.name


# --- shading nodes ---------------------------------------------------------------------------------------------------

def _material_kind(maya_type):
    from ..operators import material
    return next((k for k, v in material.MATERIALS.items() if v[0] == maya_type), None)


def new_file_texture(name=None):
    """Maya's ``file`` texture node: a Shader node group with an Image Texture node and Maya's outputs."""
    from ..operators import naming
    taken = _all_names()
    group = bpy.data.node_groups.new(unique_node_name(str(name)) if name
                                     else f"file{naming.next_number('file', taken)}", 'ShaderNodeTree')
    group[TEXTURE_PROP] = "file"
    group[FILE_NAME_PROP] = ""
    group.use_fake_user = True
    group.interface.new_socket("outColor", in_out='OUTPUT', socket_type='NodeSocketColor')
    group.interface.new_socket("outAlpha", in_out='OUTPUT', socket_type='NodeSocketFloat')
    tex = group.nodes.new("ShaderNodeTexImage")
    tex.name = "file"
    out = group.nodes.new("NodeGroupOutput")
    out.location = (300, 0)
    group.links.new(tex.outputs["Color"], out.inputs["outColor"])
    group.links.new(tex.outputs["Alpha"], out.inputs["outAlpha"])
    return group


def shadingNode(*args, **kwargs):
    """``shadingNode lambert -asShader`` = a kit material (``material.new_material``: lambert2 while lambert1
    exists, blinn1, phong1 …, default values like Maya); ``file -asTexture`` = ``new_file_texture``. No shading group
    is made; the new node becomes the selection."""
    from ..operators import material
    f = _Flags("shadingNode", kwargs)
    f.get("asShader", "asShader", False)
    as_texture = f.get("asTexture", "at", False)
    f.get("asUtility", "au", False)
    f.get("asLight", "al", False)
    f.get("asRendering", "ar", False)
    f.get("asPostProcess", "app", False)
    f.get("shared", "s", False)
    name = f.get("name", "n")
    skip = f.get("skipSelect", "ss", False)
    f.done()
    types = list(_flatten(args))
    if len(types) != 1:
        raise RuntimeError("shadingNode: one node type is needed")
    maya_type = str(types[0])
    if maya_type == "file":
        node_name = new_file_texture(name).name
    else:
        kind = _material_kind(maya_type)
        if kind is None:
            raise RuntimeError(f"shadingNode: Maya Workflow Kit can't make a '{maya_type}' node"
                               + (" (texture nodes: file)" if as_texture else ""))
        material.default_material()      # Maya's scene always has lambert1: the first new lambert is lambert2
        mat = material.new_material(kind)
        if name:
            mat.name = unique_node_name(str(name), _all_names() - {mat.name})
        node_name = mat.name
    if not skip:
        select_nodes([node_name])
    return node_name


# --- getAttr / setAttr on shading and history nodes ------------------------------------------------------------------

_MISSING = object()
# Maya material attribute -> material.maya_input name (colours) or Material property (numbers)
_COLOR_ATTRS = {"color": "Base Color", "incandescence": "Emission Color", "specularColor": "Specular Tint"}
_NUMBER_ATTRS = {"diffuse": "allset_diffuse", "eccentricity": "allset_eccentricity",
                 "cosinePower": "allset_cosine_power"}
_SOCKET_NUMBERS = {"specularRollOff": "Specular IOR Level"}
# polyExtrudeFace attribute -> kit record field
EXTRUDE_ATTRS = {"thickness": "thickness", "localTranslateZ": "local_translate_z", "offset": "offset",
                 "divisions": "divisions", "keepFacesTogether": "keep_faces_together",
                 "localTranslateX": "local_translate_x", "localTranslateY": "local_translate_y",
                 "localScaleX": "local_scale_x", "localScaleY": "local_scale_y", "localScaleZ": "local_scale_z",
                 "translateX": "translate_x", "translateY": "translate_y", "translateZ": "translate_z"}
_EXTRUDE_SHORT = {"thk": "thickness", "ltz": "localTranslateZ", "off": "offset", "dv": "divisions",
                  "kft": "keepFacesTogether", "ltx": "localTranslateX", "lty": "localTranslateY",
                  "tx": "translateX", "ty": "translateY", "tz": "translateZ"}
_EXTRUDE_LENGTHS = {"thickness", "local_translate_z", "offset", "local_translate_x", "local_translate_y"}


def _node_attr_value(found, attr):
    """Maya value of ``found.attr``, or _MISSING."""
    from ..operators import material, prim_history
    if found.kind == 'MATERIAL':
        mat = found.data
        if attr in _COLOR_ATTRS:
            sock = material.maya_input(mat, _COLOR_ATTRS[attr])
            if sock is None:
                return _MISSING
            return [tuple(float(c) for c in sock.default_value[:3])]
        if attr in _NUMBER_ATTRS:
            return float(getattr(mat, _NUMBER_ATTRS[attr]))
        if attr in _SOCKET_NUMBERS:
            sock = material.maya_input(mat, _SOCKET_NUMBERS[attr])
            return _MISSING if sock is None else float(sock.default_value)
        return _MISSING
    if found.kind == 'TEXTURE':
        if attr in ("fileTextureName", "ftn"):
            tex = found.data.nodes.get("file")
            if tex is not None and tex.image is not None:
                return tex.image.filepath
            return str(found.data.get(FILE_NAME_PROP, ""))
        return _MISSING
    if found.kind == 'EXTRUDE':
        long = _EXTRUDE_SHORT.get(attr, attr)
        key = EXTRUDE_ATTRS.get(long)
        if key is None:
            return _MISSING
        from ..operators import extrude
        default = dict(extrude.DEFAULTS, **extrude.MANIP_DEFAULTS).get(key, 0.0)
        value = found.data.get(key, default)
        return bool(value) if key == "keep_faces_together" else int(value) if key == "divisions" else float(value)
    if found.kind == 'HISTORY':
        values = prim_history.attrs(found.data)
        return values[attr] if attr in values else _MISSING
    return _MISSING


def _set_node_attr(found, attr, values):
    from ..operators import material
    v = list(_flatten(values))
    if found.kind == 'MATERIAL':
        mat = found.data
        if attr in _COLOR_ATTRS and len(v) == 3:
            sock = material.maya_input(mat, _COLOR_ATTRS[attr])
            if sock is not None:
                sock.default_value = (*[float(x) for x in v], 1.0)
                if attr == "color":
                    material.sync_display(mat)
                return True
        if attr in _NUMBER_ATTRS and len(v) == 1:
            setattr(mat, _NUMBER_ATTRS[attr], float(v[0]))
            return True
        if attr in _SOCKET_NUMBERS and len(v) == 1:
            sock = material.maya_input(mat, _SOCKET_NUMBERS[attr])
            if sock is not None:
                sock.default_value = float(v[0])
                return True
    if found.kind == 'TEXTURE' and attr in ("fileTextureName", "ftn") and len(v) == 1:
        import os
        path = str(v[0])
        found.data[FILE_NAME_PROP] = path
        tex = found.data.nodes.get("file")
        if tex is not None:
            tex.image = bpy.data.images.load(path, check_existing=True) if path and os.path.isfile(path) else None
        return True
    return False


def connect_texture(src_plug, dst_plug):
    """``connectAttr file1.outColor lambert2.color``: the file node's group goes into the material in front of its
    Maya colour input. Returns Maya's message, or None when the plugs aren't a texture -> material connection
    (for cmds_rig.connectAttr)."""
    from ..operators import material
    try:
        src_node, src_attr = str(src_plug).split(".", 1)
        dst_node, dst_attr = str(dst_plug).split(".", 1)
    except ValueError:
        return None
    src, dst = _node(src_node), _node(dst_node)
    if src is None or dst is None or src.kind != 'TEXTURE' or dst.kind != 'MATERIAL':
        return None
    if src_attr not in ("outColor", "outAlpha") or dst_attr not in _COLOR_ATTRS:
        return None
    mat = dst.data
    sock = material.maya_input(mat, _COLOR_ATTRS[dst_attr])
    if sock is None:
        return None
    tree = mat.node_tree
    node = next((n for n in tree.nodes if n.type == 'GROUP' and n.node_tree is src.data), None)
    if node is None:
        node = tree.nodes.new("ShaderNodeGroup")
        node.node_tree = src.data
        node.name = node.label = src.name
        node.location = (sock.node.location.x - 300, sock.node.location.y)
    tree.links.new(node.outputs[src_attr], sock)
    return f"Connected {src_plug} to {dst_plug}."


def shading_sources(plug):
    """Maya plugs feeding a material plug (``listConnections lambert2.color -s 1 -p 1``), or None when ``plug`` isn't
    a kit material's (for cmds_rig.listConnections)."""
    from ..operators import material
    try:
        node, attr = str(plug).split(".", 1)
    except ValueError:
        return None
    found = _node(node)
    if found is None or found.kind != 'MATERIAL' or attr not in _COLOR_ATTRS:
        return None
    sock = material.maya_input(found.data, _COLOR_ATTRS[attr])
    out = []
    for link in getattr(sock, "links", ()):
        n = link.from_node
        if n.type == 'GROUP' and n.node_tree is not None and n.node_tree.get(TEXTURE_PROP):
            out.append(f"{n.node_tree.name}.{link.from_socket.name}")
    return out


# --- polygon commands ------------------------------------------------------------------------------------------------

_COMPONENT = re.compile(r"^(.+)\.(f|vtx|e|map)\[(\d+)(?::(\d+))?\]$")


def _faces_of(args):
    """{object: [face ids]} of ``pCube1.f[1]`` / ``pCube1.f[0:2]`` names (the edit-mode selection without any)."""
    out = {}
    names = list(_flatten(args))
    if not names:
        for ob in _shim._selection():
            if ob.type == 'MESH':
                if ob.mode == 'EDIT':
                    bm = bmesh.from_edit_mesh(ob.data)
                    ids = [f.index for f in bm.faces if f.select]
                else:
                    ids = [p.index for p in ob.data.polygons if p.select]
                if ids:
                    out[ob] = ids
        return out
    for n in names:
        m = _COMPONENT.match(str(n))
        if m is None:
            ob = _shim._object(n)          # a whole mesh: every face (Maya extrudes them all)
            if ob.type == 'MESH':
                out.setdefault(ob, []).extend(range(len(ob.data.polygons)))
            continue
        ob = _shim._object(m.group(1))
        if m.group(2) != "f":
            raise RuntimeError(f"polyExtrudeFacet: {n} is not a face")
        a = int(m.group(3))
        b = int(m.group(4)) if m.group(4) is not None else a
        out.setdefault(ob, []).extend(range(a, b + 1))
    return out


def compact_components(ob_name, kind, ids):
    """Maya's component names: consecutive ids merge into ``f[a:b]``."""
    ids = sorted(set(ids))
    out, i = [], 0
    while i < len(ids):
        j = i
        while j + 1 < len(ids) and ids[j + 1] == ids[j] + 1:
            j += 1
        out.append(f"{ob_name}.{kind}[{ids[i]}]" if i == j else f"{ob_name}.{kind}[{ids[i]}:{ids[j]}]")
        i = j + 1
    return out


def _extrude_object(context, ob, ids, params, world_t, name, history):
    """Maya polyExtrudeFace on faces ``ids`` of ``ob`` (``operators/extrude.py`` geometry); the extruded faces keep
    their Maya ids and the new side faces come after them. Returns the node name (None without history)."""
    from ..operators import extrude, units
    me = ob.data
    in_edit = ob.mode == 'EDIT'
    if in_edit:
        bm = bmesh.from_edit_mesh(me)
    else:
        bm = bmesh.new()
        bm.from_mesh(me)
    try:
        bm.faces.ensure_lookup_table()
        bm.faces.index_update()
        faces = [bm.faces[i] for i in sorted(set(ids)) if 0 <= i < len(bm.faces)]
        if not faces:
            raise RuntimeError("polyExtrudeFacet: no faces to extrude")
        pre = bm.copy()
        unit = units.maya_unit(context.scene)
        keep_index = {fc: fc.index for fc in bm.faces}
        by_shape = {frozenset(extrude._key(v.co) for v in fc.verts): fc.index for fc in faces}
        caps, levels, vectors = extrude.extrude_topology(bm, faces, params["divisions"],
                                                         params["keep_faces_together"], **extrude.mesh_axes(ob))
        cap_index = {cap: by_shape.get(frozenset(extrude._key(v.co) for v in cap.verts)) for cap in caps}
        moved = extrude.moved_vertices(levels, vectors, unit)
        extrude.place(moved, params["thickness"], params["local_translate_z"], params["offset"],
                      **{k: params[k] for k in extrude.MANIP_FIELDS})
        if world_t.length:
            local = ob.matrix_world.to_3x3().inverted_safe() @ (world_t * unit)
            for v in {v for cap in caps for v in cap.verts}:
                v.co += local
        # Maya ids: the extruded faces keep theirs, new faces go after the old ones (bmesh made new caps)
        big = len(keep_index) + len(bm.faces) + 1
        order = {}
        for i, fc in enumerate(bm.faces):
            if fc in cap_index and cap_index[fc] is not None:
                order[fc] = cap_index[fc]
            elif fc in keep_index:
                order[fc] = keep_index[fc]
            else:
                order[fc] = big + i
        extrude.deselect_all(bm)
        for cap in caps:
            cap.select_set(True)
        bm.select_flush_mode()
        rank = {fc: i for i, fc in enumerate(sorted(bm.faces, key=lambda fc: order[fc]))}
        cap_ranks = [rank[cap] for cap in caps]
        # sorting moves the elements in memory: Python face references afterwards point elsewhere
        bm.faces.sort(key=lambda fc: order[fc])
        bm.faces.index_update()
        bm.faces.ensure_lookup_table()
        bm.verts.index_update()
        caps = [bm.faces[i] for i in cap_ranks]
        bm.normal_update()
        node = None
        if history:
            node = extrude.next_name(context.scene)
            if name:
                node = unique_node_name(str(name))
            rec = extrude.Record(node, pre, {k: params[k] for k in extrude.FACE.all_fields})
            rec.mesh_uid = me.session_uid
            extrude._store(rec, bm, caps, moved, rec.params)
            old = extrude.RECORDS.get(ob.name)
            if old is not None and old is not rec:
                old.free()
            extrude.keep(context, ob, rec)
            if extrude.RECORDS.get(ob.name) is not rec:
                node = None                  # Construction History off
        else:
            pre.free()
        if in_edit:
            bmesh.update_edit_mesh(me)
        else:
            bm.to_mesh(me)
            me.update()
    finally:
        if not in_edit:
            bm.free()
    if node is not None:
        entries = [e.to_dict() if hasattr(e, "to_dict") else dict(e) for e in me.get(HISTORY_PROP, ())]
        values = dict(params, translate_x=world_t.x, translate_y=world_t.y, translate_z=world_t.z)
        entries.append({"name": node, "type": extrude.NODE, "values": values})
        me[HISTORY_PROP] = entries
    return node


def polyExtrudeFacet(*args, **kwargs):
    """``polyExtrudeFacet pCube1.f[1] -ltz 2`` = Maya polyExtrudeFace through the kit's extrusion (the In-View
    Editor / Channel Box INPUTS show the node); returns [polyExtrudeFaceN]. ``-t`` / ``-tx`` … is a world move of
    the extruded faces in the kit's axes (Blender's, like ``move``); the faces stay selected."""
    from ..operators import extrude
    f = _Flags("polyExtrudeFacet", kwargs)
    params = dict(extrude.DEFAULTS, **extrude.MANIP_DEFAULTS)
    for long, short, key in (("localTranslateZ", "ltz", "local_translate_z"),
                             ("localTranslateX", "ltx", "local_translate_x"),
                             ("localTranslateY", "lty", "local_translate_y"),
                             ("thickness", "tk", "thickness"), ("offset", "off", "offset"),
                             ("divisions", "dv", "divisions"), ("keepFacesTogether", "kft", "keep_faces_together")):
        v = f.get(long, short)
        if v is None and short == "tk":
            v = f.get("thk")
        if v is not None:
            params[key] = v
    ls = f.get("localScale", "ls")
    if ls is not None:
        params.update(local_scale_x=ls[0], local_scale_y=ls[1], local_scale_z=ls[2])
    t = Vector(f.get("translate", "t") or (0.0, 0.0, 0.0))
    for i, (long, short) in enumerate((("translateX", "tx"), ("translateY", "ty"), ("translateZ", "tz"))):
        v = f.get(long, short)
        if v is not None:
            t[i] = float(v)
    name = f.get("name", "n")
    history = f.get("constructionHistory", "ch", True)
    for long, short in (("worldSpace", "ws"), ("smoothingAngle", "sma"), ("localCenter", "lc"),
                        ("localDirection", "ld"), ("random", "ran"), ("pivot", "pvt"), ("rotate", "ro"),
                        ("scale", "s"), ("caching", "cch"), ("nodeState", "nds"), ("reverseAllFaces", "raf")):
        f.get(long, short)
    f.done()
    params["divisions"] = max(1, int(params["divisions"]))
    params["keep_faces_together"] = bool(params["keep_faces_together"])
    for k in params:
        if k not in ("divisions", "keep_faces_together"):
            params[k] = float(params[k])
    targets = _faces_of(args)
    if not targets:
        raise RuntimeError("polyExtrudeFacet: no faces given or selected")
    context = bpy.context
    from ..operators import prim_history
    history = bool(history) and prim_history.history_on(context)
    out, picked = [], []
    for ob, ids in targets.items():
        node = _extrude_object(context, ob, ids, params, t, name, history)
        if node is not None:
            out.append(node)
        picked += compact_components(ob.name, "f", ids)
    sel = _shim._selection()
    select_nodes([o.name for o in sel] + picked, keep_objects=True)
    return out


def polyEvaluate(*args, **kwargs):
    """``polyEvaluate -v / -e / -f / -t / -uv``: counts of the mesh (Maya's shape = the kit's mesh without its
    display-only smooth preview); several flags / none = a dict like Maya's."""
    f = _Flags("polyEvaluate", kwargs)
    wanted = []
    for long, short, key in (("vertex", "v", "vertex"), ("edge", "e", "edge"), ("face", "f", "face"),
                             ("triangle", "t", "triangle"), ("uvcoord", "uv", "uvcoord"),
                             ("shell", "s", "shell")):
        if f.get(long, short, False):
            wanted.append(key)
    f.done()
    obs = _shim._objects(args)
    counts = {"vertex": 0, "edge": 0, "face": 0, "triangle": 0, "uvcoord": 0, "shell": 0}
    for ob in obs:
        if ob.type != 'MESH':
            raise RuntimeError(f"polyEvaluate: {ob.name} is not a polygon mesh")
        if ob.mode == 'EDIT':
            ob.update_from_editmode()
        me = ob.data
        counts["vertex"] += len(me.vertices)
        counts["edge"] += len(me.edges)
        counts["face"] += len(me.polygons)
        counts["triangle"] += sum(len(p.vertices) - 2 for p in me.polygons)
        uv = me.uv_layers.active
        if uv is not None:
            counts["uvcoord"] += len({(p.vertex_index, round(d.uv[0], 6), round(d.uv[1], 6))
                                      for p, d in zip(me.loops, uv.data)})
        counts["shell"] += _shells(me)
    if len(wanted) == 1:
        return counts[wanted[0]]
    return {k: counts[k] for k in (wanted or counts)}


def _shells(me):
    parent = list(range(len(me.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in me.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    return len({find(i) for i in range(len(me.vertices))})


def exactWorldBoundingBox(*args, **kwargs):
    """World bounding box of the shapes' points (evaluated, with everything under the objects), Maya units, in the
    kit's axes like ``xform -q -bb`` (xmin ymin zmin xmax ymax zmax)."""
    f = _Flags("exactWorldBoundingBox", kwargs)
    f.get("calculateExactly", "ce", False)
    f.get("ignoreInvisible", "ii", False)
    f.done()
    obs = _shim._objects(args)
    context = bpy.context
    context.view_layer.update()
    dg = context.evaluated_depsgraph_get()
    pts = []
    for ob in obs:
        for o in [ob, *ob.children_recursive]:
            if o.mode == 'EDIT' and o.type == 'MESH':
                o.update_from_editmode()
            ev = o.evaluated_get(dg)
            if o.type == 'MESH' and len(ev.data.vertices):
                mw = ev.matrix_world
                pts += [mw @ v.co for v in ev.data.vertices]
            elif o.type != 'MESH':
                pts += _shim._corners(o)
    if not pts:
        return [0.0] * 6
    k = _shim.linear_factor()
    return [min(p[i] for p in pts) / k for i in range(3)] + [max(p[i] for p in pts) / k for i in range(3)]


def listHistory(*args, **kwargs):
    """``listHistory`` = the shape, then its history newest first: the extrusions the kit made, then the creation
    node (Maya: -pdo polyExtrudeFace3 2 1 polyCube1). ``-pdo`` leaves the DAG nodes out."""
    from ..operators import prim_history
    f = _Flags("listHistory", kwargs)
    pdo = f.get("pruneDagObjects", "pdo", False)
    f.get("future", "f", False)
    f.get("levels", "lv")
    f.done()
    out = []
    for ob in _shim._objects(args):
        shape = _shim.shape_of(ob)
        if shape and not pdo:
            out.append(shape)
        if ob.type == 'MESH':
            out += [n for n, _t, _v in reversed(_extrusion_nodes(ob))]
        node = prim_history.node_dict(prim_history.owner_of(ob))
        if node is not None and node.get("name"):
            out.append(node["name"])
    return out or None


def camera(*args, **kwargs):
    """``camera`` = Create > Camera (``create.KINDS['CAMERA']``: camera1 / cameraShape1, a 35 mm lens on 36 mm
    film, level like Maya's); selected; returns [transform, shape]."""
    from ..operators import create
    f = _Flags("camera", kwargs)
    focal = f.get("focalLength", "fl")
    near = f.get("nearClipPlane", "ncp")
    far = f.get("farClipPlane", "fcp")
    ortho = f.get("orthographic", "o")
    width = f.get("orthographicWidth", "ow")
    f.get("position", "p")
    f.done()
    if args:
        raise RuntimeError("camera: editing an existing camera is not supported")
    context = bpy.context
    ob = create.create(context, 'CAMERA')
    data = ob.data
    k = _shim.linear_factor()
    if focal is not None:
        data.lens = float(focal)
    if near is not None:
        data.clip_start = float(near) * k
    if far is not None:
        data.clip_end = float(far) * k
    if ortho is not None:
        data.type = 'ORTHO' if ortho else 'PERSP'
    if width is not None:
        data.ortho_scale = float(width) * k
    _shim._view_layer()
    _shim._select_only([ob])
    return [ob.name, _shim.shape_of(ob)]


# --- non-DAG selection, ls / select / getAttr / setAttr / objExists for these nodes ----------------------------------

_EXTRA = {"items": [], "sig": None}


def _selection_signature():
    return tuple(o.name for o in _shim._selection())


def select_nodes(items, keep_objects=False):
    """Make ``items`` (non-DAG nodes, components; object names when ``keep_objects``) the selection, as Maya's
    shadingNode / polyExtrudeFacet do. The kit keeps them beside Blender's object selection until it changes."""
    objects = [n for n in items if bpy.data.objects.get(n) is not None]
    extra = [n for n in items if n not in objects]
    if not keep_objects:
        _shim._select_only([bpy.data.objects[n] for n in objects])
    _EXTRA["items"] = extra
    _EXTRA["sig"] = _selection_signature()


def extra_selection():
    if _EXTRA["sig"] is not None and _EXTRA["sig"] != _selection_signature():
        _EXTRA["items"], _EXTRA["sig"] = [], None
    return list(_EXTRA["items"])


def _node_list():
    """Every non-DAG Maya node: (name, type)."""
    from ..operators import material, sets as kit_sets
    material.default_material()
    out = [(m.name, _material_type(m)) for m in _materials()]
    out += [(g.name, g[TEXTURE_PROP]) for g in _textures()]
    out += [(c.name, "objectSet") for c in kit_sets.all_sets()]
    out += list(DEFAULT_SETS.items()) + [(n, "shadingEngine") for n in _shading_groups()]
    out += list(DEFAULT_NODES.items())
    return out


def _material_types():
    from ..operators import material
    return {v[0] for v in material.MATERIALS.values()} | {"material"}


def _extend_shim():
    """Teach the shim's ls / select / getAttr / setAttr / objExists the non-DAG nodes above (they stay the shim's
    for DAG objects)."""
    ls0, select0, get0, set0, exists0 = _shim.ls, _shim.select, _shim.getAttr, _shim.setAttr, _shim.objExists

    def ls(*args, **kwargs):
        kw = dict(kwargs)
        mats = kw.pop("materials", kw.pop("mat", False))
        texs = kw.pop("textures", kw.pop("tex", False))
        typ = kw.get("type", kw.get("typ"))
        names = list(_flatten(args))
        dag_names = [n for n in names if any(c in str(n) for c in "*?") or _dag(n) is not None]
        node_names = [n for n in names if n not in dag_names]
        if mats or texs:
            out = [n for n, t in _node_list() if (mats and t in _material_types()) or (texs and t == "file")]
            return [n for n in out if not names or n in node_names]
        types = [] if typ is None else list(typ) if isinstance(typ, (list, tuple)) else [typ]
        if names and not dag_names:
            out = []
        elif names:
            out = ls0(*dag_names, **kw)
        else:
            out = ls0(**kw)
        extra = []
        if kw.get("selection") or kw.get("sl"):
            extra = extra_selection() if not names else []
        elif types:
            extra = sorted(n for n, t in _node_list() if any(x in _chain(t) for x in types))
        for n in node_names:
            found = _node(n)
            if found is not None and (not types or any(x in _chain(found.type) for x in types)):
                extra.append(found.name)
        return out + [n for n in extra if n not in out]

    def select(*args, **kwargs):
        names = list(_flatten(args))
        dag, nodes = [], []
        for n in names:
            found = None if (any(c in str(n) for c in "*?") or _dag(n) is not None) else _node(n)
            if found is not None and found.kind == 'SET':
                dag += _set_members(found)          # Maya: select <set> = its members
            elif found is not None:
                nodes.append(found.name)
            else:
                dag.append(n)
        if names and not dag and nodes and not kwargs:
            result = select0(clear=True)
        else:
            result = select0(*dag, **kwargs) if (dag or not names) else None
        _EXTRA["items"], _EXTRA["sig"] = [], None
        if nodes:
            _EXTRA["items"], _EXTRA["sig"] = nodes, _selection_signature()
        return result

    def getAttr(attr, **kwargs):
        text = str(attr)
        node = text.rsplit("|", 1)[-1].split(".", 1)[0]
        if "." in text and _dag(node) is None:
            found = _node(node)
            if found is not None:
                name = text.split(".", 1)[1]
                value = _node_attr_value(found, name)
                if value is not _MISSING:
                    if kwargs.get("type") or kwargs.get("typ"):
                        return "float3" if isinstance(value, list) else "string" if isinstance(value, str) else \
                            "bool" if isinstance(value, bool) else "long" if isinstance(value, int) else "float"
                    return value
        return get0(attr, **kwargs)

    def setAttr(attr, *values, **kwargs):
        text = str(attr)
        node = text.rsplit("|", 1)[-1].split(".", 1)[0]
        if "." in text and _dag(node) is None:
            found = _node(node)
            if found is not None:
                kw = {k: v for k, v in kwargs.items() if k not in ("type", "typ")}
                if not kw and _set_node_attr(found, text.split(".", 1)[1], values):
                    return None
        return set0(attr, *values, **kwargs)

    def objExists(name, **kwargs):
        if exists0(name, **kwargs):
            return True
        text = str(name).rsplit("|", 1)[-1]
        node, _dot, attr = text.partition(".")
        found = _node(node)
        if found is None:
            return False
        return not attr or _node_attr_value(found, attr) is not _MISSING

    for fn, old in ((ls, ls0), (select, select0), (getAttr, get0), (setAttr, set0), (objExists, exists0)):
        fn.__doc__ = old.__doc__
        fn.__name__ = old.__name__
        fn.__wrapped__ = old
        setattr(_shim, old.__name__, fn)


_extend_shim()
