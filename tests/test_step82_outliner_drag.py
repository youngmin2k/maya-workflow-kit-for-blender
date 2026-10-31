"""Outliner drags parent the Maya way (drop zones, parenting, reorder in Blender's drawn order, keymap).
GUI: tests/gui/gui_step82_outliner_drag.py (LMB drop redone, MMB drag, undo)."""

import json
import math
from importlib import import_module

import bpy
from mathutils import Vector

import kit

od = import_module(kit.MODULE + ".operators.outliner_drag")
patches = import_module(kit.MODULE + ".keymap.maya_patches")


def test_zone_quarters():
    h = 25.0
    assert od.zone(-1.0, h) == (0, 'BEFORE')
    assert od.zone(-12.5, h) == (0, 'ON')
    assert od.zone(-24.0, h) == (0, 'AFTER')
    assert od.zone(-26.0, h) == (1, 'BEFORE')
    assert od.zone(-25 * 3 - 10, h) == (3, 'ON')


def test_reordered_and_drawn_order():
    names = ["A", "B", "C", "D"]
    assert od.reordered(names, ["D"], "B", after=False) == ["A", "D", "B", "C"]
    assert od.reordered(names, ["A", "C"], "D", after=True) == ["B", "D", "A", "C"]
    assert od.reordered(names, ["B"], "B", after=True) == names          # onto itself: nothing
    # Blender's unsorted Outliner draws the first linked object last
    assert od.displayed(["Z", "Y", "X"]) == ["Y", "X", "Z"]
    assert od.linked(od.displayed(names)) == names


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _ob(name, loc, col=None):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    (col or bpy.context.scene.collection).objects.link(ob)
    ob.location = loc
    return ob


def _identity(ob):
    return all(abs(ob.matrix_parent_inverse[i][j] - (i == j)) < 1e-6 for i in range(4) for j in range(4))


def _scene():
    _clear()
    a = _ob("A", (1, 0, 0))
    a.rotation_euler = (0, 0, math.radians(30))
    a.scale = (2, 2, 2)
    b = _ob("B", (0, 2, 0))
    c = _ob("C", (0, 0, 3))
    bpy.context.view_layer.update()
    return a, b, c


def test_drop_parent_rules():
    a, b, _c = _scene()
    b.parent = a
    assert od.drop_parent(a, 'ON') == a
    assert od.drop_parent(b, 'BEFORE') == a          # between rows: that row's parent
    assert od.drop_parent(a, 'AFTER') is None        # top-level row: the world
    assert od.drop_parent(None, 'ON') is None        # empty space: the world


def test_reparent_maya_keeps_world_identity_inverse():
    a, b, c = _scene()
    done, cycles = od.reparent([b, c], a, mode='MAYA')
    bpy.context.view_layer.update()
    assert set(done) == {b, c} and not cycles
    for ob, loc in ((b, (0, 2, 0)), (c, (0, 0, 3))):
        assert ob.parent == a and _identity(ob)
        assert (ob.matrix_world.translation - Vector(loc)).length < 1e-5
    assert (b.location - Vector((0, 2, 0))).length > 0.1          # channels local to A (Maya)
    done, cycles = od.reparent([a], b, mode='MAYA')                   # A under its own child: skipped
    assert not done and cycles == [a] and a.parent is None
    done, _ = od.reparent([b], None)                                  # empty space: world
    bpy.context.view_layer.update()
    assert done == [b] and b.parent is None and (b.matrix_world.translation - Vector((0, 2, 0))).length < 1e-5


def test_reparent_blender_mode_keeps_parent_inverse():
    a, b, _c = _scene()
    od.reparent([b], a, mode='BLENDER')
    bpy.context.view_layer.update()
    assert b.parent == a and not _identity(b)
    assert (b.location - Vector((0, 2, 0))).length < 1e-5 and (b.matrix_world.translation - Vector((0, 2, 0))).length < 1e-5


def test_reorder_relinks_in_drawn_order_and_keeps_base_state():
    _clear()
    col = bpy.data.collections.new("Col82")
    bpy.context.scene.collection.children.link(col)
    obs = [_ob(n, (i, 0, 0), col) for i, n in enumerate("ABCD")]
    vl = bpy.context.view_layer
    obs[3].select_set(True)
    obs[1].hide_set(True)
    vl.objects.active = obs[3]
    # drawn B C D A; drag D before B -> drawn D B C A -> linked A D B C
    assert od.reorder(vl, [obs[3]], obs[1], after=False)
    names = [o.name for o in col.objects]
    assert names == ["A", "D", "B", "C"], names
    assert od.displayed([o.name for o in vl.objects if o]) == ["D", "B", "C", "A"]
    assert obs[3].select_get() and obs[1].hide_get() and vl.objects.active == obs[3]
    # with collection rows: the same rule inside the collection
    assert od.reorder(vl, [obs[0]], obs[3], after=False, by_collection=True)
    assert od.displayed([o.name for o in col.objects]) == ["A", "D", "B", "C"], [o.name for o in col.objects]
    assert not od.reorder(vl, [obs[0]], obs[3], after=False, by_collection=True)     # already there
    bpy.data.collections.remove(col)


def test_reparent_operator_is_one_maya_step():
    a, b, c = _scene()
    c.select_set(True)
    res = bpy.ops.allset.outliner_reparent(changes=json.dumps({"B": "A", "C": None}),
                                             select=json.dumps(["B"]), active="B")
    bpy.context.view_layer.update()
    assert res == {'FINISHED'}
    assert b.parent == a and _identity(b) and (b.matrix_world.translation - Vector((0, 2, 0))).length < 1e-5
    assert c.parent is None
    assert [o.name for o in bpy.context.selected_objects] == ["B"] and bpy.context.view_layer.objects.active == b


def test_lmb_drop_watch_and_mmb_keymap_item():
    assert od._on_depsgraph in bpy.app.handlers.depsgraph_update_post
    assert set(od.DROP_OPS) == {"OUTLINER_OT_parent_drop", "OUTLINER_OT_parent_clear"}
    kc = kit.maya_kc()
    items = [k for k in kc.keymaps["Outliner"].keymap_items
             if k.active and k.type == 'MIDDLEMOUSE' and k.value == 'PRESS' and not (k.shift or k.ctrl or k.alt)]
    assert [k.idname for k in items] == ["allset.outliner_drag"], [k.idname for k in items]
    pans = [k for k in kc.keymaps["View2D"].keymap_items if k.idname == "view2d.pan" and k.type == 'MIDDLEMOUSE']
    assert any(k.alt for k in pans)                                   # Alt+MMB pans (= Maya)
    assert ("Outliner", "allset.outliner_drag") in [(a[0], a[1]) for a in patches.ADDED]


def test_mmb_poll_object_mode_outliner_only():
    assert not bpy.ops.allset.outliner_drag.poll()                  # no Outliner region in background
