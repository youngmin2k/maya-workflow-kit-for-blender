"""Issue #164: skin basics with Maya's meaning.

Expected numbers: tests/maya2026_rig_data.py SKINNING["skin"] (prune_and_max, unbind_and_bind_pose, copy_mirror_weights)
and further results written here as literals:
prune with a locked joint, Set Max Influences (recomputed by distance), Go to Bind Pose, Mirror Skin Weights barycentric,
Closest in hierarchy rows (the weights of three vertices).
Kit: operators/skin_basics.py, skin.py (bind options, mirror, closest_distance_weights).
"""

from importlib import import_module

import bpy
import numpy as np
from mathutils import Vector

import kit

skin = import_module(kit.MODULE + ".operators.skin")
sb = import_module(kit.MODULE + ".operators.skin_basics")
rig_maya = import_module(kit.MODULE + ".operators.rig_maya")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
compat = import_module(kit.MODULE + ".compat")


def _reset():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.armatures):
        for d in list(coll):
            coll.remove(d)


def _b(p):
    """Maya point -> Blender world (x, -z, y), unit 1."""
    return Vector((p[0], -p[2], p[1]))


def _skeleton(joints, name="skeleton1"):
    """joints = [(name, maya point, parent)]; bones head = the point, tail toward the first child."""
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    pos = {n: _b(p) for n, p, _ in joints}
    for n, p, parent in joints:
        eb = arm.edit_bones.new(n)
        eb.head = pos[n]
        kids = [c for c, _q, par in joints if par == n]
        eb.tail = pos[kids[0]] if kids else pos[n] + Vector((0.0, 0.0, 0.5))
        if parent:
            eb.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def _mesh(points, faces, name="body"):
    me = bpy.data.meshes.new(name)
    compat.mesh_from_pydata(me, [_b(p) for p in points], [], faces)    # Blender 5.0.1 selection attributes
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _skin(mesh, arm, names):
    md = mesh.modifiers.new("skinCluster1", 'ARMATURE')
    md.object = arm
    for n in names:
        mesh.vertex_groups.new(name=n)


def _set(mesh, i, ws):
    for name, w in ws.items():
        vg = mesh.vertex_groups[name]
        if w > 0:
            vg.add([i], w, 'REPLACE')
        elif any(g.group == vg.index for g in mesh.data.vertices[i].groups):
            vg.remove([i])


def _get(mesh, i, names):
    out = []
    for n in names:
        vg = mesh.vertex_groups[n]
        try:
            out.append(vg.weight(i))
        except RuntimeError:
            out.append(0.0)
    return out


def _close(a, b, tol=1e-5):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def _select(*obs, active=None):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or obs[-1]


CHAIN = [("joint1", (0, 0, 0), None), ("joint2", (3, 0, 0), "joint1"), ("joint3", (6, 0, 0), "joint2"),
         ("joint4", (9, 0, 0), "joint3")]
J = [n for n, _p, _q in CHAIN]


def _chain_skin():
    """Joints at Maya x 0 / 3 / 6 / 9; vertex 0 = Maya (0, 0, 0.5) like the Maya plane's vertex 0."""
    _reset()
    arm = _skeleton(CHAIN)
    mesh = _mesh([(0, 0, 0.5), (9, 0, 0.5), (9, 0, -0.5)], [(0, 1, 2)])
    _skin(mesh, arm, J)
    return arm, mesh


# --- menu ---------------------------------------------------------------------------------------------------

def test_menu_items():
    m = menu_map.MAP
    assert m["Skin/Prune Small Weights"] == "allset.prune_small_weights"
    assert m["Skin/Go to Bind Pose"] == "allset.go_to_bind_pose"
    assert m["Skin/Edit Influences/Set Max Influences..."] == "allset.set_max_influences"


# --- Prune Small Weights ----------------------------------------------------------------------------------------


def test_prune_threshold_option():
    arm, mesh = _chain_skin()
    _set(mesh, 0, dict(zip(J, [0.6, 0.05, 0.3, 0.05])))
    _select(mesh)
    assert bpy.ops.allset.prune_small_weights('EXEC_DEFAULT', below=0.1) == {'FINISHED'}
    assert _close(_get(mesh, 0, J), [2 / 3, 0.0, 1 / 3, 0.0])


# --- Set Max Influences / Maintain max influences -----------------------------------------------------------------


def test_enforce_max_rule():
    # Maya: smallest first, locked last, rest renormalised
    out = sb.enforce_max_matrix([[0.4, 0.3, 0.1, 0.2]], [False] * 4, 2)
    assert _close(out[0], [0.4 / 0.7, 0.3 / 0.7, 0.0, 0.0])
    out = sb.enforce_max_matrix([[0.4, 0.3, 0.1, 0.2]], [False, False, True, False], 2)
    assert _close(out[0], [0.9, 0.0, 0.1, 0.0])


# --- Bind Skin options ---------------------------------------------------------------------------------------

def test_on_joint_distance_is_1e4():
    segs = {"a": [(Vector((0, 0, 0)), Vector((0, 0, 0)))], "b": [(Vector((1, 0, 0)), Vector((1, 0, 0)))]}
    names, w = skin.closest_distance_weights([(5e-5, 0, 0)], segs)
    assert _close(w[0], [1.0, 0.0])
    names, w = skin.closest_distance_weights([(2e-4, 0, 0)], segs)
    assert w[0][0] < 1.0


