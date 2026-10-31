"""Maya concept operators, checked numerically (matrices, vertices, names).

Freeze / Reset / Center Pivot, Maya parenting, Duplicate Special / with Transform,
Maya creation and naming, Maya units, Delete History / by Type, keys and menus.
"""

import math
from importlib import import_module

import bpy
from mathutils import Matrix, Vector

import kit

freeze = import_module(kit.MODULE + ".operators.freeze")
duplicate = import_module(kit.MODULE + ".operators.duplicate")
naming = import_module(kit.MODULE + ".operators.naming")
units = import_module(kit.MODULE + ".operators.units")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
mm = import_module(kit.MODULE + ".marking.menus")
preferences = import_module(kit.MODULE + ".preferences")

TOL = 1e-4


# --- helpers ------------------------------------------------------------------------

def _fresh():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    duplicate.PAIRS.clear()


def _cube(name="c", size=1.0, loc=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=size, location=(0, 0, 0))
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    # Off-centre geometry so pivot and bounding-box centre differ.
    ob.data.transform(Matrix.Translation((0.5, 0.25, 0.0)))
    ob.location = loc
    return ob


def _select(objs, active=None):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[-1] if objs else None)


def _update():
    bpy.context.view_layer.update()


def _world_verts(ob):
    _update()
    return [ob.matrix_world @ v.co for v in ob.data.vertices]


def _close_m(a, b, tol=TOL):
    return all(abs(a[i][j] - b[i][j]) < tol for i in range(4) for j in range(4))


def _close_v(a, b, tol=TOL):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def _close_vs(a, b, tol=TOL):
    return len(a) == len(b) and all(_close_v(x, y, tol) for x, y in zip(a, b))


def _channels(ob):
    return (tuple(ob.location), tuple(ob.rotation_euler), tuple(ob.scale))


ZERO = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))


def _is_zero(ob):
    loc, rot, scl = _channels(ob)
    return _close_v(loc, ZERO[0]) and _close_v(rot, ZERO[1]) and _close_v(scl, ZERO[2])


def _transformed(ob, loc=(1, 2, 3), rot=(0.4, -0.3, 0.7), scale=(2.0, 0.5, 1.5)):
    ob.location, ob.rotation_euler, ob.scale = loc, rot, scale
    _update()
    return ob


def _outward(ob):
    """Every face normal points away from the object's centre (world space)."""
    _update()
    c = sum((ob.matrix_world @ v.co for v in ob.data.vertices), Vector()) / len(ob.data.vertices)
    nm = ob.matrix_world.to_3x3().inverted().transposed()
    for p in ob.data.polygons:
        n = nm @ p.normal
        if n.dot((ob.matrix_world @ p.center) - c) <= 0:
            return False
    return True


# --- Freeze -------------------------------------------------------------------------

def test_freeze_keeps_pivot_and_vertices():
    _fresh()
    ob = _transformed(_cube())
    pivot = ob.matrix_world.translation.copy()
    before = _world_verts(ob)
    _select([ob])
    assert bpy.ops.allset.freeze_transform() == {'FINISHED'}
    _update()
    assert _is_zero(ob), _channels(ob)
    assert _close_v(ob.matrix_world.translation, pivot), (ob.matrix_world.translation, pivot)
    assert _close_m(ob.matrix_world, Matrix.Translation(pivot)), ob.matrix_world
    assert _close_v(ob.delta_location, pivot)
    assert _close_vs(_world_verts(ob), before)
    assert _outward(ob)


