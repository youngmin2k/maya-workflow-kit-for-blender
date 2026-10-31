"""Step 11: Maya Outliner (UIList rows) and Attribute Editor (node tabs, template sections).

"""

import types
from importlib import import_module

import bpy

import kit

outliner = import_module(kit.MODULE + ".ui.outliner")
ae = import_module(kit.MODULE + ".ui.attribute_editor")
ae_layout = import_module(kit.MODULE + ".ui.ae_layout")


class FakeLayout:
    """Records what a draw function asks for; checks every prop exists."""

    def __init__(self, log=None):
        self.log = [] if log is None else log
        self.active = self.enabled = True
        self.alert = False

    def _sub(self, *_a, **_k):
        return FakeLayout(self.log)

    row = column = box = split = _sub

    def panel(self, idname, default_closed=False):
        self.log.append(("panel", idname, default_closed))
        return FakeLayout(self.log), FakeLayout(self.log)

    def prop(self, owner, attr, text=None, **kw):
        if not attr.startswith("["):
            assert attr in owner.bl_rna.properties, f"{owner!r} has no {attr}"
        self.log.append(("prop", owner, attr, text))

    def operator(self, idname, text=None, **kw):
        mod, name = idname.split(".")
        getattr(getattr(bpy.ops, mod), name).get_rna_type()  # raises if missing
        props = types.SimpleNamespace()
        self.log.append(("op", idname, text, props))
        return props

    def label(self, text="", **kw):
        self.log.append(("label", text))

    def menu(self, idname, text="", **kw):
        assert hasattr(bpy.types, idname), idname
        self.log.append(("menu", idname, text))

    def separator(self, *a, **kw):
        pass

    def template_list(self, *a, **kw):
        self.log.append(("list",) + a)


def _fresh():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    wm = bpy.context.window_manager
    wm.allset_ae_tab = ""
    wm.allset_ae_kind = "S"
    wm.allset_outliner_shapes = False


def _mesh(name, parent=None):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name + "Shape"))
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    return ob


def _empty(name, parent=None):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    return ob


def _rows():
    outliner.rebuild(bpy.context, force=True)
    return [(r.kind, r.label, r.depth) for r in bpy.context.window_manager.allset_outliner_rows]


def _select(objs, active=None):
    for o in bpy.context.view_layer.objects:
        if o is not None:   # Blender 5.x yields None for objects removed before the view layer syncs
            o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[-1] if objs else None)


# --- Outliner ------------------------------------------------------------------------------

def _scene():
    _fresh()
    grp = _empty("group1")
    a = _mesh("pCube1", grp)
    b = _mesh("pSphere1", grp)
    c = _mesh("pCone1", a)
    d = _mesh("pPlane1")
    return grp, a, b, c, d


def test_outliner_dag_order_and_collapse():
    grp, a, b, c, d = _scene()
    assert _rows() == [('OBJECT', "group1", 0), ('OBJECT', "pPlane1", 0)]   # autoExpand 0
    grp.allset_expanded = True
    assert _rows() == [('OBJECT', "group1", 0), ('OBJECT', "pCube1", 1), ('OBJECT', "pSphere1", 1),
                       ('OBJECT', "pPlane1", 0)]
    rows = bpy.context.window_manager.allset_outliner_rows
    assert rows[0].has_children and rows[1].has_children and not rows[2].has_children


def test_outliner_expand_recursive_and_shapes():
    grp, a, b, c, d = _scene()
    outliner.rebuild(bpy.context, force=True)
    bpy.ops.allset.outliner_expand(name="group1", recursive=True)
    assert a.allset_expanded and c.allset_expanded
    assert [r[1] for r in _rows()] == ["group1", "pCube1", "pCone1", "pSphere1", "pPlane1"]
    bpy.context.window_manager.allset_outliner_shapes = True
    d.allset_expanded = True
    rows = _rows()
    assert ('SHAPE', "pCube1Shape", 2) in rows, rows
    i = rows.index(('OBJECT', "pCube1", 1))
    assert rows[i + 1] == ('SHAPE', "pCube1Shape", 2)          # shape first under its transform
    assert ('SHAPE', "pPlane1Shape", 1) in rows
    assert not any(r[1] == "group1" and r[0] == 'SHAPE' for r in rows)  # empty: no shape
    bpy.ops.allset.outliner_expand(name="group1")             # collapse
    assert [r[1] for r in _rows()][:2] == ["group1", "pPlane1"]


