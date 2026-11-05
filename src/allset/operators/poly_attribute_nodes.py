# SPDX-License-Identifier: GPL-3.0-or-later
"""Editable Bridge and Add Divisions nodes on the kit's existing last-operation history."""

import math

import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty
from mathutils import Quaternion, Vector

from . import extrude, units


def _select_new_faces(bm, before):
    faces = [face for face in bm.faces if face not in before]
    for face in bm.faces:
        face.select_set(False)
    for face in faces:
        face.select_set(True)
    bm.select_flush_mode()
    bm.normal_update()
    return list({vertex for face in faces for vertex in face.verts})


def _border_groups(edges):
    adjacent = {}
    for edge in edges:
        for vertex in edge.verts:
            adjacent.setdefault(vertex, []).append(edge)
    if any(len(links) > 2 for links in adjacent.values()):
        return None
    groups = []
    remaining = set(adjacent)
    while remaining:
        pending = [min(remaining, key=lambda vertex: vertex.index)]
        group = set()
        while pending:
            vertex = pending.pop()
            if vertex in group:
                continue
            group.add(vertex)
            remaining.discard(vertex)
            pending.extend(edge.other_vert(vertex) for edge in adjacent[vertex])
        groups.append(group)
    if len(groups) != 2 or len(groups[0]) != len(groups[1]):
        return None
    closed = [all(len(adjacent[vertex]) == 2 for vertex in group) for group in groups]
    return groups if closed[0] == closed[1] else None


def _border_tangents(edges):
    """Outward surface co-normals provide the endpoint direction of the implied path."""
    tangents = {}
    for edge in edges:
        if len(edge.link_faces) != 1:
            continue
        face = edge.link_faces[0]
        direction = face.normal.cross(edge.verts[1].co-edge.verts[0].co)
        outward = (edge.verts[0].co+edge.verts[1].co)*.5-face.calc_center_median()
        if direction.dot(outward) < 0:
            direction.negate()
        direction.normalize()
        for vertex in edge.verts:
            tangents[vertex] = tangents.get(vertex, Vector())+direction
    return {vertex: direction.normalized() for vertex, direction in tangents.items()}


def _hermite(a, b, start, end, t):
    return (a*(2*t**3-3*t*t+1)+start*(t**3-2*t*t+t)
            +b*(-2*t**3+3*t*t)+end*(t**3-t*t))


def _shape_bridge(bm, connectors, groups, tangents, cuts, params):
    """Loft along cubic surface tangents, keeping both original border rings fixed."""
    pairs = []
    bm.verts.index_update()
    for edge in connectors:
        a, b = edge.verts
        if a not in groups[0]:
            a, b = b, a
        chord = b.co-a.co
        length = chord.length
        if length <= 1e-12:
            raise ValueError('Bridge borders contain coincident matching vertices')
        start = tangents.get(a, chord.normalized())*length
        end = -tangents.get(b, -chord.normalized())*length
        pairs.append((a.index, b.index, a.co.copy(), b.co.copy(), start, end))
    result = bmesh.ops.subdivide_edges(bm, edges=connectors, cuts=cuts, use_grid_fill=True)
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    adjacent = {}
    for edge in result['geom_split']:
        if isinstance(edge, bmesh.types.BMEdge):
            a, b = edge.verts
            adjacent.setdefault(a, []).append(b)
            adjacent.setdefault(b, []).append(a)
    rows = {}
    for first_index, last_index, a, b, start, end in pairs:
        first, last = bm.verts[first_index], bm.verts[last_index]
        previous, vertex = None, first
        for row in range(1, cuts+1):
            following = [other for other in adjacent.get(vertex, ()) if other != previous]
            if len(following) != 1 or following[0] == last:
                raise ValueError('Unable to identify the Bridge subdivision path')
            previous, vertex = vertex, following[0]
            t = row/(cuts+1)
            rows.setdefault(row, []).append((vertex, _hermite(a, b, start, end, t)))
        if last not in adjacent.get(vertex, ()):
            raise ValueError('Incomplete Bridge subdivision path')
    count = len(pairs)
    a = sum((pair[2] for pair in pairs), Vector())/count
    b = sum((pair[3] for pair in pairs), Vector())/count
    start = sum((pair[4] for pair in pairs), Vector())/count
    end = sum((pair[5] for pair in pairs), Vector())/count
    profiles = []
    for row, vertices in rows.items():
        t = row/(cuts+1)
        centre = sum((point for _vertex, point in vertices), Vector())/len(vertices)
        axis = (a*(6*t*t-6*t)+start*(3*t*t-4*t+1)
                +b*(-6*t*t+6*t)+end*(3*t*t-2*t))
        if axis.length_squared <= 1e-20:
            axis = b-a
        profiles.append((t, centre, axis.normalized(), [(vertex.index, point) for vertex, point in vertices]))
    _deform_bridge(bm, profiles, params)
    return profiles


