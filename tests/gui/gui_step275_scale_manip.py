"""#200: in a real UI: Maya Workflow Kit layout, a cube, Scale tool (R).

- Centre handle: press on it, drag left (with some vertical wobble, which Maya ignores) until the factor is 0.1:
  the cube's scale is 1 + dx * wpp / R (horizontal px since the press, world length of a px at the pivot, pivot to
  the farthest corner of the cube's world box); one Ctrl+Z gives 1.0 back.
- X axis handle: +45 px along it = 1 + 45 / (90 px x UI scale), only X changes; it becomes the active handle.
- MMB drag anywhere then scales X the same way at half speed (active handle).
- XY plane handle: both X and Y by the drag along its diagonal; Ctrl+drag on the X handle scales Y and Z.
Screenshot: gui_step275_scale.png (mid-drag, header "Scale: ...")."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, scale, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
STEPS = 10


def mod(name):
    return import_module(f"{MODULE}.{name}")


def ob1():
    return bpy.data.objects["pCube1"]


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


def px_world(at):
    """World length of one px at the depth of ``at`` (Maya: 2 depth tan(fov / 2) / view width)."""
    _area, region = view3d()
    rv3d = region.data
    depth = -(rv3d.view_matrix @ at).z
    lens = view3d()[0].spaces.active.lens
    # Blender's viewport lens is on a 72 mm sensor fitted to the larger side of the region
    return depth * 72.0 / lens / max(region.width, region.height) if rv3d.is_perspective else None


def arrow_len_px():
    manipulator = mod("ui.manipulator")
    return manipulator.ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0 * scale() * manipulator.SIZE[0]


def axis_len():
    """Screen px per unit of axis change at the pivot: 90 px at UI scale 1 and the default size."""
    return 90.0 * scale() * bpy.context.preferences.view.gizmo_size / 75.0 * mod("ui.manipulator").SIZE[0]


def depth(p):
    rv3d = view3d()[1].data
    return -(rv3d.view_matrix @ p).z if rv3d.is_perspective else 1.0


def handle_factor(d, point, length):
    """Maya's axis / plane factor: d px along the handle, the handle point's depth against the pivot's."""
    return 1 + d * depth(point) / (length * depth(C["c"]))


def hover(p):
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x) + 1, y=int(p.y))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))


def drag(button, start, path, name):
    """Steps: hover, press, first stretch alone, the rest, release (a transform started by a press sees moves
    from later ticks only)."""
    def s1():
        a = start()
        C[name + "_a"] = a
        C[name + "_pts"] = [a + d for d in path(a)]
        hover(a)

    def s2():
        a = C[name + "_a"]
        ev(button, 'PRESS', x=int(a.x), y=int(a.y))

    def s3():
        q = C[name + "_pts"][0]
        ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y))

    def s4():
        for q in C[name + "_pts"][1:]:
            ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y))

    def s5():
        if SHOTS and name == "centre":
            screenshot(os.path.join(SHOTS, "gui_step275_scale.png"))
        C[name + "_last"] = dict(mod("operators.manip_scale").LAST)
        q = C[name + "_pts"][-1]
        ev(button, 'RELEASE', x=int(q.x), y=int(q.y))

    for s in (s1, s2, s3, s4, s5):
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
    ob = ob1()
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    set_tool("builtin.scale")
    region.data.view_distance /= 4.0        # the template camera shows the 1-unit cube small: room for the drag
    bpy.ops.ed.undo_push(message="cube made")


@step
def s_redraw():
    redraw()        # the view matrix follows view_distance after a redraw


@step
def s_sizes():
    ob = ob1()
    c = ob.matrix_world.translation.copy()
    ms = mod("operators.manip_scale")
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        r = ms.radius(bpy.context, c)
    wpp = px_world(c)
    r_px = r / wpp
    C.update(c=c, r=r, wpp=wpp, r_px=r_px)
    # drag left to f = 0.1 (dx = -0.9 R_px), with a 20 px vertical wobble on the way
    C["dx"] = dx = -round(0.9 * r_px)
    C["want"] = ms.uniform_factor(dx, wpp, r)
    print(f"STEP275 R {r:.6f} wpp {wpp:.6g} R_px {r_px:.1f} dx {dx} want {C['want']:.5f}", flush=True)
    check(f"room for the drag: R on screen {r_px:.1f} px (> 30)", r_px > 30)


