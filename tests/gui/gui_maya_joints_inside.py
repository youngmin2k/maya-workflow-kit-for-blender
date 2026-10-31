"""Joints inside a mesh (cm scene, Maya layout): a three-joint chain through a cylinder. Like Maya, the shaded cylinder
hides the joint inside it; a wireframe view and X-Ray Joints show it."""

import os
import sys
from importlib import import_module

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name):
    path = os.path.join(SHOTS or bpy.app.tempdir, f"gui_maya_joints_inside_{name}.png")
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]


def violet_at(px, world, half=80):
    """Joint-violet pixels (thin smooth lines blend with the background) in a square around ``world``; the blue
    mesh wire and the grey background don't count."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    area, region = view3d()
    p = location_3d_to_region_2d(region, area.spaces.active.region_3d, world)
    x, y = int(round(p.x + region.x)), int(round(p.y + region.y))
    patch = px[y - half:y + half, x - half:x + half]
    r, g, b = patch[..., 0], patch[..., 1], patch[..., 2]
    return int(((r > 0.08) & (r < 0.4) & (g < r - 0.04) & (b > g + 0.08)).sum())


def middle():
    arm = bpy.data.objects[C["arm"]]
    return arm.matrix_world @ arm.data.bones[C["names"][1]].head_local


def space():
    return view3d()[0].spaces.active


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    k = mod(".operators.units").maya_unit()
    bpy.ops.mesh.primitive_cylinder_add(radius=1.0 * k, depth=2.0 * k, location=(0.0, 0.0, 0.0))
    joints = mod(".operators.joints")
    arm = joints.new_skeleton(bpy.context)
    names, parent = [], None
    for z in (-6.0, 0.0, 6.0):         # the end joints far outside the sampled square
        parent = joints.add_joint(arm, Vector((0.0, 0.0, z)) * k, parent, length=1.0 * k)
        names.append(parent)
    joints.finish(bpy.context, arm, names)
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for n in names:
        arm.data.bones[n][joints.RADIUS] = 1.6           # drawn radius 0.8: inside the cylinder (radius 1)
    for ob in bpy.context.scene.objects:
        ob.select_set(False)
    C["arm"], C["names"] = arm.name, names
    rv3d = space().region_3d
    rv3d.view_perspective = 'PERSP'
    rv3d.view_location = (0.0, 0.0, 0.0)
    rv3d.view_distance = 8.0 * k
    redraw()


@step
def s_shaded():
    n = violet_at(shot("shaded"), middle())
    check(f"the shaded cylinder hides the joint inside it ({n} px)", n == 0)
    space().shading.type = 'WIREFRAME'
    redraw()


@step
def s_wireframe():
    n = violet_at(shot("wireframe"), middle())
    check(f"a wireframe view shows the joint inside the cylinder ({n} px)", n > 20)
    space().shading.type = 'SOLID'
    space().overlay.show_xray_bone = True
    redraw()


@step
def s_xray_joints():
    n = violet_at(shot("xray_joints"), middle())
    check(f"X-Ray Joints shows the joint inside the cylinder ({n} px)", n > 20)


run()