def test_outliner_rebuild_skips_when_unchanged():
    _scene()
    assert outliner.rebuild(bpy.context, force=True)
    assert not outliner.rebuild(bpy.context)
    _mesh("pTorus1")
    assert outliner.rebuild(bpy.context)


def test_outliner_rename_through_label():
    grp, a, b, c, d = _scene()
    wm = bpy.context.window_manager
    wm.allset_outliner_shapes = True
    d.allset_expanded = True
    outliner.rebuild(bpy.context, force=True)
    rows = wm.allset_outliner_rows
    obj_row = next(r for r in rows if r.kind == 'OBJECT' and r.object == "pPlane1")
    obj_row.label = "floor"
    assert d.name == "floor" and obj_row.object == "floor"
    outliner.rebuild(bpy.context)
    shape_row = next(r for r in rows if r.kind == 'SHAPE' and r.object == "floor")
    shape_row.label = "floorShape1"
    assert d.data.name == "floorShape1"


def test_outliner_selection_modes():
    grp, a, b, c, d = _scene()
    grp.allset_expanded = True
    outliner.rebuild(bpy.context, force=True)
    wm = bpy.context.window_manager
    names = [r.object for r in wm.allset_outliner_rows]     # group1 pCube1 pSphere1 pPlane1
    wm.allset_outliner_index = names.index("pCube1")        # row click = replace
    assert bpy.context.selected_objects == [a] and bpy.context.view_layer.objects.active is a
    assert wm.allset_outliner_index == names.index("pCube1")
    bpy.ops.allset.outliner_select(index=names.index("pPlane1"), mode='TOGGLE')
    assert set(bpy.context.selected_objects) == {a, d}
    bpy.ops.allset.outliner_select(index=names.index("pPlane1"), mode='TOGGLE')
    assert set(bpy.context.selected_objects) == {a}
    _select([grp], grp)
    bpy.ops.allset.outliner_select(index=names.index("pSphere1"), mode='RANGE')
    assert set(bpy.context.selected_objects) == {grp, a, b}
    bpy.ops.allset.outliner_select(index=names.index("pPlane1"), mode='REPLACE')
    assert bpy.context.selected_objects == [d]


def test_outliner_list_draws():
    grp, a, b, c, d = _scene()
    bpy.context.window_manager.allset_outliner_shapes = True
    a.allset_expanded = grp.allset_expanded = True
    outliner.rebuild(bpy.context, force=True)
    ul = outliner.ALLSET_UL_outliner
    lay = FakeLayout()
    for i, row in enumerate(bpy.context.window_manager.allset_outliner_rows):
        ul.draw_item(None, bpy.context, lay, None, row, 0, None, "", i)
    icons = [e for e in lay.log if e[0] == "op" and e[1] == "allset.outliner_select"]
    assert len(icons) == len(bpy.context.window_manager.allset_outliner_rows)
    assert outliner.icon_for(bpy.context.window_manager.allset_outliner_rows[0], grp) == 'OUTLINER_OB_EMPTY'


# --- Attribute Editor ----------------------------------------------------------------------------

def _textured_cube():
    _fresh()
    ob = _mesh("pCube1")
    ob.modifiers.new("polySmooth1", 'SUBSURF')
    ob.modifiers.new("polyBevel1", 'BEVEL')
    mat = bpy.data.materials.new("standardSurface1")
    mat.use_nodes = True
    ob.data.materials.append(mat)
    _select([ob], ob)
    return ob, mat


def test_ae_tabs_in_maya_order():
    ob, mat = _textured_cube()
    assert ae.tabs(ob) == [("T", "pCube1", "transform"), ("S", "pCube1Shape", "mesh"),
                           ("M:polySmooth1", "polySmooth1", "polySmoothFace"),   # Maya node types (step 106)
                           ("M:polyBevel1", "polyBevel1", "polyBevel3"),
                           ("SG:0", "standardSurface1SG", "shadingEngine"),   # Maya's shading group (step 100)
                           ("MAT:0", "standardSurface1", "standardSurface")]
    assert ae.current_tab(bpy.context, ob) == "S"      # default: shape (preferred node)


