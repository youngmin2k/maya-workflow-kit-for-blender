# SPDX-License-Identifier: GPL-3.0-or-later
"""Editable modeling and primitive attributes using the existing history backends."""

from types import SimpleNamespace
import math

import bpy

from ..operators import extrude, model_history, prim_history, prim_shapes, units
from .attribute_edit import Field


class ModelingNode:
    def __init__(self, ob, record):
        self.ob, self.record = ob, record
        self.spec = record.spec
        self.name = record.name
        self.identity = (ob.session_uid, ob.data.session_uid, self.name)

    @property
    def params(self):
        return self.record.params

    def valid(self):
        try:
            return (self.ob.data.session_uid == self.identity[1] and self.record.pre is not None
                    and extrude.RECORDS.get(self.ob.name) is self.record)
        except ReferenceError:
            return False

    def descriptor(self, name, soft=False):
        prop = getattr(bpy.ops.allset, self.spec.edit_op).get_rna_type().properties.get(name)
        minimum = prop.hard_min if prop is not None and hasattr(prop, 'hard_min') else None
        maximum = prop.hard_max if prop is not None and hasattr(prop, 'hard_max') else None
        if soft and prop is not None and hasattr(prop, 'soft_max'):
            maximum = prop.soft_max
        kind = self.spec.kinds[name]
        return Field(kind, 0.05 if kind == 'INT' else 0.01, minimum, maximum,
                     self.spec.defaults[name])

    def to_entry(self, name, value):
        return math.radians(value) if self.spec.kinds[name] == 'ROTATION' else value

    def from_entry(self, name, value):
        return math.degrees(value) if self.spec.kinds[name] == 'ROTATION' else value

    def choices(self, name):
        return self.spec.choices[name]

    def preview(self, context, params):
        if not self.valid():
            raise ReferenceError('The modeling node is no longer available')
        if params == self.params:
            return
        extrude.preview(self.ob, self.record, params, units.maya_unit(context.scene))

    def finish(self):
        if self.valid():
            if self.record.fast_preview:
                extrude.capture_preview(self.ob, self.record)
            else:
                model_history.update(self.ob, self.record)
            self.record.live = False
            self.record.fast_preview = False

    def commit(self, context, params):
        previous = dict(params)
        if self.spec.prepare is not None:
            params = self.spec.prepare(context, self.ob, self.record, params)
        try:
            self.preview(context, params)
            if self.record.fast_preview:
                extrude.capture_preview(self.ob, self.record)
        except Exception:
            if self.spec.cleanup is not None:
                self.spec.cleanup(self.ob, previous, params)
            raise


class HistoryNode(ModelingNode):
    """An earlier node evaluated through the same recipe as its downstream nodes."""

    @property
    def params(self):
        rec = model_history.find(self.ob, self.record.history_id)
        return rec.params if rec is not None else {}

    def valid(self):
        try:
            return (self.ob.data.session_uid == self.identity[1]
                    and model_history.find(self.ob, self.record.history_id) is not None)
        except ReferenceError:
            return False

    def preview(self, context, params):
        if not self.valid():
            raise ReferenceError('The modeling node is no longer available')
        if params != self.params:
            model_history.edit(self.ob, self.record.history_id, params)

    def commit(self, context, params):
        previous = dict(params)
        if self.spec.prepare is not None:
            params = self.spec.prepare(context, self.ob, self.record, params)
        try:
            self.preview(context, params)
        except Exception:
            if self.spec.cleanup is not None:
                self.spec.cleanup(self.ob, previous, params)
            raise

    def finish(self):
        pass


def for_record(context, ob, record):
    if hasattr(record, 'creation'):
        return CreationHistoryNode(ob, ob.data, record.creation)
    terminal = extrude.current(ob) if ob.mode == 'EDIT' else extrude.object_record(ob)
    if (getattr(record, 'history_id', None) and terminal is not None
            and record.history_id != getattr(terminal, 'history_id', None)):
        return HistoryNode(ob, record)
    return ModelingNode(ob, terminal or record)


