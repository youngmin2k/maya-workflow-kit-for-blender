# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Curves / Surfaces commands Blender can build.

Results in Maya (defaults of the commands):
- Planar on a closed curve -> ``planarTrimmedSurface1``; here a copy of the curve filled in 2D (Blender fills
  closed 2D curves; the curve is flattened onto its local XY plane).
- Loft / Extrude: real NURBS surfaces (operators/surfaces_maya.py).
- Bevel Plus on a closed curve -> ``bevelPolygon1`` (a **mesh**, the curve kept): width 0.1, depth 0.1, extrude
  depth 0.25 in Maya units.
- Offset Curve -> ``offsetNurbsCurve1`` (distance 1), Sweep Mesh -> ``sweep1`` (an 8-sided tube mesh with a live
  ``sweepMeshCreator1``, operators/sweep_mesh.py): see the constants below.
- Pencil Curve Tool / Add Points Tool: Blender's curve Draw tool on a new curve / extruding the curve's end
  points (curve edit mode).

Selection order: Maya lofts / extrudes in selection order; Blender objects have none, so the active (last
selected) object is last, the others keep their name order.
"""

import bpy

from . import naming, units

# Maya Bevel Plus defaults (bevelPlus node): bevel width / depth 0.1, extrude depth 0.25.
BEVEL_WIDTH, BEVEL_DEPTH, EXTRUDE_DEPTH = 0.1, 0.1, 0.25


def _curves(context):
    """Selected curve objects, active last (module docstring: selection order)."""
    obs = sorted((ob for ob in context.selected_objects if ob.type == 'CURVE'), key=lambda o: o.name)
    act = context.active_object
    if act in obs:
        obs.remove(act)
        obs.append(act)
    return obs


def _link_new(context, ob, base, select=True):
    context.collection.objects.link(ob)
    naming.apply_maya_name(ob, base)
    if select:
        for o in context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
    return ob


def _closed(curve):
    return any(sp.use_cyclic_u for sp in curve.splines)


def _object_mode(context):
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


# --- Planar -------------------------------------------------------------------------------------

def planar(context, ob):
    data = ob.data.copy()
    data.dimensions = '2D'
    data.fill_mode = 'BOTH'
    data.extrude = data.bevel_depth = 0.0
    data.bevel_mode = 'ROUND'
    data.bevel_object = None
    new = bpy.data.objects.new("planarTrimmedSurface", data)
    new.matrix_world = ob.matrix_world
    return _link_new(context, new, "planarTrimmedSurface", select=False)


class ALLSET_OT_surface_planar(bpy.types.Operator):
    """Fill the selected closed curves with a flat surface (Maya Surfaces > Planar)"""
    bl_idname = "allset.surface_planar"
    bl_label = "Planar"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _object_mode(context)
        obs = [ob for ob in _curves(context) if _closed(ob.data)]
        if not obs:
            self.report({'WARNING'}, "No valid items selected.  Select planar curves.")   # Maya's message
            return {'CANCELLED'}
        made = [planar(context, ob) for ob in obs]
        _select(context, made)
        return {'FINISHED'}


def _select(context, obs):
    for o in context.selected_objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    context.view_layer.objects.active = obs[-1]


# --- Loft ---------------------------------------------------------------------------------------

def curve_points(context, ob):
    """World-space points along the first spline of a curve object as drawn, and whether it is closed."""
    ev = ob.evaluated_get(context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    try:
        cos = [ob.matrix_world @ v.co for v in me.vertices]
        adj = {i: [] for i in range(len(cos))}
        for e in me.edges:
            a, b = e.vertices
            adj[a].append(b)
            adj[b].append(a)
    finally:
        ev.to_mesh_clear()
    if not cos:
        return [], False
    start = next((i for i, n in adj.items() if len(n) == 1), 0)
    path, prev, cur = [start], None, start
    while True:
        nxt = next((n for n in adj[cur] if n != prev and n not in path[-2:]), None)
        if nxt is None or nxt == start:
            break
        path.append(nxt)
        prev, cur = cur, nxt
    closed = len(adj[start]) == 2 and start in adj[path[-1]]
    return [cos[i] for i in path], closed


def resample(points, count, closed):
    """``count`` points spread evenly by arc length along a polyline."""
    pts = list(points) + ([points[0]] if closed else [])
    seg = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
    total = sum(seg) or 1.0
    steps = count if closed else count - 1
    out, i, acc = [], 0, 0.0
    for k in range(count):
        d = total * k / max(steps, 1)
        while i < len(seg) - 1 and acc + seg[i] < d:
            acc += seg[i]
            i += 1
        t = 0.0 if seg[i] == 0 else min(1.0, max(0.0, (d - acc) / seg[i]))
        out.append(pts[i].lerp(pts[i + 1], t))
    return out


# Loft / Extrude moved to operators/surfaces_maya.py (real NURBS surfaces).


# --- Bevel Plus ---------------------------------------------------------------------------------

def bevel_plus(context, ob):
    """A mesh like Maya's bevelPolygon1: the closed curve filled, extruded and bevelled front and back."""
    k = units.maya_unit(context.scene)
    data = ob.data.copy()
    data.dimensions = '2D'
    data.fill_mode = 'BOTH'
    data.extrude = EXTRUDE_DEPTH * k / 2          # Blender extrudes both ways
    data.bevel_mode = 'ROUND'
    data.bevel_object = None
    data.bevel_depth = BEVEL_DEPTH * k
    data.bevel_resolution = 0                     # straight bevel
    data.offset = -BEVEL_WIDTH * k                # Maya bevels inside the curve
    tmp = bpy.data.objects.new("bevelPlusTmp", data)
    context.collection.objects.link(tmp)
    try:
        context.view_layer.update()
        me = bpy.data.meshes.new_from_object(tmp.evaluated_get(context.evaluated_depsgraph_get()))
    finally:
        bpy.data.objects.remove(tmp)
        bpy.data.curves.remove(data)
    new = bpy.data.objects.new("bevelPolygon", me)
    new.matrix_world = ob.matrix_world
    _link_new(context, new, "bevelPolygon", select=False)
    from . import material
    me.materials.clear()
    material.give_default(new)
    return new


