"""In a real UI (#68): with a cube selected in object mode the kit's Maya
UV menu > Automatic projects the whole cube (polyAutoProjection: 6 shells, 24 UVs);
in component mode the UV Editor's Create > Best Plane and Contour Stretch are enabled and run.
Menus are opened as menus and picked with the keyboard (arrows + Return). Screenshots: gui_step139_uv_menu.png,
gui_step139_uv_editor_create.png."""

import os
import sys
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, screenshot, step, tap, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def uv_info(ob):
    """(shells, distinct UVs) of the object's UV map."""
    uvt = import_module(MODULE + ".operators.uv_tools")
    if ob.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(ob.data)
    else:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    n = len(uvt.islands(bm, uv))
    uvs = len({(lp.vert.index, round(lp[uv].uv.x, 4), round(lp[uv].uv.y, 4)) for f in bm.faces for lp in f.loops})
    if ob.mode != 'EDIT':
        bm.free()
    return n, uvs


def open_menu(idname):
    area, region = view3d()
    x, y = region.x + region.width // 2, region.y + region.height // 2
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.call_menu(name=idname)


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
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    C["ob"] = bpy.context.view_layer.objects.active
    C["before"] = uv_info(C["ob"])
    check(f"object mode with pCube1 (UVs {C['before']})", bpy.context.mode == 'OBJECT' and C["ob"] is not None)
    open_menu(import_module(MODULE + ".ui.menu_sets").menu_idname("mainUVMenu"))


@step
def s_walk():
    # Blender opens a menu with its remembered row under the mouse: Home = the tear-off line, then the selectable rows
    # UV Editor, UV Set Editor, Assign Checker Shader, Automatic (the "Create" section label is skipped).
    tap('HOME')
    for _ in range(4):
        tap('DOWN_ARROW')


@step
def s_walk_shot():
    shot("gui_step139_uv_menu.png")
    tap('RET')


@step
def s_wait():
    pass


@step
def s_automatic():
    ob = C["ob"]
    after = uv_info(ob)
    check(f"UV > Automatic from object mode projects the whole cube: {C['before']} -> {after} (Maya 6 shells, 24 UVs)",
          after == (6, 24))
    check("still in object mode", bpy.context.mode == 'OBJECT')
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.select_all(action='SELECT')
    C["edit_before"] = uv_info(ob)
    menus = import_module(MODULE + ".ui.menu_sets")
    data = import_module(MODULE + ".ui.editor_menu_data")
    idx = [m[0] for m in data.EDITORS["UV Editor"]].index("Create")
    open_menu(menus.editor_menu_idname("UV Editor", idx))


@step
def s_create_walk():
    # Create ends with Best Plane, Contour Stretch: End = the last row.
    tap('END')
    tap('UP_ARROW')


@step
def s_create_shot():
    shot("gui_step139_uv_editor_create.png")
    tap('RET')


@step
def s_wait2():
    pass


@step
def s_best_plane():
    after = uv_info(C["ob"])
    check(f"UV Editor > Create > Best Plane is enabled and projects the faces: {C['edit_before']} -> {after}",
          after != C["edit_before"] and after[0] == 1)
    C["bp"] = after
    menus = import_module(MODULE + ".ui.menu_sets")
    data = import_module(MODULE + ".ui.editor_menu_data")
    idx = [m[0] for m in data.EDITORS["UV Editor"]].index("Create")
    open_menu(menus.editor_menu_idname("UV Editor", idx))


@step
def s_contour_walk():
    tap('END')


@step
def s_contour_run():
    tap('RET')


@step
def s_wait3():
    pass


@step
def s_contour():
    after = uv_info(C["ob"])
    check(f"UV Editor > Create > Contour Stretch is enabled and runs: {C['bp']} -> {after} (one shell)",
          after != C["bp"] and after[0] == 1)
    check("still in component mode", bpy.context.mode == 'EDIT_MESH')


run(interval=0.5)
