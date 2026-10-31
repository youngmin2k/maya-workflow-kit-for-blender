"""Modeling / rigging commands and their expected results.
Maya Y-up -> Blender Z-up: Maya (x, y, z) = Blender (x, -z, y).
"""

import importlib.util
import math
import os
from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

poly = import_module(kit.MODULE + ".operators.poly_maya")
rig = import_module(kit.MODULE + ".operators.rig_maya")
menu_items = import_module(kit.MODULE + ".operators.menu_items")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_data = import_module(kit.MODULE + ".ui.menu_data")
notices = import_module(kit.MODULE + ".ui.notices")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.curves):
        for d in list(coll):
            coll.remove(d)


def _grid(n, size):
    """(n+1)^2 vertices in the XY plane, centred, like Maya polyPlane -sx n -sy n (vertex order row by row)."""
    bm = bmesh.new()
    step = size / n
    vs = [[bm.verts.new((-size / 2 + i * step, -size / 2 + j * step, 0.0)) for i in range(n + 1)] for j in range(n + 1)]
    for j in range(n):
        for i in range(n):
            bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
    bm.verts.index_update()
    bm.faces.index_update()
    return bm, vs


def _close(a, b, tol=1e-3):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# --- Circularize ------------------------------------------------------------------------------

def test_circularize_matches_maya():
    bm, vs = _grid(4, 4.0)
    inner = [f for f in bm.faces if all(abs(v.co.x) <= 1.0001 and abs(v.co.y) <= 1.0001 for v in f.verts)]
    assert len(inner) == 4
    for f in inner:
        f.select = True
    assert poly.circularize_loops(bm, 'FACE') == 1
    border = [v for f in inner for v in f.verts if (abs(v.co.x) > 1e-6 or abs(v.co.y) > 1e-6)]
    radii = {round(v.co.xy.length, 4) for v in border}
    assert radii == {1.2071}, radii                       # mean distance 1.2071
    got = sorted((round(v.co.x, 4), round(v.co.y, 4)) for v in set(border))
    want = sorted([(-0.8536, 0.8536), (0.0, 1.2071), (0.8536, 0.8536), (-1.2071, 0.0), (1.2071, 0.0),
                   (-0.8536, -0.8536), (0.0, -1.2071), (0.8536, -0.8536)])
    assert all(_close(a, b) for a, b in zip(got, want)), got
    assert vs[2][2].co.length < 1e-9                      # the centre vertex stays (Maya too)
    assert len(bm.verts) == 25 and len(bm.faces) == 16    # topology unchanged
    bm.free()


def test_circularize_edges_and_object_mode():
    bm, vs = _grid(4, 4.0)
    ring = [vs[1][1], vs[1][2], vs[1][3], vs[2][3], vs[3][3], vs[3][2], vs[3][1], vs[2][1]]
    for a, b in zip(ring, ring[1:] + ring[:1]):
        bm.edges.get((a, b)).select = True
    assert poly.circularize_loops(bm, 'EDGE') == 1
    assert {round(v.co.xy.length, 4) for v in ring} == {1.2071}
    bm.free()
    bm, _vs = _grid(2, 2.0)
    assert poly.circularize_loops(bm, 'ALL') == 1         # object mode: the mesh border
    bm.free()


# --- Edit Edge Flow ---------------------------------------------------------------------------

def _maya_sphere(n=8, rows=8):
    bm = bmesh.new()
    ring = {}
    for k in range(1, rows):
        th = math.pi * k / rows
        for i in range(n):
            ph = 2 * math.pi * i / n
            ring[k, i] = bm.verts.new((math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), -math.cos(th)))
    s, top = bm.verts.new((0, 0, -1)), bm.verts.new((0, 0, 1))
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((s, ring[1, j], ring[1, i]))
        bm.faces.new((top, ring[rows - 1, i], ring[rows - 1, j]))
        for k in range(1, rows - 1):
            bm.faces.new((ring[k, i], ring[k, j], ring[k + 1, j], ring[k + 1, i]))
    return bm, ring


def test_edge_flow_close_to_maya():
    bm, ring = _maya_sphere()
    eq = [ring[4, i] for i in range(8)]
    for v in eq:
        v.co.x *= 0.7
        v.co.y *= 0.7
    edges = [bm.edges.get((eq[i], eq[(i + 1) % 8])) for i in range(8)]
    assert menu_items.edge_flow(bm, edges) == 8
    radii = [v.co.xy.length for v in eq]
    print("edge flow radius", radii[0], "expected 0.9983")
    assert all(abs(r - 0.9983) < 0.005 for r in radii), radii
    assert all(abs(v.co.z) < 1e-6 for v in eq)
    bm.free()


