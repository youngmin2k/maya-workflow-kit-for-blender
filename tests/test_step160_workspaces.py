"""#81: Maya's workspaces in the template, Windows > Workspaces / Status Line dropdown, Reset Current
Workspace. GUI shots: tests/gui/gui_step160_workspaces.py."""

import ast
import os
from importlib import import_module

import bpy

import kit


def _m(name):
    return import_module(kit.MODULE + "." + name)


def _template_table():
    """tools/make_startup.MAYA_WORKSPACES, read from the generator's source (it isn't importable inside Blender)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "make_startup.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "MAYA_WORKSPACES":
            return ast.literal_eval(node.value)
    raise AssertionError("MAYA_WORKSPACES not found")


def _types(ws):
    return sorted(a.ui_type for a in ws.screens[0].areas)


def test_template_carries_maya_workspaces():
    ws_mod = _m("ui.workspaces")
    table = _template_table()
    assert tuple(table) == ws_mod.IN_TEMPLATE, (tuple(table), ws_mod.IN_TEMPLATE)
    _m("first_start").new_maya_scene()
    names = [ws.name for ws in bpy.data.workspaces]
    assert sorted(names) == sorted(table), names          # a Maya scene has no Blender factory workspaces
    for name, (menu_set, tab, _recipe) in table.items():
        ws = bpy.data.workspaces[name]
        assert ws["allset_template"] == name and ws["allset_menu_set"] == menu_set and ws["allset_dock_tab"] == tab
    t = {name: _types(bpy.data.workspaces[name]) for name in table}
    assert "OUTLINER" in t["General"] and "TIMELINE" in t["General"]
    assert "OUTLINER" not in t["Modeling - Standard"] and "TIMELINE" not in t["Modeling - Standard"]
    assert t["Modeling - Expert"] == ["VIEW_3D"], t["Modeling - Expert"]
    assert "UV" in t["UV Editing"] and "FCURVES" in t["Animation"] and "DOPESHEET" in t["Rigging"]
    assert "TEXT_EDITOR" in t["Rendering - Standard"] and t["Rendering - Standard"].count("PROPERTIES") == 2
    sculpt = bpy.data.workspaces["Sculpting"].screens[0]
    dock = next(a for a in sculpt.areas if a.type == 'PROPERTIES')
    assert dock.spaces.active.context == 'TOOL' and not dock.spaces.active.show_properties_world, "Tool Settings dock"
    rig = next(a for a in bpy.data.workspaces["Rigging"].screens[0].areas if a.ui_type == 'DOPESHEET')
    assert rig.spaces.active.mode == 'SHAPEKEY'


def test_activate_appends_into_a_blender_file_and_applies_the_menu_set():
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    sw = _m("switch")
    ws_mod = _m("ui.workspaces")
    win = bpy.context.window_manager.windows[0]
    prefs = _m("preferences").get()
    assert ws_mod.find("Animation") is None
    before = len(bpy.data.workspaces)
    ws = ws_mod.activate(bpy.context, win, "Animation")
    assert ws is not None and len(bpy.data.workspaces) == before + 1
    assert sw.template_of(ws) == "Animation" and ws_mod.find("Animation") == ws
    assert "FCURVES" in _types(ws) and sw.is_maya_workspace(ws)
    assert prefs.menu_set == "animationMenuSet"
    assert bpy.context.window_manager.allset_dock == 'CHANNEL_BOX'
    # a second activation reuses it
    assert ws_mod.activate(bpy.context, win, "Animation") == ws and len(bpy.data.workspaces) == before + 1
    ws2 = ws_mod.activate(bpy.context, win, "Modeling - Standard")
    assert prefs.menu_set == "modelingMenuSet" and bpy.context.window_manager.allset_dock == 'MODELING_TOOLKIT'
    assert ws2 is not None and "OUTLINER" not in _types(ws2)


def test_reset_restores_the_factory_layout():
    _m("first_start").new_maya_scene()
    sw = _m("switch")
    win = bpy.context.window_manager.windows[0]
    ws = bpy.data.workspaces["Animation"]
    name = ws.name   # -b: a window.workspace assignment waits for an event loop, so the workspace is passed
    template = sw.template_of(ws)
    factory = _types(ws)
    # the user's changes: an editor swapped, the Outliner turned into an Info editor
    for area in ws.screens[0].areas:
        if area.type == 'OUTLINER':
            area.type = 'INFO'
    assert _types(ws) != factory
    new = sw.reset_workspace(win, ws)
    assert new is not None and new != ws
    assert new.name == name and _types(new) == factory, (_types(new), factory)
    assert sw.template_of(new) == template
    assert bpy.data.workspaces.get(name + " (old)") is None, "the replaced workspace (no window shows it) is gone"


def test_reset_of_the_switched_layout_keeps_the_way_back():
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    sw = _m("switch")
    win = bpy.context.window_manager.windows[0]
    ws = sw.enter_layout(win)
    assert ws is not None and ws.name == sw.WORKSPACE and sw.template_of(ws) == "General"
    prev = ws[sw.PREV_KEY]
    factory = sorted(a.type for a in ws.screens[0].areas)
    new = sw.reset_workspace(win, ws)
    assert new.name == sw.WORKSPACE and new[sw.PREV_KEY] == prev
    assert sorted(a.type for a in new.screens[0].areas) == factory


def test_menu_and_dropdown():
    ws_mod = _m("ui.workspaces")
    menu_map = _m("ui.menu_map")
    notices = _m("ui.notices")
    assert menu_map.MAP["Windows/Workspaces"] == ("menu", "ALLSET_MT_maya_workspaces")
    labels = [e[1] for e in ws_mod.FACTORY if e]
    assert labels[0] == "Maya Classic" and len(labels) == 14
    for name, _label in (e for e in ws_mod.FACTORY if e):
        if name not in ws_mod.IN_TEMPLATE:
            assert notices.tooltip(ws_mod.PATH + name, mapped=False), name
    for label in ws_mod.ACTIONS_GREYED:
        assert notices.tooltip(ws_mod.PATH + label, mapped=False), label
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    rows = ws_mod.entries()
    assert [r[2] for r in rows[:len(ws_mod.IN_TEMPLATE)]] == [ws_mod.LABELS[n] for n in ws_mod.IN_TEMPLATE]
    assert any(r[0] is None and r[1].name == "Layout" for r in rows)
    win = bpy.context.window_manager.windows[0]
    ws = _m("switch").enter_layout(win)
    assert ws_mod.label_of(ws) == "Maya Classic" and ws_mod.reset_label(ws) == 'Reset "Maya Classic" to Factory Default'
