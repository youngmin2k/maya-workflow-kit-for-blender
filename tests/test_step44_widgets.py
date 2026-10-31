"""Maya widget feel. The kit has no theme, density, font and wire presets (they wrote Blender's
preferences); what is left: the marking menu text font and the Channel Box row height."""

import os
from importlib import import_module

import bpy

import kit

draw = import_module(kit.MODULE + ".marking.draw")
channel_box = import_module(kit.MODULE + ".ui.channel_box")
SEGOE_UI = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf")


def test_no_widget_presets():
    addon = bpy.context.preferences.addons[kit.MODULE].preferences
    for name in ("maya_theme", "maya_density", "maya_font", "maya_wire", "maya_hide_splash"):
        assert not hasattr(addon, name), name


def test_marking_menu_text_uses_interface_font():
    import blf
    p = bpy.context.preferences
    assert draw.font_size() == max(8, round(11 * p.system.ui_scale))
    if os.path.isfile(SEGOE_UI):
        p.view.font_path_ui = SEGOE_UI          # the user's own choice (the test resets it)
        try:
            # draw.py draws with blf font 0: the interface font is loaded as id 0, so loading the same
            # file again returns 0.
            assert blf.load(SEGOE_UI) == 0
        finally:
            p.view.font_path_ui = ""


def test_channel_box_rows_are_maya_height():
    # 20 px Blender rows x 0.8 = 16 px channel rows.
    assert abs(20 * channel_box.ROW_SCALE - 16) < 1e-6
