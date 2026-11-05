# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Channel Box in the 3D View sidebar (category "Channel Box / Layer Editor").

Maya's Channel Box.
- Translate/Rotate/Scale/Visibility rows are getter/setter proxies on
  ``Scene.allset_cb``: they read the lead (active) object and write every
  selected object, like Maya.
- Channel names are buttons that select channels; selected channels drive
  the MMB virtual slider in the viewport and the
  Channels menu.
- Value fields are text: Maya numbers in display units and relative entry
  (``+=5``, ``*=2``; ui/cb_entry.py), applied to every selected object that has the
  channel and to every selected channel when the edited row is one of them.
- Custom properties, SHAPES (object data) and INPUTS (modifiers = construction history)
  are rows in ``Scene.allset_cb.rows`` (rebuilt from handlers), so their edits reach
  the same-named channel of the other selected objects too; stale rows fall back to the
  lead object's real properties.
"""

import math

import bpy
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty,
                       StringProperty)

from .. import results
from ..operators import auto_key, display
from .. import compat, i18n
from . import cb_entry, cb_points, chrome

# Maya's dock is one tab stack with vertical tabs on its right edge: the
# kit's sidebar categories carry Maya's tab names
CATEGORY = "Channel Box / Layer Editor"
AE_CATEGORY = "Attribute Editor"
MTK_CATEGORY = "Modeling Toolkit"
# Channel Box pane share of the dock, Layer Editor below: about half of the dock below its header, like Maya's
# standard screen.
# The split is fixed: a long Channel Box scrolls inside its part.
CB_SHARE = 0.50
CB_SHARE_MAX = 0.62      # the Layer Editor keeps its tabs, toolbar and a few rows
CB_LINES = 14            # a cube's collapsed Channel Box: 10 channels, SHAPES + shape, INPUTS + polyCube1


def cb_share(region, u):
    """Share of the dock height above the Layer Editor: about half (CB_SHARE), more on a short
    dock so a selected primitive's collapsed Channel Box (CB_LINES) still fits
    without scrolling — fixed for a given dock height, like Maya's split."""
    if region is None or region.height <= 0 or u <= 0:
        return CB_SHARE
    need = (PANE_TOP + 3.0 + 0.3 + CB_LINES * ROW_SCALE) * u    # = pane_room's terms for the menu bar + name line
    return min(CB_SHARE_MAX, max(CB_SHARE, need / region.height))

# key, label, data path, index, kind
MAIN = (
    ("tx", "Translate X", "location", 0, "LOC"),
    ("ty", "Translate Y", "location", 1, "LOC"),
    ("tz", "Translate Z", "location", 2, "LOC"),
    ("rx", "Rotate X", "rotation_euler", 0, "ROT"),
    ("ry", "Rotate Y", "rotation_euler", 1, "ROT"),
    ("rz", "Rotate Z", "rotation_euler", 2, "ROT"),
    ("sx", "Scale X", "scale", 0, "SCALE"),
    ("sy", "Scale Y", "scale", 1, "SCALE"),
    ("sz", "Scale Z", "scale", 2, "SCALE"),
    ("v", "Visibility", "hide_viewport", -1, "VIS"),
)
MAIN_BY_KEY = {c[0]: c for c in MAIN}
_LOCK_PROP = {"LOC": "lock_location", "ROT": "lock_rotation", "SCALE": "lock_scale"}

# Per-object bookkeeping for Maya attribute flags Blender doesn't have.
HIDDEN_PROP = "allset_cb_hidden"
NONKEYABLE_PROP = "allset_cb_nonkeyable"
CUSTOM_PREFIX = "cp:"
HISTORY_PREFIX = "ph:"   # an attribute of the creation node (polyCube1 ...): "ph:<attribute>"
MODEL_PREFIX = "mh:"     # a parameter of the active modeling node, identified by node kind and field
INPUT_PREFIX = "in:"     # an INPUTS row as a channel: "in:<modifier type>:<nth of that type>:<property>"
SHAPE_PREFIX = "sh:"     # a SHAPES row as a channel: light Intensity / Color, camera Focal Length ...
BLEND_PREFIX = "bw:"     # a blendShape target weight in INPUTS: "bw:<target name>" (the shape key's value)

# MMB slider: value change per pixel at speed Medium (a custom attribute moves 0.1 per px, like Maya).
SLIDER_STEP = {"LOC": 0.01, "ROT": math.radians(0.5), "SCALE": 0.01, "CUSTOM": 0.1, "SHAPE": 0.01, "INPUT": 0.01,
               "HISTORY": 0.01, "BLEND": 0.01, "MODEL": 0.01}
SPEEDS = (("SLOWEST", "Slowest", "x0.01", 0.01), ("SLOW", "Slow", "x0.1", 0.1),
          ("MEDIUM", "Medium", "x1", 1.0), ("FAST", "Fast", "x10", 10.0))
SPEED_FACTOR = {s[0]: s[3] for s in SPEEDS}


def model_key(record, field):
    return f'{MODEL_PREFIX}{record.spec.kind}:{field}'


def model_node(ob, key):
    from . import node_attributes
    if not isinstance(ob, bpy.types.Object):
        return None
    _prefix, kind, field = key.split(':', 2)
    node = node_attributes.target(bpy.context, ob)
    return node if (isinstance(node, node_attributes.ModelingNode) and node.spec.kind == kind
                    and field in node.params) else None


# --- nodes: objects or pose bones -------------------------------------------------
# A Maya joint is a pose bone. Pose bones carry the
# same RNA names as objects (location / rotation_euler / scale / lock_* / rotation_mode / ID
# properties); only their animation lives on the armature object (``pose.bones["n"].<path>``).

def is_bone(node):
    return isinstance(node, bpy.types.PoseBone)


def is_root_joint(node):
    """A joint without a parent joint: a Maya root joint (its parent is the world)."""
    return is_bone(node) and node.parent is None


def root_translate(pb):
    """Translate X / Y / Z of a root joint = its position (Maya 2026: a root joint at (3, 2, 1) shows Translate
    3 / 2 / 1): rest head + pose offset, armature space, in the kit's Z-up axes
    like every object Translate (operators/joint_edit.joint_translate shows the same in Edit
    mode). Blender keeps a pose bone's offset in the bone's rest axes."""
    b = pb.bone
    return b.head_local + b.matrix_local.to_3x3().normalized() @ pb.location


def set_root_translate(pb, t):
    """Move root joint ``pb`` so ``root_translate`` reads ``t`` (Blender length)."""
    from mathutils import Vector
    b = pb.bone
    pb.location = b.matrix_local.to_3x3().normalized().transposed() @ (Vector(t) - b.head_local)


def bone_selected(pb):
    return pb.select                    # 5.x: the selection is on the pose bone (Bone.select is gone)


def set_bone_selected(pb, state):
    pb.select = state


def active_object(context=None):
    """``context.active_object``, else the view layer's: a depsgraph handler running while a File Browser or
    Preferences window has the context gets no ``active_object`` member."""
    context = context or bpy.context
    if hasattr(context, "active_object"):
        return context.active_object
    view_layer = getattr(context, "view_layer", None)
    return view_layer.objects.active if view_layer is not None else None


def pose_armature(context=None):
    """The active armature when it is in pose mode (= Maya: joints are being picked)."""
    ob = active_object(context)
    return ob if ob is not None and ob.type == 'ARMATURE' and ob.mode == 'POSE' else None


def placing_joints(context=None):
    ob = active_object(context)
    return ob is not None and ob.type == 'ARMATURE' and ob.mode == 'EDIT'


def pose_objects(context=None):
    context = context or bpy.context
    arm = pose_armature(context)
    if arm is None:
        return []
    others = [o for o in context.view_layer.objects
              if o is not arm and o.type == 'ARMATURE' and o.mode == 'POSE']
    return [arm] + others


def selected_bones(context=None):
    return [pb for arm in pose_objects(context) for pb in arm.pose.bones
            if bone_selected(pb) and not compat.bone_hidden(pb)]


def lead(context=None):
    """The Maya lead: the active object, or in pose mode the active (selected) pose bone."""
    context = context or bpy.context
    arm = pose_armature(context)
    if arm is None:
        return active_object(context)
    act = arm.data.bones.active
    pb = arm.pose.bones.get(act.name) if act is not None else None
    if pb is not None and bone_selected(pb) and not compat.bone_hidden(pb):
        return pb
    sel = selected_bones(context)
    return sel[0] if sel else None


def targets(context=None):
    """Lead + selected objects / pose bones (lead first), like Maya's selection list."""
    context = context or bpy.context
    nodes = selected_bones(context) if pose_armature(context) else list(context.selected_objects)
    ld = lead(context)
    if ld is not None:
        nodes = [ld] + [n for n in nodes if n != ld]
    return nodes


def full_path(node, path):
    """Animation data path of ``path`` on the node's ID (the armature object for a bone)."""
    if not is_bone(node):
        return path
    return None if path == "hide_viewport" else node.path_from_id(path)   # bone visibility: Bone.hide


def _flag_list(ob, prop):
    raw = ob.get(prop, "")
    return [s for s in raw.split(",") if s] if isinstance(raw, str) else []


def _set_flag_list(ob, prop, keys):
    if keys:
        ob[prop] = ",".join(sorted(set(keys)))
    elif prop in ob:
        del ob[prop]


def is_hidden(ob, key):
    return key in _flag_list(ob, HIDDEN_PROP)


def is_keyable(ob, key):
    if key.startswith(MODEL_PREFIX):
        return False
    if key == "v" and is_bone(ob):
        return False   # Bone.hide lives on the armature data, not in the object's action
    return key not in _flag_list(ob, NONKEYABLE_PROP)


def is_locked(ob, key):
    if key.startswith(HISTORY_PREFIX):
        from ..operators import prim_history
        ob = prim_history.owner_of(ob) or ob
    if key.startswith((MODEL_PREFIX, HISTORY_PREFIX)):
        return key in _flag_list(ob, 'allset_cb_model_locked')
    c = MAIN_BY_KEY.get(key)
    if c is None or c[4] not in _LOCK_PROP:
        return False
    return bool(getattr(ob, _LOCK_PROP[c[4]])[c[3]])


def set_locked(ob, key, locked):
    if key.startswith(HISTORY_PREFIX):
        from ..operators import prim_history
        ob = prim_history.owner_of(ob) or ob
    if key.startswith((MODEL_PREFIX, HISTORY_PREFIX)):
        keys = set(_flag_list(ob, 'allset_cb_model_locked'))
        keys.add(key) if locked else keys.discard(key)
        _set_flag_list(ob, 'allset_cb_model_locked', keys)
        return True
    c = MAIN_BY_KEY.get(key)
    if c is None or c[4] not in _LOCK_PROP:
        return False
    arr = getattr(ob, _LOCK_PROP[c[4]])
    arr[c[3]] = locked
    return True


def custom_keys(ob):
    """Numeric custom properties = Maya extra (user-defined) attributes."""
    out = []
    for k in ob.keys():
        if k.startswith("_") or k.startswith("allset_"):
            continue
        if isinstance(ob[k], (int, float)):  # bool is an int too
            out.append(k)
    return sorted(out)


def is_shape_key(key):
    return key.startswith(SHAPE_PREFIX)


def shape_owner(ob, key):
    """The object data holding SHAPES channel ``key`` (None: ``ob`` has no such row)."""
    if not is_shape_key(key) or is_bone(ob):
        return None
    name = key[len(SHAPE_PREFIX):]
    if name not in SHAPE_PROPS.get(getattr(ob, "type", ""), ()):
        return None
    return row_owner(ob, "SHAPE", name)


def shape_paths(owner, key):
    """[(Blender data path, index)] a key / mute / delete on a SHAPES channel acts on: a Maya attribute
    kept differently in Blender keys its Blender properties (Light Intensity = power, Color R = color[0], spot Cone /
    Penumbra = spot_size + spot_blend)."""
    name = key[len(SHAPE_PREFIX):]
    v = _virtual(owner, name)
    if v is not None:
        return list(getattr(v, "paths", ()))
    if isinstance(owner, bpy.types.Light):
        from ..operators import lights
        if name in lights.KEY_PATHS:
            return lights.key_paths(owner, name)
    rna = owner.bl_rna.properties.get(name)
    return [(name, -1)] if rna is not None and rna.is_animatable else []


def is_input_key(key):
    return key.startswith(INPUT_PREFIX)


def input_key(mod_type, nth, name):
    return f"{INPUT_PREFIX}{mod_type}:{nth}:{name}"


def input_parts(key):
    """(modifier type, nth, property) of an INPUTS channel key."""
    mod_type, nth, name = key[len(INPUT_PREFIX):].split(":", 2)
    return mod_type, int(nth), name


def input_owner(ob, key):
    """The modifier holding INPUTS channel ``key`` on ``ob`` (same type at the same position, like a typed value)."""
    if not is_input_key(key) or is_bone(ob) or not hasattr(ob, "modifiers"):
        return None
    mod_type, nth, name = input_parts(key)
    return row_owner(ob, "INPUT", name, mod_type, nth)


def input_paths(owner, key):
    """[(path on the modifier, index)] a key on an INPUTS channel sets."""
    name = input_parts(key)[2]
    v = _virtual(owner, name)
    if v is not None:
        return list(getattr(v, "paths", ()))
    rna = owner.bl_rna.properties.get(name)
    return [(name, -1)] if rna is not None and rna.is_animatable else []


def is_blend_key(key):
    return key.startswith(BLEND_PREFIX)


def blend_target(ob, key):
    """The shape key behind blendShape weight channel ``key`` on ``ob`` (None: ob has no target of that name)."""
    if not is_blend_key(key) or is_bone(ob):
        return None
    bs = blend_shape_key(ob)
    if bs is None:
        return None
    name = key[len(BLEND_PREFIX):]
    return next((kb for kb in blend_shape_targets(bs) if kb.name == name), None)


def blend_path(name):
    """Data path of a target weight on the Key datablock (its animation lives there, like Maya's blendShape node)."""
    return f'key_blocks["{bpy.utils.escape_identifier(name)}"].value'


def is_history_key(key):
    return key.startswith(HISTORY_PREFIX)


def history_node_of(ob, key):
    """(owner, node) of ``ob``'s creation node when it has attribute ``key`` and the lead's node type, else (None,
    None) (a typed value goes to every selected object whose node has the same type)."""
    if not is_history_key(key) or not isinstance(ob, bpy.types.Object):
        return None, None
    from ..operators import prim_history
    owner, node = prim_history.node_of(ob)
    name = key[len(HISTORY_PREFIX):]
    if node is None or name not in prim_history.attrs(owner):
        return None, None
    ld = lead()
    if ld is not None and ld is not ob and isinstance(ld, bpy.types.Object):
        _o, lead_node = prim_history.node_of(ld)
        if lead_node is not None and lead_node["type"] != node["type"]:
            return None, None
    return owner, node


def _history_get(ob, key):
    from ..operators import prim_history
    owner, node = history_node_of(ob, key)
    name = key[len(HISTORY_PREFIX):]
    return prim_history.to_entry(node, name, prim_history.attrs(owner)[name])


def _history_set(ob, key, value):
    from ..operators import prim_history, prim_shapes
    owner, node = history_node_of(ob, key)
    name = key[len(HISTORY_PREFIX):]
    value = prim_history.from_entry(node, name, value)
    if prim_history.entry_kind(node["type"], name) == "INT":
        value = math.floor(value + 0.5)      # a drag / slider gives floats: integer attributes step
    value = prim_shapes.clamp(node["type"], name, value)
    if value != prim_history.attrs(owner)[name]:
        prim_history.rebuild(bpy.context, ob, {name: value})


def row_key(row):
    """The channel key of a Channel Box row (CUSTOM / SHAPE / INPUT), or None."""
    if row.kind == "CUSTOM":
        return CUSTOM_PREFIX + row.name
    if row.kind == "SHAPE":
        return SHAPE_PREFIX + row.name
    if row.kind == "INPUT":
        return input_key(row.mod_type, row.nth, row.name)
    if row.kind == "BLEND":
        return BLEND_PREFIX + row.name
    return None


def curve_owner(ob, key):
    """The ID whose animation holds channel ``key``'s curves."""
    if is_blend_key(key):
        kb = blend_target(ob, key)
        return kb.id_data if kb is not None else None
    return shape_owner(ob, key) if is_shape_key(key) else ob.id_data


def channel_path(key):
    """(data path, index, kind) for a channel key."""
    if key.startswith(MODEL_PREFIX):
        return key.rsplit(':', 1)[1], -1, 'MODEL'
    if key.startswith(CUSTOM_PREFIX):
        return f'["{key[len(CUSTOM_PREFIX):]}"]', -1, "CUSTOM"
    if is_shape_key(key):
        return key[len(SHAPE_PREFIX):], -1, "SHAPE"
    if is_input_key(key):
        return input_parts(key)[2], -1, "INPUT"
    if is_history_key(key):
        return key[len(HISTORY_PREFIX):], -1, "HISTORY"
    if is_blend_key(key):
        return blend_path(key[len(BLEND_PREFIX):]), -1, "BLEND"
    c = MAIN_BY_KEY[key]
    return c[2], c[3], c[4]


def nice_name(name):
    """Maya's nice attribute name (Channel Names > Nice, the default):
    ``fingerCurl`` -> "Finger Curl", ``curl`` -> "Curl", ``ik_blend2`` -> "Ik Blend 2"."""
    import re
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])", " ", name.replace("_", " ")).split()
    return " ".join(w[:1].upper() + w[1:] for w in words) or name


