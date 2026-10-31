# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya material assignment.

Lighting/Shading > Material Attributes / Assign New / Favorite / Existing Material
 and the same items at the end of the RMB object
menu list. Maya assigns to the selection,
or to the object the RMB menu was opened on when nothing is selected.

- Object assignment = the whole shape gets the material (Maya: the shape joins the
  shading group): one slot, every face/spline index 0.
- Face assignment (mesh edit mode, face select mode, selected faces) = only those
  faces: the material's slot is found or added and their ``material_index`` set.
  A mesh without slots first gets an empty slot (Blender's default grey, Maya's
  lambert1) so the other faces keep it.
"""

import contextlib

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from .. import undo_steps
from .. import compat, depsgraph_filter

SUPPORTED = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}

# Maya shader kinds (shelf shader buttons) on Principled BSDF.
# Default values (lambert family).
# Every lambert-family shader: color 0.5 grey, incandescence black (Principled's default Emission Color is white at
# strength 0: the AE showed white), specularColor 0.5. diffuse 0.8 has no Principled input (its "Weight" socket is
# disabled), so a "Maya Diffuse" Mix node (``ensure_diffuse``) puts color x diffuse into Base Color.
_GREY = (0.5, 0.5, 0.5, 1.0)
_BLACK = (0.0, 0.0, 0.0, 1.0)
_COMMON = {"Base Color": _GREY, "Emission Color": _BLACK}
_SPECULAR = {**_COMMON, "Specular Tint": _GREY}
MAYA_ECCENTRICITY, MAYA_ROLL_OFF, MAYA_COSINE_POWER = 0.3, 0.7, 20.0


def eccentricity_roughness(e):
    """Principled Roughness for a Maya Blinn eccentricity: Blinn's highlight is the Trowbridge-Reitz distribution
    with c3 = eccentricity (Blinn 1977) = the GGX alpha, and Principled's alpha = roughness^2."""
    return max(0.0, min(1.0, e)) ** 0.5


def cosine_power_roughness(n):
    """Principled Roughness for a Maya Phong cosine power: exponent n <-> microfacet alpha = sqrt(2 / (n + 2)),
    alpha = roughness^2."""
    return (2.0 / (max(2.0, n) + 2.0)) ** 0.25


# kind -> (Maya node name, UI label, Principled inputs).
MATERIALS = {
    # standardSurface: baseColor 0.8 (= Principled's), specularRoughness 0.4, emissionColor white
    'STANDARD_SURFACE': ("standardSurface", "Standard Surface", {"Roughness": 0.4}),
    # Arnold's default material (Maya with mtoa); same Principled stand-in
    'AI_STANDARD_SURFACE': ("aiStandardSurface", "aiStandardSurface", {}),
    'LAMBERT': ("lambert", "Lambert", {**_COMMON, "Roughness": 1.0, "Specular IOR Level": 0.0}),
    # blinn: eccentricity 0.3, specularRollOff 0.7 (AE row = Specular IOR Level), specularColor 0.5 (#71)
    'BLINN': ("blinn", "Blinn", {**_SPECULAR, "Roughness": eccentricity_roughness(MAYA_ECCENTRICITY),
                                 "Specular IOR Level": MAYA_ROLL_OFF}),
    # phong: cosinePower 20, specularColor 0.5 (#71)
    'PHONG': ("phong", "Phong", {**_SPECULAR, "Roughness": cosine_power_roughness(MAYA_COSINE_POWER)}),
    'SURFACE': ("surfaceShader", "Surface Shader", {"Emission Strength": 1.0}),
    # the rest of Maya's Hypershade Create > Maya > Surface list that Blender can build (Principled stand-ins
    # plus a node or two)
    # phongE: roughness 0.5, highlightSize 0.5 (Specular IOR Level), whiteness 0.5 (Specular Tint)
    'PHONG_E': ("phongE", "Phong E", {**_SPECULAR, "Roughness": 0.5, "Specular IOR Level": 0.5}),
    # anisotropic: roughness 0.7, angle 0, specularColor 0.5 (spreadX 13 / spreadY 3: Blender's Anisotropic 0.5 stays)
    'ANISOTROPIC': ("anisotropic", "Anisotropic", {**_SPECULAR, "Roughness": 0.7, "Anisotropic": 0.5,
                                                   "Anisotropic Rotation": 0.0}),
    'RAMP': ("rampShader", "Ramp Shader", {"Roughness": 0.5, "Emission Color": _BLACK}),
    'LAYERED': ("layeredShader", "Layered Shader", {"Emission Color": _BLACK}),
    'USE_BACKGROUND': ("useBackground", "Use Background", {}),
}
# Kinds whose look comes from extra nodes around the Principled BSDF (``_build``)
BUILT = {'RAMP', 'LAYERED', 'USE_BACKGROUND'}
KIND_ITEMS = [(k, v[1], f"Maya {v[0]} (Principled BSDF)") for k, v in MATERIALS.items()]
# The Assign Favorite Material submenu (Maya's surface-shader favourites).
FAVORITES = ('LAMBERT', 'BLINN', 'PHONG', 'STANDARD_SURFACE')
# ID property naming the Maya node type of a kit-made material (AE tab label/sections).
TYPE_PROP = "allset_type"
# The default material, like Maya: every new shape joins initialShadingGroup, whose surface
# shader is lambert1 (a lambert); Delete Unused Nodes keeps it, a new Lambert is lambert2.
DEFAULT_PROP = "allset_default"
DEFAULT_NAME = "lambert1"
DEFAULT_GROUP = "initialShadingGroup"
DEFAULT_TYPES = {'MESH', 'SURFACE'}   # Maya polygon and NURBS surface shapes (curves have no shading group)


