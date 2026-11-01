"""Files saved by older versions are tidied when they are opened (operators/legacy_cleanup.py, temporary): a
leftover ``defaultLight`` goes (the kit render camera ``persp`` stays the scene camera: renders still use it), the old camera Renderable values are dropped; the file opens without errors and
the user's own objects stay. Old Ambient / Volume Lights: the World's "Maya Ambient" nodes go (the World's own
output linked back), the lights become plain kit point lights with their Maya intensity, a Light Editor Isolate still
on is undone and the Illuminates by Default value is dropped. Old kit FX: the nucleus gravity (9.8 x the Maya unit)
goes back to Blender's 9.81 unless changed by hand since, kit cloth stiffness / damping lose their rescale, the old FX
markers are dropped."""

import os
from importlib import import_module

import bpy

import kit

lc = import_module(kit.MODULE + ".operators.legacy_cleanup")


def _path(name):
    return os.path.join(bpy.app.tempdir, name)


def _old_file(name, persp_in_collection=False):
    """A scene the way an older version saved it after a kit render (built here with plain data)."""
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    cube = bpy.context.active_object.name
    mine = bpy.data.objects.new("shotCam", bpy.data.cameras.new("shotCamShape"))
    sc.collection.objects.link(mine)
    mine.data[lc.RENDERABLE] = True
    persp = bpy.data.objects.new("persp", bpy.data.cameras.new("perspShape"))
    persp["allset_persp"] = True
    persp.use_fake_user = True
    persp.data[lc.RENDERABLE] = False
    if persp_in_collection:
        sc.collection.objects.link(persp)
    sc.camera = persp
    light = bpy.data.objects.new("defaultLight", bpy.data.lights.new("defaultLight", 'SUN'))
    light[lc.DEFAULT_LIGHT] = True
    light.data[lc.DEFAULT_LIGHT] = True
    sc.collection.objects.link(light)
    light.parent = persp
    path = _path(name)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    return path, cube


def test_old_file_is_cleaned_on_open():
    path, cube = _old_file("legacy_render.blend")
    bpy.ops.wm.read_homefile(use_empty=True)
    assert lc._on_load in bpy.app.handlers.load_post
    bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    assert sc.camera == bpy.data.objects.get("persp"), "the kit render camera stays the scene camera"
    assert not [o for o in bpy.data.objects if o.get(lc.DEFAULT_LIGHT)]
    assert not [d for d in bpy.data.lights if d.get(lc.DEFAULT_LIGHT)]
    assert not [c for c in bpy.data.cameras if lc.RENDERABLE in c.keys()]
    assert cube in bpy.data.objects and "shotCam" in bpy.data.objects, "the user's objects stay"
    # once cleaned there is nothing left to do
    assert not any(lc.clean().values())


def test_persp_linked_into_the_scene_is_kept():
    path, _cube = _old_file("legacy_render_linked.blend", persp_in_collection=True)
    bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    assert "persp" in bpy.data.objects and sc.camera == bpy.data.objects["persp"], "a linked camera is the user's"
    assert "defaultLight" not in bpy.data.objects


def test_handler_follows_maya_mode_and_disable():
    sw = import_module(kit.MODULE + ".switch")
    sw.set_mode(False, layout=False)
    try:
        assert lc._on_load not in bpy.app.handlers.load_post
    finally:
        sw.set_mode(True, layout=False)
    assert lc._on_load in bpy.app.handlers.load_post
    kit.disable()
    try:
        assert not [h for h in bpy.app.handlers.load_post if getattr(h, "__module__", "").endswith("legacy_cleanup")]
    finally:
        kit.enable()


def _old_lights_file(name, kit_world=False):
    """A scene the way an older version saved it with an Ambient and a Volume Light, a Light Editor Isolate on and
    a light whose Illuminates by Default is off (built here with plain data)."""
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    world = bpy.data.worlds.new("World")
    sc.world = world
    if kit_world:
        world[lc.WORLD_MADE] = True
    compat = import_module(kit.MODULE + ".compat")
    compat.ensure_world_nodes(world)
    tree = world.node_tree
    out = next((n for n in tree.nodes if n.type == 'OUTPUT_WORLD'), None) or tree.nodes.new('ShaderNodeOutputWorld')
    bg = next((n for n in tree.nodes if n.type == 'BACKGROUND'), None) or tree.nodes.new('ShaderNodeBackground')
    amb = tree.nodes.new('ShaderNodeBackground')
    ray = tree.nodes.new('ShaderNodeLightPath')
    nc = tree.nodes.new('ShaderNodeMath')
    add = tree.nodes.new('ShaderNodeAddShader')
    for node, nm in ((amb, "Maya Ambient"), (ray, "Maya Ambient Ray"), (nc, "Maya Ambient Not Camera"),
                     (add, lc.WORLD_ADD)):
        node.name = nm
    tree.links.new(ray.outputs["Is Camera Ray"], nc.inputs[1])
    tree.links.new(nc.outputs[0], amb.inputs["Strength"])
    tree.links.new(bg.outputs[0], add.inputs[0])
    tree.links.new(amb.outputs[0], add.inputs[1])
    tree.links.new(add.outputs[0], out.inputs["Surface"])
    obs = {}
    for nm, kind in (("ambientLight1", "ambientLight"), ("volumeLight1", "volumeLight")):
        data = bpy.data.lights.new(nm + "Shape", 'POINT')
        data[lc.LIGHT_KIND] = kind
        data[lc.LIGHT_INTENSITY] = 2.0
        data["allset_ambient_shade"] = 0.45
        ob = bpy.data.objects.new(nm, data)
        sc.collection.objects.link(ob)
        obs[nm] = ob
    vol = obs["volumeLight1"].data
    vol[lc.VOLUME_NODES_ON] = True
    compat.ensure_light_nodes(vol)
    vt = vol.node_tree
    emission = next(n for n in vt.nodes if n.type == 'EMISSION')
    falloff = vt.nodes.new('ShaderNodeLightFalloff')
    falloff.name = "Maya Volume Falloff"
    vt.links.new(falloff.outputs["Constant"], emission.inputs["Strength"])
    sun = bpy.data.objects.new("directionalLight1", bpy.data.lights.new("directionalLightShape1", 'SUN'))
    sc.collection.objects.link(sun)
    sun.hide_render = sun.hide_viewport = True              # turned off by the isolate
    sun[lc.ILLUMINATES] = False
    sc[lc.LIGHT_ISOLATE] = {"light": "ambientLight1", "saved": {"directionalLight1": [False, False],
                                                               "ambientLight1": [False, False]}}
    path = _path(name)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    return path