def channel_label(key):
    if key.startswith(MODEL_PREFIX):
        from ..operators import extrude
        _prefix, kind, field = key.split(':', 2)
        return extrude.SPECS[kind].labels[field]
    if key.startswith(CUSTOM_PREFIX):
        return nice_name(key[len(CUSTOM_PREFIX):])
    if is_shape_key(key):
        ob = lead()
        name = key[len(SHAPE_PREFIX):]
        return shape_label(ob, name) if ob is not None and shape_owner(ob, key) is not None else nice_name(name)
    if is_input_key(key):
        ob = lead()
        owner = input_owner(ob, key) if ob is not None else None
        name = input_parts(key)[2]
        return input_label(owner, name) if owner is not None else nice_name(name)
    if is_history_key(key):
        from ..operators import prim_shapes
        _owner, node = history_node_of(lead(), key) if lead() is not None else (None, None)
        name = key[len(HISTORY_PREFIX):]
        return prim_shapes.spec(node["type"], name)[1] if node is not None else nice_name(name)
    if is_blend_key(key):
        return key[len(BLEND_PREFIX):]      # Maya names a weight after its target
    return MAIN_BY_KEY[key][1]


def has_channel(ob, key):
    if key.startswith(MODEL_PREFIX):
        return model_node(ob, key) is not None
    if key.startswith(CUSTOM_PREFIX):
        return key[len(CUSTOM_PREFIX):] in ob.keys()
    if is_shape_key(key):
        return shape_owner(ob, key) is not None
    if is_input_key(key):
        return input_owner(ob, key) is not None
    if is_history_key(key):
        return history_node_of(ob, key)[1] is not None
    if is_blend_key(key):
        return blend_target(ob, key) is not None
    # Maya rotation channels are always Rotate X / Y / Z: quaternion / axis-angle nodes show Euler
    return MAIN_BY_KEY[key][4] != "ROT" or hasattr(ob, "rotation_mode")


def _non_euler_rot(ob, kind):
    return kind == "ROT" and getattr(ob, "rotation_mode", 'XYZ') in ('QUATERNION', 'AXIS_ANGLE')


def get_value(ob, key):
    path, idx, kind = channel_path(key)
    if kind == 'MODEL':
        return model_node(ob, key).params[path]
    if kind == "SHAPE":
        return _row_read(shape_owner(ob, key), "SHAPE", path)
    if kind == "INPUT":
        return _row_read(input_owner(ob, key), "INPUT", path)
    if kind == "HISTORY":
        return _history_get(ob, key)
    if kind == "BLEND":
        return blend_target(ob, key).value
    if kind == "CUSTOM":
        return ob[key[len(CUSTOM_PREFIX):]]
    if kind == "VIS":
        return not (compat.bone_hidden(ob) if is_bone(ob) else ob.hide_viewport)
    if _non_euler_rot(ob, kind):
        from .. import rotation_display
        return rotation_display.shown_euler(ob)[idx]
    if kind == "LOC" and is_root_joint(ob):
        return root_translate(ob)[idx]
    return getattr(ob, path)[idx]


# Called before the Channel Box writes a channel: (node, key). The Set Driven Key window keeps a
# typed value on a driven channel this way (operators/driven_key.hold_driven).
WRITE_HOOKS = []


def set_value(ob, key, value):
    for hook in WRITE_HOOKS:
        hook(ob, key)
    path, idx, kind = channel_path(key)
    if kind == 'MODEL':
        node = model_node(ob, key)
        node.preview(bpy.context, dict(node.params, **{path: node.descriptor(path).limit(value)}))
        return
    if kind == "SHAPE":
        _row_write(shape_owner(ob, key), "SHAPE", path, value)
        return
    if kind == "INPUT":
        owner = input_owner(ob, key)
        rna = owner.bl_rna.properties.get(path)
        if rna is not None and rna.type == 'INT' and not isinstance(value, bool):
            value = int(math.floor(value + 0.5))     # a drag / slider gives floats: integer attributes step
        _row_write(owner, "INPUT", path, value)
        return
    if kind == "HISTORY":
        _history_set(ob, key, value)
        return
    if kind == "BLEND":
        blend_target(ob, key).value = value
        return
    if kind == "CUSTOM":
        name = key[len(CUSTOM_PREFIX):]
        cur = ob[name]
        if isinstance(cur, (int, float)) and not isinstance(cur, bool):
            # Maya clamps a typed value to the attribute's Min / Max (Add Attribute)
            try:
                ui = ob.id_properties_ui(name).as_dict()
                value = max(ui.get("min", value), min(ui.get("max", value), value))
            except TypeError:
                pass
        ob[name] = type(cur)(value)
        ob.id_data.update_tag()   # an ID property write tags nothing: drivers reading it would not update
    elif kind == "VIS":
        if is_bone(ob):
            compat.set_bone_hidden(ob, not value)
        else:
            ob.hide_viewport = not value
    elif _non_euler_rot(ob, kind):
        from .. import rotation_display
        rotation_display.set_component(ob, idx, value)
    elif kind == "LOC" and is_root_joint(ob):
        t = root_translate(ob)
        t[idx] = value
        set_root_translate(ob, t)
    else:
        getattr(ob, path)[idx] = value


def keyframe(ob, key, keytype='KEYFRAME'):
    path, idx, kind = channel_path(key)
    if kind in {"HISTORY", "MODEL"}:
        return False
    if kind == "VIS" and is_bone(ob):
        return False
    if kind == "BLEND":
        # a blendShape weight is keyed on the mesh's Key datablock (Graph Editor / Dope Sheet show it there)
        kb = blend_target(ob, key)
        if kb is None:
            return False
        from ..operators import anim_layers
        if anim_layers.has_layers(kb.id_data):
            # the weight's blendShape node is in animation layers: keyed on the selected layer, solved like Translate
            return anim_layers.key(kb.id_data, path, -1)
        try:
            ok = kb.id_data.keyframe_insert(path, keytype=keytype)
        except (TypeError, RuntimeError):
            return False
        if ok:
            from ..operators import graph_key_menu
            graph_key_menu.after_insert(kb.id_data, path, -1, bpy.context.scene.frame_current)
        return ok
    if _non_euler_rot(ob, kind):
        # a quaternion is one rotation: Rotate X / Y / Z key all its components
        from .. import rotation_display
        path, idx = rotation_display.curve_path(ob), -1
    elif kind == "LOC" and is_root_joint(ob):
        # a root joint's Translate X / Y / Z mixes the bone's location components (rest axes): key all three
        idx = -1
    if kind in ("SHAPE", "INPUT"):
        owner = shape_owner(ob, key) if kind == "SHAPE" else input_owner(ob, key)
        if owner is None:
            return False
        from ..operators import graph_key_menu
        done = False
        for p, i in (shape_paths(owner, key) if kind == "SHAPE" else input_paths(owner, key)):
            try:
                if owner.keyframe_insert(p, index=i, keytype=keytype):
                    graph_key_menu.after_insert(owner, p, i, bpy.context.scene.frame_current)
                    done = True
            except (TypeError, RuntimeError):
                pass
        return done
    from ..operators import anim_layers
    if isinstance(ob, bpy.types.Object) and anim_layers.has_layers(ob):
        # Maya animation layers: the key goes to the selected layer, solved so the result is the value
        return anim_layers.key(ob, path, idx)
    if is_bone(ob) and anim_layers.has_layers(ob.id_data):
        # a joint of a layered armature (Blender's keying refuses NLA-stacked data)
        return anim_layers.key_pose_bone(ob, path, idx)
    ok = ob.keyframe_insert(path, index=idx, keytype=keytype)
    if ok:      # Maya Tangents > Default In / Out Tangent
        from ..operators import graph_key_menu
        graph_key_menu.after_insert(ob, path, idx, bpy.context.scene.frame_current)
    return ok


# --- animation state ---------------------------------------------------------------------

def _fcurves(ob):
    from .. import compat
    return compat.id_fcurve_collection(ob.id_data)


def shape_fcurves(ob, key):
    owner = shape_owner(ob, key)
    if owner is None:
        return []
    fcs = compat.id_fcurve_collection(owner)
    if fcs is None:
        return []
    out = []
    for p, i in shape_paths(owner, key):
        fc = fcs.find(p, index=max(i, 0))
        if fc is not None:
            out.append(fc)
    return out


def input_fcurves(ob, key):
    owner = input_owner(ob, key)
    fcs = _fcurves(ob) if owner is not None else None
    if fcs is None:
        return []
    out = []
    for p, i in input_paths(owner, key):
        fc = fcs.find(owner.path_from_id(p), index=max(i, 0))
        if fc is not None:
            out.append(fc)
    return out


def blend_fcurves(ob, key):
    kb = blend_target(ob, key)
    fcs = compat.id_fcurve_collection(kb.id_data) if kb is not None else None
    fc = fcs.find(blend_path(kb.name)) if fcs is not None else None
    return [fc] if fc is not None else []


def fcurve(ob, key):
    if is_history_key(key) or key.startswith(MODEL_PREFIX):
        return None
    if is_blend_key(key):
        fcs = blend_fcurves(ob, key)
        return fcs[0] if fcs else None
    if is_shape_key(key):
        fcs = shape_fcurves(ob, key)
        return fcs[0] if fcs else None
    if is_input_key(key):
        fcs = input_fcurves(ob, key)
        return fcs[0] if fcs else None
    fcs = _fcurves(ob)
    if fcs is None:
        return None
    path, idx, kind = channel_path(key)
    if _non_euler_rot(ob, kind):
        from .. import rotation_display
        path = full_path(ob, rotation_display.curve_path(ob))
        return None if path is None else next((fc for i in range(4) for fc in [fcs.find(path, index=i)] if fc), None)
    path = full_path(ob, path)
    return None if path is None else fcs.find(path, index=max(idx, 0))


def channel_fcurves(ob, key):
    """Every F-curve behind a channel (a SHAPES channel can have several: spot Cone Angle = size + blend)."""
    if is_shape_key(key):
        return shape_fcurves(ob, key)
    if is_input_key(key):
        return input_fcurves(ob, key)
    if is_blend_key(key):
        return blend_fcurves(ob, key)
    if is_history_key(key) or key.startswith(MODEL_PREFIX):
        return []
    if _non_euler_rot(ob, MAIN_BY_KEY.get(key, ("", "", "", 0, ""))[4]):
        from .. import rotation_display
        fcs, path = _fcurves(ob), full_path(ob, rotation_display.curve_path(ob))
        return [fc for i in range(4) for fc in [fcs.find(path, index=i) if fcs is not None and path else None] if fc]
    fc = fcurve(ob, key)
    return [fc] if fc is not None else []


def remove_channel_curves(ob, key):
    """Delete the channel's animation curves (Maya cutKey -clear on the whole curve). True if any."""
    owner = curve_owner(ob, key)
    fcs = compat.id_fcurve_collection(owner) if owner is not None else None
    curves = channel_fcurves(ob, key)
    for fc in curves:
        fcs.remove(fc)
    return bool(curves)


def driver(ob, key):
    if is_shape_key(key) or is_history_key(key) or key.startswith(MODEL_PREFIX):
        return None
    if is_blend_key(key):
        kb = blend_target(ob, key)
        ad = kb.id_data.animation_data if kb is not None else None
        return ad.drivers.find(blend_path(kb.name)) if ad is not None else None
    if is_input_key(key):
        owner = input_owner(ob, key)
        ad = ob.animation_data if owner is not None else None
        if ad is None:
            return None
        return next((d for p, i in input_paths(owner, key)
                     for d in [ad.drivers.find(owner.path_from_id(p), index=max(i, 0))] if d is not None), None)
    ad = ob.id_data.animation_data
    if ad is None:
        return None
    path, idx, _kind = channel_path(key)
    path = full_path(ob, path)
    return None if path is None else ad.drivers.find(path, index=max(idx, 0))


def channel_state(ob, key, frame=None):
    """'DRIVEN', 'MUTED', 'LAYERED', 'KEYED' (key on this frame), 'ANIMATED' or None (Maya
    muted = brown: Blender's UI has no brown, the mute icon marks it). A channel in an animation
    layer above BaseAnimation is teal #4db6ac in every layer state, keyed or not
    (Maya); the other channels of a layered object show their BaseAnimation keys."""
    if driver(ob, key) is not None:
        return 'DRIVEN'
    fc = fcurve(ob, key)
    if is_blend_key(key):
        from ..operators import anim_layers
        kb = blend_target(ob, key)
        if kb is not None and anim_layers.has_layers(kb.id_data):
            path = blend_path(kb.name)
            if anim_layers.member_of_layer(kb.id_data, path, -1):
                return 'LAYERED'
            fc = anim_layers.base_curve(kb.id_data, path, -1)
    if (not is_shape_key(key) and not is_input_key(key) and not is_history_key(key) and not is_blend_key(key)
            and (isinstance(ob, bpy.types.Object) or is_bone(ob))):
        from ..operators import anim_layers
        id_ob = ob.id_data
        if anim_layers.has_layers(id_ob):
            path, idx, _kind = channel_path(key)
            path = full_path(ob, path) if path is not None else None
            if path is not None:
                if anim_layers.member_of_layer(id_ob, path, idx):
                    return 'LAYERED'
                fc = anim_layers.base_curve(id_ob, path, idx)
    if fc is None:
        return None
    if fc.mute:
        return 'MUTED'
    frame = bpy.context.scene.frame_current if frame is None else frame
    if any(abs(kp.co[0] - frame) < 0.5 for kp in fc.keyframe_points):
        return 'KEYED'
    return 'ANIMATED'


# --- channel selection (WindowManager string; not undoable) -----------------------------------

def selected_channels(context=None):
    wm = (context or bpy.context).window_manager
    return [s for s in wm.allset_cb_selected.split(",") if s]


def set_selected_channels(keys, context=None):
    wm = (context or bpy.context).window_manager
    wm.allset_cb_selected = ",".join(dict.fromkeys(keys))
    if keys:
        arm_slider(context)
    else:
        disarm_slider()
    from . import cb_channels       # Sync Selection in Graph Editor
    cb_channels.after_selection(context or bpy.context)


# Like Maya, picking channels makes a middle drag in a view change them until another tool is picked (Q / W / E /
# R, the toolbar): the channels stay highlighted, and the middle drag is that tool's own again.
_slider = {"armed": False, "tool": None}


def _view3d_tool(context=None):
    context = context or bpy.context
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except (AttributeError, RuntimeError, TypeError):
        return None
    return tool.idname if tool is not None else None


def arm_slider(context=None):
    from . import in_view_editor
    in_view_editor.disarm_window(context or bpy.context)
    _slider["armed"] = True
    _slider["tool"] = _view3d_tool(context)


def disarm_slider():
    _slider["armed"] = False


def slider_armed(context=None):
    """A middle drag in a view drives the selected channels: channels were picked since the last tool change."""
    from .. import preferences
    return (_slider["armed"] and _view3d_tool(context) == _slider["tool"]
            and preferences.get(context or bpy.context).cb_manipulators != 'NONE')


def select_channel(key, mode="SET", context=None):
    """mode: SET (click), TOGGLE (Ctrl), EXTEND (Shift)."""
    sel = selected_channels(context)
    if mode == "SET":
        sel = [key]
    elif mode == "TOGGLE":
        sel = [k for k in sel if k != key] if key in sel else sel + [key]
    else:
        sel = sel + [key]
    set_selected_channels(sel, context)
    return sel


# --- channel ranges (drag over the rows, #6) -------------------------------------------------------------------

def drawn_keys(ob):
    """Channel keys in the order the Channel Box draws them (main channels, custom attributes, SHAPES rows)."""
    keys = [c[0] for c in MAIN if not is_hidden(ob, c[0]) and has_channel(ob, c[0])]
    keys += [CUSTOM_PREFIX + n for n in custom_keys(ob) if not is_hidden(ob, CUSTOM_PREFIX + n)]
    keys += [SHAPE_PREFIX + n for n in SHAPE_PROPS.get(getattr(ob, "type", ""), ())
             if has_channel(ob, SHAPE_PREFIX + n) and not is_hidden(ob, SHAPE_PREFIX + n)]
    scene = bpy.context.scene
    rows = scene.allset_cb.rows if scene is not None and hasattr(scene, "allset_cb") else ()
    keys += history_keys(ob)
    keys += [k for r in rows if r.kind in ("INPUT", "BLEND") for k in [row_key(r)] if has_channel(ob, k)]
    return keys


def history_keys(ob):
    """Channel keys of the creation node's attributes while its INPUTS node is open (Channel Box order)."""
    if not isinstance(ob, bpy.types.Object):
        return []
    from ..operators import prim_history
    _owner, node = prim_history.node_of(ob)
    if node is None or not is_open(ob, history_node(node["name"])):
        return []
    from . import creation_inputs
    return [HISTORY_PREFIX + n for n in creation_inputs.node_rows(node["type"])]


def channel_range(ob, first, last):
    """The drawn channels from ``first`` to ``last`` (either order), top to bottom."""
    keys = drawn_keys(ob)
    if first not in keys or last not in keys:
        return [k for k in (first, last) if k in keys]
    i, j = sorted((keys.index(first), keys.index(last)))
    return keys[i:j + 1]


def select_range(ob, first, last, mode="SET", base=None, context=None):
    """Select the rows ``first``..``last``: SET replaces the selection, ADD adds to ``base`` (default: the current
    selection). Maya: drag over channel names / fields selects a range, Ctrl+drag adds."""
    rng = channel_range(ob, first, last)
    if mode == "SET":
        sel = rng
    else:
        sel = list(selected_channels(context) if base is None else base) + rng
    set_selected_channels(sel, context)
    return selected_channels(context)


def _sel_get(key):
    def get(_self):
        return key in selected_channels()
    return get


def _sel_set(key):
    def set_(_self, value):
        sel = [k for k in selected_channels() if k != key]
        set_selected_channels(sel + [key] if value else sel)
    return set_


def cell_key(path, scene=None):
    """(channel key, "NAME" / "VALUE") of a Channel Box cell from its data path (``context.property``), or None."""
    import re
    m = re.match(r"^allset_cb\.([a-z]+)_(text|sel)$", path or "")
    if m and m.group(1) in MAIN_BY_KEY:
        return m.group(1), ("VALUE" if m.group(2) == "text" else "NAME")
    m = re.match(r"^allset_creation\.([A-Za-z0-9]+)_(text|sel)$", path or "")
    if m:
        return HISTORY_PREFIX + m.group(1), ("VALUE" if m.group(2) == "text" else "NAME")
    m = re.match(r"^allset_cb\.rows\[(\d+)\]\.(text|sel)$", path or "")
    if m and scene is not None:
        rows = scene.allset_cb.rows
        i = int(m.group(1))
        if i < len(rows) and rows[i].kind in ("CUSTOM", "SHAPE", "INPUT", "BLEND"):
            return row_key(rows[i]), ("VALUE" if m.group(2) == "text" else "NAME")
    return None