class ALLSET_OT_bevel_plus(bpy.types.Operator):
    """Make a bevelled solid from the selected closed curves, the curves kept (Maya Surfaces > Bevel Plus)"""
    bl_idname = "allset.bevel_plus"
    bl_label = "Bevel Plus"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _object_mode(context)
        obs = [ob for ob in _curves(context) if _closed(ob.data)]
        if not obs:
            self.report({'WARNING'}, "Select closed curves.")
            return {'CANCELLED'}
        _select(context, [bevel_plus(context, ob) for ob in obs])
        return {'FINISHED'}


# --- Offset Curve -------------------------------------------------------------------------------
# Maya offsetCurve: distance 1, in the plane of the curve normal, towards normal x tangent (a line along
# +X with normal +Y moves to -Z; a radius-2 circle came out radius 1); result offsetNurbsCurve1, curve kept.
OFFSET_DISTANCE = 1.0
OFFSET_MIN_POINTS = 32


def offset_curve(context, ob, distance):
    from mathutils import Vector
    pts, closed = curve_points(context, ob)
    if len(pts) < 2:
        return None
    pts = resample(pts, max(OFFSET_MIN_POINTS, len(pts)), closed)
    normal = (ob.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    out = []
    n = len(pts)
    for i, p in enumerate(pts):
        a = pts[(i - 1) % n] if closed or i > 0 else p
        b = pts[(i + 1) % n] if closed or i < n - 1 else p
        t = (b - a).normalized()
        out.append(p + normal.cross(t).normalized() * distance)
    data = bpy.data.curves.new("offsetNurbsCurveShape", 'CURVE')
    data.dimensions = '3D'
    sp = data.splines.new('POLY')
    sp.points.add(len(out) - 1)
    for p, q in zip(sp.points, out):
        p.co = (q.x, q.y, q.z, 1.0)
    sp.use_cyclic_u = closed
    return _link_new(context, bpy.data.objects.new("offsetNurbsCurve", data), "offsetNurbsCurve", select=False)


class ALLSET_OT_offset_curve(bpy.types.Operator):
    """Make a copy of the selected curves moved sideways in their plane (Maya Curves > Offset > Offset Curve)"""
    bl_idname = "allset.offset_curve"
    bl_label = "Offset Curve"
    bl_options = {'REGISTER', 'UNDO'}

    distance: bpy.props.FloatProperty(name="Offset Distance", default=OFFSET_DISTANCE,
                                      description="Maya units (offsetCurve distance)")

    def execute(self, context):
        _object_mode(context)
        k = units.maya_unit(context.scene)
        made = [o for o in (offset_curve(context, ob, self.distance * k) for ob in _curves(context)) if o]
        if not made:
            self.report({'WARNING'}, "Select curves to offset.")
            return {'CANCELLED'}
        _select(context, made)
        return {'FINISHED'}


# --- Sweep Mesh ---------------------------------------------------------------------------------
# Sweep Mesh: a mesh sweep1 / sweepShape1 around the curve with a live sweepMeshCreator1 node (by default an
# 8-sided profile of radius 1, 6 rings on a one-span curve); the curve is kept (operators/sweep_mesh.py).
SWEEP_RADIUS, SWEEP_SIDES = 1.0, 8


def sweep_mesh(context, ob):
    from . import sweep_mesh as sweep
    return sweep.create(context, ob)


class ALLSET_OT_sweep_mesh(bpy.types.Operator):
    """Make a tube mesh along the selected curves; its profile, size and steps stay editable and it follows the
    curves (Maya Create > Sweep Mesh)"""
    bl_idname = "allset.sweep_mesh"
    bl_label = "Sweep Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _object_mode(context)
        obs = _curves(context)
        if not obs:
            self.report({'WARNING'}, "Select curves to sweep.")
            return {'CANCELLED'}
        _select(context, [sweep_mesh(context, ob) for ob in obs])
        return {'FINISHED'}


# --- Pencil Curve Tool / Add Points Tool --------------------------------------------------------

class ALLSET_OT_pencil_curve(bpy.types.Operator):
    """Draw a new curve freehand (Maya Create > Curve Tools > Pencil Curve Tool: Blender's curve Draw tool)"""
    bl_idname = "allset.pencil_curve"
    bl_label = "Pencil Curve Tool"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _object_mode(context)
        data = bpy.data.curves.new("curveShape", 'CURVE')
        data.dimensions = '3D'
        _link_new(context, bpy.data.objects.new("curve", data), "curve")
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.draw", space_type='VIEW_3D')
        except RuntimeError:     # no tool keymaps in background (-b): the curve is still ready to draw on
            pass
        return {'FINISHED'}


def _end_points(curve):
    """Select only the last point of every open spline (Maya adds points at the curve's end)."""
    for sp in curve.splines:
        if sp.type == 'BEZIER':
            for p in sp.bezier_points:
                p.select_control_point = p.select_left_handle = p.select_right_handle = False
            if not sp.use_cyclic_u and len(sp.bezier_points):
                sp.bezier_points[-1].select_control_point = True
        else:
            for p in sp.points:
                p.select = False
            if not sp.use_cyclic_u and len(sp.points):
                sp.points[-1].select = True


class ALLSET_OT_add_points(bpy.types.Operator):
    """Add points at the end of the selected curve (Maya Curves > Add Points Tool: extrude the end point)"""
    bl_idname = "allset.add_points"
    bl_label = "Add Points Tool"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'CURVE'

    def invoke(self, context, event):
        ob = context.active_object
        if context.mode != 'EDIT_CURVE':
            bpy.ops.object.mode_set(mode='OBJECT')
            _end_points(ob.data)
            bpy.ops.object.mode_set(mode='EDIT')
        if context.area is None or context.area.type != 'VIEW_3D':
            return {'FINISHED'}
        return bpy.ops.curve.extrude_move('INVOKE_DEFAULT')

    def execute(self, context):
        ob = context.active_object
        bpy.ops.object.mode_set(mode='OBJECT')
        _end_points(ob.data)
        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}


classes = (ALLSET_OT_surface_planar, ALLSET_OT_bevel_plus,
           ALLSET_OT_offset_curve, ALLSET_OT_sweep_mesh, ALLSET_OT_pencil_curve, ALLSET_OT_add_points)
