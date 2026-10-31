"""Issue #204: Maya's Channel Box INPUTS list the mesh's history nodes in object mode too, newest first —
polyBevel / polyExtrudeFace / polySmoothFace / blendShape — each with its editable attributes. The kit's
"last operation" nodes (operators/extrude.py records) show there in object mode while the mesh is still the result
the kit made; Mesh > Smooth (menu, hotbox, shelf) leaves an editable polySmoothFace node; a blend shape is a
blendShape node with Envelope and one weight row per target."""

from importlib import import_module
from types import SimpleNamespace

import bmesh
import bpy

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")
in_view = import_module(kit.MODULE + ".ui.in_view")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
modal = import_module(kit.MODULE + ".marking.modal")
extrude = import_module(kit.MODULE + ".operators.extrude")


class Recorder:
    """A stand-in UILayout recording labels / operators / props."""

    def __init__(self, log=None):
        self.log = [] if log is None else log

    def __getattr__(self, name):
        if name in ("row", "column", "split", "box", "column_flow", "grid_flow"):
            return lambda *a, **k: Recorder(self.log)
        if name in ("menu", "operator", "prop", "label", "popover"):
            def add(*args, **kw):
                props = SimpleNamespace()
                text = kw.get("text")
                if text is None:
                    text = args[0] if args and isinstance(args[0], str) else (args[1] if len(args) > 1 else "")
                self.log.append((name, text, args, props))
                return props
            return add
        return lambda *a, **k: None

    def __setattr__(self, name, value):
        if name == "log":
            object.__setattr__(self, name, value)

    def texts(self, kind):
        return [t for k, t, _a, _p in self.log if k == kind]

    def nodes(self):
        """INPUTS node names in drawing order."""
        return [t for k, t, a, _p in self.log if k == "operator" and a[:1] == (cb.ALLSET_OT_cb_node_toggle.bl_idname,)]


def _draw():
    rec = Recorder()
    cb.ALLSET_PT_channel_box.body(rec, bpy.context)
    return rec


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    cb.reset_open()
    extrude.clear()
    scene = bpy.context.scene
    for k in [k for k in scene.keys() if k.startswith("allset_poly")]:
        del scene[k]                     # Maya numbers history nodes per scene


