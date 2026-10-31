"""Lighting menus call Blender: Create > Lights > Ambient / Volume Light are greyed with a notice (Blender has neither),
Lighting/Shading light / shadow links run Blender's light linking operators (active object = the light), the Light
Linking Editor opens Blender's Light Linking panel (Properties > Object), Light Editor = an Outliner window of the
lights, Render Settings = Blender's Render tab. The Channel Box / Attribute Editor Intensity and Decay Rate stay."""

from importlib import import_module

import bpy

import kit

menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
create = import_module(kit.MODULE + ".operators.create")
lights = import_module(kit.MODULE + ".operators.lights")


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _select(objects, active):
    for ob in bpy.context.scene.objects:
        ob.select_set(ob in objects)
    bpy.context.view_layer.objects.active = active


def _entries(coll):
    if coll is None:
        return {}
    return {ob.name: co.light_linking.link_state for ob, co in zip(coll.objects, coll.collection_objects)}


def test_ambient_and_volume_lights_are_greyed_with_a_notice():
    for menu in ("Create", "Hypershade/Create"):
        for label in ("Ambient Light", "Volume Light"):
            path = f"{menu}/Lights/{label}"
            assert path not in menu_map.MAP, path
            note = notices.greyed_notice(path)
            assert note is not None and "Blender has no" in note[1], (path, note)
        assert f"{menu}/Lights/Point Light" in menu_map.MAP
    for label, command in (("Ambient Light", "CreateAmbientLight"), ("Volume Light", "CreateVolumeLight")):
        assert shelf_map.lookup("Rendering", label, command) is None, label
    assert "AMBIENT_LIGHT" not in create.KINDS and "VOLUME_LIGHT" not in create.KINDS
    assert not hasattr(bpy.types.Light, "allset_ambient_shade")


def test_light_links_run_blender_light_linking():
    _clear()
    bpy.ops.allset.create(kind='CUBE')
    bpy.ops.allset.create(kind='CUBE')
    bpy.ops.allset.create(kind='POINT_LIGHT')
    obs = {o.name: o for o in bpy.context.scene.objects}
    light = next(o for o in obs.values() if o.type == 'LIGHT')
    a, b = obs["pCube1"], obs["pCube2"]
    _select([light, b], light)
    assert bpy.ops.allset.menu_item(item="Lighting/Shading/Break Light Links") == {'FINISHED'}
    assert _entries(light.light_linking.receiver_collection) == {"pCube2": 'EXCLUDE'}
    _select([light, a], light)
    bpy.ops.allset.menu_item(item="Lighting/Shading/Make Light Links")
    assert _entries(light.light_linking.receiver_collection) == {"pCube2": 'EXCLUDE', "pCube1": 'INCLUDE'}
    _select([light, b], light)
    bpy.ops.allset.menu_item(item="Lighting/Shading/Break Shadow Links")
    assert _entries(light.light_linking.blocker_collection) == {"pCube2": 'EXCLUDE'}
    _select([light], light)
    bpy.ops.allset.menu_item(item="Lighting/Shading/Select Objects Illuminated by Light")
    assert {o.name for o in bpy.context.selected_objects} >= {"pCube1", "pCube2"}
    for kind in ("Illuminating", "Shadowing"):
        path = f"Lighting/Shading/Select Lights {kind} Object"
        assert path not in menu_map.MAP and notices.greyed_notice(path) is not None
    assert not hasattr(bpy.types.Object, "allset_illuminates_by_default")


def test_editors_open_blender_editors():
    props = ("allset.open_editor", {"ui_type": 'PROPERTIES', "tab": 'OBJECT'})
    for path in ("Lighting/Shading/Light Linking Editor", "Windows/Relationship Editors/Light Linking/Light-Centric",
                 "Windows/Relationship Editors/Light Linking/Object-Centric"):
        assert menu_map.MAP[path] == props, path
    assert menu_map.MAP["Windows/Rendering Editors/Light Editor"] == "allset.light_editor"
    assert menu_map.MAP["Render/Render Settings..."] == "allset.render_settings"
    for op in (bpy.ops.allset.light_editor, bpy.ops.allset.render_settings):
        op.get_rna_type()
    for gone in ("ALLSET_OT_light_link", "ALLSET_OT_light_linking_editor", "ALLSET_OT_rs_defaults",
                 "ALLSET_PT_light_editor", "ALLSET_PT_rs_common"):
        assert not hasattr(bpy.types, gone), gone


def test_intensity_and_decay_rows_stay():
    _clear()
    bpy.ops.allset.create(kind='POINT_LIGHT')
    data = bpy.context.active_object.data
    assert abs(data.allset_intensity - 1.0) < 1e-6 and data.allset_decay == 'NO_DECAY'
    data.allset_intensity = 3.0
    assert abs(lights.intensity(data) - 3.0) < 1e-6
    assert lights.key_paths(data, "allset_intensity") == [("energy", -1)]


def test_no_light_handlers_left():
    names = {getattr(h, "__module__", "") for lst in (bpy.app.handlers.depsgraph_update_post,
                                                       bpy.app.handlers.frame_change_post,
                                                       bpy.app.handlers.undo_post, bpy.app.handlers.redo_post)
             for h in lst}
    assert not [n for n in names if n.endswith(("maya_lights", "light_links"))], names
