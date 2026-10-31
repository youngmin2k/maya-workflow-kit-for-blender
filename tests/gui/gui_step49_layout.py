"""In a real UI: Maya Workflow Kit layout = Maya General — Tool Box column (clicks set tools, a click under
the tools keeps the selection), the tab stack opens on the Channel Box, Help + Command row, Range Slider
under the Time Slider, quick layout buttons; screenshot."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["ALLSET_FIT_WARP"] = "1"   # the fit only runs right after load (toolbox.FIT_WINDOW)
from sim import MODULE, check, ev, run, scale, step, setup, screenshot, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
toolbox = import_module(MODULE + ".ui.toolbox")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def main_view():
    return max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)


def toolbox_area():
    return next((a for a in win().screen.areas if toolbox.is_toolbox(a.spaces.active)), None)


def tools_region():
    """The Tool Box: the column's toolbar, or the main view's when the column is too narrow for this
    UI scale and Blender has not let the kit resize it yet (ui/toolbox.py fit_columns)."""
    r = next(r for r in toolbox_area().regions if r.type == 'TOOLS')
    if r.width >= toolbox.column_width() - 1:
        return r
    return next(r for r in main_view().regions if r.type == 'TOOLS')


def tool_y(i):
    """Centre of the i-th Tool Box button: 23 px below the top, 35 px apart at effective scale 1.0
    (read from a screenshot)."""
    r = tools_region()
    return round(r.y + r.height - scale() * (23 + 35 * i))


def column_window():
    return next(r for r in toolbox_area().regions if r.type == 'WINDOW')


def active_tool():
    return bpy.context.workspace.tools.from_space_view3d_mode('OBJECT', create=False).idname


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    bpy.ops.allset.create(kind='CUBE')
    C["cube"] = bpy.context.active_object.name
    redraw()


@step
def s_layout():
    tb = toolbox_area()
    want = toolbox.column_width()
    fits = abs(tb.width - want) <= 1
    # the template column has room up to scale 1.6, so unfitted it still draws its toolbar (spare width
    # in the toolbar colour); narrower than the toolbar, the main view shows its toolbar meanwhile
    room = tb.width >= want - 1 and any(r.type == 'TOOLS' and r.width > 1 for r in tb.regions)         and not main_view().spaces.active.show_region_toolbar
    check(f"Tool Box column = one toolbar column at this scale ({tb.width} px, want {want}), or wider with its "
          f"toolbar drawn, or the main view shows its toolbar meanwhile",
          fits or room or main_view().spaces.active.show_region_toolbar)
    check("Tool Box column on the left", tb is not None and tb.x <= 2)   # Blender 5.x keeps areas 2 px in
    outl = next(a for a in win().screen.areas if a.type == 'OUTLINER')
    view = main_view()
    check("Tool Box | Outliner | view, left to right", tb.x < outl.x < view.x)
    # the Maya tab stack is its own area right of the view (not the view's sidebar), on the Channel Box
    md = import_module(MODULE + ".ui.maya_dock")
    props = [a for a in win().screen.areas if a.type == 'PROPERTIES']
    check("the only Properties area is the Maya tab stack, right of the view",
          len(props) == 1 and md.role(props[0]) == 'STACK' and props[0].x >= view.x + view.width)
    check(f"the tab stack opens on the Channel Box ({md.current_tab()})",
          md.current_tab() == 'CHANNEL_BOX' and not view.spaces.active.show_region_ui)
    tl = next(a for a in win().screen.areas if a.ui_type == 'TIMELINE')
    regions = {r.type: r for r in tl.regions}
    check("Range Slider row under the Time Slider", regions['HEADER'].y < regions['WINDOW'].y)
    check("timeline spans the window", tl.x <= 2 and tl.width >= win().width - 4)
    # Rotate = 5th Tool Box button (Select, Lasso, Paint Select, Move, Rotate, Scale)
    r = tools_region()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=tool_y(4))
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_rotate():
    check(f"Tool Box Rotate button sets the Rotate tool ({active_tool()})", active_tool() == "builtin.rotate")


@step
def s_wait():
    pass   # no double click


@step
def s_lasso_hover():
    r = tools_region()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=tool_y(1))


@step
def s_lasso_click():
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_lasso():
    check(f"Tool Box Lasso button ({active_tool()})", active_tool() == "builtin.select_lasso")
    ob = bpy.data.objects[C["cube"]]
    check("cube selected before the empty click", ob.select_get())
    # an empty spot under the quick layout buttons: reaches the Tool Box view's WINDOW region
    col = toolbox_area()
    ev('MOUSEMOVE', 'NOTHING', x=col.x + col.width // 2, y=col.y + 40)
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_empty_click():
    ob = bpy.data.objects[C["cube"]]
    check("a click under the Tool Box keeps the selection", ob.select_get())
    view = main_view()
    ev('MOUSEMOVE', 'NOTHING', x=view.x + view.width // 3, y=view.y + view.height // 2)
    bpy.ops.wm.tool_set_by_id(name="builtin.move", space_type='VIEW_3D')
    with bpy.context.temp_override(window=win(), area=toolbox_area(), region=column_window()):
        bpy.ops.allset.quick_layout(layout='FOUR')
    redraw()


step(redraw)                  # the top row splits one tick later


@step
def s_four():
    fv = import_module(MODULE + ".ui.four_view")
    check("Four View quick layout splits the main view, not the Tool Box",
          fv.is_four(win().screen) and toolbox_area() is not None)
    with bpy.context.temp_override(window=win(), area=toolbox_area(), region=column_window()):
        bpy.ops.allset.quick_layout(layout='SINGLE')
    redraw()


@step
def s_single():
    fv = import_module(MODULE + ".ui.four_view")
    check("Single Perspective quick layout", len(fv.panes(win().screen)) == 1)
    redraw()


@step
def s_rows():
    shelf = import_module(MODULE + ".ui.shelf")
    # the Status Line header and the shelf row (no header: its WINDOW draws tab strip + icons)
    rows = [shelf.strip_area(win().screen), shelf.shelf_row_area(win().screen)]
    hs = [next(r.height for r in a.regions if r.type == ('HEADER' if i == 0 else 'WINDOW')) if a else 0
          for i, a in enumerate(rows)]
    want = round(26 * scale()) - 2
    check(f"Status Line and Shelf rows fully shown at this scale (headers {hs}, want >= {want})",
          all(h >= want for h in hs))
    tb = toolbox_area()
    check(f"Tool Box column resized to one toolbar column ({tb.width} px)",
          abs(tb.width - toolbox.column_width()) <= 1)


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step49_layout.png"))


run()
