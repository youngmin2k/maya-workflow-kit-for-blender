"""In a real UI (#283): = / - make the Rotate manipulator bigger and smaller like Move / Scale.

Maya Workflow Kit layout, a cube, Rotate tool, front view: the ring size is read from the screen (outermost drawn pixel to
the right of the centre = the view ring), = twice grows them, - twice brings them back. A drag on the Y ring (the
full circle facing the front view) rotates about Y only and is remembered as the active handle; a drag inside the
trackball rotates freely. From above, the Z ring is drawn on its front half only."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, scale, load_maya_layout, tap  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
TMP = os.path.join(os.environ.get("TEMP", "."), "allset_issue283_rotate.png")
C = {}
MOVES = 8


def mod(name):
    return import_module(f"{MODULE}.{name}")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def cube():
    return bpy.data.objects["pCube1"]


def centre_px():
    area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, cube().matrix_world.translation)
    return int(region.x + p.x), int(region.y + p.y)


def park():
    """Mouse in a corner of the viewport: no handle highlighted."""
    _area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + 40, y=region.y + 40)


def grab(name):
    """Screenshot (kept with --shots) as a flat RGB list + width."""
    path = os.path.join(SHOTS, name) if SHOTS else TMP
    screenshot(path)
    img = bpy.data.images.load(path)
    w = img.size[0]
    px = list(img.pixels)
    bpy.data.images.remove(img)
    return px, w


def outer_radius(name):
    """Distance from the centre to the outermost drawn pixel on the row to the right (the view ring)."""
    px, w = grab(name)
    cx, cy = C["c"]
    _area, region = view3d()
    end = min(region.x + region.width - 60, cx + 600)

    def col(x):
        i = (cy * w + x) * 4
        return px[i:i + 3]
    bg = col(end)
    hits = [x - cx for x in range(cx + 4, end) if max(abs(a - b) for a, b in zip(col(x), bg)) > 0.15]
    return max(hits) if hits else 0


def is_blue(px, w, x, y, r=3):
    for yy in range(y - r, y + r + 1):
        for xx in range(x - r, x + r + 1):
            i = (yy * w + xx) * 4
            red, green, blue = px[i:i + 3]
            if blue > 0.6 and red < 0.35 and green < 0.35:
                return True
    return False


def tool():
    return bpy.context.workspace.tools.from_space_view3d_mode('OBJECT', create=False)


def last_op():
    ops = bpy.context.window_manager.operators
    return ops[-1] if len(ops) else None


def ring_px(view=False):
    """Expected radius of the axis rings (or the view ring): 75 px x UI scale at size 1, times the kit size."""
    m = mod("ui.manipulator")
    return 75.0 * scale() * (1.2 if view else 1.0) * m.SIZE[0]


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.wm.tool_set_by_id(name="builtin.rotate")
        bpy.ops.view3d.view_axis(type='FRONT')
    redraw()


@step
def s_measure():
    C["c"] = centre_px()
    park()
    redraw()


@step
def s_size1():
    t = tool()
    check(f"Rotate tool draws the kit manipulator ({t.idname}: {t.widget})",
          t.idname == "builtin.rotate" and t.widget == mod("ui.manipulator").GROUP)
    C["r0"] = outer_radius("issue283_rotate_size1.png")
    want = ring_px(view=True)
    check(f"view ring radius at size 1 ({C['r0']} px, the size Blender's rotate gizmo has: {want:.1f})",
          abs(C["r0"] - want) <= 4)
    C["size0"] = mod("ui.manipulator").SIZE[0]
    ev('MOUSEMOVE', 'NOTHING', x=C["c"][0] + 300, y=C["c"][1] + 200)
    tap('EQUAL')
    tap('EQUAL')


@step
def s_park_big():
    park()
    redraw()


@step
def s_bigger():
    size = mod("ui.manipulator").SIZE[0]
    r = outer_radius("issue283_rotate_bigger.png")
    check(f"= twice makes the Rotate manipulator bigger ({C['r0']} -> {r} px, size {C['size0']:.2f} -> {size:.2f})",
          size > C["size0"] and r > C["r0"] * 1.3)
    check(f"... by the size factor ({r} px vs {C['r0'] * size / C['size0']:.1f})",
          abs(r - C["r0"] * size / C["size0"]) <= 5)
    C["big"] = r
    ev('MOUSEMOVE', 'NOTHING', x=C["c"][0] + 300, y=C["c"][1] + 200)
    tap('MINUS')
    tap('MINUS')


@step
def s_park_small():
    park()
    redraw()


@step
def s_smaller():
    r = outer_radius("issue283_rotate_smaller.png")
    check(f"- twice makes it smaller again ({C['big']} -> {r} px, back near {C['r0']})",
          r < C["big"] and abs(r - C["r0"]) <= 3)
    # the Y ring: the full circle facing the front view; grab it up-right of the centre (off the edge-on X / Z
    # rings) and drag along it
    ring = ring_px()
    C["rot0"] = cube().rotation_euler.copy()
    C["drag"] = (int(C["c"][0] + ring * 0.7071), int(C["c"][1] + ring * 0.7071), -0.7071, 0.7071, 70)
    x, y = C["drag"][:2]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


def press_drag():
    x, y, dx, dy, dist = C["drag"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    for i in range(1, MOVES + 1):
        f = dist * i / MOVES
        ev('MOUSEMOVE', 'NOTHING', x=int(x + dx * f), y=int(y + dy * f))


def release_drag():
    x, y, dx, dy, dist = C["drag"]
    ev('LEFTMOUSE', 'RELEASE', x=int(x + dx * dist), y=int(y + dy * dist))


@step
def s_ring_press():
    press_drag()


@step
def s_ring_release():
    release_drag()


@step
def s_ring_done():
    d = Vector(cube().rotation_euler) - Vector(C["rot0"])
    op = last_op()
    check(f"a drag on the Y ring rotates about Y only ({tuple(round(v, 3) for v in d)})",
          abs(d.y) > 0.05 and abs(d.x) < 1e-4 and abs(d.z) < 1e-4)
    check(f"... with Blender's rotate on the Y axis ({op.bl_idname if op else None})",
          op is not None and op.bl_idname == "TRANSFORM_OT_rotate"
          and tuple(op.properties.constraint_axis) == (False, True, False))
    handle = mod("operators.manip").HANDLES.get('ROTATE')
    check(f"the Y ring is remembered as the active handle ({handle})",
          handle is not None and tuple(handle["constraint_axis"]) == (False, True, False))
    cube().rotation_euler = (0.0, 0.0, 0.0)
    # inside the trackball, off every ring: a free rotation
    C["rot0"] = cube().rotation_euler.copy()
    C["drag"] = (C["c"][0] + 20, C["c"][1] + 25, 1, 0, 50)
    park()


@step
def s_ball_hover():
    x, y = C["drag"][:2]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


@step
def s_ball_press():
    press_drag()


@step
def s_ball_release():
    release_drag()


@step
def s_ball_done():
    d = Vector(cube().rotation_euler) - Vector(C["rot0"])
    op = last_op()
    check(f"a drag inside the trackball rotates freely ({op.bl_idname if op else None}, "
          f"{tuple(round(v, 3) for v in d)})",
          op is not None and op.bl_idname == "TRANSFORM_OT_trackball" and d.length > 0.05)
    cube().rotation_euler = (0.0, 0.0, 0.0)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.view3d.view_orbit(angle=0.6, type='ORBITUP')
    park()
    redraw()


@step
def s_from_above():
    pass


@step
def s_front_half():
    # Z ring seen from above the front: the near side (-Y) is drawn, the far side (+Y) is clipped
    area, region = view3d()
    rv3d = region.data
    o = cube().matrix_world.translation
    c = location_3d_to_region_2d(region, rv3d, o)
    right = rv3d.view_rotation @ Vector((1, 0, 0))
    px_world = (location_3d_to_region_2d(region, rv3d, o + right) - c).length
    radius = ring_px() / px_world
    near = location_3d_to_region_2d(region, rv3d, o + Vector((0, -radius, 0)))
    far = location_3d_to_region_2d(region, rv3d, o + Vector((0, radius, 0)))
    px, w = grab("issue283_rotate_above.png")
    at = (lambda p: (int(region.x + p.x), int(region.y + p.y)))
    check("the Z ring's near half is drawn", is_blue(px, w, *at(near)))
    check("the Z ring's far half is not drawn", not is_blue(px, w, *at(far)))
    C["near"], C["far"] = at(near), at(far)
    C["rot0"] = cube().rotation_euler.copy()
    C["drag"] = (C["far"][0], C["far"][1], 1, 0, 60)
    ev('MOUSEMOVE', 'NOTHING', x=C["far"][0], y=C["far"][1])
    ev('MOUSEMOVE', 'NOTHING', x=C["far"][0] + 1, y=C["far"][1])


@step
def s_far_press():
    press_drag()


@step
def s_far_release():
    release_drag()


@step
def s_far_done():
    op = last_op()
    z_ring = (op is not None and op.bl_idname == "TRANSFORM_OT_rotate"
              and tuple(op.properties.constraint_axis) == (False, False, True))
    check(f"a press on the Z ring's hidden far half doesn't grab it ({op.bl_idname if op else None})", not z_ring)
    cube().rotation_euler = (0.0, 0.0, 0.0)
    C["drag"] = (C["near"][0], C["near"][1], 1, 0, 60)
    ev('MOUSEMOVE', 'NOTHING', x=C["near"][0], y=C["near"][1])
    ev('MOUSEMOVE', 'NOTHING', x=C["near"][0] + 1, y=C["near"][1])


@step
def s_near_press():
    press_drag()


@step
def s_near_release():
    release_drag()


@step
def s_near_done():
    op = last_op()
    d = Vector(cube().rotation_euler)
    check(f"a drag on the Z ring's near half rotates about Z ({op.bl_idname if op else None}, "
          f"{tuple(round(v, 3) for v in d)})",
          op is not None and op.bl_idname == "TRANSFORM_OT_rotate"
          and tuple(op.properties.constraint_axis) == (False, False, True) and abs(d.z) > 0.05)


run()
