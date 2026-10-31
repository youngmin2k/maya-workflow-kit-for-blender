"""Issue #154: the Game Exporter is a kit window that stays open (Maya: a plain floating
window), with Maya 2026's field facts (the
and the node's attributes): an "Up Axis" label before Y / Z, File Name empty with the grey hint
"Enter a filename" (one file) / "Multi File Prefix" / "Clip File Prefix", a new clip = empty name shown as the
"Clip Name" hint with the playback range, Maya's error texts."""

import inspect
from importlib import import_module

import bpy

import kit

ge = import_module(kit.MODULE + ".operators.game_exporter")
mw = import_module(kit.MODULE + ".ui.marked_window")


def _s():
    s = bpy.context.scene.allset_game_exporter
    s.clips.clear()
    s.export_type, s.export_filename = 'MODEL', ""
    s.model_file_mode, s.file_split = 'SINGLE', 'SINGLE'
    return s


def test_window_kind_is_unique_and_the_panel_polls_only_there():
    assert ge.KIND in mw.KINDS
    marks = [frozenset(v) for v in mw.KINDS.values()]
    assert len(marks) == len(set(marks)), "two marked windows share a flag pair"
    assert ge.ALLSET_PT_game_exporter.bl_category == "Tool"
    # no popup any more: the menu operator opens the window (no invoke_props_dialog)
    src = inspect.getsource(ge.ALLSET_OT_game_exporter)
    assert "invoke_props_dialog" not in src and "open_window" in src


def test_file_name_starts_empty_with_mayas_hints():
    s = _s()
    assert s.export_filename == ""                     # Maya 2026: exportFilename ""
    assert ge.filename_placeholder(s) == "Enter a filename"
    s.model_file_mode = 'PER_ROOT'
    assert ge.filename_placeholder(s) == "Multi File Prefix"
    s.export_type = 'ANIMATION'
    assert ge.filename_placeholder(s) == "Enter a filename"
    s.file_split = 'PER_CLIP'
    assert ge.filename_placeholder(s) == "Clip File Prefix"


def test_new_clip_is_empty_with_the_playback_range():
    s = _s()
    sc = bpy.context.scene
    sc.use_preview_range = False
    sc.frame_start, sc.frame_end = 5, 40
    c = ge.add_clip(sc)
    assert c.name == "" and (c.start, c.end) == (5.0, 40.0) and c.export
    src = inspect.getsource(ge.ALLSET_UL_game_clips.draw_item)
    assert 'placeholder="Clip Name"' in src           # the hint Maya shows in the empty name field


def test_mayas_error_texts():
    import tempfile
    s = _s()
    s.export_path = tempfile.mkdtemp(prefix="allset263_")
    try:
        ge.export(bpy.context, s)
        raise AssertionError("exported without a file name")
    except ValueError as ex:
        assert str(ex) == "Choose a file name to export"
    s.export_type, s.export_filename = 'ANIMATION', "hero"
    ge.add_clip(bpy.context.scene)
    try:
        ge.export(bpy.context, s)
        raise AssertionError("exported a clip without a name")
    except ValueError as ex:
        assert str(ex) == "Cannot export a clip without a name."


def test_up_axis_has_its_label():
    src = inspect.getsource(ge.draw)
    assert '_row(col, "Up Axis")' in src