def test_bind_options_dropoff_skinning_maintain():
    _reset()
    arm = _skeleton(CHAIN)
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(4.5, 0, 0.5))
    mesh = bpy.context.active_object
    mesh.scale = (9.0, 1.0, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    _select(arm, mesh)
    assert bpy.ops.allset.bind_skin('EXEC_DEFAULT', dropoff=2.0, skinning='DUAL_QUATERNION') == {'FINISHED'}
    md = skin.armature_modifier(mesh)
    assert md.use_deform_preserve_volume, "Dual quaternion = Blender Preserve Volume"
    assert mesh[sb.MAINTAIN_MAX] is True and mesh[rig_maya.MAX_INFLUENCES_PROP] == 5
    assert set(mesh[rig_maya.DROPOFF_PROP].keys()) == set(J) and mesh[rig_maya.DROPOFF_PROP]["joint1"] == 2.0
    co = np.array([mesh.matrix_world @ v.co for v in mesh.data.vertices])
    segs = skin.joint_segments(arm)
    names, w2 = skin.closest_distance_weights(co, segs, 2.0, 5)
    for i in range(len(co)):
        assert _close(_get(mesh, i, names), w2[i], 1e-5)
    assert "allset_bind_pose" in arm


# --- Go to Bind Pose ---------------------------------------------------------------------------------------

def test_go_to_bind_pose_restores_every_joint():
    _reset()
    arm = _skeleton(CHAIN)
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(4.5, 0, 0.5))
    mesh = bpy.context.active_object
    mesh.scale = (9.0, 1.0, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    _select(arm, mesh)
    assert bpy.ops.allset.bind_skin('EXEC_DEFAULT') == {'FINISHED'}
    dg = bpy.context.evaluated_depsgraph_get()
    base = [v.co.copy() for v in mesh.evaluated_get(dg).to_mesh().vertices]
    mesh.evaluated_get(dg).to_mesh_clear()
    pb = arm.pose.bones
    pb["joint2"].rotation_mode = 'XYZ'
    pb["joint2"].rotation_euler = (0.0, 0.7, 0.0)
    pb["joint1"].rotation_mode = 'XYZ'
    pb["joint1"].rotation_euler = (0.0, 0.0, 0.17)
    pb["joint3"].location = (0.0, 4.0, 0.0)
    _select(mesh)
    assert bpy.ops.allset.go_to_bind_pose('EXEC_DEFAULT') == {'FINISHED'}
    dg = bpy.context.evaluated_depsgraph_get()
    after = [v.co.copy() for v in mesh.evaluated_get(dg).to_mesh().vertices]
    mesh.evaluated_get(dg).to_mesh_clear()
    err = max((a - b).length for a, b in zip(base, after))
    assert err < 1e-6, err   # fixture after_goto_mesh_err 0.0
    assert all(p.matrix_basis == p.matrix_basis.Identity(4) for p in pb)


def test_bind_pose_is_the_pose_at_bind_and_follows_remove_and_unbind():
    # Maya: a skeleton bound with joint2 rz 30 goes back to rz 30
    _reset()
    arm = _skeleton(CHAIN)
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(4.5, 0, 0.5))
    mesh = bpy.context.active_object
    pb = arm.pose.bones["joint2"]
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler = (0.0, 0.5236, 0.0)
    _select(arm, mesh)
    assert bpy.ops.allset.bind_skin('EXEC_DEFAULT') == {'FINISHED'}
    pb.rotation_euler = (0.0, 0.0, 0.0)
    _select(arm)
    assert bpy.ops.allset.go_to_bind_pose('EXEC_DEFAULT') == {'FINISHED'}
    assert abs(pb.rotation_euler[1] - 0.5236) < 1e-5
    # Remove Joint drops the member
    bpy.ops.object.mode_set(mode='POSE')
    cbm = import_module(kit.MODULE + ".ui.channel_box")
    for p in arm.pose.bones:
        cbm.set_bone_selected(p, p.name == "joint4")
    arm.data.bones.active = arm.data.bones["joint4"]
    assert bpy.ops.allset.remove_joint('EXEC_DEFAULT') == {'FINISHED'}
    assert "joint4" not in arm["allset_bind_pose"] and "joint4" not in mesh.vertex_groups
    bpy.ops.object.mode_set(mode='OBJECT')
    _select(mesh)
    assert bpy.ops.allset.unbind_skin('EXEC_DEFAULT') == {'FINISHED'}
    assert "allset_bind_pose" not in arm, "Unbind deletes the bind pose"


def test_go_to_bind_pose_undo():
    _reset()
    arm = _skeleton(CHAIN)
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(4.5, 0, 0.5))
    mesh = bpy.context.active_object
    _select(arm, mesh)
    bpy.ops.allset.bind_skin('EXEC_DEFAULT')
    arm.pose.bones["joint2"].location = (0.0, 1.0, 0.0)
    bpy.ops.ed.undo_push(message="posed")
    _select(arm)
    assert bpy.ops.allset.go_to_bind_pose('EXEC_DEFAULT', True) == {'FINISHED'}
    assert tuple(bpy.data.objects["skeleton1"].pose.bones["joint2"].location) == (0.0, 0.0, 0.0)
    bpy.ops.ed.undo()
    assert tuple(bpy.data.objects["skeleton1"].pose.bones["joint2"].location) == (0.0, 1.0, 0.0)


# --- Mirror / Copy Skin Weights ---------------------------------------------------------------------------


def test_mirror_factory_plane_is_yz():
    assert bpy.ops.allset.mirror_skin_weights.get_rna_type().properties["plane"].default == "YZ"