def _deform_bridge(bm, profiles, params):
    bm.verts.ensure_lookup_table()
    for t, centre, axis, vertices in profiles:
        angle = math.radians(float(params.get('twist_angle', 0)))*math.sin(math.pi*t)
        rotation = Quaternion(axis.normalized(), angle) if axis.length_squared > 1e-20 else Quaternion()
        scale = 1+(float(params.get('taper', 1))-1)*4*t*(1-t)
        for index, point in vertices:
            bm.verts[index].co = centre+rotation @ ((point-centre)*scale)


def _bridge_topology(params):
    return (params.get('curve_type', 0), params['divisions'],
            params.get('bridge_offset', params.get('twist', 0)), bool(params.get('use_faces')))


def _preview_bridge(ob, record, params, unit):
    cache = record.preview_data
    if cache is None or cache['topology'] != _bridge_topology(params):
        return False
    bm = bmesh.from_edit_mesh(ob.data)
    if (len(bm.verts), len(bm.faces)) != cache['counts']:
        return False
    _deform_bridge(bm, cache['profiles'], params)
    bm.normal_update()
    bmesh.update_edit_mesh(ob.data, loop_triangles=True, destructive=False)
    record.params = dict(params)
    return True


def bridge(bm, params, unit):
    profiles = None
    face_edges = None
    if params.get('use_faces'):
        faces = {face for face in bm.faces if face.select}
        face_edges = {edge for face in faces for edge in face.edges
                      if sum(other in faces for other in edge.link_faces) == 1}
    edges = [edge for edge in bm.edges if edge.select]
    if face_edges is not None:
        edges = list(face_edges)
    elif any(not (edge.is_boundary or edge.is_wire) for edge in edges):
        return []
    if not edges:
        return []
    bm.verts.index_update()
    groups = _border_groups(edges)
    if groups is None:
        return []
    offset = int(params.get('bridge_offset', params.get('twist', 0)))
    if offset and len(edges) != sum(map(len, groups)):
        raise ValueError('Bridge Offset requires two closed borders')
    if face_edges is not None:
        bmesh.ops.delete(bm, geom=list(faces), context='FACES_ONLY')
    bm.normal_update()
    tangents = _border_tangents(edges) if params.get('curve_type', 0) else {}
    before = set(bm.faces)
    old_edges = set(bm.edges)
    result = bmesh.ops.bridge_loops(bm, edges=edges, use_pairs=False,
                                    twist_offset=offset)
    faces = result.get('faces', ())
    if not faces:
        return []
    if params['divisions']:
        connectors = list({edge for face in faces for edge in face.edges if edge not in old_edges})
        if params.get('curve_type', 0):
            profiles = _shape_bridge(bm, connectors, groups, tangents, int(params['divisions']), params)
        else:
            bmesh.ops.subdivide_edges(bm, edges=connectors, cuts=int(params['divisions']), use_grid_fill=True)
    tracked = _select_new_faces(bm, before)
    cache = (dict(topology=_bridge_topology(params), profiles=profiles, counts=(len(bm.verts), len(bm.faces)))
             if profiles is not None else None)
    return extrude.BuildResult(tracked, cache)


def subdivide(bm, params, unit):
    edges = [edge for edge in bm.edges if edge.select]
    if not edges:
        return []
    old_vertices = set(bm.verts)
    result = bmesh.ops.subdivide_edges(bm, edges=edges, cuts=int(params['divisions']),
                                      smooth=float(params['smoothness']), use_grid_fill=True)
    # Native subdivision can leave selected edges referencing unselected new vertices.
    # Normalize the affected selection before recording it, as Blender's undo reader does.
    for element in result['geom']:
        if isinstance(element, (bmesh.types.BMEdge, bmesh.types.BMFace)) and element.select:
            element.select_set(True)
    bm.select_flush_mode()
    bm.normal_update()
    return [vertex for vertex in bm.verts if vertex not in old_vertices]


