"""Hypershade window, Light Editor (an Outliner of the lights), Render menu, Render View Keep Image, AE map buttons, standardSurface
names. GUI: tests/gui/gui_step67_render.py."""

import types
from importlib import import_module

import bpy

import kit

menu_data = import_module(kit.MODULE + ".ui.menu_data")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
editor_menu_map = import_module(kit.MODULE + ".ui.editor_menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
notices = import_module(kit.MODULE + ".ui.notices")
ae_layout = import_module(kit.MODULE + ".ui.ae_layout")
ae = import_module(kit.MODULE + ".ui.attribute_editor")
hs = import_module(kit.MODULE + ".ui.hypershade")
rv = import_module(kit.MODULE + ".ui.render_view")
maps = import_module(kit.MODULE + ".operators.shading_maps")
material = import_module(kit.MODULE + ".operators.material")
status_line = import_module(kit.MODULE + ".ui.status_line")


class Rec:
    """Records every layout call (any method), returns itself so nested layouts record too."""

    def __init__(self, log=None):
        self.log = [] if log is None else log

    def __getattr__(self, name):
        def call(*args, **kw):
            self.log.append((name, args, kw))
            if name == "panel":
                return Rec(self.log), Rec(self.log)
            if name in ("operator", "operator_menu_enum"):
                props = types.SimpleNamespace()
                self.log[-1] = (name, args, kw, props)
                return props
            return Rec(self.log)
        return call

    def __setattr__(self, name, value):
        if name == "log":
            object.__setattr__(self, name, value)

    def ops(self):
        return [(e[1][0], e[3]) for e in self.log if e[0] == "operator"]


def swatches(rec):
    """Materials of the Browser swatch buttons a draw made (``Material.allset_hs_pick`` toggles)."""
    return {e[1][0].name for e in rec.log if e[0] == "prop" and e[1][1:2] == ("allset_hs_pick",)}


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)


def _sphere():
    bpy.ops.mesh.primitive_uv_sphere_add()
    return bpy.context.active_object


# --- Render menu -------------------------------------------------------------------------------

def test_render_menu_restored():
    items = [i[0] for i in menu_data.MENUS["mainRenderMenu"][3]]
    want = ["Render Settings...", "Render Using", "Render Current Frame", "Redo Previous Render",
            "IPR Render Current Frame", "Render Sequence", "Batch Render"]
    pos = [items.index(w) for w in want]
    assert pos == sorted(pos), items
    assert len(items) > 15, items
    assert menu_map.MAP["Render/Render Current Frame"] == "render.render"
    assert menu_map.MAP["Render/Render Sequence"] == ("render.render", {"animation": True})
    assert menu_map.MAP["Render/IPR Render Current Frame"] == "allset.ipr_toggle"
    assert menu_map.MAP["Render/Render Using"] == ("menu", "ALLSET_MT_render_using")
    paths = {p for p, _it in menu_sets.iter_items()}
    for path in ("Render/Render Current Frame", "Render/Batch Render", "Render/Render Using"):
        assert path in paths, path
    assert "blender -b" in notices.NOTICES["Render/Batch Render"][1]
    assert menu_map.MAP["Render/Batch Render"] == ("render.render", {"animation": True})
    assert "Render/Cancel Batch Render" not in menu_map.MAP and "Blender" in notices.NOTICES[
        "Render/Cancel Batch Render"][1]
    # the Render Using menu lists the engines
    rec = Rec()
    rv.ALLSET_MT_render_using.draw(types.SimpleNamespace(layout=rec), bpy.context)
    assert rec.log[0][0] == "props_enum" and rec.log[0][1][1] == "engine"


def test_windows_menu_and_status_line_share_operators():
    assert menu_map.MAP["Windows/Rendering Editors/Hypershade"] == "allset.hypershade"
    assert menu_map.MAP["Windows/Rendering Editors/Light Editor"] == "allset.light_editor"
    assert not hasattr(status_line, "ALLSET_OT_hypershade"), "one Hypershade operator (ui/hypershade.py)"
    for op in (bpy.ops.allset.hypershade, bpy.ops.allset.light_editor):
        op.get_rna_type()
    assert "Outliner" in notices.NOTICES["Windows/Rendering Editors/Light Editor"][0]


# --- names / aiStandardSurface ----------------------------------------------------------------------

