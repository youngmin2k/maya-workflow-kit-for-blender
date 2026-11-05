# SPDX-License-Identifier: GPL-3.0-or-later
"""Editable Bridge and Add Divisions nodes in the kit's persistent modeling history."""

import math

import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty
from mathutils import Vector

from . import bridge_curve, extrude, units


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


def _border_tangents(edges, excluded=()):
    """Outward surface co-normals provide the endpoint direction of the implied path."""
    tangents = {}
    for edge in edges:
        faces = [face for face in edge.link_faces if face not in excluded]
        if len(faces) != 1:
            continue
        face = faces[0]
        direction = face.normal.cross(edge.verts[1].co-edge.verts[0].co)
        outward = (edge.verts[0].co+edge.verts[1].co)*.5-face.calc_center_median()
        if direction.dot(outward) < 0:
            direction.negate()
        direction.normalize()
        for vertex in edge.verts:
            tangents[vertex] = tangents.get(vertex, Vector())+direction
    return {vertex: direction.normalized() for vertex, direction in tangents.items()}


def path_source(bm, params):
    faces = {face for face in bm.faces if face.select} if params.get('use_faces') else set()
    edges = ([edge for edge in bm.edges if edge.select] if not faces else
             list({edge for face in faces for edge in face.edges
                   if sum(other in faces for other in edge.link_faces) == 1}))
    bm.verts.index_update()
    groups = _border_groups(edges)
    if groups is None:
        return None
    a, b = [sum((v.co for v in group), Vector())/len(group) for group in groups]
    chord = b-a
    if chord.length_squared <= 1e-16:
        return None
    tangents = _border_tangents(edges, faces)
    start = sum((tangents.get(v, chord.normalized()) for v in groups[0]), Vector()).normalized()
    end = -sum((tangents.get(v, -chord.normalized()) for v in groups[1]), Vector()).normalized()
    return dict(a=a, b=b, start=start*chord.length*1.25, end=end*chord.length*1.25, rows=[])


def _shape_bridge(bm, connectors, groups, source, cuts, params, ob):
    """Track native longitudinal rows independently of their path and profile parameters."""
    pairs = []
    bm.verts.index_update()
    for edge in connectors:
        a, b = edge.verts
        if a not in groups[0]:
            a, b = b, a
        if (b.co-a.co).length <= 1e-12:
            raise ValueError('Bridge borders contain coincident matching vertices')
        pairs.append((a.index, b.index, a.co.copy(), b.co.copy()))
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
    for first_index, last_index, a, b in pairs:
        first, last = bm.verts[first_index], bm.verts[last_index]
        previous, vertex = None, first
        for row in range(1, cuts+1):
            following = [other for other in adjacent.get(vertex, ()) if other != previous]
            if len(following) != 1 or following[0] == last:
                raise ValueError('Unable to identify the Bridge subdivision path')
            previous, vertex = vertex, following[0]
            t = row/(cuts+1)
            rows.setdefault(row, []).append((vertex.index, a, b))
        if last not in adjacent.get(vertex, ()):
            raise ValueError('Incomplete Bridge subdivision path')
    source['rows'] = [(row/(cuts+1), vertices) for row, vertices in sorted(rows.items())]
    bridge_curve.deform(bm.verts, source, params, ob)
    return source


def _smooth_bridge(mesh, cache, params):
    angle = math.radians(float(params.get('smoothing_angle', 180)))
    if isinstance(mesh, bmesh.types.BMesh):
        faces = cache.get('bm_faces')
        edges = cache.get('bm_edges')
        if faces is None or edges is None or not all(element.is_valid for element in faces+edges):
            mesh.faces.ensure_lookup_table()
            mesh.edges.ensure_lookup_table()
            faces = [mesh.faces[index] for index in cache['faces']]
            edges = [mesh.edges[index] for index, _faces in cache['edges']]
            cache['bm'], cache['bm_faces'], cache['bm_edges'] = mesh, faces, edges
        vertices = set()
        for face in faces:
            face.normal_update()
            face.smooth = True
            vertices.update(face.verts)
        for vertex in vertices:
            vertex.normal_update()
        for edge in edges:
            edge.smooth = edge.calc_face_angle(math.pi) <= angle+1e-7
    else:
        mesh.update()
        for index in cache['faces']:
            mesh.polygons[index].use_smooth = True
        for index, faces in cache['edges']:
            value = (mesh.polygons[faces[0]].normal.angle(mesh.polygons[faces[1]].normal, math.pi)
                     if len(faces) == 2 else math.pi)
            mesh.edges[index].use_edge_sharp = value > angle+1e-7


