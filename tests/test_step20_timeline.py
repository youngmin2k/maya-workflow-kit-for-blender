"""Maya . , Alt+. Alt+, key / frame stepping, Time + Range Slider in the Timeline
header, timeline view following the playback range."""

from importlib import import_module

import bpy

import kit

time_slider = import_module(kit.MODULE + ".ui.time_slider")


def _kmis(km, type, **mods):
    km = kit.maya_kc().keymaps[km]
    want = {"shift": False, "ctrl": False, "alt": False, **mods}
    return [k for k in km.keymap_items if k.active and k.type == type and k.value == 'PRESS'
            and all(getattr(k, m) == v for m, v in want.items()) and not k.oskey]


def test_stepping_keys():
    for key, nxt in (("PERIOD", True), ("COMMA", False)):
        k = _kmis("Frames", key)
        assert [i.idname for i in k] == ["screen.keyframe_jump"] and k[0].properties.next is nxt, key
        k = _kmis("Frames", key, alt=True)
        assert [i.idname for i in k] == ["screen.frame_offset"], key
        assert k[0].properties.delta == (1 if nxt else -1) and k[0].repeat, key
    # the pies that took . and , before the Frames keymap is reached are gone
    assert _kmis("3D View", "PERIOD") == [] and _kmis("3D View", "COMMA") == []
    assert _kmis("Image", "PERIOD") == []
    assert [k.idname for k in _kmis("Outliner", "PERIOD")] == ["outliner.show_active"], "kept"


def _buttons():
    return time_slider.header_classes()[0]   # Blender 5.x: the Dope Sheet's


def _header_is_kit():
    return _buttons().draw_header.__func__.__name__ == "_header_5"


def test_header_swapped_and_restored():
    assert _header_is_kit()
    original = time_slider._ORIGINAL["draw_header"]
    kit.disable()
    try:
        assert _buttons().__dict__["draw_header"] is original or _buttons().draw_header is original
    finally:
        kit.enable()
    assert _header_is_kit()


def test_load_handler_and_fit_without_windows():
    assert time_slider._on_load in bpy.app.handlers.load_post
    # -b still has the startup window with its Timeline: fitting runs there without error.
    assert time_slider.fit_timelines() >= 1


def test_range_change_schedules_fit():
    scene = bpy.context.scene
    time_slider._schedule()
    assert bpy.app.timers.is_registered(time_slider._deferred_fit)
    bpy.app.timers.unregister(time_slider._deferred_fit)
    scene.frame_preview_end = 77   # msgbus notify runs on the next event loop; just must not raise
    scene.frame_preview_end = 120
