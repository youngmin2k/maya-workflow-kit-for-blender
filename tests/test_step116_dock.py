"""Maya's docking model — Maya panels in their own dock areas (not the viewport sidebar), roles kept in the
area, tab stack, tear-off / dock bookkeeping, menu tear-off line. Real windows: tests/gui/gui_step116_dock.py."""

from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import bpy

import kit

maya_dock = import_module(kit.MODULE + ".ui.maya_dock")
tool_dock = import_module(kit.MODULE + ".ui.tool_dock")
tool_settings = import_module(kit.MODULE + ".ui.tool_settings")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
preferences = import_module(kit.MODULE + ".preferences")
ROOT = Path(__file__).resolve().parents[1]


class Recorder:
    """A stand-in UILayout recording operator / label texts."""

    def __init__(self, log=None):
        self.log = [] if log is None else log

    def __getattr__(self, name):
        if name in ("row", "column", "split", "box", "column_flow", "grid_flow"):
            return lambda *a, **k: Recorder(self.log)
        if name == "panel":
            return lambda *a, **k: (Recorder(self.log), Recorder(self.log))
        if name in ("menu", "operator", "prop", "label", "popover"):
            def add(*args, **kw):
                props = SimpleNamespace()
                self.log.append((name, kw.get("text", args[0] if args else ""), args, props))
                return props
            return add
        return lambda *a, **k: None

    def __setattr__(self, name, value):
        if name == "log":
            object.__setattr__(self, name, value)


def _properties_areas(n):
    """``n`` Properties areas in the current screen (the factory Layout has one: split it)."""
    screen = bpy.context.window.screen
    areas = [a for a in screen.areas if a.type == 'PROPERTIES']
    while len(areas) < n:
        with bpy.context.temp_override(area=areas[0]):
            assert bpy.ops.screen.area_split(direction='HORIZONTAL', factor=0.5) == {'FINISHED'}
        areas = [a for a in screen.areas if a.type == 'PROPERTIES']
    for area in areas:               # no role left over from an earlier test
        sp = area.spaces.active
        for flag in maya_dock.ROLE_FLAGS.values():
            setattr(sp, flag, False)
        sp.show_region_header = True
    return areas


def test_roles_are_kept_in_the_area():
    areas = _properties_areas(5)
    for area, name in zip(areas, ('STACK', 'CHANNEL_BOX', 'ATTRIBUTE_EDITOR', 'MODELING_TOOLKIT', 'MENU')):
        assert maya_dock.set_role(area, name), name
        assert maya_dock.role(area) == name, (name, maya_dock.role(area))
        assert not tool_dock.is_dock(area), "a Maya panel area is not the Tool Settings dock"
    # the Tool Settings dock = Tool tab, no header, no role flag
    tool_area = areas[0]
    tool_dock.configure(tool_area)
    assert tool_dock.is_dock(tool_area) and maya_dock.role(tool_area) is None
    # a user's Properties editor (header shown) has no role even with odd tab flags
    sp = areas[1].spaces.active
    sp.show_region_header = True
    assert maya_dock.role(areas[1]) is None


