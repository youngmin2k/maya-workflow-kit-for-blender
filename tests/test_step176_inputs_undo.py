"""pCube1's creation node through Ctrl+D / Ctrl+G / Ctrl+Z / P.

The dogfood session lost Channel Box INPUTS polyCube1 between shots 04 and 05. Its keys there are 3 -> Alt+Shift+D ->
1 -> Ctrl+D -> Ctrl+G -> Ctrl+Z -> P; Alt+Shift+D is Maya's Delete History (``delete -ch``),
which removes polyCube1 as in Maya. The other commands must
keep the node, also across a real undo (``ed.undo_push`` makes the undo stack in background; the commands
run at undo depth 0 like a key press). GUI replay: tests/gui/gui_step176_inputs_undo.py.
"""

from importlib import import_module

import bpy

import kit

prim_history = import_module(kit.MODULE + ".operators.prim_history")
creation_inputs = import_module(kit.MODULE + ".ui.creation_inputs")


def _fresh():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for data in list(bpy.data.meshes):
        bpy.data.meshes.remove(data)


def _only(*names):
    for o in bpy.context.scene.objects:
        o.select_set(o.name in names)
    bpy.context.view_layer.objects.active = bpy.data.objects[names[-1]]


def _key(op, **props):
    """A command at undo depth 0 (what a key press does)."""
    assert op('EXEC_DEFAULT', True, **props) == {'FINISHED'}, op


def _shown(name):
    return creation_inputs.has_node(bpy.data.objects[name])


def _session(delete_history):
    _fresh()
    bpy.ops.ed.undo_push(message="test start")
    _key(bpy.ops.allset.create, kind='CUBE')
    _only("pCube1")
    seen = {"created": _shown("pCube1")}
    if delete_history:
        _key(bpy.ops.allset.delete_history)
        seen["delete history"] = _shown("pCube1")
    _key(bpy.ops.allset.duplicate)
    dup = bpy.context.view_layer.objects.active.name
    seen["duplicate"] = _shown("pCube1")
    bpy.data.objects[dup].location.x = 3
    _only(dup, "pCube1")
    _key(bpy.ops.allset.group)
    seen["group"] = _shown("pCube1")
    assert any(o.type == 'EMPTY' for o in bpy.context.scene.objects)
    bpy.ops.ed.undo()
    seen["undo"] = _shown("pCube1")
    assert not any(o.type == 'EMPTY' for o in bpy.context.scene.objects), "undo removes the group"
    _only(dup, "pCube1")
    _key(bpy.ops.allset.parent)
    assert bpy.data.objects[dup].parent == bpy.data.objects["pCube1"]
    seen["parent"] = _shown("pCube1")
    return seen


def test_creation_node_survives_duplicate_group_undo_parent():
    seen = _session(delete_history=False)
    assert all(seen.values()), seen


def test_dogfood_order_loses_the_node_only_at_delete_history():
    seen = _session(delete_history=True)
    assert seen.pop("created"), seen
    assert not any(seen.values()), seen
    assert prim_history.owner_of(bpy.data.objects["pCube1"]) is None
