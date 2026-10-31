"""Kit bug the audit-7 session found — the Channel Box depsgraph handler raised AttributeError when the context
(a File Browser / Preferences window) has no ``active_object`` member."""

from importlib import import_module

import bpy

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")


class _NoActive:
    """A context with a scene and view layer but no ``active_object`` (like a File Browser window's)."""

    def __init__(self):
        self.scene = bpy.context.scene
        self.view_layer = bpy.context.view_layer
        self.selected_objects = []


def test_lead_without_active_object_member():
    ob = bpy.data.objects.new("pCube1", bpy.data.meshes.new("pCubeShape1"))
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ctx = _NoActive()
    assert not hasattr(ctx, "active_object")
    assert cb.pose_armature(ctx) is None
    assert cb.placing_joints(ctx) is False
    assert cb.lead(ctx) == ob, cb.lead(ctx)
    cb.rebuild_rows(ctx)   # raised AttributeError in the depsgraph handler before