# --- data ------------------------------------------------------------------------------------

def new_material(kind):
    """A Maya-named (lambert1, blinn2, ...) Principled material of this kind."""
    from . import naming
    base, _label, values = MATERIALS[kind]
    if _maya_scene():
        default_material()   # Maya's scene always has lambert1, so a new Lambert is lambert2
    n = naming.next_number(base, {m.name for m in bpy.data.materials})
    mat = bpy.data.materials.new(f"{base}{n}")
    mat[TYPE_PROP] = base
    compat.ensure_material_nodes(mat)
    node = next(nd for nd in mat.node_tree.nodes if nd.type == 'BSDF_PRINCIPLED')
    for socket, value in values.items():
        node.inputs[socket].default_value = value
    if kind == 'SURFACE':
        node.inputs["Emission Color"].default_value = node.inputs["Base Color"].default_value
    if kind in BUILT:
        _build(mat, node, kind)
    if kind in DIFFUSE_KINDS:
        ensure_diffuse(mat)
    sync_display(mat)
    return mat


# --- Maya diffuse (#120) ---------------------------------------------------------------------------------
# Maya's lambert family renders color x diffuse x light (diffuse 0.8 for
# lambert / blinn / phong / phongE / anisotropic / rampShader, "rendered value = color x diffuse x intensity");
# a texture connected to color is multiplied by diffuse as well. Principled has no diffuse weight, so a Mix node
# (RGBA, MIX, factor = diffuse, A = black, B = the Maya colour) feeds Base Color: Base Color = diffuse x colour while
# specular / emission / alpha stay untouched and the Principled BSDF stays linked straight to the output (Blender's
# PrincipledBSDFWrapper needs that, $S\modules\bpy_extras\node_shader_utils.py:192-229). standardSurface has base 1 x
# baseColor 0.8 and gets no node. The Principled Base Color default keeps the Maya colour too (sync), so readers that
# skip links (Blender's own exporters) see the colour. Materials without the node read diffuse 1.0 (old files,
# Blender-made materials: no migration).

DIFFUSE_NODE = "Maya Diffuse"
DIFFUSE_SOCKET = "Diffuse"       # AE / map-button name of the diffuse factor (operators/shading_maps.py)
MAYA_DIFFUSE = 0.8
DIFFUSE_KINDS = {'LAMBERT', 'BLINN', 'PHONG', 'PHONG_E', 'ANISOTROPIC', 'RAMP'}


