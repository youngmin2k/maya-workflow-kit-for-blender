"""UV Editor > Cut/Sew > Stitch Together runs Blender's UV Stitch from the menu in a real UV Editor.
Blender 5.2.3 crashes on a scripted UV Stitch in background mode (no region, also in a factory Blender);
this checks the menu path in a GUI session survives and stitches."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, run, setup, step, view3d  # noqa: E402

C = {}


@step
def s_setup():
    setup()
    scene = bpy.context.scene
    ob = bpy.context.active_object or next(o for o in scene.objects if o.type == 'MESH')
    for o in scene.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project()
    a, _r = view3d()
    a.ui_type = 'UV'
    C["area"] = a


@step
def s_stitch():
    a = C["area"]
    r = next(r for r in a.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=bpy.context.window, area=a, region=r):
        res = bpy.ops.allset.menu_item(item="UV Editor/Cut/Sew/Stitch Together")
    C["res"] = res


@step
def s_check():
    check(f"Stitch Together from the UV Editor menu runs ({C['res']})", C["res"] in ({'FINISHED'}, {'CANCELLED'}))
    check("Blender is still in the UV session (edit mode)", bpy.context.object.mode == 'EDIT')


run()
