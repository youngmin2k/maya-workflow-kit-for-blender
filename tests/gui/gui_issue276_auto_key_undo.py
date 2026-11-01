"""#276: one Ctrl+Z takes back one move of a rig control, keys included, and one Shift+Z brings it back.

The session: Maya layout, an armature whose control bone has a custom shape, Pose mode, the control picked with a
click, the control keyed at frame 1 and the moves made at frame 10. Each case makes two moves, then presses Ctrl+Z at
a human pace until the pose before the first move is back, then Shift+Z until the last move is back. Every press must
take back (bring back) exactly one move together with its key, so the states after the presses are history 1, 0 and
then 1, 2.

Cases: no animation; the kit's Auto Key with manipulator drags, with the mouse resting over the Channel Box, with
rotations and moves started like R / G in Blender (the transform modal); Blender's own auto keying; a cancelled rotation between
the moves; two moves right after each other; a Rigify rig's torso control. Also a marquee over a joint the kit draws
(Blender's box select, then the kit's joint pick): one Ctrl+Z gives back the earlier selection, one Shift+Z the
marquee's."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras import view3d_utils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, setup, step, win  # noqa: E402

GUI_TIMEOUT = 900
C = {}
IDLE_TICKS = 4          # time between actions: the kit's watch timers and the Auto Key timer all run
MAX_PRESSES = 6


def mod(name):
    return import_module(MODULE + name)


def main_view():
    toolbox = mod(".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def ov():
    area, region = main_view()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def rig():
    return bpy.data.objects.get(C.get("rig", "Rig276"))


def bone():
    return C.get("bone", "ctrl")


def state():
    """The pose and the key count, rounded: one entry of the undo history."""
    ob = rig()
    pose = tuple(round(v, 4) for pb in ob.pose.bones for row in pb.matrix_basis for v in row)
    keys = 0
    ad = ob.animation_data
    if ad is not None and ad.action is not None:
        keys = sum(len(fc.keyframe_points) for fc in mod(".compat").id_fcurves(ob))
    return pose, keys


def screen_of(world):
    _a, r = main_view()
    p = view3d_utils.location_3d_to_region_2d(r, r.data, world)
    return int(r.x + p.x), int(r.y + p.y)


def control_head():
    ob = rig()
    return ob.matrix_world @ ob.pose.bones[bone()].head


def add(fn, name):
    fn.__name__ = name
    step(fn)


def release_modifiers():
    """A simulated key event's modifiers stay in the window's state: let go of them, or the next click or drag is a
    Ctrl / Shift one."""
    ev('LEFT_CTRL', 'RELEASE')
    ev('LEFT_SHIFT', 'RELEASE')


def idle(tag, n=IDLE_TICKS, where=None):
    for i in range(n):
        def s_idle(i=i):
            if where is not None:
                x, y = where()
                ev('MOUSEMOVE', 'NOTHING', x=x + (i % 3) * 6, y=y + (i % 2) * 5)
        add(s_idle, f"{tag}_idle{i}")


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_rig():
    with ov():
        arm = bpy.data.armatures.new("Rig276")
        ob = bpy.data.objects.new("Rig276", arm)
        bpy.context.scene.collection.objects.link(ob)
        for o in bpy.context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
        root = arm.edit_bones.new("root")
        root.head, root.tail = (0, 0, 0), (0, 0, 0.6)
        ctrl = arm.edit_bones.new("ctrl")
        ctrl.head, ctrl.tail = (0, 0, 0.6), (0, 0, 1.0)
        ctrl.parent = root
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.mesh.primitive_circle_add(radius=1.0, location=(4, 4, 0))
        shape = bpy.context.view_layer.objects.active
        shape.name = "WGT_ctrl276"
        shape.hide_set(True)
        ob.pose.bones["ctrl"].custom_shape = shape
        for o in bpy.context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.view3d.view_selected()
        bpy.ops.pose.select_all(action='DESELECT')
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    check("rig in Pose mode", rig().mode == 'POSE')


idle("view", 2)


@step
def s_pick():
    """Click the control's widget (a point on its circle, away from the bone line)."""
    ob = rig()
    pb = ob.pose.bones["ctrl"]
    p = ob.matrix_world @ (pb.head + pb.bone.x_axis * pb.length)
    x, y = screen_of(p)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


idle("picked", 2)


@step
def s_picked():
    cb = mod(".ui.channel_box")
    ob = rig()
    sel = [pb.name for pb in ob.pose.bones if cb.bone_selected(pb)]
    if sel != ["ctrl"]:          # pick it directly: the case is the undo, not the pick
        for pb in ob.pose.bones:
            cb.set_bone_selected(pb, pb.name == "ctrl")
        ob.data.bones.active = ob.data.bones["ctrl"]
    check(f"control picked by a click ({sel})", sel == ["ctrl"])


