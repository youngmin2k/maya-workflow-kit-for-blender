"""#152: Maya's messages on wrong selections instead of Python errors or silence.

Maya's messages + the step-258 additions (constraints with one
object, Set Blend Shape Target Weight Keys on a skeleton, nothing selected for Remesh / Reduce). Maya's Errors are the
kit's ERROR reports: a menu item called from Python raises ``RuntimeError("Error: <Maya text>")`` (no traceback).
Cases where Maya works silently must work without an error.
"""

from importlib import import_module

import bpy

import kit

maya_errors = import_module(kit.MODULE + ".operators.maya_errors")
menu_map = import_module(kit.MODULE + ".ui.menu_map")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.curves, bpy.data.hair_curves, bpy.data.actions):
        for d in list(coll):
            coll.remove(d)
    bpy.context.scene.allset_live = None


def _cube(name="pCube1", loc=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    return ob


def _skeleton():
    data = bpy.data.armatures.new("skeleton1")
    arm = bpy.data.objects.new("joint1", data)
    bpy.context.scene.collection.objects.link(arm)
    _select(arm)
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for i in range(3):
        b = data.edit_bones.new(f"joint{i + 1}")
        b.head, b.tail = (0, 0, 2.0 * i), (0, 0, 2.0 * i + 2.0)
        if prev is not None:
            b.parent, b.use_connect = prev, True
        prev = b
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm


def _select(*obs, active=None):
    for o in bpy.context.scene.objects:
        try:
            o.select_set(o in obs)
        except RuntimeError:
            pass
    bpy.context.view_layer.objects.active = active or (obs[-1] if obs else None)


def _hide(ob):
    """Maya Ctrl+H (allset.visibility HIDE) on ``ob``; it stays the active object like in the QA repro."""
    _select(ob)
    bpy.ops.allset.visibility(action='HIDE')
    assert ob.hide_viewport
    bpy.context.view_layer.objects.active = ob


def _run(item):
    """Run a Maya menu item like the menu does; returns the Error text it reported (None = no error). A Python
    traceback fails the test."""
    try:
        bpy.ops.allset.menu_item(item=item)
    except RuntimeError as ex:
        text = str(ex).strip()
        assert "Traceback" not in text and "Python" not in text, text
        assert text.startswith("Error: "), text
        return text[len("Error: "):]
    return None


# --- Deform > Cluster on a scale-0 object: Maya makes cluster1 silently -----------------------------------------------

def test_cluster_on_zero_scale_object_works():
    _clear()
    cube = _cube()
    cube.scale = (1.0, 0.0, 1.0)
    _select(cube)
    assert _run("Deform/Cluster") is None
    assert "cluster1" in cube.modifiers, [m.name for m in cube.modifiers]
    assert cube.modifiers["cluster1"].type == 'HOOK'
    assert "cluster1Handle" in bpy.data.objects


# --- Mesh > Remesh / Reduce / Conform with a joint -------------------------------------------------------------------

def test_remesh_and_reduce_with_joint_are_mayas_error():
    _clear()
    arm = _skeleton()
    for item in ("Mesh/Remesh", "Mesh/Reduce"):
        _select(arm)
        assert _run(item) == "Current selection doesn't match required selection type.", item
        assert not arm.modifiers


def test_remesh_and_reduce_with_nothing_selected():
    _clear()
    cube = _cube()
    _select(active=cube)
    cube.select_set(False)
    assert _run("Mesh/Remesh") == \
        "This command requires at least 1 argument(s) to be specified or selected;  found 0."
    assert _run("Mesh/Reduce") == "Reduce requires that at least 1 object or group of faces be selected."
    assert not cube.modifiers


def test_remesh_on_a_mesh_still_works():
    _clear()
    cube = _cube()
    _select(cube)
    assert _run("Mesh/Remesh") is None
    assert [m.type for m in cube.modifiers] == ['REMESH']


def test_conform_needs_a_live_surface():
    _clear()
    arm = _skeleton()
    _select(arm)
    assert _run("Mesh/Conform") == "A live surface is required for conform."
    cube = _cube()
    _select(cube)
    assert _run("Mesh/Conform") == "A live surface is required for conform."
    assert not cube.modifiers
    live = _cube("pPlane1", (0, 0, -3))
    bpy.context.scene.allset_live = live
    _select(active=cube)
    cube.select_set(False)
    assert _run("Mesh/Conform") == "No components or objects selected for conform."


def test_other_modifier_items_with_a_joint_warn_without_traceback():
    _clear()
    arm = _skeleton()
    _select(arm)
    assert _run("Mesh/Triangulate") is None       # kit warning (no Maya text), no TypeError
    assert not arm.modifiers


# --- nHair > Paint Hair Follicles with a mesh: valid, like Maya ------------------------------------------------------

def test_paint_hair_follicles_on_a_mesh_enters_hair_sculpt():
    _clear()
    cube = _cube()
    _select(cube)
    assert _run("nHair/Paint Hair Follicles") is None
    hair = bpy.context.active_object
    assert hair.type == 'CURVES' and hair.data.surface is cube, hair
    assert hair.mode == 'SCULPT_CURVES'
    bpy.ops.object.mode_set(mode='OBJECT')
    _select(cube)
    assert _run("nHair/Paint Hair Follicles") is None     # again: the same hair object, no second one
    assert sum(1 for o in bpy.context.scene.objects if o.type == 'CURVES') == 1
    bpy.ops.object.mode_set(mode='OBJECT')


def test_paint_hair_follicles_with_a_joint_says_so():
    _clear()
    arm = _skeleton()
    _select(arm)
    assert _run("nHair/Paint Hair Follicles") is None      # kit warning, no TypeError
    assert bpy.context.mode == 'OBJECT'


# --- hidden active object: Maya works silently ------------------------------------------------------------------------

def test_smooth_tool_on_hidden_object_does_not_raise():
    _clear()
    cube = _cube()
    _hide(cube)
    assert _run("Mesh Tools/Sculpting Tools/Smooth Tool") is None    # kit warning
    assert bpy.context.mode == 'OBJECT' and cube.hide_viewport


def test_convert_to_faces_on_hidden_object_works_silently():
    _clear()
    cube = _cube()
    bpy.context.scene.tool_settings.mesh_select_mode = (True, False, False)
    _hide(cube)
    assert _run("UV Editor/Select/Convert Selection/To Faces") is None
    assert tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (False, False, True)
    assert cube.hide_viewport


def test_all_components_on_hidden_object_works_silently():
    _clear()
    cube = _cube()
    _hide(cube)
    bpy.context.scene.tool_settings.mesh_select_mode = (True, False, False)
    assert bpy.ops.allset.component_mask(kind='ALL') == {'FINISHED'}
    assert tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (True, True, True)


def test_closest_point_on_hidden_object_works():
    _clear()
    target = _cube("pSphere1", (3, 0, 0))
    cube = _cube()
    _hide(cube)
    target.select_set(True)
    bpy.context.view_layer.objects.active = cube
    assert _run("Constrain/Closest Point") is None
    assert [c.type for c in cube.constraints] == ['SHRINKWRAP']
    assert cube.constraints[0].target is target


# --- Skin > Bind Skin without a joint ---------------------------------------------------------------------------------

def test_bind_skin_without_a_joint_is_mayas_error():
    _clear()
    _skeleton()
    handle = bpy.data.objects.new("ikHandle1", None)
    bpy.context.scene.collection.objects.link(handle)
    _select(handle)
    assert _run("Skin/Bind Skin") == "You must select at least one joint."
    data = bpy.data.curves.new("curveShape1", 'CURVE')
    data.splines.new('NURBS').points.add(3)
    curve = bpy.data.objects.new("curve1", data)
    bpy.context.scene.collection.objects.link(curve)
    _select(curve)
    assert _run("Skin/Bind Skin") == "You must select at least one joint."


def test_bind_skin_nothing_selected_and_joints_only_are_mayas_errors():
    # independent check: nothing selected / only the skeleton
    _clear()
    arm = _skeleton()
    _cube()
    _select()
    assert _run("Skin/Bind Skin") == "Select objects to bind."
    _select(arm if arm is not None else bpy.data.objects["joint1"])
    assert _run("Skin/Bind Skin") == "Bindable objects must be part of the selection."


# --- Constrain with one object ----------------------------------------------------------------------------------------

def test_constraints_with_one_object_are_mayas_error():
    _clear()
    cube = _cube()
    for item in ("Constrain/Parent", "Constrain/Point", "Constrain/Orient", "Constrain/Scale", "Constrain/Aim",
                 "Constrain/Geometry"):
        _select(cube)
        assert _run(item) == "Target list was empty or contained no valid targets.", item
    assert not cube.constraints


# --- Key menu on a plain skeleton -------------------------------------------------------------------------------------

def test_hold_current_keys_on_plain_skeleton_says_nothing():
    _clear()
    arm = _skeleton()
    _select(arm)
    assert _run("Key/Hold Current Keys") is None          # Maya: setKeyframe -insert keys nothing, prints nothing
    assert arm.animation_data is None or not kit.fcurves(arm)


def test_move_ik_to_fk_on_plain_skeleton_is_mayas_error():
    _clear()
    arm = _skeleton()
    _select(arm)
    assert _run("Key/IK/FK Keys/Move IK to FK") == \
        "Must select an ik handle, joint or object that connected to IK/FK."


def test_blend_shape_weight_keys_on_plain_skeleton_is_mayas_error():
    _clear()
    arm = _skeleton()
    _select(arm)
    assert _run("Key/Set Blend Shape Target Weight Keys") == "No shape was selected."


def test_menu_item_reports_nested_errors_as_errors():
    """``report_nested``: an Error stays an Error, anything else a Warning with its last line."""
    class Op:
        def __init__(self):
            self.got = []

        def report(self, kind, text):
            self.got.append((set(kind), text))
    op = Op()
    maya_errors.report_nested(op, maya_errors.MayaError("A live surface is required for conform."))
    maya_errors.report_nested(op, RuntimeError("Error: Python: Traceback (most recent call last):\n  x\nValueError: v"))
    maya_errors.report_nested(op, RuntimeError("Some warning"))
    assert op.got == [({'ERROR'}, "A live surface is required for conform."), ({'WARNING'}, "ValueError: v"),
                      ({'WARNING'}, "Some warning")], op.got
    assert menu_map.MAP["nHair/Paint Hair Follicles"] == "allset.paint_hair_follicles"
