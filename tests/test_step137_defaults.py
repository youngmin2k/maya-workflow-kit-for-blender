"""Step 137, issue #71: Maya material / light / Render Settings defaults (lane DEFAULTS).

Maya values: blinn1 color 0.5, incandescence black,
specularRollOff 0.7, eccentricity 0.3, specularColor 0.5; phong1 cosinePower 20; lights intensity 1, Decay Rate
No Decay; defaultResolution 960 x 540. Light power rule and its renders: operators/lights.py."""

import math
from importlib import import_module

import bpy

import kit

material = import_module(kit.MODULE + ".operators.material")
create = import_module(kit.MODULE + ".operators.create")
lights = import_module(kit.MODULE + ".operators.lights")
ae_layout = import_module(kit.MODULE + ".ui.ae_layout")
attribute_editor = import_module(kit.MODULE + ".ui.attribute_editor")
app_template = import_module(kit.MODULE + ".app_template")
compat = import_module(kit.MODULE + ".compat")

PI2 = math.pi ** 2


def _clear():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.lights, bpy.data.materials):
        for d in list(coll):
            coll.remove(d)


def _cm():
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0
    return 0.01


def _bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def _close(a, b, eps=1e-4):
    if isinstance(a, (int, float)):
        return abs(a - b) < eps
    return all(abs(x - y) < eps for x, y in zip(a, b))


def _rows(name):
    return [row for _d, sec in ae_layout.walk(ae_layout.BY_KIND[name][0]) for row in sec.rows]


# --- materials -----------------------------------------------------------------------------------------------------

def test_blinn_maya_defaults():
    _clear()
    mat = material.new_material('BLINN')
    b = _bsdf(mat)
    assert _close(b.inputs["Base Color"].default_value, (0.5, 0.5, 0.5, 1.0)), "Maya color 0.5 (was 0.8)"
    assert _close(b.inputs["Emission Color"].default_value, (0, 0, 0, 1)), "Maya incandescence black (was white)"
    assert _close(b.inputs["Specular IOR Level"].default_value, 0.7), "Specular Roll Off 0.7 (was 0.5)"
    assert _close(b.inputs["Specular Tint"].default_value, (0.5, 0.5, 0.5, 1.0)), "specularColor 0.5"
    # the AE getters show Maya's numbers
    assert _close(mat.allset_eccentricity, 0.3), mat.allset_eccentricity
    assert _close(b.inputs["Roughness"].default_value, math.sqrt(0.3)), "GGX alpha = eccentricity"
    mat.allset_eccentricity = 0.6
    assert _close(b.inputs["Roughness"].default_value, math.sqrt(0.6)) and _close(mat.allset_eccentricity, 0.6)
    rows = _rows("blinn")
    assert ("maya", "allset_eccentricity", "Eccentricity", "Roughness") in rows
    assert ("socket", "Specular IOR Level", "Specular Roll Off") in rows
    assert ("socket", "Emission Color", "Incandescence") in rows


def test_phong_maya_defaults():
    _clear()
    mat = material.new_material('PHONG')
    b = _bsdf(mat)
    assert _close(b.inputs["Base Color"].default_value, (0.5, 0.5, 0.5, 1.0))
    assert _close(b.inputs["Emission Color"].default_value, (0, 0, 0, 1))
    assert _close(b.inputs["Specular Tint"].default_value, (0.5, 0.5, 0.5, 1.0))
    assert _close(mat.allset_cosine_power, 20.0, 1e-3), mat.allset_cosine_power
    mat.allset_cosine_power = 50.0
    assert _close(mat.allset_cosine_power, 50.0, 1e-2), mat.allset_cosine_power
    assert _close(b.inputs["Roughness"].default_value, (2 / 52) ** 0.25)
    assert ("maya", "allset_cosine_power", "Cosine Power", "Roughness") in _rows("phong")
    # Blinn eccentricity 0.3 and Phong cosine power 20 give about the same Maya highlight: both near 0.55 here
    assert abs(material.eccentricity_roughness(0.3) - material.cosine_power_roughness(20.0)) < 0.01


def test_other_lambert_family_defaults():
    _clear()
    for kind in ('LAMBERT', 'PHONG_E', 'ANISOTROPIC', 'RAMP', 'LAYERED'):
        b = _bsdf(material.new_material(kind))
        assert _close(b.inputs["Emission Color"].default_value, (0, 0, 0, 1)), (kind, "incandescence black")
        if kind != 'RAMP':     # the ramp's colour comes from its Color Ramp
            want = (0.5, 0.5, 0.5, 1.0) if kind != 'LAYERED' else (0.8, 0.8, 0.8, 1.0)
            assert _close(b.inputs["Base Color"].default_value, want), kind
    b = _bsdf(material.new_material('PHONG_E'))
    assert _close(b.inputs["Roughness"].default_value, 0.5) and _close(b.inputs["Specular IOR Level"].default_value, 0.5)
    b = _bsdf(material.new_material('ANISOTROPIC'))
    assert _close(b.inputs["Roughness"].default_value, 0.7)
    s = _bsdf(material.new_material('STANDARD_SURFACE'))
    assert _close(s.inputs["Roughness"].default_value, 0.4), "standardSurface specularRoughness 0.4"
    assert _close(s.inputs["Base Color"].default_value, (0.8, 0.8, 0.8, 1.0))


