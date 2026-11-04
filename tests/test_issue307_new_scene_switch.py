"""#307: a new scene made in Maya mode, then Blender mode: Blender's tabs only, no Maya tabs mixed in.

Blender file -> Maya mode -> File > New Scene -> Blender mode used to keep the new scene's Maya workspaces (General,
Modeling - Standard, Rigging, ...) next to the Blender workspaces it brought back. A new scene that was never saved now
loses its Maya workspaces on the switch (like the Maya layout a switch appends to a Blender file) and gets the user's
startup workspaces, else Blender's factory ones, showing the workspace the user had before Maya mode."""

import os
import tempfile
from importlib import import_module

import bpy

import kit

sw = import_module(kit.MODULE + ".switch")
first_start = import_module(kit.MODULE + ".first_start")

_shown = []


def _record_targets():
    """In -b a Window.workspace assignment waits for an event loop: record what the switch chose instead."""
    real = sw.blender_target

    def wrapped(window):
        ws = real(window)
        _shown.append(ws.name if ws is not None else None)
        return ws
    sw.blender_target = wrapped


_record_targets()


def _win():
    return bpy.context.window_manager.windows[0]


def _maya_left():
    """Maya workspaces left besides the one the window still shows (in -b it is deleted once the window shows
    another, which needs an event loop)."""
    return sorted(w.name for w in bpy.data.workspaces if sw.is_maya_workspace(w) and w != _win().workspace)


def _new_scene_in_maya_mode():
    bpy.ops.wm.read_homefile()
    if not sw.is_on():
        sw.set_mode(True, layout=False)
    assert sw.enter_layout(_win()) is not None            # Blender file -> Maya mode: the Maya layout appended
    first_start.new_maya_scene()                           # File > New Scene in Maya mode
    assert not bpy.data.filepath
    assert sum(sw.is_maya_workspace(w) for w in bpy.data.workspaces) > 1


def test_new_scene_in_maya_mode_gives_blenders_factory_tabs_back():
    sw.user_startup_file = lambda: None
    sw.START_WORKSPACE["name"] = None
    _new_scene_in_maya_mode()
    assert sw.START_WORKSPACE["name"] == "Layout", sw.START_WORKSPACE     # the workspace before Maya mode
    sw.set_mode(False)
    assert _shown[-1] == "Layout", _shown
    assert not _maya_left(), _maya_left()
    names = [w.name for w in bpy.data.workspaces if not sw.is_maya_workspace(w)]
    assert sorted(names) == sorted(sw.BLENDER_WORKSPACES), names
    assert not any(n.endswith(".001") for n in names), names


def test_new_scene_in_maya_mode_gives_the_users_startup_tabs_back():
    bpy.ops.wm.read_homefile()
    _win().workspace.name = "My Workspace"
    path = os.path.join(tempfile.mkdtemp(prefix="allset307_"), "startup.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    with bpy.data.libraries.load(path) as (src, _dst):
        startup = sorted(src.workspaces)
    sw.user_startup_file = lambda: path
    sw.START_WORKSPACE["name"] = None
    _new_scene_in_maya_mode()
    sw.set_mode(False)
    assert not _maya_left(), _maya_left()
    names = sorted(w.name for w in bpy.data.workspaces if not sw.is_maya_workspace(w))
    assert names == startup, (names, startup)


def test_a_saved_maya_file_keeps_its_maya_workspaces():
    sw.user_startup_file = lambda: None
    _new_scene_in_maya_mode()
    path = os.path.join(tempfile.mkdtemp(prefix="allset307s_"), "maya_scene.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    n_maya = sum(sw.is_maya_workspace(w) for w in bpy.data.workspaces)
    sw.set_mode(False)
    assert sum(sw.is_maya_workspace(w) for w in bpy.data.workspaces) == n_maya
