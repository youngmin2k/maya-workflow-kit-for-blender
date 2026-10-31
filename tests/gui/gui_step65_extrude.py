"""In a real UI (Maya modeling workflow): top face -> Ctrl+E -> extrude
manipulator + In-View Editor (polyExtrudeFace1) -> drag the Thickness row -> 0.5 -> Channel Box INPUTS
polyExtrudeFace1 Divisions 2 -> 16 vertices -> Ctrl+Z -> Divisions 1 again -> drag the blue arrow -> Local
Translate Z changes. Screenshots vs shots/modeling_03.png / modeling_04.png."""

import os
import sys
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, dock_area, dock_region, ev, find_button, open_inputs, px, run, scroll_channel_box, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def mod(name):
    return import_module(sys.modules["sim"].MODULE + name)


def cube():
    return bpy.data.objects["Cube"]


def counts():
    bm = bmesh.from_edit_mesh(cube().data)
    return len(bm.verts), len(bm.faces)


def top_z():
    return max(v.co.z for v in bmesh.from_edit_mesh(cube().data).verts)


def rec():
    return mod(".operators.extrude").active(bpy.context)[1]


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def v3d_ctx():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active)


def in_view_rows():
    """Window positions of the In-View rows' centres (the box layout of this view)."""
    area, region = view3d()
    in_view = mod(".ui.in_view")
    with v3d_ctx():
        _r, lay = in_view.current_layout(bpy.context)
    if lay is None:
        return None
    return {f: (region.x + round((x0 + x1) / 2), region.y + round((y0 + y1) / 2)) for f, x0, y0, x1, y1 in lay["rows"]}


def arrow_point():
    """A window point on the blue arrow's shaft (a bit out from the faces' centre along the normal)."""
    from bpy_extras import view3d_utils
    area, region = view3d()
    in_view = mod(".ui.in_view")
    with v3d_ctx():
        ob, r = in_view.record(bpy.context)
        c, n, _k = in_view.cap_frame(ob, r)
    rv3d = area.spaces.active.region_3d
    p0 = view3d_utils.location_3d_to_region_2d(region, rv3d, c)
    p1 = view3d_utils.location_3d_to_region_2d(region, rv3d, c + n * 0.01)
    d = (p1 - p0).normalized()
    p = p0 + d * px(45)
    return region.x + round(p.x), region.y + round(p.y), d


@step
def s_setup():
    C["x"], C["y"] = setup()
    area, _region = view3d()
    dock_area('CHANNEL_BOX')    # Maya's tab stack right of the viewport (was the 3D View sidebar)
    bpy.context.view_layer.objects.active = cube()
    cube().select_set(True)
    with v3d_ctx():
        bpy.ops.object.mode_set('EXEC_DEFAULT', True, mode='EDIT')     # an undo step, like Tab
    bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(cube().data)
    for f in bm.faces:
        f.select_set(False)
    for f in bm.faces:   # deselect first: a later face's select_set(False) would drop shared verts
        if f.normal.z > 0.9:
            f.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(cube().data)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] - px(200), y=C["y"] - px(150))
    redraw()


@step
def s_ctrl_e():
    ev('E', 'PRESS', ctrl=True)
    ev('E', 'RELEASE', ctrl=True)


@step
def s_extruded():
    r = rec()
    check(f"Ctrl+E = polyExtrudeFace1, a zero-length extrusion (got {r and r.name}, {counts()})",
          r is not None and r.name == "polyExtrudeFace1" and counts() == (12, 10))
    with v3d_ctx():
        check("the extrude manipulator / In-View Editor show", mod(".ui.in_view").manip_visible(bpy.context))
    redraw()


@step
def s_shot_extrude():
    shot("gui_step65_extrude.png")
    C["rows"] = in_view_rows()
    check(f"In-View rows on screen ({C['rows'] and list(C['rows'])})", C["rows"] is not None)
    x, y = C["rows"]["thickness"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_press_thickness():
    redraw()
    x, y = C["rows"]["thickness"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_drag_thickness():
    x, y = C["rows"]["thickness"]
    d = round(50 * bpy.context.preferences.system.ui_scale)     # 0.01 Maya unit per px at scale 1 -> 0.5
    C["d"] = d
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=x + d * i // 8, y=y)


@step
def s_release_thickness():
    x, y = C["rows"]["thickness"]
    ev('LEFTMOUSE', 'RELEASE', x=x + C["d"], y=y)


@step
def s_thickness():
    r = rec()
    t = r.params["thickness"] if r else None
    check(f"In-View Thickness drag -> 0.5 (got {t}, top z {top_z():.3f})",
          r is not None and abs(t - 0.5) < 0.02 and abs(top_z() - (1.0 + t)) < 1e-4)
    redraw()


def dock():
    return dock_area(), dock_region()


@step
def s_shot_thickness():
    shot("gui_step65_thickness.png")
    redraw()


@step
def s_open_extrude_node():
    open_inputs("polyExtrudeFace1")   # INPUTS nodes start collapsed (Maya)
    scroll_channel_box()              # ... and a long Channel Box scrolls inside its part
    redraw()


@step
def s_wait_open_extrude():
    redraw()


# The field is looked up by its data path (the Channel Box part scrolls, rows have no fixed y).
step(find_button(dock, lambda path, _cmd: path.endswith("divisions_text"), C, "divisions", x_frac=0.8, step_px=8))


@step
def s_hover_divisions():
    check(f"INPUTS Divisions field found ({C.get('divisions')})", C.get("divisions") is not None)
    if C.get("divisions"):
        x, y = C["divisions"]
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    redraw()


@step
def s_click_divisions():
    x, y = C["divisions"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_type_divisions():
    ev('TEXTINPUT', 'PRESS', unicode="2")
    ev('RET', 'PRESS')
    ev('RET', 'RELEASE')


@step
def s_divisions():
    r = rec()
    check(f"typed 2 in Channel Box INPUTS polyExtrudeFace1 Divisions -> 16 vertices, Thickness kept (got {counts()}, {r and r.params})",
          counts() == (16, 14) and r is not None and r.params["divisions"] == 2 and abs(r.params["thickness"] - 0.5) < 0.02)
    redraw()


@step
def s_shot_inputs():
    shot("gui_step65_inputs.png")
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undone():
    r = rec()
    check(f"Ctrl+Z: back to Divisions 1, Thickness 0.5 (got {counts()}, {r and r.params})",
          counts() == (12, 10) and r is not None and r.params["divisions"] == 1 and abs(r.params["thickness"] - 0.5) < 0.02)
    redraw()


@step
def s_arrow_hover():
    x, y, d = arrow_point()
    C["arrow"] = (x, y, d)
    C["z0"] = top_z()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    redraw()


@step
def s_arrow_press():
    x, y, _d = C["arrow"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_arrow_drag():
    x, y, d = C["arrow"]
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=x + round(d.x * px(60) * i / 8), y=y + round(d.y * px(60) * i / 8))


@step
def s_arrow_release():
    x, y, d = C["arrow"]
    ev('LEFTMOUSE', 'RELEASE', x=x + round(d.x * px(60)), y=y + round(d.y * px(60)))


@step
def s_arrow_done():
    r = rec()
    ltz = r.params["local_translate_z"] if r else None
    check(f"drag the blue arrow out -> Local Translate Z > 0, faces move up (ltz {ltz}, z {C['z0']:.3f} -> {top_z():.3f})",
          r is not None and ltz > 0.05 and top_z() > C["z0"] + 0.05)
    redraw()


@step
def s_end():
    shot("gui_step65_arrow.png")


run()