def test_edge_flow_straight_stays_straight():
    bm, vs = _grid(4, 4.0)
    mid = [vs[2][i] for i in range(5)]
    edges = [bm.edges.get((mid[i], mid[i + 1])) for i in range(4)]
    before = [v.co.copy() for v in mid]
    menu_items.edge_flow(bm, edges)
    assert all((v.co - b).length < 1e-6 for v, b in zip(mid, before))
    bm.free()


# --- Connect / Make Hole ----------------------------------------------------------------------

def _cube():
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.ensure_lookup_table()
    return bm


def test_connect_two_opposite_edges():
    bm = _cube()
    face = bm.faces[0]
    e0, e2 = face.edges[0], face.edges[2]
    e0.select = e2.select = True
    want = sorted(tuple(round(c, 4) for c in (a.co + b.co) / 2) for a, b in (e.verts for e in (e0, e2)))
    poly.connect(bm, 'EDGE')
    bm.verts.ensure_lookup_table()
    assert (len(bm.verts), len(bm.faces), len(bm.edges)) == (10, 7, 15)      # 10 / 7 / 15
    mids = sorted(tuple(round(c, 4) for c in v.co) for v in bm.verts[8:])
    assert mids == want, (mids, want)
    bm.free()


def test_connect_ring_and_vertices():
    bm = _cube()
    f = bm.faces[0]
    start = f.edges[0]
    ring, e, face = [start], start, f
    for _ in range(3):                                   # walk the edge ring around the cube
        loop = next(l for l in e.link_loops if l.face == face)
        e2 = loop.link_loop_next.link_loop_next.edge
        face = next(x for x in e2.link_faces if x != face)
        ring.append(e2)
        e = e2
    for e in set(ring):
        e.select = True
    poly.connect(bm, 'EDGE')
    assert (len(bm.verts), len(bm.faces)) == (12, 10)                       # 12 / 10
    bm.free()
    bm = _cube()
    f = bm.faces[0]
    f.verts[0].select = f.verts[2].select = True
    poly.connect(bm, 'VERT')
    assert (len(bm.verts), len(bm.faces)) == (8, 7)                          # Maya: face split
    bm.free()


def test_make_hole_bridges_the_stamp():
    bm = bmesh.new()
    outer = [bm.verts.new(c) for c in ((-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0))]
    inner = [bm.verts.new(c) for c in ((0, -0.75, 0.5), (1, -0.75, 0.5), (1, 0.25, 0.5), (0, 0.25, 0.5))]
    target, stamp = bm.faces.new(outer), bm.faces.new(inner)
    pos = [v.co.copy() for v in inner]
    faces = poly.make_hole(bm, target, stamp)
    assert len(bm.verts) == 8 and len(faces) == 4 and len(bm.faces) == 4
    assert all((v.co - p).length < 1e-9 for v, p in zip(inner, pos))        # mode 6: no move
    assert all(len(f.verts) == 4 for f in bm.faces)
    bm.free()


# --- Skeleton -----------------------------------------------------------------------------------

