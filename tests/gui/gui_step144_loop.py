"""LOOP lane in a real UI (GitHub #31): Mesh Tools > Insert Edge Loop = edit mode + the kit tool, one
click on a cube edge = a loop right at that height (no second click), Ctrl+Z takes it back, press-drag = the loop
follows the mouse; Offset Edge Loop = a click on that loop = two loops (offset 0.5, relative to each side
edge), a drag sets the offset; Slide Edge = middle-drag slides the selected loop along the cube's sides."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
TOL = 0.04          # world units: a click lands within a pixel or two of the projected point


def el():
    return import_module(MODULE + ".operators.edge_loops")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def menu(path):
    # undo=True: a menu button calls its operator at undo depth 0 like this
    with override():
        return bpy.ops.allset.menu_item('EXEC_DEFAULT', True, item=path)


def tool_id():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        t = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
    return t.idname if t else None


def to_window(w):
    area, region = view3d()
    p = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, Vector(w))
    return region.x + round(p.x), region.y + round(p.y)


def cube():
    return bpy.data.objects["Cube"]


def verts():
    b = bmesh.from_edit_mesh(cube().data)
    return [cube().matrix_world @ v.co for v in b.verts]


def zs():
    return sorted({round(v.z, 2) for v in verts()})


def loop_zs():
    """Heights of the horizontal loops between the cube's top and bottom."""
    return sorted({round(v.z, 3) for v in verts() if abs(abs(v.z) - 1.0) > 1e-3})


def press(w, button='LEFTMOUSE'):
    x, y = to_window(w)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev(button, 'PRESS', x=x, y=y)
    C["press"] = (x, y)


def move_to(w):
    x, y = to_window(w)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


def release(button='LEFTMOUSE'):
    ev(button, 'RELEASE')


EDGE = (1.0, -1.0)          # the cube's front-right vertical edge (x = 1, y = -1), seen in the factory view


@step
def s_setup():
    C["x"], C["y"] = setup()
    check("Maya keymap active", sys.modules["sim"].maya_keys())
    area, _r = view3d()
    rv3d = area.spaces.active.region_3d
    rv3d.view_location = (0.0, 0.0, 0.0)
    rv3d.view_distance = 7.0
    with override():
        bpy.ops.object.select_all(action='DESELECT')
    cube().select_set(True)
    bpy.context.view_layer.objects.active = cube()
    menu("Mesh Tools/Insert Edge Loop")


@step
def s_insert_click():
    check(f"Insert Edge Loop = edit mode + the kit tool ({bpy.context.mode}, {tool_id()})",
          bpy.context.mode == 'EDIT_MESH' and tool_id() == el().INSERT_TOOL)
    with override():
        # the menu item is its own undo step (#88): Ctrl+Z below undoes only the loop
        bpy.ops.mesh.select_all('EXEC_DEFAULT', True, action='DESELECT')
    press((*EDGE, 0.4))


@step
def s_insert_release():
    release()


@step
def s_inserted():
    n = len(verts())
    got = loop_zs()
    check(f"one click = a loop through the ring, right at the click (z 0.4): {n} verts, loops at {got}",
          n == 12 and len(got) == 1 and abs(got[0] - 0.4) < TOL)
    b = bmesh.from_edit_mesh(cube().data)
    check("the new loop is selected (4 edges)", sum(e.select for e in b.edges) == 4)
    shot("gui_step144_loop_insert_click.png")
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undo():
    check(f"Ctrl+Z = one undo step back to the cube ({len(verts())} verts)", len(verts()) == 8)
    check(f"#88 Ctrl+Z keeps component mode and the tool ({bpy.context.mode}, {tool_id()})",
          bpy.context.mode == 'EDIT_MESH' and tool_id() == el().INSERT_TOOL)
    press((*EDGE, 0.4))


@step
def s_drag_move():
    move_to((*EDGE, -0.3))


@step
def s_drag_release():
    got = loop_zs()
    check(f"while the button is down the loop follows the mouse (z {got})",
          len(got) == 1 and abs(got[0] + 0.3) < TOL)
    shot("gui_step144_loop_insert_drag.png")
    release()


