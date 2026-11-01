"""A marquee over kit-drawn joints in the Maya layout when nothing is selected yet: the joint inside is picked, in
Pose mode and in Object Mode, and one Ctrl+Z takes the pick back (no more). Blender's own box changes nothing there
(its bones are off), so it ends without a result of its own."""

import os
import sys
from importlib import import_module

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, setup, step, view3d, win  # noqa: E402

C = {}


def mod(name):
    return import_module(MODULE + name)


def to_window(world):
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    area, region = view3d()
    p = location_3d_to_region_2d(region, area.spaces.active.region_3d, world)
    return Vector((p.x + region.x, p.y + region.y))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def arm():
    return bpy.data.objects[C["arm"]]


def tip():
    a = arm()
    return to_window(a.matrix_world @ a.data.bones[C["names"][2]].head_local)


def selected_joints():
    a = arm()
    if a.mode != 'POSE':
        return []
    cb = mod(".ui.channel_box")
    return [pb.name for pb in a.pose.bones if cb.bone_selected(pb)]


def mark_undo(frame):
    """A known undo step: the scene at ``frame`` (an undo past it shows another frame)."""
    bpy.context.scene.frame_set(frame)
    bpy.ops.ed.undo_push(message=f"frame {frame}")


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    joints = mod(".operators.joints")
    k = mod(".operators.units").maya_unit()
    a = joints.new_skeleton(bpy.context)
    names, parent = [], None
    for x in (-8.0, 0.0, 8.0):
        parent = joints.add_joint(a, Vector((x, 0.0, 4.0)) * k, parent, length=1.0 * k)
        names.append(parent)
    joints.finish(bpy.context, a, names)
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for n in names:
        a.data.bones[n][joints.RADIUS] = 4.0
    C["arm"], C["names"] = a.name, names
    area, _region = view3d()
    rv3d = area.spaces.active.region_3d
    rv3d.view_perspective = 'PERSP'
    rv3d.view_location = (0.0, 0.0, 4.0 * k)
    rv3d.view_distance = 40.0 * k
    # Pose mode with nothing selected (after a Deselect All the active joint stays)
    for ob in bpy.context.scene.objects:
        ob.select_set(False)
    bpy.context.view_layer.objects.active = a
    a.select_set(True)
    bpy.ops.object.mode_set(mode='POSE')
    a.data.bones.active = a.data.bones[names[0]]
    with bpy.context.temp_override(window=win(), area=area, region=_region):
        bpy.ops.pose.select_all(action='DESELECT')
    redraw()


@step
def s_scene_undo():
    mark_undo(1)
    mark_undo(7)
    check(f"Pose mode, nothing selected ({bpy.context.mode}, {selected_joints()})",
          bpy.context.mode == 'POSE' and selected_joints() == [])


def box(name, half):
    def press():
        p = tip() - Vector((half, half))
        ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))
        ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y))

    def move1():
        p = tip()
        ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))

    def move2():
        p = tip() + Vector((half, half))
        ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))

    def release():
        p = tip() + Vector((half, half))
        ev('LEFTMOUSE', 'RELEASE', x=int(p.x), y=int(p.y))

    def settle():
        pass                       # the joint rules run from a timer after the box ends
    for i, fn in enumerate((press, move1, move2, release, settle, settle)):
        f = (lambda fn: lambda: fn())(fn)
        f.__name__ = f"s_{name}_{i}"
        step(f)


def ctrl_z(name):
    def press():
        p = tip() + Vector((0, 80))
        ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))
        ev('LEFT_CTRL', 'PRESS', ctrl=True)
        ev('Z', 'PRESS', ctrl=True)
        ev('Z', 'RELEASE', ctrl=True)
        ev('LEFT_CTRL', 'RELEASE')          # or the next drag runs with Ctrl held

    def settle():
        pass                       # a paired step is taken back from a timer
    for i, fn in enumerate((press, settle, settle)):
        f = (lambda fn: lambda: fn())(fn)
        f.__name__ = f"s_{name}_{i}"
        step(f)


box("pose_box", 30)


@step
def s_pose_box_done():
    check(f"Pose mode, nothing selected: a box over a joint picks it ({selected_joints()})",
          selected_joints() == [C["names"][2]])


ctrl_z("pose_undo")


@step
def s_pose_undo_done():
    scene = bpy.context.scene
    check(f"one Ctrl+Z takes the pick back ({selected_joints()}, {bpy.context.mode})",
          selected_joints() == [] and bpy.context.mode == 'POSE')
    check(f"and nothing before it (frame {scene.frame_current})", scene.frame_current == 7)
    bpy.ops.object.mode_set(mode='OBJECT')
    for ob in bpy.context.scene.objects:
        ob.select_set(False)
    bpy.context.view_layer.objects.active = None
    redraw()


@step
def s_object_undo():
    mark_undo(3)
    mark_undo(9)
    check(f"Object Mode, nothing selected ({bpy.context.mode}, {bpy.context.selected_objects})",
          bpy.context.mode == 'OBJECT' and not bpy.context.selected_objects)


box("object_box", 30)


@step
def s_object_box_done():
    check(f"Object Mode, nothing selected: a box over a joint picks it ({bpy.context.mode}, {selected_joints()})",
          selected_joints() == [C["names"][2]])


ctrl_z("object_undo")


@step
def s_object_undo_done():
    scene = bpy.context.scene
    check(f"one Ctrl+Z takes the pick back ({bpy.context.mode}, {selected_joints()}, "
          f"{[o.name for o in bpy.context.selected_objects]})",
          selected_joints() == [] and not bpy.context.selected_objects)
    check(f"and nothing before it (frame {scene.frame_current})", scene.frame_current == 9)


# the same with the Lasso Select tool: Blender's lasso changes nothing either and keeps its path to itself
@step
def s_lasso_tool():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="builtin.select_lasso")
        C["tool"] = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode).idname
    mark_undo(4)
    mark_undo(11)


def lasso(name, r):
    import math
    ring = [(math.cos(2 * math.pi * k / 12) * r, math.sin(2 * math.pi * k / 12) * r) for k in range(13)]

    def at(k):
        p = tip() + Vector(ring[k])
        return int(p.x), int(p.y)

    def press():
        ev('MOUSEMOVE', 'NOTHING', x=at(0)[0], y=at(0)[1])
        ev('LEFTMOUSE', 'PRESS', x=at(0)[0], y=at(0)[1])
    fns = [press]
    for k in range(1, 13):
        fns.append((lambda k: lambda: ev('MOUSEMOVE', 'NOTHING', x=at(k)[0], y=at(k)[1]))(k))
    fns.append(lambda: ev('LEFTMOUSE', 'RELEASE', x=at(12)[0], y=at(12)[1]))
    fns += [lambda: None, lambda: None]
    for i, fn in enumerate(fns):
        f = (lambda fn: lambda: fn())(fn)
        f.__name__ = f"s_{name}_{i}"
        step(f)


lasso("object_lasso", 30)


@step
def s_object_lasso_done():
    check(f"Object Mode, nothing selected: a lasso around a joint picks it ({C['tool']}, {selected_joints()})",
          selected_joints() == [C["names"][2]])


ctrl_z("lasso_undo")


@step
def s_lasso_undo_done():
    check(f"one Ctrl+Z takes the lasso pick back ({selected_joints()}, frame {bpy.context.scene.frame_current})",
          selected_joints() == [] and bpy.context.scene.frame_current == 11)


run()
