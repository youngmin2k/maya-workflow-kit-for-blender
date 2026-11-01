"""Maya menu bar + menu sets, Status Line, command line, cmds_shim, Help Line."""

import math
import sys
import types
from importlib import import_module

import bpy

import kit

menu_data = import_module(kit.MODULE + ".ui.menu_data")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
status_line = import_module(kit.MODULE + ".ui.status_line")
hold = import_module(kit.MODULE + ".operators.hold")
command_line = import_module(kit.MODULE + ".command_line")
runner = import_module(kit.MODULE + ".command_line.runner")
cmds = import_module(kit.MODULE + ".command_line.cmds_shim")


# --- helpers ---------------------------------------------------------------------

class FakeLayout:
    """Records what a draw function puts in a layout."""

    def __init__(self, log=None):
        self.log = [] if log is None else log
        self.alert = False
        self.enabled = True
        self.ui_units_x = 0
        self.alignment = 'EXPAND'
        self.operator_context = 'INVOKE_DEFAULT'

    def _sub(self, *_a, **_k):
        return FakeLayout(self.log)

    row = column = box = split = _sub

    def menu(self, idname, text=None, **kw):
        self.log.append(("menu", idname, text))

    def operator(self, idname, text=None, **kw):
        props = types.SimpleNamespace()
        self.log.append(("op", idname, text, props, kw))
        return props

    def operator_menu_hold(self, idname, text=None, **kw):   # items with a Maya option box
        props = types.SimpleNamespace()
        self.log.append(("hold", idname, text, props, kw))
        return props

    def prop(self, data, attr, **kw):
        self.log.append(("prop", attr, kw.get("text")))

    def label(self, text="", **kw):
        self.log.append(("label", text))

    def separator(self, *a, **kw):
        self.log.append(("sep",))

    def __getattr__(self, name):  # template_ID, template_reports_banner, ...
        def record(*a, **kw):
            self.log.append((name,) + a)
        return record


def _prefs():
    return kit.bpy.context.preferences.addons[kit.MODULE].preferences


def _ctx(**extra):
    c = bpy.context
    win = c.window_manager.windows[0]
    d = dict(area=types.SimpleNamespace(show_menus=True), screen=win.screen, window=win,
             scene=c.scene, mode=c.mode, preferences=c.preferences,
             window_manager=c.window_manager, workspace=win.workspace)
    d.update(extra)
    return types.SimpleNamespace(**d)


def _label(text):
    """The item label of a drawn text (a filler, the Maya hotkey and the box mark follow it)."""
    return text.replace(menu_sets.HAIR, "").split("  ")[0].replace(menu_sets.BOX_MARK.strip(), "").strip()


def _action(entry):
    """(kind, target, props) a drawn Maya menu item runs."""
    if entry[1] == "allset.menu_item":
        return menu_map.spec(entry[3].item)
    props = dict(vars(entry[3]))
    if entry[1] == "allset.menu_tool":
        return ("tool", props["tool"], {"edit": props["edit"]})
    if entry[1] == "allset.menu_run":
        return ("v3d", props["op"], props)
    return ("op", entry[1], props)


def _draw_menu(idname, context=None):
    cls = getattr(bpy.types, idname)
    fake = types.SimpleNamespace(layout=FakeLayout())
    cls.draw(fake, context or bpy.context)
    return fake.layout.log


def _clear_objects():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def _override():
    win = bpy.context.window_manager.windows[0]
    return bpy.context.temp_override(window=win, screen=win.screen)


def _tool_ids():
    from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active as T
    ids = set()

    def walk(items):
        for it in items:
            if isinstance(getattr(it, "idname", None), str):  # ToolDef is a namedtuple
                ids.add(it.idname)
            elif isinstance(it, (tuple, list)):
                walk(it)
    for _mode, items in T.tools_all():
        walk(items)
    return ids


# --- menu data and mapping --------------------------------------------------------

