"""Lane A (Issue #138) in a real UI: a CV curve and a cube in the Maya layout, Constrain > Motion Paths >
Attach to Motion Path from the menu map (selection = cube + curve), scrub to frame 60: the cube sits on the curve
facing along it (expected at frame 60: (9.894338, 0, 0.105634), ry 44.977 deg);
Set Motion Path Key at frame 50 from the menu adds an edit point and a key. Shots in the shots folder."""

import math
import os
import sys
from importlib import import_module

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
PTS = [(0, 0, 0), (5, 0, 5), (10, 0, 0), (15, 0, -5), (20, 0, 0)]


def override():
    a, region = view3d()
    return bpy.context.temp_override(window=win(), screen=win().screen, area=a, region=region)


def run_item(path):
    with override():
        return bpy.ops.allset.menu_item(item=path)


def k():
    return import_module(MODULE + ".operators.units").maya_unit()


def sel(*obs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def shot(name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        screenshot(os.path.join(SHOTS, name))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    cmaya = import_module(MODULE + ".operators.curves_maya")
    c207 = import_module(MODULE + ".operators.curves_207")
    path = cmaya.make_cv_curve(bpy.context, [tuple(x * k() for x in c207.from_maya(p)) for p in PTS])
    path.name = "path"
    with override():
        bpy.ops.allset.create(kind='CUBE')
    car = bpy.context.active_object
    car.name = "car"
    car.location = (2 * k(), 3 * k(), 1 * k())       # Maya ignores where the object was
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end, sc.use_preview_range = 1, 120, False
    sc.frame_set(1)
    sel(path, car)
    C["names"] = (path.name, car.name)


@step
def s_attach():
    res = run_item("Constrain/Motion Paths/Attach to Motion Path")
    mp = import_module(MODULE + ".operators.motion_path_228")
    car = bpy.data.objects[C["names"][1]]
    c = mp.find(car)
    check(f"Attach to Motion Path from the menu ({res}) made {c.name if c else None}", c is not None
          and c.target is not None and c.target.name == C["names"][0])
    car.scale = (3.0, 1.0, 1.0)       # long along the front axis (X) so the shot shows the heading


@step
def s_frame60():
    sc = bpy.context.scene
    sc.frame_set(60)
    car = bpy.data.objects[C["names"][1]]
    want = Vector((9.894338, -0.105634, 0.0)) * k()
    got = car.matrix_world.to_translation()
    check(f"frame 60 on the path: {tuple(round(x / k(), 4) for x in got)} (Maya 9.8943 0 0.1056) "
          f"err {(got - want).length / k():.1e}", (got - want).length < 1e-3 * k())
    heading = math.degrees(car.matrix_world.to_3x3().normalized().to_euler().z)
    check(f"frame 60 faces along the path: heading {heading:.3f} deg (Maya ry 44.977)", abs(heading - 44.977254) < 0.01)
    sel(bpy.data.objects[C["names"][0]], car)
    a, region = view3d()
    with bpy.context.temp_override(window=win(), screen=win().screen, area=a, region=region):
        bpy.ops.view3d.view_axis(type='TOP')
    rv = a.spaces.active.region_3d
    rv.view_perspective = 'ORTHO'
    rv.view_location = Vector((10.0, 0.0, 0.0)) * k()
    rv.view_distance = 26.0 * k() * a.spaces.active.lens / 72.0      # ~26 units across
    for a_ in win().screen.areas:
        a_.tag_redraw()


@step
def s_wait():
    pass


@step
def s_shot60():
    shot("gui_step228_motion_path_f60.png")


@step
def s_setkey():
    sc = bpy.context.scene
    sc.frame_set(50)
    car = bpy.data.objects[C["names"][1]]
    sel(car)
    res = run_item("Constrain/Motion Paths/Set Motion Path Key")
    mp = import_module(MODULE + ".operators.motion_path_228")
    fc = mp.offset_curve(car, mp.find(car))
    keys = [tuple(round(x, 4) for x in kp.co) for kp in fc.keyframe_points]
    path = bpy.data.objects[C["names"][0]]
    check(f"Set Motion Path Key at 50 ({res}): keys {keys} (Maya 1 / 50 0.3708 / 120), path spline "
          f"{path.data.splines[0].type}", [x[0] for x in keys] == [1.0, 50.0, 120.0] and abs(keys[1][1] - 0.3708) < 1e-3)
    sel(path, car)
    for a_ in win().screen.areas:
        a_.tag_redraw()


@step
def s_wait2():
    pass


@step
def s_shot50():
    shot("gui_step228_motion_path_key50.png")


run()
