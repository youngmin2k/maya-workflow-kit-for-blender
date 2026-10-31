# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya File > Import / Export All / Export Selection: one file dialog with Files of type and an Options panel
.

Maya opens a single dialog for every format and picks the translator from "Files of type" (or the extension,
"Best Guess" on import); Blender has one operator per format. ``allset.file_dialog`` is that single dialog: the
Blender file browser with this operator's options in its side panel (Maya's Options pane), Files of type at the top
of it, and the Maya presets — a Maya scene is in cm with Y up, so exchange formats get Maya's scale and axes
(``import_args`` / ``export_args``, pure functions the headless tests check) — then runs the format's own operator.
"""

import math
import os
import re

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from mathutils import Matrix

from .. import results
from .. import compat
from . import project, units

# (id, Files of type label, extension written, file filter)
FORMATS = (
    ('BLEND', "Maya Scenes (.blend)", ".blend", "*.blend"),
    ('FBX', "FBX (.fbx)", ".fbx", "*.fbx"),
    ('OBJ', "OBJ (.obj)", ".obj", "*.obj"),
    ('ABC', "Alembic (.abc)", ".abc", "*.abc"),
    ('USD', "USD (.usd .usda .usdc .usdz)", ".usd", "*.usd;*.usda;*.usdc;*.usdz"),
    ('GLTF', "glTF 2.0 (.glb .gltf)", ".glb", "*.glb;*.gltf"),
)
_BY_ID = {f[0]: f for f in FORMATS}
_EXT = {ext: f[0] for f in FORMATS for ext in f[3].replace("*", "").split(";")}
ALL_GLOB = ";".join(f[3] for f in FORMATS)
IMPORT_TYPES = (('AUTO', "Best Guess (by extension)", "Pick the format from the file's extension (Maya Best Guess)"),
                *((f[0], f[1], "") for f in FORMATS))
EXPORT_TYPES = tuple((f[0], f[1], "") for f in FORMATS)
MODES = (('IMPORT', "Import", "Maya File > Import"), ('EXPORT_ALL', "Export All", "Maya File > Export All"),
         ('EXPORT_SELECTION', "Export Selection", "Maya File > Export Selection"))


# Maya workspace file rules: where the dialog starts per format; the
# others (scenes, FBX, USD, glTF, Best Guess) start in the scenes folder.
FILE_RULES = {'OBJ': "data", 'ABC': os.path.join("cache", "alembic")}


def start_folder(context, fmt):
    """The project folder the dialog opens in for ``fmt`` (made if missing, like Maya's workspace)."""
    root = project.ensure_root(context)
    folder = os.path.join(root, FILE_RULES.get(fmt, "scenes"))
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        folder = root
    return folder


def format_of(path):
    """Format id for a file name ("" if no format reads it)."""
    return _EXT.get(os.path.splitext(path)[1].lower(), "")


def import_args(fmt, k, maya=True):
    """(operator id, kwargs) that import ``fmt`` into a scene where one Maya unit = ``k`` BU (units.maya_unit).

    Maya writes centimetres with Y up: FBX carries its unit and axes and Blender's
    importer converts both itself; OBJ and Alembic have no unit, so their numbers are Maya units (× k) and Y up;
    USD carries metersPerUnit, which Blender converts to metres, so cm files need ×100 to become Maya units.
    Blender's readers leave that conversion on the objects' channels (Rotate X 90, Scale 0.01):
    ``after_import`` moves it into the geometry (FBX's own ``bake_space_transform`` does it there).
    Maya writes frame 1 at FBX time 1/24 s, which Blender already reads as frame 1 (no extra offset).
    OBJ: Maya names the object with ``g`` (no ``o`` line), so groups split the objects.
    """
    if fmt == 'FBX':
        return "import_scene.fbx", ({"bake_space_transform": True, "anim_offset": 0.0} if maya else {})
    if fmt == 'OBJ':
        return "wm.obj_import", ({"global_scale": k, "forward_axis": 'NEGATIVE_Z', "up_axis": 'Y',
                                  "use_split_groups": True} if maya else {})
    if fmt == 'ABC':
        return "wm.alembic_import", ({"scale": k} if maya else {})
    if fmt == 'USD':
        return "wm.usd_import", ({"scale": 100.0 * k, "apply_unit_conversion_scale": True} if maya else {})
    if fmt == 'GLTF':
        return "import_scene.gltf", {}
    raise ValueError(fmt)


def export_args(fmt, k, selection, maya=True):
    """(operator id, kwargs) that write ``fmt`` the way Maya reads it back: centimetres (one Maya unit per
    ``k`` BU), Y up; ``selection`` = only the selected objects (Export Selection).

    Maya must read the same channels the kit shows — no Rotate X -90 / Scale 100 from the axis / unit
    conversion. FBX bakes it into the geometry itself (``bake_space_transform``) and writes the timeline as one
    take (the NLA-strip default wrote no animation without strips); OBJ gets ``g`` lines and Alembic / USD are
    scaled / converted around Blender's writers (``write``, ``after_export``)."""
    if fmt == 'FBX':
        # Blender's FBX writer stores the scene unit (UnitScaleFactor) and Maya converts it to cm on import
        args = {"use_selection": selection}
        if maya:
            args.update(axis_forward='-Z', axis_up='Y', apply_unit_scale=True, global_scale=1.0,
                        apply_scale_options='FBX_SCALE_NONE', add_leaf_bones=False, bake_space_transform=True,
                        bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                        # Maya joints point X down the bone; Maya Y = the bone's
                        # Z, Maya Z = its X (joints.JOINT_AXES, what Orient Joint sets) — '-Y' put Maya Y on the
                        # bone's -X (jointOrient 90 deg off Maya's); Maya exports joints, not the kit's control bones; a key per frame like Maya's bake (also re-composable by fbx_rig)
                        primary_bone_axis='X', secondary_bone_axis='Z', use_armature_deform_only=True,
                        bake_anim_simplify_factor=0.0)
        return "export_scene.fbx", args
    if fmt == 'OBJ':
        args = {"export_selected_objects": selection}
        if maya:
            args.update(global_scale=1.0 / k, forward_axis='NEGATIVE_Z', up_axis='Y')
        return "wm.obj_export", args
    if fmt == 'ABC':
        args = {"selected": selection}
        if maya:
            # Blender's Alembic writer is always Y up; its global_scale lands on the root transforms, so
            # ``write`` scales the objects' geometry / offsets around it (_abc_maya_scale)
            args.update(global_scale=1.0 / k)
        return "wm.alembic_export", args
    if fmt == 'USD':
        args = {"selected_objects_only": selection}
        if maya:
            # one prim per transform + shape like mayaUsd, no "/root" prim, no world dome light ("env_light");
            # axes and units: ``usd_maya_axes`` after the write (Blender's own conversion lands on the prims)
            args.update(root_prim_path="", merge_parent_xform=True, convert_world_material=False)
        return "wm.usd_export", args
    if fmt == 'GLTF':
        return "export_scene.gltf", {"use_selection": selection, "export_yup": True}
    raise ValueError(fmt)


# --- the conversion goes into the geometry, not onto the channels ----------------------------
#
# Maya reads its transforms' channels straight from the file, so a Y-up / cm conversion written as a root
# rotation or scale shows as Rotate X -90 / Scale 100 in Maya and Blender's readers
# leave the reverse on the kit's channels. The kit instead conjugates: a transform M becomes C M C^-1 and
# geometry p becomes C p (C = axes x units), so channels read the same numbers in both programs (the kit's
# Z-up axes: Maya translate (1, 2, 3) = kit (1, -3, 2), rotate Y = kit rotate Z).

_SUFFIX = re.compile(r"^(.*)\.\d{3}$")
_TRAIL = re.compile(r"^(.*?)(\d*)$")
SCOPE_NAMES = ("Looks", "_materials", "materials", "mtl")      # USD material scopes (mayaUsd / Blender)
MAYA_MPU = 0.01        # Maya's internal unit is cm: kit USD files carry Maya-unit numbers with metersPerUnit 0.01


def shape_name(name):
    """Maya's shape name for transform ``name``: pCube1 -> pCubeShape1, box -> boxShape (same rule as
    ui/input_line.shape_name)."""
    m = _TRAIL.match(name)
    return f"{m.group(1)}Shape{m.group(2)}" if m.group(1) and m.group(2) else f"{name}Shape"


def maya_free_name(name, used):
    """Maya's name for an imported node whose name is taken: the trailing number goes up (pCube1 -> pCube2);
    ``name`` may carry Blender's ``.001`` clash suffix."""
    m = _SUFFIX.match(name)
    base = m.group(1) if m else name
    if base not in used:
        return base
    stem, num = _TRAIL.match(base).groups()
    n = int(num) + 1 if num else 1
    while f"{stem}{n}" in used:
        n += 1
    return f"{stem}{n}"


def _axis_matrix(up_y):
    """File axes -> kit axes: Y up becomes Z up (rotate X 90), as Blender's readers do."""
    return Matrix.Rotation(math.radians(90.0), 4, 'X') if up_y else Matrix.Identity(4)


def _parents_first(obs):
    obs = list(obs)
    rank = {}

    def depth(ob):
        if ob not in rank:
            rank[ob] = 0 if ob.parent is None else depth(ob.parent) + 1
        return rank[ob]
    return sorted(obs, key=depth)


def _bakeable(ob):
    """Objects whose data can take the conversion (others keep the reader's world matrix)."""
    if ob.type == 'EMPTY':
        return True
    if ob.type not in ('MESH', 'CURVE') or ob.data is None:
        return False
    if any(m.type in ('MESH_SEQUENCE_CACHE', 'ARMATURE') for m in ob.modifiers):
        return False
    return "transform" in ob.data.bl_rna.functions


def bake_conversion(context, obs, conv):
    """Move the reader's conversion ``conv`` (object world = true world @ conv) from the channels of the
    imported objects ``obs`` into their geometry. Transform Cache constraints (animated Alembic / USD) become
    keys on every frame of the scene range (the reader sets it to the file's), so the Channel Box shows Maya's
    numbers; cameras and lights only lose the unit scale (their local axes keep the reader's orientation)."""
    scene = context.scene
    obs = _parents_first(obs)
    if not obs:
        return
    scale = conv.to_scale()[0]
    unscale = Matrix.Scale(1.0 / scale, 4)
    conv_inv = conv.inverted_safe()
    users = {}
    for ob in obs:
        if ob.data is not None:
            users.setdefault(ob.data, []).append(ob)
    bake = {ob for ob in obs if _bakeable(ob)}
    for data, owners in users.items():          # data shared with an object that can't bake: leave all
        if data.users != len(owners) or not all(o in bake for o in owners):
            bake.difference_update(owners)
    cached = [ob for ob in obs if any(c.type == 'TRANSFORM_CACHE' for c in ob.constraints)]
    animated = any(ob in bake or ob.type in ('CAMERA', 'LIGHT') for ob in cached)
    frames = list(range(scene.frame_start, scene.frame_end + 1)) if animated else [scene.frame_current]
    keep_frame = scene.frame_current
    worlds = {ob: [] for ob in obs}
    for f in frames:
        if len(frames) > 1:
            scene.frame_set(f)
        for ob in obs:
            worlds[ob].append(ob.matrix_world.copy())
    if len(frames) > 1:
        scene.frame_set(keep_frame)
    target = {}
    for ob in obs:
        if ob in bake:
            target[ob] = [w @ conv_inv for w in worlds[ob]]
        elif ob.type in ('CAMERA', 'LIGHT'):
            target[ob] = [w @ unscale for w in worlds[ob]]
    caches = set()
    for ob in target:
        for con in [c for c in ob.constraints if c.type == 'TRANSFORM_CACHE']:
            caches.add(con.cache_file)
            ob.constraints.remove(con)
    for cache in caches:
        if cache is not None and cache.users == 0:
            bpy.data.batch_remove([cache])       # (CacheFile has no remove())
    for data in {ob.data for ob in bake if ob.data is not None}:
        if isinstance(data, bpy.types.Mesh):
            data.transform(conv, shape_keys=True)
        else:
            data.transform(conv)
    for ob in bake:
        if ob.type == 'EMPTY':
            ob.empty_display_size *= scale
    for ob in obs:
        if ob not in target:
            continue
        par = ob.parent
        locals_ = []
        for i, w in enumerate(target[ob]):
            pw = target[par][i] if par in target else (worlds[par][i] if par in worlds else
                                                         (par.matrix_world if par else Matrix.Identity(4)))
            locals_.append(pw.inverted_safe() @ w)
        ob.matrix_parent_inverse = Matrix.Identity(4)
        static = all(_close(m, locals_[0]) for m in locals_[1:])
        if static:
            ob.matrix_basis = locals_[0]
            continue
        _key_matrices(ob, frames, locals_)


def _close(a, b, eps=1e-6):
    return all(abs(a[i][j] - b[i][j]) < eps for i in range(4) for j in range(4))


def _key_matrices(ob, frames, mats):
    """Keys on location / rotation / scale at ``frames`` holding the local matrices ``mats``."""
    rot_path = {'QUATERNION': "rotation_quaternion", 'AXIS_ANGLE': "rotation_axis_angle"}.get(
        ob.rotation_mode, "rotation_euler")
    prev = None
    for f, m in zip(frames, mats):
        loc, quat, scl = m.decompose()
        ob.location, ob.scale = loc, scl
        if rot_path == "rotation_euler":
            eul = quat.to_euler(ob.rotation_mode, prev) if prev is not None else quat.to_euler(ob.rotation_mode)
            ob.rotation_euler = prev = eul
        elif rot_path == "rotation_quaternion":
            ob.rotation_quaternion = quat
        else:
            axis, angle = quat.to_axis_angle()
            ob.rotation_axis_angle = (angle, *axis)
        for path in ("location", rot_path, "scale"):
            ob.keyframe_insert(path, frame=f)


def maya_names(obs, materials, path):
    """Maya's names for what an import made: clashes count up (pCube1.001 -> pCube2, lambert1.001 ->
    lambert2), shapes are <transform>Shape (Maya FBX / OBJ / USD files name meshes "Mesh", after the file
    or after the transform)."""
    stem = os.path.splitext(os.path.basename(path))[0]
    used = {o.name for o in bpy.data.objects}
    for ob in obs:
        if _SUFFIX.match(ob.name):
            used.discard(ob.name)
            ob.name = maya_free_name(ob.name, used)
            used.add(ob.name)
    used_data = {d.name for coll in (bpy.data.meshes, bpy.data.curves) for d in coll}
    for ob in obs:
        data = ob.data
        if ob.type not in ('MESH', 'CURVE', 'SURFACE') or data is None or data.users != 1:
            continue
        base = _SUFFIX.match(data.name).group(1) if _SUFFIX.match(data.name) else data.name
        if base in (ob.name, "Mesh", stem, "") or _SUFFIX.match(data.name):
            want = shape_name(ob.name) if base in (ob.name, "Mesh", stem, "") else base
            used_data.discard(data.name)
            data.name = want if want not in used_data else maya_free_name(want, used_data)
            used_data.add(data.name)
    used_mats = {m.name for m in bpy.data.materials}
    for mat in materials:
        if _SUFFIX.match(mat.name):
            used_mats.discard(mat.name)
            mat.name = maya_free_name(mat.name, used_mats)
            used_mats.add(mat.name)


def _usd_stage_info(path):
    """(up axis is Y, metersPerUnit, Scope prim names) of a USD file; None without pxr."""
    try:
        from pxr import Usd, UsdGeom
    except ImportError:
        return None
    stage = Usd.Stage.Open(path)
    if stage is None:
        return None
    scopes = {p.GetName() for p in stage.Traverse() if p.GetTypeName() == "Scope"}
    return UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.y, UsdGeom.GetStageMetersPerUnit(stage), scopes


def after_import(context, fmt, path, obs, materials, args):
    """Maya channels and names on what a Maya-preset import made (``obs`` = the new objects)."""
    if fmt == 'OBJ':
        # OBJ has no transforms: the reader's whole matrix is the conversion
        for ob in obs:
            if ob.parent is None and _bakeable(ob):
                bake_conversion(context, [ob], ob.matrix_world.copy())
    elif fmt == 'ABC':
        # Blender's Alembic reader turns Y up into Z up itself; only the scale stays on the channels
        bake_conversion(context, obs, Matrix.Scale(args.get("scale", 1.0), 4))
    elif fmt == 'USD':
        info = _usd_stage_info(path)
        if info is not None:
            up_y, mpu, scopes = info
            c = args.get("scale", 1.0) * (mpu if args.get("apply_unit_conversion_scale", True) else 1.0)
            for ob in [o for o in obs if o.type == 'EMPTY' and o.name.split(".")[0] in scopes | set(SCOPE_NAMES)
                       and not o.children]:
                obs.remove(ob)
                bpy.data.objects.remove(ob)
            bake_conversion(context, obs, _axis_matrix(up_y) @ Matrix.Scale(c, 4))
    elif fmt == 'FBX':
        # rigs: Maya's curves / Euler rotations / skeleton without the conversion node (L12)
        # (a rig file is read without bake_space_transform, see execute: the reader would shrink skinned meshes)
        from . import fbx_rig_import, joints, naming
        done, conv = set(), None
        for arm in [o for o in obs if o.type == 'ARMATURE']:
            res = fbx_rig_import.fix_armature(context, arm, path)
            if res is None or "conversion" not in res:
                continue
            done.add(arm)
            done.update(res["meshes"])
            conv = res["conversion"]
            if arm.name.startswith("Armature"):
                naming.apply_maya_name(arm, joints.SKELETON_BASE, rename_data=False)
        if conv is not None and not args.get("bake_space_transform", False):
            rest = [o for o in obs if o not in done and o.parent not in done]
            if rest:
                bake_conversion(context, rest, conv)
        if not done:
            _file_time_slider(context, path, obs)
        for ob in obs:
            normalise_skin_weights(ob)
    maya_names(obs, materials, path)


def normalise_skin_weights(ob, eps=1e-6):
    """#189: Maya's FBX export leaves out skin weights of 0.001 or less without scaling the rest, and
    Maya's FBX import renormalises each vertex's weights to sum 1 (its skin cluster normalises). Blender's reader
    keeps the file values, so the Component Editor / Paint Skin Weights / a later export showed up to 0.0016 less.
    Divide every vertex's joint weights (groups named after a bone of the mesh's Armature modifiers) by their sum;
    other vertex groups stay. Positions don't change: the Armature modifier divides by the sum while it deforms.
    Returns the number of vertices changed."""
    if ob is None or ob.type != 'MESH':
        return 0
    bones = set()
    for md in ob.modifiers:
        if md.type == 'ARMATURE' and md.object is not None and md.object.type == 'ARMATURE':
            bones.update(b.name for b in md.object.data.bones)
    joints = {vg.index for vg in ob.vertex_groups if vg.name in bones}
    if not joints:
        return 0
    changed = 0
    for v in ob.data.vertices:
        els = [g for g in v.groups if g.group in joints]
        s = sum(g.weight for g in els)
        if s > 0.0 and abs(s - 1.0) > eps:
            for g in els:
                g.weight = g.weight / s
            changed += 1
    if changed:
        ob.data.update()
    return changed


def _file_time_slider(context, path, obs):
    """#146: an animated FBX without a skeleton sets the Time Slider to the file's range too —
    Maya's FBXImport does even with Fill Timeline off; Blender's reader
    leaves the scene's range (0-250). Rigs get it in fbx_rig_import.fix_armature."""
    if not any(o.animation_data is not None and o.animation_data.action is not None for o in obs):
        return None
    from . import fbx_rig, fbx_rig_import
    if fbx_rig.modules() is None:
        return None
    scene = context.scene
    tree, _v = fbx_rig.load(path)
    span = fbx_rig_import.time_span(tree, fbx_rig_import.file_fps(tree, scene))
    if span is None:
        return None
    scene.frame_start, scene.frame_end = span
    if scene.use_preview_range:
        scene.frame_preview_start, scene.frame_preview_end = span
    scene.frame_set(max(span[0], min(scene.frame_current, span[1])))
    return span


def _write_obj_groups(path):
    """Maya's OBJ reader names objects after ``g`` lines and ignores ``o``: add ``g <name>`` after every
    ``o <name>`` Blender writes (otherwise a cube comes in as "Mesh")."""
    with open(path, encoding="utf-8", errors="surrogateescape") as fh:
        lines = fh.readlines()
    if any(line.startswith("g ") for line in lines):
        return
    out = []
    for line in lines:
        out.append(line)
        if line.startswith("o "):
            out.append("g " + line[2:])
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as fh:
        fh.writelines(out)


def _scale_group(s):
    """Geometry Nodes group that scales the geometry by ``s`` (temporary, Alembic export)."""
    ng = bpy.data.node_groups.new(".allset_export_scale", 'GeometryNodeTree')
    ng.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    gi, go = ng.nodes.new('NodeGroupInput'), ng.nodes.new('NodeGroupOutput')
    tr = ng.nodes.new('GeometryNodeTransform')
    tr.inputs["Scale"].default_value = (s, s, s)
    ng.links.new(gi.outputs[0], tr.inputs["Geometry"])
    ng.links.new(tr.outputs["Geometry"], go.inputs[0])
    return ng


def _abc_scalable(obs):
    for ob in obs:
        if ob.type not in ('MESH', 'EMPTY', 'CAMERA', 'LIGHT') or ob.constraints or ob.parent_type != 'OBJECT':
            return False
        if ob.library is not None:            # linked objects can't take the temporary changes
            return False
        ad = ob.animation_data
        if ad is not None and any(fc.data_path == "delta_scale" for fc in
                                  list(compat.id_fcurves(ob)) + list(ad.drivers)):
            return False                       # animated delta scale would undo the temporary one
        if any(m.type == 'ARMATURE' for m in ob.modifiers):
            return False
    return True


class _AbcMayaScale:
    """Blender's Alembic writer puts ``global_scale`` s on the root transforms (S M, Scale 100 in Maya). For
    the export only, every object gets delta scale 1/s and a last Geometry Nodes modifier scaling its mesh by
    s, and every parent inverse S PI: the world geometry is unchanged, the evaluated worlds are W S^-1, so the
    writer's roots become S W S^-1 and children (S PI) M S^-1 — Maya's numbers with Scale 1. Scenes it can't
    do exactly (armatures, constraints, curves ...) keep Blender's root scale."""

    def __init__(self, context, s):
        self.s = s
        self.obs = list(context.view_layer.objects)
        self.on = abs(s - 1.0) > 1e-9 and _abc_scalable(self.obs)
        self.saved, self.mods, self.group = [], [], None

    def __enter__(self):
        if not self.on:
            return self
        s = self.s
        self.group = _scale_group(s)
        smat = Matrix.Scale(s, 4)
        for ob in self.obs:
            self.saved.append((ob, ob.delta_scale.copy(), ob.matrix_parent_inverse.copy()))
            ob.delta_scale = ob.delta_scale / s
            if ob.parent is not None:
                ob.matrix_parent_inverse = smat @ ob.matrix_parent_inverse
            if ob.type == 'MESH':
                mod = ob.modifiers.new(".allset_export_scale", 'NODES')
                mod.node_group = self.group
                mod.show_in_editmode = False
                self.mods.append((ob, mod))
        return self

    def __exit__(self, *exc):
        for ob, mod in self.mods:
            ob.modifiers.remove(mod)
        for ob, ds, pi in self.saved:
            ob.delta_scale = ds
            ob.matrix_parent_inverse = pi
        if self.group is not None:
            bpy.data.node_groups.remove(self.group)
        return False


def usd_maya_axes(path, k):
    """Rewrite a Blender-written USD (Z up, BU) the Maya way: Y up, Maya units (metersPerUnit 0.01), every
    transform conjugated (C M C^-1, cameras / lights C M S^-1 so their view axis stays) and every point / normal
    converted. Returns False (file untouched) when pxr or the stage can't do it (skeletons, usdz)."""
    try:
        import numpy as np
        from pxr import Gf, Usd, UsdGeom, Vt
    except ImportError:
        return False
    if path.lower().endswith(".usdz"):
        return False
    stage = Usd.Stage.Open(path)
    if stage is None or any(p.GetTypeName().startswith("Skel") for p in stage.Traverse()):
        return False
    s = 1.0 / k
    axes = Matrix.Rotation(math.radians(-90.0), 4, 'X')
    conv = Matrix.Scale(s, 4) @ axes
    unscale = Matrix.Scale(s, 4)
    lin = np.array(conv.to_3x3(), dtype=np.float64)
    rot = np.array(axes.to_3x3(), dtype=np.float64)
    oriented = ("Camera", "DistantLight", "SphereLight", "RectLight", "DiskLight", "CylinderLight")

    def mat(gf):
        return Matrix([list(gf.GetRow(i)) for i in range(4)]).transposed()

    def samples(attr):
        times = attr.GetTimeSamples()
        return [(t, attr.Get(t)) for t in times] if times else [(Usd.TimeCode.Default(), attr.Get())]

    def convert_array(attr, m3):
        if not attr or not attr.HasAuthoredValue():
            return
        for t, val in samples(attr):
            if val is None or len(val) == 0:
                continue
            arr = np.array(val, dtype=np.float64) @ m3.T
            attr.Set(type(val).FromNumpy(arr.astype(np.float32)) if hasattr(type(val), "FromNumpy")
                     else Vt.Vec3fArray.FromNumpy(arr.astype(np.float32)), t)

    for prim in stage.Traverse():
        typ = prim.GetTypeName()
        if typ == "Xform" and prim.HasAttribute("faceVertexCounts"):
            # Blender 4.5 writes a merged transform + mesh as an Xform prim holding the mesh attributes (no
            # mesh in Maya or Blender): it is the mesh prim mayaUsd writes (Mesh "pCube1")
            prim.SetTypeName("Mesh")
            typ = "Mesh"
        if prim.IsA(UsdGeom.Xformable):
            xf = UsdGeom.Xformable(prim)
            ops = xf.GetOrderedXformOps()
            times = sorted({t for op in ops for t in op.GetAttr().GetTimeSamples()})
            codes = [Usd.TimeCode(t) for t in times] or [Usd.TimeCode.Default()]
            pre = unscale if prim.GetParent().GetTypeName() in oriented else conv
            post = unscale.inverted() if typ in oriented else conv.inverted()
            mats = [pre @ mat(xf.GetLocalTransformation(c)) @ post for c in codes]
            for op in ops:
                prim.RemoveProperty(op.GetName())
            xf.ClearXformOpOrder()
            t_op, r_op, s_op = xf.AddTranslateOp(), xf.AddRotateXYZOp(), xf.AddScaleOp()
            prev = None
            for c, m in zip(codes, mats):
                loc, quat, scl = m.decompose()
                eul = quat.to_euler('XYZ', prev) if prev is not None else quat.to_euler('XYZ')
                prev = eul
                t_op.Set(Gf.Vec3d(*loc), c)
                r_op.Set(Gf.Vec3f(*(math.degrees(a) for a in eul)), c)
                s_op.Set(Gf.Vec3f(*scl), c)
        if prim.IsA(UsdGeom.PointBased):
            pb = UsdGeom.PointBased(prim)
            convert_array(pb.GetPointsAttr(), lin)
            convert_array(pb.GetNormalsAttr(), rot)
            convert_array(pb.GetVelocitiesAttr(), lin)
            pv = UsdGeom.PrimvarsAPI(prim).GetPrimvar("normals")
            if pv:
                convert_array(pv.GetAttr(), rot)
            ext = pb.GetExtentAttr()
            if ext and ext.HasAuthoredValue():
                for t, pts in samples(pb.GetPointsAttr()):
                    if pts is not None and len(pts):
                        ext.Set(UsdGeom.PointBased.ComputeExtent(pts), t)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, MAYA_MPU)
    stage.GetRootLayer().Save()
    return True


