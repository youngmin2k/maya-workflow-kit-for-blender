"""Lane P (#112): Constrain > UV Pin / Proximity Pin, Deform > Display / Hide Intermediate Objects, Deform >
Wrap > Add / Remove Influence (operators/pins_205.py), following Maya 2022's behaviour;
no Maya numbers yet, so these tests check the kit's rules: a pin follows the
deformed surface, keeps its creation offset (Proximity Pin), names, undo, clean disable."""

from importlib import import_module

import bpy
from mathutils import Matrix, Vector

import kit

pins = import_module(kit.MODULE + ".operators.pins_205")
deformers = import_module(kit.MODULE + ".operators.deformers")
cb = import_module(kit.MODULE + ".ui.channel_box")
ae = import_module(kit.MODULE + ".ui.attribute_editor")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
history = import_module(kit.MODULE + ".operators.history")

TOL = 1e-5


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.lattices, bpy.data.curves):
        for d in list(coll):
            coll.remove(d)
    pins._rescan()


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def _grid(name="pPlane1", size=2.0, loc=(0, 0, 0), sub=6):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=sub, y_subdivisions=sub, size=size, location=loc,
                                    calc_uvs=True)
    ob = bpy.context.active_object
    ob.name, ob.data.name = name, name.replace("pPlane", "pPlaneShape")
    return ob


def _empty(name, loc):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    bpy.context.view_layer.update()
    return ob


def _settle():
    for _i in range(3):
        bpy.context.view_layer.update()
        pins.update()
    bpy.context.view_layer.update()


def _world(ob):
    return ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world


def _close(a, b, tol=TOL, what=""):
    d = (Vector(a) - Vector(b)).length
    assert d < tol, f"{what}: {tuple(a)} vs {tuple(b)} ({d:.2e})"


def _displace(ob, strength):
    md = ob.modifiers.new("disp", 'DISPLACE')
    md.direction = 'Z'
    md.mid_level = 0.0
    md.strength = strength
    return md


# --- UV Pin ----------------------------------------------------------------------------------------------------

def test_uv_pin_snaps_to_the_closest_uv_and_follows_the_deformation():
    _clear()
    plane = _grid()
    loc = _empty("locator1", (0.3, -0.2, 0.7))
    _select(plane, loc)
    assert bpy.ops.allset.uv_pin('EXEC_DEFAULT', True) == {'FINISHED'}
    con = loc.constraints["uvPin1"]
    assert con.type == 'COPY_TRANSFORMS' and con.mix_mode == 'BEFORE_FULL'
    assert tuple(loc.location) == (0, 0, 0) and tuple(loc.scale) == (1, 1, 1)      # Maya clears the channels
    _settle()
    m = _world(loc)
    _close(m.translation, (0.3, -0.2, 0.0), what="closest point")
    _close(m.col[0].xyz, (0, 0, 1), what="X = surface normal")
    _close(m.col[1].xyz, (1, 0, 0), what="Y = surface tangent (dP/du)")
    # deforming the surface (a modifier) carries the pin
    _displace(plane, 0.5)
    _settle()
    _close(_world(loc).translation, (0.3, -0.2, 0.5), what="displaced")
    # editing the mesh points too
    for v in plane.data.vertices:
        v.co.z += 0.25
    plane.data.update()
    _settle()
    _close(_world(loc).translation, (0.3, -0.2, 0.75), what="points moved")
    # and moving the geometry
    plane.location = (1.0, 2.0, 0.0)
    _settle()
    _close(_world(loc).translation, (1.3, 1.8, 0.75), what="geometry moved")
    # the pin's own channels still move the pinned object (Maya: local on top of the offset parent matrix)
    loc.location = (0.0, 0.0, 0.1)
    _settle()
    _close(_world(loc).translation, (1.3, 1.9, 0.75), what="own channels in pin space (Z = X x Y = +Y)")


