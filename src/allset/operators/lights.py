# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya light Intensity and Decay Rate on Blender lights (issue #71).

Maya: a new point / spot / area light
has intensity 1 and Decay Rate No Decay; a lambert surface facing a point / spot light at any distance renders
color x diffuse x intensity (Linear divides by the distance in Maya units, Quadratic by its square, Cubic by its
cube). A directional light renders color x diffuse x intensity. An area light (2 x 2 units) falls off by itself,
and the Decay Rate divides by distance^n on top.

Blender (Diffuse BSDF colour a, 4.5): a point / spot light of power P watts renders
a x P / (4 pi^2 r^2) (r in metres) in Cycles and EEVEE; a sun of strength S renders a x S / pi; an area light renders
a x P / (pi^2 r^2) far away. A Light Falloff node on the light's node tree (Cycles only — EEVEE and the viewport
ignore light nodes) changes the distance law: its Constant output removes the 1/r^2, Linear leaves 1/r,
Quadratic is Blender's own law; its Strength multiplies the power.

The kit's rule (k = maya_unit(), n = Maya Decay Rate 0..3, matched at REF_UNITS = 10 Maya units):
  point / spot  power = 4 pi^2 k^2 I 10^(2-n); Cycles: n = 0 -> Constant x (10k)^-2, n = 1 -> Linear x (10k)^-1
                (exact at every distance), n = 2 Blender's own law (exact), n = 3 Blender's law matched at 10 units.
  area          power = pi^2 x 9.87 x k^2 I / 10^n (No Decay exact in shape; Linear / Quadratic / Cubic matched at
                10 units only — Blender's area light can't fall off faster than 1/r^2).
  sun           strength = pi x I.
EEVEE / the viewport always use 1/r^2: they match Maya at 10 units. Intensity is not stored: it is read back from the
power, so a Blender power edit shows in the Attribute Editor. Lights without a kit Decay Rate (made in Blender) read
as Quadratic (point / spot) or No Decay (area, sun), the law Blender gives them.
"""

import math

import bpy
from bpy.props import EnumProperty, FloatProperty

from .. import compat
from . import units

DECAY_ITEMS = (('NO_DECAY', "No Decay", "Maya: the light doesn't get darker with distance", 0),
               ('LINEAR', "Linear", "Maya: brightness / distance", 1),
               ('QUADRATIC', "Quadratic", "Maya: brightness / distance squared (Blender's own law)", 2),
               ('CUBIC', "Cubic", "Maya: brightness / distance cubed", 3))
DECAY_PROP = "allset_decay_rate"       # ID property on the Light data: Maya Decay Rate 0..3
NODES_PROP = "allset_decay_nodes"      # the kit turned the light's nodes on (turned off again when no longer needed)
FALLOFF_NODE = "Maya Decay Rate"
REF_UNITS = 10.0
AREA_FAR = 9.87                        # Maya area light, No Decay: brightness x distance^2 / intensity at 10 units
DECAY_LIGHTS = {'POINT', 'SPOT', 'AREA'}
FALLOFF_OUTPUT = {0: "Constant", 1: "Linear"}
MAYA_SPOT_CONE, MAYA_SPOT_PENUMBRA = 40.0, 0.0      # degrees (coneAngle 40, penumbraAngle 0)
MAYA_AREA_SIZE = 2.0                   # the area light is a 2 x 2 unit square


def _k():
    scene = getattr(bpy.context, "scene", None)
    return units.maya_unit(scene) if scene is not None else 1.0


def decay(light):
    """Maya Decay Rate 0..3 of a Blender light."""
    if light.type not in DECAY_LIGHTS:
        return 0
    v = light.get(DECAY_PROP)
    if v is None:
        return 2 if light.type in {'POINT', 'SPOT'} else 0
    return max(0, min(3, int(v)))


def power_factor(light_type, n, k):
    """Blender power (W) per Maya intensity 1."""
    if light_type == 'SUN':
        return math.pi
    if light_type == 'AREA':
        return math.pi ** 2 * AREA_FAR * k * k / REF_UNITS ** n
    return 4.0 * math.pi ** 2 * k * k * REF_UNITS ** (2 - n)


def falloff_strength(n, k):
    """Light Falloff Strength for point / spot Decay Rate n (Cycles), None when Blender's own law is used."""
    if n not in FALLOFF_OUTPUT:
        return None
    return (REF_UNITS * k) ** (n - 2)


