# SPDX-License-Identifier: GPL-3.0-or-later
"""Channel Box Channels menu commands Maya has and the step-38 set lacked.

Maya 2022 Channel Box Channels menu: Breakdown All / Mute All /
Unmute All act on every shown channel; Cut / Copy / Delete Selected take the whole curves of the selected channels
(``cmds.cutKey`` / ``cmds.copyKey`` over all time and every float range); Paste Selected = ``cmds.pasteKey(connect=True,
time=current)``; Freeze = ``cmds.makeIdentity(apply=True)``; Select Connection selects the node feeding
the channel. Paste, for example: a copied curve 1:0 10:5 20:2 pasted at 15 onto a curve
1:1 12:3 30:4 gives 15:3.2896 24:8.2896 34:5.2896 and moves the key at 30 to 49 — keys start at the paste time, values
are offset so the first one meets the target curve's value there (connect), later keys move right by the pasted length
(insert); a channel without a curve gets the copied values as they are.

Sync Selection in Graph Editor / Sync Timeline Display are Maya settings (off by default) = add-on prefs
``cb_sync_graph`` / ``cb_sync_timeline``: with Sync Graph Editor on, the selected channels' F-curves become the
selected curves and S keys only the selected channels (Channels menu);
with Sync Timeline Display on, the Time Slider shows only the selected channels' keys.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty

from .. import results
from .. import compat


def _cb():
    from . import channel_box
    return channel_box


def _prefs():
    from .. import preferences
    try:
        return preferences.get()
    except (KeyError, AttributeError):
        return None


def sync_graph_on():
    p = _prefs()
    return bool(p is not None and getattr(p, "cb_sync_graph", False))


def sync_timeline_on():
    p = _prefs()
    return bool(p is not None and getattr(p, "cb_sync_timeline", False))


def after_selection(context):
    """Sync Selection in Graph Editor: the selected channels' curves are the selected F-curves."""
    if not sync_graph_on():
        return
    cb = _cb()
    keys = cb.selected_channels(context)
    for ob in cb.targets(context):
        wanted = {fc.as_pointer() for k in keys if cb.has_channel(ob, k) for fc in cb.channel_fcurves(ob, k)}
        owners = {ob.id_data.as_pointer(): ob.id_data}
        data = getattr(ob, "data", None)
        if data is not None and not cb.is_bone(ob):
            owners[data.as_pointer()] = data
            bs = cb.blend_shape_key(ob)
            if bs is not None:
                owners[bs.as_pointer()] = bs
        for owner in owners.values():
            for fc in compat.id_fcurves(owner):
                fc.select = fc.as_pointer() in wanted


def synced_keys(context, node):
    """Channels S keys on ``node`` with Sync Graph Editor on (None: every keyable channel, the default like Maya)."""
    if not sync_graph_on():
        return None
    cb = _cb()
    keys = [k for k in cb.selected_channels(context) if cb.has_channel(node, k)]
    return keys or None


def timeline_curves(context, node):
    """F-curves the Time Slider shows for ``node`` with Sync Timeline Display on (None: all of them)."""
    if not sync_timeline_on():
        return None
    cb = _cb()
    keys = cb.selected_channels(context)
    if not keys:
        return None
    return [fc for k in keys if cb.has_channel(node, k) for fc in cb.channel_fcurves(node, k)]


# --- Cut / Copy / Paste Selected -----------------------------------------------------------------------------

_CLIP = {"channels": []}      # [(channel key, [key records])], in the order the channels were selected


def _record(kp):
    return (kp.co.x, kp.co.y, tuple(kp.handle_left), tuple(kp.handle_right), kp.interpolation,
            kp.handle_left_type, kp.handle_right_type, kp.type, kp.easing)


def copy_selected(context):
    """The lead's selected channels' whole curves onto the channel clipboard. Count of channels."""
    cb = _cb()
    ob = cb.lead(context)
    out = []
    for key in cb.selected_channels(context) if ob is not None else ():
        if not cb.has_channel(ob, key):
            continue
        fc = cb.fcurve(ob, key)
        if fc is not None and len(fc.keyframe_points):
            out.append((key, [_record(kp) for kp in fc.keyframe_points]))
    if out:
        _CLIP["channels"] = out
    return len(out)