def test_freeze_folds_existing_deltas():
    _fresh()
    ob = _transformed(_cube())
    ob.delta_location = (5, 0, 0)
    ob.delta_rotation_euler = (0, 0.2, 0)
    ob.delta_scale = (1, 2, 1)
    before, pivot = _world_verts(ob), ob.matrix_world.translation.copy()
    _select([ob])
    bpy.ops.allset.freeze_transform()
    assert _is_zero(ob)
    assert _close_v(ob.delta_rotation_euler, (0, 0, 0)) and _close_v(ob.delta_scale, (1, 1, 1))
    assert _close_vs(_world_verts(ob), before)
    assert _close_v(ob.matrix_world.translation, pivot)
    # A second freeze changes nothing.
    bpy.ops.allset.freeze_transform()
    assert _close_vs(_world_verts(ob), before) and _is_zero(ob)


def test_freeze_partial_flags_keep_world():
    for flags in ({"translate": True, "rotate": False, "scale": False},
                  {"translate": False, "rotate": True, "scale": False},
                  {"translate": False, "rotate": False, "scale": True},
                  {"translate": False, "rotate": True, "scale": True}):
        _fresh()
        ob = _transformed(_cube())
        loc, rot, scl = _channels(ob)
        before = _world_verts(ob)
        _select([ob])
        bpy.ops.allset.freeze_transform(**flags)
        assert _close_vs(_world_verts(ob), before), flags
        got_loc, got_rot, got_scl = _channels(ob)
        assert _close_v(got_loc, (0, 0, 0) if flags["translate"] else loc), (flags, got_loc)
        assert _close_v(got_rot, (0, 0, 0) if flags["rotate"] else rot), (flags, got_rot)
        assert _close_v(got_scl, (1, 1, 1) if flags["scale"] else scl), (flags, got_scl)


def test_freeze_hierarchy():
    _fresh()
    parent = _transformed(_cube("parent"))
    child = _transformed(_cube("child"), loc=(1, 0, 0), rot=(0, 0.5, 0), scale=(1, 1, 2))
    grandchild = _transformed(_cube("grand"), loc=(0, 1, 0), rot=(0.1, 0, 0), scale=(1, 1, 1))
    child.parent = parent
    grandchild.parent = child
    _update()
    obs = (parent, child, grandchild)
    before = {o.name: _world_verts(o) for o in obs}
    pivots = {o.name: o.matrix_world.translation.copy() for o in obs}
    _select([parent])
    bpy.ops.allset.freeze_transform()
    _update()
    for o in obs:
        assert _is_zero(o), (o.name, _channels(o))
        assert _close_vs(_world_verts(o), before[o.name]), o.name
        assert _close_v(o.matrix_world.translation, pivots[o.name]), o.name


def test_freeze_negative_scale_keeps_normals_out():
    _fresh()
    ob = _transformed(_cube(), scale=(-1.0, 1.0, 1.0))
    assert _outward(ob)
    before = _world_verts(ob)
    _select([ob])
    bpy.ops.allset.freeze_transform()
    assert _close_vs(_world_verts(ob), before)
    assert _outward(ob)


def test_freeze_shared_mesh_made_single_user():
    _fresh()
    a = _transformed(_cube("a"))
    b = bpy.data.objects.new("b", a.data)
    bpy.context.scene.collection.objects.link(b)
    _update()
    b_before = _world_verts(b)
    _select([a])
    bpy.ops.allset.freeze_transform()
    assert a.data is not b.data
    assert _close_vs(_world_verts(b), b_before)


def test_freeze_empty_group_only_translates_and_children_stay():
    _fresh()
    grp = bpy.data.objects.new("group1", None)
    bpy.context.scene.collection.objects.link(grp)
    _transformed(grp)
    kid = _transformed(_cube("kid"), loc=(1, 1, 0), rot=(0, 0, 0.3), scale=(1, 1, 1))
    kid.parent = grp
    _update()
    kid_before = _world_verts(kid)
    grp_world = grp.matrix_world.copy()
    _select([grp])
    bpy.ops.allset.freeze_transform()
    _update()
    assert _close_v(grp.location, (0, 0, 0))
    assert _close_v(grp.rotation_euler, (0.4, -0.3, 0.7)) and _close_v(grp.scale, (2.0, 0.5, 1.5))
    assert _close_m(grp.matrix_world, grp_world)
    assert _close_vs(_world_verts(kid), kid_before) and _is_zero(kid)


