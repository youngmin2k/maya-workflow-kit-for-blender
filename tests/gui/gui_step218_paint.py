"""Lane P (Issue #126 A1 A2 A5 A6): Paint Skin Weights keys and UI in a GUI session, Maya 2026 rules
(Maya 2026 Paint Skin Weights). Alt+F = the kit Flood (Replace 0.3 into joint2 with Maya's
redistribution), Ctrl+. / Ctrl+, = Skin Paint Mode cycle (real tools), Alt+R = X reflection, Ctrl+Alt+C / V = copy /
paste vertex weights, RMB on an Influences list row = 7 items (screenshot), Select Vertices from it."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, find_button, px, run, screenshot, setup, step, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 200
C = {}
SHOTS = os.environ.get("ALLSET_GUI_SHOTS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                                           "tmp", "gui_step218_paint")


def mod(name):
    return import_module(MODULE + name)


def main_view():
    toolbox = mod(".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def cyl():
    return bpy.data.objects["pCylinder1"]


def weights(name):
    c = cyl()
    vg = c.vertex_groups[name]
    return [next((g.weight for g in v.groups if g.group == vg.index), 0.0) for v in c.data.vertices]


def centre():
    _a, r = main_view()
    return r.x + r.width // 2, r.y + r.height // 2


def key(type_, **mods):
    x, y = centre()
    ev(type_, 'PRESS', x=x, y=y, **mods)
    ev(type_, 'RELEASE', x=x, y=y, **mods)


def mode():
    return mod(".operators.weight_paint").paint_mode(bpy.context)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    joints = mod(".operators.joints")
    k = mod(".operators.units").maya_unit()
    area, r = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=r):
        bpy.ops.allset.create(kind='CYLINDER')
        c = bpy.context.active_object
        bm = bmesh.new()
        bm.from_mesh(c.data)
        vertical = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1e-9]
        bmesh.ops.subdivide_edges(bm, edges=vertical, cuts=7, use_grid_fill=True)
        bm.to_mesh(c.data)
        bm.free()
        bpy.ops.object.select_all(action='DESELECT')
        sk = joints.new_skeleton(bpy.context)
        parent = None
        for z in (-1.0, 0.0, 1.0):
            parent = joints.add_joint(sk, Vector((0, 0, z * k)), parent, length=k)
        joints.finish(bpy.context, sk, ["joint1", "joint2", "joint3"])
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        sk.select_set(True)
        c.select_set(True)
        bpy.context.view_layer.objects.active = c
        bpy.ops.allset.bind_skin()
        bpy.ops.object.select_all(action='DESELECT')
        c.select_set(True)
        bpy.context.view_layer.objects.active = c
        bpy.ops.allset.frame(selected=False)
        bpy.ops.allset.weight_workspace()          # paint + Tool Settings (the option box)
    c = cyl()
    c.vertex_groups.active_index = c.vertex_groups["joint2"].index
    ts = bpy.context.tool_settings
    ups = mod(".compat").unified_paint_settings(ts)
    for owner in (ups, ts.weight_paint.brush):
        owner.weight, owner.strength = 0.3, 1.0
    ts.weight_paint.brush.blend = 'MIX'
    C["j1"] = weights("joint1")
    C["j3"] = weights("joint3")
    check(f"painting ({bpy.context.mode}), mode {mode()}", bpy.context.mode == 'PAINT_WEIGHT' and mode() == 'PAINT')
    x, y = centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_flood():
    key('F', alt=True)


@step
def s_flooded():
    j2 = weights("joint2")
    sums = [a + b + c for a, b, c in zip(weights("joint1"), j2, weights("joint3"))]
    check(f"Alt+F = Maya Flood: joint2 {min(j2):.4f}..{max(j2):.4f}, sums {min(sums):.5f}..{max(sums):.5f}",
          max(abs(w - 0.3) for w in j2) < 1e-5 and max(abs(s - 1) for s in sums) < 1e-5)
    key('PERIOD', ctrl=True)


@step
def s_select_mode():
    C["select"] = mode()
    C["mask"] = cyl().data.use_paint_mask_vertex
    key('PERIOD', ctrl=True)


@step
def s_paint_select_mode():
    C["paint_select"] = mode()
    key('PERIOD', ctrl=True)


@step
def s_paint_mode():
    C["paint"] = mode()
    key('COMMA', ctrl=True)


@step
def s_back():
    check(f"Ctrl+. cycles {C['select']} -> {C['paint_select']} -> {C['paint']}, Ctrl+, -> {mode()}; mask on "
          f"in Select {C['mask']}", (C['select'], C['paint_select'], C['paint'], mode())
          == ('SELECT', 'PAINT_SELECT', 'PAINT', 'PAINT_SELECT') and C["mask"])
    key('PERIOD', ctrl=True)                 # back to Paint
    C["mirror"] = cyl().data.use_mirror_x


@step
def s_reflect():
    check(f"back in Paint ({mode()})", mode() == 'PAINT')
    key('R', alt=True)


@step
def s_reflected():
    check(f"Alt+R toggles X reflection ({C['mirror']} -> {cyl().data.use_mirror_x})",
          cyl().data.use_mirror_x != C["mirror"])
    key('R', alt=True)
    wp = mod(".operators.weight_paint")
    c = cyl()
    c.vertex_groups["joint1"].add([0], 0.6, 'REPLACE')
    c.vertex_groups["joint2"].add([0], 0.4, 'REPLACE')
    c.vertex_groups["joint3"].remove([0])
    wp.set_vertex_selection(c, [0])
    key('C', ctrl=True, alt=True)


@step
def s_copied():
    wp = mod(".operators.weight_paint")
    wp.set_vertex_selection(cyl(), [1, 2])
    key('V', ctrl=True, alt=True)


@step
def s_pasted():
    j1, j2 = weights("joint1"), weights("joint2")
    check(f"Ctrl+Alt+C / V: vertices 1, 2 = ({j1[1]:.3f}, {j2[1]:.3f}), ({j1[2]:.3f}, {j2[2]:.3f})",
          all(abs(j1[i] - 0.6) < 1e-6 and abs(j2[i] - 0.4) < 1e-6 for i in (1, 2)))
    mod(".operators.weight_paint").set_vertex_selection(cyl(), ())
    dock = mod(".ui.tool_dock").find(win().screen)
    check("Tool Settings dock open", dock is not None)
    C["dock"] = dock


def dock():
    area = mod(".ui.tool_dock").find(win().screen)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


# list rows have no data path for the probe: find the Sort row above the list (joint1's row is 60 px below it at UI 1.25)
step(find_button(dock, lambda p, _c: p.endswith("allset_weight_workspace.sort"), C, "sort", x_frac=0.9, step_px=4))


@step
def s_hover_row():
    found = C.get("sort")
    check(f"the Influences Sort row at {found}", found is not None)
    if found:
        _area, region = dock()
        C["row"] = (region.x + region.width // 3, found[1] - px(60))
        ev('MOUSEMOVE', 'NOTHING', x=C["row"][0], y=C["row"][1])


@step
def s_rmb():
    if C.get("row"):
        ev('RIGHTMOUSE', 'PRESS', x=C["row"][0], y=C["row"][1])
        ev('RIGHTMOUSE', 'RELEASE', x=C["row"][0], y=C["row"][1])


@step
def s_wait():
    pass


@step
def s_shot():
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, "influences_rmb.png")
    screenshot(path)
    check(f"screenshot of the Influences RMB menu: {path}", os.path.exists(path))
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


@step
def s_select_verts():
    c = cyl()
    c.vertex_groups.active_index = c.vertex_groups["joint3"].index
    area, r = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=r):
        bpy.ops.allset.weight_influence_verts(mode='SET')
    sel = {v.index for v in c.data.vertices if v.select}
    want = {i for i, w in enumerate(weights("joint3")) if w > 0}
    check(f"Select Vertices (joint3) = its {len(want)} vertices with weight > 0, mask on "
          f"{c.data.use_paint_mask_vertex}", sel == want and c.data.use_paint_mask_vertex)


run()