def test_menu_map_keys_are_in_the_data():
    paths = {p for p, _it in menu_sets.iter_items()}
    missing = [k for k in menu_map.MAP if k not in paths]
    assert not missing, f"mapped paths not in menu_data: {missing}"
    assert len(menu_data.MENUS) == 42, len(menu_data.MENUS)
    sets = [s[0] for s in menu_data.MENU_SETS]
    assert sets == ["commonMenuSet", "modelingMenuSet", "riggingMenuSet", "animationMenuSet",
                    "dynamicsMenuSet", "renderingMenuSet"], sets


C_MENUS = {"TOPBAR_MT_file_open_recent"}


def test_menu_map_targets_exist():
    tools = _tool_ids()
    bad = []
    for path in menu_map.MAP:
        kind, target, props = menu_map.spec(path)
        if kind in ("op", "v3d"):
            mod, name = target.split(".")
            try:
                rna = getattr(getattr(bpy.ops, mod), name).get_rna_type()
            except (AttributeError, KeyError):
                bad.append((path, target, "no operator"))
                continue
            for key in props:
                if key not in rna.properties:
                    bad.append((path, target, f"no property {key}"))
        elif kind == "menu":
            # TOPBAR_MT_file_open_recent is a C menu type (not in bpy.types; Blender's own
            # keymap opens it: $S/presets/keyconfig/keymap_data/blender_default.py:706).
            if not hasattr(bpy.types, target) and target not in C_MENUS:
                bad.append((path, target, "no menu"))
        elif kind == "tool" and target not in tools:
            bad.append((path, target, "no tool"))
    assert not bad, bad


def test_menu_classes_registered():
    for name in menu_data.MENUS:
        assert hasattr(bpy.types, menu_sets.menu_idname(name)), name
    n_items = sum(1 for _p, it in menu_sets.iter_items() if len(it) == 1)
    n_mapped = sum(1 for p, it in menu_sets.iter_items() if len(it) == 1 and p in menu_map.MAP)
    print(f"menu items: {n_items}, mapped: {n_mapped}")
    assert n_mapped >= 200, n_mapped


def test_menu_set_switch_changes_menu_bar():
    prefs = _prefs()
    try:
        prefs.menu_set = 'riggingMenuSet'
        log = FakeLayout().log
        lay = FakeLayout(log)
        menu_sets.draw_menu_bar(lay, bpy.context)
        menus = [e[1] for e in log if e[0] == "menu"]
        mid = menu_sets.menu_idname
        assert menus[0] == "TOPBAR_MT_blender", menus
        common = [mid(n) for n in ("mainFileMenu", "mainEditMenu", "mainCreateMenu", "mainSelectMenu",
                                   "mainModifyMenu", "mainDisplayMenu", "mainWindowMenu")]
        assert menus[1:8] == common, menus
        assert mid("mainRigSkeletonsMenu") in menus and mid("mainMeshMenu") not in menus, menus
        assert menus[-2:] == [mid("mainPipelineCacheMenu"), mid("MainHelpMenu")], menus
        assert ("prop", "menu_set", "") in log
        prefs.menu_set = 'modelingMenuSet'
        log.clear()
        menu_sets.draw_menu_bar(lay, bpy.context)
        menus = [e[1] for e in log if e[0] == "menu"]
        assert mid("mainMeshMenu") in menus and mid("mainRigSkeletonsMenu") not in menus
        assert menu_sets.menus_for_set('renderingMenuSet')[7:9] == ("mainShadingMenu", "mainRenTexturingMenu")
    finally:
        prefs.menu_set = 'modelingMenuSet'


