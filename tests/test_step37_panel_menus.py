"""Maya viewport panel menus (View / Shading / Lighting / Show / Renderer / Panels)
in the 3D View header; Blender's View/Select/Add/Object under "Blender".
"""

import json
from importlib import import_module

import bpy

import kit

pm = import_module(kit.MODULE + ".ui.panel_menus")
preferences = import_module(kit.MODULE + ".preferences")


class Layout:
    """Records what a draw function puts in a layout."""

    def __init__(self, log=None):
        self.log = [] if log is None else log

    def _sub(self, *_a, **_k):
        return Layout(self.log)

    row = column = _sub

    def menu(self, idname, text="", **kw):
        self.log.append(("menu", idname, text, kw.get("icon")))

    def menu_contents(self, idname):
        self.log.append(("menu_contents", idname))

    def operator(self, idname, text="", **kw):
        self.log.append(("op", idname, text, kw.get("icon")))
        return type("Props", (), {})()

    def prop(self, owner, prop, text="", **kw):
        assert hasattr(owner, prop), (owner, prop)
        self.log.append(("prop", prop, text))

    def separator(self, **_k):
        pass

    def label(self, text="", **_k):
        self.log.append(("label", text))

    def __getattr__(self, name):   # other template_* calls Blender's own menus make
        return lambda *a, **k: None


class Ctx:
    """A context for draw functions: the space/area of a (fake) 3D View."""

    def __init__(self, space, show_menus=True):
        self.space_data = space
        self.area = type("Area", (), {"show_menus": show_menus, "type": 'VIEW_3D'})()
        self.region_data = space.region_3d
        self.preferences = bpy.context.preferences
        self.scene = bpy.context.scene
        self.view_layer = bpy.context.view_layer
        self.engine = bpy.context.engine

    def __getattr__(self, name):   # everything else from the real context
        return getattr(bpy.context, name)


def _space():
    """A real SpaceView3D (headless: build one through a screen area of the default file)."""
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    return space
    raise AssertionError("no 3D View space in the startup file")


def _prefs():
    return preferences.get(bpy.context)


def test_header_draws_maya_menus():
    log = []
    bpy.types.VIEW3D_MT_editor_menus.draw_collapsible(Ctx(_space()), Layout(log))
    labels = [e[2] for e in log if e[0] == "menu"]
    assert labels == ["View", "Shading", "Lighting", "Show", "Renderer", "Panels", "Blender"], labels


def test_collapsed_header_is_one_menu():
    log = []
    bpy.types.VIEW3D_MT_editor_menus.draw_collapsible(Ctx(_space(), show_menus=False), Layout(log))
    assert log == [("menu", "ALLSET_MT_panel_bar", "", 'COLLAPSEMENU')], log


def test_preference_off_draws_blender_menus():
    _prefs().maya_panel_menus = False
    try:
        log = []
        bpy.types.VIEW3D_MT_editor_menus.draw_collapsible(Ctx(_space()), Layout(log))
        assert log == [("menu_contents", "VIEW3D_MT_editor_menus")], log
    finally:
        _prefs().maya_panel_menus = True


def test_every_menu_draws():
    space = _space()
    for cls in pm.classes:
        if not issubclass(cls, bpy.types.Menu):
            continue
        log = []
        menu = type("M", (), {"layout": Layout(log)})()
        cls.draw(menu, Ctx(space))
        assert log, cls.bl_idname


def test_actions_exist():
    rows = [r for menu in (pm.VIEW, pm.VIEW_AXIS, pm.CAMERA_TOOLS, pm.SHADING, pm.LIGHTING, pm.SHOW,
                           pm.ISOLATE, pm.RENDERER, pm.PANELS, pm.LAYOUTS) for r in menu]
    space = _space()
    for r in rows:
        if r[0] == "run":
            mod, name = r[2].split(".")
            op = getattr(getattr(bpy.ops, mod), name)
            rna = op.get_rna_type()  # raises if the operator doesn't exist
            for k in r[3]:
                assert k in rna.properties, (r[2], k)
        elif r[0] == "prop":
            assert hasattr(pm._owner(space, bpy.context, r[1]), r[2]), r
        elif r[0] == "menu":
            assert hasattr(bpy.types, r[2]), r
    greys = sum(r[0] == "grey" for r in rows)
    mapped = sum(r[0] in ("run", "prop", "set", "menu") for r in rows)
    print(f"panel menu rows: {mapped} mapped, {greys} greyed")
    assert mapped > greys