# --- Reset ----------------------------------------------------------------------------

def test_reset_returns_to_frozen_state():
    _fresh()
    ob = _transformed(_cube())
    _select([ob])
    bpy.ops.allset.freeze_transform()
    frozen = _world_verts(ob)
    _transformed(ob, loc=(3, 3, 3), rot=(1, 0, 0), scale=(3, 3, 3))
    assert not _close_vs(_world_verts(ob), frozen)
    bpy.ops.allset.reset_transform()
    assert _is_zero(ob)
    assert _close_vs(_world_verts(ob), frozen)


def test_reset_flags():
    _fresh()
    ob = _transformed(_cube())
    _select([ob])
    bpy.ops.allset.reset_transform(translate=False, rotate=True, scale=False)
    loc, rot, scl = _channels(ob)
    assert _close_v(loc, (1, 2, 3)) and _close_v(rot, (0, 0, 0)) and _close_v(scl, (2.0, 0.5, 1.5))


# --- Center Pivot ---------------------------------------------------------------------

def test_center_pivot():
    _fresh()
    ob = _transformed(_cube())
    kid = _transformed(_cube("kid"), loc=(0, 0, 2), rot=(0, 0, 0), scale=(1, 1, 1))
    kid.parent = ob
    _update()
    channels = _channels(ob)
    kid_channels = _channels(kid)
    before, kid_before = _world_verts(ob), _world_verts(kid)
    _select([ob])
    assert bpy.ops.allset.center_pivot() == {'FINISHED'}
    _update()
    assert _close_vs(_world_verts(ob), before)
    center = sum(before, Vector()) / len(before)  # a box: vertex mean = bbox centre
    assert _close_v(ob.matrix_world.translation, center), (ob.matrix_world.translation, center)
    assert all(_close_v(a, b) for a, b in zip(_channels(ob), channels)), _channels(ob)
    assert _close_vs(_world_verts(kid), kid_before)
    assert all(_close_v(a, b) for a, b in zip(_channels(kid), kid_channels))


def test_center_pivot_group_uses_children_bounds():
    _fresh()
    grp = bpy.data.objects.new("group1", None)
    bpy.context.scene.collection.objects.link(grp)
    kid = _cube("kid", loc=(4, 0, 0))
    kid.parent = grp
    _update()
    kid_before = _world_verts(kid)
    _select([grp])
    bpy.ops.allset.center_pivot()
    _update()
    center = sum(kid_before, Vector()) / len(kid_before)
    assert _close_v(grp.matrix_world.translation, center)
    assert _close_v(grp.location, (0, 0, 0))
    assert _close_vs(_world_verts(kid), kid_before)


# --- Parenting --------------------------------------------------------------------------

def test_parent_maya_mode():
    _fresh()
    parent = _transformed(_cube("parent"), scale=(2.0, 2.0, 2.0))
    child = _transformed(_cube("child"), loc=(5, -1, 2), rot=(0.2, 0.1, 0), scale=(1, 1, 1))
    world = child.matrix_world.copy()
    _select([child, parent], active=parent)
    assert bpy.ops.allset.parent() == {'FINISHED'}
    _update()
    assert child.parent is parent
    assert _close_m(child.matrix_parent_inverse, Matrix.Identity(4))
    assert _close_m(child.matrix_world, world)
    local = parent.matrix_world.inverted() @ world
    assert _close_v(child.location, local.translation), (child.location, local.translation)
    # Unparent: back to the world, same place.
    _select([child])
    assert bpy.ops.allset.unparent() == {'FINISHED'}
    _update()
    assert child.parent is None and _close_m(child.matrix_world, world)
    assert _close_v(child.location, (5, -1, 2))


