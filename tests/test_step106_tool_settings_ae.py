"""Tool Settings dock with Maya sections, Attribute Editor history tabs / menu bar / buttons / Notes, Blender
explanation sentences moved into tooltips."""


from importlib import import_module
from types import SimpleNamespace

import bmesh
import bpy

import kit

ts_mod = import_module(kit.MODULE + ".ui.tool_settings")
tool_dock = import_module(kit.MODULE + ".ui.tool_dock")
dock_tabs = import_module(kit.MODULE + ".ui.dock_tabs")
status_line = import_module(kit.MODULE + ".ui.status_line")
notices = import_module(kit.MODULE + ".ui.notices")
ae = import_module(kit.MODULE + ".ui.attribute_editor")
in_view = import_module(kit.MODULE + ".ui.in_view")
mtk = import_module(kit.MODULE + ".ui.modeling_toolkit")
project = import_module(kit.MODULE + ".operators.project")
ex = import_module(kit.MODULE + ".operators.extrude")


class Recorder:
    """A stand-in UILayout that records labels / operator texts and the operator property objects."""

    def __init__(self, log=None):
        self.log = [] if log is None else log

    def __getattr__(self, name):
        if name in ("row", "column", "split", "box", "column_flow", "grid_flow"):
            return lambda *a, **k: Recorder(self.log)
        if name == "panel":
            def panel(idname, default_closed=False):
                self.log.append(("panel", idname, {"default_closed": default_closed}))
                return Recorder(self.log), Recorder(self.log)
            return panel
        if name in ("menu", "operator", "prop", "label", "popover", "props_enum"):
            def add(*args, **kw):
                props = type("Props", (), {})()
                kw["_props"] = props
                kw["_args"] = args
                self.log.append((name, kw.get("text", args[0] if args else ""), kw))
                return props
            return add
        return lambda *a, **k: None

    def __setattr__(self, name, value):
        if name == "log":
            object.__setattr__(self, name, value)

    def texts(self, kind):
        return [t for k, t, _kw in self.log if k == kind]

    def ops(self, idname):
        return [kw["_props"] for k, _t, kw in self.log if k == "operator" and kw["_args"][:1] == (idname,)]


# --- Tool Settings -------------------------------------------------------------------------------------------------

def test_sections_follow_maya():
    # Maya 2022 frames: order and the one open section
    assert [s[1] for s in ts_mod.sections('TRANSLATE')] == [
        "Move Settings", "Joint Orient Settings", "Move Snap Settings", "Common Selection Options", "Soft Selection",
        "Symmetry Settings", "Smart Duplicate Settings"]
    for kind, first in (('ROTATE', "Rotate Settings"), ('RESIZE', "Scale Settings")):
        assert [s[1] for s in ts_mod.sections(kind)] == [
            first, "Common Selection Options", "Soft Selection", "Symmetry Settings", "Smart Duplicate Settings"]
        assert [s[2] for s in ts_mod.sections(kind)] == [True, False, False, False, False]


def _draw_all(kind):
    rec = Recorder()
    for key, _title, _open in ts_mod.sections(kind):
        ts_mod.draw_section(rec, bpy.context, key, kind)
    return rec


