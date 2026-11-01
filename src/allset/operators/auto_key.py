# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Auto Key without Blender's preferences.

Maya's Auto Key keys only attributes that already have keys. Blender's
own auto keying keys every changed channel unless the user preference "Only Insert Available" is on, and the kit
never writes preferences. So the kit has its own toggle,
``Scene.allset_auto_key`` (the Time Slider's key button), and keys by itself while it is on: a depsgraph handler
notes the objects that changed, and a short timer — once no transform is running, like Blender keys at the end of
a transform — keys each of their F-curves whose channel value differs from the curve at the current frame. Blender's
own Auto Keying (``tool_settings.use_keyframe_insert_auto``) is left to the user.

Like Maya, editing the curves themselves (dragging keys in the Graph Editor, tangent changes) is not a channel change:
an object updated together with one of its Actions is not noted, so no key appears at the current time.

Like Maya, only a value that changes while Auto Key is on is keyed: the kit remembers the keyed channels' values when
Auto Key is turned on and each time it looks at an object, and keys a channel only when its value moved since then.
A value changed while Auto Key was off is not keyed by a later update that changes nothing (a selection change).

Blender pushes a transform's undo step when the transform ends, before any Python code runs, so the keys go into a
step of their own ("Auto Key") right after it. Like Maya, one Undo takes back the change and its keys together and one
Redo brings both back: the Auto Key step is paired with the change's own step (``undo_pairs``).
"""

import bpy
from bpy.app.handlers import persistent

from .. import compat

EPS = 1e-5
_pending = {}       # object name -> frame the change was seen at
_seen = {}          # (object name, pointer) -> {(data path, index): value} when Auto Key last looked at it


def _id(ob):
    return ob.name, ob.as_pointer()      # a new object under an old name is a new object


def enabled(scene=None):
    scene = scene if scene is not None else bpy.context.scene
    return bool(scene is not None and getattr(scene, "allset_auto_key", False))


def _playing():
    wm = bpy.context.window_manager
    return any(w.screen is not None and w.screen.is_animation_playing for w in (wm.windows if wm else ()))


# the kit's own drags that change channels or keys: Auto Key waits for them to end, like for Blender's transforms
WAIT_FOR = frozenset({"ALLSET_OT_cb_field_drag", "ALLSET_OT_graph_key_drag", "ALLSET_OT_graph_axis_drag",
                      "ALLSET_OT_graph_scale_box"})


def waits_for(bl_idname):
    return bl_idname.startswith("TRANSFORM_OT") or bl_idname.startswith("ALLSET_OT_manip") or bl_idname in WAIT_FOR


def _transforming():
    wm = bpy.context.window_manager
    for w in (wm.windows if wm else ()):
        for op in w.modal_operators:
            if waits_for(op.bl_idname):
                return True
    return False


def _actions(ad):
    """Pointers of the Actions that animate through ``ad`` (its action and its NLA strips' actions)."""
    out = set()
    if ad.action is not None:
        out.add(ad.action.as_pointer())
    for track in ad.nla_tracks:
        for strip in track.strips:
            if strip.action is not None:
                out.add(strip.action.as_pointer())
    return out


def _nla_mapped(ad):
    """NLA strips or tweak mode map scene time to action time: left to Blender's own keying."""
    if ad.use_tweak_mode:
        return True
    return any(not t.mute and len(t.strips) for t in ad.nla_tracks)


def changed_curves(ob, frame):
    """(F-curve, value) for every keyed channel of ``ob`` whose value differs from its curve at ``frame``."""
    ad = ob.animation_data
    if ad is None or ad.action is None or _nla_mapped(ad):
        return []
    out = []
    for fc in compat.id_fcurves(ob):
        if fc.mute or fc.lock or not fc.is_valid or len(fc.keyframe_points) == 0:
            continue
        try:
            value = ob.path_resolve(fc.data_path)
        except ValueError:
            continue
        if not isinstance(value, (int, float, bool)):
            try:
                value = value[fc.array_index]
            except (TypeError, IndexError, KeyError):
                continue
        if not isinstance(value, (int, float, bool)):
            continue
        value = float(value)
        if abs(value - fc.evaluate(frame)) > EPS * max(1.0, abs(value)):
            out.append((fc, value))
    return out


def _value(ob, path, index):
    try:
        v = ob.path_resolve(path)
    except ValueError:
        return None
    if not isinstance(v, (int, float, bool)):
        try:
            v = v[index]
        except (TypeError, IndexError, KeyError):
            return None
    return float(v) if isinstance(v, (int, float, bool)) else None


def changed_layer_channels(ob, frame, scene=None):
    """(path, index, value) of a layered object's channels that have keys on the layer a key would go to and whose
    value differs from the layers' result (Maya Auto Key keys the selected layer only where that attribute
    already has keys on it)."""
    from . import anim_layers
    scene = scene or bpy.context.scene
    seen, out = set(), []
    for layer in anim_layers.tracks(ob):
        for fc in anim_layers.layer_curves(ob, layer):
            ch = (fc.data_path, fc.array_index)
            if ch in seen or fc.mute or len(fc.keyframe_points) == 0:
                continue
            seen.add(ch)
            target = anim_layers.target_layer(scene, ob, *ch)
            if not any((c.data_path, c.array_index) == ch and len(c.keyframe_points)
                       for c in anim_layers.layer_curves(ob, target)):
                continue
            value = _value(ob, *ch)
            res = anim_layers.result(ob, ch[0], ch[1], frame, scene)
            if value is None or res is None:
                continue
            if abs(value - res) > EPS * max(1.0, abs(value)):
                out.append((ch[0], ch[1], value))
    return out


def _channels(ob):
    """{(data path, index): value} of the channels of ``ob`` that have curves."""
    from . import anim_layers
    ad = ob.animation_data
    if ad is None:
        return {}
    curves = list(compat.id_fcurves(ob))
    if anim_layers.has_layers(ob):
        for layer in anim_layers.tracks(ob):
            curves.extend(anim_layers.layer_curves(ob, layer))
    out = {}
    for fc in curves:
        ch = (fc.data_path, fc.array_index)
        if ch not in out:
            v = _value(ob, *ch)
            if v is not None:
                out[ch] = v
    return out


def remember(ob):
    """Note ``ob``'s channel values: Auto Key keys a channel only after its value moved from these."""
    try:
        _seen[_id(ob)] = _channels(ob)
    except (ReferenceError, AttributeError):
        pass


def remember_curves(ob, frame):
    """The curves of ``ob`` changed (keys set or edited): what they give at ``frame`` is what its channels are
    compared with from now on (a value changed in the same update still counts as moved)."""
    from . import anim_layers
    if anim_layers.has_layers(ob):
        _seen.pop(_id(ob), None)
        return
    seen = _seen.setdefault(_id(ob), {})
    for fc in compat.id_fcurves(ob):
        if len(fc.keyframe_points):
            seen[(fc.data_path, fc.array_index)] = fc.evaluate(frame)


def remember_all(scene=None):
    _seen.clear()
    scene = scene if scene is not None else bpy.context.scene
    for ob in scene.objects if scene is not None else ():
        if ob.animation_data is not None:
            remember(ob)


def moved(ob, path, index, value):
    """The channel's value moved since Auto Key last looked at ``ob`` (unknown objects / channels count as moved)."""
    seen = _seen.get(_id(ob))
    if seen is None:
        return True
    old = seen.get((path, index))
    return old is None or abs(old - value) > EPS * max(1.0, abs(value))


def key_changed(ob, frame, keyed=None):
    """Key the changed keyed channels of ``ob`` at ``frame``; returns how many keys were set. ``keyed`` (a list)
    gets the (path, index, value) of each keyed channel."""
    from . import anim_layers
    if anim_layers.has_layers(ob):
        # Maya animation layers: solved onto the target layer like the kit's S key
        count = 0
        for path, index, value in changed_layer_channels(ob, frame):
            if not moved(ob, path, index, value):
                continue
            if anim_layers.key(ob, path, index, frame, value):
                count += 1
                if keyed is not None:
                    keyed.append((path, index, value))
        return count
    count = 0
    for fc, value in changed_curves(ob, frame):
        group = fc.group.name if fc.group is not None else ""
        path, index = fc.data_path, fc.array_index
        if not moved(ob, path, index, value):
            continue
        try:
            ob.keyframe_insert(path, index=index, frame=frame, group=group)
            from . import graph_key_menu      # default tangents, like Maya
            graph_key_menu.after_insert(ob, path, index, frame)
            count += 1
            if keyed is not None:
                keyed.append((path, index, value))
        except (RuntimeError, TypeError):
            pass
    return count


def _flush():
    if not _pending:
        return None
    if _transforming():
        return 0.02                      # keyed when the transform ends (Blender keys on confirm too)
    items = list(_pending.items())
    _pending.clear()
    scene = bpy.context.scene
    if not enabled(scene) or _playing():
        return None
    count = 0
    keyed = {}
    for name, frame in items:
        ob = scene.objects.get(name)
        if ob is not None and frame == scene.frame_current:
            values = []
            count += key_changed(ob, frame, values)
            if values:
                keyed[name] = tuple(values)
        if ob is not None:
            remember(ob)
    if count:
        _push(scene, keyed)
    return None


def _push(scene, keyed):
    """Push the Auto Key step, paired with the step before it (``undo_pairs``). Undo / redo take the two together
    only while that step holds the keyed values, i.e. when the change pushed a step of its own (a transform, a
    button, Clear Transform...)."""
    from . import undo_pairs
    undo_pairs.push(scene, "Auto Key", lambda sc: _matches(sc, keyed))


def _matches(scene, keyed):
    """The scene's channels hold the values that were keyed (the change's own step, with or without its keys)."""
    for name, values in keyed.items():
        ob = scene.objects.get(name)
        if ob is None:
            return False
        for path, index, value in values:
            v = _value(ob, path, index)
            if v is None or abs(v - value) > 1e-4 * max(1.0, abs(value)):
                return False
    return True


_reloaded = [False]   # an undo / redo just loaded a state: its update is no channel change


def _reload_seen():
    _reloaded[0] = False
    if enabled():
        remember_all()
    return None


@persistent
def _on_undo_redo(*_args):
    """An undo / redo puts back a stored state (a moved pose without its key on the way to the Auto Key step, say):
    keying it would push a step and cut off the redo history. The update it causes runs before the next timer."""
    _pending.clear()
    _reloaded[0] = True
    if not bpy.app.timers.is_registered(_reload_seen):
        bpy.app.timers.register(_reload_seen, first_interval=0.0)


@persistent
def _on_depsgraph(scene, depsgraph):
    if _reloaded[0]:
        return
    if not enabled(scene) or _playing():
        return
    found = False
    # an object whose animation curves changed in this update (keys dragged in the Graph Editor, a key set, a tangent
    # rule) only shows its new animated value: that is no channel change to key
    edited = {u.id.original.as_pointer() for u in depsgraph.updates if isinstance(u.id, bpy.types.Action)}
    for update in depsgraph.updates:
        ob = update.id.original if isinstance(update.id, bpy.types.Object) else None
        if ob is None or ob.animation_data is None:
            continue
        if ob.animation_data.action is None and not ob.animation_data.nla_tracks:
            continue
        if edited and _actions(ob.animation_data) & edited:
            if _id(ob) in _seen:
                remember_curves(ob, scene.frame_current)
            continue
        _pending[ob.name] = scene.frame_current
        found = True
    if found and not bpy.app.timers.is_registered(_flush):
        bpy.app.timers.register(_flush, first_interval=0.05)


def _toggled(scene, _context):
    if enabled(scene):
        remember_all(scene)
    else:
        _seen.clear()


def register_handlers():
    bpy.types.Scene.allset_auto_key = bpy.props.BoolProperty(
        name="Auto Key",
        description="Maya Auto Key: changing a channel that already has keys sets a key at the current frame "
                    "(channels without keys are not keyed)", update=_toggled)
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn not in lst:
            lst.append(fn)


_HANDLERS = (("depsgraph_update_post", _on_depsgraph), ("undo_post", _on_undo_redo), ("redo_post", _on_undo_redo))


def unregister_handlers():
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        while fn in lst:
            lst.remove(fn)
    for fn in (_flush, _reload_seen):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
    _pending.clear()
    _seen.clear()
    _reloaded[0] = False
    del bpy.types.Scene.allset_auto_key
