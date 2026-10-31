"""FX menus connect to Blender's own simulation operators at real size: nCloth / colliders / particles / rigid bodies /
fields / Quick Smoke are Blender's operators (every selected object where Blender allows it), nothing is rescaled
(no nucleus, the scene gravity is left alone), the creating items say FX works in metre scenes, and the items with
no Blender counterpart are greyed with a notice."""

from importlib import import_module

import bpy

import kit
from test_issue123_fx_render import _cube, _run, _scene, _select

menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
create = import_module(kit.MODULE + ".operators.create")
ae = import_module(kit.MODULE + ".ui.attribute_editor")
ae_layout = import_module(kit.MODULE + ".ui.ae_layout")

DIRECT = {
    "nParticles/Emit from Object": ("object.modifier_add", {"type": 'PARTICLE_SYSTEM', "use_selected_objects": True}),
    "nCloth/Create nCloth": ("object.modifier_add", {"type": 'CLOTH', "use_selected_objects": True}),
    "nCloth/Create Passive Collider": ("object.modifier_add", {"type": 'COLLISION', "use_selected_objects": True}),
    "Fields/Solvers/Create Active Rigid Body": ("rigidbody.objects_add", {"type": 'ACTIVE'}),
    "Fields/Solvers/Create Passive Rigid Body": ("rigidbody.objects_add", {"type": 'PASSIVE'}),
    "Fields/Solvers/Use Selected as Source": ("object.forcefield_toggle", {}),
    "Fluids/3D Container": ("allset.fluid_quick_smoke", {}),
    "Effects/Fire": ("allset.fluid_quick_smoke", {"style": 'FIRE'}),
    "Fields/Solvers/Air": ("object.effector_add", {"type": 'WIND'}),
    "Fields/Solvers/Vortex": ("object.effector_add", {"type": 'VORTEX'}),
}
GREYED = (
    "nParticles/Create Emitter", "nParticles/Create Emitter#2",
    *(f"nParticles/Create Options/{s}" for s in ("Point", "Balls", "Cloud", "Thick Cloud", "Water")),
    "nCache/Transfer Cache To Input Mesh",
    *(f"Fields/Solvers/Initial State/{s}" for s in ("Set for Selected", "Set for All Dynamic", "Clear Initial State",
                                                     "Set From Mesh")),
    "Fields/Solvers/Set Rigid Body Collision", "Fields/Solvers/Assign to Selected", "Effects/Flow/Delete Selected Flow",
)
GONE_OPS = ("fx_emitter", "fx_emit_from_object", "fx_ncloth", "fx_passive", "fx_rigid", "fluid_container_emitter",
            "quick_smoke", "nconstraint", "fx_initial_state", "fx_delete_flow", "fx_clear_initial_state",
            "fx_start_from_mesh", "fx_rigid_interpenetrate", "fx_assign_fields", "fx_field_source")


def test_fx_items_call_blender_operators():
    for path, (op, props) in DIRECT.items():
        kind, target, got = menu_map.spec(path)
        assert (kind, target, got) == ("op", op, props), (path, kind, target, got)
    for path in ("nCloth/Create nCloth", "nParticles/Emit from Object", "Fields/Solvers/Create Active Rigid Body",
                 "Fluids/3D Container"):
        note = notices.NOTICES[path]
        assert "metre scenes" in note[1], (path, note)
        assert "metre scenes" in notices.tooltip(path, True)
    assert not any(k.startswith("FIELD_") for k in create.KINDS)
    for op in GONE_OPS:
        assert not hasattr(bpy.types, f"ALLSET_OT_{op}"), op
    assert "nucleus" not in ae_layout.BY_KIND and not hasattr(ae_layout, "NUCLEUS")


def test_greyed_items_have_a_notice():
    for path in GREYED:
        assert path not in menu_map.MAP, path
        note = notices.greyed_notice(path)
        assert note is not None and "Blender" in note[1], (path, note)
    assert shelf_map.lookup("FX", "Emitter", "NCreateEmitter") is None
    assert shelf_map.lookup("FXCaching", "Clear Initial State", None) is None
    action, _icon = shelf_map.lookup("FX", "Add Emitter", "NEmitFromObject")
    assert action == DIRECT["nParticles/Emit from Object"], action


