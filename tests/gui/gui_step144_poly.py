"""POLY lane in a real UI (GitHub #30): Mesh Tools > Create Polygon = click points on the ground, Backspace,
Enter -> polySurface1 (and Limit points completes by itself); Append to Polygon = click a border edge + 2 points,
Enter -> a face added to that mesh; Quad Draw (Ctrl+Shift+Q, the Cube made live) = clicks drop dots on the cube's top,
Shift hover previews and Shift+click fills a quad, Ctrl+click = edge loop, drag a vertex = it stays on the surface,
Tab+drag a border edge = a new quad, Ctrl+Shift+click = delete a face, Esc = Select tool."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def qd():
    return import_module(MODULE + ".operators.quad_draw")


def pd():
    return import_module(MODULE + ".operators.poly_draw")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def menu(path):
    with override():
        return bpy.ops.allset.menu_item(item=path)


def tool_id():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        t = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
    return t.idname if t else None


def to_window(w):
    area, region = view3d()
    p = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, Vector(w))
    return region.x + round(p.x), region.y + round(p.y)


def press(w, **mods):
    x, y = to_window(w) if len(w) == 3 else w
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y, **mods)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, **mods)


def release(**mods):
    ev('LEFTMOUSE', 'RELEASE', **mods)


def mesh_counts(ob):
    if ob.mode == 'EDIT':
        b = bmesh.from_edit_mesh(ob.data)
        return len(b.verts), len(b.edges), len(b.faces)
    return len(ob.data.vertices), len(ob.data.edges), len(ob.data.polygons)


def edit_verts(ob):
    b = bmesh.from_edit_mesh(ob.data)
    return [ob.matrix_world @ v.co for v in b.verts]


GROUND = [(2.0, -1.0, 0.0), (3.5, -1.0, 0.0), (3.5, 0.5, 0.0), (2.0, 0.5, 0.0)]
EXTRA = (2.7, 1.5, 0.0)
TOP = [(-0.6, -0.6, 1.0), (0.6, -0.6, 1.0), (0.6, 0.6, 1.0), (-0.6, 0.6, 1.0)]


# --- Create Polygon -------------------------------------------------------------------------------------

@step
def s_setup():
    C["x"], C["y"] = setup()
    check("Maya keymap active", sys.modules["sim"].maya_keys())
    with override():
        bpy.ops.object.select_all(action='DESELECT')
    menu("Mesh Tools/Create Polygon")


@step
def s_create_tool():
    check(f"Create Polygon = the kit tool in object mode ({bpy.context.mode}, {tool_id()})",
          bpy.context.mode == 'OBJECT' and tool_id() == "allset.create_polygon_tool")
    C["k"] = 0
    press(GROUND[0])


def _next_point():
    release()
    C["k"] += 1


for _i in range(1, 4):
    @step
    def s_point(i=_i):
        _next_point()
        press(GROUND[i])


@step
def s_extra():
    release()
    press(EXTRA)


@step
def s_extra_release():
    release()
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


@step
def s_backspace():
    items = pd().STATE["items"]
    check(f"5 clicks = 5 points on the ground ({len(items)}, z {[round(p.z, 3) for p in items]})",
          len(items) == 5 and all(abs(p.z) < 1e-4 for p in items))
    shot("gui_step144_create_points.png")
    tap('BACK_SPACE')


@step
def s_enter():
    check(f"Backspace removes the last point ({len(pd().STATE['items'])})", len(pd().STATE["items"]) == 4)
    tap('RET')


@step
def s_created():
    ob = bpy.data.objects.get("polySurface1")
    ok = ob is not None and mesh_counts(ob) == (4, 4, 1)
    check(f"Enter = a new polySurface1 with one quad ({ob and mesh_counts(ob)})", ok)
    if ok:
        got = [(round(v.co.x, 2), round(v.co.y, 2), round(v.co.z, 3)) for v in ob.data.vertices]
        check(f"its corners are where the clicks were, on the ground ({got})",
              all(any(abs(g[0] - x) < 0.05 and abs(g[1] - y) < 0.05 and g[2] == 0 for g in got)
                  for x, y, _z in GROUND))
        check("the new polygon is selected and active", bpy.context.view_layer.objects.active == ob and ob.select_get())
    check(f"the tool stays ({tool_id()})", tool_id() == "allset.create_polygon_tool")
    shot("gui_step144_created.png")
    bpy.context.scene.allset_poly_tools.cp_limit_on = True
    bpy.context.scene.allset_poly_tools.cp_limit_points = 3
    press((-2.0, -3.0, 0.0))


@step
def s_limit_1():
    release()
    press((-1.0, -3.0, 0.0))


@step
def s_limit_2():
    release()
    press((-1.5, -2.0, 0.0))


@step
def s_limit_3():
    release()


@step
def s_limit_done():
    ob = bpy.data.objects.get("polySurface2")
    check(f"Limit points 3: the third click completes polySurface2 ({ob and mesh_counts(ob)})",
          ob is not None and mesh_counts(ob) == (3, 3, 1))
    bpy.context.scene.allset_poly_tools.property_unset("cp_limit_points")
    bpy.context.scene.allset_poly_tools.property_unset("cp_limit_on")
    with override():
        bpy.ops.object.select_all(action='DESELECT')
    bpy.data.objects["polySurface1"].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["polySurface1"]
    menu("Mesh Tools/Append to Polygon")


# --- Append to Polygon -----------------------------------------------------------------------------------

@step
def s_append_tool():
    check(f"Append to Polygon = edit mode + the kit tool ({bpy.context.mode}, {tool_id()})",
          bpy.context.mode == 'EDIT_MESH' and tool_id() == "allset.append_polygon_tool")
    a, b = Vector(GROUND[2]), Vector(GROUND[3])      # the far edge (y = 0.5)
    press((a + b) / 2)


@step
def s_append_p1():
    release()
    check(f"a click on the border edge starts the face ({pd().STATE['items']})",
          pd().STATE["items"] and pd().STATE["items"][0][0] == 'EDGE')
    press((3.5, 1.8, 0.0))


@step
def s_append_p2():
    release()
    press((2.0, 1.8, 0.0))


@step
def s_append_enter():
    release()
    shot("gui_step144_append_points.png")
    tap('RET')


@step
def s_appended():
    ob = bpy.data.objects["polySurface1"]
    n = mesh_counts(ob)
    check(f"Enter adds the face to polySurface1 (4/4/1 -> {n}, want 6/7/2)", n == (6, 7, 2))
    b = bmesh.from_edit_mesh(ob.data)
    shared = [e for e in b.edges if len(e.link_faces) == 2]
    check(f"the new face shares the clicked border edge, normals agree ({len(shared)})",
          len(shared) == 1 and shared[0].link_loops[0].vert is not shared[0].link_loops[1].vert)
    shot("gui_step144_appended.png")
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
    cube = bpy.data.objects["Cube"]
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    with override():
        bpy.ops.allset.make_live()
    area, _r = view3d()
    rv3d = area.spaces.active.region_3d          # closer, for the screenshots (clicks follow the view)
    rv3d.view_location = (0.0, 0.0, 1.0)
    rv3d.view_distance = 6.0
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('Q', 'PRESS', ctrl=True, shift=True)
    ev('Q', 'RELEASE', ctrl=True, shift=True)


# --- Quad Draw -------------------------------------------------------------------------------------------

@step
def s_quad_tool():
    ob = bpy.context.edit_object
    check(f"Ctrl+Shift+Q with the live cube = a new mesh in edit mode + Quad Draw ({ob and ob.name}, {tool_id()})",
          ob is not None and ob.name == "polySurface3" and tool_id() == "allset.quad_draw_tool")
    area, _r = view3d()
    check("the Retopology overlay shows the new mesh over the surface", area.spaces.active.overlay.show_retopology)
    C["ob"] = ob.name if ob else ""
    C["k"] = 0
    press(TOP[0])


for _i in range(1, 4):
    @step
    def s_dot(i=_i):
        release()
        press(TOP[i])


@step
def s_dots_done():
    release()
    ob = bpy.data.objects[C["ob"]]
    bm = bmesh.from_edit_mesh(ob.data)
    dots = [ob.matrix_world @ v.co for v in qd().dots(bm)]
    check(f"4 clicks = 4 dots on the live cube's top (z {[round(d.z, 3) for d in dots]})",
          len(dots) == 4 and all(abs(d.z - 1.0) < 1e-3 for d in dots))
    shot("gui_step144_dots.png")
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_dot_undone():
    ob = bpy.data.objects[C["ob"]]
    n = len(qd().dots(bmesh.from_edit_mesh(ob.data)))
    check(f"Ctrl+Z takes the last dot back ({n} dots)", n == 3 and bpy.context.mode == 'EDIT_MESH')
    press(TOP[3])


@step
def s_dot_again():
    release()
    x, y = to_window((0.0, 0.0, 1.0))
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y, shift=True)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y, shift=True)


@step
def s_fill_preview():
    pv = qd().STATE["preview"]
    check(f"Shift hover between the dots = the quad's preview ({pv and pv[0]})", pv is not None and pv[0] == 'FILL')
    shot("gui_step144_quad_preview.png")
    press((0.0, 0.0, 1.0), shift=True)


@step
def s_fill_release():
    release(shift=True)


@step
def s_filled():
    ob = bpy.data.objects[C["ob"]]
    n = mesh_counts(ob)
    check(f"Shift+click = a quad from the 4 dots ({n})", n == (4, 4, 1))
    check("the dots became its vertices", not qd().dots(bmesh.from_edit_mesh(ob.data)))
    b = bmesh.from_edit_mesh(ob.data)
    b.faces.ensure_lookup_table()
    check("the quad faces the camera (up)", b.faces and (ob.matrix_world.to_3x3() @ b.faces[0].normal).z > 0.9)
    shot("gui_step144_quad.png")
    # Ctrl+click on the edge at y = -0.6 (front)
    x, y = to_window((0.0, -0.6, 1.0))
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y, ctrl=True)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y, ctrl=True)


@step
def s_loop_preview():
    pv = qd().STATE["preview"]
    check(f"Ctrl hover over an edge = the loop preview ({pv and pv[0]})", pv is not None and pv[0] == 'LOOP')
    press((0.0, -0.6, 1.0), ctrl=True)


@step
def s_loop_release():
    release(ctrl=True)


@step
def s_loop():
    ob = bpy.data.objects[C["ob"]]
    n = mesh_counts(ob)
    check(f"Ctrl+click = an edge loop across the quad ({n}, want 6/7/2)", n == (6, 7, 2))
    check("the new vertices lie on the live surface", all(abs(w.z - 1.0) < 1e-3 for w in edit_verts(ob)))
    # Ctrl+Shift+middle-drag the new loop's edge to the right: the loop moves (Maya "tweak edge loop")
    x, y = to_window((0.0, 0.0, 1.0))
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y, ctrl=True, shift=True)
    ev('MIDDLEMOUSE', 'PRESS', x=x, y=y, ctrl=True, shift=True)


@step
def s_slide_move():
    x, y = to_window((0.3, 0.0, 1.0))
    ev('MOUSEMOVE', 'NOTHING', x=x - 10, y=y, ctrl=True, shift=True)


@step
def s_slide_move2():
    x, y = to_window((0.3, 0.0, 1.0))
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y, ctrl=True, shift=True)


@step
def s_slide_release():
    ev('MIDDLEMOUSE', 'RELEASE', ctrl=True, shift=True)


@step
def s_slid():
    ob = bpy.data.objects[C["ob"]]
    vs = edit_verts(ob)
    mids = sorted(round(w.x, 2) for w in vs if abs(abs(w.x) - 0.6) > 0.05)
    check(f"Ctrl+Shift+middle-drag an edge moves its edge loop on the surface ({mids}, was 0.0)",
          len(mids) == 2 and all(0.2 < m < 0.4 for m in mids) and all(abs(w.z - 1) < 1e-3 for w in vs))
    shot("gui_step144_slid.png")
    # drag the corner (0.6, 0.6, 1) towards the cube's middle
    press(TOP[2])


@step
def s_drag_move():
    x, y = to_window((0.3, 0.3, 1.0))
    ev('MOUSEMOVE', 'NOTHING', x=x - 5, y=y - 5)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_drag_release():
    release()


@step
def s_dragged():
    ob = bpy.data.objects[C["ob"]]
    vs = edit_verts(ob)
    moved = [w for w in vs if abs(w.x - 0.3) < 0.08 and abs(w.y - 0.3) < 0.08]
    check(f"dragging a vertex moves it along the surface ({[tuple(round(c, 2) for c in w) for w in moved]})",
          len(moved) == 1 and abs(moved[0].z - 1.0) < 1e-3)
    C["n"] = mesh_counts(ob)
    # Tab held + drag the border edge x = -0.6 outwards (to x = -0.95)
    x, y = to_window((-0.6, 0.0, 1.0))
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('TAB', 'PRESS', x=x, y=y)


@step
def s_tab_press():
    press((-0.6, 0.0, 1.0))


@step
def s_tab_drag():
    x, y = to_window((-0.95, 0.0, 1.0))
    ev('MOUSEMOVE', 'NOTHING', x=x + 4, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_tab_shot():
    shot("gui_step144_extend_preview.png")
    release()


@step
def s_tab_release():
    ev('TAB', 'RELEASE')


@step
def s_extended():
    ob = bpy.data.objects[C["ob"]]
    n0, n = C["n"], mesh_counts(ob)
    check(f"Tab+drag a border edge = one more quad ({n0} -> {n})", n == (n0[0] + 2, n0[1] + 3, n0[2] + 1))
    vs = edit_verts(ob)
    check(f"the new edge lies on the live surface near x = -0.95 ({sorted(round(w.x, 2) for w in vs)[:2]})",
          sum(1 for w in vs if abs(w.x + 0.95) < 0.08 and abs(w.z - 1.0) < 1e-3) == 2)
    shot("gui_step144_extended.png")
    press((-0.8, 0.0, 1.0), ctrl=True, shift=True)


@step
def s_delete_release():
    release(ctrl=True, shift=True)


@step
def s_deleted():
    ob = bpy.data.objects[C["ob"]]
    n = mesh_counts(ob)
    check(f"Ctrl+Shift+click a face = it goes ({n}, faces {C['n'][2]})", n[2] == C["n"][2])
    with override():
        bpy.ops.allset.editor_toggle(editor='TOOL_SETTINGS', show=True)


@step
def s_dock():
    pass


@step
def s_dock_shot():
    shot("gui_step144_tool_settings.png")
    _a, r = view3d()
    C["x"], C["y"] = r.x + r.width // 2, r.y + r.height // 2
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    tap('ESC')


@step
def s_left():
    check(f"Esc leaves Quad Draw for Select ({tool_id()})", tool_id() is not None and tool_id().startswith("builtin.select"))


@step
def s_watch():
    pass


@step
def s_restored():
    area, _r = view3d()
    check("leaving Quad Draw puts the Retopology overlay back", not area.spaces.active.overlay.show_retopology)


run()