def clipboard():
    return list(_CLIP["channels"])


def _ensure_curve(ob, key, frame):
    """The channel's F-curve, made (with one key) when missing; (curve, made)."""
    cb = _cb()
    fc = cb.fcurve(ob, key)
    if fc is not None:
        return fc, False
    if not cb.keyframe(ob, key):
        return None, False
    return cb.fcurve(ob, key), True


def paste_onto(fc, records, frame, made):
    """Maya pasteKey -connect true -option insert at ``frame`` (see module doc). Returns the pasted count."""
    if not records:
        return 0
    x0, y0 = records[0][0], records[0][1]
    span = records[-1][0] - x0
    if made:
        dy = 0.0
        while len(fc.keyframe_points):
            fc.keyframe_points.remove(fc.keyframe_points[0], fast=True)
    else:
        dy = fc.evaluate(frame) - y0
        for kp in sorted((k for k in fc.keyframe_points if k.co.x >= frame - 1e-4), key=lambda k: -k.co.x):
            kp.co.x += span
            kp.handle_left.x += span
            kp.handle_right.x += span
    dx = frame - x0
    for x, y, hl, hr, interp, hlt, hrt, ktype, easing in records:
        kp = fc.keyframe_points.insert(x + dx, y + dy, options={'FAST'})
        kp.interpolation, kp.type, kp.easing = interp, ktype, easing
        kp.handle_left_type, kp.handle_right_type = hlt, hrt
        kp.handle_left = (hl[0] + dx, hl[1] + dy)
        kp.handle_right = (hr[0] + dx, hr[1] + dy)
    fc.update()
    return len(records)


def paste_selected(context, frame=None):
    """Paste the channel clipboard at the current time onto the selected channels of every selected node: one
    copied channel goes onto every selected channel, as many as selected go in order, else by the same name."""
    cb = _cb()
    clip = clipboard()
    if not clip:
        return 0
    frame = context.scene.frame_current if frame is None else frame
    sel = cb.selected_channels(context)
    n = 0
    for ob in cb.targets(context):
        keys = [k for k in sel if cb.has_channel(ob, k)]
        if len(clip) == 1 and keys:
            pairs = [(k, clip[0][1]) for k in keys]
        elif keys and len(keys) == len(clip):
            pairs = [(k, rec) for k, (_c, rec) in zip(keys, clip)]
        else:
            pairs = [(c, rec) for c, rec in clip if cb.has_channel(ob, c)]
        for key, records in pairs:
            if not cb.is_keyable(ob, key):
                continue
            fc, made = _ensure_curve(ob, key, frame)
            if fc is not None:
                n += paste_onto(fc, records, frame, made)
    return n


# --- Select Connection ---------------------------------------------------------------------------------------

def connection(ob, key):
    """What feeds a channel: ("DRIVER", [objects]) / ("CONSTRAINT", [objects]) / ("CURVE", fcurve) / None."""
    cb = _cb()
    dr = cb.driver(ob, key)
    if dr is not None:
        obs = [t.id for v in dr.driver.variables for t in v.targets if isinstance(t.id, bpy.types.Object)]
        return ("DRIVER", obs)
    if key in cb.constrained_keys(ob):
        obs = [getattr(c, "target", None) for c in cb.constraints(ob)]
        return ("CONSTRAINT", [o for o in obs if o is not None])
    fc = cb.fcurve(ob, key)
    if fc is not None:
        return ("CURVE", fc)
    return None


# --- Add to / Remove From Selected Layers: real (operators/anim_layers.ALLSET_OT_anim_layer_attrs) ---
LAYER_PATH = "Channel Box/Channels/"
LAYER_ITEMS = ("Add to Selected Layers", "Remove From Selected Layers")
NOTICES = {}


# --- operators -----------------------------------------------------------------------------------------------

class _AllChannels:
    """Breakdown All / Mute All / Unmute All: every channel the Channel Box shows (Maya selectedOnly = false)."""
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _cb().lead(context) is not None

    def execute(self, context):
        cb = _cb()
        n = 0
        for ob in cb.targets(context):
            for key in cb.drawn_keys(ob):
                n += bool(self.act(cb, ob, key))
        results.result(self, f"{self.bl_label}: {n} channel(s)")
        return {'FINISHED'}


