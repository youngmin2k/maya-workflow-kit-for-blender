# SPDX-License-Identifier: GPL-3.0-or-later
"""Create > Lights > Dome Light (#201): an image-based light around the whole scene.

Maya's own Create > Lights has no dome light (renderers add one). In Blender a dome light is the World: an
environment texture lights everything and shows behind the scene. ``allset.dome_light`` builds that on the scene's
World (the same World again on a second run) and adds a ``domeLight1`` locator so the Maya user finds it
the Maya way: selectable in the Outliner, Rotate X / Y / Z turn the image (Maya's dome transform), and its
Intensity attribute in the Channel Box is the World strength. The menu item opens a file browser for the image
(.hdr / .exr / any image); choosing a new file later replaces the image of the same dome.
"""

import os

import bpy

from . import naming, units

BASE = "domeLight"
MARK = "allset_dome"                 # object ID property: this locator drives the World's dome nodes
N_TEX, N_MAP, N_COORD, N_BG = "Maya Dome Texture", "Maya Dome Mapping", "Maya Dome Coordinates", "Maya Dome"
NODES = (N_TEX, N_MAP, N_COORD, N_BG)
INTENSITY = "intensity"


def find_dome(scene):
    """The scene's dome locator, or None."""
    return next((ob for ob in scene.objects if ob.get(MARK)), None)


def _output(tree):
    outs = [nd for nd in tree.nodes if nd.type == 'OUTPUT_WORLD']
    return next((nd for nd in outs if nd.is_active_output), outs[0] if outs else None)


def _node(tree, kind, name, location):
    node = tree.nodes.get(name)
    if node is None:
        node = tree.nodes.new(kind)
        node.name = node.label = name
        node.location = location
    return node


def ensure_world(scene):
    """The scene's World with the dome nodes (made when missing): Texture Coordinate > Mapping > Environment Texture >
    Background > the World output (behind the Maya ambient light's add node when there is one)."""
    from .. import compat
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    compat.ensure_world_nodes(world)
    tree = world.node_tree
    out = _output(tree) or tree.nodes.new('ShaderNodeOutputWorld')
    x, y = out.location.x, out.location.y
    coord = _node(tree, 'ShaderNodeTexCoord', N_COORD, (x - 960, y))
    mapping = _node(tree, 'ShaderNodeMapping', N_MAP, (x - 760, y))
    mapping.vector_type = 'TEXTURE'          # the image turns with the locator, not against it
    tex = _node(tree, 'ShaderNodeTexEnvironment', N_TEX, (x - 520, y))
    bg = _node(tree, 'ShaderNodeBackground', N_BG, (x - 240, y))
    links = tree.links
    links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    links.new(tex.outputs["Color"], bg.inputs["Color"])
    target = out.inputs["Surface"]
    if not (target.is_linked and target.links[0].from_node == bg):
        links.new(bg.outputs["Background"], target)
    return world


def _driver(fc_owner, path, index, ob, var_path):
    fc = fc_owner.driver_add(path, index) if index is not None else fc_owner.driver_add(path)
    drv = fc.driver
    drv.type = 'AVERAGE'
    for v in list(drv.variables):
        drv.variables.remove(v)
    var = drv.variables.new()
    var.name = "dome"
    var.type = 'SINGLE_PROP'
    var.targets[0].id_type = 'OBJECT'
    var.targets[0].id = ob
    var.targets[0].data_path = var_path
    return fc


def link_locator(world, ob):
    """Drivers: Mapping Rotation = the locator's rotation, Background Strength = its Intensity attribute."""
    tree = world.node_tree
    mapping, bg = tree.nodes[N_MAP], tree.nodes[N_BG]
    for i in range(3):
        _driver(mapping.inputs["Rotation"], "default_value", i, ob, f"rotation_euler[{i}]")
    _driver(bg.inputs["Strength"], "default_value", None, ob, f'["{INTENSITY}"]')


def ensure_locator(context):
    """The scene's dome locator (a new ``domeLight<N>`` Empty at the origin when there is none)."""
    scene = context.scene
    ob = find_dome(scene)
    if ob is not None:
        return ob, False
    n = naming.next_number(BASE, {o.name for o in bpy.data.objects})
    ob = bpy.data.objects.new(f"{BASE}{n}", None)
    ob.empty_display_type = 'SPHERE'
    ob.empty_display_size = 100.0 * units.maya_unit()      # a 100-unit sphere around the scene
    ob[MARK] = True
    ob[INTENSITY] = 1.0
    ob.id_properties_ui(INTENSITY).update(min=0.0, soft_max=10.0, description="Dome light intensity (World strength)")
    context.collection.objects.link(ob)
    return ob, True


def create(context, image=None):
    """Build or reuse the dome (``image`` on its Environment Texture when given); select its locator. Returns the
    locator."""
    world = ensure_world(context.scene)
    ob, _new = ensure_locator(context)
    link_locator(world, ob)
    if image is not None:
        world.node_tree.nodes[N_TEX].image = image
    for o in context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    world.update_tag()
    return ob


class ALLSET_OT_dome_light(bpy.types.Operator):
    """Dome light: an image (HDRI) around the scene lights it, Blender's World environment. Rotate the domeLight
    locator to turn the image; its Intensity attribute is the brightness"""
    bl_idname = "allset.dome_light"
    bl_label = "Dome Light"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    filter_image: bpy.props.BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.mode == 'OBJECT'

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        path = bpy.path.abspath(self.filepath) if self.filepath else ""
        if path and not os.path.isfile(path):
            self.report({'WARNING'}, f"Dome Light: no image file '{self.filepath}'")
            path = ""
        image = None
        if path:
            try:
                image = bpy.data.images.load(path, check_existing=True)
            except RuntimeError as ex:       # a file Blender can't read as an image
                self.report({'WARNING'}, f"Dome Light: {ex}")
                return {'CANCELLED'}
        ob = create(context, image)
        from .. import results
        results.result(self, f"Result: {ob.name}")
        return {'FINISHED'}


classes = (ALLSET_OT_dome_light,)
