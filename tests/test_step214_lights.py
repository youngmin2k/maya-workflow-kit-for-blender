"""Step 214 (#120): Maya Ambient Light / Volume Light stand-ins (operators/maya_lights.py) — creation, Maya values,
World ambient nodes, UI wiring, and headless Cycles / EEVEE renders following Maya's lighting rules
(tables printed as STEP214_LIGHTS lines in the log)."""

import math
import os
from importlib import import_module

import bpy

import kit

ml = import_module(kit.MODULE + ".operators.maya_lights")
lights = import_module(kit.MODULE + ".operators.lights")
create = import_module(kit.MODULE + ".operators.create")
material = import_module(kit.MODULE + ".operators.material")
units = import_module(kit.MODULE + ".operators.units")
channel_box = import_module(kit.MODULE + ".ui.channel_box")
attribute_editor = import_module(kit.MODULE + ".ui.attribute_editor")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
light_editor = import_module(kit.MODULE + ".ui.light_editor")


def _update():
    """A depsgraph update plus the queued light / World sync (the handler defers it to a 0 s timer, step 229)."""
    bpy.context.view_layer.update()
    ml.flush()


def _clear(world=False):
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for lt in list(bpy.data.lights):
        bpy.data.lights.remove(lt)
    if world:
        bpy.context.scene.world = None
        for w in list(bpy.data.worlds):
            bpy.data.worlds.remove(w)
    ml.sync(bpy.context.scene)


def _make(kind):
    assert bpy.ops.allset.create(kind=kind) == {'FINISHED'}
    return bpy.context.view_layer.objects.active


def _kit_nodes(world):
    return world is not None and world.node_tree is not None and world.node_tree.nodes.get(ml.W_ADD) is not None


# --- creation / values ---------------------------------------------------------------------------------------------

def test_create_names_and_defaults():
    _clear(world=True)
    k = units.maya_unit(bpy.context.scene)
    amb = _make('AMBIENT_LIGHT')
    assert (amb.name, amb.data.name) == ("ambientLight1", "ambientLightShape1"), (amb.name, amb.data.name)
    assert amb.location.length < 1e-9 and amb.data.type == 'POINT'
    assert ml.kind(amb.data) == "ambientLight"
    assert abs(amb.data.allset_intensity - 1.0) < 1e-6 and abs(amb.data.allset_ambient_shade - 0.45) < 1e-6
    assert not amb.data.use_shadow and amb.data.specular_factor == 0.0 and amb.data.shadow_soft_size == 0.0
    want = 0.45 / material.MAYA_DIFFUSE * lights.power_factor('POINT', 0, k)
    assert abs(amb.data.energy - want) < 1e-6 * want, (amb.data.energy, want)
    sc = bpy.context.scene
    assert sc.world is not None and sc.world.get(ml.W_MADE) and _kit_nodes(sc.world), "kit World with ambient nodes"
    bg = sc.world.node_tree.nodes[ml.W_BG]
    assert all(abs(c - 0.55 / 0.8) < 1e-6 for c in bg.inputs["Color"].default_value[:3]), bg.inputs[0].default_value[:]
    vol = _make('VOLUME_LIGHT')
    assert (vol.name, vol.data.name) == ("volumeLight1", "volumeLightShape1")
    assert ml.kind(vol.data) == "volumeLight" and not vol.data.use_shadow
    assert vol.data.use_custom_distance and abs(vol.data.cutoff_distance - k) < 1e-6 * k
    assert vol.data.node_tree.nodes.get(ml.V_FALLOFF) is not None
    assert vol.data.node_tree.nodes.get(lights.FALLOFF_NODE) is None