def test_uv_pin_follows_a_bent_mesh_by_uv_not_by_position():
    _clear()
    plane = _grid(sub=10)
    loc = _empty("locator1", (0.5, 0.0, 0.3))
    _select(plane, loc)
    assert bpy.ops.allset.uv_pin('EXEC_DEFAULT', True) == {'FINISHED'}
    h = loc.constraints["uvPin1"].target
    uv = tuple(h[pins.UV])
    assert abs(uv[0] - 0.75) < 1e-6 and abs(uv[1] - 0.5) < 1e-6, uv      # grid UVs span 0..1 over -1..1
    md = plane.modifiers.new("bend", 'SIMPLE_DEFORM')
    md.deform_method, md.deform_axis, md.angle = 'BEND', 'Z', 1.2
    _settle()
    dg = bpy.context.evaluated_depsgraph_get()
    geo = pins.Geo(plane, dg)
    p, w = geo.at_uv((0.75, 0.5))                  # Maya: face + bilinear corner weights
    ls = int(geo.ls[p])
    expect = sum((Vector(geo.world_points()[geo.lv[ls + k]]) * float(w[k]) for k in range(len(w))), Vector())
    _close(_world(loc).translation, expect, what="bent surface point")
    assert (_world(loc).translation - Vector((0.5, 0.0, 0.0))).length > 1e-3     # the bend really moved it


def test_uv_pin_rides_the_smooth_preview_vertices():
    _clear()
    plane = _grid()
    loc = _empty("locator1", (0.3, -0.2, 0.2))
    _select(plane, loc)
    bpy.ops.allset.uv_pin('EXEC_DEFAULT', True)
    _displace(plane, 0.5)
    ss = plane.modifiers.new("Maya Smooth Preview", 'SUBSURF')
    ss.levels = 2
    _settle()
    p = _world(loc).translation          # the mesh's own (smoothed) vertices of the subdivided result: still on z 0.5
    assert abs(p.z - 0.5) < 1e-5 and (p.xy - Vector((0.3, -0.2))).length < 0.1, p


def test_uv_pin_components_and_output_rules():
    _clear()
    plane = _grid()
    _select(plane)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    plane.data.vertices[0].select = True
    co0 = plane.matrix_world @ plane.data.vertices[0].co
    bpy.ops.object.mode_set(mode='EDIT')
    # Maya: Components + Existing Transform is an error
    assert bpy.ops.allset.uv_pin('EXEC_DEFAULT', True, setup='COMPONENTS') == {'CANCELLED'}
    assert bpy.ops.allset.uv_pin('EXEC_DEFAULT', True, setup='COMPONENTS', output='LOCATOR') == {'FINISHED'}
    out = bpy.data.objects["pinOutput"]
    _settle()
    _close(_world(out).translation, co0, what="pinOutput at the vertex")
    assert out.constraints[0].name == "uvPin1"


def test_uv_pin_selection_errors_and_axes():
    _clear()
    plane = _grid()
    _select(plane)
    assert bpy.ops.allset.uv_pin('EXEC_DEFAULT', True) == {'CANCELLED'}           # no transform
    loc = _empty("locator1", (0, 0, 1))
    _select(loc)
    assert bpy.ops.allset.uv_pin('EXEC_DEFAULT', True) == {'CANCELLED'}           # no geometry
    _select(plane, loc)
    assert bpy.ops.allset.uv_pin('EXEC_DEFAULT', True, normal_axis="Y", tangent_axis="-Y") == {'CANCELLED'}
    assert bpy.ops.allset.uv_pin('EXEC_DEFAULT', True, normal_axis="-Z", tangent_axis="X") == {'FINISHED'}
    _settle()
    m = _world(loc)
    _close(-m.col[2].xyz, (0, 0, 1), what="-Z = normal")
    _close(m.col[0].xyz, (1, 0, 0), what="X = tangent")


# --- Proximity Pin --------------------------------------------------------------------------------------------