def dock_point():
    """A point in the Channel Box part of the dock (the mouse rests there between moves)."""
    maya_dock = mod(".ui.maya_dock")
    for a in win().screen.areas:
        if a.type == 'PROPERTIES' and maya_dock.role(a) in ("STACK", "CHANNEL_BOX"):
            r = next(r for r in a.regions if r.type == 'WINDOW')
            return r.x + r.width // 2, r.y + int(r.height * 0.75)
    _a, r = main_view()
    return r.x + 30, r.y + 30


def drag(tag, dx, dy):
    """A Move manipulator drag from the control's centre."""
    def s_hover():                       # the manipulator highlights its handle before the press
        x, y = screen_of(control_head())
        C["drag"] = (x, y)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    add(s_hover, f"{tag}_hover")

    def s_press():
        x, y = C["drag"]
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    add(s_press, f"{tag}_press")
    for i in range(1, 5):
        def s_move(i=i):
            x, y = C["drag"]
            ev('MOUSEMOVE', 'NOTHING', x=x + dx * i // 4, y=y + dy * i // 4)
        add(s_move, f"{tag}_move{i}")

    def s_release():
        x, y = C["drag"]
        ev('LEFTMOUSE', 'RELEASE', x=x + dx, y=y + dy)
    add(s_release, f"{tag}_release")


def _modal(tag, dx, dy, start, cancel=False):
    """A transform modal started from the view (R / G), mouse moves, a click to confirm (or a right click to
    cancel)."""
    def s_start():
        x, y = screen_of(control_head())
        C["drag"] = (x + 80, y)
        ev('MOUSEMOVE', 'NOTHING', x=x + 80, y=y)
        start()
    add(s_start, f"{tag}_start")
    for i in range(1, 5):
        def s_move(i=i):
            x, y = C["drag"]
            ev('MOUSEMOVE', 'NOTHING', x=x + dx * i // 4, y=y + dy * i // 4)
        add(s_move, f"{tag}_move{i}")

    def s_confirm():
        x, y = C["drag"]
        button = 'RIGHTMOUSE' if cancel else 'LEFTMOUSE'
        ev(button, 'PRESS', x=x + dx, y=y + dy)
        ev(button, 'RELEASE', x=x + dx, y=y + dy)
    add(s_confirm, f"{tag}_confirm")


def rotate(tag, dx, dy):
    def start():
        with ov():
            bpy.ops.transform.rotate('INVOKE_DEFAULT')
    _modal(tag, 0, dx + dy, start)         # across the line to the pivot: the angle changes


def grab(tag, dx, dy):
    """Blender's G move (in Maya mode the G key is Repeat Last)."""
    def start():
        with ov():
            bpy.ops.transform.translate('INVOKE_DEFAULT')
    _modal(tag, dx, dy, start)


def cancelled_rotate(tag):
    def start():
        with ov():
            bpy.ops.transform.rotate('INVOKE_DEFAULT')
    _modal(tag, 0, 60, start, cancel=True)


def press_until(tag, key, shift, ctrl, target, store):
    for i in range(MAX_PRESSES):
        def s_press(i=i):
            st = state()
            if C.get(f"{store}_done"):
                return
            if i:
                C[store].append(st)
            if st == C["hist"][target]:
                C[f"{store}_done"] = True
                return
            _a, r = main_view()
            ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + 40)
            ev(key, 'PRESS', ctrl=ctrl, shift=shift)
            ev(key, 'RELEASE', ctrl=ctrl, shift=shift)
            release_modifiers()
        add(s_press, f"{tag}_{store}{i}")
        idle(f"{tag}_{store}_after{i}", 2)


def undo_redo(tag):
    def s_mark():
        C["hist"] = [C[f"{tag}_s0"], C[f"{tag}_s1"], C[f"{tag}_s2"]]
        C["undo"], C["redo"] = [], []
        C["undo_done"] = C["redo_done"] = False
        print(f"[{tag}] history keys", [h[1] for h in C["hist"]], flush=True)
    add(s_mark, f"{tag}_mark")
    press_until(tag, 'Z', False, True, 0, "undo")
    press_until(tag, 'Z', True, False, 2, "redo")          # Maya Shift+Z

    def s_count():
        hist = C["hist"]
        undo = [hist.index(s) if s in hist else "?" for s in C["undo"]]
        redo = [hist.index(s) if s in hist else "?" for s in C["redo"]]
        print(f"[{tag}] after each Ctrl+Z {undo}, after each Shift+Z {redo}", flush=True)
        check(f"{tag}: each Ctrl+Z takes back one move with its key (history after each press {undo})",
              undo == [1, 0])
        check(f"{tag}: each Shift+Z brings back one move with its key (history after each press {redo})",
              redo == [1, 2])
    add(s_count, f"{tag}_count")


def case(tag, auto_key=False, rest=None, blender_key=False, action=drag, between=IDLE_TICKS, cancel_between=False):
    def s_prepare():
        ob = rig()
        with ov():
            ob.animation_data_clear()
            if auto_key or blender_key:
                # keys at frame 1, the moves at frame 10: each move adds / replaces the key at 10
                pb = ob.pose.bones[bone()]
                bpy.context.scene.frame_set(1)
                pb.keyframe_insert("location", frame=1)
                pb.keyframe_insert("rotation_quaternion", frame=1)
                bpy.context.scene.frame_set(10)
                bpy.ops.ed.undo_push(message="Set Key")
            bpy.context.scene.allset_auto_key = auto_key
            bpy.context.scene.tool_settings.use_keyframe_insert_auto = blender_key
        C[f"{tag}_s0"] = state()
    add(s_prepare, f"{tag}_prepare")
    idle(f"{tag}_ready", IDLE_TICKS, rest)
    action(f"{tag}_d1", 60, 0)
    idle(f"{tag}_after1", between, rest)
    add(lambda: C.__setitem__(f"{tag}_s1", state()), f"{tag}_snap1")
    if cancel_between:
        cancelled_rotate(f"{tag}_cancel")
        idle(f"{tag}_after_cancel", IDLE_TICKS, rest)

        def s_cancelled():
            check(f"{tag}: a cancelled rotation changes no pose and no key", state() == C[f"{tag}_s1"])
        add(s_cancelled, f"{tag}_cancelled")
    action(f"{tag}_d2", 0, 50)
    idle(f"{tag}_after2", IDLE_TICKS, rest)

    def s_snap2():
        C[f"{tag}_s2"] = state()
        s0, s1, s2 = C[f"{tag}_s0"], C[f"{tag}_s1"], C[f"{tag}_s2"]
        check(f"{tag}: both moves moved the control (keys {s0[1]} -> {s1[1]} -> {s2[1]})",
              s0[0] != s1[0] != s2[0])
        if auto_key or blender_key:
            check(f"{tag}: each move keyed the control", s0[1] < s1[1] <= s2[1])
    add(s_snap2, f"{tag}_snap2")
    undo_redo(tag)


case("plain")
case("autokey", auto_key=True)
case("autokey_cb", auto_key=True, rest=dock_point)
case("blender_autokey", blender_key=True)
case("autokey_rotate", auto_key=True, action=rotate)
case("autokey_grab", auto_key=True, action=grab)
case("autokey_cancel", auto_key=True, cancel_between=True)
case("autokey_fast", auto_key=True, between=1)


def click_after_undo(tag):
    """Undo a keyed move, then click another control: the move and its key stay undone."""
    def s_prepare():
        ob = rig()
        with ov():
            ob.animation_data_clear()
            pb = ob.pose.bones[bone()]
            bpy.context.scene.frame_set(1)
            pb.keyframe_insert("location", frame=1)
            pb.keyframe_insert("rotation_quaternion", frame=1)
            bpy.context.scene.frame_set(10)
            bpy.ops.ed.undo_push(message="Set Key")
            bpy.context.scene.allset_auto_key = True
        C[f"{tag}_s0"] = state()
    add(s_prepare, f"{tag}_prepare")
    idle(f"{tag}_ready")
    grab(f"{tag}_d1", 60, 0)
    idle(f"{tag}_after1")

    def s_undo():
        C[f"{tag}_s1"] = state()
        _a, r = main_view()
        ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + 40)
        ev('Z', 'PRESS', ctrl=True)
        ev('Z', 'RELEASE', ctrl=True)
        release_modifiers()
    add(s_undo, f"{tag}_undo")
    idle(f"{tag}_after_undo")

    def s_click():
        ob = rig()
        x, y = screen_of(ob.matrix_world @ ob.pose.bones["root"].head)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    add(s_click, f"{tag}_click")
    idle(f"{tag}_after_click")

    def s_check():
        s0, s1, now = C[f"{tag}_s0"], C[f"{tag}_s1"], state()
        check(f"{tag}: the move keyed the control ({s0[1]} -> {s1[1]} keys)", s1[1] > s0[1])
        check(f"{tag}: after Ctrl+Z and a click the move and its key stay undone (keys {now[1]}, "
              f"before {s0[1]})", now == s0)
    add(s_check, f"{tag}_check")