def test_rows_are_bound_to_kit_state():
    for kind in ('TRANSLATE', 'ROTATE', 'RESIZE'):
        rec = _draw_all(kind)
        labels, props, ops = rec.texts("label"), rec.texts("prop"), rec.texts("operator")
        for text in ("Axis Orientation:", "Pivot:", "Step Snap:", "Preserve Children:", "Preserve UVs:",
                     "Transform Constraint:", "Tweak Mode:", "Selection Style:", "Symmetry:"):
            assert text in labels, (kind, text)
        for text in ("Edit Pivot", "Reset", "Position", "Orientation", "Pin Component Pivot", "Off", "Relative",
                     "Absolute"):
            assert text in ops, (kind, text, ops)
        assert "Camera-based selection" in props and "Highlight nearest component" in props
        assert "Shift+Drag to Extrude Components" in props and "Shift+Drag to Duplicate Objects" in props
        assert "Soft Select" in props
        owners = {(kw["_args"][0].bl_rna.identifier, kw["_args"][1]) for k, _t, kw in rec.log
                  if k == "prop" and len(kw["_args"]) > 1}
        assert ("ToolSettings", "use_transform_skip_children") in owners
        assert ("ToolSettings", "use_transform_correct_face_attributes") in owners
        assert ("TransformOrientationSlot", "type") in owners
        if kind == 'ROTATE':
            assert "Rotate Center:" in labels and "Selection" in ops
        if kind == 'RESIZE':
            assert "Scale Center:" in labels and "Selection" not in ops


def test_greyed_rows_have_tooltips():
    paths = set()
    for kind in ('TRANSLATE', 'ROTATE', 'RESIZE'):
        rec = _draw_all(kind)
        paths |= {p.item for p in rec.ops("allset.menu_unavailable")}
    rec = Recorder()
    tool = SimpleNamespace(idname="builtin.move")
    ts_mod.draw_head(rec, bpy.context, tool)
    assert "Move Tool" in rec.texts("label") and "Reset Tool" in rec.texts("operator")
    paths |= {p.item for p in rec.ops("allset.menu_unavailable")}
    assert len(paths) >= 15, paths
    for path in paths:
        text = notices.tooltip(path, mapped=False)
        assert text and "\n" in text, path


def test_dock_hides_blender_tool_panels_only_for_maya_tools():
    win_region = SimpleNamespace(type='WINDOW')
    props_space = SimpleNamespace(type='PROPERTIES')
    ctx = SimpleNamespace(region=win_region, space_data=props_space, mode='OBJECT')
    saved = ts_mod.active_tool
    try:
        ts_mod.active_tool = lambda c: SimpleNamespace(idname="builtin.move")
        assert dock_tabs._hidden(ctx)
        ts_mod.active_tool = lambda c: SimpleNamespace(idname="builtin.knife")   # no Maya sections
        assert not dock_tabs._hidden(ctx)
        ts_mod.active_tool = lambda c: SimpleNamespace(idname="builtin.rotate")
        ctx.space_data = SimpleNamespace(type='VIEW_3D')    # a 3D View main region: never
        assert not dock_tabs._hidden(ctx)
    finally:
        ts_mod.active_tool = saved
    # the Maya panel polls only in a Properties editor (the dock), never in a 3D View sidebar
    assert ts_mod.ALLSET_PT_tool_settings.poll(SimpleNamespace(space_data=props_space))
    assert not ts_mod.ALLSET_PT_tool_settings.poll(SimpleNamespace(space_data=SimpleNamespace(type='VIEW_3D')))


class _Space:
    def __init__(self, context, header):
        self.context, self.show_region_header = context, header


class _Area:
    def __init__(self, type_, space):
        self.type, self.spaces = type_, SimpleNamespace(active=space)

    def as_pointer(self):
        return id(self)


def test_dock_recognised_and_not_the_ae_properties():
    dock = _Area('PROPERTIES', _Space('TOOL', False))
    other = _Area('PROPERTIES', _Space('OBJECT', True))
    tool_tab = _Area('PROPERTIES', _Space('TOOL', True))     # a user's own Properties Tool tab is not the dock
    assert tool_dock.is_dock(dock) and not tool_dock.is_dock(other) and not tool_dock.is_dock(tool_tab)
    screen = SimpleNamespace(areas=[dock, other])
    assert tool_dock.find(screen) is dock and tool_dock.shown(screen)
    assert status_line._properties_area(screen) is other
    assert status_line._properties_area(SimpleNamespace(areas=[dock])) is None
    assert status_line.editor_shown(screen, "TOOL_SETTINGS")
    assert not status_line.editor_shown(SimpleNamespace(areas=[other]), "TOOL_SETTINGS")


