"""Ctrl+Shift+click on a Maya menu item adds it to the current shelf (Maya
menuItemToShelf appends a shelfButton for the item to the shelf tab shown, factory tabs included).

GUI: tests/gui/gui_step162_shelf_add.py (Ctrl+Shift+click Display > Grid, the button drawn on Poly Modeling)."""

import json
import os
import types
from contextlib import contextmanager
from importlib import import_module

import bpy

import kit

shelf = import_module(kit.MODULE + ".ui.shelf")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_icon_data = import_module(kit.MODULE + ".ui.menu_icon_data")
keystate = import_module(kit.MODULE + ".operators.keystate")

CUBE = "Create/Polygon Primitives/Cube"
MOVE_TOOL = "Modify/Transformation Tools/Move Tool"


@contextmanager
def _sandbox(keys=()):
    """A fresh shelves.json and the given keys held; everything restored afterwards (other test files count the
    factory slots)."""
    path = shelf.store_path()
    backup = open(path, encoding="utf-8").read() if os.path.isfile(path) else None
    if os.path.isfile(path):
        os.remove(path)
    shelf.reload_user()
    orig_down = keystate.is_down
    held = set(keys)
    keystate.is_down = lambda t: t in held
    bpy.ops.allset.shelf_select(shelf="Polygons")
    try:
        yield held
    finally:
        keystate.is_down = orig_down
        if backup is None:
            if os.path.isfile(path):
                os.remove(path)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(backup)
        shelf.reload_user()
        bpy.ops.allset.shelf_select(shelf="Polygons")


def _spy_option_box(calls):
    orig = menu_sets.ALLSET_OT_menu_option_box.execute

    def execute(self, context):
        calls.append(self.item)
        return {'FINISHED'}
    menu_sets.ALLSET_OT_menu_option_box.execute = execute
    return orig


def _cubes():
    return sum(1 for ob in bpy.data.objects if ob.name.startswith("pCube"))


def test_paths_are_mapped_menu_items():
    assert CUBE in menu_map.MAP and CUBE in menu_sets.OPTION_BOXES
    assert menu_map.spec(MOVE_TOOL)[0] == "tool"
    assert menu_icon_data.ICONS[CUBE][0] == "shelf"


def test_menu_draw_marks_clicks():
    """Menu rows carry ``clicked`` (a UI click); Python / marking-menu calls don't, so Ctrl+Shift there runs."""
    class _Layout:
        def __init__(self):
            self.ops = []

        def operator(self, idname, text="", **kw):
            props = types.SimpleNamespace()
            self.ops.append((idname, props))
            return props
        operator_menu_hold = operator
    layout = _Layout()
    menu_sets._draw_boxed(layout, CUBE, "Cube")
    (idname, props), = layout.ops
    assert idname == "allset.menu_item" and props.item == CUBE and props.clicked is True
    layout = _Layout()
    menu_sets.draw_spec(layout, "Move Tool", menu_map.spec(MOVE_TOOL), MOVE_TOOL)
    (idname, props), = layout.ops
    assert idname == "allset.menu_tool" and props.item == MOVE_TOOL


def test_ctrl_shift_click_adds_to_the_factory_shelf():
    with _sandbox({"LEFT_CTRL", "RIGHT_SHIFT"}):
        calls = []
        orig_box = _spy_option_box(calls)
        try:
            before = list(shelf.icon_buttons(bpy.context)[1])
            n_factory = len(shelf.all_buttons("Polygons"))
            assert len(before) == n_factory == 37        # Maya 2026 Poly Modeling shelf
            cubes = _cubes()
            assert bpy.ops.allset.menu_item(item=CUBE, clicked=True) == {'FINISHED'}
            assert calls == [] and _cubes() == cubes          # neither the option box nor the command
            extras = shelf.factory_extras("Polygons")
            assert extras == [{"label": "Cube", "icon": "SCRIPT", "script": "", "menu": CUBE}], extras
            after = shelf.icon_buttons(bpy.context)[1]
            assert after[:n_factory] == before                # every Maya slot keeps its index
            assert after[n_factory] == (n_factory, "Cube", None, True)
            assert shelf.button_record("Polygons", n_factory)["menu"] == CUBE
            assert shelf.button_record("Polygons", n_factory - 1) is None      # a factory slot
            on_disk = json.load(open(shelf.store_path(), encoding="utf-8"))
            assert on_disk["extra"]["Polygons"][0]["menu"] == CUBE
            # a restart reads it back
            shelf.reload_user()
            assert shelf.icon_buttons(bpy.context)[1][n_factory][1] == "Cube"
            tip = shelf.ALLSET_OT_shelf_slot.description(bpy.context, types.SimpleNamespace(slot=n_factory))
            assert "Maya menu: Create > Polygon Primitives > Cube" in tip, tip
        finally:
            menu_sets.ALLSET_OT_menu_option_box.execute = orig_box


