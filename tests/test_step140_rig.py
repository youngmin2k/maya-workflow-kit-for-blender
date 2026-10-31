"""Maya option windows / tool settings for Skeleton, Skin, Blend Shape and Aim / Pole Vector /
Scale constraints (operators/option_windows_rig.py). Labels and defaults follow Maya's
option windows."""

import json
import math
from importlib import import_module

import bpy
from mathutils import Vector

import kit

ow = import_module(kit.MODULE + ".operators.option_windows")
rig = import_module(kit.MODULE + ".operators.option_windows_rig")
skin = import_module(kit.MODULE + ".operators.skin")
joints = import_module(kit.MODULE + ".operators.joints")
cb = import_module(kit.MODULE + ".ui.channel_box")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
menu_data = import_module(kit.MODULE + ".ui.menu_data")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
compat = import_module(kit.MODULE + ".compat")

PATHS = {
    "joint_tool": ("Skeleton/Create Joints",), "ik_handle_tool": ("Skeleton/Create IK Handle",),
    "ik_spline_tool": ("Skeleton/Create IK Spline Handle",), "bind_skin_maya": ("Skin/Bind Skin",),
    "unbind_skin": ("Skin/Unbind Skin",), "copy_skin_weights": ("Skin/Copy Skin Weights",),
    "paint_skin_weights": ("Skin/Paint Skin Weights",), "blend_shape": ("Deform/Blend Shape",),
    "aim_constraint": ("Constrain/Aim",), "pole_vector": ("Constrain/Pole Vector",),
    "scale_constraint": ("Constrain/Scale",),
}


def _w(key):
    return ow._BY_KEY[key]


def _fields(key):
    return [(f.name, f.label, f.default) for f in _w(key).fields]


def _run(key, **values):
    res = ow.run(_w(key), bpy.context, values)
    assert not isinstance(res, str), (key, res)
    return res


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.armatures, bpy.data.meshes):
        for d in list(coll):
            coll.remove(d)
    for w in rig.WINDOWS:
        ow.store(w.key, None)


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def _chain(points=((0, 0, 0), (0, 0.3, 1), (0, 0, 2))):
    ob = joints.new_skeleton(bpy.context)
    parent = None
    for p in points:
        parent = joints.add_joint(ob, Vector(p), parent, length=0.5)
    joints.finish(bpy.context, ob, ["joint1", "joint2", "joint3"])
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def _cylinder(x=0.0):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.2, depth=2.6, location=(x, 0, 1.3), vertices=12)
    cyl = bpy.context.active_object
    with bpy.context.temp_override(object=cyl, active_object=cyl):
        cyl.modifiers.new("sub", 'SUBSURF').levels = 1
        bpy.ops.object.modifier_apply(modifier="sub")
    return cyl


def _bound():
    _clear()
    arm = _chain()
    cyl = _cylinder()
    _select(arm, cyl)
    _run("bind_skin_maya")
    return arm, cyl


def _empty(name, loc):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    return ob


# --- the windows ------------------------------------------------------------------------------------

def test_paths_open_these_windows():
    for key, paths in PATHS.items():
        assert key in ow._BY_KEY, key
        rna = getattr(bpy.ops.allset, "opt_" + key).get_rna_type()
        for f in _w(key).fields:
            assert f.name in rna.properties, (key, f.name)
        for p in paths:
            assert p in menu_data.OPTION_BOXES and p in menu_map.MAP, p
            assert ow.find_path(p).key == key, (p, ow.find_path(p).key)
            assert menu_sets.option_kind(p) == "window", p


