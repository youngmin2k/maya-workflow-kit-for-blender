# SPDX-License-Identifier: GPL-3.0-or-later
"""Graph Editor / Dope Sheet key commands in Maya terms.

- Edit menu key windows from a key editor act on the **selected keys** (Maya's Edit > Cut / Copy / Delete Keys & co.:
  from the Graph Editor with keys selected and the "keys" option; else the time range of the nodes,
  ``operators/time_keys``).
- Keys > Add / Remove Inbetween: the keys after the current time on the curves the editor shows move by one frame
  (Maya's Graph Editor Keys menu).
- Keys > Mute / Unmute Key: Maya keys a mute node so the curve holds the muted key's value until the
  next unmuted key. Blender has no per-key mute: a Stepped F-modifier limited to
  [muted key, next unmuted key) gives the same values; the modifiers named ``MUTE_NAME`` are the kit's.
- Select > All / Only Curve / Curve / Key / In Tangent / Out Tangent (Maya's Graph Editor Select menu): pick masks
  as add-on prefs; Blender has none, so ``_mask_tick`` filters what a selection just added.
- Tangents > Default In / Out Tangent: add-on prefs applied to the keys the kit sets (``after_insert``).
"""

import bpy
from bpy.props import BoolProperty, EnumProperty

from .. import undo_steps
from . import time_keys

MUTE_NAME = "Maya mute"
EPS = 1e-4
_END_GAP = 1e-3      # the hold stops just before the next unmuted key (Maya: that key's own value at its time)
_FAR = 1e7           # a muted last key holds to the end


def _space(context):
    space = getattr(context, "space_data", None)
    if space is None:
        return None
    if space.type == 'GRAPH_EDITOR' or (space.type == 'DOPESHEET_EDITOR' and space.mode != 'TIMELINE'):
        return space
    return None


def in_key_editor(context):
    return _space(context) is not None


def editor_curves(context):
    """The editable curves a Graph Editor / Dope Sheet shows."""
    if not in_key_editor(context):
        return []
    curves = getattr(context, "editable_fcurves", None)
    if curves is None:
        curves = getattr(context, "visible_fcurves", None) or ()
    return list(curves)


def selected_keys(context):
    """[(fcurve, [selected keyframe points])] in the key editor."""
    out = []
    for fc in editor_curves(context):
        pts = [kp for kp in fc.keyframe_points if kp.select_control_point]
        if pts:
            out.append((fc, pts))
    return out


def has_selected_keys(context):
    return bool(selected_keys(context))


def _redraw(context):
    for area in context.screen.areas if getattr(context, "screen", None) else ():
        if area.type in {'GRAPH_EDITOR', 'DOPESHEET_EDITOR', 'VIEW_3D', 'PROPERTIES'}:
            area.tag_redraw()


# --- selected-key versions of the key windows ---------------------------------------------------------------

def _remove(fc, pts):
    ids = {kp.as_pointer() for kp in pts}
    while True:
        kp = next((k for k in fc.keyframe_points if k.as_pointer() in ids), None)
        if kp is None:
            break
        ids.discard(kp.as_pointer())
        fc.keyframe_points.remove(kp)
    fc.update()


def delete_selected(context):
    """Delete Keys from a key editor: the selected keys. Count removed."""
    n = 0
    for fc, pts in selected_keys(context):
        n += len(pts)
        _remove(fc, pts)
    return n


_clip = {"from": None}     # who filled the last clipboard: "editor" (Blender's key buffer) or "kit" (time_keys)


def copy_selected(context):
    """Copy Keys from a key editor = the editor's own key buffer (Edit > Paste in the editor reads it)."""
    space = _space(context)
    if space is None or not has_selected_keys(context):
        return 0
    (bpy.ops.graph.copy if space.type == 'GRAPH_EDITOR' else bpy.ops.action.copy)()
    _clip["from"] = "editor"
    return sum(len(p) for _f, p in selected_keys(context))


def cut_selected(context):
    n = copy_selected(context)
    if n:
        delete_selected(context)
    return n


def note_kit_copy():
    _clip["from"] = "kit"