click_after_undo("autokey_click")


def picked():
    cb = mod(".ui.channel_box")
    ob = bpy.data.objects["Box276"]
    active = ob.data.bones.active
    return tuple(sorted(pb.name for pb in ob.pose.bones if cb.bone_selected(pb))), active.name if active else ""


@step
def s_box_prepare():
    """A marquee across a joint's bone (drawn by the kit; a bone belongs to its parent joint) with the Select tool
    while the child joint is picked: Blender's box select, then the kit's joint pick — one Ctrl+Z, one Shift+Z."""
    with ov():
        bpy.context.scene.allset_auto_key = False
        bpy.ops.object.mode_set(mode='OBJECT')
        arm = bpy.data.armatures.new("Box276")
        ob = bpy.data.objects.new("Box276", arm)
        ob.location = (12, 0, 0)
        bpy.context.scene.collection.objects.link(ob)
        rig().hide_set(True)
        for o in bpy.context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
        a = arm.edit_bones.new("root")
        a.head, a.tail = (0, 0, 0), (0, 0, 2)
        b = arm.edit_bones.new("tip")
        b.head, b.tail = (0, 0, 2), (0, 0, 4)
        b.parent = a
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.view3d.view_selected()
        bpy.ops.pose.select_all(action='DESELECT')
        cb = mod(".ui.channel_box")
        cb.set_bone_selected(ob.pose.bones["tip"], True)
        arm.bones.active = arm.bones["tip"]
        bpy.ops.ed.undo_push(message="Select")
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")


