"""Lane DEFORM (#34) in a real UI: Deform > Lattice on a cube makes
ffd1Lattice around it (2 5 2 divisions), selected, and its Channel Box INPUTS show ffd1 with Envelope; the
Lattice option box opens "Lattice Options". Screenshots to ALLSET_GUI_SHOTS (default tmp/gui144_deform)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import (MODULE, check, dock_area, dock_region, ev, find_button, run, screenshot, scroll_channel_box,  # noqa: E402
                 setup, step, view3d, win)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "") or os.path.join(ROOT, "tmp", "gui144_deform")
C = {}


def shot(name):
    os.makedirs(SHOTS, exist_ok=True)
    screenshot(os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def cb():
    return import_module(MODULE + ".ui.channel_box")


@step
def s_setup():
    setup()
    a, _r = view3d()
    C["mid"] = (a.x + a.width // 2, a.y + a.height // 2)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.create(kind='CUBE')
    dock_area('CHANNEL_BOX')
    redraw()


@step
def s_menu_lattice():
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    a, r = view3d()
    with bpy.context.temp_override(window=win(), area=a, region=r):
        res = bpy.ops.allset.menu_item('INVOKE_DEFAULT', item="Deform/Lattice")
    check(f"Deform > Lattice runs ({res})", res == {'FINISHED'})
    lat = bpy.data.objects.get("ffd1Lattice")
    cube = bpy.data.objects.get("pCube1")
    check("ffd1Lattice made", lat is not None and lat.type == 'LATTICE')
    check("Lattice modifier ffd1 on pCube1", cube is not None and "ffd1" in cube.modifiers
          and cube.modifiers["ffd1"].object == lat)
    if lat is not None:
        check("Maya divisions 2 5 2 (S T U; Maya Y = Blender Z)",
              (lat.data.points_u, lat.data.points_w, lat.data.points_v) == (2, 5, 2))
        check(f"fitted to the cube's bounding box (scale {tuple(round(s, 4) for s in lat.scale)})",
              all(abs(s - 1.0) < 1e-4 for s in lat.scale) and lat.location.length < 1e-4)
        check("ffd1Lattice selected (Maya)", bpy.context.view_layer.objects.active == lat
              and list(bpy.context.selected_objects) == [lat])
        for md in cb()._inputs(lat):
            cb().set_open(lat, cb().mod_node(md))
        cb().rebuild_rows()
        scroll_channel_box()   # INPUTS sit at the end of the Channel Box part
    redraw()


@step
def s_wait():
    redraw()


@step
def s_rows():
    rows = [(r.name, r.text) for r in bpy.context.scene.allset_cb.rows if r.kind == "INPUT"]
    check(f"Channel Box INPUTS of ffd1Lattice: ffd1 Envelope 1 ({rows})", rows == [("maya:envelope", "1")])
    shot("gui_step144_lattice.png")


def _dock():
    return dock_area(), dock_region()


step(find_button(_dock, lambda p, _c: "allset_cb.rows[" in p and p.endswith("].text"), C, "env_field", x_frac=0.7,
                 step_px=4))


@step
def s_found():
    check(f"the Envelope field is drawn in the dock ({C.get('env_field')})", C.get("env_field") is not None)


@step
def s_option_box():
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    with bpy.context.temp_override(window=win()):
        res = bpy.ops.allset.menu_option_box('INVOKE_DEFAULT', item="Deform/Lattice")
    check(f"Lattice option box opens ({res})", res in ({'FINISHED'}, {'RUNNING_MODAL'}))


@step
def s_wait2():
    pass


@step
def s_option_shot():
    shot("gui_step144_lattice_options.png")
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


run()