def test_parent_shear_residual_in_parent_inverse():
    _fresh()
    parent = _transformed(_cube("parent"))   # rotated + non-uniform scale
    child = _transformed(_cube("child"), loc=(5, -1, 2), rot=(0.2, 0.1, 0), scale=(1, 1, 1))
    world = child.matrix_world.copy()
    _select([child, parent], active=parent)
    bpy.ops.allset.parent()
    _update()
    assert _close_m(child.matrix_world, world)        # exact, shear kept in the inverse
    assert not _close_m(child.matrix_parent_inverse, Matrix.Identity(4))
    local = parent.matrix_world.inverted() @ world
    assert _close_v(child.location, local.translation)


def test_parent_blender_mode_keeps_inverse():
    _fresh()
    prefs = preferences.get()
    prefs.parent_mode = 'BLENDER'
    try:
        parent = _transformed(_cube("parent"))
        child = _transformed(_cube("child"), loc=(5, -1, 2), rot=(0, 0, 0), scale=(1, 1, 1))
        world = child.matrix_world.copy()
        _select([child, parent], active=parent)
        bpy.ops.allset.parent()
        _update()
        assert child.parent is parent and _close_m(child.matrix_world, world)
        assert not _close_m(child.matrix_parent_inverse, Matrix.Identity(4))
    finally:
        prefs.parent_mode = 'MAYA'


def test_parent_refuses_cycles():
    _fresh()
    a = _cube("a")
    b = _cube("b")
    b.parent = a
    _update()
    _select([a, b], active=b)   # a under its own child b
    bpy.ops.allset.parent()
    assert a.parent is None and b.parent is a


# --- Duplicate ----------------------------------------------------------------------------

def test_duplicate_special_offsets_and_names():
    _fresh()
    ob = _cube("pCube1")
    ob.data.name = "pCubeShape1"
    kid = _cube("kid1", loc=(0, 0, 1))
    kid.parent = ob
    _update()
    _select([ob])
    res = bpy.ops.allset.duplicate_special(copies=3, translate=(1, 0, 0),
                                             rotate=(0, 0, math.radians(10)), scale=(2, 1, 1))
    assert res == {'FINISHED'}
    _update()
    names = sorted(o.name for o in bpy.context.selected_objects)
    assert names == ["pCube2", "pCube3", "pCube4"], names
    for k in (1, 2, 3):
        c = bpy.data.objects[f"pCube{k + 1}"]
        assert c.data.name == f"pCubeShape{k + 1}" and c.data is not ob.data
        assert _close_v(c.location, (k, 0, 0)) and _close_v(c.rotation_euler, (0, 0, math.radians(10 * k)))
        assert _close_v(c.scale, (2 ** k, 1, 1))
        assert len(c.children) == 1 and c.children[0].name.startswith("kid")  # subtree copied
        assert _close_m(c.children[0].matrix_world, c.matrix_world @ kid.matrix_basis)


def test_duplicate_special_instance_and_new_group():
    _fresh()
    ob = _cube("pCube1")
    _select([ob])
    bpy.ops.allset.duplicate_special(geometry_type='INSTANCE', group_under='NEW_GROUP', copies=2)
    copies = [o for o in bpy.data.objects if o.name in ("pCube2", "pCube3")]
    assert len(copies) == 2 and all(c.data is ob.data for c in copies)
    grp = copies[0].parent
    assert grp is not None and grp.type == 'EMPTY' and grp.name.startswith("group")
    assert all(c.parent is grp for c in copies)


def test_duplicate_with_transform_repeats_offset():
    _fresh()
    ob = _cube("pCube1")
    _select([ob])
    bpy.ops.allset.duplicate_with_transform()
    first = bpy.context.view_layer.objects.active
    assert first.name == "pCube2" and _close_m(first.matrix_basis, ob.matrix_basis)
    first.location = (2, 0, 0)
    first.rotation_euler = (0, 0, 0.5)
    _update()
    bpy.ops.allset.duplicate_with_transform()
    second = bpy.context.view_layer.objects.active
    _update()
    assert second.name == "pCube3"
    delta = first.matrix_world @ ob.matrix_world.inverted()
    assert _close_m(second.matrix_world, delta @ first.matrix_world)
    bpy.ops.allset.duplicate_with_transform()
    third = bpy.context.view_layer.objects.active
    _update()
    assert _close_m(third.matrix_world, delta @ second.matrix_world)


