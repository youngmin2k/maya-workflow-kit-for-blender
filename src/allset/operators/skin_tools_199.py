# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Skin menu tools: Move Weights to Influences, Normalize Weights > Disable / Enable / Enable Post,
Export Weight Maps... / Import Weights Maps..., Substitute Geometry, Bake Deformation to Skin Weights...

Every rule here follows Maya 2022.
A kit skin = the Armature modifier + vertex groups named after
its bones (operators/skin.py); a joint's Maya "lock weights" (.liw) = the vertex group's ``lock_weight``.

- Move Weights to Influences (Maya runs
  ``cmds.skinPercent(transformMoveWeights=[source, target, ...])``): on each selected vertex every unlocked target gets
  the **source's weight** (set, not added), the source gets 0; with Interactive normalisation the unlocked weights are
  then scaled to fill 1 - (locked weights). None / Post leave the sums as they are.
- Normalize Weights modes (skinCluster.normalizeWeights 0 / 1 / 2): Maya deforms
  a point by sum(w_i M_i p) in world space in None and Interactive (unnormalised weights scale the point about the
  world origin; a point without weights stays put) and by sum(w_i M_i p) / sum(w_i) in Post. Blender's Armature
  modifier is Post (it divides by the weight sum), so None / Interactive skins get a Geometry Nodes modifier
  after the Armature modifier that multiplies the world position by the weight sum.
- Weight maps (Maya Export / Import Skin Weight Maps): a ``<name>.weightMap`` text file (two comment lines, then
  ``<skin>\\t<influence>\\t<image>`` per weighted influence) and a ``<name>/`` folder with one grey image per influence
  in UV space (factory 512 x 512, luminance). Import: every weight of the skins in the file is cleared
  (``cmds.skinPercent(pruneWeights=1.1)``), each listed influence takes the image value at the vertex UVs, then the
  weights are normalised.
- Substitute Geometry (``cmds.substituteGeometry(old, new, wdt=1)``): the skinned object
  keeps its name, transform and skin and takes the new mesh's object-space points; each new vertex takes the old
  weights interpolated at the closest point of the old surface (bilinear on quads, barycentric on triangles) when that
  point is within the reweighting distance, else the weights of the nearest old vertex.
- Bake Deformation to Skin Weights (``bakeDeformer``): per vertex the weights are the
  least-squares fit, over a range of motion, of linear blend skinning of the **source rest point** to the source's
  deformed points, constrained to w >= 0 and sum(w) = 1. The kit's range of motion samples each joint rotated
  +-45 degrees about its X / Y / Z axes.
"""

import math
import os

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from mathutils import Matrix, Vector, kdtree
from mathutils.bvhtree import BVHTree

from .. import results
from . import skin, units

# --- shared helpers -----------------------------------------------------------------------------------------------

NO_SKIN = "Select a skinned mesh"


def _skin_armature(mesh):
    md = skin.armature_modifier(mesh)
    return md.object if md is not None else None


def skinned_meshes(context):
    """Selected skinned meshes, the active one first (edit / paint modes: the active object)."""
    out = []
    ob = context.active_object
    if ob is not None and ob.type == 'MESH' and _skin_armature(ob) is not None:
        out.append(ob)
    for o in context.selected_objects:
        if o.type == 'MESH' and o not in out and _skin_armature(o) is not None:
            out.append(o)
    return out


def influence_names(mesh):
    """Maya skinCluster influences = the mesh's vertex groups that are bones of its skeleton, in group order."""
    arm = _skin_armature(mesh)
    if arm is None:
        return []
    bones = set(arm.data.bones.keys())
    return [vg.name for vg in mesh.vertex_groups if vg.name in bones]


class _Weights:
    """Read / write vertex group weights through a BMesh deform layer: works in object, paint and edit mode."""

    def __init__(self, mesh):
        self.mesh = mesh
        self.edit = mesh.mode == 'EDIT'
        if self.edit:
            self.bm = bmesh.from_edit_mesh(mesh.data)
        else:
            self.bm = bmesh.new()
            self.bm.from_mesh(mesh.data)
        self.bm.verts.ensure_lookup_table()
        self.layer = self.bm.verts.layers.deform.verify()

    def selected(self):
        return [v.index for v in self.bm.verts if v.select]

    def get(self, vi, gi):
        return self.bm.verts[vi][self.layer].get(gi, 0.0)

    def set(self, vi, gi, w):
        dv = self.bm.verts[vi][self.layer]
        if w > 0.0 or gi in dv:
            dv[gi] = w

    def flush(self):
        if self.edit:
            bmesh.update_edit_mesh(self.mesh.data, loop_triangles=False, destructive=False)
        else:
            self.bm.to_mesh(self.mesh.data)
            self.bm.free()
        self.mesh.data.update()


# --- Move Weights to Influences ------------------------------------------------------------------------------------
# Maya's errors (Move Weights to Influences, skinPercent).
NO_VERTS = "No skin vertices were selected."
BAD_SOURCE = "Selected source influence for move weights are either locked or not connected to this skin cluster."
BAD_TARGETS = "Selected target influences for move weights are either locked or not connected to this skin cluster."


