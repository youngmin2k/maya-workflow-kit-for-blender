"""Maya editor chrome — Channel Box / Layer Editor / Outliner menu bars, empty Channel Box text,
Time Slider buttons in the timeline sidebar, Range Slider order. GUI: tests/gui/gui_step50_chrome.py."""

from importlib import import_module
from pathlib import Path

import bpy

import kit

ROOT = Path(__file__).resolve().parent.parent
channel_box = import_module(kit.MODULE + ".ui.channel_box")
layer_editor = import_module(kit.MODULE + ".ui.layer_editor")
maya_outliner = import_module(kit.MODULE + ".ui.maya_outliner")
time_slider = import_module(kit.MODULE + ".ui.time_slider")
chrome = import_module(kit.MODULE + ".ui.chrome")


class Recorder:
    """A stand-in UILayout that records what a draw function puts in it."""

    def __init__(self, log=None):
        self.log = [] if log is None else log

    def __getattr__(self, name):
        if name in ("row", "column", "split", "box", "column_flow", "grid_flow"):
            return lambda *a, **k: Recorder(self.log)
        if name in ("menu", "operator", "prop", "label", "popover", "menu_contents"):
            def add(*args, **kw):
                self.log.append((name, kw.get("text", args[0] if args else "")))
                return type("Props", (), {})()
            return add
        return lambda *a, **k: None

    def __setattr__(self, name, value):
        if name == "log":
            object.__setattr__(self, name, value)

    def texts(self, kind):
        return [t for k, t in self.log if k == kind]


def test_channel_box_menu_bar():
    rec = Recorder()
    chrome.menu_bar(rec, channel_box.MENU_BAR)
    assert rec.texts("menu") == ["Channels", "Edit", "Object", "Show"]
    for _label, idname in channel_box.MENU_BAR:
        assert hasattr(bpy.types, idname), idname


def test_channel_box_panel_chrome():
    assert 'HIDE_HEADER' in channel_box.ALLSET_PT_channel_box.bl_options
    assert 'HIDE_HEADER' in layer_editor.ALLSET_PT_layer_editor.bl_options
    assert not hasattr(channel_box.ALLSET_PT_channel_box, "draw_header_preset"), "no gear in a panel title"


def test_channel_box_empty_text():
    for ob in list(bpy.context.selected_objects):
        ob.select_set(False)
    bpy.context.view_layer.objects.active = None
    rec = Recorder()
    channel_box.ALLSET_PT_channel_box.draw(type("P", (), {"layout": rec})(), bpy.context)
    assert " ".join(t for t in rec.texts("label") if t) == \
        "Select objects in the scene to view, edit and set keyframes on channels (attributes)"


def test_layer_editor_tabs_and_menus():
    assert [t[1] for t in layer_editor.TABS] == ["Display", "Anim"]
    rec = Recorder()
    chrome.menu_bar(rec, layer_editor.MENU_BAR)
    assert rec.texts("menu") == ["Layers", "Options", "Help"]
    assert bpy.context.window_manager.allset_le_tab == 'DISPLAY'


def test_outliner_header_is_maya():
    assert maya_outliner._draw in bpy.types.OUTLINER_HT_header.draw._draw_funcs   # own draw swapped
    rec = Recorder()
    chrome.menu_bar(rec, maya_outliner.MENU_BAR)
    assert rec.texts("menu") == ["Display", "Show", "Help"]


def _timeline_ctx():
    """A Timeline area of the startup screen (the 5.x wrapper checks ``space_data.mode``)."""
    for area in bpy.data.screens["Layout"].areas:
        if area.type == 'DOPESHEET_EDITOR' and area.spaces.active.mode == 'TIMELINE':
            return {"area": area, "space_data": area.spaces.active}
    return {}


def test_range_slider_order_and_menus_moved():
    buttons, menus = time_slider.header_classes()   # Blender 5.x: the Dope Sheet's
    assert buttons.draw_header.__name__ in ("draw_header", "_header_5")
    assert "draw_collapsible" in menus.__dict__
    rec = Recorder()
    with bpy.context.temp_override(**_timeline_ctx()):
        menus.draw_collapsible(bpy.context, rec)
    assert rec.log == [], "Playback / Keying / View / Marker are not in the Range Slider row"
    assert time_slider.RANGE_ITEMS[:5] == ("start", "playback start", "range", "playback end", "end")
    rec = Recorder()
    time_slider.ALLSET_MT_anim_preferences.draw(type("M", (), {"layout": rec})(), bpy.context)
    assert rec.texts("popover") + rec.texts("menu") == ["Playback", "Keying", "View", "Marker"]


def test_template_timeline_sidebar_and_outliner():
    path = ROOT / "src" / "allset" / "app_template" / "Maya_Workflow_Kit" / "startup.blend"
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=True)
    areas = bpy.data.workspaces["General"].screens[0].areas
    tl = next(a for a in areas if a.ui_type == 'TIMELINE')
    assert time_slider.has_slider_panel(tl.spaces.active), "Time Slider buttons in the timeline sidebar"
    outl = next(a for a in areas if a.type == 'OUTLINER').spaces.active
    assert maya_outliner.is_maya_outliner(outl) and not outl.show_restrict_column_hide
