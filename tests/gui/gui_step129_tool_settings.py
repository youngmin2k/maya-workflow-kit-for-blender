"""#3, #29: in a real UI: the Maya Workflow Kit layout, edit mode. One click on the Tool Box's Lasso icon only
sets the tool; a second click within the double-click time (Maya double-click) opens the Tool Settings dock with the
Lasso Tool's Maya sections; the Select Tool shows Common Selection Options / Soft Selection / Symmetry Settings; Paint
Selection and Insert Edge Loop get their Maya sections too (screenshots of the dock)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, find_button, run, setup, step, win, _steps, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name):
    if SHOTS:
        with bpy.context.temp_override(window=win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def in_v3d(fn, *a, **kw):
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return fn(*a, **kw)


def toolbox():
    tb = mod(".ui.toolbox")
    area = next(a for a in win().screen.areas if tb.is_toolbox(a.spaces.active))
    return area, next(r for r in area.regions if r.type == 'TOOLS')


def dock():
    return mod(".ui.tool_dock").find(win().screen)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def tool_id():
    return bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False).idname


def dock_state():
    """(tool kind, Blender panels hidden, section titles) as the dock sees them."""
    d = dock()
    ts = mod(".ui.tool_settings")
    with bpy.context.temp_override(window=win(), area=d, region=next(r for r in d.regions if r.type == 'WINDOW'),
                                   space_data=d.spaces.active):
        kind = ts.tool_kind(bpy.context)
        hidden = ts.hides_blender_panels(bpy.context)
    return kind, hidden, [s[1] for s in ts.sections(kind)] if kind else []


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    # Simulated clicks are one timer tick (0.4 s) apart: give the double click room (sandbox preferences only).
    C["dbl"] = bpy.context.preferences.inputs.mouse_double_click_time
    bpy.context.preferences.inputs.mouse_double_click_time = 2500
    in_v3d(bpy.ops.allset.create, kind='CUBE')
    in_v3d(bpy.ops.object.mode_set, mode='EDIT')
    in_v3d(bpy.ops.wm.tool_set_by_id, name="builtin.move")
    check("no Tool Settings dock at the start", dock() is None)
    redraw()


def _find_lasso():
    return find_button(toolbox, lambda path, cmd: "select_lasso" in cmd, C, "lasso", step_px=6, x_frac=0.5)


@step
def s_find():
    _steps.insert(0, _find_lasso())


@step
def s_hover():
    check(f"the Tool Box has the Lasso icon ({C.get('lasso')})", C.get("lasso") is not None)
    if C.get("lasso") is None:
        _steps.clear()
        return
    x, y = C["lasso"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_click1():
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_click1_check():
    redraw()
    check(f"one click sets the Lasso tool ({tool_id()}) and opens nothing",
          tool_id() == "builtin.select_lasso" and dock() is None)
    x, y = C["lasso"]
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


@step
def s_click2():
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_wait():
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_double_check():
    d = dock()
    check("double-click on the Lasso icon opens the Tool Settings dock", d is not None)
    if d is None:
        return
    kind, hidden, titles = dock_state()
    check(f"dock shows the Lasso Tool's Maya sections ({kind}, {titles}), Blender's panels hidden",
          kind == 'LASSO' and hidden and titles[0] == "Lasso Settings")
    shot("gui_step129_ts_lasso.png")
    C["areas"] = len(win().screen.areas)
    # a second double-click keeps the one dock (focus, not a second dock)
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_again():
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_again_check():
    redraw()
    check(f"double-click with the dock open keeps one dock ({len(win().screen.areas)} areas)",
          dock() is not None and len(win().screen.areas) == C["areas"])
    in_v3d(bpy.ops.wm.tool_set_by_id, name="builtin.select_box")
    redraw()


@step
def s_select():
    kind, hidden, titles = dock_state()
    check(f"Select Tool: {titles}", kind == 'SELECT' and hidden and titles == [
        "Common Selection Options", "Soft Selection", "Symmetry Settings"])
    shot("gui_step129_ts_select.png")
    in_v3d(bpy.ops.wm.tool_set_by_id, name="builtin.select_circle")
    redraw()


@step
def s_paint():
    kind, hidden, titles = dock_state()
    check(f"Paint Selection Tool: {titles}", kind == 'PAINT_SELECT' and hidden and titles[:2] == [
        "Brush", "Paint Operations"])
    shot("gui_step129_ts_paint_select.png")
    in_v3d(bpy.ops.wm.tool_set_by_id, name="allset.insert_edge_loop_tool")
    redraw()


@step
def s_loop():
    kind, hidden, titles = dock_state()
    check(f"Insert Edge Loop Tool: {titles}", kind == 'INSERT_EDGE_LOOP' and hidden and titles == [
        "Description", "Settings"])
    shot("gui_step129_ts_insert_edge_loop.png")
    in_v3d(bpy.ops.wm.tool_set_by_id, name="builtin.knife")
    redraw()


@step
def s_knife():
    kind, hidden, _titles = dock_state()
    check("Multi-Cut (no kit sections): Blender's tool panel stays", kind is None and not hidden)
    bpy.context.preferences.inputs.mouse_double_click_time = C["dbl"]


run()
