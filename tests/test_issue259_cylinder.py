"""polyCylinder creation attributes: Height Baseline, Create UVs, Round Cap Height Compensation (shapes checked
against Maya 2026 values: height 4, radius 1, 4 axis / 2 cap subdivisions)."""
from importlib import import_module

import bpy

import kit

ps = import_module(kit.MODULE + ".operators.prim_shapes")
ph = import_module(kit.MODULE + ".operators.prim_history")
ci = import_module(kit.MODULE + ".ui.creation_inputs")


def _y(mesh):
    """Maya Y of every vertex (the shape is built Y-up before the axis turn; axis 0 1 0 keeps Y)."""
    return [v[1] for v in mesh.verts]


def _cyl(**kw):
    a = {**ps.defaults("polyCylinder"), "subdivisionsAxis": 4, "subdivisionsCaps": 2, "radius": 1.0, "height": 4.0,
         **kw}
    return ps.build("polyCylinder", a)


def _range(mesh):
    ys = [round(y, 5) for y in _y(mesh)]
    return min(ys), max(ys)


def test_attribute_rows_in_maya_order():
    rows = ci.node_rows("polyCylinder")
    assert rows[:9] == ["heightBaseline", "radius", "height", "subdivisionsAxis", "subdivisionsHeight",
                        "subdivisionsCaps", "createUVs", "roundCap", "roundCapHeightCompensation"], rows
    assert ps.defaults("polyCylinder")["createUVs"] == 3
    labels, values = ph.enum_labels("polyCylinder", "createUVs")
    assert labels[0] == "None" and values == [0, 1, 2, 3]


def test_height_baseline():
    assert _range(_cyl(subdivisionsCaps=1)) == (-2.0, 2.0)
    assert _range(_cyl(subdivisionsCaps=1, heightBaseline=-1.0)) == (0.0, 4.0)
    assert _range(_cyl(subdivisionsCaps=1, heightBaseline=1.0)) == (-4.0, 0.0)
    assert _range(_cyl(subdivisionsCaps=1, heightBaseline=0.5)) == (-3.0, 1.0)
    assert _range(_cyl(subdivisionsCaps=0, heightBaseline=2.0)) == (-6.0, -2.0)


def test_round_cap_height_compensation():
    assert _range(_cyl(roundCap=True)) == (-3.0, 3.0)
    assert _range(_cyl(roundCap=True, roundCapHeightCompensation=True)) == (-2.0, 2.0)
    assert _range(_cyl(roundCap=True, heightBaseline=1.0)) == (-6.0, 0.0)
    assert _range(_cyl(roundCap=True, roundCapHeightCompensation=True, heightBaseline=1.0)) == (-4.0, 0.0)
    # Maya: the side rings sit at +-1, the dome ring at +-1.707107, the poles at +-2
    ys = sorted({round(y, 5) for y in _y(_cyl(roundCap=True, roundCapHeightCompensation=True))})
    assert ys == [-2.0, -1.70711, -1.0, 1.0, 1.70711, 2.0], ys
    assert _range(_cyl(roundCapHeightCompensation=True)) == (-2.0, 2.0), "no round cap: nothing to compensate"


def _new_cylinder():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    return ph.create_object(bpy.context, 'CYLINDER')


def test_create_uvs_and_baseline_rebuild_the_object():
    ob = _new_cylinder()
    assert len(ob.data.uv_layers) == 1
    ph.rebuild(bpy.context, ob, {"createUVs": 0})
    assert len(ob.data.uv_layers) == 0
    ph.rebuild(bpy.context, ob, {"createUVs": 2, "heightBaseline": -1.0})
    assert len(ob.data.uv_layers) == 1
    k = ph.node_of(ob)[1].get("unit", 1.0)
    zs = [v.co.z for v in ob.data.vertices]
    assert abs(min(zs)) < 1e-6 and abs(max(zs) - 2.0 * k) < 1e-6, (min(zs), max(zs), k)


def test_create_without_uvs_sets_the_attribute():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    ob = ph.create_object(bpy.context, 'CYLINDER', create_uvs=False)
    assert ph.attrs(ph.owner_of(ob))["createUVs"] == 0
    assert len(ob.data.uv_layers) == 0
    ph.rebuild(bpy.context, ob, {"height": 3.0})
    assert len(ob.data.uv_layers) == 0
