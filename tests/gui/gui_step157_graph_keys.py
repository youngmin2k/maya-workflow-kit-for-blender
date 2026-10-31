"""In a real UI (Maya Workflow Kit layout, the big view switched to the Graph Editor): Select > Only Curve
makes a click on a key pick its whole curve, Select > All picks the key again; Keys > Mute Key holds the muted key's
value (screenshot)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def region():
    return next(r for r in C["area"].regions if r.type == 'WINDOW')


def curve():
    return import_module(MODULE + ".compat").id_fcurve_collection(bpy.data.objects["pCube1"]).find("location", index=0)


def selected():
    return [round(kp.co.x) for kp in curve().keyframe_points if kp.select_control_point]


def at(frame):
    r = region()
    x, y = r.view2d.view_to_region(frame, curve().evaluate(frame), clip=False)
    return int(r.x + x), int(r.y + y)


def click(frame):
    x, y = at(frame)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


def deselect():
    for kp in curve().keyframe_points:
        kp.select_control_point = kp.select_left_handle = kp.select_right_handle = False


def override():
    return bpy.context.temp_override(window=win(), area=C["area"], region=region())


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
    for f, v in ((1, 0.0), (10, 0.05), (20, 0.0), (30, 0.08)):
        ob.location.x = v
        ob.keyframe_insert("location", index=0, frame=f)
    for kp in curve().keyframe_points:
        kp.interpolation = 'LINEAR'
    deselect()
    C["area"] = area
    area.ui_type = 'FCURVES'


@step
def s_frame():
    a = C["area"]
    a.spaces.active.use_normalization = False
    with override():
        bpy.ops.graph.view_all()
        bpy.ops.allset.graph_select_type(preset="ONLY_CURVE")


@step
def s_click_only_curve():
    click(10)


@step
def s_wait1():
    pass


@step
def s_wait2():
    pass


@step
def s_only_curve_check():
    check(f"Only Curve: clicking key 10 picks the whole curve ({selected()})", selected() == [1, 10, 20, 30])
    deselect()
    with override():
        bpy.ops.allset.graph_select_type(preset="ALL")


@step
def s_click_all():
    click(20)


@step
def s_wait3():
    pass


@step
def s_all_check():
    check(f"All: clicking key 20 picks that key ({selected()})", selected() == [20])
    deselect()
    curve().keyframe_points[1].select_control_point = True
    with override():
        res = bpy.ops.allset.mute_key(mute=True)
    v = round(curve().evaluate(15), 4)
    check(f"Mute Key on key 10 holds its value until key 20 ({res}, value at 15 = {v})",
          res == {'FINISHED'} and v == 0.05 and round(curve().evaluate(20), 4) == 0.0)
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step157_muted.png"))
    C["area"].ui_type = 'VIEW_3D'


run()
