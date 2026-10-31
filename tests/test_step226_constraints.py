"""Match Transformations to a joint, Maya multi-target constraints (weighted average), like Maya.

Expected results (the
values are in EXPECTED below). Scene: locators ctrl (1, 4.5, 0), ctrlB (-3, 4, 0),
obj (0, 4, 0) in Maya Y-up -> Blender (x, -z, y) x maya_unit(). Rotations: Maya XYZ Euler degrees, R_b = C R_m C^-1.
"""

import math
from importlib import import_module

import bpy
from mathutils import Euler, Matrix, Vector

import kit

multi = import_module(kit.MODULE + ".operators.constrain_multi")
snap = import_module(kit.MODULE + ".operators.snap_align")
units = import_module(kit.MODULE + ".operators.units")
cb = import_module(kit.MODULE + ".ui.channel_box")
joints = import_module(kit.MODULE + ".operators.joints")

TOL = 1e-4
C3 = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))      # Maya axes -> Blender axes

EXPECTED = {
    "orient": {"coaxial_equal": (0.0, 0.0, 15.0), "coaxial_w1_3": (0.0, 0.0, -0.26148),
               "skew_equal": (27.048397, 32.577252, 24.714866), "skew_w1_3": (18.464918, 48.151595, 9.316553)},
    "parent": {"start": (0.0, 4.0, 0.0), "a_x2": (1.0, 4.0, 0.0),
               "a_x2_rz90": (1.75, 3.75, 0.0, 0.0, 0.0, 45.0), "w1_3": (0.875, 3.875, 0.0, 0.0, 0.0, 21.598161),
               "w0_0": (0.0, 4.0, 0.0, 0.0, 0.0, 0.0)},
    "point": {"equal": (-1.0, 4.25, 0.0), "w1_3": (-2.0, 4.125, 0.0), "all_zero": (-1.0, 4.25, 0.0),
              "w0_half_only": (1.0, 4.5, 0.0)},
    "scale": {"equal": (1.414214, 2.44949, 1.414214), "w1_3": (1.189207, 2.710806, 1.189207)},
    # Maya matchTransform ctrl: joint at (5, 2, 1),
    # jointOrientZ 30 -> the matched ctrl t (5, 2, 1), r (0, 0, 30)
    "match": {"t": (5.0, 2.0, 1.0), "r": (0.0, 0.0, 30.0)},
}
DEVIATIONS = {}     # kit - Maya differences that are not faked (logged at the end)


def _u():
    return units.maya_unit()


def b_point(p):
    x, y, z = p
    return Vector((x, -z, y)) * _u()


def b_rot(deg):
    rm = Euler([math.radians(a) for a in deg], 'XYZ').to_matrix()
    return C3 @ rm @ C3.transposed()


def angle_between(r1, r2):
    return math.degrees(r1.to_quaternion().rotation_difference(r2.to_quaternion()).angle)


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)
    coll = bpy.data.collections.get(multi.HELPERS)
    if coll is not None:
        bpy.data.collections.remove(coll)


def _locator(name, maya_pos, maya_rot=(0, 0, 0)):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    _place(ob, maya_pos, maya_rot)
    return ob


def _place(ob, maya_pos=None, maya_rot=None, maya_scale=None):
    t, r, s = ob.matrix_world.decompose()
    if maya_pos is not None:
        t = b_point(maya_pos)
    if maya_rot is not None:
        r = b_rot(maya_rot).to_quaternion()
    if maya_scale is not None:
        sx, sy, sz = maya_scale
        s = Vector((sx, sz, sy))
    ob.matrix_world = Matrix.LocRotScale(t, r, s)
    bpy.context.view_layer.update()


def _select(*obs, active=None):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or obs[-1]


def two_ctrls():
    _clear()
    return _locator("ctrl", (1, 4.5, 0)), _locator("ctrlB", (-3, 4, 0)), _locator("obj", (0, 4, 0))