def write(context, fmt, path, op, args, maya, k, deform_only=True, maya_names=True):
    """Run Blender's writer with the Maya preset's pre / post steps; lambert-family Base Color is linked
    straight to the Maya colour / texture while it writes (``material.diffuse_bypass``). FBX with the Maya
    preset: ``deform_only`` = only the deforming joints, hung on the deforming chain; ``maya_names`` = Maya-safe
    node names (operators/fbx_skeleton.py)."""
    from . import material
    with material.diffuse_bypass():
        _write(context, fmt, path, op, args, maya, k, (deform_only, maya_names))


class _BlendShapesKept:
    """Issue #144: Blender's FBX writer exports the EVALUATED mesh and drops its shape keys
    when any non-Armature modifier is on ($S/addons_core/io_scene_fbx/export_fbx_bin.py:2645-2690, 2773), so a mesh
    with a blend shape and a cluster / lattice / kit deformer lost every blend shape. Maya's FBX keeps the blendShape
    (and skinCluster) and leaves the other deformers out: while writing, those deformer modifiers of meshes with
    shape keys are switched off (restored afterwards)."""

    def __init__(self, obs):
        self.obs, self.saved = obs, []

    def __enter__(self):
        from .history import is_deformer
        for ob in self.obs:
            key = getattr(ob.data, "shape_keys", None) if ob.type == 'MESH' else None
            if key is None or len(key.key_blocks) < 2:
                continue
            for md in ob.modifiers:
                if md.type != 'ARMATURE' and is_deformer(md) and (md.show_viewport or md.show_render):
                    self.saved.append((md, md.show_viewport, md.show_render))
                    md.show_viewport = md.show_render = False
        return self

    def __exit__(self, *exc):
        for md, vp, rd in self.saved:
            md.show_viewport, md.show_render = vp, rd


