"""Real Maya option windows (Maya 2022 fields and defaults),
option boxes as Maya's right-side square, every mapped option box opens something.
GUI: tests/gui/gui_step103_option_windows.py."""

import types
from importlib import import_module

import bpy
from mathutils import Vector

import kit

ow = import_module(kit.MODULE + ".operators.option_windows")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_data = import_module(kit.MODULE + ".ui.menu_data")
editor_menu_data = import_module(kit.MODULE + ".ui.editor_menu_data")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
modal = import_module(kit.MODULE + ".marking.modal")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0   # Maya Workflow Kit template units
    ow.store("poly_cube", None)


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def _size(ob):
    bpy.context.view_layer.update()      # bound_box is the evaluated mesh's
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return Vector([max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]) / 0.01


def _run(key, **values):
    res = ow.run(ow._BY_KEY[key], bpy.context, values)
    assert not isinstance(res, str), (key, res)
    return res


# --- coverage ---------------------------------------------------------------------------------------

def test_every_mapped_option_box_opens_something():
    kinds, bad = {}, []
    for path in menu_data.OPTION_BOXES:
        if path not in menu_map.MAP:
            continue
        kind = menu_sets.option_kind(path)
        kinds.setdefault(kind, []).append(path)
        if kind == "none":
            bad.append(path)
    print({k: len(v) for k, v in kinds.items()})
    assert not bad, bad
    dialogs = {ow.find_path(p).key if ow.find_path(p) else menu_map.spec(p)[1]
               for p in kinds.get("window", []) + kinds.get("dialog", [])}
    print(f"real option dialogs: {len(dialogs)}")
    assert len(dialogs) >= 30, sorted(dialogs)


def test_windows_registered_with_maya_titles_and_buttons():
    assert len(ow.WINDOWS) >= 24
    panels = ("ghosting_editor",)     # Maya's Ghosting Editor is a panel (menu item, no option box)
    for w in ow.WINDOWS:
        if w.key in panels:
            assert getattr(bpy.ops.allset, "opt_" + w.key) and w.action, w.key
            continue
        # Maya option windows end in "Options"; boxes that open Maya Tool Settings carry the tool name;
        # two Render windows carry Maya's own titles; the arc tools'
        # boxes open Maya's Tool Settings "Three / Two Point Arc Settings"
        assert (w.title.endswith(("Options", "Tool", "Arc Settings"))
                or w.title in ("Render Sequence (Current Frame)", "Batch Render Frame")) and w.action, w.key
        rna = getattr(bpy.ops.allset, "opt_" + w.key).get_rna_type()
        for f in w.fields:
            assert f.name in rna.properties, (w.key, f.name)
        for name in ("apply_now", "save_now", "reset_now"):
            assert name in rna.properties
        assert w.paths or w.match, w.key
        for p in w.paths:
            # editor menu bars (Graph Editor / Dope Sheet Edit key windows) have their own boxes
            assert (p in menu_data.OPTION_BOXES or p in editor_menu_data.OPTION_BOXES) and p in menu_map.MAP, (w.key, p)
    # default values, as in Maya
    d = ow._BY_KEY
    assert d["poly_plane"].defaults()["width_div"] == 10 and d["poly_sphere"].defaults()["axis_div"] == 20
    assert d["bevel"].defaults()["width"] == 0.5 and d["merge"].defaults()["threshold"] == 0.01
    assert d["bind_skin_maya"].defaults()["max_influences"] == 5
    assert d["parent_constraint"].defaults()["maintain_offset"] is True
    assert d["point_constraint"].defaults()["maintain_offset"] is False


