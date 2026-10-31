"""Lane A (#96): Maya Graph Editor View / Show items — Auto Frame, Auto Frame Time, Curve Name, Show >
Clear Below / Subdiv Objects mapped (ui/graph_view.py); the rest greyed with a one-line notice."""

from importlib import import_module

import bpy

import kit

menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
notices = import_module(kit.MODULE + ".ui.notices")
graph_view = import_module(kit.MODULE + ".ui.graph_view")
graph_frame = import_module(kit.MODULE + ".operators.graph_frame")
preferences = import_module(kit.MODULE + ".preferences")


GE = "Graph Editor"
MAPPED = {
    f"{GE}/View/Auto Frame": ("prop", "addon_prefs.graph_auto_frame", {}),
    f"{GE}/View/Auto Frame Time": ("prop", "addon_prefs.graph_auto_frame_time", {}),
    f"{GE}/View/Curve Name/Always": ("prop", "addon_prefs.graph_curve_names", {"value": 'ALWAYS'}),
    f"{GE}/View/Curve Name/Never": ("prop", "addon_prefs.graph_curve_names", {"value": 'NEVER'}),
    f"{GE}/View/Curve Name/Active Only": ("prop", "addon_prefs.graph_curve_names", {"value": 'ACTIVE'}),
}
GREYED_VIEW = ("Undo View Change", "Redo View Change", "Clip Time", "Show Results",  # Show Buffer Curves works
               "Show Play Range Shades", "Lock Play Range Shades", "Highlight Affected Curves", "Keys/Never",
               "Key View/Detailed", "Key View/Simple", "Time Ruler Placement/Top", "Time Ruler Placement/Bottom",
               "Theme/Dark", "Theme/Light", "Theme/TRS Distinct", "Theme/Colorblind Compatible", "Theme/Classic",
               "Theme/Export Current Theme", "Simple Toolbar")
# IkHandles / Sets / Characters and the Hidden / Driven by / User Defined filters work (test_step203_list)
GREYED_SHOW = ("Objects/Asset", "Objects/Characters", "Objects/Clips",
               "Objects/MASH", "Attributes/Published", "Show Selected Type(s)", "Select Attributes...", "Create Entry...",
               "Delete Entry...", "Show Auxiliary Nodes", "Auxiliary Nodes...")


def _prefs():
    return preferences.get(bpy.context)


def _scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 120
    sc.frame_preview_start, sc.frame_preview_end = 10, 30   # (setting the start turns the preview range on)
    sc.use_preview_range = False
    obs = []
    for name, frames, axis, values in (("pCube1", (1, 24), 0, (0.0, 5.0)), ("pCube2", (40, 200), 2, (0.0, 50.0))):
        bpy.ops.mesh.primitive_cube_add()
        ob = bpy.context.active_object
        ob.name = name
        for f, v in zip(frames, values):
            ob.location[axis] = v
            ob.keyframe_insert("location", index=axis, frame=f)
        obs.append(ob)
    sc.frame_set(1)
    return obs


def _graph():
    w = bpy.context.window_manager.windows[0]
    area = max(w.screen.areas, key=lambda a: a.width * a.height)
    area.ui_type = 'FCURVES'
    area.spaces.active.dopesheet.show_only_selected = True
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return w, area, region


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def _view(region):
    v = region.view2d
    (x0, y0), (x1, y1) = v.region_to_view(0, 0), v.region_to_view(region.width, region.height)
    return x0, y0, x1, y1


# --- mappings ---------------------------------------------------------------------------------------------------


def test_show_items_mapped():
    for ed in ("Graph Editor", "Dope Sheet"):
        assert menu_map.spec(f"{ed}/Show/Objects/Clear Below")[1] == "allset.graph_show_clear"
        assert menu_map.spec(f"{ed}/Show/Attributes/Clear Below")[1] == "allset.graph_attr_clear"
        assert menu_map.spec(f"{ed}/Show/Objects/Subdiv Objects") == (
            "prop", "space_data.dopesheet.show_meshes", {})


def test_show_clear_below_lists_every_object_type():
    w, area, region = _graph()
    ds = area.spaces.active.dopesheet
    for attr in graph_view.OBJECT_FILTERS:
        setattr(ds, attr, False)
    ds.filter_text = "Location"
    with bpy.context.temp_override(window=w, area=area, region=region):
        assert bpy.ops.allset.graph_show_clear() == {'FINISHED'}
        # (Blender's context_set_* report CANCELLED for space_data paths: no undo step, the value is set)
        bpy.ops.wm.context_set_string(data_path="space_data.dopesheet.filter_text", value="")
    assert all(getattr(ds, a) for a in graph_view.OBJECT_FILTERS)
    assert ds.filter_text == ""


# --- Auto Frame / Auto Frame Time -------------------------------------------------------------------------------

def _canvas_values(w, area, region):
    """(v0, v1) shown between Blender's time ruler strip and scroll bar (operators/graph_frame.py)."""
    with bpy.context.temp_override(window=w, area=area, region=region):
        bottom, top = graph_frame.pads(bpy.context, area.spaces.active)
    h = graph_frame.span_px(region)[1]
    v = region.view2d
    return v.region_to_view(0.0, bottom)[1], v.region_to_view(0.0, h - top)[1]