@step
def s_dragged():
    got = loop_zs()
    C["z"] = got[0] if got else None
    check(f"release keeps the slid loop at z -0.3 ({got})", len(got) == 1 and abs(got[0] + 0.3) < TOL)
    menu("Mesh Tools/Offset Edge Loop")


@step
def s_offset_click():
    check(f"Offset Edge Loop = the kit tool ({tool_id()})", tool_id() == el().OFFSET_TOOL)
    press((1.0, 0.0, C["z"]))           # the middle of the new loop's edge on the x = 1 side


@step
def s_offset_release():
    release()


@step
def s_offset_clicked():
    z = C["z"]
    got = loop_zs()
    above, below = z + 0.5 * (1.0 - z), z - 0.5 * (z + 1.0)        # Maya relative: half of each side edge
    check(f"a click = loops on both sides at offset 0.5 ({got}, want {round(below, 3)} / {round(z, 3)} / "
          f"{round(above, 3)})", len(got) == 3 and abs(got[0] - below) < 2e-3 and abs(got[2] - above) < 2e-3
          and len(verts()) == 20)
    shot("gui_step144_loop_offset_click.png")
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_offset_drag_press():
    check(f"Ctrl+Z takes the offset loops back ({len(verts())})", len(verts()) == 12)
    press((1.0, 0.0, C["z"]))


@step
def s_offset_drag_move():
    x, y = C["press"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y + 12)


@step
def s_offset_drag_release():
    release()


@step
def s_offset_dragged():
    z = C["z"]
    got = loop_zs()
    ok = len(got) == 3
    if ok:
        o_up = (got[2] - z) / (1.0 - z)
        o_down = (z - got[0]) / (z + 1.0)
        ok = abs(o_up - o_down) < 2e-3 and 0.0 < o_up < 0.5
        C["offset"] = o_up
    check(f"a short drag = a smaller offset, the same fraction of both side edges ({got})", ok)
    shot("gui_step144_loop_offset_drag.png")
    b = bmesh.from_edit_mesh(cube().data)        # select the middle loop (the one inserted first)
    for e in b.edges:
        e.select = False
    zs = {round(v.co.z, 6) for v in b.verts}
    z = min(zs, key=lambda h: abs(h - z))       # the click lands a hair apart per version (5.2.3: -0.2962)
    C["z"] = z
    for v in b.verts:
        v.select = abs(v.co.z - z) < 1e-4
    for e in b.edges:
        e.select = all(v.select for v in e.verts)
    b.select_flush_mode()
    bmesh.update_edit_mesh(cube().data)
    menu("Mesh Tools/Slide Edge")


@step
def s_slide_press():
    check(f"Slide Edge = the kit tool ({tool_id()})", tool_id() == el().SLIDE_TOOL)
    bpy.context.scene.allset_loop_tools.slide_snap = False      # a free slide (snapping: test_step144_loop)
    press((1.0, -1.0, C["z"]), button='MIDDLEMOUSE')


@step
def s_slide_move():
    x, y = C["press"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y + 6)


@step
def s_slide_release():
    shot("gui_step144_loop_slide_drag.png")
    release('MIDDLEMOUSE')


@step
def s_slid():
    z = C["z"]
    b = bmesh.from_edit_mesh(cube().data)
    sel = [cube().matrix_world @ v.co for v in b.verts if v.select]
    heights = sorted({round(v.z, 4) for v in sel})
    check(f"middle-drag up slides the selected loop up as one piece ({heights}, was {round(z, 4)})",
          len(sel) == 4 and len(heights) == 1 and heights[0] > z + 0.01)
    check("the slid vertices stay on the cube's sides", all(abs(abs(v.x) - 1) < 1e-4 or abs(abs(v.y) - 1) < 1e-4
                                                         for v in sel))
    shot("gui_step144_loop_slid.png")
    bpy.context.scene.allset_loop_tools.property_unset("slide_snap")


run()
