"""Constrain > Normal / Tangent / Remove Target / Set Rest Position / Modify Constrained Axis against
Maya (Maya's values are DATA at
the end of this file). Maya Y-up -> Blender Z-up: C = (x, y, z) -> (x, -z, y), a world matrix B = C M C^-1."""

import math
from importlib import import_module

import bpy
from mathutils import Euler, Matrix, Vector

import kit

c199 = import_module(kit.MODULE + ".operators.constrain_199")
prim = import_module(kit.MODULE + ".operators.prim_shapes")

TOL = 1e-5
C4 = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


def to_b(p):
    x, y, z = p
    return (x, -z, y)


def b_matrix(rows):
    """Maya world matrix (row-major, translation in the last row) -> Blender world matrix."""
    m = Matrix([rows[0:4], rows[4:8], rows[8:12], rows[12:16]]).transposed()
    return C4 @ m @ C4.inverted()


def maya_xform(t=(0, 0, 0), ro=(0, 0, 0), s=(1, 1, 1)):
    """Maya translate / rotate (XYZ order, degrees) / scale -> Blender world matrix."""
    r = Euler([math.radians(a) for a in ro], 'XYZ').to_matrix().to_4x4()
    m = Matrix.Translation(t) @ r @ Matrix.Diagonal((*s, 1.0))
    return C4 @ m @ C4.inverted()


def maya_channels(ch):
    return maya_xform(ch["t"], ch["r"], ch["s"])


def close(a, b, tol=TOL, what=""):
    err = max(abs(a[i][j] - b[i][j]) for i in range(4) for j in range(4))
    assert err < tol, f"{what}: max error {err:.2e}\n{a}\n{b}"
    return err


def _fresh():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    c199.unregister_handlers()
    c199.register_handlers()


