"""Lane A (Issue #138): Constrain > Motion Paths > Attach to Motion Path / Set Motion Path Key
(operators/motion_path_228.py).

Expected (rows =
[frame, world translate, rotate XYZ deg, uValue], path = 5 CV cubic, Time Slider 1-120). SETKEY_KNOTS / SETKEY_CVS = the
path after ``SetKeyPath`` at frame 50. Maya Y-up (x, y, z) -> Blender
(x, -z, y) x maya_unit (1 in the factory m scene). The values are written here."""

import math
from importlib import import_module

import bpy
from mathutils import Euler, Matrix, Vector

import kit

mp = import_module(kit.MODULE + ".operators.motion_path_228")
units = import_module(kit.MODULE + ".operators.units")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
option_windows = import_module(kit.MODULE + ".operators.option_windows")

PATH = [[0, 0, 0], [5, 0, 5], [10, 0, 0], [15, 0, -5], [20, 0, 0]]
DEFAULT = [[1, [0.0, 0.0, 0.0], [-0.0, -45.0, 0.0], 0.0],
           [8, [0.168173, 0.0, 0.166274], [-0.0, -44.342934, 0.0], 0.009974],
           [15, [0.656131, 0.0, 0.626571], [-0.0, -42.25661, 0.0], 0.038266],
           [22, [1.454553, 0.0, 1.303814], [-0.0, -38.155562, 0.0], 0.082434],
           [30, [2.767316, 0.0, 2.186326], [-0.0, -28.889578, 0.0], 0.14922],
           [37, [4.306824, 0.0, 2.788487], [-0.0, -12.380891, 0.0], 0.219184],
           [45, [6.408754, 0.0, 2.687769], [0.0, 18.242034, -0.0], 0.309041],
           [52, [8.147477, 0.0, 1.710334], [0.0, 37.891791, -0.0], 0.393586],
           [60, [9.894338, 0.0, 0.105634], [0.0, 44.977254, -0.0], 0.493698],
           [67, [11.398869, 0.0, -1.336141], [0.0, 40.971864, 0.0], 0.581607],
           [75, [13.328489, 0.0, -2.59164], [0.0, 21.902893, 0.0], 0.679155],
           [82, [15.187575, 0.0, -2.868562], [0.0, -5.489291, -0.0], 0.759213],
           [90, [17.036002, 0.0, -2.291054], [0.0, -27.156955, -0.0], 0.84138],
           [97, [18.258916, 0.0, -1.522173], [0.0, -36.433717, -0.0], 0.902372],
           [105, [19.248842, 0.0, -0.712246], [0.0, -41.816318, -0.0], 0.956339],
           [112, [19.781237, 0.0, -0.215541], [0.0, -44.13938, -0.0], 0.987049],
           [120, [20.0, 0.0, 0.0], [0.0, -45.0, -0.0], 1.0], [130, [20.0, 0.0, 0.0], [0.0, -45.0, -0.0], 1.0]]
SETKEY_KEYS = [[1.0, 50.0, 120.0], [0.0, 0.370764, 1.0]]
SETKEY = [[1, [0.0, 0.0, 0.0], [-0.0, -45.0, 0.0], 0.0],
          [8, [0.226143, 0.0, 0.223233], [-0.0, -44.247366, 0.0], 0.013335],
          [15, [0.855181, 0.0, 0.811737], [-0.0, -41.840782, 0.0], 0.049495],
          [22, [1.832601, 0.0, 1.61876], [-0.0, -36.910408, 0.0], 0.10271],
          [30, [3.337976, 0.0, 2.544275], [-0.0, -24.894467, 0.0], 0.177013],
          [37, [4.946631, 0.0, 2.97695], [0.0, -3.250699, -0.0], 0.247353],
          [45, [6.762824, 0.0, 2.596304], [0.0, 25.448682, -0.0], 0.326091],
          [52, [8.008208, 0.0, 1.80539], [0.0, 37.775449, 0.0], 0.388136],
          [60, [9.424299, 0.0, 0.558597], [0.0, 43.731074, -0.0], 0.467359],
          [67, [10.768254, 0.0, -0.745755], [0.0, 43.558047, 0.0], 0.54597],
          [75, [12.516435, 0.0, -2.18052], [0.0, 32.640915, 0.0], 0.641035],
          [82, [14.348944, 0.0, -2.895228], [0.0, 7.479669, -0.0], 0.724276],
          [90, [16.442779, 0.0, -2.5914], [0.0, -21.79925, -0.0], 0.814081],
          [97, [17.889699, 0.0, -1.797811], [0.0, -34.452023, -0.0], 0.883485],
          [105, [19.078553, 0.0, -0.865687], [0.0, -41.216361, -0.0], 0.946925],
          [112, [19.728524, 0.0, -0.266802], [0.0, -43.989011, -0.0], 0.984028],
          [120, [20.0, 0.0, 0.0], [0.0, -45.0, -0.0], 1.0], [130, [20.0, 0.0, 0.0], [0.0, -45.0, -0.0], 1.0]]