class PrimitiveNode:
    def __init__(self, ob, owner, node):
        self.ob = ob
        self.name = node['name']
        self.node_type = node['type']
        self.identity = (ob.session_uid, self.node_type, self.name)
        from .creation_inputs import node_rows
        fields = tuple(node_rows(self.node_type))
        self.spec = SimpleNamespace(
            fields=fields, node_type=self.node_type, arrow=None, in_view=True,
            labels={a[0]: a[1] for a in prim_shapes.NODES[self.node_type]},
            defaults=prim_shapes.defaults(self.node_type),
            kinds={name: prim_history.entry_kind(self.node_type, name) for name in fields})

    @property
    def params(self):
        return prim_history.attrs(prim_history.owner_of(self.ob))

    def valid(self):
        try:
            _owner, node = prim_history.node_of(self.ob)
            return node is not None and node['name'] == self.name
        except (ReferenceError, TypeError):
            return False

    def descriptor(self, name, soft=False):
        _name, _label, default, _kind, minimum, maximum = prim_shapes.spec(self.node_type, name)
        kind = self.spec.kinds[name]
        return Field(kind, 0.05 if kind == 'INT' else 0.01, minimum, maximum, default)

    def to_entry(self, name, value):
        node = prim_history.node_dict(prim_history.owner_of(self.ob))
        return prim_history.to_entry(node, name, value)

    def from_entry(self, name, value):
        node = prim_history.node_dict(prim_history.owner_of(self.ob))
        return prim_history.from_entry(node, name, value)

    def choices(self, name):
        return prim_history.enum_labels(self.node_type, name)

    def preview(self, context, params):
        if not self.valid():
            raise ReferenceError('The creation node is no longer editable')
        current = self.params
        changes = {key: value for key, value in params.items() if current[key] != value}
        if changes and prim_history.rebuild(context, self.ob, changes) is None:
            raise RuntimeError('Unable to rebuild the creation node')

    def finish(self):
        pass

    def commit(self, context, params):
        self.preview(context, params)


class CreationHistoryNode(PrimitiveNode):
    def __init__(self, ob, owner, node):
        super().__init__(ob, owner, node)
        self.history_id = node['id']

    def preview(self, context, params):
        if params != self.params:
            model_history.edit(self.ob, self.history_id, params)


def target(context, ob=None):
    ob = ob or getattr(context, 'active_object', None)
    if ob is None:
        return None
    record = extrude.current(ob) if ob.mode == 'EDIT' else extrude.object_record(ob)
    if record is not None:
        selected = model_history.selected(ob)
        return for_record(context, ob, selected or record)
    if ob.mode == 'OBJECT':
        owner, node = prim_history.node_of(ob)
        if node is not None:
            return PrimitiveNode(ob, owner, node)
    return None


def editable(node, field):
    from . import channel_box
    enabled = getattr(node.spec, 'enabled', None)
    if enabled is not None and not enabled(node.params, field):
        return False
    key = (channel_box.model_key(node.record, field) if isinstance(node, ModelingNode)
           else channel_box.HISTORY_PREFIX+field)
    return not channel_box.is_locked(node.ob, key)


def format_value(node, name, scene, params=None):
    from . import cb_entry
    value = (node.params if params is None else params)[name]
    kind = node.spec.kinds[name]
    if kind == 'ENUM':
        labels, values = node.choices(name)
        return labels[values.index(value)] if value in values else str(value)
    return cb_entry.format_value(node.to_entry(name, value), kind, scene)


def parse_value(node, name, text, scene):
    from . import cb_entry
    kind = node.spec.kinds[name]
    if kind == 'ENUM':
        labels, values = node.choices(name)
        matches = [value for label, value in zip(labels, values) if label.lower() == text.strip().lower()]
        if matches:
            return matches[0]
        prefixes = [value for label, value in zip(labels, values) if text.strip()
                    and label.lower().startswith(text.strip().lower())]
        if prefixes:
            return prefixes[0]
        value = cb_entry.parse_entry(text, node.params[name], 'INT', scene)
        if value not in values:
            raise ValueError('Choose one of the attribute values')
        return value
    value = cb_entry.parse_entry(text, node.to_entry(name, node.params[name]), kind, scene)
    value = node.from_entry(name, value)
    return value if kind == 'BOOL' else node.descriptor(name).limit(value)


def display_descriptor(node, name, context, soft=False):
    """Use the same stored units, bounds and sensitivity in every attribute UI."""
    from . import cb_entry
    field = node.descriptor(name, soft)
    def display(value):
        return cb_entry.to_display(node.to_entry(name, value), field.kind, context.scene)
    return Field(field.kind, display(field.step),
                 display(field.minimum) if field.minimum is not None else None,
                 display(field.maximum) if field.maximum is not None else None)
