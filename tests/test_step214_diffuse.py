"""#120: Maya diffuse 0.8 on the kit's lambert-family materials.

Maya renders color x diffuse x light; the kit's lambert1 rendered
1.25 x too bright. A "Maya Diffuse" Mix node now feeds the Principled Base
Color (operators/material.py); brightness: tests/test_step152_render.py."""

import os
import types
from importlib import import_module

import bpy

import kit

material = import_module(kit.MODULE + ".operators.material")
maps = import_module(kit.MODULE + ".operators.shading_maps")
ae_layout = import_module(kit.MODULE + ".ui.ae_layout")
ae = import_module(kit.MODULE + ".ui.attribute_editor")
menu_items = import_module(kit.MODULE + ".operators.menu_items")

LAMBERT_FAMILY = ('LAMBERT', 'BLINN', 'PHONG', 'PHONG_E', 'ANISOTROPIC', 'RAMP')


class Rec:
    """Records every layout call (as in tests/test_step67_render.py)."""

    def __init__(self, log=None):
        object.__setattr__(self, "log", [] if log is None else log)

    def __getattr__(self, name):
        def call(*args, **kw):
            self.log.append((name, args, kw))
            if name == "panel":
                return Rec(self.log), Rec(self.log)
            if name == "operator":
                props = types.SimpleNamespace()
                self.log[-1] = (name, args, kw, props)
                return props
            return Rec(self.log)
        return call

    def __setattr__(self, name, value):
        pass


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)


def _bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def _close(a, b, eps=1e-5):
    a = a if hasattr(a, "__len__") else (a,)
    b = b if hasattr(b, "__len__") else (b,)
    return all(abs(x - y) < eps for x, y in zip(a, b))


def _sock(node, ident):
    return next(s for s in node.inputs if s.identifier == ident)


