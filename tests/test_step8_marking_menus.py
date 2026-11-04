"""Maya marking menus as pies (definitions, classes, dispatch, keymap, Q/W/E/R)."""

import types
from importlib import import_module

import bpy

import kit

mm = import_module(kit.MODULE + ".marking.menus")
marking = import_module(kit.MODULE + ".marking")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
taphold = import_module(kit.MODULE + ".operators.taphold")
maya_patches = import_module(kit.MODULE + ".keymap.maya_patches")

# Menus resolved by hand (Maya builds their radials at run time).
HAND_RESOLVED = {"RMB_MESH", "RMB_CURVE", "RMB_LATTICE", "RMB_EMPTY"}
LABEL_ALIASES = {"To Edges": "<$toEdges>", "To Faces": "<$toFaces>"}


class FakeLayout:
    def __init__(self, log=None):
        self.log = [] if log is None else log

    def _sub(self, *_a, **_k):
        return FakeLayout(self.log)

    row = column = box = menu_pie = _sub

    def operator(self, idname, text=None, **kw):
        props = types.SimpleNamespace()
        self.log.append(("op", idname, text, props))
        return props

    def menu(self, idname, text=None, **kw):
        self.log.append(("menu", idname, text))

    def separator(self, *a, **kw):
        self.log.append(("sep",))

    def label(self, text="", **kw):
        self.log.append(("label", text))


def _tool_ids():
    from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active as T
    ids = set()

    def walk(items):
        for it in items:
            if isinstance(getattr(it, "idname", None), str):
                ids.add(it.idname)
            elif isinstance(it, (tuple, list)):
                walk(it)
    for _mode, items in T.tools_all():
        walk(items)
    return ids


def _override():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(window=win, area=area, region=region)


def _fresh():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


# --- definitions ------------------------------------------------------------------

def test_definitions_well_formed():
    assert len(mm.MENUS) == 29, sorted(mm.MENUS)  # 13 + 5 hotbox zones + A + 4 UV Editor + pivot edit + lattice + Quad Draw options
    # + Shift+S keyframe / tangent + Shift+Q / Alt+Q
    for name, menu in mm.MENUS.items():
        for path, label, action in mm.walk(menu, name):
            assert label and isinstance(label, str), path
        stack = [menu]
        while stack:
            sub = stack.pop()
            assert set(sub.radial) <= set(mm.RADIALS), (name, sub.radial.keys())
            for _label, action in list(sub.radial.values()) + [e for e in sub.items if e != mm.DIVIDER]:
                if isinstance(action, mm.Sub):
                    stack.append(action)


def test_actions_exist():
    tools = _tool_ids()
    bad = []
    for name, menu in mm.MENUS.items():
        for path, _label, action in mm.walk(menu, name):
            if action is None or isinstance(action, mm.Sub):
                continue
            kind, target, props = menu_map.normalize(action)
            if kind in ("op", "v3d"):
                mod, op = target.split(".")
                try:
                    rna = getattr(getattr(bpy.ops, mod), op).get_rna_type()
                except (AttributeError, KeyError):
                    bad.append((path, target))
                    continue
                bad.extend((path, target, k) for k in props if k not in rna.properties)
            elif kind == "tool" and target not in tools:
                bad.append((path, target))
            elif kind == "menu" and not hasattr(bpy.types, target):
                bad.append((path, target))
    assert not bad, bad


def test_pie_classes_and_slot_order():
    for name in mm.MENUS:
        assert hasattr(bpy.types, marking.idname(name)), name
    # RMB mesh pie: Blender order W, E, S, N, NW, NE, SW, SE.
    fake = types.SimpleNamespace(layout=FakeLayout())
    getattr(bpy.types, marking.idname("RMB_MESH")).draw(fake, bpy.context)
    texts = [e[2] for e in fake.layout.log if e[0] in ("op", "menu")]
    assert texts[:2] == ["Vertex", "UV ▸"], texts  # W, E (UV = submenu)
    # S, then the list under S: the object's name row, then Select
    assert texts[2] == "Face" and texts[3].endswith("...") and texts[4] == "Select", texts
    assert "Edge" in texts and "Object Mode" in texts and texts.index("Edge") > texts.index("Face")
    # Radial submenu = another pie; empty slots = separators.
    fake = types.SimpleNamespace(layout=FakeLayout())
    getattr(bpy.types, marking.idname("SHIFT_EDGE")).draw(fake, bpy.context)
    pies = [e for e in fake.layout.log if e[0] == "op" and e[1] == "wm.call_menu_pie"]
    assert {p[3].name for p in pies} >= {marking.idname("SHIFT_EDGE", "N"),
                                          marking.idname("SHIFT_EDGE", "NE")}, pies
    fake = types.SimpleNamespace(layout=FakeLayout())
    getattr(bpy.types, marking.idname("OPT_ROTATE")).draw(fake, bpy.context)
    seps = [e for e in fake.layout.log if e[0] == "sep"]
    assert seps, "N is empty in Maya's rotate options: a separator keeps the slot"
    # Discrete Rotate (greyed before) is the rotate step snap now
    ops = [e for e in fake.layout.log if e[0] == "op"]
    assert any(e[1] == "allset.step_snap" and e[2] == "Discrete Rotate" for e in ops), ops


