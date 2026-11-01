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
"""

import bpy

from .. import live_refs

MODES = {'OBJECT', 'POSE', 'EDIT_ARMATURE'}
SELECT_OPS = {"VIEW3D_OT_select_box", "VIEW3D_OT_select_lasso"}
_TICK = 0.05
_GIVE_UP = 1.5
_pending = []


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
        "seen": False, "waited": 0.0, "mode": context.mode,
    })
    if not bpy.app.timers.is_registered(_watch):
        bpy.app.timers.register(_watch, first_interval=_TICK)
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


def objects_instead(context, op, mode):
    """A drag in Pose / joint Edit mode that hit no joint: Maya selects the objects in it (Blender's box there only
    looks at bones). Leave the mode and run the same box / lasso on objects."""
    from . import joint_selection
    joint_selection.leave(context, clear_selection=(mode == 'SET'))
    p = op.properties
    if op.bl_idname == "VIEW3D_OT_select_box":
        bpy.ops.view3d.select_box(xmin=p.xmin, xmax=p.xmax, ymin=p.ymin, ymax=p.ymax, mode=mode, wait_for_input=False)
    else:
        bpy.ops.view3d.select_lasso(path=[{"name": "", "loc": tuple(q.loc), "time": 0.0} for q in p.path], mode=mode)


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


def _finish(entry):
    window = live_refs.window(entry["window"])
    if window is None:
        return
    wm = bpy.context.window_manager
    if not len(wm.operators):
        return
    op = wm.operators[-1]
    if op.as_pointer() == entry["last"] or op.bl_idname not in SELECT_OPS:
        return
    poly = region_of(op)
    if poly is None:
        return
    area = next((a for a in window.screen.areas if a.as_pointer() == entry["area"]), None)
    region = next((r for r in area.regions if r.as_pointer() == entry["region"]), None) if area else None
    if region is None:
        return
    with bpy.context.temp_override(window=window, area=area, region=region):
        picked = apply(bpy.context, poly, op.properties.mode, entry["snap"])
        if not picked and entry["mode"] in {'POSE', 'EDIT_ARMATURE'}:
            objects_instead(bpy.context, op, op.properties.mode)
            picked = True
        if picked:
            from . import undo_pairs           # one undo with Blender's box select step before it
            undo_pairs.push(bpy.context.scene, "Select")
            for a in window.screen.areas:
                a.tag_redraw()


def _running(win_ptr):
    window = live_refs.window(win_ptr)
    try:
        return window is not None and any(op.bl_idname in SELECT_OPS for op in window.modal_operators)
    except ReferenceError:
        return False


def _watch():
    for entry in list(_pending):
        running = _running(entry["window"])
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
    return _TICK if _pending else None


def cancel_all():
    _pending.clear()
    if bpy.app.timers.is_registered(_watch):
        bpy.app.timers.unregister(_watch)
