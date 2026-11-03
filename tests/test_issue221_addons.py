"""Other add-ons in Maya mode (#221): their top-bar menus, toolbar tools, 3D View header items, sidebar tabs,
context-menu items and keys stay reachable. A small sample add-on is registered inside the test.
GUI: tests/gui/gui_issue221_addons.py."""

import types
from importlib import import_module

import bpy
from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active as TOOLBAR

import kit

menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
status_line = import_module(kit.MODULE + ".ui.status_line")
toolbox = import_module(kit.MODULE + ".ui.toolbox")
panel_menus = import_module(kit.MODULE + ".ui.panel_menus")
tool_keys = import_module(kit.MODULE + ".operators.tool_keys")


class FakeLayout:
    """Records what a draw function puts in a layout."""

    def __init__(self, log=None):
        self.log = [] if log is None else log
        self.operator_context = 'INVOKE_DEFAULT'
        self.ui_units_x = 0
        self.enabled = True

    def _sub(self, *_a, **_k):
        return FakeLayout(self.log)

    row = column = box = split = _sub

    def menu(self, idname, text=None, **kw):
        self.log.append(("menu", idname, text))

    def operator(self, idname, text=None, **kw):
        self.log.append(("op", idname, text))
        return types.SimpleNamespace()

    def __getattr__(self, name):
        def record(*a, **kw):
            self.log.append((name,) + a)
        return record


# --- the sample add-on ---------------------------------------------------------------------------------------

class SAMPLE221_MT_top(bpy.types.Menu):
    bl_idname = "SAMPLE221_MT_top"
    bl_label = "Sample Top"

    def draw(self, context):
        self.layout.operator("sample221.op")


class SAMPLE221_OT_op(bpy.types.Operator):
    bl_idname = "sample221.op"
    bl_label = "Sample Op"

    def execute(self, context):
        return {'FINISHED'}


class SAMPLE221_PT_panel(bpy.types.Panel):
    bl_idname = "SAMPLE221_PT_panel"
    bl_label = "Sample"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Sample"

    def draw(self, context):
        self.layout.label(text="sample")


