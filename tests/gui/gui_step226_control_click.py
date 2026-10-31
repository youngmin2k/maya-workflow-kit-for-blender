"""L1 in a real UI: a joint with a control shape (bone
Custom Shape made by Maya ``parent -s -r``) is picked by clicking the drawn shape wire — the click selects the
bone (Pose, joint1 = lead); a click inside the circle, on the octahedron Blender doesn't draw for a shaped bone,
selects nothing."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, win  # noqa: E402

C = {}


def mod(name):
    return import_module(MODULE + name)


def main_view():
    toolbox = mod(".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def override():
    area, region = main_view()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def to_window(p):
    area, region = main_view()
    xy = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, p)
    return int(round(region.x + xy.x)), int(round(region.y + xy.y))


def rig():
    return bpy.data.objects["skeleton1"]


def deselect_all():
    cb = mod(".ui.channel_box")
    with override():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    for pb in rig().pose.bones:
        cb.set_bone_selected(pb, False)
    rig().data.bones.active = None
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = None


@step
def s_setup():
    setup()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    k = mod(".operators.units").maya_unit()
    C["k"] = k
    arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm.data.edit_bones.new("joint1")
        eb.head, eb.tail = (0, 0, 0), (0, 0, 2 * k)        # bone Y = world Z, bone X = world X
        bpy.ops.object.mode_set(mode='OBJECT')
    create = mod(".operators.create")
    with override():
        curve = create.create(bpy.context, 'NURBS_CIRCLE')
    curve.data.transform(Matrix.Scale(3.0, 4))                 # radius 3 Maya units
    bpy.context.view_layer.update()
    shapes = mod(".operators.control_shapes")
    shapes.parent_shape(curve, arm.pose.bones["joint1"], relative=True)
    # front view: the -r circle lies in the bone's X / Y plane = world X / Z
    area, region = main_view()
    with override():
        bpy.ops.view3d.view_axis(type='FRONT')
    rv3d = area.spaces.active.region_3d
    rv3d.view_perspective = 'ORTHO'
    rv3d.view_location = (0, 0, 0)
    rv3d.view_distance = 12 * k
    area.tag_redraw()
    deselect_all()


@step
def s_wire_hover():
    shapes = mod(".operators.control_shapes")
    dg = bpy.context.evaluated_depsgraph_get()
    pb = rig().pose.bones["joint1"]
    a, b = shapes.shape_segments(rig(), pb, dg)
    check(f"the control shape has a wire ({len(a)} segments)", len(a) >= 8)
    i = max(range(len(a)), key=lambda j: a[j][0] + b[j][0])        # the rightmost segment
    C["wire"] = to_window(Vector((a[i] + b[i]) / 2))
    ev('MOUSEMOVE', 'NOTHING', x=C["wire"][0], y=C["wire"][1])


@step
def s_wire_click():
    x, y = C["wire"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_wire_check():
    cb = mod(".ui.channel_box")
    pb = rig().pose.bones["joint1"]
    check(f"click on the shape wire at {C['wire']} -> Pose ({rig().mode})", rig().mode == 'POSE')
    check("joint1 selected and lead", cb.bone_selected(pb) and rig().data.bones.active == pb.bone)


@step
def s_inside_reset():
    deselect_all()
    C["mid"] = to_window(Vector((0, 0, 1 * C["k"])))      # half way up the bone, inside the circle
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])


@step
def s_inside_click():
    x, y = C["mid"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_inside_check():
    cb = mod(".ui.channel_box")
    pb = rig().pose.bones["joint1"]
    check(f"click inside the circle at {C['mid']} (no wire) selects no joint",
          not cb.bone_selected(pb) and rig().mode != 'POSE')


run()
