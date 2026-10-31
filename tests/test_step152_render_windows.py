"""Render menu option boxes: Render Sequence ❒ / Batch Render ❒ run Blender's render (no kit window, Blender has no
render options of its own), Render Current Frame ❒ is Maya's renderer warning."""

from importlib import import_module

import bpy

import kit

ow = import_module(kit.MODULE + ".operators.option_windows")
owr = import_module(kit.MODULE + ".operators.option_windows_render")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")


def test_render_sequence_and_batch_boxes_are_generic():
    assert not [w.key for w in ow.WINDOWS if w.key in ("render_sequence", "batch_render")]
    assert not hasattr(bpy.types, "ALLSET_OT_opt_render_sequence")
    for path in ("Render/Render Sequence", "Render/Batch Render"):
        assert menu_sets.option_kind(path) == "generic", path


def test_render_current_frame_box_is_maya_warning():
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    assert owr.no_options_text("Render/Render Current Frame", scene) == \
        'Renderer "Cycles" does not provide render options.'
    assert owr.no_options_text("Render/IPR Render Current Frame", scene).endswith("does not provide IPR options.")
    assert owr.no_options_text("Render/Render Sequence", scene) is None
    assert menu_sets.option_kind("Render/Render Current Frame") == "generic"
    # the generic option box reports the warning and opens nothing (its invoke; in -b INVOKE runs execute)
    import inspect
    assert "no_options_text" in inspect.getsource(ow.ALLSET_OT_option_generic.invoke)
