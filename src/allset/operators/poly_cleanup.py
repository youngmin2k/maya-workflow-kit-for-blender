# SPDX-License-Identifier: GPL-3.0-or-later
"""Mesh > Cleanup... as Maya's command (#104): a menu leaf with an option box, not Blender's Clean Up submenu.

Maya 2022: the item runs ``cmds.polyCleanup`` with the Cleanup Options values
(factory: Operation 1 "Cleanup matching polygons", Scope selected objects,
history on, every criterion off, tolerances 1e-5; the meaning of
each option: the "Fix by Tesselation" boxes triangulate, the "Remove Geometry" boxes delete).

The kit finds the same components in bmesh: 4-sided / more-than-4-sided faces, concave faces (a reflex corner),
non-planar faces (a corner off the face plane by more than ``PLANAR_TOL`` of the face size — Maya's own tolerance is
not exposed), lamina faces (two faces on the same vertices), nonmanifold edges (more than two faces) and vertices,
zero-length edges, zero-area faces and zero-UV-area faces under their tolerances. Blender has no holed faces, so
"Faces with holes" never matches. Select matching polygons selects them in component mode; Cleanup triangulates /
collapses / deletes them.
"""

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty

from .. import results

PLANAR_TOL = 1e-3


def _corner_reflex(face):
    n = face.normal
    loops = face.loops
    for lp in loops:
        a = lp.vert.co - lp.link_loop_prev.vert.co
        b = lp.link_loop_next.vert.co - lp.vert.co
        if a.cross(b).dot(n) < -1e-12:
            return True
    return False


def _non_planar(face):
    if len(face.verts) < 4:
        return False
    c = face.calc_center_median()
    n = face.normal
    size = max((e.calc_length() for e in face.edges), default=0.0)
    return size > 0 and max(abs((v.co - c).dot(n)) for v in face.verts) > PLANAR_TOL * size


def _uv_area(face, uv):
    pts = [lp[uv].uv for lp in face.loops]
    area = 0.0
    for i, p in enumerate(pts):
        q = pts[(i + 1) % len(pts)]
        area += p.x * q.y - q.x * p.y
    return abs(area) / 2.0


def find(bm, o):
    """(faces to triangulate, lamina duplicates, zero-area faces, zero-map faces, zero-length edges, nonmanifold edges,
    nonmanifold verts) for the option dict ``o``."""
    bm.faces.ensure_lookup_table()
    tri, lamina, zero_f, zero_map = [], [], [], []
    seen = {}
    uv = bm.loops.layers.uv.active
    for f in bm.faces:
        k = len(f.verts)
        if ((o["quads"] and k == 4) or (o["nsided"] and k > 4) or (o["concave"] and k > 3 and _corner_reflex(f))
                or (o["nonplanar"] and _non_planar(f))):
            tri.append(f)
        if o["lamina"]:
            key = frozenset(v.index for v in f.verts)
            if key in seen:
                lamina.append(f)
            else:
                seen[key] = f
        if o["zero_face"] and f.calc_area() < o["face_tol"]:
            zero_f.append(f)
        if o["zero_map"] and uv is not None and _uv_area(f, uv) < o["map_tol"]:
            zero_map.append(f)
    zero_e = [e for e in bm.edges if o["zero_edge"] and e.calc_length() < o["edge_tol"]]
    nm_e = [e for e in bm.edges if o["nonmanifold"] and len(e.link_faces) > 2]
    nm_v = [v for v in bm.verts if o["nonmanifold"] and not v.is_manifold and v.link_faces]
    return tri, lamina, zero_f, zero_map, zero_e, nm_e, nm_v


def _ranges(ids):
    ids = sorted(set(ids))
    out, i = [], 0
    while i < len(ids):
        j = i
        while j + 1 < len(ids) and ids[j + 1] == ids[j] + 1:
            j += 1
        out.append(f"{ids[i]}" if i == j else f"{ids[i]}:{ids[j]}")
        i = j + 1
    return out


def _names(ob, faces, edges, verts):
    """Maya's return value: the affected components (``pCube1.f[0:2] pCube1.e[4]``)."""
    out = [f"{ob.name}.f[{r}]" for r in _ranges(f.index for f in faces)]
    out += [f"{ob.name}.e[{r}]" for r in _ranges(e.index for e in edges)]
    out += [f"{ob.name}.vtx[{r}]" for r in _ranges(v.index for v in verts)]
    return out


def clean(bm, o, ob):
    """Cleanup matching polygons on ``bm``; returns the affected components' Maya names (read before the edit)."""
    tri, lamina, zero_f, zero_map, zero_e, nm_e, nm_v = find(bm, o)
    hit = _names(ob, list({*tri, *lamina, *zero_f, *zero_map}), list({*zero_e, *nm_e}), list(nm_v))
    if lamina:
        bmesh.ops.delete(bm, geom=lamina, context='FACES_ONLY')
    zero_map = [f for f in zero_map if f.is_valid]
    if zero_map:
        bmesh.ops.delete(bm, geom=zero_map, context='FACES')
    zero_e = [e for e in zero_e if e.is_valid]
    if zero_e:
        bmesh.ops.collapse(bm, edges=zero_e)
    for f in zero_f:                           # a sliver collapses into an edge: its shortest edge goes
        if f.is_valid and f.calc_area() < o["face_tol"]:
            bmesh.ops.collapse(bm, edges=[min(f.edges, key=lambda e: e.calc_length())])
    nm_e = [e for e in nm_e if e.is_valid]
    if nm_e:
        bmesh.ops.split_edges(bm, edges=nm_e)
        if o["nonmanifold_type"] == 'NORMALS':
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    tri = [f for f in tri if f.is_valid and len(f.verts) > 3]
    if tri:
        bmesh.ops.triangulate(bm, faces=tri)
    return hit