def test_proximity_pin_keeps_its_offset_and_follows():
    _clear()
    plane = _grid()
    loc = _empty("locator1", (0.3, 0.2, 0.6))
    loc.rotation_euler = (0.3, 0.1, 0.0)
    bpy.context.view_layer.update()
    before = loc.matrix_world.copy()
    _select(plane, loc)
    assert bpy.ops.allset.proximity_pin('EXEC_DEFAULT', True) == {'FINISHED'}
    assert "proximityPin1" in loc.constraints
    inp = bpy.data.objects["pinInput"]                       # Maya: a pinInput locator, selected
    assert inp.select_get()
    _settle()
    m = _world(loc)
    for i in range(4):
        _close(m.col[i], before.col[i], what=f"maintained offset col {i}")
    # a rigid move of the geometry carries the object rigidly
    rot = Matrix.Rotation(0.7, 4, 'Z')
    plane.matrix_world = rot
    _settle()
    m = _world(loc)
    expect = rot @ before
    for i in range(4):
        _close(m.col[i], expect.col[i], what=f"rigid col {i}")
    plane.matrix_world = Matrix.Identity(4)
    _displace(plane, 0.5)
    _settle()
    _close(_world(loc).translation, before.translation + Vector((0, 0, 0.5)), what="displaced")


def test_proximity_pin_without_offset_sits_on_the_surface():
    _clear()
    plane = _grid()
    loc = _empty("locator1", (0.3, 0.2, 0.6))
    _select(plane, loc)
    assert bpy.ops.allset.proximity_pin('EXEC_DEFAULT', True, maintain_offset=False, input='MATRIX') == {'FINISHED'}
    assert "pinInput" not in bpy.data.objects
    _settle()
    _close(_world(loc).translation, (0.3, 0.2, 0.0), what="surface point")
    # Maya messages
    _select(plane, loc)
    assert bpy.ops.allset.proximity_pin('EXEC_DEFAULT', True, setup='COMPONENTS') == {'CANCELLED'}
    assert bpy.ops.allset.proximity_pin('EXEC_DEFAULT', True, input='CURRENT') == {'CANCELLED'}


# --- names / Channel Box / AE ----------------------------------------------------------------------------------

def test_maya_node_names():
    _clear()
    plane = _grid()
    a = _empty("locator1", (0.1, 0, 1))
    b = _empty("locator2", (-0.1, 0, 1))
    _select(plane, a, b)
    assert bpy.ops.allset.uv_pin('EXEC_DEFAULT', True) == {'FINISHED'}
    assert a.constraints[0].name == "uvPin1" and b.constraints[0].name == "uvPin1"   # one node, two outputs
    c = _empty("locator3", (0.2, 0.3, 1))
    _select(plane, c)
    bpy.ops.allset.uv_pin('EXEC_DEFAULT', True)
    con = c.constraints[0]
    assert con.name == "uvPin2"
    assert cb.constraint_node_name(c, con) == "uvPin2"
    assert cb.maya_constraint_type(con) == "uvPin"
    assert cb.weight_name(con) == "pPlane1W0"
    tabs = ae._constraint_tabs(c)
    assert tabs and tabs[0][1] == "uvPin2" and tabs[0][2] == "uvPin", tabs
    d = _empty("locator4", (0.2, 0.3, 1))
    _select(plane, d)
    bpy.ops.allset.proximity_pin('EXEC_DEFAULT', True)
    bpy.ops.allset.proximity_pin('EXEC_DEFAULT', True)        # d is pinned twice: second pinInput = pinInput1
    assert [x.name for x in d.constraints] == ["proximityPin1", "proximityPin2"]
    assert "pinInput1" in bpy.data.objects


# --- intermediate objects -------------------------------------------------------------------------------------

