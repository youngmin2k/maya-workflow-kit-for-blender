"""#105: in a real UI: the Maya Retime Tool in the Graph Editor (big view switched to the Graph Editor).
Double-click adds markers (Snap On Frame), dragging a marker's handle 15 -> 20 retimes the keys like Maya
(1 5 12.5 20 25 35), dragging the line low moves only the marker, the ✕
deletes it, Esc ends the tool, Ctrl+Z restores the keys."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
KEYS = [1, 5, 10, 15, 20, 30]
VALUES = [0.0, 0.02, 0.05, 0.03, 0.08, 0.01]


def rt():
    return import_module(MODULE + ".operators.graph_retime")


def region():
    return next(r for r in C["area"].regions if r.type == 'WINDOW')


def curve():
    return import_module(MODULE + ".compat").id_fcurve_collection(bpy.data.objects["pCube1"]).find("location", index=0)


def frames():
    return [round(kp.co.x, 3) for kp in curve().keyframe_points]


def markers():
    return list(rt()._MARKERS.get(C["area"].as_pointer(), []))


def at(frame, frac):
    """Window position of ``frame`` at ``frac`` of the region height."""
    r = region()
    x = r.view2d.view_to_region(frame, 0, clip=False)[0]
    return int(r.x + x), int(r.y + r.height * frac)


def at_x(frame, y_px):
    r = region()
    x = r.view2d.view_to_region(frame, 0, clip=False)[0]
    return int(r.x + x), int(r.y + y_px)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def running():
    return "ALLSET_OT_retime_tool" in [op.bl_idname for op in win().modal_operators]


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
    for f, v in zip(KEYS, VALUES):
        ob.location.x = v
        ob.keyframe_insert("location", index=0, frame=f)
    import_module(MODULE + ".preferences").get().snap_time_to_selection = False
    import_module(MODULE + ".preferences").get().retime_snap_on_frame = True
    C["area"] = area
    area.ui_type = 'FCURVES'


@step
def s_frame():
    a = C["area"]
    a.spaces.active.use_normalization = False
    with bpy.context.temp_override(window=win(), area=a, region=region()):
        bpy.ops.graph.view_all()
    bpy.ops.ed.undo_push(message="test scene")


@step
def s_start():
    with bpy.context.temp_override(window=win(), area=C["area"], region=region()):
        bpy.ops.allset.retime_tool('INVOKE_DEFAULT')
    x, y = at(5, 0.25)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_dbl_5():
    check(f"the Retime Tool runs ({running()})", running())
    x, y = at(5.2, 0.25)                      # Snap On Frame -> 5
    for _ in range(2):                        # two press/release pairs in one tick = a double-click
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_dbl_15_move():
    x, y = at(14.8, 0.25)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_dbl_15():
    x, y = at(14.8, 0.25)
    for _ in range(2):
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_markers_check():
    check(f"double-clicks add markers on whole frames ({markers()})", markers() == [5.0, 15.0])
    check(f"adding markers moves no key ({frames()})", frames() == KEYS)
    redraw()


@step
def s_handle_hover():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step198_markers.png"))
    x, y = at(15, 0.5)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_handle_press():
    x, y = at(15, 0.5)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_handle_move1():
    x, y = at(17.6, 0.5)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_handle_move2():
    x, y = at(20.1, 0.5)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    redraw()


@step
def s_handle_release():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step198_drag.png"))
    x, y = at(20.1, 0.5)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_retime_check():
    check(f"handle drag 15 -> 20 retimes like Maya ({frames()})", frames() == [1, 5, 12.5, 20, 25, 35])
    vals = [round(kp.co.y, 6) for kp in curve().keyframe_points]
    check(f"values unchanged ({vals})", vals == [round(v, 6) for v in VALUES])
    check(f"the marker moved to 20 ({markers()})", markers() == [5.0, 20.0])
    x, y = at(20, 0.85)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_line_press():
    x, y = at(20, 0.85)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_line_move():
    x, y = at(22, 0.85)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_line_release():
    x, y = at(22, 0.85)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_line_check():
    check(f"dragging the line low moves only the marker ({markers()}, keys {frames()})",
          markers() == [5.0, 22.0] and frames() == [1, 5, 12.5, 20, 25, 35])
    from sim import scale
    x, y = at_x(22, rt().X_Y * scale())
    C["x"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_delete():
    x, y = C["x"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_delete_check():
    check(f"the ✕ deletes the marker ({markers()})", markers() == [5.0])
    x, y = at(10, 0.25)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('ESC', 'PRESS', x=x, y=y)
    ev('ESC', 'RELEASE', x=x, y=y)


@step
def s_esc_check():
    check(f"Esc ends the tool ({running()}, markers {rt()._MARKERS})", not running() and not rt()._MARKERS)
    check(f"the draw handler is gone ({rt()._HANDLE})", rt()._HANDLE["draw"] is None)
    x, y = at(10, 0.25)
    ev('LEFT_CTRL', 'PRESS', x=x, y=y)
    ev('Z', 'PRESS', x=x, y=y, ctrl=True)
    ev('Z', 'RELEASE', x=x, y=y, ctrl=True)
    ev('LEFT_CTRL', 'RELEASE', x=x, y=y)


@step
def s_undo_check():
    check(f"Ctrl+Z undoes the retime in one step ({frames()})", frames() == KEYS)
    import_module(MODULE + ".preferences").get().retime_snap_on_frame = False
    C["area"].ui_type = 'VIEW_3D'


run()