def test_intensity_shade_round_trip_and_radius():
    _clear(world=True)
    k = units.maya_unit(bpy.context.scene)
    amb = _make('AMBIENT_LIGHT')
    amb.data.allset_intensity = 2.0
    assert abs(amb.data.allset_intensity - 2.0) < 1e-6
    amb.data.allset_ambient_shade = 0.0
    assert amb.data.energy == 0.0 and abs(amb.data.allset_intensity - 2.0) < 1e-6, "intensity kept with s 0"
    bg = bpy.context.scene.world.node_tree.nodes[ml.W_BG]
    assert abs(bg.inputs["Color"].default_value[0] - 2.0 / 0.8) < 1e-6
    amb.data.allset_ambient_shade = 1.0
    assert abs(bg.inputs["Color"].default_value[0]) < 1e-9
    assert abs(amb.data.energy - 2.0 / 0.8 * lights.power_factor('POINT', 0, k)) < 1e-3
    assert lights.decay(amb.data) == 0
    # volume: radius follows the object's scale (depsgraph handler)
    vol = _make('VOLUME_LIGHT')
    vol.scale = (3.0, 1.0, 2.0)
    _update()
    assert abs(vol.data.cutoff_distance - 3.0 * k) < 1e-6, vol.data.cutoff_distance
    assert abs(vol.data.node_tree.nodes[ml.V_RATIO].inputs[1].default_value - 3.0 * k) < 1e-6
    vol.data.allset_intensity = 0.5
    assert abs(vol.data.energy - 4 * math.pi ** 2 * ml.VOLUME_A * (3 * k) ** 2 * 0.5) < 1e-6


def test_world_sum_hide_delete_restore():
    _clear(world=True)
    sc = bpy.context.scene
    world = bpy.data.worlds.new("userWorld")
    world.use_nodes = True
    sc.world = world
    tree = world.node_tree
    out = next(n for n in tree.nodes if n.type == 'OUTPUT_WORLD')
    user_bg = out.inputs["Surface"].links[0].from_node
    a = _make('AMBIENT_LIGHT')
    b = _make('AMBIENT_LIGHT')
    assert b.name == "ambientLight2"
    b.data.color = (1.0, 0.0, 0.0)
    _update()
    bg = tree.nodes[ml.W_BG]
    col = bg.inputs["Color"].default_value
    assert abs(col[0] - 2 * 0.55 / 0.8) < 1e-6 and abs(col[1] - 0.55 / 0.8) < 1e-6, col[:]
    add = tree.nodes[ml.W_ADD]
    assert add.inputs[0].links[0].from_node == user_bg and out.inputs["Surface"].links[0].from_node == add
    b.hide_render = True
    _update()
    assert abs(bg.inputs["Color"].default_value[0] - 0.55 / 0.8) < 1e-6, "a hidden ambient light adds nothing"
    bpy.data.objects.remove(a)
    bpy.data.objects.remove(b)
    _update()
    assert not _kit_nodes(world) and tree.nodes.get(ml.W_BG) is None
    assert out.inputs["Surface"].links[0].from_node == user_bg, "the user's World link is back"
    assert sc.world == world and bpy.data.worlds.get("userWorld") is not None
    # a kit-made World goes with the last ambient light
    _clear(world=True)
    a = _make('AMBIENT_LIGHT')
    assert sc.world.get(ml.W_MADE)
    bpy.data.objects.remove(a)
    _update()
    assert sc.world is None and not bpy.data.worlds


def test_undo_and_unregister_remove_world_nodes():
    _clear(world=True)
    sc = bpy.context.scene
    bpy.ops.ed.undo_push(message="before")
    assert bpy.ops.allset.create('EXEC_DEFAULT', True, kind='AMBIENT_LIGHT') == {'FINISHED'}
    assert _kit_nodes(bpy.context.scene.world)
    bpy.ops.ed.undo()
    sc = bpy.context.scene
    assert not any(ob.type == 'LIGHT' for ob in sc.objects)
    assert not _kit_nodes(sc.world), "undo takes the World part back too"
    _clear(world=True)
    _make('AMBIENT_LIGHT')
    name = bpy.context.scene.world.name
    kit.disable()
    try:
        assert not _kit_nodes(bpy.data.worlds.get(name)), "disable removes the kit nodes"
    finally:
        kit.enable()
    _update()
    assert _kit_nodes(bpy.context.scene.world), "re-enabled: the handler puts them back"


# --- UI wiring -----------------------------------------------------------------------------------------------------

