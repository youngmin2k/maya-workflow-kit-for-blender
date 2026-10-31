"""#217: a file saved while a duplicate still shares its original's Outliner number (as an earlier version
left it) opens with the tie in it and settles on the first order sync, the original keeping its place; undoing a
duplicate leaves a settled order."""

import os
from importlib import import_module

import bpy

import kit

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "tmp", "test_step287")


def m(name):
    return import_module(f"{kit.MODULE}.{name}")


def _scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    sc = bpy.context.scene
    coll = bpy.data.collections.new("Collection")
    sc.collection.children.link(coll)
    return sc, coll


def _cube(name, coll):
    me = bpy.data.meshes.new(name + "Shape")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def test_saved_tie_settles_after_open():
    oo = m("ui.outliner_order")
    sc, coll = _scene()
    a = _cube("pCube1", coll)
    a[oo.ORDER] = 5
    b = a.copy()                       # a duplicate as Blender makes it: same ID properties
    b.name = "pCube2"
    coll.objects.link(b)
    assert b[oo.ORDER] == 5
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "tie.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    oo = m("ui.outliner_order")
    sc, vl = bpy.context.scene, bpy.context.view_layer
    a, b = bpy.data.objects["pCube1"], bpy.data.objects["pCube2"]
    assert a[oo.ORDER] == b[oo.ORDER] == 5, "the file should still hold the tie"
    oo.sync(sc, vl, rotate=True)
    assert a[oo.ORDER] == 5 and b[oo.ORDER] > 5, (a[oo.ORDER], b[oo.ORDER])
    assert not any(oo.sync(sc, vl, rotate=True) for _i in range(6)), "the order sync didn't settle"


def test_undo_of_a_duplicate_settles():
    oo = m("ui.outliner_order")
    sc, coll = _scene()
    vl = bpy.context.view_layer
    a = _cube("pCube1", coll)
    oo.sync(sc, vl, rotate=True)
    bpy.ops.ed.undo_push(message="before duplicate")
    for o in sc.objects:
        o.select_set(o == a)
    vl.objects.active = a
    bpy.ops.object.duplicate('EXEC_DEFAULT', True)
    oo.sync(sc, vl, rotate=True)
    assert len({o[oo.ORDER] for o in sc.objects}) == len(sc.objects)
    bpy.ops.ed.undo()
    sc, vl = bpy.context.scene, bpy.context.view_layer
    assert [o.name for o in sc.objects] == ["pCube1"], [o.name for o in sc.objects]
    assert not any(oo.sync(sc, vl, rotate=True) for _i in range(3))