def _centre_path(a):
    dx = C["dx"]
    pts = [Vector((dx * i / STEPS, (20 if i % 2 else -10) if i < STEPS else 0)) for i in range(1, STEPS + 1)]
    return pts


drag('LEFTMOUSE', lambda: screen(C["c"]), _centre_path, "centre")


@step
def s_centre_check():
    s = ob1().scale
    last = C.get("centre_last", {})
    _area, region = view3d()
    end = C["centre_pts"][-1]
    press = last.get("press") or (C["centre_a"].x - region.x, C["centre_a"].y - region.y)
    dx = int(end.x) - region.x - press[0]          # the px the events moved, from the press the drag saw
    C["wpp"] = px_world(C["c"])                    # now: the layout may have refitted the view since s_sizes
    want = mod("operators.manip_scale").uniform_factor(dx, C["wpp"], C["r"])
    check(f"centre drag {dx:.1f} px left: scale {s.x:.5f} {s.y:.5f} {s.z:.5f} = Maya 1 + dx wpp / R "
          f"{want:.5f} (press at {last.get('press')}, factor shown {last.get('factor', 0):.5f}, op wpp "
          f"{last.get('wpp', 0):.6g} R {last.get('radius', 0):.6f}, test wpp {C['wpp']:.6g} R {C['r']:.6f})",
          all(abs(v - want) < 1e-3 for v in s))
    check(f"about 0.1 ({s.x:.4f})", abs(s.x - 0.1) < 0.02)
    ops = bpy.context.window_manager.operators
    check(f"one registered resize ({ops[-1].bl_idname if len(ops) else None})",
          len(ops) and ops[-1].bl_idname == "TRANSFORM_OT_resize")
    h = mod("operators.manip").HANDLES.get('RESIZE', "unset")
    check(f"the centre stays the active handle ({h})", h is None)
    hover(screen(C["c"]) + Vector((150, 80)))
    ev('LEFT_CTRL', 'PRESS')
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)
    ev('LEFT_CTRL', 'RELEASE')


@step
def s_undo_check():
    s = ob1().scale
    check(f"one Ctrl+Z gives the scale back ({s.x:.5f}, {s.y:.5f}, {s.z:.5f})",
          all(abs(v - 1.0) < 1e-5 for v in s))


def _x_dir():
    c = C["c"]
    d = screen(c + Vector((1, 0, 0)) * C["wpp"] * 50) - screen(c)
    return d.normalized()


def _axis_start():
    return screen(C["c"]) + _x_dir() * arrow_len_px() * 0.6


def _axis_path(_a):
    d = _x_dir()
    return [d * 45 * i / STEPS for i in range(1, STEPS + 1)]


drag('LEFTMOUSE', _axis_start, _axis_path, "axis")


def _along_sent(name):
    a, b = C[name + "_a"], C[name + "_pts"][-1]
    ms = mod("operators.manip_scale")
    last = C.get(name + "_last", {})
    press = last.get("press")
    _area, region = view3d()
    start = Vector(press) + Vector((region.x, region.y)) if press else Vector((int(a.x), int(a.y)))
    drag_v = Vector((int(b.x), int(b.y))) - start
    return ms.along(drag_v, last.get("dir") or tuple(_x_dir())), last


@step
def s_axis_check():
    s = ob1().scale
    d, last = _along_sent("axis")
    length = axis_len()
    tip = C["c"] + Vector((1, 0, 0)) * length * C["wpp"]
    want = handle_factor(d, tip, length)
    check(f"X handle +{d:.1f} px: scale X {s.x:.5f} = 1 + d D_tip / ({length:.1f} px D0) = {want:.5f}, Y Z stay "
          f"({s.y:.5f}, {s.z:.5f}; op length {last.get('length')})",
          abs(s.x - want) < 1e-3 and abs(s.y - 1) < 1e-6 and abs(s.z - 1) < 1e-6 and last.get("mode") == 'AXIS')
    h = mod("operators.manip").HANDLES.get('RESIZE')
    check(f"the X handle becomes the active handle ({h})",
          h is not None and tuple(h["constraint_axis"]) == (True, False, False))
    C["sx"] = s.x


