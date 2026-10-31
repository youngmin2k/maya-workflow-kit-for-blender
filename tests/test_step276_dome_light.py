"""Step 276 (#201): Create > Lights > Dome Light = Blender's World environment, driven by a domeLight locator."""

import os
import sys
import tempfile
from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

dome = import_module(kit.MODULE + ".operators.dome_light")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    scene = bpy.context.scene
    if scene.world is not None:
        w = scene.world
        scene.world = None
        bpy.data.worlds.remove(w)


def _image_file(name="dome_test.png"):
    path = os.path.join(tempfile.gettempdir(), name)
    img = bpy.data.images.new("dome_src", 8, 4)
    img.pixels = [0.5] * (8 * 4 * 4)
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    return path


def _tree():
    return bpy.context.scene.world.node_tree


def _linked(tree, from_name, to_name):
    return any(lk.from_node.name == from_name and lk.to_node.name == to_name for lk in tree.links)


def test_nodes_and_locator():
    _clean()
    assert bpy.ops.allset.dome_light('EXEC_DEFAULT') == {'FINISHED'}
    scene = bpy.context.scene
    assert scene.world is not None
    tree = _tree()
    for name in dome.NODES:
        assert tree.nodes.get(name) is not None, name
    assert _linked(tree, dome.N_COORD, dome.N_MAP) and _linked(tree, dome.N_MAP, dome.N_TEX)
    assert _linked(tree, dome.N_TEX, dome.N_BG)
    out = dome._output(tree)
    assert out.inputs["Surface"].links[0].from_node.name == dome.N_BG
    ob = bpy.data.objects.get("domeLight1")
    assert ob is not None and ob.get(dome.MARK) and ob[dome.INTENSITY] == 1.0
    assert bpy.context.active_object == ob and ob.select_get()
    # Channel Box: Intensity is a numeric custom attribute; it and the rotation drive the World
    cb = import_module(kit.MODULE + ".ui.channel_box")
    assert dome.INTENSITY in cb.custom_keys(ob)
    ob[dome.INTENSITY] = 2.5
    ob.rotation_euler = (0.0, 0.0, 1.0)
    ob.update_tag()
    bpy.context.view_layer.update()
    bg, mapping = tree.nodes[dome.N_BG], tree.nodes[dome.N_MAP]
    assert abs(bg.inputs["Strength"].default_value - 2.5) < 1e-6, bg.inputs["Strength"].default_value
    assert abs(mapping.inputs["Rotation"].default_value[2] - 1.0) < 1e-6
    assert mapping.vector_type == 'TEXTURE'


def test_second_run_reuses_world_and_takes_the_image():
    _clean()
    bpy.ops.allset.dome_light('EXEC_DEFAULT')
    world = bpy.context.scene.world
    n_nodes = len(world.node_tree.nodes)
    path = _image_file()
    assert bpy.ops.allset.dome_light('EXEC_DEFAULT', filepath=path) == {'FINISHED'}
    assert bpy.context.scene.world == world and len(world.node_tree.nodes) == n_nodes
    assert [o.name for o in bpy.context.scene.objects if o.get(dome.MARK)] == ["domeLight1"]
    img = world.node_tree.nodes[dome.N_TEX].image
    assert img is not None and os.path.normcase(bpy.path.abspath(img.filepath)) == os.path.normcase(path)
    # the same file again: no second image
    bpy.ops.allset.dome_light('EXEC_DEFAULT', filepath=path)
    assert sum(1 for i in bpy.data.images if os.path.normcase(bpy.path.abspath(i.filepath)) == os.path.normcase(path)) == 1
    # a missing file: warning, the dome stays as it was
    assert bpy.ops.allset.dome_light('EXEC_DEFAULT', filepath=path + ".missing") == {'FINISHED'}
    assert world.node_tree.nodes[dome.N_TEX].image == img


def test_existing_world_keeps_its_other_nodes():
    _clean()
    world = bpy.data.worlds.new("Mine")
    bpy.context.scene.world = world
    world.use_nodes = True
    tree = world.node_tree
    old_bg = next(nd for nd in tree.nodes if nd.type == 'BACKGROUND')
    bpy.ops.allset.dome_light('EXEC_DEFAULT')
    assert bpy.context.scene.world == world
    assert old_bg.name in tree.nodes                      # kept, only unplugged from the output
    assert dome._output(tree).inputs["Surface"].links[0].from_node.name == dome.N_BG


def test_one_undo_step():
    _clean()
    bpy.ops.ed.undo_push(message="before dome")
    assert bpy.ops.allset.dome_light('EXEC_DEFAULT', True) == {'FINISHED'}
    assert bpy.data.objects.get("domeLight1") is not None
    bpy.ops.ed.undo()
    assert bpy.data.objects.get("domeLight1") is None
    assert bpy.context.scene.world is None or bpy.context.scene.world.node_tree.nodes.get(dome.N_BG) is None


def test_menu_item_and_draw():
    paths = [p for p, _it in menu_sets.iter_items() if p.startswith("Create/Lights/")]
    assert paths[-1] == "Create/Lights/Dome Light", paths
    assert menu_map.spec("Create/Lights/Dome Light")[1] == "allset.dome_light"
    # Create and its Lights submenu draw without a Python error, Dome Light last, after a divider
    rec = import_module("test_step108_menu_hotkeys")
    top = rec.draw_menu("mainCreateMenu")
    lights = next(idn for kind, text, idn in top if kind == "menu" and text.startswith("Lights"))
    log = rec.Recorder()
    getattr(bpy.types, lights).draw(SimpleNamespace(layout=log), bpy.context)
    ops = [(kind, text) for kind, text, _x in log.log if kind in ("op", "sep")]
    assert ops[-1][0] == "op" and ops[-1][1].startswith("Dome Light") and ops[-2][0] == "sep", ops


def test_disable_removes_it():
    kit.disable()
    assert not hasattr(bpy.types, "ALLSET_OT_dome_light")
    kit.enable()
    assert hasattr(bpy.types, "ALLSET_OT_dome_light")
