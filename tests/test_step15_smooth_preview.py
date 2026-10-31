"""Smooth Mesh Preview (1/2/3) is display only — smooth shading without
touching mesh data, never baked by Delete History, hidden from INPUTS."""

from importlib import import_module

import bpy

import kit

display = import_module(kit.MODULE + ".operators.display")
history = import_module(kit.MODULE + ".operators.history")
attribute_editor = import_module(kit.MODULE + ".ui.attribute_editor")


def _cube(name="c"):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    ob = bpy.context.active_object
    ob.name = name
    return ob


def _eval(ob):
    bpy.context.view_layer.update()
    return ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).data


def _names(ob):
    return [m.name for m in ob.modifiers]


def test_preview_is_smooth_without_changing_the_mesh():
    ob = _cube()
    assert not any(p.use_smooth for p in ob.data.polygons), "primitive starts flat"
    assert bpy.ops.allset.smooth_preview(level=3) == {'FINISHED'}
    assert _names(ob) == [display.PREVIEW_SHADE_NAME, display.PREVIEW_MOD_NAME], _names(ob)
    shade, sub = ob.modifiers
    assert shade.type == 'NODES' and shade.node_group.name == display.SHADE_GROUP_NAME
    assert not shade.show_render and not sub.show_render, "renders unchanged"
    me = _eval(ob)
    assert len(me.vertices) > 8 and all(p.use_smooth for p in me.polygons), "preview looks smooth"
    assert len(ob.data.vertices) == 8 and not any(p.use_smooth for p in ob.data.polygons), \
        "mesh data untouched"
    bpy.ops.allset.smooth_preview(level=1)
    assert not shade.show_viewport and not sub.show_viewport
    me = _eval(ob)
    assert len(me.vertices) == 8 and not any(p.use_smooth for p in me.polygons), "1 = flat again"


def test_preview_subsurf_stays_last():
    # Subsurf last keeps Blender's GPU subdivision; the shading modifier sits before it.
    ob = _cube()
    ob.modifiers.new("bevel", 'BEVEL')
    bpy.ops.allset.smooth_preview(level=3)
    assert _names(ob) == ["bevel", display.PREVIEW_SHADE_NAME, display.PREVIEW_MOD_NAME]
    # An older file (0.1.0) has the preview Subsurf without the shading modifier.
    ob.modifiers.remove(ob.modifiers[display.PREVIEW_SHADE_NAME])
    ob.modifiers.new("wave", 'WAVE')
    bpy.ops.allset.smooth_preview(level=3)
    assert _names(ob) == ["bevel", display.PREVIEW_SHADE_NAME, display.PREVIEW_MOD_NAME, "wave"], _names(ob)


def test_preview_in_edit_mode():
    ob = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    assert bpy.ops.allset.smooth_preview(level=3) == {'FINISHED'}
    assert _names(ob) == [display.PREVIEW_SHADE_NAME, display.PREVIEW_MOD_NAME]
    bpy.ops.object.mode_set(mode='OBJECT')


def test_delete_history_keeps_the_preview():
    ob = _cube()
    bpy.ops.allset.smooth_preview(level=3)
    assert bpy.ops.allset.delete_history() == {'FINISHED'}
    assert len(ob.data.vertices) == 8, "preview not baked into the mesh"
    assert _names(ob) == [display.PREVIEW_SHADE_NAME, display.PREVIEW_MOD_NAME]
    assert all(m.show_viewport for m in ob.modifiers), "preview still on"
    bpy.ops.allset.delete_history(non_deformer=True)
    assert len(ob.data.vertices) == 8
    assert _names(ob) == [display.PREVIEW_SHADE_NAME, display.PREVIEW_MOD_NAME]


def test_delete_history_bakes_user_subsurf_but_not_preview():
    ob = _cube()
    ob.modifiers.new("polySmooth1", 'SUBSURF').levels = 1
    bpy.ops.allset.smooth_preview(level=3)
    bpy.ops.allset.delete_history()
    assert len(ob.data.vertices) == 26, len(ob.data.vertices)   # one level of a cube
    assert _names(ob) == [display.PREVIEW_SHADE_NAME, display.PREVIEW_MOD_NAME]


def test_non_deformer_history_with_preview_and_deformer():
    ob = _cube()
    ob.modifiers.new("bevel", 'BEVEL')
    ob.modifiers.new("arm", 'ARMATURE')
    bpy.ops.allset.smooth_preview(level=3)
    baked, notes = history.delete_history(bpy.context, [ob], non_deformer=True)
    assert baked == 1 and not notes, notes
    assert _names(ob) == ["arm", display.PREVIEW_SHADE_NAME, display.PREVIEW_MOD_NAME], _names(ob)
    assert len(ob.data.vertices) > 8, "bevel baked"


def test_preview_only_object_has_no_history():
    ob = _cube()
    bpy.ops.allset.smooth_preview(level=3)
    baked, _notes = history.delete_history(bpy.context, [ob])
    assert baked == 0


def test_preview_hidden_from_inputs():
    ob = _cube()
    ob.modifiers.new("polySmooth1", 'SUBSURF')
    bpy.ops.allset.smooth_preview(level=3)
    keys = [k for k, _label, _t in attribute_editor.tabs(ob)]
    assert "M:polySmooth1" in keys
    assert not any(display.PREVIEW_MOD_NAME in k for k in keys), keys
