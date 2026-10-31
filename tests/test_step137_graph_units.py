"""Lane GRAPH (#66): the Graph Editor value numbers in display units. Blender's label step / format
(view2d_draw.cc ``select_major_distance`` / ``view_to_string__value``) reproduced bpy-free, the display labels for the
cm scene, the "every shown curve is a length" rule and the handler lifecycle.
GUI side (positions on Blender's grid lines, covering): tests/gui/gui_step137_graph_units.py."""

from importlib import import_module

import bpy

import kit

gu = import_module(kit.MODULE + ".ui.graph_units")


def test_major_step_like_blender():
    # 45 px x UI scale 1.25 minimum (factory view2d_grid_spacing_min): the issue's view, 0.059 BU over 645 px
    ppu = 645 / 0.0591
    assert gu.major_step(ppu, 45 * 1.25) == 0.01
    assert gu.major_step(ppu, 45 * 1.0) == 0.01        # the smallest Blender step
    assert gu.major_step(10.0, 56.25) == 10
    assert gu.major_step(1e-9, 56.25) == 100000
    assert gu.major_step(0, 56.25) == 0.01
    for d in gu.STEPS:
        assert gu.major_step(56.25 / d * 1.000001, 56.25) == d


def test_ticks_and_blender_labels():
    assert gu.tick_indices(-0.0039, 0.0552, 0.01) == [0, 1, 2, 3, 4, 5]
    assert gu.tick_indices(0.2, 0.1, 1) == []
    assert gu.blender_label(0.05, 0.01) == "0.05"
    assert gu.blender_label(5, 1) == "5"
    assert gu.blender_label(0.5, 0.5) == "0.5"
    assert gu.blender_label(0.002, 0.001) == "0.002"


def test_display_labels_cm():
    rows = gu.labels(-0.0039, 0.0552, 645 / 0.0591, 56.25, 0.01)
    assert [r[1] for r in rows] == ["0.00", "0.01", "0.02", "0.03", "0.04", "0.05"], rows
    assert [r[2] for r in rows] == ["0", "1", "2", "3", "4", "5"], rows
    # 3 x 0.01 / 0.01 = 2.9999...: rounded, not Blender's int() truncation
    assert gu.display_label(3, 0.01, 0.01) == "3"
    assert gu.display_label(-2, 0.01, 0.01) == "-2"
    assert gu.display_label(1, 0.02, 0.01) == "2"
    assert gu.display_label(1, 0.05, 0.001) == "50"            # mm
    assert gu.display_label(1, 0.01, 0.1) == "0.1"             # dm-like ratio keeps Blender's format
    assert gu.display_label(0, 0.5, 0.01) == "0"
    assert gu.display_label(0, 0.001, 0.1) == "0.00"                 # Blender keeps the decimals at 0
    assert gu.display_label(-0.0, 0.001, 0.1) == "0.00"
    # inch: 0.01 BU = 0.3937 in -> three significant digits, not "0"
    assert gu.display_label(1, 0.01, 0.0254) == "0.394"
    assert gu.display_label(2, 0.1, 0.0254) == "7.87"


def test_all_length_rule():
    assert gu.all_length(['LENGTH', 'LENGTH'])
    assert not gu.all_length([])
    assert not gu.all_length(['LENGTH', 'ROTATION'])
    assert not gu.all_length(['LENGTH', 'NONE'])           # scale
    assert not gu.all_length(['ROTATION'])


def test_curve_units_of_object_channels():
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ob["notes"] = 1.0
    for path in ("location", "rotation_euler", "scale", "delta_location"):
        ob.keyframe_insert(path, frame=1)
    ob.keyframe_insert('["notes"]', frame=1)
    fcs = list(kit.fcurves(ob))
    units = dict(zip(((fc.data_path, fc.array_index) for fc in fcs), gu.curve_units(fcs)))
    print("units", units)
    for i in range(3):
        assert units[("location", i)] == 'LENGTH'
        assert units[("delta_location", i)] == 'LENGTH'
        assert units[("rotation_euler", i)] == 'ROTATION'
        assert units[("scale", i)] == 'NONE'
    assert units[('["notes"]', 0)] == 'NONE'
    loc = [fc for fc in fcs if fc.data_path == "location"]
    rot = [fc for fc in fcs if fc.data_path == "rotation_euler"]
    assert gu.all_length(gu.curve_units(loc))
    assert not gu.all_length(gu.curve_units(loc + rot))


def test_curve_units_of_pose_bones():
    bpy.ops.object.armature_add()
    arm = bpy.context.active_object
    bpy.ops.object.mode_set(mode='POSE')
    pb = arm.pose.bones[0]
    pb.keyframe_insert("location", frame=1)
    pb.keyframe_insert("rotation_quaternion", frame=1)
    bpy.ops.object.mode_set(mode='OBJECT')
    fcs = list(kit.fcurves(arm))
    units = gu.curve_units(fcs)
    print("bone units", [(fc.data_path, u) for fc, u in zip(fcs, units)])
    assert [u for fc, u in zip(fcs, units) if fc.data_path.endswith(".location")] == ['LENGTH'] * 3
    # quaternion components have no rotation unit in RNA: not lengths either
    assert all(u != 'LENGTH' for fc, u in zip(fcs, units) if "rotation" in fc.data_path)


def test_handler_registered_and_removed():
    assert gu._handles and bpy.app.timers.is_registered(gu._sync)
    kit.disable()
    try:
        assert not gu._handles and not gu._cursor_handle and not gu._SNAP
        assert not bpy.app.timers.is_registered(gu._sync)
    finally:
        kit.enable()
    gu2 = import_module(kit.MODULE + ".ui.graph_units")
    assert gu2._handles and bpy.app.timers.is_registered(gu2._sync)
