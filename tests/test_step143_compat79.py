"""Issue #79: Maya mode failed to switch on in Blender 5.2.3 with "'module' object is not iterable" when a
third-party add-on's render panel module had a submodule named ``classes``. Maya mode leaves Blender's and add-ons'
render panels alone."""

import types
from importlib import import_module

import bpy

import kit

AUTO_ENABLE = False

FAKE_MODULE = "fake79_addon.panels"


def _bound(func, module_name, classes):
    """``func`` with module globals as a third-party add-on module would have them."""
    globs = {"__name__": module_name, "classes": classes, "bpy": bpy}
    return types.FunctionType(func.__code__, globs, func.__name__)


def _poll(cls, context):
    return True


def _draw(self, context):
    self.layout.label(text="fake 79")


def _fake_panel(name, classes, module_name=FAKE_MODULE, register=False):
    cls = type(name, (bpy.types.Panel,), {
        "__module__": module_name,
        "bl_idname": name, "bl_label": name,
        "bl_space_type": 'PROPERTIES', "bl_region_type": 'WINDOW', "bl_context": "render",
        "poll": classmethod(_bound(_poll, module_name, classes)),
        "draw": _bound(_draw, module_name, classes),
    })
    return cls


def test_maya_mode_switches_on_with_a_bad_third_party_render_panel():
    """An add-on render panel whose module ``classes`` is a module: Maya mode switches on and keeps its poll."""
    bad = _fake_panel("FAKE79_PT_render", types.ModuleType("fake79_addon.classes"))
    bpy.utils.register_class(bad)
    own_poll = bad.__dict__["poll"]
    try:
        kit.enable()                  # Maya mode on (raised "'module' object is not iterable" before the fix)
        try:
            switch = import_module(kit.MODULE + ".switch")
            assert switch.is_on() and switch._registered[0], "Maya mode did not switch on"
            assert bad.is_registered and bad.__dict__["poll"] is own_poll
            assert bad.poll(bpy.context)
        finally:
            kit.disable()
        assert bad.is_registered and bad.__dict__["poll"] is own_poll
    finally:
        if bad.is_registered:
            bpy.utils.unregister_class(bad)