def _constrain(ctype, a, b, o, **kw):
    _select(a, b, o, active=o)
    assert bpy.ops.allset.constrain(type=ctype, **kw) == {'FINISHED'}
    bpy.context.view_layer.update()
    con = o.constraints[0]
    mb = multi.member(con)
    assert mb is not None, [c.name for c in o.constraints]
    return mb.group


def _weight(o, group, i, value):
    prop = multi.weights(o, group)[i][0]
    cb.set_value(o, cb.CUSTOM_PREFIX + prop, value)     # the Channel Box write (tags the ID: drivers update)
    bpy.context.view_layer.update()


def _check_pos(o, maya, what):
    got = o.matrix_world.translation
    want = b_point(maya[:3])
    assert (got - want).length < TOL * max(1.0, _u()), (what, tuple(got), tuple(want))


def _rot_dev(o, maya_rot):
    return angle_between(o.matrix_world.to_3x3().normalized(), b_rot(maya_rot))


# --- Point -----------------------------------------------------------------------------------------------------------

def test_point_two_targets_weighted_average():
    a, b, o = two_ctrls()
    g = _constrain('COPY_LOCATION', a, b, o)
    assert [c.type for c in o.constraints] == ['COPY_LOCATION', 'COPY_LOCATION']
    assert cb.constraint_node_name(o, o.constraints[1]) == "obj_pointConstraint1"
    assert [lab for _p, lab in multi.weights(o, g)] == ["ctrlW0", "ctrlBW1"]
    assert cb.weight_name(o.constraints[1]) == "ctrlBW1"
    fc = o.animation_data.drivers.find(f'constraints["{o.constraints[1].name}"].influence')
    assert fc is not None and fc.driver.is_simple_expression, fc and fc.driver.expression
    _check_pos(o, EXPECTED["point"]["equal"], "equal")
    _weight(o, g, 1, 3.0)
    _check_pos(o, EXPECTED["point"]["w1_3"], "w1_3")
    _weight(o, g, 0, 0.0)
    _weight(o, g, 1, 0.0)
    _check_pos(o, EXPECTED["point"]["all_zero"], "all_zero")
    _weight(o, g, 0, 0.5)
    _check_pos(o, EXPECTED["point"]["w0_half_only"], "w0_half_only")


def test_three_targets_and_channel_box_rows():
    a, b, o = two_ctrls()
    c = _locator("ctrlC", (0, 0, 3))
    _select(a, b, c, o, active=o)
    assert bpy.ops.allset.constrain(type='COPY_LOCATION') == {'FINISHED'}
    bpy.context.view_layer.update()
    want = (b_point((1, 4.5, 0)) + b_point((-3, 4, 0)) + b_point((0, 0, 3))) / 3
    assert (o.matrix_world.translation - want).length < TOL, tuple(o.matrix_world.translation)
    g = multi.member(o.constraints[0]).group
    _weight(o, g, 2, 2.0)
    want = (b_point((1, 4.5, 0)) + b_point((-3, 4, 0)) + 2 * b_point((0, 0, 3))) / 4
    assert (o.matrix_world.translation - want).length < TOL
    # Channel Box: one INPUTS node, its rows = the weights; weight props are not user attributes
    assert all(not k.startswith("allset_") for k in cb.custom_keys(o))
    cb.set_open(o, cb.con_node(o, o.constraints[0]), True) if hasattr(cb, "set_open") else \
        cb.open_nodes(o).add(cb.con_node(o, o.constraints[0]))
    rows = cb.wanted_rows(o)
    names = [n for k, n, _t, _i in rows if k == "CUSTOM"]
    assert names == [p for p, _l in multi.weights(o, g)], rows
    assert not [r for r in rows if r[0] == "CONSTRAINT"], rows
    heads = [con for con in o.constraints if multi.is_head(con, o)]
    assert len(heads) == 1
    # typed text on the weight row (Scene proxy) = Maya entry; drivers follow
    bpy.context.scene.allset_cb.rows_sig = ""
    cb.rebuild_rows()
    _select(o)
    row = next(r for r in bpy.context.scene.allset_cb.rows if r.name == names[0])
    cb.apply_row_entry(row, "0")
    bpy.context.view_layer.update()
    want = (b_point((-3, 4, 0)) + 2 * b_point((0, 0, 3))) / 3
    assert (o.matrix_world.translation - want).length < TOL, tuple(o.matrix_world.translation)
    # node state: every member at once
    assert bpy.ops.allset.constraint_group_enable(object=o.name, bone="", group=g) == {'FINISHED'}
    assert all(not con.enabled for con in o.constraints)
    bpy.context.view_layer.update()
    assert (o.matrix_world.translation - b_point((0, 4, 0))).length < TOL
    bpy.ops.allset.constraint_group_enable(object=o.name, bone="", group=g)
    assert all(con.enabled for con in o.constraints)


