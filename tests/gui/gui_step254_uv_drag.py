"""#170 #172: moving UVs in the Maya UV Editing workspace crashed Blender (heap corruption / access violation,
7 of 7 runs with 0.5.0 on 4.5.4 and 5.2.2): the kit's UV Editor draw handlers (shell / texture
borders, UV HUD) walked the edit BMesh on every redraw of a UV drag. Now they never read the mesh while a transform /
UV modal runs (operators/uv_arrays.editing_now) and read it with numpy otherwise.

The session: Maya layout, kit sphere in edit mode, Windows > Workspaces > UV Editing, face clicks, W-drags of faces,
UV Shell mode + shell drags on the manipulator (a drag off it draws a marquee, like Maya), Ctrl+Z. A crash ends the
run without results (the runner reports it). Checked: the UVs moved, the HUD and borders come back after each drag."""

import os
import sys
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, screenshot, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"pos": {}}


def uv_window():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == 'IMAGE_EDITOR' and a.ui_type == 'UV':
                return w, a, next(r for r in a.regions if r.type == 'WINDOW')
    return None, None, None


def uev(type, value, x=None, y=None, **kw):
    w, _a, _r = uv_window()
    p = C["pos"].setdefault(w.as_pointer(), [0, 0])
    if x is not None:
        p[:] = [int(x), int(y)]
    w.event_simulate(type=type, value=value, x=p[0], y=p[1], **kw)


def uv_px(u, v):
    _w, _a, r = uv_window()
    x, y = r.view2d.view_to_region(u, v, clip=False)
    return r.x + x, r.y + y


def face_centre(k):
    ob = bpy.context.edit_object
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    uv = bm.loops.layers.uv.active
    f = bm.faces[k]
    u = sum(l[uv].uv.x for l in f.loops) / len(f.loops)
    v = sum(l[uv].uv.y for l in f.loops) / len(f.loops)
    return uv_px(u, v)


def uv_sum():
    bm = bmesh.from_edit_mesh(bpy.context.edit_object.data)
    uv = bm.loops.layers.uv.active
    return sum(l[uv].uv.x + l[uv].uv.y for f in bm.faces for l in f.loops)


def uv_op(idname, **props):
    w, a, r = uv_window()
    mod, name = idname.split(".")
    with bpy.context.temp_override(window=w, area=a, region=r):
        return getattr(getattr(bpy.ops, mod), name)('EXEC_DEFAULT', **props)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_sphere():
    from sim import view3d
    area, r = view3d()
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0], area=area, region=r):
        bpy.ops.allset.create(kind='SPHERE')
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
    check("kit sphere in edit mode", bpy.context.mode == 'EDIT_MESH')


@step
def s_workspace():
    sw = import_module(MODULE + ".switch")
    C["ws"] = sw.append_workspace(bpy.context.window_manager.windows[0], "UV Editing")
    check("Maya UV Editing workspace", C["ws"] is not None)


@step
def s_wait_ws():
    pass


@step
def s_frame():
    w, a, r = uv_window()
    check("a UV Editor in the main window", w is not None and w == bpy.context.window_manager.windows[0])
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.image.view_all(fit_view=True)


def add(fn, name):
    fn.__name__ = name
    step(fn)


def clicks(tag, faces, shift_rest=True):
    for i, k in enumerate(faces):
        add(lambda k=k: uev('MOUSEMOVE', 'NOTHING', *face_centre(k)), f"{tag}{i}_hover")
        mods = {"shift": True} if (i and shift_rest) else {}
        add(lambda mods=mods: uev('LEFTMOUSE', 'PRESS', **mods), f"{tag}{i}_press")
        add(lambda mods=mods: uev('LEFTMOUSE', 'RELEASE', **mods), f"{tag}{i}_release")


def drag(tag, start, dx, dy, n=8):
    box = {}
    add(lambda: (box.update(p=start()), uev('MOUSEMOVE', 'NOTHING', *box["p"])), f"{tag}_hover")
    add(lambda: (box.update(sum=uv_sum()), uev('LEFTMOUSE', 'PRESS')), f"{tag}_press")
    for k in range(n):
        add(lambda k=k: uev('MOUSEMOVE', 'NOTHING', box["p"][0] + dx * (k + 1) / n, box["p"][1] + dy * (k + 1) / n),
            f"{tag}_move{k}")
    add(lambda: uev('LEFTMOUSE', 'RELEASE'), f"{tag}_release")
    add(lambda: None, f"{tag}_settle")
    add(lambda: check(f"{tag}: the UVs moved, Blender alive", abs(uv_sum() - box["sum"]) > 1e-4), f"{tag}_check")


def selected_centre():
    bm = bmesh.from_edit_mesh(bpy.context.edit_object.data)
    uv = bm.loops.layers.uv.active
    compat = import_module(MODULE + ".compat")
    pts = [l[uv].uv for f in bm.faces if f.select for l in f.loops if compat.uv_vert_selected(l, uv)]
    if not pts:
        return uv_px(0.5, 0.5)
    return uv_px(sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts))


for rnd in range(2):
    add(lambda: uv_op("allset.uv_component", mode='FACE'), f"r{rnd}_face_mode")
    clicks(f"r{rnd}_face", (200, 201, 220))
    add(lambda: uev('W', 'PRESS'), f"r{rnd}_w")
    add(lambda: uev('W', 'RELEASE'), f"r{rnd}_w_up")
    drag(f"r{rnd}_wdrag", selected_centre, -40, 25)
    add(lambda: uv_op("allset.uv_component", mode='SHELL'), f"r{rnd}_shell_mode")
    clicks(f"r{rnd}_shell", (100,), shift_rest=False)
    drag(f"r{rnd}_shelldrag", selected_centre, 60, 30)


@step
def s_after():
    uva = import_module(MODULE + ".operators.uv_arrays")
    hud = import_module(MODULE + ".ui.uv_hud")
    check("no edit modal left running", not uva.editing_now(bpy.context.window_manager))
    w, a, r = uv_window()
    a.tag_redraw()


@step
def s_redrawn():
    hud = import_module(MODULE + ".ui.uv_hud")
    disp = import_module(MODULE + ".ui.uv_display")
    stats = hud._cache.get("last")
    check(f"UV HUD numbers after the drags ({stats and stats[0]})", stats is not None and "UV shells" in stats[0])
    check("shell / texture borders drawn again after the drags", any(len(v) for v in disp._cache.values()))
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step254_uv_drag.png"))


@step
def s_undo():
    w, a, r = uv_window()
    before = uv_sum()
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.ed.undo()
    check("Ctrl+Z undoes the last shell drag", abs(uv_sum() - before) > 1e-4)


@step
def s_save():
    import tempfile
    C["file"] = os.path.join(tempfile.mkdtemp(), "uv254.blend")
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.wm.save_as_mainfile(filepath=C["file"])
    bpy.ops.wm.open_mainfile(filepath=C["file"])


@step
def s_reopened():
    ob = bpy.data.objects.get("pSphere1")
    check("saved and reopened: the sphere is back", ob is not None)
    w, a, r = uv_window()
    check("the UV Editing workspace came back with the file", w is not None)
    bpy.context.view_layer.objects.active = ob
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.image.view_all(fit_view=True)


add(lambda: uv_op("allset.uv_component", mode='SHELL'), "re_shell_mode")
clicks("re_shell", (100,), shift_rest=False)
drag("re_shelldrag", selected_centre, 50, 20)


run()
