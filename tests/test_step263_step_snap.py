"""Issue #153: Maya Step Snap Relative / Absolute per tool — Move, Rotate and Scale keep their own
(manipMoveContext / manipRotateContext / manipScaleContext -snapRelative);
Blender's one Absolute Grid Snap flag takes the mode of the tool whose transform starts."""

from importlib import import_module

import bpy

import kit

snap = import_module(kit.MODULE + ".operators.snap_align")


def _fresh():
    sc = bpy.context.scene
    sc.pop(snap.STEP_PROP, None)
    ts = sc.tool_settings
    ts.use_snap = False
    ts.snap_elements = {'INCREMENT'}
    ts.use_snap_grid_absolute = False
    for flag in snap.STEP_FLAGS.values():
        setattr(ts, flag, True)
    return ts


def _click(kind, mode):
    # like the Tool Settings button (a UI button = undo depth 0)
    bpy.ops.allset.step_snap('EXEC_DEFAULT', True, kind=kind, mode=mode)


def test_each_tool_keeps_its_own_mode():
    ts = _fresh()
    _click('TRANSLATE', 'RELATIVE')
    _click('ROTATE', 'ABSOLUTE')
    _click('RESIZE', 'RELATIVE')
    got = {k: snap.step_snap_mode(ts, k) for k in snap.STEP_FLAGS}
    assert got == {'TRANSLATE': 'RELATIVE', 'ROTATE': 'ABSOLUTE', 'RESIZE': 'RELATIVE'}, got
    # setting Move again doesn't change what Rotate / Scale show
    _click('TRANSLATE', 'ABSOLUTE')
    got = {k: snap.step_snap_mode(ts, k) for k in snap.STEP_FLAGS}
    assert got == {'TRANSLATE': 'ABSOLUTE', 'ROTATE': 'ABSOLUTE', 'RESIZE': 'RELATIVE'}, got


def test_transform_start_applies_that_tools_mode():
    ts = _fresh()
    _click('TRANSLATE', 'ABSOLUTE')
    _click('RESIZE', 'RELATIVE')            # last click: Blender's flag is relative now
    assert ts.use_snap_grid_absolute is False
    assert snap.apply_tool(ts, 'TRANSLATE') and ts.use_snap_grid_absolute is True
    assert snap.apply_tool(ts, 'RESIZE') and ts.use_snap_grid_absolute is False
    assert not snap.apply_tool(ts, 'RESIZE')                     # already right: no write
    # a tool without its own mode leaves the flag alone
    ts.use_snap_grid_absolute = True
    assert not snap.apply_tool(ts, 'ROTATE') and ts.use_snap_grid_absolute is True
    # Off keeps the other tools' modes
    _click('TRANSLATE', 'OFF')
    assert snap.step_snap_mode(ts, 'TRANSLATE') == 'OFF' and snap.step_snap_mode(ts, 'RESIZE') == 'RELATIVE'


def test_mmb_and_manipulator_press_apply_the_mode():
    ts = _fresh()
    _click('TRANSLATE', 'ABSOLUTE')
    _click('ROTATE', 'RELATIVE')
    # manip_mmb (Maya MMB drag) applies the dragged tool's mode before its transform starts; with nothing to
    # transform it passes through
    bpy.ops.object.select_all(action='DESELECT')
    try:
        bpy.ops.allset.manip_mmb('INVOKE_DEFAULT', mode='TRANSLATE')
    except RuntimeError:
        pass                       # poll: no 3D View in -b — apply_tool is the part under test
    snap.apply_tool(ts, 'TRANSLATE')
    assert ts.use_snap_grid_absolute is True
    assert snap.active_kind(bpy.context) in (None, 'TRANSLATE', 'ROTATE', 'RESIZE')


def test_modes_survive_save_and_open():
    import os
    import tempfile
    ts = _fresh()
    _click('TRANSLATE', 'ABSOLUTE')
    _click('ROTATE', 'RELATIVE')
    path = os.path.join(tempfile.mkdtemp(prefix="allset263_"), "snap.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    bpy.ops.wm.open_mainfile(filepath=path)
    ts = bpy.context.scene.tool_settings
    assert snap.step_snap_mode(ts, 'TRANSLATE') == 'ABSOLUTE'
    assert snap.step_snap_mode(ts, 'ROTATE') == 'RELATIVE'


def test_turning_one_tool_on_leaves_the_others_off():
    # QA 240 toggle invariant I3: Move Relative used to show (and make) Rotate / Scale relative too
    ts = _fresh()
    _click('TRANSLATE', 'RELATIVE')
    got = {k: snap.step_snap_mode(ts, k) for k in snap.STEP_FLAGS}
    assert got == {'TRANSLATE': 'RELATIVE', 'ROTATE': 'OFF', 'RESIZE': 'OFF'}, got
    assert not ts.use_snap_rotate and not ts.use_snap_scale        # and Blender doesn't step them
    _click('ROTATE', 'ABSOLUTE')
    assert snap.step_snap_mode(ts, 'TRANSLATE') == 'RELATIVE' and snap.step_snap_mode(ts, 'RESIZE') == 'OFF'


def test_move_absolute_only_with_world_axes():
    # Maya Move Tool Settings: "Absolute only supported in world mode"
    sc = bpy.context.scene
    slot = sc.transform_orientation_slots[1]          # the Move tool's axis (ui/manipulator.SLOT)
    slot.type = 'GLOBAL'
    assert snap.absolute_offered(sc, 'TRANSLATE')
    slot.type = 'LOCAL'
    assert not snap.absolute_offered(sc, 'TRANSLATE')
    assert snap.absolute_offered(sc, 'ROTATE') and snap.absolute_offered(sc, 'RESIZE')
    slot.type = 'GLOBAL'
