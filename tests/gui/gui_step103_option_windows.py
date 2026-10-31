"""In a real UI: option boxes are Maya's right-side square (Create > Polygon Primitives, Edit Mesh), and
three option windows (Polygon Cube, Bevel, Parent Constraint) open as dialogs with the command / Cancel buttons and
Apply / Save Settings / Reset Settings; screenshots (ALLSET_GUI_SHOTS)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def esc():
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


def submenu(path):
    menu_sets = import_module(MODULE + ".ui.menu_sets")
    for name in dir(bpy.types):
        cls = getattr(bpy.types, name)
        if name.startswith("ALLSET_MT_main") and getattr(cls, "__doc__", "") == f"Maya menu: {path}":
            return name
    return menu_sets.menu_idname("mainCreateMenu")


def call_menu(name):
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.call_menu(name=name)


@step
def s_setup():
    setup()
    a, r = view3d()
    C["mid"] = (a.x + a.width // 2, a.y + a.height // 2)
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.create(kind='CUBE')


@step
def s_prims():
    call_menu(submenu("Create/Polygon Primitives"))


@step
def s_w1():
    pass


@step
def s_prims_shot():
    shot("gui_step103_menu_polygon_primitives.png")
    esc()


@step
def s_edit_mesh():
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    call_menu(import_module(MODULE + ".ui.menu_sets").menu_idname("mainEditMeshMenu"))


@step
def s_w2():
    pass


@step
def s_edit_mesh_shot():
    shot("gui_step103_menu_edit_mesh.png")
    esc()


def _window(key):
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    with bpy.context.temp_override(window=win()):
        res = getattr(bpy.ops.allset, "opt_" + key)('INVOKE_DEFAULT')
    check(f"{key} option window opens", res == {'RUNNING_MODAL'})


@step
def s_cube():
    _window("poly_cube")


@step
def s_w3():
    pass


@step
def s_cube_shot():
    shot("gui_step103_poly_cube_options.png")
    esc()


@step
def s_bevel():
    _window("bevel")


@step
def s_w4():
    pass


@step
def s_bevel_shot():
    shot("gui_step103_bevel_options.png")
    esc()


@step
def s_parent():
    _window("parent_constraint")


@step
def s_w5():
    pass


@step
def s_parent_shot():
    shot("gui_step103_parent_constraint_options.png")
    esc()


@step
def s_box_click():
    # the right-side square of Create > Polygon Primitives > Cube opens the window (operator path, as the button)
    with bpy.context.temp_override(window=win()):
        res = bpy.ops.allset.menu_option_box('INVOKE_DEFAULT', item="Create/Polygon Primitives/Cube")
    check("the Cube option box runs", res in ({'FINISHED'}, {'RUNNING_MODAL'}))


@step
def s_w6():
    pass


@step
def s_box_close():
    esc()


run()
