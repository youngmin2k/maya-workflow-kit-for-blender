"""#172: Maya UV Shell selection in the 3D View and the UV Editor (operators/uv_shell_select.py, Maya 2026
rules). Cube with the top face's edges cut = shells A = f[0] f[4] f[5],
B = f[1], C = f[2] f[3]. The session: Alt+F12 over the viewport, clicks with Shift / Ctrl, an empty click, a box, the UV
Editor (same selection, a click there), F11 back to faces, Ctrl+Z, save / open. Shots: ALLSET_GUI_SHOTS."""

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
A, B, C = {0, 4, 5}, {1}, {2, 3}
S = {}


def ob():
    return bpy.data.objects[S["name"]]


def sel():
    return {f.index for f in bmesh.from_edit_mesh(ob().data).faces if f.select}


def ctx():
    area, r = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=r)


def face_px(i):
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    area, r = view3d()
    bm = bmesh.from_edit_mesh(ob().data)
    bm.faces.ensure_lookup_table()
    p = location_3d_to_region_2d(r, area.spaces.active.region_3d, ob().matrix_world @ bm.faces[i].calc_center_median())
    return r.x + int(p[0]), r.y + int(p[1])


def add(fn, name):
    fn.__name__ = name
    step(fn)


def click(tag, where, then, shift=False, ctrl=False, window=None):
    def hover():
        x, y = where()
        if window is None:
            ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        else:
            window().event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
            S["pos"] = (x, y)

    def press():
        if window is None:
            ev('LEFTMOUSE', 'PRESS', shift=shift, ctrl=ctrl)
        else:
            window().event_simulate(type='LEFTMOUSE', value='PRESS', x=S["pos"][0], y=S["pos"][1], shift=shift, ctrl=ctrl)

    def release():
        if window is None:
            ev('LEFTMOUSE', 'RELEASE', shift=shift, ctrl=ctrl)
        else:
            window().event_simulate(type='LEFTMOUSE', value='RELEASE', x=S["pos"][0], y=S["pos"][1], shift=shift,
                                    ctrl=ctrl)
    add(hover, tag + "_hover")
    add(press, tag + "_press")
    add(release, tag + "_release")
    add(lambda: None, tag + "_settle")
    add(then, tag + "_check")


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
        uvt = import_module(MODULE + ".operators.uv_tools")
        bm = bmesh.from_edit_mesh(ob().data)
        bm.faces.ensure_lookup_table()
        uvt.cut(bm, bm.loops.layers.uv.active, list(bm.faces[1].edges))     # Maya polyMapCut on the top face
        bmesh.update_edit_mesh(ob().data)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.view3d.view_selected()
        bpy.ops.mesh.select_all(action='DESELECT')
        area, r = view3d()
        area.spaces.active.region_3d.view_distance *= 2.5     # room around the cube for empty clicks
    check("pCube1 in edit mode", bpy.context.mode == 'EDIT_MESH')


@step
def s_wait():
    pass


@step
def s_alt_f12():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    ev('F12', 'PRESS', alt=True)
    ev('F12', 'RELEASE', alt=True)


@step
def s_mode():
    uss = import_module(MODULE + ".operators.uv_shell_select")
    vm = import_module(MODULE + ".ui.view_message")
    check("Alt+F12 over the viewport: UV Shell mask on", uss.active(bpy.context))
    check("no UV Editor window opened by it (Maya doesn't)", len(bpy.context.window_manager.windows) == 1)
    check(f"Maya's in-view message ({vm._state.get('text', '')[:40]})", "UV shell selection" in vm._state.get("text", ""))


click("front", lambda: face_px(0), lambda: check(f"click front -> shell A ({sorted(sel())})", sel() == A))
click("shift_top", lambda: face_px(1), lambda: check(f"Shift+click top adds B ({sorted(sel())})", sel() == A | B),
      shift=True)
click("shift_right", lambda: face_px(4), lambda: check(f"Shift+click right toggles A off ({sorted(sel())})", sel() == B),
      shift=True)
click("ctrl_top", lambda: face_px(1), lambda: check(f"Ctrl+click top removes B ({sorted(sel())})", sel() == set()),
      ctrl=True)
click("ctrl_shift_top", lambda: face_px(1),
      lambda: check(f"Ctrl+Shift+click top adds B ({sorted(sel())})", sel() == B), shift=True, ctrl=True)


def empty_px():
    area, r = view3d()
    x, y = int(r.width * 0.2), int(r.height * 0.5)       # left of the cube, inside the view (no corner gizmos)
    uss = import_module(MODULE + ".operators.uv_shell_select")
    with ctx():
        print("empty point ray", uss._ray_face(bpy.context, r, area.spaces.active.region_3d, (x, y)), flush=True)
    return r.x + x, r.y + y


click("empty", empty_px, lambda: check(f"click on empty space clears ({sorted(sel())})", sel() == set()))


