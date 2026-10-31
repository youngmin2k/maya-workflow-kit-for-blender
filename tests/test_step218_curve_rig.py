"""Spline IK on an existing curve (L6) and clusters on curve CVs (L7) against the expected numbers
Maya (x, y, z) = Blender (x, -z, y), factory scene = 1 unit.

Scene: joint1..joint5 at Maya (0, 2i, 0); spineCurve = degree 3, CVs (1,0,0) (2,2,0) (1,4,1) (0,6,0) (1,8,0).

"""

from importlib import import_module

import bpy
from mathutils import Vector

import kit

rig = import_module(kit.MODULE + ".operators.rig_maya")
ow = import_module(kit.MODULE + ".operators.option_windows")
parenting = import_module(kit.MODULE + ".operators.parenting")
cb = import_module(kit.MODULE + ".ui.channel_box")


CVS = [(1, 0, 0), (2, 2, 0), (1, 4, 1), (0, 6, 0), (1, 8, 0)]


def B(p):
    x, y, z = p
    return Vector((x, -z, y))


def _fresh():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.armatures, bpy.data.curves, bpy.data.meshes):
        for d in list(coll):
            coll.remove(d)


def _curve(name="spineCurve", cvs=CVS, resolution=12):
    cu = bpy.data.curves.new(name + "Shape", 'CURVE')
    cu.dimensions = '3D'
    cu.resolution_u = resolution
    sp = cu.splines.new('NURBS')
    sp.points.add(len(cvs) - 1)
    for p, c in zip(sp.points, cvs):
        p.co = (*B(c), 1.0)
    sp.order_u = 4
    sp.use_endpoint_u = True        # Maya clamped uniform knots
    ob = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(ob)
    return ob


def _chain(parent_bone=False):
    """Kit skeleton: bones joint1..joint4 between the joints, joint5 = the end joint (short bone)."""
    data = bpy.data.armatures.new("skeleton")
    arm = bpy.data.objects.new("skeleton1", data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    if parent_bone:
        prev = data.edit_bones.new("joint0")
        prev.head, prev.tail = (0, 0, -2), (0, 0, 0)
    for k in range(5):
        eb = data.edit_bones.new(f"joint{k + 1}")
        eb.head = (0, 0, 2 * k)
        eb.tail = (0, 0, 2 * k + (2 if k < 4 else 0.5))
        if prev is not None:
            eb.parent = prev
            eb.use_connect = True
        prev = eb
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name in ("joint1", "joint5"))
    data.bones.active = data.bones["joint5"]
    return arm


def _spline(curve=None, **kw):
    return bpy.ops.allset.ik_spline_handle('EXEC_DEFAULT', True, curve=curve.name if curve else "", **kw)


# --- L6 Spline IK on an existing curve --------------------------------------------------------------------------


def test_number_of_spans():
    _fresh()
    arm = _chain()
    assert _spline(spans=2) == {'FINISHED'}
    sp = arm.pose.bones["joint4"].constraints["ikHandle1"].target.data.splines[0]
    assert len(sp.points) == 5 and sp.use_endpoint_u
    assert Vector(sp.points[0].co[:3]).length < 1e-6
    assert (Vector(sp.points[-1].co[:3]) - Vector((0, 0, 8))).length < 1e-6


def test_auto_parent_curve():
    _fresh()
    curve = _curve()
    arm = _chain(parent_bone=True)
    before = curve.matrix_world.copy()
    assert _spline(curve, create_curve=False, root_on_curve=True) == {'FINISHED'}
    assert curve.parent == arm and curve.parent_type == 'BONE' and curve.parent_bone == "joint0"
    bpy.context.view_layer.update()
    assert max(abs(a - b) for ra, rb in zip(curve.matrix_world, before) for a, b in zip(ra, rb)) < 1e-5
    _fresh()
    curve = _curve()
    arm = _chain(parent_bone=True)
    assert _spline(curve, create_curve=False, parent_curve=False) == {'FINISHED'}
    assert curve.parent is None


def test_auto_create_off_needs_a_curve():
    _fresh()
    _chain()
    assert _spline(None, create_curve=False) == {'CANCELLED'}


def test_option_window_runs_the_tool_with_the_values():
    _fresh()
    curve = _curve()
    arm = _chain()
    curve.select_set(True)
    w = ow._BY_KEY["ik_spline_tool"]
    res = ow.run(w, bpy.context, {"create_curve": False, "snap_curve": True})
    assert not isinstance(res, str), res
    assert arm.pose.bones["joint4"].constraints["ikHandle1"].target == curve
    assert (curve.matrix_world @ Vector(curve.data.splines[0].points[0].co[:3])).length < 1e-6


def test_spline_ik_undo():
    _fresh()
    curve = _curve()
    arm = _chain()
    bpy.ops.ed.undo_push(message="test start")
    assert _spline(curve, create_curve=False, snap_curve=True) == {'FINISHED'}
    bpy.ops.ed.undo()
    arm = bpy.data.objects["skeleton1"]
    curve = bpy.data.objects["spineCurve"]
    assert not arm.pose.bones["joint4"].constraints
    assert curve.matrix_world.translation.length < 1e-9


# --- L7 Cluster on curve CVs ------------------------------------------------------------------------------------

def _curve_points(ob):
    """Evaluated curve polyline in world space (to_mesh)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        return [ob.matrix_world @ v.co for v in me.vertices]
    finally:
        ev.to_mesh_clear()


def _cluster_on_cvs(cvs=(3, 4)):
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    curve = bpy.data.objects["spineCurve"]
    for o in bpy.context.selected_objects:
        o.select_set(False)
    curve.select_set(True)
    bpy.context.view_layer.objects.active = curve
    for i, p in enumerate(curve.data.splines[0].points):
        p.select = i in cvs
    bpy.ops.object.mode_set(mode='EDIT')
    assert bpy.ops.allset.cluster('EXEC_DEFAULT', True) == {'FINISHED'}
    return curve


def test_cluster_object_mode_takes_every_cv():
    _fresh()
    curve = _curve()
    bpy.context.view_layer.objects.active = curve
    curve.select_set(True)
    assert bpy.ops.allset.cluster('EXEC_DEFAULT', True) == {'FINISHED'}
    handle = bpy.data.objects["cluster1Handle"]
    assert (handle.location - B((1, 4, 0.5))).length < 1e-6          # box centre of the CVs
    handle.location.z += 1.0
    bpy.context.view_layer.update()
    pts = _curve_points(curve)
    ref = _curve_points(_curve("ref"))
    assert all(abs((a - b).z - 1.0) < 1e-5 and abs((a - b).x) < 1e-5 for a, b in zip(pts, ref))


def test_cluster_bezier_point_indices():
    _fresh()
    cu = bpy.data.curves.new("bez", 'CURVE')
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(2)
    for i, bp in enumerate(sp.bezier_points):
        bp.co = (2.0 * i, 0, 0)
        bp.handle_left_type = bp.handle_right_type = 'VECTOR'
        bp.select_control_point = bp.select_left_handle = bp.select_right_handle = (i == 1)
    ob = bpy.data.objects.new("bez", cu)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    centre, idx = rig._point_selection(ob, True)
    assert idx == [3, 4, 5] and (centre - Vector((2, 0, 0))).length < 1e-6


def test_cluster_undo():
    _fresh()
    _curve()
    bpy.ops.ed.undo_push(message="test start")
    _cluster_on_cvs()
    bpy.ops.ed.undo()
    curve = bpy.data.objects["spineCurve"]
    assert not curve.modifiers and "cluster1Handle" not in bpy.data.objects