def _principled(mat):
    if mat is None or mat.node_tree is None:
        return None
    return next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)


def _ident(sockets, ident):
    return next((s for s in sockets if s.identifier == ident), None)


def diffuse_node(mat):
    """The material's "Maya Diffuse" Mix node, or None."""
    if mat is None or mat.node_tree is None:
        return None
    node = mat.node_tree.nodes.get(DIFFUSE_NODE)
    return node if node is not None and node.type == 'MIX' else None


def color_socket(mat):
    """The socket that is Maya's Color: the diffuse node's B colour when the material has one, else Principled Base
    Color (None without a Principled BSDF)."""
    node = diffuse_node(mat)
    if node is not None:
        return _ident(node.inputs, "B_Color")
    bsdf = _principled(mat)
    return bsdf.inputs.get("Base Color") if bsdf is not None else None


def maya_input(mat, name):
    """A material input by its AE / map-button name: "Base Color" = Maya Color (``color_socket``), DIFFUSE_SOCKET =
    the diffuse factor, else the Principled input of that name."""
    bsdf = _principled(mat)
    if bsdf is None:
        return None
    if name == "Base Color":
        return color_socket(mat)
    if name == DIFFUSE_SOCKET:
        node = diffuse_node(mat)
        return _ident(node.inputs, "Factor_Float") if node is not None else None
    return bsdf.inputs.get(name)


def ensure_diffuse(mat, value=MAYA_DIFFUSE):
    """Give a Principled material the Maya Diffuse node (whatever fed Base Color moves to its B input) and set the
    diffuse to ``value``; the node, or None without a Principled BSDF."""
    bsdf = _principled(mat)
    if bsdf is None:
        return None
    node = diffuse_node(mat)
    if node is None:
        tree = mat.node_tree
        base = bsdf.inputs["Base Color"]
        node = tree.nodes.new('ShaderNodeMix')
        node.name = node.label = DIFFUSE_NODE
        node.data_type, node.blend_type, node.clamp_result = 'RGBA', 'MIX', False
        node.location = (bsdf.location.x - 220, bsdf.location.y - 60)
        _ident(node.inputs, "A_Color").default_value = _BLACK
        b = _ident(node.inputs, "B_Color")
        b.default_value = base.default_value
        for link in list(base.links):
            tree.links.new(link.from_socket, b)
            tree.links.remove(link)
        tree.links.new(_ident(node.outputs, "Result_Color"), base)
    _ident(node.inputs, "Factor_Float").default_value = value
    return node


def _sync_base(mat):
    """Keep the Principled Base Color default equal to the Maya colour (B) of a diffuse node; True when written."""
    node, bsdf = diffuse_node(mat), _principled(mat)
    if node is None or bsdf is None:
        return False
    b, base = _ident(node.inputs, "B_Color"), bsdf.inputs["Base Color"]
    if all(abs(x - y) < 1e-6 for x, y in zip(base.default_value, b.default_value)):
        return False
    base.default_value = b.default_value
    return True


@contextlib.contextmanager
def diffuse_bypass():
    """Exchange-format writers (FBX / OBJ / glTF ...) read Base Color's default or an image node linked straight to
    it: for the duration, link whatever feeds each diffuse node's B directly to Base Color (default = the B colour),
    then put the diffuse node back (kit File > Export, operators/file_io.write; Blender's own File > Export menu is
    not wrapped)."""
    saved = []
    for mat in bpy.data.materials:
        node, bsdf = diffuse_node(mat), _principled(mat)
        if node is None or bsdf is None or mat.library is not None:
            continue
        base = bsdf.inputs["Base Color"]
        if not base.is_linked or base.links[0].from_node != node:
            continue
        tree, b = mat.node_tree, _ident(node.inputs, "B_Color")
        old = tuple(base.default_value)
        tree.links.remove(base.links[0])
        if b.is_linked:
            tree.links.new(b.links[0].from_socket, base)
        base.default_value = b.default_value
        saved.append((mat, old))
    try:
        yield len(saved)
    finally:
        for mat, old in saved:
            node, bsdf = diffuse_node(mat), _principled(mat)
            if node is None or bsdf is None:
                continue
            base = bsdf.inputs["Base Color"]
            for link in list(base.links):
                mat.node_tree.links.remove(link)
            mat.node_tree.links.new(_ident(node.outputs, "Result_Color"), base)
            base.default_value = old


