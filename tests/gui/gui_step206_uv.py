"""In a real UI: a Maya pCube1 in the UV Editor. Cut/Sew > Auto Seams, Split, Create Shell (Grid) and
Modify > Cycle run from the menu map; the three Maya heads-up displays (UV Statistics bottom right, UV Position
bottom left, Isolated Selection while Ctrl+1 isolates) are drawn; shots of the UV Editor."""

import os
import sys
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def uv_area():
    live_refs = import_module(MODULE + ".live_refs")
    return live_refs.area(C["area"])


def override():
    a = uv_area()
    region = next(r for r in a.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(window=win(), screen=win().screen, area=a, region=region)


def run_item(path):
    with override():
        return bpy.ops.allset.menu_item(item=path)


def bm_uv():
    ob = bpy.data.objects[C["ob"]]
    bm = bmesh.from_edit_mesh(ob.data)
    return ob, bm, bm.loops.layers.uv.verify()


def select_uvs(verts=(), faces=()):
    compat = import_module(MODULE + ".compat")
    ob, bm, uv = bm_uv()
    bm.verts.ensure_lookup_table()
    for f in bm.faces:
        f.select = True
        for l in f.loops:
            compat.set_uv_vert_selected(l, uv, l.vert.index in verts or f.index in faces)
            compat.set_uv_edge_selected(l, uv, f.index in faces)
    bmesh.update_edit_mesh(ob.data)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    a, region = view3d()
    with bpy.context.temp_override(window=win(), screen=win().screen, area=a, region=region):
        bpy.ops.allset.create(kind='CUBE')
        ob = bpy.context.view_layer.objects.active
        bpy.ops.object.mode_set(mode='EDIT')
    C["ob"] = ob.name
    C["area"] = a.as_pointer()
    a.ui_type = 'UV'
    bpy.context.scene.tool_settings.use_uv_select_sync = False
    select_uvs()


@step
def s_auto_seams():
    with override():
        bpy.ops.image.view_all()
    res = run_item("UV Editor/Cut/Sew/Auto Seams")
    ob, bm, uv = bm_uv()
    seams = sum(1 for e in bm.edges if e.seam)
    check(f"Auto Seams runs from the menu ({res}); the factory cube's cross layout already unfolds: {seams} seams "
          f"(Maya: none)", isinstance(res, set) and seams == 0)


@step
def s_grid():
    select_uvs(verts=(0, 3))                     # front face corners (Maya pCube1.vtx[0], vtx[3])
    res = run_item("UV Editor/Cut/Sew/Create Shell (Grid)")
    ob, bm, uv = bm_uv()
    bm.faces.ensure_lookup_table()
    got = sorted((round(l[uv].uv.x, 4), round(l[uv].uv.y, 4)) for l in bm.faces[0].loops)
    check(f"Create Shell (Grid) ({res}): front face = 0-1 square {got}",
          got == [(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)])


@step
def s_cycle_split():
    select_uvs(faces=(1,))
    ob, bm, uv = bm_uv()
    bm.faces.ensure_lookup_table()
    before = [tuple(l[uv].uv) for l in bm.faces[1].loops]
    res = run_item("UV Editor/Modify/Cycle")
    ob, bm, uv = bm_uv()
    bm.faces.ensure_lookup_table()
    after = [tuple(l[uv].uv) for l in bm.faces[1].loops]
    check(f"Cycle ({res}) turns face 1's UVs one corner", sorted(before) == sorted(after) and before != after)
    select_uvs(verts=(4,))
    res = run_item("UV Editor/Cut/Sew/Split")
    check(f"Split runs from the menu ({res})", res == {'FINISHED'})


@step
def s_hud():
    select_uvs(faces=(0,))
    wm = bpy.context.window_manager
    check("the three Maya HUDs are on (factory)",
          wm.allset_uv_hud_statistics and wm.allset_uv_hud_position and wm.allset_uv_hud_isolate)
    hud = import_module(MODULE + ".ui.uv_hud")
    hud._cache["value"] = None
    redraw()


@step
def s_hud_drawn():
    hud = import_module(MODULE + ".ui.uv_hud")
    val = hud._cache["value"]
    check(f"the UV Editor drew the HUD: {val}", val is not None and "UV shells" in val[0] and val[1] == "U:  0.5 V:  0.5")
    redraw()


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step206_uv_hud.png"))
    with override():
        res = bpy.ops.allset.uv_isolate()
    check(f"Ctrl+1 isolate ({res})", bpy.context.window_manager.allset_uv_isolate)
    redraw()


@step
def s_shot_isolate():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step206_uv_isolate.png"))
    with override():
        bpy.ops.allset.uv_isolate()
    res = run_item("UV Editor/View/Heads-Up Display/UV Statistics")
    check(f"View > Heads-Up Display > UV Statistics toggles it off ({res})",
          not bpy.context.window_manager.allset_uv_hud_statistics)
    run_item("UV Editor/View/Heads-Up Display/UV Statistics")


run()
