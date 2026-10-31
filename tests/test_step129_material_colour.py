"""Maya's shaded mode (5) shows the material colour. Blender's Solid shading with colour type
MATERIAL draws ``Material.diffuse_color`` (the viewport display colour), which the Principled Base Color the
kit's materials / Attribute Editor edit doesn't change — so a kit material's display colour follows its Maya
colour (and transparency)."""

from importlib import import_module

import bpy

import kit

material = import_module(kit.MODULE + ".operators.material")
create = import_module(kit.MODULE + ".operators.create")
display = import_module(kit.MODULE + ".operators.display")


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)


def _principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def _close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))


def test_shaded_mode_draws_material_colour():
    class Shading:
        type = color_type = None
    sh = Shading()
    display.apply_display_mode(sh, "SHADED")
    assert sh.type == 'SOLID' and sh.color_type == 'MATERIAL', (sh.type, sh.color_type)


def test_new_kit_material_shows_its_colour():
    _clear()
    mat = material.new_material('BLINN')
    base = tuple(_principled(mat).inputs["Base Color"].default_value)
    assert _close(mat.diffuse_color, base), (tuple(mat.diffuse_color), base)
    lam = material.default_material()
    assert _close(lam.diffuse_color[:3], (0.5, 0.5, 0.5)), tuple(lam.diffuse_color)


def test_colour_edit_reaches_viewport_colour():
    _clear()
    ob = create.create(bpy.context, 'CUBE')
    mat = material.new_material('LAMBERT')
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    bsdf = _principled(mat)
    # = AE Color (the Maya Diffuse node's B input; Blender's panel shows Base Color as linked)
    material.color_socket(mat).default_value = (0.9, 0.1, 0.05, 1.0)
    bsdf.inputs["Alpha"].default_value = 0.4                           # = AE Transparency
    bpy.context.view_layer.update()
    got = tuple(mat.diffuse_color)
    assert _close(got, (0.9, 0.1, 0.05, 0.4)), got


def test_surface_shader_shows_out_colour():
    _clear()
    mat = material.new_material('SURFACE')
    _principled(mat).inputs["Emission Color"].default_value = (0.2, 0.7, 0.3, 1.0)
    bpy.context.view_layer.update()
    assert _close(mat.diffuse_color[:3], (0.2, 0.7, 0.3)), tuple(mat.diffuse_color)


def test_blender_material_untouched():
    _clear()
    mat = bpy.data.materials.new("plain")
    import_module(kit.MODULE + ".compat").ensure_material_nodes(mat)
    mat.diffuse_color = (0.1, 0.2, 0.3, 1.0)
    _principled(mat).inputs["Base Color"].default_value = (0.9, 0.9, 0.9, 1.0)
    bpy.context.view_layer.update()
    assert _close(mat.diffuse_color, (0.1, 0.2, 0.3, 1.0)), tuple(mat.diffuse_color)