def test_menu_button_runs_the_path():
    with _sandbox({"LEFT_CTRL", "LEFT_SHIFT"}) as held:
        bpy.ops.allset.menu_item(item=CUBE, clicked=True)
        held.clear()
        n = len(shelf.all_buttons("Polygons"))
        cubes = _cubes()
        assert bpy.ops.allset.shelf_button(shelf="Polygons", index=n) == {'FINISHED'}
        assert _cubes() == cubes + 1                         # Maya's polyCube through the menu path
        calls = []
        orig_box = _spy_option_box(calls)
        try:
            bpy.ops.allset.shelf_button(shelf="Polygons", index=n, option=True)    # Ctrl+click = the option box
            assert calls == [CUBE], calls
        finally:
            menu_sets.ALLSET_OT_menu_option_box.execute = orig_box


def test_shift_or_ctrl_alone_still_opens_the_option_box():
    for key in ("LEFT_SHIFT", "RIGHT_CTRL"):
        with _sandbox({key}):
            calls = []
            orig_box = _spy_option_box(calls)
            try:
                assert bpy.ops.allset.menu_item(item=CUBE, clicked=True) == {'FINISHED'}
                assert calls == [CUBE], (key, calls)
                assert shelf.factory_extras("Polygons") is None
            finally:
                menu_sets.ALLSET_OT_menu_option_box.execute = orig_box


def test_ctrl_shift_from_python_or_marking_menus_runs():
    """No ``clicked``: a marking menu / Python call (Ctrl+Shift+RMB opens one) is not a menu click."""
    with _sandbox({"LEFT_CTRL", "LEFT_SHIFT"}):
        calls = []
        orig_box = _spy_option_box(calls)
        try:
            bpy.ops.allset.menu_item(item=CUBE)
            assert shelf.factory_extras("Polygons") is None
            assert calls == [CUBE]                            # Shift / Ctrl held: the option-box rule
        finally:
            menu_sets.ALLSET_OT_menu_option_box.execute = orig_box


def test_tool_item_and_user_shelf():
    with _sandbox({"LEFT_CTRL", "LEFT_SHIFT"}):
        bpy.ops.allset.shelf_select(shelf="USER:Custom")
        assert bpy.ops.allset.menu_tool(tool="builtin.move", item=MOVE_TOOL) == {'FINISHED'}
        s = shelf.user_shelf("Custom")
        assert [b["menu"] for b in s["buttons"]] == [MOVE_TOOL]
        assert shelf.icon_buttons(bpy.context)[1] == [(0, "Move Tool", None, True)]
        # marking pies draw tool items with their own label as the path: not a menu item, the tool runs
        assert not menu_sets.add_to_shelf_if_asked(None, bpy.context, "Marking menu x/Move Tool")


def test_remove_and_edit_with_the_shelf_tools():
    with _sandbox({"LEFT_CTRL", "LEFT_SHIFT"}):
        bpy.ops.allset.menu_item(item=CUBE, clicked=True)
        bpy.ops.allset.menu_item(item=CUBE, clicked=True)       # Maya adds it again
        assert len(shelf.factory_extras("Polygons")) == 2
        bpy.ops.allset.shelf_edit_button(index=1, label="Box", icon="MESH_CUBE", script="")
        b = shelf.factory_extras("Polygons")[1]
        assert b == {"label": "Box", "icon": "MESH_CUBE", "script": "", "menu": CUBE}, b
        bpy.ops.allset.shelf_remove_button(index=0)
        assert [b["label"] for b in shelf.factory_extras("Polygons")] == ["Box"]
        bpy.ops.allset.shelf_remove_button(index=0)
        assert shelf.factory_extras("Polygons") == []
        assert len(shelf.icon_buttons(bpy.context)[1]) == 37
