"""Issue #145: a received Rigify rig to the engine, and Maya pick walk over its controls.

Audit 0.5.0 (⑤-15): Export Selection of a Rigify human wrote 278 joints
(160 deforming + their non-deforming ancestors) that Maya named DEFFBXASC045spine...; Export All added the hidden
metarig (437). ⑤-12 (:321): Up from forearm_fk.L twice reached tweak_spine.003 instead of shoulder.L.
"""

import os
from importlib import import_module

import addon_utils
import bpy
from mathutils import Vector

import kit

units = import_module(kit.MODULE + ".operators.units")
fbx_rig = import_module(kit.MODULE + ".operators.fbx_rig")
fbx_skeleton = import_module(kit.MODULE + ".operators.fbx_skeleton")
joints = import_module(kit.MODULE + ".operators.joints")
controllers = import_module(kit.MODULE + ".operators.controllers")

OUT = os.path.join(os.environ.get("ALLSET_TEST_OUT", bpy.app.tempdir), "step236")
_RIG = {}


def check(ok, msg):
    if not ok:
        raise AssertionError(msg)


def _rigify():
    """The Rigify human (bundled add-on, Generate), a skinned box on two DEF bones, keys on frames 1 / 12."""
    if _RIG.get("rig") is not None and _RIG["rig"].name in bpy.data.objects:
        return _RIG["rig"], _RIG["meta"], _RIG["body"]
    addon_utils.enable("rigify", default_set=True)
    sc = bpy.context.scene
    sc.unit_settings.system, sc.unit_settings.length_unit = 'METRIC', 'CENTIMETERS'
    sc.frame_start, sc.frame_end = 1, 12
    sc.frame_set(1)
    bpy.ops.object.armature_human_metarig_add()
    meta = bpy.context.object
    bpy.ops.pose.rigify_generate()
    rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o is not meta)
    meta.hide_set(True)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0.0, 0.0, 1.2))
    body = bpy.context.active_object
    body.name = "body.001"
    for name in ("DEF-spine.003", "DEF-upper_arm.L"):
        vg = body.vertex_groups.new(name=name)
        vg.add(list(range(len(body.data.vertices))), 0.5, 'REPLACE')
    md = body.modifiers.new("Armature", 'ARMATURE')
    md.object = rig
    body.parent = rig
    for f, (w, z) in ((1, (1.0, 0.0)), (12, (0.8, 0.6))):
        pb = rig.pose.bones["upper_arm_fk.L"]
        pb.rotation_quaternion = (w, 0.0, 0.0, z)
        pb.keyframe_insert("rotation_quaternion", frame=f)
        pb = rig.pose.bones["torso"]
        # down, not up: a stretched IK leg scales its DEF bones unevenly and FBX can't hold the sheared foot (Blender's
        # own writer misses the toe by 0.96 cm there, with or without the kit's fix)
        pb.location = (0.0, 0.0, -0.1 * (f - 1) / 11)
        pb.keyframe_insert("location", frame=f)
    _RIG.update(rig=rig, meta=meta, body=body)
    return rig, meta, body


def _select(*obs):
    for o in bpy.context.view_layer.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[0]


def _export(name, selection=True, **opts):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    op = bpy.ops.allset.file_export_selection if selection else bpy.ops.allset.file_export_all
    res = op('EXEC_DEFAULT', filepath=path, export_type='FBX', **opts)
    assert res == {'FINISHED'}, res
    tree, _v = fbx_rig.load(path)
    return fbx_rig.Index(tree)


def _maya(p, k):
    return Vector((p.x, p.z, -p.y)) / k


