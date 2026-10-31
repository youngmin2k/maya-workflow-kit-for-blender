"""#57: Maya's Save Changes prompt before New Scene (ui/save_prompt.py). Headless: the texts with and without
a file path (the wording of Maya's Save Changes dialog), the answers' effects (Cancel = nothing, Don't Save = the
action, Save with a path = save then the action, untitled Save = the action only after a real save), and every New
Scene path (Ctrl+N / File > New Scene operator, the New Scene option window) going through the prompt.
The dialog itself, clicks and the Save As browser: tests/gui/gui_step138_prompt.py."""

import os
from importlib import import_module

import bpy

import kit

save_prompt = import_module(kit.MODULE + ".ui.save_prompt")
first_start = import_module(kit.MODULE + ".first_start")
option_windows = import_module(kit.MODULE + ".operators.option_windows")
menu_map = import_module(kit.MODULE + ".ui.menu_map")

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp", "test_step138_prompt")


def _calls():
    log = []
    return log, (lambda: log.append("ran"))


def _modified():
    bpy.ops.mesh.primitive_cube_add('EXEC_DEFAULT', True)     # undo push = a modified file
    if not bpy.data.is_dirty:
        # background undo pushes may not mark the file; any change of the open file is what matters here
        bpy.context.scene.frame_current += 1
        bpy.ops.ed.undo_push(message="test")
    return bpy.data.is_dirty


def test_texts_untitled_and_saved():
    assert save_prompt.title("") == "Warning: Scene Not Saved"
    assert save_prompt.message("") == "Save changes to untitled scene?"
    path = os.path.join("C:\\", "proj", "scenes", "shot.blend")
    assert save_prompt.title(path) == "Save Changes"
    assert save_prompt.message(path) == f"Save changes to {path}?"
    assert [c[1] for c in save_prompt.CHOICES] == ["Save", "Don't Save", "Cancel"]


# An unmodified scene runs the action without asking: GUI test (in -b a loaded or saved file still reads is_dirty).


def test_cancel_does_nothing():
    bpy.ops.wm.read_homefile()
    assert _modified()
    log, fn = _calls()
    assert save_prompt.ask(bpy.context, fn) == {'CANCELLED'}      # headless: waits for the answer
    assert save_prompt._pending[0] is fn
    assert save_prompt.choose(bpy.context, 'CANCEL') == {'CANCELLED'}
    save_prompt._run_tick()
    assert log == [] and save_prompt._pending[0] is None and bpy.data.is_dirty


def test_dont_save_runs_the_new_scene():
    bpy.ops.wm.read_homefile()
    assert _modified()
    save_prompt.ask(bpy.context, first_start.new_maya_scene)
    assert save_prompt.choose(bpy.context, 'DONT_SAVE') == {'FINISHED'}
    assert "Cube" in bpy.data.objects, "nothing loaded inside the answer (a timer does it)"
    save_prompt._run_tick()
    assert "Cube" not in bpy.data.objects and not bpy.data.filepath
    assert bpy.context.scene.unit_settings.length_unit == 'CENTIMETERS', "the Maya layout file"
    bpy.ops.wm.read_homefile()


def test_save_with_path_saves_first():
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "saved.blend")
    if os.path.exists(path):
        os.remove(path)
    bpy.ops.wm.read_homefile()
    bpy.ops.wm.save_as_mainfile(filepath=path)
    before = os.path.getmtime(path)
    bpy.ops.object.empty_add()
    bpy.context.active_object.name = "AfterSave"
    assert _modified()
    log, fn = _calls()
    save_prompt.ask(bpy.context, fn)
    assert save_prompt.message() == f"Save changes to {path}?"
    assert save_prompt.choose(bpy.context, 'SAVE') == {'FINISHED'}
    assert os.path.getmtime(path) >= before
    assert log == []
    save_prompt._run_tick()
    assert log == ["ran"], "the action after the save"
    bpy.ops.wm.read_homefile()
    with bpy.data.libraries.load(path) as (src, _dst):
        assert "AfterSave" in src.objects, src.objects


def test_untitled_save_waits_for_the_save():
    log, fn = _calls()
    # saved: the action runs from the watch timer
    save_prompt._watch_save(fn)
    assert save_prompt._on_save_post in bpy.app.handlers.save_post
    save_prompt._on_save_post(__file__)
    assert save_prompt._watch_tick() is None
    assert log == ["ran"] and save_prompt._on_save_post not in bpy.app.handlers.save_post
    # the browser was shown and closed without a save: nothing
    log.clear()
    save_prompt._watch_save(fn)
    save_prompt._save_watch["seen"] = True
    assert save_prompt._watch_tick() is None and log == []
    assert save_prompt._on_save_post not in bpy.app.handlers.save_post
    # no browser at all within the wait: nothing either
    save_prompt._watch_save(fn)
    save_prompt._save_watch["ticks"] = int(save_prompt.WATCH_SECONDS * 10) + 1
    assert save_prompt._watch_tick() is None and log == []
    save_prompt._stop_watch()


def test_every_new_scene_path_asks():
    assert menu_map.MAP["File/New Scene"] == "allset.new_maya_scene"
    bpy.ops.wm.read_homefile()
    assert _modified()
    # the operator's invoke (Ctrl+N, File > New Scene, Status Line button)
    op = first_start.ALLSET_OT_new_maya_scene
    assert op.invoke(None, bpy.context, None) == {'CANCELLED'}
    assert save_prompt._pending[0] is first_start.new_maya_scene
    save_prompt.choose(bpy.context, 'CANCEL')
    # the New Scene option window (a plain File > New Scene with saved options runs it too)
    window = option_windows.find_path("File/New Scene")
    assert window is not None
    values = {f.name: f.default for f in window.fields}
    assert option_windows._run_new_scene(bpy.context, values) == {'FINISHED'}
    assert save_prompt._pending[0] is not None and "Cube" in bpy.data.objects, "asks, loads nothing yet"
    save_prompt.choose(bpy.context, 'CANCEL')
    bpy.ops.wm.read_homefile()


def test_unregister_leaves_nothing():
    save_prompt._watch_save(lambda: None)
    save_prompt.run_later(lambda: None)
    kit.disable()
    assert save_prompt._on_save_post not in bpy.app.handlers.save_post
    assert not bpy.app.timers.is_registered(save_prompt._watch_tick)
    assert not bpy.app.timers.is_registered(save_prompt._run_tick)
    kit.enable()