def test_toggle_operator_never_opens_a_popup():
    src = open(status_line.__file__, encoding="utf-8").read()
    assert "VIEW3D_PT_active_tool\", keep_open" not in src and "tool_dock.toggle" in src
    props = bpy.ops.allset.editor_toggle.get_rna_type().properties
    assert "show" in props


# --- Attribute Editor ----------------------------------------------------------------------------------------------

def _cube():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.context.scene.pop(ex.COUNTER, None)
    assert bpy.ops.allset.create(kind='CUBE') == {'FINISHED'}
    return bpy.context.active_object


def test_modifier_tabs_have_maya_node_names():
    ob = _cube()
    ob.modifiers.new("Bevel", 'BEVEL')
    ob.modifiers.new("Bevel.001", 'BEVEL')
    ob.modifiers.new("polySmoothFace", 'SUBSURF')
    t = ae.tabs(ob)
    assert t[0][0] == "T" and t[1][0] == "S"
    hist = [x for x in t if x[0].startswith("M:")]
    assert [(x[1], x[2]) for x in hist] == [("polyBevel1", "polyBevel3"), ("polyBevel2", "polyBevel3"),
                                            ("polySmoothFace", "polySmoothFace")], hist
    # Maya order: transform, shape, history, shading group, material (initialShadingGroup | lambert1)
    kinds = [x[0].split(":")[0] for x in t]
    assert kinds.index("M") < kinds.index("SG") < kinds.index("MAT"), kinds
    assert ae.nice_type("polyExtrudeFace") == "Poly Extrude Face"


def test_extrude_record_is_a_history_tab():
    ob = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(ob.data)
    for f in bm.faces:
        f.select_set(False)
    for f in bm.faces:   # deselect first: a later face's select_set(False) would drop shared verts
        if f.normal.z > 0.9:
            f.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.extrude(local_translate_z=0.5) == {'FINISHED'}
    t = ae.tabs(ob)
    assert ("H", "polyExtrudeFace1", "polyExtrudeFace") in t and [x[0] for x in t].index("H") == 2, t
    ae.set_tab(bpy.context, "H")
    rec = Recorder()
    ae.draw(rec, bpy.context, ob)
    labels = rec.texts("label")
    assert "polyExtrudeFace:" in labels and "polyExtrudeFace1" in labels
    assert "Local Translate Z" in labels and "Thickness" in labels, labels
    assert any(i == "allset_ae_history_extrude" for k, i, _kw in rec.log if k == "panel")
    # Channel Box INPUTS: the node, its rows, and no Blender sentence (the notice is the name's tooltip)
    rec = Recorder()
    in_view.draw_cb_node(rec, bpy.context, ex.active(bpy.context)[1])
    assert not any("history" in t.lower() for t in rec.texts("label")), rec.texts("label")
    tips = rec.ops("allset.cb_node_toggle")       # the node name expands it and carries the notice
    assert len(tips) == 1 and tips[0].tip == in_view.HISTORY_TIP
    bpy.ops.object.mode_set(mode='OBJECT')


def test_ae_chrome_buttons_and_menus():
    ob = _cube()
    ae.set_tab(bpy.context, "S")
    rec = Recorder()
    ae.draw_panel(rec, bpy.context)
    menus = rec.texts("menu")
    assert menus[:7] == ["List", "Selected", "Focus", "Attributes", "Display", "Show", "Help"], menus
    ops = rec.texts("operator")
    for text in ("Focus", "Show", "Hide", "Select", "Load Attributes", "Copy Tab"):
        assert text in ops, (text, ops)
    assert "Presets" in menus
    assert "Notes:  " + ob.data.name in rec.texts("label")
    for cls in ae.MENUS:
        assert cls.is_registered and cls.__name__ in {m[1] for m in ae.MENU_BAR} | {
            "ALLSET_MT_ae_attribute_names", "ALLSET_MT_ae_node_types", "ALLSET_MT_ae_presets"}
    for path in ae.AE_NOTICES:
        assert notices.tooltip(path, mapped=False)