def test_display_and_hide_intermediate_objects():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    cube.name, cube.data.name = "pCube1", "pCubeShape1"
    _select(cube)
    assert bpy.ops.allset.intermediate_objects('EXEC_DEFAULT', True, show=True) == {'CANCELLED'}   # no deformer
    deformers.create(bpy.context, 'BEND')
    _select(cube)
    assert bpy.ops.allset.intermediate_objects('EXEC_DEFAULT', True, show=True) == {'FINISHED'}
    orig = bpy.data.objects["pCubeShape1Orig"]
    assert pins.is_intermediate(orig) and orig.data == cube.data and not orig.modifiers
    assert orig.parent == cube and orig.select_get() and not cube.select_get()
    _close(orig.matrix_world.translation, cube.matrix_world.translation)
    assert not pins.is_intermediate(cube)
    _select(cube)
    assert bpy.ops.allset.intermediate_objects('EXEC_DEFAULT', True, show=True) == {'CANCELLED'}   # already on
    _select(orig)                                             # Hide from the intermediate object itself
    assert bpy.ops.allset.intermediate_objects('EXEC_DEFAULT', True, show=False) == {'FINISHED'}
    assert "pCubeShape1Orig" not in bpy.data.objects
    assert cube.select_get() and bpy.context.view_layer.objects.active == cube
    assert bpy.ops.allset.intermediate_objects('EXEC_DEFAULT', True, show=False) == {'CANCELLED'}  # already off
    assert len(cube.modifiers) and cube.data.users == 1


# --- wrap influences ------------------------------------------------------------------------------------------

def _wrapped():
    _clear()
    target = _grid("pPlane1", size=2.0, sub=8)
    left = _grid("pPlane2", size=1.0, loc=(-0.5, 0, 0), sub=4)
    left.scale = (1.0, 2.0, 1.0)
    right = _grid("pPlane3", size=1.0, loc=(0.5, 0, 0), sub=4)
    right.scale = (1.0, 2.0, 1.0)
    bpy.context.view_layer.update()
    _select(target, left)
    deformers.create(bpy.context, 'WRAP')
    return target, left, right


def _z(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).data
    mw = ob.matrix_world
    xs = [((mw @ v.co).x, (mw @ v.co).z) for v in me.vertices]
    return ([z for x, z in xs if x < -0.6], [z for x, z in xs if x > 0.6])


def test_wrap_add_and_remove_influence():
    target, left, right = _wrapped()
    right.location.z += 1.0
    bpy.context.view_layer.update()
    lz, rz = _z(target)
    assert max(abs(z) for z in lz + rz) < 1e-5            # not an influence yet
    right.location.z -= 1.0
    _select(target, right)
    assert bpy.ops.allset.wrap_influence('EXEC_DEFAULT', True, action='ADD') == {'FINISHED'}
    names = [m.name for m in target.modifiers]
    assert names == ["wrap1", "wrap1Base", "wrap1Influence2", "wrap1Influence2Base"], names
    assert target.select_get() and not right.select_get()   # Maya: the influence leaves the selection
    # INPUTS: still one wrap node; Delete History keeps the parts (deformers)
    assert [m.name for m in cb._inputs(target)] == ["wrap1"]
    assert all(history.is_deformer(m) for m in target.modifiers)
    right.location.z += 1.0
    left.location.z -= 0.5
    bpy.context.view_layer.update()
    lz, rz = _z(target)
    assert all(abs(z - 1.0) < 1e-4 for z in rz), rz          # the right side follows pPlane3
    assert all(abs(z + 0.5) < 1e-4 for z in lz), lz          # the left side still follows pPlane2
    _select(target, right)
    assert bpy.ops.allset.wrap_influence('EXEC_DEFAULT', True, action='REMOVE') == {'FINISHED'}
    assert [m.name for m in target.modifiers] == ["wrap1", "wrap1Base"]
    assert "wrap1Influence2" not in target.vertex_groups
    bpy.context.view_layer.update()
    lz, rz = _z(target)
    assert all(abs(z + 0.5) < 1e-4 for z in lz + rz), (lz, rz)     # everything follows pPlane2 again
    # removing the node's own (last) influence removes the wrap
    _select(target, left)
    assert bpy.ops.allset.wrap_influence('EXEC_DEFAULT', True, action='REMOVE') == {'FINISHED'}
    assert not target.modifiers