def test_menu_items_active_or_grey():
    create = _draw_menu(menu_sets.menu_idname("mainCreateMenu"))
    sub = next(e[1] for e in create if e[0] == "menu" and e[2] == "Polygon Primitives")
    items = _draw_menu(sub)
    ops = {_label(e[2]): e for e in items if e[0] in ("op", "hold")}  # box mark, hotkey text
    # Maya creation (origin, Maya size and names). Option-box items are one
    # allset.menu_item button (press and hold = option box) running the item's mapped action.
    assert _action(ops["Cube"]) == ("op", "allset.create", {"kind": 'CUBE'}), ops["Cube"]
    assert _action(ops["Pyramid"]) == ("op", "allset.create", {"kind": 'PYRAMID'})
    assert _action(ops["Pipe"]) == ("op", "allset.create", {"kind": 'PIPE'})
    assert "Interactive Creation" not in ops, "a check item now (#225), not a greyed button"
    nurbs = _draw_menu(next(e[1] for e in create if e[0] == "menu" and e[2] == "NURBS Primitives"))
    grey = {_label(e[2]): e for e in nurbs if e[0] in ("op", "hold")}["Interactive Creation"]   # NURBS: still greyed
    assert grey[1] == "allset.menu_unavailable", grey
    assert grey[3].item == "Create/NURBS Primitives/Interactive Creation"
    assert not menu_sets.ALLSET_OT_menu_unavailable.poll(bpy.context)
    # Blender's own menu at the end of File; v3d / tool / menu kinds.
    file_log = _draw_menu(menu_sets.menu_idname("mainFileMenu"))
    assert file_log[-1] == ("menu", "TOPBAR_MT_file", "Blender File"), file_log[-1]
    imp = next(e for e in file_log if e[0] in ("op", "hold") and _label(e[2]) == "Import...")   # Maya dialog
    assert _action(imp) == ("op", "allset.file_import", {}), _action(imp)
    tools = _draw_menu(menu_sets.menu_idname("mainMeshToolsMenu"))
    cut = next(e for e in tools if e[0] in ("op", "hold") and _label(e[2]) == "Multi-Cut")
    assert _action(cut) == ("tool", "allset.multi_cut_tool", {"edit": True}), _action(cut)
    edit_mesh = _draw_menu(menu_sets.menu_idname("mainEditMeshMenu"))
    bevel = next(e for e in edit_mesh if e[0] in ("op", "hold") and _label(e[2]) == "Bevel")
    assert _action(bevel)[:2] == ("v3d", "allset.bevel"), _action(bevel)   # polyBevel3 at once
    # Section labels at Maya's dividers.
    assert ("label", "Pivot") not in file_log
    select = _draw_menu(menu_sets.menu_idname("mainSelectMenu"))
    comps = [e for e in select if e[0] == "menu" and e[2] == "Components"]
    assert len(comps) == 3 and len({e[1] for e in comps}) == 3, comps  # three distinct submenus
    # Every menu class draws without error.
    for cls_name in dir(bpy.types):
        if cls_name.startswith("ALLSET_MT_main") or cls_name.startswith("ALLSET_MT_Main"):
            _draw_menu(cls_name)


def test_menu_tool_enters_edit_mode():
    _clear_objects()
    with _override():
        bpy.ops.mesh.primitive_cube_add()
        try:
            bpy.ops.allset.menu_tool(tool="builtin.knife", edit=True)
        except RuntimeError as ex:
            # -b: tool keymaps are not built,
            # so activating a tool fails; the tool switch itself is checked in the GUI test.
            assert "keymap" in str(ex), ex
        try:
            assert bpy.context.mode == 'EDIT_MESH', bpy.context.mode
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')


# --- top bar ----------------------------------------------------------------------

def test_topbar_methods_swapped_and_restored():
    # the kit swaps only the class's own draw in its draw list; draw_left / draw_right stay Blender's
    cls = bpy.types.TOPBAR_HT_upper_bar
    assert status_line.draw_upper_bar in cls.draw._draw_funcs
    assert cls.draw_left.__module__ == "bl_ui.space_topbar" and cls.draw_right.__module__ == "bl_ui.space_topbar"
    kit.disable()
    try:
        assert status_line.draw_upper_bar not in cls.draw._draw_funcs
        assert cls.draw._draw_funcs[0].__qualname__ == "TOPBAR_HT_upper_bar.draw", cls.draw._draw_funcs
    finally:
        kit.enable()
    assert status_line.draw_upper_bar in cls.draw._draw_funcs