def editor_clipboard():
    return _clip["from"] == "editor"


def paste_editor(context, time_range="Current", time_offset=0.0, value_offset=0.0, copies=1, method="Merge"):
    """Paste Keys into a key editor from its buffer: Current = at the current time, Clipboard = at the copied
    times; Merge mixes, Replace replaces the pasted range, Insert pushes later keys right by the pasted length.
    Time / value offsets move the pasted keys; Copies repeats them end to end."""
    space = _space(context)
    if space is None:
        return 0
    graph = space.type == 'GRAPH_EDITOR'
    paste = bpy.ops.graph.paste if graph else bpy.ops.action.paste
    offset = 'NONE' if time_range == "Clipboard" else 'START'
    merge = 'OVER_RANGE' if method == "Replace" else 'MIX'
    n = 0
    shift = 0.0
    for _i in range(max(1, int(copies))):
        before = {fc.as_pointer(): {kp.as_pointer() for kp in fc.keyframe_points} for fc in editor_curves(context)}
        try:
            paste(offset=offset, merge=merge)
        except RuntimeError:
            return n
        pasted = []
        for fc in editor_curves(context):
            old = before.get(fc.as_pointer(), set())
            pasted += [(fc, kp) for kp in fc.keyframe_points if kp.as_pointer() not in old or kp.select_control_point]
        if not pasted:
            return n
        span = max(kp.co.x for _f, kp in pasted) - min(kp.co.x for _f, kp in pasted)
        dx = time_offset + shift
        for fc, kp in pasted:
            u = time_keys.value_unit(fc)
            if abs(dx) > 1e-9:
                time_keys._move(kp, dx)
            if abs(value_offset) > 1e-12:
                time_keys._offset_value(kp, value_offset * u)
        if method == "Insert":
            start = min(kp.co.x for _f, kp in pasted)
            ids = {kp.as_pointer() for _f, kp in pasted}
            for fc in {f.as_pointer(): f for f, _k in pasted}.values():
                for kp in fc.keyframe_points:
                    if kp.as_pointer() not in ids and kp.co.x >= start - EPS:
                        time_keys._move(kp, span + 1.0)
        for fc in {f.as_pointer(): f for f, _k in pasted}.values():
            fc.update()
        n += len(pasted)
        shift += span + 1.0
    return n


def scale_selected(context, method="Scale/Pivot", time_scale=1.0, time_pivot=0.0, value_scale=1.0, value_pivot=0.0,
                   new_start=1.0, new_end=10.0):
    """Scale Keys from a key editor: the selected keys (time about the pivot, values about the value pivot in Maya
    units; Start/End maps the selected keys' span onto New start / end)."""
    sel = selected_keys(context)
    if not sel:
        return 0
    if method == "Start/End":
        xs = [kp.co.x for _f, pts in sel for kp in pts]
        a, b = min(xs), max(xs)
        k = (new_end - new_start) / (b - a) if b - a > EPS else 1.0

        def tmap(x):
            return new_start + (x - a) * k
    else:
        def tmap(x):
            return time_pivot + (x - time_pivot) * time_scale
    n = 0
    for fc, pts in sel:
        vp = value_pivot * time_keys.value_unit(fc)
        vs = value_scale if method != "Start/End" else 1.0
        for kp in pts:
            x, y = kp.co.x, kp.co.y
            nx, ny = tmap(x), vp + (y - vp) * vs
            ks = tmap(x + 1.0) - nx
            for h in (kp.handle_left, kp.handle_right):
                h.x, h.y = nx + (h.x - x) * ks, ny + (h.y - y) * vs
            kp.co.x, kp.co.y = nx, ny
            n += 1
        fc.update()
    return n


