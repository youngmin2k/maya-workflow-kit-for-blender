"""IK Handle Tool, Pole Vector, Bind / Unbind Skin, Paint Skin Weights (+ influence list), Copy / Mirror Skin
Weights, Copy / Paste Vertex Weights. GUI: tests/gui/gui_step58_skin.py."""

import types
from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

skin = import_module(kit.MODULE + ".operators.skin")
joints = import_module(kit.MODULE + ".operators.joints")
cb = import_module(kit.MODULE + ".ui.channel_box")
paint_weights = import_module(kit.MODULE + ".ui.paint_weights")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)


def _chain(points=((0, 0, 0), (0, 0.3, 1), (0, 0, 2))):
    """skeleton1 joint1 > joint2 > joint3 (a bent chain), object mode."""
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
        cyl.modifiers.new("sub", 'SUBSURF').levels = 2
        bpy.ops.object.modifier_apply(modifier="sub")
    return cyl


def test_ik_chain_maths():
    _clear()
    arm = _chain()
    ik = skin.ik_chain(arm, ("joint1", 'HEAD'), ("joint3", 'HEAD'))
    assert ik is not None and ik[0].name == "joint2" and ik[1] == 2, ik
    ik = skin.ik_chain(arm, ("joint1", 'HEAD'), ("joint3", 'TAIL'))      # the chain's end tip
    assert ik[0].name == "joint3" and ik[1] == 3
    assert skin.ik_chain(arm, ("joint3", 'HEAD'), ("joint1", 'HEAD')) is None, "end above start"
    assert skin.ik_chain(arm, ("joint1", 'HEAD'), ("joint1", 'HEAD')) is None, "a root has no incoming bone"
    names = [(n, e) for n, e, _p in skin.joints_of(arm)]
    assert names == [("joint1", 'HEAD'), ("joint2", 'HEAD'), ("joint3", 'HEAD'), ("joint3", 'TAIL')], names


def test_ik_handle_from_two_selected_joints():
    _clear()
    arm = _chain()
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name in ("joint1", "joint3"))
    arm.data.bones.active = arm.data.bones["joint3"]
    assert skin.selected_pair(bpy.context)[1:] == (("joint1", 'HEAD'), ("joint3", 'HEAD'))
    assert bpy.ops.allset.ik_handle() == {'FINISHED'}
    h = bpy.data.objects["ikHandle1"]
    con = arm.pose.bones["joint2"].constraints["ikHandle1"]
    assert con.type == 'IK' and con.target == h and con.chain_count == 2 and con.use_tail
    assert (h.location - Vector((0, 0, 2))).length < 1e-5, tuple(h.location)
    assert bpy.context.mode == 'OBJECT' and bpy.context.active_object == h and h.select_get()
    assert abs(h.empty_display_size - 1.0) < 1e-9          # maya_unit() in a factory m scene
    # moving the handle bends the chain
    h.location = (0.5, 0, 1.6)
    bpy.context.view_layer.update()
    assert (arm.pose.bones["joint2"].tail - Vector((0.5, 0, 1.6))).length < 0.05


def test_pick_joint_on_screen():
    _clear()
    arm = _chain()
    # front orthographic: world (x, z) -> region pixels
    from mathutils import Matrix
    view = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, -10), (0, 0, 0, 1)))
    proj = Matrix(((0.2, 0, 0, 0), (0, 0.4, 0, 0), (0, 0, -0.01, 0), (0, 0, 0, 1)))
    rv3d = types.SimpleNamespace(perspective_matrix=proj @ view)
    region = types.SimpleNamespace(width=200, height=100)
    # joint3 head at world (0, 0, 2): x = 100, y = 50 + 2 * 0.4 * 50 = 90
    hit = skin.pick_joint(region, rv3d, [arm], (101, 89), 10)
    assert hit is not None and hit[1] == ("joint3", 'HEAD'), hit
    assert skin.pick_joint(region, rv3d, [arm], (180, 10), 10) is None