PARAMETRIC = [[1, [0.0, 0.0, 0.0], [-0.0, -45.0, 0.0], 0.0],
              [8, [0.296242, 0.0, 0.290313], [-0.0, -43.822154, 0.0], 0.019947],
              [15, [1.105167, 0.0, 1.019552], [-0.0, -40.067128, 0.0], 0.076532],
              [22, [2.280372, 0.0, 1.895053], [-0.0, -32.761935, 0.0], 0.164869],
              [30, [3.875049, 0.0, 2.671961], [-0.0, -17.711979, 0.0], 0.298439],
              [37, [5.344872, 0.0, 2.883571], [0.0, 2.338084, 0.0], 0.438368],
              [45, [6.996355, 0.0, 2.446578], [0.0, 26.142998, -0.0], 0.618083],
              [52, [8.37969, 0.0, 1.523908], [0.0, 39.579456, -0.0], 0.787172],
              [60, [9.905459, 0.0, 0.094521], [0.0, 44.981791, -0.0], 0.987395],
              [67, [11.234972, 0.0, -1.191494], [0.0, 41.867014, 0.0], 1.163214],
              [75, [12.802328, 0.0, -2.342309], [0.0, 28.585369, 0.0], 1.35831],
              [82, [14.236537, 0.0, -2.843183], [0.0, 8.6803, -0.0], 1.518426],
              [90, [15.91639, 0.0, -2.733629], [0.0, -15.204953, -0.0], 1.68276],
              [97, [17.338482, 0.0, -2.126863], [0.0, -29.780108, -0.0], 1.804744],
              [105, [18.745706, 0.0, -1.143249], [0.0, -39.27508, -0.0], 1.912679],
              [112, [19.616467, 0.0, -0.373557], [0.0, -43.456616, -0.0], 1.974099],
              [120, [20.0, 0.0, 0.0], [0.0, -45.0, -0.0], 2.0], [130, [20.0, 0.0, 0.0], [0.0, -45.0, -0.0], 2.0]]
PATH_3D = [[0, 0, 0], [5, 4, 5], [10, -2, 0], [15, 3, -5], [20, 0, 0]]
ROWS_3D = [[1, [0.0, 0.0, 0.0], [-26.214065, -37.985167, 38.659808], 0.0],
           [8, [0.151981, 0.120038, 0.150431], [-25.482207, -37.686647, 37.939494], 0.009974],
           [15, [0.595338, 0.452184, 0.571069], [-23.22725, -36.688755, 35.689847], 0.038266],
           [22, [1.329482, 0.940588, 1.204286], [-19.09574, -34.513146, 31.425523], 0.082434],
           [30, [2.567186, 1.576766, 2.072032], [-11.201373, -28.609291, 22.468392], 0.14922],
           [37, [4.086915, 2.005193, 2.734525], [-2.175865, -15.010905, 8.345446], 0.219184],
           [45, [6.25318, 1.904122, 2.735706], [-3.523963, 15.612964, -12.888199], 0.309041],
           [52, [8.011836, 1.329125, 1.813863], [-12.357101, 34.940711, -20.932798], 0.393586],
           [60, [9.788625, 0.777463, 0.211151], [-6.355587, 44.552397, -9.021251], 0.493698],
           [67, [11.339569, 0.829643, -1.284334], [6.720949, 40.855799, 10.212063], 0.581607],
           [75, [13.2962, 1.270997, -2.578515], [4.446771, 21.914686, 11.770006], 0.679155],
           [82, [15.207333, 1.490122, -2.866614], [-0.010267, -5.770127, 0.102121], 0.759213],
           [90, [17.101228, 1.253175, -2.25717], [6.534453, -27.021926, -14.150358], 0.84138],
           [97, [18.316295, 0.851531, -1.47954], [13.049172, -34.70846, -22.14858], 0.902372],
           [105, [19.279309, 0.404128, -0.684922], [17.985532, -38.571501, -27.505189], 0.956339],
           [112, [19.790867, 0.123133, -0.20619], [20.39616, -40.080143, -30.005907], 0.987049],
           [120, [20.0, 0.0, 0.0], [21.333963, -40.612855, -30.963757], 1.0],
           [130, [20.0, 0.0, 0.0], [21.333963, -40.612855, -30.963757], 1.0]]
