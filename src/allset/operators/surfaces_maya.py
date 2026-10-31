# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Surfaces menu on Blender legacy NURBS surfaces
(maths in ``surfaces_math`` — bpy-free, tested headless).

Representation: a Maya NURBS surface = a Blender
SURFACE object, one NURBS spline, Maya U = Blender u (along a row), Maya V = the row index. Uniform directions are exact
(Endpoint / Cyclic), non-uniform ones a Bezier decomposition (exact shape). The Maya knot vectors and CVs are kept in the
data's ID property ``allset_nurbs`` while the points are what the kit wrote (signature check), so later commands
continue with Maya's parameters. Every rule works in any right-handed frame: the operators work in Blender world space;
Maya axis choices go through ``MAYA_AXES`` (Maya (X, Y, Z) -> Blender (X, -Z, Y)) and Maya lengths through
``units.maya_unit()``.
"""

import json

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty
from mathutils import Vector

from .. import compat, results, undo_steps
from . import curves_maya, material, naming, units
from . import surfaces_math as sm
from .modify_maya import selection_order

KEY = "allset_nurbs"
MAYA_AXES = {'X': (1.0, 0.0, 0.0), 'Y': (0.0, 0.0, 1.0), 'Z': (0.0, -1.0, 0.0)}   # Maya axis -> Blender world
RESOLUTION = 4          # Blender evaluates resolution x points per direction
MAX_ORDER = 6           # Blender NURBS order 2..6: Maya degree 7 is drawn as degree 5


# --- Blender surface <-> Surf ---------------------------------------------------------------------------------

def _signature(sp):
    return [round(c, 5) for p in sp.points for c in p.co]


def _rows_of(sp):
    nu, nv = sp.point_count_u, sp.point_count_v
    return [[tuple(sp.points[j * nu + i].co[:3]) for i in range(nu)] for j in range(nv)]


def _transform(s, matrix):
    out = s.copy()
    out.cvs = [[tuple(matrix @ Vector(c)) for c in col] for col in s.cvs]
    return out


def read_surface(ob):
    """World-space Surf of a SURFACE object's first spline (the kit record when the points are still its own)."""
    sp = ob.data.splines[0]
    rec = ob.data.get(KEY)
    s = None
    if rec is not None:
        try:
            d = json.loads(rec)
            if d.get("sig") == _signature(sp):
                s = sm.Surf([[tuple(c) for c in col] for col in d["cvs"]], d["knots_u"], d["knots_v"], d["degree_u"],
                            d["degree_v"], d["periodic_u"], d["periodic_v"])
        except (ValueError, KeyError, TypeError):
            s = None
    if s is None:
        s = sm.from_blender_grid(_rows_of(sp), sp.order_u, sp.order_v, sp.use_cyclic_u, sp.use_cyclic_v,
                                 sp.use_endpoint_u, sp.use_endpoint_v, sp.use_bezier_u, sp.use_bezier_v)
    return _transform(s, ob.matrix_world)


def _clamp_degrees(s):
    if s.degree_u + 1 <= MAX_ORDER and s.degree_v + 1 <= MAX_ORDER:
        return s
    return sm.rebuild(s, *(max(1, len(set(k)) - 1) for k in (s.knots_u, s.knots_v)),
                      min(s.degree_u, MAX_ORDER - 1), min(s.degree_v, MAX_ORDER - 1))


def _write_grid(context, data, grid):
    """Fill empty SURFACE ``data`` with one spline from blender_grid ``grid`` (rows made by extruding the first one
    in edit mode of a temporary object: Python can't add surface rows, prim_history.new_curve_data)."""
    rows = grid["rows"]
    nv, nu = len(rows), len(rows[0])
    sp = data.splines.new('NURBS')
    sp.points.add(nu - 1)
    for p in sp.points:
        p.select = True
    if nv > 1:
        tmp = bpy.data.objects.new(".allset_tmp_surface", data)
        context.scene.collection.objects.link(tmp)
        layer = context.view_layer
        prev = layer.objects.active
        layer.objects.active = tmp
        try:
            bpy.ops.object.mode_set(mode='EDIT')
            for _ in range(nv - 1):
                bpy.ops.curve.extrude(mode='TRANSLATION')
            bpy.ops.object.mode_set(mode='OBJECT')
        finally:
            layer.objects.active = prev
            bpy.data.objects.remove(tmp)
        sp = data.splines[0]
    for j, row in enumerate(rows):
        for i, c in enumerate(row):
            sp.points[j * nu + i].co = (*c, 1.0)
            sp.points[j * nu + i].select = False
    for key in ("u", "v"):
        setattr(sp, "order_" + key, grid["order_" + key])
        setattr(sp, "use_cyclic_" + key, grid["cyclic_" + key])
        setattr(sp, "use_endpoint_" + key, grid["endpoint_" + key])
        setattr(sp, "use_bezier_" + key, grid["bezier_" + key])
    sp.use_smooth = True
    sp.resolution_u = sp.resolution_v = RESOLUTION
    return sp


