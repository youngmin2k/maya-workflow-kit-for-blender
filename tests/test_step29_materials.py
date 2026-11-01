"""Maya material assignment (Lighting/Shading menu, RMB menu, Shift+T).

Object assignment = whole shape, face selection = only those faces.
"""

from importlib import import_module

import bmesh
import bpy

import kit

menu_map = import_module(kit.MODULE + ".ui.menu_map")
mm = import_module(kit.MODULE + ".marking.menus")
material = import_module(kit.MODULE + ".operators.material")


def _scene():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.view_layer.update()   # the new cube joins lambert1 (Maya's initialShadingGroup)
    return bpy.context.active_object


def _edit_faces(ob, indices, mode='FACE'):
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type=mode)
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    for i in indices:
        bm.faces[i].select = True
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)


def _indices(ob):
    if ob.mode == 'EDIT':
        ob.update_from_editmode()
    return [p.material_index for p in ob.data.polygons]


def test_shading_menu_items_mapped():
    expect = {
        "Lighting/Shading/Material Attributes": ("v3d", "allset.material_attributes"),
        "Lighting/Shading/Assign New Material/New Material...": ("op", "allset.assign_new_material"),
        "Lighting/Shading/Assign Favorite Material": ("menu", "ALLSET_MT_assign_favorite_material"),
        "Lighting/Shading/Assign Existing Material": ("menu", "ALLSET_MT_assign_existing_material"),
    }
    menus = import_module(kit.MODULE + ".ui.menu_sets")
    paths = {path for path, _label in menus.iter_items()}
    for path, (kind, target) in expect.items():
        assert path in paths, f"{path} not a Maya menu path"
        spec = menu_map.spec(path)
        assert spec is not None and spec[:2] == (kind, target), (path, spec)
        if kind == "menu":
            assert hasattr(bpy.types, target), target
        else:
            mod, name = target.split(".")
            assert hasattr(getattr(bpy.ops, mod), name), target


def test_new_material_object_replaces_all_slots():
    ob = _scene()
    old = bpy.data.materials.new("old")
    ob.data.materials.append(None)
    ob.data.materials.append(old)
    ob.data.polygons[2].material_index = 1
    assert bpy.ops.allset.assign_new_material(kind='LAMBERT') == {'FINISHED'}
    # lambert1 is the default material (like Maya), so a new Lambert is lambert2 (Maya)
    assert [s.material.name for s in ob.material_slots] == ["lambert2"], [s.material for s in ob.material_slots]
    assert set(_indices(ob)) == {0}
    # Maya names count up per type; Principled values from the kind.
    bpy.ops.allset.shelf_material(kind='LAMBERT')
    assert ob.active_material.name == "lambert3"
    bpy.ops.allset.shelf_material(kind='STANDARD_SURFACE')
    assert ob.active_material.name == "standardSurface1"
    wm = bpy.context.window_manager
    assert wm.allset_ae_tab == "MAT:0", wm.allset_ae_tab


def test_faces_only_in_face_mode():
    ob = _scene()
    _edit_faces(ob, [1, 3])
    assert bpy.ops.allset.shelf_material(kind='BLINN') == {'FINISHED'}
    idx = _indices(ob)
    assert [s.material.name if s.material else None for s in ob.material_slots] == ["lambert1", "blinn1"]
    assert [i for i, v in enumerate(idx) if v == 1] == [1, 3], idx
    # Another material on another face adds a slot; the same material reuses its slot.
    _edit_faces(ob, [0])
    bpy.ops.allset.shelf_material(kind='PHONG')
    _edit_faces(ob, [5])
    bpy.ops.allset.assign_material(material="blinn1")
    idx = _indices(ob)
    assert len(ob.material_slots) == 3, len(ob.material_slots)
    assert idx == [2, 1, 0, 1, 0, 1], idx
    assert bpy.context.window_manager.allset_ae_tab == "MAT:2"


