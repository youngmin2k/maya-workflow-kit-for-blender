"""Deform > Export / Import Weights = Maya deformerWeights XML. Format and import rules follow
Maya."""

import os
from importlib import import_module

import bpy
from mathutils import Vector

import kit

dw = import_module(kit.MODULE + ".operators.deformer_weights")
skin = import_module(kit.MODULE + ".operators.skin")
joints = import_module(kit.MODULE + ".operators.joints")
deformers = import_module(kit.MODULE + ".operators.deformers")

OUT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp", "test_step159_weights"))
os.makedirs(OUT, exist_ok=True)

MAYA_POINTS = ((-2, 0, 2), (2, 0, 2), (-2, 0, 0), (2, 0, 0), (-2, 0, -2), (2, 0, -2))
MAYA_FACES = ((0, 1, 3, 2), (2, 3, 5, 4))
JOINTS = ("joint1", "joint2", "joint3")


def _clear(cm=False):
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.armatures):
        for d in list(coll):
            coll.remove(d)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', ('CENTIMETERS' if cm else 'METERS'), 1.0


def _skeleton():
    k = dw.units.maya_unit()
    ob = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 0, -2), (0, 0, 0), (0, 0, 2)):
        parent = joints.add_joint(ob, dw.from_maya(p, k), parent, length=0.5 * k)
    joints.finish(bpy.context, ob, list(JOINTS))
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def _plane(name="pPlane1", order=None, offset=(0.0, 0.0, 0.0)):
    """The Maya plane, built from Maya's points (``order``: new index -> Maya index)."""
    k = dw.units.maya_unit()
    order = list(order or range(len(MAYA_POINTS)))
    inv = {m: n for n, m in enumerate(order)}
    verts = [dw.from_maya(MAYA_POINTS[m], k) + Vector(offset) * k for m in order]
    faces = [tuple(inv[i] for i in f) for f in MAYA_FACES]
    me = bpy.data.meshes.new(name + "Shape")
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _bind(arm, mesh):
    for o in bpy.context.scene.objects:
        o.select_set(o in (arm, mesh))
    bpy.context.view_layer.objects.active = mesh
    assert bpy.ops.allset.bind_skin() == {'FINISHED'}
    assert skin.armature_modifier(mesh).name.startswith("skinCluster")


def _weights(ob):
    names = [vg.name for vg in ob.vertex_groups]
    return {v.index: {names[g.group]: g.weight for g in v.groups if g.weight > 0.0} for v in ob.data.vertices}


def _same(a, b, tol=1e-6):
    for i in set(a) | set(b):
        wa, wb = a.get(i, {}), b.get(i, {})
        for n in set(wa) | set(wb):
            assert abs(wa.get(n, 0.0) - wb.get(n, 0.0)) <= tol, (i, n, wa, wb)


def _odd_weights(mesh):
    """Unequal weights incl. zeros so a mix-up shows."""
    table = {0: (1.0, 0.0, 0.0), 1: (0.123456789, 0.876543211, 0.0), 2: (0.3, 0.3, 0.4),
             3: (0.0, 1.0 / 3.0, 2.0 / 3.0), 4: (0.0, 0.0, 1.0), 5: (0.0, 0.25, 0.75)}
    for name in JOINTS:
        vg = mesh.vertex_groups.get(name) or mesh.vertex_groups.new(name=name)
        vg.remove(list(range(len(mesh.data.vertices))))
    for i, ws in table.items():
        for name, w in zip(JOINTS, ws):
            if w > 0.0:
                mesh.vertex_groups[name].add([i], w, 'REPLACE')
    return _weights(mesh)


# --- format ---------------------------------------------------------------------------------------------------------


def test_export_xml_structure_is_mayas():
    text = dw.export_xml("pPlane1Shape", "skinCluster1",
                         {"joint1": {0: 1.0, 1: 0.123456789, 2: 0.0}, "joint2": {1: 0.876543211}},
                         points=[(-2.0, 0.0, 2.0), (2.0, 0.0, 2.0), (-2.0, 0.0, 0.0)], file_name="C:/x/skin.xml")
    lines = text.splitlines()
    assert lines[0] == '<?xml version="1.0"?>' and lines[1] == "<deformerWeight>"
    assert lines[2] == ('  <headerInfo fileName="C:/x/skin.xml" worldMatrix="1.000000 0.000000 0.000000 0.000000 '
                        '0.000000 1.000000 0.000000 0.000000 0.000000 0.000000 1.000000 0.000000 0.000000 0.000000 '
                        '0.000000 1.000000 "/>'), lines[2]
    assert lines[3] == '  <shape name="pPlane1Shape" group="0" stride="3" size="3" max="2">', lines[3]
    assert lines[4] == '    <point index="0" value=" -2.000000 0.000000 2.000000"/>', lines[4]
    assert lines[7] == '  </shape>'
    assert lines[8] == ('  <weights deformer="skinCluster1" source="joint1" shape="pPlane1Shape" layer="0" '
                        'defaultValue="0.000000000" size="2" max="1">'), lines[8]      # zero weight left out
    assert lines[10] == '    <point index="1" value="0.123456789"/>', lines[10]
    assert 'source="joint2"' in lines[12] and 'layer="1"' in lines[12] and 'size="1" max="1"' in lines[12]
    back = dw.parse_xml(text)
    assert back["weights"][0]["points"] == {0: 1.0, 1: 0.123456789}


