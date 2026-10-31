"""In a real UI: Maya's docking model. The Maya Workflow Kit layout has the Channel Box / Layer Editor | Attribute Editor
| Modeling Toolkit tab stack in its own area right of the viewport (no sidebar, no overlap). Clicking the stack's
::::: handle tears the Channel Box off into a floating window that shows only it; Dock puts it back; a floating
Attribute Editor closed by its window docks back by itself; Tool Settings and the Outliner tear off and dock back;
a menu tears off into a floating window; with no stack, Windows > General Editors > Attribute Editor opens a
floating Attribute Editor. Screenshots: gui_step116_*.png."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, px, run, setup, step, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def dock():
    return mod(".ui.maya_dock")


def wins():
    return list(bpy.context.window_manager.windows)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def view():
    return max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)


def stack():
    return dock().find_stack(win().screen)


def region(area, kind='WINDOW'):
    return next(r for r in area.regions if r.type == kind)


def floating():
    return [w for w in wins() if dock().is_floating(w)]


def redraw():
    for w in wins():
        for a in w.screen.areas:
            a.tag_redraw()


def in_area(window, area, fn, region_type='WINDOW', **kw):
    with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region(area, region_type)):
        return fn(**kw)


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_layout():
    bpy.ops.allset.keymap_activate()
    s, v = stack(), view()
    check("the Maya Workflow Kit layout has Maya's tab stack as its own area", s is not None)
    check(f"the viewport has no sidebar and ends where the stack begins (view {v.x}+{v.width}, stack {s and s.x})",
          s is not None and not v.spaces.active.show_region_ui and v.x + v.width <= s.x)
    check("the viewport's main region covers the whole area (nothing drawn over it)",
          region(v).width == v.width)
    redraw()


@step
def s_layout_shot():
    shot("gui_step116_layout.png")
    r = region(stack())
    C["handle"] = (r.x + px(30), r.y + r.height - px(16))
    ev('MOUSEMOVE', 'NOTHING', x=C["handle"][0], y=C["handle"][1])


@step
def s_click_handle():
    ev('LEFTMOUSE', 'PRESS', x=C["handle"][0], y=C["handle"][1])
    ev('LEFTMOUSE', 'RELEASE', x=C["handle"][0], y=C["handle"][1])


@step
def s_torn():
    redraw()


@step
def s_torn_check():
    fl = floating()
    wm = bpy.context.window_manager
    check(f"clicking the ::::: handle tears the Channel Box off into a floating window ({len(fl)} floating)", len(fl) == 1)
    if fl:
        C["float"] = fl[0]
        areas = fl[0].screen.areas
        check(f"the floating window holds only the Channel Box ({[(a.type, dock().role(a)) for a in areas]})",
              len(areas) == 1 and dock().role(areas[0]) == 'CHANNEL_BOX')
    check(f"the stack's tabs no longer list it ({dock().stack_tabs(wm)}), it shows {dock().current_tab(wm)}",
          dock().stack_tabs(wm) == ['ATTRIBUTE_EDITOR', 'MODELING_TOOLKIT']
          and dock().current_tab(wm) == 'ATTRIBUTE_EDITOR')
    redraw()


@step
def s_torn_shot():
    shot("gui_step116_torn_main.png")
    if C.get("float"):
        shot("gui_step116_torn_float.png", C["float"])
        w = C["float"]
        in_area(w, w.screen.areas[0], bpy.ops.allset.dock_back, action='DOCK')


@step
def s_docked_wait():
    pass


@step
def s_docked():
    wm = bpy.context.window_manager
    check(f"Dock closes the floating window ({len(floating())} floating)", not floating())
    check(f"... and the Channel Box is the stack's tab again ({dock().current_tab(wm)}, {dock().stack_tabs(wm)})",
          dock().current_tab(wm) == 'CHANNEL_BOX' and len(dock().stack_tabs(wm)) == 3)
    wm.allset_dock = 'ATTRIBUTE_EDITOR'
    in_area(win(), stack(), bpy.ops.allset.dock_handle, )


@step
def s_ae_torn():
    fl = floating()
    check("the Attribute Editor tears off too",
          len(fl) == 1 and dock().role(fl[0].screen.areas[0]) == 'ATTRIBUTE_EDITOR')
    if fl:
        with bpy.context.temp_override(window=fl[0]):
            bpy.ops.wm.window_close()      # the window's own close button


@step
def s_ae_closed():
    wm = bpy.context.window_manager
    check(f"closing the floating window docks it back ({dock().stack_tabs(wm)})",
          not floating() and 'ATTRIBUTE_EDITOR' in dock().stack_tabs(wm))
    wm.allset_dock = 'CHANNEL_BOX'
    bpy.ops.allset.editor_toggle(editor='TOOL_SETTINGS')      # Tool Settings dock left of the viewport


@step
def s_tool_wait():
    pass


@step
def s_tool_open():
    td = mod(".ui.tool_dock")
    area = td.find(win().screen)
    check("Tool Settings dock is open", area is not None and td.is_dock(area))
    if area is not None:
        in_area(win(), area, bpy.ops.allset.dock_handle)


@step
def s_tool_torn():
    td = mod(".ui.tool_dock")
    fl = floating()
    check("Tool Settings tears off into a floating window (and leaves the layout)",
          len(fl) == 1 and td.is_dock(fl[0].screen.areas[0]) and td.find(win().screen) is None)
    redraw()


@step
def s_tool_shot():
    fl = floating()
    if fl:
        shot("gui_step116_tool_float.png", fl[0])
        in_area(fl[0], fl[0].screen.areas[0], bpy.ops.allset.dock_back, action='DOCK')


@step
def s_tool_back_wait():
    pass


@step
def s_tool_back():
    td = mod(".ui.tool_dock")
    check("Dock puts Tool Settings back left of the viewport",
          not floating() and td.find(win().screen) is not None)


@step
def s_tool_ready():
    td = mod(".ui.tool_dock")
    area = td.find(win().screen)
    if area is not None:
        td.close_dock(bpy.context, win())
    outl = next((a for a in win().screen.areas if a.type == 'OUTLINER'), None)
    C["outliner_x"] = outl.x if outl else None
    if outl is not None:
        in_area(win(), outl, bpy.ops.allset.dock_handle, region_type='HEADER')


@step
def s_outliner_torn():
    fl = floating()
    check("the Outliner tears off by its header handle",
          len(fl) == 1 and fl[0].screen.areas[0].type == 'OUTLINER'
          and not any(a.type == 'OUTLINER' for a in win().screen.areas))
    redraw()


@step
def s_outliner_shot():
    fl = floating()
    if fl:
        shot("gui_step116_outliner_float.png", fl[0])
        in_area(fl[0], fl[0].screen.areas[0], bpy.ops.allset.dock_back, region_type='HEADER', action='DOCK')


@step
def s_outliner_wait():
    pass


@step
def s_outliner_back():
    outl = next((a for a in win().screen.areas if a.type == 'OUTLINER'), None)
    check(f"Dock puts the Outliner back left of the viewport ({outl and outl.x} < {view().x})",
          not floating() and outl is not None and outl.x < view().x)
    menus = mod(".ui.menu_sets")
    C["menu"] = menus.menu_idname(next(iter(menus.menus_for_set(menus.current_set()))))
    bpy.ops.allset.menu_tear_off(menu=C["menu"])


@step
def s_menu_wait():
    redraw()


@step
def s_menu_torn():
    fl = floating()
    check(f"a menu's tear-off line opens it as a floating window ({C['menu']})",
          len(fl) == 1 and dock().role(fl[0].screen.areas[0]) == 'MENU')
    redraw()


@step
def s_menu_shot():
    fl = floating()
    if fl:
        shot("gui_step116_menu_float.png", fl[0])
        in_area(fl[0], fl[0].screen.areas[0], bpy.ops.allset.dock_back, action='CLOSE')


@step
def s_no_stack():
    check("Close closes the torn-off menu", not floating())
    bpy.ops.allset.editor_toggle(editor='CHANNEL_BOX')      # shown -> hidden: the tab stack closes


@step
def s_no_stack_check():
    check("the Channel Box toggle hides the tab stack", stack() is None)
    v = view()
    with bpy.context.temp_override(window=win(), area=v, region=region(v)):
        bpy.ops.allset.menu_item(item="Windows/General Editors/Attribute Editor")


@step
def s_ae_window_wait():
    redraw()


@step
def s_ae_window():
    fl = floating()
    check("with no tab stack, Windows > General Editors > Attribute Editor opens a floating Attribute Editor",
          len(fl) == 1 and dock().role(fl[0].screen.areas[0]) == 'ATTRIBUTE_EDITOR')
    if fl:
        shot("gui_step116_ae_window.png", fl[0])
        with bpy.context.temp_override(window=fl[0]):
            bpy.ops.wm.window_close()
    bpy.ops.allset.editor_toggle(editor='CHANNEL_BOX')      # hidden -> shown: the stack comes back


@step
def s_stack_back_wait():
    redraw()


@step
def s_stack_back():
    check("the Channel Box toggle opens the tab stack again right of the viewport",
          stack() is not None and stack().x >= view().x + view().width)


run()
