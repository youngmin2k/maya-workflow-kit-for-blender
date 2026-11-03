"""Issue #274 in a real UI: a lattice bent by a deformer, in edit mode in the Maya layout — a click on a point where it
is drawn selects that point (not the one whose undeformed spot is nearest), Shift+click adds another, a marquee
around a drawn point selects what is drawn inside it, and Ctrl+Z takes the marquee back in one step."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win, load_maya_layout, screenshot  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def lattice():
    return bpy.data.objects[C["lat"]]


def selected():
    return {i for i, p in enumerate(lattice().data.points) if p.select}


def to_window(world):
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, world)
    return None if p is None else Vector((region.x + p.x, region.y + p.y))


def spots():
    """Window positions of every point: (drawn, own)."""
    lat = lattice()
    ev_lat = lat.evaluated_get(bpy.context.evaluated_depsgraph_get())
    drawn = [to_window(lat.matrix_world @ p.co_deform) for p in ev_lat.data.points]
    own = [to_window(lat.matrix_world @ p.co_deform) for p in lat.data.points]
    return drawn, own


def move(p):
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_lattice():
    bpy.ops.allset.keymap_activate()
    u = mod("operators.units").maya_unit()
    lat = bpy.data.objects.new("ffd1Lattice", bpy.data.lattices.new("ffd1LatticeShape"))
    bpy.context.scene.collection.objects.link(lat)
    lat.data.points_w = 4
    lat.scale = (8 * u, 8 * u, 8 * u)
    md = lat.modifiers.new("bend1", 'SIMPLE_DEFORM')
    md.deform_method = 'BEND'
    md.angle = 1.5
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    lat.select_set(True)
    bpy.context.view_layer.objects.active = lat
    bpy.ops.object.mode_set(mode='EDIT')
    for p in lat.data.points:
        p.select = True
    C["lat"] = lat.name
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.view3d.view_selected()
        for _i in range(3):
            bpy.ops.view3d.zoom(delta=-1)       # the bend draws the lattice bigger than its own points
    for p in lat.data.points:
        p.select = False
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 3)


@step
def s_q():
    tap('Q')       # Select tool: no manipulator in the way


@step
def s_pick_targets():
    drawn, own = spots()
    n = len(drawn)

    _a, r = view3d()

    def shown(p):
        return p is not None and r.x + 40 < p.x < r.x + r.width - 40 and r.y + 40 < p.y < r.y + r.height - 40

    def apart(k):           # drawn spot far from its own spot, and from every other drawn spot
        if not shown(drawn[k]) or own[k] is None:
            return -1
        near = min((drawn[k] - drawn[m]).length for m in range(n) if m != k and drawn[m] is not None)
        return min((drawn[k] - own[k]).length, near)

    order = sorted(range(n), key=apart, reverse=True)
    C["i"], C["j"] = order[0], order[1]
    C["drawn"], C["own"] = drawn, own
    check(f"the bend draws point {C['i']} {(drawn[C['i']] - own[C['i']]).length:.0f} px from its own spot "
          f"(the kit picker has something to do)", (drawn[C['i']] - own[C['i']]).length > 30)
    move(drawn[C["i"]])
    shot("issue274_pick_before.png")


@step
def s_click_press():
    ev('LEFTMOUSE', 'PRESS')


@step
def s_click_release():
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_clicked():
    check(f"a click on point {C['i']} where it is drawn selects it ({sorted(selected())})", selected() == {C["i"]})
    move(C["drawn"][C["j"]])


@step
def s_shift_down():
    ev('LEFT_SHIFT', 'PRESS', shift=True)


@step
def s_shift_press():
    ev('LEFTMOUSE', 'PRESS', shift=True)


@step
def s_shift_release():
    ev('LEFTMOUSE', 'RELEASE', shift=True)


@step
def s_shift_up():
    ev('LEFT_SHIFT', 'RELEASE')


@step
def s_shift_clicked():
    check(f"Shift+click on point {C['j']} where it is drawn adds it ({sorted(selected())})",
          selected() == {C["i"], C["j"]})
    C["before_box"] = selected()
    k = C["i"]
    c = C["drawn"][k]
    half = 18
    C["box"] = (c.x - half, c.y - half, c.x + half, c.y + half)
    C["want"] = {m for m, d in enumerate(C["drawn"])
                 if d is not None and c.x - half <= d.x <= c.x + half and c.y - half <= d.y <= c.y + half}
    move(Vector((c.x - half, c.y - half)))


@step
def s_box_press():
    ev('LEFTMOUSE', 'PRESS')


@step
def s_box_move1():
    x0, y0, x1, y1 = C["box"]
    move(Vector(((x0 + x1) / 2, (y0 + y1) / 2)))


@step
def s_box_move2():
    x0, y0, x1, y1 = C["box"]
    move(Vector((x1, y1)))


@step
def s_box_release():
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_wait():
    pass


@step
def s_boxed():
    shot("issue274_pick_box.png")
    check(f"a marquee around the drawn point selects what is drawn inside ({sorted(selected())} = "
          f"{sorted(C['want'])})", selected() == C["want"])
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 3)


@step
def s_undo_down():
    ev('LEFT_CTRL', 'PRESS', ctrl=True)
    ev('Z', 'PRESS', ctrl=True)


@step
def s_undo_up():
    ev('Z', 'RELEASE', ctrl=True)
    ev('LEFT_CTRL', 'RELEASE')


@step
def s_wait2():
    pass


@step
def s_undone():
    check(f"one Ctrl+Z takes the marquee back ({sorted(selected())} = {sorted(C['before_box'])})",
          selected() == C["before_box"])


run()
