# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent vertex identities and component bindings for modeling recipes."""

from fractions import Fraction
import base64
import hashlib
import json
import zlib

HIGH = '.allset_history_id_hi'
LOW = '.allset_history_id_lo'


def pack(selection):
    if selection.get('encoding') or sum(len(selection[field] or ()) for field in ('vertices','edges','faces')) < 4096:
        return selection
    payload = json.dumps(selection, separators=(',', ':')).encode()
    return dict(encoding='zlib-json', data=base64.b64encode(zlib.compress(payload, 1)).decode('ascii'),
                mode=selection['mode'], counts=selection['counts'])


def unpack(selection):
    if selection.get('encoding') == 'zlib-json':
        try:
            result = json.loads(zlib.decompress(base64.b64decode(selection['data'], validate=True)))
            if not isinstance(result, dict):
                raise ValueError('Component selection must be an object')
            return result
        except (ValueError, zlib.error, KeyError, TypeError) as error:
            raise ValueError('The saved component selection is damaged') from error
    return selection


class BindingError(ValueError):
    def __init__(self, node_id, name, message):
        self.node_id = node_id
        super().__init__(name+' needs its component selection rebound. '+message)


def layers(bm, reset=False):
    high, low = bm.verts.layers.int.get(HIGH), bm.verts.layers.int.get(LOW)
    if high is None or low is None or reset:
        high = high or bm.verts.layers.int.new(HIGH)
        low = low or bm.verts.layers.int.new(LOW)
        for index, vertex in enumerate(bm.verts, 1):
            vertex[high], vertex[low] = 0, index
    return high, low


def arrays(bm):
    import numpy as np
    handles = layers(bm)
    return [np.fromiter((vertex[layer] for vertex in bm.verts), dtype=np.int32, count=len(bm.verts))
            for layer in handles]


def write_arrays(mesh, values):
    for name, data in zip((HIGH, LOW), values):
        layer = mesh.attributes.get(name) or mesh.attributes.new(name, 'INT', 'POINT')
        layer.data.foreach_set('value', data)


def drop(ob):
    if ob.mode == 'EDIT':
        import bmesh
        bm = bmesh.from_edit_mesh(ob.data)
        for name in (HIGH, LOW):
            layer = bm.verts.layers.int.get(name)
            if layer is not None:
                bm.verts.layers.int.remove(layer)
    else:
        for name in (HIGH, LOW):
            layer = ob.data.attributes.get(name)
            if layer is not None:
                ob.data.attributes.remove(layer)


def identity(vertex, handles):
    return tuple(vertex[layer] for layer in handles)


def generated(node_id, role):
    payload = json.dumps((node_id, role), separators=(',', ':'), sort_keys=True).encode()
    value = hashlib.blake2b(payload, digest_size=8).digest()
    # A generated identity has a nonzero high word. Both layers use native signed int32.
    high = int.from_bytes(value[:4], 'little', signed=True) or -1
    return high, int.from_bytes(value[4:], 'little', signed=True)


def assign(vertex, handles, value):
    vertex[handles[0]], vertex[handles[1]] = value


def fraction(value):
    part = Fraction(value).limit_denominator(1000000)
    return part.numerator, part.denominator


def tag_generic(bm, spec, params, node_id, vertices):
    if not node_id or spec.kind in {'FACE', 'BRIDGE'}:
        return
    handles = layers(bm)
    topology = [(name, params[name]) for name in sorted(params)
                if spec.kinds.get(name) in {'INT', 'BOOL', 'ENUM'}]
    topology.append(('counts', (len(bm.verts), len(bm.edges), len(bm.faces))))
    bm.verts.index_update()
    for ordinal, vertex in enumerate(sorted(set(vertices), key=lambda item: item.index)):
        assign(vertex, handles, generated(node_id, (spec.kind, topology, ordinal)))


def capture(bm, selection):
    handles = layers(bm)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return dict(vertices=None if selection['vertices'] is None else
                [identity(bm.verts[index], handles) for index in selection['vertices']],
                edges=None if selection['edges'] is None else
                [[identity(vertex, handles) for vertex in bm.edges[index].verts]
                 for index, _vertices in selection['edges']],
                faces=None if selection['faces'] is None else
                [[identity(vertex, handles) for vertex in bm.faces[index].verts]
                 for index, _vertices in selection['faces']])


def resolve(bm, selection, node_id, name):
    """Resolve by identity and connectivity. A missing or ambiguous target remains explicit."""
    refs = selection['references']
    handles = layers(bm)
    sequences = (bm.verts, bm.edges, bm.faces)
    fields = ('vertices', 'edges', 'faces')
    fast = {}
    try:
        for field, sequence in zip(fields, sequences):
            entries = selection[field]
            if entries is None:
                fast[field] = None
                continue
            items = [sequence[entry if field == 'vertices' else entry[0]] for entry in entries]
            actual = ([identity(item, handles) for item in items] if field == 'vertices' else
                      [sorted(identity(vertex, handles) for vertex in item.verts) for item in items])
            expected = ([tuple(key) for key in refs[field]] if field == 'vertices' else
                        [sorted(tuple(key) for key in component) for component in refs[field]])
            if actual != expected:
                break
            fast[field] = items
        if len(fast) == 3:
            return fast
    except IndexError:
        pass
    requested = {tuple(value) for value in refs['vertices'] or ()}
    requested.update(tuple(value) for group in (refs['edges'], refs['faces'])
                     for component in group or () for value in component)
    found = {}
    ambiguous = set()
    for vertex in bm.verts:
        key = identity(vertex, handles)
        if key in requested:
            if key in found:
                ambiguous.add(key)
            found[key] = vertex
    if requested-found.keys() or ambiguous:
        raise BindingError(node_id, name, 'Some referenced vertices were removed or have ambiguous identities.')
    result = dict(vertices=None if refs['vertices'] is None else [found[tuple(key)] for key in refs['vertices']])
    edges = None if refs['edges'] is None else []
    for endpoints in refs['edges'] or ():
        edge = bm.edges.get(tuple(found[tuple(key)] for key in endpoints))
        if edge is None:
            raise BindingError(node_id, name, 'A referenced edge no longer exists.')
        edges.append(edge)
    faces = None if refs['faces'] is None else []
    for points in refs['faces'] or ():
        vertices = {found[tuple(key)] for key in points}
        candidates = [face for face in next(iter(vertices)).link_faces if set(face.verts) == vertices]
        if len(candidates) != 1:
            raise BindingError(node_id, name, 'A referenced face was removed, split or merged.')
        faces.append(candidates[0])
    result.update(edges=edges, faces=faces)
    return result
