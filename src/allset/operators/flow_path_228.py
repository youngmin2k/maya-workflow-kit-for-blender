# SPDX-License-Identifier: GPL-3.0-or-later
"""L9: Maya Flow Path Object (lattice along the motion path).

Maya: Constrain > Motion Paths > Flow Path Object (Divisions 5 / 2 / 2,
Lattice around Object, Local effect off) on an object that has a motion path makes ``flow1`` / ``ffd1`` /
``ffd1Lattice`` / ``ffd1Base``: a lattice around the object whose points the flow node places along the motion path
(each point at its own distance along the path, offset in the path's frame), the ffd deforming the object.

Blender construction:
- the kit lattice deformer (``deformers.create('LATTICE')``: ``ffd1`` Lattice modifier + ``ffd1Base`` Hook
  + ``ffd1Lattice``, Front / Up / Side = lattice u / w / v), interpolation Linear;
- the lattice gets a Curve modifier ``flow1`` on the path (Blender's Curve modifier maps curve-space X to the distance
  along the path and offsets Y / Z in the path frame — the same placement as Maya's flow node: the lattice end points
  match Maya to 1e-4 at frames 30 / 60 / 90) and a shape key ``flow1`` that shifts every point along the path by
  the path length, its value driven by the object's Follow Path ``offset_factor`` (= Maya motionPath uValue as a
  fraction); the object's own Follow Path constraint is muted (the lattice now carries the motion);
- deviation: Maya's ffd with Local off is a global Bernstein (Bezier) volume over the 5 x 2 x 2 points
  (matched offline to 1e-4); Blender lattices interpolate Linear / Cardinal / Catmull-Rom / B-spline only, Linear is
  closest (max 0.075 on the 4-unit test cylinder); beyond the path ends Blender extrapolates along
  the end tangent, Maya differently (0.043 at frames 1 / 120).
"""

import json

import bpy
from mathutils import Matrix, Vector

from .. import results, undo_steps

KEY = "allset_flow"           # lattice object ID prop: the flow record (json)
CHILD_OF = "flow path space"  # Child Of on the object when the path curve isn't at the world origin


def follow_path(ob):
    """The object's Follow Path constraint on a curve (Maya: its motion path), or None."""
    for con in ob.constraints:
        if con.type == 'FOLLOW_PATH' and con.target is not None and con.target.type == 'CURVE':
            return con
    return None


def path_length(context, path):
    """Length of the path Blender's Follow Path / Curve modifier walk (the evaluated polyline)."""
    dg = context.evaluated_depsgraph_get()
    pe = path.evaluated_get(dg)
    me = pe.to_mesh()
    try:
        vs = me.vertices
        return sum((vs[e.vertices[0]].co - vs[e.vertices[1]].co).length for e in me.edges)
    finally:
        pe.to_mesh_clear()


def _is_identity(m):
    return all(abs(m[i][j] - (1.0 if i == j else 0.0)) < 1e-6 for i in range(4) for j in range(4))