def _bridge_topology(params):
    return (params['divisions'],
            params.get('bridge_offset', params.get('twist', 0)), bool(params.get('use_faces')))


def _preview_bridge(ob, record, params, unit):
    cache = record.preview_data
    if cache is None or cache['topology'] != _bridge_topology(params):
        return False
    bm = bmesh.from_edit_mesh(ob.data) if ob.mode == 'EDIT' else ob.data
    counts = ((len(bm.verts), len(bm.faces)) if ob.mode == 'EDIT'
              else (len(bm.vertices), len(bm.polygons)))
    if counts != cache['counts']:
        return False
    vertices = bm.verts if ob.mode == 'EDIT' else bm.vertices
    bridge_curve.deform(vertices, cache['profiles'], params, ob)
    _smooth_bridge(bm, cache, params)
    if ob.mode == 'EDIT':
        bmesh.update_edit_mesh(ob.data, loop_triangles=True, destructive=False)
    else:
        ob.data.update()
    record.params = dict(params)
    return True


def bridge(bm, params, unit, ob=None):
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
    source = path_source(bm, params)
    if source is None:
        return []
    bridge_curve.ramp_points(params.get('taper_curve', bridge_curve.RAMP_DEFAULT))
    offset = int(params.get('bridge_offset', params.get('twist', 0)))
    if offset and len(edges) != sum(map(len, groups)):
        raise ValueError('Bridge Offset requires two closed borders')
    if face_edges is not None:
        bmesh.ops.delete(bm, geom=list(faces), context='FACES_ONLY')
    bm.normal_update()
    before = set(bm.faces)
    old_edges = set(bm.edges)
    result = bmesh.ops.bridge_loops(bm, edges=edges, use_pairs=False,
                                    twist_offset=offset)
    faces = result.get('faces', ())
    if not faces:
        return []
    if params['divisions']:
        connectors = list({edge for face in faces for edge in face.edges if edge not in old_edges})
        profiles = _shape_bridge(bm, connectors, groups, source, int(params['divisions']), params, ob)
    tracked = _select_new_faces(bm, before)
    bm.edges.index_update()
    bm.faces.index_update()
    new_faces = [face for face in bm.faces if face not in before]
    touched = {edge for face in new_faces for edge in face.edges}
    cache = dict(topology=_bridge_topology(params), profiles=profiles, counts=(len(bm.verts), len(bm.faces)),
                 faces=[face.index for face in new_faces],
                 edges=[(edge.index, [face.index for face in edge.link_faces]) for edge in touched],
                 bm=bm, bm_faces=new_faces, bm_edges=list(touched))
    _smooth_bridge(bm, cache, params)
    return extrude.BuildResult(tracked, cache if profiles is not None else None)


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
    'BRIDGE', 'polyBridgeEdge', ('curve_type', 'divisions', 'twist_angle', 'taper', 'bridge_offset',
                               'direction', 'source_direction', 'target_direction', 'smoothing_angle'),
    {'curve_type': 'Bridge Type', 'divisions': 'Divisions', 'twist_angle': 'Twist',
     'taper': 'Taper', 'bridge_offset': 'Bridge Offset', 'direction': 'Direction',
     'source_direction': 'Source', 'target_direction': 'Target', 'smoothing_angle': 'Smoothing Angle'},
    {'curve_type': 0, 'divisions': 5, 'twist_angle': 0.0, 'taper': 1.0, 'bridge_offset': 0, 'use_faces': False,
     'direction': 0, 'source_direction': 0, 'target_direction': 0, 'smoothing_angle': 30.0,
     'input_curve': '', 'taper_curve': bridge_curve.RAMP_DEFAULT},
    {'curve_type': 'ENUM', 'divisions': 'INT', 'twist_angle': 'ROTATION', 'taper': 'NONE',
     'bridge_offset': 'INT', 'use_faces': 'BOOL', 'direction': 'ENUM', 'source_direction': 'ENUM',
     'target_direction': 'ENUM', 'smoothing_angle': 'ROTATION', 'input_curve': 'STRING', 'taper_curve': 'STRING'},
    None, 'bridge_edit', bridge, hidden=('use_faces', 'input_curve', 'taper_curve'),
    manip=('use_faces', 'input_curve', 'taper_curve'),
    choices={'curve_type': (('Linear path', 'Smooth path', 'Smooth path + curve'), (0, 1, 2)),
             'direction': (('Automatic', 'Manual'), (0, 1)),
             'source_direction': (('Along normal', 'Opposite normal'), (0, 1)),
             'target_direction': (('Along normal', 'Opposite normal'), (0, 1))},
    enabled=lambda params, name: ((name not in {'twist_angle', 'taper'} or bool(params.get('curve_type', 0)))
                                  and (name not in {'source_direction', 'target_direction'}
                                       or bool(params.get('direction', 0)))),
    atomic=True, preview=_preview_bridge, with_object=True,
    prepare=bridge_curve.prepare, cleanup=bridge_curve.cleanup))