BRIDGE = extrude.add_spec(extrude.Spec(
    'BRIDGE', 'polyBridgeEdge', ('curve_type', 'divisions', 'twist_angle', 'taper', 'bridge_offset'),
    {'curve_type': 'Bridge Type', 'divisions': 'Divisions', 'twist_angle': 'Twist',
     'taper': 'Taper', 'bridge_offset': 'Bridge Offset'},
    {'curve_type': 0, 'divisions': 5, 'twist_angle': 0.0, 'taper': 1.0, 'bridge_offset': 0, 'use_faces': False},
    {'curve_type': 'ENUM', 'divisions': 'INT', 'twist_angle': 'ROTATION', 'taper': 'NONE',
     'bridge_offset': 'INT', 'use_faces': 'BOOL'}, None, 'bridge_edit', bridge,
    hidden=('use_faces',), manip=('use_faces',),
    choices={'curve_type': (('Linear path', 'Smooth path'), (0, 1))},
    enabled=lambda params, name: name not in {'twist_angle', 'taper'} or bool(params.get('curve_type', 0)),
    atomic=True, preview=_preview_bridge))
SUBDIVIDE = extrude.add_spec(extrude.Spec(
    'SUBDIVIDE', 'polySubdFace', ('divisions', 'smoothness'),
    {'divisions': 'Divisions', 'smoothness': 'Smoothness'}, {'divisions': 1, 'smoothness': 0.0},
    {'divisions': 'INT', 'smoothness': 'NONE'}, None, 'subdivide_edit', subdivide))


class _BridgeProperties:
    curve_type: IntProperty(name='Bridge Type', default=0, min=0, max=1)
    divisions: IntProperty(name='Divisions', default=5, min=0, soft_max=20, max=100)
    twist_angle: FloatProperty(name='Twist', default=0, soft_min=-360, soft_max=360,
                               description='Twist of the bridging region in degrees')
    taper: FloatProperty(name='Taper', default=1, min=0, soft_max=3)
    bridge_offset: IntProperty(name='Bridge Offset', default=0, min=-100, max=100)
    twist: IntProperty(name='Legacy Bridge Offset', default=0, min=-100, max=100, options={'HIDDEN', 'SKIP_SAVE'})
    use_faces: BoolProperty(name='Bridge Faces', default=False, options={'HIDDEN'})


class _SubdivideProperties:
    divisions: IntProperty(name='Divisions', default=1, min=1, soft_max=10, max=100)
    smoothness: FloatProperty(name='Smoothness', default=0, min=0, max=1)


def create(context, spec, params):
    done = 0
    for ob in context.objects_in_mode_unique_data:
        if ob.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(ob.data)
        try:
            record = extrude.record_new(context, ob, bm, spec, params, units.maya_unit(context.scene))
        except (ValueError, RuntimeError):
            continue
        done += record is not None
    return {'FINISHED'} if done else {'CANCELLED'}


class ALLSET_OT_bridge(_BridgeProperties, bpy.types.Operator):
    bl_idname = 'allset.bridge'
    bl_label = 'Bridge'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        params = {field: getattr(self, field) for field in BRIDGE.all_fields}
        if self.properties.is_property_set('twist'):
            params['bridge_offset'] = self.twist
        params['use_faces'] = bool(context.scene.tool_settings.mesh_select_mode[2])
        return create(context, BRIDGE, params)


class ALLSET_OT_subdivide(_SubdivideProperties, bpy.types.Operator):
    bl_idname = 'allset.subdivide'
    bl_label = 'Add Divisions'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        return create(context, SUBDIVIDE, {field: getattr(self, field) for field in SUBDIVIDE.fields})


class ALLSET_OT_bridge_edit(_BridgeProperties, extrude._ExtrudeEdit, bpy.types.Operator):
    bl_idname = 'allset.bridge_edit'
    bl_label = 'polyBridgeEdge'
    _op = 'bridge_edit'

    def execute(self, context):
        if self.properties.is_property_set('twist'):
            self.bridge_offset = self.twist
        return extrude._ExtrudeEdit.execute(self, context)


class ALLSET_OT_subdivide_edit(_SubdivideProperties, extrude._ExtrudeEdit, bpy.types.Operator):
    bl_idname = 'allset.subdivide_edit'
    bl_label = 'polySubdFace'
    _op = 'subdivide_edit'


classes = (ALLSET_OT_bridge, ALLSET_OT_subdivide, ALLSET_OT_bridge_edit, ALLSET_OT_subdivide_edit)