class ALLSET_OT_cb_breakdown_all(_AllChannels, bpy.types.Operator):
    """Set a breakdown key on every channel shown (Maya Channels > Breakdown All)"""
    bl_idname = "allset.cb_breakdown_all"
    bl_label = "Breakdown All"

    def act(self, cb, ob, key):
        return cb.is_keyable(ob, key) and cb.keyframe(ob, key, 'BREAKDOWN')


class ALLSET_OT_cb_mute_all(_AllChannels, bpy.types.Operator):
    """Mute or unmute the animation of every channel shown (Maya Channels > Mute All / Unmute All)"""
    bl_idname = "allset.cb_mute_all"
    bl_label = "Mute All"

    mute: BoolProperty(name="Mute", default=True, options={'SKIP_SAVE'})

    def act(self, cb, ob, key):
        curves = cb.channel_fcurves(ob, key)
        for fc in curves:
            fc.mute = self.mute
        return bool(curves)


class ALLSET_OT_cb_clipboard(bpy.types.Operator):
    """Cut, copy or paste the animation curves of the selected channels (Maya Channels > Cut / Copy / Paste
    Selected; Paste puts the curve's first key at the current time and joins it to the curve there)"""
    bl_idname = "allset.cb_clipboard"
    bl_label = "Channel Clipboard"
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=(("CUT", "Cut Selected", ""), ("COPY", "Copy Selected", ""),
                                ("PASTE", "Paste Selected", "")), name="Action", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return _cb().lead(context) is not None

    @classmethod
    def description(cls, context, props):
        return {"CUT": "Copy the animation curves of the selected channels, then delete them",
                "COPY": "Copy the animation curves of the selected channels",
                "PASTE": "Paste the copied curves onto the selected channels at the current time"}[props.action]

    def execute(self, context):
        cb = _cb()
        if self.action == "PASTE":
            n = paste_selected(context)
            if not n:
                self.report({'WARNING'}, "Nothing to paste: copy the channels of a keyed object first")
                return {'CANCELLED'}
        else:
            n = copy_selected(context)
            if not n:
                self.report({'WARNING'}, "No animated channel selected")
                return {'CANCELLED'}
            if self.action == "CUT":
                for ob in cb.targets(context):
                    for key in cb.selected_channels(context):
                        if cb.has_channel(ob, key):
                            cb.remove_channel_curves(ob, key)
        for area in context.screen.areas if context.screen else ():
            area.tag_redraw()
        return {'FINISHED'}


class ALLSET_OT_cb_select_connection(bpy.types.Operator):
    """Select what feeds the selected channel: the driver's or constraint's objects, else its animation curve in the
    Graph Editor (Maya Channels > Select Connection)"""
    bl_idname = "allset.cb_select_connection"
    bl_label = "Select Connection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _cb().lead(context) is not None

    def execute(self, context):
        cb = _cb()
        ob = cb.lead(context)
        key = next((k for k in cb.selected_channels(context) if cb.has_channel(ob, k)), None)
        found = connection(ob, key) if key is not None else None
        if found is None:
            self.report({'WARNING'}, "The selected channel has no input connection")
            return {'CANCELLED'}
        kind, what = found
        if kind == "CURVE":
            owner = cb.curve_owner(ob, key)
            for fc in compat.id_fcurves(owner):
                fc.select = fc == what
            if not any(a.type == 'GRAPH_EDITOR' for a in context.screen.areas):
                try:
                    bpy.ops.allset.open_editor(ui_type='FCURVES')
                except (RuntimeError, AttributeError):
                    pass
            return {'FINISHED'}
        if not what:
            self.report({'WARNING'}, "The connection has no object to select")
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        for o in what:
            try:
                o.select_set(True)
            except RuntimeError:
                pass
        context.view_layer.objects.active = what[0]
        return {'FINISHED'}


classes = (ALLSET_OT_cb_breakdown_all, ALLSET_OT_cb_mute_all, ALLSET_OT_cb_clipboard, ALLSET_OT_cb_select_connection)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    from . import notices
    notices.PANEL_NOTICES.update(NOTICES)


def unregister():
    from . import notices
    for k in NOTICES:
        notices.PANEL_NOTICES.pop(k, None)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _CLIP["channels"] = []
