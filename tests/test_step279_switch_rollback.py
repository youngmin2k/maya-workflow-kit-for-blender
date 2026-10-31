"""Step 279 (#198 #199): a Maya mode module that fails to register (or unregister) can't leave the kit half there.

- A register failure in one ``ui`` module or one MODE package rolls back: Maya mode stays off, only CORE is left,
  the top bar draws are Blender's again; switching on again later works.
- An unregister failure in one module: switching back still takes back every other module.
- Another add-on's panel Blender refuses to re-register (3D View sidebar / Properties > Render) is left as it was;
  Maya mode still starts and the panel keeps its own poll.
- Startup with Maya mode saved: a failure leaves CORE (the switch) working.
"""

from importlib import import_module

import bpy

import kit

AUTO_ENABLE = False


def _mod(name):
    return import_module(f"{kit.MODULE}.{name}")


def _allset_types():
    return {n for n in dir(bpy.types) if n.startswith("ALLSET_")}


def _boom(*_a, **_k):
    raise RuntimeError("step 279 injected failure")


class _Patch:
    """Replace ``owner.name`` for the ``with`` block."""

    def __init__(self, owner, name, value):
        self.owner, self.name, self.value = owner, name, value

    def __enter__(self):
        self.old = getattr(self.owner, self.name)
        setattr(self.owner, self.name, self.value)
        return self

    def __exit__(self, *exc):
        setattr(self.owner, self.name, self.old)
        return False


def _core_state():
    sw = _mod("switch")
    return {"on": sw.is_on(), "registered": sw._registered[0], "mode_done": list(sw._mode_done),
            "types": _allset_types()}


def _assert_core_only(base_snap, base_types, what):
    sw = _mod("switch")
    assert not sw.is_on(), f"{what}: maya_mode left on"
    assert not sw._registered[0], f"{what}: _registered left True"
    assert not sw._mode_done, f"{what}: modules still recorded: {sw._mode_done}"
    extra = _allset_types() - base_types
    assert not extra, f"{what}: {len(extra)} ALLSET types left, e.g. {sorted(extra)[:8]}"
    d = kit.diff(base_snap, kit.snapshot())
    assert not d, f"{what}: state left after the rollback:\n" + "\n".join(d[:30])


def test_ui_module_register_failure_rolls_back():
    kit.enable(maya=False)
    try:
        sw = _mod("switch")
        base_snap, base_types = kit.snapshot(), _allset_types()
        dock_tabs = _mod("ui.dock_tabs")       # after status_line (top bar swapped), before maya_dock (tear-off op)
        with _Patch(dock_tabs, "register", _boom):
            assert sw.set_mode(True, layout=False) is False
        assert sw.last_error[0] and "injected" in sw.last_error[0], sw.last_error[0]
        _assert_core_only(base_snap, base_types, "ui.dock_tabs register failure")
        assert "ALLSET_OT_menu_tear_off" not in _allset_types()
        # nothing half there: switching on again now works, and back again is clean
        assert sw.set_mode(True, layout=False) is True
        assert sw.is_on() and sw._registered[0] and sw.last_error[0] is None
        assert "ALLSET_OT_menu_tear_off" in _allset_types()
        sw.set_mode(False, layout=False)
        _assert_core_only(base_snap, base_types, "on / off after the failure")
    finally:
        kit.disable()


def test_mode_package_register_failure_rolls_back():
    """The last MODE package (keymap) fails: operators / ui / command_line / marking / first_start go back."""
    kit.enable(maya=False)
    try:
        sw = _mod("switch")
        base_snap, base_types = kit.snapshot(), _allset_types()
        with _Patch(_mod("keymap"), "register", _boom):
            assert sw.set_mode(True, layout=False) is False
        _assert_core_only(base_snap, base_types, "keymap register failure")
    finally:
        kit.disable()


