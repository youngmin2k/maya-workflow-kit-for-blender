"""#275 in a real UI: a settings file imported while Maya mode is off keeps its kit hotkeys, and they are given the
next time Maya mode starts (switching back on from the UI's timer, like the Maya | Blender switch)."""

import json
import os
import sys
import tempfile
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, setup  # noqa: E402

C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def row():
    return next(r for r in mod("ui.hotkey_editor").rows()
                if r["command"] == "SelectToggleMode" and r["context"] == "global")


def key():
    he = mod("ui.hotkey_editor")
    _km, kmi = he.editable_item(bpy.context, row())
    return he.item_event(kmi)["type"], kmi.ctrl, kmi.is_user_modified


@step
def s_setup():
    setup()


@step
def s_export():
    he = mod("ui.hotkey_editor")
    ok, _ = he.assign(bpy.context, row(), {"type": "F9", "ctrl": True})
    C["path"] = os.path.join(tempfile.mkdtemp(prefix="allset275gui_"), "kit.json")
    mod("settings_io").export_file(bpy.context, C["path"], parts=("hotkeys",))
    he.restore_all(bpy.context)
    check(f"the changed hotkey was exported, then restored ({ok}, {key()})",
          ok and key() == ("F8", False, False)
          and json.load(open(C["path"], encoding="utf-8"))["hotkeys"][0]["command"] == "SelectToggleMode")


@step
def s_off():
    mod("switch").set_mode(False, layout=False)


@step
def s_import_off():
    sio = mod("settings_io")
    lines = sio.import_file(bpy.context, C["path"])
    check(f"with Maya mode off the hotkeys are kept for later ({lines})",
          any("kept for Maya mode" in s for s in lines) and sio.has_pending())


@step
def s_on():
    mod("switch").set_mode(True, layout=False)


@step
def s_wait():
    pass


@step
def s_check():
    check(f"Maya mode started: the kept hotkey is given ({key()})", key() == ("F9", True, True))
    check("nothing is left waiting", not mod("settings_io").has_pending())
    mod("ui.hotkey_editor").restore_all(bpy.context)


run()
