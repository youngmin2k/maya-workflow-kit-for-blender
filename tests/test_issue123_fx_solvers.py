"""#123: more Maya Fields/Solvers items on Blender's systems — Clear Initial State, Set From Mesh, Set Rigid Body
Interpenetration / Collision, Assign to Selected, Use Selected as Source."""

from importlib import import_module

import bpy

import kit
from test_issue123_fx_render import _cloth, _cube, _grid, _play, _run, _scene, _select

fx_solvers = import_module(kit.MODULE + ".operators.fx_solvers")
units = import_module(kit.MODULE + ".operators.units")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")

PATHS = ("Fields/Solvers/Initial State/Clear Initial State", "Fields/Solvers/Initial State/Set From Mesh",
         "Fields/Solvers/Set Rigid Body Interpenetration", "Fields/Solvers/Set Rigid Body Collision",
         "Fields/Solvers/Assign to Selected", "Fields/Solvers/Use Selected as Source")


def _co(ob):
    return [(ob.matrix_world @ v.co).copy() for v in ob.data.vertices]


def test_items_are_mapped_with_a_tooltip():
    for path in PATHS:
        assert path in menu_map.MAP, path
        assert path in notices.NOTICES, path


def test_clear_initial_state_brings_the_cloth_back():
    sc = _scene()
    cloth = _grid("pPlane1", z=5.0)
    _cloth(cloth)
    start = _co(cloth)
    _play(sc, 8)
    _select(cloth)
    assert _run("Fields/Solvers/Initial State/Set for Selected") == {'FINISHED'}
    assert max((a - b).length for a, b in zip(_co(cloth), start)) > 1e-3
    _play(sc, 12)
    assert _run("Fields/Solvers/Initial State/Set for Selected") == {'FINISHED'}   # a second set keeps the first input
    assert _run("Fields/Solvers/Initial State/Clear Initial State") == {'FINISHED'}
    assert max((a - b).length for a, b in zip(_co(cloth), start)) < 1e-5
    assert _run("Fields/Solvers/Initial State/Clear Initial State") == {'CANCELLED'}   # nothing left to clear


def test_clear_initial_state_of_a_rigid_body():
    sc = _scene()
    cube = _cube(z=10.0)
    _select(cube)
    bpy.ops.allset.fx_rigid(type='ACTIVE')
    _play(sc, 10)
    assert _run("Fields/Solvers/Initial State/Set for Selected") == {'FINISHED'}
    assert cube.location.z < 10.0 * units.maya_unit() - 1e-4
    assert _run("Fields/Solvers/Initial State/Clear Initial State") == {'FINISHED'}
    assert abs(cube.location.z - 10.0 * units.maya_unit()) < 1e-6


def test_set_from_mesh_starts_the_cloth_from_the_other_shape():
    sc = _scene()
    cloth = _grid("pPlane1", z=5.0)
    _cloth(cloth)
    other = _grid("pPlane2", z=8.0)
    for v in other.data.vertices:
        v.co.x += 0.3 * units.maya_unit() * v.co.y
    start = _co(cloth)
    _select(cloth, other)
    assert _run("Fields/Solvers/Initial State/Set From Mesh") == {'FINISHED'}
    assert max((a - b).length for a, b in zip(_co(cloth), _co(other))) < 1e-5
    sc.frame_set(sc.frame_start)
    _select(cloth)
    assert _run("Fields/Solvers/Initial State/Clear Initial State") == {'FINISHED'}
    assert max((a - b).length for a, b in zip(_co(cloth), start)) < 1e-5
    small = _cube("pCube1")
    _select(cloth, small)
    assert _run("Fields/Solvers/Initial State/Set From Mesh") == {'CANCELLED'}     # vertex counts differ


def test_interpenetration_lets_a_body_fall_through_and_collision_undoes_it():
    k = units.maya_unit()
    sc = _scene()
    floor = _cube("pCube1", z=0.0, size=10.0)
    floor.scale.z = 0.1
    _select(floor)
    bpy.ops.allset.fx_rigid(type='PASSIVE')
    cube = _cube("pCube2", z=3.0)
    _select(cube)
    bpy.ops.allset.fx_rigid(type='ACTIVE')
    _select(cube)
    assert _run("Fields/Solvers/Set Rigid Body Interpenetration") == {'CANCELLED'}  # needs two bodies
    _select(floor, cube)
    assert _run("Fields/Solvers/Set Rigid Body Interpenetration") == {'FINISHED'}
    empties = fx_solvers.no_collide_empties(sc)
    assert len(empties) == 1 and empties[0].name == "rigidInterpenetrate1"
    c = empties[0].rigid_body_constraint
    assert c.type == 'GENERIC' and c.disable_collisions and {c.object1, c.object2} == {floor, cube}
    assert _run("Fields/Solvers/Set Rigid Body Interpenetration") == {'FINISHED'}   # no second one for the pair
    assert len(fx_solvers.no_collide_empties(sc)) == 1
    sc.frame_set(sc.frame_start)
    _play(sc, 40)
    assert cube.matrix_world.translation.z < -1.0 * k, cube.matrix_world.translation.z   # fell through the floor
    _select(floor, cube)
    assert _run("Fields/Solvers/Set Rigid Body Collision") == {'FINISHED'}
    assert not fx_solvers.no_collide_empties(sc)
    sc.frame_set(sc.frame_start)
    _play(sc, 40)
    assert cube.matrix_world.translation.z > 0.5 * k, cube.matrix_world.translation.z    # lands on it


def test_assign_to_selected_limits_the_cloth_to_those_fields():
    _scene()
    cloth = _grid("pPlane1", z=5.0)
    md = _cloth(cloth)
    _select()
    bpy.ops.allset.create(kind='FIELD_AIR')
    air = bpy.context.active_object
    bpy.ops.allset.create(kind='FIELD_GRAVITY')
    grav = bpy.context.active_object
    _select(cloth, air)
    assert _run("Fields/Solvers/Assign to Selected") == {'FINISHED'}
    coll = md.settings.effector_weights.collection
    assert coll is not None and set(coll.objects) == {air}
    _select(cloth, grav)
    assert _run("Fields/Solvers/Assign to Selected") == {'FINISHED'}
    assert md.settings.effector_weights.collection is coll and set(coll.objects) == {air, grav}
    _select(air, grav)
    assert _run("Fields/Solvers/Assign to Selected") == {'CANCELLED'}


def test_use_selected_as_source_moves_the_field_onto_the_object():
    _scene()
    cloth = _grid("pPlane1", z=5.0)
    md = _cloth(cloth)
    _select()
    bpy.ops.allset.create(kind='FIELD_AIR')
    air = bpy.context.active_object
    strength, kind, name = air.field.strength, air.field.type, air.name
    _select(cloth, air)
    assert _run("Fields/Solvers/Assign to Selected") == {'FINISHED'}
    ball = _cube("pCube1", z=2.0)
    _select(air, ball)
    assert _run("Fields/Solvers/Use Selected as Source") == {'FINISHED'}
    assert bpy.data.objects.get(name) is None
    assert ball.field is not None and ball.field.type == kind and abs(ball.field.strength - strength) < 1e-6
    assert set(md.settings.effector_weights.collection.objects) == {ball}
    assert all(not (o.type == 'EMPTY' and o.field and o.field.type == kind) for o in bpy.context.scene.objects)
