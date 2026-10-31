"""Make Blender Maya and New Scene in Maya Layout change none of Blender's
preferences and write nothing outside the extension.

The welcome dialog and the start-in-Maya-layout switch need a GUI; here: what make and the
new Maya scene change and that nothing leaks.
"""

import os
from importlib import import_module

import addon_utils
import bpy

import kit

app_template = import_module(kit.MODULE + ".app_template")
preferences = import_module(kit.MODULE + ".preferences")
first_start = import_module(kit.MODULE + ".first_start")
OTHER = "node_wrangler"   # a core add-on the "user" had on before installing the kit


def _addons():
    return set(bpy.context.preferences.addons.keys())


def _prefs():
    s = kit.snapshot()
    return {k: s[k] for k in ("prefs_inputs", "prefs_view", "prefs_edit", "prefs_system_wire", "theme", "ui_styles")}


def _templates_dir():
    return bpy.utils.user_resource('SCRIPTS', path=os.path.join("startup", "bl_app_templates_user"))


def test_runs_sandboxed():
    cfg = os.path.normcase(bpy.utils.user_resource('CONFIG'))
    assert os.path.normcase(os.path.join("tmp", os.environ.get("ALLSET_SANDBOX", "test_env"))) in cfg, cfg


def test_make_maya_changes_no_preferences():
    addon_utils.enable(OTHER, default_set=True)
    before_addons = _addons()
    before = _prefs()
    template = bpy.context.preferences.app_template
    first_start.make(bpy.context, open_layout=True)     # the operator opens the layout from a timer: call it here
    prefs = preferences.get()
    assert prefs.start_in_maya_layout and prefs.welcome_done
    assert kit.diff(before, _prefs()) == [], kit.diff(before, _prefs())
    assert bpy.context.preferences.app_template == template, "no app template switch"
    assert not os.path.isdir(os.path.join(_templates_dir(), app_template.TEMPLATE_ID)), "nothing copied out"
    assert _addons() == before_addons, (_addons() ^ before_addons)   # nothing switched off or on
    # the new Maya scene: the bundled layout as an untitled file
    assert bpy.data.filepath == ""
    assert bpy.context.scene.unit_settings.length_unit == 'CENTIMETERS'
    assert any(m.name == ".AllsetStrip" for m in bpy.data.masks), [m.name for m in bpy.data.masks]
    addon_utils.disable(OTHER, default_set=True)


def test_make_without_opening_keeps_the_file():
    bpy.ops.wm.read_homefile()
    bpy.ops.mesh.primitive_cube_add()
    name = bpy.context.active_object.name
    assert bpy.ops.allset.make_maya(open_layout=False) == {'FINISHED'}
    assert name in bpy.data.objects, "open_layout=False leaves the open file alone"


def test_new_maya_scene_reads_the_bundled_file():
    assert os.path.isfile(app_template.STARTUP)
    before = _prefs()
    first_start.new_maya_scene()
    assert bpy.data.filepath == "" and bpy.context.scene.unit_settings.length_unit == 'CENTIMETERS'
    assert kit.diff(before, _prefs()) == []
    bpy.ops.wm.read_homefile()