def test_titles_buttons_fields_defaults_are_maya():
    # Tool Settings tools: title = the tool name, button = start the tool
    assert (_w("joint_tool").title, _w("ik_handle_tool").title, _w("ik_spline_tool").title,
            _w("paint_skin_weights").title) == ("Joint Tool", "IK Handle Tool", "IK Spline Handle Tool",
                                                "Paint Skin Weights Tool")
    # Joint Tool: secondary Y, world orientation +Y, Create IK handle off
    # the Orientation section adds Orient Joint to World (off) and Auto orient secondary axis (on)
    assert _fields("joint_tool")[:6] == [
        ("orient_world", "", False),
        ("secondary_axis", "Secondary Axis:", "Y"), ("secondary_world", "Secondary Axis World Orientation:", "Y"),
        ("secondary_sign", "", "+"), ("auto_secondary", "", True), ("create_ik", "", False)]
    # IK Handle Tool: Rotate-Plane solver, Solver enable on, Weight 1
    assert _fields("ik_handle_tool") == [("solver", "Current solver:", "Rotate-Plane Solver"),
                                         ("solver_enable", "", True), ("weight", "Weight:", 1.0)]
    assert _fields("ik_spline_tool") == [("root_on_curve", "", True), ("parent_curve", "", True),
                                         ("snap_curve", "", False), ("create_curve", "", True),
                                         ("spans", "Number of spans:", "1"),
                                         ("twist_type", "Twist type:", "Linear")]
    # Bind Skin, button "Apply and Close"
    w = _w("bind_skin_maya")
    assert (w.title, w.action) == ("Bind Skin Options", "Apply and Close")
    assert _fields("bind_skin_maya") == [
        ("bind_to", "Bind to:", "Joint hierarchy"), ("bind_method", "Bind method:", "Closest distance"),
        ("skinning", "Skinning method:", "Classic linear"),
        ("normalize", "Normalize weights:", "Interactive"), ("max_influences", "Max influences:", 5),
        # Maintain max influences on, Dropoff rate 4.0
        ("maintain_max", "", True), ("dropoff", "Dropoff rate:", 4.0),
        ("remove_unused", "", True), ("colorize", "", True)]
    # Detach Skin
    w = _w("unbind_skin")
    assert (w.title, w.action) == ("Detach Skin Options", "Detach")
    assert _fields("unbind_skin") == [("history", "History:", "Delete history"),
                                      ("remove_colors", "Coloring:", True)]
    # Copy Skin Weights
    assert (_w("copy_skin_weights").title, _w("copy_skin_weights").action) == ("Copy Skin Weights Options", "Copy")
    assert [d for _n, _l, d in _fields("copy_skin_weights")] == ["Closest point on surface", "Closest joint", "None",
                                                               "None", False]
    # Paint Skin Weights Tool
    assert dict((n, d) for n, _l, d in _fields("paint_skin_weights")) == {
        "operation": "Replace", "profile": "Soft", "normalize": "Interactive", "opacity": 1.0, "value": 1.0,
        "radius": 1.0, "screen_projection": False, "show_wireframe": True, "xray_joints": True}
    # Blend Shape
    assert (_w("blend_shape").title, _w("blend_shape").action) == ("Blend Shape Options", "Create")
    assert _fields("blend_shape") == [("node_name", "BlendShape node:", ""), ("origin", "Origin:", "Local"),
                                      ("check_topology", "", True), ("delete_targets", "", False)]
    # Aim
    assert _fields("aim_constraint") == [
        ("aim_vector", "Aim vector:", (1.0, 0.0, 0.0)), ("up_vector", "Up vector:", (0.0, 1.0, 0.0)),
        ("world_up_type", "World up type:", "Vector"), ("world_up_vector", "World up vector:", (0.0, 1.0, 0.0)),
        ("world_up_object", "World up object:", ""), ("weight", "Weight:", 1.0)]   # + World up object
    # Pole Vector: only Weight 1 (:187-188); Scale: Maintain offset off, Offset 1 1 1, All, Weight 1 (:190-192)
    assert _fields("pole_vector") == [("weight", "Weight:", 1.0)]
    assert [(n, d) for n, _l, d in _fields("scale_constraint")] == [
        ("maintain_offset", False), ("offset", (1.0, 1.0, 1.0)), ("all", True), ("x", False), ("y", False),
        ("z", False), ("weight", 1.0)]
    assert _w("pole_vector").title == "Pole Vector Constraint Options"


# --- they run the Maya way ------------------------------------------------------------------------

def _aim_scene():
    _clear()
    target = _empty("locator1", (3.0, 2.0, 1.0))
    cube = _empty("locator2", (0.0, 0.0, 0.0))
    _select(target, cube)
    return target, cube


def test_aim_points_local_x_with_y_up():
    target, cube = _aim_scene()
    _run("aim_constraint")
    con = cube.constraints[-1]
    assert con.type == 'TRACK_TO' and con.track_axis == 'TRACK_X' and con.up_axis == 'UP_Z'
    bpy.context.view_layer.update()
    m = cube.matrix_world.to_3x3()
    to_target = (target.location - cube.location).normalized()
    assert (m.col[0].normalized() - to_target).length < 1e-5, "local +X (Maya aim vector) at the target"
    up = m.col[2].normalized()                       # Maya Y = Blender local Z
    assert abs(up.dot(to_target)) < 1e-5 and up.z > 0.5, tuple(up)
    # the plain menu click aims the same (allset.constrain TRACK_TO)
    target, cube = _aim_scene()
    assert bpy.ops.allset.constrain(type='TRACK_TO') == {'FINISHED'}
    con = cube.constraints[-1]
    assert (con.track_axis, con.up_axis, con.use_target_z) == ('TRACK_X', 'UP_Z', False)


