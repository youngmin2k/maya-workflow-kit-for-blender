"""#304: in a real UI, a click (no drag) on a manipulator handle makes it the active handle, like Maya.

Maya Workflow Kit layout, a cube in the perspective view:
- Move tool: click the X arrow -> MMB drag anywhere moves along X only; click the centre -> MMB drag moves freely.
- Scale tool: click the Y handle -> MMB drag anywhere scales Y only.
- Rotate tool: click the Z ring -> it is drawn in the active colour #fdff88 and MMB drag anywhere rotates about Z
  only; click the view ring -> the active handle rotates about the view axis.
Each click leaves the cube as it was."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, scale, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
TMP = os.path.join(os.environ.get("TEMP", "."), "allset_pr304_click.png")
C = {}
MOVES = 8


def mod(name):
    return import_module(f"{MODULE}.{name}")


def cube():
    return bpy.data.objects["pCube1"]


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def set_tool(name):
    with override():
        bpy.ops.wm.tool_set_by_id(name=name)
    redraw()


def screen(world):
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, world)
    return Vector((region.x + p.x, region.y + p.y))


def px_world(at):
    """World length of one px at the depth of ``at`` (perspective view)."""
    _area, region = view3d()
    rv3d = region.data
    depth = -(rv3d.view_matrix @ at).z
    lens = view3d()[0].spaces.active.lens
    return depth * 72.0 / lens / max(region.width, region.height)


def arrow_px():
    m = mod("ui.manipulator")
    return m.ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0 * scale() * m.SIZE[0]


def along(axis, frac):
    """Screen point ``frac`` handle lengths out along world ``axis`` from the pivot."""
    c = cube().matrix_world.translation
    return screen(c + axis * frac * arrow_px() * px_world(c))


def ring_point(normal_axis):
    """A screen point on the front half of the Rotate ring about ``normal_axis``, as far as possible from the other
    rings, the view ring and the centre."""
    m = mod("ui.manipulator")
    c = cube().matrix_world.translation.copy()
    r = m.ROTATE_RING_R * arrow_px() * px_world(c)
    view_z = view3d()[1].data.view_rotation @ Vector((0, 0, 1))
    cs = screen(c)
    view_px = m.ROTATE_RING_R * m.VIEW_RING * arrow_px()

    def ring(axis):
        rot = Vector(axis).to_track_quat('Z', 'Y').to_matrix()
        pts = []
        for i in range(144):
            import math
            a = 2 * math.pi * i / 144
            w = c + rot @ Vector((math.cos(a), math.sin(a), 0)) * r
            if (w - c).dot(view_z) > 0.05 * r:
                pts.append(screen(w))
        return pts
    axes = {'X': (1, 0, 0), 'Y': (0, 1, 0), 'Z': (0, 0, 1)}
    others = [p for k, v in axes.items() if k != normal_axis for p in ring(v)]

    def clearance(p):
        d_rings = min((p - q).length for q in others)
        d_view = abs((p - cs).length - view_px)
        return min(d_rings, d_view)
    return max(ring(axes[normal_axis]), key=clearance)


def park():
    _area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + 40, y=region.y + 40)


def hover(p):
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x) + 1, y=int(p.y))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))


def handle(kind):
    return mod("operators.manip").HANDLES.get(kind)


def state():
    ob = cube()
    return (ob.location.copy(), Vector(ob.rotation_euler), ob.scale.copy())


def click(name, where, then=None):
    """Steps: hover the handle, press, release (no move in between), check the cube didn't change."""
    def s_hover():
        C[name] = where()
        C[name + "_before"] = state()
        hover(C[name])

    def s_press():
        p = C[name]
        ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y))

    def s_release():
        p = C[name]
        ev('LEFTMOUSE', 'RELEASE', x=int(p.x), y=int(p.y))

    def s_settle():
        pass

    def s_still():
        before, after = C[name + "_before"], state()
        same = all((a - b).length < 1e-5 for a, b in zip(before, after))
        check(f"a click on the {name} leaves the cube as it was", same)
        running = [op.bl_idname for op in win().modal_operators]
        check(f"... and no transform keeps running ({running})",
              not any(r.startswith("TRANSFORM") for r in running))
        if then is not None:
            then()

    for s in (s_hover, s_press, s_release, s_settle, s_still):
        step(s)


def mmb(name, dx=80, dy=-70):
    """Steps: MMB press far from the manipulator, moves, release (separate ticks for the nested transform)."""
    def s_press():
        C[name + "_before"] = state()
        c = screen(cube().matrix_world.translation)
        x, y = int(c.x) - 250, int(c.y) + 150
        C[name + "_at"] = (x, y)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        ev('MIDDLEMOUSE', 'PRESS', x=x, y=y)

    def s_move():
        x, y = C[name + "_at"]
        for i in range(1, MOVES + 1):
            ev('MOUSEMOVE', 'NOTHING', x=x + dx * i // MOVES, y=y + dy * i // MOVES)

    def s_release():
        x, y = C[name + "_at"]
        ev('MIDDLEMOUSE', 'RELEASE', x=x + dx, y=y + dy)

    def s_settle():
        pass

    for s in (s_press, s_move, s_release, s_settle):
        step(s)


def delta(name):
    before, after = C[name + "_before"], state()
    return tuple(a - b for a, b in zip(after, before))


def r3(v):
    return tuple(round(x, 3) for x in v)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    with override():
        bpy.ops.allset.create(kind='CUBE')
    ob = cube()
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    view3d()[1].data.view_distance /= 4.0     # the template camera shows the cube small
    set_tool("builtin.move")
    mod("operators.manip").HANDLES.clear()


@step
def s_redraw():
    redraw()      # the view matrix follows the view change after a redraw
    park()


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "pr304_move.png"))


