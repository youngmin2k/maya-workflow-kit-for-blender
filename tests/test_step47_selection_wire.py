"""Maya wireframe on selected objects — the kit draws the evaluated edges itself (POST_VIEW),
so nothing is written to the file; batches are cached per object and dropped when the geometry changes."""

import os
import tempfile
from importlib import import_module

import bpy

import kit

sw = import_module(kit.MODULE + ".ui.selection_wire")


def _scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    obs = []
    for i, name in enumerate(("pCube1", "pCube2", "pCube3")):
        me = bpy.data.meshes.new(name + "Shape")
        me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
        ob = bpy.data.objects.new(name, me)
        ob.location.x = 2 * i
        bpy.context.scene.collection.objects.link(ob)
        obs.append(ob)
    bpy.context.view_layer.update()
    return obs


def _select(*obs, active=None):
    vl = bpy.context.view_layer
    for ob in vl.objects:
        if ob is not None:
            ob.select_set(ob in obs)
    vl.objects.active = active or (obs[-1] if obs else None)


def test_wire_objects_follow_selection_and_mode():
    a, b, c = _scene()
    _select(a, b, active=a)
    assert {o.name for o in sw.wire_objects(bpy.context)} == {"pCube1", "pCube2"}
    _select(c)
    assert [o.name for o in sw.wire_objects(bpy.context)] == ["pCube3"]
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        assert sw.wire_objects(bpy.context) == []      # Blender's edit mesh drawing instead
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')


def test_evaluated_edges_include_modifiers():
    a, _b, _c = _scene()
    dg = bpy.context.evaluated_depsgraph_get()
    co, ed = sw.edges_of(a, dg)
    assert co.shape == (4, 3) and ed.shape == (4, 2)
    a.modifiers.new("sub", 'SUBSURF').levels = 1
    dg = bpy.context.evaluated_depsgraph_get()
    co, ed = sw.edges_of(a, dg)
    assert ed.shape[0] == 12 and co.dtype.name == "float32" and ed.dtype.name == "int32"


def test_geometry_change_drops_cached_batch():
    a, b, _c = _scene()
    sw._batches[a.session_uid] = (None, 4)
    sw._batches[b.session_uid] = (None, 4)
    a.data.vertices[0].co.z = 1.0
    a.data.update()
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    sw._on_depsgraph(bpy.context.scene, dg)
    assert a.session_uid not in sw._batches and b.session_uid in sw._batches
    sw._on_reload()
    assert not sw._batches


def test_saved_file_keeps_no_wire():
    a, b, c = _scene()
    _select(a, b)
    path = os.path.join(tempfile.mkdtemp(prefix="mk47_"), "wire.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    with bpy.data.libraries.load(path) as (src, dst):
        dst.objects = [n for n in src.objects]
    loaded = [ob for ob in dst.objects if ob is not None]
    try:
        assert len(loaded) == 3
        left = [(ob.name, ob.show_wire, list(ob.keys())) for ob in loaded
                if ob.show_wire or any(k.startswith("allset_") for k in ob.keys())]
        assert not left, left
    finally:
        for ob in loaded:
            bpy.data.objects.remove(ob)
    assert not a.show_wire and not b.show_wire       # in memory either


def test_option_and_disable():
    prefs = bpy.context.preferences.addons[kit.MODULE].preferences
    assert prefs.maya_selection_wire                    # default, like Maya: wireframe on selected
    prefs.maya_selection_wire = False
    assert not sw._enabled()
    prefs.maya_selection_wire = True
    assert sw._handle and sw._on_depsgraph in bpy.app.handlers.depsgraph_update_post
    kit.disable()
    try:
        assert not sw._handle and sw._on_depsgraph not in bpy.app.handlers.depsgraph_update_post
    finally:
        kit.enable()