def _new_data(context, name, s):
    s = _clamp_degrees(s)
    data = bpy.data.curves.new(name, 'SURFACE')
    data.dimensions = '3D'
    data.resolution_u = data.resolution_v = RESOLUTION
    sp = _write_grid(context, data, sm.blender_grid(s))
    data[KEY] = json.dumps({"cvs": [[list(c) for c in col] for col in s.cvs], "knots_u": list(s.knots_u),
                            "knots_v": list(s.knots_v), "degree_u": s.degree_u, "degree_v": s.degree_v,
                            "periodic_u": s.periodic_u, "periodic_v": s.periodic_v, "sig": _signature(sp)})
    return data


def new_surface(context, base, s, select=True):
    """A new SURFACE object at the world origin (Maya: a new transform at the world root) holding world-space ``s``."""
    data = _new_data(context, base + "Shape", s)
    ob = bpy.data.objects.new(base, data)
    (context.collection or context.scene.collection).objects.link(ob)
    naming.apply_maya_name(ob, base)
    material.give_default(ob)
    if select:
        _select(context, [ob])
    return ob


def replace_surface(context, ob, s):
    """Swap ``ob``'s data for world-space ``s`` (Maya replace-original commands: Rebuild, Reverse, Insert, Detach)."""
    old = ob.data
    local = _transform(s, ob.matrix_world.inverted())
    data = _new_data(context, old.name, local)
    for m in old.materials:
        data.materials.append(m)
    name = old.name
    ob.data = data
    if old.users == 0:
        bpy.data.curves.remove(old)
        data.name = name
    return ob


def _select(context, obs):
    for o in context.selected_objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    if obs:
        context.view_layer.objects.active = obs[-1]


def _crv(ob):
    c = curves_maya.read_spline(ob.data.splines[0], ob.matrix_world)
    return sm.Crv(c.cvs, c.knots, c.degree, c.periodic)


def _curves(context):
    return [o for o in selection_order(context) if o.type == 'CURVE' and o.data.splines]


def _surfaces(context):
    return [o for o in selection_order(context) if o.type == 'SURFACE' and o.data.splines]


def _object_mode(context):
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def _done(op, context, made):
    _select(context, made)
    results.result(op, " ".join(o.name for o in made))
    return {'FINISHED'}


DEGREES = [('1', "Linear", ""), ('3', "Cubic", "")]


class _SurfOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_CURVE', 'EDIT_SURFACE'}


# --- curves -> surfaces -------------------------------------------------------------------------------------------

@undo_steps.no_redo_panel
class ALLSET_OT_loft(_SurfOp, bpy.types.Operator):
    """Make a NURBS surface through the selected curves, in selection order (Maya Surfaces > Loft)"""
    bl_idname = "allset.loft"
    bl_label = "Loft"

    uniform: BoolProperty(name="Uniform", default=True, options={'SKIP_SAVE'})
    close: BoolProperty(name="Close", default=False, options={'SKIP_SAVE'})
    auto_reverse: BoolProperty(name="Auto reverse", default=True, options={'SKIP_SAVE'})
    degree: EnumProperty(name="Surface degree", items=DEGREES, default='3', options={'SKIP_SAVE'})
    section_spans: IntProperty(name="Section spans", default=1, min=1, max=1000, options={'SKIP_SAVE'})
    # Maya Output geometry (NURBS / Polygons; Bezier isn't made)
    output: EnumProperty(name="Output geometry", items=[('NURBS', "NURBS", ""), ('POLYGONS', "Polygons", "")],
                         default='NURBS', options={'SKIP_SAVE'})

    def execute(self, context):
        _object_mode(context)
        obs = _curves(context)
        if len(obs) < 2:
            self.report({'WARNING'}, "Invalid selection.  Need at least two curves.")
            return {'CANCELLED'}
        opts = {"uniform": self.uniform, "close": self.close, "degree": int(self.degree),
                "section_spans": self.section_spans, "auto_reverse": self.auto_reverse}
        s = _loft_surf(obs, opts)
        if self.output == 'POLYGONS':
            return _done(self, context, [new_loft_mesh(context, s, [o.name for o in obs], opts)])
        return _done(self, context, [new_surface(context, "loftedSurface", s, select=False)])


