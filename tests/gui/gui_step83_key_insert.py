"""In a real UI: Ctrl+Shift+W / Alt+I insert keys keeping the curve, Shift+) / ( nudge, Ctrl+Alt+. / , select
next / previous key, Graph Editor nudge of the selected key."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, tap, view3d, win, load_maya_layout  # noqa: E402

C = {}


def cb():
    return import_module(MODULE + ".ui.channel_box")


def curves():
    fcs = cb()._fcurves(C["ob"])
    return fcs.find("location", index=0), fcs.find("rotation_euler", index=2)


def frames(fc):
    return [round(kp.co.x, 3) for kp in fc.keyframe_points]


def key(type, **mods):
    order = [m for m in ("ctrl", "shift", "alt") if mods.get(m)]
    names = {"ctrl": "LEFT_CTRL", "shift": "LEFT_SHIFT", "alt": "LEFT_ALT"}
    for m in order:
        ev(names[m], 'PRESS')
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)
    for m in reversed(order):
        ev(names[m], 'RELEASE')


def hover_view():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    bpy.ops.allset.create(kind='CUBE')
    ob = C["ob"] = bpy.context.active_object
    for f, x, rz in ((1, 0.0, 0.0), (20, 0.1, 1.5)):
        ob.location.x = x
        ob.rotation_euler.z = rz
        ob.keyframe_insert("location", index=0, frame=f)
        ob.keyframe_insert("rotation_euler", index=2, frame=f)
    bpy.context.scene.frame_set(7)
    loc, rot = curves()
    C["loc7"], C["rot7"] = loc.evaluate(7), rot.evaluate(7)
    hover_view()


@step
def s_insert_t():
    key('W', ctrl=True, shift=True)


@step
def s_insert_t_check():
    loc, rot = curves()
    check(f"Ctrl+Shift+W: key on translate at 7, value kept ({frames(loc)})",
          frames(loc) == [1, 7, 20] and abs(loc.evaluate(7) - C["loc7"]) < 1e-6)
    check(f"Ctrl+Shift+W: rotate untouched ({frames(rot)})", frames(rot) == [1, 20])
    key('I', alt=True)


@step
def s_insert_all_check():
    _loc, rot = curves()
    check(f"Alt+I: key on every curve of the selection, value kept ({frames(rot)})",
          frames(rot) == [1, 7, 20] and abs(rot.evaluate(7) - C["rot7"]) < 1e-6)
    key('ZERO', shift=True)


@step
def s_nudge_check():
    loc, rot = curves()
    check(f"Shift+): the keys at the current time move to 8, time follows ({frames(loc)}, {bpy.context.scene.frame_current})",
          frames(loc) == [1, 8, 20] and frames(rot) == [1, 8, 20] and bpy.context.scene.frame_current == 8)
    key('NINE', shift=True)


@step
def s_nudge_back_check():
    loc, _rot = curves()
    check(f"Shift+(: back to 7 ({frames(loc)})", frames(loc) == [1, 7, 20] and bpy.context.scene.frame_current == 7)
    key('PERIOD', ctrl=True, alt=True)


@step
def s_next_check():
    loc, _rot = curves()
    sel = [kp.select_control_point for kp in loc.keyframe_points]
    check(f"Ctrl+Alt+.: next key 20 selected, time 20 ({sel}, {bpy.context.scene.frame_current})",
          sel == [False, False, True] and bpy.context.scene.frame_current == 20)
    key('COMMA', ctrl=True, alt=True)


@step
def s_prev_check():
    loc, _rot = curves()
    sel = [kp.select_control_point for kp in loc.keyframe_points]
    check(f"Ctrl+Alt+,: previous key 7 selected ({sel}, {bpy.context.scene.frame_current})",
          sel == [False, True, False] and bpy.context.scene.frame_current == 7)
    # Graph Editor: nudge the selected key (key 7 of both curves selected) with the time elsewhere
    a, _r = view3d()
    C["area"] = a
    a.ui_type = 'FCURVES'
    bpy.context.scene.frame_set(15)


@step
def s_graph_hover():
    a = C["area"]
    r = next(r for r in a.regions if r.type == 'WINDOW')
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


@step
def s_graph_nudge():
    key('ZERO', shift=True)


@step
def s_graph_check():
    loc, rot = curves()
    check(f"Graph Editor Shift+): the selected keys move, time stays ({frames(loc)}, {bpy.context.scene.frame_current})",
          frames(loc) == [1, 8, 20] and frames(rot) == [1, 8, 20] and bpy.context.scene.frame_current == 15)
    C["area"].ui_type = 'VIEW_3D'


run()