def exact(light, n=None):
    """True when the Cycles render follows Maya's Decay Rate at every distance."""
    n = decay(light) if n is None else n
    if light.type in {'POINT', 'SPOT'}:
        return n <= 2
    return light.type != 'AREA' or n == 0


def decay_notice(light):
    """Attribute Editor tooltip of the Decay Rate row: what Blender renders for this light."""
    n = decay(light)
    if light.type == 'AREA':
        if n == 0:
            return "Blender's area light falls off like Maya's (No Decay) in Cycles, EEVEE and the viewport."
        return ("Blender's area light can't fall off faster than distance squared: its power matches Maya at "
                "10 units.")
    if n == 3:
        return "Blender has no cubic falloff: distance squared, its power matching Maya at 10 units."
    if n == 2:
        return "Distance squared is Blender's own falloff: Cycles, EEVEE and the viewport render it."
    return ("Cycles renders this Decay Rate (Light Falloff node); EEVEE and the viewport always darken with the "
            "square of the distance, the power matching Maya at 10 units.")


def intensity(light, k=None):
    k = _k() if k is None else k
    return light.energy / power_factor(light.type, decay(light), k)


def _falloff_nodes(light, n, k):
    """Cycles' Light Falloff node for No Decay / Linear on point and spot lights; removed when not needed."""
    strength = falloff_strength(n, k) if light.type in {'POINT', 'SPOT'} else None
    tree = light.node_tree
    node = tree.nodes.get(FALLOFF_NODE) if tree is not None else None
    if strength is None:
        if node is not None:
            tree.nodes.remove(node)
        if light.get(NODES_PROP):
            compat.release_light_nodes(light)
            del light[NODES_PROP]
        return
    if compat.ensure_light_nodes(light):
        light[NODES_PROP] = True
    tree = light.node_tree
    if tree is None:
        return
    emission = next((nd for nd in tree.nodes if nd.type == 'EMISSION'), None)
    if emission is None:
        return
    if node is None:
        node = tree.nodes.new('ShaderNodeLightFalloff')
        node.name = node.label = FALLOFF_NODE
        node.location = (emission.location.x - 220, emission.location.y)
    node.inputs["Strength"].default_value = strength
    node.inputs["Smooth"].default_value = 0.0
    tree.links.new(node.outputs[FALLOFF_OUTPUT[n]], emission.inputs["Strength"])


def apply(light, maya_intensity=None, n=None, k=None):
    """Write Maya intensity / Decay Rate to the light (power + Cycles falloff node)."""
    k = _k() if k is None else k
    if maya_intensity is None:
        maya_intensity = intensity(light, k)
    if n is not None and light.type in DECAY_LIGHTS:
        light[DECAY_PROP] = int(n)
    n = decay(light)
    light.energy = max(0.0, maya_intensity) * power_factor(light.type, n, k)
    if light.type in DECAY_LIGHTS:
        _falloff_nodes(light, n, k)


def maya_defaults(light, k):
    """A new Maya light: intensity 1, No Decay; spot cone 40 / penumbra 0; area light 2 x 2 units."""
    if light.type == 'SPOT':
        light.spot_size = math.radians(MAYA_SPOT_CONE)
        light.spot_blend = MAYA_SPOT_PENUMBRA
    if light.type == 'AREA':
        light.shape = 'SQUARE'
        light.size = MAYA_AREA_SIZE * k
    apply(light, 1.0, 0, k)


# --- properties (Attribute Editor rows) ----------------------------------------------------------------------------

def _get_intensity(self):
    return intensity(self)


def _set_intensity(self, value):
    apply(self, value)


def _get_decay(self):
    return decay(self)


