"""Lane B (Issue #137): Pose Space Deformation — Create Pose Interpolator, poses,
corrective shapes (operators/pose_space_227.py) and the Pose Editor window (ui/pose_editor.py).

Expected (``pose_one`` / ``pose_two`` / ``pose_one_gaussian``):
arm shoulder (0,0,0) -> elbow (4,0,-1) -> wrist (8,0,0), ``joint -oj xyz
-sao yup``, interpolator on the elbow, pose ``elbowBent`` at elbow rotate (0, 0, -90); the rows are the pose's output
weight at elbow rotations (Maya XYZ Euler degrees). The kit's weight = Maya's Linear swing ratio inside the neutral ->
pose arc and ignores twist about the driver axis (asserted at 1e-4); outside the arc, swing in another plane and two
poses are Maya RBF values the per-pose driver doesn't reproduce (printed as deviations)."""

import math
from importlib import import_module

import bpy
from mathutils import Matrix, Vector

import kit

ps = import_module(kit.MODULE + ".operators.pose_space_227")
pose_editor = import_module(kit.MODULE + ".ui.pose_editor")
marked_window = import_module(kit.MODULE + ".ui.marked_window")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
compat = import_module(kit.MODULE + ".compat")


# Maya joint coordinates (a, b, c) on X / Y / Z -> bone coordinates: joint X / Y / Z = bone Y / Z / X
P = Matrix(((0, 0, 1), (1, 0, 0), (0, 1, 0)))


def _maya(p):
    """Maya world (x, y, z) -> Blender (x, -z, y) (Maya Y up)."""
    return Vector((p[0], -p[2], p[1]))


def _fresh():
    bpy.ops.wm.read_homefile(use_empty=True)
    wm = bpy.context.window_manager
    wm.allset_pe_current = ""
    wm.allset_pe_pose = ""


