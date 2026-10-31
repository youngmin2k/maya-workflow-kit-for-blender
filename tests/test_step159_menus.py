"""Skeleton / Skin / Deform menu items reach the kit commands (Joint Labelling, IK enable, deformer weights),
Reset Default Weights gives the bind weights back, greyed items carry their notices."""

from importlib import import_module

import bpy
from mathutils import Vector

import kit

menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")
joints = import_module(kit.MODULE + ".operators.joints")


def test_menu_paths_mapped():
    m = menu_map.MAP
    base = "Skeleton/Joint Labelling/Add Joint Labels/Label "
    assert m[base + "Left"] == ("allset.joint_label", {"side": "LEFT"})
    assert m[base + "Shoulder"] == ("allset.joint_label", {"type": "ARM"})       # Maya's limb label
    assert m[base + "Shoulder#2"] == ("allset.joint_label", {"type": "SHOULDER"})
    assert m[base + "Hip"] == ("allset.joint_label", {"type": "LEG"})
    assert m[base + "Foot Thumb"] == ("allset.joint_label", {"type": "FOOT_THUMB"})
    for label in ("Left", "Right", "Center", "None", "Root", "Toe", "Finger"):
        op, props = m[base + label]
        for k, v in props.items():
            rna = bpy.ops.allset.joint_label.get_rna_type().properties[k]
            assert v in rna.enum_items.keys(), (label, v)
    assert m["Skeleton/Disable Selected IK Handles"] == ("allset.ik_handle_enable", {"enable": False})
    assert m["Deform/Export Weights..."] == "allset.export_deformer_weights"
    assert m["Deform/Import Weights..."] == "allset.import_deformer_weights"
    assert m["Skin/Reset Default Weights"] == "allset.reset_skin_weights"
    path = "Skin/Interactive Bind Skin"
    assert path not in m and notices.greyed_notice(path)[0] == "Bind Skin / Paint Skin Weights"
    assert m["Skin/Export Weight Maps..."] == "allset.export_weight_maps"


def test_reset_default_weights():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'METERS', 1.0
    arm = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 0, 4), (0, 0, 2), (0, 0, 0)):
        parent = joints.add_joint(arm, Vector(p), parent, length=0.5)
    joints.finish(bpy.context, arm, ["joint1", "joint2", "joint3"])
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 2))
    mesh = bpy.context.active_object
    for o in bpy.context.scene.objects:
        o.select_set(o in (arm, mesh))
    bpy.context.view_layer.objects.active = mesh
    assert bpy.ops.allset.bind_skin() == {'FINISHED'}

    def weights():
        return [sorted((mesh.vertex_groups[g.group].name, round(g.weight, 6)) for g in v.groups if g.weight > 0)
                for v in mesh.data.vertices]

    before = weights()
    for vg in mesh.vertex_groups:
        vg.add(list(range(len(mesh.data.vertices))), 0.33, 'REPLACE')
    assert weights() != before
    assert bpy.ops.allset.reset_skin_weights() == {'FINISHED'}
    assert weights() == before