def move_row(row, source, targets, locked, interactive):
    """One vertex: ``row`` {influence: weight} (every influence), returns the new row (Maya skinPercent -tmw)."""
    row = dict(row)
    s = row.get(source, 0.0)
    for t in targets:
        if t not in locked:
            row[t] = s
    row[source] = 0.0
    if interactive:
        room = max(0.0, 1.0 - sum(w for n, w in row.items() if n in locked))
        free = [n for n in row if n not in locked]
        total = sum(row[n] for n in free)
        if total > 0.0:
            for n in free:
                row[n] = row[n] * room / total
    return row


def move_weights(mesh, source, targets, verts=None):
    """Move ``source``'s weights to ``targets`` on the selected (or given) vertices; raises ValueError with Maya's
    message. Returns the number of vertices changed."""
    names = influence_names(mesh)
    groups = {vg.name: vg for vg in mesh.vertex_groups}
    locked = {n for n in names if groups[n].lock_weight}
    if source not in names or source in locked:
        raise ValueError(BAD_SOURCE)
    tgts = [t for t in targets if t in names and t != source]
    if not [t for t in tgts if t not in locked]:
        raise ValueError(BAD_TARGETS)
    io = _Weights(mesh)
    vs = io.selected() if verts is None else list(verts)
    if not vs:
        if not io.edit:
            io.bm.free()
        raise ValueError(NO_VERTS)
    interactive = skin.normalize_mode(mesh) == "INTERACTIVE"
    idx = {n: groups[n].index for n in names}
    for vi in vs:
        row = {n: io.get(vi, idx[n]) for n in names}
        new = move_row(row, source, tgts, locked, interactive)
        for n, w in new.items():
            if abs(w - row[n]) > 0.0:
                io.set(vi, idx[n], w)
    io.flush()
    return len(vs)


def picked_joints(arm):
    """Selected joints of ``arm`` as (source, targets): Maya takes the first selected joint as the source; Blender
    keeps no selection order, so with two joints the active (last picked) one is the target, with more the joints
    other than the active one come in skeleton order and the first is the source."""
    from ..ui import channel_box      # Bone.select is gone in 5.x: the shim
    sel = [pb.name for pb in arm.pose.bones if channel_box.bone_selected(pb)]
    act = arm.data.bones.active
    act = act.name if act is not None and act.name in sel else None
    others = [n for n in sel if n != act]
    if act is None:
        return (sel[0], sel[1:]) if sel else (None, [])
    if not others:
        return None, [act]
    return others[0], others[1:] + [act]