@step
def s_box_place():
    C["box_before"] = picked()
    ob = bpy.data.objects["Box276"]
    x, y = screen_of(ob.matrix_world @ ((ob.pose.bones["root"].head + ob.pose.bones["root"].tail) / 2))
    C["box"] = (x - 60, y - 20, x + 60, y + 20)


idle("box_ready", 2)


@step
def s_box_hover():
    x0, y0, _x1, _y1 = C["box"]
    ev('MOUSEMOVE', 'NOTHING', x=x0, y=y0)


@step
def s_box_press():
    x0, y0, _x1, _y1 = C["box"]
    ev('LEFTMOUSE', 'PRESS', x=x0, y=y0)


for _i in range(1, 7):
    def s_box_move(i=_i):
        x0, y0, x1, y1 = C["box"]
        ev('MOUSEMOVE', 'NOTHING', x=x0 + (x1 - x0) * i // 6, y=y0 + (y1 - y0) * i // 6)
    add(s_box_move, f"box_move{_i}")


@step
def s_box_release():
    _x0, _y0, x1, y1 = C["box"]
    ev('LEFTMOUSE', 'RELEASE', x=x1, y=y1)


idle("box_after", IDLE_TICKS)


@step
def s_box_selected():
    C["box_after"] = picked()
    print("[box] before", C["box_before"], "after", C["box_after"], flush=True)
    check(f"box: the marquee picked the root joint ({C['box_after']})", C["box_after"] == (("root",), "root"))


def _box_press(tag, key, shift, ctrl, want):
    def s_press():
        _a, r = main_view()
        ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + 40)
        ev(key, 'PRESS', ctrl=ctrl, shift=shift)
        ev(key, 'RELEASE', ctrl=ctrl, shift=shift)
        release_modifiers()
    add(s_press, f"box_{tag}")
    idle(f"box_{tag}_after", 3)

    def s_check():
        got = picked()
        check(f"box: one {tag} gives the selection {want} ({got})", got == C[want])
    add(s_check, f"box_{tag}_check")


_box_press("ctrl_z", 'Z', False, True, "box_before")
_box_press("shift_z", 'Z', True, False, "box_after")


@step
def s_rigify():
    import addon_utils
    addon_utils.enable("rigify", default_set=True)
    with ov():
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.armature_human_metarig_add()
        meta = bpy.context.view_layer.objects.active
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.pose.rigify_generate()
        meta.hide_set(True)
        rg = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE' and o.name.startswith("rig"))
        rig().hide_set(True)
        bpy.data.objects["Box276"].hide_set(True)
        C["rig"], C["bone"] = rg.name, "torso"
        for o in bpy.context.selected_objects:
            o.select_set(False)
        rg.select_set(True)
        bpy.context.view_layer.objects.active = rg
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.view3d.view_selected()
        bpy.ops.pose.select_all(action='DESELECT')
        cb = mod(".ui.channel_box")
        for pb in rg.pose.bones:
            cb.set_bone_selected(pb, pb.name == "torso")
        rg.data.bones.active = rg.data.bones["torso"]
        bpy.ops.ed.undo_push(message="Select")
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    check("Rigify rig in Pose mode, torso picked", rig().mode == 'POSE')


idle("rigify_view", 2)
case("rigify_autokey", auto_key=True)

run()
