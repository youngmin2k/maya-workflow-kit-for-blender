"""#109: Maya Workflow Kit layout details found by audit 15 (time slider current
frame at UI 1.25). Real windows: tests/gui/gui_step202_ui.py."""

import re
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import bpy

import kit

toolbox = import_module(kit.MODULE + ".ui.toolbox")
maya_outliner = import_module(kit.MODULE + ".ui.maya_outliner")
channel_box = import_module(kit.MODULE + ".ui.channel_box")
ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "allset" / "app_template" / "Maya_Workflow_Kit" / "startup.blend"


def _screens():
    return [ws.screens[0] for ws in bpy.data.workspaces if ws.screens]


def test_template_outliners_have_no_mode_column():
    bpy.ops.wm.open_mainfile(filepath=str(TEMPLATE), load_ui=True)
    outliners = [a.spaces.active for s in _screens() for a in s.areas if a.type == 'OUTLINER']
    assert outliners, "the template has Outliners"
    for sp in outliners:
        if maya_outliner.is_maya_outliner(sp):
            assert not sp.show_mode_column, "Maya's Outliner has no Blender mode column"


def test_setup_turns_the_mode_column_off():
    sp = SimpleNamespace(show_mode_column=True)
    maya_outliner.setup(sp)
    assert sp.show_mode_column is False
    assert sp.display_mode == 'VIEW_LAYER' and sp.show_restrict_column_hide is False


def test_time_slider_area_and_its_fitted_height():
    bpy.ops.wm.open_mainfile(filepath=str(TEMPLATE), load_ui=True)
    screen = bpy.data.workspaces["General"].screens[0]
    area = toolbox.time_slider_area(screen)
    assert area is not None, "the General layout has the Time Slider timeline"
    # the generator and the fit use the same ruler height (36 px at scale 1)
    src = (ROOT / "tools" / "make_startup.py").read_text(encoding="utf-8")
    assert int(re.search(r"^TIME_SLIDER_PX = (\d+)", src, re.M).group(1)) == toolbox.TIME_SLIDER_PX
    # a non-Maya timeline (no Time Slider sidebar) is never resized
    for a in screen.areas:
        if a.type == 'DOPESHEET_EDITOR' and a != area:
            assert toolbox.time_slider_area(SimpleNamespace(areas=[a])) is None


def test_channel_box_menu_bar_keeps_all_menus():
    labels = [label for label, _m in channel_box.MENU_BAR]
    assert labels == ["Channels", "Edit", "Object", "Show"], labels


def test_fit_leaves_a_fitted_time_slider_alone():
    """At the template's own scale (1.0) the Time Slider already has 36 px + header: no move is planned."""
    bpy.ops.wm.open_mainfile(filepath=str(TEMPLATE), load_ui=True)
    screen = bpy.data.workspaces["General"].screens[0]
    area = toolbox.time_slider_area(screen)
    hdr = next((r.height for r in area.regions if r.type == 'HEADER'), 0)
    if hdr == 0 or area.height <= 1:
        return            # -b loads the screen without region sizes (sizes appear after a UI load)
    assert abs(round(toolbox.TIME_SLIDER_PX * 1.0) + hdr - area.height) <= 2