def _empty(name, matrix=None):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    if matrix is not None:
        ob.matrix_world = matrix
    return ob


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def _mesh(name, verts, faces, sharp=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([to_b(v) for v in verts], [], faces)
    me.shade_smooth()           # kit primitives: smooth faces, Maya's hard edges as sharp_edge
    if sharp:
        attr = me.attributes.new("sharp_edge", 'BOOLEAN', 'EDGE')
        attr.data.foreach_set("value", [True] * len(me.edges))
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _maya_targets():
    """The three target meshes (kit primitives, Maya vertex / face order)."""
    a = prim.defaults("polySphere")
    a.update(radius=5.0, subdivisionsAxis=20, subdivisionsHeight=20)
    s = prim.poly_sphere(a)
    a.update(subdivisionsAxis=12, subdivisionsHeight=8)
    h = prim.poly_sphere(a)
    hv = [(x, y, z + 20) for x, y, z in h.verts]
    a = prim.defaults("polyPlane")
    a.update(width=10.0, height=10.0, subdivisionsWidth=4, subdivisionsHeight=4)
    p = prim.poly_plane(a)
    pv = [(x + 30, 0.08 * x * x + 0.05 * x * z, z) for x, y, z in p.verts]
    for got, want in ((s.verts, DATA["sphere_verts"]), (hv, DATA["hard_verts"]), (pv, DATA["plane_verts"])):
        for i, v in want.items():
            assert (Vector(got[i]) - Vector(v)).length < 1e-6, (i, got[i], v)
    return {"smooth_sphere": _mesh("smoothSphere", s.verts, s.faces),
            "hard_sphere": _mesh("hardSphere", hv, h.faces, sharp=True),
            "bent_plane": _mesh("bentPlane", pv, p.faces)}


# --- Normal -------------------------------------------------------------------------------------------------

def test_normal_matches_maya():
    _fresh()
    targets = _maya_targets()
    worst = 0.0
    for k, case in enumerate(DATA["normal"]):
        if "parent" in case:
            continue
        loc = _empty(f"n{k}", maya_xform(case["pos"], case["start_rot"]))
        _select(targets[case["target"]], loc)
        assert bpy.ops.allset.normal_constraint() == {'FINISHED'}
        bpy.context.view_layer.update()
        err = close(loc.matrix_world, b_matrix(case["matrix"]), what=f"normal {case}")
        print("normal", case["target"], case["pos"], f"{err:.2e}")
        worst = max(worst, err)
        con = loc.constraints[-1]
        assert c199.maya_type(con) == "normal" and c199.surface_of(con) == targets[case["target"]]
    print("normal worst", worst)


def test_normal_parented_object_is_world_space():
    _fresh()
    targets = _maya_targets()
    for k, case in enumerate(c for c in DATA["normal"] if "parent" in c):
        par = _empty(f"nParent{k}", b_matrix(case["parent"]))
        loc = _empty(f"n_child{k}")
        loc.parent = par
        loc.matrix_world = Matrix.Translation(to_b(case["pos"]))
        _select(targets["smooth_sphere"], loc)
        assert bpy.ops.allset.normal_constraint() == {'FINISHED'}
        bpy.context.view_layer.update()
        want, got = b_matrix(case["matrix"]), loc.matrix_world
        lengths = [par.matrix_world.col[i].xyz.length for i in range(3)]
        uniform = max(lengths) - min(lengths) < 1e-6
        if uniform:
            close(got, want, what="uniformly scaled parent")
        else:
            # a non-uniformly scaled parent shears Maya's child (rotate channels under the parent's scale); Blender's
            # constraint result is the world rotation itself: the position matches, the aim is the world normal
            assert (want.translation - got.translation).length < TOL
            n = Vector(c199.direction("normal", targets["smooth_sphere"], tuple(got.translation)))
            assert (got.col[0].xyz.normalized() - n).length < TOL


def test_normal_follows_the_object_live():
    _fresh()
    targets = _maya_targets()
    case = DATA["normal"][0]
    loc = _empty("live", maya_xform((0, 9, 0)))
    _select(targets["smooth_sphere"], loc)
    bpy.ops.allset.normal_constraint()
    loc.matrix_world = maya_xform(case["pos"])
    bpy.context.view_layer.update()          # the depsgraph handler moves the helper
    bpy.context.view_layer.update()
    close(loc.matrix_world, b_matrix(case["matrix"]), what="after a move")
    # the surface moves: the normal comes from the moved mesh
    targets["smooth_sphere"].location = (0, 0, 1)
    bpy.context.view_layer.update()
    bpy.context.view_layer.update()
    n = c199.direction("normal", targets["smooth_sphere"], tuple(loc.matrix_world.translation))
    assert (loc.matrix_world.col[0].xyz.normalized() - Vector(n)).length < TOL


def test_normal_options_and_hints():
    _fresh()
    targets = _maya_targets()
    loc = _empty("o", maya_xform((8, 3, 2)))
    _select(loc)
    try:
        res = bpy.ops.allset.normal_constraint()
    except RuntimeError:
        res = {'CANCELLED'}
    assert res == {'CANCELLED'}, "no target surface: nothing to do"
    _select(targets["smooth_sphere"], loc)
    assert bpy.ops.allset.normal_constraint(world_up_type="None", weight=0.5) == {'FINISHED'}
    con = loc.constraints[-1]
    assert con.type == 'DAMPED_TRACK' and abs(con.influence - 0.5) < 1e-9
    assert c199.maya_type(con) == "normal"
    bpy.context.view_layer.update()
    con.influence = 1.0
    bpy.context.view_layer.update()
    n = Vector(c199.direction("normal", targets["smooth_sphere"], tuple(loc.matrix_world.translation)))
    assert (loc.matrix_world.col[0].xyz.normalized() - n).length < TOL


# --- Tangent ------------------------------------------------------------------------------------------------

def _curve(name, cvs, cyclic=False):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('NURBS')
    sp.points.add(len(cvs) - 1)
    for p, v in zip(sp.points, cvs):
        p.co = (*to_b(v), 1.0)
    sp.order_u = 4
    sp.use_cyclic_u = cyclic
    sp.use_endpoint_u = not cyclic
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def test_tangent_matches_maya():
    _fresh()
    curve = _curve("tCurve", DATA["tangent_curve"])
    circle = _curve("tCircle", DATA["tangent_circle"], cyclic=True)
    worst = 0.0
    for k, case in enumerate(DATA["tangent"]):
        loc = _empty(f"t{k}", maya_xform(case["pos"]))
        _select(circle if case["circle"] else curve, loc)
        assert bpy.ops.allset.tangent_constraint() == {'FINISHED'}
        bpy.context.view_layer.update()
        worst = max(worst, close(loc.matrix_world, b_matrix(case["matrix"]), what=f"tangent {case}"))
        assert c199.maya_type(loc.constraints[-1]) == "tangent"
    print("tangent worst", worst)


def test_tangent_needs_a_curve():
    _fresh()
    targets = _maya_targets()
    loc = _empty("t", maya_xform((2, 3, 1)))
    _select(targets["bent_plane"], loc)
    try:
        res = bpy.ops.allset.tangent_constraint()
    except RuntimeError:
        res = {'CANCELLED'}
    assert res == {'CANCELLED'}
    assert not loc.constraints


# --- Remove Target ------------------------------------------------------------------------------------------

A_X = dict(t=(4, 2, 0), ro=(0, 30, 0), s=(2, 2, 2))
B_X = dict(t=(-2, 6, 3), ro=(45, 0, 10), s=(1, 3, 1))
O_X = dict(t=(1, 1, 1), ro=(5, 6, 7))


def _two_targets(kind):
    a, b = _empty("tA", maya_xform(**A_X)), _empty("tB", maya_xform(**B_X))
    o = _empty("obj", maya_xform(**O_X))
    for t in (a, b):
        if kind == "parent":
            # Maya parentConstraint (no offset): the object takes the target's translate and rotate; Blender Child
            # Of without scale and an inverse of identity does that on identity own channels
            o.matrix_world = Matrix.Identity(4)
            con = o.constraints.new('CHILD_OF')
            con.target = t
            con.use_scale_x = con.use_scale_y = con.use_scale_z = False
            con.inverse_matrix = Matrix.Identity(4)
        else:
            _select(t, o)
            typ = {"point": 'COPY_LOCATION', "orient": 'COPY_ROTATION', "scale": 'COPY_SCALE',
                   "aim": 'TRACK_TO'}[kind]
            assert bpy.ops.allset.constrain(type=typ) == {'FINISHED'}
    bpy.context.view_layer.update()
    return a, b, o


def test_remove_target_matches_maya():
    for kind, want in DATA["remove"].items():
        _fresh()
        a, b, o = _two_targets(kind)
        _select(b, o)
        assert bpy.ops.allset.remove_constraint_target() == {'FINISHED'}
        bpy.context.view_layer.update()
        assert len(o.constraints) == 1 and o.constraints[0].target == a, kind
        close(o.matrix_world, b_matrix(want["after_one"]), what=f"{kind} after one")
        _select(a, o)
        assert bpy.ops.allset.remove_constraint_target() == {'FINISHED'}
        bpy.context.view_layer.update()
        assert not o.constraints, kind
        # the constraint node is gone and the channels keep the constrained value (Maya)
        close(o.matrix_world, b_matrix(want["after_all"]), what=f"{kind} after all")
        close(o.matrix_basis, b_matrix(want["after_all"]), what=f"{kind} own channels")


def test_remove_target_type_flags_and_errors():
    _fresh()
    a, b, o = _two_targets("point")
    _select(a, b, o)
    # only orient constraints asked for: the point constraints stay
    assert bpy.ops.allset.remove_constraint_target(remove_all=False, point=False) == {'FINISHED'}
    assert len(o.constraints) == 2
    # a target that constrains nothing here: nothing happens, no error (Maya)
    c = _empty("other")
    _select(c, o)
    before = o.matrix_world.copy()
    assert bpy.ops.allset.remove_constraint_target() == {'FINISHED'}
    assert len(o.constraints) == 2 and (o.matrix_world == before)
    # Maya's errors
    _select(o)
    try:
        bpy.ops.allset.remove_constraint_target()
        raise AssertionError("no error with one object selected")
    except RuntimeError as ex:
        assert c199.MSG_REMOVE_SELECT in str(ex)
    _select(a, c)
    try:
        bpy.ops.allset.remove_constraint_target()
        raise AssertionError("no error on an unconstrained object")
    except RuntimeError as ex:
        assert c199.MSG_REMOVE_CONSTRAINED in str(ex)


def test_remove_normal_target_removes_its_helper():
    _fresh()
    targets = _maya_targets()
    case = DATA["normal"][0]
    loc = _empty("n", maya_xform(case["pos"]))
    _select(targets["smooth_sphere"], loc)
    bpy.ops.allset.normal_constraint()
    helper = loc.constraints[0].target
    hname = helper.name
    bpy.context.view_layer.update()
    _select(targets["smooth_sphere"], loc)
    assert bpy.ops.allset.remove_constraint_target() == {'FINISHED'}
    assert not loc.constraints and hname not in bpy.data.objects
    bpy.context.view_layer.update()
    close(loc.matrix_world, b_matrix(case["matrix"]), what="baked normal rotation")
    assert not c199.helpers()


def test_remove_pole_vector_target():
    _fresh()
    arm_data = bpy.data.armatures.new("rig")
    arm = bpy.data.objects.new("rig", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    _select(arm)
    bpy.ops.object.mode_set(mode='EDIT')
    b1 = arm_data.edit_bones.new("joint1")
    b1.head, b1.tail = (0, 0, 0), (0, 0.2, 4)
    b2 = arm_data.edit_bones.new("joint2")
    b2.head, b2.tail, b2.parent = (0, 0.2, 4), (0, 0, 8), b1
    bpy.ops.object.mode_set(mode='OBJECT')
    handle, pole = _empty("ikHandle1", Matrix.Translation((0, 0, 8))), _empty("pole", Matrix.Translation((0, 5, 4)))
    ik = arm.pose.bones["joint2"].constraints.new('IK')
    ik.target, ik.pole_target, ik.chain_count = handle, pole, 2
    _select(pole, handle)
    assert bpy.ops.allset.remove_constraint_target() == {'FINISHED'}
    assert ik.pole_target is None and ik.target == handle


# --- Set Rest Position --------------------------------------------------------------------------------------

def test_set_rest_position_matches_maya():
    for kind, want in DATA["rest"].items():
        _fresh()
        a = _empty("tA", maya_xform((4, 2, -1), (10, 30, 0), (2, 1, 3)))
        o = _empty("obj", maya_xform((1, 1, 1), (5, 6, 7)))
        if kind == "parent":
            o.matrix_world = Matrix.Identity(4)
            con = o.constraints.new('CHILD_OF')
            con.target = a
            con.use_scale_x = con.use_scale_y = con.use_scale_z = False
            con.inverse_matrix = Matrix.Identity(4)
        else:
            con = o.constraints.new({"point": 'COPY_LOCATION', "orient": 'COPY_ROTATION', "scale": 'COPY_SCALE'}[kind])
            con.target = a
        bpy.context.view_layer.update()
        before = o.matrix_world.copy()
        _select(o)
        assert bpy.ops.allset.set_constraint_rest() == {'FINISHED'}
        bpy.context.view_layer.update()
        close(o.matrix_world, before, 1e-6, what=f"{kind}: Set Rest Position moved the object")
        a.matrix_world = maya_xform((-3, 5, 2), (0, 0, 45), (1, 1, 1))
        bpy.context.view_layer.update()
        close(o.matrix_world, maya_channels(want["moved"]), what=f"{kind} target moved")
        con.influence = 0.0                         # Maya: every target weight 0 -> the rest position
        bpy.context.view_layer.update()
        close(o.matrix_world, b_matrix(want["w0_after_rest"]), what=f"{kind} weight 0")


def test_set_rest_position_errors_and_offsets():
    _fresh()
    o = _empty("obj", maya_xform((1, 1, 1)))
    _select(o)
    try:
        bpy.ops.allset.set_constraint_rest()
        raise AssertionError("no error on an unconstrained object")
    except RuntimeError as ex:
        assert c199.MSG_REST in str(ex)
    a = _empty("tA", maya_xform((4, 2, -1)))
    con = o.constraints.new('COPY_LOCATION')
    con.target, con.use_offset = a, True
    bpy.context.view_layer.update()
    before = o.matrix_world.copy()
    _select(o)
    assert bpy.ops.allset.set_constraint_rest() == {'FINISHED'}     # a warning: the own channels are the offset
    bpy.context.view_layer.update()
    close(o.matrix_world, before, 1e-6, what="offset constraint moved")


# --- Modify Constrained Axis --------------------------------------------------------------------------------

def _axis_setup(kind):
    a = _empty("tA", maya_xform((4, 2, -1), (10, 30, 20), (2, 1, 3)))
    o = _empty("obj", maya_xform((1, 1, 1), (5, 6, 7), (1.5, 1.5, 1.5)))
    con = o.constraints.new({"point": 'COPY_LOCATION', "orient": 'COPY_ROTATION', "scale": 'COPY_SCALE'}[kind])
    con.target = a
    bpy.context.view_layer.update()
    return a, o, con


def _skip_maya_y(maintain):
    # Maya Y = Blender Z (the Channel Box's letters are Blender's)
    return bpy.ops.allset.modify_constraint_axes(x=True, y=True, z=False, maintain_offset=maintain)


def test_modify_axis_point_matches_maya():
    for maintain in (0, 1):
        want = DATA["axis"][f"point_{maintain}"]
        _fresh()
        a, o, con = _axis_setup("point")
        close(o.matrix_world, maya_channels(want["constrained"]), what="point constrained")
        _select(o)
        assert _skip_maya_y(bool(maintain)) == {'FINISHED'}
        bpy.context.view_layer.update()
        assert (con.use_x, con.use_y, con.use_z) == (True, True, False)
        close(o.matrix_world, maya_channels(want["skip_y"]), what=f"point skip y {maintain}")
        a.matrix_world = maya_xform((-3, 5, 2), (0, 50, 45), (1, 2, 1))
        bpy.context.view_layer.update()
        close(o.matrix_world, maya_channels(want["target_moved"]), what=f"point target moved {maintain}")
        assert bpy.ops.allset.modify_constraint_axes(maintain_offset=bool(maintain)) == {'FINISHED'}
        bpy.context.view_layer.update()
        close(o.matrix_world, maya_channels(want["all_again"]), what=f"point all again {maintain}")


def test_modify_axis_scale_maintain_matches_maya():
    want = DATA["axis"]["scale_1"]
    _fresh()
    a, o, con = _axis_setup("scale")
    close(o.matrix_world, maya_channels(want["constrained"]), what="scale constrained")
    _select(o)
    assert _skip_maya_y(True) == {'FINISHED'}
    bpy.context.view_layer.update()
    close(o.matrix_world, maya_channels(want["skip_y"]), what="scale skip y")
    a.matrix_world = maya_xform((-3, 5, 2), (0, 50, 45), (1, 2, 1))
    bpy.context.view_layer.update()
    close(o.matrix_world, maya_channels(want["target_moved"]), what="scale target moved")
    assert bpy.ops.allset.modify_constraint_axes(maintain_offset=True) == {'FINISHED'}
    bpy.context.view_layer.update()
    close(o.matrix_world, maya_channels(want["all_again"]), what="scale all again")


def test_modify_axis_skipped_channel_keeps_its_value():
    # Maya scale without Maintain offset collapses to 0 (-offset 0 0 0): the kit keeps the value instead
    for kind in ("scale", "orient"):
        _fresh()
        a, o, con = _axis_setup(kind)
        before = o.matrix_world.copy()
        _select(o)
        assert _skip_maya_y(False) == {'FINISHED'}
        bpy.context.view_layer.update()
        close(o.matrix_world, before, 1e-5, what=f"{kind}: skipping moved the object")
        a.matrix_world = maya_xform((-3, 5, 2), (0, 50, 45), (1, 2, 1))
        bpy.context.view_layer.update()
        if kind == "scale":
            s, ts = o.matrix_world.to_scale(), a.matrix_world.to_scale()
            assert abs(s.x - ts.x) < TOL and abs(s.y - ts.y) < TOL and abs(s.z - before.to_scale().z) < TOL
        else:
            e = o.matrix_world.to_euler('XYZ')
            assert abs(e.z - before.to_euler('XYZ').z) < TOL


def test_modify_axis_parent_aim_and_errors():
    _fresh()
    a = _empty("tA", maya_xform((4, 2, -1), (10, 30, 20)))
    o = _empty("obj", maya_xform((1, 1, 1), (5, 6, 7)))
    _select(a, o)
    bpy.ops.allset.constrain(type='CHILD_OF')
    bpy.context.view_layer.update()
    before = o.matrix_world.copy()
    _select(o)
    assert _skip_maya_y(False) == {'FINISHED'}
    bpy.context.view_layer.update()
    con = o.constraints[0]
    assert not con.use_location_z and not con.use_rotation_z
    close(o.matrix_world, before, 1e-5, what="parent: nothing moves")
    # aim: Blender's Track To can't skip an axis -> warning, unchanged
    _fresh()
    a = _empty("tA", maya_xform((4, 2, -1)))
    o = _empty("obj", maya_xform((1, 1, 1)))
    _select(a, o)
    bpy.ops.allset.constrain(type='TRACK_TO')
    _select(o)
    assert _skip_maya_y(False) == {'FINISHED'}
    assert o.constraints[0].type == 'TRACK_TO'
    # Maya's errors
    for kw, msg in (({"x": False, "y": False, "z": False}, c199.MSG_AXES_NONE), ({}, None)):
        _select(o)
        if msg:
            try:
                bpy.ops.allset.modify_constraint_axes(**kw)
                raise AssertionError("no error")
            except RuntimeError as ex:
                assert msg in str(ex)
    u = _empty("free")
    _select(u)
    try:
        bpy.ops.allset.modify_constraint_axes()
        raise AssertionError("no error on an unconstrained object")
    except RuntimeError as ex:
        assert c199.MSG_AXES_INVALID in str(ex)
    for ob in bpy.context.scene.objects:
        ob.select_set(False)
    try:
        bpy.ops.allset.modify_constraint_axes()
        raise AssertionError("no error with nothing selected")
    except RuntimeError as ex:
        assert c199.MSG_AXES_SELECT in str(ex)


# --- maths units, undo, handlers ------------------------------------------------------------------------------

def test_quad_split_rule():
    sq = [(-1, 0, 0), (0, 0, -1), (1, 0, 0), (0, 0, 1)]
    assert c199.quad_split(sq) == ((0, 1, 3), (1, 2, 3))                    # tie -> 1-3 (Maya)
    q = [(-(1 - 6e-4), 0, 0), (0, 0, -1), (1 - 6e-4, 0, 0), (0, 0, 1)]      # 0-2 shorter by 6e-4: 0-2
    assert c199.quad_split(q) == ((0, 1, 2), (0, 2, 3))
    q = [(-(1 - 5e-4), 0, 0), (0, 0, -1), (1 - 5e-4, 0, 0), (0, 0, 1)]      # by 5e-4: still 1-3
    assert c199.quad_split(q) == ((0, 1, 3), (1, 2, 3))


def test_undo_removes_constraint_and_helper():
    _fresh()
    targets = _maya_targets()
    loc = _empty("u", maya_xform((8, 3, 2)))
    _select(targets["smooth_sphere"], loc)
    bpy.ops.ed.undo_push(message="before")
    assert bpy.ops.allset.normal_constraint('EXEC_DEFAULT', True) == {'FINISHED'}
    assert any(o.get(c199.KIND) for o in bpy.data.objects)
    bpy.ops.ed.undo()
    loc = bpy.data.objects["u"]
    assert not loc.constraints and not any(o.get(c199.KIND) for o in bpy.data.objects)
    bpy.context.view_layer.update()            # the handler copes with the vanished helper
    c199.update()


def test_handlers_registered_with_the_kit():
    assert c199._on_depsgraph in bpy.app.handlers.depsgraph_update_post
    assert c199._on_frame in bpy.app.handlers.frame_change_post
    kit.disable()
    try:
        assert c199._on_depsgraph not in bpy.app.handlers.depsgraph_update_post
        assert c199._on_frame not in bpy.app.handlers.frame_change_post
    finally:
        kit.enable()


DATA = {'axis': {'orient_0': {'all_again': {'r': [0.0, 50.0, 45.0], 's': [1.5, 1.5, 1.5], 't': [1.0, 1.0, 1.0]},
                       'constrained': {'r': [10.0, 30.0, 20.0], 's': [1.5, 1.5, 1.5], 't': [1.0, 1.0, 1.0]},
                       'skip_y': {'r': [10.0, 30.0, 20.0], 's': [1.5, 1.5, 1.5], 't': [1.0, 1.0, 1.0]},
                       'target_moved': {'r': [0.0, 30.0, 45.0], 's': [1.5, 1.5, 1.5], 't': [1.0, 1.0, 1.0]}},
          'orient_1': {'all_again': {'r': [0.0, 30.0, 45.0], 's': [1.5, 1.5, 1.5], 't': [1.0, 1.0, 1.0]},
                       'constrained': {'r': [10.0, 30.0, 20.0], 's': [1.5, 1.5, 1.5], 't': [1.0, 1.0, 1.0]},
                       'skip_y': {'r': [10.0, 30.0, 20.0], 's': [1.5, 1.5, 1.5], 't': [1.0, 1.0, 1.0]},
                       'target_moved': {'r': [0.0, 30.0, 45.0], 's': [1.5, 1.5, 1.5], 't': [1.0, 1.0, 1.0]}},
          'parent_0': {'all_again': {'r': [-6.809073935, 24.112491017, 35.419950329],
                                     's': [1.5, 1.5, 1.5],
                                     't': [-3.0, 5.0, 2.0]},
                       'constrained': {'r': [5.0, 6.0, 7.0], 's': [1.5, 1.5, 1.5], 't': [1.0, 1.0, 1.0]},
                       'skip_y': {'r': [5.0, 6.0, 7.0], 's': [1.5, 1.5, 1.5], 't': [4.0, 1.0, -1.0]},
                       'target_moved': {'r': [-6.809073935, 6.0, 35.419950329],
                                        's': [1.5, 1.5, 1.5],
                                        't': [-3.0, 1.0, 2.0]}},
          'parent_1': {'all_again': {'r': [-6.809073935, 24.112491017, 35.419950329],
                                     's': [1.5, 1.5, 1.5],
                                     't': [-3.982664654, 4.332319457, 3.460335052]},
                       'constrained': {'r': [5.0, 6.0, 7.0], 's': [1.5, 1.5, 1.5], 't': [1.0, 1.0, 1.0]},
                       'skip_y': {'r': [5.0, 6.0, 7.0], 's': [1.5, 1.5, 1.5], 't': [1.0, 1.0, 1.0]},
                       'target_moved': {'r': [-6.809073935, 6.0, 35.419950329],
                                        's': [1.5, 1.5, 1.5],
                                        't': [-3.982664654, 1.0, 3.460335052]}},
          'point_0': {'all_again': {'r': [5.0, 6.0, 7.0], 's': [1.5, 1.5, 1.5], 't': [-3.0, 5.0, 2.0]},
                      'constrained': {'r': [5.0, 6.0, 7.0], 's': [1.5, 1.5, 1.5], 't': [4.0, 2.0, -1.0]},
                      'skip_y': {'r': [5.0, 6.0, 7.0], 's': [1.5, 1.5, 1.5], 't': [4.0, 2.0, -1.0]},
                      'target_moved': {'r': [5.0, 6.0, 7.0], 's': [1.5, 1.5, 1.5], 't': [-3.0, 2.0, 2.0]}},
          'point_1': {'all_again': {'r': [5.0, 6.0, 7.0], 's': [1.5, 1.5, 1.5], 't': [-3.0, 2.0, 2.0]},
                      'constrained': {'r': [5.0, 6.0, 7.0], 's': [1.5, 1.5, 1.5], 't': [4.0, 2.0, -1.0]},
                      'skip_y': {'r': [5.0, 6.0, 7.0], 's': [1.5, 1.5, 1.5], 't': [4.0, 2.0, -1.0]},
                      'target_moved': {'r': [5.0, 6.0, 7.0], 's': [1.5, 1.5, 1.5], 't': [-3.0, 2.0, 2.0]}},
          'scale_0': {'all_again': {'r': [5.0, 6.0, 7.0], 's': [0.0, 0.0, 0.0], 't': [1.0, 1.0, 1.0]},
                      'constrained': {'r': [5.0, 6.0, 7.0], 's': [2.0, 1.0, 3.0], 't': [1.0, 1.0, 1.0]},
                      'skip_y': {'r': [5.0, 6.0, 7.0], 's': [0.0, 0.0, 0.0], 't': [1.0, 1.0, 1.0]},
                      'target_moved': {'r': [5.0, 6.0, 7.0], 's': [0.0, 0.0, 0.0], 't': [1.0, 1.0, 1.0]}},
          'scale_1': {'all_again': {'r': [5.0, 6.0, 7.0], 's': [1.0, 1.0, 1.0], 't': [1.0, 1.0, 1.0]},
                      'constrained': {'r': [5.0, 6.0, 7.0], 's': [2.0, 1.0, 3.0], 't': [1.0, 1.0, 1.0]},
                      'skip_y': {'r': [5.0, 6.0, 7.0], 's': [2.0, 1.0, 3.0], 't': [1.0, 1.0, 1.0]},
                      'target_moved': {'r': [5.0, 6.0, 7.0], 's': [1.0, 1.0, 1.0], 't': [1.0, 1.0, 1.0]}}},
 'hard_verts': {0: [1.657068014, -4.61939764, 19.04329133], 46: [4.330126762, 0.0, 22.5], 85: [0.0, 5.0, 20.0]},
 'normal': [{'matrix': [0.906075682, 0.307702952, 0.2904234, 0.0, -0.293018706, 0.951482471, -0.09392095, 0.0,
                        -0.305232528, 0.0, 0.95227785, 0.0, 8.0, 3.0, 2.0, 1.0],
             'pos': [8, 3, 2],
             'start_rot': [0, 0, 0],
             'target': 'smooth_sphere'},
            {'matrix': [0.153161018, 0.85912647, -0.488306678, 0.0, -0.257120189, 0.511763333, 0.819748437, 0.0,
                        0.954165033, 0.0, 0.299280954, 0.0, 1.0, 7.0, -4.0, 1.0],
             'pos': [1, 7, -4],
             'start_rot': [30, 40, 50],
             'target': 'smooth_sphere'},
            {'matrix': [-0.776944631, -0.254304912, 0.575921915, 0.0, -0.204297295, 0.967124093, 0.151438448, 0.0,
                        -0.595499501, 0.0, -0.803355677, 0.0, -6.0, -2.0, 5.0, 1.0],
             'pos': [-6, -2, 5],
             'start_rot': [0, 0, 0],
             'target': 'smooth_sphere'},
            {'matrix': [0.682614398, 0.643583835, 0.346175433, 0.0, -0.573992139, 0.765375625, -0.291089637, 0.0,
                        -0.452294823, 0.0, 0.891868484, 0.0, 1.0, 1.0, 0.5, 1.0],
             'pos': [1, 1, 0.5],
             'start_rot': [0, 0, 0],
             'target': 'smooth_sphere'},
            {'matrix': [0.00937247, -0.999932891, 0.006809604, 0.0, 0.808958331, 0.011585072, 0.587751822, 0.0,
                        -0.587791268, 0.0, 0.809012624, 0.0, 0.3, -9.0, 0.2, 1.0],
             'pos': [0.3, -9, 0.2],
             'start_rot': [0, 0, 0],
             'target': 'smooth_sphere'},
            {'matrix': [0.948575787, 0.188683553, 0.254170206, 0.0, -0.182254312, 0.982037941, -0.048834913, 0.0,
                        -0.258819131, 0.0, 0.965925803, 0.0, 6.0, 2.0, 22.0, 1.0],
             'pos': [6, 2, 22],
             'start_rot': [0, 0, 0],
             'target': 'hard_sphere'},
            {'matrix': [-0.402272863, -0.822406973, -0.402272687, 0.0, -0.581529675, 0.568899614, -0.58152942, 0.0,
                        0.707106626, -0.0, -0.707106936, 0.0, -3.0, -4.0, 18.0, 1.0],
             'pos': [-3, -4, 18],
             'start_rot': [30, 40, 50],
             'target': 'hard_sphere'},
            {'matrix': [0.142621297, 0.979447959, 0.142621391, 0.0, -0.692574063, 0.201697039, -0.692574524, 0.0,
                        -0.707107016, 0.0, 0.707106546, 0.0, 0.5, 7.0, 21.0, 1.0],
             'pos': [0.5, 7, 21],
             'start_rot': [0, 0, 0],
             'target': 'hard_sphere'},
            {'matrix': [-0.441669802, 0.889267754, -0.118872402, 0.0, 0.858709841, 0.457386994, 0.231115873, 0.0,
                        0.259894584, 0.0, -0.965636995, 0.0, 31.0, 4.0, 1.0, 1.0],
             'pos': [31, 4, 1],
             'start_rot': [0, 0, 0],
             'target': 'bent_plane'},
            {'matrix': [-0.385985623, 0.908999068, -0.157276171, 0.0, 0.84179974, 0.416798147, 0.343005107, 0.0,
                        0.377343739, -0.0, -0.926073271, 0.0, 34.0, 2.0, -3.0, 1.0],
             'pos': [34, 2, -3],
             'start_rot': [30, 40, 50],
             'target': 'bent_plane'},
            {'matrix': [0.253395138, 0.959905947, 0.119881099, 0.0, -0.867699529, 0.280322268, -0.410508166, 0.0,
                        -0.427654571, -0.0, 0.903942237, 0.0, 27.0, -3.0, 2.5, 1.0],
             'pos': [27, -3, 2.5],
             'start_rot': [0, 0, 0],
             'target': 'bent_plane'},
            {'matrix': [-0.609811523, 0.778971881, -0.146057232, 0.0, 0.757546161, 0.627058856, 0.181441464, 0.0,
                        0.232924279, -0.0, -0.972494874, 0.0, 33.7, 6.0, 4.1, 1.0],
             'pos': [33.7, 6, 4.1],
             'start_rot': [0, 0, 0],
             'target': 'bent_plane'},
            {'matrix': [0.92695184, 0.08632904, 0.229721234, 0.0, -0.071916233, 1.055110119, 0.204489383, 0.0,
                        -0.089382485, -0.404872893, 0.910830485, 0.0, 8.0, 3.0, 2.0, 1.0],
             'parent': [0.813797681, 0.46984631, -0.342020143, 0.0, -0.881939221, 1.765128239, 0.326351822, 0.0,
                        0.378522306, 0.018028311, 0.925416578, 0.0, 2.0, 1.0, -1.0, 1.0],
             'pos': [8, 3, 2],
             'start_rot': [0, 0, 0],
             'target': 'smooth_sphere'},
            {'matrix': [0.906075682, 0.307702952, 0.2904234, 0.0, -0.293018706, 0.951482471, -0.09392095, 0.0,
                        -0.305232528, 0.0, 0.95227785, 0.0, 8.0, 3.0, 2.0, 1.0],
             'parent': [1.627595363, 0.939692621, -0.684040287, 0.0, -0.881939221, 1.765128239, 0.326351822, 0.0,
                        0.757044613, 0.036056622, 1.850833157, 0.0, 2.0, 1.0, -1.0, 1.0],
             'pos': [8, 3, 2],
             'start_rot': [0, 0, 0],
             'target': 'smooth_sphere'}],
 'plane_verts': {0: [25.0, 0.75, 5.0], 7: [30.0, 0.0, 2.5], 24: [35.0, 0.75, -5.0]},
 'remove': {'aim': {'after_all': [0.904534034, 0.301511345, -0.301511345, 0.0, -0.286038777, 0.953462589, 0.095346259,
                                  0.0, 0.316227766, 0.0, 0.948683298, 0.0, 1.0, 1.0, 1.0, 1.0],
                    'after_one': [0.904534034, 0.301511345, -0.301511345, 0.0, -0.286038777, 0.953462589, 0.095346259,
                                  0.0, 0.316227766, 0.0, 0.948683298, 0.0, 1.0, 1.0, 1.0, 1.0]},
            'orient': {'after_all': [0.866025404, 0.0, -0.5, 0.0, 0.0, 1.0, 0.0, 0.0, 0.5, 0.0, 0.866025404, 0.0, 1.0,
                                     1.0, 1.0, 1.0],
                       'after_one': [0.866025404, 0.0, -0.5, 0.0, 0.0, 1.0, 0.0, 0.0, 0.5, 0.0, 0.866025404, 0.0, 1.0,
                                     1.0, 1.0, 1.0]},
            'parent': {'after_all': [0.866025404, 0.0, -0.5, 0.0, 0.0, 1.0, 0.0, 0.0, 0.5, 0.0, 0.866025404, 0.0, 4.0,
                                     2.0, 0.0, 1.0],
                       'after_one': [0.866025404, 0.0, -0.5, 0.0, 0.0, 1.0, 0.0, 0.0, 0.5, 0.0, 0.866025404, 0.0, 4.0,
                                     2.0, 0.0, 1.0]},
            'point': {'after_all': [0.98710888, 0.12120173, -0.104528463, 0.0, -0.112363244, 0.989879475, 0.086678294,
                                    0.0, 0.11397614, -0.073815757, 0.990737439, 0.0, 4.0, 2.0, 0.0, 1.0],
                      'after_one': [0.98710888, 0.12120173, -0.104528463, 0.0, -0.112363244, 0.989879475, 0.086678294,
                                    0.0, 0.11397614, -0.073815757, 0.990737439, 0.0, 4.0, 2.0, 0.0, 1.0]},
            'scale': {'after_all': [1.97421776, 0.242403461, -0.209056927, 0.0, -0.224726489, 1.97975895, 0.173356589,
                                    0.0, 0.227952279, -0.147631514, 1.981474879, 0.0, 1.0, 1.0, 1.0, 1.0],
                      'after_one': [1.97421776, 0.242403461, -0.209056927, 0.0, -0.224726489, 1.97975895, 0.173356589,
                                    0.0, 0.227952279, -0.147631514, 1.981474879, 0.0, 1.0, 1.0, 1.0, 1.0]}},
 'rest': {'orient': {'moved': {'r': [0.0, 0.0, 45.0], 's': [1.0, 1.0, 1.0], 't': [1.0, 1.0, 1.0]},
                     'w0_after_rest': [0.866025404, 0.0, -0.5, 0.0, 0.086824089, 0.984807753, 0.150383733, 0.0,
                                       0.492403877, -0.173648178, 0.852868532, 0.0, 1.0, 1.0, 1.0, 1.0]},
          'parent': {'moved': {'r': [0.0, 0.0, 45.0], 's': [1.0, 1.0, 1.0], 't': [-3.0, 5.0, 2.0]},
                     'w0_after_rest': [0.866025404, 0.0, -0.5, 0.0, 0.086824089, 0.984807753, 0.150383733, 0.0,
                                       0.492403877, -0.173648178, 0.852868532, 0.0, 4.0, 2.0, -1.0, 1.0]},
          'point': {'moved': {'r': [5.0, 6.0, 7.0], 's': [1.0, 1.0, 1.0], 't': [-3.0, 5.0, 2.0]},
                    'w0_after_rest': [0.98710888, 0.12120173, -0.104528463, 0.0, -0.112363244, 0.989879475,
                                      0.086678294, 0.0, 0.11397614, -0.073815757, 0.990737439, 0.0, 4.0, 2.0, -1.0,
                                      1.0]},
          'scale': {'moved': {'r': [5.0, 6.0, 7.0], 's': [1.0, 1.0, 1.0], 't': [1.0, 1.0, 1.0]},
                    'w0_after_rest': [1.97421776, 0.242403461, -0.209056927, 0.0, -0.112363244, 0.989879475,
                                      0.086678294, 0.0, 0.341928419, -0.221447271, 2.972212318, 0.0, 1.0, 1.0, 1.0,
                                      1.0]}},
 'sphere_verts': {0: [0.743890643, -4.938441753, -0.241704702],
                  238: [4.522542953, 1.545084834, 1.469463229],
                  259: [4.455032825, 2.269952536, 0.0],
                  380: [0.0, -5.0, 0.0],
                  381: [0.0, 5.0, 0.0]},
 'tangent': [{'circle': False,
              'matrix': [0.951668903, 0.253072211, 0.174013663, 0.0, -0.248944754, 0.967447392, -0.045519811, 0.0,
                         -0.179868863, -0.0, 0.983690598, 0.0, 2.0, 3.0, 1.0, 1.0],
              'pos': [2, 3, 1]},
             {'circle': False,
              'matrix': [0.942603926, -0.32513561, -0.076057038, 0.0, 0.324082338, 0.945667402, -0.026149629, 0.0,
                         0.080426837, 0.0, 0.996760515, 0.0, 6.0, 1.0, 3.0, 1.0],
              'pos': [6, 1, 3]},
             {'circle': False,
              'matrix': [0.979652008, -0.186039305, -0.075308162, 0.0, 0.185492043, 0.982542303, -0.014259211, 0.0,
                         0.076646228, 0.0, 0.997058351, 0.0, 10.0, 4.0, -2.0, 1.0],
              'pos': [10, 4, -2]},
             {'circle': False,
              'matrix': [0.6, 0.8, 0.0, 0.0, -0.8, 0.6, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, -2.0, -1.0, 0.5, 1.0],
              'pos': [-2, -1, 0.5]},
             {'circle': False,
              'matrix': [0.688247202, -0.688247202, 0.229415734, 0.0, 0.652928625, 0.72547625, 0.217642875, 0.0,
                         -0.316227766, -0.0, 0.948683298, 0.0, 13.0, 1.0, 1.0, 1.0],
              'pos': [13, 1, 1]},
             {'circle': False,
              'matrix': [0.938346267, 0.169251226, -0.301430432, 0.0, -0.161141047, 0.985572941, 0.051764276, 0.0,
                         0.305842845, -0.0, 0.95208201, 0.0, 7.0, -3.0, 0.0, 1.0],
              'pos': [7, -3, 0]},
             {'circle': True,
              'matrix': [0.199516468, 0.0, -0.979894473, 0.0, 0.0, 1.0, 0.0, 0.0, 0.979894473, 0.0, 0.199516468, 0.0,
                         5.0, 1.0, 31.0, 1.0],
              'pos': [5, 1, 31]},
             {'circle': True,
              'matrix': [-0.834755324, 0.0, 0.550621057, 0.0, 0.0, 1.0, 0.0, 0.0, -0.550621057, 0.0, -0.834755324,
                         0.0, -2.0, -1.0, 27.0, 1.0],
              'pos': [-2, -1, 27]},
             {'circle': True,
              'matrix': [0.994730752, 0.0, -0.102521859, 0.0, 0.0, 1.0, 0.0, 0.0, 0.102521859, 0.0, 0.994730752, 0.0,
                         0.5, 2.0, 35.0, 1.0],
              'pos': [0.5, 2, 35]}],
 'tangent_circle': [[3.1344465, 0.0, 26.8655535], [0.0, 0.0, 25.56722325], [-3.1344465, 0.0, 26.8655535],
                    [-4.43277675, 0.0, 30.0], [-3.1344465, -0.0, 33.1344465], [-0.0, -0.0, 34.43277675],
                    [3.1344465, -0.0, 33.1344465], [4.43277675, -0.0, 30.0]],
 'tangent_curve': [[0, 0, 0], [3, 4, 0], [6, -2, 2], [9, 3, -1], [12, 0, 0]]}
