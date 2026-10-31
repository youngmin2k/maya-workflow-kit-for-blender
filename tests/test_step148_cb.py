"""#87 #85 #83 #95: Channel Box finish.
GUI: tests/gui/gui_step148_cb.py (RMB menu, pane, AE, lattice, light at UI 1.0 / 1.25 / 1.5)."""

from importlib import import_module

import bpy

import kit

cbm = import_module(kit.MODULE + ".ui.channel_box")
ae = import_module(kit.MODULE + ".ui.attribute_editor")
units = import_module(kit.MODULE + ".operators.units")


def _cm_scene():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0     # the Maya Workflow Kit template
    assert abs(units.maya_unit(bpy.context.scene) - 0.01) < 1e-9


def _only(ob):
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob


def test_95_lattice_reads_maya_scale_in_cm():
    # Maya: lattice -dv 2 5 2 -oc on a radius 1 polySphere = Scale 2 2 2
    _cm_scene()
    bpy.ops.allset.create(kind='SPHERE')
    sphere = bpy.context.active_object
    _only(sphere)
    bpy.ops.allset.menu_item('EXEC_DEFAULT', True, item="Deform/Lattice")
    lat = bpy.data.objects["ffd1Lattice"]
    assert all(abs(v - 2.0) < 2e-3 for v in lat.scale), tuple(lat.scale)
    assert all(abs(v - 0.02) < 2e-5 for v in lat.matrix_world.to_scale()), tuple(lat.matrix_world.to_scale())
    # the sphere still deforms with the lattice: a moved lattice point moves the mesh
    me_before = [v.co.copy() for v in sphere.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
    lat.data.points[0].co_deform.x -= 0.5
    lat.data.update_tag()
    bpy.context.view_layer.update()
    me_after = [v.co.copy() for v in sphere.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
    assert any((a - b).length > 1e-6 for a, b in zip(me_before, me_after))


def test_light_shapes_rows_are_maya_color_and_intensity():
    _cm_scene()
    bpy.ops.allset.create(kind='POINT_LIGHT')
    ob = bpy.context.active_object
    _only(ob)
    rows = [(k, n) for k, n, _m, _i in cbm.wanted_rows(ob) if k == "SHAPE"]
    assert [n for _k, n in rows] == ["maya:colorR", "maya:colorG", "maya:colorB", "allset_intensity"], rows
    assert [cbm.shape_label(ob, n) for _k, n in rows] == ["Color R", "Color G", "Color B", "Intensity"]
    owner = cbm.row_owner(ob, "SHAPE", "maya:colorG")
    assert owner == ob.data
    cbm._row_write(owner, "SHAPE", "maya:colorG", 0.25)
    assert abs(ob.data.color[1] - 0.25) < 1e-6
    assert abs(cbm._row_read(owner, "SHAPE", "maya:colorG") - 0.25) < 1e-6
    assert cbm._row_kind(owner, "SHAPE", "maya:colorG") == "NONE"
    # Intensity is Maya's value over Blender's Power
    cbm._row_write(owner, "SHAPE", "allset_intensity", 2.0)
    assert abs(ob.data.allset_intensity - 2.0) < 1e-4


def test_83_pane_room_model():
    # screenshots: 4.8-4.9 U of fixed rows at UI 1.0 / 1.25 / 1.5 (menu bar + name line + margins + splitter)
    assert abs((cbm.PANE_TOP + 3.0 + 0.3) - 4.9) < 1e-6


class _Rec:
    def __init__(self):
        self.props = []

    def column(self, **_k):
        return self

    def split(self, **_k):
        return self

    def row(self, **_k):
        return self

    def label(self, **_k):
        pass

    def prop(self, owner, name, **_k):
        self.props.append((type(owner).__name__, name))


def test_85_ae_transform_rows_are_maya_numbers():
    _cm_scene()
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    _only(ob)
    ob.location.x = 0.62
    rec = _Rec()
    ae.draw_transform_channels(rec, bpy.context, ob)
    assert [n for _o, n in rec.props] == [k + "_text" for k in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz")]
    assert bpy.context.scene.allset_cb.tx_text == "62"          # no unit, never "62 c"
    # a second selected node: the AE shows its own node's fields (the proxies type into every selected node)
    bpy.ops.allset.create(kind='CUBE')
    other = bpy.context.active_object
    ob.select_set(True)
    rec = _Rec()
    ae.draw_transform_channels(rec, bpy.context, ob)
    assert [n for _o, n in rec.props] == ["location", "rotation_euler", "scale"], rec.props
    assert other is not ob


def test_87_rmb_takes_channel_box_cells():
    # Blender's button context menu draws a Python menu only after its own C rows: the Channel Box modal takes RMB
    assert hasattr(cbm.ALLSET_OT_cb_channel_drag, "_on_rmb")
    assert hasattr(bpy.types, "ALLSET_MT_cb_channels")
