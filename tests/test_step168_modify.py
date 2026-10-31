"""Modify menu — Smooth Mesh Preview to Polygons applies only the kit preview (skinCluster1 stays),
Default Object Manipulator / Show Manipulator Tool, Align Tool, Position Along Curve, Geometry to Bounding Box (+ its
Maya option window), Evaluate Nodes check items, Modify menu >= 60 % working, following Maya's rules.
"""

import importlib.util
import os
from importlib import import_module

import bpy
from mathutils import Matrix, Vector

import kit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
display = import_module(kit.MODULE + ".operators.display")
joints = import_module(kit.MODULE + ".operators.joints")
modify = import_module(kit.MODULE + ".operators.modify_maya")
option_windows = import_module(kit.MODULE + ".operators.option_windows")
driven_key = import_module(kit.MODULE + ".operators.driven_key")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.curves, bpy.data.materials, bpy.data.particles):
        for d in list(coll):
            coll.remove(d)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'METERS', 1.0


def _select(*obs, active=None):
    for o in bpy.context.scene.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = active or (obs[-1] if obs else None)


def _cube(name="pCube1", size=1.0, location=(0, 0, 0)):
    me = bpy.data.meshes.new(name + "Shape")
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = location
    return ob


def _skinned():
    """A 1 x 1 x 4 box with 4 height segments bound to a two-bone chain (Maya Bind Skin -> skinCluster1)."""
    import bmesh
    me = bpy.data.meshes.new("pCubeShape1")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(1, 1, 4), verts=bm.verts)
    edges = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1e-6]
    bmesh.ops.subdivide_edges(bm, edges=edges, cuts=3, use_grid_fill=True)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("pCube1", me)
    bpy.context.scene.collection.objects.link(ob)
    arm = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 0, -2), (0, 0, 0), (0, 0, 2)):
        parent = joints.add_joint(arm, Vector(p), parent, length=0.5)
    joints.finish(bpy.context, arm, ["joint1", "joint2", "joint3"])
    bpy.ops.object.mode_set(mode='OBJECT')
    _select(arm, ob, active=ob)
    assert bpy.ops.allset.bind_skin() == {'FINISHED'}
    return ob, arm


def _faces(ob):
    return len(ob.data.polygons)