drag('MIDDLEMOUSE', lambda: screen(C["c"]) + Vector((-200, 120)), lambda a: [_x_dir() * 30 * i / STEPS
                                                                                 for i in range(1, STEPS + 1)], "mmb")


@step
def s_mmb_check():
    s = ob1().scale
    d, last = _along_sent("mmb")
    length = axis_len()
    tip = C["c"] + Vector((1, 0, 0)) * length * C["wpp"]
    want = C["sx"] * handle_factor(d, tip, 2 * length)             # MMB anywhere: half speed
    check(f"MMB drag anywhere with X active, half speed: scale X {s.x:.5f} = {want:.5f}, Y Z stay "
          f"({s.y:.5f}, {s.z:.5f})",
          abs(s.x - want) < 1e-3 and abs(s.y - 1) < 1e-6 and abs(s.z - 1) < 1e-6)
    running = [op.bl_idname for op in win().modal_operators]
    check(f"no modal left running ({running})", not any("manip_scale" in r or r.startswith("TRANSFORM") for r in running))
    C["s_before"] = s.copy()
    C["names"] = {o.name for o in bpy.context.scene.objects}
    mod("operators.manip").HANDLES.pop('RESIZE', None)      # centre active again (the tool key resets it)
    redraw()


# --- plane handle (XY) and Ctrl on the X handle -----------------------------------------------------------------

def _plane_anchor():
    """Maya's plane drag point: 0.44 handle lengths out on the XY diagonal."""
    reach = axis_len() * C["wpp"] * 0.44
    return C["c"] + (Vector((1, 0, 0)) + Vector((0, 1, 0))) * reach / 2 ** 0.5


def _plane_start():
    at = mod("ui.manipulator").PLANE_AT
    world = C["c"] + (Vector((1, 0, 0)) + Vector((0, 1, 0))) * at * arrow_len_px() * C["wpp"]
    return screen(world)


def _plane_dir():
    return (screen(_plane_anchor()) - screen(C["c"])).normalized()


@step
def s_plane_reset():
    ob1().scale = (1, 1, 1)
    mod("operators.manip").HANDLES.pop('RESIZE', None)
    redraw()


drag('LEFTMOUSE', _plane_start, lambda a: [_plane_dir() * -30 * i / STEPS for i in range(1, STEPS + 1)], "plane")


@step
def s_plane_check():
    s = ob1().scale
    last = C.get("plane_last", {})
    a, b = C["plane_a"], C["plane_pts"][-1]
    _area, region = view3d()
    press = last.get("press")
    start = Vector(press) + Vector((region.x, region.y)) if press else Vector((int(a.x), int(a.y)))
    d = mod("operators.manip_scale").along(Vector((int(b.x), int(b.y))) - start, last.get("dir") or tuple(_plane_dir()))
    want = handle_factor(d, _plane_anchor(), axis_len() * 0.44)
    check(f"XY plane handle {d:.1f} px: X Y {s.x:.5f} {s.y:.5f} = {want:.5f}, Z stays {s.z:.5f} "
          f"(mode {last.get('mode')})", abs(s.x - want) < 1e-3 and abs(s.y - want) < 1e-3 and abs(s.z - 1) < 1e-6
          and last.get("mode") == 'PLANE')
    h = mod("operators.manip").HANDLES.get('RESIZE')
    check(f"the XY plane becomes the active handle ({h})",
          h is not None and tuple(h["constraint_axis"]) == (True, True, False))
    ob1().scale = (1, 1, 1)
    mod("operators.manip").HANDLES.pop('RESIZE', None)
    redraw()


@step
def s_ctrl_hover():
    hover(_axis_start())


@step
def s_ctrl_press():
    p = _axis_start()
    C["ctrl_a"] = p
    ev('LEFT_CTRL', 'PRESS', ctrl=True)
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y), ctrl=True)