def test_topbar_draw_maya_and_blender():
    prefs = _prefs()
    fake = types.SimpleNamespace(layout=FakeLayout())
    status_line.draw_left(fake, _ctx())
    menus = [e[1] for e in fake.layout.log if e[0] == "menu"]
    assert menu_sets.menu_idname("mainMeshMenu") in menus, menus
    fake = types.SimpleNamespace(layout=FakeLayout())
    status_line.draw_right(fake, _ctx())
    # Maya's "Workspace:" label + dropdown, not Blender's workspace ID field
    assert any(e[0] == "prop" and e[1] == "allset_workspace" for e in fake.layout.log), fake.layout.log
    assert not any(e[0] == "template_ID" and e[2] == "workspace" for e in fake.layout.log)
    assert not any(e[0] == "template_ID" and e[2] == "scene" for e in fake.layout.log), "one scene"
    assert not [e for e in fake.layout.log if e[0] == "op"], "Status Line is not in the top bar"
    extra = bpy.data.scenes.new("Second")
    try:
        fake = types.SimpleNamespace(layout=FakeLayout())
        status_line.draw_right(fake, _ctx())
        assert any(e[0] == "template_ID" and e[2] == "scene" for e in fake.layout.log)
    finally:
        bpy.data.scenes.remove(extra)
    screen = bpy.context.window_manager.windows[0].screen
    area, _r = status_line.main_view3d(screen)
    fake = types.SimpleNamespace(layout=FakeLayout())
    status_line.draw_tool_header(fake, _ctx(area=area))
    ops = [e[1] for e in fake.layout.log if e[0] == "op"]
    # (selection masks: collapsed by default, like Maya's Status Line)
    for op in ("allset.save_scene", "allset.select_mode", "allset.status_group", "allset.snap_toggle",
               "allset.render", "allset.render_settings", "allset.editor_toggle"):
        assert op in ops, (op, ops)
    other = types.SimpleNamespace(type='VIEW_3D')
    fake = types.SimpleNamespace(layout=FakeLayout())
    status_line.draw_tool_header(fake, _ctx(area=other))
    assert not fake.layout.log, "only the largest 3D View draws the Status Line"
    try:
        prefs.maya_top_bar = False
        fake = types.SimpleNamespace(layout=FakeLayout())
        status_line.draw_left(fake, _ctx())  # Blender's own: editor menus + workspace tabs
        names = [e[0] for e in fake.layout.log]
        assert "template_ID_tabs" in names, names
        prefs.maya_top_bar = True
        prefs.show_status_line = False
        fake = types.SimpleNamespace(layout=FakeLayout())
        status_line.draw_tool_header(fake, _ctx(area=area))
        assert not fake.layout.log
    finally:
        prefs.maya_top_bar = True
        prefs.show_status_line = True


def test_snap_toggles_and_hold_keys():
    ts = bpy.context.scene.tool_settings
    ts.use_snap = False
    ts.snap_elements = {'INCREMENT'}
    status_line.toggle_snap(ts, "GRID")
    assert ts.use_snap and set(ts.snap_elements) == {'GRID'}, set(ts.snap_elements)
    status_line.toggle_snap(ts, "CURVE")
    assert status_line.snap_on(ts, "GRID") and status_line.snap_on(ts, "CURVE")
    status_line.toggle_snap(ts, "GRID")
    assert set(ts.snap_elements) == {'EDGE'} and not status_line.snap_on(ts, "GRID")
    status_line.toggle_snap(ts, "CURVE")
    assert not ts.use_snap
    # Holding V lights the point-snap button; releasing restores (operators/hold.py).
    hold.begin(ts, "point")
    assert status_line.snap_on(ts, "POINT") and not status_line.snap_on(ts, "GRID")
    status_line.toggle_snap(ts, "GRID")  # pressed during the hold ...
    hold.end(ts, "point")
    assert not ts.use_snap, "... the hold restores the state from before it"
    with _override():
        bpy.ops.allset.snap_toggle(snap="LIVE")
    assert ts.use_snap and set(ts.snap_elements) == {'FACE_PROJECT'}
    ts.use_snap = False


