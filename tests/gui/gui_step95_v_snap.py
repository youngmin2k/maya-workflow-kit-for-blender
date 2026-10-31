"""V point snap with the Move manipulator, default and close zoom.

Maya Workflow Kit cm template, pCube1 at the origin and pCube2 at x = 3 cm, Move tool. V held + drag of pCube1's X arrow to the
screen position of a pCube2 vertex -> pCube1's pivot lands on that vertex projected onto the X axis (t x = 2.5 cm).
Run with the template view (small cubes) and zoomed in close (the dragged cube fills much of the view). Mouse moves go one per timer tick: Blender recomputes the snap target at most once
per 10 ms (transform_snap.cc transform_snap_mixed_apply), so a burst of moves queued in one tick keeps the target found
for its first move — that, not the zoom, made the close-zoom snap fail."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, scale, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
STEPS = 12


def mod(name):
    return import_module(f"{MODULE}.{name}")


def k():
    return mod("operators.units").maya_unit()


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def screen(world):
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, world)
    return Vector((region.x + p.x, region.y + p.y))


def px_world(at):
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, at)
    w = region_2d_to_location_3d(region, region.data, p + Vector((1, 0)), at)
    return (w - at).length


def arrow_point(ob, frac):
    """Window point ``frac`` of the X arrow from the manipulator centre."""
    c = ob.matrix_world.translation
    length = mod("ui.manipulator").ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0 * scale()
    return screen(c + Vector((1, 0, 0)) * length * frac * px_world(c))


def hover(p):
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x) + 1, y=int(p.y))


def set_tool(name):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name=name)
    redraw()


def cubes():
    return bpy.data.objects["pCube1"], bpy.data.objects["pCube2"]


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cubes():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.allset.create(kind='CUBE')
    a, b = cubes()
    b.location = (3 * k(), 0, 0)
    C["view"] = (region.data.view_distance, region.data.view_location.copy())
    set_tool("builtin.move")


def pick(kind, verts, a, eye):
    if kind == "camera":
        return min(verts, key=lambda p: (p - eye).length)
    if kind == "inner":  # the pCube2 corner nearest pCube1 (the original target; may sit behind pCube1)
        return min(verts, key=lambda p: (p - a.matrix_world.translation).length)
    raise ValueError(kind)


def case(name, distance, handle="arrow", target="camera", pacing="paced"):
    """V + handle drag onto a pCube2 vertex with the view at ``distance`` x the template's. ``paced`` = one mouse
    move per timer tick (like a hand: events further apart than Blender's 10 ms snap throttle); ``burst`` = all
    moves in one tick (only the first one in each 10 ms recomputes the snap target)."""

    def prepare():
        a, b = cubes()
        a.location = (0, 0, 0)
        for o in bpy.context.view_layer.objects:
            o.select_set(o is a)
        bpy.context.view_layer.objects.active = a
        _area, region = view3d()
        rv3d = region.data
        d0, loc0 = C["view"]
        rv3d.view_distance = d0 * distance
        rv3d.view_location = loc0 if distance == 1.0 else Vector((1.5 * k(), 0, 0))
        bpy.context.view_layer.update()
        redraw()

    def aim():
        a, b = cubes()
        _area, region = view3d()
        eye = region.data.view_matrix.inverted().translation
        verts = [b.matrix_world @ v.co for v in b.data.vertices]
        C["target"] = pick(target, verts, a, eye)
        C["p"] = arrow_point(a, 0.75) if handle == "arrow" else screen(a.matrix_world.translation)
        C["to"] = screen(C["target"])
        print(f"GUI {name}: view distance {region.data.view_distance / k():.2f} cm, cube px "
              f"{0.01 / px_world(a.matrix_world.translation) * k() / 0.01:.1f}, press {tuple(C['p'])}, "
              f"to {tuple(C['to'])}, target {tuple(round(v / k(), 3) for v in C['target'])}")
        if SHOTS:
            screenshot(os.path.join(SHOTS, f"gui_step95_{name}_before.png"))
        hover(C["p"])

    def press():
        ev('V', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))
        ev('LEFTMOUSE', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))

    def mover(i):
        def move():
            p, to = C["p"], C["to"]
            for j in {"burst": range(1, STEPS + 1), "jump": (STEPS,)}.get(pacing, (i,)):
                q = p + (to - p) * (j / STEPS)
                ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y))
        return move

    def release():
        print(f"GUI {name} ({pacing}) before release: loc {tuple(round(v / k(), 3) for v in cubes()[0].location)}")
        if SHOTS:
            screenshot(os.path.join(SHOTS, f"gui_step95_{name}_drag.png"))
        ev('LEFTMOUSE', 'RELEASE', x=int(C["to"].x), y=int(C["to"].y))
        ev('V', 'RELEASE')

    def done():
        got = cubes()[0].matrix_world.translation
        want = Vector((C["target"].x, 0, 0)) if handle == "arrow" else C["target"]
        what = "X arrow puts pCube1 on pCube2's vertex projected onto X" if handle == "arrow" else             "centre handle puts pCube1's pivot on pCube2's vertex"
        check(f"{name}: V + {what} "
              f"({tuple(round(v / k(), 3) for v in got)} cm, want {tuple(round(v / k(), 3) for v in want)}, S4)",
              (got - want).length < 1e-6)

    moves = [mover(1)] if pacing in ("burst", "jump") else [mover(i) for i in range(1, STEPS + 1)]
    for fn in (prepare, aim, press, *moves, release, done):
        step(fn)


CASES = os.environ.get("ALLSET_STEP95_CASES", "")
if CASES:
    for spec in CASES.split(";"):
        n, d, h, t, pc = spec.split(",")
        case(n, float(d), h, t, pc)
else:
    case("default", 1.0)
    case("default_inner", 1.0, target="inner")
    case("close", 0.15)
    case("close_inner", 0.15, target="inner")
    case("close_centre", 0.15, handle="centre")

run()