@step
def s_ctrl_move1():
    q = C["ctrl_a"] + _x_dir() * 4
    ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y), ctrl=True)


@step
def s_ctrl_move2():
    for i in range(1, STEPS + 1):
        q = C["ctrl_a"] + _x_dir() * 40 * i / STEPS
        ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y), ctrl=True)


@step
def s_ctrl_release():
    C["ctrl_last"] = dict(mod("operators.manip_scale").LAST)
    q = C["ctrl_a"] + _x_dir() * 40
    C["ctrl_end"] = q
    ev('LEFTMOUSE', 'RELEASE', x=int(q.x), y=int(q.y), ctrl=True)
    ev('LEFT_CTRL', 'RELEASE')


@step
def s_ctrl_check():
    s = ob1().scale
    last = C.get("ctrl_last", {})
    _area, region = view3d()
    press = last.get("press")
    start = Vector(press) + Vector((region.x, region.y)) if press else C["ctrl_a"]
    q = C["ctrl_end"]
    d = mod("operators.manip_scale").along(Vector((int(q.x), int(q.y))) - start, last.get("dir") or tuple(_x_dir()))
    tip = C["c"] + Vector((1, 0, 0)) * axis_len() * C["wpp"]
    want = handle_factor(d, tip, axis_len())
    check(f"Ctrl+drag on the X handle: Y Z {s.y:.5f} {s.z:.5f} = the X handle's factor {want:.5f}, X stays "
          f"{s.x:.5f} (channels {last.get('channels')})",
          abs(s.y - want) < 1e-3 and abs(s.z - want) < 1e-3 and abs(s.x - 1) < 1e-6)
    ob1().scale = C["s_before"]
    mod("operators.manip").HANDLES.pop('RESIZE', None)
    redraw()


@step
def s_shift_hover():
    hover(screen(C["c"]))


@step
def s_shift_press():
    p = screen(C["c"])
    ev('LEFT_SHIFT', 'PRESS', shift=True)       # a keyboard Shift reaches the window state
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y), shift=True)


@step
def s_shift_move1():
    p = screen(C["c"])
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x) + 6, y=int(p.y), shift=True)


@step
def s_shift_move2():
    p = screen(C["c"])
    for i in range(2, 9):
        ev('MOUSEMOVE', 'NOTHING', x=int(p.x) + 5 * i, y=int(p.y), shift=True)


@step
def s_shift_release():
    p = screen(C["c"])
    C["shift_last"] = dict(mod("operators.manip_scale").LAST)
    ev('LEFTMOUSE', 'RELEASE', x=int(p.x) + 40, y=int(p.y), shift=True)
    ev('LEFT_SHIFT', 'RELEASE')


@step
def s_shift_wait():
    pass        # the Smart Duplicate watcher keeps the copy once the scale ended


@step
def s_shift_check():
    new = [o for o in bpy.context.scene.objects if o.name not in C["names"]]
    last = C.get("shift_last", {})
    f = last.get("factor", 0)
    orig = ob1().scale
    ok_copy = len(new) == 1 and all(abs(a - b * f) < 1e-4 for a, b in zip(new[0].scale, C["s_before"]))
    check(f"Shift+drag on the centre = Smart Duplicate, the copy scaled x{f:.4f} "
          f"({[o.name for o in new]}, {[tuple(round(v, 4) for v in o.scale) for o in new]})", ok_copy and f > 1.2)
    _area, region = view3d()
    p = screen(C["c"])
    press = last.get("press") or (0, 0)
    r = C["r"] * C["s_before"].length / 3 ** 0.5     # R of the lead's world box: the cube scaled (1.775, 1, 1)
    want = mod("operators.manip_scale").uniform_factor(int(p.x) + 40 - region.x - press[0], C["wpp"], r)
    check(f"the copy's factor is Maya's for the drag from the press ({f:.5f} vs {want:.5f}, press {press}, "
          f"pivot {int(p.x) - region.x, int(p.y) - region.y})", abs(f - want) < 1e-3)
    check(f"original keeps its scale ({tuple(round(v, 4) for v in orig)})",
          all(abs(a - b) < 1e-6 for a, b in zip(orig, C["s_before"])))


run()