# --- Scale -----------------------------------------------------------------------------------------------------------

def _check_scale(o, maya, what):
    s = o.matrix_world.to_scale()
    got = (s.x, s.z, s.y)
    assert all(abs(g - w) < TOL for g, w in zip(got, maya)), (what, got, maya)


def test_scale_two_targets_geometric_mean():
    a, b, o = two_ctrls()
    g = _constrain('COPY_SCALE', a, b, o)
    _place(a, maya_scale=(2, 2, 2))
    _place(b, maya_scale=(1, 3, 1))
    _check_scale(o, EXPECTED["scale"]["equal"], "equal")
    _weight(o, g, 1, 3.0)
    _check_scale(o, EXPECTED["scale"]["w1_3"], "w1_3")


# --- Orient ----------------------------------------------------------------------------------------------------------

def test_orient_two_targets():
    a, b, o = two_ctrls()
    _place(a, maya_rot=(0, 0, 45))
    _place(b, maya_rot=(0, 0, -15))
    g = _constrain('COPY_ROTATION', a, b, o)
    dev = _rot_dev(o, EXPECTED["orient"]["coaxial_equal"])
    assert dev < 1e-3, dev
    _weight(o, g, 1, 3.0)
    DEVIATIONS["orient coaxial_w1_3 (deg)"] = _rot_dev(o, EXPECTED["orient"]["coaxial_w1_3"])
    assert DEVIATIONS["orient coaxial_w1_3 (deg)"] < 1.0
    _weight(o, g, 1, 1.0)
    _place(a, maya_rot=(30, 0, 45))
    _place(b, maya_rot=(0, 60, -15))
    DEVIATIONS["orient skew_equal (deg)"] = _rot_dev(o, EXPECTED["orient"]["skew_equal"])
    assert DEVIATIONS["orient skew_equal (deg)"] < 1e-3, DEVIATIONS
    _weight(o, g, 1, 3.0)
    DEVIATIONS["orient skew_w1_3 (deg)"] = _rot_dev(o, EXPECTED["orient"]["skew_w1_3"])
    assert DEVIATIONS["orient skew_w1_3 (deg)"] < 2.0, DEVIATIONS


# --- Parent ----------------------------------------------------------------------------------------------------------