def test_selection_masks_all_views():
    spaces = list(status_line.all_view3d_spaces())
    assert spaces
    try:
        status_line.set_mask("JOINTS", False)
        assert all(not s.show_object_select_armature for s in spaces)
        assert not status_line.mask_on(spaces[0], "JOINTS") and status_line.mask_on(spaces[0], "CURVES")
        with _override():
            bpy.ops.allset.select_mask(group="JOINTS")
        assert all(s.show_object_select_armature for s in spaces)
        with _override():
            bpy.ops.allset.select_mask(group="SURFACES")
        assert all(not s.show_object_select_mesh and not s.show_object_select_surf for s in spaces)
    finally:
        for group in ("JOINTS", "SURFACES"):
            status_line.set_mask(group, True)


def test_selection_mode_and_editor_buttons():
    _clear_objects()
    with _override():
        bpy.ops.mesh.primitive_cube_add()
        bpy.ops.allset.select_mode(mode="COMPONENT")
        assert bpy.context.mode == 'EDIT_MESH'
        bpy.ops.allset.select_mode(mode="OBJECT")
        assert bpy.context.mode == 'OBJECT'
        screen = bpy.context.window_manager.windows[0].screen
        bpy.ops.allset.render_settings()
        props = next(a for a in screen.areas if a.type == 'PROPERTIES')
        assert props.spaces.active.context == 'RENDER'
        # the Maya panels are dock areas / floating windows (GUI: gui_step116_dock); a factory screen has
        # no tab stack, so they aren't shown and the user's Properties editor is left alone
        assert not status_line.editor_shown(screen, "CHANNEL_BOX")
        assert not status_line.editor_shown(screen, "ATTRIBUTE")
        assert status_line._properties_area(screen) == props
        assert not status_line.editor_shown(screen, "TOOL_SETTINGS")
        area, _r = status_line.main_view3d(screen)
        bpy.ops.allset.ipr_toggle()
        assert area.spaces.active.shading.type == 'RENDERED'
        bpy.ops.allset.ipr_toggle()
        assert area.spaces.active.shading.type == 'SOLID'


# --- command line ------------------------------------------------------------------

def test_runner_results_and_errors():
    runner.reset()
    assert runner.run("1 + 2").text == "# Result: 3 #"
    assert runner.run("x = 5").text == ""
    assert runner.run("x * 2").text == "# Result: 10 #", "namespace persists"
    r = runner.run("1/0")
    assert r.error and r.text.startswith("# Error: ZeroDivisionError"), r
    r = runner.run("print('hi'); print('there')")
    assert r.text == "there" and not r.error, r
    assert runner.run("C.scene.name").text == f"# Result: {bpy.context.scene.name!r} #"
    assert runner.run("D.scenes[0]").text == f"# Result: {bpy.data.scenes[0].name} #"
    r = runner.run("def f(:")
    assert r.error and "SyntaxError" in r.text, r
    runner.run("1 + 2")
    runner.run("1 + 2")
    assert runner.history.count("1 + 2") == 2 and runner.history[-1] == "1 + 2"
    assert runner.history[-2] != "1 + 2", "consecutive repeats are stored once"