def test_diffuse_node_on_lambert_family():
    _clear()
    for kind in LAMBERT_FAMILY:
        mat = material.new_material(kind)
        node = material.diffuse_node(mat)
        assert node is not None and node.type == 'MIX' and node.data_type == 'RGBA', kind
        assert node.blend_type == 'MIX' and not node.clamp_result, kind
        assert _close(_sock(node, "Factor_Float").default_value, 0.8), kind
        assert _close(_sock(node, "A_Color").default_value, (0, 0, 0, 1)), kind
        base = _bsdf(mat).inputs["Base Color"]
        assert base.is_linked and base.links[0].from_node == node, kind
        assert material.color_socket(mat) == _sock(node, "B_Color"), kind
        assert _close(mat.allset_diffuse, 0.8), kind
        if kind == 'RAMP':     # the facing-ratio ramp is the Maya colour, multiplied by diffuse like Maya's
            assert material.color_socket(mat).links[0].from_node.type == 'VALTORGB'
        else:
            assert _close(material.color_socket(mat).default_value, (0.5, 0.5, 0.5, 1.0)), kind
            assert _close(base.default_value, (0.5, 0.5, 0.5, 1.0)), "Base Color default keeps the Maya colour"
        # the Principled BSDF still feeds the output straight (PrincipledBSDFWrapper, specular / alpha untouched)
        out = next(n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL')
        assert out.inputs["Surface"].links[0].from_node == _bsdf(mat), kind
    lam1 = material.default_material()
    assert material.diffuse_node(lam1) is not None and _close(lam1.allset_diffuse, 0.8), "lambert1 diffuse 0.8"
    for kind in ('STANDARD_SURFACE', 'AI_STANDARD_SURFACE', 'SURFACE', 'LAYERED', 'USE_BACKGROUND'):
        mat = material.new_material(kind)
        assert material.diffuse_node(mat) is None, kind
        assert material.color_socket(mat) == _bsdf(mat).inputs["Base Color"], kind
        assert _close(mat.allset_diffuse, 1.0), (kind, "no node = diffuse 1")


def test_viewport_colour_is_maya_colour():
    _clear()
    mat = material.new_material('LAMBERT')
    assert _close(mat.diffuse_color, (0.5, 0.5, 0.5, 1.0)), "display = colour, not colour x diffuse"
    material.color_socket(mat).default_value = (0.9, 0.1, 0.05, 1.0)
    assert material.sync_display(mat) and _close(mat.diffuse_color, (0.9, 0.1, 0.05, 1.0))
    assert material._sync_base(mat) and _close(_bsdf(mat).inputs["Base Color"].default_value, (0.9, 0.1, 0.05, 1))


def test_allset_diffuse_get_set():
    _clear()
    mat = material.new_material('BLINN')
    mat.allset_diffuse = 0.3
    assert _close(_sock(material.diffuse_node(mat), "Factor_Float").default_value, 0.3)
    assert _close(mat.allset_diffuse, 0.3)
    mat.allset_diffuse = 1.0
    assert _close(mat.allset_diffuse, 1.0)
    # a Blender-made material reads 1.0; setting it adds the node, keeping its colour / links
    plain = bpy.data.materials.new("plain")
    plain.use_nodes = True
    _bsdf(plain).inputs["Base Color"].default_value = (0.2, 0.4, 0.6, 1.0)
    assert material.diffuse_node(plain) is None and _close(plain.allset_diffuse, 1.0)
    plain.allset_diffuse = 0.5
    node = material.diffuse_node(plain)
    assert node is not None and _close(plain.allset_diffuse, 0.5)
    assert _close(_sock(node, "B_Color").default_value, (0.2, 0.4, 0.6, 1.0))
    assert len([n for n in plain.node_tree.nodes if n.type == 'MIX']) == 1
    plain.allset_diffuse = 0.7          # no second node
    assert len([n for n in plain.node_tree.nodes if n.type == 'MIX']) == 1


def test_ae_rows_redirect_to_maya_color_and_diffuse():
    _clear()
    bpy.ops.mesh.primitive_uv_sphere_add()
    ob = bpy.context.active_object
    mat = material.new_material('LAMBERT')
    material.assign_object(ob, mat)
    assert ("maya", "allset_diffuse", "Diffuse", "Diffuse") in [r for _d, s in ae_layout.walk(ae_layout.LAMBERT)
                                                                for r in s.rows]
    rec = Rec()
    ae.draw_sections(rec, bpy.context, ob, mat, ae_layout.LAMBERT, "t")
    props = [(e[1][0], e[1][1], e[2].get("text")) for e in rec.log if e[0] == "prop"]
    b = material.color_socket(mat)
    assert any(o == b and a == "default_value" and t == "Color" for o, a, t in props), props
    assert any(o == mat and a == "allset_diffuse" and t == "Diffuse" for o, a, t in props), props
    sockets = [e[3].socket for e in rec.log if e[0] == "operator" and e[1][0] == "allset.ae_map"]
    assert "Base Color" in sockets and "Diffuse" in sockets, sockets
    # rampShader shows Diffuse in its Color section
    ramp = material.new_material('RAMP')
    rec = Rec()
    ae.draw_sections(rec, bpy.context, ob, ramp, ae_layout.RAMP_SHADER, "t")
    assert any(e[0] == "prop" and e[1][1] == "allset_diffuse" for e in rec.log)


def test_map_button_connects_into_maya_color():
    _clear()
    mat = material.new_material('LAMBERT')
    assert bpy.ops.allset.ae_map_connect(material=mat.name, socket="Base Color", kind='CHECKER') == {'FINISHED'}
    b = material.color_socket(mat)
    assert b.is_linked and b.links[0].from_node.type == 'TEX_CHECKER', "texture x diffuse like Maya"
    base = _bsdf(mat).inputs["Base Color"]
    assert base.links[0].from_node == material.diffuse_node(mat), "the diffuse node stays in front of Base Color"
    assert bpy.ops.allset.ae_map_break(material=mat.name, socket="Base Color") == {'FINISHED'}
    assert not b.is_linked and base.is_linked
    assert bpy.ops.allset.ae_map_connect(material=mat.name, socket="Diffuse", kind='NOISE') == {'FINISHED'}
    fac = _sock(material.diffuse_node(mat), "Factor_Float")
    assert fac.is_linked and fac.links[0].from_node.type == 'TEX_NOISE'
    # standardSurface keeps the Principled input
    ss = material.new_material('STANDARD_SURFACE')
    assert bpy.ops.allset.ae_map_connect(material=ss.name, socket="Base Color", kind='FILE') == {'FINISHED'}
    assert _bsdf(ss).inputs["Base Color"].links[0].from_node.type == 'TEX_IMAGE'


def test_checker_materials():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.allset.checker_shader()
    mat = bpy.context.active_object.active_material
    b = material.color_socket(mat)
    assert b.links[0].from_node.type == 'TEX_IMAGE' and _close(mat.allset_diffuse, 0.8)
    disp = menu_items._checker_material()
    assert material.color_socket(disp).links[0].from_node.type == 'TEX_IMAGE'
    assert _close(disp.allset_diffuse, 1.0), "the display checker shows at full brightness"


def test_diffuse_bypass_round_trip():
    _clear()
    mat = material.new_material('LAMBERT')
    material.color_socket(mat).default_value = (0.25, 0.5, 0.75, 1.0)
    tex = maps.build(mat, "Base Color", 'FILE')
    other = material.new_material('PHONG')            # a flat colour
    material.color_socket(other).default_value = (0.1, 0.2, 0.3, 1.0)
    base, obase = _bsdf(mat).inputs["Base Color"], _bsdf(other).inputs["Base Color"]
    before = tuple(obase.default_value)
    with material.diffuse_bypass() as n:
        assert n == 3, n          # lambert1 (made with the first new material), lambert2, phong1
        assert base.links[0].from_node == tex, "the texture straight into Base Color while writing"
        assert not obase.is_linked and _close(obase.default_value, (0.1, 0.2, 0.3, 1.0))
    assert base.links[0].from_node == material.diffuse_node(mat)
    assert obase.links[0].from_node == material.diffuse_node(other)
    assert _close(obase.default_value, before)
    assert material.color_socket(mat).links[0].from_node == tex


def test_kit_obj_export_writes_maya_colour():
    _clear()
    tmp = bpy.app.tempdir
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    mat = material.new_material('LAMBERT')
    material.assign_object(ob, mat)
    img = bpy.data.images.new("kit214", 4, 4)
    img.filepath_raw = os.path.join(tmp, "kit214.png")
    img.file_format = 'PNG'
    img.save()
    tex = maps.build(mat, "Base Color", 'FILE')
    tex.image = img
    path = os.path.join(tmp, "kit214.obj")
    assert bpy.ops.allset.file_dialog('EXEC_DEFAULT', mode='EXPORT_ALL', export_type='OBJ',
                                      filepath=path) == {'FINISHED'}
    mtl = open(path[:-4] + ".mtl", encoding="utf-8").read()
    assert "map_Kd" in mtl and "kit214.png" in mtl, mtl
    assert _bsdf(mat).inputs["Base Color"].links[0].from_node == material.diffuse_node(mat), "restored"


def test_undo_of_a_diffuse_edit():
    _clear()
    mat = material.new_material('LAMBERT')
    name = mat.name
    bpy.ops.ed.undo_push(message="before")
    mat.allset_diffuse = 0.25
    bpy.ops.ed.undo_push(message="diffuse")
    bpy.ops.ed.undo()
    assert _close(bpy.data.materials[name].allset_diffuse, 0.8), bpy.data.materials[name].allset_diffuse
