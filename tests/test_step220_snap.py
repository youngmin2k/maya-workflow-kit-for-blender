"""Issue #139 (user report): Snap to Grid / Points looked on but Move didn't snap. Cause: Step Snap Off
(Tool Settings, also Reset Tool) cleared Blender's use_snap_translate ("Affect: Move"), which switches *every* snap
mode off for Move. GUI: tests/gui/gui_step220_snap.py (drag the Move manipulator)."""

from importlib import import_module

import bpy

import kit

snap_align = import_module(kit.MODULE + ".operators.snap_align")
status_line = import_module(kit.MODULE + ".ui.status_line")
tool_settings = import_module(kit.MODULE + ".ui.tool_settings")


def _ts():
    ts = bpy.context.scene.tool_settings
    ts.use_snap = False
    ts.snap_elements = {'INCREMENT'}
    ts.use_snap_translate = ts.use_snap_rotate = ts.use_snap_scale = True
    bpy.context.scene.pop(snap_align.STEP_PROP, None)
    return ts


def test_step_snap_off_keeps_grid_snapping_for_move():
    ts = _ts()
    status_line.toggle_snap(ts, "GRID")
    assert ts.use_snap and 'GRID' in ts.snap_elements
    assert snap_align.set_step_snap(ts, 'TRANSLATE', 'OFF') == 'OFF'
    assert ts.use_snap_translate, "Step Snap Off cut grid snapping off for Move (#139)"
    assert status_line.snap_on(ts, "GRID") and snap_align.step_snap_mode(ts, 'TRANSLATE') == 'OFF'


def test_step_snap_off_first_then_grid_button():
    """The reported order: Step Snap Off (or Reset Tool) while nothing snaps, then the Status Line grid button."""
    ts = _ts()
    snap_align.set_step_snap(ts, 'TRANSLATE', 'OFF')
    status_line.toggle_snap(ts, "GRID")
    assert ts.use_snap and ts.use_snap_translate
    status_line.toggle_snap(ts, "POINT")
    assert {'GRID', 'VERTEX'} <= set(ts.snap_elements) and ts.use_snap_translate


def test_broken_file_state_is_healed_by_the_button_and_load():
    ts = _ts()
    ts.use_snap, ts.snap_elements = True, {'GRID'}
    ts.use_snap_translate = False                       # a file saved by an older kit
    assert snap_align.heal_affect(ts) == 1 and ts.use_snap_translate
    ts.use_snap_translate = False
    status_line.toggle_snap(ts, "POINT")                 # any snap button turned on heals it too
    assert ts.use_snap_translate
    # nothing but the increment on: nothing to heal (Step Snap Off for Move really means no stepping)
    ts = _ts()
    ts.use_snap, ts.snap_elements = True, {'INCREMENT'}
    ts.use_snap_translate = False
    assert snap_align.heal_affect(ts) == 0 and not ts.use_snap_translate


def test_step_snap_modes_still_work():
    ts = _ts()
    assert snap_align.set_step_snap(ts, 'TRANSLATE', 'RELATIVE') == 'RELATIVE'
    assert ts.use_snap and 'INCREMENT' in ts.snap_elements and ts.use_snap_translate
    assert snap_align.step_snap_mode(ts, 'TRANSLATE') == 'RELATIVE'
    snap_align.set_step_snap(ts, 'ROTATE', 'ABSOLUTE')
    snap_align.set_step_snap(ts, 'TRANSLATE', 'OFF')
    assert snap_align.step_snap_mode(ts, 'TRANSLATE') == 'OFF'
    assert snap_align.step_snap_mode(ts, 'ROTATE') == 'ABSOLUTE' and 'INCREMENT' in ts.snap_elements
    snap_align.set_step_snap(ts, 'ROTATE', 'OFF')
    assert not ts.use_snap                               # nothing left on


def test_hold_x_snaps_move_even_with_affect_off():
    hold = import_module(kit.MODULE + ".operators.hold")
    ts = _ts()
    ts.use_snap_translate = False
    group = hold.GROUPS["snap"]
    saved = group.capture(ts)
    group.apply(ts, ["grid"])
    assert ts.use_snap and ts.snap_elements == {'GRID'} and ts.use_snap_translate
    group.restore(ts, saved)
    assert not ts.use_snap_translate and not ts.use_snap


def test_reset_tool_keeps_grid_snapping():
    ts = _ts()
    status_line.toggle_snap(ts, "GRID")
    tool_settings.reset_maya_options(bpy.context, 'TRANSLATE')
    assert ts.use_snap and 'GRID' in ts.snap_elements and ts.use_snap_translate