def test_runner_mel_notice_and_hints():
    r = runner.run("polyCube -w 2 -h 3;")
    assert r.error and r.text == "# Error: no MEL, use Python: cmds.polyCube(w=2, h=3)", r
    assert runner.mel_to_python("select -cl;") == "cmds.select(cl=True)"
    assert runner.mel_to_python("move -r 0 1 0;") == "cmds.move(0, 1, 0, r=True)"
    assert runner.mel_to_python('setAttr "pCube1.tx" 5;') == 'cmds.setAttr("pCube1.tx", 5)'
    assert runner.mel_to_python("select pCube1; delete;") == "cmds.select('pCube1'); cmds.delete()"
    assert runner.mel_to_python("x = [1, 2") is None
    r = runner.run("$a = 1;")
    assert r.error and r.text == "# Error: MEL is not supported, use Python", r
    r = runner.run("polyCube()")
    assert r.error and "cmds.polyCube(...)" in r.text, r


def test_command_field_runs_through_operator():
    runner.reset()
    wm = bpy.context.window_manager
    with _override():
        wm.allset_cmd = "z = 7; z + 1"
    assert wm.allset_cmd == "", "field is cleared after Enter"
    assert command_line._result["text"] == "# Result: 8 #", command_line._result
    with _override():
        wm.allset_cmd = "1/0"  # an error from the field does not raise
    assert command_line._result["error"]
    runner.history.remove("1/0")
    with _override():
        try:
            bpy.ops.allset.command_line_exec(command="nope()")
            raise AssertionError("an error result is reported as ERROR")
        except RuntimeError as ex:
            assert "NameError" in str(ex), ex
    assert command_line._result["error"]
    assert runner.history == ["z = 7; z + 1", "nope()"], runner.history


def test_import_maya_cmds():
    """Every import form works inside the Command Line namespace (without sys.modules entries)."""
    assert "maya" not in sys.modules and "maya.cmds" not in sys.modules
    for src in ("import maya.cmds as mc; mc.ls is cmds.ls", "from maya import cmds as c2; c2.ls is cmds.ls",
                "import maya.cmds; maya.cmds.ls is cmds.ls", "from maya.cmds import ls; ls is cmds.ls"):
        r = runner.run(src)
        assert r.text == "# Result: True #", (src, r)
    assert "maya" not in sys.modules and "maya.cmds" not in sys.modules
    r = runner.run("import json; json.dumps(1)")
    assert r.text == "# Result: '1' #", r
    r = runner.run("import os, maya.cmds as c3\nif True:\n    from maya.cmds import ls as l2\nl2 is c3.ls and bool(os.sep)")
    assert r.text == "# Result: True #", r


def test_runner_uses_blenders_run_script():
    """#40: entries run from a temporary Text through ``text.run_script`` — prepared source, no Text left."""
    runner.reset()
    before = {t.name for t in bpy.data.texts}
    src = runner.prepare("import maya.cmds as cmds\nx = 1\nx + 1  # c")
    assert "import maya" not in src and f"from {runner._PKG} import cmds_shim as cmds" in src, src
    assert "_allset_result = (x + 1\n)  # c" in src, src
    assert src.splitlines()[0].endswith(f"{runner.RUNNER}.bind(globals())"), src
    r = runner.run("y = (\n  2 *\n  3)\ny")
    assert r.text == "# Result: 6 #", r
    r = runner.run("name = 'ü'; name + 'x'")                            # non-ASCII columns (UTF-8 offsets)
    assert r.text == "# Result: 'üx' #", r
    r = runner.run("for i in range(2):\n    print('line', i)")
    assert r.text == "line 1" and not r.error, r
    r = runner.run("def g():\n    return undefined_name\ng()")
    assert r.error and r.text == "# Error: NameError: file <maya console> line 2: name 'undefined_name' is not "         "defined", r          # Maya History > Line numbers in errors, factory on
    assert {t.name for t in bpy.data.texts} == before, "the temporary Text is removed"
    r = runner.run("y * 2")
    assert r.text == "# Result: 12 #", "variables of earlier entries persist"
    r = runner.run("w = 4\n1/0")
    assert r.error and runner.namespace().get("w") == 4, "variables set before an error persist (Maya)"
    r = runner.run("z = 3", persist=False)
    assert not r.error and "z" not in runner.namespace(), "a shelf run keeps no variables"


