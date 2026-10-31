"""In a real UI, in Maya's order:

Maya Workflow Kit layout, a cube, Move tool: the Maya-shaped manipulator (size, X handle drag, active
handle), X hold + X arrow drag from 0.3 cm lands on whole cm (S2), D hold + drag moves only
the pivot (translate, geometry stay, P3), D + X snaps the pivot to the grid, E then rotates
about the new pivot (P1), V + centre handle puts the pivot on another cube's vertex (S4), the
Status Line grid button follows X (S6); screenshots of Move / Rotate / Scale / pivot mode."""

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
STEPS = 10
TMP = os.path.join(os.environ.get("TEMP", "."), "allset_step59_shot.png")


def mod(name):
    return import_module(f"{MODULE}.{name}")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def k():
    return mod("operators.units").maya_unit()


def ob1():
    return bpy.data.objects["pCube1"]


def screen(world):
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, world)
    return Vector((region.x + p.x, region.y + p.y))


def px_world(at):
    """World length of one window pixel at ``at`` (the manipulator's draw scale)."""
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, at)
    w = region_2d_to_location_3d(region, region.data, p + Vector((1, 0)), at)
    return (w - at).length


def arrow_len_px():
    return mod("ui.manipulator").ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0 * scale()


def handle_point(ob, axis, frac):
    """Window point ``frac`` of the Move arrow along world ``axis`` from the manipulator centre."""
    c = ob.matrix_world.translation
    world = c + Vector(axis) * arrow_len_px() * frac * px_world(c)
    return screen(world)


def hover(p):
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x) + 1, y=int(p.y))


def press_move(p, to):
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y))
    for i in range(1, STEPS + 1):
        q = p + (to - p) * (i / STEPS)
        ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y))


def release(to):
    ev('LEFTMOUSE', 'RELEASE', x=int(to.x), y=int(to.y))


def set_tool(name):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name=name)
    redraw()


def world_verts(ob):
    return [ob.matrix_world @ v.co for v in ob.data.vertices]


