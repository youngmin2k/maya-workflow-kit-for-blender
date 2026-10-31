"""In a real UI: = / - manipulator size, Alt+5 wireframe on shaded, Home default view,
PgUp / PgDn smoothing level, 0 back to rough display (simulated keys over the viewport)."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, tap, view3d  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def centre():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


def manip_size():
    """= / - scale the kit's Move / Scale manipulator for the session (Blender's gizmo_size is a preference)."""
    from importlib import import_module
    return import_module(MODULE + ".ui.manipulator").SIZE[0]


def preview():
    return bpy.data.objects["Cube"].modifiers.get("Maya Smooth Preview")


@step
def s_setup():
    C["x"], C["y"] = setup()
    C["size"] = manip_size()
    centre()
    tap('EQUAL')


@step
def s_bigger():
    size = manip_size()
    check(f"= makes the manipulator bigger ({C['size']} -> {size})", size > C["size"])
    C["big"] = size
    centre()
    tap('MINUS')


@step
def s_smaller():
    size = manip_size()
    check(f"- makes it smaller ({C['big']} -> {size})", size < C["big"])
    ov = view3d()[0].spaces.active.overlay
    C["wire"] = ov.show_wireframes
    centre()
    ev('FIVE', 'PRESS', alt=True)
    ev('FIVE', 'RELEASE', alt=True)


@step
def s_wire():
    ov = view3d()[0].spaces.active.overlay
    check(f"Alt+5 toggles wireframe on shaded ({C['wire']} -> {ov.show_wireframes})",
          ov.show_wireframes != C["wire"])
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step27_wireframe_on_shaded.png"))
    rv3d = view3d()[0].spaces.active.region_3d
    rv3d.view_distance = 50.0
    rv3d.view_location = (3.0, 3.0, 3.0)
    centre()
    tap('HOME')


@step
def s_home():
    rv3d = view3d()[0].spaces.active.region_3d
    check(f"Home goes to the startup persp view (distance {rv3d.view_distance:.2f} BU, "
          f"location {tuple(round(v, 2) for v in rv3d.view_location)})",
          abs(rv3d.view_distance - 44.82) < 0.05 and rv3d.view_location.length < 1e-6)
    cube = bpy.data.objects["Cube"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o is cube)
    bpy.context.view_layer.objects.active = cube
    centre()
    tap('THREE')


@step
def s_three():
    mod = preview()
    C["level"] = mod.levels if mod else None
    centre()
    tap('PAGE_UP')


@step
def s_pgup():
    mod = preview()
    check(f"PgUp raises the smooth preview level ({C['level']} -> {mod.levels if mod else None})",
          mod is not None and mod.levels == C["level"] + 1)
    centre()
    tap('PAGE_DOWN')
    tap('PAGE_DOWN')


@step
def s_pgdn():
    mod = preview()
    check(f"PgDn lowers it ({mod.levels})", mod.levels == C["level"] - 1)
    centre()
    tap('ZERO')


@step
def s_zero():
    mod = preview()
    check("0 = rough display (preview off)", not mod.show_viewport)


run()