def test_dispatch_by_context():
    _fresh()
    R = marking.resolve
    with _override():
        assert R("RMB", bpy.context) == ("pie", marking.idname("RMB_EMPTY"))
        assert R("SHIFT_RMB", bpy.context) == ("pie", marking.idname("SHIFT_DEFAULT"))
        bpy.ops.mesh.primitive_cube_add()
        assert R("RMB", bpy.context) == ("pie", marking.idname("RMB_MESH"))
        assert R("SHIFT_RMB", bpy.context) == ("pie", marking.idname("SHIFT_OBJECT"))
        # Maya's Ctrl+RMB convert marking menu picks by the lead's shape type: a mesh object gets the convert menu
        assert R("CTRL_RMB", bpy.context) == ("pie", marking.idname("CTRL_CONVERT")), "mesh object: convert menu"
        bpy.ops.object.mode_set(mode='EDIT')
        ts = bpy.context.scene.tool_settings
        for sel, want in (((True, False, False), "SHIFT_VERTEX"),
                          ((False, True, False), "SHIFT_EDGE"),
                          ((False, False, True), "SHIFT_FACE")):
            ts.mesh_select_mode = sel
            assert R("SHIFT_RMB", bpy.context) == ("pie", marking.idname(want)), sel
        assert R("CTRL_RMB", bpy.context) == ("pie", marking.idname("CTRL_CONVERT"))
        assert R("RMB", bpy.context) == ("pie", marking.idname("RMB_MESH"))
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.camera_add()
        assert R("RMB", bpy.context) == ("menu", "VIEW3D_MT_object_context_menu")
        bpy.ops.curve.primitive_bezier_curve_add()
        assert R("RMB", bpy.context) == ("pie", marking.idname("RMB_CURVE"))


def test_lattice_dispatch_and_component():
    # #227: a lattice gets the Maya RMB menu in object and edit mode, and
    # Lattice Point enters lattice edit mode
    _fresh()
    R = marking.resolve
    with _override():
        bpy.ops.object.add(type='LATTICE')
        assert R("RMB", bpy.context) == ("pie", marking.idname("RMB_LATTICE"))
        bpy.ops.allset.mm_component(type='LATTICE')
        assert bpy.context.mode == 'EDIT_LATTICE'
        assert R("RMB", bpy.context) == ("pie", marking.idname("RMB_LATTICE"))
        bpy.ops.allset.mm_component(type='NONE')
        bpy.ops.object.mode_set(mode='OBJECT')


def test_tool_options_dispatch():
    ws = bpy.context.workspace
    tool = ws.tools.from_space_view3d_mode('OBJECT', create=True)
    for tid, want in (("builtin.move", "OPT_MOVE"), ("builtin.rotate", "OPT_ROTATE"),
                      ("builtin.scale", "OPT_SCALE"), ("builtin.select_box", "OPT_SELECT")):
        tool.idname = tid
        with _override():
            assert marking.resolve("TOOL_OPTIONS", bpy.context) == ("pie", marking.idname(want)), tid


def test_component_item_targets_picked_object():
    _fresh()
    with _override():
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        a = bpy.context.active_object
        bpy.ops.mesh.primitive_cube_add(location=(5, 0, 0))
        b = bpy.context.active_object
        bpy.context.window_manager.allset_mm_target = a.name  # RMB was over cube a
        bpy.ops.allset.mm_component(type='EDGE')
        assert bpy.context.mode == 'EDIT_MESH' and bpy.context.active_object == a
        assert tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (False, True, False)
        assert not b.select_get()
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.window_manager.allset_mm_target = b.name
        bpy.ops.allset.mm_component(type='NONE')
        assert bpy.context.mode == 'OBJECT' and b.select_get() and not a.select_get()
        bpy.ops.allset.mm_clear_selection()
        assert not bpy.context.selected_objects
        bpy.context.window_manager.allset_mm_target = ""


