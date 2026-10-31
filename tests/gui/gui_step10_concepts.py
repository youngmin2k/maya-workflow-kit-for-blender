"""In a real UI: P / Shift+P, Shift+D, Alt+Shift+D keys, the A hold + LMB
marking menu (Freeze Transforms by drag), the Modify menu Pivot section; screenshots."""

import os
import sys
from importlib import import_module

import bpy
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, tap, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
D = 110  # px: past the marking menu ring


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def select(objs, active):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def close(a, b, tol=1e-4):
    return all(abs(a[i][j] - b[i][j]) < tol for i in range(4) for j in range(4))


def mid():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


@step
def s_setup():
    C["x"], C["y"] = setup()
    C["draw"] = import_module(MODULE + ".marking.draw")
    C["mm"] = import_module(MODULE + ".marking.menus")
    cube, cam = bpy.data.objects["Cube"], bpy.data.objects["Camera"]
    cube.location, cube.rotation_euler = (1, 2, 0.5), (0.2, 0.3, 0.1)
    bpy.context.view_layer.update()
    C["world"] = cube.matrix_world.copy()
    select([cube, cam], cam)
    mid()
    tap('P')


@step
def s_parented():
    cube, cam = bpy.data.objects["Cube"], bpy.data.objects["Camera"]
    check("P parents the selection under the last selected", cube.parent is cam)
    check("P: parent inverse = identity (Maya)", close(cube.matrix_parent_inverse, Matrix.Identity(4)))
    check("P: world transform kept", close(cube.matrix_world, C["world"]))
    select([cube], cube)
    ev('P', 'PRESS', shift=True)
    ev('P', 'RELEASE', shift=True)


@step
def s_unparented():
    cube = bpy.data.objects["Cube"]
    check("Shift+P unparents, world kept", cube.parent is None and close(cube.matrix_world, C["world"]))
    C["n"] = len(bpy.data.objects)
    ev('D', 'PRESS', shift=True)
    ev('D', 'RELEASE', shift=True)


@step
def s_duplicated():
    check("Shift+D duplicates with a Maya name",
          len(bpy.data.objects) == C["n"] + 1 and "Cube1" in bpy.data.objects)
    cube = bpy.data.objects["Cube"]
    cube.modifiers.new("sub", 'SUBSURF')
    select([cube], cube)
    ev('D', 'PRESS', shift=True, alt=True)
    ev('D', 'RELEASE', shift=True, alt=True)


@step
def s_history_deleted():
    cube = bpy.data.objects["Cube"]
    check("Alt+Shift+D deletes history (Subsurf baked)",
          len(cube.modifiers) == 0 and len(cube.data.vertices) == 26)
    cube.scale = (2, 1, 1)
    mid()
    ev('A', 'PRESS')
    ev('LEFTMOUSE', 'PRESS', x=C["x"], y=C["y"])


@step
def s_a_menu_open():
    s = C["draw"].ACTIVE.get("session")
    check("A hold + LMB opens the SELECT_ALL marking menu",
          s is not None and s.stack[0][0].sub is C["mm"].MENUS["SELECT_ALL"])


@step
def s_a_menu_shot():
    shot("gui_step10_a_menu.png")
    x, y = C["x"], C["y"]
    for f in (1, 2, 3):
        ev('MOUSEMOVE', 'NOTHING', x=x + f * D // 3, y=y - f * D // 3)


@step
def s_a_release():
    ev('LEFTMOUSE', 'RELEASE', x=C["x"] + D, y=C["y"] - D)
    ev('A', 'RELEASE')


@step
def s_frozen():
    cube = bpy.data.objects["Cube"]
    check("drag SE + release = Freeze Transforms",
          tuple(cube.scale) == (1.0, 1.0, 1.0) and tuple(cube.rotation_euler) == (0.0, 0.0, 0.0)
          and tuple(cube.location) == (0.0, 0.0, 0.0))
    check("freeze kept the pivot", abs(cube.matrix_world.translation.x - 1.0) < 1e-4)
    check("menu closed", not C["draw"].ACTIVE)
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.call_menu(name="ALLSET_MT_mainModifyMenu")


@step
def s_modify_menu():
    pass  # screenshot shows the previous frame


@step
def s_modify_shot():
    shot("gui_step10_modify_menu.png")
    tap('ESC')


run()
