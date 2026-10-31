"""In the Maya Workflow Kit layout: Visualize > Ghost Selected draws Maya's ghosts.

Scene (flat #5c5c5c viewport):
a 1-unit cube keyed translateX 0 -> 18 over frames 1 -> 10 (linear), current frame 5, Ghost Selected, nothing
selected, seen from the front. Expected pixels at each ghost's front-face centre (frame 5):
pre frames 2 / 3 / 4 = #4d7371 / #3d8a87 / #339e9a, post 6 / 7 / 8 = #96807f / #847272 / #6f6565, no ghost at
frames 1 / 9 / 10. Shots with ``--shots``."""

import math
import os
import sys
from importlib import import_module

import bpy
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Euler, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, scale, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
MAYA = {2: "#4d7371", 3: "#3d8a87", 4: "#339e9a", 6: "#96807f", 7: "#847272", 8: "#6f6565"}
BG = "#5c5c5c"
TOL = 14            # per channel, 8-bit
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def shot(name):
    path = os.path.join(SHOTS or bpy.app.tempdir, f"gui_step171_{name}_{scale():.2f}.png".replace(".", "", 1))
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active)


def rgb(hex_str):
    h = hex_str.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float64)


def sample(px, frame):
    """Median 8-bit colour of a 5 x 5 patch at the front-face point of the cube's position at ``frame``."""
    u = C["u"]
    area, region = view3d()
    rv3d = area.spaces.active.region_3d
    p = location_3d_to_region_2d(region, rv3d, Vector((2.0 * (frame - 1) * u, -0.5 * u, 0.25 * u)))
    x, y = region.x + int(p.x), region.y + int(p.y)
    patch = px[y - 2:y + 3, x - 2:x + 3].reshape(-1, 3)
    return np.median(patch, axis=0) * 255.0, (x, y)


@step
def s_setup():
    setup()
    load_maya_layout()


for _i in range(6):
    step(redraw)


@step
def s_scene():
    u = C["u"] = mod("operators.units").maya_unit(bpy.context.scene)
    with override():
        bpy.ops.allset.create(kind='CUBE')
    cube = bpy.data.objects["pCube1"]
    for f, x in ((1, 0.0), (10, 18.0 * u)):
        cube.location.x = x
        cube.keyframe_insert("location", index=0, frame=f)
    try:
        compat = mod("compat")
        for fc in compat.id_fcurves(cube):
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'
    except Exception:  # noqa: BLE001
        pass
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 10
    scene.frame_set(5)
    for o in scene.objects:
        o.select_set(o == cube)
    bpy.context.view_layer.objects.active = cube
    with override():
        bpy.ops.allset.ghost(action="GHOST")
    for o in scene.objects:
        o.select_set(False)
    area, _region = view3d()
    space = area.spaces.active
    space.overlay.show_floor = False
    space.overlay.show_axis_x = space.overlay.show_axis_y = False
    rv3d = space.region_3d
    rv3d.view_perspective = 'PERSP'
    rv3d.view_rotation = Euler((math.radians(90), 0, 0)).to_quaternion()      # front: looking along +Y
    rv3d.view_location = Vector((9.0 * u, 0.0, 0.0))
    rv3d.view_distance = 30.0 * u
    redraw()


for _i in range(4):
    step(redraw)


@step
def s_check():
    ghosting = mod("ui.ghosting")
    cube = bpy.data.objects["pCube1"]
    have = sorted(f for (uid, f) in ghosting._geom if uid == cube.session_uid)
    check(f"ghost geometry sampled for frames 2-4 / 6-8 ({have})", have == [2.0, 3.0, 4.0, 6.0, 7.0, 8.0])
    check("the current frame is back at 5 after sampling", bpy.context.scene.frame_current == 5)
    px = shot("ghost_f5")
    worst = 0.0
    for frame, want in MAYA.items():
        got, at = sample(px, frame)
        diff = float(np.abs(got - rgb(want)).max())
        worst = max(worst, diff)
        print("GUI171 frame", frame, "at", at, "kit", got.round().tolist(), "maya", rgb(want).tolist(), "diff", diff,
              flush=True)
        check(f"frame {frame} ghost colour {got.round().astype(int).tolist()} ~ Maya {want} (max diff {diff:.0f})",
              diff <= TOL)
    for frame in (1, 9, 10):
        got, _at = sample(px, frame)
        check(f"no ghost at frame {frame} ({got.round().astype(int).tolist()} ~ {BG})",
              float(np.abs(got - rgb(BG)).max()) <= 3)
    C["worst"] = worst


@step
def s_wire():
    area, _region = view3d()
    area.spaces.active.shading.type = 'WIREFRAME'
    redraw()


step(redraw)
step(redraw)


@step
def s_wire_check():
    px = shot("ghost_f5_wire")
    area, region = view3d()
    rv3d = area.spaces.active.region_3d
    u = C["u"]
    # the left vertical edge of the frame-4 ghost (pre colour, cyan-ish over grey)
    p = location_3d_to_region_2d(region, rv3d, Vector(((6.0 - 0.5) * u, -0.5 * u, 0.25 * u)))
    x, y = region.x + int(round(p.x)), region.y + int(p.y)
    patch = px[y - 1:y + 2, x - 3:x + 4].reshape(-1, 3) * 255.0
    cyan = (patch[:, 1] - patch[:, 0]) > 20
    check(f"wireframe shading: the frame-4 ghost draws its edges in the pre colour ({int(cyan.sum())} px)",
          cyan.any())
    area.spaces.active.shading.type = 'SOLID'
    with override():
        bpy.ops.allset.ghost(action="UNGHOST_ALL")
    redraw()


step(redraw)
step(redraw)


@step
def s_unghosted():
    px = shot("unghosted")
    got, _at = sample(px, 3)
    check(f"Unghost All: no ghost left ({got.round().astype(int).tolist()} ~ {BG})",
          float(np.abs(got - rgb(BG)).max()) <= 3)


run()