def flow(context, ob, divisions=(5, 2, 2)):
    """Maya ``flow`` on ``ob`` (which has a motion path). Returns (flow name, lattice object)."""
    from . import deformers
    con = follow_path(ob)
    if con is None:
        raise RuntimeError(f"{ob.name} has no motion path. Attach it to a motion path first "
                           "(Constrain > Motion Paths > Attach to Motion Path).")
    path = con.target
    con.mute = True                       # the lattice carries the motion from now on
    if not _is_identity(path.matrix_world):
        # the Curve modifier reads the lattice in the path's space: the object sits in that space like Follow Path
        # put it there (world = path @ basis)
        co = ob.constraints.new('CHILD_OF')
        co.name = CHILD_OF
        co.target = path
        co.inverse_matrix = Matrix.Identity(4)
    context.view_layer.update()
    for o in context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    front, up, side = (max(2, int(d)) for d in divisions)
    # Maya S / T / U along X / Y / Z: Front = X, Up = Maya Y, Side = Maya Z (deformers._lattice takes Maya's order)
    lob = deformers.create(context, 'LATTICE', {"divisions": (front, up, side), "center": True, "auto_parent": False})
    lat = lob.data
    lat.interpolation_type_u = lat.interpolation_type_v = lat.interpolation_type_w = 'KEY_LINEAR'
    name = deformers.new_name("flow")
    length = path_length(context, path)
    lob.shape_key_add(name="Basis", from_mix=False)
    sk = lob.shape_key_add(name=name, from_mix=False)
    shift = lob.matrix_world.inverted().to_3x3() @ (path.matrix_world.to_3x3() @ Vector((length, 0.0, 0.0)))
    for p in sk.data:
        p.co = p.co + shift
    sk.slider_min, sk.slider_max = -10.0, 10.0
    drv = sk.driver_add("value").driver
    drv.type = 'AVERAGE'
    var = drv.variables.new()
    var.name = "u"
    var.type = 'SINGLE_PROP'
    var.targets[0].id_type = 'OBJECT'
    var.targets[0].id = ob
    var.targets[0].data_path = f'constraints["{con.name}"].offset_factor'
    md = lob.modifiers.new(name, 'CURVE')
    md.object = path
    md.deform_axis = 'POS_X'
    path.data.use_deform_bounds = False    # Bounds Clamp would pin the lattice's back end to the path start
    lob[KEY] = json.dumps({"flow": name, "object": ob.name, "path": path.name, "constraint": con.name,
                           "length": length, "divisions": [front, up, side]})
    context.view_layer.update()
    return name, lob


@undo_steps.no_redo_panel
class ALLSET_OT_flow_path(bpy.types.Operator):
    """Make a lattice around each selected object that bends along its motion path (Maya Constrain > Motion Paths >
    Flow Path Object)"""
    bl_idname = "allset.flow_path"
    bl_label = "Flow Path Object"
    bl_options = {'REGISTER', 'UNDO'}

    front: bpy.props.IntProperty(name="Front", default=5, min=2, max=100, options={'SKIP_SAVE'})
    up: bpy.props.IntProperty(name="Up", default=2, min=2, max=100, options={'SKIP_SAVE'})
    side: bpy.props.IntProperty(name="Side", default=2, min=2, max=100, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        obs = [o for o in context.selected_objects if o.type in {'MESH', 'CURVE', 'SURFACE', 'LATTICE'}
               and follow_path(o) is not None]
        if not obs:
            self.report({'WARNING'}, "Select an object that is attached to a motion path "
                                     "(Constrain > Motion Paths > Attach to Motion Path).")
            return {'CANCELLED'}
        made, lats = [], []
        for ob in obs:
            try:
                name, lob = flow(context, ob, (self.front, self.up, self.side))
            except RuntimeError as ex:
                self.report({'WARNING'}, str(ex))
                continue
            base = lob.name[:-len("Lattice")]
            made += [name, base, lob.name, base + "Base"]
            lats.append(lob)
        if not lats:
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        for lob in lats:
            lob.select_set(True)
        context.view_layer.objects.active = lats[-1]
        results.result(self, " ".join(made))
        return {'FINISHED'}


def windows():
    """Maya Flow Path Object Options (default values —
    Divisions Front 5 / Up 2 / Side 2, Lattice around Object, Local effect off 2 / 2 / 2)."""
    from .option_windows import F, Window

    def run(context, v):
        return bpy.ops.allset.flow_path('EXEC_DEFAULT', front=v["front"], up=v["up"], side=v["side"])

    return [Window("flow_path", "Flow Path Object Options", "Flow", ("allset.flow_path", {}), [
        F("front", "Front:", "int", 5, lo=2, hi=100, heading="Divisions"),
        F("up", "Up:", "int", 2, lo=2, hi=100),
        F("side", "Side:", "int", 2, lo=2, hi=100),
    ], run, paths=("Constrain/Motion Paths/Flow Path Object",),
        missing=("Lattice around: Object only (Curve not made)",
                 "Local effect: off only (Front / Up / Side 2 / 2 / 2)"))]


classes = (ALLSET_OT_flow_path,)


def register_props():
    from . import surfaces_maya
    surfaces_maya.register_history()


def unregister_props():
    from . import surfaces_maya
    surfaces_maya.unregister_history()
