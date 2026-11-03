"""UV interaction like Maya (#264): after F12 (UV) a click on a UV in the UV Editor shows that UV's vertex as
selected in the 3D View and the other vertices as unselected (the mesh itself keeps every face selected so the UV
Editor shows all UVs). In the UV Editor the UV / face under the mouse is pre-selected (drawn red) before a
click. Shots: ALLSET_GUI_SHOTS."""

import os
import sys
import tempfile
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, screenshot, load_maya_layout, view3d, win, tap  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
S = {}


def ob():
    return bpy.data.objects[S["name"]]


def ctx():
    area, r = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=r)


def uv_win():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == 'IMAGE_EDITOR' and a.ui_type == 'UV':
                return w, a, next(r for r in a.regions if r.type == 'WINDOW')
    return None, None, None


def add(fn, name):
    fn.__name__ = name
    step(fn)


def top_face(bm):
    bm.faces.ensure_lookup_table()
    return max(bm.faces, key=lambda f: f.normal.z)


def vert_px(v):
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    area, r = view3d()
    p = location_3d_to_region_2d(r, area.spaces.active.region_3d, ob().matrix_world @ v.co)
    return r.x + int(round(p[0])), r.y + int(round(p[1]))


def pixel(path, x, y):
    """sRGB colour of window pixel (x, y) (bottom-left origin) in a screenshot, brightest in a 3 x 3 block."""
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        px = img.pixels[:]
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                i = ((y + dy) * w + (x + dx)) * 4
                c = tuple(round(px[i + k], 3) for k in range(3))
                if best is None or sum(c) > sum(best):
                    best = c
        return best
    finally:
        bpy.data.images.remove(img)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cube():
    with ctx():
        bpy.ops.allset.create(kind='CUBE')
        S["name"] = bpy.context.view_layer.objects.active.name
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.view3d.view_selected()
        bpy.ops.mesh.select_all(action='DESELECT')


@step
def s_f12():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    tap('F12')


@step
def s_wait():
    pass


@step
def s_frame():
    w, a, r = uv_win()
    check("F12 opened the UV Editor", w is not None)
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.image.view_all(fit_view=True)
    ts = bpy.context.scene.tool_settings
    check("UV mode: UV Sync off, UVs picked one by one", not ts.use_uv_select_sync and ts.uv_select_mode == 'VERTEX')
    bm = bmesh.from_edit_mesh(ob().data)
    check("the mesh keeps every face selected (all UVs show)", all(f.select for f in bm.faces))


def uv_target():
    w, a, r = uv_win()
    bm = bmesh.from_edit_mesh(ob().data)
    uv = bm.loops.layers.uv.active
    lp = top_face(bm).loops[0]
    S["vert"] = lp.vert.index
    x, y = r.view2d.view_to_region(lp[uv].uv.x, lp[uv].uv.y, clip=False)
    return w, r.x + x, r.y + y


@step
def s_uv_hover():
    w, x, y = uv_target()
    S["pos"] = (x, y)
    w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)


@step
def s_uv_press():
    w = uv_win()[0]
    w.event_simulate(type='LEFTMOUSE', value='PRESS', x=S["pos"][0], y=S["pos"][1])


@step
def s_uv_release():
    w = uv_win()[0]
    w.event_simulate(type='LEFTMOUSE', value='RELEASE', x=S["pos"][0], y=S["pos"][1])


@step
def s_settle():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + 10, y=r.y + 10)     # park the mouse off the cube


@step
def s_settle2():
    pass


@step
def s_check_selection():
    cc = import_module(MODULE + ".ui.component_colors")
    bm = bmesh.from_edit_mesh(ob().data)
    picked = {i for i, on in enumerate(cc.uv_selected_verts(bm)) if on}
    S["picked"] = picked
    check(f"the UV click picked the clicked vertex's UV ({sorted(picked)})", S["vert"] in picked)
    check("the 3D View draws the UV selection", cc.uv_mode(bpy.context))