def test_help_line_text():
    assert "Move Tool" in command_line.help_for_tool("builtin.move")
    assert command_line.help_for_tool("builtin.select_box").startswith("Select Tool")
    assert command_line.help_for_tool("builtin.unknown") == ""
    fake = types.SimpleNamespace(layout=FakeLayout())
    command_line.draw_status_bar(fake, _ctx())
    entries = fake.layout.log
    assert ("prop", "allset_cmd", "") in entries, entries
    assert any(e[0] == "op" and e[1] == "allset.command_line_language" for e in entries)


# --- cmds_shim ---------------------------------------------------------------------

def _units(length='CENTIMETERS', scale=1.0):
    us = bpy.context.scene.unit_settings
    us.system = 'METRIC'
    us.length_unit = length
    us.scale_length = scale


def test_cmds_create_and_units():
    _clear_objects()
    _units()
    assert abs(cmds.linear_factor() - 0.01) < 1e-6
    assert cmds.polyCube(w=2, h=3, d=4) == ["pCube1", "polyCube1"]
    ob = bpy.data.objects["pCube1"]
    assert ob.data.name == "pCubeShape1"
    dims = sorted(round(v.co[i], 6) for v in ob.data.vertices[:1] for i in range(3))
    xs = [v.co.x for v in ob.data.vertices]
    ys = [v.co.y for v in ob.data.vertices]
    zs = [v.co.z for v in ob.data.vertices]
    assert abs(max(xs) - min(xs) - 0.02) < 1e-6 and abs(max(zs) - min(zs) - 0.03) < 1e-6, dims
    assert abs(max(ys) - min(ys) - 0.04) < 1e-6, "Maya depth -> Blender Y"
    assert cmds.ls(sl=True) == ["pCube1"] and bpy.context.view_layer.objects.active == ob
    assert cmds.polyCube()[0] == "pCube2"
    assert len(bpy.data.objects[cmds.polySphere()[0]].data.vertices) == 382  # 20x20
    assert len(bpy.data.objects[cmds.polyCylinder()[0]].data.vertices) == 40
    assert len(bpy.data.objects[cmds.polyPlane()[0]].data.vertices) == 121  # 10x10
    assert cmds.polyCube(n="box")[0] == "box"
    _units(scale=0.01)  # "Maya units" option: 1 BU = 1 cm
    try:
        name = cmds.polyCube()[0]
        xs = [v.co.x for v in bpy.data.objects[name].data.vertices]
        assert abs(max(xs) - min(xs) - 1.0) < 1e-6
    finally:
        _units()