def _chain(points):
    """An armature of bones joint1..jointN from Maya joint positions (Maya xyz -> Blender x, -z, y)."""
    _fresh()
    data = bpy.data.armatures.new("skeleton")
    arm = bpy.data.objects.new("skeleton1", data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    pts = [Vector((x, -z, y)) for x, y, z in points]
    for k in range(len(pts) - 1):
        eb = data.edit_bones.new(f"joint{k + 1}")
        eb.head, eb.tail = pts[k], pts[k + 1]
        if prev is not None:
            eb.parent = prev
            eb.use_connect = True
        prev = eb
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
    return arm


def _joints(arm):
    mw = arm.matrix_world
    out = set()
    for b in arm.data.bones:
        out.add(tuple(round(c, 4) for c in mw @ b.head_local))
        out.add(tuple(round(c, 4) for c in mw @ b.tail_local))
    return out


def test_reroot_like_maya():
    arm = _chain([(0, 0, 0), (0, 5, 0), (5, 5, 0), (10, 5, 0)])
    before = _joints(arm)
    assert rig.reroot(arm, "joint3")
    bones = arm.data.bones
    assert bones["joint3"].parent is None and bones["joint2"].parent is None
    assert bones["joint1"].parent == bones["joint2"]
    # joint3 (Maya (5,5,0)) is where the roots start; the old root joint (0,0,0) is now a chain end
    j3 = Vector((5, 0, 5))
    assert (bones["joint3"].head_local - j3).length < 1e-5 and (bones["joint2"].head_local - j3).length < 1e-5
    assert bones["joint1"].tail_local.length < 1e-5
    assert _joints(arm) == before                                            # Maya: positions unchanged
    assert not rig.reroot(arm, "joint3")


def test_preferred_angle_set_and_assume():
    arm = _chain([(0, 0, 0), (0, 5, 0), (5, 5, 0), (10, 5, 0)])
    j2 = arm.pose.bones["joint2"]
    j2.rotation_euler = (0.0, 0.0, math.radians(30))
    rig.set_preferred([j2])
    assert [round(a, 4) for a in j2[rig.PREFERRED_PROP]] == [0.0, 0.0, 30.0]
    assert [round(a, 4) for a in arm.pose.bones["joint3"][rig.PREFERRED_PROP]] == [0.0, 0.0, 0.0]   # -ch
    j2.rotation_euler = (0.0, 0.0, 0.0)
    rig.assume_preferred([j2])
    assert abs(math.degrees(j2.rotation_euler.z) - 30.0) < 1e-4


def test_ik_spline_handle():
    maya = [(0, 0, 0), (0, 5, 0), (4.330127, 7.5, 0), (8.660254, 10, 0)]
    arm = _chain(maya)
    res = rig.create_spline_ik(bpy.context, arm, ("joint1", 'HEAD'), ("joint3", 'TAIL'))
    assert res is not None
    con, curve = res
    assert con.type == 'SPLINE_IK' and con.chain_count == 3 and con.target == curve
    assert con.name == "ikHandle1" and curve.name == "curve1"
    sp = curve.data.splines[0]
    assert sp.type == 'NURBS' and len(sp.points) == 4 and sp.order_u == 4 and sp.use_endpoint_u   # 1 span, cubic
    cv = [Vector(p.co[:3]) for p in sp.points]
    assert cv[0].length < 1e-6 and (cv[3] - Vector((8.660254, 0, 10))).length < 1e-5
    maya_mid = [Vector((-1.377, 0, 6.7578)), Vector((3.9399, 0, 6.8854))]
    print("IK spline middle CVs", [tuple(round(c, 3) for c in v) for v in cv[1:3]], "Maya",
          [tuple(v) for v in maya_mid])


# --- Skin --------------------------------------------------------------------------------------

def _skinned_plane():
    _fresh()
    bm, _vs = _grid(4, 4.0)
    me = bpy.data.meshes.new("pPlaneShape1")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("pPlane1", me)
    bpy.context.collection.objects.link(ob)
    data = bpy.data.armatures.new("skeleton")
    arm = bpy.data.objects.new("skeleton1", data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for name, h, t in (("joint1", (-2, 0, 0), (2, 0, 0)), ("joint2", (2, 0, 0), (3, 0, 0)),
                       ("joint3", (0, -3, 0), (0, -4, 0))):
        eb = data.edit_bones.new(name)
        eb.head, eb.tail = h, t
    bpy.ops.object.mode_set(mode='OBJECT')
    md = ob.modifiers.new("skinCluster1", 'ARMATURE')
    md.object = arm
    g1, g2 = ob.vertex_groups.new(name="joint1"), ob.vertex_groups.new(name="joint2")
    return ob, arm, g1, g2


def test_hammer_is_the_neighbour_average():
    ob, _arm, g1, g2 = _skinned_plane()
    # expected weights around vertex 12 (neighbours 7, 11, 13, 17)
    w = {12: (0.95, 0.05), 7: (0.9615, 0.0385), 17: (0.9615, 0.0385), 11: (1.0, 0.0), 13: (1.0, 0.0)}
    for i in range(25):
        a, b = w.get(i, (1.0, 0.0))
        g1.add([i], a, 'REPLACE')
        g2.add([i], b, 'REPLACE')
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    deform = bm.verts.layers.deform.verify()
    bm.verts[12].select = True
    assert rig.hammer(bm, deform, [g1.index, g2.index]) == 1
    got = bm.verts[12][deform]
    assert abs(got[g1.index] - 0.9808) < 1e-3 and abs(got[g2.index] - 0.0192) < 1e-3, dict(got)   # Maya
    bm.free()


def test_add_remove_unused_influence():
    ob, _arm, g1, g2 = _skinned_plane()
    g1.add(list(range(25)), 0.8, 'REPLACE')
    g2.add(list(range(25)), 0.2, 'REPLACE')
    # Lock weights, Default weight 0 (the factory add recomputes the weights by distance: test_step202_add_influence)
    assert rig.add_influence(ob, ["joint3"], lock=True) == ["joint3"]
    g3 = ob.vertex_groups["joint3"]
    assert all(g3.weight(i) == 0.0 for i in range(25))                     # weight 0
    assert abs(g1.weight(0) - 0.8) < 1e-6                                   # others unchanged
    assert rig.unused_influences(ob) == ["joint3"]
    assert rig.remove_influence(ob, ["joint2"]) == ["joint2"]
    assert abs(ob.vertex_groups["joint1"].weight(0) - 1.0) < 1e-6           # renormalised


# --- Deformers --------------------------------------------------------------------------------

def test_cluster_handle_at_component_centroid():
    _fresh()
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(3, 0, 0))
    cube = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(cube.data)
    for v in bm.verts:
        v.select = v.co.z > 0
    bm.select_flush(True)
    bmesh.update_edit_mesh(cube.data)
    assert bpy.ops.allset.cluster() == {'FINISHED'}
    h = bpy.data.objects["cluster1Handle"]
    md = cube.modifiers["cluster1"]
    assert md.type == 'HOOK' and md.object == h
    assert (h.location - Vector((3, 0, 0.5))).length < 1e-6                 # centroid (3, 0.5, 0), Maya Y-up
    h.location.z += 1.0
    bpy.context.view_layer.update()
    ev = cube.evaluated_get(bpy.context.evaluated_depsgraph_get())
    zs = sorted(round(v.co.z, 4) for v in ev.to_mesh().vertices)
    ev.to_mesh_clear()
    assert zs == [-0.5] * 4 + [1.5] * 4, zs                                  # only the cluster's points move
    bpy.context.view_layer.objects.active = cube
    cube.select_set(True)
    assert bpy.ops.allset.cluster() == {'FINISHED'}                        # object mode: whole object
    h2 = bpy.data.objects["cluster2Handle"]
    assert (h2.location - Vector((3, 0, 0))).length < 1e-6


def test_nonlinear_handle_like_maya():
    _fresh()
    bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=4, location=(1, 0, 2))
    cyl = bpy.context.active_object
    for method, name in (('BEND', "bend1"), ('TWIST', "twist1"), ('STRETCH', "squash1"), ('TAPER', "flare1")):
        _select = [cyl]
        for o in bpy.context.selected_objects:
            o.select_set(False)
        cyl.select_set(True)
        bpy.context.view_layer.objects.active = cyl
        assert bpy.ops.allset.nonlinear(method=method) == {'FINISHED'}
        h = bpy.data.objects[f"{name}Handle"]
        md = cyl.modifiers[name]
        assert md.deform_method == method and md.origin == h and md.deform_axis == 'Z'
        assert (h.location - Vector((1, 0, 2))).length < 1e-5                # Maya: bbox centre
        assert all(abs(s - 2.0) < 1e-5 for s in h.scale)                     # Maya: half the height
        assert md.angle == 0.0 and md.factor == 0.0                          # neutral values