# --- viewport colour (issue #14) ---------------------------------------------------------------
# Maya's shaded mode (5) draws the material colour. Blender's Solid shading with colour type MATERIAL (the kit's
# display mode SHADED, operators/display.py) draws ``Material.diffuse_color``, the viewport display colour, which
# a Principled Base Color edit (Attribute Editor Color, Blender's material panel) doesn't change. Kit materials
# keep it equal to their Maya colour (surfaceShader: out colour = Emission Color; rampShader: the ramp's mean
# colour) and transparency (Alpha); materials made in Blender keep Blender's own display colour.

def _maya_colour(mat):
    """(r, g, b, a) Maya's shaded mode would show for a kit material, or None (not a kit material / no colour)."""
    if mat is None or not mat.get(TYPE_PROP) or mat.node_tree is None:
        return None
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        return None
    sock = bsdf.inputs.get("Emission Color") if mat.get(TYPE_PROP) == "surfaceShader" else color_socket(mat)
    if sock is None:
        return None
    if sock.is_linked:
        src = sock.links[0].from_node
        if src.type != 'VALTORGB' or not len(src.color_ramp.elements):
            return None              # a texture: Maya's 5 shows no texture either, keep the display colour
        els = src.color_ramp.elements
        rgb = [sum(e.color[i] for e in els) / len(els) for i in range(3)]
    else:
        rgb = list(sock.default_value[:3])
    alpha = bsdf.inputs.get("Alpha")
    a = 1.0 if alpha is None or alpha.is_linked else float(alpha.default_value)
    return (*rgb, a)


def sync_display(mat):
    """Set a kit material's viewport display colour to its Maya colour; True when it changed."""
    col = _maya_colour(mat)
    if col is None or all(abs(x - y) < 1e-6 for x, y in zip(mat.diffuse_color, col)):
        return False
    mat.diffuse_color = col
    return True


def _build(mat, bsdf, kind):
    """Node set-ups of Maya shaders that aren't one Principled BSDF:
    rampShader = colour from a ramp over the facing ratio (Layer Weight Facing -> Color Ramp -> Base Color);
    layeredShader = two layers mixed (Mix Shader; Maya's top layer transparency = the mix factor);
    useBackground = the surface shows the background (Holdout)."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    out = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL')
    if kind == 'RAMP':
        facing = nodes.new('ShaderNodeLayerWeight')
        ramp = nodes.new('ShaderNodeValToRGB')
        facing.location = (bsdf.location.x - 780, bsdf.location.y)
        ramp.location = (bsdf.location.x - 520, bsdf.location.y)
        for el in ramp.color_ramp.elements:      # default ramp (like Maya): one 0.5 grey entry
            el.color = (0.5, 0.5, 0.5, 1.0)
        links.new(facing.outputs["Facing"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    elif kind == 'LAYERED':
        second = nodes.new('ShaderNodeBsdfPrincipled')
        mix = nodes.new('ShaderNodeMixShader')
        second.location = (bsdf.location.x, bsdf.location.y - 700)
        mix.location = (out.location.x - 200, out.location.y)
        out.location.x += 100
        mix.inputs["Fac"].default_value = 0.0      # top layer (input 1) fully opaque
        links.new(bsdf.outputs["BSDF"], mix.inputs[1])
        links.new(second.outputs["BSDF"], mix.inputs[2])
        links.new(mix.outputs["Shader"], out.inputs["Surface"])
    elif kind == 'USE_BACKGROUND':
        hold = nodes.new('ShaderNodeHoldout')
        hold.location = (bsdf.location.x, bsdf.location.y + 200)
        links.new(hold.outputs["Holdout"], out.inputs["Surface"])


def default_material(create=True):
    """The scene's lambert1 (marked by DEFAULT_PROP, so a rename keeps it); made on first use with a fake user so
    File > Optimize Scene Size / purges keep it like Maya's Delete Unused Nodes."""
    mat = next((m for m in bpy.data.materials if m.get(DEFAULT_PROP)), None)
    if mat is not None or not create:
        return mat
    old = bpy.data.materials.get(DEFAULT_NAME)
    if old is not None and old.get(TYPE_PROP) == "lambert" and old.library is None:
        # a kit "lambert1" from an older version (Assign New Material > Lambert): it becomes the default
        old[DEFAULT_PROP] = True
        old.use_fake_user = True
        return old
    mat = bpy.data.materials.new(DEFAULT_NAME)   # another material owns the name: Blender's suffix, names untouched
    mat[TYPE_PROP] = "lambert"
    mat[DEFAULT_PROP] = True
    mat.use_fake_user = True
    compat.ensure_material_nodes(mat)
    node = next(nd for nd in mat.node_tree.nodes if nd.type == 'BSDF_PRINCIPLED')
    for socket, value in MATERIALS['LAMBERT'][2].items():
        node.inputs[socket].default_value = value
    ensure_diffuse(mat)                      # Maya lambert1 diffuse 0.8
    sync_display(mat)
    return mat