def select_only(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob


def measure(path, origin, colour, radius):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = img.pixels[:]
    ox, oy = int(origin.x), int(origin.y)
    best = 0.0
    for y in range(max(0, oy - radius), min(h, oy + radius)):
        row = y * w
        for x in range(max(0, ox - radius), min(w, ox + radius)):
            i = (row + x) * 4
            if abs(px[i] - colour[0]) < 0.12 and abs(px[i + 1] - colour[1]) < 0.12 and abs(px[i + 2] - colour[2]) < 0.12:
                best = max(best, ((x - ox) ** 2 + (y - oy) ** 2) ** 0.5)
    bpy.data.images.remove(img)
    return best


# --- Maya Workflow Kit layout, a cube, Move tool ---------------------------------------------------------

@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cube():
    bpy.ops.allset.keymap_activate()
    # Keep the on-screen sizes this test was written for: the template view went from lens 35 to 70
    #, which doubles them. (The V-snap drag below queues its moves in one tick; Blender recomputes the
    # snap target at most once per 10 ms, so a longer drag never caught.)
    view3d()[1].data.view_distance *= 2.0
    ts = bpy.context.scene.tool_settings
    slots = bpy.context.scene.transform_orientation_slots
    check(f"template: Maya axis modes Move World / Rotate+Scale Object, pivot at the lead, rotate snap 15 "
          f"({slots[1].type}, {slots[2].type}, {slots[3].type}, {ts.transform_pivot_point}, "
          f"{ts.snap_angle_increment_3d:.4f})",
          (slots[1].type, slots[2].type, slots[3].type) == ('GLOBAL', 'LOCAL', 'LOCAL')
          and ts.transform_pivot_point == 'ACTIVE_ELEMENT' and abs(ts.snap_angle_increment_3d - 0.2618) < 1e-3)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.allset.create(kind='CUBE')
    b = bpy.context.view_layer.objects.active
    b.location = (3 * k(), 0, 0)
    select_only(ob1())
    set_tool("builtin.move")


@step
def s_widget():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        tool = bpy.context.workspace.tools.from_space_view3d_mode('OBJECT')
        check(f"Move tool draws the Maya manipulator ({tool.idname}: {tool.widget})",
              tool.idname == "builtin.move" and tool.widget == "ALLSET_GGT_xform")
    redraw()


@step
def s_shot_move():
    with bpy.context.temp_override(window=win()):
        bpy.ops.screen.screenshot(filepath=TMP)
    shot("gui_step59_move.png")


@step
def s_measure():
    o = screen(ob1().matrix_world.translation)
    blue = mod("ui.manipulator").axis_colours()['Z']     # Maya's Z blue (#76), not the theme's
    want = arrow_len_px()
    got = measure(TMP, o, blue, int(want * 1.6))
    check(f"Move Z (Maya Y) arrow at the Maya size ({got:.0f} px drawn, {want:.0f} px = 108 x gizmo/75 x UI)",
          0.7 * want < got < 1.2 * want)
    C["p"] = handle_point(ob1(), (1, 0, 0), 0.6)
    C["start"] = ob1().location.copy()
    hover(C["p"])


# --- plain drag on the X arrow + active handle ------------------------------------------------

@step
def s_drag_x():
    C["to"] = C["p"] + (handle_point(ob1(), (1, 0, 0), 1.6) - C["p"])
    press_move(C["p"], C["to"])


@step
def s_drag_x_release():
    release(C["to"])


@step
def s_drag_x_done():
    moved = ob1().location - C["start"]
    check(f"X arrow drag moves along X only ({moved.x / k():.2f}, {moved.y / k():.3f}, {moved.z / k():.3f} cm)",
          moved.x > 0.1 * k() and abs(moved.y) < 1e-6 and abs(moved.z) < 1e-6)
    h = mod("operators.manip").HANDLES.get('TRANSLATE')
    check(f"X becomes the active handle (yellow, Maya M2): {h}",
          h is not None and tuple(h["constraint_axis"]) == (True, False, False))
    redraw()


@step
def s_shot_active():
    shot("gui_step59_move_active_x.png")
    # S2: start at 0.3 cm, X hold + drag
    ob1().location = (0.3 * k(), 0, 0)
    bpy.context.view_layer.update()
    C["p"] = handle_point(ob1(), (1, 0, 0), 0.6)
    C["to"] = handle_point(ob1(), (1, 0, 0), 1.9)
    hover(C["p"])


@step
def s_x_snap():
    ev('X', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_x_snap_state():
    C["grid_button"] = mod("ui.status_line").snap_on(bpy.context.scene.tool_settings, "GRID")
    redraw()


@step
def s_x_snap_shot():
    shot("gui_step59_status_line_x_held.png")
    press_move(C["p"], C["to"])


@step
def s_x_snap_release():
    release(C["to"])
    ev('X', 'RELEASE')


@step
def s_x_snap_done():
    n = ob1().location.x / k()
    check("Status Line grid snap button on while X is held (S6)", C["grid_button"])
    check("grid snap off again after X", not mod("ui.status_line").snap_on(bpy.context.scene.tool_settings, "GRID"))
    check(f"X snap from 0.3 cm lands on a whole cm, absolute grid (x = {n:.4f} cm)",
          abs(n - round(n)) < 1e-3 and round(n) >= 1)
    # D hold: pivot only (back near the middle of the view first)
    ob1().location = (0, 0, 0)
    bpy.context.view_layer.update()
    C["loc"] = ob1().location.copy()
    C["verts"] = world_verts(ob1())
    C["p"] = handle_point(ob1(), (1, 0, 0), 0.6)
    C["to"] = handle_point(ob1(), (1, 0, 0), 1.1)
    hover(C["p"])


@step
def s_pivot_drag():
    ev('D', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))
    redraw()


@step
def s_pivot_shot():
    shot("gui_step59_pivot_mode.png")
    check("D held = pivot edit (Affect Only Origins + Parents)",
          bpy.context.scene.tool_settings.use_transform_data_origin)
    press_move(C["p"], C["to"])


@step
def s_pivot_release():
    release(C["to"])


@step
def s_pivot_d_up():
    ev('D', 'RELEASE')


@step
def s_pivot_done():
    ob = ob1()
    same = all((a - b).length < 1e-6 for a, b in zip(C["verts"], world_verts(ob)))
    piv = ob.matrix_world.translation / k()
    check(f"D + drag moves only the pivot: translate stays ({ob.location.x / k():.3f} cm), "
          f"pivot at x {piv.x:.3f} cm, geometry stays (P3)",
          (ob.location - C["loc"]).length < 1e-7 and abs(ob.delta_location.x) > 0.1 * k() and same)
    check("pivot mode off after D", not bpy.context.scene.tool_settings.use_transform_data_origin)
    print("GUI after pivot drag modal ops", [op.bl_idname for op in win().modal_operators], C["p"])
    C["p"] = handle_point(ob, (1, 0, 0), 0.6)
    C["to"] = handle_point(ob, (1, 0, 0), 0.95)
    hover(C["p"])


@step
def s_pivot_snap_keys():
    ev('D', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))
    print("GUI D event sent at", C["p"], "window", win().width, win().height)


@step
def s_pivot_snap_x():
    print("GUI after D modal ops", [op.bl_idname for op in win().modal_operators],
          bpy.context.scene.tool_settings.use_transform_data_origin)
    ev('X', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))
    redraw()


