"""#281: windows with a temporary screen (Preferences, file browser) are skipped by the joint overlay settle tick
and by the playback stop before a switch: Blender can't use a temporary screen in a context override."""

from importlib import import_module
from types import SimpleNamespace

import kit

maya_joints = import_module(kit.MODULE + ".ui.maya_joints")


class _Screen(dict):
    is_temporary = True
    is_animation_playing = True
    areas = ()


def test_settle_skips_a_temporary_screen():
    window = SimpleNamespace(screen=_Screen(), workspace=None)
    assert maya_joints.settle(window) is False


def test_settle_survives_real_windows():
    import bpy
    for window in bpy.context.window_manager.windows:
        maya_joints.settle(window)       # must not raise