def _write(context, fmt, path, op, args, maya, k, rig=(True, True)):
    if fmt == 'FBX' and maya:
        obs = context.selected_objects if args.get("use_selection") else list(context.view_layer.objects)
        with _BlendShapesKept([o for o in obs if o is not None]):
            return _write_one(context, fmt, path, op, args, maya, k, rig)
    return _write_one(context, fmt, path, op, args, maya, k, rig)


def _write_one(context, fmt, path, op, args, maya, k, rig=(True, True)):
    mod, name = op.split(".")
    run = getattr(getattr(bpy.ops, mod), name)
    if maya and fmt == 'ABC':
        with _AbcMayaScale(context, args.get("global_scale", 1.0)):
            run('EXEC_DEFAULT', filepath=path, **args)
        return
    run('EXEC_DEFAULT', filepath=path, **args)
    if not maya:
        return
    if fmt == 'FBX':
        rig_fbx_maya(context, path, run, args, deform_only=rig[0])
        from . import fbx_blend, fbx_rig
        if fbx_rig.modules() is not None:        # Maya's blendShape: in-betweens in their target's channel (235)
            obs = context.selected_objects if args.get("use_selection") else list(context.view_layer.objects)
            fbx_blend.rewrite(path, [o for o in obs if o is not None and o.type == 'MESH'])
        if fbx_rig.modules() is not None:
            sc = context.scene
            fps = sc.render.fps / (sc.render.fps_base or 1.0)
            fbx_rig.set_time_span(path, sc.frame_start, sc.frame_end, fps)     # Maya's Time Slider range (235)
            if rig[1]:
                from . import fbx_skeleton
                fbx_skeleton.rewrite_names(path)       # no FBXASC names in Maya
    elif fmt == 'OBJ':
        _write_obj_groups(path)
    elif fmt == 'USD' and not usd_maya_axes(path, k):
        # no pxr / skeletons / usdz: Blender's own conversion (it lands on the top prims' channels)
        run('EXEC_DEFAULT', filepath=path, **dict(args, convert_orientation=True,
                                                  export_global_forward_selection='NEGATIVE_Z',
                                                  export_global_up_selection='Y', convert_scene_units='CUSTOM',
                                                  meters_per_unit=k))