def is_default(mat):
    return mat is not None and bool(mat.get(DEFAULT_PROP))


def shading_group_name(mat):
    """Maya's shading group of a material: initialShadingGroup for lambert1, else <material>SG."""
    return DEFAULT_GROUP if is_default(mat) else f"{mat.name}SG"


def give_default(ob):
    """A new shape without a material joins lambert1 (Maya: initialShadingGroup); True when assigned."""
    if ob is None or ob.type not in DEFAULT_TYPES or ob.data is None or ob.library is not None:
        return False
    if any(m is not None for m in ob.data.materials) or any(s.material is not None for s in ob.material_slots):
        return False
    mat = default_material()
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    return True


def _maya_scene(context=None):
    from .. import preferences
    try:
        return preferences.get(context or bpy.context).maya_naming
    except KeyError:
        return True


# New objects (any path: kit create, Blender's Add menu, duplicate, separate, import) are found by comparing the
# scene's objects with the last known set; file load, undo and redo only re-baseline (their objects aren't new).
_known = {}
_busy = [False]


def _baseline(*_args):
    _known.clear()
    for scene in bpy.data.scenes:
        _known[scene.as_pointer()] = {o.as_pointer() for o in scene.objects}


@bpy.app.handlers.persistent
def _on_load(*_args):
    _baseline()
    if not bpy.data.filepath and _maya_scene():   # File > New: Maya's new scene already has lambert1
        default_material()


@bpy.app.handlers.persistent
def _on_undo(*_args):
    _baseline()


@bpy.app.handlers.persistent
def _on_depsgraph(scene, depsgraph):
    if _busy[0]:
        return
    if depsgraph.id_type_updated('MATERIAL') or depsgraph.id_type_updated('NODETREE'):
        _busy[0] = True
        try:
            for mat in bpy.data.materials:
                if mat.library is None and mat.get(TYPE_PROP):
                    sync_display(mat)
                if mat.library is None:
                    _sync_base(mat)
        finally:
            _busy[0] = False
    if not depsgraph.id_type_updated('OBJECT'):
        return
    key = scene.as_pointer()
    known = _known.get(key)
    # #191: objects are only added with a Scene / Collection update, and an addition raises the count —
    # a move or a selection change skips the walk over every object (0.45 ms per update at 620 objects)
    if known is not None and (not depsgraph_filter.structure_changed(depsgraph)
                              or len(scene.objects) == len(known)):
        return
    now = {o.as_pointer() for o in scene.objects}
    _known[key] = now
    if known is None or not (now - known) or not _maya_scene():
        return
    _busy[0] = True
    try:
        for ob in scene.objects:
            if ob.as_pointer() not in known:
                give_default(ob)
    finally:
        _busy[0] = False


