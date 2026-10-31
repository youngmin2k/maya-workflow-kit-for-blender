"""Step 202 lane X (issue #109, audit 15 NB7-NB9): Delete Non-Deformer History keeps the kit's Geometry Nodes deformers
(wire, skin weight sum), deleting a Normal / Tangent constrained object or its constraints takes the hidden helper
empty with it, Select / Delete All by Type > Wires, nCloths, nParticles, nRigids act on the nodes the kit makes.
Maya: Non-Deformer History keeps deformers; Select / Delete All by Type
(SelectAllWires / SelectAllNCloths / SelectAllNParticles / SelectAllNRigids, DeleteAll*)."""

from importlib import import_module

import bmesh
import bpy

import kit

wire = import_module(kit.MODULE + ".operators.wire_deformer")
st = import_module(kit.MODULE + ".operators.skin_tools_199")
skin = import_module(kit.MODULE + ".operators.skin")
c199 = import_module(kit.MODULE + ".operators.constrain_199")
by_type = import_module(kit.MODULE + ".operators.by_type")
history = import_module(kit.MODULE + ".operators.history")
menu_map = import_module(kit.MODULE + ".ui.menu_map")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.armatures, bpy.data.particles):
        for d in list(coll):
            coll.remove(d)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'METERS', 1.0      # maya_unit() = 1
    c199.unregister_handlers()
    c199.register_handlers()


def _select(*obs, active=None):
    for o in bpy.context.scene.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = active or (obs[-1] if obs else None)


def _link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _cube(name="pCube1", size=4.0, location=(0, 0, 0)):
    me = bpy.data.meshes.new(name.replace("pCube", "pCubeShape"))
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.to_mesh(me)
    bm.free()
    ob = _link(bpy.data.objects.new(name, me))
    ob.location = location
    return ob