def test_soft_mod_falloff_matches_maya():
    _fresh()
    bm, vs = _grid(10, 10.0)
    me = bpy.data.meshes.new("pPlaneShape1")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("pPlane1", me)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bme = bmesh.from_edit_mesh(me)
    for v in bme.verts:
        v.select = v.co.length < 1e-6
    bmesh.update_edit_mesh(me)
    assert bpy.ops.allset.soft_mod() == {'FINISHED'}
    h = bpy.data.objects["softMod1Handle"]
    md = ob.modifiers["softMod1"]
    assert md.falloff_type == 'CURVE' and abs(md.falloff_radius - 5.0) < 1e-6
    h.location.z += 1.0
    bpy.context.view_layer.update()
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    m = ev.to_mesh()
    height = {round(v.co.x, 3): v.co.z for v in m.vertices if abs(v.co.y) < 1e-6 and v.co.x >= -1e-6}
    ev.to_mesh_clear()
    maya = {0.0: 1.0, 1.0: 0.9045, 2.0: 0.6545, 3.0: 0.3455, 4.0: 0.0955, 5.0: 0.0}
    print("soft mod", {d: round(height[d], 4) for d in maya}, "Maya", maya)
    for d, want in maya.items():
        assert abs(height[d] - want) < 0.01, (d, height[d], want)


# --- menus ---------------------------------------------------------------------------------------

def _menu_count():
    spec = importlib.util.spec_from_file_location("menu_count110", os.path.join(ROOT, "tools", "menu_count.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.count(menu_data, menu_map, notices)


def test_menu_working_share_modeling_rigging():
    sets = _menu_count()["sets"]
    for label in ("Modeling", "Rigging"):
        c = sets[label]
        share = c["working"] / c["leaves"]
        print(label, c["working"], "/", c["leaves"], f"{share:.1%}")
        assert share >= 0.35, (label, share)
    for path in ("Edit Mesh/Circularize", "Mesh Tools/Connect", "Mesh Tools/Make Hole", "Skeleton/Reroot Skeleton",
                 "Skeleton/Set Preferred Angle", "Skeleton/Assume Preferred Angle", "Skeleton/Create IK Spline Handle",
                 "Skin/Hammer Skin Weights", "Skin/Edit Influences/Add Influence",
                 "Skin/Edit Influences/Remove Unused Influences", "Deform/Cluster", "Deform/Nonlinear/Twist",
                 "Deform/Soft Modification Tool"):
        assert path in menu_map.MAP, path
