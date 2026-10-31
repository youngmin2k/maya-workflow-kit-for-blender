"""0.7.0 release check: Python errors the seeded monkey found. Select > Similar in edit mode with
nothing selected reports Blender's refusal instead of a Python traceback."""

import bpy



def _scene():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _menu(item):
    """Run a Maya menu item; return (result, error text) — an ERROR report raises RuntimeError at the caller."""
    try:
        return bpy.ops.allset.menu_item(item=item), ""
    except RuntimeError as ex:
        return None, str(ex)


def test_select_similar_with_nothing_selected():
    _scene()
    bpy.ops.allset.create(kind='CUBE')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    res, err = _menu("Select/Similar")
    assert "Traceback" not in err, err
    assert res in (None, {'CANCELLED'}, {'FINISHED'}), res
    bpy.ops.object.mode_set(mode='OBJECT')


def test_pivot_and_live_drags_start_fresh():
    """A handle that doesn't set the constraint (the pivot / live centre square) must not take the axis of the
    drag before (D+V after a D+X axis drag moved along X only)."""
    for idname in ("pivot_translate", "live_translate", "component_scale", "pivot_rotate"):
        rna = getattr(bpy.ops.allset, idname).get_rna_type()
        props = [p for p in rna.properties if p.identifier != "rna_type" and p.is_hidden]
        assert props, idname
        stale = [p.identifier for p in props if not p.is_skip_save]
        assert not stale, (idname, stale)
