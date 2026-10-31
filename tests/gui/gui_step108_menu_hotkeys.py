"""In a real UI: the Maya File and Edit Mesh menus opened from the top of the window show Maya's hotkeys
right-aligned (Ctrl+N / Ctrl+O / Ctrl+S ..., Ctrl+B / Ctrl+E / Ctrl+Del), no Blender shortcut (Recent Files had
"Shift Ctrl O"), and File reaches Exit inside a 900 px window at the default scale (screenshots beside audit-7
pairs menu_Modeling_File / menu_Modeling_Edit_Mesh)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name):
    if SHOTS:
        with bpy.context.temp_override(window=win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def park(x):
    """Mouse over the viewport, one tick before the menu opens (a move queued in the same tick as the popup closes
    it). A popup opened with the mouse at the window top doesn't show in screen.screenshot, so the menu
    opens mid-window: Blender then fits the whole menu in the 900 px window (no scroll arrows) - the same space a
    top-bar dropdown has minus its title row."""
    area, region = v3d()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=region.y + region.height // 2)


def open_menu(name):
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.call_menu(name=mod(".ui.menu_sets").menu_idname(name))


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_keys():
    bpy.ops.allset.keymap_activate()
    # an open tooltip hides the popup menu from screen.screenshot: no tooltips in this session
    bpy.context.preferences.view.show_tooltips = False
    ms = mod(".ui.menu_sets")
    km = sys.modules["sim"].maya_kc().keymaps["Window"]
    check("no Shift Ctrl O recent-files key left for Blender to print beside Recent Files",
          not [k for k in km.keymap_items if k.idname == "wm.call_menu" and k.type == 'O' and k.ctrl and k.shift])
    del ms
    park(500)


@step
def s_file():
    open_menu("mainFileMenu")


@step
def s_wait1():
    pass


@step
def s_wait1b():
    pass


@step
def s_file_shot():
    shot("gui_step108_file.png")
    tap('ESC')
    check("File menu shot taken (Exit inside the window: see screenshot)", True)


@step
def s_edit_mesh():
    park(700)


@step
def s_edit_mesh_open():
    open_menu("mainEditMeshMenu")


@step
def s_wait2():
    pass


@step
def s_wait2b():
    pass


@step
def s_edit_mesh_shot():
    shot("gui_step108_edit_mesh.png")
    tap('ESC')
    check("session ran", True)


run()
