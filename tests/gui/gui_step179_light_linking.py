"""Light linking in a real UI: a point light and two cubes, Lighting/Shading > Break Light Links from the menu map
(Blender's light linking: the active light, the selected cube excluded), then Light Linking Editor opens a Properties
window on the Object tab (Blender's Light Linking panel); shot of that window."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def override():
    a, region = view3d()
    return bpy.context.temp_override(window=win(), screen=win().screen, area=a, region=region)


def _entries(coll):
    if coll is None:
        return {}
    return {ob.name: co.light_linking.link_state for ob, co in zip(coll.objects, coll.collection_objects)}


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    unit = import_module(MODULE + ".operators.units").maya_unit()
    with override():
        for x in (-2, 2):
            bpy.ops.allset.create(kind='CUBE')
            bpy.context.view_layer.objects.active.location = (x * unit, 0, 0)
        bpy.ops.allset.create(kind='POINT_LIGHT')
    obs = {o.name: o for o in bpy.context.scene.objects}
    light = next(o for o in obs.values() if o.type == 'LIGHT')
    cube = obs["pCube2"]
    for o in bpy.context.scene.objects:
        o.select_set(o in (light, cube))
    bpy.context.view_layer.objects.active = light
    C["light"] = light.name
    C["windows"] = len(bpy.context.window_manager.windows)
    with override():
        res = bpy.ops.allset.menu_item(item="Lighting/Shading/Break Light Links")
    ent = _entries(light.light_linking.receiver_collection)
    check(f"Break Light Links from the menu ({res}): pCube2 excluded from {light.name}, pCube1 not listed ({ent})",
          ent.get("pCube2") == 'EXCLUDE' and "pCube1" not in ent)


@step
def s_editor():
    with override():
        res = bpy.ops.allset.menu_item(item="Lighting/Shading/Light Linking Editor")
    C["res"] = res


@step
def s_editor_wait():
    pass


@step
def s_editor_check():
    wins = bpy.context.window_manager.windows
    w = wins[-1] if len(wins) > C["windows"] else None
    a = w.screen.areas[0] if w else None
    ctx = a.spaces.active.context if a is not None and a.type == 'PROPERTIES' else None
    C["tries"] = C.get("tries", 0) + 1
    if ctx != 'OBJECT' and C["tries"] < 15:          # the tab is set from a timer once the window has drawn
        sys.modules["sim"]._steps.insert(0, s_editor_check)
        return
    check(f"Light Linking Editor opens a Properties window on the Object tab ({C['res']}, {a and a.ui_type}, {ctx})",
          a is not None and a.ui_type == 'PROPERTIES' and ctx == 'OBJECT')
    if SHOTS and w is not None:
        screenshot(os.path.join(SHOTS, "gui_step179_light_linking_editor.png"))


run()
