"""In the Maya Workflow Kit layout: a kit material's colour edit shows in the default shaded
viewport (Solid / Material colour reads the display colour the kit keeps in sync)."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, run, screenshot, setup, step, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    path = os.path.join(SHOTS or os.path.join(os.environ.get("TEMP", "."), "gui129"), name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    screenshot(path)
    return path


def pixel(path, x, y):
    im = bpy.data.images.load(path, check_existing=False)
    w, _h = im.size
    i = (y * w + x) * 4
    px = im.pixels[i:i + 3]
    bpy.data.images.remove(im)
    return tuple(round(v * 255) for v in px)


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
        ob = bpy.context.active_object
        ob.scale = (6, 6, 6)
        bpy.ops.view3d.view_selected()
        ob.select_set(False)
    sh = area.spaces.active.shading
    check(f"the template viewport is Solid / Material colour ({sh.type}, {sh.color_type})",
          sh.type == 'SOLID' and sh.color_type == 'MATERIAL')
    from importlib import import_module
    from sim import MODULE
    material = import_module(MODULE + ".operators.material")
    mat = material.new_material('LAMBERT')
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    # the AE Color field writes Maya's Color: the "Maya Diffuse" input (material.color_socket)
    material.color_socket(mat).default_value = (0.8, 0.02, 0.02, 1.0)
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_wait():
    pass


@step
def s_shot():
    area, region = view3d()
    path = shot("gui_step129_material_red.png")
    rgb = pixel(path, region.x + region.width // 2 - region.width // 6, region.y + region.height // 2)
    check(f"#14: the cube shows its red material colour in shaded mode ({rgb})",
          rgb[0] > 90 and rgb[0] > 2 * rgb[1] and rgb[0] > 2 * rgb[2])


run()
