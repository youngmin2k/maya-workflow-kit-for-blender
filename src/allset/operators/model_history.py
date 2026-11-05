# SPDX-License-Identifier: GPL-3.0-or-later
"""Versioned modeling recipes with one immutable input mesh and transactional replay."""

from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import uuid4

import bmesh
import bpy

KEY = 'allset_model_history'
BASE = 'allset_model_history_base'
VERSION = 1
OWNED = 'allset_history_input'
_cache = {}
_active = {}
_busy = set()
_valid = {}


def read(ob):
    if not isinstance(ob, bpy.types.Object) or ob.type != 'MESH':
        return None
    text = ob.data.get(KEY)
    if not isinstance(text, str):
        return None
    uid = ob.data.session_uid
    cached = _cache.get(uid)
    if cached is not None and cached[0] == text:
        return cached[1]
    _valid.pop(uid, None)
    try:
        data = json.loads(text)
        if (data['version'] != VERSION or not isinstance(data['nodes'], list)
                or not data['nodes'] or not isinstance(ob.data.get(BASE), bpy.types.Mesh)):
            return None
        from . import extrude
        for node in data['nodes']:
            if (node['kind'] not in extrude.SPECS or not isinstance(node['params'], dict)
                    or not isinstance(node['selection'], dict)):
                return None
    except (KeyError, TypeError, ValueError):
        return None
    _cache[uid] = text, data
    return data


def write(ob, data):
    text = json.dumps(data, separators=(',', ':'), allow_nan=False)
    ob.data[KEY] = text
    _cache[ob.data.session_uid] = text, data
    _valid[ob.data.session_uid] = True


def token(data):
    upstream = [(node['id'], node['kind'], node['params'], node['unit'], node['input_hash'])
                for node in data['nodes'][:-1]]
    return json.dumps((data.get('creation'), upstream), sort_keys=True, separators=(',', ':'))


def _selection(bm):
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    vertices = [v for v in bm.verts if v.select]
    edges = [e for e in bm.edges if e.select]
    faces = [f for f in bm.faces if f.select]
    return dict(vertices=None if len(vertices) == len(bm.verts) else [v.index for v in vertices],
                edges=None if len(edges) == len(bm.edges) else [[e.index, [v.index for v in e.verts]] for e in edges],
                faces=None if len(faces) == len(bm.faces) else [[f.index, [v.index for v in f.verts]] for f in faces],
                counts=[len(bm.verts), len(bm.edges), len(bm.faces)], mode=sorted(bm.select_mode))


def _select(bm, selection, name):
    from . import extrude
    bm.select_mode = set(selection['mode'])
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    counts = [len(bm.verts), len(bm.edges), len(bm.faces)]
    # References to generated components need an explicit rebind after upstream topology changes.
    if counts != selection['counts']:
        raise ValueError(name+' needs its component selection rebound after the upstream topology change')
    for sequence, entries in ((bm.edges, selection['edges']), (bm.faces, selection['faces'])):
        for index, vertices in entries or ():
            if index >= len(sequence) or set(vertices) != {v.index for v in sequence[index].verts}:
                raise ValueError(name+' has an incompatible component reference')
    extrude.deselect_all(bm)
    for index in selection['vertices'] or ():
        if not 0 <= index < len(bm.verts):
            raise ValueError(name+' references a missing vertex')
        bm.verts[index].select = True
    for sequence, entries in ((bm.edges, selection['edges']), (bm.faces, selection['faces'])):
        for index, _vertices in entries or ():
            sequence[index].select = True
    for sequence, entries in ((bm.verts, selection['vertices']), (bm.edges, selection['edges']),
                              (bm.faces, selection['faces'])):
        if entries is None:
            for element in sequence:
                element.select = True


def _build(bm, spec, params, unit, ob):
    from . import extrude
    if spec is extrude.FACE:
        caps, moved = extrude.extrude(bm, [f for f in bm.faces if f.select], unit=unit,
                                      **params, **extrude.mesh_axes(ob))
        return caps, moved
    values = {key: params[key] for key in spec.fields+spec.hidden if key in params}
    tracked = spec.build(bm, values, unit, **({'ob': ob} if spec.with_object else {}))
    if not tracked:
        raise ValueError(spec.node_type+' did not produce valid geometry')
    return tracked, None