def snap_selected(context, snap="Times", time_multiple=1.0, value_multiple=1.0):
    n = 0
    for fc, pts in selected_keys(context):
        u = time_keys.value_unit(fc)
        for kp in pts:
            hit = False
            if snap in ("Times", "Both"):
                dx = time_keys._snap(kp.co.x, time_multiple) - kp.co.x
                if abs(dx) > 1e-9:
                    time_keys._move(kp, dx)
                    hit = True
            if snap in ("Values", "Both"):
                dv = time_keys._snap(kp.co.y / u, value_multiple) * u - kp.co.y
                if abs(dv) > 1e-12:
                    time_keys._offset_value(kp, dv)
                    hit = True
            n += hit
        fc.update()
    return n


# --- Add / Remove Inbetween ---------------------------------------------------------------------------------

def inbetween(context, delta):
    """Keys at or after the current frame on the editor's curves move by ``delta`` frames (Maya ``-option over``:
    a key moved onto another stays a separate key). Count moved."""
    frame = context.scene.frame_current + context.scene.frame_subframe
    n = 0
    for fc in editor_curves(context):
        pts = [kp for kp in fc.keyframe_points if kp.co.x >= frame - EPS]
        if delta < 0:
            pts.sort(key=lambda kp: kp.co.x)
        else:
            pts.sort(key=lambda kp: -kp.co.x)
        for kp in pts:
            time_keys._move(kp, delta)
        if pts:
            fc.update()
            n += len(pts)
    return n


# --- Mute / Unmute Key --------------------------------------------------------------------------------------

def mute_modifiers(fc):
    return [m for m in fc.modifiers if m.type == 'STEPPED' and m.name == MUTE_NAME]


def muted_times(fc):
    """Times of the keys the kit's mute modifiers hold (key times inside a [start, end) range)."""
    spans = [(m.frame_start, m.frame_end) for m in mute_modifiers(fc)]
    return sorted(kp.co.x for kp in fc.keyframe_points
                  if any(a - EPS <= kp.co.x <= b + EPS for a, b in spans))


