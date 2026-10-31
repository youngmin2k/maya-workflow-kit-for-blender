# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Deform > Export Weights... / Import Weights... (``deformerWeights``): a deformer's weights as Maya's XML file.

Format and import rules: one ``<shape>`` with the shape's
object-space points (Maya Y-up, cm), then one ``<weights>`` element per influence (skinCluster: per joint; cluster and
other one-weight deformers: source ``baseLayer``) listing only the points with a non-zero weight. The kit writes the
same structure, so Maya reads its files and the kit reads Maya's (and Maya's JSON variant).

A kit skin = the Armature modifier (named ``skinClusterN``) + vertex groups named after its bones; a kit
deformer (operators/deformers.py) owns one vertex group = its ``baseLayer`` weights.

Import "Index" (the default, like Maya): an influence in the file replaces that influence's whole weight list — vertices the
file leaves out get the element's defaultValue (0 = out of the group); influences the file doesn't mention keep their
weights. "Nearest": each vertex takes the weights of the file point closest to it (object space). Sources that aren't
influences of the target are skipped with Maya's warning.
"""

import json
import os
import xml.etree.ElementTree as ET

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from mathutils import Matrix, Vector, kdtree

from .. import results
from . import units

PRECISION = 9          # Maya writes 3 decimals by default (-weightPrecision 3); the kit writes 9 (lossless to 1e-9)
BASE_LAYER = "baseLayer"
METHODS = (("INDEX", "Index", "Weights by vertex index (the default, like Maya)"),
           ("NEAREST", "Nearest", "Each vertex takes the weights of the closest point in the file"))
UNKNOWN_WARNING = "Unable to find the match weight set name '{}' to given deformer."
NO_DEFORMER = "No deformer found.  Please select an object with a deformer."


# --- Maya <-> Blender object space ----------------------------------------------------------------------------------
# Maya Y-up axes map to Blender as X -> X, Y -> Z, Z -> -Y; one Maya length = units.maya_unit().

def to_maya(co, k=1.0):
    """Blender object-space point -> Maya point (x, y, z)."""
    return (co[0] / k, co[2] / k, -co[1] / k)


def from_maya(p, k=1.0):
    """Maya point -> Blender object-space point."""
    return Vector((p[0] * k, -p[2] * k, p[1] * k))


_AXES = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))      # Maya coords -> Blender coords


def maya_world_matrix(matrix_world, k=1.0):
    """Maya's 16 worldMatrix numbers (row-vector order: translation last) of a Blender object matrix."""
    m = _AXES.inverted() @ matrix_world @ _AXES
    m = m.copy()
    for r in range(3):
        m[r][3] /= k
    return [m[r][c] for c in range(4) for r in range(4)]


# --- XML ------------------------------------------------------------------------------------------------------------

def _num(v, digits):
    return f"{v:.{digits}f}"


def export_xml(shape, deformer, influences, points=None, world_matrix=None, file_name="", precision=PRECISION):
    """Maya deformerWeights XML text.

    ``influences``: ordered {source name: {vertex index: weight}}; ``points``: [Maya point] by vertex index (the
    ``<shape>`` element); ``world_matrix``: Maya's 16 numbers (identity when None). Zero weights are left out like
    Maya does; an influence without any weight is written as an empty element (size 0)."""
    wm = world_matrix if world_matrix is not None else [1.0 if r == c else 0.0 for c in range(4) for r in range(4)]
    lines = ['<?xml version="1.0"?>', "<deformerWeight>",
             f'  <headerInfo fileName="{_esc(file_name)}" worldMatrix="'
             + "".join(_num(v, 6) + " " for v in wm) + '"/>']
    if points is not None:
        n = len(points)
        lines.append(f'  <shape name="{_esc(shape)}" group="0" stride="3" size="{n}" max="{max(n - 1, 0)}">')
        for i, p in enumerate(points):
            lines.append(f'    <point index="{i}" value="' + "".join(" " + _num(c, 6) for c in p) + '"/>')
        lines.append("  </shape>")
    for layer, (source, weights) in enumerate(influences.items()):
        rows = sorted((i, w) for i, w in weights.items() if w > 0.0)
        top = rows[-1][0] if rows else 0
        lines.append(f'  <weights deformer="{_esc(deformer)}" source="{_esc(source)}" shape="{_esc(shape)}" '
                     f'layer="{layer}" defaultValue="{_num(0.0, precision)}" size="{len(rows)}" max="{top}">')
        for i, w in rows:
            lines.append(f'    <point index="{i}" value="{_num(w, precision)}"/>')
        lines.append("  </weights>")
    lines.append("</deformerWeight>")
    return "\n".join(lines) + "\n"


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _floats(text):
    return [float(x) for x in (text or "").split()]


