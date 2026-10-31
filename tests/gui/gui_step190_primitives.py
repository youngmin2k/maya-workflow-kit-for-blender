"""In a real UI: the seven new Create > Polygon Primitives (Pipe, Helix, Gear, Soccer Ball, Super Ellipse,
Spherical Harmonics, Ultra Shape) made from the Create menu actions in the Maya Workflow Kit layout, laid out in a row
and framed (shot); the last one's node shows in Channel Box INPUTS."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
KINDS = ('PIPE', 'HELIX', 'GEAR', 'SOCCER_BALL', 'SUPER_ELLIPSE', 'SPHERICAL_HARMONICS', 'ULTRA_SHAPE')


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region)


@step
def s_setup():
    C["x"], C["y"] = setup()
    load_maya_layout()


@step
def s_create():
    bpy.ops.allset.keymap_activate()
    unit = import_module(MODULE + ".operators.units").maya_unit()
    made = []
    with override():
        for i, kind in enumerate(KINDS):
            bpy.ops.allset.create(kind=kind)
            ob = bpy.context.view_layer.objects.active
            ob.location.x = (i - 3) * 3.0 * unit
            made.append(ob)
    C["made"] = made
    names = [o.name for o in made]
    check(f"seven primitives created with Maya names ({names})",
          names[:4] == ["pPipe1", "pHelix1", "pGear1", "pSolid1"] and all(n.startswith("pSuperShape") for n in names[4:]))


@step
def s_frame():
    with override():
        for o in bpy.context.selected_objects:
            o.select_set(False)
        for o in C["made"]:
            o.select_set(True)
        bpy.context.view_layer.objects.active = C["made"][-1]
        bpy.ops.view3d.view_selected()


@step
def s_wait():
    with override():
        bpy.ops.view3d.zoom(delta=2)
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_selected_shot():
    shot("gui_step190_primitives_selected.png")
    for o in C["made"][:-1]:
        o.select_set(False)
    C["made"][-1].select_set(False)
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_shot():
    shot("gui_step190_primitives.png")
    prim_history = import_module(MODULE + ".operators.prim_history")
    _owner, node = prim_history.node_of(C["made"][-1])   # INPUTS shown in the selected shot
    check("Ultra Shape keeps its polySuperShape node for Channel Box INPUTS",
          node is not None and node["type"] == "polySuperShape")


run()
