"""In the Maya Workflow Kit layout: RMB on a cube > Inputs opens the node list
(like Maya's RMB Inputs list: Select / Enable / Disable All, the nodes, All Inputs...), picking a node opens it in the
Channel Box; in component mode the Channel Box shows the shape, the CVs line and INPUTS. Shots with ``--shots``."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, scale, screenshot, setup, step, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def main_view():
    return mod("ui.status_line").main_view3d(win().screen)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def shot(name):
    screenshot(os.path.join(SHOTS or bpy.app.tempdir, f"gui_step165_{name}_{scale():.2f}.png".replace(".", "", 1)))


def session():
    return mod("marking.draw").ACTIVE.get("session")


def row_point(s, label, level=-1):
    """Window pixel of list row ``label`` in the session's menu at stack ``level``."""
    lay, (cx, cy) = s.stack[level]
    _area, region = main_view()
    for it in lay.items:
        if it.label == label and it.kind == "list":
            x0, y0, x1, y1 = it.rect
            return region.x + int(cx + (x0 + x1) / 2), region.y + int(cy + (y0 + y1) / 2)
    return None


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.view_layer.objects.active
    C["ob"] = ob.name
    C["md"] = ob.modifiers.new("Bend", 'SIMPLE_DEFORM').name
    ob.modifiers[C["md"]].deform_axis = 'Z'
    redraw()


step(redraw)


@step
def s_rmb_press():
    _area, region = main_view()
    ob = bpy.data.objects[C["ob"]]
    p = location_3d_to_region_2d(region, region.data, ob.matrix_world.translation)
    x, y = region.x + int(p.x), region.y + int(p.y)
    C["rmb"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y)


@step
def s_rmb_wait():
    redraw()


@step
def s_to_inputs():
    s = session()
    check("RMB on the cube opens the object marking menu", s is not None)
    if s is None:
        return
    p = row_point(s, "Inputs", 0)
    check("the RMB list has an Inputs row", p is not None)
    if p is None:
        return
    C["inputs_row"] = p
    ev('MOUSEMOVE', 'NOTHING', x=p[0] - 20, y=p[1])


@step
def s_on_inputs():
    p = C.get("inputs_row")
    if p:
        ev('MOUSEMOVE', 'NOTHING', x=p[0], y=p[1])
    redraw()


step(redraw)


@step
def s_inputs_open():
    s = session()
    if s is None:
        check("menu still open over Inputs", False)
        return
    labels = [it.label for it in s.layout.items]
    check(f"Inputs ▸ lists the nodes like Maya ({labels})",
          labels[:3] == ["Select All Inputs", "Enable All Inputs", "Disable All Inputs"]
          and "Non Linear" in labels and "Poly Cube" in labels and labels[-1] == "All Inputs...")
    check("the node rows are enabled", all(it.enabled for it in s.layout.items))
    shot("rmb_inputs")
    p = row_point(s, "Non Linear")
    C["node_row"] = p
    if p:
        ev('MOUSEMOVE', 'NOTHING', x=p[0] - 30, y=p[1])


@step
def s_on_node():
    p = C.get("node_row")
    if p:
        ev('MOUSEMOVE', 'NOTHING', x=p[0] - 20, y=p[1])


@step
def s_release():
    p = C.get("node_row") or C["rmb"]
    ev('RIGHTMOUSE', 'RELEASE', x=p[0] - 20, y=p[1])
    redraw()


step(redraw)


@step
def s_node_open():
    ob = bpy.data.objects[C["ob"]]
    cb = mod("ui.channel_box")
    md = ob.modifiers[C["md"]]
    check("picking Inputs > Non Linear opens bend1 under INPUTS in the Channel Box", cb.is_open(ob, cb.mod_node(md)))
    check("the cube stays the lead", bpy.context.view_layer.objects.active == ob and ob.select_get())
    redraw()


@step
def s_node_shot():
    last = mod("ui.channel_box")._last
    check(f"the Channel Box scrolled to the picked node ({list(last.values())})",
          any(v[2] is None or v[0] > 0 for v in last.values()))
    shot("node_picked")     # screen.screenshot shows the previous frame: one tick after the redraw


@step
def s_component():
    ob = bpy.data.objects[C["ob"]]
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    for i in (0, 1, 3):
        bm.verts[i].select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    redraw()


step(redraw)


@step
def s_component_shot():
    check("component mode on the lead", mod("ui.channel_box").component_mode(bpy.data.objects[C["ob"]]))
    shot("component_cb")
    bpy.ops.allset.cb_points_toggle()
    redraw()


step(redraw)


@step
def s_cvs_shot():
    check("CVs table open", bpy.context.window_manager.allset_cb_points)
    shot("component_cvs")


run()