def _curve(name="curve1", z=2.0):
    cu = bpy.data.curves.new(name + "Shape", 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('NURBS')
    sp.points.add(3)
    for p, x in zip(sp.points, (-3, -1, 1, 3)):
        p.co = (x, 0, z, 1)
    sp.order_u = 4
    sp.use_endpoint_u = True
    return _link(bpy.data.objects.new(name, cu))


def _evaluated(ob):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    out = [v.co.copy() for v in me.vertices]
    ev.to_mesh_clear()
    return out


def _wire_bevel_cube():
    _clear()
    cube = _cube()
    bev = cube.modifiers.new("polyBevel1", 'BEVEL')
    bev.width = 0.2
    curve = _curve()
    _select(cube, curve, active=curve)
    assert bpy.ops.allset.deformer(kind='WIRE') == {'FINISHED'}
    md = cube.modifiers["wire1"]
    wire.set_(md, "Dropoff Distance", 10.0)
    assert [m.name for m in cube.modifiers] == ["polyBevel1", "wire1"]
    return cube, curve


def _check_wire_kept(cube, curve):
    assert [m.type for m in cube.modifiers] == ['NODES'], [m.name for m in cube.modifiers]
    md = cube.modifiers["wire1"]
    assert wire.is_wire(md), "the wire node must stay (Maya keeps deformers)"
    assert wire.get(md, "Wire") == curve and wire.get(md, "Base Wire") is not None
    assert len(cube.data.vertices) > 8, "the bevel is baked into the mesh"
    rest = [v.co.copy() for v in cube.data.vertices]
    before = _evaluated(cube)
    assert max((a - b).length for a, b in zip(rest, before)) < 1e-4, "an unmoved wire deforms nothing"
    curve.location.z += 1.0
    after = _evaluated(cube)
    moved = max((a - b).length for a, b in zip(rest, after))
    assert moved > 0.1, f"moving the wire curve must still deform the baked mesh ({moved})"


def test_non_deformer_history_keeps_the_wire():
    cube, curve = _wire_bevel_cube()
    _select(cube)
    assert bpy.ops.allset.delete_history(non_deformer=True) == {'FINISHED'}
    _check_wire_kept(cube, curve)


def test_non_deformer_history_before_only_keeps_the_wire():
    cube, curve = _wire_bevel_cube()
    _select(cube)
    assert bpy.ops.allset.delete_history(non_deformer=True, before_only=True) == {'FINISHED'}
    _check_wire_kept(cube, curve)


def test_full_delete_history_still_bakes_the_wire():
    cube, _curve_ob = _wire_bevel_cube()
    _select(cube)
    assert bpy.ops.allset.delete_history() == {'FINISHED'}
    assert not cube.modifiers, "Maya Delete History deletes the deformers too"


def test_is_deformer():
    cube, _c = _wire_bevel_cube()
    assert history.is_deformer(cube.modifiers["wire1"])
    assert not history.is_deformer(cube.modifiers["polyBevel1"])


def _armature():
    data = bpy.data.armatures.new("skeleton1")
    ob = _link(bpy.data.objects.new("skeleton1", data))
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    a = data.edit_bones.new("joint1")
    a.head, a.tail = (0, 0, -2), (0, 0, 0)
    b = data.edit_bones.new("joint2")
    b.head, b.tail = (0, 0, 0), (0, 0, 2)
    b.parent, b.use_connect = a, True
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def test_non_deformer_history_keeps_the_weight_sum():
    _clear()
    arm = _armature()
    cube = _cube()
    for name in ("joint1", "joint2"):
        cube.vertex_groups.new(name=name)
    for v in cube.data.vertices:
        cube.vertex_groups["joint1" if v.co.z < 0 else "joint2"].add([v.index], 0.6, 'REPLACE')
    md = cube.modifiers.new("skinCluster1", 'ARMATURE')
    md.object = arm
    bev = cube.modifiers.new("polyBevel1", 'BEVEL')
    bev.width = 0.2
    with bpy.context.temp_override(object=cube):
        bpy.ops.object.modifier_move_to_index(modifier="polyBevel1", index=0)
    st.set_normalize_mode(bpy.context, cube, "NONE")
    assert [m.name for m in cube.modifiers] == ["polyBevel1", "skinCluster1", "skinCluster1WeightSum"]
    _select(cube)
    assert bpy.ops.allset.delete_history(non_deformer=True) == {'FINISHED'}
    assert [m.name for m in cube.modifiers] == ["skinCluster1", "skinCluster1WeightSum"], \
        [m.name for m in cube.modifiers]
    assert st.is_part(cube.modifiers["skinCluster1WeightSum"])
    assert skin.normalize_mode(cube) == "NONE", "the normalization mode stays"
    assert len(cube.data.vertices) > 8
    # weight sum 0.6 under the skin: the evaluated points are scaled by 0.6 about the world origin (Maya, step 199)
    rest = [v.co.copy() for v in cube.data.vertices]
    ev = _evaluated(cube)
    assert max((e - r * 0.6).length for e, r in zip(ev, rest)) < 1e-3


def _helpers():
    return [o for o in bpy.data.objects if o.get(c199.KIND) in c199.LABEL]


def _plane(name="pPlane1"):
    me = bpy.data.meshes.new(name + "Shape")
    me.from_pydata([(-5, -5, 0), (5, -5, 0), (5, 5, 0), (-5, 5, 0)], [], [(0, 1, 2, 3)])
    return _link(bpy.data.objects.new(name, me))


def _constrained(n=2):
    _clear()
    plane = _plane()
    cubes = [_cube(f"pCube{i + 1}", 1.0, (i * 3.0, 0, 2)) for i in range(n)]
    for c in cubes:
        c199.add_surface_constraint(bpy.context, "normal", c, plane)
    assert len(_helpers()) == n
    return plane, cubes


def test_delete_constrained_object_deletes_its_helper():
    plane, (a, b) = _constrained()
    _select(a)
    assert bpy.ops.allset.delete() == {'FINISHED'}
    assert "pCube1" not in bpy.data.objects
    left = _helpers()
    assert [h.get(c199.OWNER) for h in left] == [b], "only the deleted object's helper goes"
    _select(b)
    assert bpy.ops.allset.delete() == {'FINISHED'}
    assert not _helpers()
    assert "pPlane1" in bpy.data.objects, "the surface stays"


def test_delete_constrained_object_with_its_helper_selected():
    plane, (a, b) = _constrained()
    own = [h for h in _helpers() if h.get(c199.OWNER) == a]
    with bpy.context.temp_override(selected_objects=[a, *own]):     # the helper is in the deleted set itself
        assert bpy.ops.allset.delete() == {'FINISHED'}
    assert [h.get(c199.OWNER) for h in _helpers()] == [b] and "pCube2" in bpy.data.objects


def test_delete_by_type_constraints_deletes_helpers():
    plane, (a, b) = _constrained()
    _select(a)
    assert bpy.ops.allset.menu_item(item="Edit/Delete by Type/Constraints") == {'FINISHED'}
    assert not a.constraints and [h.get(c199.OWNER) for h in _helpers()] == [b]
    assert bpy.ops.allset.menu_item(item="Edit/Delete All by Type/Constraints") == {'FINISHED'}
    assert not b.constraints and not _helpers()
    assert {"pCube1", "pCube2", "pPlane1"} <= set(bpy.data.objects.keys())


def test_delete_constrained_object_undo():
    plane, (a,) = _constrained(1)
    _select(a)
    bpy.ops.ed.undo_push(message="before")
    assert bpy.ops.allset.delete('EXEC_DEFAULT', True) == {'FINISHED'}
    assert not _helpers()
    bpy.ops.ed.undo()
    assert "pCube1" in bpy.data.objects and len(_helpers()) == 1, "undo brings the object and its helper back"


# --- All by Type ---------------------------------------------------------------------------------------------------

def _fx_scene():
    _clear()
    cloth = _cube("pCloth1", 2.0, (0, 0, 0))
    rigid = _cube("pRigid1", 2.0, (5, 0, 0))
    legacy = _cube("pLegacy1", 2.0, (10, 0, 0))
    legacy.modifiers.new("particles1", 'PARTICLE_SYSTEM')
    cloth.modifiers.new("nCloth1", 'CLOTH')
    rigid.modifiers.new("nRigid1", 'COLLISION')
    emitter = _cube("emitter1", 1.0, (0, -5, 0))       # an nParticle from an older file: settings nParticleN
    emitter.modifiers.new("nParticle1", 'PARTICLE_SYSTEM').particle_system.settings.name = "nParticle1"
    target = _cube("pWire1", 4.0, (0, 10, 0))
    curve = _curve("curve1")
    curve.location = (0, 10, 0)
    _select(target, curve, active=curve)
    assert bpy.ops.allset.deformer(kind='WIRE') == {'FINISHED'}
    return cloth, rigid, legacy, emitter, target, curve


def test_all_by_type_menu_items_are_mapped():
    for label, kind in (("Wires", 'WIRES'), ("nCloths", 'NCLOTHS'), ("nParticles", 'NPARTICLES'),
                        ("nRigids", 'NRIGIDS')):
        assert menu_map.MAP[f"Select/All by Type/{label}"] == ("allset.select_all_by_type", {"type": kind})
        assert menu_map.MAP[f"Edit/Delete All by Type/{label}"] == ("allset.delete_by_type",
                                                                    {"type": kind, "all": True})


def test_select_all_by_type_kit_nodes():
    cloth, rigid, legacy, emitter, target, curve = _fx_scene()
    ctx = bpy.context
    assert by_type.select_all(ctx, 'NCLOTHS') == [cloth]
    assert by_type.select_all(ctx, 'NRIGIDS') == [rigid]
    assert by_type.select_all(ctx, 'NPARTICLES') == [emitter]
    assert by_type.select_all(ctx, 'WIRES') == [curve]
    # Maya `-type particle` includes nParticle shapes: Particles still finds both
    assert set(by_type.select_all(ctx, 'PARTICLES')) == {legacy, emitter}
    for label, want in (("Wires", curve), ("nCloths", cloth), ("nParticles", emitter), ("nRigids", rigid)):
        assert bpy.ops.allset.menu_item(item=f"Select/All by Type/{label}") == {'FINISHED'}
        assert list(ctx.selected_objects) == [want], (label, ctx.selected_objects)
        assert ctx.view_layer.objects.active == want


def test_delete_all_by_type_kit_nodes():
    cloth, rigid, legacy, emitter, target, curve = _fx_scene()
    n_objects = len(bpy.data.objects)
    assert bpy.ops.allset.menu_item(item="Edit/Delete All by Type/nCloths") == {'FINISHED'}
    assert not [m for m in cloth.modifiers if m.type == 'CLOTH']
    assert bpy.ops.allset.menu_item(item="Edit/Delete All by Type/nRigids") == {'FINISHED'}
    assert not [m for m in rigid.modifiers if m.type == 'COLLISION']
    assert bpy.ops.allset.menu_item(item="Edit/Delete All by Type/nParticles") == {'FINISHED'}
    assert not emitter.particle_systems, "the nParticle goes"
    assert len(legacy.particle_systems) == 1, "a legacy particle system isn't an nParticle"
    assert not [s for s in bpy.data.particles if s.name.startswith("nParticle")]
    assert len(bpy.data.objects) == n_objects, "the meshes (and the emitter) stay"
    assert bpy.ops.allset.menu_item(item="Edit/Delete All by Type/Wires") == {'FINISHED'}
    assert not [m for m in target.modifiers if wire.is_wire(m)]
    assert "curve1" in bpy.data.objects and "curve1BaseWire" not in bpy.data.objects, "Maya: curve kept, base gone"
    assert "wire1" not in target.vertex_groups
    for kind in ('WIRES', 'NCLOTHS', 'NPARTICLES', 'NRIGIDS'):
        assert by_type.select_all(bpy.context, kind) == [], kind


def test_delete_all_by_type_undo():
    cloth, rigid, legacy, emitter, target, curve = _fx_scene()
    _select(cloth)
    bpy.ops.ed.undo_push(message="before")
    assert bpy.ops.allset.delete_by_type('EXEC_DEFAULT', True, type='WIRES', all=True) == {'FINISHED'}
    assert not by_type.select_all(bpy.context, 'WIRES')
    bpy.ops.ed.undo()
    assert [o.name for o in by_type.select_all(bpy.context, 'WIRES')] == ["curve1"]