def test_parent_two_targets_maintain_offset():
    a, b, o = two_ctrls()
    g = _constrain('CHILD_OF', a, b, o)
    # + the hidden Interp Type blend (Copy Rotation, not a Maya node)
    from bl_ext.user_default.allset.operators import constrain_interp as ci
    assert [c.type for c in o.constraints if not ci.is_blend(c)] == ['COPY_LOCATION', 'COPY_ROTATION'] * 2
    assert cb.constraint_node_name(o, o.constraints[3]) == "obj_parentConstraint1"
    assert cb.maya_constraint_type(o.constraints[1]) == "parentConstraint"
    hs = [h for h in multi.helpers() if ci.H_GROUP not in h.keys()]
    assert len(hs) == 2 and all(h.name not in bpy.context.scene.objects for h in multi.helpers())
    assert not any(h.parent for h in hs)         # helpers are no DAG children of the targets
    p = EXPECTED["parent"]
    _check_pos(o, p["start"], "start")
    _place(a, maya_pos=(3, 4.5, 0))
    _check_pos(o, p["a_x2"], "a_x2")
    _place(a, maya_rot=(0, 0, 90))
    _check_pos(o, p["a_x2_rz90"], "a_x2_rz90")
    assert _rot_dev(o, p["a_x2_rz90"][3:]) < 1e-3
    _weight(o, g, 1, 3.0)
    _check_pos(o, p["w1_3"], "w1_3")
    DEVIATIONS["parent w1_3 rotation (deg)"] = _rot_dev(o, p["w1_3"][3:])
    assert DEVIATIONS["parent w1_3 rotation (deg)"] < 1.0
    _weight(o, g, 0, 0.0)
    _check_pos(o, p["w0_0"], "w0_0")
    assert _rot_dev(o, p["w0_0"][3:]) < 1e-3
    # deleting the constrained object takes the helpers with it (Maya: the constraint node is its child)
    _select(o)
    assert bpy.ops.allset.delete() == {'FINISHED'}
    multi.cleanup()
    assert not multi.helpers()
    assert a.name in bpy.data.objects and b.name in bpy.data.objects


def test_option_window_weight_and_offset_on_group():
    a, b, o = two_ctrls()
    _select(a, b, o, active=o)
    # Point Constraint Options with Maintain offset: the object keeps its place, weights = the window's Weight
    assert bpy.ops.allset.constrain(type='COPY_LOCATION', maintain_offset='ON', weight=0.5) == {'FINISHED'}
    bpy.context.view_layer.update()
    g = multi.member(o.constraints[0]).group
    assert all(abs(o[p] - 0.5) < 1e-9 for p, _l in multi.weights(o, g))
    _check_pos(o, (0, 4, 0), "offset")
    _place(a, maya_pos=(3, 4.5, 0))              # ctrl x+2 with equal weights -> obj x+1
    _check_pos(o, (1, 4, 0), "offset follows")
    # removing the node removes constraints, drivers, weights and helpers
    multi.remove_group(o, g)
    assert not o.constraints and not [k for k in o.keys() if k.startswith(multi.WEIGHT)]
    multi.cleanup()
    assert not multi.helpers()


def test_cleared_constraints_drop_group():
    a, b, o = two_ctrls()
    g = _constrain('CHILD_OF', a, b, o)
    o.constraints.clear()                         # Delete by Type > Constraints / anything that clears the stack
    multi.cleanup()
    assert not multi.helpers()
    assert multi.GROUPS not in o.keys() and not [k for k in o.keys() if k.startswith(multi.WEIGHT)]
    assert not (o.animation_data and o.animation_data.drivers), g


def test_single_target_unchanged():
    a, b, o = two_ctrls()
    _select(a, o, active=o)
    assert bpy.ops.allset.constrain(type='COPY_LOCATION') == {'FINISHED'}
    assert len(o.constraints) == 1 and multi.member(o.constraints[0]) is None
    assert cb.weight_name(o.constraints[0]) == "ctrlW0"
    assert cb.constraint_node_name(o, o.constraints[0]) == "obj_pointConstraint1"


# --- pose bones -----------------------------------------------------------------------------------------------------

def _skeleton():
    """joint1 at Maya (5, 2, 1), jointOrientZ 30: the bone's Y (Maya X) and Z (Maya Y) turned 30 deg about Maya Z."""
    arm = joints.new_skeleton(bpy.context)
    joints.add_joint(arm, b_point((0, 0, 0)), None, length=0.5)
    joints.finish(bpy.context, arm, ["joint1"])
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones["joint1"]
    rot = b_rot((0, 0, 30))
    # bone X = Maya Z, bone Y = Maya X, bone Z = Maya Y (in Blender axes: (0,-1,0), (1,0,0), (0,0,1))
    b0 = Matrix(((0, 1, 0), (-1, 0, 0), (0, 0, 1)))
    m = (rot @ b0).to_4x4()
    m.translation = b_point(EXPECTED["match"]["t"])
    eb.matrix = m
    eb.length = 0.5
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()
    return arm


