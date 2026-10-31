"""In a real UI: with a cube selected in object mode the Edit Mesh menu has no greyed mapped item,
Poke from the menu pokes the whole cube (Maya pokes every face), the Cache menu has Maya's three
submenus, the Audio menu is filled; screenshots (ALLSET_GUI_SHOTS)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def menu(name):
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.call_menu(name=import_module(MODULE + ".ui.menu_sets").menu_idname(name))


def esc():
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


@step
def s_setup():
    setup()
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.create(kind='CUBE')
    C["cube"] = bpy.context.view_layer.objects.active
    check("object mode with a cube", bpy.context.mode == 'OBJECT' and C["cube"] is not None)


@step
def s_edit_mesh():
    menu("mainEditMeshMenu")


@step
def s_wait1():
    pass


@step
def s_edit_mesh_shot():
    shot("gui_step101_edit_mesh_object_mode.png")
    esc()


@step
def s_poke():
    with bpy.context.temp_override(window=win()):
        res = bpy.ops.allset.menu_item('INVOKE_DEFAULT', item="Edit Mesh/Poke")
    check("Poke from the menu in object mode runs", res == {'FINISHED'})
    check("Poke made 24 faces (Maya pokes every face)", len(C["cube"].data.polygons) == 24)
    check("still in object mode", bpy.context.mode == 'OBJECT')


@step
def s_cache():
    menu("mainPipelineCacheMenu")


@step
def s_wait2():
    pass


@step
def s_cache_shot():
    shot("gui_step101_cache.png")
    esc()


@step
def s_surfaces():
    menu("mainSurfacesMenu")


@step
def s_wait3():
    pass


@step
def s_surfaces_shot():
    shot("gui_step101_surfaces.png")
    esc()


@step
def s_audio():
    menu("mainAudioMenu")


@step
def s_wait4():
    pass


@step
def s_audio_shot():
    shot("gui_step101_audio.png")
    esc()


run()