class ALLSET_OT_move_skin_weights(bpy.types.Operator):
    """Maya Skin > Move Weights to Influences: on the selected vertices the target joints get the source joint's
    weight and the source gets none (select the vertices, the source joint, then the targets)"""
    bl_idname = "allset.move_skin_weights"
    bl_label = "Move Weights to Influences"
    bl_options = {'REGISTER', 'UNDO'}

    source: StringProperty(name="Source", default="", options={'SKIP_SAVE', 'HIDDEN'})
    targets: StringProperty(name="Targets", description="Comma-separated joint names", default="",
                            options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        meshes = skinned_meshes(context)
        if not meshes:
            self.report({'WARNING'}, "No skin cluster found: select the skinned vertices and the joints")
            return {'CANCELLED'}
        done = 0
        for mesh in meshes:
            if self.source:
                src, tgts = self.source, [t.strip() for t in self.targets.split(",") if t.strip()]
            else:
                src, tgts = picked_joints(_skin_armature(mesh))
            try:
                done += move_weights(mesh, src, tgts)
            except ValueError as ex:
                self.report({'ERROR'}, str(ex))
                return {'CANCELLED'}
        results.result(self, f"skinPercent: moved weights on {done} vertices")
        return {'FINISHED'}


# --- Normalize Weights: None / Interactive / Post --------------------------------------------------------------------
SUM_SUFFIX = "WeightSum"               # modifier "<skinClusterN>WeightSum" (part of the skin node, not an INPUTS node)
SUM_TAG = "allset_weight_sum"          # node group ID prop: the influence names it sums
NORMALIZE_LABELS = {"NONE": "Disable Weight Normalization", "INTERACTIVE": "Enable Weight Normalization",
                    "POST": "Enable Weight Post Normalization"}
MAYA_VALUE = {"NONE": 0, "INTERACTIVE": 1, "POST": 2}      # skinCluster.normalizeWeights


def is_part(md):
    """True for the kit's weight-sum modifier: part of the skin (hide it from INPUTS / the AE like a Hook base)."""
    return md.type == 'NODES' and md.node_group is not None and SUM_TAG in md.node_group


def sum_modifier(mesh):
    return next((m for m in mesh.modifiers if is_part(m)), None)


def _link(tree, a, b):
    tree.links.new(a, b)


def _build_sum_group(tree, names):
    """position_world *= sum(influence weights) where that sum > 1e-4 (Blender's Armature modifier leaves points
    whose sum is below 1e-4 at rest), in the object's world space (Maya scales about the world origin)."""
    tree.nodes.clear()
    if not tree.interface.items_tree:
        tree.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
        tree.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    n = tree.nodes
    gin = n.new('NodeGroupInput')
    gout = n.new('NodeGroupOutput')
    total = None
    for name in names:
        na = n.new('GeometryNodeInputNamedAttribute')
        na.data_type = 'FLOAT'
        na.inputs["Name"].default_value = name
        if total is None:
            total = na.outputs["Attribute"]
        else:
            add = n.new('ShaderNodeMath')
            add.operation = 'ADD'
            _link(tree, total, add.inputs[0])
            _link(tree, na.outputs["Attribute"], add.inputs[1])
            total = add.outputs[0]
    setp = n.new('GeometryNodeSetPosition')
    _link(tree, gin.outputs[0], setp.inputs["Geometry"])
    _link(tree, setp.outputs["Geometry"], gout.inputs[0])
    if total is None:
        return
    self_ob = n.new('GeometryNodeSelfObject')
    info = n.new('GeometryNodeObjectInfo')
    info.transform_space = 'ORIGINAL'
    _link(tree, self_ob.outputs[0], info.inputs["Object"])
    pos = n.new('GeometryNodeInputPosition')
    to_world = n.new('FunctionNodeTransformPoint')
    _link(tree, pos.outputs[0], to_world.inputs["Vector"])
    _link(tree, info.outputs["Transform"], to_world.inputs["Transform"])
    scale = n.new('ShaderNodeVectorMath')
    scale.operation = 'SCALE'
    _link(tree, to_world.outputs[0], scale.inputs[0])
    _link(tree, total, scale.inputs["Scale"])
    inv = n.new('FunctionNodeInvertMatrix')
    _link(tree, info.outputs["Transform"], inv.inputs[0])
    back = n.new('FunctionNodeTransformPoint')
    _link(tree, scale.outputs[0], back.inputs["Vector"])
    _link(tree, inv.outputs[0], back.inputs["Transform"])
    cmp = n.new('FunctionNodeCompare')
    cmp.data_type = 'FLOAT'
    cmp.operation = 'GREATER_THAN'
    _link(tree, total, cmp.inputs[0])
    cmp.inputs[1].default_value = 1e-4
    _link(tree, cmp.outputs[0], setp.inputs["Selection"])
    _link(tree, back.outputs[0], setp.inputs["Position"])


def _sum_signature(mesh):
    return "\n".join(influence_names(mesh))


def ensure_sum_modifier(mesh):
    """The weight-sum modifier right after the skin's Armature modifier, summing the current influences."""
    arm_md = skin.armature_modifier(mesh)
    if arm_md is None:
        return None
    md = sum_modifier(mesh)
    if md is None:
        tree = bpy.data.node_groups.new(f".Allset Weight Sum {mesh.name}", 'GeometryNodeTree')
        md = mesh.modifiers.new(f"{arm_md.name}{SUM_SUFFIX}", 'NODES')
        md.node_group = tree
        md.show_in_editmode = arm_md.show_in_editmode
        md.show_on_cage = False
        md.show_expanded = False
        target = list(mesh.modifiers).index(arm_md) + 1
        if list(mesh.modifiers).index(md) != target:
            with bpy.context.temp_override(object=mesh):
                bpy.ops.object.modifier_move_to_index(modifier=md.name, index=target)
    sig = _sum_signature(mesh)
    if md.node_group.get(SUM_TAG) != sig or not md.node_group.nodes:
        _build_sum_group(md.node_group, influence_names(mesh))
        md.node_group[SUM_TAG] = sig
    return md


def remove_sum_modifier(mesh):
    md = sum_modifier(mesh)
    if md is None:
        return
    tree = md.node_group
    mesh.modifiers.remove(md)
    if tree is not None and tree.users == 0:
        bpy.data.node_groups.remove(tree)


def set_normalize_mode(context, mesh, mode):
    """Maya skinCluster.normalizeWeights for one skin: the mode only (weights are not touched, switching
    to Interactive or Post leaves unnormalised weights as they are)."""
    mesh[skin.NORMALIZE_PROP] = mode
    if mode == "POST":
        remove_sum_modifier(mesh)
    else:
        ensure_sum_modifier(mesh)


def normalize_state(context):
    """The normalize mode of the active skin (None without one): the menu's radio state."""
    meshes = skinned_meshes(context)
    return skin.normalize_mode(meshes[0]) if meshes else None


class ALLSET_OT_skin_normalize_mode(bpy.types.Operator):
    """Maya Skin > Normalize Weights > Disable / Enable / Enable Post: how the selected skins keep their weights"""
    bl_idname = "allset.skin_normalize_mode"
    bl_label = "Weight Normalization"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name="Normalize Weights", items=skin.NORMALIZE, default="INTERACTIVE")

    @classmethod
    def description(cls, context, props):
        return {"NONE": "Maya Disable Weight Normalization: weights stay as painted and deform unnormalised",
                "INTERACTIVE": "Maya Enable Weight Normalization: painting a joint takes weight from the others",
                "POST": "Maya Enable Weight Post Normalization: weights are stored as painted, the skin deforms "
                        "with them normalised"}[props.mode]

    def execute(self, context):
        meshes = skinned_meshes(context)
        if not meshes:
            self.report({'ERROR'}, "Select a skinned object or its components")     # Maya's error text
            return {'CANCELLED'}
        for mesh in meshes:
            set_normalize_mode(context, mesh, self.mode)
        context.tool_settings.use_auto_normalize = self.mode == "INTERACTIVE"
        names = [m.name for m in meshes]
        results.result(self, f"setAttr {', '.join(names)} normalizeWeights {MAYA_VALUE[self.mode]}")
        return {'FINISHED'}