# --- proxies -------------------------------------------------------------------------------------

def _proxy_get(key):
    def get(_self):
        ob = lead()
        if ob is None or not has_channel(ob, key):
            return False if MAIN_BY_KEY[key][4] == "VIS" else 0.0
        return get_value(ob, key)
    return get


def _proxy_set(key):
    def set_(_self, value):
        context = bpy.context
        autokey = auto_key.enabled(context.scene)
        for ob in targets(context):
            if not has_channel(ob, key) or is_locked(ob, key):
                continue
            set_value(ob, key, value)
            if autokey and auto_keys(ob, key, context):
                keyframe(ob, key)
    return set_


def auto_keys(ob, key, context=None):
    """Auto Key keys this channel: keyable and (Maya) already keyed (the kit's own Auto Key,
    operators/auto_key.py)."""
    if not is_keyable(ob, key):
        return False
    return fcurve(ob, key) is not None


# --- text entry ------------------------------------------------------------------

_KIND_ENTRY = {"LOC": "LENGTH", "ROT": "ROTATION", "SCALE": "NONE", "VIS": "BOOL"}


def entry_kind(ob, key):
    if key.startswith(MODEL_PREFIX):
        node = model_node(ob, key)
        return node.spec.kinds[key.rsplit(':', 1)[1]] if node is not None else None
    if key.startswith(CUSTOM_PREFIX):
        return cb_entry.kind_of_value(ob.get(key[len(CUSTOM_PREFIX):]))
    if is_shape_key(key):
        return _row_kind(shape_owner(ob, key), "SHAPE", key[len(SHAPE_PREFIX):])
    if is_input_key(key):
        return _row_kind(input_owner(ob, key), "INPUT", input_parts(key)[2])
    if is_history_key(key):
        from ..operators import prim_history
        _owner, node = history_node_of(ob, key)
        kind = prim_history.entry_kind(node["type"], key[len(HISTORY_PREFIX):])
        return kind
    if is_blend_key(key):
        return "NONE"
    return _KIND_ENTRY[MAIN_BY_KEY[key][4]]


def entry_keys(key, context=None):
    """The edited channel, or every selected channel when it is one of them."""
    sel = selected_channels(context)
    return sel if key in sel else [key]


def apply_entry(key, text, context=None):
    """Typed text on channel ``key``: absolute or relative (``+=``...) per object, on every
    selected object that has the channel; returns how many values changed."""
    context = context or bpy.context
    scene = context.scene
    autokey = auto_key.enabled(scene)
    entries = []
    models = {}
    histories = {}
    history_fields = set()
    for k in entry_keys(key, context):
        for ob in targets(context):
            if not has_channel(ob, k) or is_locked(ob, k):
                continue
            kind = entry_kind(ob, k)
            if kind is None:
                continue
            try:
                if k.startswith(MODEL_PREFIX):
                    from . import node_attributes
                    node = model_node(ob, k)
                    field = k.rsplit(':', 1)[1]
                    if not node_attributes.editable(node, field):
                        continue
                    value = node_attributes.parse_value(node, field, text, scene)
                    if ob not in models:
                        models[ob] = node, dict(node.params)
                    models[ob][1][field] = value
                elif is_history_key(k):
                    from . import node_attributes
                    owner, history = history_node_of(ob, k)
                    field = k[len(HISTORY_PREFIX):]
                    pair = owner.as_pointer(), field
                    if pair in history_fields:
                        continue
                    history_fields.add(pair)
                    node = node_attributes.PrimitiveNode(ob, owner, history)
                    value = node_attributes.parse_value(node, field, text, scene)
                    if value == node.params[field]:
                        continue
                    if pair[0] not in histories:
                        histories[pair[0]] = node, dict(node.params)
                    histories[pair[0]][1][field] = value
                else:
                    value = cb_entry.parse_entry(text, get_value(ob, k), kind, scene)
            except (ValueError, TypeError, SyntaxError):
                return 0
            entries.append((ob, k, value))
    for ob, k, value in entries:
        if k.startswith(MODEL_PREFIX) or is_history_key(k):
            for hook in WRITE_HOOKS:
                hook(ob, k)
        else:
            set_value(ob, k, value)
        if autokey and auto_keys(ob, k, context):
            keyframe(ob, k)
    for node, params in (*models.values(), *histories.values()):
        try:
            node.commit(context, params)
        finally:
            node.finish()
    return len(entries)


def _text_get(key):
    def get(_self):
        ob = lead()
        if ob is None or not has_channel(ob, key):
            return ""
        return cb_entry.format_value(get_value(ob, key), entry_kind(ob, key), bpy.context.scene)
    return get


def _text_set(key):
    def set_(_self, text):
        apply_entry(key, text)
    return set_


# --- rows for custom attributes, SHAPES and INPUTS --------------------------------

def _inputs(ob):
    # + the kit deformers a lattice / handle drives: Maya shows ffd1 / bend1 in the INPUTS of ffd1Lattice /
    # bend1Handle
    from ..operators import deformers, skin_method, skin_tools_199, type_manip
    return [m for m in getattr(ob, "modifiers", ()) if not display.is_preview(m) and not deformers.is_base(m)
            and not skin_tools_199.is_part(m) and not skin_method.is_part(m) and not type_manip.is_part(m)] \
        + deformers.driven_modifiers(ob)


def _virtual(owner, name):
    """The Maya attribute behind an INPUTS row ``maya:<key>`` of a kit deformer (operators/deformers.ATTRS), or a
    SHAPES row of a light (Color R / G / B, operators/lights.channel_attrs)."""
    if not name.startswith("maya:"):
        return None
    if isinstance(owner, bpy.types.Light):
        from ..operators import lights
        return lights.channel_attr(name, owner)
    if not isinstance(owner, bpy.types.Modifier):
        return None
    from ..operators import deformers
    return deformers.attr(owner, name)


def input_label(mod, name):
    """Channel Box label of INPUTS row ``name`` of modifier ``mod`` (a Maya attribute, else the RNA name)."""
    v = _virtual(mod, name)
    if v is not None:
        return v.label
    rna = mod.bl_rna.properties.get(name)
    return rna.name if rna is not None else name


# Maya shape attribute labels of SHAPES rows (ffd1LatticeShape: S / T / U Divisions)
SHAPE_LABELS = {('LATTICE', "points_u"): "S Divisions", ('LATTICE', "points_w"): "T Divisions",
                ('LATTICE', "points_v"): "U Divisions"}


def shape_label(ob, prop):
    label = SHAPE_LABELS.get((ob.type, prop))
    v = _virtual(ob.data, prop)
    if label is None and v is not None:
        label = v.label
    if label is None:
        rna = ob.data.bl_rna.properties.get(prop)
        label = rna.name if rna is not None else prop
    return label


# --- INPUTS node expansion (#55) -------------------------------------------------------------------------
# Maya 2022: every INPUTS node starts collapsed (polyCube1, polyExtrudeFace1), a click on
# its name shows its attributes under it and a second click hides them; a new lead shows every node collapsed again,
# also when the earlier lead comes back. This is UI state, not scene data: kept in Python (never
# Blender's ``Modifier.show_expanded``, which is the Properties editor's panel state, saved and undone), not undone,
# not saved.

_open = {"lead": None, "nodes": set()}


def lead_key(ob):
    if ob is None:
        return None
    if is_bone(ob):
        return ("BONE", ob.id_data.name, ob.name)
    return ("OB", ob.name)


def open_nodes(ob):
    """The expanded INPUTS node keys of lead ``ob`` (emptied when the lead changed, Maya's behaviour)."""
    key = lead_key(ob)
    if key != _open["lead"]:
        _open["lead"] = key
        _open["nodes"] = set()
        _scroll.clear()
    return _open["nodes"]


def is_open(ob, node):
    return node in open_nodes(ob)


def set_open(ob, node, state=True):
    nodes = open_nodes(ob)
    if state:
        nodes.add(node)
    else:
        nodes.discard(node)


def mod_node(mod):
    return "mod:" + mod.name


def history_node(name):
    """A Maya history node drawn by the kit (creation node polyCube1, extrusion polyExtrudeFace1)."""
    return "node:" + name


def con_node(node, con):
    return "con:" + constraint_node_name(node, con)


def reset_open():
    _open["lead"] = None
    _open["nodes"] = set()
    _scroll.clear()


# --- constraints = Maya constraint nodes ------------------------------------------------
# Maya names them like pCube1_parentConstraint1, weight locator1W0.

MAYA_CONSTRAINT = {'CHILD_OF': "parentConstraint", 'COPY_TRANSFORMS': "parentConstraint",
                   'COPY_LOCATION': "pointConstraint", 'COPY_ROTATION': "orientConstraint",
                   'COPY_SCALE': "scaleConstraint", 'TRACK_TO': "aimConstraint",
                   'DAMPED_TRACK': "aimConstraint", 'LOCKED_TRACK': "aimConstraint"}
_AIM = ('TRACK_TO', 'DAMPED_TRACK', 'LOCKED_TRACK')


def constraints(node):
    """Constraints shown as INPUTS nodes (Limit constraints are Maya transform limits: AE only)."""
    from ..operators import constrain_interp, ik_rp, rig_tools, skin_follow
    # a group blend / Object up turn is part of its Maya node; the kit's 3+ bone RP solve belongs
    # to the IK handle; a skin's follow of its skeleton is part of the skin
    return [c for c in getattr(node, "constraints", ()) if not c.type.startswith("LIMIT_")
            and not constrain_interp.is_blend(c) and not rig_tools.is_up_companion(c)
            and not ik_rp.is_solver_constraint(c) and not skin_follow.is_follow(c)]


def constraint_enabled(con):
    en = getattr(con, "enabled", None)
    return (not con.mute) if en is None else bool(en)


def _nth_constraint(node, con):
    return [c for c in constraints(node) if c.type == con.type].index(con)


def maya_constraint_type(con, default=None):
    """Maya node type of a kit constraint: normal / tangent constraints are a Track To on a helper (
    operators/constrain_199.maya_type), UV / Proximity Pins a Copy Transforms on a helper (
    operators/pins_205.pin_type), a kit multi-target group its own type (a parent group's Copy Location / Rotation,
    operators/constrain_multi.py), the rest by Blender type."""
    from ..operators import constrain_multi
    grouped = constrain_multi.group_type(con)
    if grouped is not None:
        return grouped
    if con.type == 'COPY_TRANSFORMS':
        from ..operators import pins_205
        kind = pins_205.pin_type(con)
        if kind is not None:
            return kind
    if con.type in _AIM:
        from ..operators import constrain_199
        kind = constrain_199.maya_type(con)
        if kind in ("normal", "tangent"):
            return f"{kind}Constraint"
    return MAYA_CONSTRAINT.get(con.type, default)


def constraint_node_name(node, con):
    """Maya's name for the constraint node: ``<node>_<type><n>`` (pCube1_parentConstraint1)."""
    from ..operators import constrain_multi
    con = constrain_multi.head_of(con, node)     # a hidden blend / Object up turn = its node
    mtype = maya_constraint_type(con)
    if mtype is None:
        return con.name
    from ..operators import pins_205
    pin = pins_205.node_name(con)          # a pin node keeps its own name (uvPin1)
    if pin is not None:
        return pin
    from ..operators import constrain_multi
    # a multi-target group is one Maya node: count group heads, name every member like its head
    head = constrain_multi.head_of(con, node)
    same = [c for c in constraints(node) if constrain_multi.is_head(c, node) and maya_constraint_type(c) == mtype]
    return f"{node.name}_{mtype}{same.index(head) + 1}"


def weight_name(con):
    """Maya target weight attribute: ``<target>W0`` (one target per Blender constraint; normal / tangent
    constraints name their surface / curve; a member of a kit multi-target group = ``<target>W<i>``)."""
    from ..operators import constrain_199, constrain_multi, pins_205
    mb = constrain_multi.member(con)
    if mb is not None:
        return f"{mb.label}W{mb.index}"
    geometry = pins_205.geometry_of(con)   # UV / Proximity Pin: the pinned-to geometry
    if geometry is not None:
        return f"{geometry.name}W0"
    surface, _sub = constrain_199.maya_target(con)
    if surface is not None and surface is not getattr(con, "target", None):
        return f"{surface.name}W0"
    target = getattr(con, "target", None)
    if target is None:
        return "W0"
    sub = getattr(con, "subtarget", "")
    return f"{sub if target.type == 'ARMATURE' and sub else target.name}W0"


def _axes(con, pattern):
    return [a for a in "xyz" if getattr(con, pattern.format(a), True)]


def constrained_keys(node):
    """Channel keys an enabled constraint drives (Maya draws them blue)."""
    out = set()
    for con in constraints(node):
        if not constraint_enabled(con):
            continue
        t = con.type
        if t == 'CHILD_OF':
            for k, pattern in (("t", "use_location_{}"), ("r", "use_rotation_{}"), ("s", "use_scale_{}")):
                out.update(k + a for a in _axes(con, pattern))
        elif t in ('COPY_TRANSFORMS', 'ARMATURE'):
            out.update(k for k in MAIN_BY_KEY if k != "v")
        elif t == 'COPY_LOCATION':
            out.update("t" + a for a in _axes(con, "use_{}"))
        elif t == 'COPY_ROTATION':
            out.update("r" + a for a in _axes(con, "use_{}"))
        elif t == 'COPY_SCALE':
            out.update("s" + a for a in _axes(con, "use_{}"))
        elif t in _AIM:
            out.update(("rx", "ry", "rz"))
    return out


def _nth_of_type(ob, mod):
    return [m for m in _inputs(ob) if m.type == mod.type].index(mod)


def row_owner(ob, kind, name, mod_type="", nth=0, lead_ob=None):
    """The struct holding row ``name`` on ``ob`` (None: ob has no such channel).

    Same-named channel: custom = same property name,
    SHAPE = same object type and data property, INPUT = same modifier type at the same
    position among that type."""
    if kind == "CUSTOM":
        return ob if name in ob.keys() else None
    if kind == "BLEND":
        return blend_target(ob, BLEND_PREFIX + name)
    if kind == "SHAPE":
        data = getattr(ob, "data", None)
        if data is None or (lead_ob is not None and ob.type != lead_ob.type):
            return None
        return data if name in data.bl_rna.properties or _virtual(data, name) is not None else None
    if kind == "INPUT":
        mods = [m for m in _inputs(ob) if m.type == mod_type]
        if nth < len(mods) and (name in mods[nth].bl_rna.properties or _virtual(mods[nth], name) is not None):
            return mods[nth]
    if kind == "CONSTRAINT":
        cons = [c for c in constraints(ob) if c.type == mod_type]
        if nth < len(cons) and name in cons[nth].bl_rna.properties:
            return cons[nth]
    return None


def _row_kind(owner, kind, name):
    if kind == "CUSTOM":
        return cb_entry.kind_of_value(owner.get(name))
    if kind == "BLEND":
        return "NONE"
    v = _virtual(owner, name)
    if v is not None:
        return v.kind
    return cb_entry.kind_of_rna(owner.bl_rna.properties[name])


def _row_read(owner, kind, name):
    if kind == "CUSTOM":
        return owner[name]
    if kind == "BLEND":
        return owner.value
    v = _virtual(owner, name)
    return v.get(owner) if v is not None else getattr(owner, name)


def _row_write(owner, kind, name, value):
    if kind == "CUSTOM":
        owner[name] = type(owner[name])(value)
        return
    if kind == "BLEND":
        owner.value = value
        return
    v = _virtual(owner, name)
    if v is not None:
        v.set(owner, value)
    else:
        setattr(owner, name, value)


def _row_get(self):
    ob = lead()
    if ob is None:
        return ""
    owner = row_owner(ob, self.kind, self.name, self.mod_type, self.nth)
    if owner is None:
        return ""
    entry = _row_kind(owner, self.kind, self.name)
    return cb_entry.format_value(_row_read(owner, self.kind, self.name), entry, bpy.context.scene)


def apply_row_entry(row, text, context=None):
    """Typed text on a custom / SHAPES / INPUTS row: every selected object with that channel."""
    context = context or bpy.context
    if row.kind == "CUSTOM":
        return apply_entry(CUSTOM_PREFIX + row.name, text, context)
    ld = lead(context)
    count = 0
    for ob in targets(context):
        owner = row_owner(ob, row.kind, row.name, row.mod_type, row.nth, ld)
        if owner is None:
            continue
        entry = _row_kind(owner, row.kind, row.name)
        try:
            value = cb_entry.parse_entry(text, _row_read(owner, row.kind, row.name), entry,
                                         context.scene)
        except (ValueError, TypeError, SyntaxError):
            return count
        try:
            _row_write(owner, row.kind, row.name, value)
        except (TypeError, ValueError, AttributeError):
            continue
        count += 1
    return count


def _row_set(self, text):
    apply_row_entry(self, text)


def _row_sel_get(self):
    key = row_key(self)
    return key is not None and key in selected_channels()


def _row_sel_set(self, value):
    key = row_key(self)
    if key is not None:
        _sel_set(key)(self, value)


class ALLSET_PG_cb_row(bpy.types.PropertyGroup):
    kind: StringProperty()        # CUSTOM / SHAPE / INPUT / CONSTRAINT / BLEND
    name: StringProperty()        # property name (BLEND: the blendShape target's name)
    mod_type: StringProperty()    # INPUT: modifier type, CONSTRAINT: constraint type
    nth: IntProperty()            # position among the lead's modifiers / constraints of that type
    text: StringProperty(get=_row_get, set=_row_set)
    sel: BoolProperty(name="Selected", get=_row_sel_get, set=_row_sel_set,
                      description="Select this channel: click, Ctrl toggle, Shift range, drag over the rows")


# --- the name line: click to rename (#283) ---------------------------------------------------------------