# --- Loft > Output geometry Polygons, with kit history -----------------------------------------------
# Maya:
# ``loft ... -po 1`` gives only a mesh ``loftedSurface1`` (history nurbsTessellate <- loft <- the curves; moving a CV
# moves the mesh), UVs = the surface's normalised (u, v): UV u across the curves, UV v along them. Maya's general
# tessellation (uNumber / vNumber 3, chord height 0.9) picks its own non-uniform rows; the kit cuts each span
# into TESS_ALONG x TESS_ACROSS uniform parameter steps, two triangles per cell (Maya polygonType 0 = triangles):
# 40 vertices / 56 triangles / 40 UVs on a two-curve loft, like Maya.

LOFT_KEY = "allset_loft"       # mesh object ID prop: {"curves", "opts", "sig"} while the mesh is the kit's result
TESS_ALONG = 7                 # segments per span along the curves (kit Surf U)
TESS_ACROSS = 4                # segments per span across the curves (kit Surf V)


def _loft_surf(obs, opts):
    return sm.loft([_crv(o) for o in obs], opts["uniform"], opts["close"], int(opts["degree"]),
                   opts["section_spans"], opts["auto_reverse"])


def _params(knots, degree, per_span):
    d0, d1 = sm.domain(knots, degree)
    brk = sorted({k for k in knots if d0 - 1e-12 <= k <= d1 + 1e-12})
    out = [brk[0]]
    for a, b in zip(brk, brk[1:]):
        out += [a + (b - a) * k / per_span for k in range(1, per_span + 1)]
    return out, d0, d1


def tessellate(s, along=TESS_ALONG, across=TESS_ACROSS):
    """(vertices, triangles, per-vertex UVs) of Surf ``s`` (world space): a grid on uniform parameter steps per span,
    UV = (normalised U, normalised V): u along the curves, v across them, like Maya's Loft menu item."""
    us, u0, u1 = _params(s.knots_u, s.degree_u, along)
    vs, v0, v1 = _params(s.knots_v, s.degree_v, across)
    nu = len(us)
    verts, uvs = [], []
    for v in vs:
        for u in us:
            verts.append(s.point(u, v))
            uvs.append(((u - u0) / ((u1 - u0) or 1.0), (v - v0) / ((v1 - v0) or 1.0)))
    tris = []
    for j in range(len(vs) - 1):
        for i in range(nu - 1):
            a, b = j * nu + i, j * nu + i + 1
            c, d = (j + 1) * nu + i + 1, (j + 1) * nu + i
            tris += [(a, b, c), (a, c, d)]
    return verts, tris, uvs


def _mesh_signature(me):
    import hashlib
    import numpy as np
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    return hashlib.md5(np.round(co, 4).tobytes() + str(len(me.polygons)).encode()).hexdigest()


def _write_mesh(me, s):
    verts, tris, uvs = tessellate(s)
    me.clear_geometry()
    compat.mesh_from_pydata(me, verts, [], tris)
    layer = me.uv_layers.new(name="map1")
    data = layer.data
    for poly in me.polygons:
        for li in poly.loop_indices:
            data[li].uv = uvs[me.loops[li].vertex_index]
    me.update()


def new_loft_mesh(context, s, curve_names, opts):
    """Mesh ``loftedSurfaceN`` of Surf ``s`` with UVs, recording its input curves (kit history, ``refresh_lofts``)."""
    me = bpy.data.meshes.new("loftedSurfaceShape")
    _write_mesh(me, s)
    ob = bpy.data.objects.new("loftedSurface", me)
    (context.collection or context.scene.collection).objects.link(ob)
    naming.apply_maya_name(ob, "loftedSurface")
    material.give_default(ob)
    ob[LOFT_KEY] = json.dumps({"curves": list(curve_names), "opts": opts, "sig": _mesh_signature(me)})
    return ob


def loft_record(ob):
    try:
        return json.loads(ob[LOFT_KEY]) if LOFT_KEY in ob else None
    except (ValueError, TypeError):
        return None


