"""In a real UI: Deform > Tension on a subdivided cube from the Maya menu makes
tension1 (a Geometry Nodes modifier) and its Attribute Editor tab draws Maya's attributes (Smoothing Iterations …);
Deform > Sculpt makes sculptor1 and selects it; the Tension option box opens "Tension Options".
Screenshots to ALLSET_GUI_SHOTS (default tmp/gui205_deform)."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, dock_area, ev, run, screenshot, setup, step, view3d, win  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "") or os.path.join(ROOT, "tmp", "gui205_deform")
C = {}


def shot(name):
    os.makedirs(SHOTS, exist_ok=True)
    screenshot(os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def menu(item):
    a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    with bpy.context.temp_override(window=win(), area=a, region=r):
        return bpy.ops.allset.menu_item('INVOKE_DEFAULT', item=item)


@step
def s_setup():
    setup()
    a, _r = view3d()
    C["mid"] = (a.x + a.width // 2, a.y + a.height // 2)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.create(kind='CUBE')
        cube = bpy.context.active_object
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.subdivide(number_cuts=2)
        bpy.ops.object.mode_set(mode='OBJECT')
    C["cube"] = cube.name
    redraw()


@step
def s_tension():
    res = menu("Deform/Tension")
    cube = bpy.data.objects.get(C["cube"])
    md = cube.modifiers.get("tension1") if cube else None
    check(f"Deform > Tension runs ({res})", res == {'FINISHED'})
    check("tension1 is a Geometry Nodes modifier on pCube1", md is not None and md.type == 'NODES')
    for ob in bpy.context.scene.objects:
        ob.select_set(ob == cube)
    bpy.context.view_layer.objects.active = cube
    dock_area('ATTRIBUTE_EDITOR')
    redraw()


@step
def s_tension_wait():
    redraw()


@step
def s_tension_shot():
    shot("gui_step205_tension_ae.png")
    a, _r = view3d()
    with bpy.context.temp_override(window=win(), area=a):
        C["window"] = bpy.ops.allset.menu_item('INVOKE_DEFAULT', item="Deform/Tension", option=True) \
            if "option" in bpy.ops.allset.menu_item.get_rna_type().properties else None
    redraw()


@step
def s_sculpt():
    for ob in bpy.context.scene.objects:
        ob.select_set(ob.name == C["cube"])
    bpy.context.view_layer.objects.active = bpy.data.objects[C["cube"]]
    res = menu("Deform/Sculpt")
    sculptor = bpy.data.objects.get("sculptor1")
    check(f"Deform > Sculpt runs ({res})", res == {'FINISHED'})
    check("sculptor1 made and selected (Maya)", sculptor is not None
          and bpy.context.view_layer.objects.active == sculptor)
    check("sculpt1 modifier on pCube1", "sculpt1" in bpy.data.objects[C["cube"]].modifiers)
    redraw()


@step
def s_sculpt_shot():
    shot("gui_step205_sculpt.png")


run()
