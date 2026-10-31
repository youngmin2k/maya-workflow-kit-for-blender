"""The Maya layout file bundled in the extension (never copied into the user's scripts folder as an
app template; "New Scene in Maya Layout" reads it as an untitled file)."""

import os
from importlib import import_module

import bpy

import kit

app_template = import_module(kit.MODULE + ".app_template")
first_start = import_module(kit.MODULE + ".first_start")


def test_bundled_layout_files():
    src = app_template.SOURCE_DIR
    assert sorted(f for f in os.listdir(src) if not f.startswith("__pycache__")) == \
        ["splash.png", "splash_2x.png", "startup.blend"]   # data only, no code
    assert app_template.STARTUP == os.path.join(src, "startup.blend")


# --- theme --------------------------------------------------------------------------------

def test_no_theme_in_the_kit():
    """#40: the kit ships no theme and has no theme operators; the user's theme is never written."""
    import importlib.util
    assert importlib.util.find_spec(kit.MODULE + ".theme") is None
    assert not hasattr(bpy.types, "ALLSET_OT_theme_apply") and not hasattr(bpy.types, "ALLSET_OT_theme_restore")
    root = os.path.dirname(import_module(kit.MODULE).__file__)
    xml = [os.path.join(d, f) for d, _s, fs in os.walk(root) for f in fs if f.endswith(".xml")]
    assert not xml, xml


def test_nothing_installed_into_user_scripts():
    assert not hasattr(app_template, "install") and not hasattr(app_template, "remove_on_disable")
    tpl = bpy.utils.user_resource('SCRIPTS', path=os.path.join("startup", "bl_app_templates_user"))
    assert not os.path.isdir(tpl), os.listdir(tpl)


# --- loading the layout (last: replaces the open file) -----------------------------------

def test_new_maya_scene_layout():
    template = bpy.context.preferences.app_template
    first_start.new_maya_scene()
    assert bpy.context.preferences.app_template == template, "no app template switch"
    assert bpy.data.filepath == "", "an untitled file: saving never writes into the extension"
    assert kit.is_enabled()
    # the flat #5c5c5c viewport as view data, not theme (#45): scene linear 0.10702
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D' and area.spaces.active.show_region_header:   # not the Tool Box column
                sh = area.spaces.active.shading
                assert sh.background_type == 'VIEWPORT', (screen.name, sh.background_type)
                assert abs(sh.background_color[0] - 0.10702) < 1e-3, tuple(sh.background_color)
    ws = bpy.data.workspaces["General"]
    scr = ws.screens[0]
    types = sorted(a.type for a in scr.areas)
    # Maya General: Status Line row, Shelf row, Tool Box (narrow 3D View), Outliner, view,
    # Time + Range Slider (timeline); CB/LE, AE and MTK are Maya's right tab stack, its own Properties area.
    assert types == ['DOPESHEET_EDITOR', 'IMAGE_EDITOR', 'IMAGE_EDITOR', 'OUTLINER', 'PROPERTIES', 'VIEW_3D',
                     'VIEW_3D'], types
    outliners = [a.spaces.active for a in scr.areas if a.type == 'OUTLINER']
    assert outliners[0].use_filter_object and not outliners[0].use_filter_object_content, "DAG-only Outliner"
    v3d = max((a for a in scr.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height).spaces.active
    # no sidebar (the Maya panels are their own areas); the Tool Box column replaces the toolbar;
    # the tool header row is Maya's panel toolbar
    assert not v3d.show_region_ui and not v3d.show_region_toolbar and v3d.show_region_tool_header
    # persp angle (35 mm on 36 mm film) = Blender viewport lens 70 (72 mm sensor)
    assert abs(v3d.lens - 70.0) < 1e-6
    for area in scr.areas:
        if area.type == 'VIEW_3D':
            assert abs(area.spaces.active.lens - 70.0) < 1e-6, area

    scene = bpy.context.scene
    assert scene.unit_settings.length_unit == 'CENTIMETERS' and scene.unit_settings.scale_length == 1.0
    # animation range 1-200 = frame range, playback 1-120 = preview range
    assert (scene.frame_start, scene.frame_end, scene.render.fps) == (1, 200, 24)
    assert scene.use_preview_range and (scene.frame_preview_start, scene.frame_preview_end) == (1, 120)
    # only Maya's hidden startup cameras (operators/startup_cameras.py)
    assert sorted(o.name for o in bpy.data.objects) == ["front", "persp", "side", "top"],         [o.name for o in bpy.data.objects]
    assert all(o.get("allset_startup_camera") and o.hide_viewport for o in bpy.data.objects)
    bpy.ops.wm.read_homefile()