def box(tag, a, b, then, shift=False, ctrl=False):
    """A box: the kit's drag item (allset.uv_shell_box, first in the Select Box keymap) then Blender's own
    view3d.select_box, both run in the view (event simulation makes no CLICK_DRAG here)."""
    def run_box():
        area, r = view3d()
        (x0, y0), (x1, y1) = a(), b()
        x0, x1, y0, y1 = x0 - r.x, x1 - r.x, y0 - r.y, y1 - r.y
        with ctx():
            bpy.ops.allset.uv_shell_box('INVOKE_DEFAULT')
            uss = import_module(MODULE + ".operators.uv_shell_select")
            if "state" in uss._box:
                uss._box["state"].update(shift=shift, ctrl=ctrl)
            mode = 'ADD' if shift and not ctrl else 'SUB' if ctrl and not shift else 'SET'
            bpy.ops.view3d.select_box(xmin=min(x0, x1), xmax=max(x0, x1), ymin=min(y0, y1), ymax=max(y0, y1), mode=mode,
                                      wait_for_input=False)
        S["blender_box"] = sorted(sel())
    add(run_box, tag + "_box")
    add(lambda: None, tag + "_w1")
    add(lambda: None, tag + "_w2")
    add(then, tag + "_check")


def small_box(i, d):
    return (lambda: (face_px(i)[0] - d, face_px(i)[1] - d)), (lambda: (face_px(i)[0] + d, face_px(i)[1] + d))


def select_tool():
    with ctx():
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")      # Maya's Select Tool (Q)


def whole_shells(x):
    return all(x & sh in (set(), sh) for sh in (A, B, C))


add(select_tool, "q_tool")
a0, b0 = small_box(0, 8)
box("box_front", a0, b0, lambda: check(f"box over the front face: Blender picked {S.get('blender_box')}, grown to "
                                       f"the whole shell A ({sorted(sel())})", sel() == A))
a1, b1 = small_box(4, 8)
box("box_ctrl_right", a1, b1, lambda: check(f"Ctrl+box over the right face removes shell A ({sorted(sel())})",
                                            sel() == set()), ctrl=True)


@step
def s_uv_open():
    with ctx():
        bpy.ops.allset.open_editor(ui_type='UV')
    uss = import_module(MODULE + ".operators.uv_shell_select")
    uss.pick(bpy.context, ob(), 0, False, False)       # A selected from the 3D side
    bmesh.update_edit_mesh(ob().data)


@step
def s_uv_wait():
    pass


def uv_win():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == 'IMAGE_EDITOR' and a.ui_type == 'UV':
                return w, a, next(r for r in a.regions if r.type == 'WINDOW')
    return None, None, None


@step
def s_uv_frame():
    w, a, r = uv_win()
    check("UV Editor opened", w is not None)
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.image.view_all(fit_view=True)


@step
def s_uv_shot():
    w, a, r = uv_win()
    if SHOTS:
        with bpy.context.temp_override(window=w):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, "gui_step256_uv_after_3d.png"))


def uv_face_px(i):
    w, a, r = uv_win()
    bm = bmesh.from_edit_mesh(ob().data)
    bm.faces.ensure_lookup_table()
    uv = bm.loops.layers.uv.active
    f = bm.faces[i]
    u = sum(l[uv].uv.x for l in f.loops) / len(f.loops)
    v = sum(l[uv].uv.y for l in f.loops) / len(f.loops)
    x, y = r.view2d.view_to_region(u, v, clip=False)
    return r.x + x, r.y + y


click("uv_top", lambda: uv_face_px(1), lambda: check(f"UV Editor click on the top UV face -> shell B, the same selection "
                                                     f"in 3D ({sorted(sel())})", sel() == B),
      window=lambda: uv_win()[0])
click("uv_shift_back", lambda: uv_face_px(3),
      lambda: check(f"UV Editor Shift+click adds shell C ({sorted(sel())})", sel() == B | C),
      shift=True, window=lambda: uv_win()[0])


@step
def s_uv_shot2():
    w, a, r = uv_win()
    if SHOTS:
        with bpy.context.temp_override(window=w):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, "gui_step256_uv_click.png"))
        screenshot(os.path.join(SHOTS, "gui_step256_3d.png"))


@step
def s_undo():
    with ctx():
        bpy.ops.ed.undo()
    check(f"Ctrl+Z undoes the last shell click ({sorted(sel())})", sel() == B)


@step
def s_f11():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    tap('F11')


click("face_mode_front", lambda: face_px(0),
      lambda: check(f"F11 (faces): the mask is off, a click picks one face ({sorted(sel())})",
                    not import_module(MODULE + ".operators.uv_shell_select").flag(bpy.context) and sel() == {0}))


@step
def s_save_open():
    S["file"] = os.path.join(tempfile.mkdtemp(), "uv256.blend")
    with ctx():
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.wm.save_as_mainfile(filepath=S["file"])
    bpy.ops.wm.open_mainfile(filepath=S["file"])


@step
def s_reopened():
    with ctx():
        o = ob()
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.allset.uv_component(mode='SHELL')


click("re_front", lambda: face_px(0), lambda: check(f"after save / open: shell click still picks A ({sorted(sel())})",
                                                    sel() == A))

run()