def test_menus_shelf_editor_ae_channel_box():
    for path, kind in (("Create/Lights/Ambient Light", 'AMBIENT_LIGHT'), ("Create/Lights/Volume Light", 'VOLUME_LIGHT'),
                       ("Hypershade/Create/Lights/Ambient Light", 'AMBIENT_LIGHT'),
                       ("Hypershade/Create/Lights/Volume Light", 'VOLUME_LIGHT')):
        action = menu_map.MAP.get(path)
        assert action is not None and action[1] == {"kind": kind}, (path, action)
    assert "Create/Lights" not in notices.CATEGORIES and "Hypershade/Create/Lights" not in notices.CATEGORIES
    assert shelf_map.lookup("Rendering", "Ambient Light", "CreateAmbientLight")[0][1] == {"kind": 'AMBIENT_LIGHT'}
    assert shelf_map.lookup("Rendering", "Volume Light", "CreateVolumeLight")[0][1] == {"kind": 'VOLUME_LIGHT'}
    kinds = [kd for kd, _i in light_editor.CREATE]
    assert kinds[0] == 'AMBIENT_LIGHT' and kinds[-1] == 'VOLUME_LIGHT'
    _clear(world=True)
    for kind, maya, first in (('AMBIENT_LIGHT', "ambientLight", "Ambient Light Attributes"),
                              ('VOLUME_LIGHT', "volumeLight", "Volume Light Attributes")):
        ob = _make(kind)
        assert attribute_editor.node_type(ob) == maya
        sections, lid = attribute_editor.sections_for(ob, "S")
        assert sections and sections[0].name == first and lid == maya.lower(), (sections, lid)
        rows = [name for k_, name, _t, _n in channel_box.wanted_rows(ob) if k_ == "SHAPE"]
        assert rows == ["maya:colorR", "maya:colorG", "maya:colorB", "allset_intensity"], rows
        paths = channel_box.shape_paths(ob.data, channel_box.SHAPE_PREFIX + "allset_intensity")
        assert paths == [(f'["{ml.INTENSITY_PROP}"]', -1)], paths
    # a keyed intensity drives the power on frame change
    amb = bpy.data.objects["ambientLight1"]
    amb.data[ml.INTENSITY_PROP] = 1.0
    amb.data.keyframe_insert(f'["{ml.INTENSITY_PROP}"]', frame=1)
    amb.data[ml.INTENSITY_PROP] = 3.0
    amb.data.keyframe_insert(f'["{ml.INTENSITY_PROP}"]', frame=10)
    sc = bpy.context.scene
    sc.frame_set(10)
    k = units.maya_unit(sc)
    assert abs(amb.data.energy - 3.0 * 0.45 / 0.8 * lights.power_factor('POINT', 0, k)) < 1e-3, amb.data.energy
    sc.frame_set(1)
    assert abs(amb.data.allset_intensity - 1.0) < 1e-6


# --- renders -------------------------------------------------------------------------------------------------------

RES = 24
EEVEE = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in {
    e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items} else 'BLENDER_EEVEE'


def _setup_render(engine, k, half_width):
    sc = bpy.context.scene
    sc.render.engine = engine
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'OPEN_EXR'
    sc.view_settings.view_transform = 'Standard'
    if engine == 'CYCLES':
        sc.cycles.samples, sc.cycles.use_denoising = 64, False
        sc.cycles.max_bounces = 0          # Maya Software has no bounce light
    cam = bpy.data.objects.new("probeCam", bpy.data.cameras.new("probeCam"))
    sc.collection.objects.link(cam)
    cam.data.type, cam.data.ortho_scale = 'ORTHO', 2 * half_width * k
    cam.data.clip_start, cam.data.clip_end = 0.01 * k, 100 * k
    cam.location = (0.0, 0.0, 20.0 * k)
    cam.hide_render = False
    sc.camera = cam
    return sc, cam


def _render(tag):
    sc = bpy.context.scene
    path = os.path.join(bpy.app.tempdir, f"step214_{tag}.exr")
    sc.render.filepath = path
    ml.sync(sc)
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path, check_existing=False)
    try:
        return img.size[0], img.size[1], img.pixels[:]
    finally:
        bpy.data.images.remove(img)


def test_ambient_keeps_the_camera_background_black():
    """Maya's ambient light doesn't change the black render background: the World part is for non-camera rays."""
    for engine in ('CYCLES', EEVEE):
        _clear(world=True)
        k = units.maya_unit(bpy.context.scene)
        _setup_render(engine, k, 0.05)
        amb = _make('AMBIENT_LIGHT')
        amb.data.allset_ambient_shade = 0.0
        w, h, px = _render(f"amb_bg_{engine}")
        assert max(px[i * 4 + c] for i in range(w * h) for c in range(3)) < 1e-4, engine
    _clear(world=True)