def test_standard_surface_name_table():
    probe = bpy.data.materials.new("probe")
    probe.use_nodes = True
    sockets = {s.name for s in ae.principled(probe).inputs}
    bpy.data.materials.remove(probe)
    table = dict(ae_layout.STANDARD_SURFACE_ATTRS)
    assert len(table) >= 30
    missing = [(a, s) for a, s in table.items() if s and s not in sockets]
    assert not missing, missing
    assert table["baseColor"] == "Base Color" and table["specularRoughness"] == "Roughness"
    assert table["thinWalled"] is None
    used = {row[1] for _d, sec in ae_layout.walk(ae_layout.STANDARD_SURFACE) for row in sec.rows if row[0] == "socket"}
    assert used <= set(ae_layout.MAYA_ATTR), used - set(ae_layout.MAYA_ATTR)
    rows = [row for _d, sec in ae_layout.walk(ae_layout.STANDARD_SURFACE) for row in sec.rows]
    assert ("missing", "Thin Walled") == rows[-1][:2]


def test_ai_standard_surface_kind():
    _clear()
    mat = material.new_material('AI_STANDARD_SURFACE')
    assert mat.name == "aiStandardSurface1", mat.name
    assert ae.material_type(mat) == "aiStandardSurface"
    assert ae_layout.BY_KIND["aiStandardSurface"][0] is ae_layout.STANDARD_SURFACE


# --- AE map buttons -----------------------------------------------------------------------------------

def test_map_button_drawn_on_socket_rows():
    _clear()
    ob = _sphere()
    mat = material.new_material('STANDARD_SURFACE')
    material.assign_object(ob, mat)
    rec = Rec()
    ae.draw_sections(rec, bpy.context, ob, mat, ae_layout.STANDARD_SURFACE, "t")
    maps_ = [p for idname, p in rec.ops() if idname == "allset.ae_map"]
    sockets = [p.socket for p in maps_]
    assert "Base Color" in sockets and "Roughness" in sockets, sockets
    assert all(p.material == mat.name for p in maps_)
    labels = [e[2].get("text", "") for e in rec.log if e[0] == "label"]
    assert any(t.startswith("Thin Walled:") for t in labels), labels
    tip = maps.ALLSET_OT_ae_map.description(bpy.context, types.SimpleNamespace(socket="Base Color"))
    assert tip.startswith("baseColor"), tip