def test_match_transform_to_joint():
    _clear()
    arm = _skeleton()
    ctrl = _locator("ctrl_grp", (0, 0, 0))
    # Maya hand: the group first, the joint last (picking the joint enters Pose mode)
    _select(ctrl, arm, active=arm)
    bpy.ops.object.mode_set(mode='POSE')
    arm.data.bones.active = arm.data.bones["joint1"]
    assert bpy.ops.allset.match_transform(kind='ALL') == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    want = Matrix.LocRotScale(b_point(EXPECTED["match"]["t"]), b_rot(EXPECTED["match"]["r"]).to_quaternion(), None)
    got = ctrl.matrix_world
    assert (got.translation - want.translation).length < TOL, tuple(got.translation)
    assert angle_between(got.to_3x3(), want.to_3x3()) < 1e-3, ctrl.rotation_euler
    # object mode with the armature active: its active bone is the lead too
    ctrl.matrix_world = Matrix.Identity(4)
    _select(ctrl, arm, active=arm)
    assert bpy.ops.allset.match_transform(kind='TRANSLATE') == {'FINISHED'}
    assert (ctrl.matrix_world.translation - want.translation).length < TOL


def test_pose_bone_owner_two_targets():
    _clear()
    arm = _skeleton()
    a = _locator("ctrl", (1, 4.5, 0))
    b = _locator("ctrlB", (-3, 4, 0))
    _select(a, b, arm, active=arm)
    bpy.ops.object.mode_set(mode='POSE')
    pb = arm.pose.bones["joint1"]
    arm.data.bones.active = arm.data.bones["joint1"]
    cb.set_bone_selected(pb, True)
    assert bpy.ops.allset.constrain(type='COPY_LOCATION') == {'FINISHED'}
    assert not arm.constraints and len(pb.constraints) == 2
    g = multi.member(pb.constraints[0]).group
    bpy.context.view_layer.update()
    head = arm.matrix_world @ pb.head
    assert (head - b_point((-1, 4.25, 0))).length < TOL, tuple(head)
    _weight(pb, g, 1, 3.0)
    head = arm.matrix_world @ pb.head
    assert (head - b_point((-2, 4.125, 0))).length < TOL, tuple(head)
    assert cb.weight_name(pb.constraints[1]) == "ctrlBW1"
    assert cb.constraint_node_name(pb, pb.constraints[0]) == "joint1_pointConstraint1"
    # parent with offset on a joint: the helpers name the joint, follow the targets
    assert bpy.ops.allset.constrain(type='CHILD_OF') == {'FINISHED'}
    bpy.context.view_layer.update()
    from bl_ext.user_default.allset.operators import constrain_interp as ci
    hs = [h for h in multi.helpers() if ci.H_GROUP not in h.keys()]      # + the Interp Type blend helper
    assert len(hs) == 2 and all(h.get(multi.H_BONE) == "joint1" for h in multi.helpers())
    bpy.ops.object.mode_set(mode='OBJECT')


def test_unregister_leaves_no_handler():
    assert multi._on_depsgraph in bpy.app.handlers.depsgraph_update_post
    kit.disable()
    assert multi._on_depsgraph not in bpy.app.handlers.depsgraph_update_post
    assert multi._on_load not in bpy.app.handlers.load_post
    kit.enable()


def test_zz_report_deviations():
    print("STEP226 DEVIATIONS (kit - Maya, slerp vs nlerp):", {k: round(v, 5) for k, v in DEVIATIONS.items()})