def test_export_selection_writes_the_deforming_joints_with_maya_names():
    rig, _meta, body = _rigify()
    _select(rig, body)
    index = _export("rig_selection.fbx")
    limbs = index.limbs()
    names = sorted(fbx_rig.name_of(m) for m in limbs.values())
    deform = [b.name for b in rig.data.bones if b.use_deform]
    check(len(names) == len(deform) == 160, f"joints {len(names)} (deforming {len(deform)})")
    bad = [n for n in names if not n.replace("_", "a").isalnum()]
    check(not bad, f"Maya-unsafe names {bad[:5]}")
    check("DEF_spine_001" in names and "DEF_upper_arm_L" in names, names[:8])
    roots = [fbx_rig.name_of(m) for uid, m in limbs.items() if index.parent.get(uid) not in limbs]
    check(roots == ["DEF_spine"], f"roots {roots}")
    parent = {fbx_rig.name_of(m): fbx_rig.name_of(limbs[index.parent[uid]]) for uid, m in limbs.items()
              if index.parent.get(uid) in limbs}
    for child, want in (("DEF_upper_arm_L", "DEF_shoulder_L"), ("DEF_shoulder_L", "DEF_spine_003"),
                        ("DEF_thigh_L", "DEF_spine"), ("DEF_f_index_01_L", "DEF_palm_01_L"),
                        ("DEF_forearm_L", "DEF_upper_arm_L_001")):
        check(parent.get(child) == want, f"{child} parent {parent.get(child)} (want {want})")
    meshes = [fbx_rig.name_of(m) for m in index.models.values() if m.props[2] == b"Mesh"]
    check(meshes == ["body_001"], meshes)
    clusters = [d for d in index.objects.find(b"Deformer") if d.props[2] == b"Cluster"]
    weighted = [d for d in clusters if d.first(b"Indexes") is not None and len(d.first(b"Indexes").props[0])]
    check(len(clusters) == 160 and len(weighted) == 2, f"clusters {len(clusters)}, weighted {len(weighted)}")
    # the joints are where Blender's writer put them (its own file, options off: the re-parenting maths) and where
    # Blender's DEF bones are (Maya cm, Y up) wherever the writer itself is exact, at the file's first and last key
    _select(rig, body)
    plain = _export("rig_plain_ref.fbx", deform_only=False, maya_names=False)
    k = units.maya_unit(bpy.context.scene)
    sc = bpy.context.scene
    worst, where, worst_bl, n_bl = 0.0, None, 0.0, 0
    for key, frame in ((0, 1), (11, 12)):
        sc.frame_set(frame)
        bpy.context.view_layer.update()
        file_w = fbx_rig.world_matrices(index, sample=key)
        ref_w = fbx_rig.world_matrices(plain, sample=key)
        for name in deform:
            got = file_w[fbx_skeleton.maya_name(name)].to_translation()
            ref = ref_w[name].to_translation()
            if (got - ref).length > worst:
                worst, where = (got - ref).length, (frame, name)
            want = _maya(rig.matrix_world @ rig.pose.bones[name].head, k)
            if (ref - want).length < 1e-4:
                n_bl += 1
                worst_bl = max(worst_bl, (got - want).length)
    sc.frame_set(1)
    check(worst < 1e-4, f"joints moved by the re-parenting: {worst:.2e} cm at {where}")
    check(worst_bl < 1e-4 and n_bl > 250, f"vs Blender's bones: {worst_bl:.2e} cm over {n_bl}")
    print(f"rigify: 160 joints, root DEF_spine, vs writer {worst:.2e} cm, vs Blender {worst_bl:.2e} cm ({n_bl})")


def test_export_all_leaves_the_metarig_out():
    rig, meta, body = _rigify()
    index = _export("rig_all.fbx", selection=False)
    names = [fbx_rig.name_of(m) for m in index.limbs().values()]
    check(len(names) == 160, f"Export All wrote {len(names)} joints")
    check(meta.name in bpy.context.scene.objects, "the metarig is back in the scene")


def test_options_off_keep_blender_s_skeleton_and_names():
    rig, _meta, body = _rigify()
    _select(rig, body)
    index = _export("rig_plain.fbx", deform_only=False, maya_names=False)
    names = [fbx_rig.name_of(m) for m in index.limbs().values()]
    check(len(names) == 278, f"{len(names)} joints (Blender's deform-only writes 278)")
    check("DEF-spine.001" in names, "Blender names kept")


def test_maya_name_rule():
    for a, b in (("DEF-spine.001", "DEF_spine_001"), ("pCube1", "pCube1"), ("3d", "_3d"), ("a b", "a_b")):
        check(fbx_skeleton.maya_name(a) == b, (a, fbx_skeleton.maya_name(a)))


def test_pick_walk_follows_the_rigify_controls():
    rig, _meta, _body = _rigify()
    bones = rig.data.bones

    def up(name, n=1):
        b = bones[name]
        for _i in range(n):
            b = joints.walk_bone(b, "UP", True)
        return b.name
    check(up("forearm_fk.L") == "upper_arm_fk.L", up("forearm_fk.L"))
    check(up("forearm_fk.L", 2) == "shoulder.L", up("forearm_fk.L", 2))
    check(up("upper_arm_ik.L") == "shoulder.L", up("upper_arm_ik.L"))
    # Rigify hangs ORG-spine.003 on its tweak / FK controls (no ORG parent with a control twin): shown-ancestor rule
    check(up("tweak_spine.003") == "spine_fk.003", up("tweak_spine.003"))
    check(up("f_index.02.L") == "f_index.01.L", up("f_index.02.L"))
    # torso hangs on the hidden MCH-torso.parent root: it is a top controller (Up stays, like Maya)
    check(up("chest") == "torso" and up("torso") == "torso", (up("chest"), up("torso")))
    down = joints.walk_bone(bones["upper_arm_fk.L"], "DOWN", True).name
    check(down == "forearm_fk.L", down)
    side = joints.walk_bone(bones["upper_arm_fk.L"], "RIGHT", True).name
    check(side != "upper_arm_fk.L" and joints.rigify_parents(rig.data)[side] == "shoulder.L", side)
    # the preference off = Blender's own hierarchy (a hidden MCH bone)
    check(joints.walk_bone(bones["upper_arm_fk.L"], "UP", False).name == "MCH-upper_arm_parent.L", "DAG")
    # a kit Parent Controller wins over the computed one
    try:
        controllers.parent_controllers(bones["torso"], [bones["upper_arm_fk.L"]])
        check(joints.walk_bone(bones["upper_arm_fk.L"], "UP", True).name == "torso", "kit tags win")
    finally:
        for b in bones:
            for key in (joints.CONTROLLER, joints.CONTROLLER_PARENT):
                if key in b:
                    del b[key]
