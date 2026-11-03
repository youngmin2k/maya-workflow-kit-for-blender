"""#289: the main view's display mode follows a workspace switch, like Maya's shared persp panel. Wireframe set in
General stays wireframe in Rigging, so a joint inside a cylinder is drawn there; X-Ray Joints follows too."""

import os
import sys
from importlib import import_module

import bpy
import numpy as np
from mathutils import Euler, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, screenshot, setup, step, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def main_view():
    area, region = mod(".ui.status_line").main_view3d(win().screen)
    return area, region


def violet_at(world, half=40):
    """Joint-violet pixels in a square around ``world`` (the blue mesh wire and the grey background don't count)."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    path = os.path.join(SHOTS or bpy.app.tempdir, "gui_issue289_rigging.png")
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    px = px.reshape(h, w, 4)[..., :3]
    area, region = main_view()
    p = location_3d_to_region_2d(region, area.spaces.active.region_3d, world)
    x, y = int(round(p.x + region.x)), int(round(p.y + region.y))
    patch = px[y - half:y + half, x - half:x + half]
    r, g, b = patch[..., 0], patch[..., 1], patch[..., 2]
    return int(((r > 0.08) & (r < 0.4) & (g < r - 0.04) & (b > g + 0.08)).sum())


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_general():
    bpy.ops.allset.keymap_activate()
    space = main_view()[0].spaces.active
    check("General starts shaded", space.shading.type == 'SOLID')
    space.shading.type = 'WIREFRAME'
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.maya_workspace(name="Rigging")


@step
def s_rigging():
    check("the Rigging workspace is shown", win().workspace.name == "Rigging")
    area, region = main_view()
    space = area.spaces.active
    check(f"Rigging's main view is wireframe too ({space.shading.type})", space.shading.type == 'WIREFRAME')
    k = mod(".operators.units").maya_unit()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        mod(".operators.create").create(bpy.context, 'CYLINDER', overrides={"subdivisionsHeight": 20})
    joints = mod(".operators.joints")
    arm = joints.new_skeleton(bpy.context)
    names, parent = [], None
    for z in (-1.4, 0.0, 1.4):
        parent = joints.add_joint(arm, Vector((0.0, 0.0, z)) * k, parent, length=1.0 * k)
        names.append(parent)
    joints.finish(bpy.context, arm, names)
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in bpy.context.scene.objects:
        ob.select_set(False)
    C["mid"] = arm.matrix_world @ arm.data.bones[names[1]].head_local
    rv3d = space.region_3d
    rv3d.view_perspective = 'ORTHO'
    rv3d.view_rotation = Euler((1.5707963, 0.0, 0.0)).to_quaternion()
    rv3d.view_location = (0.0, 0.0, 0.0)
    rv3d.view_distance = 6.0 * k
    area.tag_redraw()


@step
def s_drawn():
    n = violet_at(C["mid"])
    check(f"the joint inside the cylinder is drawn in Rigging's wireframe view ({n} px)", n > 20)
    space = main_view()[0].spaces.active
    space.shading.type = 'SOLID'
    space.overlay.show_xray_bone = True
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.maya_workspace(name="General")


@step
def s_back():
    space = main_view()[0].spaces.active
    check(f"back in General: shaded again ({space.shading.type})", space.shading.type == 'SOLID')
    check("X-Ray Joints followed the switch", space.overlay.show_xray_bone)


run()
