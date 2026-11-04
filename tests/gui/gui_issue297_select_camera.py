"""#297 in a real UI, the reporter's steps: a scene made in Blender mode, then Maya mode, then View > Select Camera
in the perspective view selects the persp camera (the scene gets the startup cameras on that first use); the
panel toolbar's Select Camera button is not greyed; Undo takes the cameras back out."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region)


@step
def s_setup():
    setup()
    mod("switch").set_mode(False)                     # the scene is made in Blender mode


@step
def s_blender():
    names = sorted(mod("operators.startup_cameras").names(bpy.context.scene))
    check(f"Blender mode, a Blender scene without startup cameras ({names})", not mod("switch").is_on() and not names)
    mod("switch").set_mode(True)


@step
def s_maya():
    check(f"Maya mode ({win().workspace.name})", mod("switch").is_on())
    area, _r = view3d()
    area.spaces.active.region_3d.view_perspective = 'PERSP'
    bpy.data.objects["Cube"].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["Cube"]
    C["n"] = len(bpy.data.objects)
    with override():
        check("the toolbar's Select Camera button is enabled in the persp view",
              mod("ui.panel_menus").has_panel_camera(bpy.context))
        C["res"] = bpy.ops.allset.panel_set('INVOKE_DEFAULT', True, key='SELECT_CAMERA')   # an undo step


@step
def s_selected():
    lead = bpy.context.view_layer.objects.active
    sc = mod("operators.startup_cameras")
    check(f"View > Select Camera: {C['res']}, persp is the lead ({lead.name if lead else None})",
          C["res"] == {'FINISHED'} and lead is not None and lead.get(sc.MARK) == "persp")
    check("the cube is no longer selected", not bpy.data.objects["Cube"].select_get())
    check(f"the scene got persp / top / front / side ({sorted(sc.names(bpy.context.scene))})",
          sorted(sc.names(bpy.context.scene)) == sorted(sc.NAMES) and len(bpy.data.objects) == C["n"] + 4)
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_issue297_select_camera.png"))
    with override():
        bpy.ops.allset.panel_set('INVOKE_DEFAULT', True, key='SELECT_CAMERA')   # an undo step


@step
def s_again():
    check(f"a second Select Camera makes nothing new ({len(bpy.data.objects)})", len(bpy.data.objects) == C["n"] + 4)
    _area, r = view3d()
    for _i in range(2):                                # Ctrl+Z twice: both Select Camera steps
        ev('Z', 'PRESS', x=r.x + r.width // 2, y=r.y + r.height // 2, ctrl=True)
        ev('Z', 'RELEASE', x=r.x + r.width // 2, y=r.y + r.height // 2, ctrl=True)


@step
def s_undo():
    sc = mod("operators.startup_cameras")
    check(f"Undo takes the startup cameras back out ({sorted(sc.names(bpy.context.scene))})",
          not sc.names(bpy.context.scene) and len(bpy.data.objects) == C["n"])


run()