def test_vertex_mode_assigns_whole_object():
    ob = _scene()
    _edit_faces(ob, [1], mode='VERT')
    bpy.ops.allset.shelf_material(kind='PHONG')
    assert [s.material.name for s in ob.material_slots] == ["phong1"]
    assert set(_indices(ob)) == {0}
    # Object assignment in face mode with nothing selected: the whole object too.
    _edit_faces(ob, [])
    bpy.ops.allset.shelf_material(kind='LAMBERT')
    assert [s.material.name for s in ob.material_slots] == ["lambert2"]


def test_existing_material_and_rmb_target():
    ob = _scene()
    other = bpy.data.objects.new("pCube2", ob.data.copy())
    bpy.context.collection.objects.link(other)
    mat = bpy.data.materials.new("blinn7")
    for o in bpy.context.selected_objects:
        o.select_set(False)
    wm = bpy.context.window_manager
    wm.allset_mm_target = ""
    assert not material.targets(bpy.context, rmb=True)
    assert not bpy.ops.allset.assign_material.poll()
    # From the RMB menu, nothing selected: the object the menu was opened on.
    wm.allset_mm_target = other.name
    assert bpy.ops.allset.assign_material(material="blinn7") == {'CANCELLED'}, "top menu: selection only"
    assert bpy.ops.allset.assign_material(material="blinn7", rmb=True) == {'FINISHED'}
    assert other.active_material == mat and ob.active_material is not mat
    # A selection overrides the object under the menu (Maya 2022 RMB marking menu).
    ob.select_set(True)
    bpy.ops.allset.shelf_material(kind='LAMBERT', rmb=True)
    assert ob.active_material.name == "lambert2" and other.active_material == mat
    wm.allset_mm_target = ""


def test_material_attributes_opens_ae_tab():
    ob = _scene()
    ob.data.materials.append(bpy.data.materials.new("a"))
    ob.data.materials.append(bpy.data.materials.new("b"))
    ob.active_material_index = 1
    wm = bpy.context.window_manager
    wm.allset_dock = 'CHANNEL_BOX'
    assert bpy.ops.allset.material_attributes() == {'FINISHED'}
    assert wm.allset_dock == 'ATTRIBUTE_EDITOR' and wm.allset_ae_tab == "MAT:1"
    wm.allset_dock = 'CHANNEL_BOX'
    bare = _scene()
    bare.data.materials.clear()   # (a new mesh joins lambert1)
    assert not bare.material_slots
    assert not bpy.ops.allset.material_attributes.poll()


class _Layout:
    def __init__(self):
        self.ops = []
        self.labels = []

    def operator(self, idname, text="", icon='NONE'):
        class P:
            pass
        p = P()
        self.ops.append((idname, text, p))
        return p

    def label(self, text=""):
        self.labels.append(text)


def _draw(menu_cls):
    lay = _Layout()
    fake = type("M", (), {"layout": lay, "rmb": menu_cls.rmb})()
    menu_cls.draw(fake, bpy.context)
    return lay


def test_favorite_and_existing_menus():
    _scene()
    fav = _draw(material.ALLSET_MT_assign_favorite_material)
    assert [(t, p.kind) for _i, t, p in fav.ops] == [
        ("Lambert", 'LAMBERT'), ("Blinn", 'BLINN'), ("Phong", 'PHONG'), ("Standard Surface", 'STANDARD_SURFACE')]
    assert {i for i, _t, _p in fav.ops} == {"allset.shelf_material"}
    # Maya's scene always has lambert1, so Assign Existing Material lists it
    assert [t for _i, t, _p in _draw(material.ALLSET_MT_assign_existing_material).ops] == ["lambert1"]
    bpy.data.materials.new("phong1")
    bpy.data.materials.new("Blinn2")
    gp = bpy.data.materials.new("stroke")
    bpy.data.materials.create_gpencil_data(gp)
    ex = _draw(material.ALLSET_MT_assign_existing_material_rmb)
    assert [(t, p.material, p.rmb) for _i, t, p in ex.ops] == [("Blinn2", "Blinn2", True),
                                                               ("lambert1", "lambert1", True),
                                                               ("phong1", "phong1", True)], ex.ops