# --- Create and names -----------------------------------------------------------------------

def test_naming_helpers():
    assert naming.base_name("pCube12") == "pCube"
    assert naming.base_name("Cube.001") == "Cube"
    assert naming.base_name("foo") == "foo"
    assert naming.next_number("pCube", {"pCube1", "pCube3"}) == 4   # Maya: one past the highest
    assert naming.next_number("pCube", {"pCube1"}, {"pCubeShape2"}) == 3


CREATE_CASES = (
    # kind, object name, data name, dimensions, polygon count
    ('CUBE', "pCube1", "pCubeShape1", (1, 1, 1), 6),
    ('SPHERE', "pSphere1", "pSphereShape1", (2, 2, 2), 400),
    ('CYLINDER', "pCylinder1", "pCylinderShape1", (2, 2, 2), 60),   # Maya menu: caps = centre fans
    ('CONE', "pCone1", "pConeShape1", (2, 2, 2), 21),
    ('TORUS', "pTorus1", "pTorusShape1", (3, 3, 1), 400),
    ('PLANE', "pPlane1", "pPlaneShape1", (1, 1, 0), 100),
)


def test_create_maya_defaults():
    _fresh()
    for kind, name, data_name, dims, faces in CREATE_CASES:
        assert bpy.ops.allset.create(kind=kind) == {'FINISHED'}, kind
        ob = bpy.context.view_layer.objects.active
        _update()
        assert (ob.name, ob.data.name) == (name, data_name), (kind, ob.name, ob.data.name)
        assert _close_v(ob.location, (0, 0, 0)) and _close_v(ob.rotation_euler, (0, 0, 0)), kind
        assert _close_v(ob.dimensions, dims, 1e-3), (kind, tuple(ob.dimensions))
        assert len(ob.data.polygons) == faces, (kind, len(ob.data.polygons))


def test_create_numbers_and_other_kinds():
    _fresh()
    bpy.ops.allset.create(kind='CUBE')
    bpy.ops.allset.create(kind='CUBE')
    bpy.data.objects.remove(bpy.data.objects["pCube1"])
    bpy.data.meshes.remove(bpy.data.meshes["pCubeShape1"])
    bpy.ops.allset.create(kind='CUBE')
    assert bpy.context.view_layer.objects.active.name == "pCube3"   # Maya: one past the highest
    for kind, name in (('POINT_LIGHT', "pointLight1"), ('DIRECTIONAL_LIGHT', "directionalLight1"),
                       ('CAMERA', "camera1"), ('LOCATOR', "locator1"), ('EMPTY_GROUP', "null1"),
                       ('NURBS_SPHERE', "nurbsSphere1"), ('NURBS_CIRCLE', "nurbsCircle1")):
        bpy.ops.allset.create(kind=kind)
        ob = bpy.context.view_layer.objects.active
        assert ob.name == name, (kind, ob.name)
        assert _close_v(ob.location, (0, 0, 0)), kind
    cam = bpy.data.objects["camera1"]
    assert cam.data.name == "cameraShape1"
    assert _close_v(cam.rotation_euler, (math.pi / 2, 0, 0))


def test_create_leaves_edit_mode_and_blender_names_option():
    _fresh()
    bpy.ops.allset.create(kind='CUBE')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.allset.create(kind='SPHERE')
    assert bpy.context.mode == 'OBJECT' and len(bpy.data.objects) == 2
    prefs = preferences.get()
    prefs.maya_naming = False
    try:
        bpy.ops.allset.create(kind='CUBE')
        assert not bpy.context.view_layer.objects.active.name.startswith("pCube")
    finally:
        prefs.maya_naming = True