def test_box_mark_not_a_left_window_icon():
    class Rec:
        def __init__(self):
            self.log = []

        def operator_menu_hold(self, idname, text="", icon='NONE', menu="", **kw):
            props = types.SimpleNamespace()
            self.log.append((idname, text, icon, menu, props))
            return props

        def __getattr__(self, name):
            return lambda *a, **k: None

    rec = Rec()
    menu_sets._draw_boxed(rec, "Create/Polygon Primitives/Cube", "Cube" + menu_sets.BOX_MARK)   # full text
    idname, text, icon, menu, props = rec.log[0]
    assert text == "Cube" + menu_sets.BOX_MARK and icon == 'NONE' and props.item == "Create/Polygon Primitives/Cube"
    assert menu == "ALLSET_MT_option_box"
    assert menu_sets.ALLSET_OT_menu_option_box.description(
        bpy.context, types.SimpleNamespace(item="Create/Polygon Primitives/Cube")) == "Polygon Cube Options"
    tip = menu_sets.ALLSET_OT_menu_item.description(bpy.context, types.SimpleNamespace(item="Mesh/Combine"))
    assert "Press and hold" not in tip, tip


# --- windows run the Maya way ------------------------------------------------------------------------

def test_primitives():
    _clear()
    _run("poly_cube", width=2.0, height=3.0, depth=4.0, width_div=2, height_div=3, depth_div=1)
    ob = bpy.context.active_object
    assert ob.name == "pCube1"
    assert (_size(ob) - Vector((2, 4, 3))).length < 1e-4, _size(ob)     # Maya depth = Blender Y, height = Z
    # 2 x 3 x 1 divisions: faces 2*(2*3 + 2*1 + 3*1) = 22
    assert len(ob.data.polygons) == 22, len(ob.data.polygons)
    _run("poly_sphere", radius=2.0, axis_div=8, height_div=6)
    ob = bpy.context.active_object
    assert abs(_size(ob).z - 4.0) < 1e-3 and len(ob.data.polygons) == 8 * 6, (_size(ob), len(ob.data.polygons))
    _run("poly_cylinder", height=5.0, height_div=4, axis="X")
    ob = bpy.context.active_object
    assert abs(_size(ob).x - 5.0) < 1e-3, _size(ob)                    # Maya axis X: lies along X
    assert len(ob.data.polygons) == 20 * 4 + 2 * 20     # cap divisions 1: two centre fans
    _run("poly_plane", width=3.0, height=2.0, width_div=3, height_div=2)
    ob = bpy.context.active_object
    assert (_size(ob) - Vector((3, 2, 0))).length < 1e-4 and len(ob.data.polygons) == 6


def test_saved_settings_used_by_a_plain_click_and_reset():
    _clear()
    ow.store("poly_cube", {"width": 5.0})
    modal.run_action(bpy.context, menu_map.MAP["Create/Polygon Primitives/Cube"],
                     path="Create/Polygon Primitives/Cube")
    assert abs(_size(bpy.context.active_object).x - 5.0) < 1e-4
    ow.store("poly_cube", None)
    modal.run_action(bpy.context, menu_map.MAP["Create/Polygon Primitives/Cube"],
                     path="Create/Polygon Primitives/Cube")
    assert abs(_size(bpy.context.active_object).x - 1.0) < 1e-4


def test_edit_commands_and_transforms():
    _clear()
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    _select(ob)
    _run("bevel", width=0.5, segments=2)
    assert len(ob.data.vertices) > 8 and bpy.context.mode == 'OBJECT'
    _clear()
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    _select(ob)
    _run("extrude", thickness=2.0, divisions=2)
    # every face of a closed cube, faces kept together: the shell moves out by the thickness (no side faces)
    assert abs(_size(ob).x - 5.0) < 1e-3 and bpy.context.mode == 'OBJECT', _size(ob)
    n0 = len(ob.data.polygons)
    _run("smooth", levels=2)        # real polySmoothFace geometry: every quad -> 4 x 4 quads
    assert len(ob.data.polygons) == 16 * n0 and not any(m.type == 'SUBSURF' for m in ob.modifiers),         (n0, len(ob.data.polygons), [m.type for m in ob.modifiers])
    _run("duplicate_special_maya", copies=3, translate=(2.0, 0.0, 0.0))
    assert len([o for o in bpy.context.scene.objects if o.type == 'MESH']) == 4
    ob.location = (0.05, 0.0, 0.0)
    ob.rotation_euler = (0.3, 0.0, 0.0)
    _select(ob)
    _run("reset", translate=True, rotate=False, scale=True)
    assert ob.location.length < 1e-9 and abs(ob.rotation_euler.x - 0.3) < 1e-6, (tuple(ob.location), tuple(ob.rotation_euler), ob.name, [o.name for o in bpy.context.selected_objects])