def refresh_lofts(scene=None, changed=None):
    """Rebuild every kit loft mesh whose input curves are in ``changed`` (None = all). A mesh edited away from the
    kit's result, or whose curves are gone, loses its record (Maya: the history link is broken). Returns the
    rebuilt objects."""
    scene = scene or bpy.context.scene
    done = []
    for ob in list(scene.objects):
        if ob is None or ob.type != 'MESH' or LOFT_KEY not in ob:
            continue
        rec = loft_record(ob)
        if rec is None:
            del ob[LOFT_KEY]
            continue
        if changed is not None and not set(rec["curves"]) & changed:
            continue
        curves = [bpy.data.objects.get(n) for n in rec["curves"]]
        if (any(c is None or c.type != 'CURVE' or not c.data.splines for c in curves)
                or _mesh_signature(ob.data) != rec["sig"] or ob.mode != 'OBJECT'):
            del ob[LOFT_KEY]
            continue
        try:
            s = _loft_surf(curves, rec["opts"])
        except (ValueError, ZeroDivisionError):
            continue
        _write_mesh(ob.data, s)
        rec["sig"] = _mesh_signature(ob.data)
        ob[LOFT_KEY] = json.dumps(rec)
        done.append(ob)
    return done


_pending = set()


def _tick():
    names = set(_pending)
    _pending.clear()
    try:
        refresh_lofts(bpy.context.scene, names)
    except (ReferenceError, AttributeError):
        pass
    return None


@bpy.app.handlers.persistent
def _on_depsgraph(scene, depsgraph):
    names = set()
    for up in depsgraph.updates:
        idb = up.id
        if isinstance(idb, bpy.types.Object) and idb.type == 'CURVE' and (up.is_updated_geometry
                                                                          or up.is_updated_transform):
            names.add(idb.original.name)
    if not names or not any(LOFT_KEY in o for o in scene.objects if o is not None and o.type == 'MESH'):
        return
    _pending.update(names)
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.0)


def register_history():
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister_history():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _pending.clear()


@undo_steps.no_redo_panel
class ALLSET_OT_revolve(_SurfOp, bpy.types.Operator):
    """Revolve each selected curve around an axis into a NURBS surface (Maya Surfaces > Revolve)"""
    bl_idname = "allset.revolve"
    bl_label = "Revolve"

    axis: EnumProperty(name="Axis preset", items=[(a, a, f"Maya {a} axis") for a in "XYZ"], default='Y',
                       options={'SKIP_SAVE'})
    pivot: EnumProperty(name="Pivot", items=[('OBJECT', "Object", "The curve's pivot"),
                                             ('PRESET', "Preset", "The pivot point below")],
                        default='OBJECT', options={'SKIP_SAVE'})
    pivot_point: FloatVectorProperty(name="Pivot point", size=3, default=(0.0, 0.0, 0.0), options={'SKIP_SAVE'})
    start_sweep: FloatProperty(name="Start sweep angle", default=0.0, min=0.0, max=360.0, options={'SKIP_SAVE'})
    end_sweep: FloatProperty(name="End sweep angle", default=360.0, min=0.0, max=360.0, options={'SKIP_SAVE'})
    degree: EnumProperty(name="Surface degree", items=DEGREES, default='3', options={'SKIP_SAVE'})
    segments: IntProperty(name="Segments", default=8, min=1, max=1000, options={'SKIP_SAVE'})

    def execute(self, context):
        _object_mode(context)
        obs = _curves(context)
        if not obs:
            self.report({'WARNING'}, "Select curves to revolve.")
            return {'CANCELLED'}
        if abs(self.end_sweep - self.start_sweep) < 1e-6:
            self.report({'WARNING'}, "The sweep angle must not be 0.")
            return {'CANCELLED'}
        k = units.maya_unit(context.scene)
        p = self.pivot_point
        preset = Vector((p[0], -p[2], p[1])) * k            # Maya point (Y up) -> Blender
        made = []
        for ob in obs:
            pivot = ob.matrix_world.translation if self.pivot == 'OBJECT' else preset
            s = sm.revolve(_crv(ob), MAYA_AXES[self.axis], tuple(pivot), self.start_sweep, self.end_sweep,
                           self.segments, int(self.degree))
            made.append(new_surface(context, "revolvedSurface", s, select=False))
        return _done(self, context, made)


