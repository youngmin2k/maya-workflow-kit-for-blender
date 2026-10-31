"""In a real UI: a pPlane whose UVs are shrunk and turned, UV Editor > Modify > Map Border (Maya untangleUV
-mapBorder square) puts the border UVs on the 0-1 square; shot of the UV Editor afterwards. Also Select > Texture
Borders and Back-Facing run from the menu map without errors."""

import math
import os
import sys
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def uv_area():
    from importlib import import_module as im
    live_refs = im(MODULE + ".live_refs")
    return live_refs.area(C["area"])


def override():
    a = uv_area()
    region = next(r for r in a.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(window=win(), screen=win().screen, area=a, region=region)


def run_item(path):
    """Run a UV Editor menu item the way the menu does (marking/modal.run_action through allset.menu_item)."""
    with override():
        return bpy.ops.allset.menu_item(item=path)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    a, region = view3d()
    with bpy.context.temp_override(window=win(), screen=win().screen, area=a, region=region):
        bpy.ops.allset.create(kind='PLANE')
        ob = bpy.context.view_layer.objects.active
        bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.verify()
    c, s = math.cos(math.radians(20)), math.sin(math.radians(20))
    for f in bm.faces:
        f.select = True
        for loop in f.loops:
            u, v = loop[uv].uv
            u, v = (u - 0.5) * 0.4, (v - 0.5) * 0.4
            loop[uv].uv = (0.4 + u * c - v * s, 0.45 + u * s + v * c)
    bm.select_flush(True)
    bmesh.update_edit_mesh(ob.data)
    C["ob"] = ob.name
    C["area"] = a.as_pointer()
    a.ui_type = 'UV'


@step
def s_map_border():
    check(f"the viewport became a UV Editor ({uv_area().type})", uv_area().type == 'IMAGE_EDITOR')
    with override():
        bpy.ops.image.view_all()
        bpy.ops.uv.select_all(action='SELECT')    # UV Sync Selection is off: the UVs are the selection (Maya UVs)
    res = run_item("UV Editor/Modify/Map Border")
    ob = bpy.data.objects[C["ob"]]
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.verify()
    border = {loop.vert.index: tuple(loop[uv].uv) for e in bm.edges if e.is_boundary for loop in e.link_loops}
    on_square = [p for p in border.values()
                 if min(abs(p[0]), abs(p[0] - 1), abs(p[1]), abs(p[1] - 1)) < 1e-4]
    corners = {(round(p[0], 4), round(p[1], 4)) for p in border.values()} & {(0, 0), (1, 0), (1, 1), (0, 1)}
    check(f"Map Border ({res}): every border UV on the 0-1 square ({len(on_square)} / {len(border)}), "
          f"corners {sorted(corners)}", border and len(on_square) == len(border) and len(corners) == 4)
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step178_map_border.png"))
    for path in ("UV Editor/Select/Texture Borders", "UV Editor/Select/Back-Facing", "UV Editor/Modify/Match Grid"):
        try:
            res = run_item(path)
        except RuntimeError as ex:
            res = f"error {ex}"
        check(f"{path} runs from the menu ({res})", isinstance(res, set))


run()
