# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya animation layers on Blender NLA tracks.

Maya 2022: BaseAnimation = the plain anim curves; an Additive
layer adds weight x its curve (rotations Euler component-wise, scale multiplies: below x layer^weight), an Override
layer replaces ((1 - w) below + w layer); mute drops a layer, solo keeps BaseAnimation + the soloed layers; a key set
on the selected layer is the curve value that makes the result the displayed value.

Blender 4.5 NLA gives the same numbers: BaseAnimation = a REPLACE strip on the bottom track,
Additive = COMBINE (location / Euler add, scale multiplies with influence as exponent), Override = REPLACE, weight =
the strip influence, mute = track mute; strips span a fixed wide range with 1:1 time so every key is evaluated.
Blender's tweak mode evaluates only the tracks below the tweaked one (no Python switch for the upper stack), so keys
are not set through tweak mode: ``key()`` solves the layer value from the composition rule itself.

Layers are scene-wide (``Scene.allset_anim_layers``, first entry BaseAnimation) like Maya's animLayer nodes; every
member object has one NLA track per layer, named like the layer, playing an action ``<layer>_<object>`` marked with
the ID property ``allset_anim_layer``.

Display: Maya's Graph Editor, Dope Sheet and Time Slider show the
keys of the layers selected in the Anim tab, the Channel Box marks layer members teal. A layered object's active
action is the selected layer's strip action (BaseAnimation when the object is not in it) at action influence 0: the
NLA result is unchanged, and every reader of the active action (Graph Editor,
Dope Sheet, compat.id_fcurves, the kit's key readers) sees that layer's curves.
"""

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, CollectionProperty, FloatProperty, IntProperty, StringProperty

from .. import compat
from . import naming

BASE = "BaseAnimation"
MARK = "allset_anim_layer"
WIDE = (-1000.0, 1000.0)          # strip / action range: keys outside it are not evaluated
SCALE_PATHS = {"scale", "delta_scale"}


def _leaf(path):
    """The property name of a data path (``pose.bones["j"].scale`` -> ``scale``)."""
    return path.rsplit(".", 1)[-1] if "." in path else path


def is_scale(path):
    return _leaf(path) in SCALE_PATHS


# --- scene model -----------------------------------------------------------------------------------

def layers(scene):
    return scene.allset_anim_layers


def ensure_list(scene):
    """The layer list with BaseAnimation as first entry."""
    ls = layers(scene)
    if not len(ls) or ls[0].name != BASE:
        e = ls.add()
        e.name = BASE
        ls.move(len(ls) - 1, 0)
    return ls


def selected(scene):
    ls = layers(scene)
    i = scene.allset_anim_layer_index
    return ls[i] if 0 <= i < len(ls) else (ls[0] if len(ls) else None)


def selected_layers(scene):
    """Maya's selected layers (Layer Editor Ctrl / Shift click), list order: the ``picked`` entries while
    they include the last picked one (``allset_anim_layer_index``), else only that one (any direct index write is a
    plain single selection)."""
    cur = selected(scene)
    if cur is None:
        return []
    if not cur.picked:
        return [cur]
    return [e for e in layers(scene) if e.picked]


def unique_name(scene, base="AnimLayer"):
    """Maya ``AnimLayer<N>``: one past the highest, gaps not filled."""
    return f"{base}{naming.next_number(base, {e.name for e in layers(scene)})}"


# --- per object tracks -------------------------------------------------------------------------------

def tracks(ob):
    ad = ob.animation_data
    if ad is None:
        return {}
    return {tr.name: tr for tr in ad.nla_tracks if tr.strips and tr.strips[0].action is not None
            and tr.strips[0].action.get(MARK) == tr.name}


def has_layers(ob):
    return bool(tracks(ob))


def _new_action(ob, layer):
    """An empty action with a slot for ``ob`` (Blender 4.4+ makes the slot when the action is assigned)."""
    act = bpy.data.actions.new(f"{layer}_{ob.name}")
    act[MARK] = layer
    ob.animation_data_create()
    slots = getattr(act, "slots", None)
    if slots is not None:       # 4.4+: an empty action gets no slot by being assigned; make it (the strip needs it)
        slot = slots.new(id_type='OBJECT', name=ob.name)
        act["allset_slot"] = slot.identifier
    return act


def _slot(act):
    ident = act.get("allset_slot")
    slots = getattr(act, "slots", None)
    if slots is None:
        return None
    if ident and ident in slots:
        return slots[ident]
    return slots[0] if len(slots) else None


def _strip(tr):
    return tr.strips[0]


def _add_track(ob, layer, act):
    ad = ob.animation_data_create()
    tr = ad.nla_tracks.new()
    tr.name = layer
    st = tr.strips.new(layer, int(WIDE[0]), act)
    sl = _slot(act)
    if sl is not None and hasattr(st, "action_slot"):
        st.action_slot = sl
    st.action_frame_start, st.action_frame_end = WIDE
    st.frame_start, st.frame_end = WIDE
    st.use_auto_blend = False
    st.blend_in = st.blend_out = 0.0
    st.extrapolation = 'HOLD' if layer == BASE else 'HOLD_FORWARD'
    return tr


def ensure_base(ob):
    """Move the object's own animation (its active action) onto the BaseAnimation track."""
    if BASE in tracks(ob):
        return tracks(ob)[BASE]
    ad = ob.animation_data_create()
    act = ad.action
    if act is not None:
        slot = getattr(ad, "action_slot", None)
        act[MARK] = BASE
        if slot is not None:
            act["allset_slot"] = slot.identifier
        ad.action = None
    else:
        act = _new_action(ob, BASE)
    tr = _add_track(ob, BASE, act)
    order_tracks(ob, [e.name for e in layers(bpy.context.scene)] or [BASE])
    return tr


def add_object(scene, ob, layer):
    """Make ``ob`` a member of ``layer`` (Maya Add Selected Objects / Create Layer from Selected)."""
    ensure_list(scene)
    ensure_base(ob)
    if layer != BASE and layer not in tracks(ob):
        _add_track(ob, layer, _new_action(ob, layer))
    order_tracks(ob, [e.name for e in layers(scene)])
    sync(scene)


def remove_object(scene, ob, layer):
    tr = tracks(ob).get(layer)
    if tr is None or layer == BASE:
        return
    act = _strip(tr).action
    ad = ob.animation_data
    if ad.action is not None and ad.action == act:      # shown as the active action
        ad.action = None
    ad.nla_tracks.remove(tr)
    if act is not None and act.users == 0:
        bpy.data.actions.remove(act)


def order_tracks(ob, names):
    """NLA tracks in the layer list order, bottom first (Blender can only move tracks by recreating them, so only the
    kit tracks' strip settings are swapped into place: track i gets layer names[i])."""
    have = tracks(ob)
    want = [n for n in names if n in have]
    ad = ob.animation_data
    kit = [tr for tr in ad.nla_tracks if tr.name in have]
    if [tr.name for tr in kit] == want:
        return
    data = {n: (_strip(have[n]).action, have[n].mute, strip_state(_strip(have[n]))) for n in want}
    for tr in kit:
        ad.nla_tracks.remove(tr)
    for n in want:
        tr = _add_track(ob, n, data[n][0])
        tr.mute = data[n][1]
        restore_strip_state(_strip(tr), data[n][2])      # a keyed weight survives the rebuild


def strip_state(st):
    """(animated?, influence, influence keys) of a layer strip: Maya's layer weight and its keys."""
    keys = []
    fc = st.fcurves.find("influence") if st.use_animated_influence else None
    if fc is not None:
        keys = [(tuple(kp.co), tuple(kp.handle_left), tuple(kp.handle_right), kp.interpolation,
                 kp.handle_left_type, kp.handle_right_type) for kp in fc.keyframe_points]
    return st.use_animated_influence, st.influence, keys


def restore_strip_state(st, state):
    animated, influence, keys = state
    if not animated:
        return
    fc = weight_curve(st)
    if fc is None:
        return
    fc.keyframe_points.clear()
    for co, hl, hr, interp, tl, tr in keys:
        kp = fc.keyframe_points.insert(co[0], co[1], options={'FAST'})
        kp.interpolation = interp
        kp.handle_left_type, kp.handle_right_type = tl, tr
        kp.handle_left, kp.handle_right = hl, hr
    fc.update()
    st.influence = influence


def weight_curve(st):
    """The strip's influence F-curve (Maya's keyed layer weight), made without Blender's automatic first key."""
    if not st.use_animated_influence:
        keep = st.influence
        st.use_animated_influence = True      # Blender keys influence when it turns this on: drop that key
        fc = st.fcurves.find("influence")
        if fc is not None:
            fc.keyframe_points.clear()
        st.influence = keep
    return st.fcurves.find("influence")


def strip_weight(st, frame):
    """The strip's weight at ``frame`` (its influence curve when keyed)."""
    if not st.use_animated_influence:
        return 1.0
    fc = st.fcurves.find("influence")
    if fc is not None and len(fc.keyframe_points):
        return fc.evaluate(frame)
    return st.influence


def members(scene, layer):
    return [ob for ob in scene.objects if layer in tracks(ob)]


def sync(scene):
    """Write the layer list onto every member object's tracks (Maya weight / mute / solo / mode)."""
    ls = layers(scene)
    if not len(ls):
        return
    solo = {e.name for e in ls if e.solo and e.name != BASE}
    info = {e.name: e for e in ls}
    for ob in scene.objects:
        have = tracks(ob)
        if not have:
            continue
        for name, tr in have.items():
            e = info.get(name)
            if e is None:
                continue
            st = _strip(tr)
            tr.mute = e.mute or (bool(solo) and name != BASE and name not in solo)
            st.blend_type = 'REPLACE' if name == BASE or e.override else 'COMBINE'
            st.extrapolation = 'HOLD' if name == BASE else 'HOLD_FORWARD'
            _set_influence(st, 1.0 if name == BASE else e.weight)
            tr.lock = e.lock
        ob.update_tag(refresh={'TIME'})
    show(scene)


def display_layer(scene, ob):
    """The layer whose keys ``ob`` shows: the selected layer when the object is in it, else BaseAnimation."""
    e = selected(scene)
    name = e.name if e is not None else BASE
    have = tracks(ob)
    if name in have:
        return name
    for x in reversed(selected_layers(scene)):     # another selected layer the object is in (top first)
        if x.name in have:
            return x.name
    return BASE


def show(scene):
    """Make every layered object's active action its display layer's strip action at influence 0 (module docstring):
    Graph Editor / Dope Sheet / key readers then show that layer, the evaluated result stays the NLA's."""
    for ob in scene.objects:
        have = tracks(ob)
        if not have:
            continue
        ad = ob.animation_data
        tr = have.get(display_layer(scene, ob)) or have.get(BASE) or next(iter(have.values()))
        act = _strip(tr).action
        if ad.action != act:
            ad.action = act
            sl = _slot(act)
            if sl is not None and hasattr(ad, "action_slot"):
                ad.action_slot = sl
        if ad.action_influence != 0.0:
            ad.action_influence = 0.0      # the strip already plays it: shown, not applied twice


def show_base(ob):
    """Make BaseAnimation ``ob``'s active action (influence 0) — what a bake writes into."""
    tr = tracks(ob).get(BASE)
    if tr is None:
        return
    ad = ob.animation_data
    act = _strip(tr).action
    if ad.action != act:
        ad.action = act
        sl = _slot(act)
        if sl is not None and hasattr(ad, "action_slot"):
            ad.action_slot = sl
    ad.action_influence = 0.0


def settle_base(scene, ob, prefixes):
    """After a bake wrote the VISUAL values into BaseAnimation: re-solve every baked key of channels the layers
    above also animate, so base + layers = the baked value (otherwise the layers add again). ``prefixes`` = data path prefixes of the baked owners ("" = the object)."""
    base = tracks(ob).get(BASE)
    if base is None:
        return 0
    act = _strip(base).action
    upper = set()
    for name, tr in tracks(ob).items():
        if name != BASE:
            upper |= {(fc.data_path, fc.array_index) for fc in compat.action_fcurves(_strip(tr).action,
                                                                                   _slot(_strip(tr).action))}
    if not upper:
        return 0

    def mine(path):
        return any(path.startswith(p) if p else not path.startswith("pose.") for p in prefixes)
    curves = [fc for fc in compat.action_fcurves(act, _slot(act)) if mine(fc.data_path)]
    n = 0
    quats = {}
    for fc in curves:
        if _leaf(fc.data_path) == "rotation_quaternion":
            quats.setdefault(fc.data_path, {})[fc.array_index] = fc
            continue
        if (fc.data_path, fc.array_index) not in upper:
            continue
        for f, v in [(kp.co[0], kp.co[1]) for kp in fc.keyframe_points]:
            key(ob, fc.data_path, fc.array_index, frame=f, value=v, scene=scene, layer=BASE)
            n += 1
    from mathutils import Quaternion
    for path, comps in quats.items():
        if not any((path, i) in upper for i in range(4)) or len(comps) < 4:
            continue
        frames = sorted({kp.co[0] for kp in comps[0].keyframe_points})
        values = {f: Quaternion([comps[i].evaluate(f) for i in range(4)]) for f in frames}
        for f in frames:
            key_quaternion(ob, path, f, values[f], scene, BASE)
            n += 1
    ob.update_tag(refresh={'TIME'})
    return n


def base_curve(ob, path, index):
    """``ob``'s BaseAnimation curve of one channel (None without layers or curve)."""
    tr = tracks(ob).get(BASE)
    return None if tr is None else _fcurve(_strip(tr).action, path, max(index, 0))


def member_of_layer(ob, path, index):
    """The channel is in a layer above BaseAnimation (Maya draws it teal in the Channel Box)."""
    return any(name != BASE and is_member(ob, name, path, index) for name in tracks(ob))


def hidden_base_curves(ob, scene):
    """BaseAnimation curves the display layer doesn't show: channels that are not in that layer still show their
    base keys in Maya's Time Slider."""
    layer = display_layer(scene, ob)
    if layer == BASE or BASE not in tracks(ob):
        return []
    return [fc for fc in layer_curves(ob, BASE) if not is_member(ob, layer, fc.data_path, fc.array_index)]


def _set_influence(st, w):
    if abs(w - 1.0) < 1e-9 and not st.use_animated_influence:
        return
    if not st.use_animated_influence:
        st.use_animated_influence = True      # Blender keys influence when it turns this on: drop that key
        fc = st.fcurves.find("influence")
        if fc is not None:
            while fc.keyframe_points:
                fc.keyframe_points.remove(fc.keyframe_points[0])
    st.influence = w


# --- evaluation and keys -------------------------------------------------------------------------------

def _fcurve(act, path, index):
    for fc in compat.action_fcurves(act, _slot(act)):
        if fc.data_path == path and fc.array_index == index:
            return fc
    return None


def compose(steps, start):
    """Fold the layer steps over ``start``: steps = [(mode, weight, value)] bottom first, mode REPLACE / ADD /
    MUL (scale COMBINE). Returns the result."""
    acc = start
    for mode, w, x in steps:
        if mode == 'REPLACE':
            acc = (1.0 - w) * acc + w * x
        elif mode == 'MUL':
            acc = acc * (x ** w if x > 0 else 0.0)
        else:
            acc = acc + w * x
    return acc


def _steps(ob, path, index, frame, scene):
    """[(layer name, mode, weight, value or None)] of the object's evaluated layers for one channel, bottom first."""
    info = {e.name: e for e in layers(scene)}
    out = []
    ad = ob.animation_data
    for tr in ad.nla_tracks:
        if tr.name not in info or tr.mute:
            continue
        st = _strip(tr)
        fc = _fcurve(st.action, path, index)
        w = strip_weight(st, frame)
        if st.blend_type == 'REPLACE':
            mode = 'REPLACE'
        elif st.blend_type == 'COMBINE' and is_scale(path):
            mode = 'MUL'
        else:
            mode = 'ADD'
        out.append((tr.name, mode, w, fc.evaluate(frame) if fc is not None else None))
    return out


def solve(steps, target, layer, start=0.0):
    """The value ``layer``'s curve needs so the folded result is ``target`` (Maya: a key on the selected layer makes
    the displayed value the result). ``steps`` as from ``_steps``; missing values = no curve yet (identity)."""
    def ident(mode):
        return 1.0 if mode == 'MUL' else 0.0
    k = next(i for i, s in enumerate(steps) if s[0] == layer)
    below = compose([(m, w, x) for _n, m, w, x in steps[:k] if x is not None], start)
    upper = [(m, w, x) for _n, m, w, x in steps[k + 1:] if x is not None]
    # the upper layers are affine in their input: result = a * acc + b (or a * acc for MUL steps)
    a, b = 1.0, 0.0
    for m, w, x in upper:
        if m == 'REPLACE':
            a, b = a * (1.0 - w), b * (1.0 - w) + w * x
        elif m == 'MUL':
            f = x ** w if x > 0 else 0.0
            a, b = a * f, b * f
        else:
            b = b + w * x
    _n, mode, w, cur = steps[k]
    if abs(a) < 1e-12 or w < 1e-12:
        return cur if cur is not None else ident(mode)        # an upper Override hides this layer: keep it
    acc = (target - b) / a
    if mode == 'REPLACE':
        return (acc - (1.0 - w) * below) / w
    if mode == 'MUL':
        return (acc / below) ** (1.0 / w) if below and acc / below > 0 else 1.0
    return (acc - below) / w


# --- attribute membership ---------------------------------------
# Maya layer members are attributes (animLayer -attribute): Channel Box > Channels > Add to / Remove From Selected
# Layers edits them, a key on a non-member attribute goes to BaseAnimation, removing a keyed attribute deletes its
# layer curve. The kit's members are objects (one NLA track each, Add Selected Objects = every attribute); an object's
# attribute list is kept in the object ID property ATTRS {layer: "tx,ry,..."} only once Add / Remove edited it.
ATTRS = "allset_layer_attrs"


def _attr_record(ob):
    raw = ob.get(ATTRS)
    return {str(k): [x for x in str(v).split(",") if x] for k, v in raw.items()} if raw else {}


def _set_attr_record(ob, layer, keys):
    d = _attr_record(ob)
    if keys is None:
        d.pop(layer, None)
    else:
        d[layer] = list(dict.fromkeys(keys))
    if d:
        ob[ATTRS] = {k: ",".join(v) for k, v in d.items()}
    elif ATTRS in ob:
        del ob[ATTRS]


def channel_key(path, index):
    from . import character_sets
    return character_sets.channel_key_of(path, index)


BONE = "bone:"           # a joint member of a layer (Maya adds the joint node), "bone:<bone name>"


def bone_of(path):
    """The bone name of a ``pose.bones["<name>"]...`` path, else None."""
    if not path.startswith('pose.bones["'):
        return None
    end = path.find('"]', 12)
    return bpy.utils.unescape_identifier(path[12:end]) if end > 0 else None


def bone_path(pb, prop):
    return f'pose.bones["{bpy.utils.escape_identifier(pb.name)}"].{prop}'


def is_member(ob, layer, path=None, index=-1):
    """``ob``'s channel (``path``, ``index``) is in ``layer`` (no path: the object is a member at all). A joint
    channel is a member when its bone is (Maya Add Selected Objects on joints)."""
    if layer == BASE:
        return True
    if layer not in tracks(ob):
        return False
    rec = _attr_record(ob).get(layer)
    if rec is None or path is None:
        return True
    bone = bone_of(path)
    if bone is not None:
        return BONE + bone in rec
    return channel_key(path, index) in rec


def member_bones(ob, layer):
    """Joints of the armature ``ob`` in ``layer`` (all of them when the whole object is a member)."""
    if layer not in tracks(ob) or ob.type != 'ARMATURE':
        return []
    rec = _attr_record(ob).get(layer)
    if rec is None:
        return [pb.name for pb in ob.pose.bones]
    return [k[len(BONE):] for k in rec if k.startswith(BONE)]


def member_keys(ob, layer):
    """Channel Box keys of ``ob`` in ``layer`` (all keyable shown channels when no list was edited)."""
    rec = _attr_record(ob).get(layer)
    if rec is not None:
        return list(rec)
    from ..ui import channel_box as cb
    return [k for k in cb._visible_channels(ob) if cb.is_keyable(ob, k)] if layer in tracks(ob) else []


def add_attrs(scene, ob, layer, keys):
    """Maya Add to Selected Layers: the object joins ``layer`` with only these attributes, or gains them."""
    new = layer not in tracks(ob)
    if new:
        add_object(scene, ob, layer)
        _set_attr_record(ob, layer, keys)
    elif layer in _attr_record(ob):
        _set_attr_record(ob, layer, _attr_record(ob)[layer] + list(keys))


def remove_attrs(scene, ob, layer, keys):
    """Maya Remove From Selected Layers: the attributes leave ``layer`` and their layer curves are deleted; an object
    left without attributes leaves the layer."""
    if layer == BASE or layer not in tracks(ob):
        return
    left = [k for k in member_keys(ob, layer) if k not in keys]
    act = _strip(tracks(ob)[layer]).action
    from ..ui import channel_box as cb
    for k in keys:
        if k.startswith(BONE):         # a joint leaves: all its layer curves go
            fcs = [fc for fc in compat.action_fcurves(act, _slot(act)) if bone_of(fc.data_path) == k[len(BONE):]]
        else:
            path, idx, _kind = cb.channel_path(k)
            fcs = [_fcurve(act, path, max(idx, 0))]
        for fc in fcs:
            if fc is None:
                continue
            for owner in compat.fcurve_owners(act):
                if any(f == fc for f in owner.fcurves):
                    owner.fcurves.remove(fc)
                    break
    if left:
        _set_attr_record(ob, layer, left)
    else:
        _set_attr_record(ob, layer, None)
        remove_object(scene, ob, layer)
    ob.update_tag(refresh={'TIME'})


def target_layer(scene, ob, path=None, index=-1):
    """The layer a key on ``ob`` goes to: the selected layer when the object (and with ``path`` that channel) is in
    it, else BaseAnimation (Maya: a non-member attribute is keyed on BaseAnimation)."""
    e = selected(scene)
    name = e.name if e is not None else BASE
    return name if is_member(ob, name, path, index) else BASE


def result(ob, path, index, frame=None, scene=None):
    """The value the layers give a channel at ``frame`` (None when no layer has a curve for it)."""
    scene = scene or bpy.context.scene
    frame = scene.frame_current if frame is None else frame
    steps = _steps(ob, path, max(index, 0), frame, scene)
    known = [(m, w, x) for _n, m, w, x in steps if x is not None]
    if not known:
        return None
    return compose(known, 1.0 if is_scale(path) else 0.0)


def layer_curves(ob, layer):
    """F-curves of ``ob`` on ``layer``."""
    tr = tracks(ob).get(layer)
    if tr is None:
        return []
    act = _strip(tr).action
    return list(compat.action_fcurves(act, _slot(act))) if act is not None else []


def key(ob, path, index, frame=None, value=None, scene=None, layer=None):
    """Key channel (``path``, ``index``) of ``ob`` on the selected layer (or ``layer``) so the result is ``value``
    (default: the displayed value). A quaternion (``rotation_quaternion``) is keyed whole whatever ``index``.
    False when the layer is locked."""
    scene = scene or bpy.context.scene
    frame = scene.frame_current if frame is None else frame
    if _leaf(path) == "rotation_quaternion":
        return key_quaternion(ob, path, frame, value if value is not None and not isinstance(value, float) else None,
                              scene, layer)
    if value is None:
        v = ob.path_resolve(path)
        value = float(v[index] if index >= 0 else v)
    layer = layer or target_layer(scene, ob, path, index)
    index = max(index, 0)
    info = {e.name: e for e in layers(scene)}
    if layer in info and info[layer].lock:
        return False
    steps = _steps(ob, path, index, frame, scene)
    if not any(s[0] == layer for s in steps):          # the target layer is muted: Maya keys it anyway
        tr = tracks(ob)[layer]
        steps = [s for s in steps if s[0] != layer]
        st = _strip(tr)
        steps.append((layer, 'REPLACE' if st.blend_type == 'REPLACE' else
                      ('MUL' if is_scale(path) else 'ADD'), 1.0, None))
    # NLA starts a channel no lower strip animates from the property's default (scale 1, else 0)
    start = value if layer == BASE else (1.0 if is_scale(path) else 0.0)
    x = solve(steps, value, layer, start)
    act = _strip(tracks(ob)[layer]).action
    fc = _fcurve(act, path, index)
    if fc is None:
        fc = _new_fcurve(ob, act, path, index)
    if fc is None:
        return False
    fc.keyframe_points.insert(frame, x)
    fc.update()
    ob.update_tag(refresh={'TIME'})
    return True


# Quaternion channels (Rigify-style joints, shown as Euler). Blender's NLA mixes a quaternion
# as a whole: REPLACE = component lerp of the lower result and the strip by the influence, COMBINE = lower @ strip^w
# (checked in tests/test_step234_layer_joints.py against the evaluated pose). The layer's key is solved so the result
# is the displayed rotation, with the layers above combined after it.
def _quat_power(q, w):
    from mathutils import Quaternion
    axis, angle = q.to_axis_angle()
    return Quaternion(axis, angle * w)


def _quat_layers(ob, path, frame, scene):
    """[(layer, blend, weight, Quaternion or None)] bottom first for a quaternion channel."""
    from mathutils import Quaternion
    info = {e.name: e for e in layers(scene)}
    out = []
    for tr in ob.animation_data.nla_tracks:
        if tr.name not in info or tr.mute:
            continue
        st = _strip(tr)
        fcs = [_fcurve(st.action, path, i) for i in range(4)]
        q = None
        if any(fcs):
            ident = (1.0, 0.0, 0.0, 0.0)
            q = Quaternion([fc.evaluate(frame) if fc is not None else ident[i] for i, fc in enumerate(fcs)])
        out.append((tr.name, st.blend_type, strip_weight(st, frame), q))
    return out


def compose_quaternion(steps, start):
    from mathutils import Quaternion
    acc = Quaternion(start)
    for _n, blend, w, q in steps:
        if q is None:
            continue
        if blend == 'REPLACE':
            acc = Quaternion([(1.0 - w) * a + w * b for a, b in zip(acc, q)])
        else:
            acc = acc @ _quat_power(q, w)
    return acc


def key_quaternion(ob, path, frame, value=None, scene=None, layer=None):
    """Key a quaternion channel (all four curves) on ``layer`` (default: the selected one) so the result is ``value``
    (default: the displayed rotation)."""
    from mathutils import Quaternion
    scene = scene or bpy.context.scene
    target = Quaternion(value if value is not None else ob.path_resolve(path))
    layer = layer or target_layer(scene, ob, path, 0)
    info = {e.name: e for e in layers(scene)}
    if layer in info and info[layer].lock:
        return False
    steps = _quat_layers(ob, path, frame, scene)
    if not any(s[0] == layer for s in steps):
        st = _strip(tracks(ob)[layer])
        steps.append((layer, st.blend_type, 1.0, None))
    k = next(i for i, s in enumerate(steps) if s[0] == layer)
    _n, blend, w, cur = steps[k]
    upper = Quaternion()
    for _u, b, uw, q in steps[k + 1:]:
        if q is not None and b != 'REPLACE':
            upper = upper @ _quat_power(q, uw)
    acc = target @ upper.inverted()                     # the result just above this layer
    if layer == BASE:
        x = acc
    else:
        below = compose_quaternion(steps[:k], Quaternion())
        if w < 1e-12:
            return False
        if blend == 'REPLACE':
            if below.dot(acc) < 0.0:
                acc = -acc
            x = Quaternion([(a - (1.0 - w) * b) / w for a, b in zip(acc, below)])
        else:
            x = _quat_power(below.inverted() @ acc, 1.0 / w)
    if cur is not None and cur.dot(x) < 0.0:
        x = -x                                          # keep the curve on one side (no flips between keys)
    act = _strip(tracks(ob)[layer]).action
    for i in range(4):
        fc = _fcurve(act, path, i) or _new_fcurve(ob, act, path, i)
        if fc is None:
            return False
        fc.keyframe_points.insert(frame, x[i])
        fc.update()
    ob.update_tag(refresh={'TIME'})
    return True


def key_pose_bone(pb, path, index, frame=None, scene=None):
    """Channel Box / S key of a joint channel on a layered armature (Blender's own keying refuses an
    NLA-stacked armature: "Due to the NLA stack setup ..."). ``index`` -1 = every component."""
    scene = scene or bpy.context.scene
    frame = scene.frame_current if frame is None else frame
    arm = pb.id_data
    full = bone_path(pb, path)
    if _leaf(full) == "rotation_quaternion":
        return key_quaternion(arm, full, frame, scene=scene)
    if index >= 0:
        return key(arm, full, index, frame, scene=scene)
    v = arm.path_resolve(full)
    try:
        n = len(v)
    except TypeError:
        return key(arm, full, 0, frame, value=float(v), scene=scene)
    done = False
    for i in range(n):
        done = key(arm, full, i, frame, scene=scene) or done
    return done


def _new_fcurve(ob, act, path, index):
    ad = ob.animation_data
    keep, keep_slot = ad.action, getattr(ad, "action_slot", None)
    try:
        ad.action = act
        sl = _slot(act)
        if sl is not None and hasattr(ad, "action_slot"):
            ad.action_slot = sl
        if hasattr(act, "fcurve_ensure_for_datablock"):
            fc = act.fcurve_ensure_for_datablock(ob, path, index=index)
        else:
            fc = act.fcurves.new(path, index=index)
        # Blender's keying gives transform channels X / Y / Z = red / green / blue (Maya's axis colours); a curve
        # made through the API starts AUTO_RAINBOW (a layer's Translate Y would draw red)
        if _leaf(path) in {"location", "rotation_euler", "scale", "delta_location", "rotation_quaternion"}:
            fc.color_mode = 'AUTO_RGB'
        return fc
    finally:
        ad.action = keep
        if keep is not None and keep_slot is not None:
            ad.action_slot = keep_slot


# --- operators -------------------------------------------------------------------------------------

def _sync_update(self, context):
    sync(context.scene)


def _index_update(self, context):
    show(self)


@persistent
def _load_post(_dummy):
    """Files layered by older kit versions have no active action: show the selected layer."""
    for scene in bpy.data.scenes:
        if len(layers(scene)):
            show(scene)


class ALLSET_PG_anim_layer(bpy.types.PropertyGroup):
    weight: FloatProperty(name="Weight", default=1.0, min=0.0, max=1.0, update=_sync_update,
                          description="Maya layer weight (NLA strip influence)")
    mute: BoolProperty(name="Mute", update=_sync_update, description="Mute layer")
    solo: BoolProperty(name="Solo", update=_sync_update, description="Solo layer (BaseAnimation stays)")
    lock: BoolProperty(name="Lock", update=_sync_update, description="Lock layer: no keys")
    override: BoolProperty(name="Override", update=_sync_update,
                           description="Override the layers below (else Additive)")
    picked: BoolProperty(name="Selected", options={'HIDDEN'},
                         description="Selected in the Layer Editor (Ctrl / Shift click)")


def _layer_entry(scene, name=""):
    """The layer a single-layer command acts on: ``name`` (the layer row's right-click menu) or the selected
    one."""
    if name:
        return next((e for e in layers(scene) if e.name == name), None)
    return selected(scene)


ROW_LAYER = dict(options={'SKIP_SAVE', 'HIDDEN'}, description="Act on this layer only (layer right-click menu)")


def _layer_objects(context):
    return [ob for ob in context.selected_objects if ob.type in {'MESH', 'CURVE', 'SURFACE', 'EMPTY', 'ARMATURE',
                                                               'LIGHT', 'CAMERA', 'LATTICE', 'META', 'FONT'}]


def _selected_joints(context, ob):
    """Selected joints of an armature in pose mode (Maya: the joint nodes picked), else []."""
    if ob.type != 'ARMATURE' or ob.mode != 'POSE':
        return []
    from ..ui import channel_box as cb
    return [pb.name for pb in ob.pose.bones if cb.bone_selected(pb)]


def add_selected(context, layer):
    """Maya Create Layer from Selected / Add Selected Objects: objects join whole, joints in pose mode one by one."""
    for ob in _layer_objects(context):
        bones = _selected_joints(context, ob)
        if bones:
            add_attrs(context.scene, ob, layer, [BONE + n for n in bones])
        else:
            add_object(context.scene, ob, layer)


class ALLSET_OT_anim_layer_create(bpy.types.Operator):
    """Create an animation layer, empty or with the selected objects (Maya Create Empty Layer / Create Layer from
    Selected)"""
    bl_idname = "allset.anim_layer_create"
    bl_label = "Create Animation Layer"
    bl_options = {'UNDO'}

    from_selected: BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        scene = context.scene
        ls = ensure_list(scene)
        e = ls.add()
        e.name = unique_name(scene)
        scene.allset_anim_layer_index = len(ls) - 1
        if self.from_selected:
            add_selected(context, e.name)
        sync(scene)
        return {'FINISHED'}


class ALLSET_OT_anim_layer_members(bpy.types.Operator):
    """Add the selected objects to the selected layer, or remove them (Maya Add / Remove Selected Objects)"""
    bl_idname = "allset.anim_layer_members"
    bl_label = "Layer Members"
    bl_options = {'UNDO'}

    add: BoolProperty(default=True, options={'SKIP_SAVE'})
    layer: StringProperty(**ROW_LAYER)

    def execute(self, context):
        e = _layer_entry(context.scene, self.layer)
        if e is None or e.name == BASE:
            self.report({'WARNING'}, "Select an animation layer")
            return {'CANCELLED'}
        if self.add:
            add_selected(context, e.name)
        else:
            for ob in _layer_objects(context):
                bones = _selected_joints(context, ob)
                if bones:
                    remove_attrs(context.scene, ob, e.name, [BONE + n for n in bones])
                else:
                    remove_object(context.scene, ob, e.name)
        sync(context.scene)
        return {'FINISHED'}


class ALLSET_OT_anim_layer_attrs(bpy.types.Operator):
    """Add the Channel Box's selected channels to the selected animation layer, or remove them (Maya Channel Box >
    Channels > Add to / Remove From Selected Layers)"""
    bl_idname = "allset.anim_layer_attrs"
    bl_label = "Selected Layers"
    bl_options = {'UNDO'}

    add: BoolProperty(default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        from ..ui import channel_box as cb
        scene = context.scene
        e = selected(scene)
        if e is None or e.name == BASE:
            self.report({'WARNING'}, "Select an animation layer")
            return {'CANCELLED'}
        keys = cb.selected_channels(context)
        obs = [ob for ob in _layer_objects(context)]
        if not keys or not obs:
            self.report({'WARNING'}, "Select attributes in the Channel Box")
            return {'CANCELLED'}
        for ob in obs:
            mine = [k for k in keys if cb.has_channel(ob, k)]
            if mine:
                (add_attrs if self.add else remove_attrs)(scene, ob, e.name, mine)
        sync(scene)
        return {'FINISHED'}


class ALLSET_OT_anim_layer_delete(bpy.types.Operator):
    """Delete the selected animation layer and its keys (Maya Delete Layer)"""
    bl_idname = "allset.anim_layer_delete"
    bl_label = "Delete Animation Layer"
    bl_options = {'UNDO'}

    layer: StringProperty(**ROW_LAYER)

    def execute(self, context):
        scene = context.scene
        e = _layer_entry(scene, self.layer)
        if e is None or e.name == BASE:
            self.report({'WARNING'}, "BaseAnimation can't be deleted")
            return {'CANCELLED'}
        name = e.name
        for ob in members(scene, name):
            remove_object(scene, ob, name)
        ls = layers(scene)
        ls.remove(next(i for i, x in enumerate(ls) if x.name == name))
        scene.allset_anim_layer_index = max(0, min(scene.allset_anim_layer_index, len(ls) - 1))
        sync(scene)
        return {'FINISHED'}


def _identity(path):
    return 1.0 if is_scale(path) else 0.0


def zero_key(scene, obs, frame=None):
    """Maya Zero Key Layer (``cmds.setKeyframe(identity=True,
    inTangentType="flat")``): an identity key on every member channel of the selected layer at ``frame`` (an existing
    key's value is overwritten, its tangents kept; a new key's in tangent is flat). Returns the number of keys, None for
    BaseAnimation."""
    e = selected(scene)
    if e is None or e.name == BASE:
        return None
    frame = scene.frame_current if frame is None else frame
    from ..ui import channel_box as cb
    n = 0
    for ob in obs:
        if e.name not in tracks(ob):
            continue
        act = _strip(tracks(ob)[e.name]).action
        for k in member_keys(ob, e.name):
            path, idx, _kind = cb.channel_path(k)
            try:
                v = ob.path_resolve(path)
                v = v[idx] if idx >= 0 else v
            except (ValueError, TypeError, IndexError):
                continue
            if isinstance(v, bool):       # visibility is not layered by the kit's NLA tracks
                continue
            idx = max(idx, 0)
            fc = _fcurve(act, path, idx) or _new_fcurve(ob, act, path, idx)
            if fc is None:
                continue
            old = next((kp for kp in fc.keyframe_points if abs(kp.co.x - frame) < 1e-4), None)
            if old is not None:
                d = _identity(path) - old.co.y
                old.co.y += d
                old.handle_left.y += d
                old.handle_right.y += d
            else:
                kp = fc.keyframe_points.insert(frame, _identity(path))
                kp.handle_left_type = 'FREE'
                kp.handle_left.y = kp.co.y
            fc.update()
            n += 1
        ob.update_tag(refresh={'TIME'})
    return n


def merge_down(scene, layer):
    """Maya Merge Layers with BaseAnimation and ``layer`` selected (default options:
    bake every frame, delete the merged layer): each member channel of ``layer`` gets a BaseAnimation curve keyed on
    every whole frame of the object's key range with the result of Base + ``layer``; non-member channels keep their
    keys; the layer is deleted."""
    if layer == BASE:
        return False
    for ob in members(scene, layer):
        base_act = _strip(tracks(ob)[BASE]).action
        curves = layer_curves(ob, BASE) + layer_curves(ob, layer)
        xs = [kp.co.x for fc in curves for kp in fc.keyframe_points]
        if not xs:
            continue
        frames = range(int(round(min(xs))), int(round(max(xs))) + 1)
        info = {e.name: e for e in layers(scene)}
        lay = tracks(ob)[layer]
        st = _strip(lay)
        mode = 'REPLACE' if info[layer].override else None
        w = 0.0 if info[layer].mute else (st.influence if st.use_animated_influence else 1.0)
        baked = {}
        for fc in layer_curves(ob, layer):
            path, idx = fc.data_path, fc.array_index
            if not is_member(ob, layer, path, idx):
                continue
            m = mode or ('MUL' if is_scale(path) else 'ADD')
            bfc = _fcurve(base_act, path, idx)
            rest = _identity(path)     # NLA starts a channel no lower strip animates from its default (see key())
            vals = []
            for f in frames:
                below = bfc.evaluate(f) if bfc is not None else rest
                vals.append(compose([(m, w, fc.evaluate(f))], below))
            baked[(path, idx)] = vals
        for (path, idx), vals in baked.items():
            bfc = _fcurve(base_act, path, idx) or _new_fcurve(ob, base_act, path, idx)
            if bfc is None:
                continue
            bfc.keyframe_points.clear()
            bfc.keyframe_points.add(len(vals))
            for kp, f, v in zip(bfc.keyframe_points, frames, vals):
                kp.co = (f, v)
                kp.interpolation = 'BEZIER'
                kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
            bfc.update()
        remove_object(scene, ob, layer)
        ob.update_tag(refresh={'TIME'})
    ls = layers(scene)
    i = next((i for i, x in enumerate(ls) if x.name == layer), None)
    if i is not None:
        ls.remove(i)
    scene.allset_anim_layer_index = 0
    sync(scene)
    return True


class ALLSET_OT_anim_layer_zero_key(bpy.types.Operator):
    """Set an identity key on the selected layer's attributes at the current time (Maya Zero Key Layer)"""
    bl_idname = "allset.anim_layer_zero_key"
    bl_label = "Zero Key Layer"
    bl_options = {'UNDO'}

    def execute(self, context):
        n = zero_key(context.scene, _layer_objects(context))
        if n is None:
            self.report({'WARNING'}, "Cannot set an identity key on BaseAnimation")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_anim_layer_merge(bpy.types.Operator):
    """Merge the selected layer into BaseAnimation, baking every frame (Maya Merge Layers with BaseAnimation and
    the layer selected)"""
    bl_idname = "allset.anim_layer_merge"
    bl_label = "Merge Layers"
    bl_options = {'UNDO'}

    layer: StringProperty(**ROW_LAYER)

    def execute(self, context):
        e = _layer_entry(context.scene, self.layer)
        if e is None or e.name == BASE:
            self.report({'WARNING'}, "Select an animation layer to merge into BaseAnimation")
            return {'CANCELLED'}
        merge_down(context.scene, e.name)
        return {'FINISHED'}


class ALLSET_OT_anim_layer_select(bpy.types.Operator):
    """Make this the selected layer: keys go to it (Maya click on a layer; Ctrl+click adds / removes, Shift+click
    selects a range)"""
    bl_idname = "allset.anim_layer_select"
    bl_label = "Select Animation Layer"
    bl_options = {'INTERNAL'}

    index: IntProperty(options={'SKIP_SAVE'})
    toggle: BoolProperty(options={'SKIP_SAVE'}, description="Ctrl: add / remove this layer")
    extend_range: BoolProperty(options={'SKIP_SAVE'}, description="Shift: select the range up to this layer")

    def invoke(self, context, event):
        from . import keystate
        self.toggle = event.ctrl or any(keystate.is_down(k) for k in ("LEFT_CTRL", "RIGHT_CTRL"))
        self.extend_range = not self.toggle and (
            event.shift or any(keystate.is_down(k) for k in ("LEFT_SHIFT", "RIGHT_SHIFT")))
        return self.execute(context)

    def execute(self, context):
        from . import anim_layers_204
        anim_layers_204.pick(context.scene, self.index, toggle=self.toggle, extend=self.extend_range)
        anim_layers_204.redraw(context)
        return {'FINISHED'}


classes = (ALLSET_PG_anim_layer, ALLSET_OT_anim_layer_create, ALLSET_OT_anim_layer_members, ALLSET_OT_anim_layer_attrs,
           ALLSET_OT_anim_layer_delete, ALLSET_OT_anim_layer_select, ALLSET_OT_anim_layer_zero_key,
           ALLSET_OT_anim_layer_merge)


def register_props():
    bpy.types.Scene.allset_anim_layers = CollectionProperty(type=ALLSET_PG_anim_layer)
    bpy.types.Scene.allset_anim_layer_index = IntProperty(name="Selected Layer", default=0, min=0,
                                                          update=_index_update)
    bpy.app.handlers.load_post.append(_load_post)


def unregister_props():
    if _load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post)
    del bpy.types.Scene.allset_anim_layer_index
    del bpy.types.Scene.allset_anim_layers