def test_hide_and_show_node_types():
    ob = _cube()
    ob.modifiers.new("Bevel", 'BEVEL')
    wm = bpy.context.window_manager
    ae.set_tab(bpy.context, "M:Bevel")
    assert bpy.ops.allset.ae_hide_type() == {'FINISHED'}
    assert not any(x[2] == "polyBevel3" for x in ae.tabs(ob)) and "polyBevel3" in wm.allset_ae_hidden
    ae.set_tab(bpy.context, "T")
    assert bpy.ops.allset.ae_hide_type() == {'CANCELLED'}     # the transform keeps its tab
    assert bpy.ops.allset.ae_show_types() == {'FINISHED'}
    assert any(x[2] == "polyBevel3" for x in ae.tabs(ob)) and wm.allset_ae_hidden == ""


def test_focus_locks_and_load_follows_selection():
    ob = _cube()
    wm = bpy.context.window_manager
    wm.allset_ae_auto_load = True
    assert bpy.ops.allset.ae_focus() == {'FINISHED'}
    assert not wm.allset_ae_auto_load and wm.allset_ae_node == ob.name
    assert bpy.ops.allset.create(kind='SPHERE') == {'FINISHED'}
    sphere = bpy.context.active_object
    assert ae.ae_node(bpy.context) is ob              # focused: stays on the cube
    assert bpy.ops.allset.ae_load() == {'FINISHED'}
    assert ae.ae_node(bpy.context) is sphere           # Load Attributes: the current selection
    wm.allset_ae_auto_load = True
    assert ae.ae_node(bpy.context) is sphere


def test_notes_live_on_the_node():
    ob = _cube()
    wm = bpy.context.window_manager
    wm.allset_ae_auto_load = True
    scene = bpy.context.scene
    ae.set_tab(bpy.context, "S")
    scene.allset_ae_notes = "shape note"
    assert ob.data.get(ae.NOTES_PROP) == "shape note" and scene.allset_ae_notes == "shape note"
    ae.set_tab(bpy.context, "T")
    assert scene.allset_ae_notes == ""
    scene.allset_ae_notes = "transform note"
    assert ob.get(ae.NOTES_PROP) == "transform note"
    scene.allset_ae_notes = ""
    assert ae.NOTES_PROP not in ob.keys()
    # Extra Attributes don't list the notes
    rec = Recorder()
    ae.draw_extra(rec, ob.data, "mesh")
    assert ae.NOTES_PROP not in str(rec.log)


def test_attribute_names_display():
    ctx = bpy.context
    wm = ctx.window_manager
    wm.allset_ae_names = 'LONG'
    assert ae.attr_label(ctx, "Visibility", "hide_viewport") == "hide_viewport"
    wm.allset_ae_names = 'SHORT'
    assert ae.attr_label(ctx, "Visibility", "hide_viewport") == "hv"
    wm.allset_ae_names = 'NICE'
    assert ae.attr_label(ctx, "Visibility", "hide_viewport") == "Visibility"


# --- explanation sentences -> tooltips (#22) -------------------------------------------------------------------

def test_project_window_notice_is_a_tooltip():
    rna = bpy.ops.allset.project_window.get_rna_type()
    assert rna.properties["name"].description == project.NOTICE
    src = open(project.__file__, encoding="utf-8").read()
    assert "chrome.paragraph(layout, context, NOTICE" not in src


def test_soft_selection_note_is_a_tooltip():
    rec = Recorder()
    mtk.draw_soft(rec, bpy.context)
    assert mtk.NOTE not in rec.texts("label")
    assert [p.text for p in rec.ops("allset.tip")] == [mtk.NOTE]
