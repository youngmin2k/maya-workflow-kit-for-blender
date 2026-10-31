"""In a real UI: Alt+Shift+LMB mostly-vertical drag tumbles about the view's right axis
only; Alt+Shift+MMB diagonal drag in the front view tracks along X only; Left arrow in vertex
mode walks to the next vertex."""

import os
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def rv3d():
    return view3d()[0].spaces.active.region_3d


def v3d_override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def drag(button, dx, dy):
    """Press, moves and release in separate ticks (a modal started on press needs one)."""
    @step
    def press():
        ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"], shift=True, alt=True)
        ev(button, 'PRESS', x=C["x"], y=C["y"], shift=True, alt=True)

    @step
    def move():
        for i in range(1, 9):
            ev('MOUSEMOVE', 'NOTHING', x=C["x"] + dx * i // 8, y=C["y"] + dy * i // 8, shift=True, alt=True)

    @step
    def release():
        ev(button, 'RELEASE', x=C["x"] + dx, y=C["y"] + dy, shift=True, alt=True)


@step
def s_setup():
    C["x"], C["y"] = setup()
    r = rv3d()
    C["rot0"] = r.view_rotation.copy()
    C["right0"] = r.view_rotation @ Vector((1, 0, 0))


drag('LEFTMOUSE', 12, 70)   # mostly vertical: rotate about the right axis only


@step
def s_tumbled():
    r = rv3d()
    right = r.view_rotation @ Vector((1, 0, 0))
    angle = r.view_rotation.rotation_difference(C["rot0"]).angle
    check(f"Alt+Shift+LMB vertical drag tumbled the view ({angle:.3f} rad)", angle > 0.1)
    check(f"... about the view's right axis only (right moved {(right - C['right0']).length:.5f})",
          (right - C["right0"]).length < 1e-4)
    with v3d_override():
        bpy.ops.view3d.view_axis(type='FRONT')
    C["loc0"] = r.view_location.copy()


drag('MIDDLEMOUSE', 90, 35)  # diagonal, horizontal wins: track along X only


@step
def s_tracked():
    d = rv3d().view_location - C["loc0"]
    check(f"Alt+Shift+MMB diagonal drag in the front view moved along X ({tuple(round(c, 4) for c in d)})",
          abs(d.x) > 0.05 and abs(d.y) < 1e-6 and abs(d.z) < 1e-6)
    cube = bpy.data.objects["Cube"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o is cube)
    bpy.context.view_layer.objects.active = cube
    with v3d_override():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(cube.data)
    v = next(v for v in bm.verts if (v.co - Vector((1, -1, 1))).length < 1e-4)
    v.select_set(True)
    bm.select_history.add(v)
    bmesh.update_edit_mesh(cube.data)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('LEFT_ARROW', 'PRESS')
    ev('LEFT_ARROW', 'RELEASE')


@step
def s_walked():
    cube = bpy.data.objects["Cube"]
    sel = [tuple(round(c) for c in v.co) for v in bmesh.from_edit_mesh(cube.data).verts if v.select]
    check(f"Left arrow walked the vertex (1,-1,1) to its left neighbour in the front view ({sel})",
          sel == [(-1, -1, 1)])
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step39_pickwalk.png"))


run()