def rename_lead(ob, text):
    """Maya Channel Box name field: rename the lead (spaces -> "_", Maya's name rule; a taken name gets the next
    number of its base, the shape follows like Maya's rename). Returns the new name, None when nothing changed."""
    from . import input_line
    name = input_line.clean_name(text)
    if name is None:
        input_line._say(f"Rename: \"{text.strip()}\" is not a valid name (letters, digits and _, "
                        "not starting with a digit).")
        return None
    if name == ob.name:
        return None
    if is_bone(ob):
        ob.name = name
        return ob.name
    from ..operators import naming
    taken = {o.name for o in bpy.data.objects if o != ob}
    if name in taken:       # a taken name: its base with one more than the highest number (pCube1 -> pCube2)
        base = naming.base_name(name)
        name = f"{base}{naming.next_number(base, taken)}"
    new = name
    ob.name = new
    data = ob.data
    if data is not None and data.users == 1 and hasattr(data, "name") and data.library is None:
        data.name = input_line.shape_name(new)
    return new


def _lead_name_get(_self):
    ob = lead()
    return ob.name if ob is not None else ""


def _lead_name_set(_self, value):
    ob = lead()
    if ob is not None and rename_lead(ob, value) is not None:
        _redraw_all()


def _redraw_all():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


class ALLSET_PT_cb_name(bpy.types.Panel):
    """The Channel Box name editor popover (called by allset.cb_rename only)"""
    bl_space_type = 'TOPBAR'   # dummy, like Blender's TOPBAR_PT_name (F2): only shown through wm.call_panel
    bl_region_type = 'HEADER'
    bl_label = "Rename"
    bl_ui_units_x = 8

    def draw(self, context):
        ob = lead(context)
        if ob is None:
            return
        row = self.layout.row()
        row.activate_init = True
        if component_mode(ob):
            row.prop(ob.data, "name", text="")
        else:
            row.prop(context.scene.allset_cb, "lead_name", text="")


class ALLSET_OT_cb_rename(bpy.types.Operator):
    """Rename this node (click the name, type, Enter)"""
    bl_idname = "allset.cb_rename"
    bl_label = "Rename"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return lead(context) is not None

    def invoke(self, context, event):
        bpy.ops.wm.call_panel(name=ALLSET_PT_cb_name.__name__, keep_open=False)
        return {'FINISHED'}

    def execute(self, context):
        return self.invoke(context, None)


def _make_proxy_annotations():
    ann = {}
    for key, label, _path, _idx, kind in MAIN:
        if kind == "VIS":
            ann[key] = BoolProperty(name=label, get=_proxy_get(key), set=_proxy_set(key))
        elif kind == "LOC":
            ann[key] = FloatProperty(name=label, get=_proxy_get(key), set=_proxy_set(key),
                                     subtype='DISTANCE', unit='LENGTH', precision=3, step=10)
        elif kind == "ROT":
            ann[key] = FloatProperty(name=label, get=_proxy_get(key), set=_proxy_set(key),
                                     subtype='ANGLE', unit='ROTATION', precision=3)
        else:
            ann[key] = FloatProperty(name=label, get=_proxy_get(key), set=_proxy_set(key),
                                     precision=3, step=10)
        ann[key + "_text"] = StringProperty(name=label, get=_text_get(key), set=_text_set(key))
        ann[key + "_sel"] = BoolProperty(name=label, get=_sel_get(key), set=_sel_set(key),
                                         description="Select this channel: click, Ctrl toggle, Shift range, "
                                                     "drag over the rows")
    ann["lead_name"] = StringProperty(name="Name", get=_lead_name_get, set=_lead_name_set,
                                      description="The lead's name: Enter renames it")
    ann["rows"] = CollectionProperty(type=ALLSET_PG_cb_row)
    ann["rows_sig"] = StringProperty(options={'HIDDEN'})
    return ann


ALLSET_PG_channel_box = type("ALLSET_PG_channel_box", (bpy.types.PropertyGroup,),
                              {"__annotations__": _make_proxy_annotations()})


# --- MMB virtual slider ---------------------------------------------------------------------------

def slider_delta(dx, kind, speed=1.0, ctrl=False, shift=False, hyperbolic=False):
    from . import attribute_edit
    return attribute_edit.delta(dx, SLIDER_STEP[kind], speed, ctrl, shift, hyperbolic)


def slider_targets(context):
    """[(object, key)] the slider would change: selected numeric channels on targets."""
    out = []
    for key in selected_channels(context):
        if key in MAIN_BY_KEY and MAIN_BY_KEY[key][4] == "VIS":
            continue
        for ob in targets(context):
            if has_channel(ob, key) and not is_locked(ob, key) and not is_hidden(ob, key):
                value = get_value(ob, key)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                if entry_kind(ob, key) in {None, 'ENUM'}:
                    continue     # an enum attribute (Maya's slider skips it)
                if key.startswith(MODEL_PREFIX):
                    from . import node_attributes
                    if not node_attributes.editable(model_node(ob, key), key.rsplit(':', 1)[1]):
                        continue
                out.append((ob, key))
    return out


def drag_limit(ob, key, value):
    """A dragged INPUTS value stays in the property's soft range, like Blender's own field drag (a Subdivision's
    Levels stops at 6; typing can go to the hard limit)."""
    if key.startswith(MODEL_PREFIX):
        node = model_node(ob, key)
        return node.descriptor(key.rsplit(':', 1)[1], soft=True).limit(value)
    if not is_input_key(key):
        return value
    owner = input_owner(ob, key)
    rna = owner.bl_rna.properties.get(input_parts(key)[2]) if owner is not None else None
    if rna is None or rna.type not in {'INT', 'FLOAT'}:
        return value
    return max(rna.soft_min, min(rna.soft_max, value))


ROT_DEG_PER_PX = 0.36     # a selected rotate channel turns 0.36 degrees per px, right / down = more (like Maya)
AXIS_MIN_SHARE = 0.15     # an axis seen nearly end-on (shorter than this share of the longest) drags sideways


def node_axes(ob, key):
    """(world origin, world direction moved by one unit of the translate channel ``key``) of an object or pose
    bone, None for other channels."""
    path, index, kind = channel_path(key) if key in MAIN_BY_KEY else (None, -1, None)
    if kind != "LOC" or index < 0:
        return None
    from mathutils import Vector
    if isinstance(ob, bpy.types.PoseBone):
        arm = ob.id_data
        world = arm.matrix_world @ ob.matrix
        basis = ob.matrix_basis
    else:
        world, basis = ob.matrix_world, ob.matrix_basis
    try:
        parent = world.to_3x3() @ basis.to_3x3().inverted()
    except ValueError:
        return None
    axis = Vector((0.0, 0.0, 0.0))
    axis[index] = 1.0
    return world.translation.copy(), parent @ axis


def screen_axis(region, rv3d, origin, direction):
    """Region px moved per unit along ``direction`` at ``origin`` (None when it can't be projected)."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    eps = 1e-3
    a = location_3d_to_region_2d(region, rv3d, origin)
    b = location_3d_to_region_2d(region, rv3d, origin + direction * eps)
    if a is None or b is None:
        return None
    return (b - a) / eps


def projected_delta(axis_px, dx, dy):
    """Units along an axis for a mouse move (dx, dy): the move projected on the axis as drawn, like dragging that
    axis of the Move manipulator (vertical moves count)."""
    ax, ay = axis_px
    n = ax * ax + ay * ay
    return (dx * ax + dy * ay) / n if n > 0.0 else 0.0


def rotate_delta(dx, dy):
    """Radians for a mouse move on a selected rotate channel: right and down turn it up, left and up down."""
    return math.radians(ROT_DEG_PER_PX) * (dx - dy)


def slider_apply(starts, dx, speed=1.0, ctrl=False, shift=False, hyperbolic=False):
    """starts: {(ob, key): start value}. Sets each to start + delta."""
    for (ob, key), start in starts.items():
        kind = channel_path(key)[2]
        set_value(ob, key, drag_limit(ob, key, start + slider_delta(dx, kind, speed, ctrl, shift, hyperbolic)))


def _unit_dirs(direction):
    """``direction`` and two directions of the same length square to it (to tell an end-on axis)."""
    from mathutils import Vector
    n = direction.normalized()
    side = n.orthogonal().normalized()
    return [direction, side * direction.length, n.cross(side) * direction.length]


class ALLSET_OT_cb_virtual_slider(bpy.types.Operator):
    """MMB-drag in the viewport changes the channels selected in the Channel Box"""
    bl_idname = "allset.cb_virtual_slider"
    bl_label = "Channel Box Virtual Slider"
    bl_options = {'REGISTER', 'GRAB_CURSOR', 'BLOCKING'}

    def invoke(self, context, event):
        from . import attribute_edit
        from .. import preferences
        if (_slider['armed'] and _view3d_tool(context) == _slider['tool']
                and preferences.get(context).cb_manipulators == 'NONE'):
            return {'CANCELLED'}
        if context.mode not in {'OBJECT', 'POSE', 'EDIT_MESH'} or not slider_armed(context):
            return {'PASS_THROUGH'}
        pairs = slider_targets(context)
        if context.mode == 'EDIT_MESH':
            pairs = [(ob, key) for ob, key in pairs if key.startswith(MODEL_PREFIX)]
        if not pairs or attribute_edit.busy(context):
            return {'PASS_THROUGH'}
        self._starts = {(ob, key): get_value(ob, key) for ob, key in pairs}
        self._nodes = {ob: model_node(ob, key) for ob, key in pairs if key.startswith(MODEL_PREFIX)}
        self._node_starts = {ob: dict(node.params) for ob, node in self._nodes.items()}
        self._drags = {}
        self._axes = {}
        self._dx = self._dy = 0
        self._last = event.mouse_x, event.mouse_y
        self._scene, self._frame = context.scene, context.scene.frame_current
        self._object = context.active_object
        self._window = context.window.as_pointer()
        self._mode = context.mode
        self._tool = _view3d_tool(context)
        region, rv3d = context.region, context.region_data
        for ob, key in pairs:
            kind = channel_path(key)[2]
            if key.startswith(MODEL_PREFIX):
                descriptor = self._nodes[ob].descriptor(channel_path(key)[0], soft=True)
            else:
                descriptor = attribute_edit.Field(entry_kind(ob, key), SLIDER_STEP[kind])
            self._drags[(ob, key)] = attribute_edit.Drag(self._starts[(ob, key)], descriptor)
            if rv3d is None or context.area.type != 'VIEW_3D':
                continue
            if kind == "ROT" and not _non_euler_rot(ob, kind):
                self._axes[(ob, key)] = "ROT"
                continue
            axes = node_axes(ob, key)
            if axes is None:
                continue
            px = screen_axis(region, rv3d, *axes)
            longest = max((v.length for v in (screen_axis(region, rv3d, axes[0], d) for d in
                                               _unit_dirs(axes[1])) if v is not None), default=0.0)
            if px is not None and px.length > AXIS_MIN_SHARE * longest > 0.0:
                self._axes[(ob, key)] = (px.x, px.y)
        if not attribute_edit.claim(context, self):
            return {'CANCELLED'}
        self._finished = False
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _header(self, context, text):
        if context.area:
            context.area.header_text_set(text)

    def _finish(self, context, cancel=False):
        from . import attribute_edit
        if getattr(self, '_finished', True):
            return {'CANCELLED'}
        self._finished = True
        changed = False
        try:
            for ob, node in self._nodes.items():
                if node.valid():
                    if cancel:
                        node.preview(context, self._node_starts[ob])
                    node_changed = node.params != self._node_starts[ob]
                    changed |= node_changed
                    if not cancel and node_changed:
                        node.commit(context, node.params)
                    node.finish()
            for (ob, key), start in self._starts.items():
                if key.startswith(MODEL_PREFIX):
                    continue
                try:
                    changed |= get_value(ob, key) != start
                    if cancel:
                        set_value(ob, key, start)
                    elif (get_value(ob, key) != start and auto_key.enabled(context.scene)
                          and auto_keys(ob, key, context)):
                        keyframe(ob, key)
                except (ReferenceError, RuntimeError, AttributeError):
                    pass
        finally:
            self._header(context, None)
            attribute_edit.release(self._window, self)
        if not cancel and changed:
            from .. import undo_steps
            undo_steps.push('Edit Channel Attributes')
        return {'CANCELLED'} if cancel or not changed else {'FINISHED'}

    def modal(self, context, event):
        try:
            if (context.scene != self._scene or context.scene.frame_current != self._frame
                    or context.active_object != self._object or context.mode != self._mode
                    or _view3d_tool(context) != self._tool):
                return self._finish(context, cancel=True)
            if event.type == 'MOUSEMOVE':
                sx, sy = event.mouse_x-self._last[0], event.mouse_y-self._last[1]
                self._last = event.mouse_x, event.mouse_y
                if context.region and abs(sx) > context.region.width//2:
                    sx = 0
                if context.region and abs(sy) > context.region.height//2:
                    sy = 0
                self._dx += sx
                self._dy += sy
                from .. import preferences
                prefs = preferences.get(context)
                pending = {ob: dict(node.params) for ob, node in self._nodes.items()}
                for pair, start in self._starts.items():
                    ob, key = pair
                    how = self._axes.get(pair)
                    if how == 'ROT':
                        value = start+rotate_delta(self._dx, self._dy)
                    elif how is not None:
                        value = start+projected_delta(how, self._dx, self._dy)
                    else:
                        value = self._drags[pair].move(sx/(context.preferences.system.ui_scale or 1.0),
                                                      SPEED_FACTOR[prefs.cb_speed], event.ctrl,
                                                      event.shift, prefs.cb_hyperbolic)
                        value = drag_limit(ob, key, value)
                    if key.startswith(MODEL_PREFIX):
                        pending[ob][channel_path(key)[0]] = value
                    elif get_value(ob, key) != value:
                        set_value(ob, key, value)
                for ob, params in pending.items():
                    if self._nodes[ob].params != params:
                        self._nodes[ob].preview(context, params)
                ob, key = next(iter(self._starts))
                self._header(context, f"{channel_label(key)}: {get_value(ob, key):.3f}")
                context.area.tag_redraw()
            elif event.type == 'MIDDLEMOUSE' and event.value == 'RELEASE':
                return self._finish(context)
            elif event.type in {'ESC', 'RIGHTMOUSE', 'WINDOW_DEACTIVATE'}:
                return self._finish(context, cancel=True)
            elif event.value == 'PRESS' and event.type in {'Q', 'W', 'E', 'R', 'T', 'Z'}:
                self._finish(context, cancel=True)
                return {'CANCELLED', 'PASS_THROUGH'}
        except (ReferenceError, RuntimeError, AttributeError, TypeError, ValueError) as error:
            self.report({'WARNING'}, str(error))
            return self._finish(context, cancel=True)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._finish(context, cancel=True)


# --- operators: selection, Channels menu ----------------------------------------------------------

class ALLSET_OT_cb_select_channel(bpy.types.Operator):
    """Select this channel (Ctrl: toggle, Shift: add). Selected channels follow MMB-drag in the viewport"""
    bl_idname = "allset.cb_select_channel"
    bl_label = "Select Channel"
    bl_options = {'INTERNAL'}

    key: StringProperty()
    mode: EnumProperty(items=(("SET", "Set", ""), ("TOGGLE", "Toggle", ""), ("EXTEND", "Extend", "")))

    def invoke(self, context, event):
        self.mode = "TOGGLE" if event.ctrl else "EXTEND" if event.shift else "SET"
        return self.execute(context)

    def execute(self, context):
        select_channel(self.key, self.mode, context)
        for area in context.screen.areas if context.screen else ():
            area.tag_redraw()
        return {'FINISHED'}


class ALLSET_OT_cb_deselect_channels(bpy.types.Operator):
    """Clear the Channel Box channel selection"""
    bl_idname = "allset.cb_deselect_channels"
    bl_label = "Deselect Channels"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        set_selected_channels([], context)
        return {'FINISHED'}


# --- drag over the rows ---------------------------------------------------------------------------------
# An embossed text field starts its text edit on PRESS, so no keymap item sees a press-drag that starts on a value
# field. ``allset.cb_hover`` (Property Editor MOUSEMOVE, first) remembers the Channel Box
# cell under the mouse (``context.property``) and starts ``allset.cb_channel_drag``, a window modal (window handlers
# run before the UI) that lives while the mouse is in that region and handles the LMB presses on channel cells.

_hover = {}      # window pointer -> (key, "NAME" / "VALUE") under the mouse, or None
_watching = set()
_anchor = {"key": None}
_field_handoff = {}


def start_field_drag(context, event, key, start_x):
    """Keep the triggering modifiers across bpy.ops' synchronous invoke handoff."""
    ptr = context.window.as_pointer()
    _field_handoff[ptr] = dict(type=event.type, value=event.value, mouse_x=event.mouse_x,
                               ctrl=event.ctrl, shift=event.shift, alt=event.alt)
    try:
        return bpy.ops.allset.cb_field_drag('INVOKE_DEFAULT', True, key=key, start_x=start_x)
    finally:
        _field_handoff.pop(ptr, None)


def _field_is_driven(ob, key):
    if is_input_key(key) or is_history_key(key):
        return driver(ob, key) is not None
    if not is_shape_key(key):
        kind = MAIN_BY_KEY.get(key, (None, None, None, None, None))[4]
        # A displayed Euler channel on a quaternion/axis-angle node writes the
        # entire four-component rotation; a root joint's armature-space translate
        # writes all three local components. Do not overwrite any driven component.
        if _non_euler_rot(ob, kind) or (kind == "LOC" and is_root_joint(ob)):
            ad = ob.id_data.animation_data
            if ad is None:
                return False
            if _non_euler_rot(ob, kind):
                from .. import rotation_display
                path, size = rotation_display.curve_path(ob), 4
            else:
                path, size = "location", 3
            path = full_path(ob, path)
            return bool(path and any(ad.drivers.find(path, index=i) is not None for i in range(size)))
        return driver(ob, key) is not None
    owner = shape_owner(ob, key)
    ad = owner.animation_data if owner is not None else None
    return bool(ad and any(ad.drivers.find(path, index=max(index, 0)) is not None
                           for path, index in shape_paths(owner, key)))