def test_ae_draws_maya_numbers():
    """The AE row draws the Material property (Maya's number), not the Roughness socket."""
    _clear()
    mat = material.new_material('BLINN')
    calls = []

    class Rec:
        def row(self, **_kw):
            return self

        def prop(self, owner, attr, text=""):
            calls.append((owner, attr, text))

        def operator(self, *_a, **_kw):
            class P:
                pass
            return P()

        def label(self, text=""):
            calls.append((None, None, text))

    attribute_editor.draw_row(Rec(), bpy.context, None, mat, ("maya", "allset_eccentricity", "Eccentricity",
                                                                 "Roughness"))
    assert calls == [(mat, "allset_eccentricity", "Eccentricity")], calls


# --- lights --------------------------------------------------------------------------------------------------------

def _falloff(light):
    tree = light.node_tree
    node = tree.nodes.get(lights.FALLOFF_NODE) if tree is not None else None
    if node is None:
        return None, None
    em = next(n for n in tree.nodes if n.type == 'EMISSION')
    link = em.inputs["Strength"].links[0] if em.inputs["Strength"].is_linked else None
    return (link.from_socket.name if link else None), node.inputs["Strength"].default_value


def test_new_point_spot_lights_no_decay():
    _clear()
    k = _cm()
    for kind in ('POINT_LIGHT', 'SPOT_LIGHT'):
        ob = create.create(bpy.context, kind)
        light = ob.data
        assert light.allset_decay == 'NO_DECAY' and _close(light.allset_intensity, 1.0), (kind, light.allset_decay)
        assert _close(light.energy, 4 * PI2 * 100 * k * k, 1e-6), light.energy
        out, strength = _falloff(light)
        assert out == "Constant" and _close(strength, 1 / (10 * k) ** 2, 1e-3), (out, strength)
    spot = bpy.data.objects["spotLight1"].data
    assert _close(math.degrees(spot.spot_size), 40.0) and spot.spot_blend == 0.0, "Maya cone 40, penumbra 0"


def test_decay_rate_changes_keep_intensity():
    _clear()
    k = _cm()
    light = create.create(bpy.context, 'POINT_LIGHT').data
    light.allset_intensity = 2.0
    light.allset_decay = 'LINEAR'
    assert _close(light.allset_intensity, 2.0) and _close(light.energy, 2 * 4 * PI2 * 10 * k * k, 1e-6)
    out, strength = _falloff(light)
    assert out == "Linear" and _close(strength, 1 / (10 * k)), (out, strength)
    light.allset_decay = 'QUADRATIC'
    assert _falloff(light) == (None, None), "Blender's own law: no falloff node"
    assert _close(light.energy, 2 * 4 * PI2 * k * k, 1e-8) and _close(light.allset_intensity, 2.0)
    if not compat.LIGHT_ALWAYS_NODES:
        assert not light.use_nodes, "nodes the kit turned on are turned off again"
    assert lights.exact(light)
    light.allset_decay = 'CUBIC'
    assert not lights.exact(light) and "cubic" in lights.decay_notice(light)
    light.allset_decay = 'NO_DECAY'
    assert _falloff(light)[0] == "Constant" and _close(light.allset_intensity, 2.0)


def test_area_and_directional_lights():
    _clear()
    k = _cm()
    area = create.create(bpy.context, 'AREA_LIGHT').data
    assert area.allset_decay == 'NO_DECAY' and _close(area.size, 2 * k), "Maya area light 2 x 2 units"
    assert _close(area.energy, PI2 * lights.AREA_FAR * k * k, 1e-8) and _falloff(area) == (None, None)
    area.allset_decay = 'LINEAR'
    assert not lights.exact(area) and _close(area.allset_intensity, 1.0)
    sun = create.create(bpy.context, 'DIRECTIONAL_LIGHT').data
    assert _close(sun.energy, math.pi) and _close(sun.allset_intensity, 1.0)
    # a light made in Blender reads with Blender's own law
    plain = bpy.data.lights.new("plain", 'POINT')
    plain.energy = 10.0
    assert plain.allset_decay == 'QUADRATIC' and _close(plain.allset_intensity, 10.0 / (4 * PI2 * k * k), 1e-3)


def test_ae_light_rows():
    for name in ("POINT", "SPOT", "AREA"):
        rows = _rows(name)
        assert ("prop", "data", "allset_intensity", "Intensity") in rows and ("draw", "light_decay") in rows, name
    assert "light_decay" in attribute_editor.DRAWERS


# --- Render Settings -----------------------------------------------------------------------------------------------

def test_template_resolution_960_540():
    with bpy.data.libraries.load(app_template.STARTUP) as (src, dst):
        dst.scenes = list(src.scenes)
    try:
        for sc in dst.scenes:
            r = sc.render
            assert (r.resolution_x, r.resolution_y, r.resolution_percentage) == (960, 540, 100), \
                (sc.name, r.resolution_x, r.resolution_y, r.resolution_percentage)
            assert (r.pixel_aspect_x, r.pixel_aspect_y) == (1.0, 1.0)
    finally:
        for sc in dst.scenes:
            bpy.data.scenes.remove(sc)