def test_pick_object_ray_cast():
    _fresh()
    with _override():
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.active_object
        r3d = bpy.context.region_data
        r3d.view_location = (0, 0, 0)
        r3d.view_distance = 10
        region = bpy.context.region
        if region.width < 10:  # -b: region sizes may be 0, ray cast needs a real view
            print("region has no size in -b: skipped")
            return
        ev = types.SimpleNamespace(mouse_region_x=region.width // 2, mouse_region_y=region.height // 2)
        assert marking.pick_object(bpy.context, ev) == cube
        ev = types.SimpleNamespace(mouse_region_x=2, mouse_region_y=2)
        assert marking.pick_object(bpy.context, ev) is None


# --- keymap and Q/W/E/R ------------------------------------------------------------

def _items(km_name):
    kc = kit.maya_kc()
    return kc.keymaps[km_name].keymap_items


def test_keymap_marking_menus():
    for km, _menu in maya_patches.MM_KEYMAPS:
        items = _items(km)
        found = {}
        for kmi in items:
            if kmi.type == 'RIGHTMOUSE' and kmi.idname == "allset.marking_menu" and kmi.value == 'PRESS':
                found[(kmi.shift, kmi.ctrl)] = kmi.properties.trigger
        assert found == {(False, False): "RMB", (True, False): "SHIFT_RMB",
                         (False, True): "CTRL_RMB", (True, True): "TOOL_OPTIONS"}, (km, found)
        assert not [k for k in items if k.idname == "wm.call_menu" and k.type == 'RIGHTMOUSE'], km
    v3d = _items("3D View")
    assert not [k for k in v3d if k.type == 'RIGHTMOUSE' and k.shift and not k.ctrl], "Shift+RMB cursor removed"


def test_sculpt_rmb():
    """Sculpt Mode: plain RMB = the object marking menu, first in "Sculpt" (before the stencil drag); Blender's
    sculpt context panel is gone; the menu resolves to the mesh one."""
    items = [k for k in _items("Sculpt") if k.type == 'RIGHTMOUSE' and k.value == 'PRESS'
             and not (k.shift or k.ctrl or k.alt)]
    assert items and items[0].idname == "allset.marking_menu" and items[0].properties.trigger == "RMB", \
        [k.idname for k in items]
    assert not [k for k in items if k.idname == "wm.call_panel"], [k.idname for k in items]
    assert "allset.marking_menu" in maya_patches.PASS_THROUGH_FIRST
    _fresh()
    with _override():
        bpy.ops.mesh.primitive_cube_add()
        bpy.ops.object.mode_set(mode='SCULPT')
        assert marking.resolve("RMB", bpy.context) == ("pie", marking.idname("RMB_MESH"))
        assert not marking.sculpt_stencil(bpy.context)
        # Select leaves Sculpt Mode, Vertex enters vertex select mode
        bpy.ops.allset.mm_component(type='NONE')
        assert bpy.context.mode == 'OBJECT'
        bpy.ops.object.mode_set(mode='SCULPT')
        bpy.ops.allset.mm_component(type='VERT')
        assert bpy.context.mode == 'EDIT_MESH'
        assert tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (True, False, False)
        bpy.ops.object.mode_set(mode='OBJECT')


def test_keymap_qwer_tap_hold():
    for km in maya_patches.TOOL_KEY_KEYMAPS:
        items = _items(km)
        for key, binding in maya_patches.TOOL_KEYS:
            hits = [k for k in items if k.type == key and not (k.shift or k.ctrl or k.alt)]
            assert [(k.idname, k.properties.binding) for k in hits] == [("allset.tap_hold", binding)], \
                (km, key, [(k.idname) for k in hits])
    for _key, binding in maya_patches.TOOL_KEYS:
        b = taphold.get_binding(binding)
        assert b.tool.startswith("builtin.") and hasattr(bpy.types, marking.idname(b.menu)), binding


def test_bindings_removed_on_disable():
    kit.disable()
    try:
        names = taphold.binding_names()
        assert not any(n.startswith("tool_") for n in names), names
        assert not hasattr(bpy.types, marking.idname("RMB_MESH"))
        assert "allset_mm_target" not in bpy.types.WindowManager.bl_rna.properties
    finally:
        kit.enable()
