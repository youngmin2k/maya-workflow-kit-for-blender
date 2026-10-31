# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Auto Key without Blender's preferences (step 130).

Maya's Auto Key keys only attributes that already have keys. Blender's
own auto keying keys every changed channel unless the user preference "Only Insert Available" is on, and the kit
no longer writes preferences (steps 70–129 did, ``prefs_preset`` group ``autokey``). So the kit has its own toggle,
``Scene.allset_auto_key`` (the Time Slider's key button), and keys by itself while it is on: a depsgraph handler
notes the objects that changed, and a short timer — once no transform is running, like Blender keys at the end of
a transform — keys each of their F-curves whose channel value differs from the curve at the current frame. Blender's
own Auto Keying (``tool_settings.use_keyframe_insert_auto``) is left to the user.

Like Maya, editing the curves themselves (dragging keys in the Graph Editor, tangent changes) is not a channel change:
an object updated together with one of its Actions is not noted, so no key appears at the current time.
"""

import bpy
from bpy.app.handlers import persistent

from .. import compat

EPS = 1e-5
_pending = {}       # object name -> frame the change was seen at


def enabled(scene=None):
    scene = scene if scene is not None else bpy.context.scene
    return bool(scene is not None and getattr(scene, "allset_auto_key", False))


def _playing():
    wm = bpy.context.window_manager
    return any(w.screen is not None and w.screen.is_animation_playing for w in (wm.windows if wm else ()))


# the kit's own drags that change channels or keys: Auto Key waits for them to end, like for Blender's transforms
WAIT_FOR = frozenset({"ALLSET_OT_cb_field_drag", "ALLSET_OT_graph_key_drag", "ALLSET_OT_graph_axis_drag"})


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
    value differs from the layers' result (step 188: Maya Auto Key keys the selected layer only where that attribute
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


def key_changed(ob, frame):
    """Key the changed keyed channels of ``ob`` at ``frame``; returns how many keys were set."""
    from . import anim_layers
    if anim_layers.has_layers(ob):
        # Maya animation layers (step 188): solved onto the target layer like the kit's S key
        return sum(bool(anim_layers.key(ob, path, index, frame, value))
                   for path, index, value in changed_layer_channels(ob, frame))
    count = 0
    for fc, _value in changed_curves(ob, frame):
        group = fc.group.name if fc.group is not None else ""
        try:
            ob.keyframe_insert(fc.data_path, index=fc.array_index, frame=frame, group=group)
            from . import graph_key_menu      # default tangents, like Maya
            graph_key_menu.after_insert(ob, fc.data_path, fc.array_index, frame)
            count += 1
        except (RuntimeError, TypeError):
            pass
    return count


def _flush():
    if not _pending:
        return None
    if _transforming():
        return 0.1                       # keyed when the transform ends (Blender keys on confirm too)
    items = list(_pending.items())
    _pending.clear()
    scene = bpy.context.scene
    if not enabled(scene) or _playing():
        return None
    count = 0
    for name, frame in items:
        ob = scene.objects.get(name)
        if ob is not None and frame == scene.frame_current:
            count += key_changed(ob, frame)
    if count:
        try:
            bpy.ops.ed.undo_push(message="Auto Key")
        except RuntimeError:
            pass
    return None


@persistent
def _on_depsgraph(scene, depsgraph):
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
            continue
        _pending[ob.name] = scene.frame_current
        found = True
    if found and not bpy.app.timers.is_registered(_flush):
        bpy.app.timers.register(_flush, first_interval=0.05)


def register_handlers():
    bpy.types.Scene.allset_auto_key = bpy.props.BoolProperty(
        name="Auto Key",
        description="Maya Auto Key: changing a channel that already has keys sets a key at the current frame "
                    "(channels without keys are not keyed)")
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister_handlers():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    if bpy.app.timers.is_registered(_flush):
        bpy.app.timers.unregister(_flush)
    _pending.clear()
    del bpy.types.Scene.allset_auto_key
