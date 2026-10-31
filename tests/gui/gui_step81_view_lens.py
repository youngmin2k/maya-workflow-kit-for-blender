"""In a real UI: the Maya Workflow Kit layout's persp view has a 54.4 deg angle (lens 70), a pCube1 has its
usual on-screen size, Four View keeps the angle, Ctrl+Shift+C makes a 35 mm camera."""

import math
import os
import sys

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, screenshot, setup, step, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region)


@step
def s_start():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    with override():
        bpy.ops.allset.create(kind='CUBE')
    for o in bpy.context.selected_objects:
        o.select_set(False)
    area, region = view3d()
    C["x"], C["y"] = region.x + region.width // 2, region.y + region.height // 2
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_view():
    area, region = view3d()
    space = area.spaces.active
    fov = math.degrees(2 * math.atan(36.0 / space.lens))
    check(f"persp view lens {space.lens:.0f} = Maya's horizontal angle ({fov:.1f} deg, Maya 54.4)", abs(fov - 54.4) < 0.1)
    ob = bpy.data.objects["pCube1"]
    pts = [location_3d_to_region_2d(region, region.data, ob.matrix_world @ Vector(c)) for c in ob.bound_box]
    ys = [p.y for p in pts if p is not None]
    C["cube_h"] = (max(ys) - min(ys)) / region.width
    check(f"pCube1 height = {C['cube_h']:.3f} of the view width (lens 35 made it half)", C["cube_h"] > 0.03)
    shot("gui_step81_persp.png")
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('C', 'PRESS', shift=True, ctrl=True)
    ev('C', 'RELEASE', shift=True, ctrl=True)


@step
def s_camera():
    # the scene also has Maya's hidden startup cameras (persp / top / front / side)
    cams = [o for o in bpy.data.objects if o.type == 'CAMERA' and not o.get("allset_startup_camera")]
    lens = cams[-1].data.lens if cams else None
    check(f"Ctrl+Shift+C = a 35 mm camera ({[c.name for c in cams]}, focal {lens})",
          len(cams) == 1 and abs(lens - 35.0) < 1e-3 and cams[-1].data.sensor_width == 36.0)
    area, _region = view3d()
    with override():
        bpy.ops.screen.region_quadview()


@step
def s_four():
    area, _region = view3d()
    space = area.spaces.active
    check(f"Four View: the persp quadrant keeps lens {space.lens:.0f}", bool(space.region_quadviews) and abs(space.lens - 70) < 1e-6)
    shot("gui_step81_four_view.png")
    with override():
        bpy.ops.screen.region_quadview()


run()
