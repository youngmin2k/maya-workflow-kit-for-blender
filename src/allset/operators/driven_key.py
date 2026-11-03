# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Set Driven Key (Key > Set Driven Key > Set... / Go to Previous / Go to Next).

Maya's result is an animCurveUU from the driver attribute to the driven one.
Blender equivalent: a driver on the driven
channel (one variable ``sdk`` reading the driver channel, type AVERAGE = the variable) whose
F-curve has keys (driver value, driven value) — the same curve shape.
Values are raw RNA values (radians, metres), so the mapping is the one the user posed.

Blender writes a driver's result back over a typed value at the next update,
so while the Set Driven Key window is open, a Channel Box edit of a channel driven by a kit SDK
driver mutes that driver until Key (which records the pose) or Close (which drops it).
The window state lives on the WindowManager like a Maya window (not undoable, not saved).

Maya 2026 behaviour:
1. Curve shape = Maya 2026 ``auto`` tangents written by the kit (``maya_auto``): end keys flat, a key between two
   neighbours gets the slope (y[i+1] - y[i-1]) / (x[i+1] - x[i-1]), a local extreme is flat (sdk_three_keys: the
   middle key's slope is 9 = 90 / 10; sdk_four_keys_overshoot: both inner keys flat). Blender's own handle modes
   (Auto / Auto Clamped, with or without Continuous Acceleration) give other shapes,
   so the handles are ALIGNED at a third of each segment with that slope. Pre / post infinity Constant.
2. A second driver on the same driven channel = Maya ``blendWeighted`` (the inputs are **added**, sdk_two_drivers):
   every driver's curve sits on a hidden float ID property ``allset_sdk_<n>`` of the file's input helper (
   its own kit SDK driver, variable ``sdk``), and the channel's driver becomes a SUM over variables ``sdk``, ``sdk1`` ...
   reading those properties (``is_blend``). Key on a summed channel keys that driver's input so the sum equals the
   posed value (posed - the other inputs' current values; Maya keys one blendWeighted input).
3. Driven nodes besides objects / joints (Maya: any keyable attribute): a mesh's blendShape (its shape Key ID, one
   attribute per target = key block ``value``) and constraint nodes (Maya ``<target>W0`` = ``influence``, or the
   owner's ``allset_w_<constraint>`` weight property when a multi-target constraint group keeps one).
   Their values are not Channel Box channels, so posing them is held through msgbus (``_watch``), not WRITE_HOOKS.

#186: Blender doesn't order a driver that writes an ID property against another driver of the same ID
that reads it, so a SUM over inputs kept on the driven ID itself read a stale input now and then. The hidden inputs
live on their own data-block instead (like Maya's blendWeighted node): one hidden Texture per file (``helper``,
type NONE, fake user, marked ``HELPER``). Older files are moved over on load (``sync``), inputs a copied object
shares with its original get their own copy, and inputs no channel reads any more are dropped.
"""

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, PointerProperty, StringProperty

from .. import results
from ..ui import channel_box as cb

VAR = "sdk"          # the kit's driver variable name: marks a Set Driven Key driver
INPUT_PROP = "allset_sdk_"     # hidden blendWeighted input properties (channel_box.custom_keys hides allset_*)
SHAPE = "bs:"        # a blendShape target weight: key block ``value`` of a shape Key
WEIGHT = "cw"        # a constraint node's weight (<target>W0)
WEIGHT_PROP = "allset_w_"      # the Maya weight of a multi-target constraint group, on the owner
HELPER = "allset_blend_inputs" # marks the hidden Texture that holds the blendWeighted inputs
HELPER_NAME = ".allset_sdk"


# --- nodes ---------------------------------------------------------------------------------------

def node_of(ob, bone, kind="", sub=""):
    """The node an (object, bone, kind, sub) reference names: object / pose bone, its shape Key ('KEY') or one of
    its constraints ('CON', ``sub`` = constraint name)."""
    if ob is None:
        return None
    if kind == 'KEY':
        return getattr(getattr(ob, "data", None), "shape_keys", None)
    if bone:
        node = ob.pose.bones.get(bone) if ob.pose else None
    else:
        node = ob
    if kind == 'CON':
        return node.constraints.get(sub) if node is not None else None
    return node


def item_node(item):
    """The node of a window list item (ALLSET_PG_sdk_node)."""
    return node_of(item.object, item.bone, item.kind, item.sub)


def is_key(node):
    return isinstance(node, bpy.types.Key)


def is_constraint(node):
    return isinstance(node, bpy.types.Constraint)


def constraint_owner(con):
    """The object or pose bone holding ``con``."""
    ob = con.id_data
    if any(c == con for c in ob.constraints):
        return ob
    for pb in (ob.pose.bones if ob.pose else ()):
        if any(c == con for c in pb.constraints):
            return pb
    return None


def node_ref(node, ob=None):
    """(object, bone name, kind, sub) of a node; a shape Key needs ``ob`` (the object using it)."""
    if is_key(node):
        return ob, "", 'KEY', ""
    if is_constraint(node):
        owner = constraint_owner(node)
        o, b = (owner.id_data, owner.name) if cb.is_bone(owner) else (owner, "")
        return o, b, 'CON', node.name
    return ((node.id_data, node.name) if cb.is_bone(node) else (node, "")) + ("", "")


def store(item, node, ob=None):
    item.object, item.bone, item.kind, item.sub = node_ref(node, ob)


def node_label(node):
    """Maya's node name: blendShapeN (the Key), <owner>_<type>N (constraints), else the object / joint name."""
    if is_constraint(node):
        owner = constraint_owner(node)
        return cb.constraint_node_name(owner, node) if owner is not None else node.name
    return node.name


def extra_nodes(node):
    """Nodes listed under a loaded object / joint in the Driven list: its blendShape and its constraint nodes
    (IK constraints are Maya ikHandles: their ikBlend is the handle's custom attribute, ik_fk.IK_BLEND)."""
    if is_key(node) or is_constraint(node):
        return []
    out = []
    if not cb.is_bone(node):
        keys = getattr(getattr(node, "data", None), "shape_keys", None)
        if keys is not None and keys.use_relative and len(keys.key_blocks) > 1:
            out.append(keys)
    return out + [c for c in cb.constraints(node) if c.type != 'IK']


def channels(node):
    """The node's keyable attributes (Maya SDK lists the Channel Box ones)."""
    if is_key(node):     # Maya targets only: the hidden in-between helper keys are driven
        from . import blend_shapes_227
        return [SHAPE + b.name for b in blend_shapes_227.target_blocks(node)]
    if is_constraint(node):
        return [WEIGHT]
    keys = cb._visible_channels(node)
    return [k for k in keys if not (k == "v" and cb.is_bone(node))]


def attr_label(node, key):
    if key.startswith(SHAPE):
        return key[len(SHAPE):]                 # Maya: the target name (blendShape1.smile)
    if key == WEIGHT:
        return cb.weight_name(node) if is_constraint(node) else "W0"
    return cb.channel_label(key)


# --- channels ------------------------------------------------------------------------------------

class Chan:
    """One driven / driver attribute: the ID that holds its animation data, the full data path + index, the struct
    and attribute that hold the value, and the struct that takes hidden blendWeighted input properties."""
    __slots__ = ("id", "path", "index", "struct", "attr", "host")

    def __init__(self, id_, path, index, struct, attr, host):
        self.id, self.path, self.index, self.struct, self.attr, self.host = id_, path, index, struct, attr, host

    def get(self):
        if self.attr.startswith('["'):
            return float(self.struct[self.attr[2:-2]])
        value = getattr(self.struct, self.attr)
        return float(value[self.index] if self.index >= 0 else value)

    def set(self, value):
        if self.attr.startswith('["'):
            name = self.attr[2:-2]
            self.struct[name] = type(self.struct[name])(value)
            self.id.update_tag()
        elif self.index >= 0:
            getattr(self.struct, self.attr)[self.index] = value
        else:
            setattr(self.struct, self.attr, type(getattr(self.struct, self.attr))(value))

    @property
    def var_path(self):
        return self.path + (f"[{self.index}]" if self.index >= 0 else "")

    def find(self):
        ad = self.id.animation_data
        return None if ad is None else ad.drivers.find(self.path, index=max(self.index, 0))


def _quote(name):
    return name.replace("\\", "\\\\").replace('"', '\\"')


def _rel_path(host, rel):
    """Data path of ``rel`` (relative to ``host``) on the host's ID."""
    return host.path_from_id(rel) if cb.is_bone(host) else rel


def chan(node, key):
    """The Chan of channel ``key`` of ``node`` (None: no such channel)."""
    if node is None or not key:
        return None
    if is_key(node):
        block = node.key_blocks.get(key[len(SHAPE):]) if key.startswith(SHAPE) else None
        if block is None:
            return None
        return Chan(node, f'key_blocks["{_quote(block.name)}"].value', -1, block, "value", node)
    if is_constraint(node):
        owner = constraint_owner(node)
        if key != WEIGHT or owner is None:
            return None
        prop = WEIGHT_PROP + node.name
        if prop in owner.keys():
            attr = f'["{_quote(prop)}"]'
            return Chan(owner.id_data, _rel_path(owner, attr), -1, owner, attr, owner)
        return Chan(owner.id_data, _rel_path(owner, f'constraints["{_quote(node.name)}"].influence'), -1, node,
                    "influence", owner)
    if cb.is_shape_key(key) or key.startswith(SHAPE) or key == WEIGHT:
        return None
    if key.startswith(cb.CUSTOM_PREFIX):
        if key[len(cb.CUSTOM_PREFIX):] not in node.keys():
            return None
    elif key not in cb.MAIN_BY_KEY:
        return None
    path, idx, _kind = cb.channel_path(key)
    full = cb.full_path(node, path)
    if full is None:
        return None
    return Chan(node.id_data, full, idx, node, path, node)


def raw_value(node, key):
    return chan(node, key).get()


def set_raw_value(node, key, value):
    chan(node, key).set(value)


def _var_path(node, key):
    """Driver variable path of a channel on the node's ID (pose bones: on the armature object)."""
    return chan(node, key).var_path


def _id_type(id_):
    if isinstance(id_, bpy.types.Key):
        return 'KEY'
    return 'TEXTURE' if isinstance(id_, bpy.types.Texture) else 'OBJECT'


def is_sdk(fc):
    return fc is not None and fc.driver is not None and any(v.name == VAR for v in fc.driver.variables)


def is_blend(fc):
    """A summed (Maya blendWeighted) channel driver: SUM over the hidden input properties."""
    return is_sdk(fc) and fc.driver.type == 'SUM' and all(
        INPUT_PROP in v.targets[0].data_path for v in fc.driver.variables)


def sdk_fcurve(node, key):
    """The kit SDK driver F-curve of a driven channel (the one driver's curve, or the summed channel driver)."""
    c = chan(node, key)
    fc = c.find() if c is not None else None
    return fc if is_sdk(fc) else None


def _inputs(blend):
    """[(variable, input F-curve or None)] of a summed channel driver."""
    out = []
    for var in blend.driver.variables:
        t = var.targets[0]
        ad = t.id.animation_data if t.id is not None else None
        out.append((var, ad.drivers.find(t.data_path) if ad is not None else None))
    return out


def input_curves(node, key):
    """Every per-driver SDK curve of a driven channel: [the channel curve] or the blendWeighted inputs' curves."""
    fc = sdk_fcurve(node, key)
    if fc is None:
        return []
    if not is_blend(fc):
        return [fc]
    return [f for _v, f in _inputs(fc) if is_sdk(f)]


def _target(fc):
    return next(v for v in fc.driver.variables if v.name == VAR).targets[0]


def _reads(fc, d):
    t = _target(fc)
    return t.id == d.id and t.data_path == d.var_path


def driver_curve(driven, key, driver_node, driver_key):
    """The SDK curve of ``driven``.``key`` that reads ``driver_node``.``driver_key``, or None."""
    d = chan(driver_node, driver_key)
    if d is None:
        return None
    return next((fc for fc in input_curves(driven, key) if _reads(fc, d)), None)


LENGTH_KEYS = ("tx", "ty", "tz")


def curve_scale(driver_key):
    """Curve x per raw driver value. Blender merges F-curve keys less than 0.01 apart in x,
    and a length driver in the cm template moves 0.01 BU per cm: those curves keep x in display units."""
    from . import units
    k = units.maya_unit()
    return 1.0 / k if driver_key in LENGTH_KEYS and k < 1.0 else 1.0


def fcurve_scale(fc):
    """The x scale a kit SDK curve was made with (``sdk*<s>`` expression; plain average = 1)."""
    d = fc.driver
    if d.type == 'SCRIPTED' and d.expression.startswith(VAR + "*"):
        try:
            return float(d.expression[len(VAR) + 1:])
        except ValueError:
            return 1.0
    return 1.0


def input_x(fc):
    """The curve x a per-driver SDK curve sits at now (its driver's raw value x its scale)."""
    t = _target(fc)
    if t.id is None:
        return 0.0
    try:
        value = t.id.path_resolve(t.data_path)
    except ValueError:
        return 0.0
    return float(value) * fcurve_scale(fc)


def input_value(fc):
    """What a per-driver SDK curve gives now (0 for a curve without keys)."""
    return fc.evaluate(input_x(fc)) if len(fc.keyframe_points) else 0.0


# --- curve shape ----------------------------------------------------------------------------------

def maya_slopes(points):
    """Maya 2026 auto tangent slopes of sorted (x, y) keys (module docstring 1): ends and local extremes flat,
    else the neighbours' chord slope; the slope is limited so a handle never passes a neighbour's value [U: no
    known case reaches the limit]."""
    n = len(points)
    out = [0.0] * n
    for i in range(1, n - 1):
        (x0, y0), (x1, y1), (x2, y2) = points[i - 1], points[i], points[i + 1]
        if (y1 - y0) * (y2 - y1) <= 0.0 or x2 - x0 <= 0.0:
            continue
        s = (y2 - y0) / (x2 - x0)
        lim = min(3.0 * abs(y1 - y0) / max(x1 - x0, 1e-12), 3.0 * abs(y2 - y1) / max(x2 - x1, 1e-12))
        out[i] = max(-lim, min(lim, s))
    return out


def maya_auto(fc):
    """Bezier keys with Maya auto tangents: ALIGNED handles a third of each segment long."""
    kps = fc.keyframe_points
    for kp in kps:
        kp.interpolation = 'BEZIER'
        kp.handle_left_type = kp.handle_right_type = 'ALIGNED'
    fc.update()        # sorts the keys
    pts = [(kp.co[0], kp.co[1]) for kp in kps]
    slopes = maya_slopes(pts)
    n = len(pts)
    for i, kp in enumerate(kps):
        x, y = pts[i]
        dl = (x - pts[i - 1][0]) / 3.0 if i > 0 else ((pts[1][0] - x) / 3.0 if n > 1 else 1.0 / 3.0)
        dr = (pts[i + 1][0] - x) / 3.0 if i + 1 < n else dl
        kp.handle_left = (x - dl, y - slopes[i] * dl)
        kp.handle_right = (x + dr, y + slopes[i] * dr)
    fc.update()


# --- drivers -------------------------------------------------------------------------------------

def _set_target(var, c):
    t = var.targets[0]
    t.id_type = _id_type(c.id)
    t.id = c.id
    t.data_path = c.var_path


def _new_curve(c):
    """An empty driver curve on channel ``c`` (a driver already there is replaced: Maya replaces the connection)."""
    old = c.find()
    if old is not None:
        c.id.animation_data.drivers.remove(old)
    fc = c.id.driver_add(c.path, c.index) if c.index >= 0 else c.id.driver_add(c.path)
    # A new driver curve maps 1:1 — a Generator modifier in 4.5, two keys (0, 0) (1, 1) in 5.x
    #: SDK curves start empty either way.
    for mod in list(fc.modifiers):
        fc.modifiers.remove(mod)
    while len(fc.keyframe_points):
        fc.keyframe_points.remove(fc.keyframe_points[0], fast=True)
    fc.extrapolation = 'CONSTANT'   # Maya infinity Constant (5.x driver curves start LINEAR)
    return fc


def _sdk_curve(c, d, driver_key):
    """A new one-driver SDK curve on ``c`` reading driver channel ``d``."""
    fc = _new_curve(c)
    scale = curve_scale(driver_key)
    if scale != 1.0:   # a simple expression: no Python auto-run needed
        fc.driver.type = 'SCRIPTED'
        fc.driver.expression = f"{VAR}*{scale:g}"
    else:
        fc.driver.type = 'AVERAGE'
    var = fc.driver.variables.new()
    var.name = VAR
    var.type = 'SINGLE_PROP'
    _set_target(var, d)
    return fc


def is_helper(id_):
    return isinstance(id_, bpy.types.Texture) and bool(id_.get(HELPER))


def helpers():
    return [t for t in bpy.data.textures if t.get(HELPER)]


def helper(create=True):
    """The file's input helper: a hidden Texture (no users but its fake one; a NONE texture draws nothing)."""
    tex = next((t for t in helpers() if t.library is None), None)
    if tex is None and create:
        tex = bpy.data.textures.new(HELPER_NAME, 'NONE')
        tex.use_fake_user = True
        tex[HELPER] = 1
    return tex


def _new_input(c, value):
    """A hidden blendWeighted input property on the input helper, numbered one past the highest (Maya)."""
    tex = helper()
    taken = [int(k[len(INPUT_PROP):]) for k in tex.keys()
             if k.startswith(INPUT_PROP) and k[len(INPUT_PROP):].isdigit()]
    name = f"{INPUT_PROP}{max(taken) + 1 if taken else 0}"
    tex[name] = float(value)
    attr = f'["{name}"]'
    return Chan(tex, attr, -1, tex, attr, tex)


def _copy_var(src, dst):
    dst.name = src.name
    dst.type = src.type
    for a, b in zip(src.targets, dst.targets):
        if src.type == 'SINGLE_PROP':
            b.id_type = a.id_type
        b.id = a.id
        b.data_path = a.data_path
        b.bone_target = a.bone_target
        b.transform_type = a.transform_type
        b.transform_space = a.transform_space
        b.rotation_mode = a.rotation_mode


def _copy_curve(src, dst):
    n = len(src.keyframe_points)
    dst.keyframe_points.add(n)
    for a, b in zip(src.keyframe_points, dst.keyframe_points):
        b.co = a.co
        b.interpolation = a.interpolation
        b.handle_left_type, b.handle_right_type = a.handle_left_type, a.handle_right_type
        b.handle_left, b.handle_right = a.handle_left, a.handle_right
    dst.extrapolation = src.extrapolation
    dst.auto_smoothing = src.auto_smoothing
    dst.driver.type = src.driver.type
    dst.driver.expression = src.driver.expression
    dst.update()


def _blend_var(blend, inp):
    names = {v.name for v in blend.driver.variables}
    name = VAR if VAR not in names else next(f"{VAR}{i}" for i in range(1, 10000) if f"{VAR}{i}" not in names)
    var = blend.driver.variables.new()
    var.name = name
    var.type = 'SINGLE_PROP'
    _set_target(var, inp)
    return var


def _add_input(c, blend, d, driver_key):
    inp = _new_input(c, 0.0)
    fc = _sdk_curve(inp, d, driver_key)
    _blend_var(blend, inp)
    return fc


def to_blend(c, fc):
    """Move a one-driver SDK curve onto a hidden input property; the channel gets a SUM driver over it."""
    inp = _new_input(c, input_value(fc))
    moved = _new_curve(inp)
    _copy_curve(fc, moved)
    var = moved.driver.variables.new()
    var.name = VAR
    var.type = 'SINGLE_PROP'
    src = _target(fc)
    t = var.targets[0]
    t.id_type = src.id_type
    t.id = src.id
    t.data_path = src.data_path
    blend = _new_curve(c)          # removes the old channel driver
    blend.driver.type = 'SUM'
    _blend_var(blend, inp)
    return blend


def ensure_driver(driven, key, driver_node, driver_key):
    """The kit SDK curve of ``driven``.``key`` that reads ``driver_node``.``driver_key`` (made when missing;
    a second driver turns the channel into a Maya blendWeighted sum)."""
    c = chan(driven, key)
    d = chan(driver_node, driver_key)
    fc = c.find()
    if is_sdk(fc) and not is_blend(fc):
        if _reads(fc, d):
            return fc
        fc = to_blend(c, fc)
    if is_blend(fc):
        move_inputs(fc)       # an older file's inputs on the driven ID itself (normally done on load)
        for _var, inp in _inputs(fc):
            if is_sdk(inp) and _reads(inp, d):
                return inp
        return _add_input(c, fc, d, driver_key)
    return _sdk_curve(c, d, driver_key)


def set_key(driven, key, driver_node, driver_key):
    """One Set Driven Key key: (driver value, driven value) on the driven channel's curve for this driver."""
    c = chan(driven, key)
    y = c.get()          # held by a muted driver while posing, else the driven value
    fc = ensure_driver(driven, key, driver_node, driver_key)
    channel = c.find()
    if channel != fc:   # a blendWeighted input: the others' current values stay added
        y -= sum(input_value(f) for _v, f in _inputs(channel) if is_sdk(f) and f != fc)
    x = input_x(fc)
    for kp in fc.keyframe_points:
        if abs(kp.co[0] - x) < 1e-6:
            kp.co[1] = y
            break
    else:
        fc.keyframe_points.insert(x, y, options={'FAST'})
    maya_auto(fc)
    for f in (fc, channel):
        f.mute = False
        f.driver.is_valid = True
    return fc


def key_xs(fcs):
    return sorted({round(kp.co[0], 6) for fc in fcs for kp in fc.keyframe_points})


def step_to(xs, current, direction):
    """The key x after (NEXT) or before (PREVIOUS) ``current``, or None."""
    if direction == 'NEXT':
        return next((x for x in xs if x > current + 1e-6), None)
    return next((x for x in reversed(xs) if x < current - 1e-6), None)


def all_sdk_curves():
    for idb in (*bpy.data.objects, *bpy.data.shape_keys, *helpers()):
        ad = idb.animation_data
        if ad is None:
            continue
        for fc in ad.drivers:
            if is_sdk(fc):
                yield fc


# --- input helper upkeep ----------------------------------------------------------------

def _split_prop(path):
    """'pose.bones["j"]["allset_sdk_0"]' -> ('pose.bones["j"]', 'allset_sdk_0'); None when not an input path."""
    i = path.rfind('["')
    if i < 0 or not path.endswith('"]'):
        return None
    name = path[i + 2:-2]
    return (path[:i], name) if name.startswith(INPUT_PROP) else None


def _editable(id_):
    return id_ is not None and id_.library is None and getattr(id_, "override_library", None) is None


def _move_input(var, remove_old):
    """Give one blendWeighted input its own property on the file's helper: the value, the input's SDK curve and
    the summing variable move there. ``remove_old`` drops the old property and curve (a shared input keeps them)."""
    t = var.targets[0]
    old_id, path = t.id, t.data_path
    split = _split_prop(path)
    if old_id is None or split is None:
        return False
    prefix, name = split
    try:
        struct = old_id.path_resolve(prefix) if prefix else old_id
        value = struct[name]
    except (KeyError, ValueError):
        return False
    ad = old_id.animation_data
    old_fc = ad.drivers.find(path) if ad is not None else None
    inp = _new_input(None, value)
    if old_fc is not None:
        new_fc = _new_curve(inp)
        _copy_curve(old_fc, new_fc)
        for v in old_fc.driver.variables:
            _copy_var(v, new_fc.driver.variables.new())
        new_fc.mute = old_fc.mute
    t.id_type = 'TEXTURE'
    t.id = inp.id
    t.data_path = inp.var_path
    if remove_old and _editable(old_id):
        if old_fc is not None:
            ad.drivers.remove(old_fc)
        del struct[name]
    return True


def move_inputs(blend):
    """Move the inputs of a summed channel that still sit on another ID than the file's helper (an older file, a
    second helper brought in by append / paste); returns how many moved."""
    if not _editable(blend.id_data):
        return 0
    main = helper(create=False)
    n = 0
    for var in blend.driver.variables:
        t = var.targets[0]
        if t.id is None or (main is not None and t.id == main):
            continue
        n += _move_input(var, remove_old=not is_helper(t.id))
        main = helper(create=False)
    if n:
        blend.driver.is_valid = True
    return n


def _blend_curves():
    for idb in (*bpy.data.objects, *bpy.data.shape_keys):
        ad = idb.animation_data
        if ad is None:
            continue
        for fc in ad.drivers:
            if is_blend(fc):
                yield fc


def sync():
    """Keep every blendWeighted input on the file's helper, one channel per input (a duplicated object's summed
    channel gets copies of the inputs it shares with the original), and drop inputs no channel reads.
    Returns (moved, copied, dropped). Pushes no undo step: it runs on load and after object additions / removals."""
    moved = copied = dropped = 0
    blends = list(_blend_curves())
    for fc in blends:
        moved += move_inputs(fc)
    seen = set()
    for fc in blends:
        own = _editable(fc.id_data)
        for var in fc.driver.variables:
            t = var.targets[0]
            if t.id is None:
                continue
            key = (t.id.as_pointer(), t.data_path)
            if key in seen and own:
                copied += _move_input(var, remove_old=False)
                key = (t.id.as_pointer(), t.data_path)
            seen.add(key)
    for tex in helpers():
        if not _editable(tex):
            continue
        ad = tex.animation_data
        for name in [k for k in tex.keys() if k.startswith(INPUT_PROP)]:
            path = f'["{name}"]'
            if (tex.as_pointer(), path) in seen:
                continue
            fc = ad.drivers.find(path) if ad is not None else None
            if fc is not None:
                ad.drivers.remove(fc)
            del tex[name]
            dropped += 1
        if ad is not None:      # input curves whose property is gone
            for fc in [f for f in ad.drivers if (tex.as_pointer(), f.data_path) not in seen]:
                ad.drivers.remove(fc)
        if not any(k.startswith(INPUT_PROP) for k in tex.keys()):
            bpy.data.textures.remove(tex)
    return moved, copied, dropped


_COUNTS = [None]


def _counts():
    return len(bpy.data.objects), len(bpy.data.shape_keys), len(bpy.data.textures)


def sync_if_changed():
    """``sync`` when data-blocks were added or removed since the last look (duplicate, delete, append, paste)."""
    now = _counts()
    if now == _COUNTS[0]:
        return None
    out = sync() if helpers() or any(True for _ in _old_layout()) else (0, 0, 0)
    _COUNTS[0] = _counts()
    return out


def _old_layout():
    for fc in _blend_curves():
        if any(not is_helper(v.targets[0].id) for v in fc.driver.variables):
            yield fc


def release_all():
    """Unmute every kit SDK driver muted for posing; returns how many."""
    n = 0
    for fc in all_sdk_curves():
        if fc.mute:
            fc.mute = False
            n += 1
    return n


# --- window state ----------------------------------------------------------------------------------

class ALLSET_PG_sdk_node(bpy.types.PropertyGroup):
    object: PointerProperty(type=bpy.types.Object)
    bone: StringProperty()
    kind: StringProperty()     # '' object / joint, 'KEY' its blendShape, 'CON' its constraint ``sub``
    sub: StringProperty()


class ALLSET_PG_sdk_item(bpy.types.PropertyGroup):
    key: StringProperty()      # channel key (channel_box, or SHAPE / WEIGHT)
    label: StringProperty()


class ALLSET_PG_sdk(bpy.types.PropertyGroup):
    open: BoolProperty(name="Set Driven Key")
    driver: PointerProperty(type=ALLSET_PG_sdk_node)
    driver_attr: StringProperty()
    driven: CollectionProperty(type=ALLSET_PG_sdk_node)
    driven_index: IntProperty()
    driven_attrs: StringProperty()          # comma-separated channel keys
    # rows of the scrolling attribute lists (UIList needs collections); rebuilt by refresh_items()
    driver_items: CollectionProperty(type=ALLSET_PG_sdk_item)
    driver_items_index: IntProperty()
    driven_items: CollectionProperty(type=ALLSET_PG_sdk_item)
    driven_items_index: IntProperty()


def state(context=None):
    return (context or bpy.context).window_manager.allset_sdk


def driver_node(st):
    return item_node(st.driver)


def driven_nodes(st):
    return [n for n in (item_node(i) for i in st.driven) if n is not None]


def driven_keys(st):
    return [k for k in st.driven_attrs.split(",") if k]


def _fill(items, node, selected):
    items.clear()
    first = -1
    for i, key in enumerate(channels(node) if node is not None else ()):
        item = items.add()
        item.key, item.label = key, attr_label(node, key)
        if first < 0 and key in selected:
            first = i
    return max(first, 0)


def refresh_items(st):
    """Rebuild the attribute rows; the lists scroll to the first selected attribute."""
    st.driver_items_index = _fill(st.driver_items, driver_node(st), {st.driver_attr})
    nodes = driven_nodes(st)
    node = nodes[min(st.driven_index, len(nodes) - 1)] if nodes else None
    st.driven_items_index = _fill(st.driven_items, node, set(driven_keys(st)))


def hold_driven(node, key):
    """channel_box.set_value hook: keep a typed value on a channel the SDK window drives."""
    try:
        st = state()
    except AttributeError:
        return
    if not st.open:
        return
    fc = sdk_fcurve(node, key)
    if fc is not None:
        fc.mute = True


# Blend shape weights and constraint weights are posed outside the Channel Box (Shape Editor, AE, Properties), so no
# WRITE_HOOKS call reaches us: an RNA subscription on each loaded driven value of those nodes mutes its SDK driver
# the same way. Driver results are written without an RNA update, so they don't publish (GUI unverified).
_MSG = object()


def _on_posed(id_name, id_kind, path, index):
    st = state()
    if not st.open:
        return
    coll = bpy.data.shape_keys if id_kind == 'KEY' else bpy.data.objects
    idb = coll.get(id_name)
    ad = idb.animation_data if idb is not None else None
    fc = ad.drivers.find(path, index=max(index, 0)) if ad is not None else None
    if is_sdk(fc) and not fc.mute:
        fc.mute = True


# #146: msgbus notifies on the next event-loop pass, so a value typed into a blend
# shape / constraint weight and keyed before that pass met a depsgraph update first, and the unmuted driver wrote its
# result over it (the key became (90, 0)). The driven values seen after each update are kept; an update that finds a
# value changed since (= typed, not driven) mutes that SDK driver first — depsgraph_update_pre runs before drivers.
_SEEN = {}


def _loaded_chans(st):
    for node in driven_nodes(st):
        if not (is_key(node) or is_constraint(node)):
            continue
        for key in channels(node):
            c = chan(node, key)
            if c is not None and not c.attr.startswith('["'):
                yield c


def _remember(st):
    _SEEN.clear()
    for c in _loaded_chans(st):
        _SEEN[(c.id.name, c.path, c.index)] = c.get()


@bpy.app.handlers.persistent
def _before_update(_scene, _depsgraph=None):
    try:
        st = state()
    except (AttributeError, ReferenceError):
        return
    if not st.open or not _SEEN:
        return
    for c in _loaded_chans(st):
        seen = _SEEN.get((c.id.name, c.path, c.index))
        if seen is None or abs(c.get() - seen) < 1e-9:
            continue
        fc = c.find()
        if is_sdk(fc) and not fc.mute:
            fc.mute = True


@bpy.app.handlers.persistent
def _after_update(_scene, _depsgraph=None):
    try:
        sync_if_changed()
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    try:
        st = state()
    except (AttributeError, ReferenceError):
        return
    if st.open:
        _remember(st)
    elif _SEEN:
        _SEEN.clear()


def _watch(st):
    bpy.msgbus.clear_by_owner(_MSG)
    if st.open:
        _remember(st)
    else:
        _SEEN.clear()
    if not st.open:
        return
    for node in driven_nodes(st):
        if not (is_key(node) or is_constraint(node)):
            continue
        for key in channels(node):
            c = chan(node, key)
            if c is None or c.attr.startswith('["'):
                continue
            bpy.msgbus.subscribe_rna(key=c.struct.path_resolve(c.attr, False), owner=_MSG,
                                     args=(c.id.name, _id_type(c.id), c.path, c.index), notify=_on_posed)


def _redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


# --- operators -----------------------------------------------------------------------------------

class ALLSET_OT_sdk_window(bpy.types.Operator):
    """Maya Set Driven Key window: load a driver and driven channels, pose, Key (Key > Set Driven Key > Set...)"""
    bl_idname = "allset.sdk_window"
    bl_label = "Set Driven Key"

    def execute(self, context):
        st = state(context)
        st.open = True
        if hasattr(bpy.ops.allset, "dock_show"):
            try:   # the window is drawn under the Channel Box in the sidebar dock
                bpy.ops.allset.dock_show(dock='CHANNEL_BOX')
            except RuntimeError:
                context.window_manager.allset_dock = 'CHANNEL_BOX'
        _watch(st)
        _redraw(context)
        return {'FINISHED'}


def blend_pick(node, sel):
    """(shape Key, its SDK keys) for the blendShape weight channels (``bw:<target>``) picked in the Channel Box on
    an object: Set Driven Key lists those weights under the blendShape node. (None, []) when none is picked."""
    names = [k[len(cb.BLEND_PREFIX):] for k in sel if cb.is_blend_key(k)]
    if not names or cb.is_bone(node) or is_key(node) or is_constraint(node):
        return None, []
    key = getattr(getattr(node, "data", None), "shape_keys", None)
    if key is None:
        return None, []
    have = set(channels(key))
    return key, [SHAPE + n for n in names if SHAPE + n in have]


class ALLSET_OT_sdk_load(bpy.types.Operator):
    """Load the lead (Driver) or every selected object / joint (Driven, with its blendShape and constraint
    nodes); the channels selected in the Channel Box become the selected attributes"""
    bl_idname = "allset.sdk_load"
    bl_label = "Load"

    which: EnumProperty(items=(('DRIVER', "Driver", ""), ('DRIVEN', "Driven", "")), options={'SKIP_SAVE'})

    def execute(self, context):
        st = state(context)
        sel = cb.selected_channels(context)
        if self.which == 'DRIVER':
            node = cb.lead(context)
            if node is None:
                self.report({'WARNING'}, "Select the driver object (or joint) first")
                return {'CANCELLED'}
            avail = channels(node)
            picked = next((k for k in sel if k in avail), "")
            key, weights = blend_pick(node, sel)
            if not picked and weights:      # a picked blendShape weight drives: the blendShape node is the driver
                store(st.driver, key, node)
                picked = weights[0]
            else:
                store(st.driver, node)
            st.driver_attr = picked
        else:
            nodes = cb.targets(context)
            if not nodes:
                self.report({'WARNING'}, "Select the driven objects (or joints) first")
                return {'CANCELLED'}
            st.driven.clear()
            for node in nodes:
                store(st.driven.add(), node)
                for extra in extra_nodes(node):
                    store(st.driven.add(), extra, node if is_key(extra) else None)
            st.driven_index = 0
            avail = set(channels(nodes[0]))
            picked = [k for k in sel if k in avail]
            key, weights = blend_pick(nodes[0], sel)
            if not picked and weights:      # picked blendShape weights: their node is the one shown
                st.driven_index = next((i for i, n in enumerate(driven_nodes(st)) if n == key), 0)
                picked = weights
            st.driven_attrs = ",".join(picked)
        refresh_items(st)
        _watch(st)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_sdk_pick(bpy.types.Operator):
    """Pick an attribute (Driven: Ctrl adds / removes) or a driven node in the Set Driven Key lists"""
    bl_idname = "allset.sdk_pick"
    bl_label = "Pick"
    bl_options = {'INTERNAL'}

    which: EnumProperty(items=(('DRIVER', "Driver", ""), ('DRIVEN', "Driven", ""), ('NODE', "Node", "")),
                        options={'SKIP_SAVE'})
    key: StringProperty(options={'SKIP_SAVE'})
    index: IntProperty(options={'SKIP_SAVE'})
    toggle: BoolProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        self.toggle = self.toggle or event.ctrl or event.shift
        return self.execute(context)

    def execute(self, context):
        st = state(context)
        if self.which == 'DRIVER':
            st.driver_attr = self.key
        elif self.which == 'NODE':
            st.driven_index = self.index
            refresh_items(st)
        else:
            keys = driven_keys(st)
            if self.toggle:
                keys = [k for k in keys if k != self.key] if self.key in keys else keys + [self.key]
            else:
                keys = [self.key]
            st.driven_attrs = ",".join(keys)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_sdk_key(bpy.types.Operator):
    """Key: record (driver value, driven value) for every loaded driven attribute"""
    bl_idname = "allset.sdk_key"
    bl_label = "Key"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        st = state(context)
        return driver_node(st) is not None and st.driver_attr and driven_nodes(st) and driven_keys(st)

    def execute(self, context):
        st = state(context)
        drv = driver_node(st)
        count = 0
        for node in driven_nodes(st):
            if node == drv:
                continue
            avail = set(channels(node))
            for key in driven_keys(st):
                if key in avail:
                    set_key(node, key, drv, st.driver_attr)
                    count += 1
        context.view_layer.update()
        results.result(self, f"Set Driven Key: {count} key(s) at {cb.channel_label(st.driver_attr)} = "
                              f"{raw_value(drv, st.driver_attr):g}")
        return {'FINISHED'}


class ALLSET_OT_sdk_go(bpy.types.Operator):
    """Set the driver to the previous / next driven key (Key > Set Driven Key > Go to Previous / Next)"""
    bl_idname = "allset.sdk_go"
    bl_label = "Go to Driven Key"
    bl_options = {'REGISTER', 'UNDO'}

    direction: EnumProperty(items=(('PREVIOUS', "Previous", ""), ('NEXT', "Next", "")), options={'SKIP_SAVE'})

    def execute(self, context):
        st = state(context)
        drv = driver_node(st)
        fcs = [fc for node in driven_nodes(st) for key in driven_keys(st)
               if (fc := driver_curve(node, key, drv, st.driver_attr)) is not None] if drv is not None else []
        if not fcs:
            self.report({'WARNING'}, "Load a driver and driven attributes with keys (Set Driven Key window)")
            return {'CANCELLED'}
        scale = fcurve_scale(fcs[0])
        x = step_to(key_xs(fcs), raw_value(drv, st.driver_attr) * scale, self.direction)
        if x is None:
            results.result(self, "No more driven keys")
            return {'CANCELLED'}
        release_all()
        set_raw_value(drv, st.driver_attr, x / scale)
        context.view_layer.update()
        return {'FINISHED'}


class ALLSET_OT_sdk_close(bpy.types.Operator):
    """Close the Set Driven Key window (driven values posed but not keyed go back to the curve)"""
    bl_idname = "allset.sdk_close"
    bl_label = "Close"

    def execute(self, context):
        st = state(context)
        st.open = False
        _watch(st)
        release_all()
        context.view_layer.update()
        _redraw(context)
        return {'FINISHED'}


@bpy.app.handlers.persistent
def _on_load(_dummy):
    _COUNTS[0] = None
    sync_if_changed()        # an older file's inputs move to the helper (no undo step of its own)
    release_all()
    try:
        _watch(state())      # a file load clears msgbus
    except (AttributeError, ReferenceError):
        pass


classes = (ALLSET_PG_sdk_node, ALLSET_PG_sdk_item, ALLSET_PG_sdk, ALLSET_OT_sdk_window, ALLSET_OT_sdk_load, ALLSET_OT_sdk_pick,
           ALLSET_OT_sdk_key, ALLSET_OT_sdk_go, ALLSET_OT_sdk_close)


def register_props():
    bpy.types.WindowManager.allset_sdk = PointerProperty(type=ALLSET_PG_sdk, options={'SKIP_SAVE'})
    cb.WRITE_HOOKS.append(hold_driven)
    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.handlers.depsgraph_update_pre.append(_before_update)
    bpy.app.handlers.depsgraph_update_post.append(_after_update)
    _COUNTS[0] = None
    bpy.app.timers.register(_first_sync, first_interval=0.0)   # the open file (register can't edit data)


def _first_sync():
    try:
        sync_if_changed()
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return None


def unregister_props():
    if bpy.app.timers.is_registered(_first_sync):
        bpy.app.timers.unregister(_first_sync)
    bpy.msgbus.clear_by_owner(_MSG)
    bpy.app.handlers.load_post.remove(_on_load)
    for lst, fn in ((bpy.app.handlers.depsgraph_update_pre, _before_update),
                    (bpy.app.handlers.depsgraph_update_post, _after_update)):
        if fn in lst:
            lst.remove(fn)
    _SEEN.clear()
    if hold_driven in cb.WRITE_HOOKS:
        cb.WRITE_HOOKS.remove(hold_driven)
    del bpy.types.WindowManager.allset_sdk