def test_ae_tab_kind_kept_across_selection_and_steps():
    ob, mat = _textured_cube()
    bpy.ops.allset.ae_tab(key="M:polySmooth1")
    bpy.ops.allset.ae_step(forward=True)
    assert ae.current_tab(bpy.context, ob) == "M:polyBevel1"
    bpy.ops.allset.ae_step(forward=False)
    assert ae.current_tab(bpy.context, ob) == "M:polySmooth1"
    other = _mesh("pSphere1")
    other.modifiers.new("polyMirror1", 'MIRROR')
    _select([other], other)
    assert ae.current_tab(bpy.context, other) == "M:polyMirror1"   # same kind: history
    bpy.ops.allset.ae_tab(key="T")
    lamp = bpy.data.objects.new("pointLight1", bpy.data.lights.new("pointLightShape1", 'POINT'))
    bpy.context.scene.collection.objects.link(lamp)
    assert ae.current_tab(bpy.context, lamp) == "T"


def _maya_sections(nodes, out, prefix=""):
    for n in nodes:
        if "section" in n:
            key = prefix + n["section"]
            out.setdefault(key, n["collapse"])
            _maya_sections(n.get("children", []), out, key + "/")
    return out


def _rna_owner(owner_name, kind):
    if kind == "joint":   # step 55: a joint is a pose bone
        return {"ob": bpy.types.PoseBone, "bone": bpy.types.Bone, "arm": bpy.types.Armature,
                "armob": bpy.types.Object}[owner_name]
    if owner_name == "ob":
        return bpy.types.Object
    if owner_name == "view":
        return bpy.types.SpaceView3D
    return {"MESH": bpy.types.Mesh, "CAMERA": bpy.types.Camera, "POINT": bpy.types.PointLight,
            "SUN": bpy.types.SunLight, "SPOT": bpy.types.SpotLight, "AREA": bpy.types.AreaLight,
            "material": bpy.types.Material, "FONT": bpy.types.TextCurve}.get(kind)


def test_ae_rows_exist_in_blender():
    sockets = {s.name for s in _principled_inputs()}
    bad = []
    for kind, (sections, _t) in ae_layout.BY_KIND.items():
        for _d, sec in ae_layout.walk(sections):
            for row in sec.rows:
                if row[0] == "prop":
                    rna = _rna_owner(row[1], kind).bl_rna
                    *head, attr = row[2].split(".")
                    for part in head:
                        rna = rna.properties[part].fixed_type
                    if attr not in rna.properties:
                        bad.append((kind, sec.name, row))
                elif row[0] == "socket" and row[1] not in sockets:
                    bad.append((kind, sec.name, row))
                elif row[0] == "draw" and not (row[1] in ae.DRAWERS or row[1].startswith("limit:")):
                    bad.append((kind, sec.name, row))
    assert not bad, bad


def _principled_inputs():
    mat = bpy.data.materials.new("probe")
    mat.use_nodes = True
    return list(ae.principled(mat).inputs)