def _eval_faces(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    n = len(me.polygons)
    ev.to_mesh_clear()
    return n


# --- Smooth Mesh Preview to Polygons ------------------------------------------------------------------------------

def test_skinned_mesh_keeps_skin_cluster_and_gets_four_to_the_level_faces():
    _clear()
    ob, arm = _skinned()
    base = _faces(ob)
    skin_names = [m.name for m in ob.modifiers if m.type == 'ARMATURE']
    assert skin_names == ["skinCluster1"], [m.name for m in ob.modifiers]
    display.set_smooth_preview(ob, 3)                     # level 2 (default)
    assert _eval_faces(ob) == base * 16
    _select(ob)
    assert bpy.ops.allset.smooth_to_polygons() == {'FINISHED'}
    assert _faces(ob) == base * 4 ** 2, (_faces(ob), base)
    names = [m.name for m in ob.modifiers]
    assert names == ["skinCluster1"], names               # only the preview modifiers were applied
    assert not any(display.is_preview(m) for m in ob.modifiers)
    assert {g.name for g in ob.vertex_groups} >= {"joint1", "joint2"}
    # the skin still deforms the converted mesh (Maya: polySmoothFace1 after skinCluster1)
    top = max(range(len(ob.data.vertices)), key=lambda i: ob.data.vertices[i].co.z)
    dg = bpy.context.evaluated_depsgraph_get()
    rest = ob.evaluated_get(dg).to_mesh().vertices[top].co.copy()
    ob.evaluated_get(dg).to_mesh_clear()
    bpy.context.view_layer.objects.active = arm
    pb = arm.pose.bones[1]
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler = (0.8, 0.0, 0.0)     # bend (local Y runs along the bone)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    posed = ob.evaluated_get(dg).to_mesh().vertices[top].co.copy()
    ob.evaluated_get(dg).to_mesh_clear()
    assert (posed - rest).length > 0.1, (rest, posed)
    assert len(ob.evaluated_get(dg).data.polygons) == base * 16


def test_level_one_and_three_and_other_history_stays():
    _clear()
    for level in (1, 3):
        ob = _cube(f"pCube{level}")
        bev = ob.modifiers.new("polyBevel1", 'BEVEL')         # history before the preview stays history
        display.set_smooth_preview(ob, 3)
        display.preview_modifier(ob, False).levels = level
        _select(ob)
        assert bpy.ops.allset.smooth_to_polygons() == {'FINISHED'}
        assert _faces(ob) == 6 * 4 ** level, (level, _faces(ob))
        assert [m.name for m in ob.modifiers] == [bev.name]
    # display mode 2 (cage + smooth) converts too and its wireframe goes
    ob = _cube("pCube9")
    display.set_smooth_preview(ob, 2)
    assert ob.show_wire
    _select(ob)
    assert bpy.ops.allset.smooth_to_polygons() == {'FINISHED'}
    assert _faces(ob) == 96 and not ob.show_wire


def test_no_preview_and_nothing_selected_warn_like_maya():
    _clear()
    plain = _cube("pCube1")
    hidden = _cube("pCube2")
    display.set_smooth_preview(hidden, 3)
    display.set_smooth_preview(hidden, 1)               # preview off (Maya displaySmoothMesh 0)
    _select(plain, hidden)
    assert bpy.ops.allset.smooth_to_polygons() == {'CANCELLED'}
    assert _faces(plain) == 6 and _faces(hidden) == 6
    assert display.preview_modifier(hidden, False) is not None   # the hidden preview keeps its level
    _select()
    assert bpy.ops.allset.smooth_to_polygons() == {'CANCELLED'}
    assert modify.WARN_NO_PREVIEW == "No polygonal objects selected were in smooth preview mode."
    assert modify.WARN_NO_POLYS == "No polygonal objects selected."
    # mixed: only the preview one converts (Maya 6 / 96)
    on = _cube("pCube3")
    display.set_smooth_preview(on, 3)
    _select(plain, on)
    assert bpy.ops.allset.smooth_to_polygons() == {'FINISHED'}
    assert (_faces(plain), _faces(on)) == (6, 96)


def test_menu_item_is_the_kit_command():
    assert menu_map.MAP["Modify/Convert/Smooth Mesh Preview to Polygons"] == "allset.smooth_to_polygons"


# --- Default Object Manipulator / Show Manipulator Tool ----------------------------------------------------------

def test_default_object_manipulator():
    _clear()
    a, b = _cube("pCube1"), _cube("pCube2")
    assert modify.show_manip_tool(a) == "builtin.transform"     # factory None = the kit's T tool
    _select(a, b)
    for value, tool in ((1, "builtin.move"), (2, "builtin.rotate"), (3, "builtin.scale"), (4, "builtin.transform")):
        assert bpy.ops.allset.default_manip(value=value) == {'FINISHED'}
        assert modify.manip_default(a) == modify.manip_default(b) == value
        assert modify.show_manip_tool(b) == tool
    assert bpy.ops.allset.default_manip(value=0) == {'FINISHED'}
    assert modify.MANIP_PROP not in a
    _select()
    assert bpy.ops.allset.default_manip(value=2) == {'CANCELLED'}       # "No objects selected."
    for i, label in enumerate(("None", "Move", "Rotate", "Scale", "Transform")):
        assert menu_map.MAP[f"Modify/Transformation Tools/Default Object Manipulator/{label}"][1] == {"value": i}


# --- Align Tool / Position Along Curve ------------------------------------------------------------------------------

def test_align_tool_aligns_to_the_last_selected():
    _clear()
    a = _cube("pCube1", location=(0, 0, 0))
    b = _cube("pCube2", size=2.0, location=(5, 3, 1))
    _select(a, b, active=b)
    assert bpy.ops.allset.align_to_lead(axis=0, mode='MIN') == {'FINISHED'}
    assert abs(a.location.x - 4.5) < 1e-6 and b.location.x == 5     # min x 4 = lead's min
    assert bpy.ops.allset.align_to_lead(axis=2, mode='MAX') == {'FINISHED'}
    assert abs(a.location.z - 1.5) < 1e-6                           # max z 2
    assert bpy.ops.allset.align_tool() == {'FINISHED'}              # popup (background: nothing to show)
    _select(a)
    assert bpy.ops.allset.align_tool() == {'CANCELLED'}


def _maya_curve():
    cu = bpy.data.curves.new("curveShape1", 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('NURBS')
    sp.points.add(3)
    for p, x in zip(sp.points, (0, 1, 3, 6)):
        p.co = (x, 0, 0, 1)
    sp.order_u = 4
    sp.use_endpoint_u = True
    ob = bpy.data.objects.new("curve1", cu)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def test_position_along_curve_uses_the_parameter_like_maya():
    _clear()
    crv = _maya_curve()
    obs = [_cube(f"pCube{i}", location=(0, 5, 0)) for i in (1, 2, 3)]
    obs[1].delta_location = (0.5, 0, 0)       # Maya pivot offset 0.5 (rotatePivot) -> translate 1.75
    _select(*obs, crv, active=crv)
    assert bpy.ops.allset.position_along_curve() == {'FINISHED'}
    # Maya: translations 0 / 1.75 / 6, i.e. pivots at the 0 / 50 / 100 % parameter points
    assert [round(ob.location.x, 6) for ob in obs] == [0.0, 1.75, 6.0], [tuple(ob.location) for ob in obs]
    assert all(abs(ob.location.y) < 1e-9 for ob in obs)
    _select(obs[0], crv, active=crv)
    try:                                                            # an ERROR report raises in Python
        bpy.ops.allset.position_along_curve()
    except RuntimeError as ex:
        assert modify.ERR_SELECTION in str(ex)
    else:
        raise AssertionError("two selected accepted")
    _select(*obs)
    try:
        modify.position_along_curve(obs)
    except ValueError as ex:
        assert str(ex) == modify.ERR_NO_CURVE
    else:
        raise AssertionError("no curve accepted")


# --- Geometry to Bounding Box ---------------------------------------------------------------------------------------

def _corners(ob):
    return sorted(tuple(round(c, 5) for c in v.co) for v in ob.data.vertices)


def test_geometry_to_bounding_box_like_maya():
    _clear()
    a = _cube("pCube1")
    a.scale = (1, 1, 1)
    a.data.transform(Matrix.Diagonal((2, 1, 1, 1)))
    a.location = (3, 0, 0)
    a.rotation_euler = (0, 0, 0.785398)
    bpy.context.view_layer.update()
    mw = a.matrix_world.copy()
    _select(a)
    assert bpy.ops.allset.geometry_to_bbox() == {'FINISHED'}
    box = bpy.data.objects["pCube1_BBox"]
    assert "pCube1" not in bpy.data.objects                       # replaced (Keep original off)
    assert len(box.data.vertices) == 8 and len(box.data.polygons) == 6
    assert _corners(box)[0] == (-1.0, -0.5, -0.5) and _corners(box)[-1] == (1.0, 0.5, 0.5)
    assert all(abs(box.matrix_world[i][j] - mw[i][j]) < 1e-5 for i in range(4) for j in range(4))
    mat = box.data.materials[0]
    assert mat.name == "BBoxLambert1"
    node = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    assert tuple(round(c, 4) for c in node.inputs["Base Color"].default_value[:3]) == (0.5, 0.5, 0.5)
    assert bpy.context.view_layer.objects.active is box and box.select_get()
    # a hierarchy -> one world box, identity transform
    _clear()
    grp = bpy.data.objects.new("grp", None)
    bpy.context.scene.collection.objects.link(grp)
    c = _cube("pCube1", location=(3, 0, 0))
    s = _cube("pSphere1", location=(0, 0, 2))
    c.parent = s.parent = grp
    _select(grp)
    assert bpy.ops.allset.geometry_to_bbox(keep_original=True) == {'FINISHED'}
    gb = bpy.data.objects["grp_BBox"]
    assert gb.matrix_world == Matrix.Identity(4)
    assert _corners(gb)[0] == (-0.5, -0.5, -0.5) and _corners(gb)[-1] == (3.5, 0.5, 2.5)
    assert "pCube1" in bpy.data.objects                          # Keep original
    # one box per shape
    _select(grp)
    assert bpy.ops.allset.geometry_to_bbox(per_shape=True) == {'FINISHED'}
    assert {"pCube1_BBox", "pSphere1_BBox"} <= set(bpy.data.objects.keys())
    assert "grp" not in bpy.data.objects and "pCube1" not in bpy.data.objects


def test_geometry_to_bbox_option_window():
    w = option_windows.find_path("Modify/Convert/Geometry to Bounding Box")
    assert w is not None and w.title == "Convert Geometry to Bounding Box Options" and w.action == "Convert"
    assert w.defaults() == {"name": "", "suffix": "_BBox", "hierarchy": "One bounding box",
                            "colour": (0.5, 0.5, 0.5), "keep_original": False}
    assert hasattr(bpy.ops.allset, "opt_geom_to_bbox")
    _clear()
    _cube("pCube1")
    _select(bpy.data.objects["pCube1"])
    res = option_windows.run(w, bpy.context, {"suffix": "_box", "keep_original": True})
    assert res == {'FINISHED'} and "pCube1_box" in bpy.data.objects and "pCube1" in bpy.data.objects


# --- Evaluate Nodes -------------------------------------------------------------------------------------------------

def test_evaluate_nodes_switches():
    _clear()
    scene = bpy.context.scene
    ev = scene.allset_eval
    arm = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 0, 0), (0, 0, 2), (0, 0, 4)):
        parent = joints.add_joint(arm, Vector(p), parent, length=0.5)
    joints.finish(bpy.context, arm, ["joint1", "joint2", "joint3"])
    bpy.ops.object.mode_set(mode='OBJECT')
    target = bpy.data.objects.new("ikHandle1", None)
    scene.collection.objects.link(target)
    pb = arm.pose.bones[-1]
    ik = pb.constraints.new('IK')
    ik.target = target
    ik2 = arm.pose.bones[0].constraints.new('IK')
    ik2.mute = True                                     # the user's own solverEnable off
    a, b = _cube("pCube1"), _cube("pCube2")
    con = a.constraints.new('COPY_LOCATION')
    con.target = b
    fc = a.driver_add("location", 2)
    fc.driver.expression = "frame"
    sdk = b.driver_add("location", 1)
    sdk.driver.variables.new().name = driven_key.VAR
    cloth = a.modifiers.new("nCloth1", 'CLOTH')
    ps_mod = b.modifiers.new("nParticle1", 'PARTICLE_SYSTEM')
    ps_mod.particle_system.settings.name = "nParticle1"
    other = a.modifiers.new("particle1", 'PARTICLE_SYSTEM')
    col = b.modifiers.new("nRigid1", 'COLLISION')
    _select(a)
    bpy.ops.rigidbody.world_add()
    assert scene.rigidbody_world is not None

    ev.iksolver = False
    assert ik.mute and ik2.mute
    ev.iksolver = True
    assert not ik.mute and ik2.mute                      # only the ones the kit muted come back
    ev.constraint = False
    assert con.mute and not ik.mute
    ev.constraint = True
    assert not con.mute
    ev.expression = False
    assert fc.mute and not sdk.mute                      # Set Driven Key is a Maya animCurve
    ev.expression = True
    assert not fc.mute
    ev.ncloth = False
    assert not cloth.show_viewport and not cloth.show_render
    ev.nparticle = False
    assert not ps_mod.show_viewport and other.show_viewport
    ev.particle = False
    assert not other.show_viewport
    ev.nrigid = False
    assert not b.collision.use
    ev.rigidbody = False
    assert not scene.rigidbody_world.enabled
    assert bpy.ops.allset.evaluate_all(on=True) == {'FINISHED'}
    assert all(getattr(ev, k) for k in modify.KINDS)
    assert cloth.show_viewport and ps_mod.show_viewport and other.show_viewport and b.collision.use
    assert scene.rigidbody_world.enabled
    assert bpy.ops.allset.evaluate_all(on=False) == {'FINISHED'}
    assert not any(getattr(ev, k) for k in modify.KINDS)
    assert ik.mute and con.mute and fc.mute and not cloth.show_viewport
    bpy.ops.allset.evaluate_all(on=True)
    assert not ik.mute and ik2.mute and not con.mute