def field_drag_starts(context, key):
    """Snapshot editable scalar channels, using the same selection rule as text entry."""
    starts = {}
    for k in entry_keys(key, context):
        for ob in targets(context):
            if (not has_channel(ob, k) or is_locked(ob, k) or is_hidden(ob, k)
                    or k in constrained_keys(ob) or _field_is_driven(ob, k)):
                continue
            value = get_value(ob, k)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                kind = entry_kind(ob, k)
                if kind in {'LENGTH', 'ROTATION', 'NONE', 'INT', 'FLOAT'}:
                    starts[(ob, k)] = (value, kind)
    return starts


class ALLSET_OT_cb_field_drag(bpy.types.Operator):
    """Drag a numeric Channel Box value horizontally"""
    bl_idname = "allset.cb_field_drag"
    bl_label = "Adjust Channel Values"
    bl_options = {'INTERNAL', 'UNDO', 'BLOCKING'}

    key: StringProperty(options={'SKIP_SAVE'})
    start_x: bpy.props.IntProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        from types import SimpleNamespace
        handoff = _field_handoff.get(context.window.as_pointer()) if context.window is not None else None
        if handoff is not None:
            event = SimpleNamespace(**handoff)
        self._starts = field_drag_starts(context, self.key)
        if not self._starts:
            return {'CANCELLED'}
        self._last_x = self.start_x
        self._drag_values = {pair: value for pair, (value, _kind) in self._starts.items()}
        self._mode = None
        self._window = context.window
        self._scene = context.scene
        self._frame = context.scene.frame_current
        try:
            if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                self._apply(event, 1 if event.type == 'WHEELUPMOUSE' else -1, wheel=True)
                return self._confirm(context)
            self._move(event)
        except (ReferenceError, RuntimeError, AttributeError, TypeError, ValueError):
            self._restore()
            return {'CANCELLED'}
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _move(self, event):
        step = event.mouse_x - self._last_x
        self._last_x = event.mouse_x
        self._apply(event, step)

    def _apply(self, event, step, wheel=False):
        if not step:
            return
        mode = (event.ctrl, event.shift, event.alt)
        if mode != self._mode or wheel:
            # Begin each sensitivity mode and each wheel notch at the actual value.
            # Neither a modifier change nor a notch should reveal a hidden fraction.
            self._drag_values = {pair: get_value(*pair) for pair in self._starts}
            self._mode = mode
        precision = (0.1 if event.shift else 1.0) * (0.01 if event.alt else 1.0)
        for (ob, key), (start, kind) in self._starts.items():
            display_step = 0.5 if kind == 'ROTATION' and cb_entry._degrees(self._scene) else 0.01
            if kind == 'INT':
                display_step = 0.1
            amount = (step * precision if wheel else
                      step * display_step * precision * (10.0 if event.ctrl else 1.0))
            continuous = self._drag_values[(ob, key)] + cb_entry.from_display(amount, kind, self._scene)
            self._drag_values[(ob, key)] = continuous
            value = continuous
            if event.ctrl and not wheel:
                quantum = precision
                shown = cb_entry.to_display(value, kind, self._scene) / quantum
                snapped = math.floor(shown + 0.5) if shown >= 0 else math.ceil(shown - 0.5)
                value = cb_entry.from_display(snapped * quantum, kind, self._scene)
            if kind == 'INT':
                # Symmetric nearest integer, independent of the sign of the starting value.
                value = math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)
            value = drag_limit(ob, key, value)
            if get_value(ob, key) != value:
                set_value(ob, key, value)
        try:
            _redraw(self._window)
        except ReferenceError:
            pass

    def _restore(self):
        for (ob, key), (start, _kind) in self._starts.items():
            try:
                if get_value(ob, key) != start:
                    set_value(ob, key, start)
            except (ReferenceError, RuntimeError, AttributeError, TypeError, ValueError):
                pass  # A removed or no longer writable object cannot be restored.
        try:
            _redraw(self._window)
        except ReferenceError:
            pass

    def _confirm(self, context):
        if context.scene != self._scene or self._scene.frame_current != self._frame:
            self._restore()
            return {'CANCELLED'}
        changed = [(ob, key) for (ob, key), (start, _kind) in self._starts.items()
                   if get_value(ob, key) != start]
        if not changed:
            return {'CANCELLED'}
        if auto_key.enabled(self._scene):
            for ob, key in changed:
                if auto_keys(ob, key, context):
                    keyframe(ob, key)
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            try:
                self._move(event)
            except (ReferenceError, RuntimeError, AttributeError, TypeError, ValueError):
                self._restore()
                return {'CANCELLED'}
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            try:
                return self._confirm(context)
            except (ReferenceError, RuntimeError, AttributeError, TypeError, ValueError):
                self._restore()
                return {'CANCELLED'}
        elif event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            try:
                self._apply(event, 1 if event.type == 'WHEELUPMOUSE' else -1, wheel=True)
            except (ReferenceError, RuntimeError, AttributeError, TypeError, ValueError):
                self._restore()
                return {'CANCELLED'}
        elif event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._restore()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


def _round_half_up(x):
    """C roundf for UI sizes (UI_UNIT_Y = roundf(18 x scale) + 2 x pixel size): Python's round(22.5) is 22, Blender's 23,
    so at UI 1.25 the unit was 24 px instead of 25 and every 0.8 U row 0.8 px short (#83)."""
    return int(x + 0.5)


def row_pitch(context):
    """Channel row height in px (ROW_SCALE x Blender's widget unit)."""
    system = context.preferences.system
    unit = _round_half_up(18.0 * system.ui_scale) + 2 * system.pixel_size
    return max(1.0, unit * ROW_SCALE)


def _redraw(window):
    for area in window.screen.areas if window is not None and window.screen else ():
        area.tag_redraw()


def _hovered_cell(context):
    prop = getattr(context, "property", None)
    if not prop or not isinstance(prop[0], bpy.types.Scene):
        return None
    return cell_key(prop[1], prop[0])


class ALLSET_OT_cb_hover(bpy.types.Operator):
    """Channel Box: remember the channel under the mouse and watch for a drag over the rows"""
    bl_idname = "allset.cb_hover"
    bl_label = "Channel Box Hover"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        window = context.window
        if window is None:
            return {'PASS_THROUGH'}
        hit = _hovered_cell(context)
        _hover[window.as_pointer()] = hit
        # also over the Channel Box part's empty space / headers: RMB there is Maya's Channels menu
        if ((hit is not None or in_channel_part(context, event)) and window.as_pointer() not in _watching
                and context.region is not None):
            bpy.ops.allset.cb_channel_drag('INVOKE_DEFAULT', True)
        return {'PASS_THROUGH'}