def append(ob, rec, unit):
    """Record the already successful operation. Existing unsupported edits become a new input base."""
    from . import extrude
    data = read(ob)
    snapshot = bpy.data.meshes.new('.allset_history_input')
    try:
        rec.pre.to_mesh(snapshot)
        input_hash = extrude.mesh_coords_hash(snapshot)
        replacing = (data is not None and data['nodes'][-1]['name'] == rec.name
                     and data['nodes'][-1].get('input_hash') == input_hash)
        if data is None or (data.get('result_hash') != input_hash and not replacing):
            from . import prim_history, prim_shapes
            creation = prim_history.node_dict(ob.data)
            if (creation is not None and creation['type'] in prim_shapes.POLY
                    and prim_history._sig_mesh(snapshot) == creation.get('sig')):
                creation['id'] = uuid4().hex
            else:
                creation = None
            for material in ob.data.materials:
                snapshot.materials.append(material)
            previous = ob.data.get(BASE)
            snapshot[OWNED] = True
            ob.data[BASE] = snapshot
            if previous is not None and previous.users == 0 and previous.get(OWNED):
                bpy.data.meshes.remove(previous)
            snapshot.name = '.'+ob.data.name+'_modelInput'
            snapshot = None
            data = dict(version=VERSION, nodes=[], creation=creation)
        else:
            data = deepcopy(data)
        node = dict(id=uuid4().hex, name=rec.name, kind=rec.spec.kind, params=dict(rec.params),
                    selection=_selection(rec.pre), unit=unit, input_hash=input_hash)
        # Re-running an operator on the same original input updates its node.
        if data['nodes'] and data['nodes'][-1]['name'] == rec.name:
            node['id'] = data['nodes'][-1]['id']
            data['nodes'][-1] = node
        else:
            data['nodes'].append(node)
        data['result_hash'] = rec.states[-1][3]
        write(ob, data)
        rec.history_id = node['id']
        rec.history_token = token(data)
        _active[ob.data.session_uid] = node['id']
    finally:
        if snapshot is not None:
            bpy.data.meshes.remove(snapshot)


def update(ob, rec):
    data = read(ob)
    if data is None or data['nodes'][-1]['id'] != getattr(rec, 'history_id', None):
        return
    data = deepcopy(data)
    data['nodes'][-1]['params'] = dict(rec.params)
    data['result_hash'] = rec.states[-1][3]
    write(ob, data)
    rec.history_token = token(data)


def records(ob):
    data = read(ob)
    if data is None:
        return []
    from . import extrude
    return [SimpleNamespace(history_id=node['id'], name=node['name'], spec=extrude.SPECS[node['kind']],
                            params=dict(node['params']), pre=None, dismissed=False,
                            cap_verts=[], cap_faces=[]) for node in data['nodes']]


def find(ob, name_or_id):
    data = read(ob)
    if data is None:
        return None
    creation = data.get('creation')
    if creation is not None and name_or_id in (creation['id'], creation['name']):
        return SimpleNamespace(history_id=creation['id'], name=creation['name'], creation=creation)
    node = next((node for node in data['nodes'] if name_or_id in (node['id'], node['name'])), None)
    if node is None:
        return None
    from . import extrude
    return SimpleNamespace(history_id=node['id'], name=node['name'], spec=extrude.SPECS[node['kind']],
                           params=dict(node['params']), pre=None, dismissed=False, cap_verts=[], cap_faces=[])


def activate(ob, name_or_id):
    rec = find(ob, name_or_id)
    if rec is not None:
        _active[ob.data.session_uid] = rec.history_id
        wm = bpy.context.window_manager
        if wm is not None and hasattr(wm, 'allset_ae_tab'):
            last = read(ob)['nodes'][-1]['id']
            wm.allset_ae_tab = ('CH' if hasattr(rec, 'creation') else
                                'H' if rec.history_id == last else 'H:'+rec.history_id)
            wm.allset_ae_kind = 'CH' if hasattr(rec, 'creation') else 'H'
    return rec


def selected(ob):
    data = read(ob)
    if data is None:
        return None
    name = _active.get(ob.data.session_uid, data['nodes'][-1]['id'])
    return find(ob, name) or find(ob, data['nodes'][-1]['id'])


def drop(ob):
    if not isinstance(ob, bpy.types.Object) or ob.type != 'MESH':
        return
    base = ob.data.get(BASE)
    for key in (KEY, BASE):
        if key in ob.data:
            del ob.data[key]
    if base is not None and base.users == 0 and base.get(OWNED):
        bpy.data.meshes.remove(base)
    _cache.pop(ob.data.session_uid, None)
    _active.pop(ob.data.session_uid, None)
    _valid.pop(ob.data.session_uid, None)


def _evaluate(ob, data):
    """Build off-screen. Keep one compact native Mesh checkpoint for the final node's input."""
    from . import extrude
    bm = bmesh.new()
    checkpoint = bpy.data.meshes.new('.allset_history_checkpoint')
    try:
        creation = data.get('creation')
        if creation is not None:
            from . import prim_history, prim_shapes
            values = {**prim_shapes.defaults(creation['type']), **creation['attrs']}
            prim_history.fill_bmesh(bm, prim_shapes.build(creation['type'], values),
                                    creation.get('unit', 1.0), prim_history.uvs_on(values, creation))
        else:
            bm.from_mesh(ob.data[BASE])
        for index, node in enumerate(data['nodes']):
            _select(bm, node['selection'], node['name'])
            if index == len(data['nodes'])-1:
                bm.to_mesh(checkpoint)
            result, moved = _build(bm, extrude.SPECS[node['kind']], node['params'], node['unit'], ob)
        return bm, checkpoint, result, moved
    except Exception:
        bm.free()
        bpy.data.meshes.remove(checkpoint)
        raise