SETKEY_KNOTS = [0.0, 0.0, 0.0, 0.719319, 1.0, 2.0, 2.0, 2.0]
SETKEY_CVS = [[0.0, 0.0, 0.0], [3.596594, 0.0, 3.596594], [6.459033, 0.0, 3.435153], [12.03417, 0.0, -1.960603],
              [15.0, 0.0, -5.0], [20.0, 0.0, 0.0]]

C = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))     # Maya world -> Blender world
POS_TOL = 1e-4
ROT_TOL = 1e-3      # degrees


def m2b(p):
    return Vector((p[0], -p[2], p[1])) * units.maya_unit()


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for cu in list(bpy.data.curves):
        bpy.data.curves.remove(cu)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end, sc.use_preview_range = 1, 120, False
    sc.frame_set(1)


def _scene(points=PATH, car_pos=(0, 0, 0), car_rot=(0, 0, 0)):
    _clear()
    k = units.maya_unit()
    cu = bpy.data.curves.new("curveShape1", 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('NURBS')
    sp.points.add(len(points) - 1)
    for p, v in zip(sp.points, points):
        p.co = (*m2b(v), 1.0)
    sp.order_u, sp.use_endpoint_u, sp.resolution_u = 4, True, 12
    path = bpy.data.objects.new("path", cu)
    car = bpy.data.objects.new("car", bpy.data.meshes.new("carShape"))
    for ob in (path, car):
        bpy.context.scene.collection.objects.link(ob)
    car.location = m2b(car_pos)
    car.rotation_euler = (math.radians(car_rot[0]), -math.radians(car_rot[2]), math.radians(car_rot[1]))
    car.select_set(True)
    path.select_set(True)
    bpy.context.view_layer.objects.active = car
    assert abs(k - 1.0) < 1e-12, k
    return path, car


def _rot_err(ob, r):
    """Angle (deg) between the object's world rotation and Maya's rotate XYZ (converted to Blender axes)."""
    rm = Euler([math.radians(a) for a in r], 'XYZ').to_matrix()
    want = C @ rm @ C.transposed()
    q = (want.transposed() @ ob.matrix_world.to_3x3().normalized()).to_quaternion()
    return math.degrees(2 * math.asin(min(1.0, Vector(q[1:]).length)))


def _compare(ob, rows, rot=True):
    sc = bpy.context.scene
    ep = er = 0.0
    for f, t, r, _u in rows:
        sc.frame_set(f)
        ep = max(ep, (ob.matrix_world.to_translation() - m2b(t)).length)
        if rot:
            er = max(er, _rot_err(ob, r))
    sc.frame_set(1)
    return ep, er


def _attach(**kw):
    res = bpy.ops.allset.motion_path_attach('EXEC_DEFAULT', **kw)
    assert res == {'FINISHED'}, res
    car = bpy.data.objects["car"]
    c = mp.find(car)
    assert c is not None and c.type == 'FOLLOW_PATH'
    return car, c


def test_menu_and_window():
    assert menu_map.MAP["Constrain/Motion Paths/Attach to Motion Path"] == "allset.motion_path_attach"
    assert menu_map.MAP["Constrain/Motion Paths/Set Motion Path Key"] == "allset.motion_path_key"
    w = option_windows.find_path("Constrain/Motion Paths/Attach to Motion Path")
    assert w is not None and w.title == "Attach to Motion Path Options" and w.action == "Attach", w
    d = w.defaults()
    assert d == {"time_range": "Time Slider", "start_time": 1.0, "end_time": 30.0, "parametric": False,
                 "follow": True, "front_axis": "X", "up_axis": "Y", "inverse_up": False, "inverse_front": False}, d


def test_default_matches_maya():
    _scene()
    car, c = _attach()
    assert c.name == "motionPath1" and c.target.name == "path"
    assert c.use_fixed_location and c.use_curve_follow and c.forward_axis == 'FORWARD_X' and c.up_axis == 'UP_Z'
    fc = mp.offset_curve(car, c)
    keys = [tuple(kp.co) for kp in fc.keyframe_points]
    assert keys == [(1.0, 0.0), (120.0, 1.0)], keys
    assert fc.extrapolation == 'CONSTANT'
    for f, _t, _r, u in DEFAULT:
        assert abs(fc.evaluate(f) - u) < 1e-6, (f, fc.evaluate(f), u)
    ep, er = _compare(car, DEFAULT)
    print(f"mp_default: max position error {ep:.2e}, rotation {er:.2e} deg, resolution "
          f"{c.target.data.splines[0].resolution_u}")
    assert ep < POS_TOL and er < ROT_TOL, (ep, er)


def test_default_resolution_would_be_off():
    """Blender's path at the curve's own resolution 12 is far from Maya: the kit raises it (module docstring)."""
    path, car = _scene()
    c = car.constraints.new('FOLLOW_PATH')
    c.target, c.use_fixed_location, c.use_curve_follow = path, True, True
    for f, v in ((1, 0.0), (120, 1.0)):
        c.offset_factor = v
        car.keyframe_insert(c.path_from_id("offset_factor"), frame=f)
    ep, _er = _compare(car, DEFAULT, rot=False)
    print(f"resolution 12: max position error {ep:.2e}")
    assert ep > 1e-3, ep
    mp.prepare_path(path)
    assert path.data.splines[0].resolution_u == 256


def test_curve_first_and_own_transform_ignored():
    """Maya: the curve can be picked first (L8_motion_path_wrong_order); the object's own place and turn don't add
    (mp_offset / mp_rotated_obj = mp_default)."""
    path, car = _scene(car_pos=(2, 1, -3), car_rot=(0, 30, 0))
    bpy.context.view_layer.objects.active = path
    car, c = _attach()
    assert tuple(car.location) == (0.0, 0.0, 0.0) and tuple(car.rotation_euler) == (0.0, 0.0, 0.0)
    ep, er = _compare(car, DEFAULT)
    assert ep < POS_TOL and er < ROT_TOL, (ep, er)


def test_set_motion_path_key_at_50():
    _scene()
    car, c = _attach()
    bpy.context.scene.frame_set(50)
    res = bpy.ops.allset.motion_path_key('EXEC_DEFAULT')
    assert res == {'FINISHED'}, res
    mc = mp.maya_curve(bpy.data.objects["path"])
    dk = max(abs(a - b) for a, b in zip(mc.knots, SETKEY_KNOTS))
    assert len(mc.knots) == len(SETKEY_KNOTS) and dk < 1e-5, (mc.knots, SETKEY_KNOTS)
    dc = max((Vector(a) - m2b(b)).length for a, b in zip(mc.cvs, SETKEY_CVS))
    assert len(mc.cvs) == len(SETKEY_CVS) and dc < POS_TOL, (mc.cvs, dc)
    fc = mp.offset_curve(car, c)
    frames = [kp.co[0] for kp in fc.keyframe_points]
    values = [kp.co[1] for kp in fc.keyframe_points]
    assert frames == SETKEY_KEYS[0], frames
    dv = max(abs(a - b) for a, b in zip(values, SETKEY_KEYS[1]))
    assert dv < 1e-5, (values, SETKEY_KEYS[1])
    du = max(abs(fc.evaluate(f) - u) for f, _t, _r, u in SETKEY)
    ep, er = _compare(car, SETKEY)
    print(f"mp_setkey50: knots {dk:.1e}, CVs {dc:.1e}, key value {dv:.1e}, u {du:.1e}, position {ep:.2e}, "
          f"rotation {er:.2e} deg")
    # the expected arc length is approximate: the exact (double) arc-length positions on the new curve differ from
    # the expected rows by up to 1.23e-4 (length 23.82464, exact 23.82537), so this case allows 1.5e-4 / 2e-3 deg
    assert du < 1e-5 and ep < 1.5e-4 and er < 2 * ROT_TOL, (du, ep, er)


def test_parametric():
    _scene()
    car, c = _attach(parametric=True)
    ep, er = _compare(car, PARAMETRIC)
    print(f"mp_parametric: max position error {ep:.2e}, rotation {er:.2e} deg")
    assert ep < POS_TOL and er < ROT_TOL, (ep, er)


def test_3d_path():
    _scene(points=PATH_3D)
    car, c = _attach()
    ep, er = _compare(car, ROWS_3D)
    sc = bpy.context.scene
    front = 0.0
    for f, _t, r, _u in ROWS_3D:
        sc.frame_set(f)
        want = C @ Euler([math.radians(a) for a in r], 'XYZ').to_matrix() @ Vector((1, 0, 0))
        got = car.matrix_world.to_3x3().normalized() @ Vector((1, 0, 0))
        front = max(front, math.degrees(want.angle(got, 0.0)))
    sc.frame_set(1)
    print(f"mp_3d: max position error {ep:.2e}; front axis {front:.2e} deg; rotation {er:.2f} deg "
          "(Blender's up roll vs the Maya world-up vector)")
    assert ep < POS_TOL and front < ROT_TOL * 10, (ep, front)
    assert er < 10.0, er


def test_axes_and_inverse_up():
    assert mp.axes("X", "Y") == ('FORWARD_X', 'UP_Z', None)
    assert mp.axes("X", "Z") == ('FORWARD_X', 'UP_Y', "X")
    assert mp.axes("Y", "X") == ('FORWARD_Z', 'UP_X', None)
    assert mp.axes("X", "X") is None
    _scene()
    car, c = _attach(inverse_up=True)
    bpy.context.scene.frame_set(60)
    m = car.matrix_world.to_3x3().normalized()
    assert (m @ Vector((0, 0, 1))).z < -0.999, m      # Maya up Y inverted = the object's Blender Z points down
    bpy.context.scene.frame_set(1)
    _scene()
    try:
        bpy.ops.allset.motion_path_attach('EXEC_DEFAULT', front_axis="Y", up_axis="Y")
    except RuntimeError as ex:      # an operator that reports ERROR raises in Python
        assert "must differ" in str(ex), ex
    else:
        raise AssertionError("same front and up axis attached")


def test_time_ranges():
    _scene()
    car, c = _attach(time_range='START_END', start_time=10.0, end_time=40.0)
    assert [tuple(k.co) for k in mp.offset_curve(car, c).keyframe_points] == [(10.0, 0.0), (40.0, 1.0)]
    _scene()
    sc = bpy.context.scene
    sc.use_preview_range, sc.frame_preview_start, sc.frame_preview_end = True, 5, 50
    car, c = _attach()
    assert [tuple(k.co) for k in mp.offset_curve(car, c).keyframe_points] == [(5.0, 0.0), (50.0, 1.0)]
    sc.use_preview_range = False


def test_selection_and_undo():
    _clear()
    car = bpy.data.objects.new("car", bpy.data.meshes.new("carShape"))
    bpy.context.scene.collection.objects.link(car)
    car.select_set(True)
    bpy.context.view_layer.objects.active = car
    assert bpy.ops.allset.motion_path_attach('EXEC_DEFAULT') == {'CANCELLED'}     # no curve
    assert bpy.ops.allset.motion_path_key('EXEC_DEFAULT') == {'CANCELLED'}        # not on a path
    _scene()
    bpy.ops.ed.undo_push(message="before path")
    assert bpy.ops.allset.motion_path_attach('EXEC_DEFAULT', True) == {'FINISHED'}
    assert mp.find(bpy.data.objects["car"]) is not None
    bpy.ops.ed.undo()
    car = bpy.data.objects["car"]
    assert mp.find(car) is None and len(car.constraints) == 0
    # attaching again replaces the kit path (one constraint, Maya numbers one past the highest)
    _scene()
    _attach()
    car, c = _attach()
    assert len(car.constraints) == 1 and c.name == "motionPath2", [x.name for x in car.constraints]


def test_unregister_removes_operators():
    kit.disable()
    try:
        assert not hasattr(bpy.types, "ALLSET_OT_motion_path_attach")
        assert not hasattr(bpy.types, "ALLSET_OT_motion_path_key")
    finally:
        kit.enable()
