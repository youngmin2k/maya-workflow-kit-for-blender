"""#294 in a real UI: the RMB marking menu over the mesh works in Sculpt Mode like in Object Mode.
1. Sculpt Mode, RMB drag W (Vertex) + release = Edit Mode, vertex select mode.
2. Sculpt Mode, RMB drag NE (Object Mode) + release = Object Mode.
3. Sculpt Mode, RMB click = the menu stays open, ESC = still sculpting.
4. A stencil brush keeps Blender's RMB stencil drag (no marking menu)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
DRAG = 120  # px, well past the marking menu threshold


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def cube():
    return bpy.data.objects["Cube"]


def menu_open():
    return bool(import_module(MODULE + ".marking.draw").ACTIVE.get("session"))


def to_sculpt():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for o in bpy.context.view_layer.objects:
            o.select_set(o == cube())
        bpy.context.view_layer.objects.active = cube()
        bpy.ops.object.mode_set(mode='SCULPT')


def rmb_pick(label, dx, dy, expect):
    """Steps: (in Sculpt Mode) RMB press over the cube, drag (dx, dy), release, then ``expect()``."""
    @step
    def s_press():
        to_sculpt()
        check(f"{label}: in Sculpt Mode", bpy.context.mode == 'SCULPT')
        ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
        ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"])

    @step
    def s_wait():
        check(f"{label}: RMB opens the marking menu in Sculpt Mode", menu_open())

    @step
    def s_drag():
        x, y = C["x"] + dx, C["y"] + dy
        ev('MOUSEMOVE', 'NOTHING', x=(C["x"] + x) // 2, y=(C["y"] + y) // 2)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)

    @step
    def s_release():
        shot(f"gui_issue294_sculpt_{label}.png")
        ev('RIGHTMOUSE', 'RELEASE', x=C["x"] + dx, y=C["y"] + dy)

    @step
    def s_check():
        expect(label)


@step
def s_setup():
    C["x"], C["y"] = setup()
    check("Maya keymap active", sys.modules["sim"].maya_keys())


def _vertex(label):
    ts = bpy.context.scene.tool_settings
    check(f"{label}: W = Vertex leaves Sculpt Mode for vertex select mode",
          bpy.context.mode == 'EDIT_MESH' and tuple(ts.mesh_select_mode) == (True, False, False))


def _object(label):
    check(f"{label}: NE = Object Mode leaves Sculpt Mode ({bpy.context.mode})", bpy.context.mode == 'OBJECT')


rmb_pick("vertex", -DRAG, 0, _vertex)
rmb_pick("object", DRAG, DRAG, _object)


@step
def s_click():
    to_sculpt()
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"])
    ev('RIGHTMOUSE', 'RELEASE', x=C["x"], y=C["y"])     # a quick click (same tick): the menu stays open


@step
def s_click_wait():
    pass


@step
def s_click_open():
    shot("gui_issue294_sculpt_click.png")
    check("RMB click in Sculpt Mode: the menu stays open", menu_open())
    tap('ESC')


@step
def s_click_closed():
    check("ESC closes it and Sculpt Mode stays", not menu_open() and bpy.context.mode == 'SCULPT')


@step
def s_stencil():
    brush = bpy.context.tool_settings.sculpt.brush
    C["brush"] = brush
    try:
        C["map"] = brush.texture_slot.map_mode
        brush.texture_slot.map_mode = 'STENCIL'
    except (AttributeError, TypeError, RuntimeError) as ex:
        C["map"] = None
        print("stencil brush not writable:", ex)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"])


@step
def s_stencil_check():
    if C["map"] is not None:
        check("stencil brush: RMB stays Blender's stencil drag (no marking menu)", not menu_open())
    ev('RIGHTMOUSE', 'RELEASE', x=C["x"], y=C["y"])


@step
def s_stencil_restore():
    if C["map"] is not None:
        C["brush"].texture_slot.map_mode = C["map"]
    tap('ESC')
    check("still in Sculpt Mode after the stencil drag", bpy.context.mode == 'SCULPT')


run()
