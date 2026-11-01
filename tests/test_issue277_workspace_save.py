"""#277: Windows > Workspaces > Save Current Workspace As / Delete Current Workspace and the user's saved workspaces
after Maya's. Only the workspace goes into its file (extension user folder); loading it into another scene brings no
scene data. GUI: tests/gui/gui_issue277_workspace_save.py."""

import os
from importlib import import_module

import bpy

import kit


def _m(name):
    return import_module(kit.MODULE + "." + name)


def _types(ws):
    return sorted(a.ui_type for a in ws.screens[0].areas)


def _win():
    return bpy.context.window_manager.windows[0]


def _clear_saved():
    uw = _m("ui.user_workspaces")
    base = uw.folder()
    if os.path.isdir(base):
        for f in os.listdir(base):
            os.remove(os.path.join(base, f))


def _data_counts():
    return {name: len(getattr(bpy.data, name)) for name in
            ("objects", "cameras", "images", "texts", "meshes", "materials", "scenes", "collections", "worlds")}


def test_file_names_round_trip():
    uw = _m("ui.user_workspaces")
    for name in ("My Layout", 'a/b:c*?"<>|', "100%", "end.", "end ", "日本語"):
        f = uw.file_name(name)
        assert not any(c in f[:-len(uw.EXT)] for c in '<>:"/\\|?*'), f
        assert uw.name_of(f) == name, (name, f)


def test_save_lists_and_loads_into_another_scene():
    _clear_saved()
    uw = _m("ui.user_workspaces")
    ws_mod = _m("ui.workspaces")
    sw = _m("switch")
    _m("first_start").new_maya_scene()
    ws = _win().workspace                 # the shown one (-b: editor changes only apply to a shown screen)
    assert ws.name == "General"
    # the user's change: the Outliner becomes an Info editor
    for area in ws.screens[0].areas:
        if area.type == 'OUTLINER':
            area.type = 'INFO'
    changed = _types(ws)
    path = uw.save(bpy.context, ws, "My Anim")
    assert "INFO" in changed
    assert os.path.isfile(path) and os.path.dirname(path) == uw.folder()
    assert os.path.normcase(uw.folder()).startswith(os.path.normcase(
        bpy.utils.extension_path_user(kit.MODULE, create=False)))
    assert uw.saved_names() == ["My Anim"]
    assert ws.name == "My Anim" and uw.user_name(ws) == "My Anim"
    assert sw.template_of(ws) is None and sw.is_maya_workspace(ws)
    assert ws_mod.find("General") is None, "Maya Classic stays factory: picking it appends a fresh copy"
    with bpy.data.libraries.load(path) as (src, _dst):
        assert list(src.workspaces) == ["My Anim"]
        for kind in ("objects", "cameras", "images", "texts", "meshes", "scenes", "masks"):
            assert not list(getattr(src, kind)), (kind, list(getattr(src, kind)))

    # another scene: a Blender factory file with an extra object and image
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    bpy.data.images.new("Other", 4, 4)
    before = _data_counts()
    win = _win()
    prev = win.workspace.name
    rows = ws_mod.entries()
    assert (("user", "My Anim"), None, "My Anim") in rows
    new = uw.activate(bpy.context, win, "My Anim")
    assert new is not None and uw.user_name(new) == "My Anim" and new.name == "My Anim"
    assert _types(new) == changed, (_types(new), changed)
    assert _data_counts() == before, (_data_counts(), before)
    left = [lib.filepath for lib in bpy.data.libraries
            if os.path.normcase(bpy.path.abspath(lib.filepath)) == os.path.normcase(path)]
    assert not left, f"no library entry of the saved file left behind: {left}"
    assert new[sw.PREV_KEY] == prev, "the way back to Blender's layout"
    assert sw.template_of(new) is None
    masks = sorted(a.spaces.active.mask.name for a in new.screens[0].areas
                   if a.type == 'IMAGE_EDITOR' and a.spaces.active.mask is not None)
    assert masks == sorted(sw.STRIP_MASKS), masks
    assert new.get("allset_dock_tab") == "CHANNEL_BOX", "the saved workspace keeps its Maya tab"
    # chosen again: the file's copy is reused
    n = len(bpy.data.workspaces)
    assert uw.activate(bpy.context, win, "My Anim") == new and len(bpy.data.workspaces) == n
    _clear_saved()


