"""In the Maya Workflow Kit layout: G repeats the last Maya command, menu items too.

Maya 2022: Create > Polygon Primitives > Cube from the menu, then G = the next cube;
Edit > Repeat reads 'Repeat "<command>"'. Here: the menu item runs like a click on it (allset.menu_item), then the real
G key over the viewport; a key command (Ctrl+D) afterwards is what the next G repeats; the Edit menu is opened for a
shot of its Repeat row."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
CUBE = "Create/Polygon Primitives/Cube"


def key(type, **mods):
    names = {"ctrl": "LEFT_CTRL", "shift": "LEFT_SHIFT", "alt": "LEFT_ALT"}
    for m in mods:
        ev(names[m], 'PRESS')
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)
    for m in mods:
        ev(names[m], 'RELEASE')


def centre():
    _a, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def meshes():
    return sorted(o.name for o in bpy.context.scene.objects if o.type == 'MESH')


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_menu_cube():
    bpy.ops.allset.keymap_activate()
    with override():
        bpy.ops.allset.menu_item(item=CUBE, clicked=True)      # what a click on the menu row runs
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    check(f"menu Cube made pCube1 ({meshes()})", meshes() == ["pCube1"])
    centre()
    key('G')


step(redraw)


@step
def s_after_g():
    if bpy.context.mode != 'OBJECT':
        with override():
            bpy.ops.object.mode_set(mode='OBJECT')
    check(f"G after the menu Cube made pCube2 ({meshes()})", meshes() == ["pCube1", "pCube2"])
    rep = import_module(MODULE + ".operators.repeat_maya")
    check(f"Edit > Repeat label ({rep.label(bpy.context)})", rep.label(bpy.context) == 'Repeat "Cube"')
    for o in bpy.context.scene.objects:
        o.select_set(o.name == "pCube2")
    bpy.context.view_layer.objects.active = bpy.data.objects["pCube2"]
    centre()
    key('D', ctrl=True)                                          # a key command: Maya Duplicate


step(redraw)


@step
def s_after_dup():
    n = len(meshes())
    check(f"Ctrl+D duplicated ({meshes()})", n == 3)
    centre()
    key('G')


step(redraw)


@step
def s_g_repeats_dup():
    check(f"G after Ctrl+D repeats the duplicate ({meshes()})", len(meshes()) == 4)
    ms = import_module(MODULE + ".ui.menu_sets")
    with override():
        bpy.ops.wm.call_menu(name=ms.menu_idname("mainEditMenu"))


step(redraw)


@step
def s_edit_menu_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step175_edit_menu.png"))
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


run()