@step
def s_pivot_snap_hover():
    ts = bpy.context.scene.tool_settings
    print("GUI D+X state", ts.use_transform_data_origin, ts.use_snap, set(ts.snap_elements))
    hover(C["p"])


@step
def s_pivot_snap_drag():
    press_move(C["p"], C["to"])


@step
def s_pivot_snap_release():
    release(C["to"])
    ev('X', 'RELEASE')
    ev('D', 'RELEASE')


@step
def s_pivot_snap_done():
    ob = ob1()
    piv = ob.matrix_world.translation.x / k()
    check(f"D + X: the pivot snaps to a whole cm (x = {piv:.4f} cm), translate stays",
          abs(piv - round(piv)) < 1e-3 and (ob.location - C["loc"]).length < 1e-7)
    C["pivot"] = ob.matrix_world.translation.copy()
    C["verts"] = world_verts(ob)
    set_tool("builtin.rotate")


def _ring_try(i):
    """Hover / press-drag / release on the Z ring at the i-th radius guess (the C rotate gizmo's
    radius depends on the UI scale in ways the test can't read: try 0.9, 0.75, 1.05 x gizmo size)."""
    factor = (0.9, 0.75, 1.05)[i]

    @step
    def hover_ring():
        if abs(ob1().rotation_euler.z) > 0.05:
            return
        ob = ob1()
        c = ob.matrix_world.translation
        r = factor * bpy.context.preferences.view.gizmo_size * bpy.context.preferences.system.ui_scale * px_world(c)
        # on the Z ring (XY plane), -X side: the moved pivot may sit near the dock on the right
        C["p"] = screen(c + Vector((-r, 0, 0)))
        C["to"] = screen(c + Vector((-r, -r * 0.6, 0)))
        C["ring_try"] = abs(ob1().rotation_euler.z) <= 0.05
        hover(C["p"])
        if i == 0:
            shot("gui_step59_rotate.png")

    @step
    def drag_ring():
        if C.get("ring_try"):
            press_move(C["p"], C["to"])

    @step
    def release_ring():
        if C.get("ring_try"):
            release(C["to"])
            C["ring_try"] = False


for _i in range(3):
    _ring_try(_i)


@step
def s_rotate_done():
    ob = ob1()
    rz = ob.rotation_euler.z
    moved = [(a - b).length for a, b in zip(C["verts"], world_verts(ob))]
    check(f"E: the Z ring rotates about the moved pivot (rot z {rz:.3f}, pivot stays "
          f"{(ob.matrix_world.translation - C['pivot']).length:.2e}, geometry turned {max(moved) / k():.2f} cm, P1)",
          abs(rz) > 0.05 and (ob.matrix_world.translation - C["pivot"]).length < 1e-7 and max(moved) > 0.05 * k())
    set_tool("builtin.scale")


@step
def s_scale_shot():
    shot("gui_step59_scale.png")
    # V: centre handle onto pCube2's vertex
    ob = ob1()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region, active_object=ob,
                                   selected_objects=[ob], object=ob):
        bpy.ops.allset.reset_pivot()
    ob.rotation_euler = (0, 0, 0)
    ob.location = (0, 0, 0)
    bpy.context.view_layer.update()
    set_tool("builtin.move")
    b = bpy.data.objects["pCube2"]
    C["verts2"] = [b.matrix_world @ v.co for v in b.data.vertices]
    # the pCube2 vertex nearest the camera: the dragged pCube1 must not cover it (Blender snaps to visible
    # elements only; with Maya's persp angle the nearest-to-pCube1 corner ended up behind pCube1)
    eye = region.data.view_matrix.inverted().translation
    C["target"] = min(C["verts2"], key=lambda p: (p - eye).length)
    C["p"] = screen(ob.matrix_world.translation)
    C["to"] = screen(C["target"]) + Vector((2, 2))
    hover(C["p"])


@step
def s_point_snap():
    ev('V', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))
    ev('LEFTMOUSE', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_point_snap_move():
    # moves in their own tick: the transform modal started on the press misses moves queued with it
    p, to = C["p"], C["to"]
    for i in range(1, STEPS + 1):
        q = p + (to - p) * (i / STEPS)
        ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y))


@step
def s_point_snap_release():
    release(C["to"])
    ev('V', 'RELEASE')


@step
def s_point_snap_done():
    got = ob1().matrix_world.translation
    hit = min(C["verts2"], key=lambda p: (p - got).length)
    check(f"V + centre handle: the pivot lands exactly on a pCube2 vertex ({tuple(round(v / k(), 3) for v in got)} cm, "
          f"aimed at {tuple(round(v / k(), 3) for v in C['target'])}, S4)", (got - hit).length < 1e-6)
    redraw()


run()
