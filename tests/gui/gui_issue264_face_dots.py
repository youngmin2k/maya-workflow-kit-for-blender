"""UV mode from face mode (#264): the 3D View shows the UVs as points and no face centre dots, also in wireframe
(where Blender draws face dots for face select mode); F11 brings face mode back."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, setup, view3d, win, load_maya_layout, screenshot  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def uv_tools():
    return import_module(MODULE + ".operators.uv_tools")


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, reg = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=reg):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.object.mode_set(mode='EDIT')
        ts = bpy.context.scene.tool_settings
        ts.mesh_select_mode = (False, False, True)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.view3d.view_selected()
        uv_tools().set_component(bpy.context, 'UV')       # the kit's F12 UV component
    sp = area.spaces.active
    sp.shading.type = 'WIREFRAME'
    sp.region_3d.view_distance *= 2.5
    C["area"] = area


@step
def s_wait():
    pass


def centres():
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    area, region = view3d()
    ob = bpy.context.edit_object
    ob.update_from_editmode()
    out = []
    for p in ob.data.polygons:
        q = location_3d_to_region_2d(region, area.spaces.active.region_3d, ob.matrix_world @ p.center)
        if q is not None and 8 < q.x < region.width - 8 and 8 < q.y < region.height - 8:
            out.append((int(q.x + region.x), int(q.y + region.y)))
    return out


@step
def s_shot():
    C["path"] = os.path.join(SHOTS or bpy.app.tempdir, "issue264_face_dots.png")
    screenshot(C["path"])
    C["pts"] = centres()


@step
def s_check():
    ts = bpy.context.scene.tool_settings
    check(f"UV mode from face mode: the mesh select mode is vertex ({tuple(ts.mesh_select_mode)})",
          tuple(ts.mesh_select_mode) == (True, False, False) and not ts.use_uv_select_sync)
    img = bpy.data.images.load(C["path"])
    w = img.size[0]
    px = img.pixels[:]

    def rgb(x, y):
        return [round(px[(y * w + x) * 4 + k] * 255) for k in range(3)]
    dots = []
    for x, y in C["pts"]:
        c = rgb(x, y)
        if c[0] > c[1] > c[2] and c[0] - c[2] > 60:      # an orange dot where the face centre is
            dots.append((x, y, c))
    check(f"no face centre dots in wireframe ({len(C['pts'])} centres, coloured: {dots})", C["pts"] and not dots)
    bpy.data.images.remove(img)
    area, reg = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=reg):
        uv_tools().set_component(bpy.context, 'FACE')     # F11
    check(f"F11 brings face mode back ({tuple(ts.mesh_select_mode)}, sync {ts.use_uv_select_sync})",
          tuple(ts.mesh_select_mode) == (False, False, True) and ts.use_uv_select_sync)
    C["area"].spaces.active.shading.type = 'SOLID'


run()