def _exported_armatures(context, args):
    obs = context.selected_objects if args.get("use_selection") else context.view_layer.objects
    return [ob for ob in obs if ob is not None and ob.type == 'ARMATURE']


def rig_fbx_maya(context, path, run, args, deform_only=True):
    """Joint orient as PreRotation, no armature Null (operators/fbx_rig.py). Needs a second export of the
    same objects at the rest pose (the writer's own conventions). ``deform_only``: only the
    deforming joints, on the deforming chain (``fbx_skeleton.deform_parents``). Returns (joints, nulls) or None."""
    from . import fbx_rig
    rigs = _exported_armatures(context, args)
    if not rigs or fbx_rig.modules() is None:
        return None
    saved = [(arm, arm.pose_position) for arm in {ob.data for ob in rigs}]
    # written beside the user's file and deleted at once (the kit writes nowhere the user didn't choose)
    rest = os.path.splitext(path)[0] + ".rest_pose.tmp.fbx"
    try:
        for arm, _pos in saved:
            arm.pose_position = 'REST'
        context.view_layer.update()
        run('EXEC_DEFAULT', filepath=rest, **dict(args, bake_anim=False))
    finally:
        for arm, pos in saved:
            arm.pose_position = pos
        context.view_layer.update()
    from .joints import maya_frames
    ends = {}
    for ob in rigs:
        ends.update(maya_frames(ob))
    parents = None
    if deform_only:
        from . import fbx_skeleton
        parents = {}
        for arm in {ob.data for ob in rigs}:          # armatures already on a deforming chain stay untouched
            own = fbx_skeleton.deform_parents(arm)
            if fbx_skeleton.changes_anything(own, arm):
                parents.update(own)
    try:
        return fbx_rig.rewrite(path, rest, ends, parents)
    finally:
        try:
            os.remove(rest)
        except OSError:
            pass