def test_old_lights_are_cleaned_on_open():
    path = _old_lights_file("legacy_lights.blend")
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    tree = sc.world.node_tree
    assert not [n.name for n in tree.nodes if n.name.startswith("Maya Ambient")]
    out = next(n for n in tree.nodes if n.type == 'OUTPUT_WORLD')
    assert out.inputs["Surface"].links[0].from_node.type == 'BACKGROUND', "the World's own background is back"
    lights = import_module(kit.MODULE + ".operators.lights")
    for nm in ("ambientLight1", "volumeLight1"):
        data = bpy.data.objects[nm].data
        assert not [k for k in data.keys() if k in (*lc.LIGHT_PROPS, lc.VOLUME_NODES_ON)], (nm, data.keys())
        assert abs(lights.intensity(data) - 2.0) < 1e-6 and lights.decay(data) == 0, nm
    vt = bpy.data.objects["volumeLight1"].data.node_tree
    assert vt.nodes.get("Maya Volume Falloff") is None and vt.nodes.get(lights.FALLOFF_NODE) is not None
    sun = bpy.data.objects["directionalLight1"]
    assert not sun.hide_render and not sun.hide_viewport, "the isolate is undone"
    assert lc.LIGHT_ISOLATE not in sc.keys() and lc.ILLUMINATES not in sun.keys()
    assert not any(lc.clean().values())


def test_kit_made_world_is_removed():
    path = _old_lights_file("legacy_lights_world.blend", kit_world=True)
    bpy.ops.wm.open_mainfile(filepath=path)
    assert bpy.context.scene.world is None
    assert "World" not in bpy.data.worlds


def _old_fx_file(name, hand_gravity=None):
    """A centimetre scene the way an older version saved it after kit FX: nucleus gravity 9.8 x 0.01, a cloth with
    stiffness and damping x 0.01, the markers of the old FX items."""
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    us = sc.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0
    nuc = getattr(sc, lc.NUCLEUS)
    nuc.exists = True
    sc.gravity = hand_gravity or (0.0, 0.0, -0.098)
    bpy.ops.mesh.primitive_plane_add(size=0.2)
    cloth = bpy.context.active_object
    cloth.name = "pPlane1"
    st = cloth.modifiers.new("nCloth1", 'CLOTH').settings
    base = {attr: getattr(st, attr) for attr in lc.CLOTH_SCALED}
    for attr in lc.CLOTH_SCALED:
        setattr(st, attr, base[attr] * 0.01)
    cloth[lc.CLOTH_G] = 0.01
    cloth["allset_nconstraints"] = ["dynamicConstraint1"]
    cloth.data.attributes.new(lc.FX_MESH_ATTRIBUTE, 'FLOAT_VECTOR', 'POINT')
    empty = bpy.data.objects.new("dynamicConstraint1", None)
    empty["allset_nconstraint"] = cloth.name
    sc.collection.objects.link(empty)
    coll = bpy.data.collections.new("pPlane1Fields")
    coll["allset_fields_of"] = cloth.name
    coll.use_fake_user = True
    path = _path(name)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    return path, base


def test_old_fx_scene_is_cleaned_on_open():
    path, base = _old_fx_file("legacy_fx.blend")
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    assert tuple(round(v, 4) for v in sc.gravity) == (0.0, 0.0, -9.81), tuple(sc.gravity)
    assert not sc.is_property_set(lc.NUCLEUS), "the nucleus values are dropped"
    cloth = bpy.data.objects["pPlane1"]
    st = cloth.modifiers["nCloth1"].settings
    for attr in lc.CLOTH_SCALED:
        assert abs(getattr(st, attr) - base[attr]) < 1e-4 * max(1.0, base[attr]), (attr, getattr(st, attr), base[attr])
    assert lc.CLOTH_G not in cloth.keys() and "allset_nconstraints" not in cloth.keys()
    assert cloth.data.attributes.get(lc.FX_MESH_ATTRIBUTE) is None
    empty = bpy.data.objects["dynamicConstraint1"]
    assert "allset_nconstraint" not in empty.keys(), "the marker goes, the empty stays"
    assert "allset_fields_of" not in bpy.data.collections["pPlane1Fields"].keys()
    assert not any(lc.clean().values())


def test_gravity_changed_by_hand_stays():
    path, _base = _old_fx_file("legacy_fx_hand.blend", hand_gravity=(0.0, 0.0, -3.0))
    bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    assert abs(sc.gravity.z + 3.0) < 1e-6, tuple(sc.gravity)
    assert not sc.is_property_set(lc.NUCLEUS)
