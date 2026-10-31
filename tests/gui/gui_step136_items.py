"""In a real UI: RMB in component mode — Select All / Deselect All / Invert / Select Hierarchy are
enabled (#62), a greyed row puts its notice in the Help Line while hovered, releasing on Select All selects every
vertex and stays in component mode. Ctrl+RMB on the mesh in object mode opens the convert menu (Maya's Ctrl+RMB convert
marking menu picks its items by shape type) and a row converts the whole object in component mode (main session).
Screenshot: gui_step136_rmb_component.png."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, screenshot, step, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def draw():
    return import_module(MODULE + ".marking.draw")


def main_view():
    status_line = import_module(MODULE + ".ui.status_line")
    return status_line.main_view3d(win().screen)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def _row(s, label):
    return next((it for it in s.layout.items if it.kind == "list" and it.label == label), None)


def _hover(s, label):
    it = _row(s, label)
    _area, region = main_view()
    x = region.x + int(s.center[0] + (it.rect[0] + it.rect[2]) / 2)
    y = region.y + int(s.center[1] + (it.rect[1] + it.rect[3]) / 2)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    return x, y


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
    redraw()


@step
def s_rmb_press():
    _area, region = main_view()
    ob = bpy.data.objects["pCube1"]
    p = location_3d_to_region_2d(region, region.data, ob.location)
    x, y = region.x + int(p.x), region.y + int(p.y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y)


@step
def s_rmb_wait():
    redraw()


@step
def s_rows():
    s = draw().ACTIVE.get("session")
    check("RMB in component mode opens the object marking menu", s is not None)
    if s is None:
        return
    for label in ("Select All", "Deselect All", "Select Hierarchy", "Invert Selection", "Select Similar"):
        it = _row(s, label)
        check(f"{label} is enabled in component mode", it is not None and it.enabled)
    C["s"] = s
    _hover(s, "Time Editor")


@step
def s_notice():
    notices = import_module(MODULE + ".ui.notices")
    check(f"hovering greyed Time Editor shows its notice ({notices.current()!r})", "NLA" in notices.current())
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step136_rmb_component.png"))
    C["xy"] = _hover(C["s"], "Select All")


@step
def s_release():
    x, y = C["xy"]
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_wait():
    redraw()


@step
def s_result():
    ob = bpy.data.objects["pCube1"]
    check("still in component mode", bpy.context.mode == 'EDIT_MESH')
    bm = bmesh.from_edit_mesh(ob.data)
    n = sum(v.select for v in bm.verts)
    check(f"Select All selected every vertex ({n})", n == len(bm.verts))


@step
def s_object_mode():
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.object.mode_set(mode='OBJECT')
    redraw()


@step
def s_ctrl_press():
    _area, region = main_view()
    ob = bpy.data.objects["pCube1"]
    p = location_3d_to_region_2d(region, region.data, ob.location)
    x, y = region.x + int(p.x), region.y + int(p.y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y, ctrl=True)


@step
def s_ctrl_wait():
    redraw()


@step
def s_ctrl_menu():
    s = draw().ACTIVE.get("session")
    check("Ctrl+RMB on a mesh in object mode opens a menu", s is not None)
    if s is None:
        return
    check(f"it is the convert menu ({s.layout.sub.name if hasattr(s.layout.sub, 'name') else '?'})",
          getattr(s.layout.sub, "name", "") == "CTRL_CONVERT")
    it = _row(s, "To Shell")
    check("To Shell is enabled from object mode", it is not None and it.enabled)
    C["s"] = s
    C["xy"] = _hover(s, "To Shell")


@step
def s_ctrl_release():
    x, y = C["xy"]
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y, ctrl=True)


@step
def s_ctrl_wait2():
    redraw()


@step
def s_ctrl_result():
    ob = bpy.data.objects["pCube1"]
    check(f"To Shell from object mode goes to component mode ({bpy.context.mode})", bpy.context.mode == 'EDIT_MESH')
    if bpy.context.mode == 'EDIT_MESH':
        bm = bmesh.from_edit_mesh(ob.data)
        n = sum(v.select for v in bm.verts)
        check(f"the whole object is converted ({n} vertices)", n == len(bm.verts))


run()
