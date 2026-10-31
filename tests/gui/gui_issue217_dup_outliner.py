"""#217 in a real UI: Maya Workflow Kit layout (Maya Outliner shown), a cube, Move tool. Shift+drag on the X arrow
duplicates it (Smart Duplicate); afterwards, for some seconds, the Outliner link order, the selection and the lead
stay put (before: the copy and the original swapped rows every 0.25 s and the selection flickered). A click on the
original then selects it, and a plain drag on its X arrow moves it.
Screenshot: gui_issue217_outliner.png (after the watch)."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, scale, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
STEPS = 8
MOVES = 4
WATCH = 10          # ticks of 0.4 s: 4 s, sixteen runs of the Outliner order timer


def mod(name):
    return import_module(f"{MODULE}.{name}")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def set_tool(name):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name=name)
    redraw()


def screen(world):
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, world)
    return Vector((region.x + p.x, region.y + p.y))


def arrow(ob):
    """A point on the X arrow of the kit Move manipulator, and the arrow's screen direction."""
    c = ob.matrix_world.translation
    o, a = screen(c), screen(c + Vector((0.1, 0, 0)))
    d = (a - o).normalized()
    m = mod("ui.manipulator")
    length = m.ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0 * scale() * m.SIZE[0]
    return o + d * length * 0.8, d


def hover(p):
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x) + 1, y=int(p.y))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))


def state():
    vl = bpy.context.view_layer
    coll = bpy.data.objects["pCube1"].users_collection[0]
    active = vl.objects.active
    return ([o.name for o in coll.objects], sorted(o.name for o in vl.objects if o.select_get()),
            active.name if active else None)


def drag(name, shift, dist=70, pause=0):
    """Hover, ``pause`` idle ticks with the pointer still on the arrow (a user aiming), press, move, release."""
    def s_hover():
        p, d = arrow(bpy.data.objects[C[name + "_ob"]])
        C[name] = (p, d)
        C[name + "_n"] = len(bpy.data.objects)
        hover(p)

    def s_press():
        p, d = C[name]
        if shift:
            ev('LEFT_SHIFT', 'PRESS', shift=True)        # a real Shift drag
        ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y), shift=shift)

    def s_move():
        p, d = C[name]
        for i in range(1, STEPS + 1):
            q = p + d * dist * i / STEPS
            ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y), shift=shift)

    def s_release():
        p, d = C[name]
        q = p + d * dist
        ev('LEFTMOUSE', 'RELEASE', x=int(q.x), y=int(q.y), shift=shift)
        if shift:
            ev('LEFT_SHIFT', 'RELEASE')

    for s in (s_hover, *[(lambda: None)] * pause, s_press, s_move, s_release, redraw):
        step(s)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cube():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.data.objects["pCube1"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    set_tool("builtin.move")
    region.data.view_distance /= 3.0
    C["dup_ob"] = "pCube1"


for _i in range(3):
    step(redraw)

drag("dup", shift=True)


@step
def s_dup_check():
    copy = bpy.data.objects.get("pCube2")
    check(f"Shift+drag duplicated pCube1 ({[o.name for o in bpy.data.objects if o.type == 'MESH']})",
          copy is not None and len(bpy.data.objects) == C["dup_n"] + 1)
    C["seen"] = [state()]


def _watch():
    C["seen"].append(state())


for _i in range(WATCH):
    step(_watch)


@step
def s_watch_check():
    seen = C["seen"]
    changes = sum(1 for a, b in zip(seen, seen[1:]) if a != b)
    check(f"for {WATCH * 0.4:.0f} s after the duplicate nothing changes by itself: {changes} changes "
          f"(first {seen[0]}, last {seen[-1]})", changes == 0)
    links, selected, active = seen[-1]
    shown = mod("ui.outliner_order").display_order([n for n in links if bpy.data.objects[n].parent is None])
    check(f"the Outliner lists the copy after the original ({shown})",
          shown.index("pCube1") < shown.index("pCube2"))
    check(f"the copy is the selection and the lead ({selected}, {active})",
          selected == ["pCube2"] and active == "pCube2")
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_issue217_outliner.png"))
    hover(screen(bpy.data.objects["pCube1"].matrix_world.translation))


@step
def s_click_press():
    p = screen(bpy.data.objects["pCube1"].matrix_world.translation)
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y))


@step
def s_click_release():
    p = screen(bpy.data.objects["pCube1"].matrix_world.translation)
    ev('LEFTMOUSE', 'RELEASE', x=int(p.x), y=int(p.y))
    redraw()


for _i in range(4):
    step(redraw)


@step
def s_click_check():
    _links, selected, active = state()
    check(f"a click on the original selects it ({selected}, {active})",
          selected == ["pCube1"] and active == "pCube1")


def _moves(k):
    @step
    def s_start():
        C[f"move{k}_ob"] = "pCube1"
        C["start"] = bpy.data.objects["pCube1"].location.copy()

    drag(f"move{k}", shift=False, dist=40, pause=k % 3)

    @step
    def s_move_check():
        ob = bpy.data.objects["pCube1"]
        moved = ob.location - C["start"]
        C["moves"].append(moved.x > 1e-3 and abs(moved.y) < 1e-5 and abs(moved.z) < 1e-5
                          and len(bpy.data.objects) == C[f"move{k}_n"])
        print(f"ISSUE217 drag {k}: moved {tuple(round(v, 4) for v in moved)}", flush=True)


C["moves"] = []
for _k in range(MOVES):
    _moves(_k)


@step
def s_moves_check():
    check(f"plain drags on the X arrow move the original along X every time ({C['moves']})",
          len(C["moves"]) == MOVES and all(C["moves"]))


run()
