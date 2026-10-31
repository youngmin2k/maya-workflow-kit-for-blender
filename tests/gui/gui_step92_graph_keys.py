"""In a real UI (Maya Workflow Kit layout, the big view switched to the Graph Editor): t centers the current time,
Alt+/ turns on Snap Time To Selection (clicking key 20 moves the time there), i held + MMB click inserts a key that
keeps the curve shape."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def key(type, **mods):
    names = {"alt": "LEFT_ALT", "ctrl": "LEFT_CTRL", "shift": "LEFT_SHIFT"}
    for m in mods:
        ev(names[m], 'PRESS')
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)
    for m in mods:
        ev(names[m], 'RELEASE')


def region():
    return next(r for r in C["area"].regions if r.type == 'WINDOW')


def curve():
    return import_module(MODULE + ".compat").id_fcurve_collection(bpy.data.objects["pCube1"]).find("location", index=0)


def frames():
    return [round(kp.co.x, 3) for kp in curve().keyframe_points]


def at(frame, value):
    r = region()
    x, y = r.view2d.view_to_region(frame, value, clip=False)
    return r.x + x, r.y + y


def hover():
    r = region()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, reg = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=reg):
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.data.objects["pCube1"]
    for f, v in ((1, 0.0), (10, 0.05), (20, 0.0)):
        ob.location.x = v
        ob.keyframe_insert("location", index=0, frame=f)
    for kp in curve().keyframe_points:
        kp.select_control_point = kp.select_left_handle = kp.select_right_handle = False
    import_module(MODULE + ".preferences").get().snap_time_to_selection = False
    C["area"] = area
    area.ui_type = 'FCURVES'


@step
def s_frame():
    a = C["area"]
    a.spaces.active.use_normalization = False
    with bpy.context.temp_override(window=win(), area=a, region=region()):
        bpy.ops.graph.view_all()
    bpy.context.scene.frame_set(15)
    hover()


@step
def s_t():
    r = region()
    C["x15_before"] = r.view2d.view_to_region(15, 0, clip=False)[0]
    key('T')


@step
def s_t_check():
    r = region()
    x = r.view2d.view_to_region(15, 0, clip=False)[0]
    check(f"t centers the current time 15 (x {C['x15_before']} -> {x}, middle {r.width // 2})", abs(x - r.width / 2) <= 2)
    with bpy.context.temp_override(window=win(), area=C["area"], region=r):
        bpy.ops.graph.view_all()
    hover()
    key('SLASH', alt=True)


@step
def s_snap_on():
    on = import_module(MODULE + ".preferences").get().snap_time_to_selection
    check(f"Alt+/ turns Snap Time To Selection on ({on})", on)
    bpy.context.scene.frame_set(3)
    x, y = at(20, curve().evaluate(20))
    ev('MOUSEMOVE', 'NOTHING', x=int(x), y=int(y))
    ev('LEFTMOUSE', 'PRESS', x=int(x), y=int(y))
    ev('LEFTMOUSE', 'RELEASE', x=int(x), y=int(y))


@step
def s_snap_wait():
    pass


@step
def s_snap_check():
    sel = [round(kp.co.x) for kp in curve().keyframe_points if kp.select_control_point]
    check(f"clicking key 20 selects it ({sel}) and moves the time there ({bpy.context.scene.frame_current})",
          sel == [20] and bpy.context.scene.frame_current == 20)
    C["v7"] = curve().evaluate(7)
    x, y = at(7, C["v7"] * 0.5)            # under the curve, inside the view: MMB anywhere in the column
    C["mmb"] = (int(x), int(y))
    ev('MOUSEMOVE', 'NOTHING', x=C["mmb"][0], y=C["mmb"][1])
    ev('I', 'PRESS', x=C["mmb"][0], y=C["mmb"][1])


@step
def s_mmb_press():
    x, y = C["mmb"]
    ev('MIDDLEMOUSE', 'PRESS', x=x, y=y)


@step
def s_mmb_line():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_mmb_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step92_insert_line.png"))
    x, y = C["mmb"]
    ev('MIDDLEMOUSE', 'RELEASE', x=x, y=y)


@step
def s_release_i():
    x, y = C["mmb"]
    ev('I', 'RELEASE', x=x, y=y)


@step
def s_insert_check():
    fc = curve()
    k7 = next((kp for kp in fc.keyframe_points if abs(kp.co.x - 7) < 1e-4), None)
    check(f"i + MMB click inserts a key at frame 7 ({frames()})", k7 is not None)
    if k7 is not None:
        check(f"the new key has the curve's value ({k7.co.y:.5f} vs {C['v7']:.5f})", abs(k7.co.y - C["v7"]) < 1e-5)
        sel = [round(kp.co.x) for kp in fc.keyframe_points if kp.select_control_point]
        check(f"only the new key is selected ({sel})", sel == [7])
    check(f"the time stays at 20 ({bpy.context.scene.frame_current})", bpy.context.scene.frame_current == 20)
    mods = [op.bl_idname for op in win().modal_operators]
    check(f"releasing i ends the tool ({mods})", "ALLSET_OT_insert_key_tool" not in mods)
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step92_inserted.png"))
    import_module(MODULE + ".preferences").get().snap_time_to_selection = False
    C["area"].ui_type = 'VIEW_3D'


run()