def test_map_connect_each_kind():
    _clear()
    mat = material.new_material('STANDARD_SURFACE')
    node = maps.principled(mat)
    for kind, socket, want in (('FILE', "Base Color", 'TEX_IMAGE'), ('RAMP', "Specular Tint", 'VALTORGB'),
                               ('NOISE', "Roughness", 'TEX_NOISE'), ('CHECKER', "Coat Tint", 'TEX_CHECKER'),
                               ('NOISE', "Normal", 'BUMP')):
        assert bpy.ops.allset.ae_map_connect(material=mat.name, socket=socket, kind=kind) == {'FINISHED'}
        inp = node.inputs[socket]
        assert inp.is_linked and inp.links[0].from_node.type == want, (kind, socket, inp.links[0].from_node.type)
    ramp = node.inputs["Specular Tint"].links[0].from_node
    assert [tuple(round(c, 3) for c in e.color[:3]) for e in ramp.color_ramp.elements] == [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    assert ramp.inputs["Fac"].links[0].from_socket.name == "Y", "Maya ramp runs along V"
    bump = node.inputs["Normal"].links[0].from_node
    assert bump.inputs["Height"].links[0].from_node.type == 'TEX_NOISE', "Maya bump2d"
    count = len(mat.node_tree.nodes)
    assert bpy.ops.allset.ae_map_break(material=mat.name, socket="Base Color") == {'FINISHED'}
    assert not node.inputs["Base Color"].is_linked and len(mat.node_tree.nodes) == count, "Maya keeps the nodes"
    # the connected row shows the node and, for a file texture, the image picker
    material.assign_object(_sphere(), mat)
    bpy.ops.allset.ae_map_connect(material=mat.name, socket="Base Color", kind='FILE')
    rec = Rec()
    ae.draw_sections(rec, bpy.context, bpy.context.active_object, mat, ae_layout.STANDARD_SURFACE, "t")
    labels = [e[2].get("text", "") for e in rec.log if e[0] == "label"]
    assert any(t.startswith("Color: connected (") for t in labels), labels
    assert any(e[0] == "template_ID" and e[1][1] == "image" for e in rec.log)


# --- Hypershade -----------------------------------------------------------------------------------------

def _node_space():
    area = bpy.context.window_manager.windows[0].screen.areas[0]
    old = area.ui_type
    area.ui_type = 'ShaderNodeTree'
    return area, old


def test_hypershade_browser_create_assign():
    _clear()
    ob = _sphere()
    wm = bpy.context.window_manager
    wm.allset_hs_material = ""
    area, old = _node_space()
    space = area.spaces.active
    try:
        # Create = a material, unassigned, kept on save (fake user), current in the Hypershade
        with bpy.context.temp_override(area=area, space_data=space):
            assert bpy.ops.allset.hs_create(kind='STANDARD_SURFACE') == {'FINISHED'}
        mat = bpy.data.materials["standardSurface1"]
        assert mat.use_fake_user and mat.users == 1 and ob.active_material is not mat   # (ob has lambert1)
        assert hs.current(bpy.context) == mat and wm.allset_hs_material == mat.name
        assert space.pin and space.node_tree == mat.node_tree, "not on the object: the graph is pinned to it"
        # Assign Material To Selection
        assert bpy.ops.allset.assign_material(material=mat.name) == {'FINISHED'}
        assert ob.material_slots[0].material == mat
        # picking a material the object has = its slot, the graph follows the object again
        other = material.new_material('LAMBERT')
        with bpy.context.temp_override(area=area, space_data=space):
            bpy.ops.allset.hs_pick(material=other.name)
        assert space.pin and space.node_tree == other.node_tree
        with bpy.context.temp_override(area=area, space_data=space):
            bpy.ops.allset.hs_pick(material=mat.name)
        assert not space.pin and ob.active_material == mat
        # panels draw: browser buttons for every material, Create kinds, Property Editor = AE material sections
        rec = Rec()
        hs.draw_browser(rec, bpy.context)
        assert swatches(rec) == {mat.name, other.name, "lambert1"}
        rec = Rec()
        wm.allset_hs_create_cat = 'SURFACE'          # Create pane = Maya's category tree + node list
        hs.draw_create(rec, bpy.context)
        made = [p.item.rsplit("/", 1)[-1] for i, p in rec.ops() if i == "allset.menu_item"]
        # + the Maya materials Blender builds from other nodes (hair, USD Preview, Shading Map)
        extra = [label.rsplit("/", 1)[-1] for label in editor_menu_map.HS_EXTRA if label.startswith("Materials/")]
        assert made == sorted([material.MATERIALS[k][1] for k in hs.CREATE] + extra), made
        wm.allset_hs_create_cat = 'MAYA'
        rec = Rec()
        hs.draw_property_editor(rec, bpy.context)
        assert any(i == "allset.ae_map" for i, _p in rec.ops())
    finally:
        area.ui_type = old


# --- Render View Keep Image -----------------------------------------------------------------------------

def test_keep_image_render_slots():
    sc = bpy.context.scene
    if sc.camera is None:
        cam = bpy.data.objects.new("camera1", bpy.data.cameras.new("camera1"))
        sc.collection.objects.link(cam)
        sc.camera = cam
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 32, 18, 100
    bpy.ops.render.render()
    image = rv.render_result()
    assert image is not None
    slots = image.render_slots
    slots.active_index = 0
    image[rv.KEPT_PROP] = []
    assert bpy.ops.allset.render_keep_image() == {'FINISHED'}
    assert rv.kept(image) == {0} and slots.active_index == 1, "next render goes to slot 2"
    bpy.ops.render.render()
    assert slots.active_index == 1
    # all slots kept -> a new one
    for _ in range(len(slots) - 1):
        rv.keep(image)
    assert len(slots) == 9 and slots.active_index == 8
    # Remove Image forgets the shown slot
    slots.active_index = 3
    assert rv.remove(image) == 3 and 3 not in rv.kept(image)
    # header buttons only for Render Result
    rec = Rec()
    rv.draw_header(rec, types.SimpleNamespace(space_data=types.SimpleNamespace(image=image)))
    assert [i for i, _p in rec.ops()] == ["render.render", "allset.render_keep_image",
                                      "allset.render_remove_image"]
    rec = Rec()
    rv.draw_header(rec, types.SimpleNamespace(space_data=types.SimpleNamespace(image=None)))
    assert not rec.log


def test_light_decay_rate_row():
    for kind in ("POINT", "SPOT", "AREA"):
        rows = [row for _d, sec in ae_layout.walk(ae_layout.BY_KIND[kind][0]) for row in sec.rows]
        # a real Decay Rate row (Light.allset_decay, operators/lights.py)
        assert ("draw", "light_decay") in rows, kind
    rows = [row for _d, sec in ae_layout.walk(ae_layout.BY_KIND["SUN"][0]) for row in sec.rows]
    assert ("draw", "light_decay") not in rows, "directional lights have no decay"

