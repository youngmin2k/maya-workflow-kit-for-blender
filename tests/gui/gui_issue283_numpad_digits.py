"""#283 in a real UI: numpad digits over the viewport act like the top row — numpad 3 smooth preview, numpad 1 rough
display, numpad 4 / 5 / 6 wireframe / shaded / textured (simulated keys over the viewport)."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, tap, view3d  # noqa: E402

C = {}


def centre():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


def preview():
    return bpy.data.objects["Cube"].modifiers.get("Maya Smooth Preview")


def shading():
    return view3d()[0].spaces.active.shading


@step
def s_setup():
    C["x"], C["y"] = setup()
    cube = bpy.data.objects["Cube"]
    for ob in bpy.context.view_layer.objects:
        ob.select_set(ob == cube)
    bpy.context.view_layer.objects.active = cube


@step
def s_three():
    centre()
    tap('NUMPAD_3')


@step
def s_smooth():
    mod = preview()
    check("numpad 3 = smooth preview", mod is not None and mod.show_viewport)
    centre()
    tap('NUMPAD_1')


@step
def s_rough():
    mod = preview()
    check("numpad 1 = rough display", mod is None or not mod.show_viewport)
    centre()
    tap('NUMPAD_4')


@step
def s_wire():
    check(f"numpad 4 = wireframe ({shading().type})", shading().type == 'WIREFRAME')
    centre()
    tap('NUMPAD_5')


@step
def s_shaded():
    check(f"numpad 5 = shaded ({shading().type})", shading().type == 'SOLID')
    centre()
    tap('NUMPAD_6')


@step
def s_textured():
    sh = shading()
    check(f"numpad 6 = shaded and textured ({sh.type}, {sh.color_type})",
          sh.type == 'SOLID' and sh.color_type == 'TEXTURE' or sh.type == 'MATERIAL')


run()
