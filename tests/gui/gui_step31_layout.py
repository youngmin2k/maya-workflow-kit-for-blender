"""In a real UI: Maya Workflow Kit layout Outliner (width, DAG rows), leaving four views keeps the
picked view's name, W hold menu toggles show their state (engine and pie fallback), timeline;
screenshots."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def prefs():
    return bpy.context.preferences.addons[MODULE].preferences


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def main_view():
    return max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)


def left_outliner():
    return min((a for a in win().screen.areas if a.type == 'OUTLINER'), key=lambda a: a.x)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    for kind in ('CUBE', 'SPHERE', 'CYLINDER'):
        bpy.ops.allset.create(kind=kind)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.data.objects["pCube1"].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["pCube1"]
    bpy.ops.allset.group()   # group1 > pCube1, like the step-23 audit scene
    area = main_view()
    ev('MOUSEMOVE', 'NOTHING', x=area.x + area.width // 2, y=area.y + area.height // 2)
    redraw()


@step
def s_layout():
    so = left_outliner()
    sp = so.spaces.active
    C["outliner_w"] = so.width
    check(f"left Outliner ~20% of the window ({so.width} px)", so.width >= 250)
    check("Outliner = Maya DAG: objects only, no collection rows, no render column",
          not sp.use_filter_collection and not sp.show_restrict_column_render
          and not sp.use_filter_object_content)
    redraw()


@step
def s_layout_shot():
    shot("gui_step31_layout.png")
    area = main_view()
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.toggle_quad_view()
    C["area"] = area


@step
def s_quad_wait():
    redraw()                  # the top row splits one tick later


@step
def s_quad():
    fv = import_module(MODULE + ".ui.four_view")
    placed = fv.roles(win().screen)
    print("STATE panels", len(fv.panes(win().screen)))
    check("four views on", len(placed) == 4)
    tl = placed["top"]                       # Maya's top-left panel = top
    C["tl"] = tl
    reg = next(r for r in tl.regions if r.type == 'WINDOW')
    ev('MOUSEMOVE', 'NOTHING', x=reg.x + reg.width // 2, y=reg.y + reg.height // 2)


@step
def s_quad_shot():
    shot("gui_step31_quad.png")
    tl = C["tl"]
    reg = next(r for r in tl.regions if r.type == 'WINDOW')
    rv = reg.data
    C["picked"] = (rv.view_perspective, rv.is_orthographic_side_view)
    with bpy.context.temp_override(window=win(), area=tl, region=reg):
        bpy.ops.allset.toggle_quad_view()
    C["area"] = main_view()


@step
def s_single():
    fv = import_module(MODULE + ".ui.four_view")
    C["area"] = main_view()
    rv = C["area"].spaces.active.region_3d
    print("STATE picked", C["picked"], "single", rv.view_perspective, rv.is_orthographic_side_view)
    check("back to one view", len(fv.panes(win().screen)) == 1)
    check("the kept view is still a named axis view (header 'Top Orthographic', not 'User')",
          rv.view_perspective == 'ORTHO' and rv.is_orthographic_side_view == C["picked"][1] is True)
    redraw()


@step
def s_single_shot():
    shot("gui_step31_quad_back.png")
    area = C["area"]
    region = next(r for r in area.regions if r.type == 'WINDOW')
    region.data.view_perspective = 'PERSP'
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.view_home()   # Maya persp again for the menu shots
    bpy.context.scene.frame_set(8)
    # a move in its own tick first (the first key after a layout change is lost under event simulation)
    ev('MOUSEMOVE', 'NOTHING', x=area.x + area.width // 3, y=area.y + area.height // 2)
    redraw()


@step
def s_timeline_shot():
    shot("gui_step31_timeline_f8.png")
    area = C["area"]
    x, y = area.x + area.width // 3, area.y + area.height // 2
    C["w"] = (x, y)
    bpy.ops.object.select_all(action='DESELECT')
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('W', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_w_wait():
    redraw()


@step
def s_w_shot():
    draw = import_module(MODULE + ".marking.draw")
    s = draw.ACTIVE.get("session")
    labels = [i.label for i in s.layout.items] if s else []
    check("W + LMB opens the Move tool options with Shift Duplicate", "Shift Duplicate" in labels)
    shot("gui_step31_w_menu.png")
    x, y = C["w"]
    tap_esc(x, y)


def tap_esc(x, y):
    ev('ESC', 'PRESS', x=x, y=y)
    ev('ESC', 'RELEASE', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    ev('W', 'RELEASE', x=x, y=y)


@step
def s_pie():
    marking = import_module(MODULE + ".marking")
    prefs().marking_menu_style = 'PIE'
    x, y = C["w"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    with bpy.context.temp_override(window=win(), area=C["area"]):
        bpy.ops.wm.call_menu_pie(name=marking.idname("OPT_MOVE"))


@step
def s_pie_wait():
    redraw()


@step
def s_pie_shot():
    shot("gui_step31_w_pie.png")
    x, y = C["w"]
    ev('ESC', 'PRESS', x=x, y=y)
    ev('ESC', 'RELEASE', x=x, y=y)
    prefs().marking_menu_style = 'ENGINE'


run()