def parse_xml(text):
    """Read a deformerWeights file (Maya's or the kit's; XML, or Maya's JSON variant).

    Returns {"file_name", "world_matrix": [16], "shapes": {name: {index: (x, y, z)}} (Maya coords),
    "deformers": {name: {"type", "attributes": {name: value}}}, "weights": [{"deformer", "source", "shape",
    "layer", "default", "points": {index: weight}}]} in file order."""
    if text.lstrip().startswith("{"):
        return _parse_json(text)
    root = ET.fromstring(text)
    if root.tag != "deformerWeight":
        raise ValueError("Not a deformer weights file")
    out = {"file_name": "", "world_matrix": None, "shapes": {}, "deformers": {}, "weights": []}
    for el in root:
        if el.tag == "headerInfo":
            out["file_name"] = el.get("fileName", "")
            wm = _floats(el.get("worldMatrix"))
            out["world_matrix"] = wm if len(wm) == 16 else None
        elif el.tag == "shape":
            out["shapes"][el.get("name", "")] = {int(p.get("index")): tuple(_floats(p.get("value")))
                                                 for p in el if p.tag == "point"}
        elif el.tag == "deformer":
            out["deformers"][el.get("name", "")] = {
                "type": el.get("type", ""),
                "attributes": {a.get("name"): a.get("value") for a in el if a.tag == "attribute"}}
        elif el.tag == "weights":
            out["weights"].append({
                "deformer": el.get("deformer", ""), "source": el.get("source", ""), "shape": el.get("shape", ""),
                "layer": int(el.get("layer", len(out["weights"]))), "default": float(el.get("defaultValue", 0.0)),
                "points": {int(p.get("index")): float(p.get("value")) for p in el if p.tag == "point"}})
    return out


def _parse_json(text):
    d = json.loads(text).get("deformerWeight", {})
    head = d.get("headerInfo", {})
    wm = head.get("worldMatrix")
    out = {"file_name": head.get("fileName", ""), "world_matrix": list(wm) if wm and len(wm) == 16 else None,
           "shapes": {}, "deformers": {}, "weights": []}
    for s in d.get("shapes", ()):
        out["shapes"][s.get("name", "")] = {int(p["index"]): tuple(p["value"]) for p in s.get("points", ())}
    for df in d.get("deformers", ()):
        out["deformers"][df.get("name", "")] = {
            "type": df.get("type", ""),
            "attributes": {a.get("name"): a.get("value") for a in df.get("attributes", ())}}
    for i, w in enumerate(d.get("weights", ())):
        out["weights"].append({
            "deformer": w.get("deformer", ""), "source": w.get("source", ""), "shape": w.get("shape", ""),
            "layer": int(w.get("layer", i)), "default": float(w.get("defaultValue", 0.0)),
            "points": {int(p["index"]): float(p["value"]) for p in w.get("points", ())}})
    return out


# --- Import maths (bpy-free) ----------------------------------------------------------------------------------------

