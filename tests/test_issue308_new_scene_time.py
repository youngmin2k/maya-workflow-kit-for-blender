"""#308: the Time (frame rate) of a new Maya scene is a kit setting, like Maya's New Scene Options Time: File >
New Scene / Ctrl+N give the new scene that rate (default 24 fps); Blender's own File > New is left alone."""

import json
import math
from importlib import import_module

import bpy

import kit

first_start = import_module(kit.MODULE + ".first_start")
option_windows = import_module(kit.MODULE + ".operators.option_windows")
prefs_data = import_module(kit.MODULE + ".ui.maya_prefs_data")


def _prefs():
    return bpy.context.preferences.addons[kit.MODULE].preferences


def _clean():
    p = _prefs()
    p.property_unset("new_scene_time")
    p.option_settings = ""


def _rate(scene):
    return scene.render.fps / scene.render.fps_base


def test_default_is_24_fps():
    _clean()
    bpy.context.scene.render.fps = 30
    first_start.new_maya_scene()
    sc = bpy.context.scene
    assert (sc.render.fps, sc.render.fps_base) == (24, 1.0), (sc.render.fps, sc.render.fps_base)
    assert sc.unit_settings.length_unit == 'CENTIMETERS'


def test_new_scene_gets_the_stored_time():
    _clean()
    p = _prefs()
    p.new_scene_time = "30 fps"
    bpy.context.scene.render.fps = 25
    first_start.new_maya_scene()
    sc = bpy.context.scene
    assert (sc.render.fps, sc.render.fps_base) == (30, 1.0), (sc.render.fps, sc.render.fps_base)
    assert (sc.frame_start, sc.frame_end) == (1, 200), "the ranges of the layout file stay"
    p.new_scene_time = "29.97 fps"
    first_start.new_maya_scene()
    assert math.isclose(_rate(bpy.context.scene), 29.97, rel_tol=1e-6), _rate(bpy.context.scene)
    _clean()


def test_option_window_time_is_the_same_setting():
    _clean()
    p = _prefs()
    window = option_windows.find_path("File/New Scene")
    assert window.pref_fields == {"fps": "new_scene_time"}
    values = {**window.defaults(), "fps": "60 fps", "anim_end": 300}
    option_windows.store(window.key, values)
    assert p.new_scene_time == "60 fps"
    assert "fps" not in json.loads(p.option_settings)[window.key], "kept once, in the preference"
    assert option_windows.saved(window.key)["fps"] == "60 fps"
    first_start.new_maya_scene()            # Ctrl+N: the saved options and the time
    sc = bpy.context.scene
    assert sc.render.fps == 60 and sc.frame_end == 300, (sc.render.fps, sc.frame_end)
    p.new_scene_time = "25 fps"             # changed in the Preferences window: the option window shows it
    assert option_windows.saved(window.key)["fps"] == "25 fps"
    option_windows.store(window.key, None)  # Reset Settings
    assert not p.is_property_set("new_scene_time") and p.new_scene_time == "24 fps"
    _clean()


def test_do_not_reset_working_units_keeps_the_open_scenes():
    _clean()
    _prefs().new_scene_time = "60 fps"
    bpy.context.scene.render.fps = 50
    window = option_windows.find_path("File/New Scene")
    first_start.new_maya_scene({**window.defaults(), "keep_units": True})
    assert bpy.context.scene.render.fps == 50, bpy.context.scene.render.fps
    _clean()


def test_blender_new_file_is_left_alone():
    _clean()
    _prefs().new_scene_time = "30 fps"
    bpy.ops.wm.read_homefile()
    assert bpy.context.scene.render.fps == 24, bpy.context.scene.render.fps
    _clean()


def test_preferences_window_row():
    rows = [r for _k, section, r in prefs_data.rows("pref") if section == "Working Units"]
    assert ("pref", "new_scene_time", "Time (new scenes)") in rows, rows


def test_saved_time_from_older_options_is_kept():
    _clean()
    p = _prefs()
    window = option_windows.find_path("File/New Scene")
    p.option_settings = json.dumps({window.key: {**window.defaults(), "fps": "30 fps"}})
    assert option_windows.saved(window.key)["fps"] == "30 fps"
    first_start.new_maya_scene()
    assert bpy.context.scene.render.fps == 30
    _clean()
