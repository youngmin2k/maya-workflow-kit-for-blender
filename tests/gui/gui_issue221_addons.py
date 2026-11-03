"""#221: in Maya mode, a Maya Workflow Kit layout keeps other add-ons' UI in reach. A sample add-on registered
here adds a top-bar menu, a toolbar tool, a 3D View header item, a sidebar tab and an object context-menu item:
the Maya menu bar draws the top-bar menu after the Maya menus, the 3D View toolbar lists the tool after the Maya
tools, the header item draws, Ctrl+] over the viewport shows the sidebar with the add-on's tab and the Menu key
opens Blender's object context menu with the add-on's item."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
SEEN = {"top": set(), "header": set(), "panel": set(), "context": 0, "tools": []}
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


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
        SEEN["panel"].add(context.area.as_pointer())
        self.layout.label(text="sample")


class Sample221Tool(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "sample221.tool"
    bl_label = "Sample Tool"
    bl_icon = "ops.generic.select_circle"
    bl_keymap = ()


def _top(self, context):
    SEEN["top"].add(context.area.type if context.area is not None else None)
    self.layout.menu("SAMPLE221_MT_top")


def _header(self, context):
    if context.region is not None:
        SEEN["header"].add(context.region.type)
    self.layout.label(text="Sample")


def _context_item(self, context):
    SEEN["context"] += 1
    self.layout.operator("sample221.op")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()
    mod("ui.status_line").redraw_top_bars()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_before():
    redraw()


@step
def s_count_menus():
    C["shown"] = mod("ui.status_line").shown_menus(win())[1]    # Maya menus in the bar before the add-on


@step
def s_register():
    for cls in (SAMPLE221_MT_top, SAMPLE221_OT_op, SAMPLE221_PT_panel):
        bpy.utils.register_class(cls)
    bpy.utils.register_tool(Sample221Tool)
    bpy.types.TOPBAR_MT_editor_menus.append(_top)
    bpy.types.VIEW3D_HT_header.append(_header)
    bpy.types.VIEW3D_MT_object_context_menu.append(_context_item)
    # record the toolbar the real draw builds
    toolbox = mod("ui.toolbox")
    original = toolbox.maya_tools

    def recording(items, mode):
        out = original(items, mode)
        if out is not None:
            SEEN["tools"].append([None if t is None else t.idname for t in out])
        return out

    toolbox.maya_tools = recording
    C["maya_tools"] = original
    redraw()


@step
def s_wait():
    redraw()


@step
def s_more_menu():
    # a full menu bar keeps the add-on's menu behind Maya's »: open it
    C["inline"] = 'TOPBAR' in SEEN["top"]
    names, n = mod("ui.status_line").shown_menus(win())
    C["n"] = (len(names), n)
    if not C["inline"]:
        SEEN["top"].clear()
        area, r = view3d()
        with bpy.context.temp_override(window=win(), area=area, region=r):
            bpy.ops.wm.call_menu('INVOKE_DEFAULT', name=mod("ui.status_line").ALLSET_MT_menu_more.bl_idname)


@step
def s_check_bars():
    total, n = C["n"]
    check(f"the add-on's top-bar menu is in the Maya menu bar or behind its » (in line {C['inline']}, "
          f"drawn {SEEN['top']})", C["inline"] or bool(SEEN["top"]))
    check(f"the Maya menus keep their place ({C['shown']} before, {n} of {total} now)",
          n >= min(C["shown"], total) - 1)
    if not C["inline"]:
        ev('ESC', 'PRESS')
        ev('ESC', 'RELEASE')


@step
def s_check_view():
    check(f"the add-on's 3D View header item draws ({sorted(SEEN['header'])})", 'HEADER' in SEEN["header"])
    drawn = [ids for ids in SEEN["tools"] if "builtin.move" in ids]
    check(f"the toolbar lists the add-on tool after the Maya tools ({drawn[-1] if drawn else None})",
          bool(drawn) and drawn[-1][-1] == "sample221.tool"
          and drawn[-1].index("sample221.tool") > drawn[-1].index("builtin.scale")
          and drawn[-1][-2] is None and drawn[-1][-3] != drawn[-1][-2])
    area, r = view3d()
    C["area"] = area.as_pointer()
    C["ui_before"] = area.spaces.active.show_region_ui
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    ev('LEFT_CTRL', 'PRESS')
    ev('RIGHT_BRACKET', 'PRESS', ctrl=True)
    ev('RIGHT_BRACKET', 'RELEASE', ctrl=True)
    ev('LEFT_CTRL', 'RELEASE')



@step
def s_sidebar_tab():
    area, _r = view3d()
    space = area.spaces.active
    check(f"Ctrl+] toggled the viewport sidebar ({C['ui_before']} -> {space.show_region_ui})",
          space.show_region_ui != C["ui_before"])
    if space.show_region_ui:
        ui = next(r for r in area.regions if r.type == 'UI')
        try:
            ui.active_panel_category = "Sample"
        except (TypeError, AttributeError):
            pass   # the tabs aren't drawn yet: the next tick
    redraw()


@step
def s_sidebar_tab_again():
    area, _r = view3d()
    ui = next(r for r in area.regions if r.type == 'UI')
    try:
        ui.active_panel_category = "Sample"
    except (TypeError, AttributeError):
        pass
    area.tag_redraw()


@step
def s_check_panel():
    area, r = view3d()
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_issue221_sidebar.png"))
    check("the add-on's sidebar tab draws in the viewport sidebar", area.as_pointer() in SEEN["panel"])
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 3)
    ev('APP', 'PRESS')
    ev('APP', 'RELEASE')


@step
def s_wait_menu():
    pass


@step
def s_check_context():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_issue221_context.png"))
    check(f"the Menu key opens Blender's object context menu with the add-on item ({SEEN['context']})",
          SEEN["context"] > 0)
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


@step
def s_cleanup():
    mod("ui.toolbox").maya_tools = C["maya_tools"]
    bpy.types.VIEW3D_MT_object_context_menu.remove(_context_item)
    bpy.types.VIEW3D_HT_header.remove(_header)
    bpy.types.TOPBAR_MT_editor_menus.remove(_top)
    bpy.utils.unregister_tool(Sample221Tool)
    for cls in (SAMPLE221_PT_panel, SAMPLE221_OT_op, SAMPLE221_MT_top):
        bpy.utils.unregister_class(cls)


run()
