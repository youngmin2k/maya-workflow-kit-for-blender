"""#282: after Maya mode, Blender's Sculpting tab must be Blender's own workspace.

A Maya Workflow Kit scene carries Maya workspaces named like Blender's (Sculpting, UV Editing, Animation). Switching
to Blender used to leave them under those names, so the Sculpting tab opened a Maya layout with Blender's sculpt
tools. Now in a saved file they become "<name> (Maya)" and the file gets Blender's own workspace of that name."""

import os
import tempfile
from importlib import import_module

import bpy

import kit

sw = import_module(kit.MODULE + ".switch")
first_start = import_module(kit.MODULE + ".first_start")
workspaces = import_module(kit.MODULE + ".ui.workspaces")

_shown = []


def _record_targets():
    """In -b a Window.workspace assignment waits for an event loop: record what the switch chose instead."""
    real = sw.blender_target

    def wrapped(window):
        ws = real(window)
        _shown.append(ws.name if ws is not None else None)
        return ws
    sw.blender_target = wrapped


def test_maya_workspaces_step_aside_for_blenders_own():
    sw.user_startup_file = lambda: None
    _record_targets()
    first_start.new_maya_scene()
    # a saved file keeps its Maya workspaces (a never saved new scene loses them, #307)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(tempfile.mkdtemp(prefix="allset282_"), "maya_scene.blend"))
    clashing = sorted(w.name for w in bpy.data.workspaces
                      if sw.is_maya_workspace(w) and w.name in sw.BLENDER_WORKSPACES)
    assert {"Sculpting", "UV Editing", "Animation"} <= set(clashing), clashing
    sw.set_mode(False)
    assert _shown[-1] == "Layout", _shown
    for name in clashing:
        own, maya = bpy.data.workspaces.get(name), bpy.data.workspaces.get(name + sw.MAYA_SUFFIX)
        assert own is not None and not sw.is_maya_workspace(own), name
        assert maya is not None and sw.template_of(maya) == name, name
        assert maya.get(sw.MAYA_NAME_KEY) == name
    # the Maya menus still find the renamed workspace by its template
    assert workspaces.find("Sculpting") == bpy.data.workspaces["Sculpting" + sw.MAYA_SUFFIX]
    assert workspaces.label_of(bpy.data.workspaces["Sculpting" + sw.MAYA_SUFFIX]) == "Sculpting"
    # Maya and back again: nothing appended or renamed twice
    names = sorted(w.name for w in bpy.data.workspaces)
    sw.set_mode(True)
    sw.set_mode(False)
    assert sorted(w.name for w in bpy.data.workspaces) == names


def test_blender_file_keeps_its_names():
    """A Blender file without Maya workspaces: nothing renamed."""
    bpy.ops.wm.read_homefile()
    names = sorted(w.name for w in bpy.data.workspaces)
    assert sw._rename_maya_clashes() == []
    assert sorted(w.name for w in bpy.data.workspaces) == names
