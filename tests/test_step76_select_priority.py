"""Maya selection priority for object-mode clicks (IK handle 10 > joint 9 > curve 4 > mesh 2).
GUI: tests/gui/gui_step76_select_priority.py."""

import types
from importlib import import_module

import bpy
from mathutils import Matrix

import kit

compat = import_module(kit.MODULE + ".compat")
sp = import_module(kit.MODULE + ".operators.select_priority")
patches = import_module(kit.MODULE + ".keymap.maya_patches")
preferences = import_module(kit.MODULE + ".preferences")

W = H = 400


def test_priority_table_is_mayas():
    # priorities like Maya
    assert sp.priority('IK_HANDLE') == 10 and sp.priority('ARMATURE') == 9 and sp.priority('CURVE') == 4
    for other in ('MESH', 'EMPTY', 'LIGHT', 'CAMERA', 'SURFACE', 'FONT', 'OTHER'):
        assert sp.priority(other) == 2, other


def test_rank_priority_then_distance_then_name():
    hits = [("curve", 4, 1.0), ("rig", 9, 4.0), ("ik", 10, 4.9), ("far", 10, 9.0), ("mesh", 2, 0.0)]
    assert sp.rank(hits, 5.0)[0] == "ik"
    assert sp.rank([h for h in hits if h[0] != "ik"], 5.0)[0] == "rig"
    assert sp.rank([("b", 4, 2.0), ("a", 4, 2.0), ("c", 4, 1.0)], 5.0)[0] == "c"
    assert sp.rank([("b", 4, 2.0), ("a", 4, 2.0)], 5.0)[0] == "a"
    assert sp.rank([("mesh", 2, 0.0), ("far", 9, 6.0)], 5.0) is None      # Blender's own pick then


def test_items_lead_the_click_select_items():
    kc = kit.maya_kc()
    assert "allset.select_priority" in patches.PASS_THROUGH_FIRST
    for km_name, value in patches.SELECT_PRIORITY_ITEMS:
        items = [k for k in kc.keymaps[km_name].keymap_items if k.active]
        for shift in (False, True):
            for ctrl in (False, True):
                same = [k.idname for k in items if k.type == 'LEFTMOUSE' and k.value == value
                        and k.shift == shift and k.ctrl == ctrl and not k.alt]
                assert "allset.select_priority" in same and "view3d.select" in same, (km_name, same)
                assert same.index("allset.select_priority") < same.index("view3d.select"), (km_name, same)
    assert preferences.get().select_priority is True       # Maya ignoreSelectionPriority false


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _scene():
    """Front view looking along +Y: a cube at the origin, a curve circle in front of it, an armature
    to the right and an IK target empty to the left (all on the screen's centre row)."""
    _clear()
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    cube = bpy.context.active_object
    bpy.ops.curve.primitive_bezier_circle_add(radius=0.5, location=(0, -2, 0), rotation=(1.5708, 0, 0))
    circle = bpy.context.active_object
    arm_data = bpy.data.armatures.new("rig")
    arm = bpy.data.objects.new("rig", arm_data)
    sc.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for name, head, tail in (("a", (3, 0, -1), (3, 0, 0.5)), ("b", (3, 0, 0.5), (3, 0, 1.5))):
        eb = arm_data.edit_bones.new(name)
        eb.head, eb.tail = head, tail
    arm_data.edit_bones["b"].parent = arm_data.edit_bones["a"]
    bpy.ops.object.mode_set(mode='OBJECT')
    ik = bpy.data.objects.new("ikHandle1", None)
    sc.collection.objects.link(ik)
    ik.location = (-3, 0, 0)
    ik.empty_display_size = 0.5
    con = arm.pose.bones["b"].constraints.new('IK')
    con.target = ik
    con.influence = 0.0                                      # keep the chain straight
    bpy.context.view_layer.update()
    return cube, circle, arm, ik


