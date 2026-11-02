"""Type tool node in the Attribute Editor: the text itself, font and spacing, extrude / bevel."""
from importlib import import_module

import bpy

import kit

ae = import_module(kit.MODULE + ".ui.attribute_editor")
ae_layout = import_module(kit.MODULE + ".ui.ae_layout")
create = import_module(kit.MODULE + ".operators.create")


def _type_object():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    return create.create(bpy.context, 'TEXT')


def _rows(sections):
    return [row for _d, sec in ae_layout.walk(sections) for row in sec.rows]


def test_type_tab_has_maya_sections():
    ob = _type_object()
    assert ob.type == 'FONT'
    key, _label, node = ae.tabs(ob)[1]
    assert node == "type"
    sections, _layout = ae.sections_for(ob, key)
    assert [s.name for s in sections] == ["Text", "Geometry", "Generator", "Texturing", "Animation"]
    props = {row[2]: row[3] for row in _rows(sections) if row[0] == "prop"}
    assert props["body"] == "Text" and props["extrude"] == "Extrude Distance"
    assert props["bevel_depth"] == "Bevel Distance"


def test_text_row_edits_the_text_not_the_name():
    ob = _type_object()
    name = ob.data.name
    row = next(r for r in _rows(ae_layout.TYPE) if r[0] == "prop" and r[2] == "body")
    owner, attr = ae.resolve(ob.data, row[2])
    setattr(owner, attr, "What")
    assert ob.data.body == "What"
    assert ob.data.name == name, "the text field leaves the node name alone"


def test_type_tab_draws():
    ob = _type_object()
    bpy.context.view_layer.objects.active = ob
    key = ae.tabs(ob)[1][0]
    sections, _layout = ae.sections_for(ob, key)
    assert all(row[0] in ("prop", "missing", "draw") for row in _rows(sections))
