"""#276: a value changed while Auto Key is off is not keyed when Auto Key is turned on and only the selection changes
(joints picked in Pose mode); the next real change of that channel is keyed, like Maya."""

import os
import sys
from importlib import import_module

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, setup, step, view3d, win  # noqa: E402

C = {}
PATH = 'pose.bones["{}"].location'


def mod(name):
    return import_module(MODULE + name)


def arm():
    return bpy.data.objects[C["arm"]]


def pb():
    return arm().pose.bones[C["bone"]]


def keys():
    fc = mod(".compat").id_fcurve_collection(arm()).find(PATH.format(C["bone"]), index=0)
    return len(fc.keyframe_points)


def ov():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


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
    for x in (0.0, 8.0):
        parent = joints.add_joint(a, Vector((x, 0.0, 4.0)) * k, parent, length=1.0 * k)
        names.append(parent)
    joints.finish(bpy.context, a, names)
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    C["arm"], C["bone"], C["k"] = a.name, names[1], k
    for ob in bpy.context.scene.objects:
        ob.select_set(False)
    bpy.context.view_layer.objects.active = a
    a.select_set(True)
    with ov():
        bpy.ops.object.mode_set(mode='POSE')
    scene = bpy.context.scene
    scene.allset_auto_key = False
    scene.frame_set(1)
    a.keyframe_insert(PATH.format(C["bone"]), index=0, frame=1)
    scene.frame_set(10)
    pb().location.x = 2.0 * k                # changed with Auto Key off: no key


@step
def s_auto_key_on():
    bpy.context.scene.allset_auto_key = True


def select(name, action):
    def run_it():
        with ov():
            bpy.ops.pose.select_all(action=action)
    run_it.__name__ = "s_" + name
    step(run_it)
    for i in range(3):
        f = (lambda: None)
        f.__name__ = f"s_{name}_wait{i}"
        step(f)


select("select_all", 'SELECT')
select("deselect_all", 'DESELECT')


@step
def s_selection_only():
    check(f"picking joints keys nothing ({keys()} key(s), x {pb().location.x / C['k']:.3f})", keys() == 1)
    pb().location.x = 3.0 * C["k"]          # a real change with Auto Key on


@step
def s_wait():
    pass


@step
def s_real_change():
    check(f"a real change is keyed ({keys()} key(s))", keys() == 2)
    bpy.context.scene.allset_auto_key = False


run()
