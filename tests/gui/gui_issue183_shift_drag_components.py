"""#183 in a real UI (real Shift: the LEFT_SHIFT key goes down first): Shift+drag on the Move manipulator
extrudes the selected edge and the selected vertex too (Smart Extrude), not only faces; the face / object cases are
tests/gui/gui_step26_smart_extrude.py and gui_step22_manip_duplicate.py."""

import os
import sys

import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, screenshot, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def v3d_override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def counts():
    bm = bmesh.from_edit_mesh(bpy.data.objects["Cube"].data)
    return len(bm.verts), len(bm.edges), len(bm.faces)


def arrow(origin, axis):
    _area, region = view3d()
    o = location_3d_to_region_2d(region, region.data, origin)
    a = location_3d_to_region_2d(region, region.data, origin + axis * 0.1)
    d = (a - o).normalized()
    size = bpy.context.preferences.view.gizmo_size * bpy.context.preferences.system.ui_scale
    p = o + d * size * 0.75
    return int(region.x + p.x), int(region.y + p.y), d


def hover(x, y):
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


def select_only(kind):
    """Edge mode with the top front edge / vertex mode with the top front right vertex; returns its centre."""
    ob = bpy.data.objects["Cube"]
    with v3d_override():
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_mode(type=kind)
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    bm = bmesh.from_edit_mesh(ob.data)
    if kind == 'EDGE':
        el = max(bm.edges, key=lambda e: sum(v.co.z - v.co.y for v in e.verts))
        centre = (el.verts[0].co + el.verts[1].co) / 2
    else:
        el = max(bm.verts, key=lambda v: v.co.z - v.co.y + v.co.x)
        centre = el.co.copy()
    el.select = True
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    return ob.matrix_world @ centre


def drag_steps(kind, axis, name):
    @step
    def s_select():
        centre = select_only(kind)
        C[name + "before"] = counts()
        C[name] = arrow(centre, axis)
        hover(*C[name][:2])

    @step
    def s_press():
        x, y, d = C[name]
        ev('LEFT_SHIFT', 'PRESS', shift=True)
        ev('LEFTMOUSE', 'PRESS', x=x, y=y, shift=True)
        for i in range(1, 9):
            ev('MOUSEMOVE', 'NOTHING', x=int(x + d.x * 60 * i / 8), y=int(y + d.y * 60 * i / 8), shift=True)

    @step
    def s_release():
        x, y, d = C[name]
        ev('LEFTMOUSE', 'RELEASE', x=int(x + d.x * 60), y=int(y + d.y * 60), shift=True)
        ev('LEFT_SHIFT', 'RELEASE')

    @step
    def s_wait():
        pass

    @step
    def s_check():
        before, after = C[name + "before"], counts()
        if SHOTS:
            screenshot(os.path.join(SHOTS, f"183_{name}.png"))
        check(f"Shift+drag on the {kind.lower()} = Smart Extrude ({before} -> {after})",
              after[0] > before[0] and after[2] > before[2])


@step
def s_setup():
    C["x"], C["y"] = setup()
    cube = bpy.data.objects["Cube"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o is cube)
    bpy.context.view_layer.objects.active = cube
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    tap('F11')


drag_steps('EDGE', Vector((0, 0, 1)), "edge")
drag_steps('VERT', Vector((1, 0, 0)), "vert")

run()
