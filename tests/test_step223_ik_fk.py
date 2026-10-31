"""Issue #133: Maya IK / FK switching on kit IK handles — Ik Blend on the handle drives
the IK constraint's Influence (Channel Box "Ik Blend"), poses at Ik Blend 1 / 0 equal Maya's, Set IK/FK Key / Enable
IK Solver / Move IK to FK follow Maya 2026 (RP arm shoulder (0,0,0)
-> elbow (4,0,-1) -> wrist (8,0,0), handle moved to (6,0,2))."""

import math
from importlib import import_module

import bpy
from mathutils import Matrix, Vector

import kit

compat = import_module(kit.MODULE + ".compat")
skin = import_module(kit.MODULE + ".operators.skin")
ik_fk = import_module(kit.MODULE + ".operators.ik_fk")
channel_box = import_module(kit.MODULE + ".ui.channel_box")
menu_map = import_module(kit.MODULE + ".ui.menu_map")

PTS = {"shoulder": (0, 0, 0), "elbow": (4, 0, -1), "wrist": (8, 0, 0)}
JO_Z = (math.sin(math.radians(14.036243467926484)), 0.0, math.cos(math.radians(14.036243467926484)))


def bl(p):
    return Vector((p[0], -p[2], p[1]))        # Maya (x, y, z) -> Blender (x, -z, y), 1 Maya unit = 1 m here


def _arm():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    sc = bpy.context.scene
    sc.frame_set(1)
    arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
    sc.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for name, tail in (("shoulder", PTS["elbow"]), ("elbow", PTS["wrist"]), ("wrist", (9, 0, 0))):
        eb = arm.data.edit_bones.new(name)
        eb.head, eb.tail = bl(PTS[name]), bl(tail)
        if prev is not None:
            eb.parent, eb.use_connect = prev, True
        prev = eb
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
    handle = skin.create_ik(bpy.context, arm, ("shoulder", 'HEAD'), ("wrist", 'HEAD'))
    con = arm.pose.bones["elbow"].constraints[0]
    return arm, handle, con


def _update():
    bpy.context.view_layer.update()


def _world(arm, name):
    return arm.matrix_world @ arm.pose.bones[name].head


def _rotate_shoulder(arm, deg):
    """Maya shoulder.rotateZ += deg: about the shoulder's joint Z (jointOrient (0, 14.04, 0)) in world."""
    pb = arm.pose.bones["shoulder"]
    rot = Matrix.Rotation(math.radians(deg), 4, bl(JO_Z).normalized())
    pb.matrix = rot @ pb.matrix
    _update()


def _select(*obs):
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    for ob in obs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1] if obs else None


def test_menu_items_mapped():
    for label, op in (("Set IK/FK Key", "allset.ik_fk_key"), ("Move IK to FK", "allset.move_ik_to_fk")):
        assert menu_map.MAP[f"Key/IK/FK Keys/{label}"] == op
    # a Maya check item drawn as the WindowManager property that runs allset.ik_solver_toggle
    assert menu_map.MAP["Key/IK/FK Keys/Enable IK Solver"] == ("prop", "window_manager.allset_ik_solver", {})


def test_undo_restores_blend():
    arm, handle, con = _arm()
    bpy.ops.ed.undo_push(message="before")
    _select(handle)
    ik_fk._STATE["on"] = True
    bpy.ops.allset.ik_solver_toggle('EXEC_DEFAULT', True)
    assert bpy.data.objects[handle.name]["ikBlend"] == 0.0
    bpy.ops.ed.undo()
    assert bpy.data.objects["ikHandle1"]["ikBlend"] == 1.0
