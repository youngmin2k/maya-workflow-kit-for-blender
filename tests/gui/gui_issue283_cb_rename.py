"""#283 in the Maya Workflow Kit layout: a click on the object's name at the top of the Channel Box edits it in place
(type a new name, Enter), like Maya; the object and its shape are renamed and it stays selected."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import (MODULE, check, dock_area, dock_region, ev, find_button, load_maya_layout, run, screenshot,  # noqa: E402
                 setup, step, tap, view3d, win)

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
GUI_TIMEOUT = 300


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def cb():
    return import_module(MODULE + ".ui.channel_box")


def dock():
    return dock_area(), dock_region()


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def wait(tag, n=3):
    for i in range(n):
        def w():
            redraw()
        w.__name__ = f"s_{tag}_wait{i}"
        step(w)


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
    C["ob"] = ob
    C["old"] = ob.name
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    dock_area('CHANNEL_BOX')
    redraw()


wait("scene", 3)


@step
def s_scene_shot():
    shot("gui_issue283_cb_rename_before.png")
# the name line: the lead's name at the top of the Channel Box
step(find_button(dock, lambda _p, c: "allset.cb_rename" in c, C, "name", x_frac=0.08, step_px=4))


@step
def s_found():
    check(f"the name line found ({C.get('name')})", C.get("name"))
    if not C.get("name"):
        raise RuntimeError("name line not found")
    ev('MOUSEMOVE', 'NOTHING', x=C["name"][0], y=C["name"][1])


@step
def s_click():
    x, y = C["name"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


wait("click", 2)


@step
def s_type():
    shot("gui_issue283_cb_rename_edit.png")
    ev('A', 'PRESS', ctrl=True)       # select the whole text, then type over it
    ev('A', 'RELEASE', ctrl=True)
    for ch in "box1":
        ev('TEXTINPUT', 'PRESS', unicode=ch)


@step
def s_enter():
    tap('RET')


wait("enter", 2)


@step
def s_renamed():
    shot("gui_issue283_cb_rename_after.png")
    ob = C["ob"]
    check(f"the object is renamed in place ({C['old']} -> {ob.name})", ob.name == "box1")
    check(f"its shape follows ({ob.data.name})", ob.data.name == "boxShape1")
    check("it stays selected and the lead", ob.select_get() and bpy.context.view_layer.objects.active == ob)


run()