def test_ae_draws_every_tab():
    ob, mat = _textured_cube()
    cam = bpy.data.objects.new("camera1", bpy.data.cameras.new("cameraShape1"))
    lamp = bpy.data.objects.new("spotLight1", bpy.data.lights.new("spotLightShape1", 'SPOT'))
    sun = bpy.data.objects.new("directionalLight1", bpy.data.lights.new("dl", 'SUN'))
    ob["myAttr"] = 2.0
    plain = bpy.data.materials.new("lambert1")
    ob.data.materials.append(plain)
    for o in (cam, lamp, sun):
        bpy.context.scene.collection.objects.link(o)
    for target in (ob, cam, lamp, sun):
        _select([target], target)
        for key, _label, _type in ae.tabs(target):
            bpy.ops.allset.ae_tab(key=key)
            lay = FakeLayout()
            ae.draw(lay, bpy.context, target)
            panels = [e for e in lay.log if e[0] == "panel"]
            assert panels, (target.name, key)
            if key == "T":
                # the lead and only selected node: Maya number fields (Channel Box text proxies, step 148 #85)
                assert (("prop", target, "location", "") in lay.log or
                        ("prop", bpy.context.scene.allset_cb, "tx_text", "") in lay.log), lay.log[:12]
                assert ("label", "Translate") in lay.log
                assert any(e[0] == "panel" and e[1].endswith("Transform Attributes") and not e[2]
                           for e in lay.log)   # open, as in Maya
                if target is ob:
                    assert any(e[0] == "prop" and e[2] == '["myAttr"]' for e in lay.log)
            if key.startswith("M:"):
                assert any(e[0] == "op" and e[1] == "allset.ae_modifier" for e in lay.log)
    # Material tab: sockets of the Principled BSDF under Maya standardSurface sections.
    _select([ob], ob)
    bpy.ops.allset.ae_tab(key="MAT:0")
    lay = FakeLayout()
    ae.draw(lay, bpy.context, ob)
    labels = [e[3] for e in lay.log if e[0] == "prop" and e[2] == "default_value"]
    assert "Color" in labels and "Metalness" in labels, labels
    bpy.ops.allset.ae_tab(key="MAT:1")
    lay = FakeLayout()
    ae.draw(lay, bpy.context, ob)
    if plain.node_tree is not None and any(n.type == 'BSDF_PRINCIPLED' for n in plain.node_tree.nodes):
        # Blender 5.x: every new material has a Principled tree, shown as standardSurface (step 53)
        assert "Color" in [e[3] for e in lay.log if e[0] == "prop" and e[2] == "default_value"]
    else:
        assert ("prop", plain, "diffuse_color", "Color") in lay.log


def test_ae_modifier_apply_and_remove():
    ob, mat = _textured_cube()
    n = len(ob.data.vertices)
    bpy.ops.allset.ae_modifier(modifier="polyBevel1", action='REMOVE')
    assert [m.name for m in ob.modifiers] == ["polySmooth1"]
    bpy.ops.allset.ae_modifier(modifier="polySmooth1", action='APPLY')
    assert len(ob.modifiers) == 0 and len(ob.data.vertices) == n   # empty mesh stays empty


def test_ae_add_limit_and_select():
    ob, mat = _textured_cube()
    bpy.ops.allset.ae_add_limit(type='LIMIT_ROTATION')
    assert ob.constraints[0].type == 'LIMIT_ROTATION'
    lay = FakeLayout()
    ae.draw_limit(lay, bpy.context, ob, 'LIMIT_ROTATION')
    assert ("prop", ob.constraints[0], "use_limit_x", None) in lay.log
    other = _mesh("pSphere1")
    _select([ob, other], ob)
    bpy.ops.allset.ae_select()
    assert bpy.context.selected_objects == [ob]


def test_dock_mode_switches_panels():
    wm = bpy.context.window_manager
    wm.allset_dock = 'CHANNEL_BOX'
    # step 116: no 3D View sidebar tabs any more; one panel draws the Maya panels in their own dock areas (a
    # Properties Tool tab draws "Tool"-category panels)
    for gone in ("ALLSET_PT_channel_box", "ALLSET_PT_layer_editor", "ALLSET_PT_dock_attribute_editor",
                 "ALLSET_PT_dock_modeling_toolkit"):
        assert not hasattr(bpy.types, gone), gone
    assert bpy.types.ALLSET_PT_maya_dock.bl_category == "Tool"
    bpy.ops.allset.ae_toggle()
    assert wm.allset_dock == 'ATTRIBUTE_EDITOR'
    bpy.ops.allset.ae_toggle()
    assert wm.allset_dock == 'CHANNEL_BOX'


def _kmis(km_name, key, **mods):
    km = kit.maya_kc().keymaps[km_name]
    return [(k.idname, getattr(k.properties, "action", None)) for k in km.keymap_items
            if k.type == key and k.value == 'PRESS' and k.active
            and k.shift == mods.get("shift", False) and k.ctrl == mods.get("ctrl", False)
            and k.alt == mods.get("alt", False)]


def test_keys():
    assert _kmis("Object Mode", "A", ctrl=True) == [("allset.ae_toggle", None)]
    assert _kmis("Object Mode", "A", ctrl=True, shift=True) == [("object.select_all", 'SELECT')]
    # Select None also clears latent bone selection and releases joint modes.
    assert _kmis("Object Mode", "D", alt=True) == [("allset.select_none", None)]
