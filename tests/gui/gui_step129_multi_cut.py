"""In a real UI (GitHub #27): Ctrl+Shift+X = the kit Multi-Cut tool; click an edge, hover the opposite edge
(live preview), click it, Backspace removes it, click again, RMB = a new edge across the face (+2 v / +3 e / +1 f,
Maya polySplit) and the tool stays; Ctrl hover = loop preview, Ctrl+click = an edge loop; Shift = Snap Step;
Esc with no points leaves the tool."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras import view3d_utils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mc():
    return import_module(MODULE + ".operators.multi_cut")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def cube():
    return bpy.data.objects["Cube"]


def bm():
    b = bmesh.from_edit_mesh(cube().data)
    for seq in (b.verts, b.edges, b.faces):
        seq.ensure_lookup_table()
    return b


def counts():
    b = bm()
    return len(b.verts), len(b.edges), len(b.faces)


def depth(co):
    area, _region = view3d()
    return -(area.spaces.active.region_3d.view_matrix @ (cube().matrix_world @ co)).z


def to_window(co):
    area, region = view3d()
    p = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, cube().matrix_world @ co)
    return region.x + round(p.x), region.y + round(p.y)


def tool_id():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        t = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
    return t.idname if t else None


def front_edges():
    """Two opposite edges of the face nearest to the camera: [(end a, end b), (end a, end b)]."""
    b = bm()
    face = min(b.faces, key=lambda f: sum(depth(v.co) for v in f.verts))
    e0 = face.edges[0]
    e1 = next(e for e in face.edges if not set(e.verts) & set(e0.verts))
    return [(e.verts[0].co.copy(), e.verts[1].co.copy()) for e in (e0, e1)]


def at(k, t):
    a, b = C["edges"][k]
    return to_window(a.lerp(b, t))


def click(x, y, **mods):
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y, **mods)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, **mods)


def release(**mods):
    ev('LEFTMOUSE', 'RELEASE', **mods)


def undo():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


def on_edge_ts(a, b):
    out = []
    for v in bm().verts:
        if abs((v.co - a).length + (v.co - b).length - (a - b).length) < 1e-4 and \
                (v.co - a).length > 1e-4 and (v.co - b).length > 1e-4:
            out.append(round((v.co - a).length / (b - a).length, 4))
    return sorted(out)


@step
def s_setup():
    C["x"], C["y"] = setup()
    check("Maya keymap active", sys.modules["sim"].maya_keys())
    bpy.context.view_layer.objects.active = cube()
    cube().select_set(True)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('X', 'PRESS', ctrl=True, shift=True)
    ev('X', 'RELEASE', ctrl=True, shift=True)


@step
def s_tool():
    check(f"Ctrl+Shift+X = edit mode + the kit Multi-Cut tool ({bpy.context.mode}, {tool_id()})",
          bpy.context.mode == 'EDIT_MESH' and tool_id() == "allset.multi_cut_tool")
    C["edges"] = front_edges()
    C["n0"] = counts()
    click(*at(0, 0.3))


@step
def s_first_release():
    release()


@step
def s_hover():
    pts = mc().STATE["points"]
    check(f"click on an edge = one cut point at ~30 % ({pts})",
          len(pts) == 1 and pts[0][0] == 'EDGE' and abs(min(pts[0][2], 1 - pts[0][2]) - 0.3) < 0.03)
    ev('MOUSEMOVE', 'NOTHING', x=at(1, 0.5)[0], y=at(1, 0.5)[1])


@step
def s_second():
    hov = mc().STATE["hover"]
    check(f"hovering the opposite edge = a live preview point there ({hov})",
          hov is not None and hov[1][0] == 'EDGE' and mc().STATE["hover_ok"])
    shot("gui_step129_preview.png")
    click(*at(1, 0.5))


@step
def s_second_release():
    release()


@step
def s_backspace():
    check(f"second click = two points ({len(mc().STATE['points'])})", len(mc().STATE["points"]) == 2)
    tap('BACK_SPACE')


@step
def s_after_backspace():
    check(f"Backspace removes the last point ({len(mc().STATE['points'])} left)", len(mc().STATE["points"]) == 1)
    click(*at(1, 0.5))


@step
def s_again_release():
    release()


@step
def s_rmb():
    ev('RIGHTMOUSE', 'PRESS')
    ev('RIGHTMOUSE', 'RELEASE')


@step
def s_cut():
    n0, n = C["n0"], counts()
    check(f"RMB completes: a new edge across the face ({n0} -> {n}, Maya +2 v / +3 e / +1 f)",
          n == (n0[0] + 2, n0[1] + 3, n0[2] + 1))
    check(f"the tool stays after the cut ({tool_id()})", tool_id() == "allset.multi_cut_tool")
    check("no points left", not mc().STATE["points"])
    shot("gui_step129_cut.png")
    undo()


@step
def s_ctrl_hover():
    if bpy.context.mode != 'EDIT_MESH':
        check(f"Ctrl+Z after the cut stays in edit mode ({bpy.context.mode})", False)
        return
    check(f"Ctrl+Z undoes the whole cut in one step ({counts()})", counts() == C["n0"])
    x, y = at(0, 0.3)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y + 1, ctrl=True)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y, ctrl=True)


@step
def s_ctrl_click():
    lp = mc().STATE["loop"]
    check(f"Ctrl hover over an edge = edge loop preview ({lp})", lp is not None)
    shot("gui_step129_loop_preview.png")
    click(*at(0, 0.3), ctrl=True)


@step
def s_ctrl_release():
    release(ctrl=True)


@step
def s_loop():
    n0, n = C["n0"], counts()
    ts = on_edge_ts(*C["edges"][0])
    check(f"Ctrl+click = an edge loop around the cube ({n0} -> {n}, t {ts})",
          n[0] == n0[0] + 4 and len(ts) == 1 and abs(min(ts[0], 1 - ts[0]) - 0.3) < 0.03)
    undo()


@step
def s_shift():
    bpy.context.scene.allset_mesh_tools.snap_step = 25
    click(*at(0, 0.33), shift=True)


@step
def s_shift_release():
    release(shift=True)


@step
def s_shift_second():
    click(*at(1, 0.5))


@step
def s_shift_second_release():
    release()


@step
def s_enter():
    tap('RET')


@step
def s_shifted():
    ts = on_edge_ts(*C["edges"][0])
    check(f"Shift snaps the point to the 25 % Snap Step ({ts}), Enter completes", ts in ([0.25], [0.75]))
    bpy.context.scene.allset_mesh_tools.snap_step = 10
    undo()


@step
def s_esc():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    tap('ESC')


@step
def s_end():
    check(f"Esc with no points leaves Multi-Cut for Select ({tool_id()})",
          tool_id() is not None and tool_id().startswith("builtin.select"))


run()