def test_rmb_menu_lists_material_items():
    for menu in (mm.RMB_MESH, mm.RMB_CURVE):
        labels = [e[0] for e in menu.items if e != mm.DIVIDER]
        tail = labels[-4:]
        assert tail == ["Material Attributes...", "Assign New Material", "Assign Favorite Material",
                        "Assign Existing Material"], (menu.name, labels)
        items = dict(e for e in menu.items if e != mm.DIVIDER)
        assert items["Assign New Material"].items == [("New Material...", ("allset.assign_new_material",
                                                                           {"rmb": True}))]
        # the scene's materials, filled when the menu opens (a submenu like Maya's, #283)
        assert isinstance(items["Assign Existing Material"], mm.MaterialList)
        assert not mm.is_unavailable(items["Assign Existing Material"])
        filled = dict(e for e in mm.with_materials(menu, ["blinn1", "lambert1"]).items if e != mm.DIVIDER)
        assert filled["Assign Existing Material"].items == [
            ("blinn1", ("allset.assign_material", {"material": "blinn1", "rmb": True})),
            ("lambert1", ("allset.assign_material", {"material": "lambert1", "rmb": True}))]
        fav = items["Assign Favorite Material"]
        assert isinstance(fav, mm.Sub) and [k[1][1]["kind"] for k in fav.items] == [
            'LAMBERT', 'BLINN', 'PHONG', 'STANDARD_SURFACE']
    assert mm.RMB_MESH.items[-2][1] is not mm.RMB_CURVE.items[-2][1], "own favourite submenu each"
    engine = import_module(kit.MODULE + ".marking.engine")
    assert engine.Layout._text("Assign Existing Material", ("menu", "X")).endswith("▸")


def test_shift_t_keymap():
    kc = kit.maya_kc()
    for km_name in ("Object Mode", "Mesh"):
        km = kc.keymaps[km_name]
        hits = [k.idname for k in km.keymap_items if k.active and k.type == 'T' and k.value == 'PRESS'
                and k.shift and not (k.ctrl or k.alt or k.oskey)]
        assert hits == ["allset.assign_new_material"], (km_name, hits)


def test_list_submenu_kept_inside_region():
    """The Favorite submenu opened near the region's bottom edge moves up (GUI step-29 shot)."""
    engine = import_module(kit.MODULE + ".marking.engine")

    def measure(text):
        return 7.0 * len(text)

    bounds = (0, 0, 800, 600)
    s = engine.Session(mm.RMB_MESH, (400.0, 120.0), 0.0, measure, None, None, bounds)
    fav = next(it for it in s.layout.items if it.label == "Assign Favorite Material")
    s.move(400 + fav.rect[0] + 5, 120 + (fav.rect[1] + fav.rect[3]) / 2, 0.3)
    assert len(s.stack) == 2, "hover opens the submenu"
    cx, cy = s.center
    for it in s.layout.items:
        assert bounds[1] <= cy + it.rect[1] and cy + it.rect[3] <= bounds[3], (it.label, cy, it.rect)
        assert bounds[0] <= cx + it.rect[0] and cx + it.rect[2] <= bounds[2], (it.label, cx, it.rect)
    # Without bounds (headless callers) the submenu stays at the row's corner.
    s = engine.Session(mm.RMB_MESH, (400.0, 120.0), 0.0, measure)
    fav = next(it for it in s.layout.items if it.label == "Assign Favorite Material")  # unmoved root
    s.move(400 + fav.rect[0] + 5, 120 + (fav.rect[1] + fav.rect[3]) / 2, 0.3)
    assert s.center == (400 + fav.rect[2], 120 + fav.rect[3])