def test_world_matrix_is_maya_order():
    from mathutils import Matrix
    k = 0.01
    m = Matrix.Translation((0.1, 0.0, 0.0))        # Maya translate X 10 in a cm scene
    wm = dw.maya_world_matrix(m, k)
    assert [round(x, 6) for x in wm[12:]] == [10.0, 0.0, 0.0, 1.0], wm
    m = Matrix.Translation((0.0, -0.05, 0.02))     # Maya (0, 2, 5)
    wm = dw.maya_world_matrix(m, k)
    assert [round(x, 6) for x in wm[12:15]] == [0.0, 2.0, 5.0], wm


# --- Blender round trips --------------------------------------------------------------------------------------------

def test_round_trip_export_clear_import():
    _clear()
    arm = _skeleton()
    mesh = _plane()
    _bind(arm, mesh)
    before = _odd_weights(mesh)
    path = dw.export_file(mesh, "", os.path.join(OUT, "round.xml"))
    for vg in list(mesh.vertex_groups):        # clear: no weights at all
        mesh.vertex_groups.remove(vg)
    applied, warnings = dw.import_file(mesh, path)
    assert applied == list(JOINTS) and not warnings, (applied, warnings)
    _same(_weights(mesh), before)
    # and onto weights that are all different (every influence replaced, missing vertices out of the group)
    for vg in mesh.vertex_groups:
        vg.add(list(range(6)), 0.5, 'REPLACE')
    dw.import_file(mesh, path)
    _same(_weights(mesh), before)


def test_export_points_are_maya_object_space():
    _clear(cm=True)
    arm = _skeleton()
    mesh = _plane()
    mesh.location = (0.1, 0.0, 0.0)
    bpy.context.view_layer.update()
    _bind(arm, mesh)
    d = dw.parse_xml(open(dw.export_file(mesh, "", os.path.join(OUT, "points.xml"))).read())
    assert list(d["shapes"]) == ["pPlane1Shape"], list(d["shapes"])
    shape = d["shapes"]["pPlane1Shape"]
    for i, p in enumerate(MAYA_POINTS):
        assert all(abs(a - b) < 1e-5 for a, b in zip(shape[i], p)), (i, shape[i], p)
    assert [round(x, 4) for x in d["world_matrix"][12:15]] == [10.0, 0.0, 0.0], d["world_matrix"]


def test_kit_deformer_round_trip():
    _clear()
    mesh = _plane()
    for o in bpy.context.scene.objects:
        o.select_set(o == mesh)
    bpy.context.view_layer.objects.active = mesh
    deformers.create(bpy.context, 'BEND')
    md = next(m for m in mesh.modifiers if m.name.startswith("bend"))
    found = dw.deformers_of(mesh)
    assert [(n, k) for n, _m, k in found] == [(md.name, 'GROUP')], found
    vg = mesh.vertex_groups[md.vertex_group]
    vg.add([0, 1], 0.25, 'REPLACE')
    vg.remove([2])
    before = _weights(mesh)
    path = dw.export_file(mesh, md.name, os.path.join(OUT, "bend.xml"))
    d = dw.parse_xml(open(path).read())
    assert [(w["deformer"], w["source"]) for w in d["weights"]] == [(md.name, "baseLayer")]
    vg.remove(list(range(6)))
    applied, _w = dw.import_file(mesh, path)
    assert applied == ["baseLayer"]
    _same(_weights(mesh), before)


# --- operators ------------------------------------------------------------------------------------------------------

def test_operators_execute_both_ways():
    _clear()
    arm = _skeleton()
    mesh = _plane()
    _bind(arm, mesh)
    before = _odd_weights(mesh)
    for o in bpy.context.scene.objects:
        o.select_set(o == mesh)
    bpy.context.view_layer.objects.active = mesh
    name = skin.armature_modifier(mesh).name
    path = os.path.join(OUT, "op.xml")
    if os.path.exists(path):
        os.remove(path)
    assert bpy.ops.allset.export_deformer_weights(filepath=path, deformer=name) == {'FINISHED'}
    assert os.path.isfile(path)
    for vg in mesh.vertex_groups:
        vg.add(list(range(6)), 0.5, 'REPLACE')
    assert bpy.ops.allset.import_deformer_weights(filepath=path, method='INDEX') == {'FINISHED'}
    _same(_weights(mesh), before)
    # nearest through the operator too
    for vg in mesh.vertex_groups:
        vg.add(list(range(6)), 0.5, 'REPLACE')
    assert bpy.ops.allset.import_deformer_weights(filepath=path, method='NEAREST') == {'FINISHED'}
    _same(_weights(mesh), before)
    # no deformed mesh selected: Maya's warning, nothing written
    mesh.select_set(False)
    bpy.context.view_layer.objects.active = None
    assert bpy.ops.allset.export_deformer_weights(filepath=os.path.join(OUT, "none.xml")) == {'CANCELLED'}
    assert not os.path.exists(os.path.join(OUT, "none.xml"))