def _view():
    # orthographic front view: x right, z up, 8 units across 400 px (50 px per unit)
    view = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, -10), (0, 0, 0, 1)))
    proj = Matrix(((0.25, 0, 0, 0), (0, 0.25, 0, 0), (0, 0, -0.01, 0), (0, 0, 0, 1)))
    rv3d = types.SimpleNamespace(perspective_matrix=proj @ view)
    region = types.SimpleNamespace(width=W, height=H)
    ctx = types.SimpleNamespace(space_data=None, view_layer=bpy.context.view_layer, scene=bpy.context.scene,
                                evaluated_depsgraph_get=bpy.context.evaluated_depsgraph_get)
    return ctx, region, rv3d


def _px(x, z):
    return (W / 2 + x * W / 8, H / 2 + z * H / 8)


def _best(mouse):
    ctx, region, rv3d = _view()
    best = sp.rank(sp.hits(ctx, region, rv3d, mouse), sp.RADIUS_PX)
    return best and best[0]


def test_curve_in_front_of_mesh_wins():
    cube, circle, arm, ik = _scene()
    assert _best(_px(0.5, 0.0)) == circle.name               # on the circle, inside the cube's silhouette
    assert _best(_px(0.0, 0.5)) == circle.name
    assert _best(_px(0.0, 0.0)) is None                      # the cube alone: Blender's pick
    assert _best(_px(0.5 + 3.0 / 50, 0.0)) == circle.name    # 3 px off the line
    assert _best(_px(0.5 + 8.0 / 50, 0.0)) is None           # 8 px off: outside the click box


def test_curve_behind_mesh_still_wins():
    cube, circle, arm, ik = _scene()
    circle.location.y = 3.0                                  # behind the cube now
    bpy.context.view_layer.update()
    assert _best(_px(0.5, 0.0)) == circle.name


def test_joint_and_ik_handle_beat_the_curve():
    cube, circle, arm, ik = _scene()
    assert _best(_px(3.0, 0.0)) == arm.name                  # on bone a
    assert _best(_px(3.0 + 0.2, -0.85)) == arm.name          # 10 px out, inside the bone's thickness
    assert _best(_px(3.0 + 0.2, 0.45)) is None               # 10 px out at the thin end
    assert _best(_px(-3.0, 0.0)) == ik.name
    assert _best(_px(-3.25, 0.0)) == ik.name                 # on the empty's x axis
    circle.location.x = 3.0                                  # curve over the bone: the joint wins
    bpy.context.view_layer.update()
    assert _best(_px(3.0, 0.5)) == arm.name
    ik.location = (3.0, 0.0, 0.5)                            # IK handle over both: the handle wins
    bpy.context.view_layer.update()
    assert _best(_px(3.0, 0.5)) == ik.name


def test_hidden_or_unselectable_candidates_are_skipped():
    cube, circle, arm, ik = _scene()
    circle.hide_select = True
    assert _best(_px(0.5, 0.0)) is None
    circle.hide_select = False
    circle.hide_set(True)
    assert _best(_px(0.5, 0.0)) is None
    compat.set_bone_hidden(arm.pose.bones["a"], True)
    assert _best(_px(3.0, -0.5)) is None
    assert _best(_px(3.0, 1.0)) == arm.name                  # bone b still shows
    pb = arm.pose.bones["b"]
    pb.constraints.remove(pb.constraints[0])
    assert _best(_px(-3.0, 0.0)) is None                     # a plain empty is a locator (2)


def test_modifiers_are_mayas():
    cube, circle, arm, ik = _scene()
    ctx = bpy.context
    for ob in ctx.scene.objects:
        ob.select_set(ob == cube)
    sp.apply(ctx, circle, shift=False, ctrl=False)           # replace
    assert [o.name for o in ctx.selected_objects] == [circle.name] and ctx.view_layer.objects.active == circle
    sp.apply(ctx, arm, shift=True, ctrl=True)                # add
    assert {o.name for o in ctx.selected_objects} == {circle.name, arm.name}
    assert ctx.view_layer.objects.active == arm
    sp.apply(ctx, arm, shift=True, ctrl=False)               # toggle off
    assert {o.name for o in ctx.selected_objects} == {circle.name}
    sp.apply(ctx, arm, shift=True, ctrl=False)               # toggle on
    assert {o.name for o in ctx.selected_objects} == {circle.name, arm.name}
    sp.apply(ctx, circle, shift=False, ctrl=True)            # deselect
    assert {o.name for o in ctx.selected_objects} == {arm.name}