class ALLSET_OT_cb_channel_drag(bpy.types.Operator):
    """Maya Channel Box selection: click a channel name or field, drag over the rows to select a range
    (Ctrl toggles / adds, Shift selects from the last clicked channel)"""
    bl_idname = "allset.cb_channel_drag"
    bl_label = "Select Channels"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        region = context.region
        if region is None or context.window is None:
            return {'CANCELLED'}
        self._win = context.window.as_pointer()
        self._window = context.window
        self._rect = (region.x, region.y, region.x + region.width, region.y + region.height)
        self._pitch = row_pitch(context)
        self._press = None
        # the Channel Box part of a Maya dock: from the region top down to the Layer Editor split (None: no dock)
        self._cb_bottom = None
        self._rows_bottom = None
        if _is_cb_dock(context):
            u = _unit(context)
            self._cb_bottom = region.y + region.height - cb_share(region, u) * region.height
            used = _filled.get(context.area.as_pointer())
            if used is not None:
                self._rows_bottom = region.y + region.height - used * u
        _watching.add(self._win)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _inside(self, event):
        x0, y0, x1, y1 = self._rect
        return x0 <= event.mouse_x < x1 and y0 <= event.mouse_y < y1

    def _finish(self, cancel=False):
        _watching.discard(self._win)
        return {'CANCELLED' if cancel else 'FINISHED', 'PASS_THROUGH'}

    def modal(self, context, event):
        try:
            self._window.screen
        except ReferenceError:
            _watching.discard(self._win)
            return {'CANCELLED', 'PASS_THROUGH'}
        if self._press is None:
            if event.type == 'MOUSEMOVE' and not self._inside(event):
                return self._finish()
            if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and self._inside(event):
                hit = _hover.get(self._win)
                if hit is not None:
                    return self._on_press(context, event, hit)
                if self._in_empty_space(event) and selected_channels(context):
                    # Maya: a click on the empty space under the channels deselects them
                    set_selected_channels([], context)
                    _redraw(self._window)
            if event.type == 'RIGHTMOUSE' and event.value == 'PRESS' and self._inside(event):
                hit = _hover.get(self._win)
                in_part = hit is not None or (self._cb_bottom is not None and event.mouse_y >= self._cb_bottom)
                if in_part and not (event.shift or event.alt):
                    return self._on_rmb(context, hit, edit=event.ctrl)
            return {'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE':
            if self._on_move(context, event):
                # The field already applied this move. Passing it through can
                # start a newer channel watcher that preempts the active drag.
                self._finish()
                return {'FINISHED'}
            return {'PASS_THROUGH'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return self._on_release(context, event)
        if event.type == 'ESC' and event.value == 'PRESS':
            set_selected_channels(self._base)
            self._press = None
            _redraw(self._window)
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def _in_empty_space(self, event):
        if self._cb_bottom is None or self._rows_bottom is None:
            return False
        return self._cb_bottom <= event.mouse_y < self._rows_bottom

    def _on_rmb(self, context, hit, edit=False):
        """Maya: RMB in the Channel Box = the Channels menu. Blender's button
        context menu draws its C items first and a Python menu only after them (#87: the Channels items
        sat under 15 Blender rows), so the press is taken here, before the region's button handler. A channel
        that isn't selected becomes the selection first, so Key Selected keys the clicked channel."""
        if edit:     # Ctrl+RMB = the Edit menu (Maya Channel Box), selection kept
            bpy.ops.wm.call_menu(name=ALLSET_MT_cb_edit.__name__)
            return {'RUNNING_MODAL'}
        if hit is not None:
            key, _part = hit
            if key not in selected_channels(context):
                set_selected_channels([key], context)
                _anchor["key"] = key
                _redraw(self._window)
        bpy.ops.wm.call_menu(name=ALLSET_MT_cb_channels.__name__)
        return {'RUNNING_MODAL'}

    def _on_press(self, context, event, hit):
        ob = lead(context)
        if ob is None:
            return {'PASS_THROUGH'}
        key, part = hit
        self._ob = ob
        self._y0 = event.mouse_y
        self._x0 = event.mouse_x
        self._field_candidate = part == 'VALUE'
        self._dragging = False
        self._ctrl = event.ctrl
        self._base = selected_channels(context)
        self._anchor = key
        self._part = part
        self._key = key
        self._mods = (event.shift, event.ctrl)
        if part == 'VALUE' and (event.shift or event.ctrl):
            # over a value, a modifier press may start a drag (Shift finer, Ctrl whole units): the Shift / Ctrl
            # selection waits for the release of a plain click (_on_release)
            pass
        elif part == 'VALUE':
            if key not in self._base:
                set_selected_channels([key], context)
                _anchor["key"] = key
        elif event.shift and _anchor["key"] is not None:
            select_range(ob, _anchor["key"], key, "SET", context=context)
            self._anchor = _anchor["key"]
        elif event.ctrl:
            select_channel(key, "TOGGLE", context)
            _anchor["key"] = key
        elif not (part == "VALUE" and key in self._base and len(self._base) > 1):
            # a field of one of several selected channels keeps them (the typed value goes to all of them)
            set_selected_channels([key], context)
            _anchor["key"] = key
        self._press = part
        _redraw(self._window)
        # eaten: an embossed field would start its text edit here and swallow the drag
        return {'RUNNING_MODAL'}

    def _key_at_offset(self, event):
        keys = drawn_keys(self._ob)
        if self._anchor not in keys:
            return None
        rows = round((self._y0 - event.mouse_y) / self._pitch)
        i = max(0, min(len(keys) - 1, keys.index(self._anchor) + rows))
        return keys[i]

    def _current(self, event):
        hit = _hover.get(self._win)   # updated by allset.cb_hover after the previous move
        return hit[0] if hit is not None else self._key_at_offset(event)

    def _extend(self, context, cur):
        if cur is None or (cur == self._anchor and not self._dragging):
            return
        self._dragging = True
        base = self._base if self._ctrl else None
        select_range(self._ob, self._anchor, cur, "ADD" if self._ctrl else "SET", base=base, context=context)
        _redraw(self._window)

    def _on_move(self, context, event):
        dx = event.mouse_x - self._x0
        dy = event.mouse_y - self._y0
        if (self._field_candidate and not self._dragging and abs(dx) >= 6
                and abs(dx) > abs(dy) and field_drag_starts(context, self._key)):
            result = start_field_drag(context, event, self._key, self._x0)
            if 'RUNNING_MODAL' in result:
                self._press = None
                return True
        if not self._dragging and abs(event.mouse_y - self._y0) < 0.5 * self._pitch:
            return
        self._extend(context, self._current(event))

    def _on_release(self, context, event):
        part, self._press = self._press, None
        shift, ctrl = getattr(self, "_mods", (False, False))
        if self._dragging:
            self._extend(context, self._current(event))   # the hover of the last move
        elif part == "VALUE" and (shift or ctrl):
            # a Shift / Ctrl click on a value selects like one on the name
            if shift and _anchor["key"] is not None:
                select_range(self._ob, _anchor["key"], self._key, "SET", context=context)
            else:
                select_channel(self._key, "TOGGLE", context)
                _anchor["key"] = self._key
        elif part == "VALUE" and not (event.ctrl or event.shift):
            # a click on a field: Maya edits it in place. The press was eaten, so the field is edited in a popup
            # over it (text active at once); Enter writes the text into every selected channel (apply_entry).
            try:
                edit_field(context, self._key)
            except RuntimeError:
                pass
        _redraw(self._window)
        return {'RUNNING_MODAL'}


def field_owner(context, key):
    """(owner, property) of the Channel Box text field of channel ``key``."""
    cb = context.scene.allset_cb
    if key in MAIN_BY_KEY:
        return cb, key + "_text"
    for r in cb.rows:
        if row_key(r) == key:
            return r, "text"
    if is_history_key(key):
        return context.scene.allset_creation, key[len(HISTORY_PREFIX):] + "_text"
    return None, None


_edit = {"key": None}


def edit_field(context, key):
    """Edit channel ``key``'s field in a popover at the mouse with the text active at once (Maya: a click into a
    field edits it); Enter writes the text into every selected channel (apply_entry) and closes it, like F2."""
    if field_owner(context, key)[0] is None:
        return False
    _edit["key"] = key
    bpy.ops.wm.call_panel(name=ALLSET_PT_cb_field.__name__, keep_open=False)
    return True


class ALLSET_PT_cb_field(bpy.types.Panel):
    """The Channel Box field editor popover (called by edit_field only)"""
    bl_space_type = 'TOPBAR'   # dummy, like Blender's TOPBAR_PT_name (F2): only shown through wm.call_panel
    bl_region_type = 'HEADER'
    bl_label = "Channel Value"
    bl_ui_units_x = 6

    def draw(self, context):
        owner, prop = field_owner(context, _edit["key"] or "")
        if owner is None:
            return
        row = self.layout.row()
        row.activate_init = True
        row.prop(owner, prop, text="")


def _visible_channels(ob):
    keys = [c[0] for c in MAIN if has_channel(ob, c[0])] + \
           [CUSTOM_PREFIX + k for k in custom_keys(ob)]
    return [k for k in keys if not is_hidden(ob, k)]


class _ChannelAction:
    """Base: acts on selected channels of all target objects."""
    bl_options = {'REGISTER', 'UNDO'}
    use_all = False  # True: every visible channel when nothing is selected

    @classmethod
    def poll(cls, context):
        return lead(context) is not None

    def channel_keys(self, context, ob):
        sel = selected_channels(context)
        if not sel and self.use_all:
            return _visible_channels(ob)
        return [k for k in sel if has_channel(ob, k)]

    def execute(self, context):
        count = 0
        for ob in targets(context):
            for key in self.channel_keys(context, ob):
                count += bool(self.act(context, ob, key))
        results.result(self, f"{self.bl_label}: {count} channel(s)")
        return {'FINISHED'}


def _op(idname, label, doc, act, use_all=False, **props):
    cls = type(f"ALLSET_OT_{idname}", (_ChannelAction, bpy.types.Operator), {
        "bl_idname": f"allset.{idname}", "bl_label": label, "__doc__": doc,
        "act": act, "use_all": use_all, "__annotations__": props})
    return cls


def _act_key(self, context, ob, key):
    return is_keyable(ob, key) and keyframe(ob, key)


def _act_breakdown(self, context, ob, key):
    return is_keyable(ob, key) and keyframe(ob, key, 'BREAKDOWN')


def _act_mute(self, context, ob, key):
    curves = channel_fcurves(ob, key)
    for fc in curves:
        fc.mute = self.mute
    return bool(curves)


def _act_delete(self, context, ob, key):
    return remove_channel_curves(ob, key)


def _act_break(self, context, ob, key):
    done = _act_delete(self, context, ob, key)
    dr = driver(ob, key)
    if dr is not None:
        owner = curve_owner(ob, key) if is_blend_key(key) else ob.id_data
        owner.animation_data.drivers.remove(dr)
        done = True
    return done


def _act_lock(self, context, ob, key):
    return set_locked(ob, key, self.lock)


def _act_hide(self, context, ob, key):
    if self.lock:
        set_locked(ob, key, True)
    _set_flag_list(ob, HIDDEN_PROP, _flag_list(ob, HIDDEN_PROP) + [key])
    return True


def _act_keyable(self, context, ob, key):
    keys = [k for k in _flag_list(ob, NONKEYABLE_PROP) if k != key]
    if not self.keyable:
        keys.append(key)
    _set_flag_list(ob, NONKEYABLE_PROP, keys)
    return True


def _act_duplicate(self, context, ob, key):
    ld = lead(context)
    if ob == ld or not has_channel(ld, key) or is_locked(ob, key):
        return False
    set_value(ob, key, get_value(ld, key))
    return True


CHANNEL_OPS = (
    _op("cb_key_selected", "Key Selected", "Set a key on the selected channels", _act_key),
    _op("cb_key_all", "Key All Keyable", "Set a key on every keyable channel", _act_key, use_all=True),
    _op("cb_breakdown_selected", "Breakdown Selected", "Set a breakdown key on the selected channels",
        _act_breakdown),
    _op("cb_mute", "Mute Selected", "Mute or unmute the animation of the selected channels", _act_mute,
        mute=BoolProperty(default=True)),
    _op("cb_delete_keys", "Delete Selected", "Delete the animation curves of the selected channels",
        _act_delete),
    _op("cb_break_connections", "Break Connections",
        "Remove the animation curve or driver feeding the selected channels", _act_break),
    _op("cb_lock", "Lock Selected", "Lock or unlock the selected channels", _act_lock,
        lock=BoolProperty(default=True)),
    _op("cb_hide", "Hide Selected", "Hide the selected channels from the Channel Box", _act_hide,
        lock=BoolProperty(default=False)),
    _op("cb_keyable", "Make Selected Keyable", "Make the selected channels keyable or nonkeyable",
        _act_keyable, keyable=BoolProperty(default=True)),
    _op("cb_duplicate_values", "Duplicate Values",
        "Copy the lead object's values of the selected channels to the other selected objects",
        _act_duplicate),
)


class ALLSET_OT_cb_show_all(bpy.types.Operator):
    """Show every hidden channel again"""
    bl_idname = "allset.cb_show_all"
    bl_label = "Show All Channels"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for ob in targets(context):
            _set_flag_list(ob, HIDDEN_PROP, [])
        return {'FINISHED'}


# --- menus -------------------------------------------------------------------------------------------

class ALLSET_MT_cb_channels(bpy.types.Menu):
    """Maya Channel Box Channels menu (RMB anywhere in the Channel Box)"""
    bl_label = "Channels"

    def draw(self, context):
        from .. import preferences
        lay = self.layout
        lay.operator("allset.cb_key_selected")
        lay.operator("allset.cb_key_all")
        lay.operator("allset.cb_breakdown_selected")
        lay.operator("allset.cb_breakdown_all")
        lay.operator("allset.cb_mute", text="Mute Selected").mute = True
        lay.operator("allset.cb_mute_all", text="Mute All").mute = True
        lay.operator("allset.cb_mute", text="Unmute Selected").mute = False
        lay.operator("allset.cb_mute_all", text="Unmute All").mute = False
        lay.separator()
        prefs = preferences.get(context)
        lay.prop(prefs, "cb_sync_graph", text="Sync Selection in Graph Editor")
        lay.prop(prefs, "cb_sync_timeline", text="Sync Timeline Display")
        lay.separator()
        lay.operator("allset.cb_clipboard", text="Cut Selected").action = "CUT"
        lay.operator("allset.cb_clipboard", text="Copy Selected").action = "COPY"
        lay.operator("allset.cb_clipboard", text="Paste Selected").action = "PASTE"
        lay.operator("allset.cb_delete_keys")
        lay.separator()
        lay.operator("allset.cb_duplicate_values")
        lay.menu(ALLSET_MT_cb_freeze.__name__)
        lay.separator()
        lay.operator("allset.cb_break_connections")
        lay.operator("allset.cb_select_connection")
        lay.separator()
        lay.operator("allset.cb_lock", text="Lock Selected").lock = True
        lay.operator("allset.cb_lock", text="Unlock Selected").lock = False
        lay.operator("allset.cb_hide", text="Hide Selected").lock = False
        lay.operator("allset.cb_hide", text="Lock and Hide Selected").lock = True
        lay.operator("allset.cb_show_all")
        lay.operator("allset.cb_keyable", text="Make Selected Nonkeyable").keyable = False
        lay.operator("allset.cb_keyable", text="Make Selected Keyable").keyable = True
        lay.separator()
        # the selected animation layer's attributes (operators/anim_layers.py, Maya animLayer -attribute)
        lay.operator("allset.anim_layer_attrs", text="Add to Selected Layers").add = True
        lay.operator("allset.anim_layer_attrs", text="Remove From Selected Layers").add = False
        lay.separator()
        lay.operator("allset.cb_deselect_channels")


class ALLSET_MT_cb_freeze(bpy.types.Menu):
    """Maya Channels > Freeze (makeIdentity -apply on the chosen channels)"""
    bl_label = "Freeze"

    def draw(self, context):
        lay = self.layout
        for text, t, r, sc in (("Translate", True, False, False), ("Rotate", False, True, False),
                               ("Scale", False, False, True), ("All", True, True, True)):
            op = lay.operator("allset.freeze_transform", text=text)
            op.translate, op.rotate, op.scale = t, r, sc


def is_cb_button(context):
    """The button under the mouse is a Channel Box channel name or value (for its RMB menu)."""
    op = getattr(context, "button_operator", None)
    if op is not None and op.bl_rna.identifier == ALLSET_OT_cb_select_channel.__name__:
        return True
    ptr = getattr(context, "button_pointer", None)
    return isinstance(ptr, (ALLSET_PG_channel_box, ALLSET_PG_cb_row))


# Maya's Channel Box RMB menu = the Channels menu. RMB on a UI button
# opens Blender's button context menu from C (not a keymap item), so the Channels items go on top of it.
RMB_ITEMS = (("allset.cb_key_selected", "Key Selected", {}),
             ("allset.cb_breakdown_selected", "Breakdown Selected", {}),
             ("allset.cb_mute", "Mute Selected", {"mute": True}),
             ("allset.cb_mute", "Unmute Selected", {"mute": False}),
             ("allset.cb_delete_keys", "Delete Selected", {}),
             ("allset.cb_break_connections", "Break Connections", {}),
             ("allset.cb_lock", "Lock Selected", {"lock": True}),
             ("allset.cb_lock", "Unlock Selected", {"lock": False}),
             ("allset.cb_hide", "Hide Selected", {"lock": False}),
             ("allset.cb_keyable", "Make Selected Nonkeyable", {"keyable": False}))


def draw_button_menu(self, context):
    if not is_cb_button(context):
        return
    lay = self.layout
    for idname, text, props in RMB_ITEMS:
        op = lay.operator(idname, text=text)
        for k, v in props.items():
            setattr(op, k, v)
    lay.separator()


class ALLSET_MT_cb_settings(bpy.types.Menu):
    bl_label = "Settings"

    def draw(self, context):
        from .. import preferences
        prefs = preferences.get(context)
        lay = self.layout
        lay.label(text="Virtual slider speed")
        lay.prop(prefs, "cb_speed", expand=True)
        lay.prop(prefs, "cb_hyperbolic")
        lay.prop(prefs, 'cb_manipulators', text='Manipulators')


class ALLSET_MT_cb_edit(bpy.types.Menu):
    """Maya Channel Box Edit menu"""
    bl_label = "Edit"

    def draw(self, context):
        lay = self.layout
        chrome.grey(lay, "Expressions...")
        lay.operator("allset.sdk_window", text="Set Driven Key...")
        lay.operator("allset.open_editor", text="Graph Editor").ui_type = 'FCURVES'
        chrome.grey(lay, "Channel Control...")
        chrome.grey(lay, "Connection Editor")
        lay.operator("allset.dock_show", text="Attribute Editor").dock = 'ATTRIBUTE_EDITOR'
        lay.operator("allset.material_attributes", text="Material Attributes...")
        lay.separator()
        lay.operator("allset.add_attribute", text="Add Attribute...")
        lay.operator("allset.edit_attribute", text="Edit Attribute...")
        chrome.grey(lay, "Duplicate Attribute")
        lay.operator("allset.delete_attribute", text="Delete Attributes")
        lay.separator()
        lay.operator(ALLSET_OT_cb_make_lead.bl_idname, text="Select Node").only = True
        lay.operator("allset.delete", text="Delete Node")
        lay.operator("allset.delete_history", text="Delete History")
        lay.separator()
        lay.menu("ALLSET_MT_cb_settings", text="Settings")
        chrome.grey(lay, "Channel Names")


class ALLSET_OT_cb_make_lead(bpy.types.Operator):
    """Make this object the lead (Maya Channel Box Object menu: select -add)"""
    bl_idname = "allset.cb_make_lead"
    bl_label = "Lead Object"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    name: StringProperty(options={'SKIP_SAVE'})
    only: BoolProperty(name="Only", description="Select only this object", options={'SKIP_SAVE'})

    def execute(self, context):
        if pose_armature(context):
            return self._bone(context)
        ob = context.scene.objects.get(self.name) if self.name else context.active_object
        if ob is None:
            return {'CANCELLED'}
        if self.only:
            for other in context.selected_objects:
                other.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        return {'FINISHED'}

    def _bone(self, context):
        bones = [pb for arm in pose_objects(context) for pb in arm.pose.bones]
        pb = next((b for b in bones if b.name == self.name), None) if self.name else lead(context)
        if pb is None:
            return {'CANCELLED'}
        if self.only:
            for other in bones:
                set_bone_selected(other, False)
        set_bone_selected(pb, True)
        pb.id_data.data.bones.active = pb.bone
        return {'FINISHED'}


class ALLSET_OT_cb_rotate_order(bpy.types.Operator):
    """Set the rotate order (Blender converts the rotation, the pose stays): Maya channels need Euler"""
    bl_idname = "allset.cb_rotate_order"
    bl_label = "Rotate Order"
    bl_options = {'REGISTER', 'UNDO'}

    order: EnumProperty(name="Rotate Order", items=[(m, m, "") for m in
                                                    ('XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX')])

    @classmethod
    def poll(cls, context):
        return lead(context) is not None

    def execute(self, context):
        for node in targets(context):
            node.rotation_mode = self.order
        return {'FINISHED'}


class ALLSET_MT_cb_object(bpy.types.Menu):
    """Maya Channel Box Object menu: the selected objects (joints in pose mode), picking one makes it
    the lead"""
    bl_label = "Object"

    def draw(self, context):
        lay = self.layout
        obs = targets(context)
        if not obs:
            chrome.grey(lay, "Nothing selected")
        ld = lead(context)
        for ob in obs[:10]:
            lay.operator(ALLSET_OT_cb_make_lead.bl_idname, text=ob.name,
                         icon='LAYER_ACTIVE' if ob == ld else 'BLANK1').name = ob.name


class ALLSET_MT_cb_show(bpy.types.Menu):
    """Maya Channel Box Show menu"""
    bl_label = "Show"

    def draw(self, context):
        lay = self.layout
        lay.operator("allset.cb_show_all", text="All")
        lay.separator()
        for label in ("Assets", "Attribute Type Filters"):
            chrome.grey(lay, label)


# Maya Channel Box menu bar, left to right (Maya 2022).
MENU_BAR = (("Channels", "ALLSET_MT_cb_channels"), ("Edit", "ALLSET_MT_cb_edit"),
            ("Object", "ALLSET_MT_cb_object"), ("Show", "ALLSET_MT_cb_show"))
# Maya's empty Channel Box text (compare/01_layout_empty, three centred lines).
EMPTY_TEXT = (i18n.mark("Select objects in the scene to view,"), i18n.mark("edit and set keyframes on channels"),
              i18n.mark("(attributes)"))


# #156: an unskinned skeleton's joints are edited in Edit mode (W / E / R reposition them); their keyable
# channels are in Pose mode
PLACING_TEXT = (i18n.mark("Editing joints: W / E / R move them,"), i18n.mark("F8 = pose mode (channels and keys)"))
# #155: short enough for the dock at its default width (the longer text was cut at UI scale 1.25)
POSE_HINT = "Ctrl+Tab: joint channels"


def draw_joint_translate(layout, context):
    """Edit-mode joints: the lead joint's name + Translate X / Y / Z text fields (``+=`` entry, display
    units; typing moves the joint, its children follow unless Preserve Children, every Maya frame stays —
    operators/joint_edit.py). Returns the UI units drawn."""
    from ..operators import joint_edit
    _ob, eb = joint_edit.lead_joint(context)
    if eb is None:
        return 0
    layout.label(text=eb.name)
    for a in joint_edit.AXES:
        row = layout.row(align=True)
        split = row.split(factor=0.5, align=True)
        split.label(text=f"Translate {a.upper()}")
        split.prop(context.scene, f"allset_joint_t{a}", text="")
        row.label(text="", icon='BLANK1')
    return 1 + len(joint_edit.AXES)


def draw_empty(layout):
    layout.separator(factor=6)
    chrome.wrapped(layout, EMPTY_TEXT)   # empty state
    layout.separator(factor=6)


# --- panel ---------------------------------------------------------------------------------------------

_STATE_ICON = {'KEYED': 'DECORATE_KEYFRAME', 'ANIMATED': 'DECORATE_ANIMATE', 'DRIVEN': 'DECORATE_DRIVER',
               'MUTED': 'MUTE_IPO_ON', 'LAYERED': 'NLA'}
# states drawn red (``alert``); a layer member is Maya teal, which UILayout can't draw: icon only
_ALERT_STATES = {'KEYED', 'ANIMATED', 'DRIVEN', 'MUTED'}


def state_alert(state):
    """A channel state the value cell draws in the key colour (UILayout ``alert``); the Attribute Editor's
    Translate / Rotate / Scale fields use it too."""
    return state in _ALERT_STATES


def _row_label(row, key, selected, sel_owner=None, sel_prop=None):
    sub = row.row(align=True)
    if sel_owner is not None:
        # a toggle of the channel's selection: pressed = Maya's blue name cell; the drag
        # watcher reads it from ``context.property`` (#6)
        sub.prop(sel_owner, sel_prop, text=channel_label(key), toggle=True, emboss=selected)
        return
    op = sub.operator("allset.cb_select_channel", text=channel_label(key), depress=selected,
                      emboss=selected)
    op.key = key


ROW_SCALE = 0.8

def draw_channel_row(layout, ob, key, value_owner, value_prop, selected, constrained=False,
                     sel_owner=None, sel_prop=None):
    row = layout.row(align=True)
    split = row.split(factor=0.5, align=True)
    _row_label(split, key, selected, sel_owner, sel_prop)
    right = split.row(align=True)
    state = channel_state(ob, key)
    right.enabled = not is_locked(ob, key)
    if constrained:
        # Maya draws constrained channels blue: a pressed button is the user's
        # theme selection colour (wcol_tool inner_sel; Blender's factory #4772b3 is blue); UILayout has no other colour.
        text = cb_entry.format_value(get_value(ob, key), entry_kind(ob, key), bpy.context.scene)
        right.operator("allset.cb_select_channel", text=text, depress=True).key = key
        row.label(text="", icon='CONSTRAINT')
        return row
    right.alert = state_alert(state)
    right.prop(value_owner, value_prop, text="")
    # Proxy fields get no automatic keyframe colouring: show the lead object's state.
    row.label(text="", icon=_STATE_ICON.get(state, 'BLANK1'))
    return row


def _modifier_props(mod, limit=10):
    """Editable scalar properties of a modifier, Maya INPUTS-style; a kit Maya deformer shows
    its Maya attributes instead (``maya:<key>`` rows, operators/deformers.ATTRS)."""
    from ..operators import deformers
    maya = deformers.attrs(mod)
    if maya is not None:
        return [deformers.PREFIX + a.key for a in maya]
    skip ={"name", "show_expanded", "show_on_cage", "show_in_editmode", "show_render",
            "use_apply_on_spline", "use_pin_to_last", "is_override_data_editable",
            "persistent_uid", "execution_time", "show_viewport"}
    out = []
    for p in mod.bl_rna.properties:
        ident = p.identifier
        if (ident in skip or p.is_readonly or ident.startswith(("show_", "open_", "is_"))
                or ident.endswith("_panel")):
            continue
        if p.type in {'INT', 'FLOAT', 'BOOLEAN'} and getattr(p, "array_length", 0) == 0:
            out.append(p.identifier)
        if len(out) >= limit:
            break
    return out


SHAPE_PROPS = {
    'CAMERA': ("lens", "clip_start", "clip_end"),
    # Maya light shapes: Color R / G / B, Intensity first (the Maya keyable order); Intensity is the
    # Maya value over Blender's Power (operators/lights.py)
    # + spot Cone Angle / Penumbra Angle (keyable on a Maya spotLight)
    'LIGHT': ("maya:colorR", "maya:colorG", "maya:colorB", "allset_intensity", "maya:coneAngle", "maya:penumbraAngle"),
    'LATTICE': ("points_u", "points_w", "points_v"),     # Maya S / T / U Divisions (Maya Y = Blender Z)
}


def wanted_rows(ob):
    """(kind, name, mod_type, nth) for every text row of the lead object."""
    out = [("CUSTOM", name, "", 0) for name in custom_keys(ob)]
    data = getattr(ob, "data", None)
    if data is not None:
        for prop in SHAPE_PROPS.get(ob.type, ()):
            rna = data.bl_rna.properties.get(prop)
            if (rna is not None and cb_entry.kind_of_rna(rna)) or _virtual(data, prop) is not None:
                out.append(("SHAPE", prop, "", 0))
    for mod in _inputs(ob):
        if is_open(ob, mod_node(mod)):
            for prop in _modifier_props(mod):
                out.append(("INPUT", prop, mod.type, _nth_of_type(ob, mod)))
    bs = blend_shape_key(ob)
    if bs is not None and is_open(ob, blend_shape_node(bs)):
        out += [("BLEND", kb.name, "", 0) for kb in blend_shape_targets(bs)]
    from ..operators import constrain_multi
    for con in constraints(ob):
        if not is_open(ob, con_node(ob, con)):
            continue
        mb = constrain_multi.member(con, ob)
        if mb is None:
            out.append(("CONSTRAINT", "influence", con.type, _nth_constraint(ob, con)))
        elif constrain_multi.is_head(con, ob):
            # Maya weights <target>W0, W1 ... = the owner's weight ID properties, typed like custom rows
            out += [("CUSTOM", prop, "", 0) for prop, _label in constrain_multi.weights(ob, mb.group)
                    if prop in ob.keys()]
    return out


def rows_signature(ob):
    if ob is None:
        return ""
    cons = [(c.name, c.type, weight_name(c)) for c in constraints(ob)]
    opened = sorted(open_nodes(ob))
    if is_bone(ob):
        return repr(("BONE", ob.id_data.name, ob.name, custom_keys(ob), cons, opened))
    mods = [(m.name, m.type) for m in _inputs(ob)]
    bs = blend_shape_key(ob)
    targets_ = [kb.name for kb in blend_shape_targets(bs)] if bs is not None else []
    return repr((ob.name, ob.type, custom_keys(ob), mods, cons, opened, targets_))


_rows_state = {"busy": False}


def rebuild_rows(context=None):
    """Make ``Scene.allset_cb.rows`` match the lead object (only when it changed)."""
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    cb = getattr(scene, "allset_cb", None) if scene is not None else None
    view_layer = getattr(context, "view_layer", None)
    if cb is None or view_layer is None or _rows_state["busy"]:
        return False
    ob = lead(context)
    sig = rows_signature(ob)
    if cb.rows_sig == sig:
        return False
    _rows_state["busy"] = True
    try:
        cb.rows.clear()
        if ob is not None:
            for kind, name, mod_type, nth in wanted_rows(ob):
                r = cb.rows.add()
                r.kind, r.name, r.mod_type, r.nth = kind, name, mod_type, nth
        cb.rows_sig = sig
    finally:
        _rows_state["busy"] = False
    return True


def row_for(context, ob, kind, name, mod_type="", nth=0):
    """The text row to draw, or None when the rows are stale (then draw the real property)."""
    cb = context.scene.allset_cb
    if cb.rows_sig != rows_signature(ob):
        return None
    for r in cb.rows:
        if r.kind == kind and r.name == name and r.mod_type == mod_type and r.nth == nth:
            return r
    return None


def _nothing_selected(context):
    sel = getattr(context, "selected_objects", None)
    if sel is None:
        return False     # a window context without a view layer (File Browser, Preferences)
    if getattr(context.window_manager, "allset_character_nodes", ""):
        return False     # picked character nodes stand in for the selection
    if pose_armature(context) is not None:
        return not selected_bones(context)
    return not sel


@persistent
def _on_depsgraph(_scene, _depsgraph):
    if selected_channels() and _nothing_selected(bpy.context):
        set_selected_channels([])      # Maya: deselecting everything also deselects the channels
    rebuild_rows()
    # The dock is a custom PROPERTIES-area UI, not Blender's native transform
    # sidebar. Tag it explicitly: transform gizmos can update RNA values without
    # invalidating the Channel Box panel's drawn value fields.
    from . import maya_dock
    maya_dock.redraw()


@persistent
def _on_load(_dummy):
    global _wheel_generation
    _wheel_generation += 1
    _wheel_windows.clear()
    _last.clear()
    reset_open()
    rebuild_rows()


_transform_snapshot = None


def _transforming():
    """A transform modal (manipulator drag, G / R / S) runs in some window."""
    wm = bpy.context.window_manager
    from ..operators.manip_scale import TRANSFORM_MODALS
    return wm is not None and any(op.bl_idname.startswith(TRANSFORM_MODALS)
                                  for w in wm.windows for op in w.modal_operators)


def _poll_transform_values():
    """Refresh displayed transform channels even during modal gizmo movements."""
    global _transform_snapshot
    try:
        ob = lead()
        if ob is None:
            signature = None
        elif is_bone(ob):
            signature = (ob.id_data.as_pointer(), ob.name, tuple(v for row in ob.matrix for v in row))
        else:
            signature = (ob.as_pointer(), tuple(ob.location), tuple(ob.rotation_euler),
                         tuple(ob.rotation_quaternion), tuple(ob.rotation_axis_angle),
                         tuple(ob.scale), ob.rotation_mode, ob.hide_viewport)
        # Redraw when the lead's channels changed, and on every tick while a transform modal runs (its RNA values
        # can stay the same between ticks while the drawn fields are stale); idle ticks draw nothing.
        if signature != _transform_snapshot or _transforming():
            _transform_snapshot = signature
            from . import maya_dock
            maya_dock.redraw()
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return 0.1


def _first_rebuild():
    rebuild_rows()
    return None


def _draw_text_row(layout, context, ob, owner, prop, kind, mod_type="", nth=0, label=None):
    """A SHAPES / INPUTS row: label + text field applied to all selected (else the real prop)."""
    v = _virtual(owner, prop)
    if label is None:
        label = v.label if v is not None else owner.bl_rna.properties[prop].name
    row = row_for(context, ob, kind, prop, mod_type, nth)
    # the channel rows' geometry (draw_channel_row): the name centred in the left half, the field, then the state
    # icon's column, so SHAPES / INPUTS values line up under Translate X ... (Maya: one value column)
    line = layout.row(align=True)
    split = line.split(factor=0.5, align=True)
    if kind in ("SHAPE", "INPUT") and row is not None:
        # a SHAPES / INPUTS row is a channel: selectable name (MMB virtual slider, value drag), keyed / animated
        # state like Translate X
        key = row_key(row)
        sub = split.row(align=True)
        sub.prop(row, "sel", text=label, toggle=True, emboss=key in selected_channels(context))
        right = split.row(align=True)
        state = channel_state(ob, key)
        right.alert = state in _ALERT_STATES
        right.prop(row, "text", text="")
        line.label(text="", icon=_STATE_ICON.get(state, 'BLANK1'))
        return
    name = split.row(align=True)
    name.alignment = 'CENTER'
    name.label(text=label)
    right = split.row(align=True)
    if row is None:
        if v is not None:   # a Maya attribute has no RNA property to draw until the rows are rebuilt
            right.label(text=cb_entry.format_value(v.get(owner), v.kind, context.scene))
        else:
            right.prop(owner, f'["{prop}"]' if kind == "CUSTOM" else prop, text="")
    else:
        right.prop(row, "text", text="")
    line.label(text="", icon='BLANK1')


# --- lines: the Channel Box below its name row is a fixed pane that scrolls (#55) ---------------------------
# Maya keeps the Channel Box / Layer Editor split and scrolls a long Channel Box inside its part.
# Blender can't scroll part of a region, so every Channel Box row
# under the lead's name is one equal line (ROW_SCALE) of one aligned column, and the pane draws the lines that fit.

_scroll = {}    # area pointer -> first line shown
_reveal = {"node": None}    # an INPUTS node key to scroll into view at the next draw (``reveal``)
_last = {}      # area pointer -> (first, total, limit) of the last draw (limit None: every line fits)
_filled = {}    # area pointer -> UI units from the region top that the Channel Box rows use (empty space below)
WHEEL_LINES = 3     # Maya: one notch = 15 px x QApplication.wheelScrollLines 3 = 45 px ~ 3 rows (PR #125 check)
BUTTON_LINES = 3
_wheel_windows = {}   # live window pointer -> registration generation
_wheel_generation = 0


class Lines:
    """An aligned column of equal rows that shows only rows ``first`` .. ``first + limit`` (``layout`` None: count)."""

    def __init__(self, layout, first=0, limit=None):
        self.layout = layout
        self.first = first
        self.limit = limit
        self.n = 0
        self.shown = 0
        self.marks = {}     # INPUTS node key -> its line index (``reveal``)

    def row(self):
        i = self.n
        self.n += 1
        if self.layout is None or i < self.first or (self.limit is not None and self.shown >= self.limit):
            return None
        self.shown += 1
        return self.layout.row(align=True)


def reveal(node):
    """Scroll the Channel Box to INPUTS node ``node`` at its next draw."""
    _reveal["node"] = node


def as_lines(layout):
    return layout if isinstance(layout, Lines) else Lines(layout)


def window_lines(total, room, first):
    """(first, limit, overflow) for ``total`` lines in a pane of ``room`` lines. The scroll buttons sit on the lead's
    name line (on the last content line they took the place of the node that was just expanded)."""
    if room is None or total <= room:
        return 0, None, False
    limit = max(1, room)
    return max(0, min(first, total - limit)), limit, True


def _unit(context):
    system = context.preferences.system
    return _round_half_up(18.0 * system.ui_scale) + 2 * system.pixel_size


def _split_off(context):
    sdk = getattr(context.window_manager, "allset_sdk", None)
    return sdk is not None and sdk.open    # the Set Driven Key window takes the Layer Editor's place


def pane_room(context, units):
    """Lines that fit in the Channel Box part (CB_SHARE of the region) under ``units`` of fixed rows; None = no
    split (no region: headless drawing, or the Set Driven Key window)."""
    region = context.region
    if region is None or region.type not in {'UI', 'WINDOW'} or _split_off(context):
        return None
    u = _unit(context)
    if u <= 0 or region.height <= 0:
        return None
    room = (cb_share(region, u) * region.height / u - units - PANE_TOP - 0.3) / ROW_SCALE
    return max(2, int(room + 1e-6))    # 11.2 / 0.8 = 13.999...: don't lose the last line to rounding


def node_row(lines, ob, node, label, tip="", active=True):
    """An INPUTS node name: Maya's indented, flat, click-to-expand row. Returns (row or None, expanded)."""
    opened = is_open(ob, node)
    if isinstance(lines, Lines):
        lines.marks[node] = lines.n
    row = lines.row()
    if row is not None:
        name = row.row(align=True)
        name.alignment = 'LEFT'
        name.active = active
        name.separator(factor=1.5)
        op = name.operator(ALLSET_OT_cb_node_toggle.bl_idname, text=label, emboss=False)
        op.node = node
        op.tip = tip
    return row, opened


class ALLSET_OT_cb_node_toggle(bpy.types.Operator):
    """Show or hide this node's attributes (Maya: click the node name in INPUTS)"""
    bl_idname = "allset.cb_node_toggle"
    bl_label = "Expand Node"
    bl_options = {'INTERNAL'}     # no undo step: Maya's expansion is UI state

    node: StringProperty(options={'SKIP_SAVE'})
    tip: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return props.tip or cls.__doc__

    def execute(self, context):
        ob = lead(context)
        if ob is None or not self.node:
            return {'CANCELLED'}
        set_open(ob, self.node, not is_open(ob, self.node))
        rebuild_rows(context)
        _redraw(context.window)
        return {'FINISHED'}


def _is_cb_dock(context):
    area, region = context.area, context.region
    if area is None or region is None or area.type != 'PROPERTIES' or region.type != 'WINDOW':
        return False
    from . import maya_dock
    return maya_dock.shown_kind(context) == 'CHANNEL_BOX'


def in_channel_part(context, event):
    """The mouse is over the Channel Box part of a Maya dock (above the Layer Editor), cells or not."""
    if not _is_cb_dock(context):
        return False
    region = context.region
    from_top = region.height - event.mouse_region_y
    return 0 <= from_top <= cb_share(region, _unit(context)) * region.height


def over_pane(context, event):
    """The mouse is over an overflowing Channel Box part of a Maya dock."""
    area, region = context.area, context.region
    if area is None or region is None or area.type != 'PROPERTIES' or region.type != 'WINDOW':
        return False
    from . import maya_dock
    if maya_dock.shown_kind(context) != 'CHANNEL_BOX':
        return False
    if _last.get(area.as_pointer(), (0, 0, None))[2] is None:
        return False
    from_top = region.height - event.mouse_region_y
    return 0 <= from_top <= cb_share(region, _unit(context)) * region.height


def scroll_lines(context, amount):
    """Move only the virtual Channel Box rows, never values or the Layer Editor."""
    area = context.area
    if area is None:
        return False
    ptr = area.as_pointer()
    first, total, limit = _last.get(ptr, (0, 0, None))
    if limit is None:
        return False
    first = _scroll.get(ptr, first)  # several wheel events may arrive before the next redraw
    _scroll[ptr] = max(0, min(first + amount, max(0, total - limit)))
    if _scroll[ptr] != first and context.window is not None:
        # New rows can appear under a stationary cursor; never retain the old
        # channel hit for the next click or drag.
        _hover.pop(context.window.as_pointer(), None)
    area.tag_redraw()
    return True


class ALLSET_OT_cb_wheel(bpy.types.Operator):
    """Catch Channel Box scrolling before Blender's field and panel handlers"""
    bl_idname = 'allset.cb_wheel'
    bl_label = 'Channel Box Wheel Navigation'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if context.window is None:
            return {'CANCELLED'}
        self._window_ptr = context.window.as_pointer()
        self._generation = _wheel_generation
        self._fraction = {}
        _wheel_windows[self._window_ptr] = self._generation
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        from .. import live_refs
        window = live_refs.window(self._window_ptr)
        if self._generation != _wheel_generation or window is None:
            if _wheel_windows.get(self._window_ptr) == self._generation:
                _wheel_windows.pop(self._window_ptr, None)
            return {'CANCELLED', 'PASS_THROUGH'}
        if (event.type not in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN'} or event.oskey):
            return {'PASS_THROUGH'}
        # Resolve the current regions each event: panes can resize, change tabs,
        # move to another window, or close while this window watcher is running.
        x, y = event.mouse_x, event.mouse_y
        for area in window.screen.areas:
            if area.type != 'PROPERTIES':
                continue
            for region in area.regions:
                if (region.type != 'WINDOW' or not region.x <= x < region.x + region.width
                        or not region.y <= y < region.y + region.height):
                    continue
                with context.temp_override(window=window, area=area, region=region):
                    ctx = bpy.context
                    from . import maya_dock
                    if x >= region.x + region.width - maya_dock.area_reserved_px(ctx):
                        return {'PASS_THROUGH'}
                    from types import SimpleNamespace
                    if not over_pane(ctx, SimpleNamespace(mouse_region_y=y - region.y)):
                        return {'PASS_THROUGH'}
                    if event.ctrl or event.shift or event.alt:
                        hit = _hover.get(self._window_ptr)
                        if (event.ctrl and event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}
                                and hit is not None and hit[1] == 'VALUE'
                                and field_drag_starts(ctx, hit[0])):
                            start_field_drag(ctx, event, hit[0], event.mouse_x)
                            # The gesture belongs to the field even at a limit or
                            # on a rounded no-op; don't send it on to the UI too.
                            return {'RUNNING_MODAL'}
                        return {'PASS_THROUGH'}
                    if event.type == 'TRACKPADPAN':
                        ptr = area.as_pointer()
                        delta = (event.mouse_prev_y - event.mouse_y) / row_pitch(ctx)
                        fraction = self._fraction.get(ptr, 0.0) + delta
                        amount = int(fraction)
                        self._fraction[ptr] = fraction - amount
                    else:
                        amount = WHEEL_LINES if event.type == 'WHEELDOWNMOUSE' else -WHEEL_LINES
                    scroll_lines(ctx, amount)
                    return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


def _ensure_wheel_watch():
    if bpy.app.background:
        return None
    for window in bpy.context.window_manager.windows:
        if _wheel_windows.get(window.as_pointer()) == _wheel_generation:
            continue
        for area in window.screen.areas:
            if area.type != 'PROPERTIES':
                continue
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if region is None:
                continue
            with bpy.context.temp_override(window=window, area=area, region=region):
                if _is_cb_dock(bpy.context):
                    bpy.ops.allset.cb_wheel('INVOKE_DEFAULT', True)
                    break
    return 0.25


class ALLSET_OT_cb_scroll(bpy.types.Operator):
    """Scroll the Channel Box (Maya: its own scroll bar; the Layer Editor below stays)"""
    bl_idname = "allset.cb_scroll"
    bl_label = "Scroll Channel Box"
    bl_options = {'INTERNAL'}

    lines: IntProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            if event.ctrl or event.shift or event.alt or not over_pane(context, event):
                return {'PASS_THROUGH'}
            self.lines = WHEEL_LINES if event.type == 'WHEELDOWNMOUSE' else -WHEEL_LINES
        return self.execute(context)

    def execute(self, context):
        return {'FINISHED'} if scroll_lines(context, self.lines) else {'CANCELLED'}


def _scroll_row(col, first, limit, total):
    row = col.row(align=True)
    row.alignment = 'RIGHT'
    for lines, icon, on in ((-BUTTON_LINES, 'TRIA_UP', first > 0), (BUTTON_LINES, 'TRIA_DOWN', first + limit < total)):
        sub = row.row(align=True)
        sub.enabled = on
        sub.operator(ALLSET_OT_cb_scroll.bl_idname, text="", icon=icon, emboss=False).lines = lines


COMPONENT_TYPES = {'MESH', 'CURVE', 'SURFACE', 'LATTICE'}


def component_mode(ob):
    """Maya component mode on the lead: a mesh / curve / surface / lattice object in edit mode (armature edit mode is
    joint placement, PLACING_TEXT)."""
    return ob is not None and not is_bone(ob) and ob.type in COMPONENT_TYPES and ob.mode == 'EDIT'


def _draw_component_lines(lines, context, ob):
    """Component mode under the shape's name: the CVs line / table (points selected), then INPUTS."""
    cb_points.draw(lines, context, ob)
    draw_inputs(lines, context, ob)


def _draw_lines(lines, context, ob, cb, sel, blue):
    """Every Channel Box line under the lead's name: channels, SHAPES, INPUTS (collapsed nodes)."""
    for key, _label, _path, _idx, kind in MAIN:
        if is_hidden(ob, key):
            continue
        if kind == "ROT" and not has_channel(ob, key):
            continue
        r = lines.row()
        if r is not None:
            draw_channel_row(r, ob, key, cb, key + "_text", key in sel, key in blue, cb, key + "_sel")
    if not has_channel(ob, "rx"):
        r = lines.row()
        if r is not None:
            r.label(text=f"Rotation mode {ob.rotation_mode}")
        r = lines.row()
        if r is not None:
            r.prop(ob, "rotation_quaternion" if ob.rotation_mode == 'QUATERNION' else "rotation_axis_angle", text="")
        r = lines.row()
        if r is not None:
            r.operator(ALLSET_OT_cb_rotate_order.bl_idname, text="Rotate Order XYZ").order = 'XYZ'
    for name in custom_keys(ob):
        key = CUSTOM_PREFIX + name
        if is_hidden(ob, key):
            continue
        r = lines.row()
        if r is None:
            continue
        row = row_for(context, ob, "CUSTOM", name)
        if row is not None:
            draw_channel_row(r, ob, key, row, "text", key in sel, sel_owner=row, sel_prop="sel")
        else:
            draw_channel_row(r, ob, key, ob, f'["{name}"]', key in sel)
    # #165: a joint's Radius under Visibility (Maya joint.radius, non-keyable; operators/joint_display.py)
    if is_bone(ob) and hasattr(ob.bone, "allset_joint_radius"):
        r = lines.row()
        if r is not None:
            split = r.row(align=True).split(factor=0.5, align=True)
            split.alignment = 'RIGHT'
            split.label(text="Radius")
            split.prop(ob.bone, "allset_joint_radius", text="")
            r.label(text="", icon='BLANK1')

    # SHAPES: the shape name is a rename field (Maya); camera / light shapes show
    # their attributes expanded
    data = getattr(ob, "data", None)
    if data is not None:
        r = lines.row()
        if r is not None:
            r.label(text="SHAPES")
        r = lines.row()
        if r is not None:
            # Maya draws the shape row as a darker full-width bar (its rename field,
            # #373737): an embossed field
            r.separator(factor=1.5)
            r.prop(data, "name", text="")
        for prop in SHAPE_PROPS.get(ob.type, ()):
            if hasattr(data, prop) or _virtual(data, prop) is not None:
                r = lines.row()
                if r is not None:
                    _draw_text_row(r, context, ob, data, prop, "SHAPE", label=shape_label(ob, prop))

    draw_inputs(lines, context, ob)


def draw_inputs(lines, context, ob):
    """INPUTS, newest first; every node starts collapsed (Maya).
    Maya treats Smooth Mesh Preview as a shape display attribute, not an input node."""
    inputs = _inputs(ob)
    cons = constraints(ob)
    from . import in_view
    last = in_view.cb_record(context, ob)    # the last kit extrusion = Maya's newest history node
    from . import creation_inputs
    created = creation_inputs.has_node(ob)   # the primitive's creation node, oldest history
    key = blend_shape_key(ob)                # the mesh's blendShape node (#204)
    if not (inputs or cons or last is not None or created or key is not None):
        return
    r = lines.row()
    if r is not None:
        r.label(text="INPUTS")
    if last is not None:
        in_view.draw_cb_node(lines, context, last)
    from . import attribute_editor
    for mod in inputs:
        # the Maya node name the Attribute Editor shows (Blender's automatic "Armature" = skinCluster1, #97)
        try:
            label = attribute_editor.modifier_node(ob, mod)[0]
        except ValueError:      # a deformer on another object (lattice / handle INPUTS)
            label = mod.name
        row, opened = node_row(lines, ob, mod_node(mod), label)
        if row is not None:
            row.prop(mod, "show_viewport", text="")
        if opened:
            for prop in _modifier_props(mod):
                r = lines.row()
                if r is not None:
                    _draw_text_row(r, context, ob, mod, prop, "INPUT", mod.type, _nth_of_type(ob, mod))
    if key is not None:
        # shape keys are evaluated before every modifier: below the modifiers, above the creation node (Maya:
        # polyBevel1, blendShape1, polyCube1)
        draw_blend_shape(lines, context, ob, key)
    if created:
        creation_inputs.draw_cb(lines, context, ob)
    from ..operators import constrain_multi
    for con in cons:
        mb = constrain_multi.member(con, ob)
        if mb is not None:
            if constrain_multi.is_head(con, ob):
                _draw_group(lines, context, ob, con, mb)
            continue
        # Maya constraint node + its target weight
        row, opened = node_row(lines, ob, con_node(ob, con), constraint_node_name(ob, con),
                               active=constraint_enabled(con))
        if row is not None and hasattr(con, "enabled"):
            row.prop(con, "enabled", text="")
        if opened:
            r = lines.row()
            if r is not None:
                _draw_text_row(r, context, ob, con, "influence", "CONSTRAINT", con.type,
                               _nth_constraint(ob, con), label=weight_name(con))


def blend_shape_key(ob):
    """The mesh's shape keys = its Maya blendShape node (named blendShapeN, as in the Shape Editor), or None."""
    if not isinstance(ob, bpy.types.Object) or ob.type != 'MESH':
        return None
    key = ob.data.shape_keys
    return key if key is not None and len(key.key_blocks) else None


def blend_shape_node(key):
    return "bs:" + key.name


def blend_shape_targets(key):
    """The key blocks Maya lists as targets: every block after the Basis but the kit's hidden in-between keys."""
    from ..operators import blend_shapes_227
    hidden = blend_shapes_227.helper_names(key)
    return [kb for i, kb in enumerate(key.key_blocks) if i and kb.name not in hidden]


def draw_blend_shape(lines, context, ob, key):
    """Maya's blendShape node in INPUTS: Envelope, then one weight row per target named after it. Blender has no
    envelope: it reads 1, like the Shape Editor."""
    _row, opened = node_row(lines, ob, blend_shape_node(key), key.name)
    if not opened:
        return
    rows = [("Envelope", None)] + [(kb.name, kb) for kb in blend_shape_targets(key)]
    for label, kb in rows:
        r = lines.row()
        if r is None:
            continue
        line = r.row(align=True)
        split = line.split(factor=0.5, align=True)
        if kb is None:
            name = split.row(align=True)
            name.alignment = 'CENTER'
            name.label(text=label)
            right = split.row(align=True)
            right.enabled = False
            right.label(text=cb_entry.format_value(1.0, "NONE", context.scene))
            line.label(text="", icon='BLANK1')
            continue
        row = row_for(context, ob, "BLEND", kb.name)
        if row is None:     # rows not rebuilt yet: the real value
            name = split.row(align=True)
            name.alignment = 'CENTER'
            name.label(text=label)
            split.row(align=True).prop(kb, "value", text="")
            line.label(text="", icon='BLANK1')
            continue
        # a target weight is a channel like Translate X: selectable name, keyed / animated state (Key Selected)
        key = row_key(row)
        sub = split.row(align=True)
        sub.prop(row, "sel", text=label, toggle=True, emboss=key in selected_channels(context))
        right = split.row(align=True)
        state = channel_state(ob, key)
        right.alert = state in _ALERT_STATES
        right.prop(row, "text", text="")
        line.label(text="", icon=_STATE_ICON.get(state, 'BLANK1'))


def _draw_group(lines, context, ob, con, mb):
    """A kit multi-target constraint = one Maya node: its state toggles every member, its rows are the target weights
    <target>W0, W1 ... (operators/constrain_multi.py)."""
    from ..operators import constrain_multi
    on = constraint_enabled(con)
    row, opened = node_row(lines, ob, con_node(ob, con), constraint_node_name(ob, con), active=on)
    if row is not None:
        op = row.operator("allset.constraint_group_enable", text="", emboss=False,
                          icon='CHECKBOX_HLT' if on else 'CHECKBOX_DEHLT')
        op.object = ob.id_data.name
        op.bone = ob.name if is_bone(ob) else ""
        op.group = mb.group
    if opened:
        if constrain_multi.group_type(con, ob) in ("orientConstraint", "parentConstraint"):
            r = lines.row()
            if r is not None:
                _draw_interp_row(r, ob, mb.group)
        for prop, label in constrain_multi.weights(ob, mb.group):
            if prop not in ob.keys():
                continue
            r = lines.row()
            if r is not None:
                _draw_text_row(r, context, ob, ob, prop, "CUSTOM", label=label)


def _draw_interp_row(layout, ob, group):
    """Maya's keyable Interp Type of an orient / parent constraint (enum, default Average; #168)."""
    from ..operators import constrain_interp
    mode = constrain_interp.mode_of(ob, group)
    line = layout.row(align=True)
    split = line.split(factor=0.5, align=True)
    name = split.row(align=True)
    name.alignment = 'CENTER'
    name.label(text="Interp Type")
    right = split.row(align=True)
    right.context_pointer_set("allset_interp_owner", ob)
    right.context_string_set("allset_interp_group", group)
    right.menu(ALLSET_MT_cb_interp.bl_idname,
               text=constrain_interp.NAMES[constrain_interp.SHORTEST if mode is None else mode])
    line.label(text="", icon='BLANK1')


class ALLSET_MT_cb_interp(bpy.types.Menu):
    bl_idname = "ALLSET_MT_cb_interp"
    bl_label = "Interp Type"

    def draw(self, context):
        from ..operators import constrain_interp
        owner = getattr(context, "allset_interp_owner", None)
        group = getattr(context, "allset_interp_group", "")
        if owner is None or not group:
            return
        for i, n in enumerate(constrain_interp.NAMES):
            op = self.layout.operator("allset.constraint_interp", text=n)
            op.object = owner.id_data.name
            op.bone = owner.name if is_bone(owner) else ""
            op.group = group
            op.mode = str(i)


class ALLSET_PT_channel_box(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY
    bl_label = "Channel Box"
    bl_order = 0
    bl_options = {'HIDE_HEADER'}   # Maya: a menu bar, no collapsible panel title

    # Not registered: ui/maya_dock.ALLSET_PT_maya_dock draws ``body`` in the Maya dock areas.

    def draw(self, context):
        units = ALLSET_PT_channel_box.body(self.layout, context)
        fill_pane(self.layout, context, units)

    @staticmethod
    def body(layout, context):
        """Draw the Channel Box; returns its height in UI units (estimate, for the CB_SHARE pane). The row above it
        (Maya's title / tab row) is the dock's handle + tab row (ui/maya_dock.py)."""
        # Early-return views (paint tools, no selection, joint placement) use
        # native region scrolling and must not retain an old virtual-row range.
        if context.area is not None:
            _last.pop(context.area.as_pointer(), None)
        # a dock narrower than Maya's Channel Box (user-sized, or not fitted yet) wraps the menu bar instead of
        # cutting "Channels" to "Chann..." (same rule as the AE bar)
        from .attribute_editor import wrap_rows
        rows = wrap_rows(context, [label for label, _m in MENU_BAR], equal=False)
        for idx in rows:
            chrome.menu_bar(layout, [MENU_BAR[i] for i in idx])
        units = 1.0 + len(rows)
        # Paint Skin Weights: the Channel Box stays the Channel Box (no Maya version puts paint UI here, PR #125
        # check 9c); the paint settings are the Tool Settings dock (ui/tool_settings.draw_dock)
        if placing_joints(context):
            # armature edit mode = joint placement (#160): the lead joint's Maya Translate
            # (position in the parent's Maya frame) is typed here like Maya's Channel Box
            extra = draw_joint_translate(layout, context)
            layout.separator(factor=2)
            chrome.wrapped(layout, PLACING_TEXT)
            return units + 0.5 + extra + len(PLACING_TEXT)
        ob = lead(context)
        comp = component_mode(ob)
        if ob is None or (comp and not cb_points.has_selection(ob)):
            # Maya: component mode with nothing selected = the empty Channel Box too
            draw_empty(layout)
            return units + 4.2 + len(EMPTY_TEXT)
        units += 1.0
        cb = context.scene.allset_cb
        sel = set(selected_channels(context))
        head = layout.row(align=True)
        # Maya: the lead's name as plain text; a click edits it (a borderless Blender text field would need a
        # double-click)
        name = head.row(align=True)
        name.alignment = 'LEFT'
        if comp:
            # Maya component mode: the shape node, then INPUTS — no transform channels, no SHAPES header
            # (as Maya)
            name.operator(ALLSET_OT_cb_rename.bl_idname, text=ob.data.name, emboss=False, translate=False)
            args = (context, ob)
            draw = _draw_component_lines
        else:
            name.operator(ALLSET_OT_cb_rename.bl_idname, text=ob.name, emboss=False, translate=False)
            args = (context, ob, cb, sel, constrained_keys(ob))
            draw = _draw_lines
        n = len(targets(context))
        if n > 1:
            head.label(text=f"+{n - 1}")
        if not is_bone(ob) and ob.type == 'ARMATURE' and ob.mode == 'OBJECT':
            hint = layout.row()
            hint.active = False
            hint.label(text=POSE_HINT)
            units += 1.0
        count = Lines(None)
        draw(count, *args)      # first pass: how many lines (also resets the expansion on a new lead)
        area = context.area
        ptr = area.as_pointer() if area is not None else 0
        start = _scroll.get(ptr, 0)
        if _reveal["node"] in count.marks:
            # a node picked from the RMB Inputs / Outputs list: scroll it to the top of the Channel Box
            # part, like Maya shows the selected node's attributes
            start = count.marks[_reveal["node"]]
            _reveal["node"] = None
        first, limit, over = window_lines(count.n, pane_room(context, units), start)
        if over:
            _scroll[ptr] = first
        col = layout.column(align=True)
        # Maya channel rows are 16 px with 11 px text; Blender rows are 20 px at scale 1.0.
        col.scale_y = ROW_SCALE
        lines = Lines(col, first, limit)
        draw(lines, *args)
        shown = lines.shown
        if over:
            _scroll_row(head, first, limit, count.n)
        _last[ptr] = (first, count.n, limit)
        return units + shown * ROW_SCALE + 0.3


def fill_pane(layout, context, units):
    """Empty space under the Channel Box so the Layer Editor starts at CB_SHARE of the dock height, like Maya's
    fixed split (a longer Channel Box scrolls inside its part, ``Lines``)."""
    region = context.region
    if units is None or region is None or region.type not in {'UI', 'WINDOW'} or _split_off(context):
        return
    u = _unit(context)
    if u <= 0:
        return
    if context.area is not None:
        _filled[context.area.as_pointer()] = units + PANE_TOP
    gap = cb_share(region, u) * region.height / u - units - PANE_TOP
    if gap > 0.25:
        col = layout.column()
        col.scale_y = gap
        col.label(text="")


# panel margins, row spacing and the Layer Editor's splitter, in UI units. The 3D View sidebar draws 2.2;
# the dock's Properties region draws them 0.6-0.7 U shorter (shots at UI 1.0 / 1.25 / 1.5: 4.9 / 4.8 / 4.8 U of
# fixed rows against the 5.5 the model assumed), which cost a line and left 1.5 rows empty above the Layer Editor (#83)
PANE_TOP = 1.6


class ALLSET_PT_dock_attribute_editor(bpy.types.Panel):
    """Maya Attribute Editor tab of the dock"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = AE_CATEGORY
    bl_label = "Attribute Editor"
    bl_order = 0
    bl_options = {'HIDE_HEADER'}

    def draw(self, context):
        from . import attribute_editor
        attribute_editor.draw_panel(self.layout, context)


class ALLSET_PT_dock_modeling_toolkit(bpy.types.Panel):
    """Maya Modeling Toolkit tab of the dock"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = MTK_CATEGORY
    bl_label = "Modeling Toolkit"
    bl_order = 0
    bl_options = {'HIDE_HEADER'}

    def draw(self, context):
        from . import modeling_toolkit
        modeling_toolkit.draw(self.layout, context)


classes = (ALLSET_PG_cb_row, ALLSET_PG_channel_box, ALLSET_OT_cb_virtual_slider, ALLSET_OT_cb_select_channel,
           ALLSET_OT_cb_deselect_channels, ALLSET_OT_cb_hover, ALLSET_OT_cb_channel_drag, ALLSET_OT_cb_field_drag,
           ALLSET_PT_cb_field, ALLSET_PT_cb_name, ALLSET_OT_cb_rename, ALLSET_OT_cb_node_toggle, ALLSET_OT_cb_scroll, ALLSET_OT_cb_wheel, *CHANNEL_OPS,
           ALLSET_OT_cb_show_all,
           ALLSET_MT_cb_channels, ALLSET_MT_cb_freeze, ALLSET_MT_cb_settings, ALLSET_OT_cb_make_lead,
           ALLSET_OT_cb_rotate_order, ALLSET_MT_cb_edit, ALLSET_MT_cb_interp,
           ALLSET_MT_cb_object, ALLSET_MT_cb_show)
# ALLSET_PT_channel_box / _dock_attribute_editor / _dock_modeling_toolkit are no longer registered as 3D View sidebar
# tabs: the Maya panels live in their own dock areas / floating windows (ui/maya_dock.py), which call
# ``ALLSET_PT_channel_box.body`` etc.


def register():
    global _wheel_generation
    _wheel_generation += 1
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.allset_cb = bpy.props.PointerProperty(type=ALLSET_PG_channel_box)
    bpy.types.WindowManager.allset_cb_selected = StringProperty(
        name="Selected Channels", options={'SKIP_SAVE'})
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.timers.register(_first_rebuild, first_interval=0.0)
    if not bpy.app.timers.is_registered(_poll_transform_values):
        bpy.app.timers.register(_poll_transform_values, first_interval=0.1)
    bpy.types.UI_MT_button_context_menu.prepend(draw_button_menu)
    if not bpy.app.background:
        bpy.app.timers.register(_ensure_wheel_watch, first_interval=0.0, persistent=True)


def unregister():
    global _transform_snapshot, _wheel_generation
    _wheel_generation += 1
    _wheel_windows.clear()
    if bpy.app.timers.is_registered(_ensure_wheel_watch):
        bpy.app.timers.unregister(_ensure_wheel_watch)
    _transform_snapshot = None
    if bpy.app.timers.is_registered(_poll_transform_values):
        bpy.app.timers.unregister(_poll_transform_values)
    _reveal["node"] = None
    _watching.clear()
    _hover.clear()
    reset_open()
    _last.clear()
    bpy.types.UI_MT_button_context_menu.remove(draw_button_menu)
    if bpy.app.timers.is_registered(_first_rebuild):
        bpy.app.timers.unregister(_first_rebuild)
    bpy.app.handlers.load_post.remove(_on_load)
    bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    del bpy.types.WindowManager.allset_cb_selected
    del bpy.types.Scene.allset_cb
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
