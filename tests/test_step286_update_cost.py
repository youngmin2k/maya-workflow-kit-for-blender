"""Issue #191: with many objects a move, a mesh edit or a selection change no longer makes the kit walk the
whole scene, and everything those walks keep up to date still follows the edits that matter: Outliner rows (rename,
parent, unparent, add, delete, edit-mode bones, undo), DAG visibility of children, symmetry on entering edit mode,
lambert1 on new objects, Outliner order and joint labels."""

import time
from importlib import import_module

import bpy

import kit

M = kit.MODULE
outliner = import_module(M + ".ui.outliner")
dag = import_module(M + ".operators.dag")
symmetry = import_module(M + ".operators.symmetry")
material = import_module(M + ".operators.material")
dfilter = import_module(M + ".depsgraph_filter")
CUBES = 300


def _scene():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    scene = bpy.context.scene
    me = bpy.data.meshes.new("c")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    for i in range(CUBES):
        o = bpy.data.objects.new(f"c{i}", me)
        o.location = (i % 30, i // 30, 0)
        scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    return scene


def _rows_ok():
    wm, sc = bpy.context.window_manager, bpy.context.scene
    want = outliner.dag_rows(sc, wm.allset_outliner_shapes)
    have = [(r.kind, r.object, r.depth, r.has_children, r.bone) for r in wm.allset_outliner_rows]
    return want == have


class Counter:
    """Counts calls of module functions that walk the whole scene."""

    def __init__(self, *targets):
        self.targets, self.n, self._orig = targets, {}, []

    def __enter__(self):
        for mod, name in self.targets:
            fn = getattr(mod, name)
            key = f"{mod.__name__.rsplit('.', 1)[-1]}.{name}"
            self.n[key] = 0

            def w(*a, _fn=fn, _key=key, **k):
                self.n[_key] += 1
                return _fn(*a, **k)
            setattr(mod, name, w)
            self._orig.append((mod, name, fn))
        return self

    def __exit__(self, *exc):
        for mod, name, fn in self._orig:
            setattr(mod, name, fn)


def _walkers():
    return Counter((outliner, "dag_rows"), (dag, "sync"), (symmetry, "edit_meshes"))


def test_move_and_select_walk_nothing():
    _scene()
    c0, c1 = bpy.data.objects["c0"], bpy.data.objects["c1"]
    with _walkers() as cnt:
        for i in range(10):
            c0.location.x = i * 0.1
            bpy.context.view_layer.update()
        for o in (c0, c1, c0):
            o.select_set(not o.select_get())
            bpy.context.view_layer.update()
    # selection: DAG visibility still runs (hide_set is a Scene-only update too)
    assert cnt.n["outliner.dag_rows"] == 0 and cnt.n["symmetry.edit_meshes"] == 0, cnt.n
    assert cnt.n["dag.sync"] <= 3, cnt.n
    assert _rows_ok()


def test_structure_edits_keep_rows_right():
    scene = _scene()
    c0, c1, c2 = (bpy.data.objects[f"c{i}"] for i in range(3))
    v = outliner.structure_version()
    c0.location.x = 3.0
    bpy.context.view_layer.update()
    assert outliner.structure_version() == v, "a move bumped the structure version"
    for tag, edit in (("rename", lambda: setattr(c0, "name", "renamed")),
                      ("parent", lambda: setattr(c1, "parent", c0)),
                      ("unparent", lambda: setattr(c1, "parent", None)),
                      ("hide_set", lambda: c2.hide_set(True)),
                      ("select", lambda: c2.select_set(True))):
        edit()
        bpy.context.view_layer.update()
        assert _rows_ok(), f"rows stale after {tag}"
    assert outliner.structure_version() > v
    new = bpy.data.objects.new("added", c0.data)
    scene.collection.objects.link(new)
    bpy.context.view_layer.update()
    assert _rows_ok(), "rows stale after add"
    bpy.data.objects.remove(new)
    bpy.context.view_layer.update()
    assert _rows_ok(), "rows stale after delete"


def test_edit_mode_bone_add_and_undo():
    scene = _scene()
    arm = bpy.data.objects.new("rig", bpy.data.armatures.new("rig"))
    scene.collection.objects.link(arm)
    arm.allset_expanded = True
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones.new("joint1")
    eb.head, eb.tail = (0, 0, 0), (0, 0, 1)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()
    assert any(r.bone == "joint1" for r in bpy.context.window_manager.allset_outliner_rows), "bone row missing"
    assert _rows_ok()
    bpy.ops.ed.undo_push(message="before add")
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.ed.undo_push(message="add")
    assert _rows_ok()
    bpy.ops.ed.undo()
    assert _rows_ok(), "rows stale after undo"


def test_hidden_parent_still_hides_children():
    _scene()
    c0, c1 = bpy.data.objects["c0"], bpy.data.objects["c1"]
    c1.parent = c0
    bpy.context.view_layer.update()
    c0.hide_viewport = True
    bpy.context.view_layer.update()
    assert c1.hide_get(), "child of a hidden node shown"
    c0.location.x = 2.0                      # a move after that: nothing changes
    bpy.context.view_layer.update()
    assert c1.hide_get()
    c0.hide_viewport = False
    bpy.context.view_layer.update()
    assert not c1.hide_get()


def test_symmetry_on_entering_edit_mode():
    _scene()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    sym = bpy.context.scene.allset_symmetry
    sym.on, sym.about, sym.axis = True, 'OBJECT', 'X'
    ob.data.use_mirror_x = False
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.view_layer.update()
    assert ob.data.use_mirror_x, "symmetry not applied on entering edit mode"
    bpy.ops.object.mode_set(mode='OBJECT')
    sym.on = False


def test_new_object_gets_lambert1():
    if not material._maya_scene():
        return                               # the default material belongs to kit (Maya) scenes only
    _scene()
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.view_layer.update()
    ob = bpy.context.active_object
    assert ob.material_slots and ob.material_slots[0].material is material.default_material(), \
        [s.material for s in ob.material_slots]


def test_filter_rules():
    _scene()
    seen = {}

    def watch(scene, depsgraph):
        seen["motion"] = dfilter.only_motion(depsgraph)
        seen["scene"] = dfilter.only_scene(depsgraph)
        seen["skip"] = dfilter.outliner_skip(depsgraph)
    bpy.app.handlers.depsgraph_update_post.append(watch)
    try:
        c0 = bpy.data.objects["c0"]
        c0.location.x = 5.0
        bpy.context.view_layer.update()
        assert seen == {"motion": True, "scene": False, "skip": True}, ("move", seen)
        c0.select_set(not c0.select_get())
        bpy.context.view_layer.update()
        assert seen["scene"] and seen["skip"] and not seen["motion"], ("select", seen)
        c0.name = "other"
        bpy.context.view_layer.update()
        assert not seen["skip"] and not seen["motion"], ("rename", seen)
    finally:
        bpy.app.handlers.depsgraph_update_post.remove(watch)
    assert dfilter.only_motion(None) is False and dfilter.outliner_skip(None) is False


def test_update_cost_budget():
    """Kit handlers on a move at 300 objects: well under a millisecond per update."""
    _scene()
    c0 = bpy.data.objects["c0"]
    times = []
    for i in range(60):
        c0.location.x = i * 0.01
        t = time.perf_counter()
        bpy.context.view_layer.update()
        times.append(time.perf_counter() - t)
    times.sort()
    median = times[len(times) // 2] * 1000
    assert median < 1.0, f"update median {median:.3f} ms"
