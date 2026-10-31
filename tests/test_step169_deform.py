"""Deform completion — the kit wire deformer like Maya's (translate / rotate / twist / scale / CV edit /
envelope / dropoff / dropoff locators), Wire edit items, ShrinkWrap target edits, Lattice reset / remove tweaks,
Prune Membership, Point On Curve, Paint Weights windows, Deform >= 60 %, no "Blender has no settings" box left.
"""

import importlib.util
import os
from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
deformers = import_module(kit.MODULE + ".operators.deformers")
wire = import_module(kit.MODULE + ".operators.wire_deformer")
deform_edit = import_module(kit.MODULE + ".operators.deform_edit")
option_windows = import_module(kit.MODULE + ".operators.option_windows")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
notices = import_module(kit.MODULE + ".ui.notices")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.lattices):
        for d in list(coll):
            coll.remove(d)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'METERS', 1.0      # maya_unit() = 1


def _select(*obs, active=None):
    for o in bpy.context.scene.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = active or (obs[-1] if obs else None)


def _plane():
    me = bpy.data.meshes.new("pPlaneShape1")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=40, y_segments=40, size=5.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("pPlane1", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _curve(z=0.0, name="curve1"):
    cu = bpy.data.curves.new(name + "Shape", 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('NURBS')
    sp.points.add(3)
    for p, x in zip(sp.points, (-5, -5 / 3, 5 / 3, 5)):
        p.co = (x, 0, z, 1)
    sp.order_u = 4
    sp.use_endpoint_u = True
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _make(dropoff=1.0, z=0.0):
    _clear()
    p = _plane()
    c = _curve(z)
    _select(p, c, active=c)
    assert bpy.ops.allset.deformer(kind='WIRE') == {'FINISHED'}
    md = p.modifiers["wire1"]
    if dropoff != 1.0:
        wire.set_(md, "Dropoff Distance", dropoff)
    return p, c, md


def _displacements(p):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = p.evaluated_get(dg).to_mesh()
    out = {tuple(round(x, 4) for x in v.co): me.vertices[i].co - v.co for i, v in enumerate(p.data.vertices)}
    p.evaluated_get(dg).to_mesh_clear()
    return out


# --- the wire like Maya's --------------------------------------------------------------------------------------

def test_wire_made_like_maya():
    p, c, md = _make()
    assert md.type == 'NODES' and deformers.base_of(md) == "wire" and deformers.node_type(md) == "wire"
    assert "wire1" in p.vertex_groups                                  # Maya weights 1 on every point
    base = bpy.data.objects.get("curve1BaseWire")
    assert base is not None and wire.get(md, "Base Wire") == base and not base.visible_get()
    assert bpy.context.view_layer.objects.active == c and c.select_get() and not p.select_get()  # Maya: curve1
    vals = {a.key: round(a.get(md), 6) for a in deformers.attrs(md)}
    assert vals == {"envelope": 1.0, "rotation": 1.0, "dropoffDistance[0]": 1.0}, vals
    assert all(v.length < 1e-6 for v in _displacements(p).values())  # nothing moves until the curve does


def test_wire_weights_scale_the_pull():
    p, c, md = _make()
    vg = p.vertex_groups["wire1"]
    vg.add([v.index for v in p.data.vertices if v.co.x > 0], 0.5, 'REPLACE')
    c.location = (0, 0, 1)
    got = _displacements(p)
    assert abs(got[(-2.5, 0.0, 0.0)].z - 1.0) < 1e-4 and abs(got[(2.5, 0.0, 0.0)].z - 0.5) < 1e-4


# --- wire edit items -------------------------------------------------------------------------------------------------

def test_wire_reset_show_base_parent_remove():
    p, c, md = _make()
    c.location = (0, 0, 1)
    _select(c)
    assert bpy.ops.allset.wire_edit(action='RESET') == {'FINISHED'}
    assert c.location.length < 1e-9
    assert all(v.length < 1e-6 for v in _displacements(p).values())        # Maya: the plane is back at rest
    _select(c)
    assert bpy.ops.allset.wire_edit(action='SHOW_BASE') == {'FINISHED'}
    base = bpy.data.objects["curve1BaseWire"]
    assert base.visible_get() and base.select_get() and c.select_get()      # Maya: curve1, curve1BaseWire
    _select(c)
    assert bpy.ops.allset.wire_edit(action='PARENT_BASE') == {'FINISHED'}
    assert base.parent == c
    c.location = (0, 0, 1)                                                   # both move: nothing deforms
    assert all(v.length < 1e-6 for v in _displacements(p).values())
    _select(c)
    assert bpy.ops.allset.wire_edit(action='REMOVE') == {'FINISHED'}
    assert "wire1" not in p.modifiers and "curve1BaseWire" not in bpy.data.objects
    assert "curve1" in bpy.data.objects                                      # Maya keeps the curve
    _select(p)
    assert bpy.ops.allset.wire_edit(action='RESET') == {'CANCELLED'}       # "Must select wire curves to be reset."


def test_wire_add_second_curve():
    p, c, md = _make()
    c2 = _curve(0.0, "curve2")
    c2.location = (0, 3, 0)
    _select(c2, c, active=c)
    assert bpy.ops.allset.wire_edit(action='ADD') == {'FINISHED'}
    extra = p.modifiers["wire1curve2"]
    assert wire.get(extra, "Wire") == c2 and "curve2BaseWire" in bpy.data.objects
    c2.location = (0, 3, 1)
    got = _displacements(p)
    assert abs(got[(0.0, 3.0, 0.0)].z - 1.0) < 1e-4 and abs(got[(0.0, 0.0, 0.0)].z) < 1e-6


# --- ShrinkWrap / Lattice / Prune / Point On Curve -------------------------------------------------------------------

def _cube(name, size=1.0):
    me = bpy.data.meshes.new(name + "Shape")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def test_shrink_wrap_edits():
    _clear()
    a, b, t2 = _cube("pCube1"), _cube("pSphere1", 4.0), _cube("pCube2", 3.0)
    _select(a, b, active=b)
    assert bpy.ops.allset.deformer(kind='SHRINK_WRAP') == {'FINISHED'}
    md = a.modifiers["shrinkWrap1"]
    _select(a, t2, active=t2)
    assert bpy.ops.allset.shrink_wrap_edit(action='SET_TARGET') == {'FINISHED'}
    assert md.target == t2
    c = _cube("pCube3")
    _select(c, t2, active=t2)
    assert bpy.ops.allset.shrink_wrap_edit(action='ADD_SURFACES') == {'FINISHED'}
    assert c.modifiers["shrinkWrap1"].target == t2 and "shrinkWrap1" in c.vertex_groups
    _select(c, t2, active=t2)
    assert bpy.ops.allset.shrink_wrap_edit(action='REMOVE_SURFACES') == {'FINISHED'}
    assert "shrinkWrap1" not in c.modifiers
    _select(a, t2, active=t2)
    assert bpy.ops.allset.shrink_wrap_edit(action='REMOVE_TARGET') == {'FINISHED'}
    assert md.target is None


def test_lattice_reset_and_remove_tweaks():
    _clear()
    cube = _cube("pCube1", 2.0)
    _select(cube)
    assert bpy.ops.allset.deformer(kind='LATTICE') == {'FINISHED'}
    lob = bpy.data.objects["ffd1Lattice"]
    rest = lob.matrix_world.copy()
    lob.data.points[-1].co_deform = Vector(lob.data.points[-1].co) + Vector((0, 0, 0.3))
    lob.location.z += 0.5
    _select(lob)
    assert bpy.ops.allset.lattice_edit(action='REMOVE_TWEAKS') == {'FINISHED'}
    assert all((Vector(pt.co_deform) - Vector(pt.co)).length < 1e-9 for pt in lob.data.points)
    assert abs(lob.matrix_world.translation.z - rest.translation.z - 0.5) < 1e-6   # Maya: the transform stays
    lob.data.points[0].co_deform = Vector(lob.data.points[0].co) + Vector((0, 0, 0.3))
    assert bpy.ops.allset.lattice_edit(action='RESET') == {'FINISHED'}
    assert (lob.matrix_world.translation - rest.translation).length < 1e-6
    assert all((Vector(pt.co_deform) - Vector(pt.co)).length < 1e-9 for pt in lob.data.points)


def test_prune_membership():
    _clear()
    cube = _cube("pCube1")
    _select(cube)
    assert bpy.ops.allset.cluster() == {'FINISHED'}
    vg = cube.vertex_groups["cluster1"]
    vg.add([0, 1, 2], 0.0, 'REPLACE')
    _select(cube)
    assert bpy.ops.allset.prune_membership(kind="cluster") == {'FINISHED'}
    members = [v.index for v in cube.data.vertices if any(g.group == vg.index for g in v.groups)]
    assert members == [3, 4, 5, 6, 7], members
    _select(cube)
    assert bpy.ops.allset.prune_membership(kind="cluster") == {'CANCELLED'}   # "No components could be pruned."


def test_point_on_curve():
    _clear()
    c = _curve()
    _select(c)
    bpy.ops.object.mode_set(mode='EDIT')
    for i, pt in enumerate(c.data.splines[0].points):
        pt.select = i == 2
    assert bpy.ops.allset.point_on_curve() == {'FINISHED'}
    loc = bpy.context.view_layer.objects.active
    assert loc.name == "locator1" and (loc.location - Vector((5 / 3, 0, 0))).length < 1e-6
    loc.location.z += 1.0
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = c.evaluated_get(dg)
    zs = [v.co.z for v in ev.to_mesh().vertices]                  # the evaluated curve (hooks applied)
    ev.to_mesh_clear()
    assert zs and 0.2 < max(zs) < 1.0, max(zs or [0])                # the curve bends up towards locator1


# --- menus / option boxes ------------------------------------------------------------------------------------------

def test_paint_weights_windows_and_wire_paint():
    for label in ("Blend Shape", "Cluster", "Delta Mush", "Proximity Wrap", "Lattice", "ShrinkWrap", "Wire",
                  "Nonlinear", "Texture Deformer", "Set Membership"):
        # Maya's menus have Paint Weights > Set Membership under Deform > Paint Membership
        path = "Deform/Paint Membership" if label == "Set Membership" else f"Deform/Paint Weights/{label}"
        w = option_windows.find_path(path)
        assert w is not None and w.title in ("Paint Attributes Tool", "Paint Blend Shape Weights Tool"), path
        assert menu_sets.option_kind(path) == "window", path
    p, c, md = _make()
    _select(c)
    assert bpy.ops.allset.paint_deformer_weights(kind="wire") == {'FINISHED'}
    assert bpy.context.mode == 'PAINT_WEIGHT' and p.vertex_groups.active.name == "wire1"
    bpy.ops.object.mode_set(mode='OBJECT')


def test_deform_option_boxes_and_count():
    spec = importlib.util.spec_from_file_location("tool_menu_count", os.path.join(ROOT, "tools", "menu_count.py"))
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    md_ = import_module(kit.MODULE + ".ui.menu_data")
    _label, _set, _src, items = md_.MENUS["mainDeformMenu"]
    paths = [p for p, _it in mc.leaves(md_, menu_map, items, "Deform")]
    working = sum(1 for p in paths if p in menu_map.MAP)
    kinds = {}
    for p in paths:
        if p in md_.OPTION_BOXES:
            k = menu_sets.option_kind(p) if p in menu_map.MAP else "dead"
            kinds.setdefault(k, []).append(p)
    print(f"Deform: {working} / {len(paths)} working ({100 * working / len(paths):.0f} %); boxes "
          + ", ".join(f"{k} {len(v)}" for k, v in sorted(kinds.items())))
    print("dead:", kinds.get("dead"))
    # Maya's menus include the 70-item Maya Muscle plug-in submenu: a separate legacy muscle system the
    # kit explains with notices (rare Maya systems get a notice, not a re-implementation), so the
    # working share is counted without it; every greyed Muscle item still needs a notice below.
    core = [p for p in paths if not p.startswith("Deform/Muscle/")]
    working = sum(1 for p in core if p in menu_map.MAP)
    assert working / len(core) >= 0.60, (working, len(core))
    assert not kinds.get("generic"), kinds.get("generic")
    assert len(kinds.get("dead", ())) <= 12, kinds.get("dead")
    for p in paths:
        if p not in menu_map.MAP:
            assert notices.greyed_notice(p), p
