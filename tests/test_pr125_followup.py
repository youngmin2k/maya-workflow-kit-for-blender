"""PR #125 follow-up (0.5.0): Maya checks of the merged PR
— idle Channel Box poll, wheel step, Joint Tool branching, menu data, header extras,
Select Priority off. GUI parts: tests/gui/gui_pr125_window_close.py, tests/integration/."""

from importlib import import_module

import bpy

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")
maya_dock = import_module(kit.MODULE + ".ui.maya_dock")


def _cube():
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ob.select_set(True)
    return ob


def test_idle_poll_draws_nothing():
    """The 0.1 s live-value poll redraws the dock only when the lead's channels changed (or a transform runs)."""
    ob = _cube()
    calls = []
    real = maya_dock.redraw
    maya_dock.redraw = lambda *a, **k: calls.append(1)
    try:
        cb._poll_transform_values()
        calls.clear()
        for _ in range(5):
            cb._poll_transform_values()
        assert not calls, f"idle ticks redrew the dock {len(calls)} times"
        ob.location.x += 1.0
        cb._poll_transform_values()
        assert len(calls) == 1, calls
        cb._poll_transform_values()
        assert len(calls) == 1, "the same values again: no redraw"
    finally:
        maya_dock.redraw = real


def test_wheel_is_three_lines():
    """Maya: one wheel notch = QScrollBar singleStep 15 px x wheelScrollLines 3 = 45 px, about 3 rows."""
    assert cb.WHEEL_LINES == 3


def test_no_split_faces_by_edges():
    """'Split Faces by Edges' is Blender's name, in no Maya Edit Mesh menu (2022-2027); Maya's tool is Detach."""
    data = import_module(kit.MODULE + ".ui.menu_data")
    mm = import_module(kit.MODULE + ".ui.menu_map")
    labels = [it[0] for it in data.MENUS["mainEditMeshMenu"][3]]
    assert "Split Faces by Edges" not in labels and "Detach" in labels
    assert "Edit Mesh/Split Faces by Edges" not in mm.MAP
    assert mm.MAP["Edit Mesh/Detach"] == "allset.detach"


class _Ops:
    """A stand-in UILayout recording operator ids in draw order."""

    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        if name in ("row", "column", "box", "split"):
            return lambda *a, **k: _Ops(self.log)
        if name == "operator":
            def op(idname, **kw):
                self.log.append(idname)
                from types import SimpleNamespace
                return SimpleNamespace()
            return op
        return lambda *a, **k: None

    def __setattr__(self, name, value):
        if name == "log":
            object.__setattr__(self, name, value)


def test_header_extras_off_and_search_under_layouts():
    """No Maya viewport header has a mode picker or a pulse: both are add-on preferences, off by default. The Tool
    Box Search button sits under the layout / Outliner buttons (Maya 2022.1+ Tool Box), and the column
    keeps Maya's width (no +3 px)."""
    from types import SimpleNamespace
    prefs = import_module(kit.MODULE + ".preferences").get()
    assert prefs.armature_mode_header is False and prefs.armature_mode_pulse is False
    pulse = import_module(kit.MODULE + ".ui.armature_mode_pulse")
    assert not pulse.wanted()
    tb = import_module(kit.MODULE + ".ui.toolbox")
    assert tb.column_width() == round(tb.TOOLBAR_PX * bpy.context.preferences.system.ui_scale)
    log = []
    tb.ALLSET_PT_toolbox_layouts.draw(SimpleNamespace(layout=_Ops(log)), bpy.context)
    assert log[-1] == "allset.viewport_search" and log[-2] == "allset.toggle_outliner", log
    # the header picker draws nothing with the preference off
    log = []
    bpy.ops.object.armature_add()
    tb._draw_armature_mode_header(SimpleNamespace(layout=_Ops(log)), bpy.context)
    assert not log, log


def test_priority_off_leaves_non_joint_clicks_to_blender():
    """Selection Priority off: an Object-mode click is the kit's only when it hits a joint;
    everything else passes through to Blender's own pick (the PR called view3d.select for every click)."""
    from types import SimpleNamespace
    sp = import_module(kit.MODULE + ".operators.select_priority")
    js = import_module(kit.MODULE + ".operators.joint_selection")
    prefs = import_module(kit.MODULE + ".preferences").get()
    _cube()
    bpy.ops.object.armature_add(location=(3, 0, 0))
    bpy.ops.object.mode_set(mode='OBJECT')
    arm = bpy.context.active_object
    space = SimpleNamespace(type='VIEW_3D', show_region_toolbar=False)
    region = SimpleNamespace(type='WINDOW', width=400, height=300)
    ctx = SimpleNamespace(mode='OBJECT', space_data=space, region=region, region_data=SimpleNamespace(),
                          preferences=bpy.context.preferences, visible_objects=list(bpy.context.visible_objects),
                          window_manager=bpy.context.window_manager)
    event = SimpleNamespace(mouse_region_x=10, mouse_region_y=10, shift=False, ctrl=False, value='CLICK',
                            mouse_x=10, mouse_y=10)
    calls = []
    real = (js.pick, js.select, js.select_object_at, sp.hits)
    js.select_object_at = lambda *a, **k: calls.append("view3d.select")
    sp.hits = lambda *a, **k: calls.append("priority hits") or []
    js.select = lambda c, ob, name, *a: calls.append(("joint", ob.name, name)) or True
    was = prefs.select_priority
    prefs.select_priority = False
    try:
        js.pick = lambda c, ob, mouse, radius: None
        res = sp.ALLSET_OT_select_priority.invoke(SimpleNamespace(), ctx, event)
        assert res == {'PASS_THROUGH'} and not calls, (res, calls)
        js.pick = lambda c, ob, mouse, radius: "Bone" if ob == arm else None
        me = SimpleNamespace(_finish_pick=lambda c, e, selected: {'FINISHED'} if selected else {'CANCELLED'})
        res = sp.ALLSET_OT_select_priority.invoke(me, ctx, event)
        assert calls == [("joint", arm.name, "Bone")] and res == {'FINISHED'}, (res, calls)
    finally:
        js.pick, js.select, js.select_object_at, sp.hits = real
        prefs.select_priority = was


def test_paint_skin_weights_sections_and_channel_box():
    """Paint Skin Weights Tool Settings = Maya 2024+ frames in order, Blender extras after;
    the Channel Box stays the Channel Box in weight paint mode (no Maya version swaps it for paint UI)."""
    import inspect
    pw = import_module(kit.MODULE + ".ui.paint_weights")
    names = [n for n, _fn in pw.SECTIONS]
    assert names[:7] == ["Skin Clusters", "Influences", "Brush", "Visualization", "Stroke", "Stylus Pressure",
                         "Display"], names
    assert tuple(names[:7]) == pw.MAYA_SECTIONS
    src = inspect.getsource(cb.ALLSET_PT_channel_box.body)
    assert "paint_weights.draw" not in src
    ts = import_module(kit.MODULE + ".ui.tool_settings")
    assert "paint_weights.draw" in inspect.getsource(ts.draw_dock)


def test_column_width_retina():
    """#248: on a Retina display (pixel size 2) the column is 4 px wider than 56 x the scale, or Blender hides the
    toolbar."""
    from types import SimpleNamespace
    tb = import_module(kit.MODULE + ".ui.toolbox")

    def ctx(scale, pixel):
        return SimpleNamespace(preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=scale, pixel_size=pixel)))
    assert tb.column_width(ctx(1.0, 1)) == 56
    assert tb.column_width(ctx(1.25, 1)) == 70
    assert tb.column_width(ctx(2.0, 2)) == 116