# --- Units ---------------------------------------------------------------------------------

def _view():
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                return area.spaces.active
    raise AssertionError("no 3D view")


def test_maya_units_apply_and_restore():
    scene = bpy.context.scene
    us = scene.unit_settings
    before = (us.length_unit, us.scale_length, _view().clip_start, _view().clip_end)
    prefs = preferences.get()
    prefs.maya_units = True
    try:
        assert (us.length_unit, us.scale_length) == ('CENTIMETERS', 0.01) or \
            (us.length_unit == 'CENTIMETERS' and abs(us.scale_length - 0.01) < 1e-7)
        assert abs(_view().clip_start - 0.1) < 1e-6 and abs(_view().clip_end - 10000) < 1e-3
        assert units.is_applied(scene)
    finally:
        prefs.maya_units = False
    after = (us.length_unit, us.scale_length, _view().clip_start, _view().clip_end)
    assert all(a == b or abs(a - b) < 1e-6 for a, b in zip(after, before)), (before, after)
    assert not units.is_applied(scene)


def test_maya_units_load_post_only_for_new_files():
    import os
    import tempfile
    prefs = preferences.get()
    path = os.path.join(tempfile.mkdtemp(), "saved.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    prefs.maya_units = True
    try:
        units.restore_file()   # the saved file itself: back to its own values
        bpy.ops.wm.open_mainfile(filepath=path)
        assert not units.is_applied(bpy.context.scene), "a saved file must not be changed"
        bpy.ops.wm.read_homefile()
        assert units.is_applied(bpy.context.scene), "new file gets Maya units"
        assert abs(bpy.context.scene.unit_settings.scale_length - 0.01) < 1e-7
    finally:
        preferences.get().maya_units = False


# --- Delete History / by Type ---------------------------------------------------------------

def test_delete_history_bakes_modifiers_and_shape_keys():
    _fresh()
    ob = _cube()
    ob.modifiers.new("sub", 'SUBSURF').levels = 1
    ob.shape_key_add(name="Basis")
    key = ob.shape_key_add(name="up")
    for p in key.data:
        p.co.z += 1.0
    key.value = 1.0
    _update()
    dg = bpy.context.evaluated_depsgraph_get()
    eval_verts = len(ob.evaluated_get(dg).data.vertices)
    zmax = max(v.co.z for v in ob.evaluated_get(dg).data.vertices)
    _select([ob])
    assert bpy.ops.allset.delete_history() == {'FINISHED'}
    assert len(ob.modifiers) == 0 and ob.data.shape_keys is None
    assert len(ob.data.vertices) == eval_verts
    assert abs(max(v.co.z for v in ob.data.vertices) - zmax) < 1e-5


def test_delete_non_deformer_history_keeps_deformers():
    _fresh()
    ob = _cube()
    ob.modifiers.new("bevel", 'BEVEL')
    ob.modifiers.new("arm", 'ARMATURE')
    ob.modifiers.new("sub", 'SUBSURF')
    _update()
    n_before = len(ob.data.vertices)
    _select([ob])
    bpy.ops.allset.delete_history(non_deformer=True, before_only=True)
    assert [m.name for m in ob.modifiers] == ["arm", "sub"], [m.name for m in ob.modifiers]
    assert len(ob.data.vertices) > n_before   # bevel baked
    # the default option "All non-deformer history": the Subdivision after the deformer goes too
    n_mid = len(ob.data.vertices)
    bpy.ops.allset.delete_history(non_deformer=True)
    assert [m.name for m in ob.modifiers] == ["arm"], [m.name for m in ob.modifiers]
    assert len(ob.data.vertices) > n_mid      # subdivision baked under the armature


def test_delete_by_type():
    _fresh()
    a = _cube("a")
    a.constraints.new('COPY_LOCATION')
    a.modifiers.new("hook", 'HOOK')
    a.keyframe_insert("location", frame=1)
    a.location.x = 3
    a.keyframe_insert("location", frame=10)   # x animated, y/z static
    bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam = bpy.data.objects["cam"]
    bpy.context.scene.collection.objects.link(cam)
    _select([a])
    bpy.ops.allset.delete_by_type(type='CONSTRAINTS')
    assert len(a.constraints) == 0
    bpy.ops.allset.delete_by_type(type='STATIC_CHANNELS')
    paths = sorted((fc.data_path, fc.array_index) for owner in
                   [cb for layer in a.animation_data.action.layers for st in layer.strips
                    for cb in st.channelbags] for fc in owner.fcurves)
    assert paths == [("location", 0)], paths
    bpy.ops.allset.delete_by_type(type='CHANNELS')
    assert a.animation_data is None
    bpy.ops.allset.delete_by_type(type='CLUSTERS', all=True)
    assert len(a.modifiers) == 0
    bpy.ops.allset.delete_by_type(type='CAMERAS')            # selection only: camera stays
    assert "cam" in bpy.data.objects
    bpy.ops.allset.delete_by_type(type='CAMERAS', all=True)
    assert "cam" not in bpy.data.objects


# --- keys, menus, marking menu ----------------------------------------------------------------

def _kmis(km_name, key, **mods):
    km = kit.maya_kc().keymaps[km_name]
    return [k for k in km.keymap_items if k.type == key and k.value == 'PRESS' and k.active
            and k.shift == mods.get("shift", False) and k.ctrl == mods.get("ctrl", False)
            and k.alt == mods.get("alt", False)]


def test_concept_keys():
    cases = (("Object Mode", "P", {}, "allset.parent"),
             ("Object Mode", "P", {"shift": True}, "allset.unparent"),
             ("Outliner", "P", {}, "allset.parent"),
             ("Outliner", "P", {"shift": True}, "allset.unparent"),
             ("Object Mode", "D", {"shift": True}, "allset.duplicate_with_transform"),
             ("Object Mode", "D", {"shift": True, "ctrl": True}, "allset.duplicate_special"),
             ("Object Mode", "D", {"shift": True, "alt": True}, "allset.delete_history"))
    for km, key, mods, idname in cases:
        got = [k.idname for k in _kmis(km, key, **mods)]
        assert got == [idname], (km, key, mods, got)


def test_menus_use_concept_operators():
    want = {"Modify/Freeze Transformations": "allset.freeze_transform",
            "Modify/Reset Transformations": "allset.reset_transform",
            "Modify/Center Pivot": "allset.center_pivot",
            "Edit/Delete by Type/History": "allset.delete_history",
            "Edit/Delete All by Type/Cameras": "allset.delete_by_type",
            "Edit/Duplicate Special": "allset.duplicate_special",
            "Edit/Duplicate with Transform": "allset.duplicate_with_transform",
            "Edit/Parent": "allset.parent", "Edit/Unparent": "allset.unparent",
            "Create/Polygon Primitives/Cube": "allset.create"}
    for path, idname in want.items():
        assert menu_map.spec(path)[1] == idname, (path, menu_map.spec(path))
    # Center Pivot sits in a "Pivot" section after Match Transformations (EXTRA, Maya order).
    modify = next(m for m in menu_sets.menu_data.MENUS.values() if m[0] == "Modify")
    entries = list(menu_sets.children(modify[3], "Modify"))
    i = [p for p, _it in entries].index("Modify/Center Pivot")
    assert entries[i - 1][1] == ("-", "Pivot") and entries[i - 2][0] == "Modify/Match Transformations"


def test_select_all_marking_menu():
    menu = mm.MENUS["SELECT_ALL"]
    assert menu.radial["NW"][1] == "allset.delete_history"
    assert menu.radial["SE"][1] == "allset.freeze_transform"
    assert "Freeze Transforms" in menu.options
