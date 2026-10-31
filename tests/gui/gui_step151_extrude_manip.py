"""In a real UI: top face -> Ctrl+E -> Maya's polyExtrudeFace manipulator (three local arrows, scale
cubes, plane handles, centre square) from Maya's persp angle; drag the
red X arrow (Local Translate X, one Ctrl+Z step), the red X scale cube (Local Scale X) and the centre square (uniform
Local Scale). Screenshots: gui_step151_manip.png / _hover.png / _scaled.png (compare with modeling_03.png)."""

import math
import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras import view3d_utils
from mathutils import Euler, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def mod(name):
    return import_module(sys.modules["sim"].MODULE + name)


def cube():
    return bpy.data.objects["Cube"]


def rec():
    return mod(".operators.extrude").active(bpy.context)[1]


def caps_x():
    """x range of the extruded top (the cap vertices)."""
    r = rec()
    bm = bmesh.from_edit_mesh(cube().data)
    bm.verts.ensure_lookup_table()
    xs = [bm.verts[i].co.x for i in r.cap_verts]
    return min(xs), max(xs)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def v3d_ctx():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active)


def handle_point(axis, frac):
    """Window point at ``frac`` arrow units along the manipulator's ``axis`` (0 / 1 / 2) from its centre (one unit =
    in_view.unit_px: wm_gizmo scale = scale_basis x gizmo_size x UI scale)."""
    area, region = view3d()
    in_view = mod(".ui.in_view")
    with v3d_ctx():
        ob, r = in_view.record(bpy.context)
        c, axes, _k = in_view.manip_frame(ob, r)
        upx = in_view.unit_px(bpy.context)
    rv3d = area.spaces.active.region_3d
    p0 = view3d_utils.location_3d_to_region_2d(region, rv3d, c)
    w = view3d_utils.region_2d_to_location_3d(region, rv3d, p0 + Vector((1, 0)), c) - c   # world size of 1 px
    unit = upx * w.length
    p = view3d_utils.location_3d_to_region_2d(region, rv3d, c + axes.col[axis] * unit * frac)
    d = (p - p0).normalized()
    return region.x + round(p.x), region.y + round(p.y), d


def centre_point():
    x, y, _d = handle_point(2, 0.0)
    return x, y


def drag(key, dx, dy):
    """press at C[key], 8 moves to + (dx, dy), release: one step each (snap / modal like a hand)."""
    x, y = C[key][:2]
    yield lambda: ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    yield lambda: ev('LEFTMOUSE', 'PRESS', x=x, y=y)

    def moves():
        for i in range(1, 9):
            ev('MOUSEMOVE', 'NOTHING', x=x + round(dx * i / 8), y=y + round(dy * i / 8))
    yield moves
    yield lambda: ev('LEFTMOUSE', 'RELEASE', x=x + round(dx), y=y + round(dy))


@step
def s_setup():
    C["x"], C["y"] = setup()
    area, _region = view3d()
    rv3d = area.spaces.active.region_3d
    # the startup persp angle, like Maya (from +X, front, above)
    rv3d.view_perspective = 'PERSP'
    rv3d.view_rotation = Euler((math.radians(62), 0, math.radians(42))).to_quaternion()
    rv3d.view_location = (0, 0, 0.3)
    rv3d.view_distance = 5.0
    bpy.context.view_layer.objects.active = cube()
    cube().select_set(True)
    with v3d_ctx():
        bpy.ops.object.mode_set('EXEC_DEFAULT', True, mode='EDIT')
    bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(cube().data)
    for f in bm.faces:
        f.select_set(False)
    for f in bm.faces:
        if f.normal.z > 0.9:
            f.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(cube().data)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] - 300, y=C["y"] - 200)
    redraw()


@step
def s_ctrl_e():
    ev('E', 'PRESS', ctrl=True)
    ev('E', 'RELEASE', ctrl=True)


@step
def s_extruded():
    r = rec()
    with v3d_ctx():
        shown = mod(".ui.in_view").manip_visible(bpy.context)
    check(f"Ctrl+E = polyExtrudeFace1 with the manipulator (got {r and r.name}, shown {shown})",
          r is not None and r.name == "polyExtrudeFace1" and shown)
    redraw()


@step
def s_shot():
    shot("gui_step151_manip.png")
    C["tx"] = handle_point(0, 0.35)
    C["sx"] = handle_point(0, 1.0)
    C["s"] = centre_point()
    C["x0"] = caps_x()
    x, y, _d = C["tx"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    redraw()


@step
def s_hover_wait1():
    redraw()


@step
def s_hover_wait2():
    redraw()


@step
def s_hover_wait3():
    redraw()


@step
def s_hover_shot():
    shot("gui_step151_hover.png")     # Maya manipulators show no tooltip (#98): nothing next to the arrow


def _drag_steps(key, dist_px, along=True, dx=None):
    """Four steps (hover, press, moves, release) of a drag from handle ``key`` (known only after Ctrl+E)."""
    holder = {}

    def make():
        x, y, d = C[key] if len(C[key]) == 3 else (*C[key], Vector((1, 0)))
        vx, vy = (d.x * dist_px, d.y * dist_px) if along else (dx, 0)
        holder["gen"] = list(drag(key, vx, vy))

    @step
    def s_hover():
        make()
        holder["gen"][0]()

    @step
    def s_press():
        holder["gen"][1]()

    @step
    def s_moves():
        holder["gen"][2]()

    @step
    def s_release():
        holder["gen"][3]()


_drag_steps("tx", 60)


@step
def s_tx_done():
    r = rec()
    x0, x1 = caps_x()
    ltx = r.params["local_translate_x"] if r else None
    check(f"drag the red X arrow -> Local Translate X > 0, the top moves +X, Z untouched "
          f"(ltx {ltx}, caps x {C['x0']} -> {(x0, x1)}, ltz {r and r.params['local_translate_z']})",
          r is not None and ltx > 0.05 and x0 > C["x0"][0] + 0.03 and abs(r.params["local_translate_z"]) < 1e-6)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] - 300, y=C["y"] - 200)
    redraw()


@step
def s_undo():
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undone():
    r = rec()
    check(f"one Ctrl+Z takes the X drag back (ltx {r and r.params['local_translate_x']}, caps x {caps_x()})",
          r is not None and abs(r.params["local_translate_x"]) < 1e-6 and abs(caps_x()[0] - C["x0"][0]) < 1e-5)
    redraw()


_drag_steps("sx", 50)


@step
def s_sx_done():
    r = rec()
    lsx = r.params["local_scale_x"] if r else None
    x0, x1 = caps_x()
    check(f"drag the red X scale cube out -> Local Scale X > 1, Y / Z scale 1 (lsx {lsx}, caps x {(x0, x1)})",
          r is not None and lsx > 1.1 and x1 - x0 > (C["x0"][1] - C["x0"][0]) * 1.1
          and r.params["local_scale_y"] == 1.0 and r.params["local_scale_z"] == 1.0)
    C["lsx"] = lsx
    redraw()


_drag_steps("s", 0, along=False, dx=-40)


@step
def s_s_done():
    r = rec()
    p = r.params if r else {}
    check(f"drag the centre square left -> uniform Local Scale (got {[p.get(k) for k in ('local_scale_x', 'local_scale_y', 'local_scale_z')]})",
          r is not None and p["local_scale_y"] < 0.9 and abs(p["local_scale_y"] - p["local_scale_z"]) < 1e-6
          and p["local_scale_x"] < C["lsx"])
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] - 300, y=C["y"] - 200)
    redraw()


@step
def s_end():
    shot("gui_step151_scaled.png")


run()
