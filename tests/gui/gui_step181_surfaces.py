"""In a real UI (Maya Workflow Kit layout): three EP curves at different heights -> Surfaces > Loft (the menu
item, as a Maya user runs it) -> loftedSurface1, a NURBS surface through the curves, drawn shaded in the persp view;
then one profile -> Surfaces > Revolve -> revolvedSurface1. Screenshots: gui_step181_loft.png, gui_step181_revolve.png."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def main_view():
    toolbox = import_module(MODULE + ".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def k():
    return import_module(MODULE + ".operators.units").maya_unit(bpy.context.scene)


def maya(p):
    """Maya point (Y up, Maya units) -> Blender world."""
    s = k()
    return (p[0] * s, -p[2] * s, p[1] * s)


def select(obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def menu(path):
    area, region = main_view()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return bpy.ops.allset.menu_item(item=path)


def frame():
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.view3d.view_selected()
    area.spaces.active.shading.type = 'SOLID'
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_curves():
    cmaya = import_module(MODULE + ".operators.curves_maya")
    shapes = (
        [(-6, 0, 0), (-2, 0, 3), (2, 0, -1), (6, 0, 2)],
        [(-5, 4, 1), (-2, 4, -2), (2, 4, 2), (5, 4, 0)],
        [(-6, 8, -1), (-2, 8, 1), (2, 8, -2), (6, 8, 1)],
    )
    obs = []
    for i, pts in enumerate(shapes):
        ob = cmaya.make_ep_curve(bpy.context, [maya(p) for p in pts])
        obs.append(ob)
    C["curves"] = [o.name for o in obs]
    select(obs)
    check(f"three EP curves ({C['curves']})", len(obs) == 3 and all(o.type == 'CURVE' for o in obs))


C = {}


@step
def s_loft():
    res = menu("Surfaces/Loft")
    check(f"Surfaces > Loft runs ({res})", res == {'FINISHED'})


@step
def s_loft_check():
    ob = bpy.data.objects.get("loftedSurface1")
    check(f"loftedSurface1 is a NURBS surface ({ob and ob.type})", ob is not None and ob.type == 'SURFACE')
    if ob is None:
        return
    sp = ob.data.splines[0]
    # 3 curves, factory uniform cubic loft: n + 2 = 5 CV rows; U = the curves' 6 CVs
    check(f"5 CV rows x 6 along the curves ({sp.point_count_v} x {sp.point_count_u})",
          sp.point_count_v == 5 and sp.point_count_u == 6)
    smaya = import_module(MODULE + ".operators.surfaces_maya")
    cm = import_module(MODULE + ".operators.curves_math")
    s = smaya.read_surface(ob)
    cmaya = import_module(MODULE + ".operators.curves_maya")
    worst = 0.0
    for v, name in enumerate(C["curves"]):
        c = cmaya.read_spline(bpy.data.objects[name].data.splines[0], bpy.data.objects[name].matrix_world)
        d0, d1 = s.domain_u()
        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            p = cm.evaluate(c.cvs, c.knots, c.degree, c.knots[0] + (c.knots[-1] - c.knots[0]) * f)
            q = s.point(d0 + (d1 - d0) * f, float(v))
            worst = max(worst, sum((a - b) ** 2 for a, b in zip(p, q)) ** 0.5)
    check(f"the surface passes through the three curves (max {worst:.1e})", worst < 1e-4 * max(1.0, k() * 100))
    check("the loft is the selected lead", bpy.context.view_layer.objects.active == ob and ob.select_get())
    check("lambert1 assigned", ob.active_material is not None)
    frame()


@step
def s_loft_shot():
    shot("gui_step181_loft.png")


@step
def s_revolve():
    cmaya = import_module(MODULE + ".operators.curves_maya")
    for o in list(bpy.context.scene.objects):
        o.hide_set(True)
    prof = cmaya.make_cv_curve(bpy.context, [maya(p) for p in ((1, 0, 0), (2.5, 1, 0), (1.5, 3, 0), (2, 5, 0))])
    select([prof])
    res = menu("Surfaces/Revolve")
    check(f"Surfaces > Revolve runs ({res})", res == {'FINISHED'})


@step
def s_revolve_check():
    ob = bpy.data.objects.get("revolvedSurface1")
    check(f"revolvedSurface1 is a NURBS surface ({ob and ob.type})", ob is not None and ob.type == 'SURFACE')
    if ob is None:
        return
    sp = ob.data.splines[0]
    check(f"factory revolve: 8 segments around, cyclic V ({sp.point_count_v}, {sp.use_cyclic_v})",
          sp.point_count_v == 8 and sp.use_cyclic_v)
    frame()


@step
def s_revolve_shot():
    shot("gui_step181_revolve.png")


run()