def test_pole_vector_keeps_the_pose():
    _clear()
    arm = _chain()
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name in ("joint1", "joint3"))
    arm.data.bones.active = arm.data.bones["joint3"]
    bpy.ops.allset.ik_handle()
    handle = bpy.data.objects["ikHandle1"]
    bpy.context.view_layer.update()
    before = arm.pose.bones["joint2"].head.copy()
    pole = bpy.data.objects.new("locator1", None)
    bpy.context.scene.collection.objects.link(pole)
    pole.location = (0, 2, 1)                               # in front of the knee (the chain bends to +y)
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    pole.select_set(True)
    handle.select_set(True)
    bpy.context.view_layer.objects.active = handle
    assert bpy.ops.allset.pole_vector() == {'FINISHED'}
    con = arm.pose.bones["joint2"].constraints["ikHandle1"]
    # Maya's pole vector = target - start joint drives the handle's pole helper
    assert handle.get("allset_pole_object") == pole and con.pole_target == handle["allset_pole_helper"]
    bpy.context.view_layer.update()
    after = arm.pose.bones["joint2"].head
    assert (after - before).length < 0.02, ("the knee didn't jump", tuple(before), tuple(after))


def test_bind_skin_any_order_no_parenting():
    _clear()
    arm = _chain()
    cyl = _cylinder()
    for ob in bpy.context.view_layer.objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = cyl            # Maya habit: joints first, mesh last (mesh active)
    assert bpy.ops.allset.bind_skin() == {'FINISHED'}
    assert cyl.parent is None, "Maya keeps the skin out of the joint hierarchy"
    mod = skin.armature_modifier(cyl)
    assert mod is not None and mod.object == arm
    assert sorted(vg.name for vg in skin.influences(cyl)) == ["joint1", "joint2", "joint3"]
    top = max(cyl.data.vertices, key=lambda v: v.co.z)
    assert any(cyl.vertex_groups[g.group].name == "joint3" and g.weight > 0.3 for g in top.groups)
    # Max Influences 1: one joint per vertex
    bpy.ops.allset.unbind_skin()
    assert skin.armature_modifier(cyl) is None and not skin.influences(cyl)
    arm.select_set(True)
    bpy.ops.allset.bind_skin(max_influences=1)
    assert all(len([g for g in v.groups if g.weight > 0]) <= 1 for v in cyl.data.vertices)


def test_bind_selected_joints_only():
    _clear()
    arm = _chain()
    cyl = _cylinder()
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    cyl.select_set(True)
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name in ("joint1", "joint2"))
    assert bpy.ops.allset.bind_skin(bind_to='SELECTED') == {'FINISHED'}
    assert sorted(vg.name for vg in skin.influences(cyl)) == ["joint1", "joint2"]


def _bound():
    _clear()
    arm = _chain()
    cyl = _cylinder()
    arm.select_set(True)
    cyl.select_set(True)
    bpy.context.view_layer.objects.active = cyl
    bpy.ops.allset.bind_skin()
    return arm, cyl


def test_paint_skin_weights_mode_and_panel():
    arm, cyl = _bound()
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    cyl.select_set(True)
    bpy.context.view_layer.objects.active = cyl
    assert bpy.ops.allset.paint_skin_weights() == {'FINISHED'}
    assert bpy.context.mode == 'PAINT_WEIGHT' and arm.mode == 'POSE', "the skeleton is posable while painting"
    assert cyl.vertex_groups.active is not None
    assert paint_weights.active(bpy.context)
    cyl.vertex_groups.new(name="not_a_joint")
    flags, _order = paint_weights.influence_filter(cyl, 1)
    shown = [vg.name for vg, f in zip(cyl.vertex_groups, flags) if f]
    assert sorted(shown) == ["joint1", "joint2", "joint3"], shown
    assert bpy.ops.allset.paint_skin_weights() == {'FINISHED'}     # again = leave the tool
    assert bpy.context.mode == 'OBJECT'


def test_copy_skin_weights_to_another_mesh():
    arm, cyl = _bound()
    other = _cylinder(x=0.0)
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    cyl.select_set(True)
    other.select_set(True)
    bpy.context.view_layer.objects.active = other          # Maya: source, then destination
    assert bpy.ops.allset.copy_skin_weights() == {'FINISHED'}
    assert skin.armature_modifier(other).object == arm
    assert sorted(vg.name for vg in other.vertex_groups) == ["joint1", "joint2", "joint3"]
    top = max(other.data.vertices, key=lambda v: v.co.z)
    assert any(other.vertex_groups[g.group].name == "joint3" and g.weight > 0.3 for g in top.groups)