@undo_steps.no_redo_panel
class ALLSET_OT_surface_extrude(_SurfOp, bpy.types.Operator):
    """Sweep the selected profile curves along the last selected curve (Maya Surfaces > Extrude)"""
    bl_idname = "allset.surface_extrude"
    bl_label = "Extrude"

    style: EnumProperty(name="Style", items=[('DISTANCE', "Distance", ""), ('FLAT', "Flat", ""),
                                             ('TUBE', "Tube", "")], default='TUBE', options={'SKIP_SAVE'})
    result_position: EnumProperty(name="Result position", items=[('PROFILE', "At profile", ""),
                                                                 ('PATH', "At path", "")],
                                  default='PROFILE', options={'SKIP_SAVE'})
    pivot: EnumProperty(name="Pivot", items=[('CLOSEST', "Closest end point", ""), ('COMPONENT', "Component", "")],
                        default='CLOSEST', options={'SKIP_SAVE'})
    direction: EnumProperty(name="Direction", items=[('NORMAL', "Profile normal", ""), ('X', "X axis", ""),
                                                     ('Y', "Y axis", ""), ('Z', "Z axis", "")],
                            default='NORMAL', options={'SKIP_SAVE'})
    length: FloatProperty(name="Extrude length", default=1.0, options={'SKIP_SAVE'})

    def execute(self, context):
        _object_mode(context)
        obs = _curves(context)
        made = []
        if self.style == 'DISTANCE':
            if not obs:
                self.report({'WARNING'}, "Select curves to extrude.")
                return {'CANCELLED'}
            d = None if self.direction == 'NORMAL' else MAYA_AXES[self.direction]
            for ob in obs:
                try:
                    s = sm.extrude_distance(_crv(ob), d, self.length * units.maya_unit(context.scene))
                except (ValueError, ZeroDivisionError):
                    self.report({'WARNING'}, f"{ob.name}: the profile has no normal; pick a direction.")
                    continue
                made.append(new_surface(context, "extrudedSurface", s, select=False))
        else:
            if len(obs) < 2:
                self.report({'WARNING'}, "Select the profile curves, then the path curve last.")
                return {'CANCELLED'}
            path = _crv(obs[-1])
            for ob in obs[:-1]:
                prof = _crv(ob)
                if self.style == 'FLAT':
                    s = sm.extrude_flat(prof, path)
                else:
                    s = sm.extrude_tube(prof, path, tuple(ob.matrix_world.translation),
                                        self.result_position == 'PATH', self.pivot == 'COMPONENT')
                made.append(new_surface(context, "extrudedSurface", s, select=False))
        if not made:
            return {'CANCELLED'}
        return _done(self, context, made)


def _near(c, p, samples=64):
    """Distance from point p to curve c (sampled)."""
    d0, d1 = sm.domain(c.knots, c.degree)
    from . import curves_math as cm
    best = None
    for k in range(samples + 1):
        q = cm.evaluate(c.cvs, c.knots, c.degree, d0 + (d1 - d0) * k / samples)
        dist = (Vector(q) - Vector(p)).length
        best = dist if best is None or dist < best else best
    return best


def birail_roles(curves):
    """(profile, rail1, rail2) from three curves by shape: the profile is the curve
    whose two ends lie nearest the other two curves, rail 1 the one at the profile's start; a rail is reversed when the
    profile sits nearer its end (Maya starts the surface at the rails' starts)."""
    best = None
    for i, prof in enumerate(curves):
        a, b = [c for j, c in enumerate(curves) if j != i]
        s0, s1 = prof.cvs[0], prof.cvs[-1]
        for r1, r2 in ((a, b), (b, a)):
            score = _near(r1, s0) + _near(r2, s1)
            if best is None or score < best[0]:
                best = (score, prof, r1, r2)
    _score, prof, r1, r2 = best

    def oriented(r):
        p = prof.cvs[0] if r is r1 else prof.cvs[-1]
        if (Vector(r.cvs[-1]) - Vector(p)).length < (Vector(r.cvs[0]) - Vector(p)).length:
            return sm._reverse_curve(r)
        return r
    return prof, oriented(r1), oriented(r2)


