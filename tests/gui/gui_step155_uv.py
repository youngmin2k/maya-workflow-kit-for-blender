"""In a real UI: cube -> UV > UV Editor -> top face cut out (two shells) + Layout -> Maya 9 texture
borders (on by default, thick), 8 shell borders (colour), Ctrl+1 isolate, 4 wireframe; screenshots per state
(src/allset/ui/uv_display.py)."""

import os
import sys
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, run, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(sys.modules["sim"].MODULE + name)


def cube():
    return bpy.data.objects["Cube"]


def uv_window():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.ui_type == 'UV':
                return w, a, next(r for r in a.regions if r.type == 'WINDOW')
    return None, None, None


def shot(name):
    w, _a, _r = uv_window()
    if SHOTS and w is not None:
        with bpy.context.temp_override(window=w):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def uv_op(op, **kw):
    w, a, r = uv_window()
    with bpy.context.temp_override(window=w, area=a, region=r):
        return op(**kw)


def redraw_all():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def shells():
    b = bmesh.from_edit_mesh(cube().data)
    C["bm"] = b
    uv = b.loops.layers.uv.active
    return mod(".operators.uv_tools").islands(b, uv)


@step
def s_setup():
    C["x"], C["y"] = setup()
    bpy.context.view_layer.objects.active = cube()
    cube().select_set(True)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        C["open"] = mod(".marking.modal").run_action(bpy.context, mod(".ui.menu_map").MAP["UV/UV Editor"])


@step
def s_wait_uv_window():
    # the window opens a few ticks later when it has a remembered place (window places)
    import sim
    C.setdefault("wait_uv", 0)
    if uv_window()[1] is None and C["wait_uv"] < 15:
        C["wait_uv"] += 1
        sim._steps.insert(0, s_wait_uv_window)


@step
def s_cut():
    w, a, r = uv_window()
    check(f"UV Editor window open ({C['open']})", a is not None and cube().mode == 'EDIT')
    if a is None:
        return
    b = bmesh.from_edit_mesh(cube().data)
    for el in (*b.verts, *b.edges, *b.faces):
        el.select = False
    for e in b.edges:
        e.select = all(v.co.z > 0.5 for v in e.verts)
    for v in b.verts:
        v.select = any(e.select for e in v.link_edges)
    bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
    bmesh.update_edit_mesh(cube().data)
    uv_op(bpy.ops.allset.uv_cut)
    b = bmesh.from_edit_mesh(cube().data)
    for f in b.faces:
        f.select_set(True)
    bmesh.update_edit_mesh(cube().data)
    uv_op(bpy.ops.allset.uv_layout)
    uv_op(bpy.ops.image.view_all, fit_view=True)
    check(f"two shells after Cut + Layout (got {len(shells())})", len(shells()) == 2)
    redraw_all()


@step
def s_shot_default():
    wm = bpy.context.window_manager
    check("default: Texture Borders on", wm.allset_uv_texture_borders and not wm.allset_uv_shell_borders)
    w, _a, _r = uv_window()
    seg = mod(".ui.uv_display").segments_of(cube(), bpy.context.scene.tool_settings.use_uv_select_sync)
    check(f"border segments drawn: {len(seg) // 2}", len(seg) // 2 == 12 + 4)   # 5-face cross outline 12 + top face 4


@step
def s_shot_default2():
    shot("gui_step155_uv_texture_borders.png")
    uv_op(bpy.ops.allset.uv_display, mode='TEXTURE_BORDERS')
    redraw_all()


@step
def s_off():
    pass


@step
def s_shot_off():
    check("9 toggles Texture Borders off", not bpy.context.window_manager.allset_uv_texture_borders)
    shot("gui_step155_uv_borders_off.png")
    uv_op(bpy.ops.allset.uv_display, mode='TEXTURE_BORDERS')
    uv_op(bpy.ops.allset.uv_display, mode='SHELL_BORDERS')
    redraw_all()


@step
def s_shell():
    pass


@step
def s_shot_shell():
    check("8 = Shell Borders on", bpy.context.window_manager.allset_uv_shell_borders)
    shot("gui_step155_uv_shell_borders.png")
    # select the top face's UVs only, then Ctrl+1
    ts = bpy.context.scene.tool_settings
    b = bmesh.from_edit_mesh(cube().data)
    C["bm"] = b
    if ts.use_uv_select_sync:
        for el in (*b.verts, *b.edges, *b.faces):
            el.select = False
        for f in b.faces:
            if all(v.co.z > 0.5 for v in f.verts):
                f.select_set(True)
    else:
        uv = b.loops.layers.uv.active
        compat = mod(".compat")
        for f in b.faces:
            for loop in f.loops:
                compat.set_uv_vert_selected(loop, uv, all(v.co.z > 0.5 for v in f.verts))
    bmesh.update_edit_mesh(cube().data)
    C["iso"] = uv_op(bpy.ops.allset.uv_isolate)
    redraw_all()


@step
def s_iso():
    pass


@step
def s_shot_iso():
    b = bmesh.from_edit_mesh(cube().data)
    C["bm"] = b
    ts = bpy.context.scene.tool_settings
    shown = [f for f in b.faces if not f.hide and (ts.use_uv_select_sync or f.select)]
    check(f"Ctrl+1 isolates the top face (shown {len(shown)}, {C['iso']})", len(shown) == 1)
    shot("gui_step155_uv_isolate.png")
    uv_op(bpy.ops.allset.uv_isolate)
    uv_op(bpy.ops.allset.uv_display, mode='WIREFRAME')
    redraw_all()


@step
def s_wire():
    pass


@step
def s_shot_wire():
    b = bmesh.from_edit_mesh(cube().data)
    C["bm"] = b
    ts = bpy.context.scene.tool_settings
    shown = [f for f in b.faces if not f.hide and (ts.use_uv_select_sync or f.select)]
    check(f"Ctrl+1 again shows all 6 faces (got {len(shown)})", len(shown) == 6)
    _w, a, _r = uv_window()
    check("4 = wireframe (faces off)", not a.spaces.active.uv_editor.show_faces)
    shot("gui_step155_uv_wireframe.png")
    uv_op(bpy.ops.allset.uv_move_shell)


@step
def s_move_shell():
    ts = bpy.context.scene.tool_settings
    tool = bpy.context.workspace.tools.from_space_image_mode('UV', create=False)
    check(f"Move UV Shell: shell selection + Move tool ({tool.idname if tool else None})",
          mod(".compat").uv_island_mode(ts) and tool is not None and tool.idname == "builtin.move")
    uv_op(bpy.ops.wm.tool_set_by_id, name="builtin.select_box", space_type='IMAGE_EDITOR')


@step
def s_wait1():
    pass


@step
def s_wait2():
    pass


@step
def s_wait3():
    pass


@step
def s_back():
    ts = bpy.context.scene.tool_settings
    check("another UV tool -> back to UV selection", not mod(".compat").uv_island_mode(ts))


run()
