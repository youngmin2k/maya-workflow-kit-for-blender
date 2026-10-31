"""L1 (Issue #136): NURBS curves as bone Custom Shapes — Maya ``parent -s [-r]``.

Expected (parent shape relative / absolute):
a circle (r 1, normal Maya Y) with cv0 at (0.7836, 0, -0.7836);
joint1 at (5, 2, 0) with jointOrient Z 30. ``parent -s -r`` -> cv0 world (5.6786, 2.3918, -0.7836), cv1
(5, 2, -1.1082), the old transform stays without a shape; ``parent -s`` (circle moved x+1) keeps cv0 world
(1.7836, 0, -0.7836) and the old transform goes. Maya (x, y, z) = Blender (x, z, -y) / maya_unit."""

import math
import os
from importlib import import_module

import bpy
import numpy as np
from mathutils import Matrix, Vector

import kit

cs = import_module(kit.MODULE + ".operators.control_shapes")
sp = import_module(kit.MODULE + ".operators.select_priority")
pre = import_module(kit.MODULE + ".operators.preselect")
units = import_module(kit.MODULE + ".operators.units")
fbx_rig = import_module(kit.MODULE + ".operators.fbx_rig")
cmds = import_module(kit.MODULE + ".command_line.cmds_shim")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp", "test_step226")

TOL = 1e-4


def _clear():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for c in list(bpy.data.curves):
        bpy.data.curves.remove(c)
    for a in list(bpy.data.armatures):
        bpy.data.armatures.remove(a)
    coll = bpy.data.collections.get(cs.COLLECTION)
    if coll is not None:
        bpy.data.collections.remove(coll)
    return units.maya_unit()


def _joint(k, name="joint1", arm_name="skeleton1"):
    """A bone whose frame is Maya's joint1 frame: bone Y = Maya joint X, bone Z = joint Y, bone X = joint Z."""
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    jx, jy, jz = Vector((c, s, 0)), Vector((-s, c, 0)), Vector((0, 0, 1))     # Maya joint axes (jointOrient Z 30)
    bl = lambda v: Vector((v.x, -v.z, v.y))                                     # Maya -> Blender direction
    m = Matrix.Identity(4)
    for col, v in enumerate((bl(jz), bl(jx), bl(jy))):
        for row in range(3):
            m[row][col] = v[row]
    m.translation = Vector((5, 0, 2)) * k
    arm = bpy.data.objects.get(arm_name)
    if arm is None:
        arm = bpy.data.objects.new(arm_name, bpy.data.armatures.new(arm_name))
        bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones.new(name)
    eb.head, eb.tail = (0, 0, 0), (0, 1 * k, 0)
    eb.matrix = m
    bpy.ops.object.mode_set(mode='POSE')
    bpy.context.view_layer.update()
    pb = arm.pose.bones[name]
    for i in range(3):
        assert (pb.matrix.col[i].xyz - m.col[i].xyz).length < 1e-5, (i, pb.matrix)
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm, pb


def _circle(k, name="ctrl_circle", location=(0, 0, 0)):
    """Circle CVs (radius 1.1082 at 45 deg steps, cv0 = Maya (0.7836, 0, -0.7836)) lying in Blender XY."""
    cu = bpy.data.curves.new(name + "Shape", 'CURVE')
    cu.dimensions = '3D'
    sp_ = cu.splines.new('NURBS')
    r = 0.7836 * math.sqrt(2)
    # cv0 at 45 deg = Blender (0.7836, 0.7836, 0); cv1 = Maya (0, 0, -1.1082) = Blender (0, 1.1082, 0)
    pts = [(r * math.cos(math.radians(45 + 45 * i)), r * math.sin(math.radians(45 + 45 * i)), 0.0) for i in range(8)]
    sp_.points.add(len(pts) - 1)
    for p, co in zip(sp_.points, pts):
        p.co = (co[0] * k, co[1] * k, co[2] * k, 1.0)
    sp_.use_cyclic_u = True
    sp_.order_u = 4
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = Vector(location) * k
    bpy.context.view_layer.update()
    return ob


def _close(a, b, tol=TOL):
    return (Vector(a) - Vector(b)).length < tol


def test_second_shape_adds_and_replace_swaps():
    k = _clear()
    arm, pb = _joint(k)
    cs.parent_shape(_circle(k, "ctrl_a"), pb)
    shape = pb.custom_shape
    cs.parent_shape(_circle(k, "ctrl_b"), pb)
    assert pb.custom_shape == shape and len(shape.data.splines) == 2      # Maya: two shapes, one control
    cs.parent_shape(_circle(k, "ctrl_c"), pb, replace=True)
    assert pb.custom_shape.name == "ctrl_cShape" and len(pb.custom_shape.data.splines) == 1
    assert bpy.data.objects.get("ctrl_aShape") is None                  # the replaced kit shape is gone