def test_panel_polls_only_in_dock_areas():
    areas = _properties_areas(3)
    maya_dock.set_role(areas[0], 'STACK')
    tool_dock.configure(areas[1])
    win_region = lambda a: next(r for r in a.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(area=areas[0], region=win_region(areas[0])):
        assert bpy.types.ALLSET_PT_maya_dock.poll(bpy.context)
        assert not tool_settings.ALLSET_PT_tool_settings.poll(bpy.context), "no Tool Settings in the CB stack"
        assert not bpy.types.VIEW3D_PT_tools_object_options.poll(bpy.context), "Blender's Tool panels hidden"
    with bpy.context.temp_override(area=areas[1], region=win_region(areas[1])):
        assert not bpy.types.ALLSET_PT_maya_dock.poll(bpy.context)
        assert tool_settings.ALLSET_PT_tool_settings.poll(bpy.context)


def test_stack_tabs_skip_floating_panels():
    wm = bpy.context.window_manager
    areas = _properties_areas(2)
    maya_dock.set_role(areas[0], 'STACK')
    maya_dock.set_role(areas[1], 'ATTRIBUTE_EDITOR')      # = a torn-off Attribute Editor
    try:
        assert maya_dock.floating_kinds(wm) == {'ATTRIBUTE_EDITOR'}
        assert maya_dock.stack_tabs(wm) == ['CHANNEL_BOX', 'MODELING_TOOLKIT']
        wm.allset_dock = 'ATTRIBUTE_EDITOR'
        assert maya_dock.current_tab(wm) == 'CHANNEL_BOX', "the stack shows another tab"
        assert maya_dock.kind_visible(wm, 'ATTRIBUTE_EDITOR'), "the floating one is shown"
        # Windows > Attribute Editor: the floating panel is already there, nothing new opens
        assert maya_dock.show(bpy.context, 'ATTRIBUTE_EDITOR') == 'FLOATING'
    finally:
        maya_dock.set_role(areas[1], 'STACK')
        wm.allset_dock = 'CHANNEL_BOX'


def test_stack_panel_draws_handle_tabs_and_content():
    wm = bpy.context.window_manager
    areas = _properties_areas(1)
    maya_dock.set_role(areas[0], 'STACK')
    region = next(r for r in areas[0].regions if r.type == 'WINDOW')
    for kind, marker in (('CHANNEL_BOX', "Layers"), ('ATTRIBUTE_EDITOR', None), ('MODELING_TOOLKIT', None)):
        wm.allset_dock = kind
        rec = Recorder()
        with bpy.context.temp_override(area=areas[0], region=region):
            bpy.types.ALLSET_PT_maya_dock.draw(SimpleNamespace(layout=rec), bpy.context)
        ops = [(t, a[0] if a else "") for k, t, a, _p in rec.log if k == "operator"]
        assert ops[0] == (maya_dock.HANDLE, "allset.dock_handle"), ops[:3]
        # #78: the tabs are Maya's vertical strip drawn on the right edge, not a button row
        assert not [t for t, idname in ops if idname == "allset.dock_tab"], ops[:6]
        assert maya_dock.stack_tabs(wm) == ['CHANNEL_BOX', 'ATTRIBUTE_EDITOR', 'MODELING_TOOLKIT']
        if marker:
            assert any(t == marker for k, t, _a, _p in rec.log if k in ("menu", "label")), (kind, rec.log[:12])
    wm.allset_dock = 'CHANNEL_BOX'


def test_menus_start_with_the_tear_off_line():
    cls = next(getattr(bpy.types, n) for n in sorted(dir(bpy.types)) if n.startswith("ALLSET_MT_")
               and (getattr(bpy.types, n).__doc__ or "").startswith("Maya menu: "))
    rec = Recorder()
    cls.draw(SimpleNamespace(layout=rec), bpy.context)
    first = rec.log[0]
    assert first[0] == "operator" and first[2][0] == "allset.menu_tear_off" and first[1] == maya_dock.TEAR_LINE, first
    # the torn-off copy draws the items without the line
    maya_dock._drawing_torn[0] = True
    try:
        rec = Recorder()
        cls.draw(SimpleNamespace(layout=rec), bpy.context)
        assert not any(k == "operator" and a and a[0] == "allset.menu_tear_off" for k, _t, a, _p in rec.log)
    finally:
        maya_dock._drawing_torn[0] = False


def test_template_stack_and_no_viewport_sidebar():
    path = ROOT / "src" / "allset" / "app_template" / "Maya_Workflow_Kit" / "startup.blend"
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=True)
    screen = bpy.data.workspaces["General"].screens[0]
    stack = maya_dock.find_stack(screen)
    view = max((a for a in screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    assert stack is not None
    assert not view.spaces.active.show_region_ui, "no sidebar dock over / inside the viewport"
    assert view.x + view.width <= stack.x, "viewport and tab stack side by side, no overlap"
    assert not any(r.type == 'NAVIGATION_BAR' and r.width > 1 for r in stack.regions)
    assert not hasattr(preferences.get(), "maya_dock_only")
