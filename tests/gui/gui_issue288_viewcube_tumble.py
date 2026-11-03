"""#288: clicking a ViewCube face in the persp view keeps the view perspective (like Maya's persp camera), so Alt+LMB
still tumbles it afterwards; a top / front / side ortho view stays locked as before."""

import os
import sys
from importlib import import_module

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, setup, step, win  # noqa: E402

C = {}


def vf():
    return import_module(MODULE + ".ui.view_furniture")


def view():
    return import_module(MODULE + ".ui.status_line").main_view3d(win().screen)


def face_centre(name):
    area, region = view()
    m = vf()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        b = m._bounds(bpy.context)
    s = m._scale()
    size = m.cube_size(region.width, region.height, s)
    centre, _l, _t = m.layout(b, s, size)
    for f, poly, *_r in m.faces_2d(region.data.view_rotation, centre, size):
        if f == name:
            return (region.x + int(sum(p[0] for p in poly) / 4), region.y + int(sum(p[1] for p in poly) / 4))
    return None


def at(fx, fy):
    _a, r = view()
    return int(r.x + r.width * fx), int(r.y + r.height * fy)


def tumble_steps(tag):
    def start():
        C["rot"] = view()[1].data.view_rotation.copy()
        x, y = at(0.45, 0.5)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        ev('LEFT_ALT', 'PRESS', x=x, y=y, alt=True)

    def press():
        x, y = at(0.45, 0.5)
        ev('LEFTMOUSE', 'PRESS', x=x, y=y, alt=True)

    def moves(f):
        def fn():
            x, y = at(f, 0.5)
            ev('MOUSEMOVE', 'NOTHING', x=x, y=y, alt=True)
        return fn

    def release():
        x, y = at(0.57, 0.5)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y, alt=True)
        ev('LEFT_ALT', 'RELEASE', x=x, y=y)

    def done():
        rot = view()[1].data.view_rotation
        C[tag] = max(abs(a - b) for a, b in zip(rot, C["rot"])) > 1e-3
    return [start, press, moves(0.49), moves(0.53), moves(0.57), release, done]


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_hover():
    bpy.ops.allset.keymap_activate()
    C["face"] = face_centre("TOP")
    check(f"ViewCube TOP face found ({C['face']})", C["face"] is not None)
    x, y = C["face"]
    ev('MOUSEMOVE', 'NOTHING', x=x - 3, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_press():
    x, y = C["face"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_release():
    x, y = C["face"]
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


def _idle():
    pass


for _i in range(4):
    step(_idle)


@step
def s_top():
    rv3d = view()[1].data
    d = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))
    check(f"the TOP click turned the view to look down ({tuple(round(c, 3) for c in d)})", d.z < -0.999)
    check(f"the persp view stays perspective ({rv3d.view_perspective})", rv3d.view_perspective == 'PERSP')


for _f in tumble_steps("after_cube"):
    step(_f)


@step
def s_tumbled():
    check("Alt+LMB still tumbles the view after the ViewCube click", C.get("after_cube"))
    # a Maya ortho view (top / front / side) stays locked
    rv3d = view()[1].data
    rv3d.view_perspective = 'ORTHO'
    rv3d.is_orthographic_side_view = True


for _f in tumble_steps("ortho"):
    step(_f)


@step
def s_ortho():
    check("an axis-aligned ortho view still doesn't tumble (Maya ortho lock)", not C.get("ortho"))


run()