def test_curve_target_merges_and_empty_target_warns():
    k = _clear()
    a = _circle(k, "ctrlA")
    b = _circle(k, "ctrlB", location=(0, 0, 3))
    world = b.matrix_world @ Vector(b.data.splines[0].points[0].co[:3])
    cs.parent_shape(b, a, relative=False)
    assert len(a.data.splines) == 2
    got = a.matrix_world @ Vector(a.data.splines[1].points[0].co[:3])
    assert _close(got, world), (tuple(got), tuple(world))
    c = _circle(k, "ctrlC")
    e = bpy.data.objects.new("null1", None)
    bpy.context.scene.collection.objects.link(e)
    try:
        cs.parent_shape(c, e)
    except ValueError as ex:
        assert "can't give null1 a shape" in str(ex), ex
    else:
        raise AssertionError("an Empty target must be refused")
    assert c.type == 'CURVE' and len(c.data.splines) == 1


def test_operator_and_undo():
    k = _clear()
    arm, pb = _joint(k)
    curve = _circle(k)
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    curve.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    arm.data.bones.active = arm.data.bones["joint1"]
    bpy.ops.ed.undo_push(message="before shape")
    res = bpy.ops.allset.parent_shape('EXEC_DEFAULT', True, relative=True)
    assert res == {'FINISHED'}, res
    assert bpy.data.objects["skeleton1"].pose.bones["joint1"].custom_shape is not None
    bpy.ops.ed.undo()
    assert bpy.data.objects["skeleton1"].pose.bones["joint1"].custom_shape is None
    assert bpy.data.objects["ctrl_circle"].type == 'CURVE'
    assert bpy.data.objects.get("ctrl_circleShape") is None


def _ortho_top(k, size=20.0, px=800):
    """A top orthographic projection: world x, y in [-size/2, size/2] x maya_unit -> region px."""
    s = 2.0 / (size * k)
    m = Matrix.Identity(4)
    m[0][0], m[1][1], m[2][2] = s, s, -0.01
    return np.array(m), px, px


def test_hit_on_wire_not_octahedron():
    k = _clear()
    arm, pb = _joint(k)
    cs.parent_shape(_circle(k), pb)
    dg = bpy.context.evaluated_depsgraph_get()
    a, b = cs.shape_segments(arm, pb, dg)
    assert len(a) >= 8, len(a)                       # the evaluated NURBS wire
    persp, w, h = _ortho_top(k)
    xa, fa = pre.project(a, persp, w, h)
    xb, fb = pre.project(b, persp, w, h)
    on_wire = (xa[0] + xb[0]) / 2
    assert sp.shape_hit(on_wire, xa, xb, fa & fb) < 1.0
    # the middle of the (undrawn) octahedron: half way down the bone, well inside the circle
    mid = (arm.matrix_world @ pb.matrix @ Vector((0, 0.5 * k, 0)))
    xm, _ = pre.project(np.array([mid]), persp, w, h)
    assert sp.shape_hit(xm[0], xa, xb, fa & fb) > sp.RADIUS_PX * 2
    # select_priority's coarse armature segments are the wire for a shaped bone, the bone for a plain one
    sa, sb, reach = sp._segments(arm, 'ARMATURE', dg)
    assert len(sa) == len(a) and not np.any(reach)


def test_fbx_export_leaves_shapes_out():
    k = _clear()
    arm, pb = _joint(k)
    cs.parent_shape(_circle(k), pb)
    # a Rigify-style widget mesh in the scene used as another bone's shape
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones.new("joint2")
    eb.head, eb.tail = (0, 0, 0), (0, 0, 1 * k)
    bpy.ops.object.mode_set(mode='OBJECT')
    me = bpy.data.meshes.new("WGT-joint2")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [(0, 1), (1, 2)], [])
    wgt = bpy.data.objects.new("WGT-joint2", me)
    bpy.context.scene.collection.objects.link(wgt)
    bpy.ops.mesh.primitive_cube_add(size=1 * k)
    bpy.context.active_object.name = "body"
    arm.pose.bones["joint2"].custom_shape = wgt
    order = [o.name for o in bpy.context.scene.collection.objects]
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "shapes226.fbx")
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    res = bpy.ops.allset.file_export_all('EXEC_DEFAULT', filepath=path, export_type='FBX')
    assert res == {'FINISHED'}, res
    index = fbx_rig.Index(fbx_rig.load(path)[0])
    names = [fbx_rig.name_of(m) for m in index.models.values()]
    assert "body" in names, names
    assert not any("Shape" in n or "WGT" in n for n in names), names     # the -r empty ctrl_circle stays
    # the widget is back in the scene, same order
    assert [o.name for o in bpy.context.scene.collection.objects] == order
    # Export Selection with the widget selected leaves it out too
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    wgt.select_set(True)
    bpy.data.objects["body"].select_set(True)
    path2 = os.path.join(OUT, "shapes226_sel.fbx")
    res = bpy.ops.allset.file_export_selection('EXEC_DEFAULT', filepath=path2, export_type='FBX')
    assert res == {'FINISHED'}, res
    names = [fbx_rig.name_of(m) for m in fbx_rig.Index(fbx_rig.load(path2)[0]).models.values()]
    assert "body" in names and not any("WGT" in n for n in names), names
    assert wgt.select_get() and wgt.name in bpy.context.scene.collection.objects