def nearest_map(vertex_points, file_points):
    """{vertex index: file point index} — the closest file point to each vertex (same space for both)."""
    if not file_points:
        return {}
    tree = kdtree.KDTree(len(file_points))
    for idx, p in file_points.items():
        tree.insert(p, idx)
    tree.balance()
    return {i: tree.find(co)[1] for i, co in enumerate(vertex_points)}


def resolve(element, count, mapping=None):
    """{vertex index: weight} for ``count`` vertices from one ``<weights>`` element (Index: by index; with ``mapping``
    = nearest_map: by the mapped file point). Vertices without an entry get the element's default."""
    pts, dv = element["points"], element["default"]
    if mapping is None:
        return {i: pts.get(i, dv) for i in range(count)}
    return {i: pts.get(mapping.get(i, -1), dv) for i in range(count)}


# --- Blender side ---------------------------------------------------------------------------------------------------

def _skin():
    from . import skin
    return skin


def _deformers_mod():
    from . import deformers
    return deformers


def deformers_of(mesh):
    """[(Maya deformer name, modifier, kind)] of a mesh: its skin ('SKIN') and kit deformers with a weight group
    ('GROUP')."""
    out = []
    if mesh is None or mesh.type != 'MESH':
        return out
    md = _skin().armature_modifier(mesh)
    if md is not None:
        out.append((md.name, md, 'SKIN'))
    dfm = _deformers_mod()
    for m in mesh.modifiers:
        if m.type == 'ARMATURE' or dfm.is_base(m) or dfm.node_type(m) is None:
            continue
        if getattr(m, "vertex_group", "") and m.vertex_group in mesh.vertex_groups:
            out.append((m.name, m, 'GROUP'))
    return out


def find_deformer(mesh, name=""):
    found = deformers_of(mesh)
    if name:
        return next((d for d in found if d[0] == name), None)
    return found[0] if found else None


def influence_groups(mesh, deformer):
    """Ordered {source: vertex group} of a deformer entry from ``deformers_of``."""
    _name, md, kind = deformer
    if kind == 'SKIN':
        return {vg.name: vg for vg in _skin().influences(mesh)}
    return {BASE_LAYER: mesh.vertex_groups[md.vertex_group]}


def collect(mesh, deformer):
    """Ordered {source: {vertex index: weight}} (non-zero weights only)."""
    groups = influence_groups(mesh, deformer)
    out = {src: {} for src in groups}
    by_index = {vg.index: src for src, vg in groups.items()}
    for v in mesh.data.vertices:
        for g in v.groups:
            src = by_index.get(g.group)
            if src is not None and g.weight > 0.0:
                out[src][v.index] = g.weight
    return out


def export_file(mesh, deformer_name, filepath, precision=PRECISION):
    """Write the weights of ``mesh``'s deformer ``deformer_name`` (its first deformer when empty); returns the path."""
    deformer = find_deformer(mesh, deformer_name)
    if deformer is None:
        raise RuntimeError(NO_DEFORMER)
    k = units.maya_unit()
    points = [to_maya(v.co, k) for v in mesh.data.vertices]
    path = os.path.abspath(filepath)
    text = export_xml(maya_shape_name(mesh), deformer[0], collect(mesh, deformer), points,
                      maya_world_matrix(mesh.matrix_world, k), path.replace("\\", "/"), precision)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def maya_shape_name(mesh):
    """The kit keeps Maya's shape name on the mesh data (``pCubeShape1``); other data gets Maya's rule."""
    if "Shape" in mesh.data.name:
        return mesh.data.name
    from .file_io import shape_name
    return shape_name(mesh.name)


def _pick_shape(data, mesh):
    shapes = data["shapes"]
    name = maya_shape_name(mesh)
    if name in shapes:
        return name
    return next(iter(shapes), "")


