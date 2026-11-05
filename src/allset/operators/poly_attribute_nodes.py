# SPDX-License-Identifier: GPL-3.0-or-later
"""Editable Bridge and Add Divisions nodes on the kit's existing last-operation history."""

import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty

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


def bridge(bm, params, unit):
    face_edges = None
    if params.get('use_faces'):
        faces = {face for face in bm.faces if face.select}
        face_edges = {edge for face in faces for edge in face.edges
                      if sum(other in faces for other in edge.link_faces) == 1}
        bmesh.ops.delete(bm, geom=list(faces), context='FACES_ONLY')
    edges = [edge for edge in bm.edges if edge.select and edge.is_boundary]
    if face_edges is not None:
        edges = [edge for edge in face_edges if edge.is_valid and (edge.is_boundary or edge.is_wire)]
    if not edges:
        return []
    from .poly_maya import _ordered_loops
    loops = _ordered_loops(edges)
    if loops and (len(loops) != 2 or len(loops[0]) != len(loops[1])):
        return []
    before = set(bm.faces)
    old_edges = set(bm.edges)
    result = bmesh.ops.bridge_loops(bm, edges=edges, use_pairs=False,
                                    twist_offset=int(params['twist']))
    faces = result.get('faces', ())
    if not faces:
        return []
    if params['divisions']:
        connectors = list({edge for face in faces for edge in face.edges if edge not in old_edges})
        bmesh.ops.subdivide_edges(bm, edges=connectors, cuts=int(params['divisions']), use_grid_fill=True)
    return _select_new_faces(bm, before)


def subdivide(bm, params, unit):
    edges = [edge for edge in bm.edges if edge.select]
    if not edges:
        return []
    old_vertices = set(bm.verts)
    bmesh.ops.subdivide_edges(bm, edges=edges, cuts=int(params['divisions']),
                              smooth=float(params['smoothness']), use_grid_fill=True)
    bm.select_flush_mode()
    bm.normal_update()
    return [vertex for vertex in bm.verts if vertex not in old_vertices]


BRIDGE = extrude.add_spec(extrude.Spec(
    'BRIDGE', 'polyBridgeEdge', ('divisions', 'twist'), {'divisions': 'Divisions', 'twist': 'Twist'},
    {'divisions': 5, 'twist': 0, 'use_faces': False},
    {'divisions': 'INT', 'twist': 'INT', 'use_faces': 'BOOL'}, None, 'bridge_edit', bridge,
    hidden=('use_faces',), manip=('use_faces',)))
SUBDIVIDE = extrude.add_spec(extrude.Spec(
    'SUBDIVIDE', 'polySubdFace', ('divisions', 'smoothness'),
    {'divisions': 'Divisions', 'smoothness': 'Smoothness'}, {'divisions': 1, 'smoothness': 0.0},
    {'divisions': 'INT', 'smoothness': 'NONE'}, None, 'subdivide_edit', subdivide))


class _BridgeProperties:
    divisions: IntProperty(name='Divisions', default=5, min=0, soft_max=20, max=100)
    twist: IntProperty(name='Twist', default=0, min=-100, max=100)
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


class ALLSET_OT_subdivide_edit(_SubdivideProperties, extrude._ExtrudeEdit, bpy.types.Operator):
    bl_idname = 'allset.subdivide_edit'
    bl_label = 'polySubdFace'
    _op = 'subdivide_edit'


classes = (ALLSET_OT_bridge, ALLSET_OT_subdivide, ALLSET_OT_bridge_edit, ALLSET_OT_subdivide_edit)
