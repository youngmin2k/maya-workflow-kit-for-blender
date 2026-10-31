"""Issue #135: in a real UI: File > Game Exporter opens the kit window (Animation Clips tab with two clips),
Visualize > Motion Trail Editor opens Maya's editor and Create Motion Trail draws a Blender motion path on an animated
cube. Shots in the shots folder."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, win, load_maya_layout, screenshot  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                                           "tmp", "gui_step225")
C = {}


def main_view():
    toolbox = import_module(MODULE + ".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def override():
    area, r = main_view()
    return bpy.context.temp_override(window=win(), area=area, region=r)


def centre():
    _a, r = main_view()
    return r.x + r.width // 2, r.y + r.height // 2


def shot(name):
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, name)
    screenshot(path)
    return path


def esc():
    x, y = centre()
    ev('ESC', 'PRESS', x=x, y=y)
    ev('ESC', 'RELEASE', x=x, y=y)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    k = import_module(MODULE + ".operators.units").maya_unit()
    with override():
        bpy.ops.allset.create(kind='CUBE')
        cube = bpy.context.active_object
        for f, x, z in ((1, -8, 0), (12, 0, 6), (24, 8, 0)):
            cube.location = (x * k, 0, z * k)
            cube.keyframe_insert("location", frame=f)
    C["cube"] = cube.name
    ge = import_module(MODULE + ".operators.game_exporter")
    s = bpy.context.scene.allset_game_exporter
    s.export_type = 'ANIMATION'
    for name, a, b in (("walk", 1, 10), ("run", 11, 24)):
        c = ge.add_clip(bpy.context.scene)
        c.name, c.start, c.end = name, a, b
    s.export_filename = "hero"
    x, y = centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_game_exporter():
    with override():
        bpy.ops.allset.menu_item(item="File/Game Exporter")


@step
def s_wait1():
    pass


@step
def s_game_shot():
    path = shot("game_exporter.png")
    check(f"Game Exporter window shot: {path}", os.path.exists(path))
    mw = import_module(MODULE + ".ui.marked_window")          # a kit window, not a popup
    w = mw.find_window(bpy.context, "GAME_EXPORTER")
    check("Game Exporter is a window that stays open", w is not None)
    if w is not None:
        mw.close_later(w)


@step
def s_trail_editor():
    x, y = centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    with override():
        bpy.ops.allset.motion_trail(action='CREATE')
    cube = bpy.data.objects[C["cube"]]
    check(f"Create Motion Trail made a motion path ({cube.motion_path is not None})", cube.motion_path is not None)
    with override():
        bpy.ops.allset.menu_item(item="Visualize/Motion Trail Editor")


@step
def s_wait2():
    pass


@step
def s_trail_shot():
    path = shot("motion_trail_editor.png")
    check(f"Motion Trail Editor shot: {path}", os.path.exists(path))
    esc()


run()