@undo_steps.no_redo_panel
class ALLSET_OT_birail1(_SurfOp, bpy.types.Operator):
    """Sweep a profile curve along two rail curves (Maya Surfaces > Birail > Birail 1 Tool: select the profile and the
    two rails; the kit tells them apart by where they touch)"""
    bl_idname = "allset.birail1"
    bl_label = "Birail 1 Tool"

    proportional: BoolProperty(name="Proportional", default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        _object_mode(context)
        obs = _curves(context)
        if len(obs) != 3:
            self.report({'WARNING'}, "Select one profile curve and two rail curves.")
            return {'CANCELLED'}
        prof, r1, r2 = birail_roles([_crv(o) for o in obs])
        try:
            s = sm.birail1(prof, r1, r2, self.proportional)
        except ValueError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        return _done(self, context, [new_surface(context, "singleProfileBirailSurface", s, select=False)])


@undo_steps.no_redo_panel
class ALLSET_OT_surface_boundary(_SurfOp, bpy.types.Operator):
    """Fill the space between three or four boundary curves (Maya Surfaces > Boundary / Square)"""
    bl_idname = "allset.surface_boundary"
    bl_label = "Boundary"

    kind: EnumProperty(name="Kind", items=[('BOUNDARY', "Boundary", ""), ('SQUARE', "Square", "")],
                       default='BOUNDARY', options={'SKIP_SAVE'})

    def execute(self, context):
        _object_mode(context)
        obs = _curves(context)
        if len(obs) not in ((3, 4) if self.kind == 'BOUNDARY' else (4,)):
            self.report({'WARNING'}, "Select four boundary curves." if self.kind == 'SQUARE'
                        else "Select three or four boundary curves.")
            return {'CANCELLED'}
        try:
            s = sm.boundary(sm.order_boundary([_crv(o) for o in obs]), square=self.kind == 'SQUARE')
        except ValueError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        base = "squareSurface" if self.kind == 'SQUARE' else "boundarySurface"
        return _done(self, context, [new_surface(context, base, s, select=False)])


# --- surface edits ----------------------------------------------------------------------------------------------

@undo_steps.no_redo_panel
class ALLSET_OT_surface_attach(_SurfOp, bpy.types.Operator):
    """Join two surfaces at their nearest edges into a new surface (Maya Surfaces > Attach; factory Blend 0.5)"""
    bl_idname = "allset.surface_attach"
    bl_label = "Attach Surfaces"

    method: EnumProperty(name="Attach method", items=[('CONNECT', "Connect", ""), ('BLEND', "Blend", "")],
                         default='BLEND', options={'SKIP_SAVE'})
    bias: FloatProperty(name="Blend bias", default=0.5, min=0.0, max=1.0, options={'SKIP_SAVE'})
    keep_originals: BoolProperty(name="Keep originals", default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        _object_mode(context)
        obs = _surfaces(context)
        if len(obs) != 2:
            self.report({'WARNING'}, "Select two surfaces to attach.")
            return {'CANCELLED'}
        first, second = obs
        try:
            s = sm.attach(read_surface(first), read_surface(second), self.method, self.bias)
        except ValueError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        ob = new_surface(context, f"{first.name}attachedSurface", s, select=False)
        if not self.keep_originals:
            for o in (first, second):
                bpy.data.objects.remove(o)
        return _done(self, context, [ob])


def _picked_lines(context):
    """(ob, Surf, direction, Maya parameters) from the CVs selected in edit mode: a selected CV row (same Blender row)
    = a V isoparm, a column = a U isoparm, at the Greville parameter of that line (Blender can't pick isoparms;
    like the curve Detach)."""
    ob = context.edit_object if context.mode == 'EDIT_SURFACE' else None
    if ob is None or ob.type != 'SURFACE':
        return None
    sp = ob.data.splines[0]
    nu = sp.point_count_u
    sel = [(k % nu, k // nu) for k, p in enumerate(sp.points) if p.select]
    _object_mode(context)
    sp = ob.data.splines[0]
    if not sel:
        return None
    s = read_surface(ob)
    grid = sm.blender_grid(_transform(s, ob.matrix_world.inverted()))
    blender = sm.from_blender_grid(_rows_of(sp), sp.order_u, sp.order_v, sp.use_cyclic_u, sp.use_cyclic_v,
                                   sp.use_endpoint_u, sp.use_endpoint_v, sp.use_bezier_u, sp.use_bezier_v)
    us, vs = {i for i, _ in sel}, {j for _, j in sel}
    direction = "V" if len(vs) == 1 and len(us) > 1 else "U"
    if direction == "U":
        g = sm.greville(blender.knots_u, blender.degree_u, blender.num_cvs[0])
        ts = [_back(grid["map_u"], g[i]) for i in sorted(us)]
    else:
        g = sm.greville(blender.knots_v, blender.degree_v, blender.num_cvs[1])
        ts = [_back(grid["map_v"], g[j]) for j in sorted(vs)]
    return ob, s, direction, ts, sel, blender, grid


def _back(brk, t):
    """Blender parameter -> Maya parameter (inverse of surfaces_math.map_param)."""
    return sm.map_param([(b, a) for a, b in brk], t)


def _interior(s, direction, ts):
    d0, d1 = s.domain_u() if direction == "U" else s.domain_v()
    return sorted({round(t, 9) for t in ts if d0 + 1e-6 < t < d1 - 1e-6})


@undo_steps.no_redo_panel
class ALLSET_OT_surface_detach(_SurfOp, bpy.types.Operator):
    """Split the surface at the isoparm through the selected CV row or column (Maya Surfaces > Detach)"""
    bl_idname = "allset.surface_detach"
    bl_label = "Detach Surfaces"

    keep_original: BoolProperty(name="Keep original", default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        picked = _picked_lines(context)
        if picked is None:
            self.report({'WARNING'}, "Select a row or column of surface CVs to detach at.")
            return {'CANCELLED'}
        ob, s, direction, ts, *_rest = picked
        ts = _interior(s, direction, ts)
        if not ts:
            self.report({'WARNING'}, "Pick CVs inside the surface, not on its border.")
            return {'CANCELLED'}
        pieces, cur = [], s
        for t in reversed(ts):           # cut from the far end: the first piece keeps the original parameters
            a, b = sm.detach(cur, direction, t)
            if b is None:                # periodic: opened at t
                cur = a
                continue
            pieces.insert(0, b)
            cur = a
        pieces.insert(0, cur)
        made = []
        if self.keep_original:
            first = new_surface(context, f"{ob.name}detachedSurface", pieces[0], select=False)
            made.append(first)
        else:
            replace_surface(context, ob, pieces[0])
            made.append(ob)
        for p in pieces[1:]:
            made.append(new_surface(context, f"{ob.name}detachedSurface", p, select=False))
        return _done(self, context, made)


@undo_steps.no_redo_panel
class ALLSET_OT_surface_insert_isoparm(_SurfOp, bpy.types.Operator):
    """Insert an isoparm at the selected CV row or column, keeping the shape (Maya Surfaces > Insert Isoparms)"""
    bl_idname = "allset.surface_insert_isoparm"
    bl_label = "Insert Isoparms"

    # Maya option box (Insert Isoparms Options defaults: At selection,
    # Increase, 1, Keep original off)
    between: BoolProperty(name="Between selections", default=False, options={'SKIP_SAVE'},
                          description="Insert evenly between the selected rows / columns instead of at them")
    increase: BoolProperty(name="Increase", default=True, options={'SKIP_SAVE'},
                           description="Multiplicity: on = increase it by the count, off = set it to the count")
    count: IntProperty(name="Count", default=1, min=1, max=7, options={'SKIP_SAVE'},
                       description="Multiplicity (at selection) or isoparms to insert (between selections)")
    keep_original: BoolProperty(name="Keep original", default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        picked = _picked_lines(context)
        if picked is None:
            self.report({'WARNING'}, "Select a row or column of surface CVs to insert an isoparm at.")
            return {'CANCELLED'}
        ob, s, direction, ts, *_rest = picked
        ts = _interior(s, direction, ts)
        if self.between:
            ts = between_params(ts, self.count)
            if not ts:
                self.report({'WARNING'}, "Select two rows or columns of surface CVs to insert isoparms between.")
                return {'CANCELLED'}
        if not ts:
            self.report({'WARNING'}, "Pick CVs inside the surface, not on its border.")
            return {'CANCELLED'}
        for t in ts:
            times = 1 if self.between else insert_times(s, direction, t, self.count, self.increase)
            if times:
                s = sm.insert_knot(s, direction, t, times)
        if self.keep_original:
            return _done(self, context, [new_surface(context, f"{ob.name}insertedSurface", s, select=False)])
        replace_surface(context, ob, s)
        return _done(self, context, [ob])


def between_params(ts, count):
    """Maya Insert location Between selections: ``count`` parameters evenly inside each pair of picked ones."""
    ts = sorted(ts)
    return [a + (b - a) * k / (count + 1) for a, b in zip(ts, ts[1:]) for k in range(1, count + 1)]


def insert_times(s, direction, t, count, increase):
    """How many knots to insert at ``t``: Increase = ``count``; Set = up to multiplicity ``count`` (nothing when it
    is already that high); never past the degree (a full-multiplicity knot)."""
    knots = s.knots_u if direction == "U" else s.knots_v
    degree = s.degree_u if direction == "U" else s.degree_v
    have = sum(1 for k in knots if abs(k - t) < 1e-9)
    want = have + count if increase else count
    return max(0, min(want, degree) - have)


def _span(knots, lo, hi):
    """Knot span [a, b] covering the parameters lo..hi."""
    k = sorted(set(knots))
    a = max((x for x in k if x <= lo + 1e-9), default=k[0])
    b = min((x for x in k if x >= hi - 1e-9 and x > a + 1e-9), default=k[-1])
    return a, b


@undo_steps.no_redo_panel
class ALLSET_OT_duplicate_nurbs_patch(_SurfOp, bpy.types.Operator):
    """Copy the surface patches around the selected CVs as a new surface (Maya Surfaces > Duplicate NURBS Patches)"""
    bl_idname = "allset.duplicate_nurbs_patch"
    bl_label = "Duplicate NURBS Patches"

    def execute(self, context):
        picked = _picked_lines(context)
        if picked is None:
            self.report({'WARNING'}, "Select surface CVs of the patches to duplicate.")
            return {'CANCELLED'}
        ob, s, _direction, _ts, sel, blender, grid = picked
        gu = sm.greville(blender.knots_u, blender.degree_u, blender.num_cvs[0])
        gv = sm.greville(blender.knots_v, blender.degree_v, blender.num_cvs[1])
        us = [_back(grid["map_u"], gu[i]) for i, _ in sel]
        vs = [_back(grid["map_v"], gv[j]) for _, j in sel]
        u0, u1 = _span(s.knots_u, min(us), max(us))
        v0, v1 = _span(s.knots_v, min(vs), max(vs))
        patch = sm.sub_patch(s, u0, u1, v0, v1)
        return _done(self, context, [new_surface(context, "duplicatedSurface", patch, select=False)])


class _ObjectSurfOp(_SurfOp):
    def _targets(self, context):
        if context.mode == 'EDIT_SURFACE':
            obs = [context.edit_object]
        else:
            obs = _surfaces(context)
        _object_mode(context)
        return [o for o in obs if o is not None and o.type == 'SURFACE' and o.data.splines]


@undo_steps.no_redo_panel
class ALLSET_OT_surface_reverse(_ObjectSurfOp, bpy.types.Operator):
    """Reverse the surface's U or V direction, or swap them (Maya Surfaces > Reverse Direction; factory U)"""
    bl_idname = "allset.surface_reverse"
    bl_label = "Reverse Surface Direction"

    direction: EnumProperty(name="Surface direction", items=[('U', "U", ""), ('V', "V", ""), ('SWAP', "Swap", ""),
                                                             ('BOTH', "Both", "")],
                            default='U', options={'SKIP_SAVE'})

    def execute(self, context):
        obs = self._targets(context)
        if not obs:
            self.report({'WARNING'}, "Select surfaces to reverse.")
            return {'CANCELLED'}
        for ob in obs:
            replace_surface(context, ob, sm.reverse(read_surface(ob), self.direction))
        return _done(self, context, obs)


REBUILD_DEGREES = [('1', "1 Linear", ""), ('2', "2", ""), ('3', "3 Cubic", ""), ('5', "5", ""), ('7', "7", "")]


@undo_steps.no_redo_panel
class ALLSET_OT_surface_rebuild(_ObjectSurfOp, bpy.types.Operator):
    """Rebuild the surface with uniform spans (default 4 x 4 spans, cubic; Maya Surfaces > Rebuild)"""
    bl_idname = "allset.surface_rebuild"
    bl_label = "Rebuild Surface"

    spans_u: IntProperty(name="Number of spans U", default=4, min=1, max=1000, options={'SKIP_SAVE'})
    spans_v: IntProperty(name="Number of spans V", default=4, min=1, max=1000, options={'SKIP_SAVE'})
    degree_u: EnumProperty(name="Degree U", items=REBUILD_DEGREES, default='3', options={'SKIP_SAVE'})
    degree_v: EnumProperty(name="Degree V", items=REBUILD_DEGREES, default='3', options={'SKIP_SAVE'})

    def execute(self, context):
        obs = self._targets(context)
        if not obs:
            self.report({'WARNING'}, "Select surfaces to rebuild.")
            return {'CANCELLED'}
        du = min(int(self.degree_u), MAX_ORDER - 1)
        dv = min(int(self.degree_v), MAX_ORDER - 1)
        for ob in obs:
            replace_surface(context, ob, sm.rebuild(read_surface(ob), self.spans_u, self.spans_v, du, dv))
        return _done(self, context, obs)


classes = (ALLSET_OT_loft, ALLSET_OT_revolve, ALLSET_OT_surface_extrude, ALLSET_OT_birail1, ALLSET_OT_surface_boundary,
           ALLSET_OT_surface_attach, ALLSET_OT_surface_detach, ALLSET_OT_surface_insert_isoparm,
           ALLSET_OT_duplicate_nurbs_patch, ALLSET_OT_surface_reverse, ALLSET_OT_surface_rebuild)