SUBDIVIDE = extrude.add_spec(extrude.Spec(
    'SUBDIVIDE', 'polySubdFace', ('divisions', 'smoothness'),
    {'divisions': 'Divisions', 'smoothness': 'Smoothness'}, {'divisions': 1, 'smoothness': 0.0},
    {'divisions': 'INT', 'smoothness': 'NONE'}, None, 'subdivide_edit', subdivide))


class _BridgeProperties:
    curve_type: IntProperty(name='Bridge Type', default=0, min=0, max=2)
    divisions: IntProperty(name='Divisions', default=5, min=0, soft_max=20, max=100)
    twist_angle: FloatProperty(name='Twist', default=0, soft_min=-360, soft_max=360,
                               description='Twist of the bridging region in degrees')
    taper: FloatProperty(name='Taper', default=1, min=0, soft_max=3)
    bridge_offset: IntProperty(name='Bridge Offset', default=0, min=-100, max=100)
    twist: IntProperty(name='Legacy Bridge Offset', default=0, min=-100, max=100, options={'HIDDEN', 'SKIP_SAVE'})
    use_faces: BoolProperty(name='Bridge Faces', default=False, options={'HIDDEN'})
    direction: IntProperty(name='Direction', default=0, min=0, max=1)
    source_direction: IntProperty(name='Source', default=0, min=0, max=1)
    target_direction: IntProperty(name='Target', default=0, min=0, max=1)
    smoothing_angle: FloatProperty(name='Smoothing Angle', default=30, min=0, max=180)
    input_curve: StringProperty(name='Path Curve', options={'SKIP_SAVE'})
    taper_curve: StringProperty(name='Taper Curve', default=bridge_curve.RAMP_DEFAULT, options={'SKIP_SAVE'})


class _SubdivideProperties:
    divisions: IntProperty(name='Divisions', default=1, min=1, soft_max=10, max=100)
    smoothness: FloatProperty(name='Smoothness', default=0, min=0, max=1)


def create(context, spec, params):
    done = 0
    for ob in context.objects_in_mode_unique_data:
        if ob.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(ob.data)
        values = dict(params)
        try:
            if spec.prepare is not None:
                values = spec.prepare(context, ob, None, values)
            record = extrude.record_new(context, ob, bm, spec, values, units.maya_unit(context.scene))
        except (ValueError, RuntimeError):
            if spec.cleanup is not None:
                spec.cleanup(ob, params, values)
            continue
        if record is None and spec.cleanup is not None:
            spec.cleanup(ob, params, values)
        if record is not None and spec is BRIDGE:
            from . import display
            display.ensure_maya_normals(ob)
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
        from ..ui.node_attributes import ModelingNode
        objects = context.objects_in_mode_unique_data if context.mode == 'EDIT_MESH' else [context.active_object]
        done = 0
        for ob in objects:
            rec = extrude.current(ob) if context.mode == 'EDIT_MESH' else extrude.object_record(ob)
            if rec is None or rec.spec is not BRIDGE:
                continue
            node = ModelingNode(ob, rec)
            try:
                node.commit(context, extrude._params(self, BRIDGE))
                node.finish()
                done += 1
            except (ValueError, RuntimeError) as error:
                self.report({'WARNING'}, str(error))
        return {'FINISHED'} if done else {'CANCELLED'}


class ALLSET_OT_subdivide_edit(_SubdivideProperties, extrude._ExtrudeEdit, bpy.types.Operator):
    bl_idname = 'allset.subdivide_edit'
    bl_label = 'polySubdFace'
    _op = 'subdivide_edit'


classes = (ALLSET_OT_bridge, ALLSET_OT_subdivide, ALLSET_OT_bridge_edit, ALLSET_OT_subdivide_edit)