# --- Move: click the X arrow, MMB along X; click the centre, MMB free ------------------------------------------

click("Move X arrow", lambda: along(Vector((1, 0, 0)), 0.7))


@step
def s_move_x_active():
    h = handle('TRANSLATE')
    check(f"a click on the Move X arrow makes it the active handle ({h})",
          h is not None and tuple(h["constraint_axis"]) == (True, False, False))


mmb("move_x")


@step
def s_move_x_check():
    d_loc, d_rot, d_scale = delta("move_x")
    check(f"MMB drag anywhere then moves along X only ({r3(d_loc)})",
          abs(d_loc.x) > 0.005 and abs(d_loc.y) < 1e-6 and abs(d_loc.z) < 1e-6)
    park()


click("Move centre", lambda: screen(cube().matrix_world.translation))


@step
def s_centre_free():
    h = handle('TRANSLATE')
    check(f"a click on the Move centre frees the active handle ({h})", 'TRANSLATE' in mod("operators.manip").HANDLES
          and h is None)


mmb("move_free")


@step
def s_move_free_check():
    d_loc = delta("move_free")[0]
    check(f"MMB drag then moves freely ({r3(d_loc)})",
          d_loc.length > 0.005 and sum(abs(v) > 1e-4 for v in d_loc) >= 2)
    set_tool("builtin.scale")
    park()


@step
def s_scale_redraw():
    redraw()


# --- Scale: click the Y handle, MMB scales Y only ----------------------------------------------------------------

click("Scale Y handle", lambda: along(Vector((0, 1, 0)), mod("ui.manipulator").CUBE_AT))


@step
def s_scale_y_active():
    h = handle('RESIZE')
    check(f"a click on the Scale Y handle makes it the active handle ({h})",
          h is not None and tuple(h["constraint_axis"]) == (False, True, False))


mmb("scale_y", dx=90, dy=60)


@step
def s_scale_y_check():
    d_scale = delta("scale_y")[2]
    check(f"MMB drag anywhere then scales Y only ({r3(d_scale)})",
          abs(d_scale.y) > 0.01 and abs(d_scale.x) < 1e-5 and abs(d_scale.z) < 1e-5)
    set_tool("builtin.rotate")
    park()


@step
def s_rotate_redraw():
    redraw()


# --- Rotate: click the Z ring (drawn active), MMB rotates about Z; click the view ring ---------------------------

def _after_z_click():
    park()
    redraw()


click("Rotate Z ring", lambda: ring_point('Z'), then=_after_z_click)


@step
def s_rotate_z_active():
    h = handle('ROTATE')
    check(f"a click on the Rotate Z ring makes it the active handle ({h})",
          h is not None and tuple(h["constraint_axis"]) == (False, False, True) and h.get("orient_axis") == 'Z')
    path = os.path.join(SHOTS, "pr304_rotate_z_active.png") if SHOTS else TMP
    screenshot(path)
    img = bpy.data.images.load(path)
    w, hgt = img.size
    px = list(img.pixels)
    bpy.data.images.remove(img)
    p = C["Rotate Z ring"]
    found = []
    for yy in range(int(p.y) - 3, int(p.y) + 4):
        for xx in range(int(p.x) - 3, int(p.x) + 4):
            if 0 <= xx < w and 0 <= yy < hgt:
                i = (yy * w + xx) * 4
                found.append(tuple(px[i:i + 3]))
    # #fdff88: red and green high, blue clearly above the hover yellow's 0 and below red / green
    yellow = [c for c in found if c[0] > 0.75 and c[1] > 0.75 and 0.2 < c[2] < c[0] - 0.15]
    blue = [c for c in found if c[2] > 0.6 and c[0] < 0.35 and c[1] < 0.35]
    check(f"the active Z ring is drawn in the active colour, not its axis blue "
          f"({len(yellow)} active / {len(blue)} blue px)", yellow and not blue)


mmb("rotate_z")


@step
def s_rotate_z_check():
    d_rot = delta("rotate_z")[1]
    check(f"MMB drag anywhere then rotates about Z only ({r3(d_rot)})",
          abs(d_rot.z) > 0.05 and abs(d_rot.x) < 1e-4 and abs(d_rot.y) < 1e-4)
    park()


def _view_ring():
    m = mod("ui.manipulator")
    cs = screen(cube().matrix_world.translation)
    r = m.ROTATE_RING_R * m.VIEW_RING * arrow_px()
    return cs + Vector((-0.7071, 0.7071)) * r


click("Rotate view ring", _view_ring)


@step
def s_view_active():
    h = handle('ROTATE')
    check(f"a click on the Rotate view ring makes it the active handle, about the view axis ({h})",
          h is not None and not any(h["constraint_axis"]) and h.get("orient_type") == 'VIEW')


run()
