"""Issue #139: in a real UI: the reported path — Move tool, Step Snap Off in Tool Settings, then Snap to Grid
on the Status Line (no hold key) — and a Move manipulator drag lands on a whole Maya unit, in object mode and on
selected vertices in edit mode. Before the fix the drag moved freely (use_snap_translate off)."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, win, load_maya_layout  # noqa: E402

C = {}


def area3d():
    toolbox = import_module(MODULE + ".ui.toolbox")
    return max((a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)),
               key=lambda a: a.width * a.height)


def region3d():
    return next(r for r in area3d().regions if r.type == 'WINDOW')


def override():
    return bpy.context.temp_override(window=win(), area=area3d(), region=region3d())


def manip_origin():
    ob = bpy.data.objects[C["ob"]]
    if ob.mode == 'EDIT':
        me = ob.data
        ob.update_from_editmode()
        pts = [ob.matrix_world @ v.co for v in me.vertices if v.select]
        return sum(pts, Vector()) / len(pts)
    return ob.matrix_world.translation.copy()


def hover_arrow():
    region = region3d()
    p0 = manip_origin()
    o = location_3d_to_region_2d(region, region.data, p0)
    a = location_3d_to_region_2d(region, region.data, p0 + Vector((C["k"], 0, 0)))
    d = (a - o).normalized()
    size = bpy.context.preferences.view.gizmo_size * bpy.context.preferences.system.ui_scale
    p = o + d * size * 0.75
    C["g"] = (int(region.x + p.x), int(region.y + p.y), d)
    x, y, _ = C["g"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


def press():
    x, y, _ = C["g"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


def move(i):
    x, y, d = C["g"]
    px = 113
    ev('MOUSEMOVE', 'NOTHING', x=int(x + d.x * px * i / 6), y=int(y + d.y * px * i / 6))


def release():
    x, y, d = C["g"]
    ev('LEFTMOUSE', 'RELEASE', x=int(x + d.x * 113), y=int(y + d.y * 113))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    with override():
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
        ob = bpy.context.view_layer.objects.active
        ob.location = (0.3 * import_module(MODULE + ".operators.units").maya_unit(), 0, 0)
        # the reported clicks: Tool Settings > Step Snap Off, then the Status Line Snap to Grid button
        bpy.ops.allset.step_snap(kind='TRANSLATE', mode='OFF')
        bpy.ops.allset.snap_toggle(snap='GRID')
    C["ob"], C["k"] = ob.name, import_module(MODULE + ".operators.units").maya_unit()
    ts = bpy.context.scene.tool_settings
    check(f"grid snap on, Move affected (use_snap {ts.use_snap}, {set(ts.snap_elements)}, "
          f"translate {ts.use_snap_translate})", ts.use_snap and 'GRID' in ts.snap_elements and ts.use_snap_translate)


def _drag_steps(tag):
    step(hover_arrow)
    step(press)
    for i in range(1, 7):        # one MOUSEMOVE per tick: Blender looks for a snap target at most every 10 ms
        step(lambda i=i: move(i))
    step(release)

    @step
    def done():
        ob = bpy.data.objects[C["ob"]]
        if ob.mode == 'EDIT':
            ob.update_from_editmode()
            xs = [(ob.matrix_world @ v.co).x / C["k"] for v in ob.data.vertices if v.select]
            xs.append(sum(xs) / len(xs))         # the manipulator centre (snap target Center, Maya)
        else:
            xs = [ob.location.x / C["k"]]
        # Blender snaps the closest selected point (Maya: the manipulator centre) - one of them is on the grid
        off = min(abs(n - round(n)) for n in xs)
        check(f"{tag}: the drag lands on a whole Maya unit (x = {[round(n, 4) for n in xs]})",
              off < 1e-3 and max(xs) >= 0.99)
    done.__name__ = f"s_{tag}_done"


_drag_steps("object")


@step
def s_edit():
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
    ob = bpy.data.objects[C["ob"]]
    import bmesh
    bm = bmesh.from_edit_mesh(ob.data)
    top = max(v.co.z for v in bm.verts)
    for v in bm.verts:
        v.select = abs(v.co.z - top) < 1e-6
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    region3d().tag_redraw()


_drag_steps("edit_vertices")


run()
