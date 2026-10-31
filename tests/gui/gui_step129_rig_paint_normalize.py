"""#20: , from the audit 128 repro: Maya skinClusters normalize weights interactively (normalizeWeights 1, the Bind
Skin default), so painting joint3 with Replace 1.0 makes the painted vertices follow joint3 only (joint1 drops to 0)
and Flood Replace 1.0 assigns every vertex to joint3. In the kit, Skin > Paint Skin Weights paints with Blender's
Auto Normalize off (tool_settings.use_auto_normalize is False in the factory scene and in the Maya Workflow Kit template)
and the dock's Flood button is paint.weight_set, which never normalizes: joint1 keeps its weight, the vertex sum
goes above 1 and the Armature modifier blends 50/50 instead of following the painted joint.
Each check PASSES once painted / flooded vertices stay normalized (sum 1, painted joint 1.0)."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 200
C = {}


def mod(name):
    return import_module(MODULE + name)


def main_view():
    toolbox = mod(".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def screen_of(world):
    _area, r = main_view()
    p = view3d_utils.location_3d_to_region_2d(r, r.data, world)
    return r.x + int(p.x), r.y + int(p.y)


def cyl():
    return bpy.data.objects["pCylinder1"]


def sums(indices=None):
    me = cyl().data
    vs = me.vertices if indices is None else [me.vertices[i] for i in indices]
    return [sum(g.weight for g in v.groups) for v in vs]


def weight_of(name, indices):
    c = cyl()
    vg = c.vertex_groups[name]
    out = []
    for i in indices:
        out.append(next((g.weight for g in c.data.vertices[i].groups if g.group == vg.index), 0.0))
    return out


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
        bmesh.ops.subdivide_edges(bm, edges=vertical, cuts=9, use_grid_fill=True)
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
        bpy.ops.allset.paint_skin_weights()
    C["k"] = k
    # front-facing vertices low on the cylinder (joint1's zone)
    me = c.data
    C["low"] = [i for i, v in enumerate(me.vertices) if v.co.y < -0.9 * k and v.co.z < -0.5 * k]
    check(f"bound and painting ({bpy.context.mode}), auto normalize {bpy.context.scene.tool_settings.use_auto_normalize}",
          bpy.context.mode == 'PAINT_WEIGHT')


@step
def s_pick_joint3():
    c = cyl()
    c.vertex_groups.active_index = c.vertex_groups["joint3"].index
    k = C["k"]
    C["stroke"] = [screen_of(Vector((x * k, -k, z * k))) for z in (-0.9, -0.75, -0.6) for x in (-0.7, -0.3, 0.0, 0.3, 0.7)]
    x, y = C["stroke"][0]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_press():
    x, y = C["stroke"][0]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_move():
    for x, y in C["stroke"][1:]:
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_release():
    x, y = C["stroke"][-1]
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_painted():
    low = C["low"]
    w3 = weight_of("joint3", low)
    painted = [i for i, w in zip(low, w3) if w > 0.5]
    s = sums(painted)
    check(f"painted {len(painted)}/{len(low)} low vertices with joint3; their weight sums stay 1 like Maya "
          f"(max sum {max(s) if s else 0:.3f}, joint1 left {max(weight_of('joint1', painted)) if painted else 0:.3f})",
          painted and max(s) < 1.001)
    area, r = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=r):
        bpy.ops.allset.flood_weights()       # the dock's Flood button (ui/paint_weights.FLOOD_OP)


@step
def s_flooded():
    s = sums()
    w3 = weight_of("joint3", range(len(cyl().data.vertices)))
    check(f"Flood (Replace 1.0, joint3) = every vertex joint3 only, normalized (max sum {max(s):.3f}, "
          f"min joint3 {min(w3):.3f})", max(s) < 1.001 and min(w3) > 0.999)


run()
