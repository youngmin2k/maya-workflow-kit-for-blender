"""In a real UI: UV > 3D Cut and Sew UV Tool (menu) = edge mode + the tool; a drag around the cube's top face
cuts it into its own UV shell (only those 4 edges), Ctrl+drag sews it back, Shift+drag selects edges and x cuts
them; screenshots of the borders."""

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


def mod(name):
    return import_module(MODULE + name)


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def ob():
    return bpy.data.objects["Cube"]


def tool_id():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        t = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
    return t.idname if t else None


def shells():
    bm = bmesh.from_edit_mesh(ob().data)
    return len(mod(".operators.uv_tools").islands(bm, bm.loops.layers.uv.verify()))


def seams():
    bm = bmesh.from_edit_mesh(ob().data)
    return sorted(e.index for e in bm.edges if e.seam)


def top_path():
    """Screen points: the middle of each top edge in turn, going round the top face (closing at the first)."""
    bm = bmesh.from_edit_mesh(ob().data)
    top = max(bm.faces, key=lambda f: f.calc_center_median().z)
    area, region = view3d()
    rv3d = area.spaces.active.region_3d
    mw = ob().matrix_world
    verts = [mw @ v.co for v in top.verts]
    pts = []
    for k in range(len(verts) + 1):
        a, b = verts[k % len(verts)], verts[(k + 1) % len(verts)]
        for t in (0.3, 0.5, 0.7):
            p = view3d_utils.location_3d_to_region_2d(region, rv3d, a + (b - a) * t)
            pts.append((region.x + int(p.x), region.y + int(p.y)))
    C["top_edges"] = sorted(e.index for e in top.edges)
    return pts


def stroke(name, **mods):
    """Press, one move per path point (separate ticks), release."""
    def press():
        C["path"] = top_path()
        x, y = C["path"][0]
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        ev('LEFTMOUSE', 'PRESS', x=x, y=y, **mods)
    step(press)
    for i in range(1, 15):
        def move(i=i):
            if i < len(C["path"]):
                x, y = C["path"][i]
                ev('MOUSEMOVE', 'NOTHING', x=x, y=y, **mods)
        step(move)

    def release():
        x, y = C["path"][-1]
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y, **mods)
    step(release)


@step
def s_setup():
    C["mid"] = setup()
    bpy.ops.allset.keymap_activate()
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob().select_set(True)
    bpy.context.view_layer.objects.active = ob()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        C["run"] = mod(".marking.modal").run_action(bpy.context, mod(".ui.menu_map").MAP["UV/3D Cut and Sew UV Tool"], False)


@step
def s_tool():
    check(f"UV > 3D Cut and Sew UV Tool: edit mode, edge mode, the tool ({bpy.context.mode}, "
          f"{tuple(bpy.context.scene.tool_settings.mesh_select_mode)}, {tool_id()})",
          bpy.context.mode == 'EDIT_MESH' and tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (False, True, False)
          and tool_id() == "allset.cut_sew_tool")
    C["shells0"] = shells()
    bpy.ops.mesh.select_all(action='DESELECT')


stroke("cut")


@step
def s_cut_check():
    check(f"drag round the top face cuts it off: shells {C['shells0']} -> {shells()}", shells() == C["shells0"] + 1)
    check(f"only the 4 top edges became seams ({seams()} vs {C['top_edges']})", seams() == C["top_edges"])
    x, y = C["mid"]
    ev('MOUSEMOVE', 'NOTHING', x=x + 5, y=y + 5)


@step
def s_cut_shot():
    shot("gui_step79_cut.png")


stroke("sew", ctrl=True)


@step
def s_sew_check():
    check(f"Ctrl+drag sews it back: shells {shells()}, seams {seams()}", shells() == C["shells0"] and not seams())


stroke("select", shift=True)


@step
def s_select_check():
    bm = bmesh.from_edit_mesh(ob().data)
    sel = sorted(e.index for e in bm.edges if e.select)
    check(f"Shift+drag selects the edges without cutting ({sel}, shells {shells()})",
          sel == C["top_edges"] and shells() == C["shells0"])
    x, y = C["mid"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    tap('X')


@step
def s_x_check():
    check(f"x cuts the selected edges (shells {shells()})", shells() == C["shells0"] + 1)
    shot("gui_step79_x.png")


run()