def test_auto_frame_frames_the_new_selection():
    """Maya Auto Frame: the value axis is refit to the curves shown (25 % margins), the time range stays."""
    a, b = _scene()
    w, area, region = _graph()
    p = _prefs()
    p.graph_auto_frame, p.graph_auto_frame_time = True, False
    graph_view._state["sig"] = None
    _select(a)
    assert graph_view.step(bpy.context, p) == 0, "first poll = baseline"
    assert graph_view.step(bpy.context, p) == 0, "no change, no frame"
    x0, x1, _y0, _y1 = graph_frame.current_view(region)
    for ob, (v0, v1) in ((b, (-12.5, 62.5)), (a, (-1.25, 6.25))):
        _select(ob)
        assert graph_view.step(bpy.context, p) == 1
        nx0, nx1, _ny0, _ny1 = graph_frame.current_view(region)
        assert abs(nx0 - x0) < 1e-3 and abs(nx1 - x1) < 1e-3, ("time range kept", (x0, x1), (nx0, nx1))
        got = _canvas_values(w, area, region)
        assert abs(got[0] - v0) < 1e-2 and abs(got[1] - v1) < 1e-2, (got, (v0, v1))
    # off: no framing
    p.graph_auto_frame = False
    _select(b)
    assert graph_view.step(bpy.context, p) == 0
    assert abs(_canvas_values(w, area, region)[1] - 6.25) < 1e-2
    p.graph_auto_frame = True


def test_auto_frame_time_keeps_the_value_axis_and_the_preview_range():
    """Auto Frame Time alone: the time axis is refit with 10 % margins, the value axis stays."""
    a, b = _scene()
    w, area, region = _graph()
    p = _prefs()
    p.graph_auto_frame, p.graph_auto_frame_time = False, True
    graph_view._state["sig"] = None
    _select(a)
    graph_view.step(bpy.context, p)
    _x0, _x1, y0, y1 = graph_frame.current_view(region)
    sc = bpy.context.scene
    for on, ob, (t0, t1) in ((False, b, (24.0, 216.0)), (True, a, (-1.3, 26.3))):
        sc.use_preview_range = on
        before = (sc.use_preview_range, sc.frame_preview_start, sc.frame_preview_end)
        _select(ob)
        assert graph_view.step(bpy.context, p) == 1
        got = (sc.use_preview_range, sc.frame_preview_start, sc.frame_preview_end)
        assert got == before, (got, before)
        x0, x1, ny0, ny1 = graph_frame.current_view(region)
        assert abs(x0 - t0) < 1e-2 and abs(x1 - t1) < 1e-2, (x0, x1, t0, t1)
        assert abs(ny0 - y0) < 1e-3 and abs(ny1 - y1) < 1e-3, "value axis kept"
    p.graph_auto_frame, p.graph_auto_frame_time = True, False


def test_time_span():
    assert graph_view.time_span([]) is None
    assert graph_view.time_span([40, 200]) == (32, 208)
    lo, hi = graph_view.time_span([5])
    assert lo < 5 < hi


# --- Curve Name -------------------------------------------------------------------------------------------------

def test_plug_names():
    assert graph_view.maya_attr("Translate X") == "translateX"
    assert graph_view.maya_attr("Delta Rotate Z") == "deltaRotateZ"
    assert graph_view.maya_attr("myAttr") == "myAttr"
    assert graph_view.plug_name("pCube1", "location", "Translate X") == "pCube1.translateX"
    assert graph_view.plug_name("rig", 'pose.bones["joint2"].location', "Translate Y") == "joint2.translateY"
    assert graph_view.plug_name("Key", 'key_blocks["smile"].value', "Value") == "smile.value"


def test_curve_names_drawn_per_mode():
    a, b = _scene()
    w, area, region = _graph()
    _select(a, b)
    p = _prefs()
    with bpy.context.temp_override(window=w, area=area, region=region):
        bpy.ops.graph.view_all()
        p.graph_curve_names = 'NEVER'
        assert graph_view.name_items(bpy.context, region) == []
        p.graph_curve_names = 'ALWAYS'
        items = graph_view.name_items(bpy.context, region)
        texts = sorted(t for _x, _y, t, _c in items)
        assert texts == ["pCube1.translateX", "pCube2.translateZ"], texts
        # at the last key, in region pixels of the stored value
        x, y, _t, rgba = next(i for i in items if i[2] == "pCube2.translateZ")
        ex, ey = region.view2d.view_to_region(200, 50.0, clip=False)
        assert abs(x - ex) < 1 and abs(y - ey) < 1, (x, y, ex, ey)
        assert len(rgba) == 4
        p.graph_curve_names = 'ACTIVE'
        for ob, sel in ((a, True), (b, False)):
            for fc in kit.fcurves(ob):
                fc.select = sel
        assert [t for _x, _y, t, _c in graph_view.name_items(bpy.context, region)] == ["pCube1.translateX"]
        area.spaces.active.use_normalization = True
        assert graph_view.name_items(bpy.context, region) == [], "normalized view: no names"
        area.spaces.active.use_normalization = False
    p.graph_curve_names = 'NEVER'


# --- notices ----------------------------------------------------------------------------------------------------

def test_still_greyed_items_have_a_notice():
    paths = [f"{GE}/View/{i}" for i in GREYED_VIEW] + [f"{ed}/Show/{i}" for ed in (GE, "Dope Sheet")
                                                         for i in GREYED_SHOW]
    paths.remove(f"{GE}/Show/Objects/Characters")      # character nodes in the kit Graph Editor outliner
    paths.remove("Dope Sheet/Show/Objects/Characters")  # their members in the Dope Sheet
    leaves = {p for p, _it in menu_sets.iter_items()}
    for path in paths:
        assert path in leaves, path
        assert path not in menu_map.MAP, path
        sub, line = notices.greyed_notice(path)
        assert sub and "Blender" in line, path
    # the View items now have their own line (no generic "no such display option")
    for item in GREYED_VIEW:
        if not item.startswith("Theme/"):
            assert f"{GE}/View/{item}" in notices.NOTICES, item
    assert f"{GE}/View/Show Buffer Curves" in menu_map.MAP      # kit buffer curves
