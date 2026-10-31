"""In a real UI: Maya view furniture in the Maya Workflow Kit layout — ViewCube click on TOP gives the
top view, four-view panel labels top / persp / side / front, Blender navigation gizmo and text info
off (screenshots)."""

import os
import sys
from importlib import import_module

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def area3d():
    return max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)


def regions():
    return [r for r in area3d().regions if r.type == 'WINDOW']


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def vf():
    return import_module(MODULE + ".ui.view_furniture")


def view_dir(region):
    return region.data.view_rotation @ Vector((0.0, 0.0, -1.0))


def face_centre(region, name):
    m = vf()
    area = area3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        b = m._bounds(bpy.context)
    s = m._scale()
    size = m.cube_size(region.width, region.height, s)
    centre, _l, _t = m.layout(b, s, size)
    for f, poly, *_r in m.faces_2d(region.data.view_rotation, centre, size):
        if f == name:
            return (region.x + int(sum(p[0] for p in poly) / 4), region.y + int(sum(p[1] for p in poly) / 4))
    return None


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_template():
    bpy.ops.allset.keymap_activate()
    space = area3d().spaces.active
    check("Maya Workflow Kit view: Blender navigation gizmo and text info off",
          not space.show_gizmo_navigate and not space.overlay.show_text)
    check("... so it is a Maya view (ViewCube, triad, camera name)", vf().maya_view(space))
    redraw()


@step
def s_single_shot():
    shot("gui_step46_single.png")
    r = regions()[-1]
    C["persp"] = (r.data.view_rotation.copy(), r.data.view_distance, r.data.view_location.copy())
    C["top"] = face_centre(r, "TOP")
    check(f"ViewCube TOP face visible in the Maya persp view ({C['top']})", C["top"] is not None)
    if C["top"]:
        x, y = C["top"]
        ev('MOUSEMOVE', 'NOTHING', x=x - 3, y=y)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    redraw()


@step
def s_hover_shot():
    shot("gui_step46_hover.png")
    if C["top"]:
        x, y = C["top"]
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_release():
    if C["top"]:
        x, y = C["top"]
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_wait():
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_top():
    r = regions()[-1]
    d = view_dir(r)
    check(f"ViewCube TOP click -> top view (looking {tuple(round(c, 3) for c in d)}, "
          f"{r.data.view_perspective})", d.z < -0.999)
    shot("gui_step46_top.png")
    # back to the Maya persp view, then four view (Blender's quad copies the current view into the user panel)
    rv3d = r.data
    rv3d.view_perspective = 'PERSP'
    rv3d.view_rotation, rv3d.view_distance, rv3d.view_location = C["persp"]
    area = area3d()
    with bpy.context.temp_override(window=win(), area=area, region=regions()[-1]):
        bpy.ops.screen.region_quadview()
    redraw()


@step
def s_quad_wait():
    redraw()


@step
def s_quad():
    m = vf()
    names = []
    for r in regions():
        rv3d = r.data
        names.append(m.label_for(rv3d.view_perspective, rv3d.is_orthographic_side_view, tuple(view_dir(r))))
    C["names"] = names
    first = sorted(n.split()[0] for n in names)
    check(f"four-view labels {names} = top / persp / side / front", first == ["front", "persp", "side", "top"])
    shot("gui_step46_quad.png")


run()