def preset_text(fmt, k, export):
    """One line for the Options panel: what the Maya preset does for this format."""
    if fmt == 'BLEND':
        return "Blender scene: units and axes are kept as they are"
    if fmt == 'GLTF':
        return "glTF is always metres, Y up (no Maya preset)"
    if fmt == 'FBX':
        return "Centimetres, Y up (stored in the FBX)"
    if fmt == 'USD':
        return f"Y up, metersPerUnit {k:g}" if export else "Y up, metersPerUnit converted to Maya units"
    scale = 1.0 / k if export else k
    return f"Y up, scale ×{scale:g} (1 Maya unit = 1 {'file unit' if export else 'scene unit'})"


# --- .blend as a Maya scene file ------------------------------------------------------------------

def multi_skin_meshes(obs):
    """Names of the meshes with more than one skin (Armature modifier with a skeleton)."""
    from . import skin
    return [o.name for o in obs if o.type == 'MESH' and len(skin.armature_modifiers(o)) > 1]


def import_blend(context, path):
    """Maya Import of a Maya scene: the other file's objects join this scene (in a collection named after it)."""
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = list(src.objects)
    coll = bpy.data.collections.new(os.path.splitext(os.path.basename(path))[0])
    context.scene.collection.children.link(coll)
    obs = [ob for ob in dst.objects if ob is not None]
    for ob in obs:
        coll.objects.link(ob)
    return obs