def _select(bm, hit):
    faces, edges, verts = hit
    for seq in (bm.verts, bm.edges, bm.faces):
        for el in seq:
            el.select = False
    for el in (*faces, *edges, *verts):
        el.select = True
    bm.select_flush_mode()


def _meshes(context, all_meshes):
    if context.mode == 'EDIT_MESH':
        return list(context.objects_in_mode or [context.edit_object])
    if all_meshes:
        return [o for o in context.view_layer.objects if o is not None and o.type == 'MESH' and o.visible_get()]
    return [o for o in context.selected_objects if o.type == 'MESH']


class ALLSET_OT_poly_cleanup(bpy.types.Operator):
    """Clean up or select faces and edges that match the chosen criteria (Maya Mesh > Cleanup)"""
    bl_idname = "allset.poly_cleanup"
    bl_label = "Cleanup"
    bl_options = {'REGISTER', 'UNDO'}

    operation: EnumProperty(name="Operation", items=(('CLEANUP', "Cleanup matching polygons", ""),
                                                     ('SELECT', "Select matching polygons", "")), default='CLEANUP')
    all_meshes: BoolProperty(name="Apply to all polygonal objects", default=False)
    quads: BoolProperty(name="4-sided faces", default=False)
    nsided: BoolProperty(name="Faces with more than 4 sides", default=False)
    concave: BoolProperty(name="Concave faces", default=False)
    holes: BoolProperty(name="Faces with holes", default=False)
    nonplanar: BoolProperty(name="Non-planar faces", default=False)
    lamina: BoolProperty(name="Lamina faces", default=False)
    nonmanifold: BoolProperty(name="Nonmanifold geometry", default=False)
    nonmanifold_type: EnumProperty(name="Nonmanifold", items=(('NORMALS', "Normals and geometry", ""),
                                                              ('GEOMETRY', "Geometry only", "")), default='NORMALS')
    zero_edge: BoolProperty(name="Edges with zero length", default=False)
    edge_tol: FloatProperty(name="Length tolerance", default=1e-5, min=0.0, precision=6)
    zero_face: BoolProperty(name="Faces with zero geometry area", default=False)
    face_tol: FloatProperty(name="Area tolerance", default=1e-5, min=0.0, precision=6)
    zero_map: BoolProperty(name="Faces with zero map area", default=False)
    map_tol: FloatProperty(name="Map area tolerance", default=1e-5, min=0.0, precision=6)

    def _values(self):
        return {k: getattr(self, k) for k in ("quads", "nsided", "concave", "holes", "nonplanar", "lamina",
                                               "nonmanifold", "nonmanifold_type", "zero_edge", "edge_tol",
                                               "zero_face", "face_tol", "zero_map", "map_tol")}

    def execute(self, context):
        obs = _meshes(context, self.all_meshes)
        if not obs:
            self.report({'WARNING'}, "Select a polygon object to clean up.")
            return {'CANCELLED'}
        o = self._values()
        edit = context.mode == 'EDIT_MESH'
        names = []
        for ob in obs:
            if edit:
                bm = bmesh.from_edit_mesh(ob.data)
            else:
                bm = bmesh.new()
                bm.from_mesh(ob.data)
            if self.operation == 'SELECT':
                f = find(bm, o)
                hit = (list({*f[0], *f[1], *f[2], *f[3]}), list({*f[4], *f[5]}), list(f[6]))
                _select(bm, hit)
                names += _names(ob, *hit)
            else:
                names += clean(bm, o, ob)
            if edit:
                bmesh.update_edit_mesh(ob.data)
            else:
                bm.to_mesh(ob.data)
                bm.free()
                ob.data.update()
        if self.operation == 'SELECT' and not edit:
            # Maya shows the matching components: component mode on the meshes that have some
            for ob in context.view_layer.objects:
                if ob is not None:
                    ob.select_set(ob in obs)
            context.view_layer.objects.active = obs[0]
            bpy.ops.object.mode_set(mode='EDIT')
        if self.operation == 'SELECT':
            ts = context.tool_settings
            any_e = any(".e[" in n or ".vtx[" in n for n in names)
            any_f = any(".f[" in n for n in names)
            ts.mesh_select_mode = (False, any_e or not any_f, any_f)
        results.result(self, "Result: " + " ".join(names))
        return {'FINISHED'}


def run_window(context, v):
    """The Cleanup Options window's values -> the operator (option_windows spec)."""
    return bpy.ops.allset.poly_cleanup(
        'EXEC_DEFAULT', operation='SELECT' if v["operation"].startswith("Select") else 'CLEANUP',
        all_meshes=v["scope"] != "Apply to selected objects",
        quads=v["quads"], nsided=v["nsided"], concave=v["concave"], holes=v["holes"], nonplanar=v["nonplanar"],
        lamina=v["lamina"], nonmanifold=v["nonmanifold"],
        nonmanifold_type='NORMALS' if v["nonmanifold_type"] == "Normals and geometry" else 'GEOMETRY',
        zero_edge=v["zero_edge"], edge_tol=v["edge_tol"], zero_face=v["zero_face"], face_tol=v["face_tol"],
        zero_map=v["zero_map"], map_tol=v["map_tol"])


classes = (ALLSET_OT_poly_cleanup,)