def test_combine_pivot_and_merge():
    _clear()
    bpy.ops.allset.create(kind='CUBE')
    a = bpy.context.active_object
    bpy.ops.allset.create(kind='CUBE')
    b = bpy.context.active_object
    b.location = (0.1, 0.0, 0.0)
    _select(a, b)
    _run("combine", pivot="World origin")
    ob = bpy.context.active_object
    assert (ob.matrix_world.translation + ob.delta_location).length < 1e-6 or ob.location.length < 1e-6
    _select(ob)
    _run("merge", threshold=1000.0)
    assert len(ob.data.vertices) < 16


def test_constraint_windows():
    _clear()
    tgt = bpy.data.objects.new("locator1", None)
    drv = bpy.data.objects.new("locator2", None)
    for o in (tgt, drv):
        bpy.context.scene.collection.objects.link(o)
    _select(tgt, drv)
    _run("point_constraint", all=False, x=True, weight=0.5, maintain_offset=True)
    con = drv.constraints[-1]
    assert con.type == 'COPY_LOCATION' and con.use_x and not con.use_y and not con.use_z
    assert abs(con.influence - 0.5) < 1e-6 and con.use_offset
    _select(tgt, drv)
    _run("orient_constraint", all=False, y=True)
    con = drv.constraints[-1]
    assert con.type == 'COPY_ROTATION' and con.use_z and not con.use_x      # Maya Y = Blender Z
    _select(tgt, drv)
    _run("parent_constraint", maintain_offset=False)
    assert drv.constraints[-1].type == 'CHILD_OF'


def test_uv_and_keys():
    _clear()
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    _select(ob)
    _run("uv_planar", fit="Bounding box", project_from="Y axis")
    assert ob.data.uv_layers.active is not None
    _run("uv_automatic", planes="6")
    child = bpy.data.objects.new("child", None)
    bpy.context.scene.collection.objects.link(child)
    child.parent = ob
    _select(ob)
    _run("set_key", hierarchy="Below")
    assert child.animation_data is not None and child.animation_data.action is not None
    _select(ob)
    ob.location = (0.0, 0.0, 0.0)
    _run("bake_simulation", time_range="Start/End", start=1.0, end=3.0)
    assert ob.animation_data.action is not None


def test_apply_save_reset_buttons():
    """Apply / Save Settings / Reset Settings are toggles whose update callbacks act and spring back."""
    _clear()
    w = ow._BY_KEY["poly_cube"]
    holder = types.SimpleNamespace(**w.defaults(), apply_now=True, save_now=False, reset_now=False)
    holder.width = 4.0
    ow._apply_update(w)(holder, bpy.context)
    assert holder.apply_now is False and abs(_size(bpy.context.active_object).x - 4.0) < 1e-4
    assert ow.saved("poly_cube")["width"] == 4.0          # Maya keeps the values of a command that ran
    holder.reset_now = True
    ow._reset_update(w)(holder, bpy.context)
    assert holder.width == 1.0 and ow.saved("poly_cube") is None and holder.reset_now is False
    holder.width, holder.save_now = 2.5, True
    ow._save_update(w)(holder, bpy.context)
    assert ow.saved("poly_cube")["width"] == 2.5
    ow.store("poly_cube", None)