def set_muted(fc, times):
    """Rebuild the mute modifiers: each run of consecutive muted keys holds its first key's value until the next
    unmuted key (to the end after the last key)."""
    for m in mute_modifiers(fc):
        fc.modifiers.remove(m)
    keys = sorted(kp.co.x for kp in fc.keyframe_points)
    muted = [any(abs(x - t) <= EPS for t in times) for x in keys]
    i = 0
    while i < len(keys):
        if not muted[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(keys) and muted[j + 1]:
            j += 1
        start = keys[i]
        end = keys[j + 1] - _END_GAP if j + 1 < len(keys) else _FAR
        m = fc.modifiers.new('STEPPED')
        m.name = MUTE_NAME
        m.frame_step = max(1.0, end - start + 1.0)
        m.frame_offset = start
        m.use_restricted_range = True
        m.frame_end = end            # end before start: Blender clamps start to end otherwise
        m.frame_start = start
        m.blend_in = m.blend_out = 0.0
        m.show_expanded = False
        i = j + 1
    fc.update()


def mute_selected(context, mute=True):
    """Maya Keys > Mute / Unmute Key on the selected keys. Count of keys changed."""
    n = 0
    for fc, pts in selected_keys(context):
        times = muted_times(fc)
        sel = [kp.co.x for kp in pts]
        if mute:
            new = sorted(set(times) | set(sel))
        else:
            new = [t for t in times if not any(abs(t - s) <= EPS for s in sel)]
        if new != times:
            n += len(sel)
            set_muted(fc, new)
    return n


# --- Default In / Out Tangent -------------------------------------------------------------------------------

def _prefs():
    from .. import preferences
    try:
        return preferences.get()
    except (KeyError, AttributeError):
        return None


def default_tangents():
    p = _prefs()
    if p is None:
        return "AUTO", "AUTO"
    return p.default_in_tangent, p.default_out_tangent


def apply_default(fc, kp):
    """The default in / out tangent (like Maya) on a key the kit just set (Auto = Blender's own new key: untouched)."""
    tin, tout = default_tangents()
    if tin == "AUTO" and tout == "AUTO":
        return False
    if tin == tout:
        time_keys.apply_tangent(kp, tin, fc)
    else:
        _default_side(kp, tin, "IN", fc)
        _default_side(kp, tout, "OUT", fc)
    fc.update()
    return True


def _default_side(kp, kind, side, fc=None):
    """One side of a new key. Blender's interpolation belongs to the segment after a key, so only a Stepped out
    tangent changes it; a Linear side = a Vector handle (points at the neighbour key), the neighbour segment keeps
    its shape (Maya: the other key's own tangent)."""
    if kind == "AUTO":
        return
    if kind == "STEPPED":            # out only (Maya has no stepped in tangent)
        kp.interpolation = 'CONSTANT'
        return
    # a Flat side next to a different one is a free handle (an aligned one would follow the other side)
    handle = {"LINEAR": 'VECTOR', "FLAT": 'FREE'}.get(kind) or time_keys.TANGENTS[kind][1]
    setattr(kp, "handle_left_type" if side == "IN" else "handle_right_type", handle)
    if kind == "FLAT":
        (kp.handle_left if side == "IN" else kp.handle_right).y = kp.co.y
    if fc is not None:
        from . import maya_tangents
        maya_tangents.mark(fc, kp, kind, side)


def _new_curve_weights(idd, full, index):
    from . import graph_weights
    from .. import compat
    try:
        for fc in compat.id_fcurves(idd):
            if fc.data_path == full and (index is None or index < 0 or fc.array_index == index)                     and len(fc.keyframe_points) == 1:
                graph_weights.apply_default(fc)
    except (AttributeError, TypeError, ReferenceError):
        pass


def after_insert(owner, path, index, frame):
    """Apply the default tangents to the keys ``owner.keyframe_insert(path, index=index, frame=frame)`` made.
    ``owner`` is an ID or a struct inside one (pose bone). A curve this insert created gets the Default Tangent
    Weight (operators/graph_weights.apply_default)."""
    from .. import compat
    idd = owner.id_data
    full = path if owner == idd else owner.path_from_id(path)
    _new_curve_weights(idd, full, index)
    from . import maya_tangents
    n = 0
    for fc in compat.id_fcurves(idd):
        if fc.data_path != full or (index is not None and index >= 0 and fc.array_index != index):
            continue
        kp = next((k for k in fc.keyframe_points if abs(k.co.x - frame) <= EPS), None)
        if kp is not None and apply_default(fc, kp):
            n += 1
        # Maya tangent shapes on the curve (the new key and its neighbours; #151, #210)
        maya_tangents.apply(fc)
    return n


# --- Select masks -------------------------------------------------------------------------------------------

MASKS = ("graph_select_curve", "graph_select_key", "graph_select_in", "graph_select_out")
_mask = {"last": None}
MASK_POLL = 0.05


def masks():
    p = _prefs()
    if p is None:
        return (True, True, True, True)
    return tuple(bool(getattr(p, m)) for m in MASKS)


def _flags(fc):
    import numpy as np
    n = len(fc.keyframe_points)
    out = []
    for attr in ("select_control_point", "select_left_handle", "select_right_handle"):
        a = np.empty(n, dtype=bool)
        fc.keyframe_points.foreach_get(attr, a)
        out.append(a)
    return out


def _curves(scene):
    from .. import compat
    for ob in scene.objects:
        if ob is None:
            continue
        for fc in compat.id_fcurves(ob):
            yield ob, fc


def _signature(scene):
    return {(ob.name, fc.data_path, fc.array_index): _flags(fc) for ob, fc in _curves(scene)}


def mask_step(scene, curve, key, tin, tout):
    """One poll: drop what the last selection added against the masks. Returns how many curves changed."""
    if curve and key and tin and tout:
        _mask["last"] = None
        return 0
    last = _mask["last"]
    changed = 0
    now = {}
    for ob, fc in _curves(scene):
        k = (ob.name, fc.data_path, fc.array_index)
        flags = _flags(fc)
        prev = last.get(k) if last else None
        if prev is not None and len(prev[0]) == len(flags[0]):
            ctrl_new = flags[0] & ~prev[0]
            left_new = flags[1] & ~prev[1]
            right_new = flags[2] & ~prev[2]
            hit = False
            pts = fc.keyframe_points
            if not key and ctrl_new.any():
                if curve:       # Maya curve pick: the whole curve
                    pts.foreach_set("select_control_point", [True] * len(pts))
                else:
                    for i in ctrl_new.nonzero()[0]:
                        pts[int(i)].select_control_point = False
                hit = True
            if not tin and left_new.any():
                for i in left_new.nonzero()[0]:
                    pts[int(i)].select_left_handle = False
                hit = True
            if not tout and right_new.any():
                for i in right_new.nonzero()[0]:
                    pts[int(i)].select_right_handle = False
                hit = True
            if hit:
                changed += 1
                flags = _flags(fc)
        now[k] = flags
    _mask["last"] = now
    return changed


def remember_masks(scene=None):
    scene = scene or bpy.context.scene
    _mask["last"] = _signature(scene) if scene else None


def _graph_open():
    wm = bpy.context.window_manager
    return any(a.type == 'GRAPH_EDITOR' for w in wm.windows for a in w.screen.areas)


def _mask_tick():
    try:
        scene = bpy.context.scene
        m = masks()
        if scene is not None and not all(m) and _graph_open():
            if mask_step(scene, *m):
                for w in bpy.context.window_manager.windows:
                    for a in w.screen.areas:
                        if a.type in {'GRAPH_EDITOR', 'DOPESHEET_EDITOR'}:
                            a.tag_redraw()
        else:
            _mask["last"] = None
    except (KeyError, AttributeError, ReferenceError):
        pass
    return MASK_POLL


@bpy.app.handlers.persistent
def _mask_reset(*_args):
    _mask["last"] = None


# --- operators ----------------------------------------------------------------------------------------------

@undo_steps.no_redo_panel
class ALLSET_OT_mute_key(bpy.types.Operator):
    """Mute the selected keys: the curve holds the key's value until the next unmuted key (Maya Keys > Mute Key;
    Blender has no per-key mute: a Stepped modifier named "Maya mute" holds the value)"""
    bl_idname = "allset.mute_key"
    bl_label = "Mute Key"
    bl_options = {'REGISTER', 'UNDO'}

    mute: BoolProperty(name="Mute", default=True, options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        if props.mute:
            return cls.__doc__
        return "Unmute the selected keys: the curve plays through them again (Maya Keys > Unmute Key)"

    def execute(self, context):
        if not in_key_editor(context):
            self.report({'WARNING'}, "Mute Key works on the keys selected in the Graph Editor or Dope Sheet")
            return {'CANCELLED'}
        n = mute_selected(context, self.mute)
        if not n:
            # Maya's Mute / Unmute Key error texts
            self.report({'WARNING'}, "No keys selected to mute" if self.mute else "No muted keys selected to unmute")
            return {'CANCELLED'}
        _redraw(context)
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_graph_inbetween(bpy.types.Operator):
    """Add or remove an inbetween: the keys after the current time on the curves shown move one frame later or
    earlier (Maya Keys > Add / Remove Inbetween)"""
    bl_idname = "allset.graph_inbetween"
    bl_label = "Add Inbetween"
    bl_options = {'REGISTER', 'UNDO'}

    delta: EnumProperty(items=(("ADD", "Add Inbetween", ""), ("REMOVE", "Remove Inbetween", "")),
                        name="Inbetween", options={'SKIP_SAVE'})

    def execute(self, context):
        if not in_key_editor(context):
            return bpy.ops.allset.key_edit(action="ADD_INBETWEEN" if self.delta == "ADD" else "REMOVE_INBETWEEN")
        if not inbetween(context, 1.0 if self.delta == "ADD" else -1.0):
            self.report({'WARNING'}, "No keys after the current time")
        _redraw(context)
        return {'FINISHED'}


SELECT_PRESETS = (("ALL", "All", "Curves, keys and tangents can be picked (Maya Select > All)"),
                  ("ONLY_CURVE", "Only Curve", "Only curves can be picked (Maya Select > Only Curve)"))


class ALLSET_OT_graph_select_type(bpy.types.Operator):
    """Choose what a click or drag picks in the Graph Editor (Maya Select > All / Only Curve)"""
    bl_idname = "allset.graph_select_type"
    bl_label = "Select Type"
    bl_options = {'REGISTER'}

    preset: EnumProperty(items=SELECT_PRESETS, name="Preset", options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return next(d for k, _l, d in SELECT_PRESETS if k == props.preset)

    def execute(self, context):
        p = _prefs()
        if p is None:
            return {'CANCELLED'}
        only = self.preset == "ONLY_CURVE"
        p.graph_select_curve = True
        p.graph_select_key = p.graph_select_in = p.graph_select_out = not only
        remember_masks(context.scene)
        return {'FINISHED'}


# --- Dope Sheet Curves items that are Graph Editor commands -----------------------------------------
# Maya's Dope Sheet Curves menu runs the Graph Editor's curve commands (Euler Filter, Smooth Filter, Resample, Isolate;
# same annotations) on the curves of the selected keys. Blender's
# graph.* operators only run in a Graph Editor, so the Dope Sheet area turns into one for the call and back.

DOPE_GRAPH_OPS = {"EULER": ("graph.euler_filter", {}), "BUTTERWORTH": ("graph.butterworth_smooth", {}),
                  "GAUSSIAN": ("graph.gaussian_smooth", {}), "RESAMPLE": ("graph.bake_keys", {}),
                  "ISOLATE": ("graph.hide", {"unselected": True})}


def curves_with_selected_keys(fcurves):
    return [fc for fc in fcurves if any(k.select_control_point for k in fc.keyframe_points)]


class ALLSET_OT_dope_graph_op(bpy.types.Operator):
    """Run this Graph Editor curve command on the curves of the selected keys (Maya Dope Sheet > Curves)"""
    bl_idname = "allset.dope_graph_op"
    bl_label = "Curve Command"
    bl_options = {'REGISTER', 'UNDO'}

    command: EnumProperty(items=[(k, k.title(), "") for k in DOPE_GRAPH_OPS], options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        area = context.area
        return area is not None and area.type in {'DOPESHEET_EDITOR', 'GRAPH_EDITOR'}

    def execute(self, context):
        idname, props = DOPE_GRAPH_OPS[self.command]
        mod, name = idname.split(".")
        op = getattr(getattr(bpy.ops, mod), name)
        area = context.area
        if area.type == 'GRAPH_EDITOR':
            return op('EXEC_DEFAULT', **props)
        fcurves = list(getattr(context, "editable_fcurves", None) or getattr(context, "visible_fcurves", None) or ())
        picked = curves_with_selected_keys(fcurves)
        if not picked:
            self.report({'WARNING'}, "Select keys of the curves to filter.")
            return {'CANCELLED'}
        saved = {fc: fc.select for fc in fcurves}
        for fc in fcurves:
            fc.select = fc in picked              # the Graph Editor commands act on the selected curves
        old = area.ui_type
        try:
            area.ui_type = 'FCURVES'
            region = next(r for r in area.regions if r.type == 'WINDOW')
            with context.temp_override(area=area, region=region, space_data=area.spaces.active):
                res = op('EXEC_DEFAULT', **props)
        except (RuntimeError, StopIteration) as ex:
            self.report({'WARNING'}, str(ex).strip() or "The curve command did not run")
            res = {'CANCELLED'}
        finally:
            area.ui_type = old
            for fc, sel in saved.items():
                try:
                    fc.select = sel
                except ReferenceError:      # Resample can replace curves
                    pass
        return res


classes = (ALLSET_OT_mute_key, ALLSET_OT_graph_inbetween, ALLSET_OT_graph_select_type, ALLSET_OT_dope_graph_op)


def register_bindings():
    bpy.app.handlers.load_post.append(_mask_reset)
    if not bpy.app.timers.is_registered(_mask_tick):
        bpy.app.timers.register(_mask_tick, first_interval=MASK_POLL, persistent=True)


def unregister_bindings():
    if bpy.app.timers.is_registered(_mask_tick):
        bpy.app.timers.unregister(_mask_tick)
    if _mask_reset in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_mask_reset)
    _mask["last"] = None
