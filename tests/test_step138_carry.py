"""Lane CARRY (#64, #63): Maya tool settings are global across File > Open / New Scene / Revert
(ui/scene_carry.py), and the "Keep Maya Layout When Opening Files" rule."""

import math
import os
from importlib import import_module

import bpy

import kit

carry = import_module(kit.MODULE + ".ui.scene_carry")
first_start = import_module(kit.MODULE + ".first_start")
preferences = import_module(kit.MODULE + ".preferences")
units = import_module(kit.MODULE + ".operators.units")
snap_align = import_module(kit.MODULE + ".operators.snap_align")

TMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(kit.__file__))), "tmp", "test_step138_carry")


def _path(name):
    os.makedirs(TMP, exist_ok=True)
    return os.path.join(TMP, name)


def _settings(sc, axis, rotate_axis, snap, radius, sym_on, axis_sym, pin):
    ts = sc.tool_settings
    sc.transform_orientation_slots[1].type = axis
    sc.transform_orientation_slots[2].type = rotate_axis
    snap_align.set_step_snap(ts, 'TRANSLATE', 'ABSOLUTE' if snap else 'OFF')
    sc.allset_soft_radius = radius
    ts.proportional_edit_falloff = 'SPHERE' if sym_on else 'SMOOTH'
    ts.use_transform_correct_face_attributes = sym_on
    sc.allset_symmetry.on = sym_on
    sc.allset_symmetry.axis = axis_sym
    sc.allset_mesh_tools.weld_preserve_uvs = not sym_on
    bpy.context.window_manager.allset_pin_pivot = pin


def _assert_settings(sc, axis, rotate_axis, snap, radius, sym_on, axis_sym, pin, where):
    ts = sc.tool_settings
    got = (sc.transform_orientation_slots[1].type, sc.transform_orientation_slots[2].type,
           snap_align.step_snap_mode(ts, 'TRANSLATE'), round(sc.allset_soft_radius, 4), ts.proportional_edit_falloff,
           ts.use_transform_correct_face_attributes, sc.allset_symmetry.on, sc.allset_symmetry.axis,
           sc.allset_mesh_tools.weld_preserve_uvs, bpy.context.window_manager.allset_pin_pivot)
    want = (axis, rotate_axis, 'ABSOLUTE' if snap else 'OFF', round(radius, 4), 'SPHERE' if sym_on else 'SMOOTH',
            sym_on, sym_on, axis_sym, not sym_on, pin)
    assert got == want, f"{where}: {got} != {want}"


A = ("NORMAL", "GIMBAL", True, 7.5, True, "Z", True)        # the session's settings
B = ("GLOBAL", "LOCAL", False, 2.0, False, "X", False)       # the file's settings


def test_first_maya_scene_starts_from_maya_defaults():
    """Right after Maya mode came on in Blender's startup scene (not the Maya layout, nothing loaded yet) its Blender
    settings are not the session's Maya settings: the kit's New Scene keeps the template's Maya settings."""
    assert not carry.carries_from_current()
    sc = bpy.context.scene
    sc.transform_orientation_slots[2].type = 'GIMBAL'
    sc.tool_settings.transform_pivot_point = 'MEDIAN_POINT'
    first_start.new_maya_scene()
    sc = bpy.context.scene
    assert (sc.transform_orientation_slots[1].type, sc.transform_orientation_slots[2].type,
            sc.tool_settings.transform_pivot_point) == ('GLOBAL', 'LOCAL', 'ACTIVE_ELEMENT')
    assert carry.carries_from_current(), "from now on the session's settings are carried"


def test_registered_handlers():
    assert carry._before_load in bpy.app.handlers.load_pre
    assert carry._after_load in bpy.app.handlers.load_post


def test_open_keeps_session_settings():
    sc = bpy.context.scene
    _settings(sc, *B)
    path = _path("file_b.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    _settings(bpy.context.scene, *A)
    bpy.ops.wm.open_mainfile(filepath=path)
    assert bpy.data.filepath, "the file is open"
    _assert_settings(bpy.context.scene, *A, where="after File > Open")


def test_every_scene_of_the_opened_file():
    _settings(bpy.context.scene, *B)
    bpy.ops.scene.new(type='NEW')
    path = _path("two_scenes.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    _settings(bpy.context.scene, *A)
    bpy.ops.wm.open_mainfile(filepath=path)
    assert len(bpy.data.scenes) == 2
    for sc in bpy.data.scenes:
        _assert_settings(sc, *A, where=f"scene {sc.name}")


def test_new_scene_keeps_settings():
    _settings(bpy.context.scene, *A)
    first_start.new_maya_scene()          # File > New Scene / Ctrl+N: the kit's startup.blend
    assert not bpy.data.filepath
    _assert_settings(bpy.context.scene, *A, where="after New Scene")


def test_revert_keeps_settings():
    _settings(bpy.context.scene, *B)
    path = _path("revert.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    _settings(bpy.context.scene, *A)
    bpy.ops.wm.revert_mainfile()
    _assert_settings(bpy.context.scene, *A, where="after Revert")


def test_soft_radius_is_carried_in_maya_units():
    """A cm scene (New Scene) and a metre file: the radius stays 4 Maya units, not 0.04 m."""
    bpy.ops.wm.read_homefile(use_empty=True)          # factory: metres, Maya unit 1
    path = _path("metres.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    first_start.new_maya_scene()
    sc = bpy.context.scene
    assert math.isclose(units.maya_unit(sc), 0.01), units.maya_unit(sc)
    sc.allset_soft_radius = 4.0
    assert math.isclose(sc.tool_settings.proportional_size, 0.04, rel_tol=1e-5)
    bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    assert math.isclose(units.maya_unit(sc), 1.0)
    assert math.isclose(sc.allset_soft_radius, 4.0, rel_tol=1e-5), sc.allset_soft_radius
    assert math.isclose(sc.tool_settings.proportional_size, 4.0, rel_tol=1e-5)


def test_custom_orientation_stays_the_files():
    """The "Maya Pivot" orientation is scene data (the turned pivot of an object): not carried into a file without it."""
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    sc.transform_orientation_slots[1].type = "LOCAL"
    path = _path("local.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    state = carry.read(sc)
    state["slots"][1] = (None, state["slots"][1][1])      # what read() gives for a custom orientation
    carry.write(sc, state)
    assert sc.transform_orientation_slots[1].type == "LOCAL"
    assert carry.read(sc)["slots"][1][0] == "LOCAL"


def test_layout_rule():
    w = carry.wants_layout
    assert w(True, True, "C:/x.blend", False)
    assert not w(False, True, "C:/x.blend", False), "Blender mode: the file's layout"
    assert not w(True, False, "C:/x.blend", False), "option off"
    assert not w(True, True, "", False), "untitled (New Scene / File > New / startup): left to first_start"
    assert not w(True, True, "C:/x.blend", True), "already the Maya layout"
    assert not w(True, True, "C:/x.blend", False, background=True)


def test_option_default_on():
    prefs = preferences.get()
    assert prefs.bl_rna.properties["maya_layout_on_open"].default is True
    assert prefs.maya_layout_on_open


def test_no_layout_timer_in_background():
    bpy.ops.wm.open_mainfile(filepath=_path("file_b.blend"))
    assert not bpy.app.timers.is_registered(carry._layout_tick)


def test_maya_workspace_lookup_prefers_the_files_own():
    first_start.new_maya_scene()
    switch = import_module(kit.MODULE + ".switch")
    ws = carry.maya_workspace()
    assert ws is not None and switch.is_maya_workspace(ws) and switch.PREV_KEY not in ws, ws
