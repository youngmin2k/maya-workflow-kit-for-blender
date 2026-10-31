"""In a real UI: a wire made from the menu bends a plane when its curve moves (the viewport draws the
Geometry Nodes wire), Show Base Wire shows curve1BaseWire, and the Paint Weights > Wire box opens the Paint
Attributes Tool window; screenshots (ALLSET_GUI_SHOTS)."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, setup, step, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def v3d_override():
    a = view3d()[0]
    region = next(r for r in a.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(window=win(), area=a, region=region)


@step
def s_setup():
    setup()
    for ob in list(bpy.data.objects):
        if ob.type == 'MESH':
            bpy.data.objects.remove(ob)
    with v3d_override():
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=40, y_subdivisions=40, size=10)
    C["plane"] = bpy.context.active_object.name
    cu = bpy.data.curves.new("curve1Shape", 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('NURBS')
    sp.points.add(3)
    for p, x in zip(sp.points, (-5, -5 / 3, 5 / 3, 5)):
        p.co = (x, 0, 0, 1)
    sp.order_u, sp.use_endpoint_u = 4, True
    c = bpy.data.objects.new("curve1", cu)
    bpy.context.scene.collection.objects.link(c)
    plane = bpy.data.objects[C["plane"]]
    for o in bpy.context.view_layer.objects:
        o.select_set(o in (plane, c))
    bpy.context.view_layer.objects.active = c


@step
def s_wire():
    with v3d_override():
        res = bpy.ops.allset.menu_item(item="Deform/Wire")
    plane = bpy.data.objects[C["plane"]]
    check(f"Deform > Wire runs ({res})", res == {'FINISHED'} and "wire1" in plane.modifiers)
    c = bpy.data.objects["curve1"]
    c.location.z = 1.0
    pt = c.data.splines[0].points[1]
    pt.co = (pt.co[0], pt.co[1], pt.co[2] + 1.0, 1)
    with v3d_override():
        bpy.ops.view3d.view_axis(type='FRONT')
        bpy.ops.view3d.view_all()


@step
def s_measure():
    plane = bpy.data.objects[C["plane"]]
    dg = bpy.context.evaluated_depsgraph_get()
    zs = [v.co.z for v in plane.evaluated_get(dg).to_mesh().vertices]
    plane.evaluated_get(dg).to_mesh_clear()
    check(f"the plane follows the wire (max z {max(zs):.3f})", 1.2 < max(zs) < 1.5)


@step
def s_shot():
    shot("gui_step169_wire.png")
    with v3d_override():
        bpy.context.view_layer.objects.active = bpy.data.objects["curve1"]
        res = bpy.ops.allset.wire_edit(action='SHOW_BASE')
    base = bpy.data.objects.get("curve1BaseWire")
    check(f"Show Base Wire ({res})", res == {'FINISHED'} and base is not None and base.visible_get())


@step
def s_shot2():
    shot("gui_step169_base_wire.png")
    ev('MOUSEMOVE', 'NOTHING', x=win().width // 2, y=win().height // 2)
    with bpy.context.temp_override(window=win()):
        res = bpy.ops.allset.opt_paint_weights_wire('INVOKE_DEFAULT')
    check(f"Paint Weights > Wire box opens its window ({res})", res != {'CANCELLED'})


@step
def s_wait():
    pass


@step
def s_shot3():
    shot("gui_step169_paint_window.png")
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


run()