def test_shading_and_lighting_radios():
    space = _space()
    ctx = Ctx(space)
    sh = space.shading
    pm.apply(ctx, "SHADE_WIRE")
    assert sh.type == 'WIREFRAME' and pm.state(ctx, "SHADE_WIRE") and not pm.state(ctx, "SHADE_SMOOTH")
    pm.apply(ctx, "SHADE_SMOOTH")
    assert sh.type == 'SOLID'
    pm.apply(ctx, "LIGHT_FLAT")
    assert sh.light == 'FLAT' and pm.state(ctx, "LIGHT_FLAT") and not pm.state(ctx, "LIGHT_DEFAULT")
    pm.apply(ctx, "LIGHT_ALL")
    assert sh.type == 'MATERIAL' and sh.use_scene_lights and pm.state(ctx, "LIGHT_ALL")
    assert pm.state(ctx, "RENDER_VP2")
    pm.apply(ctx, "RENDER_ENGINE")
    assert sh.type == 'RENDERED' and pm.state(ctx, "RENDER_ENGINE")
    pm.apply(ctx, "LIGHT_DEFAULT")
    assert sh.type == 'SOLID' and sh.light == 'STUDIO' and pm.state(ctx, "LIGHT_DEFAULT")
    pm.apply(ctx, "DEFAULT_MATERIAL")
    assert sh.color_type == 'SINGLE' and pm.state(ctx, "DEFAULT_MATERIAL")
    pm.apply(ctx, "DEFAULT_MATERIAL")
    assert sh.color_type == 'MATERIAL'


def test_show_all_none():
    space = _space()
    ctx = Ctx(space)
    pm.apply(ctx, "SHOW_NONE")
    assert not any(getattr(space, f"show_object_viewport_{t}") for t in pm.ALL_TYPES)
    pm.apply(ctx, "SHOW_ALL")
    assert all(getattr(space, f"show_object_viewport_{t}") for t in pm.ALL_TYPES)


def test_apply_current_to_all():
    spaces = [s for scr in bpy.data.screens for a in scr.areas for s in a.spaces if s.type == 'VIEW_3D']
    assert len(spaces) > 1, len(spaces)
    src = spaces[0]
    src.shading.type = 'WIREFRAME'
    src.overlay.show_wireframes = True
    pm.apply(Ctx(src), "APPLY_ALL")
    for s in spaces:
        assert s.shading.type == 'WIREFRAME' and s.overlay.show_wireframes
    src.shading.type = 'SOLID'
    pm.apply(Ctx(src), "APPLY_ALL")


def test_view_along_axis_names():
    views = {r[1]: json.loads(json.dumps(r[3]))["view"] for r in pm.VIEW_AXIS}
    assert views == {"X": 'RIGHT', "-X": 'LEFT', "Y": 'BACK', "-Y": 'FRONT', "Z": 'TOP', "-Z": 'BOTTOM'}


def test_disable_restores_header():
    assert "draw_collapsible" in bpy.types.VIEW3D_MT_editor_menus.__dict__
    kit.disable()
    try:
        assert "draw_collapsible" not in bpy.types.VIEW3D_MT_editor_menus.__dict__
        log = []
        bpy.types.VIEW3D_MT_editor_menus.draw_collapsible(Ctx(_space()), Layout(log))
        assert log == [("menu_contents", "VIEW3D_MT_editor_menus")], log
    finally:
        kit.enable()
    assert "draw_collapsible" in bpy.types.VIEW3D_MT_editor_menus.__dict__