def export_blend(context, path, selection):
    if not selection:
        bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
        return
    from . import dag
    obs = set(dag.hierarchy(context.selected_objects))     # Maya: the selection with its descendants
    bpy.data.libraries.write(path, obs, fake_user=False, compress=False)


# --- the dialog -------------------------------------------------------------------------------------

def _filter_update(self, context):
    self.filter_glob = ALL_GLOB if self.mode == 'IMPORT' and self.import_type == 'AUTO' else \
        _BY_ID[self.import_type if self.mode == 'IMPORT' else self.export_type][3]
    if self.mode != 'IMPORT' and self.filepath and format_of(self.filepath) != self.export_type:
        self.filepath = bpy.path.ensure_ext(os.path.splitext(self.filepath)[0], _BY_ID[self.export_type][2])


class _FileDialog:
    """Maya file dialog: Files of type and the format options in the side panel, Maya's cm / Y-up presets
    (Maya File > Import / Export All / Export Selection)"""
    bl_options = {'REGISTER', 'UNDO'}
    FIXED = None     # the mode of the menu-item operators (their label is the file browser's button text)

    mode: EnumProperty(items=MODES, name="Mode", options={'SKIP_SAVE'})
    filepath: StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    filter_glob: StringProperty(default=ALL_GLOB, options={'HIDDEN', 'SKIP_SAVE'})
    import_type: EnumProperty(items=IMPORT_TYPES, name="Files of type", update=_filter_update)
    export_type: EnumProperty(items=EXPORT_TYPES, name="Files of type", default='FBX', update=_filter_update)
    maya_conversion: BoolProperty(name="Maya Units and Axes", default=True,
                                  description="Convert to / from a Maya scene: centimetres and Y up")
    animation: BoolProperty(name="Animation", default=True, description="Write the animation (FBX, Alembic, USD)")
    # Issue #145: engine-ready skeletons (operators/fbx_skeleton.py)
    deform_only: BoolProperty(name="Deforming Joints Only", default=True,
                              description="FBX: write only the joints that deform the skin (a Rigify rig's DEF "
                                          "bones), parented along the deforming chain; helper and control bones "
                                          "stay out")
    maya_names: BoolProperty(name="Maya-Safe Names", default=True,
                             description="FBX: '-', '.' and other characters Maya can't have in a node name "
                                         "become '_' (DEF-spine.001 -> DEF_spine_001)")
    option_box: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'},
                             description="Maya option box: the Options panel of this dialog")

    @property
    def selection(self):
        return self.mode == 'EXPORT_SELECTION'

    def _fmt(self):
        if self.mode == 'IMPORT':
            return format_of(self.filepath) if self.import_type == 'AUTO' else self.import_type
        return self.export_type

    def invoke(self, context, event):
        if self.FIXED:
            self.mode = self.FIXED
        if self.mode == 'IMPORT':
            name, fmt = "", (None if self.import_type == 'AUTO' else self.import_type)
        else:
            base = os.path.splitext(bpy.path.basename(bpy.data.filepath))[0] or "untitled"
            name, fmt = base + _BY_ID[self.export_type][2], self.export_type
        self.filepath = os.path.join(start_folder(context, fmt), name)
        _filter_update(self, context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def check(self, context):
        """Keep the file name's extension in step with Files of type (Maya does the same)."""
        if self.mode == 'IMPORT' or not self.filepath or format_of(self.filepath) == self.export_type:
            return False
        self.filepath = bpy.path.ensure_ext(os.path.splitext(self.filepath)[0], _BY_ID[self.export_type][2])
        return True

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = False
        layout.label(text="Files of type:")
        layout.prop(self, "import_type" if self.mode == 'IMPORT' else "export_type", text="")
        fmt = self._fmt() or 'FBX'
        k = units.maya_unit(context.scene)
        box = layout.box()
        box.label(text="General Options")
        box.prop(self, "maya_conversion")
        sub = box.column()
        sub.enabled = self.maya_conversion
        sub.label(text=preset_text(fmt, k, self.mode != 'IMPORT'))
        if self.mode != 'IMPORT':
            box.label(text="Selection Only", icon='CHECKBOX_HLT' if self.selection else 'CHECKBOX_DEHLT')
            if fmt in ('FBX', 'ABC', 'USD'):
                box = layout.box()
                box.label(text="File Type Specific Options")
                box.prop(self, "animation")
                if fmt == 'FBX':
                    col = box.column()
                    col.enabled = self.maya_conversion
                    col.prop(self, "deform_only")
                    col.prop(self, "maya_names")
        layout.label(text=f"Project: {os.path.basename(project.current_root(context))}", icon='FILE_FOLDER')

    def execute(self, context):
        if self.FIXED:
            self.mode = self.FIXED
        path = bpy.path.abspath(self.filepath)
        fmt = self._fmt()
        if not fmt:
            self.report({'ERROR'}, f"No translator reads {os.path.basename(path)} "
                                   "(Maya .ma / .mb can't be read: export FBX from Maya)")
            return {'CANCELLED'}
        k = units.maya_unit(context.scene)
        try:
            if self.mode == 'IMPORT':
                if not os.path.isfile(path):
                    self.report({'ERROR'}, f"No such file: {path}")
                    return {'CANCELLED'}
                if fmt == 'BLEND':
                    obs = import_blend(context, path)
                    results.result(self, f"Imported {len(obs)} object(s) from {os.path.basename(path)}")
                    return {'FINISHED'}
                op, args = import_args(fmt, k, self.maya_conversion)
                if fmt == 'FBX' and self.maya_conversion:
                    from . import fbx_rig_import
                    if fbx_rig_import.has_skeleton(path):
                        # Blender's reader bakes the conversion into a skinned mesh but leaves it on the armature
                        # (mesh 0.01 x, first_hour #37): read plain, after_import converts
                        args = dict(args, bake_space_transform=False)
                before, mats = set(bpy.data.objects), set(bpy.data.materials)
                mod, name = op.split(".")
                getattr(getattr(bpy.ops, mod), name)('EXEC_DEFAULT', filepath=path, **args)
                if self.maya_conversion:
                    after_import(context, fmt, path, [ob for ob in bpy.data.objects if ob not in before],
                                 [m for m in bpy.data.materials if m not in mats], args)
            else:
                if self.selection and not context.selected_objects:
                    self.report({'WARNING'}, "Nothing selected to export.")
                    return {'CANCELLED'}
                path = bpy.path.ensure_ext(path, _BY_ID[fmt][2]) if format_of(path) != fmt else path
                if fmt == 'BLEND':
                    export_blend(context, path, self.selection)
                    results.result(self, f"Exported {os.path.basename(path)}")
                    return {'FINISHED'}
                op, args = export_args(fmt, k, self.selection, self.maya_conversion)
                args.update(_animation_args(fmt, self.animation))
                # Maya Export Selection writes the selected nodes with everything below them;
                # Blender's writers take only the selected objects
                from . import dag
                from .control_shapes import excluded as shapes_excluded   # no control shape curves
                if self.selection:
                    with dag.selected_hierarchy(context), shapes_excluded(context.scene, context.view_layer):
                        write(context, fmt, path, op, args, self.maya_conversion, k,
                              self.deform_only, self.maya_names)
                else:
                    from . import startup_cameras
                    with startup_cameras.excluded(context.scene, context.view_layer),                             shapes_excluded(context.scene, context.view_layer):
                        write(context, fmt, path, op, args, self.maya_conversion, k,
                              self.deform_only, self.maya_names)
        except RuntimeError as ex:
            self.report({'ERROR'}, str(ex).strip().splitlines()[-1])
            return {'CANCELLED'}
        verb = "Imported" if self.mode == 'IMPORT' else "Exported"
        if self.mode != 'IMPORT':
            many = multi_skin_meshes(context.selected_objects if self.selection else context.scene.objects)
            if many:
                # Blender reads a second Armature modifier back as one, engines keep one skin
                self.report({'WARNING'}, f"{', '.join(many)}: several skin clusters — FBX and game engines keep one "
                                         "skin per mesh")
        results.result(self, f"{verb} {os.path.basename(path)}")
        return {'FINISHED'}


class ALLSET_OT_file_dialog(_FileDialog, bpy.types.Operator):
    bl_idname = "allset.file_dialog"
    bl_label = "File"


class ALLSET_OT_file_import(_FileDialog, bpy.types.Operator):
    """Import a file into the scene; Files of type / Best Guess picks the format (Maya File > Import)"""
    bl_idname = "allset.file_import"
    bl_label = "Import"
    FIXED = 'IMPORT'


class ALLSET_OT_file_export_all(_FileDialog, bpy.types.Operator):
    """Export the whole scene in the chosen format (Maya File > Export All)"""
    bl_idname = "allset.file_export_all"
    bl_label = "Export All"
    FIXED = 'EXPORT_ALL'


class ALLSET_OT_file_export_selection(_FileDialog, bpy.types.Operator):
    """Export the selected objects in the chosen format (Maya File > Export Selection)"""
    bl_idname = "allset.file_export_selection"
    bl_label = "Export Selection"
    FIXED = 'EXPORT_SELECTION'


def _animation_args(fmt, on):
    if fmt == 'FBX':
        return {"bake_anim": on}
    if fmt == 'USD':
        return {"export_animation": on}
    if fmt == 'ABC' and not on:
        f = bpy.context.scene.frame_current
        return {"start": f, "end": f}
    return {}


# --- file browser: Current Project ------------------------------------------------------------------

class ALLSET_OT_file_goto(bpy.types.Operator):
    """Show this folder in the file browser (Maya file dialog: project folder list)"""
    bl_idname = "allset.file_goto"
    bl_label = "Go to Folder"
    bl_options = {'INTERNAL'}

    path: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.type == 'FILE_BROWSER' and space.params is not None

    def execute(self, context):
        if not os.path.isdir(self.path):
            os.makedirs(self.path, exist_ok=True)
        context.space_data.params.directory = os.path.join(self.path, "").encode()
        return {'FINISHED'}


class ALLSET_OT_file_set_project(bpy.types.Operator):
    """Make the folder shown in the file browser the current project (Maya file dialog: Set Project...)"""
    bl_idname = "allset.file_set_project"
    bl_label = "Set Project"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return ALLSET_OT_file_goto.poll(context)

    def execute(self, context):
        folder = os.path.abspath(context.space_data.params.directory.decode())
        # in a project sub-folder (scenes ...) the project is the folder above it
        if os.path.basename(folder.rstrip(os.sep)) in project.FOLDERS and project.is_project(os.path.dirname(folder)):
            folder = os.path.dirname(folder)
        project.create_project(folder)
        project.set_current(folder, context)
        scenes = os.path.join(folder, "scenes", "")
        context.space_data.params.directory = scenes.encode()
        results.result(self, f"Project: {folder}")
        return {'FINISHED'}


classes = (ALLSET_OT_file_dialog, ALLSET_OT_file_import, ALLSET_OT_file_export_all, ALLSET_OT_file_export_selection,
           ALLSET_OT_file_goto, ALLSET_OT_file_set_project)
