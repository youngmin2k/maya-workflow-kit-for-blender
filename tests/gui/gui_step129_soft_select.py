"""With simulated events: B tap = one soft select state for object + component mode (#15, #1), B hold + MMB
drag sets the radius with a circle / value in the view and no navigation (#1), falloff colour overlay (#2)."""

import os
import sys
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def ts():
    return bpy.context.scene.tool_settings


def soft():
    return import_module(MODULE + ".operators.soft_select")


def overlay():
    return import_module(MODULE + ".ui.soft_overlay")


def in_v3d(fn, *a, **kw):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return fn(*a, **kw)


def shot(name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        screenshot(os.path.join(SHOTS, name))


def view():
    return [tuple(r) for r in view3d()[0].spaces.active.region_3d.view_matrix]


@step
def s_setup():
    C["x"], C["y"] = setup()
    check("Maya mode starts with soft select off",
          not soft().is_on() and not ts().use_proportional_edit and not ts().use_proportional_edit_objects)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    in_v3d(bpy.ops.mesh.primitive_grid_add, x_subdivisions=40, y_subdivisions=40, size=4.0)
    in_v3d(bpy.ops.view3d.view_selected)           # close enough to see the coloured wire in the shots
    ts().proportional_size = 0.6
    ts().proportional_edit_falloff = 'SMOOTH'
    tap('B')


@step
def s_object_on():
    check("B tap in object mode -> soft select on in object AND component mode",
          ts().use_proportional_edit_objects and ts().use_proportional_edit and soft().is_on())
    in_v3d(bpy.ops.object.mode_set, mode='EDIT')
    ts().mesh_select_mode = (True, False, False)
    me = bpy.context.active_object.data
    bm = bmesh.from_edit_mesh(me)
    centre = min(bm.verts, key=lambda v: v.co.length)
    for v in bm.verts:
        v.select = v is centre
    bm.select_flush(False)
    bmesh.update_edit_mesh(me)


@step
def s_edit_still_on():
    check("still on after entering component mode (#15)", ts().use_proportional_edit)
    tap('B')


@step
def s_edit_off():
    check("B tap in component mode -> off everywhere",
          not ts().use_proportional_edit and not ts().use_proportional_edit_objects and not soft().is_on())
    tap('B')


@step
def s_edit_on_again():
    check("B tap again -> on", ts().use_proportional_edit and ts().use_proportional_edit_objects)
    C["view"] = view()
    C["size0"] = ts().proportional_size
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] + 120, y=C["y"] - 120)


@step
def s_overlay_shot():
    # drawn in the previous tick; the screenshot shows the previous frame
    shot("gui_step129_overlay.png")


@step
def s_overlay():
    ob = bpy.context.active_object
    st = overlay()._cache.get(ob.as_pointer())
    check("overlay drew the falloff colours (batches built)", st is not None and st.batches)
    if st is not None and st.w is not None:
        w = st.w
        n_on = int((w > 0).sum())
        cols = soft().ramp(w[w > 0])
        check(f"affected vertices coloured ({n_on}), selected yellow, outer ones towards black",
              n_on > 10 and tuple(cols.max(axis=0)) == (1.0, 1.0, 0.0) and cols[:, 0].min() < 0.5)
    ev('B', 'PRESS')


@step
def s_mmb_press():
    ev('MIDDLEMOUSE', 'PRESS', x=C["x"], y=C["y"])


@step
def s_mmb_move():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] + 50, y=C["y"])


@step
def s_mmb_move2():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] + 100, y=C["y"])


@step
def s_drag_shot():
    shot("gui_step129_radius_drag.png")


@step
def s_dragging():
    d = overlay()._drag
    C["size"] = ts().proportional_size
    check(f"B + MMB drag 100 px -> radius x2 ({C['size0']:.3f} -> {C['size']:.3f})",
          abs(C["size"] - 2 * C["size0"]) < 1e-3)
    check(f"radius circle + value shown while dragging ({d.get('text')!r})",
          d.get("text", "").startswith("Falloff Radius:") and d.get("centre") is not None)
    check("B + MMB drag does not orbit the view", view() == C["view"])
    ev('MIDDLEMOUSE', 'RELEASE', x=C["x"] + 100, y=C["y"])


@step
def s_b_release():
    ev('B', 'RELEASE')


@step
def s_after():
    check("B release after the drag does not toggle soft select", ts().use_proportional_edit and soft().is_on())
    check("radius display gone after the drag", not overlay()._drag)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] + 120, y=C["y"] - 120)


@step
def s_big_shot():
    shot("gui_step129_overlay_bigger.png")


run()
