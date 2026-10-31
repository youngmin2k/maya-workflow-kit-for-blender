"""In a real UI (Maya Workflow Kit layout): Key > Create Character Set makes the Time Slider's character
field show "character1" (Maya: the new set becomes current), its dropdown lists the sets + None, S keys the current
character's attributes."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    path = os.path.join(SHOTS or os.path.join(os.environ.get("TEMP", "."), "gui187"), name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    screenshot(path)
    return path


def timeline():
    for area in win().screen.areas:
        if area.type == 'DOPESHEET_EDITOR' and area.spaces.active.mode == 'TIMELINE':
            return area, next(r for r in area.regions if r.type == 'HEADER')
    raise LookupError("no timeline")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def cs():
    return import_module(MODULE + ".operators.character_sets")


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        ob = bpy.context.view_layer.objects.active
        bpy.ops.allset.menu_item('EXEC_DEFAULT', item="Key/Create Character Set")
    C["ob"] = ob.name
    redraw()


@step
def s_wait():
    redraw()


@step
def s_created():
    sc = bpy.context.scene
    ks = cs().current(sc)
    check(f"Key > Create Character Set: current = {ks and ks.bl_label} (Maya: character1)",
          ks is not None and ks.bl_label == "character1")
    names = cs().member_names(sc, ks) if ks else []
    check(f"members = the cube's translate / rotate ({len(names)}: {names[:3]} ...)",
          len(names) == 6 and all(".translate" in n or ".rotate" in n for n in names))
    shot("gui_step187_field.png")
    area, header = timeline()
    x, y = header.x + header.width // 2, header.y + header.height // 2
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    with bpy.context.temp_override(window=win(), area=area, region=header):
        bpy.ops.wm.call_menu(name="ALLSET_MT_character_set_current")


@step
def s_menu_wait():
    redraw()


@step
def s_menu_shot():
    shot("gui_step187_dropdown.png")
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


@step
def s_key():
    area, region = view3d()
    ob = bpy.data.objects[C["ob"]]
    for o in bpy.context.scene.objects:
        o.select_set(False)
    bpy.context.scene.frame_set(7)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.set_key()
    from_kit = import_module(MODULE + ".compat")
    fcs = list(from_kit.id_fcurves(ob) or ())
    check(f"S with nothing selected keys the current character ({len(fcs)} curves, Maya: 6)", len(fcs) == 6)


@step
def s_done():
    check("done", True)


run()
