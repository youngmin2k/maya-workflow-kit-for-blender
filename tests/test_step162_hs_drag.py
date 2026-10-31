"""Maya Hypershade swatch MMB drag onto an object = assign (ui/hs_drag.py). Headless: the window / view-ray /
ray-cast target lookup, the assignment path (operators/material.assign: whole object, or the selected faces of a
mesh edited in face mode), the swatch button property and the keymap item. Real drag across windows:
tests/gui/gui_step162_hs_drag.py."""

from importlib import import_module

import bmesh
import bpy
from mathutils import Matrix, Vector

import kit

drag = import_module(kit.MODULE + ".ui.hs_drag")
hs = import_module(kit.MODULE + ".ui.hypershade")
material = import_module(kit.MODULE + ".operators.material")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)


def _cube(name="pCube1", location=(0, 0, 0)):
    me = bpy.data.meshes.new(name + "Shape")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = location
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    return ob


def test_screen_point_and_window_under():
    assert drag.screen_point((643, 153), (-145, 307)) == (498, 460)
    rects = [("main", 0, 60, 1600, 900), ("hs", 643, 153, 667, 679)]
    assert drag.window_under(rects, (498, 460)) == "main", "only the main window there"
    assert drag.window_under(rects, (700, 300), own="hs") == "hs", "overlap: the window the drag started in is in front"
    assert drag.window_under(rects, (700, 300)) == "main", "overlap, no own window: window-manager order"
    assert drag.window_under(rects, (1700, 300)) is None
    assert drag.window_under(rects, (1600, 300)) is None, "right edge is outside"


def _persp(eye, target, width, height, lens_deg=40.0):
    """A perspective matrix (projection @ view) like RegionView3D.perspective_matrix."""
    import math
    f = 1.0 / math.tan(math.radians(lens_deg) / 2)
    aspect = width / height
    n, fa = 0.1, 1000.0
    proj = Matrix(((f / aspect, 0, 0, 0), (0, f, 0, 0), (0, 0, (fa + n) / (n - fa), 2 * fa * n / (n - fa)),
                   (0, 0, -1, 0)))
    eye, target = Vector(eye), Vector(target)
    fwd = (target - eye).normalized()
    right = fwd.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(fwd)
    rot = Matrix((right, up, -fwd)).to_4x4()
    view = rot @ Matrix.Translation(-eye)
    return proj @ view


def test_ray_through_region_pixel():
    pm = _persp((10, -10, 10), (0, 0, 0), 800, 600)
    origin, direction = drag.ray(pm, 800, 600, 400, 300)
    to_target = (Vector((0, 0, 0)) - origin).normalized()
    assert (direction - to_target).length < 1e-4, (direction, to_target)
    # orthographic: parallel rays, origins differ
    ortho = Matrix.Diagonal((0.1, 0.1, -0.01, 1.0))
    o1, d1 = drag.ray(ortho, 200, 200, 100, 100)
    o2, d2 = drag.ray(ortho, 200, 200, 150, 100)
    assert (d1 - d2).length < 1e-6 and abs((o2 - o1).x - 5.0) < 1e-4, (o1, o2)


def test_object_at_ray_cast():
    _clear()
    cube = _cube()
    _cube("pCube2", (6, 0, 0))
    scene, dg = bpy.context.scene, bpy.context.evaluated_depsgraph_get()
    pm = _persp((10, -10, 10), (0, 0, 0), 800, 600)
    origin, direction = drag.ray(pm, 800, 600, 400, 300)
    hit = drag.object_at(scene, dg, origin, direction)
    assert hit == cube and hit.original == hit, hit
    origin, direction = drag.ray(pm, 800, 600, 5, 595)     # top-left corner: sky
    assert drag.object_at(scene, dg, origin, direction) is None


def test_drop_whole_object():
    _clear()
    cube = _cube()
    old = material.new_material('LAMBERT')
    cube.data.materials.append(old)
    blinn = material.new_material('BLINN')
    done = drag.drop(bpy.context, blinn, cube)
    assert done == {cube.name: 0}, done
    assert [s.material for s in cube.material_slots] == [blinn]
    assert drag.drop(bpy.context, blinn, None) is None
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    assert drag.drop(bpy.context, blinn, cam) is None, "a camera takes no material"


def test_drop_on_selected_faces_in_face_mode():
    _clear()
    cube = _cube()
    for o in bpy.context.selected_objects:
        o.select_set(False)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(cube.data)
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        f.select_set(f.index in (0, 1))
    bmesh.update_edit_mesh(cube.data)
    blinn = material.new_material('BLINN')
    done = drag.drop(bpy.context, blinn, cube)
    bpy.ops.object.mode_set(mode='OBJECT')
    index = done[cube.name]
    assert cube.material_slots[index].material == blinn
    got = [p.material_index for p in cube.data.polygons]
    assert got[:2] == [index, index] and all(i != index for i in got[2:]), got


def test_swatch_property():
    _clear()
    _cube()
    blinn = material.new_material('BLINN')
    blinn.use_fake_user = True
    wm = bpy.context.window_manager
    wm.allset_hs_material = ""
    assert not blinn.allset_hs_pick
    blinn.allset_hs_pick = True               # = a click on the swatch's name button
    assert wm.allset_hs_material == blinn.name and blinn.allset_hs_pick
    blinn.allset_hs_pick = False              # clicking the picked swatch keeps it picked
    assert wm.allset_hs_material == blinn.name
    assert drag.material_of_property((blinn, "allset_hs_pick", -1)) == blinn
    assert drag.material_of_property((blinn, "name", -1)) is None
    assert drag.material_of_property((wm, "allset_hs_pick", -1)) is None
    assert drag.material_of_property(None) is None
    assert drag.PICK_PROP == hs.PICK_PROP
    # outside the Browser pane (no Hypershade here): no swatch
    assert drag.swatch_material(bpy.context) is None


def test_drag_operator_and_keymap_item():
    ops = drag.ALLSET_OT_hs_swatch_drag
    assert 'UNDO' in ops.bl_options and 'REGISTER' not in ops.bl_options, "one undo step, no redo panel"
    patches = import_module(kit.MODULE + ".keymap.maya_patches")
    items = [(km, ev["type"], ev["value"]) for km, idname, ev, _p, _s in patches.ADDED
             if idname == "allset.hs_swatch_drag"]
    assert items == [("View2D Buttons List", "MIDDLEMOUSE", "PRESS")], items
    assert "allset.hs_swatch_drag" in patches.PASS_THROUGH_FIRST
    km = kit.maya_kc().keymaps["View2D Buttons List"]
    mmb = [k.idname for k in km.keymap_items if k.type == 'MIDDLEMOUSE' and k.value == 'PRESS' and k.active
           and not (k.alt or k.ctrl or k.shift)]
    assert mmb and mmb[0] == "allset.hs_swatch_drag", mmb