HANDLERS = ((bpy.app.handlers.load_post, _on_load), (bpy.app.handlers.undo_post, _on_undo),
            (bpy.app.handlers.redo_post, _on_undo), (bpy.app.handlers.depsgraph_update_post, _on_depsgraph))


# --- Maya attributes stored as Principled inputs (#71) -------------------------------------------------------------
# The Attribute Editor shows Maya's numbers: Blinn Eccentricity and Phong Cosine Power are read from / written to the
# Principled Roughness through the conversions above (nothing stored, so a Roughness edit elsewhere shows here).

def _roughness_socket(mat):
    if mat is None or not compat.material_uses_nodes(mat):
        return None
    node = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    return node.inputs.get("Roughness") if node is not None else None


def _get_eccentricity(self):
    sock = _roughness_socket(self)
    return MAYA_ECCENTRICITY if sock is None else float(sock.default_value) ** 2


def _set_eccentricity(self, value):
    sock = _roughness_socket(self)
    if sock is not None:
        sock.default_value = eccentricity_roughness(value)


def _get_cosine_power(self):
    sock = _roughness_socket(self)
    if sock is None:
        return MAYA_COSINE_POWER
    r4 = max(float(sock.default_value), 1e-3) ** 4
    return max(2.0, 2.0 / r4 - 2.0)


def _set_cosine_power(self, value):
    sock = _roughness_socket(self)
    if sock is not None:
        sock.default_value = cosine_power_roughness(value)


def _get_diffuse(self):
    sock = maya_input(self, DIFFUSE_SOCKET)
    return 1.0 if sock is None else float(sock.default_value)


def _set_diffuse(self, value):
    if compat.material_uses_nodes(self):
        ensure_diffuse(self, max(0.0, min(1.0, value)))


MATERIAL_PROPS = ("allset_eccentricity", "allset_cosine_power", "allset_diffuse")


def register_props():
    from bpy.props import FloatProperty
    bpy.types.Material.allset_eccentricity = FloatProperty(
        name="Eccentricity", min=0.0, max=1.0, precision=3, get=_get_eccentricity, set=_set_eccentricity,
        description="Maya Blinn eccentricity (size of the highlight); Principled Roughness = sqrt(eccentricity)")
    bpy.types.Material.allset_cosine_power = FloatProperty(
        name="Cosine Power", min=2.0, soft_max=100.0, precision=3, get=_get_cosine_power, set=_set_cosine_power,
        description="Maya Phong cosine power (higher = smaller highlight); Principled Roughness = "
                    "(2 / (power + 2)) ^ 0.25")
    bpy.types.Material.allset_diffuse = FloatProperty(
        name="Diffuse", min=0.0, max=1.0, precision=3, get=_get_diffuse, set=_set_diffuse,
        description="Maya diffuse: the share of the colour reflected (Base Color = Color x Diffuse through the "
                    "Maya Diffuse node)")


def unregister_props():
    for name in MATERIAL_PROPS:
        if hasattr(bpy.types.Material, name):
            delattr(bpy.types.Material, name)


def register_handlers():
    for lst, fn in HANDLERS:
        if fn not in lst:
            lst.append(fn)
    try:
        _baseline()
    except AttributeError:   # register runs with restricted bpy.data at startup: the first update baselines
        pass


def unregister_handlers():
    for lst, fn in HANDLERS:
        if fn in lst:
            lst.remove(fn)
    _known.clear()


def targets(context, rmb=False):
    """Objects to assign to: the edited objects, the selection, else (from the RMB
    menu) the object the menu was opened on, like Maya."""
    if context.mode.startswith('EDIT'):
        return [o for o in context.objects_in_mode if o.type in SUPPORTED]
    obs = [o for o in context.selected_objects if o.type in SUPPORTED]
    if not obs and rmb:
        ob = bpy.data.objects.get(getattr(context.window_manager, "allset_mm_target", ""))
        if ob is not None and ob.type in SUPPORTED:
            obs = [ob]
    return obs


def _poll(context):
    # Poll can't see ``rmb``: the object under the last RMB menu counts too (Maya doesn't
    # grey these items either; without a target the operator reports and cancels).
    return bool(targets(context, rmb=True))