@bpy.app.handlers.persistent
def _sync_sum_modifiers(scene, depsgraph):
    """Keep weight-sum modifiers summing the skin's current influences; drop them when the skin is gone."""
    for upd in depsgraph.updates:
        ob = upd.id.original if isinstance(upd.id, bpy.types.Object) else None
        if ob is None or ob.type != 'MESH' or not ob.modifiers:
            continue
        md = sum_modifier(ob)
        if md is None:
            continue
        if skin.armature_modifier(ob) is None:
            remove_sum_modifier(ob)
        elif md.node_group.get(SUM_TAG) != _sum_signature(ob):
            ensure_sum_modifier(ob)


# --- Weight maps ---------------------------------------------------------------------------------------------------
# Maya Export Skin Weight Maps file types; Blender writes these (IFF / SGI / Alias / SoftImage ... aren't Blender formats).
MAP_FORMATS = (("PNG", "PNG", "png"), ("TIFF", "TIFF", "tiff"), ("JPEG", "JPEG", "jpg"), ("TARGA", "Targa", "tga"),
               ("BMP", "Windows Bitmap", "bmp"))
MAP_EXT = {k: e for k, _l, e in MAP_FORMATS}
MAP_HEADER = "// Exported skin weight map file\n// \n"


def map_file_name(taken, base, skin_name, inf, count):
    """Maya's map file names: ``<skin>_<influence>`` (short names), ``_<count>`` when taken,
    ``<base>_<count>`` when longer than 100 characters."""
    def short(name):
        pipe = name.split("|")[-1]
        colon = name.split(":")[-1]
        return colon if ":" in name and len(colon) < len(pipe) else pipe
    out = f"{short(skin_name)}_{short(inf)}"
    if out in taken:
        out += f"_{count}"
    if len(out) > 100:
        out = f"{base}_{count}"
    return out


def map_paths(filepath):
    """(<dir>/<name>.weightMap, <dir>/<name>): Maya's export paths (name = text before the first '.')."""
    folder, fn = os.path.split(filepath)
    base = fn.split(".")[0] or "skinMap"
    return os.path.join(folder, base + ".weightMap"), os.path.join(folder, base), base