def _pick(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    cb.rebuild_rows()


def _cube():
    assert bpy.ops.allset.create(kind='CUBE') == {'FINISHED'}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    ob = bpy.context.view_layer.objects.active
    _pick(ob)
    return ob


def _counts(ob):
    if ob.mode == 'EDIT':
        ob.update_from_editmode()
    me = ob.data
    return len(me.vertices), len(me.polygons)


def _hist():
    return bpy.context.window_manager.allset_history


# --- Bevel ------------------------------------------------------------------------------------------------------------

def test_object_mode_bevel_lists_poly_bevel_newest_first_and_stays_editable():
    """Maya: Edit Mesh > Bevel on an object selection = polyBevel1 above polyCube1 in INPUTS (object mode)."""
    _fresh()
    ob = _cube()
    assert bpy.ops.allset.menu_item(item="Edit Mesh/Bevel") == {'FINISHED'}
    assert bpy.context.mode == 'OBJECT'
    rec = in_view.cb_record(bpy.context, ob)
    assert rec is not None and rec.name == "polyBevel1", rec
    nodes = _draw().nodes()
    # newest first (the kit's creation node is only listed while the mesh is the bare primitive)
    assert nodes[:1] == ["polyBevel1"], nodes
    # typed in the Channel Box from object mode: the bevel is rebuilt, still object mode, same node
    hist = _hist()
    assert hist.segments_text == "1", hist.segments_text
    n1 = _counts(ob)
    bpy.ops.ed.undo_push(message="before segments")
    hist.segments_text = "3"
    assert bpy.context.mode == 'OBJECT' and ob.select_get()
    n3 = _counts(ob)
    assert n3[0] > n1[0], (n1, n3)
    rec = in_view.cb_record(bpy.context, ob)
    assert rec is not None and rec.name == "polyBevel1" and rec.params["segments"] == 3, rec and rec.params
    assert hist.segments_text == "3"
    # one undo step: back to segments 1 (the record follows the mesh)
    bpy.ops.ed.undo()
    ob = bpy.context.view_layer.objects.active
    assert _counts(ob) == n1, (_counts(ob), n1)
    rec = in_view.cb_record(bpy.context, ob)
    assert rec is not None and rec.params["segments"] == 1, rec and rec.params


def test_record_hides_when_the_mesh_changes_in_object_mode():
    _fresh()
    ob = _cube()
    assert bpy.ops.allset.menu_item(item="Edit Mesh/Bevel") == {'FINISHED'}
    assert in_view.cb_record(bpy.context, ob) is not None
    ob.data.vertices[0].co.x += 0.5               # another edit: no longer the node's result (kit history rule)
    ob.data.update()
    assert in_view.cb_record(bpy.context, ob) is None
    assert "polyBevel1" not in _draw().nodes()
    assert _hist().segments_text == ""


def test_edit_mode_bevel_still_listed_after_tab_out():
    _fresh()
    ob = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select = False
    bm.edges.ensure_lookup_table()
    bm.edges[0].select = True
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.bevel() == {'FINISHED'}
    assert in_view.cb_record(bpy.context, ob).name == "polyBevel1"
    bpy.ops.object.mode_set(mode='OBJECT')
    rec = in_view.cb_record(bpy.context, ob)
    assert rec is not None and rec.name == "polyBevel1", rec
    before = _counts(ob)
    _hist().segments_text = "2"
    assert bpy.context.mode == 'OBJECT'
    assert _counts(ob)[0] == before[0] + 2, (before, _counts(ob))
    # the AE history tab follows the same record
    ae = import_module(kit.MODULE + ".ui.attribute_editor")
    assert ae.history_record(ob) is not None


# --- Extrude ----------------------------------------------------------------------------------------------------------

def test_extrude_listed_and_editable_in_object_mode():
    _fresh()
    ob = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    top = max(bm.faces, key=lambda f: f.calc_center_median().z)
    for f in bm.faces:
        f.select = f is top
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.extrude() == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    rec = in_view.cb_record(bpy.context, ob)
    assert rec is not None and rec.name == "polyExtrudeFace1", rec
    assert _draw().nodes()[:1] == ["polyExtrudeFace1"]
    _hist().local_translate_z_text = "0.5"
    assert bpy.context.mode == 'OBJECT'
    unit = extrude.units.maya_unit(bpy.context.scene)
    zmax = max(v.co.z for v in ob.data.vertices)
    assert abs(zmax - 1.0 * unit) < 1e-5, (zmax, unit)
    _hist().divisions_text = "2"
    assert _counts(ob) == (16, 14), _counts(ob)


# --- Smooth -----------------------------------------------------------------------------------------------------------

def test_menu_smooth_leaves_an_editable_poly_smooth_face_node():
    """Maya Mesh > Smooth (main menu / hotbox) = polySmoothFace1, Divisions in INPUTS."""
    _fresh()
    ob = _cube()
    assert bpy.ops.allset.menu_item(item="Mesh/Smooth") == {'FINISHED'}
    assert _counts(ob) == (26, 24) and not ob.modifiers
    rec = in_view.cb_record(bpy.context, ob)
    assert rec is not None and rec.name == "polySmoothFace1" and rec.spec.node_type == "polySmoothFace", rec
    assert _draw().nodes()[:1] == ["polySmoothFace1"]
    assert _hist().divisions_text == "1"
    _hist().divisions_text = "2"
    assert _counts(ob) == (98, 96), _counts(ob)
    assert bpy.context.mode == 'OBJECT'
    assert in_view.cb_record(bpy.context, ob).params["divisions"] == 2


def test_shelf_smooth_is_the_menu_item():
    """Maya's shelf Smooth runs the same command as Mesh > Smooth: the same polySmoothFace node."""
    assert shelf_map.BY_COMMAND["SmoothPolygon"][0] == ("item", "Mesh/Smooth")
    _fresh()
    ob = _cube()
    modal.run_action(bpy.context, shelf_map.BY_COMMAND["SmoothPolygon"][0])
    assert _counts(ob) == (26, 24) and not ob.modifiers, (_counts(ob), list(ob.modifiers))
    rec = in_view.cb_record(bpy.context, ob)
    assert rec is not None and rec.name.startswith("polySmoothFace"), rec


def test_edit_mode_smooth_is_recorded():
    _fresh()
    ob = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='SELECT')
    assert bpy.ops.allset.smooth() == {'FINISHED'}
    rec = in_view.cb_record(bpy.context, ob)
    assert rec is not None and rec.spec.node == "polySmoothFace", rec
    _hist().divisions_text = "2"
    assert _counts(ob) == (98, 96), _counts(ob)
    bpy.ops.object.mode_set(mode='OBJECT')
    assert in_view.cb_record(bpy.context, ob) is not None


# --- Blend Shape ------------------------------------------------------------------------------------------------------

def test_blend_shape_node_in_inputs():
    """Maya: blendShape1 in the base's INPUTS; expanded: Envelope, then one weight per target (named after it)."""
    _fresh()
    target = _cube()
    target.name = "pCube2"
    base = _cube()
    base.name = "pCube1"
    target.select_set(True)
    base.select_set(True)
    bpy.context.view_layer.objects.active = base
    assert bpy.ops.allset.blend_shape() == {'FINISHED'}
    _pick(base)
    key = base.data.shape_keys
    assert key is not None and key.name == "blendShape1"
    nodes = _draw().nodes()
    assert "blendShape1" in nodes, nodes
    if "polyCube1" in nodes:
        assert nodes.index("blendShape1") < nodes.index("polyCube1"), nodes
    cb.set_open(base, cb.blend_shape_node(key))
    rec = _draw()
    labels = rec.texts("label")
    assert "Envelope" in labels, labels
    i = labels.index("Envelope")
    assert "pCube2" in labels[i:], labels
    props = [a for k, _t, a, _p in rec.log if k == "prop" and a[:1] and isinstance(a[0], bpy.types.ShapeKey)]
    assert any(a[0].name == "pCube2" and a[1] == "value" for a in props), props