def _face_mode(context):
    return context.mode == 'EDIT_MESH' and context.tool_settings.mesh_select_mode[2]


def assign_object(ob, mat):
    """The whole object gets ``mat``; returns its slot index (0)."""
    data = ob.data
    if ob.type == 'MESH':
        if ob.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(data)
            for f in bm.faces:
                f.material_index = 0
            bmesh.update_edit_mesh(data)
        else:
            data.polygons.foreach_set("material_index", [0] * len(data.polygons))
    elif ob.type in {'CURVE', 'SURFACE'}:
        for spline in data.splines:
            spline.material_index = 0
    data.materials.clear()
    data.materials.append(mat)
    ob.active_material_index = 0
    ob.active_material = mat  # also right for object-linked slots
    return 0


def assign_faces(ob, mat):
    """Selected faces of an edited mesh get ``mat``; returns the slot index, or None
    when no face is selected."""
    bm = bmesh.from_edit_mesh(ob.data)
    faces = [f for f in bm.faces if f.select]
    if not faces:
        return None
    slots = ob.material_slots
    index = next((i for i, s in enumerate(slots) if s.material == mat), None)
    if index is None:
        if not slots:   # the rest of the mesh keeps the default: Maya's lambert1, else no material
            ob.data.materials.append(default_material() if _maya_scene() else None)
        ob.data.materials.append(mat)
        index = len(ob.material_slots) - 1
        bm = bmesh.from_edit_mesh(ob.data)
        faces = [f for f in bm.faces if f.select]
    for f in faces:
        f.material_index = index
    bmesh.update_edit_mesh(ob.data)
    return index


def assign(context, mat, obs):
    """Assign ``mat`` the Maya way; returns {object name: slot index}."""
    done = {}
    faces = _face_mode(context)
    for ob in obs:
        index = assign_faces(ob, mat) if faces and ob.type == 'MESH' and ob.mode == 'EDIT' else None
        done[ob.name] = assign_object(ob, mat) if index is None else index
    return done


def _show_in_ae(context, done):
    """Point the Attribute Editor's tab at the assigned material (Maya shows a new
    material in the AE, AEpopupWhenCreatingShaders)."""
    from ..ui import attribute_editor
    ob = context.active_object
    if ob is None or ob.name not in done:
        ob = bpy.data.objects.get(next(iter(done)))
    attribute_editor.set_tab(context, f"MAT:{done[ob.name]}")


# --- operators -------------------------------------------------------------------------------

_RMB = BoolProperty(name="From RMB Menu", options={'HIDDEN', 'SKIP_SAVE'},
                    description="Use the object under the RMB menu when nothing is selected")


def create_and_assign(op, context, kind):
    obs = targets(context, op.rmb)
    if not obs:
        op.report({'WARNING'}, "Select objects or faces to assign a material to")
        return {'CANCELLED'}
    mat = new_material(kind)
    _show_in_ae(context, assign(context, mat, obs))
    return {'FINISHED'}


class ALLSET_OT_shelf_material(bpy.types.Operator):
    """Create a material and assign it to the selected objects or faces (Maya shelf
    material buttons, Assign Favorite Material)"""
    bl_idname = "allset.shelf_material"
    bl_label = "Assign New Material"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(items=KIND_ITEMS)
    rmb: _RMB

    @classmethod
    def poll(cls, context):
        return _poll(context)

    def execute(self, context):
        return create_and_assign(self, context, self.kind)


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_assign_new_material(bpy.types.Operator):
    """Pick a material type, create it and assign it to the selected objects or faces
    (Maya Assign New Material, Shift+T)"""
    bl_idname = "allset.assign_new_material"
    bl_label = "Assign New Material"
    bl_options = {'REGISTER', 'UNDO'}
    bl_property = "kind"

    kind: EnumProperty(items=KIND_ITEMS, name="Material")
    rmb: _RMB

    @classmethod
    def poll(cls, context):
        return _poll(context)

    def invoke(self, context, event):
        # Maya's "Assign New Material" type list with its search field.
        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        return create_and_assign(self, context, self.kind)


