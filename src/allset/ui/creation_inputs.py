# SPDX-License-Identifier: GPL-3.0-or-later
"""Channel Box INPUTS / Attribute Editor tab for the creation node of a primitive (#11, #12).

``polyCylinder1`` with Radius, Height, Subdivisions Axis / Height / Caps ... (Maya's Channel Box
attribute names). Values are typed like every Channel Box field (
``+=2``, ``*2``, units) into text proxies on the Scene (UI edits of Scene properties push an undo step) and go to
every selected object whose node has the same type; ``operators/prim_history.rebuild`` remakes the shape.
"""

import bpy
from bpy.props import BoolProperty, PointerProperty, StringProperty

from ..operators import prim_history, prim_shapes
from . import cb_entry

AXIS_ATTRS = {"axisX", "axisY", "axisZ", "pivotX", "pivotY", "pivotZ", "normalX", "normalY", "normalZ",
              "centerX", "centerY", "centerZ"}
ALL_ATTRS = sorted({a[0] for spec in prim_shapes.NODES.values() for a in spec})


def _lead(context):
    from . import channel_box
    ob = channel_box.lead(context)
    return ob if isinstance(ob, bpy.types.Object) else None


def node_rows(node_type):
    """Attribute names in Channel Box order: the shape values first, the axis / pivot / normal / centre last."""
    names = [a[0] for a in prim_shapes.NODES[node_type]]
    return [n for n in names if n not in AXIS_ATTRS] + [n for n in names if n in AXIS_ATTRS]


def format_attr(node, name, value, scene):
    kind = prim_history.entry_kind(node["type"], name)
    if kind == "ENUM":
        labels, values = prim_history.enum_labels(node["type"], name)
        return labels[values.index(value)] if value in values else str(value)
    return cb_entry.format_value(prim_history.to_entry(node, name, value), kind, scene)


def parse_attr(node, name, text, old, scene):
    """Typed text -> Maya attribute value (ValueError when it can't be read)."""
    kind = prim_history.entry_kind(node["type"], name)
    if kind == "ENUM":
        labels, values = prim_history.enum_labels(node["type"], name)
        low = text.strip().lower()
        for label, v in zip(labels, values):
            if label.lower().startswith(low) and low:
                return v
        return int(round(cb_entry.parse_entry(text, old, "INT", scene)))
    entry = cb_entry.parse_entry(text, prim_history.to_entry(node, name, old), kind, scene)
    return prim_history.from_entry(node, name, entry)


def apply_text(context, name, text):
    """Typed ``text`` on attribute ``name`` of the lead's creation node: every selected object with a node of the
    same type is rebuilt. Returns the number of objects changed."""
    from . import channel_box
    lead = _lead(context)
    _owner, node = prim_history.node_of(lead)
    if node is None:
        return 0
    count = 0
    done = set()
    for ob in channel_box.targets(context):
        if not isinstance(ob, bpy.types.Object):
            continue
        owner, other = prim_history.node_of(ob)
        if other is None or other["type"] != node["type"] or owner.as_pointer() in done:
            continue
        done.add(owner.as_pointer())   # instances share the node (Maya: one shape, one history)
        old = prim_history.attrs(owner)[name]
        try:
            value = parse_attr(other, name, text, old, context.scene)
        except (ValueError, TypeError, SyntaxError, NameError):
            return count
        if prim_shapes.clamp(other["type"], name, value) == old:
            continue
        prim_history.rebuild(context, ob, {name: value})
        count += 1
    return count


def _text_get(name):
    def get(_self):
        context = bpy.context
        owner, node = prim_history.node_of(_lead(context))
        if node is None or name not in prim_history.attrs(owner):
            return ""
        return format_attr(node, name, prim_history.attrs(owner)[name], context.scene)
    return get


def _text_set(name):
    def set_(_self, text):
        apply_text(bpy.context, name, text)
    return set_


def _sel_get(name):
    def get(_self):
        from . import channel_box
        return channel_box.HISTORY_PREFIX + name in channel_box.selected_channels()
    return get


def _sel_set(name):
    def set_(self, value):
        from . import channel_box
        channel_box._sel_set(channel_box.HISTORY_PREFIX + name)(self, value)
    return set_


class ALLSET_PG_creation(bpy.types.PropertyGroup):
    __annotations__ = {
        **{f"{n}_text": StringProperty(name=n, get=_text_get(n), set=_text_set(n), options={'SKIP_SAVE'})
           for n in ALL_ATTRS},
        **{f"{n}_sel": BoolProperty(name=n, get=_sel_get(n), set=_sel_set(n), options={'SKIP_SAVE'},
                                    description="Select this attribute: click, Ctrl toggle, Shift range, drag "
                                                "over the rows; then middle-drag in the viewport changes it")
           for n in ALL_ATTRS}}


def has_node(ob):
    return prim_history.node_of(ob)[1] is not None


def draw_cb(layout, context, ob):
    """The node in Channel Box INPUTS: its name (click = expand / collapse, collapsed at first like Maya)
    and, expanded, one text row per attribute."""
    _owner, node = prim_history.node_of(ob)
    if node is None:
        return False
    from . import channel_box
    lines = channel_box.as_lines(layout)
    _row, opened = channel_box.node_row(lines, ob, channel_box.history_node(node["name"]), node["name"])
    if not opened:
        return True
    props = context.scene.allset_creation
    for name in node_rows(node["type"]):
        row = lines.row()
        if row is None:
            continue
        split = row.split(factor=0.5, align=True)
        selected = channel_box.HISTORY_PREFIX + name in channel_box.selected_channels(context)
        split.prop(props, f"{name}_sel", text=prim_shapes.spec(node["type"], name)[1], toggle=True, emboss=selected)
        split.prop(props, f"{name}_text", text="")
    return True


def _rows(col, context, node, factor):
    props = context.scene.allset_creation
    for name in node_rows(node["type"]):
        label = prim_shapes.spec(node["type"], name)[1]
        split = col.row(align=True).split(factor=factor, align=True)
        split.label(text=label)
        split.prop(props, f"{name}_text", text="")


def nice_type(node_type):
    import re
    return re.sub(r"(?<!^)(?=[A-Z])", " ", node_type[:1].upper() + node_type[1:])


def draw_ae(layout, context, ob):
    """The Attribute Editor tab of the node: Maya's "<Nice Type> History" section with the same fields."""
    _owner, node = prim_history.node_of(ob)
    if node is None:
        return
    header, body = layout.panel("allset_ae_creation", default_closed=False)
    header.label(text=f"{nice_type(node['type'])} History")
    if body is not None:
        from .attribute_editor import section_body
        _rows(section_body(body).column(align=True), context, node, 0.42)     # inset content area (#194)


classes = (ALLSET_PG_creation,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.allset_creation = PointerProperty(type=ALLSET_PG_creation)


def unregister():
    del bpy.types.Scene.allset_creation
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