def test_unregister_failure_still_takes_back_the_rest():
    kit.enable(maya=False)
    try:
        sw = _mod("switch")
        base_snap, base_types = kit.snapshot(), _allset_types()
        blender_draws = kit._draw_funcs("TOPBAR_HT_upper_bar")
        assert sw.set_mode(True, layout=False) is True
        assert kit._draw_funcs("TOPBAR_HT_upper_bar") != blender_draws, "Maya top bar not swapped in"
        shelf = _mod("ui.shelf")
        shelf_types = {c.__name__ for c in getattr(shelf, "classes", ())}
        real_unregister = shelf.unregister
        with _Patch(shelf, "unregister", _boom):
            sw.set_mode(False, layout=False)
        assert not sw.is_on() and not sw._registered[0] and not sw._mode_done
        assert kit._draw_funcs("TOPBAR_HT_upper_bar") == blender_draws, "top bar still Maya's after switching back"
        left = _allset_types() - base_types
        assert left <= shelf_types, f"switch back left more than the failing module: {sorted(left - shelf_types)[:8]}"
        assert "ALLSET_OT_menu_tear_off" not in left
        real_unregister()           # the failing module's own leftovers
        _assert_core_only(base_snap, base_types, "after the failing module's own unregister")
    finally:
        kit.disable()


def _foreign_panels():
    class FOREIGN279_PT_sidebar(bpy.types.Panel):
        bl_label = "Foreign 279"
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = "Foreign"

        @classmethod
        def poll(cls, context):
            return True

        def draw(self, context):
            self.layout.label(text="foreign")

    class FOREIGN279_PT_render(bpy.types.Panel):
        bl_label = "Foreign 279 Render"
        bl_space_type = 'PROPERTIES'
        bl_region_type = 'WINDOW'
        bl_context = "render"

        def draw(self, context):
            self.layout.label(text="foreign")

    return FOREIGN279_PT_sidebar, FOREIGN279_PT_render


def test_foreign_panel_reregister_failure_is_skipped():
    panels = _foreign_panels()
    for cls in panels:
        bpy.utils.register_class(cls)
    raw_polls = {cls: cls.__dict__.get("poll") for cls in panels}
    real_register, real_unregister = bpy.utils.register_class, bpy.utils.unregister_class
    refused = set()

    def register_class(cls):
        if cls in panels and cls not in refused:   # refuse the first re-register of each foreign panel
            refused.add(cls)
            raise ValueError(f"step 279: {cls.__name__} refused")
        return real_register(cls)

    kit.enable(maya=False)
    try:
        sw = _mod("switch")
        with _Patch(bpy.utils, "register_class", register_class):
            assert sw.set_mode(True, layout=False) is True, sw.last_error[0]
        assert sw._registered[0]
        sidebar, render = panels
        # the sidebar panel is re-registered to hide it in the Maya dock; render panels are left alone
        assert refused == {sidebar}, f"re-registered: {refused}"
        for cls in panels:
            assert cls.is_registered, f"{cls.__name__} lost"
            assert cls.__dict__.get("poll") is raw_polls[cls], f"{cls.__name__} kept a kit poll"
        assert "ALLSET_OT_menu_tear_off" in _allset_types()
        sw.set_mode(False, layout=False)
        for cls in panels:
            assert cls.is_registered and cls.__dict__.get("poll") is raw_polls[cls], cls.__name__

        # a foreign panel Blender won't unregister: left alone too
        def unregister_class(cls):
            if cls in panels:
                raise RuntimeError(f"step 279: {cls.__name__} can't be unregistered")
            return real_unregister(cls)
        with _Patch(bpy.utils, "unregister_class", unregister_class):
            assert sw.set_mode(True, layout=False) is True, sw.last_error[0]
        for cls in panels:
            assert cls.is_registered and cls.__dict__.get("poll") is raw_polls[cls], cls.__name__
        sw.set_mode(False, layout=False)
    finally:
        kit.disable()
        for cls in panels:
            if cls.is_registered:
                bpy.utils.unregister_class(cls)


def test_startup_failure_keeps_core():
    """Maya mode saved + a failing module at add-on register: the add-on stays enabled with CORE only."""
    kit.enable(maya=True)
    pkg = import_module(kit.MODULE)
    sw = _mod("switch")
    try:
        assert sw.is_on()
        pkg.unregister()                  # like quitting Blender: maya_mode stays saved as on
        assert not sw._mode_done
        with _Patch(_mod("ui.dock_tabs"), "register", _boom):
            pkg.register()                # like the next start
        assert not sw.is_on() and not sw._registered[0] and not sw._mode_done
        assert "ALLSET_OT_switch_mode" in _allset_types(), "CORE switch missing after a failed start"
        assert "ALLSET_OT_menu_tear_off" not in _allset_types()
        assert sw.last_error[0]
        assert sw.set_mode(True, layout=False) is True   # the user can still switch on
    finally:
        kit.disable()