def test_evaluate_nodes_menu_items():
    for label in ("IK Solvers", "Constraints", "Expressions", "Fluids", "nCloths", "nParticles", "nRigids",
                  "Particles", "Rigid Bodies", "Snapshots"):       # Snapshots too
        kind, target, _props = menu_map.normalize(menu_map.MAP[f"Modify/Evaluate Nodes/{label}"])
        assert kind == "prop" and target.startswith("scene.allset_eval."), (label, target)
    assert menu_map.MAP["Modify/Evaluate Nodes/Ignore All"] == ("allset.evaluate_all", {"on": False})
    for label in ("Dynamic Constraints", "Global Stitch", "nucleuses"):
        path = f"Modify/Evaluate Nodes/{label}"
        assert path not in menu_map.MAP and notices.greyed_notice(path), path


# --- menu count -----------------------------------------------------------------------------------------------------

def test_modify_menu_at_least_sixty_percent():
    spec = importlib.util.spec_from_file_location("tool_menu_count", os.path.join(ROOT, "tools", "menu_count.py"))
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    md = import_module(kit.MODULE + ".ui.menu_data")
    _label, _set, _src, items = md.MENUS["mainModifyMenu"]
    paths = [p for p, _it in mc.leaves(md, menu_map, items, "Modify")]
    working = sum(1 for p in paths if p in menu_map.MAP)
    print(f"Modify: {working} / {len(paths)} working ({100 * working / len(paths):.0f} %)")
    assert working / len(paths) >= 0.60, (working, len(paths))