def import_data(mesh, data, deformer_name="", method="INDEX", normalize=True, ignore_names=False):
    """Apply parsed deformer weights to ``mesh``. Returns (sources applied, warnings).

    Target deformer = ``deformer_name``, else the file's deformer if the mesh has it, else the mesh's first deformer.
    Skin sources that are bones of the skeleton but have no vertex group yet get one."""
    shape = _pick_shape(data, mesh)
    elements = [w for w in data["weights"] if not w["shape"] or not shape or w["shape"] == shape]
    target = find_deformer(mesh, deformer_name) if deformer_name else None
    if target is None and not deformer_name:
        names = {w["deformer"] for w in elements}
        target = next((d for d in deformers_of(mesh) if d[0] in names), None) or find_deformer(mesh)
    if target is None:
        raise RuntimeError(NO_DEFORMER)
    file_deformers = {w["deformer"] for w in elements}
    if len(file_deformers) > 1:
        keep = target[0] if target[0] in file_deformers else elements[0]["deformer"]
        elements = [w for w in elements if w["deformer"] == keep]
    groups = influence_groups(mesh, target)
    bones = set()
    if target[2] == 'SKIN':
        bones = {b.name for b in target[1].object.data.bones}
    count = len(mesh.data.vertices)
    mapping = None
    if method == "NEAREST":
        k = units.maya_unit()
        file_pts = {i: from_maya(p, k) for i, p in data["shapes"].get(shape, {}).items()}
        mapping = nearest_map([v.co for v in mesh.data.vertices], file_pts)
    order = list(groups)
    applied, warnings = [], []
    for n, el in enumerate(elements):
        src = el["source"]
        if ignore_names:
            src = order[n] if n < len(order) else None
        if target[2] == 'GROUP' and len(groups) == 1 and len(elements) == 1:
            src = BASE_LAYER
        vg = groups.get(src) if src is not None else None
        if vg is None and src in bones:
            vg = mesh.vertex_groups.new(name=src)
            groups[src] = vg
        if vg is None:
            warnings.append(UNKNOWN_WARNING.format(el["source"]))
            continue
        weights = resolve(el, count, mapping)
        vg.remove(list(range(count)))
        by_value = {}
        for i, w in weights.items():
            if w > 0.0:
                by_value.setdefault(w, []).append(i)
        for w, idx in by_value.items():
            vg.add(idx, w, 'REPLACE')
        applied.append(src)
    if normalize and target[2] == 'SKIN' and applied:
        normalize_skin(mesh, groups)
    return applied, warnings


def normalize_skin(mesh, groups):
    """Maya Import option "Normalize weights" (skinCluster -forceNormalizeWeights): each vertex's influence weights
    sum to 1 (vertices without weight stay without)."""
    idx = {vg.index for vg in groups.values()}
    for v in mesh.data.vertices:
        gs = [g for g in v.groups if g.group in idx]
        total = sum(g.weight for g in gs)
        if total > 0.0 and abs(total - 1.0) > 1e-7:
            for g in gs:
                g.weight = g.weight / total


def import_file(mesh, filepath, deformer_name="", method="INDEX", normalize=True, ignore_names=False):
    with open(filepath, encoding="utf-8") as fh:
        data = parse_xml(fh.read())
    return import_data(mesh, data, deformer_name, method, normalize, ignore_names)


def default_dir(context):
    """The current project's data folder (Maya's -path default is the project), else the .blend's folder."""
    try:
        from . import project
        root = project.ensure_root(context)
        if root:
            return os.path.join(root, "data")
    except Exception:
        pass
    return bpy.path.abspath("//") or os.path.expanduser("~")


def target_mesh(context):
    """The selected deformed mesh: the active object first."""
    obs = [context.active_object] if context.active_object is not None else []
    obs += [o for o in context.selected_objects if o not in obs]
    return next((o for o in obs if deformers_of(o)), None)


# --- Operators ------------------------------------------------------------------------------------------------------

_ENUM_CACHE = []