class ALLSET_OT_assign_material(bpy.types.Operator):
    """Assign this material to the selected objects or faces (Maya Assign Existing Material)"""
    bl_idname = "allset.assign_material"
    bl_label = "Assign Existing Material"
    bl_options = {'REGISTER', 'UNDO'}

    material: StringProperty(name="Material", options={'SKIP_SAVE'})
    rmb: _RMB

    @classmethod
    def poll(cls, context):
        return _poll(context)

    def execute(self, context):
        mat = bpy.data.materials.get(self.material)
        obs = targets(context, self.rmb)
        if mat is None or not obs:
            self.report({'WARNING'}, "Select objects or faces and a material")
            return {'CANCELLED'}
        assign(context, mat, obs)
        return {'FINISHED'}


class ALLSET_OT_material_attributes(bpy.types.Operator):
    """Show the object's material in the Attribute Editor (Maya Material Attributes)"""
    bl_idname = "allset.material_attributes"
    bl_label = "Material Attributes"

    rmb: _RMB

    @staticmethod
    def _object(context, rmb):
        if rmb:
            ob = bpy.data.objects.get(getattr(context.window_manager, "allset_mm_target", ""))
            if ob is not None:
                return ob
        return context.active_object

    @classmethod
    def poll(cls, context):
        ob = cls._object(context, True)
        return ob is not None and any(s.material for s in ob.material_slots)

    def execute(self, context):
        from ..ui import attribute_editor
        ob = self._object(context, self.rmb)
        if ob is None:
            return {'CANCELLED'}
        slots = ob.material_slots
        i = ob.active_material_index
        if i >= len(slots) or slots[i].material is None:
            i = next((n for n, s in enumerate(slots) if s.material), None)
        if i is None:
            self.report({'WARNING'}, f"{ob.name} has no material")
            return {'CANCELLED'}
        if context.active_object is not ob and context.view_layer.objects.get(ob.name):
            context.view_layer.objects.active = ob
        attribute_editor.show_dock(context, 'ATTRIBUTE_EDITOR')
        attribute_editor.set_tab(context, f"MAT:{i}")
        for area in context.screen.areas if context.screen else ():
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}


# --- menus -----------------------------------------------------------------------------------

class ALLSET_MT_assign_favorite_material(bpy.types.Menu):
    """Create a material of a favourite type and assign it (Maya Assign Favorite Material)"""
    bl_idname = "ALLSET_MT_assign_favorite_material"
    bl_label = "Assign Favorite Material"
    rmb = False

    def draw(self, context):
        for kind in FAVORITES:
            op = self.layout.operator("allset.shelf_material", text=MATERIALS[kind][1], icon='MATERIAL')
            op.kind = kind
            op.rmb = self.rmb


class ALLSET_MT_assign_existing_material(bpy.types.Menu):
    """Assign a material of the scene (Maya Assign Existing Material)"""
    bl_idname = "ALLSET_MT_assign_existing_material"
    bl_label = "Assign Existing Material"
    rmb = False

    def draw(self, context):
        mats = sorted((m for m in bpy.data.materials if not m.is_grease_pencil), key=lambda m: m.name.lower())
        if not mats:
            self.layout.label(text="No materials in the scene")
            return
        for mat in mats:
            op = self.layout.operator("allset.assign_material", text=mat.name, icon='MATERIAL')
            op.material = mat.name
            op.rmb = self.rmb


class ALLSET_MT_assign_existing_material_rmb(ALLSET_MT_assign_existing_material):
    """Assign a material of the scene to the selection or the object under the RMB menu"""
    bl_idname = "ALLSET_MT_assign_existing_material_rmb"
    rmb = True


classes = (ALLSET_OT_shelf_material, ALLSET_OT_assign_new_material, ALLSET_OT_assign_material,
           ALLSET_OT_material_attributes, ALLSET_MT_assign_favorite_material,
           ALLSET_MT_assign_existing_material, ALLSET_MT_assign_existing_material_rmb)