def _set_decay(self, value):
    if self.type in DECAY_LIGHTS:
        apply(self, intensity(self), value)


PROPS = ("allset_intensity", "allset_decay")


def _color(i):
    def get(light):
        return light.color[i]

    def set_(light, v):
        light.color[i] = max(0.0, float(v))
    return get, set_


PENUMBRA_PROP = "allset_penumbra"     # Maya penumbra angle (degrees) last written: tells a negative penumbra apart


def cone_penumbra(light):
    """(Maya coneAngle, penumbraAngle) in degrees from Blender's spot: a positive penumbra widens the
    cone outward (size = cone + 2p, blend = 2p / size), a negative one softens inward (size = cone, blend = 2|p| / cone)."""
    size = math.degrees(light.spot_size)
    soft = light.spot_blend * size / 2.0
    p = light.get(PENUMBRA_PROP)
    if isinstance(p, (int, float)) and p < 0 and abs(abs(p) - soft) < 1e-3:
        return size, float(p)
    return size - 2.0 * soft, soft


def set_cone_penumbra(light, cone=None, penumbra=None):
    c0, p0 = cone_penumbra(light)
    cone = c0 if cone is None else max(0.006, float(cone))
    p = p0 if penumbra is None else float(penumbra)
    size = cone + 2.0 * max(p, 0.0)
    size = min(180.0, max(1.0, size))
    light.spot_size = math.radians(size)
    light.spot_blend = min(1.0, 2.0 * abs(p) / size) if size > 0 else 0.0
    light[PENUMBRA_PROP] = p


def _cone():
    def get(light):
        return cone_penumbra(light)[0]

    def set_(light, v):
        set_cone_penumbra(light, cone=v)
    return get, set_


def _penumbra():
    def get(light):
        return cone_penumbra(light)[1]

    def set_(light, v):
        set_cone_penumbra(light, penumbra=v)
    return get, set_


def channel_attrs(light=None):
    """Maya light shape channels Blender keeps differently (keyable attributes): Color R / G / B
    (one colour vector), spot Cone Angle / Penumbra Angle (``spot_size`` + ``spot_blend``) — Channel Box SHAPES rows
    ``maya:colorR`` ... (ui/channel_box._virtual). ``paths`` = the Blender properties a key on the row keys."""
    from .deformers import Attr
    out = []
    for i, c in enumerate("RGB"):
        a = Attr(f"color{c}", f"Color {c}", "NONE", *_color(i))
        a.paths = (("color", i),)
        out.append(a)
    for key, label, fns in (("coneAngle", "Cone Angle", _cone()), ("penumbraAngle", "Penumbra Angle", _penumbra())):
        a = Attr(key, label, "NONE", *fns)
        a.paths = (("spot_size", -1), ("spot_blend", -1))
        a.spot_only = True
        out.append(a)
    return out


def channel_attr(name, light=None):
    for a in channel_attrs():
        if name == "maya:" + a.key:
            if getattr(a, "spot_only", False) and light is not None and light.type != 'SPOT':
                return None
            return a
    return None


# Blender properties a key on a Light row keys: Maya Intensity is read from the power
KEY_PATHS = {"allset_intensity": (("energy", -1),)}


def key_paths(light, name):
    """Blender properties a key on Light row ``name`` keys."""
    return list(KEY_PATHS.get(name, ()))


def register_props():
    bpy.types.Light.allset_intensity = FloatProperty(
        name="Intensity", min=0.0, soft_max=10.0, precision=3, get=_get_intensity, set=_set_intensity,
        description="Maya light intensity: 1 lights a surface like Maya's intensity 1 (at 10 units when the render "
                    "engine falls off with distance squared)")
    bpy.types.Light.allset_decay = EnumProperty(
        name="Decay Rate", items=DECAY_ITEMS, get=_get_decay, set=_set_decay,
        description="Maya Decay Rate: how the light gets darker with distance")


def unregister_props():
    for name in PROPS:
        if hasattr(bpy.types.Light, name):
            delattr(bpy.types.Light, name)