class Sample221Tool(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "sample221.tool"
    bl_label = "Sample Tool"
    bl_icon = "ops.generic.select_circle"
    bl_keymap = ()


def _top(self, context):
    self.layout.menu("SAMPLE221_MT_top")


def _item(self, context):
    self.layout.operator("sample221.op")


APPENDED = ("VIEW3D_HT_header", "VIEW3D_HT_tool_header", "VIEW3D_MT_editor_menus", "VIEW3D_MT_object",
            "VIEW3D_MT_add", "VIEW3D_MT_object_context_menu")


def _sample_on():
    for cls in (SAMPLE221_MT_top, SAMPLE221_OT_op, SAMPLE221_PT_panel):
        bpy.utils.register_class(cls)
    bpy.utils.register_tool(Sample221Tool)
    bpy.types.TOPBAR_MT_editor_menus.append(_top)
    for name in APPENDED:
        getattr(bpy.types, name).append(_item)


def _sample_off():
    bpy.types.TOPBAR_MT_editor_menus.remove(_top)
    for name in APPENDED:
        getattr(bpy.types, name).remove(_item)
    bpy.utils.unregister_tool(Sample221Tool)
    for cls in (SAMPLE221_PT_panel, SAMPLE221_OT_op, SAMPLE221_MT_top):
        bpy.utils.unregister_class(cls)


def _ctx(**extra):
    c = bpy.context
    win = c.window_manager.windows[0]
    d = dict(area=types.SimpleNamespace(show_menus=True), screen=win.screen, window=win, scene=c.scene,
             mode=c.mode, preferences=c.preferences, window_manager=c.window_manager, workspace=win.workspace)
    d.update(extra)
    return types.SimpleNamespace(**d)


def _menu_bar_log():
    fake = types.SimpleNamespace(layout=FakeLayout())
    status_line.draw_left(fake, _ctx())
    return fake.layout.log


# --- tests ---------------------------------------------------------------------------------------------------

def test_top_bar_menus_follow_the_maya_menus():
    assert not menu_sets.addon_menu_funcs(_ctx())   # the kit's own and Blender's own entries don't count
    assert ("menu_contents", menu_sets.ALLSET_MT_addon_menus.bl_idname) not in _menu_bar_log()
    _sample_on()
    try:
        assert menu_sets.addon_menu_funcs(_ctx()) == [_top]
        log = _menu_bar_log()
        entry = ("menu_contents", menu_sets.ALLSET_MT_addon_menus.bl_idname)
        assert entry in log, log
        maya = [i for i, e in enumerate(log) if e[0] == "menu" and e[1].startswith("ALLSET_MT_")]
        assert log.index(entry) > max(maya), "after the Maya menus"
        # the kit menu draws the add-on's entry
        fake = types.SimpleNamespace(layout=FakeLayout())
        menu_sets.ALLSET_MT_addon_menus.draw(fake, _ctx())
        assert ("menu", "SAMPLE221_MT_top", None) in fake.layout.log, fake.layout.log
        # a full bar puts them at the end of the » menu
        fake = types.SimpleNamespace(layout=FakeLayout())
        status_line.ALLSET_MT_menu_more.draw(fake, _ctx())
        assert fake.layout.log[-1] == entry, fake.layout.log
        # the workspace's add-on filter applies as in Blender's own menus
        ws = bpy.context.window_manager.windows[0].workspace
        _top._owner = "sample221"
        ws.use_filter_by_owner = True
        try:
            assert menu_sets.addon_menu_funcs(_ctx()) == []
        finally:
            ws.use_filter_by_owner = False
            del _top._owner
    finally:
        _sample_off()
    assert not menu_sets.addon_menu_funcs(_ctx())


def test_a_broken_addon_menu_does_not_stop_the_others():
    def broken(self, context):
        raise RuntimeError("broken add-on")

    bpy.types.TOPBAR_MT_editor_menus.append(broken)
    bpy.types.TOPBAR_MT_editor_menus.append(_top)
    try:
        fake = types.SimpleNamespace(layout=FakeLayout())
        menu_sets.ALLSET_MT_addon_menus.draw(fake, _ctx())
        assert ("menu", "SAMPLE221_MT_top", None) in fake.layout.log, fake.layout.log
    finally:
        bpy.types.TOPBAR_MT_editor_menus.remove(_top)
        bpy.types.TOPBAR_MT_editor_menus.remove(broken)


def test_other_addon_tools_stay_in_the_toolbar():
    def ids():
        items = list(toolbox._saved["tools_from_context"].__func__(TOOLBAR, bpy.context, 'OBJECT'))
        return [None if t is None else t.idname for t in toolbox.maya_tools(items, 'OBJECT')]

    plain = ids()
    assert plain == list(toolbox.MAYA_TOOLS) + [None], plain     # the kit's own tools are reached from menus
    _sample_on()
    try:
        got = ids()
        assert got == plain + ["sample221.tool"], got     # after the separator that ends the Maya tools
        tool_keys.LAST['OBJECT'] = "builtin.cursor"            # with a last-tool slot: a separator before it
        try:
            got = ids()
            assert got == plain + ["builtin.cursor", None, "sample221.tool"], got
        finally:
            tool_keys.LAST.clear()
    finally:
        _sample_off()
    assert toolbox.is_other_addon_tool("sample221.tool")
    assert not toolbox.is_other_addon_tool("builtin.move") and not toolbox.is_other_addon_tool("allset.dolly_tool")


def test_header_items_and_blender_menus_keep_other_addons():
    _sample_on()
    try:
        # the kit swaps only Blender's own header draws: appended ones keep drawing
        for name in ("VIEW3D_HT_header", "VIEW3D_HT_tool_header"):
            assert _item in getattr(bpy.types, name).draw._draw_funcs, name
        # the 3D View header's "Blender" menu draws Blender's View / Select / Add / Object menus and what add-ons
        # added to that menu bar
        fake = types.SimpleNamespace(layout=FakeLayout())
        panel_menus.ALLSET_MT_panel_blender.draw(fake, bpy.context)
        menus = [e[1] for e in fake.layout.log if e[0] == "menu"]
        assert "VIEW3D_MT_view" in menus and "VIEW3D_MT_object" in menus, menus
        assert ("op", "sample221.op", None) in fake.layout.log, fake.layout.log
        # sidebar panels of other add-ons poll in the 3D View sidebar
        assert SAMPLE221_PT_panel.is_registered and "poll" not in SAMPLE221_PT_panel.__dict__
    finally:
        _sample_off()


def test_keys_that_reach_blender_ui():
    kc = kit.maya_kc()

    def has(km_name, idname, type_, ctrl=False, **props):
        km = kc.keymaps.get(km_name)
        return any(k.active and k.idname == idname and k.type == type_ and bool(k.ctrl) == ctrl
                   and all(getattr(k.properties, p, None) == v for p, v in props.items())
                   for k in km.keymap_items)

    assert has("3D View Generic", "wm.context_toggle", "RIGHT_BRACKET", ctrl=True,
               data_path="space_data.show_region_ui")        # Ctrl+] = sidebar (add-on tabs)
    assert has("Object Mode", "wm.call_menu", "APP", name="VIEW3D_MT_object_context_menu")   # Menu key
    assert has("Screen", "wm.search_menu", "F", ctrl=True)     # menu search finds add-on menu items


def test_addon_keys_kept():
    kc = bpy.context.window_manager.keyconfigs.addon
    km = kc.keymaps.new("3D View", space_type='VIEW_3D')
    kmi = km.keymap_items.new("sample221.op", 'T', 'PRESS', ctrl=True, alt=True, shift=True)
    try:
        kit.disable()
        kit.enable()
        assert kmi.active and kmi in list(km.keymap_items)
    finally:
        km.keymap_items.remove(kmi)


def test_addon_menu_room_follows_what_they_draw():
    ctx = bpy.context
    u = import_module(kit.MODULE + ".ui.toolbar_fit").unit(ctx.preferences.system.ui_scale or 1.0,
                                                           ctx.preferences.system.pixel_size)

    def one(self, context):
        self.layout.menu("SAMPLE221_MT_top")

    def three(self, context):
        row = self.layout.row(align=True)
        row.menu("SAMPLE221_MT_top")
        row.menu("SAMPLE221_MT_top", text="A much longer add-on menu name")
        op = row.operator("sample221.op", text="", icon='PLUGIN')
        op.anything = 1

    def odd(self, context):
        self.layout.template_ID(context.scene, "camera")      # not sized: keeps the fixed room

    _sample_on()
    try:
        w1 = menu_sets.addon_menus_width(ctx, [one])
        w3 = menu_sets.addon_menus_width(ctx, [three])
        wodd = menu_sets.addon_menus_width(ctx, [odd])
    finally:
        _sample_off()
    assert 1.5 * u < w1 < 5 * u, (w1, u)                   # "Sample Top" + padding, less than the old 5 units
    assert w3 > w1 + 10 * u, (w1, w3, u)                   # a long name takes its room
    assert wodd == int(menu_sets.ADDON_MENU_UNITS * u), (wodd, u)