def test_cmds_transforms_and_attrs():
    _clear_objects()
    _units()
    cmds.polyCube()
    cmds.move(0, 5, 0, "pCube1")
    ob = bpy.data.objects["pCube1"]
    assert abs(ob.location.y - 0.05) < 1e-6, tuple(ob.location)
    cmds.move(1, 0, 0, "pCube1", r=True)
    assert abs(ob.location.x - 0.01) < 1e-6 and abs(ob.location.y - 0.05) < 1e-6
    cmds.rotate(0, 90, 0, "pCube1")
    assert abs(ob.rotation_euler.y - math.pi / 2) < 1e-6
    cmds.rotate(0, 0, 45, "pCube1", relative=True)
    assert abs(ob.rotation_euler.z - math.pi / 4) < 1e-6
    cmds.scale(2, 2, 2, "pCube1")
    cmds.scale(1.5, 1, 1, "pCube1", r=True)
    assert abs(ob.scale.x - 3.0) < 1e-6 and abs(ob.scale.y - 2.0) < 1e-6
    cmds.setAttr("pCube1.tx", 10)
    assert abs(ob.location.x - 0.1) < 1e-6
    assert abs(cmds.getAttr("pCube1.translateX") - 10) < 1e-6
    t = cmds.getAttr("pCube1.translate")
    assert isinstance(t, list) and len(t[0]) == 3 and abs(t[0][1] - 5) < 1e-6, t
    cmds.setAttr("pCube1.rotate", 10, 20, 30)
    assert abs(cmds.getAttr("pCube1.ry") - 20) < 1e-6
    assert cmds.getAttr("pCube1.visibility") is True
    cmds.setAttr("pCube1.v", 0)
    assert ob.hide_viewport and cmds.getAttr("pCube1.v") is False
    cmds.setAttr("pCube1.tx", lock=True)
    assert cmds.getAttr("pCube1.tx", lock=True)
    try:
        cmds.setAttr("pCube1.tx", 3)
        raise AssertionError("locked attribute changed")
    except RuntimeError:
        pass
    cmds.setAttr("pCube1.tx", lock=False)
    ob["myAttr"] = 1.5
    cmds.setAttr("pCube1.myAttr", 4)
    assert cmds.getAttr("pCube1.myAttr") == 4.0
    assert [round(v, 6) for v in cmds.xform("pCube1", q=True, t=True)] == [10.0, 5.0, 0.0]
    cmds.xform("pCube1", t=(1, 2, 3))
    assert abs(ob.location.z - 0.03) < 1e-6
    assert cmds.getAttr("pCubeShape1.tx") == cmds.getAttr("pCube1.tx"), "shape name -> transform"


def test_cmds_select_ls_scene():
    _clear_objects()
    _units()
    a, b = cmds.polyCube()[0], cmds.polyCube()[0]
    cmds.select(a)
    assert cmds.ls(sl=True) == [a]
    cmds.select(b, add=True)
    assert cmds.ls(sl=True) == [a, b] and bpy.context.view_layer.objects.active.name == b
    cmds.select(a, d=True)
    assert cmds.ls(sl=True) == [b]
    cmds.select(a, tgl=True)
    assert set(cmds.ls(sl=True)) == {a, b}
    cmds.select(cl=True)
    assert cmds.ls(sl=True) == []
    assert sorted(cmds.ls(type="mesh")) == ["pCubeShape1", "pCubeShape2"]
    assert sorted(cmds.ls()) == [a, b, "pCubeShape1", "pCubeShape2"]   # Maya ls lists shapes too
    assert cmds.listRelatives(a) == ["pCubeShape1"], "Maya: the shape is a child"
    bpy.data.objects[b].parent = bpy.data.objects[a]
    assert cmds.listRelatives(a, c=True) == ["pCubeShape1", b] and cmds.listRelatives(b, p=True) == [a]
    assert cmds.listRelatives(a, s=True) == ["pCubeShape1"]
    assert cmds.ls(b, long=True) == [f"|{a}|{b}"]
    assert cmds.rename(b, "child") == "child" and cmds.objExists("child")
    cmds.delete("child")
    assert not cmds.objExists("child")
    assert cmds.currentTime(12) == 12.0 and bpy.context.scene.frame_current == 12
    assert cmds.currentTime(q=True) == 12.0
    for bad in (lambda: cmds.select(a, bogus=True), lambda: cmds.fooBar(),
                lambda: cmds.select("pCube1.vtx[0]"), lambda: cmds.select("nothing")):
        try:
            bad()
            raise AssertionError("no error")
        except (TypeError, AttributeError, RuntimeError, ValueError) as ex:
            assert "no error" not in str(ex)
    try:
        cmds.fooBar
    except AttributeError as ex:
        assert "not available in Maya Workflow Kit" in str(ex)