def test_aim_options():
    target, cube = _aim_scene()
    _run("aim_constraint", world_up_type="None", weight=0.5)
    con = cube.constraints[-1]
    assert con.type == 'DAMPED_TRACK' and con.track_axis == 'TRACK_X' and con.target == target
    assert abs(con.influence - 0.5) < 1e-6 and len(cube.constraints) == 1
    target, cube = _aim_scene()
    _run("aim_constraint", aim_vector=(0.0, 0.0, 1.0), up_vector=(1.0, 0.0, 0.0))
    con = cube.constraints[-1]
    assert (con.track_axis, con.up_axis) == ('TRACK_NEGATIVE_Y', 'UP_X'), (con.track_axis, con.up_axis)  # Maya Z = -Y
    target, cube = _aim_scene()
    # #168: any world up vector (a hidden empty's Z axis = the vector, Track To uses its Z)
    res = ow.run(_w("aim_constraint"), bpy.context, {"world_up_vector": (1.0, 0.0, 0.0)})
    con = cube.constraints[-1]
    assert res == {'FINISHED'} and con.type == 'TRACK_TO' and con.use_target_z and con.target is not target, res


def test_scale_constraint_offset_and_axes():
    _clear()
    target = _empty("locator1", (0, 0, 0))
    target.scale = (2.0, 3.0, 4.0)
    ob = _empty("locator2", (1, 0, 0))
    _select(target, ob)
    _run("scale_constraint")
    bpy.context.view_layer.update()
    assert (ob.matrix_world.to_scale() - Vector((2, 3, 4))).length < 1e-5
    ob.constraints.clear()
    _run("scale_constraint", offset=(1.0, 2.0, 0.5), all=False, x=True, y=True)
    bpy.context.view_layer.update()
    con = ob.constraints[-1]
    assert (con.use_x, con.use_y, con.use_z) == (True, False, True)          # Maya Y = Blender Z
    # x: 2 x 1, Blender y (Maya Z, not constrained): own 0.5, Blender z (Maya Y): 4 x 2
    assert (ob.matrix_world.to_scale() - Vector((2, 0.5, 8))).length < 1e-5, tuple(ob.matrix_world.to_scale())


def _ik_scene():
    _clear()
    arm = _chain()
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name in ("joint1", "joint3"))
    arm.data.bones.active = arm.data.bones["joint3"]
    return arm


def test_ik_handle_tool_solver():
    arm = _ik_scene()
    _run("ik_handle_tool")
    con = arm.pose.bones["joint2"].constraints["ikHandle1"]
    assert con.type == 'IK' and not con.use_rotation and not con.mute and con.weight == 1.0     # RP
    arm = _ik_scene()
    _run("ik_handle_tool", solver="Single-Chain Solver", solver_enable=False, weight=0.5)
    con = arm.pose.bones["joint2"].constraints[-1]
    assert con.use_rotation and con.mute and abs(con.weight - 0.5) < 1e-6                       # SC


def test_pole_vector_weight():
    arm = _ik_scene()
    _run("ik_handle_tool")
    handle = bpy.data.objects["ikHandle1"]
    pole = _empty("locator1", (0, 2, 1))
    _select(pole, handle)
    res = ow.run(_w("pole_vector"), bpy.context, {"weight": 0.5})
    assert isinstance(res, str) and "weight" in res.lower(), res
    con = arm.pose.bones["joint2"].constraints["ikHandle1"]
    # an RP handle has a pole vector like Maya (a hidden helper) from the start
    helper = handle["allset_pole_helper"]
    assert con.pole_target == helper and handle.get("allset_pole_object") is None
    _run("pole_vector")
    assert handle.get("allset_pole_object") == pole and con.pole_target == helper    # pv = target - start joint


