# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Attribute Editor map button: connect a texture to a material attribute.

Maya: the checker button next to an attribute -> Create Render Node -> File / Ramp / Noise / Checker; a connected
attribute's button goes to the connected node, RMB > Break Connection unlinks it.
Blender: the texture node is added to the material's node tree, left of the Principled BSDF, and linked to
the input; a Normal input goes through a Bump node (Maya's bump2d). Break Connection removes the link and keeps the
nodes, like Maya. Lambert-family Color = the "Maya Diffuse" node's B input (``material.maya_input``), so a
colour texture is multiplied by diffuse like Maya's.
"""

import bpy
from bpy.props import EnumProperty, StringProperty

from .. import results
from . import material as _material

# kind -> (Maya node name, Blender node label)
MAPS = {
    'FILE': ("File", "Image Texture"),
    'RAMP': ("Ramp", "Color Ramp"),
    'NOISE': ("Noise", "Noise Texture"),
    'CHECKER': ("Checker", "Checker Texture"),
}
MAP_ITEMS = [(k, v[0], f"Maya {v[0]} texture = Blender {v[1]}") for k, v in MAPS.items()]
# Maya ramp default: red / green / blue along V; checker on UVs [K/U: Maya's repeat count unknown].
RAMP_COLOURS = ((0.0, (1.0, 0.0, 0.0, 1.0)), (0.5, (0.0, 1.0, 0.0, 1.0)), (1.0, (0.0, 0.0, 1.0, 1.0)))
CHECKER_SCALE = 4.0     # 4 x 4 squares over 0-1 UV (Maya checker repeat count unknown)


def principled(mat):
    if mat is None or mat.node_tree is None:
        return None
    return next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)


def _uv(nodes, links, x, y):
    coord = nodes.new("ShaderNodeTexCoord")
    coord.location = (x, y)
    return coord.outputs["UV"]


def build(mat, socket_name, kind):
    """Add the ``kind`` texture network and link it to the Principled input ``socket_name``; the texture node."""
    inp = _material.maya_input(mat, socket_name)
    owner = inp.node
    tree = mat.node_tree
    nodes, links = tree.nodes, tree.links
    index = list(owner.inputs).index(inp) if owner.type == 'BSDF_PRINCIPLED' else 0
    x, y = owner.location.x - 360, owner.location.y - 40 * index
    if kind == 'FILE':
        tex = nodes.new("ShaderNodeTexImage")
        out = tex.outputs["Color"]
    elif kind == 'RAMP':
        sep = nodes.new("ShaderNodeSeparateXYZ")
        sep.location = (x - 380, y)
        links.new(_uv(nodes, links, x - 560, y), sep.inputs[0])
        tex = nodes.new("ShaderNodeValToRGB")
        elements = tex.color_ramp.elements
        while len(elements) > len(RAMP_COLOURS):
            elements.remove(elements[-1])
        while len(elements) < len(RAMP_COLOURS):
            elements.new(1.0)
        for el, (pos, colour) in zip(elements, RAMP_COLOURS):
            el.position, el.color = pos, colour
        links.new(sep.outputs["Y"], tex.inputs["Fac"])
        out = tex.outputs["Color"]
    elif kind == 'NOISE':
        tex = nodes.new("ShaderNodeTexNoise")
        out = tex.outputs["Color"]
    else:
        tex = nodes.new("ShaderNodeTexChecker")
        tex.inputs["Scale"].default_value = CHECKER_SCALE
        links.new(_uv(nodes, links, x - 200, y), tex.inputs["Vector"])
        out = tex.outputs["Color"]
    tex.location = (x, y)
    tex.label = MAPS[kind][0]
    if inp.type == 'VECTOR' and socket_name.endswith("Normal"):
        bump = nodes.new("ShaderNodeBump")
        bump.location = (x + 180, y)
        links.new(out, bump.inputs["Height"])
        out = bump.outputs["Normal"]
    links.new(out, inp)
    nodes.active = tex
    return tex


def break_connection(mat, socket_name):
    inp = _material.maya_input(mat, socket_name)
    if inp is None:
        return False
    for link in list(inp.links):
        mat.node_tree.links.remove(link)
    return True


def _maya_attr(socket):
    from ..ui import ae_layout
    return ae_layout.MAYA_ATTR.get(socket, socket)


_MAT = StringProperty(name="Material", options={'SKIP_SAVE', 'HIDDEN'})
_SOCKET = StringProperty(name="Input", options={'SKIP_SAVE', 'HIDDEN'})


class ALLSET_OT_ae_map(bpy.types.Operator):
    """Create Render Node: connect a texture to this attribute (Maya map button)"""
    bl_idname = "allset.ae_map"
    bl_label = "Create Render Node"

    material: _MAT
    socket: _SOCKET

    @classmethod
    def description(cls, context, props):
        attr = _maya_attr(props.socket)
        return f"{attr}: connect a texture (Maya map button = a texture node linked to {props.socket})"

    def invoke(self, context, event):
        mat = bpy.data.materials.get(self.material)
        inp = _material.maya_input(mat, self.socket)
        if inp is None:
            return {'CANCELLED'}
        material, socket = self.material, self.socket

        def draw(menu, _context):
            layout = menu.layout
            if inp.is_linked:
                layout.label(text=f"Connected: {inp.links[0].from_node.name}")
                op = layout.operator("allset.ae_map_break", text="Break Connection", icon='UNLINKED')
                op.material, op.socket = material, socket
                layout.separator()
            for kind, (label, blender) in MAPS.items():
                op = layout.operator("allset.ae_map_connect", text=f"{label}  ({blender})", icon='TEXTURE')
                op.material, op.socket, op.kind = material, socket, kind

        context.window_manager.popup_menu(draw, title=f"Create Render Node: {_maya_attr(socket)}")
        return {'FINISHED'}


class ALLSET_OT_ae_map_connect(bpy.types.Operator):
    """Create this texture and connect it to the attribute (Maya Create Render Node)"""
    bl_idname = "allset.ae_map_connect"
    bl_label = "Connect Texture"
    bl_options = {'REGISTER', 'UNDO'}

    material: _MAT
    socket: _SOCKET
    kind: EnumProperty(items=MAP_ITEMS, name="Texture")

    def execute(self, context):
        mat = bpy.data.materials.get(self.material)
        if _material.maya_input(mat, self.socket) is None:
            self.report({'WARNING'}, "No such material attribute")
            return {'CANCELLED'}
        tex = build(mat, self.socket, self.kind)
        results.result(self, f"{tex.name} -> {mat.name}.{_maya_attr(self.socket)}")
        return {'FINISHED'}


class ALLSET_OT_ae_map_break(bpy.types.Operator):
    """Disconnect the texture from this attribute; the nodes stay (Maya Break Connection)"""
    bl_idname = "allset.ae_map_break"
    bl_label = "Break Connection"
    bl_options = {'REGISTER', 'UNDO'}

    material: _MAT
    socket: _SOCKET

    def execute(self, context):
        if not break_connection(bpy.data.materials.get(self.material), self.socket):
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (ALLSET_OT_ae_map, ALLSET_OT_ae_map_connect, ALLSET_OT_ae_map_break)