def test_wrap_remove_the_first_influence_keeps_the_second():
    target, left, right = _wrapped()
    _select(target, right)
    bpy.ops.allset.wrap_influence('EXEC_DEFAULT', True, action='ADD')
    _select(target, left)
    assert bpy.ops.allset.wrap_influence('EXEC_DEFAULT', True, action='REMOVE') == {'FINISHED'}
    md = target.modifiers["wrap1"]
    assert md.target == right and md.is_bound and len(target.modifiers) == 2
    right.location.z += 1.0
    bpy.context.view_layer.update()
    lz, rz = _z(target)
    assert all(abs(z - 1.0) < 1e-3 for z in lz + rz), (lz, rz)


def test_wrap_influence_errors():
    target, left, right = _wrapped()
    _select(right)
    assert bpy.ops.allset.wrap_influence('EXEC_DEFAULT', True, action='ADD') == {'CANCELLED'}
    other = _grid("pPlane9", loc=(0, 0, 3))
    _select(other, right)
    assert bpy.ops.allset.wrap_influence('EXEC_DEFAULT', True, action='ADD') == {'CANCELLED'}    # no wrap


# --- menus, undo, disable -------------------------------------------------------------------------------------

def test_menu_paths_mapped():
    assert menu_map.MAP["Constrain/UV Pin"] == "allset.uv_pin"
    assert menu_map.MAP["Constrain/Proximity Pin"] == "allset.proximity_pin"
    assert menu_map.MAP["Deform/Display Intermediate Objects"] == ("allset.intermediate_objects", {"show": True})
    assert menu_map.MAP["Deform/Hide Intermediate Objects"] == ("allset.intermediate_objects", {"show": False})
    assert menu_map.MAP["Deform/Wrap#2/Add Influence"] == ("allset.wrap_influence", {"action": 'ADD'})
    assert menu_map.MAP["Deform/Wrap#2/Remove Influence"] == ("allset.wrap_influence", {"action": 'REMOVE'})


def test_option_window_specs_have_maya_factory_values():
    ws = {w.key: w for w in pins.windows()}
    uv = ws["uv_pin"].defaults()
    assert uv == {"setup": "Transforms", "output": "Existing Transform", "normal_axis": "X", "tangent_axis": "Y"}
    px = ws["proximity_pin"].defaults()
    assert px == {"setup": "Transforms", "output": "Existing Transform", "input": "New Locator",
                  "maintain_offset": True, "mode": "Edge", "normal_axis": "X", "tangent_axis": "Y"}


def test_one_undo_step_each():
    _clear()
    plane = _grid()
    loc = _empty("locator1", (0.3, 0.2, 0.6))
    _select(plane, loc)
    bpy.ops.ed.undo_push(message="before")
    assert bpy.ops.allset.uv_pin('EXEC_DEFAULT', True) == {'FINISHED'}
    bpy.ops.ed.undo()
    loc = bpy.data.objects["locator1"]
    assert not loc.constraints and not any(o.get(pins.KIND) for o in bpy.data.objects)
    _close(loc.location, (0.3, 0.2, 0.6))
    bpy.context.view_layer.update()
    pins.update()                                   # the handler copes with the vanished helper


def test_handlers_registered_with_the_kit():
    assert pins._on_depsgraph in bpy.app.handlers.depsgraph_update_post
    assert pins._on_frame in bpy.app.handlers.frame_change_post
    kit.disable()
    try:
        assert pins._on_depsgraph not in bpy.app.handlers.depsgraph_update_post
        assert pins._on_frame not in bpy.app.handlers.frame_change_post
        assert not hasattr(bpy.types, "ALLSET_OT_uv_pin")
    finally:
        kit.enable()


def test_handler_moves_pins_on_its_own():
    _clear()
    plane = _grid()
    loc = _empty("locator1", (0.3, -0.2, 0.7))
    _select(plane, loc)
    bpy.ops.allset.uv_pin('EXEC_DEFAULT', True)
    plane.location.z = 2.0
    for _i in range(4):
        bpy.context.view_layer.update()            # depsgraph_update_post -> pins._on_depsgraph
    _close(_world(loc).translation, (0.3, -0.2, 2.0), what="handler")