def input_mesh(ob, node_id):
    """A detached input for a node preparing an explicit path or another dependency."""
    from . import extrude
    data = read(ob)
    if data is None:
        raise ValueError('The modeling history is no longer available')
    bm = bmesh.new()
    try:
        creation = data.get('creation')
        if creation is None:
            bm.from_mesh(ob.data[BASE])
        else:
            from . import prim_history, prim_shapes
            values = {**prim_shapes.defaults(creation['type']), **creation['attrs']}
            prim_history.fill_bmesh(bm, prim_shapes.build(creation['type'], values),
                                    creation.get('unit', 1), prim_history.uvs_on(values, creation))
        for node in data['nodes']:
            _select(bm, node['selection'], node['name'])
            if node['id'] == node_id:
                return bm
            _build(bm, extrude.SPECS[node['kind']], node['params'], node['unit'], ob)
        raise ValueError('The modeling node is no longer available')
    except Exception:
        bm.free()
        raise


def _record(ob, data, bm, checkpoint, result, moved):
    from . import extrude
    last = data['nodes'][-1]
    pre = bmesh.new()
    pre.from_mesh(checkpoint)
    rec = extrude.Record(last['name'], pre, last['params'], extrude.SPECS[last['kind']])
    rec.mesh_uid = ob.data.session_uid
    rec.history_id = last['id']
    rec.history_token = token(data)
    if rec.spec is extrude.FACE:
        extrude._store(rec, bm, result, moved, last['params'])
    else:
        extrude._store_generic(rec, bm, result, last['params'])
    old = extrude.RECORDS.get(ob.name)
    if old is not None:
        old.free()
    extrude.RECORDS[ob.name] = rec
    return rec


def ensure(ob):
    from . import extrude
    rec = extrude.RECORDS.get(ob.name)
    data = read(ob)
    if data is None or ob.data.session_uid in _busy:
        return rec
    uid = ob.data.session_uid
    if rec is None or not rec.live:
        valid = _valid.get(uid)
        if valid is None:
            actual = (extrude.coords_hash(bmesh.from_edit_mesh(ob.data)) if ob.mode == 'EDIT'
                      else extrude.mesh_coords_hash(ob.data))
            valid = actual == data.get('result_hash')
            _valid[uid] = valid
        if not valid:
            return None
    if (rec is not None and rec.pre is not None and rec.mesh_uid == ob.data.session_uid
            and getattr(rec, 'history_id', None) == data['nodes'][-1]['id']
            and getattr(rec, 'history_token', None) == token(data)):
        return rec
    _busy.add(ob.data.session_uid)
    try:
        bm, checkpoint, result, moved = _evaluate(ob, data)
        try:
            if extrude.coords_hash(bm) != data['result_hash']:
                return None
            return _record(ob, data, bm, checkpoint, result, moved)
        finally:
            bm.free()
            bpy.data.meshes.remove(checkpoint)
    except (ValueError, RuntimeError, KeyError):
        return None
    finally:
        _busy.discard(ob.data.session_uid)


def edit(ob, node_id, params):
    """Replay an earlier node and every downstream node before replacing visible geometry."""
    from . import extrude
    data = deepcopy(read(ob))
    if data is None:
        raise ValueError('The modeling history is no longer available')
    node = next((node for node in data['nodes'] if node['id'] == node_id), None)
    creation = data.get('creation')
    editing_creation = creation is not None and creation['id'] == node_id
    if editing_creation:
        creation['attrs'] = dict(params)
    elif node is None:
        raise ValueError('The modeling node is no longer available')
    else:
        node['params'] = dict(params)
    _busy.add(ob.data.session_uid)
    try:
        bm, checkpoint, result, moved = _evaluate(ob, data)
        try:
            data['result_hash'] = extrude.coords_hash(bm)
            if ob.mode == 'EDIT':
                extrude.restore_mesh(bmesh.from_edit_mesh(ob.data), bm)
                bmesh.update_edit_mesh(ob.data)
            else:
                bm.to_mesh(ob.data)
                ob.data.update()
            rec = _record(ob, data, bm, checkpoint, result, moved)
            write(ob, data)
            if editing_creation:
                from . import prim_history
                ob.data[prim_history.KEY] = {key: value for key, value in creation.items() if key != 'id'}
            return rec
        finally:
            bm.free()
            bpy.data.meshes.remove(checkpoint)
    finally:
        _busy.discard(ob.data.session_uid)


@bpy.app.handlers.persistent
def clear(_dummy=None):
    _cache.clear()
    _active.clear()
    _busy.clear()
    _valid.clear()


@bpy.app.handlers.persistent
def changed(_scene, depsgraph):
    for update in depsgraph.updates:
        data = update.id.original
        if isinstance(data, bpy.types.Mesh) and update.is_updated_geometry and KEY in data:
            if data.session_uid not in _busy:
                _valid.pop(data.session_uid, None)
