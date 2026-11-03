"""UV-only selection in the UV Editor (#264): UV Edge / UV Face components with UV Sync Selection off, a
double-click on a UV edge = its UV loop, Ctrl+double-click = its edge ring, a double-click on a UV = its shell (the
keymap items themselves are checked headless: event simulation sends no DOUBLE_CLICK). Shots: ALLSET_GUI_SHOTS."""

import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, setup, step, load_maya_layout, view3d, win, tap  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
S = {}
N = 10        # the plane's subdivisions


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


def uv_px(u, v):
    _w, _a, r = uv_win()
    x, y = r.view2d.view_to_region(u, v, clip=False)
    return r.x + x, r.y + y


def uv_ctx():
    w, a, r = uv_win()
    return bpy.context.temp_override(window=w, area=a, region=r)


def selected_uv_edges():
    bm = bmesh.from_edit_mesh(ob().data)
    uv = bm.loops.layers.uv.active
    out = set()
    for f in bm.faces:
        for lp in f.loops:
            if lp.uv_select_edge:
                a = tuple(round(c, 3) for c in lp[uv].uv)
                b = tuple(round(c, 3) for c in lp.link_loop_next[uv].uv)
                out.add(tuple(sorted((a, b))))
    return out


def double_click(ring=False):
    """Event simulation can't send DOUBLE_CLICK: run the UV Editor double-click item's operator the way the keymap
    does (INVOKE at the mouse the previous step moved over the UV Editor)."""
    with uv_ctx():
        return bpy.ops.allset.uv_loop_pick('INVOKE_DEFAULT', ring=ring)


def hover(uv):
    w = uv_win()[0]
    x, y = uv_px(*uv)
    w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_plane():
    with ctx():
        bpy.ops.allset.create(kind='PLANE')
        S["name"] = bpy.context.view_layer.objects.active.name
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.view3d.view_selected()


@step
def s_f12():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    tap('F12')


@step
def s_wait():
    pass


@step
def s_uv_edge_mode():
    w, a, r = uv_win()
    check("F12 opened the UV Editor", w is not None)
    with uv_ctx():
        bpy.ops.image.view_all(fit_view=True)
        check("UV Edge component", bpy.ops.allset.uv_component(mode='UV_EDGE') == {'FINISHED'})
        bpy.ops.uv.select_all(action='DESELECT')
    ts = bpy.context.scene.tool_settings
    check("UV Edge: UV Sync off, UV edges picked apart from the mesh",
          not ts.use_uv_select_sync and ts.uv_select_mode == 'EDGE' and not ts.use_uv_select_island)


@step
def s_hover_edge():
    hover((0.25, 0.5))


@step
def s_double_click_edge():
    check("double-click item runs", double_click() == {'FINISHED'})


@step
def s_wait2():
    pass


@step
def s_loop_check():
    edges = selected_uv_edges()
    check(f"double-click on a UV edge = its UV loop ({len(edges)} edges)",
          len(edges) == N and all(a[1] == b[1] == 0.5 for a, b in edges))
    if SHOTS:
        with uv_ctx():
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, "gui_issue264_uv_loop.png"))


@step
def s_hover_ring():
    hover((0.25, 0.5))


@step
def s_ctrl_double_click():
    check("Ctrl+double-click item runs", double_click(ring=True) == {'FINISHED'})


@step
def s_wait3():
    pass


@step
def s_ring_check():
    edges = selected_uv_edges()
    check(f"Ctrl+double-click on a UV edge = its edge ring ({len(edges)} edges)",
          len(edges) == N + 1 and all(a[1] == b[1] and (a[0], b[0]) == (0.2, 0.3) for a, b in edges))
    if SHOTS:
        with uv_ctx():
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, "gui_issue264_uv_ring.png"))


@step
def s_uv_mode():
    with uv_ctx():
        bpy.ops.allset.uv_component(mode='UV')
        bpy.ops.uv.select_all(action='DESELECT')


@step
def s_hover_uv():
    hover((0.3, 0.3))


@step
def s_double_click_uv():
    check("double-click item runs on a UV", double_click() == {'FINISHED'})


@step
def s_wait4():
    pass


@step
def s_shell_check():
    bm = bmesh.from_edit_mesh(ob().data)
    n = sum(lp.uv_select_vert for f in bm.faces for lp in f.loops)
    check(f"double-click on a UV = its whole UV shell ({n} of {N * N * 4} corners)", n == N * N * 4)


@step
def s_toolkit_shot():
    w, a, r = uv_win()
    with bpy.context.temp_override(window=w, area=a):
        bpy.ops.allset.uv_component(mode='UV_FACE')
        side = next((rg for rg in a.regions if rg.type == 'UI'), None)
        if side is not None and side.width <= 1:
            bpy.ops.wm.context_toggle(data_path="space_data.show_region_ui")
    a.tag_redraw()


@step
def s_toolkit_wait():
    pass


@step
def s_toolkit_check():
    from importlib import import_module
    from sim import MODULE
    tk = import_module(MODULE + ".ui.uv_toolkit")
    check("the UV Toolkit shows UV Face as the current component",
          tk.current_component(bpy.context) == 'UV_FACE')
    if SHOTS:
        with uv_ctx():
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, "gui_issue264_uv_toolkit.png"))


run()
