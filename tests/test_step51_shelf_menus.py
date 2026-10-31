"""Step 51: Maya option boxes in the menus (count = Maya's), kit-made shelf icons,
shelf icon row (draw handler + gizmo pool). GUI: tests/gui/gui_step51_shelf_menus.py."""

from importlib import import_module
from pathlib import Path

import bpy
import numpy as np

import kit

ROOT = Path(__file__).resolve().parent.parent
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
menu_data = import_module(kit.MODULE + ".ui.menu_data")
shelf = import_module(kit.MODULE + ".ui.shelf")
shelf_icons = import_module(kit.MODULE + ".ui.shelf_icons")
shelf_data = import_module(kit.MODULE + ".ui.shelf_data")


class Props:
    def __init__(self, entry):
        object.__setattr__(self, "entry", entry)

    def __setattr__(self, name, value):
        self.entry[name] = value


class Recorder:
    """Stand-in UILayout recording the icon of every button."""

    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        if name in ("row", "column", "split", "box"):
            return lambda *a, **k: Recorder(self.log)
        if name in ("menu", "operator", "operator_menu_hold", "label", "prop"):
            def add(*args, **kw):
                entry = {"kind": name, "text": kw.get("text", ""), "icon": kw.get("icon", 'NONE')}
                self.log.append(entry)
                return Props(entry)
            return add
        return lambda *a, **k: None

    def __setattr__(self, name, value):
        if name == "log":
            object.__setattr__(self, name, value)


def _all_menu_buttons():
    log = []
    for cls in menu_sets._menu_classes:
        cls.draw(type("M", (), {"layout": Recorder(log)})(), bpy.context)
    return log


def test_option_box_runs_with_options():
    path = "Create/Polygon Primitives/Cube"
    assert path in menu_data.OPTION_BOXES
    n = len(bpy.data.objects)
    assert bpy.ops.allset.menu_option_box(item=path) == {'FINISHED'}
    assert len(bpy.data.objects) == n + 1
    assert bpy.ops.allset.menu_item(item=path) == {'FINISHED'}
    assert len(bpy.data.objects) == n + 2


def test_every_factory_button_has_a_kit_icon():
    seen = set()
    for shelf_id, _label, buttons in shelf_data.SHELVES:
        for label, _cmd in buttons:
            px = shelf_icons.draw(label, shelf_id)
            assert px.shape == (32, 32, 4), px.shape
            cover = float((px[..., 3] > 0.5).mean())
            assert 0.05 < cover < 0.95, (label, cover)
            seen.add(px.round(2).tobytes())
    assert len(seen) >= 60, f"only {len(seen)} different icons"


def test_letters_fallback_and_colours():
    # step 131: every factory button has its own drawing (no letter tiles); only user shelf buttons with a label
    # the kit doesn't know get Maya's generic script button with the label's initials written on it
    for shelf_id, _label, buttons in shelf_data.SHELVES:
        for label, _cmd in buttons:
            assert shelf_icons.icon_for(label, shelf_id) is not None, (shelf_id, label)
    assert shelf_icons.icon_for("My Script") is None
    assert shelf_icons.initials("Convert To Frozen") == "CT"
    a, b = shelf_icons.draw("My Script"), shelf_icons.draw("Other Tool")
    assert not np.allclose(a, b), "the label's initials tell user buttons apart"
    # a factory command keeps its picture on any shelf, like Maya's icon (Set Key on Rigging and Animation)
    assert np.allclose(shelf_icons.draw("Set Key", "Rigging"), shelf_icons.draw("Set Key", "Animation"))
    assert np.allclose(shelf_icons.draw("Polygon Cube"), shelf_icons.draw("Polygon Cube", "Polygons"))
    # Maya buttons that share a label (FX From Current: start / rest) differ by their shelf position
    assert not np.allclose(shelf_icons.draw("From Current", "FX", index=19),
                           shelf_icons.draw("From Current", "FX", index=21))


def test_shelf_row_layout():
    region = type("R", (), {"height": 38})()
    x0, y0, size = shelf.icon_rect(region, 0, 1.0)
    x1, _y, _s = shelf.icon_rect(region, 1, 1.0)
    assert size == 32 and x1 - x0 == 35 and y0 == 3      # shelf button 35x34, 32 px icons
    assert sorted(r for _h, r in shelf._handle) == ['HEADER', 'WINDOW'], "icon row + tab row dim handlers"
    assert round(0x44 * (1 - shelf.TAB_DIM)) == 0x37   # tab row #373737 over the #444444 header
    assert shelf.SLOTS >= max(len(b) for _s, _l, b in shelf_data.SHELVES)
    cur, buttons = shelf.icon_buttons(bpy.context)
    assert buttons and buttons[0][1] == "Polygon Sphere", (cur, buttons[:2])


def test_template_shelf_row():
    path = ROOT / "src" / "allset" / "app_template" / "Maya_Workflow_Kit" / "startup.blend"
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=True)
    screen = bpy.data.workspaces["General"].screens[0]
    row = shelf.shelf_row_area(screen)
    # step 113: no header — tab strip and icons are drawn in the WINDOW region (64 px shelf block)
    assert not row.spaces.active.show_region_header
    assert 60 <= row.height <= 68, row.height       # shelf 64


class _Fake:
    def __init__(self, log):
        object.__setattr__(self, "log", log)

    def __getattr__(self, name):
        if name in ("row", "column"):
            return lambda *a, **k: _Fake(self.log)

        def add(*a, **kw):
            self.log.append((name, a, kw.get("icon")))
            return type("P", (), {})()
        return add

    def __setattr__(self, name, value):
        pass


def test_status_line_collapse_handles():
    """Every Maya Status Line group has a collapse arrow; the groups Maya collapses by default
    (masks, history, input line) start collapsed."""
    status_line = import_module(kit.MODULE + ".ui.status_line")
    icons = import_module(kit.MODULE + ".ui.status_icons")

    def draw():
        log = []
        status_line.draw_status_line(_Fake(log), bpy.context)
        return log

    groups = [g for g, _d in status_line.GROUPS if g != "EDITORS"]
    log = draw()
    handles = [e for e in log if e[1] and e[1][0] == "allset.status_group"]
    assert len(handles) == len(groups), handles
    assert set(status_line.DEFAULT_COLLAPSED) <= set(groups)
    assert any(e[0] == "operator" and e[1] and e[1][0] == "allset.new_maya_scene" for e in log)
    assert bpy.ops.allset.status_group(group="FILE") == {'FINISHED'}
    try:
        log = draw()
        assert not any(e[1] and e[1][0] in ("allset.new_maya_scene", "ed.undo") for e in log), "File group hidden"
        assert any(e[1] and e[1][0] == "render.render" for e in log)
    finally:
        bpy.ops.allset.status_group(group="FILE")
    # every kit-drawn Status Line / panel toolbar glyph renders (icon ids are 0 in background: no GPU previews)
    for name in list(icons.GLYPHS) + list(icons.EXTRA):
        cv = icons.Canvas(16)
        (icons.GLYPHS.get(name) or icons.EXTRA[name])(cv)
        assert cv.px[..., 3].max() > 0.5, name