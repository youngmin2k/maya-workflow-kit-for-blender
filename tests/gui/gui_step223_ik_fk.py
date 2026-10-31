"""Issue #133: in a real UI: an IK handle made with the kit shows Maya's "Ik Blend" row in the Channel Box,
and Key > IK/FK Keys > Set IK/FK Key / Enable IK Solver / Move IK to FK run from the Maya menu path (menu_item, one
undo step each). A screenshot of the Channel Box with the handle selected goes to the shots folder."""

import os
import sys
from importlib import import_module

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, setup, win, load_maya_layout, screenshot  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                                           "tmp", "gui_step223")
C = {}


def area3d():
    toolbox = import_module(MODULE + ".ui.toolbox")
    return max((a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)),
               key=lambda a: a.width * a.height)


def override():
    a = area3d()
    return bpy.context.temp_override(window=win(), area=a, region=next(r for r in a.regions if r.type == 'WINDOW'))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    units = import_module(MODULE + ".operators.units")
    skin = import_module(MODULE + ".operators.skin")
    k = units.maya_unit()
    pts = [Vector((0, 0, 0)), Vector((4, 1, 0)), Vector((8, 0, 0))]        # Maya arm in Blender axes
    with override():
        arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
        bpy.context.scene.collection.objects.link(arm)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')
        prev = None
        for name, a, b in (("shoulder", pts[0], pts[1]), ("elbow", pts[1], pts[2]),
                           ("wrist", pts[2], pts[2] + Vector((1, 0, 0)))):
            eb = arm.data.edit_bones.new(name)
            eb.head, eb.tail = a * k, b * k
            if prev is not None:
                eb.parent, eb.use_connect = prev, True
            prev = eb
        bpy.ops.object.mode_set(mode='OBJECT')
        handle = skin.create_ik(bpy.context, arm, ("shoulder", 'HEAD'), ("wrist", 'HEAD'))
        handle.location = Vector((6, 0, 2)) * k
    C["arm"], C["handle"] = arm.name, handle.name
    channel_box = import_module(MODULE + ".ui.channel_box")
    rows = channel_box.wanted_rows(handle)
    check(f"Channel Box rows of the handle hold Ik Blend ({rows})", ("CUSTOM", "ikBlend", "", 0) in rows)
    redraw()


@step
def s_wait():
    redraw()


@step
def s_shot():
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, "ik_blend_channel_box.png")
    screenshot(path)
    check(f"screenshot of the Channel Box with the IK handle: {path}", os.path.exists(path))


@step
def s_menu_key():
    handle = bpy.data.objects[C["handle"]]
    with override():
        bpy.ops.allset.menu_item(item="Key/IK/FK Keys/Set IK/FK Key")
    compat = import_module(MODULE + ".compat")
    paths = {fc.data_path for fc in compat.id_fcurves(handle)}
    check(f"menu Set IK/FK Key keyed the handle ({sorted(paths)})", '["ikBlend"]' in paths and "location" in paths)


@step
def s_menu_solver():
    ik_fk = import_module(MODULE + ".operators.ik_fk")
    ik_fk._STATE["on"] = True
    handle = bpy.data.objects[C["handle"]]
    with override():
        bpy.ops.allset.menu_item(item="Key/IK/FK Keys/Enable IK Solver")
    check(f"menu Enable IK Solver switched to FK (Ik Blend {handle['ikBlend']})", handle["ikBlend"] == 0.0)
    with override():
        bpy.ops.ed.undo()
    handle = bpy.data.objects[C["handle"]]
    check(f"one undo brings Ik Blend back ({handle['ikBlend']})", handle["ikBlend"] == 1.0)


@step
def s_menu_move():
    handle = bpy.data.objects[C["handle"]]
    with override():
        bpy.ops.allset.menu_item(item="Key/IK/FK Keys/Move IK to FK")
    arm = bpy.data.objects[C["arm"]]
    wrist = arm.matrix_world @ arm.pose.bones["wrist"].head
    check(f"menu Move IK to FK: handle at the wrist ({tuple(handle.matrix_world.translation)} / {tuple(wrist)})",
          (handle.matrix_world.translation - wrist).length < 1e-4)


run()