def test_mirror_skin_weights_pairs_mirrored_joints():
    _clear()
    arm = _chain(((1, 0, 0), (1, 0, 1), (1, 0, 2)))
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    joints.mirror(arm, ["joint1"], "YZ")                   # joint4..6 at x = -1
    bpy.ops.object.mode_set(mode='OBJECT')
    assert skin.mirror_group_names(arm, 0)["joint2"] == "joint5"
    bpy.ops.mesh.primitive_plane_add(size=4)
    plane = bpy.context.active_object
    mod = plane.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    g2, g5 = plane.vertex_groups.new(name="joint2"), plane.vertex_groups.new(name="joint5")
    pos = [v.index for v in plane.data.vertices if v.co.x > 0]
    neg = [v.index for v in plane.data.vertices if v.co.x < 0]
    g2.add(pos, 0.8, 'REPLACE')
    g2.add(neg, 0.1, 'REPLACE')                            # the -x side is wrong before the mirror
    assert bpy.ops.allset.mirror_skin_weights() == {'FINISHED'}
    for i in neg:
        ws = {plane.vertex_groups[g.group].name: g.weight for g in plane.data.vertices[i].groups}
        assert ws == {"joint5": 0.8} or abs(ws.get("joint5", 0) - 0.8) < 1e-6 and "joint2" not in ws, ws
    for i in pos:
        ws = {plane.vertex_groups[g.group].name: g.weight for g in plane.data.vertices[i].groups}
        assert abs(ws["joint2"] - 0.8) < 1e-6, "the source side stays"


def test_copy_paste_vertex_weights():
    arm, cyl = _bound()
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    cyl.select_set(True)
    bpy.context.view_layer.objects.active = cyl
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(cyl.data)
    bm.verts.ensure_lookup_table()
    top = max(bm.verts, key=lambda v: v.co.z)
    low = min(bm.verts, key=lambda v: v.co.z)
    for v in bm.verts:
        v.select = v is top
    bm.select_history.clear()
    bm.select_history.add(top)
    bmesh.update_edit_mesh(cyl.data)
    assert bpy.ops.allset.copy_vertex_weights() == {'FINISHED'}
    for v in bm.verts:
        v.select = v is low
    bmesh.update_edit_mesh(cyl.data)
    assert bpy.ops.allset.paste_vertex_weights() == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    ws = lambda v: {cyl.vertex_groups[g.group].name: round(g.weight, 5) for g in v.groups if g.weight > 0}
    verts = cyl.data.vertices
    hi = max(verts, key=lambda v: v.co.z)
    lo = min(verts, key=lambda v: v.co.z)
    assert ws(lo) == ws(hi) and ws(hi), (ws(lo), ws(hi))


def test_menus_and_shelf():
    m = menu_map.MAP
    assert m["Skeleton/Create IK Handle"] == "allset.ik_handle"
    assert m["Constrain/Pole Vector"] == "allset.pole_vector"
    for path, op in (("Skin/Bind Skin", "bind_skin"), ("Skin/Unbind Skin", "unbind_skin"),
                     ("Skin/Paint Skin Weights", "paint_skin_weights"), ("Skin/Mirror Skin Weights", "mirror_skin_weights"),
                     ("Skin/Copy Skin Weights", "copy_skin_weights"), ("Skin/Copy Vertex Weights", "copy_vertex_weights"),
                     ("Skin/Paste Vertex Weights", "paste_vertex_weights")):
        assert m[path] == f"allset.{op}", path
    assert shelf_map.BY_COMMAND["IKHandleTool"][0] == "allset.ik_handle"
    assert shelf_map.BY_COMMAND["SmoothBindSkin"][0] == "allset.bind_skin"
    assert shelf_map.BY_COMMAND["ArtPaintSkinWeightsTool"][0] == "allset.paint_skin_weights"
