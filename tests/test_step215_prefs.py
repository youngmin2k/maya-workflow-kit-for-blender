"""#121: Maya's Preferences window (ui/maya_prefs.py, ui/maya_prefs_data.py).

Category tree = Maya 2022's (38 rows, Interface / Display / Settings /
Security / Modules / Applications). Rows are kit add-on preferences, scene values, read-only Blender preferences (the
kit never writes them, decisions 13 / 14) or greyed Maya controls."""

import os
from importlib import import_module

import bpy

import kit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def m(name):
    return import_module(f"{kit.MODULE}.{name}")


def _prefs():
    return m("preferences").get(bpy.context)


def test_every_row_resolves():
    mp = m("ui.maya_prefs")
    data = m("ui.maya_prefs_data")
    ctx = bpy.context
    missing = []
    for key, section, row in data.rows():
        if row[0] in {"pref", "scene", "blender"}:
            owner, attr = mp._target(ctx, row)
            if owner is None:
                missing.append((key, section, row[1]))
        if row[0] == "blender":
            assert row[2] in mp.SECTIONS, row
    assert not missing, missing
    assert set(data.MAYA_FACTORY) <= {r[1] for _k, _s, r in data.rows("scene")}


def test_revert_puts_back_the_opening_values():
    mp = m("ui.maya_prefs")
    prefs, scene = _prefs(), bpy.context.scene
    old_fps, old_wire, old_end = scene.render.fps, prefs.maya_selection_wire, scene.frame_end
    mp.take_snapshot(bpy.context)
    scene.render.fps = 30
    scene.frame_end = 77
    prefs.maya_selection_wire = not old_wire
    assert mp.revert(bpy.context) == 3
    assert (scene.render.fps, scene.frame_end, prefs.maya_selection_wire) == (old_fps, old_end, old_wire)
    assert mp.revert(bpy.context) == 0


def test_restore_defaults_is_maya_factory():
    mp = m("ui.maya_prefs")
    prefs, scene = _prefs(), bpy.context.scene
    scene.render.fps, scene.frame_start, scene.frame_end = 30, 5, 50
    scene.frame_preview_start, scene.frame_preview_end = 3, 30
    scene.unit_settings.system_rotation = 'RADIANS'
    scene.sync_mode = 'AUDIO_SYNC'
    prefs.smart_extrude = False
    prefs.in_view_messages = False
    mp.restore_defaults(bpy.context)
    assert scene.render.fps == 24
    assert (scene.frame_start, scene.frame_end) == (1, 200)
    assert (scene.frame_preview_start, scene.frame_preview_end, scene.use_preview_range) == (1, 120, True)
    assert scene.unit_settings.system_rotation == 'DEGREES'
    assert scene.unit_settings.length_unit == 'CENTIMETERS'
    assert scene.sync_mode == 'NONE'
    assert prefs.smart_extrude is True and prefs.in_view_messages is True


def test_no_blender_preference_written():
    mp = m("ui.maya_prefs")
    p = bpy.context.preferences
    paths = [r[3] for _k, _s, r in m("ui.maya_prefs_data").rows("blender")]
    before = {}
    for path in paths:
        owner, attr = mp.resolve(p, path)
        before[path] = getattr(owner, attr)
    mp.take_snapshot(bpy.context)
    mp.restore_defaults(bpy.context)
    mp.revert(bpy.context)
    for path in paths:
        owner, attr = mp.resolve(p, path)
        assert getattr(owner, attr) == before[path], path


def test_menu_item_opens_kit_window_and_kind_is_unique():
    mm = m("ui.menu_map")
    assert mm.MAP["Windows/Settings/Preferences/Preferences"] == "allset.maya_preferences"
    assert m("compat").has_op(bpy.ops.allset, "maya_preferences")
    mw = m("ui.marked_window")
    pairs = [frozenset(v) for v in mw.KINDS.values()]
    assert len(set(pairs)) == len(pairs)
    assert set(mw.KINDS["PREFERENCES"]) & set(m("ui.maya_dock").ROLE_FLAGS.values()) == set()
    assert m("ui.maya_prefs").KIND in mw.KINDS
    for key, _label, _depth, _title, _s in m("ui.maya_prefs_data").PAGES:
        bpy.context.window_manager.allset_prefs_category = key


def test_disable_removes_window_props():
    kit.disable()
    assert not hasattr(bpy.types.WindowManager, "allset_prefs_category")
    assert not hasattr(bpy.types, "ALLSET_OT_maya_preferences")
    kit.enable()
    assert hasattr(bpy.types.WindowManager, "allset_prefs_category")
