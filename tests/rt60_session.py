"""One Blender session of the Maya mode switch round trip (run by test_step60_switch.py, not a test file).

    blender -b --python tests/rt60_session.py -- <out.json> <action> [<action> ...]

Runs with a sandbox BLENDER_USER_CONFIG (the caller creates it and checks it is under tmp/),
WITHOUT --factory-startup so the saved preferences of the previous session are read.
Actions: user_setup, enable, make_maya, maya_off, maya_on, disable, save.
Writes {"dump": ..., "state": ...} after the actions (dump = tests/rt60_dump.dump()).
"""

import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit  # noqa: E402
from rt60_dump import dump, edit_user_key, populate  # noqa: E402

assert os.path.abspath(bpy.utils.user_resource('CONFIG')).replace("\\", "/").find("/tmp/") > 0, \
    bpy.utils.user_resource('CONFIG')


def mod(name):
    from importlib import import_module
    return import_module(f"{kit.MODULE}.{name}")


def user_setup():
    """A user who changed things before Maya Workflow Kit: a key, the theme, navigation, another add-on."""
    import addon_utils
    prefs = bpy.context.preferences
    edit_user_key()                         # a user keymap edit
    prefs.themes[0].view_3d.space.gradients.high_gradient = (0.5, 0.1, 0.1)
    prefs.inputs.view_rotate_method = 'TRACKBALL'
    prefs.view.show_splash = True
    addon_utils.enable("node_wrangler", default_set=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out, actions = argv[0], argv[1:]
    state = {}
    for action in actions:
        if action == "user_setup":
            user_setup()
        elif action == "enable":
            kit.enable()
        elif action == "make_maya":
            mod("first_start").make(bpy.context, open_layout=False)
        elif action == "maya_off":
            mod("switch").set_mode(False)
        elif action == "maya_on":
            mod("switch").set_mode(True)
        elif action == "disable":
            kit.disable()
        elif action == "save":
            bpy.ops.wm.save_userpref()
    if kit.is_enabled():
        sw = mod("switch")
        state = {"maya_mode": sw.is_on(),
                 "keyconfig": bpy.context.window_manager.keyconfigs.active.name}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"dump": dump(), "state": state,
                   "userpref": os.path.join(bpy.utils.user_resource('CONFIG'), "userpref.blend")}, fh)


main()
