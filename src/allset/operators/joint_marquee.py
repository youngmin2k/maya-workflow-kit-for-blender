# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya marquee / lasso on joints in the Maya layout's views, where the kit draws the joints (``ui/maya_joints.py``)
and Blender's bones are off, so Blender's box and lasso selection can't see them.

Maya's rules: a marquee or lasso hits a joint when it touches one of its drawn lines (sphere rings or a bone to a
child — a bone belongs to its parent joint); each skeleton keeps only its hit joint closest to the root; when any
joint is hit the meshes in the same region are dropped (joints have the higher selection priority); Shift toggles,
Ctrl removes, Ctrl+Shift adds, as for objects.

``allset.select_through`` (first in the select tools' drag keymaps) calls ``begin``: the selection is remembered and,
once Blender's box / lasso modal has ended, the region it registered is checked against the drawn joints. When a joint
was hit the remembered selection comes back and the joints are applied with the drag's mode.

A box that changes nothing in Blender's eyes (nothing selected before, no Blender element inside) ends CANCELLED and is
not registered, so the box is also read from the running operator while it is drawn and used when nothing new was
registered. Blender pushed no undo step then, so the kit's step stands alone. A running lasso keeps its path to
itself until it ends, so the path of such a lasso is the pointer track a draw cursor callback collects while it runs.
"""

import bpy

from .. import live_refs

MODES = {'OBJECT', 'POSE', 'EDIT_ARMATURE'}
SELECT_OPS = {"VIEW3D_OT_select_box", "VIEW3D_OT_select_lasso"}
_TICK = 0.05
_GIVE_UP = 1.5
_pending = []
_track = {"handle": None, "region": 0, "pts": []}      # pointer track of the running drag (region px)


def _track_cursor(*args):
    """Draw cursor callback: called for the region under the pointer while it redraws (a lasso redraws on every
    move). Keeps the pointer track of the drag's region."""
    region = bpy.context.region
    if region is None or region.as_pointer() != _track["region"] or not args:
        return
    xy = args[0] if isinstance(args[0], (tuple, list)) else args[:2]     # Blender passes the pointer first
    try:
        x, y = float(xy[0]) - region.x, float(xy[1]) - region.y       # window px -> region px
    except (TypeError, ValueError, IndexError):
        return
    pts = _track["pts"]
    if not pts or pts[-1] != (x, y):
        pts.append((x, y))


def _track_start(region):
    _track["region"], _track["pts"] = region.as_pointer(), []
    if _track["handle"] is None:
        _track["handle"] = bpy.context.window_manager.draw_cursor_add(_track_cursor, (), 'VIEW_3D', 'WINDOW')


def _track_stop():
    if _track["handle"] is not None:
        try:
            bpy.context.window_manager.draw_cursor_remove(_track["handle"])
        except (ValueError, ReferenceError, AttributeError):
            pass
        _track["handle"] = None
    _track["region"] = 0


def begin(context):
    from ..ui import maya_joints
    space = context.space_data
    if (context.mode not in MODES or context.region is None or context.region.type != 'WINDOW'
            or not maya_joints.is_maya_view(space, getattr(getattr(context, "window", None), "workspace", None))):
        return False
    wm = context.window_manager
    last = wm.operators[-1].as_pointer() if len(wm.operators) else 0
    _pending.append({
        "window": live_refs.pointer(context.window), "area": context.area.as_pointer(),
        "region": context.region.as_pointer(), "last": last, "snap": snapshot(context),
        "seen": False, "waited": 0.0, "mode": context.mode, "box": None,
    })
    if not bpy.app.timers.is_registered(_watch):
        bpy.app.timers.register(_watch, first_interval=_TICK)
    _track_start(context.region)
    return True


def snapshot(context):
    objs = {ob.name: ob.select_get() for ob in context.scene.objects}
    act = context.view_layer.objects.active
    bones = {}
    from ..ui.channel_box import bone_selected
    for ob in context.scene.objects:
        if ob.type != 'ARMATURE':
            continue
        if ob.mode == 'EDIT':
            bones[ob.name] = ('EDIT', {eb.name: (eb.select, eb.select_head, eb.select_tail)
                                       for eb in ob.data.edit_bones},
                              ob.data.edit_bones.active.name if ob.data.edit_bones.active else None)
        else:
            bones[ob.name] = ('POSE', {pb.name: bone_selected(pb) for pb in ob.pose.bones},
                              ob.data.bones.active.name if ob.data.bones.active else None)
    return {"objects": objs, "active": act.name if act else None, "bones": bones}


def restore(context, snap):
    from ..ui.channel_box import set_bone_selected
    for ob in context.scene.objects:
        want = snap["objects"].get(ob.name)
        if want is not None and ob.select_get() != want:
            ob.select_set(want)
    act = snap["active"]
    if act and act in context.scene.objects:
        context.view_layer.objects.active = context.scene.objects[act]
    for name, (kind, states, active) in snap["bones"].items():
        ob = context.scene.objects.get(name)
        if ob is None:
            continue
        if kind == 'EDIT' and ob.mode == 'EDIT':
            for eb in ob.data.edit_bones:
                if eb.name in states:
                    eb.select, eb.select_head, eb.select_tail = states[eb.name]
            ob.data.edit_bones.active = ob.data.edit_bones.get(active) if active else None
        elif kind == 'POSE':
            for pb in ob.pose.bones:
                if pb.name in states:
                    set_bone_selected(pb, states[pb.name])
            ob.data.bones.active = ob.data.bones.get(active) if active else None


def region_of(op):
    """The screen polygon (region px) of a finished select_box / select_lasso, or None."""
    props = op.properties
    if op.bl_idname == "VIEW3D_OT_select_box":
        x0, x1, y0, y1 = props.xmin, props.xmax, props.ymin, props.ymax
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    path = [tuple(p.loc) for p in props.path]
    return path if len(path) >= 3 else None


def modifiers(mode):
    """(shift, ctrl) of joint_selection.select for a box mode: SET replace, XOR toggle, SUB remove, ADD add."""
    return {'XOR': (True, False), 'SUB': (False, True), 'ADD': (True, True)}.get(mode, (False, False))


def objects_instead(context, poly, mode, lasso):
    """A drag in Pose / joint Edit mode that hit no joint: Maya selects the objects in it (Blender's box there only
    looks at bones). Leave the mode and run the same box / lasso (``poly`` from ``region_of``) on objects."""
    from . import joint_selection
    joint_selection.leave(context, clear_selection=(mode == 'SET'))
    if not lasso:
        (x0, y0), _b, (x1, y1), _d = poly
        bpy.ops.view3d.select_box(xmin=x0, xmax=x1, ymin=y0, ymax=y1, mode=mode, wait_for_input=False)
    else:
        bpy.ops.view3d.select_lasso(path=[{"name": "", "loc": q, "time": 0.0} for q in poly], mode=mode)


def apply(context, poly, mode, snap):
    """Maya's joint rules for a finished drag. Returns the joints selected (empty: Blender's result stands)."""
    from ..ui import maya_joints
    from . import joint_selection
    space = context.space_data
    picks = []
    for ob in context.scene.objects:
        if ob.type != 'ARMATURE' or ob.hide_select or not ob.visible_get() \
                or not ob.visible_in_viewport_get(space):
            continue
        name = maya_joints.region_pick(context, ob, poly)
        if name is not None:
            picks.append((ob, name))
    if not picks:
        return []
    restore(context, snap)
    shift, ctrl = modifiers(mode)
    for i, (ob, name) in enumerate(picks):
        if i > 0 and mode == 'SET':
            shift, ctrl = True, True          # the rest of a replace adds
        joint_selection.select(context, ob, name, shift, ctrl)
    return [n for _o, n in picks]


def _registered(entry):
    """The box / lasso Blender registered for this drag, or None (it ended CANCELLED)."""
    wm = bpy.context.window_manager
    if not len(wm.operators):
        return None
    op = wm.operators[-1]
    if op.as_pointer() == entry["last"] or op.bl_idname not in SELECT_OPS:
        return None
    return op


def _finish(entry):
    window = live_refs.window(entry["window"])
    if window is None:
        return
    op = _registered(entry)
    if op is not None:
        poly, mode = region_of(op), op.properties.mode
    elif entry["box"] is not None:
        poly, mode = entry["box"]
    elif entry.get("lasso") and len(entry.get("track", ())) >= 3:
        poly, mode = entry["track"], entry["lasso"]
    else:
        return
    if poly is None:
        return
    area = next((a for a in window.screen.areas if a.as_pointer() == entry["area"]), None)
    region = next((r for r in area.regions if r.as_pointer() == entry["region"]), None) if area else None
    if region is None:
        return
    with bpy.context.temp_override(window=window, area=area, region=region):
        picked = apply(bpy.context, poly, mode, entry["snap"])
        if not picked and entry["mode"] in {'POSE', 'EDIT_ARMATURE'}:
            lasso = (op.bl_idname == "VIEW3D_OT_select_lasso") if op is not None else bool(entry.get("lasso"))
            objects_instead(bpy.context, poly, mode, lasso)
            picked = True
        if picked:
            if op is not None:
                from . import undo_pairs       # one undo with Blender's box select step before it
                undo_pairs.push(bpy.context.scene, "Select")
            else:
                bpy.ops.ed.undo_push(message="Select")
            for a in window.screen.areas:
                a.tag_redraw()


def _running(entry):
    """Blender's box / lasso modal of this drag is still running; keeps the box drawn so far in ``entry``."""
    window = live_refs.window(entry["window"])
    try:
        ops = [op for op in window.modal_operators if op.bl_idname in SELECT_OPS] if window is not None else []
        for op in ops:
            if op.bl_idname == "VIEW3D_OT_select_box":
                p = op.properties
                if p.xmin != p.xmax or p.ymin != p.ymax:
                    entry["box"] = (region_of(op), p.mode)
            else:
                entry["lasso"] = op.properties.mode
                entry["track"] = list(_track["pts"])
        return bool(ops)
    except ReferenceError:
        return False


def _watch():
    for entry in list(_pending):
        running = _running(entry)
        entry["seen"] = entry["seen"] or running
        entry["waited"] += _TICK
        if entry["seen"] and not running:
            _pending.remove(entry)
            try:
                _finish(entry)
            except (ReferenceError, RuntimeError, AttributeError, KeyError) as e:
                print("allset: joint marquee:", e)
        elif not entry["seen"] and entry["waited"] >= _GIVE_UP:
            _pending.remove(entry)
    if not _pending:
        _track_stop()
    return _TICK if _pending else None


def cancel_all():
    _pending.clear()
    _track_stop()
    if bpy.app.timers.is_registered(_watch):
        bpy.app.timers.unregister(_watch)