def test_joint_tool_options_reach_the_bones():
    _clear()
    pts = json.dumps([(0, 0, 0), (2, 0, 0), (4, 0, 2)])
    # window values -> tool properties
    props = rig.joint_tool_props({**_w("joint_tool").defaults(), "secondary_world": "Z", "create_ik": True})
    assert props["secondary_world"] == "Z" and props["create_ik"] and props["ik_solver"] == "RP"
    assert bpy.ops.allset.joint_tool(points=pts, secondary_world="Z", secondary_sign="+") == {'FINISHED'}
    arm = bpy.context.active_object
    # secondary Y (= bone Z) faces Maya +Z = Blender -Y
    for b in arm.data.bones[:2]:
        z = (arm.matrix_world.to_3x3() @ b.matrix_local.to_3x3()).col[2]
        assert z.dot(Vector((0, -1, 0))) > 0.99, (b.name, tuple(z))
    rolled = [bpy.types.Bone.AxisRollFromMatrix(b.matrix_local.to_3x3())[1] for b in arm.data.bones]
    assert any(abs(r) > 0.1 for r in rolled), rolled
    _clear()
    assert bpy.ops.allset.joint_tool(points=pts, secondary_axis="NONE", secondary_world="Z") == {'FINISHED'}
    arm = bpy.context.active_object
    # Secondary Axis None = Maya's orient without a secondary world axis (traditional: Z = child x parent
    # direction): joint2 bends in the Maya XY plane... here the chain is in Blender's XZ plane
    j2 = arm.data.bones[1]
    a = (j2.tail_local - j2.head_local).normalized()
    b = (arm.data.bones[0].head_local - j2.head_local).normalized()
    maya_z = (arm.matrix_world.to_3x3() @ j2.matrix_local.to_3x3()).col[0]      # bone X = Maya Z
    assert (maya_z - a.cross(b).normalized()).length < 1e-5, ("None = traditional orient", tuple(maya_z))
    _clear()
    assert bpy.ops.allset.joint_tool(points=pts) == {'FINISHED'}
    arm = bpy.context.active_object
    # Maya 2025+ default = auto orient secondary axis: Maya Y (bone Z) = the bend normal of this chain
    # (it lies in Blender's XZ plane, so the normal is +-Blender Y; n . up = 0 is Maya's tie, the kit keeps n)
    zy = arm.data.bones[1].matrix_local.to_3x3().col[2]
    assert abs(zy.y) > 1 - 1e-5, tuple(zy)
    assert bpy.ops.allset.joint_tool(points=pts, auto_secondary=False) == {'FINISHED'}   # aos off: projected up
    arm = bpy.context.active_object
    zy = arm.data.bones[1].matrix_local.to_3x3().col[2]
    y = arm.data.bones[1].matrix_local.to_3x3().col[1]
    want = (Vector((0, 0, 1)) - y * y.z).normalized()
    assert (zy - want).length < 1e-5, (tuple(zy), tuple(want))
    # Create IK handle: an IK from the first to the last joint
    _clear()
    assert bpy.ops.allset.joint_tool(points=pts, create_ik=True, ik_solver="SC") == {'FINISHED'}
    h = bpy.data.objects.get("ikHandle1")
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    con = arm.pose.bones["joint2"].constraints["ikHandle1"]
    assert h is not None and con.target == h and con.chain_count == 2 and con.use_rotation
    res = ow.run(_w("joint_tool"), bpy.context, {"secondary_axis": "X"})
    assert isinstance(res, str) and "primary" in res, res


def test_ik_spline_root_on_curve():
    arm = _ik_scene()
    _run("ik_spline_tool", root_on_curve=False)
    con = next(c for pb in arm.pose.bones for c in pb.constraints if c.type == 'SPLINE_IK')
    assert con.use_chain_offset


def test_bind_skin_options():
    arm, cyl = _bound()
    assert skin.armature_modifier(cyl).object == arm and not skin.armature_modifier(cyl).use_deform_preserve_volume
    assert cyl[skin.NORMALIZE_PROP] == "INTERACTIVE"
    assert all(b.color.palette != 'DEFAULT' for b in arm.data.bones), "Colorize skeleton on"
    bpy.ops.allset.unbind_skin()
    for b in arm.data.bones:
        b.color.palette = 'DEFAULT'
    _select(arm, cyl)
    _run("bind_skin_maya", skinning="Dual quaternion", normalize="Post", colorize=False, max_influences=1)
    assert skin.armature_modifier(cyl).use_deform_preserve_volume and cyl[skin.NORMALIZE_PROP] == "POST"
    assert all(b.color.palette == 'DEFAULT' for b in arm.data.bones)
    assert all(len([g for g in v.groups if g.weight > 0]) <= 1 for v in cyl.data.vertices)


