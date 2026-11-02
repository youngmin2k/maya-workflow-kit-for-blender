"""Issue #264 in a real UI: the UV Editor's Move / Rotate / Scale tools show the kit's Maya-style manipulator at
the centre of the selected UVs' box. Drags on the U arrow, the V arrow and the centre square move the UVs along U, along
V and freely; the ring turns them about the centre; the U box scales them along U only. Several drags in a row each
act (the handles never read the mesh while a transform runs). Under event simulation the first drag of a session keeps
only part of its move (Blender's own UV gizmo too), so a warm-up drag comes first."""

import math
import os
import sys
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, screenshot, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"pos": {}}


def um():
    return import_module(MODULE + ".ui.uv_manipulator")


def uv_window():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == 'IMAGE_EDITOR' and a.ui_type == 'UV':
                return w, a, next(r for r in a.regions if r.type == 'WINDOW')
    return None, None, None


def uev(type, value, x=None, y=None, **kw):
    """Events go to the main window (the UV Editor is in it) through sim.ev, which keeps the held-button state."""
    import sim
    if x is not None:
        kw.update(x=int(x), y=int(y))
    sim.ev(type, value, **kw)


def cur():
    import sim
    return sim._pos


def uvs():
    bm = bmesh.from_edit_mesh(bpy.context.edit_object.data)
    uv = bm.loops.layers.uv.active
    return [tuple(l[uv].uv) for f in bm.faces for l in f.loops]


def spread(vals):
    return max(vals) - min(vals)


def handle_point(handle, frac=0.6):
    """Window pixels of a point on the manipulator's ``handle``: U / V ``frac`` of the handle length out, R on the
    ring, C the centre."""
    w, a, r = uv_window()
    with bpy.context.temp_override(window=w, area=a, region=r):
        b = um().selected_uv_bounds(bpy.context)
        cx, cy = um().center_px(bpy.context, b)
        length = um().length_px(bpy.context)
    dx, dy = {'U': (length * frac, 0), 'V': (0, length * frac), 'R': (length, 0)}.get(handle, (0, 0))
    return r.x + cx + dx, r.y + cy + dy


def tool_set(idname):
    w, a, r = uv_window()
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.wm.tool_set_by_id(name=idname, space_type='IMAGE_EDITOR')


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cube():
    from sim import view3d
    area, r = view3d()
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0], area=area, region=r):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
    check("cube in edit mode", bpy.context.mode == 'EDIT_MESH')


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
    check("a UV Editor", w is not None)
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.image.view_all(fit_view=True)
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.mesh.select_all(action='SELECT')
    tool_set("builtin.move")


@step
def s_wait_tool():
    pass


@step
def s_tool():
    tool = C["ws"].tools.from_space_image_mode('UV', create=False) if C["ws"] else None
    check(f"the UV Move tool uses the kit manipulator ({tool and tool.widget})",
          tool is not None and tool.widget == um().GROUP)
    shot("gui_issue264_uv_manip_move.png")


def add(fn, name):
    fn.__name__ = name
    step(fn)


def drag(tag, handle, dx, dy, n=6):
    """Hover a handle, press, move in ``n`` ticks, release (each in its own tick); the UVs before / after."""
    box = {}
    for i in range(3):
        add(lambda: None, f"s_{tag}_pause{i}")      # a press soon after the last one would be a double click
    add(lambda: (box.update(p=handle_point(handle)), uev('MOUSEMOVE', 'NOTHING', *box["p"])), f"s_{tag}_hover")
    add(lambda: (box.update(before=uvs()), uev('LEFTMOUSE', 'PRESS')), f"s_{tag}_press")
    for k in range(n):
        add(lambda k=k: uev('MOUSEMOVE', 'NOTHING', box["p"][0] + dx * (k + 1) / n, box["p"][1] + dy * (k + 1) / n),
            f"s_{tag}_move{k}")
    add(lambda: uev('LEFTMOUSE', 'RELEASE'), f"s_{tag}_release")
    add(lambda: box.update(after=uvs()), f"s_{tag}_settle")
    return box


def deltas(box):
    du = [a[0] - b[0] for a, b in zip(box["after"], box["before"])]
    dv = [a[1] - b[1] for a, b in zip(box["after"], box["before"])]
    return du, dv


def check_move(tag, box, axis):
    def fn():
        du, dv = deltas(box)
        if axis == 'UV':
            check(f"{tag}: the centre square moves the UVs freely ({du[0]:.4f}, {dv[0]:.4f})",
                  abs(du[0]) > 1e-3 and abs(dv[0]) > 1e-3 and spread(du) < 1e-5 and spread(dv) < 1e-5)
            return
        on, off = (du, dv) if axis == 'U' else (dv, du)
        check(f"{tag}: the {axis} arrow moves the UVs along {axis} ({on[0]:.4f})",
              abs(on[0]) > 1e-3 and spread(on) < 1e-5)
        check(f"{tag}: ... and not across ({max(abs(x) for x in off):.6f})", max(abs(x) for x in off) < 1e-6)
    add(fn, f"s_{tag}_check")


def box_of(pts):
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    return min(us), min(vs), max(us), max(vs)


# warm-up: the first drag of a simulated session keeps only part of the move
b = drag("warm", 'U', 40, 0)
add(lambda: check("warm-up drag on the U arrow moves along U only", max(abs(x) for x in deltas(b)[1]) < 1e-6),
    "s_warm_check")
for tag, handle, dx, dy in (("u", 'U', 60, 30), ("v", 'V', 30, 50), ("c", 'C', 40, 30), ("u2", 'U', -50, 0)):
    check_move(tag, drag(tag, handle, dx, dy), {'C': 'UV'}.get(handle, handle))

add(lambda: tool_set("builtin.rotate"), "s_rotate_tool")
add(lambda: None, "s_rotate_wait")
add(lambda: shot("gui_issue264_uv_manip_rotate.png"), "s_rotate_shot")
rot = drag("ring", 'R', 0, 60)


@step
def s_ring_check():
    b0, b1 = box_of(rot["before"]), box_of(rot["after"])
    c0 = ((b0[0] + b0[2]) / 2, (b0[1] + b0[3]) / 2)
    moved = max(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(rot["after"], rot["before"]))
    near = [abs(math.hypot(a[0] - c0[0], a[1] - c0[1]) - math.hypot(b[0] - c0[0], b[1] - c0[1]))
            for a, b in zip(rot["after"], rot["before"])]
    check(f"the ring turns the UVs ({moved:.4f})", moved > 1e-3)
    check(f"... about the box centre ({max(near):.6f})", max(near) < 1e-4)


add(lambda: tool_set("builtin.scale"), "s_scale_tool")
add(lambda: None, "s_scale_wait")
add(lambda: shot("gui_issue264_uv_manip_scale.png"), "s_scale_shot")
sca = drag("box", 'U', 40, 20)


@step
def s_box_check():
    b0, b1 = box_of(sca["before"]), box_of(sca["after"])
    w0, w1, h0, h1 = b0[2] - b0[0], b1[2] - b1[0], b0[3] - b0[1], b1[3] - b1[1]
    check(f"the U box scales the UVs along U ({w0:.4f} -> {w1:.4f})", w1 > w0 + 1e-3)
    check(f"... and not along V ({h0:.4f} -> {h1:.4f})", abs(h1 - h0) < 1e-5)


run()