def _deformer_items(self, context):
    mesh = target_mesh(context)
    items = [(d[0], d[0], "") for d in deformers_of(mesh)] if mesh is not None else []
    _ENUM_CACHE[:] = items or [("", "(none)", "")]
    return _ENUM_CACHE


def _set_mode_object(context):
    if context.active_object is not None and context.active_object.mode not in {'OBJECT', 'PAINT_WEIGHT'}:
        bpy.ops.object.mode_set(mode='OBJECT')


class ALLSET_OT_export_deformer_weights(bpy.types.Operator):
    """Maya Export Weights: write the selected object's deformer weights to an XML file Maya can import"""
    bl_idname = "allset.export_deformer_weights"
    bl_label = "Export"
    bl_options = set()

    filepath: StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    filter_glob: StringProperty(default="*.xml;*.json", options={'HIDDEN'})
    deformer: EnumProperty(name="Existing nodes", items=_deformer_items)

    def invoke(self, context, event):
        mesh = target_mesh(context)
        if mesh is None:
            self.report({'WARNING'}, NO_DEFORMER)
            return {'CANCELLED'}
        name = self.deformer or deformers_of(mesh)[0][0]
        self.filepath = os.path.join(default_dir(context), f"{name}.xml")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        mesh = target_mesh(context)
        if mesh is None:
            self.report({'WARNING'}, NO_DEFORMER)
            return {'CANCELLED'}
        _set_mode_object(context)
        path = self.filepath or os.path.join(default_dir(context), f"{self.deformer or 'weightSet'}.xml")
        if not os.path.splitext(path)[1]:
            path += ".xml"
        try:
            path = export_file(mesh, self.deformer, path)
        except (OSError, RuntimeError) as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        results.result(self, f"Exported deformer weights to '{path.replace(os.sep, '/')}'.")
        return {'FINISHED'}


class ALLSET_OT_import_deformer_weights(bpy.types.Operator):
    """Maya Import Weights: read deformer weights from an XML file (Maya's or the kit's) onto the selected object"""
    bl_idname = "allset.import_deformer_weights"
    bl_label = "Import"
    bl_options = {'UNDO'}      # Maya has no redo panel: UNDO only

    filepath: StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    filter_glob: StringProperty(default="*.xml;*.json", options={'HIDDEN'})
    deformer: EnumProperty(name="Deformer node", items=_deformer_items)
    method: EnumProperty(name="Mapping method", items=METHODS, default="INDEX")
    ignore_names: BoolProperty(name="Ignore names", default=False,
                               description="Match the file's influences by their order instead of their names")
    normalize: BoolProperty(name="Normalize weights", default=True,
                            description="Make each vertex's skin weights sum to 1 after the import")

    def invoke(self, context, event):
        if target_mesh(context) is None:
            self.report({'WARNING'}, NO_DEFORMER)
            return {'CANCELLED'}
        self.filepath = default_dir(context) + os.sep
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        mesh = target_mesh(context)
        if mesh is None:
            self.report({'WARNING'}, NO_DEFORMER)
            return {'CANCELLED'}
        if not self.filepath or not os.path.isfile(self.filepath):
            self.report({'ERROR'}, f"Cannot open file '{self.filepath}'.")
            return {'CANCELLED'}
        _set_mode_object(context)
        try:
            applied, warnings = import_file(mesh, self.filepath, self.deformer, self.method, self.normalize,
                                            self.ignore_names)
        except (OSError, ValueError, ET.ParseError, RuntimeError) as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        for w in warnings:
            self.report({'WARNING'}, w)
        mesh.data.update()
        mesh.update_tag()
        if not applied:
            return {'CANCELLED'}
        results.result(self, f"Imported deformer weights from '{self.filepath.replace(os.sep, '/')}'.")
        return {'FINISHED'}


classes = (ALLSET_OT_export_deformer_weights, ALLSET_OT_import_deformer_weights)


def register_bindings():
    pass


def unregister_bindings():
    pass