def test_unbind_keep_and_delete_history():
    arm, cyl = _bound()
    _select(cyl)
    _run("unbind_skin", history="Keep history")
    assert skin.armature_modifier(cyl) is None
    assert sorted(vg.name for vg in cyl.vertex_groups) == ["joint1", "joint2", "joint3"], "weights kept"
    assert all(b.color.palette == 'DEFAULT' for b in arm.data.bones), "joint colours removed"
    arm, cyl = _bound()
    _select(cyl)
    _run("unbind_skin", remove_colors=False)
    assert skin.armature_modifier(cyl) is None and not cyl.vertex_groups
    assert all(b.color.palette != 'DEFAULT' for b in arm.data.bones)


def test_copy_skin_weights_with_options():
    arm, cyl = _bound()
    other = _cylinder()
    _select(cyl, other)
    _run("copy_skin_weights", surface="Closest component", normalize=True)
    assert skin.armature_modifier(other).object == arm
    assert sorted(vg.name for vg in other.vertex_groups) == ["joint1", "joint2", "joint3"]
    for v in other.data.vertices:
        total = sum(g.weight for g in v.groups)
        assert total == 0 or abs(total - 1.0) < 1e-4, total


def test_paint_skin_weights_tool_settings():
    arm, cyl = _bound()
    _select(cyl)
    _run("paint_skin_weights", value=0.25, opacity=0.5, radius=3.0, normalize="Off", xray_joints=False)
    assert bpy.context.mode == 'PAINT_WEIGHT'
    ups = compat.unified_paint_settings(bpy.context.tool_settings)       # 5.0+: per paint mode (#90)
    assert abs(ups.weight - 0.25) < 1e-6 and abs(ups.strength - 0.5) < 1e-6
    assert abs(compat.unprojected_radius(ups) - 3.0) < 1e-6          # Maya cm x maya_unit() (1 in a factory m scene)
    assert not bpy.context.tool_settings.use_auto_normalize and not arm.show_in_front
    bpy.ops.object.mode_set(mode='OBJECT')


def _mesh(name, offset=(0, 0, 0), z=0.0):
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=offset)
    ob = bpy.context.active_object
    ob.name = name
    for v in ob.data.vertices:
        v.co.z += z
    return ob


def test_blend_shape_options():
    _clear()
    target = _mesh("target", offset=(5, 0, 0), z=1.0)
    base = _mesh("base")
    _select(target, base)
    _run("blend_shape")
    key = base.data.shape_keys
    assert key.name == "blendShape1" and [k.name for k in key.key_blocks] == ["Basis", "target"]
    assert abs(key.key_blocks["target"].data[0].co.z - 1.0) < 1e-6 and abs(key.key_blocks["target"].data[0].co.x) < 1
    assert "target" in bpy.data.objects
    # World origin + name + delete targets
    _clear()
    target = _mesh("target", offset=(5, 0, 0), z=1.0)
    base = _mesh("base")
    _select(target, base)
    _run("blend_shape", node_name="faceShapes", origin="World", delete_targets=True)
    key = base.data.shape_keys
    co = key.key_blocks["target"].data[0].co
    assert key.name == "faceShapes" and abs(co.x - (5 - 0.5)) < 1e-6 and abs(co.z - 1.0) < 1e-6, tuple(co)
    assert "target" not in bpy.data.objects
    # Check topology: same vertex count, other faces -> refused; off -> taken
    _clear()
    target = _mesh("target")
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(target.data)
    bmesh.ops.delete(bm, geom=list(bm.faces), context='FACES_ONLY')
    bm.to_mesh(target.data)
    bm.free()
    base = _mesh("base")
    _select(target, base)
    res = ow.run(_w("blend_shape"), bpy.context, {})
    assert base.data.shape_keys is None, res
    _run("blend_shape", check_topology=False)
    assert base.data.shape_keys is not None


def test_saved_values_used_by_plain_menu_click():
    from importlib import import_module as im
    modal = im(kit.MODULE + ".marking.modal")
    target, cube = _aim_scene()
    ow.store("aim_constraint", {"world_up_type": "None"})
    modal.run_action(bpy.context, menu_map.MAP["Constrain/Aim"], path="Constrain/Aim")
    assert cube.constraints[-1].type == 'DAMPED_TRACK'
    ow.store("aim_constraint", None)
    assert math.isclose(_w("aim_constraint").defaults()["weight"], 1.0)