def test_saved_views_follow_the_scene_unit():
    _clear_saved()
    uw = _m("ui.user_workspaces")
    units = _m("operators.units")
    _m("first_start").new_maya_scene()
    ws = bpy.data.workspaces["General"]
    unit = units.maya_unit(bpy.context.scene)
    view = next(a.spaces.active for a in ws.screens[0].areas
                if a.type == 'VIEW_3D' and a.spaces.active.show_region_header)
    dist = view.region_3d.view_distance
    uw.save(bpy.context, ws, "Mine")
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    new = uw.activate(bpy.context, _win(), "Mine")
    view = next(a.spaces.active for a in new.screens[0].areas
                if a.type == 'VIEW_3D' and a.spaces.active.show_region_header)
    ratio = units.maya_unit(bpy.context.scene) / unit
    assert abs(view.region_3d.view_distance - dist * ratio) < 1e-4 * max(1.0, dist * ratio), \
        (view.region_3d.view_distance, dist, ratio)
    _clear_saved()


def test_reset_and_delete():
    _clear_saved()
    uw = _m("ui.user_workspaces")
    ws_mod = _m("ui.workspaces")
    _m("first_start").new_maya_scene()
    ws = bpy.data.workspaces["General"]
    uw.save(bpy.context, ws, "Mine")
    saved = _types(ws)
    for area in ws.screens[0].areas:
        if area.type == 'OUTLINER':
            area.type = 'INFO'
    assert _types(ws) != saved
    win = _win()
    new = uw.reset(win, ws)
    assert new is not None and new != ws and new.name == "Mine" and _types(new) == saved
    assert uw.find("Mine") == new
    # Delete Current Workspace: the file goes, Maya Classic is shown
    assert uw.delete(bpy.context, win, new)
    assert uw.saved_names() == [] and not os.path.exists(uw.path_of("Mine"))
    assert ws_mod.find("General") is not None
    # a template workspace can't be deleted or reset from a saved file
    assert not uw.delete(bpy.context, win, ws_mod.find("General"))
    assert uw.reset(win, ws_mod.find("General")) is None


def test_operators_and_menu():
    _clear_saved()
    uw = _m("ui.user_workspaces")
    ws_mod = _m("ui.workspaces")
    _m("first_start").new_maya_scene()
    win = _win()
    ws = bpy.data.workspaces["General"]
    with bpy.context.temp_override(window=win, screen=ws.screens[0], workspace=ws):
        for bad in ("", "  ", "Maya Classic", "Animation"):
            assert bpy.ops.allset.save_workspace_as(name=bad) == {'CANCELLED'}, bad
        assert uw.saved_names() == []
        assert bpy.ops.allset.save_workspace_as(name="Layout A") == {'FINISHED'}
    assert uw.saved_names() == ["Layout A"]
    # the menu: the saved workspace after Maya's, and the actions
    for label in ws_mod.ACTIONS_GREYED:
        assert label not in ("Save Current Workspace As...", "Delete Current Workspace")
    notices = _m("ui.notices")
    assert notices.tooltip(ws_mod.PATH + "Delete Current Workspace", mapped=False)
    assert bpy.ops.allset.user_workspace.poll() is not None
    _clear_saved()


def test_enable_disable_leaves_saved_files():
    """Saved workspaces are the user's files: turning Maya mode off and on keeps them."""
    _clear_saved()
    uw = _m("ui.user_workspaces")
    _m("first_start").new_maya_scene()
    uw.save(bpy.context, bpy.data.workspaces["General"], "Kept")
    kit.disable()
    kit.enable()
    uw = _m("ui.user_workspaces")
    assert uw.saved_names() == ["Kept"]
    _clear_saved()