def _uv_raster(mesh, width, height):
    """(face triangle index per pixel (-1 = none), barycentrics (H, W, 3), triangle vertex indices (T, 3)) of the
    mesh's active UV map; pixel (i, j) centre = ((i + .5) / W, (j + .5) / H), row 0 at v = 0 (Blender's order)."""
    import numpy as np
    me = mesh.data
    uv = me.uv_layers.active
    me.calc_loop_triangles()
    tris = me.loop_triangles
    nt = len(tris)
    loops = np.empty(nt * 3, dtype=np.int64)
    tris.foreach_get("loops", loops)
    verts = np.empty(nt * 3, dtype=np.int64)
    tris.foreach_get("vertices", verts)
    uvs = np.empty(len(me.loops) * 2)
    uv.data.foreach_get("uv", uvs)
    tuv = uvs.reshape(-1, 2)[loops].reshape(nt, 3, 2) * (width, height) - 0.5    # in pixel-centre coordinates
    tri_of = np.full((height, width), -1, dtype=np.int64)
    bary = np.zeros((height, width, 3))
    for t in range(nt):
        a, b, c = tuv[t]
        lo = np.floor(np.minimum(np.minimum(a, b), c)).astype(int)
        hi = np.ceil(np.maximum(np.maximum(a, b), c)).astype(int)
        x0, y0 = max(lo[0], 0), max(lo[1], 0)
        x1, y1 = min(hi[0], width - 1), min(hi[1], height - 1)
        if x1 < x0 or y1 < y0:
            continue
        det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(det) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        l1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / det
        l2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / det
        l3 = 1.0 - l1 - l2
        inside = (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
        yy, xx = ys[inside], xs[inside]
        tri_of[yy, xx] = t
        bary[yy, xx] = np.stack([l1[inside], l2[inside], l3[inside]], axis=1)
    return tri_of, bary, verts.reshape(nt, 3)


def _vertex_weights(mesh, name):
    import numpy as np
    vg = mesh.vertex_groups[name]
    w = np.zeros(len(mesh.data.vertices))
    for v in mesh.data.vertices:
        for g in v.groups:
            if g.group == vg.index:
                w[v.index] = g.weight
    return w


def export_weight_maps(meshes, filepath, width=512, height=512, file_format="PNG"):
    """Write the .weightMap file and one image per weighted influence; returns (map file, image paths)."""
    import numpy as np
    map_file, folder, base = map_paths(filepath)
    ext = MAP_EXT[file_format]
    rows, taken = [], []
    for mesh in meshes:
        if mesh.data.uv_layers.active is None:
            raise ValueError(f"{mesh.name} has no UVs: weight maps are drawn in UV space")
        for inf in influence_names(mesh):
            if not _vertex_weights(mesh, inf).any():          # weighted influences only
                continue
            name = map_file_name(taken, base, mesh.name, inf, len(taken))
            taken.append(name)
            rows.append((mesh, inf, f"{name}.{ext}"))
    with open(map_file, "w", encoding="utf-8") as f:
        f.write(MAP_HEADER)
        for mesh, inf, img in rows:
            f.write(f"{mesh.name}\t{inf}\t{img}\n")
    os.makedirs(folder, exist_ok=True)
    paths = []
    raster = {}
    for mesh, inf, img in rows:
        if mesh.name not in raster:
            raster[mesh.name] = _uv_raster(mesh, width, height)
        tri_of, bary, tv = raster[mesh.name]
        w = _vertex_weights(mesh, inf)
        val = np.where(tri_of >= 0, (bary * w[tv[np.maximum(tri_of, 0)]]).sum(axis=2), 0.0)
        val = np.clip(val, 0.0, 1.0)
        px = np.empty((height, width, 4), dtype=np.float32)
        px[..., 0] = px[..., 1] = px[..., 2] = val
        px[..., 3] = 1.0
        image = bpy.data.images.new(".allset_weight_map", width, height, alpha=False)
        try:
            image.pixels.foreach_set(px.ravel())
            path = os.path.join(folder, img)
            image.filepath_raw = path
            image.file_format = file_format
            image.save()
            paths.append(path)
        finally:
            bpy.data.images.remove(image)
    return map_file, paths


def _sample(px, uv):
    """Bilinear sample (pixel centres, clamped edges) of grey ``px`` (H, W) at ``uv`` (N, 2)."""
    import numpy as np
    h, w = px.shape
    x = np.clip(uv[:, 0] * w - 0.5, 0, w - 1)
    y = np.clip(uv[:, 1] * h - 0.5, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = x - x0, y - y0
    return (px[y0, x0] * (1 - fx) * (1 - fy) + px[y0, x1] * fx * (1 - fy) + px[y1, x0] * (1 - fx) * fy
            + px[y1, x1] * fx * fy)


def _vertex_uvs(mesh):
    """Each vertex's UV (its first face corner, Maya's artisan samples one UV per vertex)."""
    import numpy as np
    me = mesh.data
    uvs = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uvs)
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    out = np.zeros((len(me.vertices), 2))
    seen = np.zeros(len(me.vertices), dtype=bool)
    for li in range(len(lv) - 1, -1, -1):          # reversed: the first corner wins
        out[lv[li]] = uvs[2 * li:2 * li + 2]
        seen[lv[li]] = True
    return out, seen


def import_weight_maps(filepath):
    """Read a .weightMap file (+ its image folder) into the skins it names; returns the (skin, influence) pairs set."""
    import numpy as np
    map_file, folder, _base = map_paths(filepath)
    if not os.path.isfile(map_file):
        map_file = filepath
    lines = []
    with open(map_file, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 3:                     # Maya's map file rows (comment lines have other counts)
                lines.append(parts)
    skins = []
    for skin_name, _inf, _img in lines:
        ob = bpy.data.objects.get(skin_name)
        if ob is not None and ob.type == 'MESH' and _skin_armature(ob) is not None and ob not in skins:
            skins.append(ob)
    for ob in skins:                                # Maya pruneWeights 1.1: every weight goes
        io = _Weights(ob)
        groups = {vg.name: vg.index for vg in ob.vertex_groups}
        for n in influence_names(ob):
            gi = groups[n]
            for v in io.bm.verts:
                if gi in v[io.layer]:
                    v[io.layer][gi] = 0.0
        io.flush()
    done = []
    for skin_name, inf, img in lines:
        ob = bpy.data.objects.get(skin_name)
        path = os.path.join(folder, img)
        if ob not in skins or not os.path.isfile(path) or inf not in influence_names(ob):
            continue
        if ob.data.uv_layers.active is None:
            continue
        image = bpy.data.images.load(path, check_existing=False)
        try:
            w, h = image.size
            raw = np.empty(w * h * 4, dtype=np.float32)
            image.pixels.foreach_get(raw)
        finally:
            bpy.data.images.remove(image)
        px = raw.reshape(h, w, 4)
        grey = px[..., 0] * 0.299 + px[..., 1] * 0.587 + px[..., 2] * 0.114
        uv, seen = _vertex_uvs(ob)
        vals = np.where(seen, _sample(grey, uv), 0.0)
        vg = ob.vertex_groups[inf]
        for vi, value in enumerate(vals):
            vg.add([vi], float(value), 'REPLACE')
        done.append((ob.name, inf))
    for ob in skins:                                # normalizeWeights back + skinPercent -normalize true
        names = influence_names(ob)
        idx = {ob.vertex_groups[n].index for n in names}
        for v in ob.data.vertices:
            gs = [g for g in v.groups if g.group in idx]
            total = sum(g.weight for g in gs)
            if total > 0.0:
                for g in gs:
                    g.weight = g.weight / total
        ob.data.update()
    return done


class ALLSET_OT_export_weight_maps(bpy.types.Operator):
    """Maya Skin > Export Weight Maps...: one grey image per joint in UV space and a .weightMap file listing them"""
    bl_idname = "allset.export_weight_maps"
    bl_label = "Export Weight Maps"
    bl_options = {'REGISTER'}

    filepath: StringProperty(subtype='FILE_PATH', default="", options={'SKIP_SAVE'})
    filter_glob: StringProperty(default="*.weightMap", options={'HIDDEN'})
    size_x: IntProperty(name="Map size X", default=512, min=1, max=8192)
    size_y: IntProperty(name="Map size Y", default=512, min=1, max=8192)
    file_format: EnumProperty(name="Image format", items=[(k, l, f".{e}") for k, l, e in MAP_FORMATS], default="PNG")

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = "skinMap.weightMap"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        meshes = skinned_meshes(context)
        if not meshes:
            self.report({'ERROR'}, "Select skinned objects to export their weight maps")      # Maya's error text
            return {'CANCELLED'}
        if not self.filepath:
            self.report({'ERROR'}, "No file name")
            return {'CANCELLED'}
        try:
            map_file, paths = export_weight_maps(meshes, bpy.path.abspath(self.filepath), self.size_x, self.size_y,
                                                 self.file_format)
        except (ValueError, OSError) as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        results.result(self, f"Exported {len(paths)} weight maps: {map_file}")
        return {'FINISHED'}


class ALLSET_OT_import_weight_maps(bpy.types.Operator):
    """Maya Skin > Import Weights Maps...: set the skins' weights from a .weightMap file and its images"""
    bl_idname = "allset.import_weight_maps"
    bl_label = "Import Weight Maps"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(subtype='FILE_PATH', default="", options={'SKIP_SAVE'})
    filter_glob: StringProperty(default="*.weightMap", options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not self.filepath or not os.path.isfile(bpy.path.abspath(self.filepath)):
            self.report({'ERROR'}, f"Unable to open file {self.filepath}")         # Maya's error text
            return {'CANCELLED'}
        if context.active_object is not None and context.active_object.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            done = import_weight_maps(bpy.path.abspath(self.filepath))
        except (ValueError, OSError) as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        if not done:
            self.report({'WARNING'}, "No skinned object or influence of the file was found")
            return {'CANCELLED'}
        results.result(self, f"Imported {len(done)} weight maps")
        return {'FINISHED'}


# --- Substitute Geometry -------------------------------------------------------------------------------------------
NO_DEFORMERS = "No deformers found attached to the geometry."      # substituteGeometry's warning


def _quad_weights(p, q):
    """Bilinear weights of the point of quad ``q`` (4 corners, in order) closest to ``p`` (Newton, clamped)."""
    s = t = 0.5
    for _ in range(30):
        pt = (1 - s) * (1 - t) * q[0] + s * (1 - t) * q[1] + s * t * q[2] + (1 - s) * t * q[3]
        ps = (1 - t) * (q[1] - q[0]) + t * (q[2] - q[3])
        pq = (1 - s) * (q[3] - q[0]) + s * (q[2] - q[1])
        r = p - pt
        a, b, c = ps.dot(ps), ps.dot(pq), pq.dot(pq)
        det = a * c - b * b
        if abs(det) < 1e-18:
            break
        e, f = ps.dot(r), pq.dot(r)
        ds, dt = (c * e - b * f) / det, (a * f - b * e) / det
        s2, t2 = min(1.0, max(0.0, s + ds)), min(1.0, max(0.0, t + dt))
        if abs(s2 - s) < 1e-13 and abs(t2 - t) < 1e-13:
            s, t = s2, t2
            break
        s, t = s2, t2
    return ((1 - s) * (1 - t), s * (1 - t), s * t, (1 - s) * t)


def _tri_weights(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
    d20, d21 = v2.dot(v0), v2.dot(v1)
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-18:
        return (1.0, 0.0, 0.0)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    return (1.0 - v - w, v, w)


def face_weights(p, corners):
    """Interpolation weights of the face corners at its point ``p`` (on or near the face)."""
    if len(corners) == 3:
        return _tri_weights(p, *corners)
    if len(corners) == 4:
        return _quad_weights(p, corners)
    from mathutils.interpolate import poly_3d_calc
    return tuple(poly_3d_calc(corners, p))       # n-gons: Blender's polygon weights


def substitute_weights(old_co, old_faces, old_w, new_co, tolerance):
    """New vertices' weights (list of rows) from the old surface: closest point within ``tolerance`` = interpolated
    weights there, else the nearest old vertex's weights (tolerance <= 0: always the nearest vertex)."""
    old_co = [Vector(c) for c in old_co]
    kd = kdtree.KDTree(len(old_co))
    for i, c in enumerate(old_co):
        kd.insert(c, i)
    kd.balance()
    bvh = BVHTree.FromPolygons(old_co, old_faces) if old_faces else None
    out = []
    for p in new_co:
        p = Vector(p)
        hit = bvh.find_nearest(p) if bvh is not None and tolerance > 0 else (None, None, None, None)
        if hit[0] is None or hit[3] > tolerance:
            out.append(list(old_w[kd.find(p)[1]]))
            continue
        face = old_faces[hit[2]]
        cw = face_weights(hit[0], [old_co[i] for i in face])
        out.append([sum(c * old_w[i][g] for c, i in zip(cw, face)) for g in range(len(old_w[0]))])
    return out


def _all_group_weights(mesh):
    names = [vg.name for vg in mesh.vertex_groups]
    rows = [[0.0] * len(names) for _ in mesh.data.vertices]
    for v in mesh.data.vertices:
        for g in v.groups:
            rows[v.index][g.group] = g.weight
    return names, rows


def substitute_geometry(context, old, new, tolerance, retain_old=False, disable_non_skin=False):
    """Maya substituteGeometry: ``old`` keeps name, transform, skin and vertex group names, takes ``new``'s points
    (object space) and faces with reweighted weights; ``new`` is removed. Returns the retained copy (or None)."""
    arm_md = skin.armature_modifier(old)
    if arm_md is None:
        raise ValueError(NO_DEFORMERS)
    old_me = old.data
    names, old_w = _all_group_weights(old)
    old_co = [v.co.copy() for v in old_me.vertices]
    old_faces = [list(p.vertices) for p in old_me.polygons]
    new_me = new.data.copy()
    new_w = substitute_weights(old_co, old_faces, old_w, [v.co for v in new_me.vertices], tolerance)
    kept = None
    if retain_old:                              # Maya: a copy of the old skinned geometry on a copy of the skeleton
        arm = arm_md.object
        arm2 = arm.copy()
        arm2.data = arm.data.copy()
        kept = old.copy()
        kept.data = old_me
        for coll in old.users_collection:
            coll.objects.link(kept)
        for coll in arm.users_collection:
            coll.objects.link(arm2)
        for md in kept.modifiers:
            if md.type == 'ARMATURE' and md.object == arm:
                md.object = arm2
    shape_name = old_me.name
    old.data = new_me
    if old_me.users == 0:
        bpy.data.meshes.remove(old_me)
    new_me.name = shape_name
    old.vertex_groups.clear()                   # group names live on the mesh: the skin's groups, in their order
    groups = old.vertex_groups
    for name in names:
        groups.new(name=name)
    for vi, row in enumerate(new_w):
        for gi, w in enumerate(row):
            if w > 0.0:
                groups[names[gi]].add([vi], w, 'REPLACE')
    if disable_non_skin:
        for md in old.modifiers:
            if md.type != 'ARMATURE' and not is_part(md):
                md.show_viewport = md.show_render = False
    new_data = new.data
    bpy.data.objects.remove(new)
    if new_data is not None and new_data.users == 0:
        bpy.data.meshes.remove(new_data)
    return kept


class ALLSET_OT_substitute_geometry(bpy.types.Operator):
    """Maya Skin > Substitute Geometry: the selected skinned mesh takes the other selected mesh's geometry and keeps
    its skin (weights carried over by closest point)"""
    bl_idname = "allset.substitute_geometry"
    bl_label = "Substitute Geometry"
    bl_options = {'REGISTER', 'UNDO'}

    reweight_distance: FloatProperty(name="Reweighting distance", description="Maya units: new points farther "
                                     "from the old surface take the nearest old vertex's weights", default=1.0,
                                     min=0.0, soft_max=10.0, max=10000.0)
    retain_old: BoolProperty(name="Retain old geometry", default=False)
    disable_non_skin: BoolProperty(name="Disable non-skin deformers", default=False)

    def execute(self, context):
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        skinned = [o for o in meshes if skin.armature_modifier(o) is not None]
        if len(meshes) != 2 or not skinned:
            self.report({'WARNING'}, "Select the skinned mesh and the new mesh")
            return {'CANCELLED'}
        act = context.active_object
        if len(skinned) == 2:                   # both skinned: the active one is the new geometry
            old = next(o for o in meshes if o is not act) if act in meshes else skinned[0]
        else:
            old = skinned[0]
        new = next(o for o in meshes if o is not old)
        if context.active_object is not None and context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            substitute_geometry(context, old, new, self.reweight_distance * units.maya_unit(context.scene),
                                self.retain_old, self.disable_non_skin)
        except ValueError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        old.select_set(True)
        context.view_layer.objects.active = old
        results.result(self, old.name)
        return {'FINISHED'}


# --- Bake Deformation to Skin Weights ------------------------------------------------------------------------------
BAKE_ANGLE = 45.0          # degrees: each joint +-45 about its X / Y / Z axes (see the module doc)


def simplex_lsq(Q, c, tol=1e-12):
    """argmin_w 1/2 w'Qw - c'w subject to w >= 0, sum(w) = 1 (primal active set, Nocedal-Wright 16.3)."""
    import numpy as np
    n = len(c)
    # start at the best single influence (feasible vertex of the simplex)
    obj = 0.5 * np.diag(Q) - c
    free = [int(np.argmin(obj))]
    w = np.zeros(n)
    w[free[0]] = 1.0
    for _ in range(4 * n + 20):
        k = len(free)
        K = np.zeros((k + 1, k + 1))
        K[:k, :k] = Q[np.ix_(free, free)]
        K[:k, k] = 1.0
        K[k, :k] = 1.0
        sol = np.linalg.lstsq(K, np.append(c[free], 1.0), rcond=None)[0]
        target = np.zeros(n)
        target[free] = sol[:k]
        p = target - w
        if np.abs(p).max() > tol:
            neg = [i for i in free if p[i] < -tol]
            alpha = 1.0
            block = None
            for i in neg:
                a = -w[i] / p[i]
                if a < alpha:
                    alpha, block = a, i
            w = w + alpha * p
            if block is not None:
                w[block] = 0.0
                free.remove(block)
            continue
        g = Q @ w - c
        nu = -g[free].mean()
        mu = g + nu
        out = [i for i in range(n) if i not in free]
        if not out:
            break
        j = min(out, key=lambda i: mu[i])
        if mu[j] >= -1e-10 * (1.0 + abs(nu)):
            break
        free.append(j)
    w = np.clip(w, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else w


def _pose_bones_matching(src_arm, dst_arm, dst_names):
    """[(name, src pose bone, dst pose bone)] for the destination influences the source skeleton also has."""
    out = []
    for name in dst_names:
        sp = src_arm.pose.bones.get(name)
        dp = dst_arm.pose.bones.get(name)
        if sp is not None and dp is not None:
            out.append((name, sp, dp))
    return out


def _deformed_world(ob, depsgraph):
    import numpy as np
    ev = ob.evaluated_get(depsgraph)
    me = ev.to_mesh()
    try:
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
    finally:
        ev.to_mesh_clear()
    mw = np.array(ev.matrix_world)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


def _skin_matrices(arm, bones):
    import numpy as np
    mw = arm.matrix_world
    return np.array([np.array(mw @ pb.matrix @ (mw @ pb.bone.matrix_local).inverted()) for _n, _s, pb in bones])


def bake_weights(context, src, dst, max_influences=3, angle=BAKE_ANGLE):
    """Fit ``dst``'s skin weights to ``src``'s deformation (see the module doc); returns (names, weights (V, J))."""
    import numpy as np
    src_arm, dst_arm = _skin_armature(src), _skin_armature(dst)
    bones = _pose_bones_matching(src_arm, dst_arm, influence_names(dst) or [
        b.name for b in dst_arm.data.bones if b.use_deform])
    if not bones:
        raise ValueError("The source and destination skeletons share no joint")
    saved = {pb: pb.matrix_basis.copy() for arm in {src_arm, dst_arm} for pb in arm.pose.bones}
    previews = [m for m in src.modifiers if m.show_viewport and m.type in {'SUBSURF', 'MULTIRES'}
                and m.name.startswith("Maya Smooth")]
    for m in previews:
        m.show_viewport = False
    try:
        for pb in saved:
            pb.matrix_basis = Matrix.Identity(4)
        context.view_layer.update()
        dg = context.evaluated_depsgraph_get()
        rest = _deformed_world(src, dg)
        if len(rest) != len(dst.data.vertices):
            raise ValueError("The source and destination meshes need the same vertex count")
        samples, mats = [], []
        a = math.radians(angle)
        for name, sp, dp in bones:
            for axis in "XYZ":
                for sign in (1.0, -1.0):
                    rot = Matrix.Rotation(sign * a, 4, axis)
                    sp.matrix_basis = rot
                    dp.matrix_basis = rot
                    context.view_layer.update()
                    samples.append(_deformed_world(src, context.evaluated_depsgraph_get()))
                    mats.append(_skin_matrices(dst_arm, bones))
                    sp.matrix_basis = Matrix.Identity(4)
                    dp.matrix_basis = Matrix.Identity(4)
    finally:
        for pb, m in saved.items():
            pb.matrix_basis = m
        for m in previews:
            m.show_viewport = True
        context.view_layer.update()
    S = np.stack(samples)                         # (F, V, 3)
    M = np.stack(mats)                            # (F, J, 4, 4)
    ph = np.concatenate([rest, np.ones((len(rest), 1))], axis=1)
    nj = len(bones)
    W = np.zeros((len(rest), nj))
    for v in range(len(rest)):
        X = np.einsum('fjab,b->fja', M, ph[v])[..., :3]          # (F, J, 3): each joint's motion of the rest point
        A = X.transpose(0, 2, 1).reshape(-1, nj)                   # rows (frame, xyz), columns joints
        b = S[:, v, :].reshape(-1)
        W[v] = simplex_lsq(A.T @ A, A.T @ b)
        if 0 < max_influences < np.count_nonzero(W[v] > 0):
            keep = np.argsort(-W[v])[:max_influences]
            sub = simplex_lsq((A.T @ A)[np.ix_(keep, keep)], (A.T @ b)[keep])
            W[v] = 0.0
            W[v, keep] = sub
    return [n for n, _s, _d in bones], W


def apply_weights(mesh, names, W):
    import numpy as np
    every = list(range(len(mesh.data.vertices)))
    for j, name in enumerate(names):
        vg = mesh.vertex_groups.get(name) or mesh.vertex_groups.new(name=name)
        vg.remove(every)
        col = W[:, j]
        for value in np.unique(col):
            if value > 0.0:
                vg.add(np.flatnonzero(col == value).tolist(), float(value), 'REPLACE')


class ALLSET_OT_bake_deformation(bpy.types.Operator):
    """Maya Skin > Bake Deformation to Skin Weights...: fit the destination skin's weights to the source mesh's whole
    deformation (skin + deformers) over each joint's range of motion (select the source, then the destination)"""
    bl_idname = "allset.bake_deformation"
    bl_label = "Bake Deformation to Skin Weights"
    bl_options = {'REGISTER', 'UNDO'}

    max_influences: IntProperty(name="Max influences", default=3, min=1, max=50)    # default like Maya

    def execute(self, context):
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        act = context.active_object
        if len(meshes) != 2 or act not in meshes:
            self.report({'WARNING'}, "Select the source mesh, then the destination mesh")
            return {'CANCELLED'}
        dst = act
        src = next(o for o in meshes if o is not dst)
        if _skin_armature(src) is None:
            self.report({'WARNING'}, f"{src.name} has no skin: bind the source mesh to its skeleton first")
            return {'CANCELLED'}
        if context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        if _skin_armature(dst) is None:          # the destination gets the source skeleton (Maya needs a skin there)
            skin.bind_skin(context, _skin_armature(src), [dst], max_influences=self.max_influences)
        try:
            names, W = bake_weights(context, src, dst, self.max_influences)
        except ValueError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        apply_weights(dst, names, W)
        dst.data.update()
        results.result(self, f"Baked {src.name}'s deformation into {dst.name}'s skin weights")
        return {'FINISHED'}


classes = (ALLSET_OT_move_skin_weights, ALLSET_OT_skin_normalize_mode, ALLSET_OT_export_weight_maps,
           ALLSET_OT_import_weight_maps, ALLSET_OT_substitute_geometry, ALLSET_OT_bake_deformation)


def register_handlers():
    if _sync_sum_modifiers not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_sync_sum_modifiers)


def unregister_handlers():
    while _sync_sum_modifiers in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_sync_sum_modifiers)