@step
def s_shot():
    S["shot"] = os.path.join(SHOTS or tempfile.mkdtemp(), "gui_issue264_uv_3d.png")
    screenshot(S["shot"])
    w, a, r = uv_win()
    if SHOTS:
        with bpy.context.temp_override(window=w):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, "gui_issue264_uv_editor.png"))


@step
def s_pixels():
    bm = bmesh.from_edit_mesh(ob().data)
    top = top_face(bm)
    for v in top.verts:
        x, y = vert_px(v)
        c = pixel(S["shot"], x, y)
        if v.index in S["picked"]:
            check(f"vertex {v.index} with a picked UV drawn selected (yellow) {c}", c[0] > 0.85 and c[1] > 0.85)
        else:
            check(f"vertex {v.index} without a picked UV drawn unselected (magenta) {c}",
                  c[0] > 0.6 and c[1] < 0.35 and c[2] > 0.6)


def uv_shot(name):
    w, a, r = uv_win()
    path = os.path.join(SHOTS or tempfile.mkdtemp(), name)
    with bpy.context.temp_override(window=w):
        bpy.ops.screen.screenshot(filepath=path)
    return path


def uv_px(u, v):
    w, a, r = uv_win()
    x, y = r.view2d.view_to_region(u, v, clip=False)
    return r.x + int(round(x)), r.y + int(round(y))


def red(c):
    return c[0] > c[1] + 0.12 and c[0] > c[2] + 0.12


def face_centre_uv(f):
    bm = bmesh.from_edit_mesh(ob().data)
    uv = bm.loops.layers.uv.active
    return (sum(l[uv].uv.x for l in f.loops) / len(f.loops), sum(l[uv].uv.y for l in f.loops) / len(f.loops))


@step
def s_hover_uv():
    bm = bmesh.from_edit_mesh(ob().data)
    uv = bm.loops.layers.uv.active
    bm.faces.ensure_lookup_table()
    lp = bm.faces[3].loops[1]
    S["hover_uv"] = (lp[uv].uv.x, lp[uv].uv.y)
    x, y = uv_px(*S["hover_uv"])
    uv_win()[0].event_simulate(type='MOUSEMOVE', value='NOTHING', x=x + 6, y=y + 5)


@step
def s_hover_uv_wait():
    pass


@step
def s_hover_uv_shot():
    S["uv_shot"] = uv_shot("gui_issue264_uv_hover_uv.png")


@step
def s_hover_uv_check():
    x, y = uv_px(*S["hover_uv"])
    c = pixel(S["uv_shot"], x, y)
    check(f"UV mode: the UV near the mouse is pre-selected (red) {c}", red(c))


@step
def s_face_mode():
    bpy.context.scene.tool_settings.uv_select_mode = 'FACE'
    bm = bmesh.from_edit_mesh(ob().data)
    bm.faces.ensure_lookup_table()
    S["face_uv"] = face_centre_uv(bm.faces[3])
    S["other_uv"] = face_centre_uv(bm.faces[4])
    x, y = uv_px(*S["face_uv"])
    uv_win()[0].event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)


@step
def s_face_wait():
    pass


@step
def s_face_shot():
    S["face_shot"] = uv_shot("gui_issue264_uv_hover_face.png")


@step
def s_face_check():
    x, y = uv_px(*S["face_uv"])
    c = pixel(S["face_shot"], x + 12, y + 12)
    ox, oy = uv_px(*S["other_uv"])
    o = pixel(S["face_shot"], ox + 12, oy + 12)
    check(f"UV face mode: the face under the mouse is pre-selected (red tint {c}, other face {o})",
          red(c) and not red(o))


@step
def s_f11():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + 10, y=r.y + 10)
    tap('F11')


@step
def s_f11_wait():
    pass


@step
def s_f11_check():
    cc = import_module(MODULE + ".ui.component_colors")
    check("F11 (faces): UV Sync back on, the 3D View shows the mesh selection again", not cc.uv_mode(bpy.context))


run()