def _arm():
    """Maya's arm as an armature: bones shoulder / elbow, bone Z = Maya joint Y (world up, sao yup)."""
    arm = bpy.data.armatures.new("skeleton1")
    ob = bpy.data.objects.new("skeleton1", arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    s = arm.edit_bones.new("shoulder")
    s.head, s.tail = _maya((0, 0, 0)), _maya((4, 0, -1))
    e = arm.edit_bones.new("elbow")
    e.head, e.tail = _maya((4, 0, -1)), _maya((8, 0, 0))
    e.parent, e.use_connect = s, True
    for b in (s, e):
        b.align_roll(Vector((0, 0, 1)))
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def _skinned_mesh(arm):
    """A line of vertices along the arm, x < 4 on the shoulder, else the elbow, with an Armature modifier."""
    me = bpy.data.meshes.new("armMeshShape")
    pts = [(x, 0.0, 0.0) for x in range(0, 9)]
    me.from_pydata(pts, [(i, i + 1) for i in range(len(pts) - 1)], [])
    ob = bpy.data.objects.new("armMesh", me)
    bpy.context.scene.collection.objects.link(ob)
    gs, ge = ob.vertex_groups.new(name="shoulder"), ob.vertex_groups.new(name="elbow")
    for i, (x, _y, _z) in enumerate(pts):
        (gs if x < 4 else ge).add([i], 1.0, 'REPLACE')
    m = ob.modifiers.new("skinCluster1", 'ARMATURE')
    m.object = arm
    return ob


def _rotate(arm, rot):
    """Elbow rotate (rx, ry, rz) in Maya degrees, rotate order xyz (X first)."""
    rx, ry, rz = (math.radians(v) for v in rot)
    r = (Matrix.Rotation(rz, 3, 'Z') @ Matrix.Rotation(ry, 3, 'Y') @ Matrix.Rotation(rx, 3, 'X'))
    pb = arm.pose.bones["elbow"]
    pb.rotation_mode = 'QUATERNION'
    pb.rotation_quaternion = (P @ r @ P.transposed()).to_quaternion()
    bpy.context.view_layer.update()


def _pose_mode(arm, bone="elbow"):
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    arm.data.bones.active = arm.data.bones[bone]


def _setup(poses=(("elbowBent", (0, 0, -90)),), axis='X'):
    _fresh()
    arm = _arm()
    mesh = _skinned_mesh(arm)
    _pose_mode(arm)
    assert bpy.ops.allset.pose_interpolator_create(twist_axis=axis) == {'FINISHED'}
    interp = bpy.data.objects["elbow_poseInterpolator"]
    for name, rot in poses:
        _rotate(arm, rot)
        assert bpy.ops.allset.pose_add(interpolator=interp.name, name=name) == {'FINISHED'}
    _rotate(arm, (0, 0, 0))
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm, mesh, interp


def _drivers(id_):
    ad = id_.animation_data
    return list(ad.drivers) if ad is not None else []


def test_registered_and_mapped():
    for op in ("pose_interpolator_create", "pose_editor", "pose_pick", "pose_add", "pose_add_shape", "pose_edit",
               "pose_go", "pose_delete"):
        assert compat.has_op(bpy.ops.allset, op), op
    assert hasattr(bpy.types, "ALLSET_PT_pose_editor")
    assert "POSE_EDITOR" in marked_window.KINDS
    pairs = [frozenset(v) for v in marked_window.KINDS.values()]
    assert len(pairs) == len(set(pairs)), "each marked window kind has its own flag pair"
    m = menu_map.MAP
    assert m["Windows/Animation Editors/Pose Editor"] == ("allset.pose_editor", {})
    assert m["Deform/Pose Space Deformation/Pose Editor"] == ("allset.pose_editor", {})
    assert m["Deform/Pose Space Deformation/Create Pose Interpolator"] == ("allset.pose_interpolator_create", {})


def test_create_names_node_and_neutral():
    arm, _mesh, interp = _setup(poses=())
    assert ps.is_interpolator(interp) and interp.type == 'EMPTY'
    assert ps.driver_of(interp) == (arm, arm.pose.bones["elbow"])
    tip = interp[ps.P_TIP]
    bpy.context.view_layer.update()
    tail = arm.matrix_world @ arm.pose.bones["elbow"].tail
    assert tip.name not in bpy.context.scene.objects, "helpers stay out of the scene"
    # an Empty parented to a bone (identity parent inverse, zero location) sits at the bone's tail
    assert (ps._tip_world(arm, arm.pose.bones["elbow"], 0) - tail).length < 1e-5
    _pose_mode(arm)
    assert bpy.ops.allset.pose_interpolator_create() == {'FINISHED'}
    assert "elbow_poseInterpolator1" in bpy.data.objects, "Maya's next name"
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = None
    for o in bpy.context.scene.objects:
        o.select_set(False)
    assert bpy.ops.allset.pose_interpolator_create() == {'CANCELLED'}, "no joint selected"


def test_twist_axis_y_ignores_rotation_about_joint_y():
    arm, _mesh, interp = _setup(axis='Y')
    _rotate(arm, (0, 0, -45))
    w0 = ps.weight(interp, "elbowBent")
    _rotate(arm, (0, 45, -45))
    assert abs(ps.weight(interp, "elbowBent") - w0) < 1e-4 and abs(w0 - 0.5) < 1e-4, (w0,)


def test_corrective_shape_follows_the_pose_weight():
    arm, mesh, interp = _setup()
    bpy.context.view_layer.objects.active = mesh
    assert bpy.ops.allset.pose_add_shape(interpolator=interp.name, pose="elbowBent", edit=False) == {'FINISHED'}
    key = mesh.data.shape_keys
    assert key.name.startswith("blendShape") and [k.name for k in key.key_blocks] == ["Basis", "elbowBent"]
    kb = key.key_blocks["elbowBent"]
    for fc in _drivers(key):
        assert fc.driver.is_valid and fc.driver.is_simple_expression, fc.driver.expression
    kb.data[1].co.z += 1.0            # vertex 1 (x 1) sits on the shoulder: the elbow pose doesn't move it
    for rot in ((0, 0, 0), (0, 0, -30), (0, 0, -45), (0, 0, -90), (60, 0, -45)):
        _rotate(arm, rot)
        w = ps.weight(interp, "elbowBent")
        assert abs(kb.value - w) < 1e-6, (rot, kb.value, w)
        dg = bpy.context.evaluated_depsgraph_get()
        ev = mesh.evaluated_get(dg)
        z = ev.data.vertices[1].co.z
        assert abs(z - w) < 1e-4, (rot, z, w)
    assert ps.shapes_of(interp, "elbowBent") == [(mesh, "elbowBent")]


def test_go_to_pose_and_edit_shape():
    arm, mesh, interp = _setup()
    assert bpy.ops.allset.pose_go(interpolator=interp.name, pose="elbowBent") == {'FINISHED'}
    assert abs(ps.weight(interp, "elbowBent") - 1.0) < 1e-4
    assert bpy.ops.allset.pose_go(interpolator=interp.name, pose="neutral") == {'FINISHED'}
    assert abs(ps.weight(interp, "elbowBent")) < 1e-4
    bpy.context.view_layer.objects.active = mesh
    assert bpy.ops.allset.pose_add_shape(interpolator=interp.name, pose="elbowBent") == {'FINISHED'}
    assert mesh.mode == 'EDIT' and mesh.active_shape_key.name == "elbowBent", "Add Shape goes into Edit"
    assert abs(ps.weight(interp, "elbowBent") - 1.0) < 1e-4, "sculpted in the pose"
    mod = mesh.modifiers["skinCluster1"]
    assert mod.show_in_editmode and mod.show_on_cage
    assert ps.editing(interp, "elbowBent") == (mesh, "elbowBent")
    assert bpy.ops.allset.pose_edit(interpolator=interp.name, pose="elbowBent") == {'FINISHED'}
    assert mesh.mode == 'OBJECT' and ps.editing(interp, "elbowBent") is None


def test_add_pose_rejects_neutral_and_taken_names():
    arm, _mesh, interp = _setup()
    _pose_mode(arm)
    _rotate(arm, (0, 0, 0))
    assert bpy.ops.allset.pose_add(interpolator=interp.name, name="same") == {'CANCELLED'}
    _rotate(arm, (0, 0, -30))
    assert bpy.ops.allset.pose_add(interpolator=interp.name, name="elbowBent") == {'CANCELLED'}
    assert ps.next_pose_name(interp) == "pose1"
    bpy.ops.object.mode_set(mode='OBJECT')


def test_delete_cleans_up():
    arm, mesh, interp = _setup(poses=(("elbowBent", (0, 0, -90)), ("elbowUp", (0, 60, 0))))
    bpy.context.view_layer.objects.active = mesh
    assert bpy.ops.allset.pose_add_shape(interpolator=interp.name, pose="elbowBent", edit=False) == {'FINISHED'}
    helpers = bpy.data.collections[ps.HELPERS]
    assert len(helpers.objects) == 3          # tip + one per pose
    assert bpy.ops.allset.pose_delete(interpolator=interp.name, pose="elbowUp") == {'FINISHED'}
    assert ps.poses(interp) == ["elbowBent"] and len(helpers.objects) == 2 and "elbowUp" not in interp
    assert bpy.ops.allset.pose_delete(interpolator=interp.name, pose="") == {'FINISHED'}
    assert "elbow_poseInterpolator" not in bpy.data.objects
    assert ps.HELPERS not in bpy.data.collections
    assert not any(o.get(ps.H_OWNER) for o in bpy.data.objects)
    key = mesh.data.shape_keys
    assert "elbowBent" in key.key_blocks, "the corrective target stays (Maya keeps the blendShape target)"
    assert not _drivers(key) and key.key_blocks["elbowBent"].value == 0.0


def test_editor_draws_rows():
    arm, mesh, interp = _setup()
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.allset.pose_add_shape(interpolator=interp.name, pose="elbowBent", edit=False)
    _rotate(arm, (0, 0, -45))
    log = []
    pose_editor.draw_toolbar(_Layout(log), bpy.context)
    pose_editor.draw_lists(_Layout(log), bpy.context)
    pose_editor.draw_settings(_Layout(log), bpy.context)
    texts = [kw.get("text") for name, _a, kw in log if name in ("operator", "label")]
    for t in ("elbow_poseInterpolator", "neutral", "elbowBent", "0.500", "Edit", "Linear", "Gaussian",
              "Add Pose", "Go to Pose"):
        assert t in texts, (t, texts)
    from importlib import import_module as im
    notices = im(kit.MODULE + ".ui.notices")
    assert "Pose Editor/Interpolation/Gaussian" in notices.PANEL_NOTICES


def test_unregister_clean():
    kit.disable()
    assert not hasattr(bpy.types.WindowManager, "allset_pe_current")
    assert not hasattr(bpy.types, "ALLSET_PT_pose_editor")
    kit.enable()
    assert hasattr(bpy.types.WindowManager, "allset_pe_current")


class _Layout:
    """Accepts every UILayout call (headless: no real layout) and records them."""

    def __init__(self, log):
        object.__setattr__(self, "_log", log)

    def __getattr__(self, name):
        def call(*args, **kw):
            self._log.append((name, args, kw))
            return _Layout(self._log)
        return call

    def __setattr__(self, name, value):
        pass