def test_simulations_are_not_rescaled():
    sc = _scene()                       # a centimetre scene, like the Maya layout
    sc.gravity = (0.0, 0.0, -9.81)
    a, b = _cube("pPlane1"), _cube("pPlane2", z=3.0)
    _select(a, b)
    assert _run("nCloth/Create nCloth") == {'FINISHED'}
    ref = bpy.data.objects.new("ref", bpy.data.meshes.new("ref"))
    ref_md = ref.modifiers.new("Cloth", 'CLOTH')
    for ob in (a, b):
        md = next(m for m in ob.modifiers if m.type == 'CLOTH')
        for attr in ("tension_stiffness", "bending_damping", "quality"):
            assert getattr(md.settings, attr) == getattr(ref_md.settings, attr), (ob.name, attr)
        assert md.collision_settings.distance_min == ref_md.collision_settings.distance_min
        assert "allset_cloth_g" not in ob.keys()
    _select(a, b)
    assert _run("nParticles/Emit from Object") == {'FINISHED'}
    assert all(len(o.particle_systems) == 1 for o in (a, b)), "every selected mesh"
    floor = _cube("floor", z=-5.0)
    _select(floor)
    assert _run("nCloth/Create Passive Collider") == {'FINISHED'}
    assert any(m.type == 'COLLISION' for m in floor.modifiers)
    c, d = _cube("pCube1", z=10.0), _cube("pCube2", z=14.0)
    _select(c, d)
    assert _run("Fields/Solvers/Create Active Rigid Body") == {'FINISHED'}
    assert c.rigid_body.type == d.rigid_body.type == 'ACTIVE'
    assert abs(c.rigid_body.collision_margin - 0.04) < 1e-6, "Blender's margin, not rescaled"
    assert tuple(round(v, 4) for v in sc.gravity) == (0.0, 0.0, -9.81), "the scene gravity is left alone"
    assert not any(t[0] == "NUC" for t in ae.tabs(a))


def test_rigid_body_interpenetration_is_a_generic_constraint():
    sc = _scene()
    c, d = _cube("pCube1"), _cube("pCube2", z=1.0)
    _select(c, d)
    _run("Fields/Solvers/Create Active Rigid Body")
    before = set(bpy.data.objects)
    assert _run("Fields/Solvers/Set Rigid Body Interpenetration") == {'FINISHED'}
    cons = [o for o in set(bpy.data.objects) - before if o.rigid_body_constraint is not None]
    assert len(cons) == 1, cons
    rbc = cons[0].rigid_body_constraint
    assert rbc.type == 'GENERIC' and rbc.disable_collisions and not rbc.use_limit_lin_x
    assert {rbc.object1, rbc.object2} == {c, d}
    assert sc.rigidbody_world is not None


def test_fields_and_field_source():
    _scene()
    for path, kind in (("Fields/Solvers/Air", 'WIND'), ("Fields/Solvers/Drag", 'DRAG'),
                       ("Fields/Solvers/Turbulence", 'TURBULENCE'), ("Fields/Solvers/Newton", 'FORCE')):
        assert _run(path) == {'FINISHED'}, path
        ob = bpy.context.view_layer.objects.active
        assert ob.type == 'EMPTY' and ob.field.type == kind, (path, ob.field.type)
    assert _run("Fields/Solvers/Gravity") == {'FINISHED'}
    grav = bpy.context.view_layer.objects.active
    assert grav.field.type == 'WIND' and grav.matrix_world.to_3x3().col[2].z < -0.99, "blows down"
    assert _run("Fields/Solvers/Uniform") == {'FINISHED'}
    assert bpy.context.view_layer.objects.active.matrix_world.to_3x3().col[2].x > 0.99, "along +X"
    cube = _cube("pCube1")
    _select(cube)
    assert _run("Fields/Solvers/Use Selected as Source") == {'FINISHED'}
    assert cube.field is not None and cube.field.type != 'NONE'


def test_quick_smoke_is_blenders():
    _scene()
    cube = _cube("pCube1")
    _select(cube)
    before = set(bpy.data.objects)
    assert _run("Effects/Smoke") == {'FINISHED'}
    domains = [o for o in set(bpy.data.objects) - before
               if any(m.type == 'FLUID' and m.fluid_type == 'DOMAIN' for m in o.modifiers)]
    assert len(domains) == 1
    assert any(m.type == 'FLUID' and m.fluid_type == 'FLOW' for m in cube.modifiers)


def test_ncache_bake_and_delete():
    sc = _scene()
    sc.frame_end = 10
    cloth, other = _cube("pPlane1", z=2.0), _cube("pPlane2", z=4.0)
    for ob in (cloth, other):
        _select(ob)
        _run("nCloth/Create nCloth")
    pc = next(m for m in cloth.modifiers if m.type == 'CLOTH').point_cache
    pc2 = next(m for m in other.modifiers if m.type == 'CLOTH').point_cache
    _select(cloth)
    assert bpy.ops.allset.ncache(action='CREATE', kind='NOBJECT') == {'FINISHED'}
    assert pc.is_baked and not pc2.is_baked, "only the selection"
    assert bpy.ops.allset.ncache(action='DELETE', kind='ALL') == {'FINISHED'}
    assert not pc.is_baked
    _select()
    bpy.ops.allset.ncache(action='CREATE', kind='NOBJECT')
    assert pc.is_baked and pc2.is_baked, "nothing selected = the whole scene"
    bpy.ops.allset.ncache(action='DELETE', kind='NOBJECT')
    assert bpy.ops.allset.ncache(action='CREATE', kind='FLUID') == {'CANCELLED'}, "no fluid domain"


def test_no_fx_handlers_or_scene_props():
    names = {getattr(f, "__module__", "") for lst in (bpy.app.handlers.depsgraph_update_post,
                                                       bpy.app.handlers.frame_change_post, bpy.app.handlers.load_post)
             for f in lst}
    assert not any(n.endswith((".fx", ".fx_more")) for n in names), names
    assert not hasattr(bpy.types.WindowManager, "allset_nparticle_style")
