"""Step 88: the hand-check items of steps 59-79 that event simulation can prove, run in one Maya Workflow Kit session.

Each check name starts with the item's id ``[M<step>-<n>]`` (n = its place in that step's list); an item counts as
done only when all of its checks pass. Keys, clicks and drags are simulated events; a few Enter-in-a-field
actions set the field's property (its setter is the Enter path; gui_step75 proves the typing itself)."""

import os
import sys
import tempfile
from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win, load_maya_layout  # noqa: E402

C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def k():
    return mod("operators.units").maya_unit()


def ts():
    return bpy.context.scene.tool_settings


def key(type, **mods):
    names = {"alt": "LEFT_ALT", "ctrl": "LEFT_CTRL", "shift": "LEFT_SHIFT"}
    for m in mods:
        ev(names[m], 'PRESS')
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)
    for m in mods:
        ev(names[m], 'RELEASE')


def hover():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def tool_id():
    with override():
        t = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
    return t.idname if t else None


def select_only(*obs):
    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[-1]


def create(kind):
    with override():
        bpy.ops.allset.create(kind=kind)
    return bpy.context.view_layer.objects.active


def clear():
    if bpy.context.mode != 'OBJECT':
        with override():
            bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    # Maya names count the shapes too (pCubeShape1): drop the data so each section starts at pCube1
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.armatures, bpy.data.cameras, bpy.data.actions):
        for d in list(coll):
            coll.remove(d)


def near(a, b, eps=1e-4):
    return (Vector(a) - Vector(b)).length < eps


def notice():
    return mod("ui.notices").current()


# --- setup ---------------------------------------------------------------------------------------------------

@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_keymap():
    bpy.ops.allset.keymap_activate()
    hover()


# --- [M59-7] lead pivot / component bounding box --------------------------------------------------------------

@step
def m59_7_objects():
    a = create('CUBE')
    b = create('CUBE')
    b.location = (3 * k(), 0, 0)
    select_only(a, b)
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
        centre, _f, _o = mod("ui.manipulator").pivot_frame(bpy.context, 'TRANSLATE')
    check(f"[M59-7] two objects: the manipulator at the lead's pivot ({tuple(round(v / k(), 2) for v in centre)} cm)",
          near(centre, b.matrix_world.translation))
    hover()
    tap('F9')


@step
def m59_7_components():
    with override():
        bpy.ops.mesh.select_all(action='SELECT')
    check(f"[M59-7] edit mode: Pivot = Bounding Box Center ({ts().transform_pivot_point})",
          bpy.context.mode == 'EDIT_MESH' and ts().transform_pivot_point == 'BOUNDING_BOX_CENTER')
    with override():
        centre, _f, _o = mod("ui.manipulator").pivot_frame(bpy.context, 'TRANSLATE')
    pts = [ob.matrix_world @ v.co for ob in bpy.context.objects_in_mode for v in ob.data.vertices]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    check("[M59-7] components: the manipulator at the selection's bounding box centre", near(centre, (lo + hi) / 2))
    tap('F8')


# --- [M63-5] Combine / Separate ----------------------------------------------------------------------------

@step
def m63_5_combine():
    clear()
    cube = create('CUBE')
    cube.location = (2 * k(), 0, 0)
    sphere = create('SPHERE')
    sphere.location = (-2 * k(), 0, 1 * k())
    bpy.context.view_layer.update()
    pts = [ob.matrix_world @ v.co for ob in (cube, sphere) for v in ob.data.vertices]
    C["bbox"] = (Vector([min(p[i] for p in pts) for i in range(3)]) + Vector([max(p[i] for p in pts) for i in range(3)])) / 2
    select_only(cube, sphere)
    with override():
        C["combine"] = bpy.ops.allset.combine()


@step
def m63_5_combined():
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    ob = meshes[0] if len(meshes) == 1 else None
    check(f"[M63-5] Combine: one mesh pCube2 ({[o.name for o in meshes]})", ob is not None and ob.name == "pCube2")
    if ob is None:
        return
    check(f"[M63-5] Combine: Translate 0, pivot at the combined box centre ({tuple(ob.location)})",
          near(ob.location, (0, 0, 0)) and near(ob.matrix_world.translation, C["bbox"]))
    select_only(ob)
    with override():
        bpy.ops.allset.separate()


@step
def m63_5_separated():
    group = bpy.data.objects.get("pCube2")
    kids = sorted(o.name for o in group.children) if group else []
    check(f"[M63-5] Separate: pCube2 group with polySurface1 / polySurface2 ({group and group.type}, {kids})",
          group is not None and group.type == 'EMPTY' and kids == ["polySurface1", "polySurface2"])
    check("[M63-5] Separate: pieces at Translate 0",
          all(near(bpy.data.objects[n].location, (0, 0, 0)) for n in kids))
    # edit mode Separate = Blender's mesh.separate (loose parts), no group, Blender names
    me = bpy.data.meshes.new("parts")
    bm = bmesh.new()
    for x in (0.0, 3.0):
        v = [bm.verts.new((x + a, b, 0)) for a, b in ((0, 0), (1, 0), (1, 1), (0, 1))]
        bm.faces.new(v)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("parts", me)
    bpy.context.scene.collection.objects.link(ob)
    select_only(ob)
    C["before_sep"] = len(bpy.data.objects)
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.allset.separate()
        bpy.ops.object.mode_set(mode='OBJECT')
    new = sorted(o.name for o in bpy.data.objects if o.name.startswith("parts"))
    check(f"[M63-5] edit mode Separate = Blender's (loose parts, Blender names, no group: {new})",
          len(bpy.data.objects) == C["before_sep"] + 1 and new == ["parts", "parts.001"]
          and bpy.data.objects["parts.001"].parent is None)


# --- [M69-3] Ctrl+Alt+S increment and save -----------------------------------------------------------------

@step
def m69_3_save():
    d = tempfile.mkdtemp(prefix="allset_sweep_")
    C["v001"] = os.path.join(d, "shot_v001.blend")
    bpy.ops.wm.save_as_mainfile(filepath=C["v001"])
    hover()
    key('S', ctrl=True, alt=True)


@step
def m69_3_check():
    want = os.path.join(os.path.dirname(C["v001"]), "shot_v001.0001.blend")
    check(f"[M69-3] Ctrl+Alt+S saves shot_v001.0001.blend and goes on in it ({os.path.basename(bpy.data.filepath)})",
          os.path.exists(want) and os.path.normcase(bpy.data.filepath) == os.path.normcase(want))
    check("[M69-3] the original file stays", os.path.exists(C["v001"]))


# --- [M70-3] Graph Editor G / D / F / A, 3D View G = repeat last ----------------------------------------------

def graph():
    return C["garea"], next(r for r in C["garea"].regions if r.type == 'WINDOW')


@step
def m70_3_setup():
    clear()
    cube = create('CUBE')
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 48
    sc.use_preview_range = False
    for f, x in ((5, 0.0), (20, 3.0), (30, -1.0)):
        cube.location.x = x * k()
        cube.keyframe_insert("location", index=0, frame=f)
    select_only(cube)
    a, _r = view3d()
    C["garea"] = a
    a.ui_type = 'FCURVES'


@step
def m70_3_hover():
    a, r = graph()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    a2, r2 = graph()
    with bpy.context.temp_override(window=win(), area=a2, region=r2):
        bpy.ops.graph.select_all(action='SELECT')
        for fc in bpy.context.visible_fcurves:
            for kp in fc.keyframe_points:
                kp.handle_left_type = kp.handle_right_type = 'VECTOR'
    tap('G')


@step
def m70_3_g():
    _a, r = graph()
    x0 = r.view2d.region_to_view(0, 0)[0]
    x1 = r.view2d.region_to_view(r.width, 0)[0]
    check(f"[M70-3] Graph Editor G frames the playback range 1-48 ({x0:.1f}..{x1:.1f})",
          -8 < x0 < 1.5 and 47 < x1 < 58)
    tap('D')


@step
def m70_3_d():
    fc = bpy.data.objects["pCube1"].animation_data.action.layers[0].strips[0].channelbags[0].fcurves[0]
    types = {(kp.handle_left_type, kp.handle_right_type, kp.interpolation) for kp in fc.keyframe_points}
    check(f"[M70-3] D = Auto tangents on the selected keys ({types})", types == {('AUTO_CLAMPED', 'AUTO_CLAMPED', 'BEZIER')})
    a, r = graph()
    with bpy.context.temp_override(window=win(), area=a, region=r):
        bpy.ops.graph.select_all(action='DESELECT')
        fc.keyframe_points[1].select_control_point = True
    tap('F')


@step
def m70_3_f():
    _a, r = graph()
    x0 = r.view2d.region_to_view(0, 0)[0]
    x1 = r.view2d.region_to_view(r.width, 0)[0]
    check(f"[M70-3] F frames the selected key (frame 20 in view {x0:.1f}..{x1:.1f}, narrower than the range)",
          x0 < 20 < x1 and (x1 - x0) < 40)
    C["fspan"] = x1 - x0
    tap('A')


@step
def m70_3_a():
    _a, r = graph()
    x0 = r.view2d.region_to_view(0, 0)[0]
    x1 = r.view2d.region_to_view(r.width, 0)[0]
    check(f"[M70-3] A frames all keys (5..30 in view {x0:.1f}..{x1:.1f})", x0 < 5 and x1 > 30)
    kc = sys.modules["sim"].maya_kc()
    rep = [km.name for km in kc.keymaps for it in km.keymap_items
           if it.active and it.idname in ("screen.repeat_last", "allset.repeat_last")   # step 175: Maya G
           and it.type == 'G' and not (it.shift or it.ctrl or it.alt)]
    v3d_g = [it.idname for km_name in ("3D View", "Object Mode", "3D View Generic")
             for it in kc.keymaps[km_name].keymap_items if it.active and it.type == 'G' and it.value == 'PRESS'
             and not (it.shift or it.ctrl or it.alt)]
    check(f"[M70-3] 3D View G stays Repeat Last ({rep}, 3D View G items {v3d_g})", "Screen" in rep and not v3d_g)
    C["garea"].ui_type = 'VIEW_3D'


# --- [M70-4] Maya Auto Key -----------------------------------------------------------------------------------

def curves(ob):
    ad = ob.animation_data
    if ad is None or ad.action is None:
        return set()
    bag = ad.action.layers[0].strips[0].channelbags[0]
    return {(fc.data_path, fc.array_index) for fc in bag.fcurves}


@step
def m70_4_on():
    clear()
    cube = create('CUBE')
    select_only(cube)
    sc = bpy.context.scene
    sc.frame_set(1)
    cube.keyframe_insert("location", frame=1)
    sc.frame_set(10)
    sc.allset_auto_key = True        # step 130: the kit's own Maya Auto Key, no Blender preference
    with override():
        bpy.ops.transform.rotate(value=0.5, orient_axis='Z')
    bpy.context.scene.allset_cb.rx_text = "30"
    c = curves(cube)
    check(f"[M70-4] rotating a cube with only Translate keys adds no rotate keys (manipulator or Channel Box) ({sorted(c)})",
          not any(p == "rotation_euler" for p, _i in c))
    sc.allset_auto_key = False


@step
def m70_4_off():
    cube = bpy.data.objects["pCube1"]
    bpy.context.scene.frame_set(20)
    with override():
        bpy.ops.transform.rotate(value=0.5, orient_axis='Z')
    c = curves(cube)
    check(f"[M70-4] Maya Auto Key off: no keys added at frame 20 ({sorted(c)})", not any(p == "rotation_euler" for p, _i in c))


# --- [M75-1..4] Status Line input line -----------------------------------------------------------------------

def inp():
    return bpy.context.scene.allset_input


@step
def m75_1():
    clear()
    cube = create('CUBE')
    cube.location = (1 * k(), 2 * k(), 3 * k())
    select_only(cube)
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    bpy.ops.ed.undo_push(message="sweep 75")
    inp().mode = 'ABS'
    inp().x = "10"
    check(f"[M75-1] Abs X 10 = x 10 cm, Y / Z kept ({tuple(round(v / k(), 3) for v in cube.location)})",
          near(cube.location, (10 * k(), 2 * k(), 3 * k())))
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.rotate")
    inp().z = "45"
    check(f"[M75-1] Rotate tool: Abs Z 45 = rotate Z 45 ({cube.rotation_euler.z:.4f})",
          abs(cube.rotation_euler.z - 0.785398) < 1e-4)
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.scale")
    inp().y = "2"
    check(f"[M75-1] Scale tool: Abs Y 2 = scale Y 2 ({tuple(cube.scale)})", abs(cube.scale.y - 2) < 1e-6)
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
        bpy.ops.ed.undo()
    cube = bpy.data.objects["pCube1"]
    check(f"[M75-1] Ctrl+Z once takes back the last entry (scale {tuple(cube.scale)})", abs(cube.scale.y - 1) < 1e-6)


@step
def m75_2():
    cube = bpy.data.objects["pCube1"]
    select_only(cube)
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(cube.data)
        for v in bm.verts:
            v.select_set(v.co.z > 0)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(cube.data)
    inp().mode = 'ABS'
    inp().z = "0"
    zs = [round((cube.matrix_world @ v.co).z, 6) for v in cube.data.vertices]
    me = cube.data
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.mode_set(mode='EDIT')
    sel = [cube.matrix_world @ v.co for v in me.vertices if v.select]
    check(f"[M75-2] edit mode Abs Z 0: the selected components' centre at z 0 ({sum(p.z for p in sel) / len(sel):.6f})",
          abs(sum(p.z for p in sel) / len(sel)) < 1e-6)
    before = [p.copy() for p in sel]
    inp().mode = 'REL'
    inp().x = "1"
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
    after = [cube.matrix_world @ v.co for v in me.vertices if v.select]
    check("[M75-2] Rel X 1 moves them 1 cm in x", all(abs((q - p).x - k()) < 1e-6 and abs((q - p).z) < 1e-6
                                                      for p, q in zip(before, after)))
    del zs


@step
def m75_3():
    clear()
    obs = [create('CUBE') for _ in range(3)]
    select_only(*obs)
    inp().mode = 'RENAME'
    check(f"[M75-3] Rename shows the lead's name ({inp().text})", inp().text == obs[-1].name)
    inp().text = "crate"
    names = sorted(o.name for o in bpy.context.selected_objects)
    shapes = sorted(o.data.name for o in bpy.context.selected_objects)
    check(f"[M75-3] Rename crate: crate, crate1, crate2 + crateShape… ({names}, {shapes})",
          names == ["crate", "crate1", "crate2"] and all(s.startswith("crateShape") for s in shapes))
    inp().text = "1x"
    e1 = notice()
    inp().text = "a-b"
    e2 = notice()
    check(f"[M75-3] '1x' and 'a-b' are refused with a Help Line message ({e1!r}, {e2!r})",
          e1 and e2 and sorted(o.name for o in bpy.context.selected_objects) == ["crate", "crate1", "crate2"])


@step
def m75_4():
    clear()
    create('CUBE')
    create('CUBE')
    create('SPHERE')
    inp().mode = 'SELECT'
    inp().text = "pCube*"
    s1 = sorted(o.name for o in bpy.context.selected_objects)
    inp().text = "p?phere1"
    s2 = sorted(o.name for o in bpy.context.selected_objects)
    check(f"[M75-4] Select by Name pCube* / p?phere1 ({s1}, {s2})", s1 == ["pCube1", "pCube2"] and s2 == ["pSphere1"])
    inp().text = "nothing*"
    check(f"[M75-4] a missing name: Help Line message, the text stays ({notice()!r}, {inp().text!r})",
          bool(notice()) and inp().text == "nothing*")
    il = mod("ui.input_line")
    # step 189: Construction History is Maya's real toggle now (no grey button, no notice)
    on = bpy.context.window_manager.allset_construction_history
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.construction_history()
    flipped = bpy.context.window_manager.allset_construction_history
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.construction_history()
    check(f"[M75-4] the History button toggles Construction History ({on} -> {flipped})",
          on is True and flipped is False and il.HISTORY_PATH not in mod("ui.notices").PANEL_NOTICES)
    inp().mode = 'ABS'


# --- [M77-2] Insert + D; Insert twice clears the pivot ----------------------------------------------------------

@step
def m77_2_setup():
    clear()
    cube = create('CUBE')
    select_only(cube)
    hover()
    tap('F9')


@step
def m77_2_insert():
    with override():
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    C["tool"] = tool_id()
    tap('INSERT')


@step
def m77_2_d():
    on = mod("operators.hold").COMPONENT.on
    check(f"[M77-2] Insert turns the pivot edit on ({on}, {tool_id()})", on and tool_id() == "builtin.cursor")
    tap('D')


@step
def m77_2_d_check():
    check(f"[M77-2] D while it is on turns it off ({mod('operators.hold').COMPONENT.on}, {tool_id()})",
          not mod("operators.hold").COMPONENT.on and tool_id() == C["tool"])
    tap('INSERT')


@step
def m77_2_twice():
    tap('INSERT')


@step
def m77_2_twice_check():
    with override():
        centre, _f, _o = mod("ui.manipulator").pivot_frame(bpy.context, 'TRANSLATE')
    cube = bpy.data.objects["pCube1"]
    pts = [cube.matrix_world @ v.co for v in cube.data.vertices]
    mid = (Vector([min(p[i] for p in pts) for i in range(3)]) + Vector([max(p[i] for p in pts) for i in range(3)])) / 2
    check(f"[M77-2] Insert twice without moving: no user pivot ({ts().transform_pivot_point}), manipulator at the bbox centre",
          ts().transform_pivot_point != 'CURSOR' and near(centre, mid) and not mod("operators.hold").COMPONENT.on)
    tap('F8')


# --- [M78-3] Ctrl+Alt+Left / Right spin an edge -------------------------------------------------------------

def strip_mesh():
    me = bpy.data.meshes.new("strip")
    bm = bmesh.new()
    v = [bm.verts.new(co) for co in ((0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0))]
    bm.faces.new((v[0], v[1], v[4], v[3]))
    bm.faces.new((v[1], v[2], v[5], v[4]))
    bm.to_mesh(me)
    bm.free()
    return me


def shared_edge(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    e = next(e for e in bm.edges if len(e.link_faces) == 2)
    return tuple(sorted(v.index for v in e.verts))


@step
def m78_3_setup():
    clear()
    ob = bpy.data.objects.new("strip", strip_mesh())
    bpy.context.scene.collection.objects.link(ob)
    select_only(ob)
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')
        bm = bmesh.from_edit_mesh(ob.data)
        for e in bm.edges:
            e.select_set(len(e.link_faces) == 2)
        bmesh.update_edit_mesh(ob.data)
    C["e0"] = shared_edge(ob)
    hover()
    key('RIGHT_ARROW', ctrl=True, alt=True)


@step
def m78_3_right():
    ob = bpy.data.objects["strip"]
    C["e1"] = shared_edge(ob)
    check(f"[M78-3] Ctrl+Alt+Right spins the edge ({C['e0']} -> {C['e1']})", C["e1"] != C["e0"])
    key('LEFT_ARROW', ctrl=True, alt=True)


@step
def m78_3_left():
    e2 = shared_edge(bpy.data.objects["strip"])
    check(f"[M78-3] Ctrl+Alt+Left spins it the other way, back ({e2})", e2 == C["e0"])
    mm = mod("ui.menu_map").MAP
    kc = sys.modules["sim"].maya_kc()
    keys = {it.type: bool(it.properties.use_ccw) for it in kc.keymaps["Mesh"].keymap_items
            if it.active and it.idname == "mesh.edge_rotate" and it.ctrl and it.alt}
    check(f"[M78-3] the keys spin like the menu (Right = Forward, Left = Backward: {keys})",
          keys.get('RIGHT_ARROW') == mm["Edit Mesh/Spin Edge Forward"][1]["use_ccw"]
          and keys.get('LEFT_ARROW') == mm["Edit Mesh/Spin Edge Backward"][1]["use_ccw"])
    tap('F8')


# --- [M78-6] Graph Editor 1 / 2 / 3 -------------------------------------------------------------------------

@step
def m78_6_setup():
    clear()
    cube = create('CUBE')
    for f in (1, 20):
        cube.location.z = f * 0.1 * k()
        cube.keyframe_insert("location", index=2, frame=f)
    select_only(cube)
    a, _r = view3d()
    C["garea"] = a
    a.ui_type = 'FCURVES'


@step
def m78_6_hover():
    _a, r = graph()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    tap('THREE')


@step
def m78_6_three():
    sp = C["garea"].spaces.active
    check(f"[M78-6] 3 = normalized ({sp.use_normalization})", sp.use_normalization)
    tap('ONE')


@step
def m78_6_one():
    sp = C["garea"].spaces.active
    check(f"[M78-6] 1 = absolute ({sp.use_normalization})", not sp.use_normalization)
    tap('TWO')


@step
def m78_6_two():
    sp = C["garea"].spaces.active
    gk = mod("operators.graph_keys")
    # the notice is the operator's INFO report (status bar = Maya Help Line); Python can't read the report list,
    # so the check is: 2 ran the STACKED mode (normalized) and that mode reports the notice
    kc = sys.modules["sim"].maya_kc()
    two = [it for it in kc.keymaps["Graph Editor"].keymap_items
           if it.active and it.type == 'TWO' and it.idname == "allset.graph_view_mode"]
    check(f"[M78-6] 2 = Stacked mode: normalized + its 'no Stacked' report ({sp.use_normalization}, "
          f"{two and two[0].properties.mode}, {gk.STACKED_NOTICE!r})",
          sp.use_normalization and two and two[0].properties.mode == "STACKED" and "Stacked" in gk.STACKED_NOTICE)
    C["garea"].ui_type = 'VIEW_3D'


# --- [M79-3] Cut and Sew tool x / s / d, outside the tool X / D ------------------------------------------------

def shells(ob):
    return len(mod("operators.uv_tools").islands(bmesh.from_edit_mesh(ob.data), ob.data.uv_layers.active.name)) \
        if hasattr(mod("operators.uv_tools"), "islands") else None


@step
def m79_3_setup():
    clear()
    cube = create('CUBE')
    select_only(cube)
    hover()
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')
        bm = bmesh.from_edit_mesh(cube.data)
        top = max(v.co.z for v in bm.verts)
        for e in bm.edges:
            e.select_set(all(abs(v.co.z - top) < 1e-6 for v in e.verts))
        bmesh.update_edit_mesh(cube.data)
        bpy.ops.wm.tool_set_by_id(name=mod("operators.cut_sew").TOOL)
    C["uvs0"] = sum(1 for e in bmesh.from_edit_mesh(cube.data).edges if e.seam)


def seams():
    cube = bpy.data.objects["pCube1"]
    return sum(1 for e in bmesh.from_edit_mesh(cube.data).edges if e.seam)


@step
def m79_3_x():
    check(f"[M79-3] the Cut and Sew tool is active ({tool_id()})", tool_id() == mod("operators.cut_sew").TOOL)
    tap('X')


@step
def m79_3_s():
    check(f"[M79-3] x cuts the selected edges (seams {C['uvs0']} -> {seams()})", seams() == 4)
    tap('S')


@step
def m79_3_d():
    check(f"[M79-3] s sews them (seams {seams()})", seams() == 0)
    tap('D')


@step
def m79_3_d_check():
    cube = bpy.data.objects["pCube1"]
    bm = bmesh.from_edit_mesh(cube.data)
    uv = bm.loops.layers.uv.active
    co = [l[uv].uv for f in bm.faces for l in f.loops]
    ok = all(-1e-4 <= c.x <= 1 + 1e-4 and -1e-4 <= c.y <= 1 + 1e-4 for c in co)
    check(f"[M79-3] d = Unfold + Layout in 0-1 ({ok})", ok)
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    ev('X', 'PRESS')


@step
def m79_3_outside_x():
    check(f"[M79-3] outside the tool X = grid snap hold ({ts().use_snap}, {set(ts().snap_elements)})",
          ts().use_snap and 'GRID' in set(ts().snap_elements))
    ev('X', 'RELEASE')
    ev('D', 'PRESS')


@step
def m79_3_outside_d():
    check(f"[M79-3] outside the tool D = pivot edit hold ({mod('operators.hold').COMPONENT.on})",
          mod("operators.hold").COMPONENT.on)
    ev('D', 'RELEASE')
    C["seams_before_s"] = seams()


@step
def m79_3_outside_s():
    tap('S')


@step
def m79_3_outside_s_check():
    check(f"[M79-3] outside the tool S doesn't sew (seams {C['seams_before_s']} -> {seams()})",
          seams() == C["seams_before_s"])
    if bpy.context.window_manager.windows[0].modal_operators:
        ev('ESC', 'PRESS')
        ev('ESC', 'RELEASE')
    tap('F8')


# =============================================================================================================
# Step 97: the remaining simulatable items of steps 59-79.
# Menu / shelf / sidebar-button actions run the Maya menu path (allset.menu_item) or the button's operator: the
# click -> operator link is what the menu / shelf / sidebar GUI tests prove (gui_step34, 51, 62, ...); keys, clicks
# in the views and drags are simulated events.
# =============================================================================================================

import math  # noqa: E402

GUI_TIMEOUT = 2400   # tests/gui/run.py: the whole sweep runs much longer than one GUI test file

from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d  # noqa: E402
from mathutils import Matrix, Quaternion  # noqa: E402


def named(name):
    """@step with a readable name (ALLSET_SWEEP_ONLY keeps steps whose name starts with one of its prefixes)."""
    def deco(fn):
        fn.__name__ = name
        return step(fn)
    return deco


def screen(world, region=None):
    region = region or view3d()[1]
    p = location_3d_to_region_2d(region, region.data, world)
    return Vector((region.x + p.x, region.y + p.y))


def px_world(at):
    _a, region = view3d()
    p = location_3d_to_region_2d(region, region.data, at)
    w = region_2d_to_location_3d(region, region.data, p + Vector((1, 0)), at)
    return (w - at).length


def arrow_len_px():
    return (mod("ui.manipulator").ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0
            * bpy.context.preferences.system.ui_scale)


def handle_point(ob, axis, frac):
    c = ob.matrix_world.translation
    return screen(c + Vector(axis) * arrow_len_px() * frac * px_world(c))


def move_to(p):
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x) + 1, y=int(p.y))


def drag(name, start, end, hold=(), button='LEFTMOUSE', moves=8, mods=None, skip=None):
    """Register a drag as steps (hover / keys + press / one move per tick / release): a transform modal started on
    a press misses moves queued in the same tick (step 28) and snapping looks for its target at most every 10 ms
    (step 95). ``start`` / ``end`` are callables giving window points; ``skip()`` True = do nothing."""
    mods = mods or {}
    pts = {}

    def off():
        return pts.get("off", False)

    @named(f"{name}_hover")
    def _hover():
        pts["off"] = bool(skip and skip())
        if off():
            return
        pts["p"], pts["to"] = Vector(start()), Vector(end())
        move_to(pts["p"])
        redraw_all()   # gizmos highlight on the redraw after the hover

    for j, keyname in enumerate(hold):   # hold keys one per tick before the press (their modals start first)
        @named(f"{name}_hold{j}")
        def _hold(keyname=keyname):
            if off():
                return
            ev(keyname, 'PRESS', x=int(pts["p"].x), y=int(pts["p"].y))
            redraw_all()

    @named(f"{name}_press")
    def _press():
        if off():
            return
        p = pts["p"]
        if hold:   # the manipulator may have rebuilt for the held key: hover again so its handle is highlighted
            move_to(p)
        ev(button, 'PRESS', x=int(p.x), y=int(p.y), **mods)

    for i in range(1, moves + 1):
        @named(f"{name}_move{i}")
        def _move(i=i):
            if off():
                return
            p, to = pts["p"], pts["to"]
            q = p + (to - p) * (i / moves)
            ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y), **mods)

    @named(f"{name}_release")
    def _release():
        if off():
            return
        to = pts["to"]
        ev(button, 'RELEASE', x=int(to.x), y=int(to.y), **mods)
        for keyname in reversed(hold):
            ev(keyname, 'RELEASE')


def menu(path, **kw):
    with override():
        return bpy.ops.allset.menu_item(item=path, **kw)


def set_tool(name):
    with override():
        bpy.ops.wm.tool_set_by_id(name=name)
    redraw_all()


def redraw_all():
    for a in win().screen.areas:
        a.tag_redraw()


def world_verts(ob):
    return [ob.matrix_world @ v.co for v in ob.data.vertices]


def same_points(a, b, eps=1e-6):
    return len(a) == len(b) and all((x - y).length < eps for x, y in zip(a, b))


def view_dir():
    _a, region = view3d()
    return region.data.view_rotation @ Vector((0, 0, -1))


def eye():
    return view3d()[1].data.view_matrix.inverted().translation


def nearest_vertex_to_eye(ob):
    return min((ob.matrix_world @ v.co for v in ob.data.vertices), key=lambda p: (p - eye()).length)


def cm(v):
    return tuple(round(x / k(), 3) for x in v)


def esc_modals():
    if win().modal_operators:
        tap('ESC')


def undo_base(message):
    """An undo step for the state built with bpy.data calls (they push none), so a later Ctrl+Z lands here."""
    with override():
        bpy.ops.ed.undo_push(message=message)


# --- [M59-2] active handle stays yellow, MMB anywhere = that axis, centre square = screen plane ---------------

@named("m59_2_setup")
def _m59_2_setup():
    clear()
    ts().use_snap = False
    C["ob"] = create('CUBE')
    select_only(C["ob"])
    set_tool("builtin.move")
    C["start"] = C["ob"].location.copy()


drag("m59_2_x", lambda: handle_point(C["ob"], (1, 0, 0), 0.6), lambda: handle_point(C["ob"], (1, 0, 0), 1.3))


@named("m59_2_x_check")
def _m59_2_x_check():
    d = C["ob"].location - C["start"]
    man = mod("ui.manipulator")
    check(f"[M59-2] X arrow drag moves along X ({cm(d)} cm)", d.x > 0.05 * k() and abs(d.y) < 1e-7 and abs(d.z) < 1e-7)
    check("[M59-2] X stays the active handle and is drawn yellow (the manipulator's colour rule)",
          man._is_active('TRANSLATE', (True, False, False)) and not man._is_active('TRANSLATE', (False, True, False)))
    C["start"] = C["ob"].location.copy()
    _a, r = view3d()
    C["mmb_p"] = Vector((r.x + r.width * 0.25, r.y + r.height * 0.75))


drag("m59_2_mmb", lambda: C["mmb_p"], lambda: C["mmb_p"] + Vector((60, -25)), button='MIDDLEMOUSE')


@named("m59_2_mmb_check")
def _m59_2_mmb_check():
    d = C["ob"].location - C["start"]
    check(f"[M59-2] MMB drag away from the manipulator moves along the active X ({cm(d)} cm)",
          abs(d.x) > 0.05 * k() and abs(d.y) < 1e-7 and abs(d.z) < 1e-7)
    C["start"] = C["ob"].location.copy()


drag("m59_2_centre", lambda: screen(C["ob"].matrix_world.translation),
     lambda: screen(C["ob"].matrix_world.translation) + Vector((40, 30)))


@named("m59_2_centre_check")
def _m59_2_centre_check():
    d = C["ob"].location - C["start"]
    check(f"[M59-2] centre square drag = free move in the screen plane ({cm(d)} cm, along the view "
          f"{d.dot(view_dir()) / k():.2e} cm)",
          d.length > 0.05 * k() and abs(d.dot(view_dir())) < 1e-3 * d.length and sum(abs(c) > 1e-6 for c in d) >= 2)


# --- [M59-4] D drag = pivot only, pivot ring = pivot orientation, E about the new pivot, Insert, Ctrl+Z ----------

@named("m59_4_setup")
def _m59_4_setup():
    clear()
    ob = create('CUBE')
    child = create('CUBE')
    child.location = (0, 0, 2 * k())
    mod("operators.parenting").set_parent_maya(child, ob)
    select_only(ob)
    bpy.context.view_layer.update()
    C.update(ob=ob, child=child, loc=ob.location.copy(), verts=world_verts(ob),
             child_w=child.matrix_world.translation.copy())
    set_tool("builtin.move")
    undo_base("m59_4 setup")


drag("m59_4_d", lambda: handle_point(C["ob"], (1, 0, 0), 0.6), lambda: handle_point(C["ob"], (1, 0, 0), 1.1),
     hold=('D',))


@named("m59_4_d_check")
def _m59_4_d_check():
    ob = C["ob"]
    check(f"[M59-4] D + drag: Channel Box Translate stays ({cm(ob.location)}), the pivot moved "
          f"(delta {ob.delta_location.x / k():.3f} cm)",
          (ob.location - C["loc"]).length < 1e-7 and abs(ob.delta_location.x) > 0.05 * k())
    check("[M59-4] D + drag: geometry and child stay",
          same_points(C["verts"], world_verts(ob))
          and (C["child"].matrix_world.translation - C["child_w"]).length < 1e-6)
    hover()
    key('Z', ctrl=True)


@named("m59_4_undo_check")
def _m59_4_undo_check():
    ob = bpy.data.objects["pCube1"]
    check(f"[M59-4] Ctrl+Z once = before the pivot move (delta {cm(ob.delta_location)}, Translate {cm(ob.location)})",
          ob.delta_location.length < 1e-7 and ob.location.length < 1e-7)


@named("m59_4_again")
def _m59_4_again():
    C["ob"] = bpy.data.objects["pCube1"]
    C["child"] = bpy.data.objects["pCube2"]
    select_only(C["ob"])


drag("m59_4_d2", lambda: handle_point(C["ob"], (1, 0, 0), 0.6), lambda: handle_point(C["ob"], (1, 0, 0), 1.1),
     hold=('D',))


@named("m59_4_d2_check")
def _m59_4_d2_check():
    ob = C["ob"]
    check("[M59-4] (the pivot moved again for the ring / E part)", abs(ob.delta_location.x) > 0.05 * k())
    C["pivot"] = ob.matrix_world.translation.copy()
    C["verts"] = world_verts(ob)
    hover()
    tap('INSERT')


def ring_point(angle, frac_r=1.0):
    c = C["ob"].matrix_world.translation
    r = mod("ui.manipulator").PIVOT_RING_R * arrow_len_px() * px_world(c) * frac_r
    return screen(c + Vector((r * math.cos(angle), r * math.sin(angle), 0)))


@named("m59_4_insert_check")
def _m59_4_insert_check():
    check(f"[M59-4] Insert = pivot edit on ({ts().use_transform_data_origin})", ts().use_transform_data_origin)
    redraw_all()


drag("m59_4_ring", lambda: ring_point(math.pi * 1.25), lambda: ring_point(math.pi * 1.25) + Vector((-35, 40)))


@named("m59_4_ring_check")
def _m59_4_ring_check():
    ob = C["ob"]
    pv = mod("operators.pivot")
    slot = bpy.context.scene.transform_orientation_slots[pv.MOVE_SLOT]
    check(f"[M59-4] the small Z ring turns the pivot: Move axis = '{pv.ORIENT_NAME}' ({slot.type}), Rotate stays "
          f"({tuple(round(v, 4) for v in ob.rotation_euler)}), geometry stays",
          slot.type == pv.ORIENT_NAME and Vector(ob.rotation_euler).length < 1e-6 and pv.PROP in ob
          and same_points(C["verts"], world_verts(ob)))
    hover()
    tap('INSERT')


@named("m59_4_rotate")
def _m59_4_rotate():
    check(f"[M59-4] Insert again = pivot edit off ({ts().use_transform_data_origin})", not ts().use_transform_data_origin)
    set_tool("builtin.rotate")


def _rot_ring(frac):
    c = C["ob"].matrix_world.translation
    r = frac * bpy.context.preferences.view.gizmo_size * bpy.context.preferences.system.ui_scale * px_world(c)
    return screen(c + Vector((-r, 0, 0))), screen(c + Vector((-r, -r * 0.6, 0)))


for _i, _f in enumerate((0.9, 0.75, 1.05)):
    drag(f"m59_4_e{_i}", lambda f=_f: _rot_ring(f)[0], lambda f=_f: _rot_ring(f)[1],
         skip=lambda: abs(C["ob"].rotation_euler.z) > 0.05)


@named("m59_4_e_check")
def _m59_4_e_check():
    ob = C["ob"]
    check(f"[M59-4] E then turns the cube about the new pivot (rot z {ob.rotation_euler.z:.3f}, pivot moved "
          f"{(ob.matrix_world.translation - C['pivot']).length:.1e})",
          abs(ob.rotation_euler.z) > 0.05 and (ob.matrix_world.translation - C["pivot"]).length < 1e-6)
    set_tool("builtin.move")


# --- [M59-5] D + X / V, Bake Pivot, Tool Settings Reset, Match Pivots --------------------------------------------

@named("m59_5_setup")
def _m59_5_setup():
    clear()
    a = create('CUBE')
    b = create('CUBE')
    b.location = (3 * k(), 0, 0)
    a.location = (0.3 * k(), 0, 0)
    select_only(a)
    bpy.context.view_layer.update()
    C.update(a=a, b=b, loc=a.location.copy())
    set_tool("builtin.move")


drag("m59_5_dx", lambda: handle_point(C["a"], (1, 0, 0), 0.6), lambda: handle_point(C["a"], (1, 0, 0), 1.2),
     hold=('D', 'X'))


@named("m59_5_dx_check")
def _m59_5_dx_check():
    a = C["a"]
    x = a.matrix_world.translation.x / k()
    check(f"[M59-5] D + X: the pivot lands on a grid line (x {x:.4f} cm), Translate stays",
          abs(x - round(x)) < 1e-3 and abs(x - 0.3) > 0.5 and (a.location - C["loc"]).length < 1e-7)
    C["target"] = nearest_vertex_to_eye(C["b"])


drag("m59_5_dv", lambda: screen(C["a"].matrix_world.translation), lambda: screen(C["target"]), hold=('D', 'V'))


@named("m59_5_dv_check")
def _m59_5_dv_check():
    a = C["a"]
    check(f"[M59-5] D + V: the pivot lands on pCube2's vertex ({cm(a.matrix_world.translation)} cm), Translate stays",
          (a.matrix_world.translation - C["target"]).length < 1e-6 and (a.location - C["loc"]).length < 1e-7)
    # a turned pivot (what the pivot ring makes, M59-4) -> Modify > Bake Pivot
    a[mod("operators.pivot").PROP] = tuple(Quaternion((0, 0, 1), math.radians(30)))
    C["verts"] = world_verts(a)
    C["baked"] = menu("Modify/Bake Pivot")


@named("m59_5_bake_check")
def _m59_5_bake_check():
    a, b = C["a"], C["b"]
    bpy.context.view_layer.update()
    check(f"[M59-5] Modify > Bake Pivot: the pivot orientation goes into Rotate ({math.degrees(a.rotation_euler.z):.2f}), "
          f"geometry stays",
          abs(abs(a.rotation_euler.z) - math.radians(30)) < 1e-3 and same_points(C["verts"], world_verts(a)))
    C["verts"] = world_verts(a)
    with override():
        bpy.ops.allset.reset_pivot()   # the Tool Settings "Reset" button (manipulator.draw_tool_settings)
    bpy.context.view_layer.update()
    check(f"[M59-5] Tool Settings Reset: pivot = the object origin (delta {cm(a.delta_location)}), geometry stays",
          a.delta_location.length < 1e-7 and same_points(C["verts"], world_verts(a)))
    mod("operators.freeze").shift_pivot(b, Vector((0, 0.5 * k(), 1 * k())))
    bpy.context.view_layer.update()
    select_only(a, b)
    C["verts"] = world_verts(a)
    menu("Modify/Match Transformations/Match Pivots")
    bpy.context.view_layer.update()
    check(f"[M59-5] Match Pivots: pCube1's pivot onto pCube2's ({cm(a.matrix_world.translation)} / "
          f"{cm(b.matrix_world.translation)}), geometry stays",
          (a.matrix_world.translation - b.matrix_world.translation).length < 1e-6 and same_points(C["verts"], world_verts(a)))


# --- [M59-6] X drag from 0.3 cm, V centre onto a vertex, Status Line snap buttons while held -------------------------

@named("m59_6_setup")
def _m59_6_setup():
    clear()
    a = create('CUBE')
    b = create('CUBE')
    b.location = (3 * k(), 0, 0)
    a.location = (0.3 * k(), 0, 0)
    select_only(a)
    bpy.context.view_layer.update()
    C.update(a=a, b=b)
    set_tool("builtin.move")


drag("m59_6_x", lambda: handle_point(C["a"], (1, 0, 0), 0.6), lambda: handle_point(C["a"], (1, 0, 0), 1.6), hold=('X',))


@named("m59_6_x_check")
def _m59_6_x_check():
    x = C["a"].location.x / k()
    check(f"[M59-6] X held drag from 0.3 cm lands on a whole cm (x {x:.4f})", abs(x - round(x)) < 1e-3 and round(x) >= 1)
    C["a"].location = (0, 0, 0)
    bpy.context.view_layer.update()
    C["target"] = nearest_vertex_to_eye(C["b"])
    move_to(screen(C["a"].matrix_world.translation))


@named("m59_6_v_down")
def _m59_6_v_down():
    ev('V', 'PRESS')


@named("m59_6_v_state")
def _m59_6_v_state():
    check("[M59-6] the Status Line point snap button is on while V is held", mod("ui.status_line").snap_on(ts(), "POINT"))
    ev('V', 'RELEASE')


@named("m59_6_x_down")
def _m59_6_x_down():
    check("[M59-6] ... and off after V", not mod("ui.status_line").snap_on(ts(), "POINT"))
    ev('X', 'PRESS')


@named("m59_6_x_state")
def _m59_6_x_state():
    check("[M59-6] the Status Line grid snap button is on while X is held", mod("ui.status_line").snap_on(ts(), "GRID"))
    ev('X', 'RELEASE')


@named("m59_6_x_up")
def _m59_6_x_up():
    check("[M59-6] ... and off after X", not mod("ui.status_line").snap_on(ts(), "GRID"))


drag("m59_6_v", lambda: screen(C["a"].matrix_world.translation), lambda: screen(C["target"]), hold=('V',))


@named("m59_6_v_check")
def _m59_6_v_check():
    got = C["a"].matrix_world.translation
    check(f"[M59-6] V held + centre handle: the pivot on pCube2's vertex ({cm(got)} cm)", (got - C["target"]).length < 1e-6)


# --- [M59-8] Move Options Tool Settings contents, W menu = Move axis only, E menu = Rotate axis only, Discrete Rotate ---

class LayoutRecorder:
    """Stands in for a UILayout: records label / prop / operator texts so a draw function's contents can be read."""

    def __init__(self, out=None):
        self.out = out if out is not None else []

    def _sub(self, *_a, **_kw):
        return LayoutRecorder(self.out)

    row = column = box = split = _sub

    def __getattr__(self, name):   # template_list, prop_enum, ... : nothing to record
        return self._sub

    def separator(self, *_a, **_kw):
        pass

    def label(self, text="", **_kw):
        self.out.append(text)

    def prop(self, data, prop, text=None, **_kw):
        self.out.append(text if text is not None else prop)

    def operator(self, idname, text=None, **_kw):
        self.out.append(text if text is not None else idname)

        class _Props:
            pass
        return _Props()


def gesture(name, keyname, direction, mods=None):
    """Register a Maya marking menu gesture: ``keyname`` held + LMB drag towards ``direction`` (N, NE, ...), release."""
    mods = mods or {}
    vec = {"N": (0, 1), "NE": (0.7071, 0.7071), "E": (1, 0), "SE": (0.7071, -0.7071), "S": (0, -1),
           "SW": (-0.7071, -0.7071), "W": (-1, 0), "NW": (-0.7071, 0.7071)}[direction]
    pts = {}

    @named(f"{name}_key")
    def _key():
        _a, r = view3d()
        pts["c"] = Vector((r.x + r.width * 0.4, r.y + r.height * 0.5))
        move_to(pts["c"])
        ev(keyname, 'PRESS', **mods)

    @named(f"{name}_lmb")
    def _lmb():
        c = pts["c"]
        ev('LEFTMOUSE', 'PRESS', x=int(c.x), y=int(c.y), **mods)

    @named(f"{name}_drag")
    def _drag():
        c, d = pts["c"], 110 * bpy.context.preferences.system.ui_scale
        for f in (0.3, 0.6, 1.0):
            ev('MOUSEMOVE', 'NOTHING', x=int(c.x + vec[0] * d * f), y=int(c.y + vec[1] * d * f), **mods)

    @named(f"{name}_release")
    def _release():
        c, d = pts["c"], 110 * bpy.context.preferences.system.ui_scale
        ev('LEFTMOUSE', 'RELEASE', x=int(c.x + vec[0] * d), y=int(c.y + vec[1] * d), **mods)

    @named(f"{name}_key_up")
    def _key_up():
        ev(keyname, 'RELEASE', **mods)


def slots():
    return tuple(s.type for s in bpy.context.scene.transform_orientation_slots[1:4])


@named("m59_8_setup")
def _m59_8_setup():
    clear()
    select_only(create('CUBE'))
    set_tool("builtin.move")
    rec = LayoutRecorder()

    class _Panel:
        layout = rec
    with override():
        mod("ui.manipulator").draw_tool_settings(_Panel(), bpy.context)
    want = ["Move Settings", "Axis Orientation", "Pivot", "Step Snap", "Off", "Relative", "Absolute",
            "Retain Component Spacing", "Edit Pivot", "Reset", "Bake"]
    missing = [w for w in want if not any(w in t for t in rec.out)]
    check(f"[M59-8] Move Options Tool Settings list Move Settings: Axis Orientation, Pivot, Step Snap Off / Relative / "
          f"Absolute, Retain Component Spacing, Edit Pivot / Reset / Bake (missing {missing})", not missing)
    panel = bpy.types.VIEW3D_PT_active_tool
    funcs = getattr(panel.draw, "_draw_funcs", [])
    check("[M59-8] they are drawn in the active tool panel (the Status Line / W menu Tool Settings popup)",
          mod("ui.manipulator").draw_tool_settings in funcs)
    move_list = [it[0] for it in mod("marking.menus").OPT_MOVE.items if isinstance(it, tuple)]
    check(f"[M59-8] the W menu list ends with Move Options ({move_list[-1:]})", move_list[-1:] == ["Move Options"])
    bpy.context.scene.transform_orientation_slots[1].type = 'GLOBAL'
    bpy.context.scene.transform_orientation_slots[2].type = 'LOCAL'
    bpy.context.scene.transform_orientation_slots[3].type = 'LOCAL'
    C["slots"] = slots()


gesture("m59_8_w_nw", 'W', "NW")


@named("m59_8_w_nw_check")
def _m59_8_w_nw_check():
    check(f"[M59-8] W menu NW Object = Move axis Object only ({slots()})", slots() == ('LOCAL', 'LOCAL', 'LOCAL'))


gesture("m59_8_w_ne", 'W', "NE")


@named("m59_8_w_ne_check")
def _m59_8_w_ne_check():
    check(f"[M59-8] W menu NE Component = Move axis Component only ({slots()})", slots() == ('NORMAL', 'LOCAL', 'LOCAL'))


gesture("m59_8_w_w", 'W', "W")


@named("m59_8_w_w_check")
def _m59_8_w_w_check():
    check(f"[M59-8] W menu W World = Move axis World only ({slots()})", slots() == ('GLOBAL', 'LOCAL', 'LOCAL'))
    set_tool("builtin.rotate")


gesture("m59_8_e_w", 'E', "W")


@named("m59_8_e_w_check")
def _m59_8_e_w_check():
    check(f"[M59-8] E menu W World = Rotate axis only ({slots()})", slots() == ('GLOBAL', 'GLOBAL', 'LOCAL'))
    C["rot_snap"] = mod("operators.snap_align").step_snap_mode(ts(), 'ROTATE')


gesture("m59_8_e_se", 'E', "SE")


@named("m59_8_e_se_check")
def _m59_8_e_se_check():
    mode = mod("operators.snap_align").step_snap_mode(ts(), 'ROTATE')
    check(f"[M59-8] E menu SE Discrete Rotate turns on 15-degree steps ({C['rot_snap']} -> {mode}, "
          f"{math.degrees(ts().snap_angle_increment_3d):.1f} deg)",
          mode != 'OFF' and C["rot_snap"] == 'OFF' and abs(math.degrees(ts().snap_angle_increment_3d) - 15) < 1e-3)


gesture("m59_8_e_se2", 'E', "SE")


@named("m59_8_done")
def _m59_8_done():
    check("[M59-8] (Discrete Rotate again = off)", mod("operators.snap_align").step_snap_mode(ts(), 'ROTATE') == 'OFF')
    set_tool("builtin.move")


# --- [M59-9] Snap Align Objects, Snap Together Tool, Make Live -------------------------------------------------

def _select_verts(ob, indices):
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    for v in bm.verts:
        v.select = False
    bm.select_history.clear()
    for i in indices:
        bm.verts[i].select = True
        bm.select_history.add(bm.verts[i])
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)


def _two_cubes_edit(indices):
    clear()
    a = create('CUBE')
    b = create('CUBE')
    b.location = (4 * k(), 1 * k(), 0)
    b.rotation_euler.z = math.radians(30)
    bpy.context.view_layer.update()
    select_only(a, b)
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
    _select_verts(a, indices)
    _select_verts(b, indices)
    return a, b


@named("m59_9_p2p")
def _m59_9_p2p():
    a, b = _two_cubes_edit([0])
    rot = a.rotation_euler.copy()
    r = menu("Modify/Snap Align Objects/Point to Point")
    bpy.context.view_layer.update()
    pa, pb = a.matrix_world @ a.data.vertices[0].co, b.matrix_world @ b.data.vertices[0].co
    check(f"[M59-9] Point to Point in edit mode: the moving object's vertex (first) onto the active object's ({r}, "
          f"{(pa - pb).length / k():.1e} cm apart), moves only", (pa - pb).length < 1e-6 and a.rotation_euler == rot)


@named("m59_9_p2")
def _m59_9_p2():
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
    a, b = _two_cubes_edit([0, 1])
    menu("Modify/Snap Align Objects/2 Points to 2 Points")
    bpy.context.view_layer.update()
    a0, a1 = (a.matrix_world @ a.data.vertices[i].co for i in (0, 1))
    b0, b1 = (b.matrix_world @ b.data.vertices[i].co for i in (0, 1))
    check(f"[M59-9] 2 Points to 2 Points: first points meet, directions line up "
          f"({(a0 - b0).length / k():.1e} cm, angle {math.degrees((a1 - a0).angle(b1 - b0)):.3f} deg)",
          (a0 - b0).length < 1e-6 and (a1 - a0).angle(b1 - b0) < 1e-4)


@named("m59_9_p3")
def _m59_9_p3():
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
    a, b = _two_cubes_edit([0, 1, 2])
    menu("Modify/Snap Align Objects/3 Points to 3 Points")
    bpy.context.view_layer.update()
    err = max(((a.matrix_world @ a.data.vertices[i].co) - (b.matrix_world @ b.data.vertices[i].co)).length
              for i in (0, 1, 2))
    check(f"[M59-9] 3 Points to 3 Points: all three meet (orientation too, {err / k():.1e} cm)", err < 1e-5)
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
    # Align Objects: world X, mid, at the average (S11)
    clear()
    a = create('CUBE')
    c = create('CUBE')
    c.location = (-3 * k(), 2 * k(), 1 * k())
    c.scale = (2, 3, 1)
    bpy.context.view_layer.update()
    select_only(a, c)
    menu("Modify/Snap Align Objects/Align Objects")
    bpy.context.view_layer.update()
    sa = mod("operators.snap_align")
    mid = [(bb[0].x + bb[1].x) / 2 for bb in (sa.bbox_world(a), sa.bbox_world(c))]
    check(f"[M59-9] Align Objects: X middles lined up at their average ({[round(m / k(), 3) for m in mid]} cm), "
          f"Y / Z kept", abs(mid[0] - mid[1]) < 1e-6 and abs(mid[0] + 1.5 * k()) < 1e-6 and abs(c.location.y - 2 * k()) < 1e-6)


@named("m59_9_together_setup")
def _m59_9_together_setup():
    clear()
    a = create('CUBE')
    b = create('CUBE')
    b.location = (3 * k(), 0, 0)
    bpy.context.view_layer.update()
    select_only(a)
    C.update(a=a, b=b)
    C["p_top"] = screen(Vector((0, 0, 0.5 * k())))
    C["p_side"] = screen(Vector((3.5 * k(), 0, 0)))
    move_to(C["p_top"])
    menu("Modify/Snap Together Tool")


@named("m59_9_click1")
def _m59_9_click1():
    check("[M59-9] Snap Together Tool waits for clicks", any(op.bl_idname == "ALLSET_OT_snap_together"
                                                             for op in win().modal_operators))
    p = C["p_top"]
    C["a_mw0"] = C["a"].matrix_world.copy()
    C["hit_top"] = click_hit(p, Vector((0, 0, 0.5 * k())), Vector((0, 0, 1)))
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y))
    ev('LEFTMOUSE', 'RELEASE', x=int(p.x), y=int(p.y))


def click_hit(p, plane_co, plane_no):
    """The world point a click at whole pixel ``p`` hits on a face plane (step 135: one pixel is ~0.06 cm in the
    viewport beside the wider dock, so the tool's result is checked against the clicked points)."""
    from mathutils.geometry import intersect_line_plane
    from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
    _a, region = view3d()
    xy = Vector((int(p.x) - region.x, int(p.y) - region.y))
    o = region_2d_to_origin_3d(region, region.data, xy)
    return intersect_line_plane(o, o + region_2d_to_vector_3d(region, region.data, xy), plane_co, plane_no)


@named("m59_9_click2")
def _m59_9_click2():
    p = C["p_side"]
    C["hit_side"] = click_hit(p, Vector((3.5 * k(), 0, 0)), Vector((1, 0, 0)))
    move_to(p)
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y))
    ev('LEFTMOUSE', 'RELEASE', x=int(p.x), y=int(p.y))


@named("m59_9_together_check")
def _m59_9_together_check():
    a = C["a"]
    top = a.matrix_world @ C["a_mw0"].inverted() @ C["hit_top"]     # the clicked point of the top face, moved
    want = C["hit_side"]
    n = (a.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    check(f"[M59-9] Snap Together: the clicked top face point meets the clicked side face point ({cm(top)} cm vs "
          f"{cm(want)}), facing it (normal {tuple(round(c, 3) for c in n)})",
          (top - want).length < 0.01 * k() and abs(want.x - 3.5 * k()) < 1e-6 and n.dot(Vector((-1, 0, 0))) > 0.999)
    select_only(C["b"])
    snap_before = ts().use_snap, set(ts().snap_elements)
    menu("Modify/Make Live")
    live = getattr(bpy.context.scene, "allset_live", None)
    check(f"[M59-9] Make Live: reference restricted, Status Line shows the name ({live and live.name})",
          live == C["b"] and live.hide_select and not live.select_get()
          and (ts().use_snap, set(ts().snap_elements)) == snap_before)
    for o in bpy.context.scene.objects:
        o.select_set(False)
    menu("Modify/Make Live")
    check(f"[M59-9] Make Live with an empty selection = off ({getattr(bpy.context.scene, 'allset_live', None)})",
          bpy.context.scene.allset_live is None and not C["b"].hide_select
          and (ts().use_snap, set(ts().snap_elements)) == snap_before)
    ts().use_snap = False


# --- [M72-1] F2-F6 repaint the top bar at once, in every window ------------------------------------------------

def prefs():
    return bpy.context.preferences.addons[MODULE].preferences


@named("m72_1_setup")
def _m72_1_setup():
    clear()
    select_only(create('CUBE'))
    # step 115: the kit swaps the top bar's own draw, which calls status_line.draw_left (not the class method)
    sl = mod("ui.status_line")
    C["draw_left"] = sl.draw_left
    C["drawn"] = []

    def recorder(self, context):
        C["drawn"].append((context.window.as_pointer(), prefs().menu_set))
        return C["draw_left"](self, context)
    sl.draw_left = recorder
    with override():
        bpy.ops.wm.window_new_main()   # a second main window (its own top bar)
    hover()


@named("m72_1_wait1")
def _m72_1_wait1():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


@named("m72_1_wait2")
def _m72_1_wait2():
    pass


@named("m72_1_f4")
def _m72_1_f4():
    C["windows"] = [w.as_pointer() for w in bpy.context.window_manager.windows]
    C["drawn"].clear()
    hover()
    tap('F4')


@named("m72_1_wait")
def _m72_1_wait():
    pass


@named("m72_1_check")
def _m72_1_check():
    mod("ui.status_line").draw_left = C["draw_left"]
    painted = {w for w, s in C["drawn"] if s == 'animationMenuSet'}
    check(f"[M72-1] F4 with the mouse in the view: the menu set is Animation ({prefs().menu_set})",
          prefs().menu_set == 'animationMenuSet')
    check(f"[M72-1] the top bars of both windows repaint with it, no hover ({len(painted)} of "
          f"{len(C['windows'])} windows)", len(C["windows"]) >= 2 and set(C["windows"]) <= painted)
    for w in list(bpy.context.window_manager.windows)[1:]:
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()
    hover()
    tap('F2')


# --- [M72-3] message positions, b soft select message, Make Live messages ------------------------------------------

def vm():
    return mod("ui.view_message")


def message():
    cur = vm().current()
    return cur[0] if cur else ""


@named("m72_3_setup")
def _m72_3_setup():
    clear()
    a = create('CUBE')
    create('CUBE')
    select_only(a)
    hover()
    key('G', ctrl=True)


@named("m72_3_group")
def _m72_3_group():
    space = view3d()[0].spaces.active
    check(f"[M72-3] Ctrl+G message top left in the Maya Workflow Kit view ({message()!r}, "
          f"{vm().placement(vm()._state['pos'], space)})",
          "grouped" in message() and vm().placement(vm()._state["pos"], space) == 'TOP_LEFT')
    space.overlay.show_text = True
    check(f"[M72-3] with Blender's text info on, the same message goes top centre "
          f"({vm().placement(vm()._state['pos'], space)})", vm().placement(vm()._state["pos"], space) == 'TOP_CENTER')
    space.overlay.show_text = False
    hover()
    key('H', ctrl=True)


@named("m72_3_hide")
def _m72_3_hide():
    space = view3d()[0].spaces.active
    check(f"[M72-3] Ctrl+H message top left ({message()!r})",
          "hidden" in message() and vm().placement(vm()._state["pos"], space) == 'TOP_LEFT')
    C["t"] = vm()._state["start"]
    hover()
    key('H', alt=True)


@named("m72_3_alt_h")
def _m72_3_alt_h():
    space = view3d()[0].spaces.active
    check(f"[M72-3] Alt+H message top left ({message()!r})",
          vm()._state["start"] != C["t"] and message() and vm().placement(vm()._state["pos"], space) == 'TOP_LEFT')
    C["soft0"] = ts().use_proportional_edit_objects
    vm()._state["text"] = ""
    hover()
    tap('B')


@named("m72_3_b_wait")
def _m72_3_b_wait():
    pass


@named("m72_3_b_on")
def _m72_3_b_on():
    check(f"[M72-3] b turning soft select on shows a message ({message()!r})",
          ts().use_proportional_edit_objects and not C["soft0"] and "Soft Select" in message())
    vm()._state["text"] = ""
    hover()
    tap('B')


@named("m72_3_b_wait2")
def _m72_3_b_wait2():
    pass


@named("m72_3_b_off")
def _m72_3_b_off():
    check(f"[M72-3] b turning it off shows none ({message()!r})",
          not ts().use_proportional_edit_objects and message() == "")
    for o in bpy.context.scene.objects:
        o.hide_set(False)
        o.hide_viewport = False      # step 129 (#26): Maya visibility = hide_viewport
    select_only(bpy.data.objects["pCube2"])
    menu("Modify/Make Live")
    check(f"[M72-3] Make Live on message ({message()!r})", "live" in message() and "pCube2" in message())
    for o in bpy.context.scene.objects:
        o.select_set(False)
    menu("Modify/Make Live")
    check(f"[M72-3] Make Live off message ({message()!r})", "off" in message())
    ts().use_snap = False


# --- [M72-4] In-View Messages preference off; four views: only the view the key was pressed in ----------------------

@named("m72_4_off")
def _m72_4_off():
    prefs().in_view_messages = False
    vm()._state["text"] = ""
    select_only(bpy.data.objects["pCube1"])
    hover()
    key('H', ctrl=True)


@named("m72_4_off_check")
def _m72_4_off_check():
    check(f"[M72-4] In-View Messages off: no message ({message()!r})", message() == "")
    prefs().in_view_messages = True
    key('H', shift=True)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.screen.region_quadview()


@named("m72_4_quad")
def _m72_4_quad():
    area = view3d()[0]
    quads = [r for r in area.regions if r.type == 'WINDOW']
    check(f"[M72-4] (four views: {len(quads)} view regions)", len(quads) == 4)
    C["quad"] = quads[0]
    r = quads[0]
    select_only(bpy.data.objects["pCube1"])
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    ev('H', 'PRESS', ctrl=True)
    ev('H', 'RELEASE', ctrl=True)


@named("m72_4_quad_check")
def _m72_4_quad_check():
    check(f"[M72-4] four views: the message is drawn only in the view Ctrl+H was pressed in ({message()!r})",
          message() != "" and vm()._state["region"] == C["quad"].as_pointer())
    key('H', shift=True)
    area = view3d()[0]
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.screen.region_quadview()


# --- [M73-2] Range Slider bar: move, ends, clamp, Esc / RMB cancel, Ctrl+Z ----------------------------------------

def timeline():
    for area in win().screen.areas:
        if area.type == 'DOPESHEET_EDITOR' and area.spaces.active.mode == 'TIMELINE':
            return (area, next(r for r in area.regions if r.type == 'WINDOW'),
                    next(r for r in area.regions if r.type == 'HEADER'))
    raise LookupError("no timeline")


def rb():
    return mod("ui.range_bar")


def prange():
    sc = bpy.context.scene
    return sc.frame_preview_start, sc.frame_preview_end


@named("m73_2_setup")
def _m73_2_setup():
    clear()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 200
    sc.use_preview_range = True
    sc.frame_preview_start, sc.frame_preview_end = 1, 120
    undo_base("m73_2 setup")
    redraw_all()


def bar_points():
    area, _r, header = timeline()
    bar = rb()._bars.get(area.as_pointer())
    xs, xe = rb().segment(bar, *prange())
    ppf = (bar["x1"] - bar["x0"]) / (bar["e"] - bar["s"])
    y = header.y + int((bar["y0"] + bar["y1"]) / 2)
    return {"mid": Vector((header.x + (xs + xe) / 2, y)), "end": Vector((header.x + xe - 4, y)),
            "start": Vector((header.x + xs + 4, y)), "ppf": ppf}


drag("m73_2_seg", lambda: bar_points()["mid"], lambda: bar_points()["mid"] + Vector((30 * bar_points()["ppf"], 0)),
     moves=3)


@named("m73_2_seg_check")
def _m73_2_seg_check():
    a, b = prange()
    check(f"[M73-2] dragging the grey segment moves the playback range, same length ({(a, b)})",
          b - a == 119 and 29 <= a - 1 <= 31)
    _ar, r, _h = timeline()
    v0, v1 = r.view2d.region_to_view(0, 0)[0], r.view2d.region_to_view(r.width, 0)[0]
    check(f"[M73-2] the Time Slider follows the range (view {v0:.0f}..{v1:.0f})", v0 <= a + 1 and v1 >= b - 1)
    C["after_seg"] = (a, b)


drag("m73_2_end", lambda: bar_points()["end"], lambda: bar_points()["end"] - Vector((40 * bar_points()["ppf"], 0)),
     moves=3)


@named("m73_2_end_check")
def _m73_2_end_check():
    a, b = prange()
    a0, b0 = C["after_seg"]
    check(f"[M73-2] dragging an end handle moves only that end ({(a0, b0)} -> {(a, b)})", a == a0 and 38 <= b0 - b <= 42)
    C["after_end"] = (a, b)


drag("m73_2_clamp", lambda: bar_points()["mid"], lambda: bar_points()["mid"] + Vector((300 * bar_points()["ppf"], 0)),
     moves=3)


@named("m73_2_clamp_check")
def _m73_2_clamp_check():
    a, b = prange()
    check(f"[M73-2] the range stays inside the animation range 1-200 ({(a, b)})",
          b == 200 and b - a == C["after_end"][1] - C["after_end"][0])
    C["before_esc"] = (a, b)
    pts = bar_points()
    C["esc_p"] = pts["mid"]
    move_to(pts["mid"])
    ev('LEFTMOUSE', 'PRESS', x=int(pts["mid"].x), y=int(pts["mid"].y))


@named("m73_2_esc_move")
def _m73_2_esc_move():
    p = C["esc_p"] - Vector((50 * bar_points()["ppf"], 0))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))


@named("m73_2_esc")
def _m73_2_esc():
    C["during"] = prange()
    tap('ESC')
    ev('LEFTMOUSE', 'RELEASE', x=int(C["esc_p"].x), y=int(C["esc_p"].y))


@named("m73_2_esc_check")
def _m73_2_esc_check():
    check(f"[M73-2] Esc cancels the drag ({C['during']} -> {prange()})",
          C["during"] != C["before_esc"] and prange() == C["before_esc"])
    p = C["esc_p"]
    move_to(p)
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y))


@named("m73_2_rmb_move")
def _m73_2_rmb_move():
    p = C["esc_p"] - Vector((50 * bar_points()["ppf"], 0))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))


@named("m73_2_rmb")
def _m73_2_rmb():
    C["during"] = prange()
    ev('RIGHTMOUSE', 'PRESS')
    ev('RIGHTMOUSE', 'RELEASE')
    ev('LEFTMOUSE', 'RELEASE', x=int(C["esc_p"].x), y=int(C["esc_p"].y))


@named("m73_2_rmb_check")
def _m73_2_rmb_check():
    check(f"[M73-2] RMB cancels the drag ({C['during']} -> {prange()})",
          C["during"] != C["before_esc"] and prange() == C["before_esc"])
    hover()
    key('Z', ctrl=True)


@named("m73_2_undo_check")
def _m73_2_undo_check():
    check(f"[M73-2] Ctrl+Z takes the last drag back ({prange()} vs before {C['after_end']})", prange() == C["after_end"])


# --- [M76-1..4] Maya selection priority (curve 4, joint 9, IK handle 10 over meshes) ------------------------------

def sel():
    return sorted(o.name for o in bpy.context.selected_objects)


def act():
    ob = bpy.context.view_layer.objects.active
    return ob and ob.name


def click_at(p, **mods):
    p = Vector(p)
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y), **mods)
    ev('LEFTMOUSE', 'RELEASE', x=int(p.x), y=int(p.y), **mods)


def view_rot():
    return view3d()[1].data.view_rotation


def make_circle(name):
    cu = bpy.data.curves.new(name, 'CURVE')
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(3)
    r = 0.4 * k()
    for p, (x, y) in zip(sp.bezier_points, ((r, 0), (0, r), (-r, 0), (0, -r))):
        p.co = (x, y, 0)
        p.handle_left_type = p.handle_right_type = 'AUTO'
    sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def place(ob, t):
    """On the line eye -> origin: t > 0 in front of the cube, t < 0 behind; facing the view."""
    ob.location = (eye() - Vector()) * t
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = view_rot()
    bpy.context.view_layer.update()


def circle_point():
    ob = C["circle"]
    return screen(ob.matrix_world @ ob.data.splines[0].bezier_points[0].co)


def cube_spot():
    c = screen(Vector())
    far = max((screen(C["cube"].matrix_world @ v.co) for v in C["cube"].data.vertices), key=lambda p: (p - c).length)
    return c + (far - c) * 0.8


@named("m76_setup")
def _m76_setup():
    clear()
    mod("ui.view_message")._state["text"] = ""
    C["cube"] = create('CUBE')
    C["circle"] = make_circle("ctrl")
    for o in bpy.context.scene.objects:
        o.select_set(False)
    # step 135: the viewport beside the wider dock is narrower, so the 0.8 cm circle was ~13 px across and its centre
    # lay within the 5 px (x UI scale) pick radius of its drawn chords. Zoom in 2x for this section (restored at m76_2_ik).
    rv3d = view3d()[1].data
    C["m76_view"] = rv3d.view_distance
    rv3d.view_distance *= 0.5
    view3d()[0].tag_redraw()


@named("m76_setup_click")
def _m76_setup_click():
    # one tick after the zoom (the view matrices update when the view draws); a little in front of the 1 cm cube
    place(C["circle"], 0.3 * 0.01)
    set_tool("builtin.select_box")
    click_at(circle_point())


@named("m76_1_front")
def _m76_1_front():
    check(f"[M76-1] the control curve in front of the mesh: click = the curve ({sel()}, lead {act()})",
          sel() == ["ctrl"] and act() == "ctrl")
    place(C["circle"], -0.35 * 0.01)
    click_at(circle_point())


@named("m76_1_behind")
def _m76_1_behind():
    check(f"[M76-1] the curve behind the mesh: click on its line = still the curve ({sel()})", sel() == ["ctrl"])
    # a click on the mesh more than the pick radius from the curve line: 9 px in from the line, or the circle's centre
    # when the circle is smaller on screen (the view is narrower beside a solid dock, step 112)
    p = circle_point()
    c = screen(C["circle"].matrix_world.translation)
    away = p + (c - p).normalized() * min(9, (c - p).length)
    C["away"] = away
    click_at(away)


@named("m76_1_away")
def _m76_1_away():
    check(f"[M76-1] off the curve (9 px or its centre), over the mesh = the mesh ({sel()})", sel() == ["pCube1"])
    click_at(circle_point(), shift=True)


@named("m76_3_shift")
def _m76_3_shift():
    check(f"[M76-3] Shift+click the curve = toggle on ({sel()}, lead {act()})", sel() == ["ctrl", "pCube1"] and act() == "ctrl")
    click_at(circle_point(), shift=True)


@named("m76_3_shift2")
def _m76_3_shift2():
    check(f"[M76-3] Shift+click again = toggle off ({sel()})", sel() == ["pCube1"])
    click_at(circle_point(), shift=True, ctrl=True)


@named("m76_3_add")
def _m76_3_add():
    check(f"[M76-3] Ctrl+Shift+click = add ({sel()})", sel() == ["ctrl", "pCube1"])
    click_at(circle_point(), shift=True, ctrl=True)


@named("m76_3_add2")
def _m76_3_add2():
    check(f"[M76-3] Ctrl+Shift+click again keeps it ({sel()})", sel() == ["ctrl", "pCube1"])
    click_at(circle_point(), ctrl=True)


@named("m76_3_ctrl")
def _m76_3_ctrl():
    check(f"[M76-3] Ctrl+click = deselect ({sel()})", sel() == ["pCube1"])
    set_tool("builtin.select")   # the Tweak tool
    C["loc"] = C["circle"].location.copy()


drag("m76_3_tweak", circle_point, lambda: circle_point() + Vector((40, 25)), moves=4)


@named("m76_3_tweak_check")
def _m76_3_tweak_check():
    moved = (C["circle"].location - C["loc"]).length
    check(f"[M76-3] Tweak tool: press on the curve and drag = the curve is picked and moves ({sel()}, moved "
          f"{moved / k():.2f} cm)", sel() == ["ctrl"] and moved > 0.05 * k())
    C["circle"].location = C["loc"]
    bpy.context.view_layer.update()
    set_tool("builtin.select_box")
    prefs().select_priority = False
    click_at(circle_point())


@named("m76_4_off")
def _m76_4_off():
    check(f"[M76-4] Selection Priority off: Blender's depth pick, the mesh in front wins ({sel()})", sel() == ["pCube1"])
    # meshes overlapping on screen: Blender's repeated-click cycling (still with the option on)
    prefs().select_priority = True
    C["circle"].hide_set(True)
    b = create('CUBE')
    b.location = (eye() - Vector()) * 0.004
    bpy.context.view_layer.update()
    for o in bpy.context.scene.objects:
        o.select_set(False)
    C["spot"] = screen(Vector())
    click_at(C["spot"])


@named("m76_4_cycle1")
def _m76_4_cycle1():
    C["first"] = sel()
    click_at(C["spot"])


@named("m76_4_cycle2")
def _m76_4_cycle2():
    check(f"[M76-4] a second click on overlapping meshes picks the other one ({C['first']} -> {sel()})",
          len(C["first"]) == 1 and len(sel()) == 1 and sel() != C["first"])
    # [M76-2] a rig: a bone in front of the mesh, an IK handle over the bone
    for o in list(bpy.context.scene.objects):
        if o.name not in ("pCube1",):
            bpy.data.objects.remove(o)
    arm = bpy.data.objects.new("rig", bpy.data.armatures.new("rig"))
    bpy.context.scene.collection.objects.link(arm)
    for o in bpy.context.scene.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = arm
    up = view_rot() @ Vector((0, 1, 0))
    right = view_rot() @ Vector((1, 0, 0))
    base = (eye() - Vector()) * 0.003
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm.data.edit_bones.new("joint1")
        eb.head, eb.tail = base - up * 0.4 * k(), base + up * 0.4 * k()
        eb2 = arm.data.edit_bones.new("joint2")
        eb2.head, eb2.tail = base + right * 2.5 * k(), base + right * 2.5 * k() + up * 0.5 * k()
        bpy.ops.object.mode_set(mode='OBJECT')
    C.update(arm=arm, base=base, up=up, right=right)
    # the thick part of the octahedral bone: 0.1 of its length from the head, a little off the axis
    C["thick"] = screen(base - up * 0.4 * k() + up * 0.08 * k() + right * 0.05 * k())
    click_at(C["thick"])


@named("m76_2_bone")
def _m76_2_bone():
    check(f"[M76-2] a click on the bone's thick part in front of the mesh = the armature ({sel()})", sel() == ["rig"])
    click_at(C["thick"], shift=True)


@named("m76_3_bone_shift")
def _m76_3_bone_shift():
    check(f"[M76-3] Shift+click on the bone toggles it off ({sel()})", sel() == [])
    # an IK handle (ikHandle1 empty = an IK constraint target) drawn across the bone
    ik = bpy.data.objects.new("ikHandle1", None)
    ik.empty_display_type = 'PLAIN_AXES'
    ik.empty_display_size = 0.3 * k()
    ik.location = C["base"]
    bpy.context.scene.collection.objects.link(ik)
    con = C["arm"].pose.bones["joint2"].constraints.new('IK')
    con.target = ik
    con.influence = 0.0
    bpy.context.view_layer.update()
    C["ik"] = ik
    click_at(screen(C["base"] + C["right"] * 0.2 * k()))


@named("m76_2_ik")
def _m76_2_ik():
    check(f"[M76-2] a click where the IK handle crosses the bone = the IK handle first ({sel()})", sel() == ["ikHandle1"])
    if "m76_view" in C:
        view3d()[1].data.view_distance = C.pop("m76_view")


# --- [M77-1] F9 + Insert: cursor tool, "Pivot edit on", click / drag the pivot, Insert again ----------------------
# --- [M77-3] Insert on + F8 / Tab leaves it; back in edit mode the old tool; W menu World ------------------------

def cursor():
    return bpy.context.scene.cursor


@named("m77_1_setup")
def _m77_1_setup():
    clear()
    ob = create('CUBE')
    select_only(ob)
    cursor().location = (0, 0, 0)
    cursor().rotation_mode = 'XYZ'
    cursor().rotation_euler = (0, 0, 0)
    C["ob"] = ob
    hover()
    tap('F9')


@named("m77_1_w")
def _m77_1_w():
    check(f"[M77-1] F9 = vertex mode ({bpy.context.mode})", bpy.context.mode == 'EDIT_MESH')
    with override():     # step 129: a new Maya primitive enters component mode with nothing selected
        bpy.ops.mesh.select_all(action='SELECT')
    hover()
    tap('W')


@named("m77_1_insert")
def _m77_1_insert():
    hover()
    tap('INSERT')


@named("m77_1_insert_check")
def _m77_1_insert_check():
    check(f"[M77-1] Insert: the toolbar shows the cursor tool ({tool_id()}), pivot = cursor ({ts().transform_pivot_point})",
          tool_id() == "builtin.cursor" and ts().transform_pivot_point == 'CURSOR')
    # the Help Line text is the operator's report ("Pivot edit on", operators/hold.py ALLSET_OT_pivot_toggle):
    # Python can't read reports (RNA looks Operator.report up before the class), so the state stands for it
    check("[M77-1] pivot edit on (its report says 'Pivot edit on')", mod("operators.hold").COMPONENT.on)
    # the +X side face (camera on +x / -y / +z), clicked at its middle: since #207 a pivot click picks the component
    # (vertices and edges win near their own screen position, a face gives its centre)
    # a close view (as in gui_pivot_tap_components): on a small cube the vertex hits cover the face
    rv3d = view3d()[0].spaces.active.region_3d
    C["m77_view"] = (rv3d.view_location.copy(), rv3d.view_distance)
    rv3d.view_location, rv3d.view_distance = (0, 0, 0), 6 * k()
    C["face_p"] = screen(Vector((0.5 * k(), 0.0, 0.0)))
    click_at(C["face_p"])


@named("m77_1_clicked")
def _m77_1_clicked():
    loc, z = cursor().location.copy(), cursor().matrix.to_3x3().col[2]
    # a component of that face: its centre, or an edge / vertex of it when one is near the click on screen
    on_face = abs(loc.x - 0.5 * k()) < 0.02 * k() and abs(loc.y) <= 0.5 * k() + 1e-6 and abs(loc.z) <= 0.5 * k() + 1e-6
    check(f"[M77-1] a click on a face puts the cursor on a component of it ({cm(loc)} cm), its axis turned to it "
          f"(Z {tuple(round(v, 2) for v in z)})", on_face and z.x > 0.5)
    rv3d = view3d()[0].spaces.active.region_3d
    rv3d.view_location, rv3d.view_distance = C.pop("m77_view")
    C["loc"] = loc


drag("m77_1_drag", lambda: screen(Vector((0.5 * k(), 0.15 * k(), -0.15 * k()))),
     lambda: screen(Vector((0.5 * k(), 0.15 * k(), -0.15 * k()))) + Vector((25, 12)), moves=4)


@named("m77_1_dragged")
def _m77_1_dragged():
    check(f"[M77-1] dragging moves the cursor with the mouse ({cm(cursor().location)} cm)",
          (cursor().location - C["loc"]).length > 0.01 * k())
    C["pivot"] = cursor().location.copy()
    hover()
    tap('INSERT')


@named("m77_1_off")
def _m77_1_off():
    slot = bpy.context.scene.transform_orientation_slots[1].type
    with override():
        centre, frame, _o = mod("ui.manipulator").pivot_frame(bpy.context, 'TRANSLATE')
    zx = abs(Vector(frame.col[2]).x) if hasattr(frame, "col") else 0
    check(f"[M77-1] Insert again: the Move tool back ({tool_id()}), manipulator at the pivot ({cm(centre)} cm), "
          f"face-normal axes ({slot})",
          tool_id() == "builtin.move" and (centre - C["pivot"]).length < 1e-6 and slot == "Maya Pivot")
    hover()
    tap('INSERT')


@named("m77_3_f8")
def _m77_3_f8():
    check("[M77-3] (Insert on)", tool_id() == "builtin.cursor")
    hover()
    tap('F8')


@named("m77_3_f8_check")
def _m77_3_f8_check():
    check(f"[M77-3] F8 to object mode closes the pivot edit ({bpy.context.mode}, {ts().transform_pivot_point})",
          bpy.context.mode == 'OBJECT' and ts().transform_pivot_point != 'CURSOR'
          and not mod("operators.hold").COMPONENT.on)
    hover()
    tap('F8')


@named("m77_3_back")
def _m77_3_back():
    pass


@named("m77_3_back_check")
def _m77_3_back_check():
    check(f"[M77-3] back in edit mode: the old tool (Move) ({tool_id()})",
          bpy.context.mode == 'EDIT_MESH' and tool_id() == "builtin.move")
    hover()
    tap('INSERT')


@named("m77_3_menu")
def _m77_3_menu():
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')   # the header's mode menu (Tab is Blender's menu search here)


@named("m77_3_menu_check")
def _m77_3_menu_check():
    check(f"[M77-3] leaving edit mode another way (mode menu) also ends it ({bpy.context.mode}, "
          f"{ts().transform_pivot_point})", bpy.context.mode == 'OBJECT' and not mod("operators.hold").COMPONENT.on)
    hover()
    tap('F8')


@named("m77_3_tab_back")
def _m77_3_tab_back():
    bpy.context.scene.transform_orientation_slots[1].type = 'NORMAL'


gesture("m77_3_w_world", 'W', "W")


@named("m77_3_world_check")
def _m77_3_world_check():
    check(f"[M77-3] the W menu turns the Move axis back to World ({bpy.context.scene.transform_orientation_slots[1].type})",
          bpy.context.scene.transform_orientation_slots[1].type == 'GLOBAL')
    hover()
    tap('F8')


# --- [M78-1] Shift+Q tap = select tool + mesh edit mode; hold + LMB = the pick mask menu ------------------------
# --- [M78-2] Alt+Q hold + LMB = N/E/S/W components, the view doesn't turn ---------------------------------------

def mask():
    return tuple(ts().mesh_select_mode)


@named("m78_1_setup")
def _m78_1_setup():
    clear()
    select_only(create('CUBE'))
    set_tool("builtin.move")
    hover()
    ev('Q', 'PRESS', shift=True)
    ev('Q', 'RELEASE', shift=True)


@named("m78_1_tap_wait")
def _m78_1_tap_wait():
    pass


@named("m78_1_tap_check")
def _m78_1_tap_check():
    check(f"[M78-1] Shift+Q tap = the select tool in mesh edit mode ({bpy.context.mode}, {tool_id()})",
          bpy.context.mode == 'EDIT_MESH' and tool_id() == "builtin.select_box")
    ts().mesh_select_mode = (True, False, False)


gesture("m78_1_faces", 'Q', "SE", mods={"shift": True})


@named("m78_1_faces_check")
def _m78_1_faces_check():
    draw = mod("marking.draw")
    menus = mod("marking.menus")
    faces = menus.SELECT_COMPONENT.radial["SE"][1]
    check(f"[M78-1] hold + LMB, SE Faces turns faces on in the pick mask ({mask()})", mask() == (True, False, True))
    check(f"[M78-1] the Faces item shows its check box state ({draw.checked(faces)})", draw.checked(faces) is True)
    greyed = [lab for lab, act in menus.SELECT_COMPONENT.radial.values() if act is None]
    check(f"[M78-1] items with no Blender meaning are greyed (no action: {greyed})", "Hulls" in greyed and "Handles" in greyed)


gesture("m78_1_faces_off", 'Q', "SE", mods={"shift": True})


@named("m78_1_off_check")
def _m78_1_off_check():
    check(f"[M78-1] SE again turns faces off ({mask()})", mask() == (True, False, False))
    C["view"] = view3d()[1].data.view_matrix.copy()


gesture("m78_2_e", 'Q', "E", mods={"alt": True})


@named("m78_2_e_check")
def _m78_2_e_check():
    same = all(abs(a - b) < 1e-9 for ra, rb in zip(C["view"], view3d()[1].data.view_matrix) for a, b in zip(ra, rb))
    check(f"[M78-2] Alt+Q hold + LMB east = Edges ({mask()})", mask() == (False, True, False))
    check("[M78-2] with Alt held the view doesn't turn", same)


gesture("m78_2_s", 'Q', "S", mods={"alt": True})


@named("m78_2_s_check")
def _m78_2_s_check():
    check(f"[M78-2] south = Faces ({mask()})", mask() == (False, False, True))


gesture("m78_2_n", 'Q', "N", mods={"alt": True})


@named("m78_2_n_check")
def _m78_2_n_check():
    check(f"[M78-2] north = Vertices ({mask()})", mask() == (True, False, False))
    C["uv_mode"] = None


gesture("m78_2_w", 'Q', "W", mods={"alt": True})


@named("m78_2_w_check")
def _m78_2_w_check():
    uv = [w for w in bpy.context.window_manager.windows if any(a.ui_type == 'UV' for a in w.screen.areas)]
    check(f"[M78-2] west = UVs (= F12: a UV Editor shows, {len(uv)} window(s))", len(uv) >= 1)
    for w in list(bpy.context.window_manager.windows)[1:]:
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()
    hover()
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')


# --- [M78-4] Shift+G at several places = a cube at each; also in a side ortho view -----------------------------------

@named("m78_4_setup")
def _m78_4_setup():
    clear()
    with override():
        bpy.ops.allset.create('EXEC_DEFAULT', True, kind='CUBE')   # registered like a menu click
    C["spots"] = [Vector((3 * k(), 2 * k(), 0)), Vector((-4 * k(), 1 * k(), 0)), Vector((1 * k(), -5 * k(), 0))]
    C["made"] = []


for _n in range(3):
    @named(f"m78_4_spot{_n}")
    def _m78_4_spot(n=_n):
        move_to(screen(C["spots"][n]))
        ev('G', 'PRESS', shift=True)
        ev('G', 'RELEASE', shift=True)

    @named(f"m78_4_spot{_n}_check")
    def _m78_4_spot_check(n=_n):
        ob = bpy.context.view_layer.objects.active
        C["made"].append(ob.matrix_world.translation.copy() if ob else None)


@named("m78_4_check")
def _m78_4_check():
    # 0.15: one screen pixel is ~0.07 cm at this zoom in the view beside the solid dock (step 112)
    ok = all(m is not None and (m - s).length < 0.15 * k() for m, s in zip(C["made"], C["spots"]))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    check(f"[M78-4] Shift+G at three grid spots = a cube at each ({[cm(m) if m else None for m in C['made']]}, "
          f"{len(meshes)} cubes)", ok and len(meshes) == 4)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.view3d.view_axis(type='FRONT')
    C["side"] = Vector((2 * k(), 0, 3 * k()))


@named("m78_4_side")
def _m78_4_side():
    _a, region = view3d()
    p = location_3d_to_region_2d(region, region.data, C["side"])
    move_to(Vector((region.x + p.x, region.y + p.y)))
    # where the mouse really is: move_to ends at (int(x) + 1, int(y)); one pixel is ~0.06 cm in the viewport beside
    # the wider dock (step 135), more than the 0.05 cm tolerance
    C["side_mouse"] = region_2d_to_location_3d(region, region.data, Vector((int(region.x + p.x) + 1 - region.x,
                                                                             int(region.y + p.y) - region.y)), Vector())
    ev('G', 'PRESS', shift=True)
    ev('G', 'RELEASE', shift=True)


@named("m78_4_side_check")
def _m78_4_side_check():
    ob = bpy.context.view_layer.objects.active
    got = ob.matrix_world.translation if ob else Vector((99, 99, 99))
    want = C["side_mouse"]
    check(f"[M78-4] front ortho view: the mouse spot at the origin's depth ({cm(got)} cm, want {cm(want)}, "
          f"aimed at {cm(C['side'])})",
          abs(got.x - want.x) < 0.01 * k() and abs(got.z - want.z) < 0.01 * k() and abs(got.y) < 1e-6
          and (want - C["side"]).length < 0.15 * k())
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.view3d.view_persportho()
        bpy.ops.view3d.view_axis(type='TOP')
    C["persp"] = False


# --- [M78-5] Ctrl+Shift+C = camera1 from the view (Look Through = the same picture); ortho view -> ortho camera ------

@named("m78_5_persp")
def _m78_5_persp():
    clear()
    _area, region = view3d()
    rv3d = region.data
    rv3d.view_perspective = 'PERSP'
    rv3d.view_rotation = Quaternion((0.82, 0.42, 0.18, 0.35)).normalized()
    rv3d.view_distance = 45 * k()
    bpy.context.view_layer.update()
    hover()
    ev('C', 'PRESS', shift=True, ctrl=True)
    ev('C', 'RELEASE', shift=True, ctrl=True)


@named("m78_5_persp_check")
def _m78_5_persp_check():
    cams = [o for o in bpy.context.scene.objects if o.type == 'CAMERA']
    area, region = view3d()
    space = area.spaces.active
    ok = len(cams) == 1
    if ok:
        cam = cams[0]
        d = cam.matrix_world @ region.data.view_matrix
        err = max(abs(d[i][j] - (1.0 if i == j else 0.0)) for i in range(4) for j in range(4))
        fov_view = 2 * math.atan(72 / (2 * space.lens))
        fov_cam = 2 * math.atan(cam.data.sensor_width / (2 * cam.data.lens))
        check(f"[M78-5] Ctrl+Shift+C = {cam.name} at the view (matrix error {err:.1e}), same field of view "
              f"({math.degrees(fov_cam):.2f} vs {math.degrees(fov_view):.2f} deg)",
              cam.name == "camera1" and err < 1e-4 and abs(fov_cam - fov_view) < 1e-4)
    else:
        check(f"[M78-5] Ctrl+Shift+C makes one camera ({[o.name for o in cams]})", False)
    region.data.view_perspective = 'ORTHO'
    hover()
    ev('C', 'PRESS', shift=True, ctrl=True)
    ev('C', 'RELEASE', shift=True, ctrl=True)


@named("m78_5_ortho_check")
def _m78_5_ortho_check():
    cam = bpy.context.view_layer.objects.active
    check(f"[M78-5] from an ortho view: an orthographic camera ({cam and cam.name}, {cam and cam.data.type})",
          cam is not None and cam.type == 'CAMERA' and cam.data.type == 'ORTHO')
    region = view3d()[1]
    region.data.view_perspective = 'PERSP'


# --- [M62-1..3] Set Driven Key window: load, key, drive; held values; Go to Previous / Next; the curve -------------
# Dialog / sidebar buttons run their operators; Channel Box channel clicks = its channel selection, typed values =
# its Enter path (channel_box.apply_entry).

def cb():
    return mod("ui.channel_box")


def sdk():
    return mod("operators.driven_key")


def sdk_state():
    return bpy.context.window_manager.allset_sdk


def ry(ob):
    bpy.context.view_layer.update()
    return math.degrees(ob.rotation_euler[1])


@named("m62_1_setup")
def _m62_1_setup():
    clear()
    loc = create('LOCATOR')
    cube = create('CUBE')
    C.update(loc=loc, cube=cube)
    r = menu("Key/Set Driven Key/Set...")
    st = sdk_state()
    check(f"[M62-1] Key > Set Driven Key > Set... opens the window in the dock ({r}, open {st.open})", st.open)
    rec = LayoutRecorder()
    with override():
        mod("ui.set_driven_key").draw(rec, bpy.context)
    C["sdk_ui"] = rec.out
    select_only(loc)
    cb().set_selected_channels(["tx"])
    with override():
        bpy.ops.allset.sdk_load(which='DRIVER')
    select_only(cube)
    cb().set_selected_channels(["ry"])
    with override():
        bpy.ops.allset.sdk_load(which='DRIVEN')
        bpy.ops.allset.sdk_key()
    check(f"[M62-1] driver locator1 Translate X, driven pCube1 Rotate Y, Key = a driven key "
          f"({sdk().driver_node(st) and sdk().driver_node(st).name}, {st.driver_attr}, {sdk().driven_keys(st)})",
          sdk().driver_node(st) == loc and st.driver_attr == "tx" and sdk().driven_keys(st) == ["ry"]
          and sdk().sdk_fcurve(cube, "ry") is not None)
    ui = C["sdk_ui"]
    if ui:
        missing = [w for w in ("Key", "Load Driver", "Load Driven", "Close") if not any(w in t for t in ui)]
        check(f"[M62-1] the window has Key / Load Driver / Load Driven / Close (missing {missing})", not missing)
    select_only(loc)
    n = cb().apply_entry("tx", "1")
    select_only(cube)
    cb().apply_entry("ry", "90")
    with override():
        bpy.ops.allset.sdk_key()
    select_only(loc)
    cb().apply_entry("tx", "0.5")
    check(f"[M62-1] moving the driver drives the driven (tx 0.5 -> ry {ry(cube):.2f}), its Channel Box row = driven "
          f"({cb().channel_state(cube, 'ry')})", abs(ry(cube) - 45) < 0.5 and cb().channel_state(cube, "ry") == 'DRIVEN')


@named("m62_2_held")
def _m62_2_held():
    loc, cube = C["loc"], C["cube"]
    select_only(loc)
    cb().apply_entry("tx", "1")
    select_only(cube)
    cb().apply_entry("ry", "60")
    check(f"[M62-2] with the window open a typed driven value stays until Key ({ry(cube):.2f})", abs(ry(cube) - 60) < 0.5)
    with override():
        bpy.ops.allset.sdk_close()
    check(f"[M62-2] closing the window: the un-keyed pose goes back to the curve ({ry(cube):.2f})", abs(ry(cube) - 90) < 0.5)
    cube.rotation_euler[1] = math.radians(10)   # what a manipulator drag writes
    check(f"[M62-2] a manipulator change on a driven channel goes back to the driver ({ry(cube):.2f})",
          abs(ry(cube) - 90) < 0.5)


@named("m62_3_go")
def _m62_3_go():
    loc, cube = C["loc"], C["cube"]
    menu("Key/Set Driven Key/Set...")
    select_only(cube)
    r1 = menu("Key/Set Driven Key/Go to Previous")
    x1 = loc.location.x / k()
    r2 = menu("Key/Set Driven Key/Go to Next")
    x2 = loc.location.x / k()
    check(f"[M62-3] Go to Previous / Next move the driver to the neighbouring keys (tx {x1:.2f} -> {x2:.2f}; {r1}, {r2})",
          abs(x1 - 0.0) < 1e-4 and abs(x2 - 1.0) < 1e-4)
    fc = sdk().sdk_fcurve(cube, "ry")
    kps = list(fc.keyframe_points)
    # step 226: the kit writes Maya 2026 auto tangents itself (ALIGNED handles, operators/driven_key.maya_auto)
    check(f"[M62-3] the SDK curve is a smooth S, flat at the ends (Bezier, Maya auto, constant extrapolation: "
          f"{[(p.interpolation, p.handle_left_type) for p in kps]}, {fc.extrapolation})",
          all(p.interpolation == 'BEZIER' and p.handle_left_type in ('ALIGNED', 'AUTO_CLAMPED') for p in kps)
          and fc.extrapolation == 'CONSTANT'
          and all(abs(p.handle_left[1] - p.co[1]) < 1e-6 and abs(p.handle_right[1] - p.co[1]) < 1e-6 for p in (kps[0], kps[-1])))
    with override():
        bpy.ops.allset.sdk_close()


# --- [M62-4] control, Shift armature, Ctrl+Tab pose mode, joint, Constrain > Orient -> on the bone ------------------

@named("m62_4_setup")
def _m62_4_setup():
    clear()
    ctrl = create('LOCATOR')
    arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
    bpy.context.scene.collection.objects.link(arm)
    select_only(arm)
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
        for i in (1, 2):
            eb = arm.data.edit_bones.new(f"joint{i}")
            eb.head, eb.tail = (0, 0, (i - 1) * k()), (0, 0, i * k())
        bpy.ops.object.mode_set(mode='OBJECT')
    select_only(ctrl, arm)
    C.update(ctrl=ctrl, arm=arm)
    hover()
    key('TAB', ctrl=True)


@named("m62_4_pose")
def _m62_4_pose():
    check(f"[M62-4] Ctrl+Tab = pose mode ({bpy.context.mode})", bpy.context.mode == 'POSE')
    arm = C["arm"]
    for pb in arm.pose.bones:
        cb().set_bone_selected(pb, pb.name == "joint2")
    arm.data.bones.active = arm.data.bones["joint2"]
    r = menu("Constrain/Orient")
    cons = arm.pose.bones["joint2"].constraints
    check(f"[M62-4] Constrain > Orient puts the constraint on the joint (bone), not the armature ({r}, "
          f"{[c.type for c in cons]}, armature {len(arm.constraints)})",
          # step 233: a joint that follows an object's rotation is constrained to Maya's axes helper of the control
          # ("<owner>_<node>_<target>Axes", operators/constrain_multi.py), which follows the control
          len(cons) == 1 and cons[0].type == 'COPY_ROTATION' and cons[0].target is not None
          and (cons[0].target == C["ctrl"] or cons[0].target.name.endswith(C["ctrl"].name + "Axes"))
          and not arm.constraints)
    C["ctrl"].select_set(False)
    for pb in arm.pose.bones:
        cb().set_bone_selected(pb, pb.name == "joint1")
    arm.data.bones.active = arm.data.bones["joint1"]
    try:
        r2 = menu("Constrain/Orient")
    except RuntimeError as ex:
        r2 = {str(ex)}
    # the Help Line text is the operator's warning report (rig_tools.CONSTRAIN_HINT; Python can't read reports)
    check(f"[M62-4] no target: nothing is made, the 'Select the control first, then the joint last' warning ({r2})",
          not arm.pose.bones["joint1"].constraints and len(arm.pose.bones["joint2"].constraints) == 1)
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')


# --- [M62-5] Add / Edit / Delete Attribute ------------------------------------------------------------------------

@named("m62_5_attr")
def _m62_5_attr():
    clear()
    ob = create('CUBE')
    select_only(ob)
    with override():   # the Add Attribute dialog's OK with these fields
        r = bpy.ops.allset.add_attribute(long_name="fingerCurl", data_type='FLOAT', use_min=True, minimum=0,
                                           use_max=True, maximum=10, default=0)
    check(f"[M62-5] Modify > Add Attribute: Channel Box row 'Finger Curl' ({r}, "
          f"{cb().channel_label('cp:fingerCurl')}, visible {'cp:fingerCurl' in cb()._visible_channels(ob)})",
          cb().channel_label("cp:fingerCurl") == "Finger Curl" and "cp:fingerCurl" in cb()._visible_channels(ob))
    cb().apply_entry("cp:fingerCurl", "25")
    check(f"[M62-5] a value outside Min / Max is clamped ({ob['fingerCurl']})", abs(ob["fingerCurl"] - 10) < 1e-6)
    for kind in ('INT', 'BOOL'):
        with override():
            bpy.ops.allset.add_attribute(long_name=f"a{kind.lower()}", data_type=kind, default=1)
    check(f"[M62-5] Integer / Boolean attributes ({type(ob['aint']).__name__}, {type(ob['abool']).__name__})",
          isinstance(ob["aint"], int) and isinstance(ob["abool"], bool))
    ob.keyframe_insert('["fingerCurl"]', frame=1)
    cb().set_selected_channels(["cp:fingerCurl"])
    with override():
        bpy.ops.allset.edit_attribute(attribute="fingerCurl", long_name="curl", data_type='FLOAT', use_min=True,
                                        minimum=0, use_max=True, maximum=10, default=0)
    check(f"[M62-5] Edit Attribute renames it and its keys follow ({sorted(k for k in ob.keys() if not k.startswith('_'))})",
          "curl" in ob.keys() and "fingerCurl" not in ob.keys() and cb().fcurve(ob, "cp:curl") is not None)
    cb().set_selected_channels(["cp:curl"])
    with override():
        bpy.ops.allset.delete_attribute()
    check("[M62-5] Delete Attributes removes the selected channel and its keys",
          "curl" not in ob.keys() and cb().fcurve(ob, "cp:curl") is None)


# --- [M62-6] duplicate a head, edit it, target then base -> Deform > Blend Shape -----------------------------------

@named("m62_6_blend")
def _m62_6_blend():
    clear()
    head = create('SPHERE')
    select_only(head)
    hover()
    key('D', ctrl=True)


@named("m62_6_edit")
def _m62_6_edit():
    head = bpy.data.objects["pSphere1"]
    target = bpy.context.view_layer.objects.active
    check(f"[M62-6] Ctrl+D duplicates the head ({target.name})", target is not head and target.type == 'MESH')
    target.data.vertices[0].co.z += 0.3 * k()
    select_only(target, head)   # target first, the base last
    r = menu("Deform/Blend Shape")
    keys = [kb.name for kb in head.data.shape_keys.key_blocks] if head.data.shape_keys else []
    check(f"[M62-6] Deform > Blend Shape: Basis + a shape key named after the target, value 0 ({r}, {keys})",
          keys == ["Basis", target.name] and head.data.shape_keys.key_blocks[target.name].value == 0)
    other = create('CUBE')
    select_only(other, head)
    try:
        r2 = menu("Deform/Blend Shape")
    except RuntimeError as ex:
        r2 = str(ex)
    # the error text is the operator's ERROR report ("different vertex count", headless test_step62 reads it)
    check(f"[M62-6] different vertex counts: refused with an error, no shape added ({r2})",
          r2 != {'FINISHED'} and [kb.name for kb in head.data.shape_keys.key_blocks] == ["Basis", "pSphere2"])


# --- [M63-2] Modeling Toolkit buttons; greyed rows have their notice -----------------------------------------------

def mtk():
    return mod("ui.modeling_toolkit")


def counts(ob):
    return len(ob.data.vertices), len(ob.data.polygons)


def edit_cube(select_faces=None):
    clear()
    ob = create('CUBE')
    select_only(ob)
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
    if select_faces:   # faces are a face-mode selection (in vertex mode Maya extrudes the vertices, step 139)
        bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(ob.data)
    for f in bm.faces:
        f.select_set(False)
    bm.faces.ensure_lookup_table()
    for i in (select_faces or []):
        bm.faces[i].select_set(True)
    bmesh.update_edit_mesh(ob.data)
    return ob


def object_mode():
    if bpy.context.mode != 'OBJECT':
        with override():
            bpy.ops.object.mode_set(mode='OBJECT')


@named("m63_2_paths")
def _m63_2_paths():
    mm = mod("ui.menu_map").MAP
    paths = [p for _l, p, _i in (*mtk().MESH, *mtk().COMPONENTS, *mtk().TOOLS) if p]
    missing = [p for p in paths if p not in mm]
    check(f"[M63-2] every Mesh / Components / Tools button runs its Maya menu action (unmapped {missing})", not missing)
    notes = mod("ui.notices").PANEL_NOTICES
    grey = ["Modeling Toolkit/Highlight Backfaces", "Modeling Toolkit/Selection Constraint",
            "Modeling Toolkit/Transform Constraint", "Modeling Toolkit/UV"]
    check(f"[M63-2] greyed rows (Highlight Backfaces, Selection / Transform Constraint, UV) carry a tooltip / Help Line "
          f"notice ({[g for g in grey if g not in notes]} missing)", all(g in notes for g in grey))
    check("[M63-2] Target Weld is a real tool now (step 64), not greyed", mm.get("Mesh Tools/Target Weld", (None,))[0] == "tool")
    ob = edit_cube([0])
    C["ob"] = ob
    with override():
        r = bpy.ops.allset.extrude('INVOKE_DEFAULT')
    rec = mod("operators.extrude").current(ob)
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.mode_set(mode='EDIT')
    check(f"[M63-2] Extrude: the face is extruded at once as polyExtrudeFace1 with its manipulator ({r}, "
          f"{rec and rec.name}, {counts(ob)})", rec is not None and rec.name == "polyExtrudeFace1" and counts(ob)[1] == 10)


@named("m63_2_components")
def _m63_2_components():
    ob = edit_cube([0])
    n0 = counts(ob)
    menu("Edit Mesh/Add Divisions")
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
    check(f"[M63-2] Add Divisions subdivides the face ({n0} -> {counts(ob)})", counts(ob)[1] > n0[1])
    ob = edit_cube([0])
    move_to(screen(Vector()))
    C["bevel_n0"] = counts(ob)
    menu("Edit Mesh/Bevel")
    C["bevel_modal"] = [op.bl_idname for op in win().modal_operators]
    tap('ESC')
    C["bevel_ob"] = ob


@named("m63_2_bevel")
def _m63_2_bevel():
    # step 139 (#16): Maya bevels at once (polyBevel3 factory values) and Esc keeps it; no Blender modal
    ob_b = C["bevel_ob"]
    if bpy.context.mode == 'EDIT_MESH':
        ob_b.update_from_editmode()
    check(f"[M63-2] Bevel bevels at once, Esc keeps it, no modal ({C['bevel_modal']}, {C['bevel_n0']} -> {counts(ob_b)})",
          "MESH_OT_bevel" not in C["bevel_modal"] and counts(ob_b) != C["bevel_n0"])
    ob = edit_cube([0, 2])          # two opposite faces
    bm = bmesh.from_edit_mesh(ob.data)
    sel = [f for f in bm.faces if f.select]
    opposite = abs(sel[0].normal.dot(sel[1].normal) + 1) < 1e-6 if len(sel) == 2 else False
    if not opposite:   # pick a real opposite pair
        bm.faces.ensure_lookup_table()
        for f in bm.faces:
            f.select_set(False)
        a = bm.faces[0]
        b = next(f for f in bm.faces if abs(f.normal.dot(a.normal) + 1) < 1e-6)
        a.select_set(True)
        b.select_set(True)
        bmesh.update_edit_mesh(ob.data)
    n0 = counts(ob)
    menu("Edit Mesh/Bridge")
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
    check(f"[M63-2] Bridge joins two faces through the cube ({n0} -> {counts(ob)})", counts(ob) != n0)
    ob = edit_cube()
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    f = bm.faces[0]
    a, b = f.verts[0], f.verts[2]
    for v in bm.verts:
        v.select_set(False)
    a.select_set(True)
    b.select_set(True)
    bm.select_history.add(a)
    bm.select_history.add(b)
    bmesh.update_edit_mesh(ob.data)
    ts().mesh_select_mode = (True, False, False)
    n0 = len(ob.data.edges)
    menu("Edit Mesh/Connect")
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
    check(f"[M63-2] Connect joins two vertices of a face with an edge ({n0} -> {len(ob.data.edges)} edges)",
          len(ob.data.edges) == n0 + 1)
    for path, tool in (("Mesh Tools/Multi-Cut", "allset.multi_cut_tool"), ("Mesh Tools/Quad Draw", "allset.quad_draw_tool")):
        select_only(ob)
        menu(path)
        check(f"[M63-2] {path.split('/')[-1]} = edit mode + that tool ({bpy.context.mode}, {tool_id()})",
              bpy.context.mode == 'EDIT_MESH' and tool_id() == tool)
        object_mode()
    set_tool("builtin.select_box")
    clear()
    a = create('CUBE')
    b = create('CUBE')
    b.location = (0.5 * k(), 0.5 * k(), 0)
    select_only(a)
    menu("Mesh/Smooth")
    check(f"[M63-2] Smooth = real Catmull-Clark geometry, Maya 24 faces (step 139; {len(a.data.polygons)})",
          len(a.data.polygons) == 24)
    select_only(a, b)
    menu("Mesh/Booleans/Union")
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    check(f"[M63-2] Boolean (Union) leaves one mesh ({[o.name for o in meshes]})", len(meshes) == 1)
    clear()
    a = create('CUBE')
    b = create('CUBE')
    b.location = (3 * k(), 0, 0)
    select_only(a, b)
    menu("Mesh/Combine")
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    check(f"[M63-2] Combine = one mesh ({[o.name for o in meshes]})", len(meshes) == 1)
    select_only(meshes[0])
    menu("Mesh/Separate")
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    check(f"[M63-2] Separate = the pieces again ({[o.name for o in meshes]})", len(meshes) == 2)


# --- [M63-3] Camera Based Selection; Highlight Nearest Component --------------------------------------------------

def box_all(name):
    def corners():
        _a, r = view3d()
        pts = [screen(C["ob"].matrix_world @ v.co) for v in C["ob"].data.vertices]
        lo = Vector((min(p.x for p in pts) - 25, min(p.y for p in pts) - 25))
        hi = Vector((max(p.x for p in pts) + 25, max(p.y for p in pts) + 25))
        return lo, hi
    drag(name, lambda: corners()[0], lambda: corners()[1], moves=3)


@named("m63_3_setup")
def _m63_3_setup():
    C["ob"] = edit_cube()
    ts().mesh_select_mode = (True, False, False)
    set_tool("builtin.select_box")
    bpy.context.window_manager.allset_mtk_camera_based = True


box_all("m63_3_box_on")


@named("m63_3_on_check")
def _m63_3_on_check():
    bm = bmesh.from_edit_mesh(C["ob"].data)
    n = sum(v.select for v in bm.verts)
    check(f"[M63-3] Camera Based Selection on: the marquee takes only the vertices facing the camera ({n} of 8)", n == 7)
    for v in bm.verts:
        v.select_set(False)
    bmesh.update_edit_mesh(C["ob"].data)
    bpy.context.window_manager.allset_mtk_camera_based = False


box_all("m63_3_box_off")


@named("m63_3_off_check")
def _m63_3_off_check():
    bm = bmesh.from_edit_mesh(C["ob"].data)
    n = sum(v.select for v in bm.verts)
    check(f"[M63-3] off (default, like Maya): the marquee goes through to the back ({n} of 8)", n == 8)
    wm = bpy.context.window_manager
    ps = mod("operators.preselect")
    with override():
        on = ps._enabled(bpy.context)
        wm.allset_mtk_nearest = False
        off = ps._enabled(bpy.context)
        wm.allset_mtk_nearest = True
    check(f"[M63-3] Highlight Nearest Component off = no hover highlight (pre-selection gizmo {on} -> {off})", on and not off)
    object_mode()


# --- [M63-4] b tap soft select = radius 5; b + drag header in Maya units = MTK Falloff radius; Volume / Surface;
#     Reset ------------------------------------------------------------------------------------------------------

@named("m63_4_setup")
def _m63_4_setup():
    C["ob"] = edit_cube()
    ts().use_proportional_edit = False
    ts().proportional_size = 1.0     # Blender's untouched default
    hover()
    tap('B')


@named("m63_4_tap_wait")
def _m63_4_tap_wait():
    pass


@named("m63_4_tap")
def _m63_4_tap():
    r = ts().proportional_size / k()
    check(f"[M63-4] b tap turns soft select on with radius 5 (= 5 cm here: {r:.3f})",
          ts().use_proportional_edit and abs(r - 5) < 1e-6)
    check(f"[M63-4] the MTK Falloff radius shows the same number ({bpy.context.scene.allset_soft_radius:.3f})",
          abs(bpy.context.scene.allset_soft_radius - 5) < 1e-6)
    cls = mod("operators.taphold").SoftSelectBinding
    C["hdr"] = []
    C["hdr_orig"] = cls.__dict__["_show"]      # step 129: header text + radius circle

    def rec(context, event, size):
        C["hdr"].append(None if size is None else size / k())
        return C["hdr_orig"].__func__(context, event, size)
    cls._show = staticmethod(rec)


_a_b = {}


def _b_start():
    _a, r = view3d()
    return Vector((r.x + r.width * 0.4, r.y + r.height * 0.5))


drag("m63_4_bdrag", _b_start, lambda: _b_start() + Vector((100, 0)), hold=('B',), moves=4)


@named("m63_4_bdrag_check")
def _m63_4_bdrag_check():
    cls = mod("operators.taphold").SoftSelectBinding
    cls._show = C["hdr_orig"]
    shown = [h for h in C["hdr"] if h is not None]
    r = bpy.context.scene.allset_soft_radius
    check(f"[M63-4] b + drag right 100 px: the header shows the radius in Maya units, ending at the MTK Falloff "
          f"radius ({shown[-1:] if shown else None} vs {r:.3f})",
          bool(shown) and abs(shown[-1] - r) < 1e-3 and abs(r - 10) < 0.5)
    with override():
        bpy.ops.allset.soft_falloff_mode(surface=True)
    surf = ts().use_proportional_connected
    with override():
        bpy.ops.allset.soft_falloff_mode(surface=False)
    check(f"[M63-4] Falloff mode Surface / Volume = connected only / by distance ({surf}, {ts().use_proportional_connected})",
          surf and not ts().use_proportional_connected)
    ts().proportional_edit_falloff = 'LINEAR'
    with override():
        bpy.ops.allset.soft_select_reset()
    check(f"[M63-4] Reset: radius 5, Volume, smooth falloff ({ts().proportional_size / k():.3f}, "
          f"{ts().proportional_edit_falloff})",
          abs(ts().proportional_size / k() - 5) < 1e-6 and ts().proportional_edit_falloff == 'SMOOTH')
    ts().use_proportional_edit = False
    object_mode()


# --- [M63-6] Mesh > Mirror (last settings), option box, World X - cut + merge; Booleans -----------------------------

@named("m63_6_mirror")
def _m63_6_mirror():
    clear()
    ob = create('CUBE')
    ob.location = (2 * k(), 0, 0)
    bpy.context.view_layer.update()
    select_only(ob)
    with override():   # the Mirror Options window's Mirror button with World, X, -, Cut, Combine, Merge
        r = bpy.ops.allset.mirror(cut=True, position='WORLD', axis='X', direction='NEGATIVE', combine=True, merge=True)
    xs = [(ob.matrix_world @ v.co).x / k() for v in ob.data.vertices]
    check(f"[M63-6] World X -: the cube across the world plane becomes its mirror pair, one mesh ({r}, x "
          f"{min(xs):.2f}..{max(xs):.2f} cm, {len(ob.data.vertices)} verts)",
          abs(min(xs) + 2.5) < 1e-4 and abs(max(xs) - 2.5) < 1e-4 and len(ob.data.vertices) == 16)
    last = bpy.context.window_manager.operator_properties_last("allset.mirror")
    check(f"[M63-6] a plain click reuses the last settings ({last.position}, {last.axis}, {last.direction})",
          (last.position, last.axis, last.direction) == ('WORLD', 'X', 'NEGATIVE'))
    props = {p.identifier for p in bpy.ops.allset.mirror.get_rna_type().properties}
    want = {"cut", "position", "offset", "axis", "direction", "combine", "merge", "threshold", "option_box"}
    check(f"[M63-6] the option box (hold the menu item) opens Mirror Options with Cut / Position / Offset / Axis / "
          f"Direction / Combine / Merge / Threshold ({sorted(want - props)} missing)", want <= props)
    # cut + merge at the plane: a cube straddling x = 0
    clear()
    ob = create('CUBE')
    ob.location = (0.3 * k(), 0, 0)
    bpy.context.view_layer.update()
    select_only(ob)
    with override():
        bpy.ops.allset.mirror(cut=True, position='WORLD', axis='X', direction='NEGATIVE', combine=True, merge=True)
    xs = [(ob.matrix_world @ v.co).x / k() for v in ob.data.vertices]
    check(f"[M63-6] a cube across the plane: the + half is cut and mirrored to -, border merged (x {min(xs):.2f}.."
          f"{max(xs):.2f}, {len(ob.data.vertices)} verts)",
          abs(min(xs) + 0.8) < 1e-4 and abs(max(xs) - 0.8) < 1e-4 and len(ob.data.vertices) == 12)
    for op, n_expect in (("Difference", 1), ("Intersection", 1)):
        clear()
        a = create('CUBE')
        b = create('CUBE')
        b.location = (0.5 * k(), 0, 0)
        select_only(a, b)    # first selected - last selected
        menu(f"Mesh/Booleans/{op} (A - B)" if op == "Difference" else f"Mesh/Booleans/{op}")   # Maya 2026 label (step 219)
        meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
        xs = [(meshes[0].matrix_world @ v.co).x / k() for v in meshes[0].data.vertices] if meshes else [0]
        want = (-0.5, 0.0) if op == "Difference" else (0.0, 0.5)
        check(f"[M63-6] Booleans > {op}: first selected {'-' if op == 'Difference' else '&'} last ({[o.name for o in meshes]}, "
              f"x {min(xs):.2f}..{max(xs):.2f})",
              len(meshes) == n_expect and abs(min(xs) - want[0]) < 1e-3 and abs(max(xs) - want[1]) < 1e-3)


# --- [M64-1..3] Target Weld tool: entries, drag weld, rubber band, fallback marquee, cancel, selection, settings ---

def OB():
    """pCube1 fetched again each time: undo replaces the object datablocks."""
    return bpy.data.objects[C["obname"]]


def mtools():
    return mod("operators.mesh_tools")


def zoom(dist_cm, at=(0, 0, 0)):
    _a, region = view3d()
    region.data.view_distance = dist_cm * k()
    region.data.view_location = Vector(at) * k()
    bpy.context.view_layer.update()
    redraw_all()


def emesh(ob):
    b = bmesh.from_edit_mesh(ob.data)
    b.verts.ensure_lookup_table()
    b.edges.ensure_lookup_table()
    return b


def vdepth(ob, co):
    return -(view3d()[1].data.view_matrix @ (ob.matrix_world @ co)).z


def front_pair(ob):
    """(source, target) vertex coordinates: the vertex nearest the camera and its nearest neighbour."""
    b = emesh(ob)
    src = min(b.verts, key=lambda v: vdepth(ob, v.co))
    dst = min((e.other_vert(src) for e in src.link_edges), key=lambda v: vdepth(ob, v.co))
    return src.co.copy(), dst.co.copy()


def wpt(ob, co):
    return screen(ob.matrix_world @ co)


def deselect_all(ob):
    b = emesh(ob)
    for v in b.verts:
        v.select = False
    b.select_flush(False)
    bmesh.update_edit_mesh(ob.data)


def set_selected(ob, cos):
    b = emesh(ob)
    for v in b.verts:
        v.select = any((v.co - c).length < 1e-6 for c in cos)
    b.select_flush(True)
    bmesh.update_edit_mesh(ob.data)


def nverts(ob):
    return len(emesh(ob).verts)


@named("m64_1_entries")
def _m64_1_entries():
    menus = mod("marking.menus")
    tw = menus.TARGET_WELD
    found = []
    for name in dir(menus):
        mm = getattr(menus, name)
        if isinstance(mm, menus.MarkingMenu):
            def walk(radial, items, path):
                for pos, (label, act) in radial.items():
                    if act == tw:
                        found.append(f"{mm.name}:{path}{pos}")
                    if isinstance(act, menus.Sub):
                        walk(act.radial, act.items, path + pos + ">")
                for it in items:
                    if isinstance(it, tuple) and it[1] == tw:
                        found.append(f"{mm.name}:{path}list")
            walk(mm.radial, mm.items, "")
    shelf = mod("ui.shelf_map").BY_COMMAND.get("MergeVertexTool", (None,))[0]
    check(f"[M64-1] Target Weld from Mesh Tools menu / Shift+RMB N / vertex + edge Merge > S / shelf / MTK "
          f"(marking menus {found}, shelf {shelf})",
          mod("ui.menu_map").MAP["Mesh Tools/Target Weld"] == tw and shelf == tw and len(found) >= 3
          and any(f.endswith(":N") for f in found))
    clear()
    ob = create('CUBE')
    select_only(ob)
    rv3d = view3d()[1].data
    C["view0"] = (rv3d.view_distance, rv3d.view_location.copy())
    zoom(6)
    C["obname"] = ob.name
    menu("Mesh Tools/Target Weld")
    check(f"[M64-1] the menu item = edit mode + the Target Weld tool ({bpy.context.mode}, {tool_id()})",
          bpy.context.mode == 'EDIT_MESH' and tool_id() == "allset.target_weld_tool")
    ts().mesh_select_mode = (True, False, False)
    deselect_all(ob)
    undo_base("m64 setup")
    C["src"], C["dst"] = front_pair(ob)
    C["n0"] = nverts(ob)


drag("m64_1_weld", lambda: wpt(OB(), C["src"]), lambda: wpt(OB(), C["dst"]), moves=6)


@named("m64_1_weld_during")
def _m64_1_weld_during():
    pass


@named("m64_1_weld_check")
def _m64_1_weld_check():
    ob = OB()
    b = emesh(ob)
    at = any((v.co - C["dst"]).length < 1e-6 for v in b.verts)
    gone = not any((v.co - C["src"]).length < 1e-6 for v in b.verts)
    check(f"[M64-1] LMB on a vertex, drag, release on its neighbour = merged into that vertex "
          f"({C['n0']} -> {len(b.verts)} verts)", len(b.verts) == C["n0"] - 1 and at and gone)
    hover()
    key('Z', ctrl=True)


# the rubber band / red target: drawn by the running weld modal (its draw handler) while the button is held
@named("m64_1_band_press")
def _m64_1_band_press():
    ob = OB()
    C["src"], C["dst"] = front_pair(ob)
    p = wpt(ob, C["src"])
    move_to(p)
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y))


@named("m64_1_band_move")
def _m64_1_band_move():
    p, q = wpt(OB(), C["src"]), wpt(OB(), C["dst"])
    for f in (0.5, 1.0):
        r = p + (q - p) * f
        ev('MOUSEMOVE', 'NOTHING', x=int(r.x), y=int(r.y))


@named("m64_1_band_state")
def _m64_1_band_state():
    ops = [op for op in win().modal_operators if op.bl_idname == "ALLSET_OT_target_weld"]
    hover_ok = None
    if ops:
        try:
            hover_ok = getattr(ops[0], "_hover", None)
        except Exception:   # noqa: BLE001
            hover_ok = None
    check(f"[M64-1] while dragging: the weld modal draws its rubber band (draw handler on: {bool(mtools()._handles)}) "
          f"and the target under the mouse is picked for the red mark ({hover_ok})",
          bool(ops) and bool(mtools()._handles) and (hover_ok is None or hover_ok >= 0))
    tap('ESC')


@named("m64_1_esc_check")
def _m64_1_esc_check():
    ev('LEFTMOUSE', 'RELEASE')
    check(f"[M64-1] Esc cancels: nothing merged ({nverts(OB())} verts, handlers {len(mtools()._handles)})",
          nverts(OB()) == C["n0"] and not mtools()._handles)
    p = wpt(OB(), C["src"])
    move_to(p)
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y))


@named("m64_1_rmb_move")
def _m64_1_rmb_move():
    q = wpt(OB(), C["dst"])
    ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y))


@named("m64_1_rmb")
def _m64_1_rmb():
    ev('RIGHTMOUSE', 'PRESS')
    ev('RIGHTMOUSE', 'RELEASE')
    ev('LEFTMOUSE', 'RELEASE')


@named("m64_1_rmb_check")
def _m64_1_rmb_check():
    check(f"[M64-1] RMB cancels too ({nverts(OB())} verts)", nverts(OB()) == C["n0"])
    esc_modals()
    deselect_all(OB())


def _empty_corner():
    _a, r = view3d()
    return Vector((r.x + r.width * 0.2, r.y + r.height * 0.8))


drag("m64_1_marquee", _empty_corner, lambda: screen(Vector()) + Vector((5, -5)), moves=3)


@named("m64_1_marquee_check")
def _m64_1_marquee_check():
    n = sum(v.select for v in emesh(OB()).verts)
    check(f"[M64-1] a drag away from vertices = marquee selection (the tool's fallback; {n} selected)",
          n >= 1 and nverts(OB()) == C["n0"])


@named("m64_2_preselect")
def _m64_2_preselect():
    with override():
        on = mod("operators.preselect")._enabled(bpy.context)
    check(f"[M64-2] vertex mode with this tool: the vertex under the mouse is highlighted (pre-selection on: {on})", on)
    ob = OB()
    b = emesh(ob)
    src = min(b.verts, key=lambda v: vdepth(ob, v.co))
    nbrs = sorted((e.other_vert(src) for e in src.link_edges), key=lambda v: vdepth(ob, v.co))
    C["src"], C["dst"], C["other"] = src.co.copy(), nbrs[0].co.copy(), nbrs[1].co.copy()
    set_selected(ob, [C["src"], C["other"]])
    C["n0"] = nverts(ob)


drag("m64_2_two", lambda: wpt(OB(), C["src"]), lambda: wpt(OB(), C["dst"]), moves=6)


@named("m64_2_two_check")
def _m64_2_two_check():
    ob = OB()
    b = emesh(ob)
    check(f"[M64-2] two selected vertices, drag one onto a target: both merge into it ({C['n0']} -> {len(b.verts)})",
          len(b.verts) == C["n0"] - 2 and any((v.co - C["dst"]).length < 1e-6 for v in b.verts))
    hover()
    key('Z', ctrl=True)


@named("m64_2_one_setup")
def _m64_2_one_setup():
    ob = OB()
    b = emesh(ob)
    src = min(b.verts, key=lambda v: vdepth(ob, v.co))
    nbrs = sorted((e.other_vert(src) for e in src.link_edges), key=lambda v: vdepth(ob, v.co))
    C["src"], C["dst"], C["other"] = src.co.copy(), nbrs[0].co.copy(), nbrs[1].co.copy()
    set_selected(ob, [C["other"]])     # a selected vertex elsewhere; drag an unselected one
    C["n0"] = nverts(ob)


drag("m64_2_one", lambda: wpt(OB(), C["src"]), lambda: wpt(OB(), C["dst"]), moves=6)


@named("m64_2_one_check")
def _m64_2_one_check():
    check(f"[M64-2] dragging an unselected vertex merges only it ({C['n0']} -> {nverts(OB())})",
          nverts(OB()) == C["n0"] - 1)
    hover()
    key('Z', ctrl=True)


@named("m64_3_center")
def _m64_3_center():
    s = mtools().settings(bpy.context)
    rec = LayoutRecorder()
    with override():
        mod("ui.mesh_tools").draw_target_weld_settings(rec, bpy.context) \
            if hasattr(mod("ui.mesh_tools"), "draw_target_weld_settings") else None
    C["weld_ui"] = rec.out
    check(f"[M64-3] Tool Settings: Merge To Target / Center, Preserve UVs ({s.weld_merge_to}, {s.weld_preserve_uvs})",
          s.weld_merge_to == 'TARGET' and s.weld_preserve_uvs
          and {"TARGET", "CENTER"} <= {i.identifier for i in s.bl_rna.properties["weld_merge_to"].enum_items})
    s.weld_merge_to = 'CENTER'
    ob = OB()
    deselect_all(ob)
    C["src"], C["dst"] = front_pair(ob)
    C["n0"] = nverts(ob)


drag("m64_3_c", lambda: wpt(OB(), C["src"]), lambda: wpt(OB(), C["dst"]), moves=6)


@named("m64_3_c_check")
def _m64_3_c_check():
    mid = (C["src"] + C["dst"]) / 2
    b = emesh(OB())
    check(f"[M64-3] Merge To Center: merged half way ({C['n0']} -> {len(b.verts)})",
          len(b.verts) == C["n0"] - 1 and any((v.co - mid).length < 1e-6 for v in b.verts))
    mtools().settings(bpy.context).weld_merge_to = 'TARGET'
    # Adjust Last Operation: the redo panel re-runs the last weld with Merge To changed
    last = bpy.context.window_manager.operators[-1]
    C["last"] = (last.bl_idname, last.properties.source, last.properties.target, last.properties.element)
    hover()
    key('Z', ctrl=True)


@named("m64_3_redo")
def _m64_3_redo():
    name, src, dst, el = C["last"]
    ob = OB()
    with override():
        r = bpy.ops.allset.target_weld('EXEC_DEFAULT', True, object=ob.name, element=el, source=src, target=dst, merge_to='TARGET')
    b = emesh(ob)
    check(f"[M64-3] Adjust Last Operation Merge To = Target re-runs it at the target ({name}, {r}, {len(b.verts)} verts)",
          name == "ALLSET_OT_target_weld" and r == {'FINISHED'} and any((v.co - C["dst"]).length < 1e-6 for v in b.verts))
    hover()
    key('Z', ctrl=True)


@named("m64_3_neighbour")
def _m64_3_neighbour():
    ob = OB()
    ts().mesh_select_mode = (False, True, False)
    b = emesh(ob)
    face = min(b.faces, key=lambda f: sum(vdepth(ob, v.co) for v in f.verts))
    e0 = face.edges[0]
    e1 = next(e for e in face.edges if e is not e0 and set(e.verts) & set(e0.verts))
    C["e0"] = [v.co.copy() for v in e0.verts]
    C["e1"] = [v.co.copy() for v in e1.verts]
    C["shared"] = next(v.co.copy() for v in e0.verts if v in e1.verts)
    C["n0"] = nverts(ob)
    deselect_all(ob)


drag("m64_3_n", lambda: _edge_mid(C["e0"]), lambda: _edge_mid(C["e1"]), moves=6)


@named("m64_3_n_check")
def _m64_3_n_check():
    b = emesh(OB())
    check(f"[M64-3] neighbouring edges: the shared vertex stays, the other end merges ({C['n0']} -> {len(b.verts)})",
          len(b.verts) == C["n0"] - 1 and any((v.co - C["shared"]).length < 1e-6 for v in b.verts))
    hover()
    key('Z', ctrl=True)


@named("m64_3_edges")
def _m64_3_edges():
    ob = OB()
    ts().mesh_select_mode = (False, True, False)   # an edit-mode undo restores the step's select mode
    b = emesh(ob)
    # two parallel edges of the front face (no shared vertex) and two neighbouring edges
    face = min(b.faces, key=lambda f: sum(vdepth(ob, v.co) for v in f.verts))
    e0 = face.edges[0]
    e2 = next(e for e in face.edges if not (set(e.verts) & set(e0.verts)))
    C["e0"] = [v.co.copy() for v in e0.verts]
    C["e2"] = [v.co.copy() for v in e2.verts]
    C["n0"] = nverts(ob)
    deselect_all(ob)


def _edge_mid(cos):
    return wpt(OB(), (cos[0] + cos[1]) / 2)


drag("m64_3_e", lambda: _edge_mid(C["e0"]), lambda: _edge_mid(C["e2"]), moves=6)


@named("m64_3_e_check")
def _m64_3_e_check():
    b = emesh(OB())
    check(f"[M64-3] edge mode: an edge dragged onto another merges end to end ({C['n0']} -> {len(b.verts)} verts)",
          len(b.verts) == C["n0"] - 2 and all(any((v.co - c).length < 1e-6 for v in b.verts) for c in C["e2"]))
    hover()
    key('Z', ctrl=True)
    ts().mesh_select_mode = (True, False, False)


# --- [M64-5] Multi-Cut: Ctrl+click loop, Ctrl+MMB middle, Ctrl+Shift+click snap step, Position, Shift+click start,
#     Shift while cutting = edge midpoint, Tool Settings ---------------------------------------------------------

def front_edge(ob):
    b = emesh(ob)
    e = min(b.edges, key=lambda e: vdepth(ob, e.verts[0].co) + vdepth(ob, e.verts[1].co))
    return e.index, e.verts[0].co.copy(), e.verts[1].co.copy()


def on_edge_ts(ob, a, b):
    bm_ = emesh(ob)
    out = []
    for v in bm_.verts:
        if abs((v.co - a).length + (v.co - b).length - (a - b).length) < 1e-5 and (v.co - a).length > 1e-5 \
                and (v.co - b).length > 1e-5:
            out.append(round((v.co - a).length / (b - a).length, 3))
    return sorted(out)


@named("m64_5_setup")
def _m64_5_setup():
    ob = OB()
    hover()
    key('X', ctrl=True, shift=True)


@named("m64_5_ctrl_click")
def _m64_5_ctrl_click():
    check(f"[M64-5] Ctrl+Shift+X = Multi-Cut ({tool_id()})", tool_id() == "allset.multi_cut_tool")
    ob = OB()
    _i, a, b = front_edge(ob)
    C["edge"], C["n0"] = (a, b), nverts(ob)
    p = wpt(ob, a.lerp(b, 0.3))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y), ctrl=True)
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y), ctrl=True)
    ev('LEFTMOUSE', 'RELEASE', x=int(p.x), y=int(p.y), ctrl=True)


@named("m64_5_ctrl_click_check")
def _m64_5_ctrl_click_check():
    ob = OB()
    t = on_edge_ts(ob, *C["edge"])
    check(f"[M64-5] Ctrl+click = an edge loop at the clicked ratio ({C['n0']} -> {nverts(ob)} verts, t {t})",
          nverts(ob) == C["n0"] + 4 and len(t) == 1 and abs(t[0] - 0.3) < 0.03)
    last = bpy.context.window_manager.operators[-1]
    C["loop"] = (last.bl_idname, last.properties.edge, last.properties.object)
    hover()
    key('Z', ctrl=True)


@named("m64_5_position")
def _m64_5_position():
    name, edge, obname = C["loop"]
    with override():   # Adjust Last Operation: Position 0.7
        r = bpy.ops.allset.multicut_loop('EXEC_DEFAULT', True, object=obname, edge=edge, factor=0.7)
    t = on_edge_ts(OB(), *C["edge"])
    check(f"[M64-5] Adjust Last Operation Position moves the loop ({name}, {r}, t {t})",
          name == "ALLSET_OT_multicut_loop" and len(t) == 1 and abs(min(t[0], 1 - t[0]) - 0.3) < 1e-3)
    hover()
    key('Z', ctrl=True)


@named("m64_5_ctrl_mmb")
def _m64_5_ctrl_mmb():
    ob = OB()
    a, b = C["edge"]
    p = wpt(ob, a.lerp(b, 0.3))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y), ctrl=True)
    ev('MIDDLEMOUSE', 'PRESS', x=int(p.x), y=int(p.y), ctrl=True)
    ev('MIDDLEMOUSE', 'RELEASE', x=int(p.x), y=int(p.y), ctrl=True)


@named("m64_5_ctrl_mmb_check")
def _m64_5_ctrl_mmb_check():
    t = on_edge_ts(OB(), *C["edge"])
    check(f"[M64-5] Ctrl+MMB = the loop in the middle (t {t})", t == [0.5])
    hover()
    key('Z', ctrl=True)


@named("m64_5_ctrl_shift")
def _m64_5_ctrl_shift():
    mtools().settings(bpy.context).snap_step = 25
    ob = OB()
    a, b = C["edge"]
    p = wpt(ob, a.lerp(b, 0.33))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y), ctrl=True, shift=True)
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y), ctrl=True, shift=True)
    ev('LEFTMOUSE', 'RELEASE', x=int(p.x), y=int(p.y), ctrl=True, shift=True)


@named("m64_5_ctrl_shift_check")
def _m64_5_ctrl_shift_check():
    t = on_edge_ts(OB(), *C["edge"])
    check(f"[M64-5] Ctrl+Shift+click = the loop on the Snap Step (25 %: t {t})", t in ([0.25], [0.75]))
    hover()
    key('Z', ctrl=True)


@named("m64_5_shift_start")
def _m64_5_shift_start():
    ob = OB()
    a, b = C["edge"]
    C["n0"] = nverts(ob)
    p = wpt(ob, a.lerp(b, 0.33))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y), shift=True)
    ev('LEFT_SHIFT', 'PRESS', x=int(p.x), y=int(p.y), shift=True)
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y), shift=True)


@named("m64_5_shift_release")
def _m64_5_shift_release():
    ev('LEFTMOUSE', 'RELEASE', shift=True)
    ev('LEFT_SHIFT', 'RELEASE')


@named("m64_5_second")
def _m64_5_second():
    # second point with Shift held: Maya's Shift while cutting = the edge midpoint (kit: Blender's midpoint snap)
    ob = OB()
    b = emesh(ob)
    a, e1 = C["edge"]
    first = next(e for e in b.edges if {tuple(v.co) for v in e.verts} == {tuple(a), tuple(e1)})
    face = max(first.link_faces, key=lambda f: -sum(vdepth(ob, v.co) for v in f.verts))
    other = next(e for e in face.edges if not (set(e.verts) & set(first.verts)))
    C["other"] = (other.verts[0].co.copy(), other.verts[1].co.copy())
    p = wpt(ob, C["other"][0].lerp(C["other"][1], 0.4))
    ev('LEFT_SHIFT', 'PRESS', x=int(p.x), y=int(p.y), shift=True)
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y), shift=True)


@named("m64_5_second_click")
def _m64_5_second_click():
    ob = OB()
    p = wpt(ob, C["other"][0].lerp(C["other"][1], 0.4))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x) + 1, y=int(p.y), shift=True)
    ev('LEFTMOUSE', 'PRESS', x=int(p.x) + 1, y=int(p.y), shift=True)
    ev('LEFTMOUSE', 'RELEASE', x=int(p.x) + 1, y=int(p.y), shift=True)
    ev('LEFT_SHIFT', 'RELEASE')


@named("m64_5_confirm")
def _m64_5_confirm():
    tap('RET')


@named("m64_5_cut_check")
def _m64_5_cut_check():
    ob = OB()
    t1 = on_edge_ts(ob, *C["edge"])
    t2 = on_edge_ts(ob, *C["other"])
    check(f"[M64-5] Shift+click: the cut starts on the nearest Snap Step point (t {t1})", t1 in ([0.25], [0.75]))
    check(f"[M64-5] Shift while cutting = the edge midpoint (second edge t {t2})", t2 == [0.5])
    mtools().settings(bpy.context).snap_step = 10
    hover()
    key('Z', ctrl=True)
    notes = mod("ui.notices").PANEL_NOTICES
    grey = ["Multi-Cut/Edge Flow"]     # step 129: Smoothing Angle, Subdivisions, Slice Tool are real now
    check(f"[M64-5] Tool Settings: Snap Step % + greyed Maya items with tooltip notices ({[g for g in grey if g not in notes]} "
          f"missing)", "snap_step" in mtools().settings(bpy.context).bl_rna.properties and all(g in notes for g in grey))
    set_tool("builtin.select_box")
    object_mode()
    rv3d = view3d()[1].data
    rv3d.view_distance, rv3d.view_location = C["view0"]


# --- [M65-2..5] polyExtrudeFace: manipulator arrow, In-View Editor, Channel Box INPUTS, leaving the record ---------

def iv():
    return mod("ui.in_view")


def ex():
    return mod("operators.extrude")


def v3d_ctx():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active)


def xrec():
    return ex().active(bpy.context)[1]


def hist():
    return bpy.context.window_manager.allset_history


def top_z():
    ob = OB()
    return max(v.co.z for v in bmesh.from_edit_mesh(ob.data).verts) / k()


def ecounts():
    b = bmesh.from_edit_mesh(OB().data)
    return len(b.verts), len(b.faces)


def arrow_pts(length_px=60):
    area, region = view3d()
    with v3d_ctx():
        ob, r = iv().record(bpy.context)
        c, n, _k = iv().cap_frame(ob, r)
    p0 = location_3d_to_region_2d(region, region.data, c)
    p1 = location_3d_to_region_2d(region, region.data, c + n * 0.01)
    d = (p1 - p0).normalized()
    s = bpy.context.preferences.system.ui_scale
    start = p0 + d * 45 * s / 1.25
    a = Vector((region.x + start.x, region.y + start.y))
    return a, a + d * length_px * s / 1.25


def iv_rows():
    _a, region = view3d()
    with v3d_ctx():
        _r, lay = iv().current_layout(bpy.context)
    if lay is None:
        return {}
    return {f: Vector((region.x + (x0 + x1) / 2, region.y + (y0 + y1) / 2)) for f, x0, y0, x1, y1 in lay["rows"]}


def fresh(name, n_faces=1):
    """Steps: a new cube in edit mode with its top face (and a side face) selected, then Ctrl+E."""
    @named(f"{name}_fresh")
    def _fresh():
        object_mode()
        clear()
        ob = create('CUBE')
        C["obname"] = ob.name
        select_only(ob)
        with v3d_ctx():
            bpy.ops.object.mode_set('EXEC_DEFAULT', True, mode='EDIT')
        ts().mesh_select_mode = (False, False, True)
        top_faces(ob, n_faces)
        undo_base(name)
        _a, r = view3d()
        move_to(Vector((r.x + r.width * 0.25, r.y + r.height * 0.3)))

    @named(f"{name}_ctrl_e")
    def _ctrl_e():
        key('E', ctrl=True)
        redraw_all()


def top_faces(ob, n=1):
    b = bmesh.from_edit_mesh(ob.data)
    for f in b.faces:
        f.select_set(False)
    tops = sorted(b.faces, key=lambda f: -f.normal.z)
    for f in tops[:1]:
        f.select_set(True)
    if n == 2:   # the top face and the side face facing the camera most
        side = max((f for f in b.faces if abs(f.normal.z) < 0.5), key=lambda f: f.normal.dot(-view_dir()))
        side.select_set(True)
    b.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)


@named("m65_setup")
def _m65_setup():
    clear()
    bpy.context.scene.pop(mod("operators.extrude").COUNTER, None)   # node numbers count per scene: start like a new one
    ob = create('CUBE')
    C["obname"] = ob.name
    select_only(ob)
    rv3d = view3d()[1].data
    C["view0"] = (rv3d.view_distance, rv3d.view_location.copy())
    zoom(7)
    with v3d_ctx():
        bpy.ops.object.mode_set('EXEC_DEFAULT', True, mode='EDIT')
    ts().mesh_select_mode = (False, False, True)
    top_faces(ob)
    undo_base("m65 setup")
    _a, r = view3d()
    move_to(Vector((r.x + r.width * 0.25, r.y + r.height * 0.3)))
    key('E', ctrl=True)


@named("m65_2_extruded")
def _m65_2_extruded():
    r = xrec()
    with v3d_ctx():
        vis = iv().manip_visible(bpy.context)
    check(f"[M65-2] (Ctrl+E = polyExtrudeFace1 with its arrow and In-View Editor: {r and r.name}, {vis})",
          r is not None and r.name == "polyExtrudeFace1" and vis)
    C["z0"] = top_z()
    redraw_all()


@named("m65_2_a_hover")
def _m65_2_a_hover():
    C["p"], C["q"] = arrow_pts()
    move_to(C["p"])
    redraw_all()


@named("m65_2_a_hover2")
def _m65_2_a_hover2():
    move_to(C["p"])
    redraw_all()


@named("m65_2_a_press")
def _m65_2_a_press():
    ev('LEFTMOUSE', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))


@named("m65_2_a_move")
def _m65_2_a_move():
    for f in (0.25, 0.5, 0.75, 1.0):
        r = C["p"] + (C["q"] - C["p"]) * f
        ev('MOUSEMOVE', 'NOTHING', x=int(r.x), y=int(r.y))


@named("m65_2_a_release")
def _m65_2_a_release():
    ev('LEFTMOUSE', 'RELEASE', x=int(C["q"].x), y=int(C["q"].y))


@named("m65_2_arrow_check")
def _m65_2_arrow_check():
    r = xrec()
    ltz = r.params["local_translate_z"] if r else None
    check(f"[M65-2] dragging the arrow moves the faces along the normal and Local Translate Z follows "
          f"(ltz {ltz}, Channel Box {hist().local_translate_z_text!r}, top z {C['z0']:.3f} -> {top_z():.3f} cm)",
          r is not None and ltz > 0.05 and abs(top_z() - (C["z0"] + ltz)) < 1e-3
          and abs(float(hist().local_translate_z_text) - ltz) < 1e-3)
    hover()
    key('Z', ctrl=True)


@named("m65_2_undo_check")
def _m65_2_undo_check():
    r = xrec()
    check(f"[M65-2] Ctrl+Z once takes the drag back (ltz {r and r.params['local_translate_z']}, top z {top_z():.3f})",
          r is not None and abs(r.params["local_translate_z"]) < 1e-6 and abs(top_z() - C["z0"]) < 1e-4)
    p, q = arrow_pts()
    C["p"], C["q"] = p, q
    move_to(p)


@named("m65_2_esc_press")
def _m65_2_esc_press():
    ev('LEFTMOUSE', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))


@named("m65_2_esc_move")
def _m65_2_esc_move():
    ev('MOUSEMOVE', 'NOTHING', x=int(C["q"].x), y=int(C["q"].y))


@named("m65_2_esc")
def _m65_2_esc():
    C["during"] = top_z()
    tap('ESC')
    ev('LEFTMOUSE', 'RELEASE', x=int(C["q"].x), y=int(C["q"].y))


@named("m65_2_esc_check")
def _m65_2_esc_check():
    check(f"[M65-2] Esc cancels the drag (top z {C['during']:.3f} -> {top_z():.3f})",
          C["during"] > C["z0"] + 0.05 and abs(top_z() - C["z0"]) < 1e-4)
    move_to(C["p"])


@named("m65_2_rmb_press")
def _m65_2_rmb_press():
    ev('LEFTMOUSE', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))


@named("m65_2_rmb_move")
def _m65_2_rmb_move():
    ev('MOUSEMOVE', 'NOTHING', x=int(C["q"].x), y=int(C["q"].y))


@named("m65_2_rmb")
def _m65_2_rmb():
    ev('RIGHTMOUSE', 'PRESS')
    ev('RIGHTMOUSE', 'RELEASE')
    ev('LEFTMOUSE', 'RELEASE', x=int(C["q"].x), y=int(C["q"].y))


@named("m65_2_rmb_check")
def _m65_2_rmb_check():
    check(f"[M65-2] RMB cancels too (top z {top_z():.3f})", abs(top_z() - C["z0"]) < 1e-4)
    redraw_all()


# [M65-3] In-View rows: drag (Ctrl finer, Shift coarser), click = type, Keep Faces Together toggles, hot row yellow

def row_drag(name, field, dx_px, mods=None):
    drag(name, lambda: iv_rows()[field], lambda: iv_rows()[field] + Vector((dx_px * bpy.context.preferences.system.ui_scale, 0)),
         moves=4, mods=mods)


row_drag("m65_3_plain", "thickness", 20)


@named("m65_3_plain_check")
def _m65_3_plain_check():
    C["t_plain"] = xrec().params["thickness"]
    C["hot"] = iv()._state["hot"]
    _a, region = view3d()
    with v3d_ctx():
        _r, lay = iv().current_layout(bpy.context)
    import sim as _sim
    mx, my = _sim._pos
    C["under"] = next((i for i, (_f, x0, y0, x1, y1) in enumerate(lay["rows"])
                       if region.x + x0 <= mx <= region.x + x1 and region.y + y0 <= my <= region.y + y1), None)
    with v3d_ctx():
        bpy.ops.allset.extrude_edit('EXEC_DEFAULT', True, thickness=0.0)
    check(f"[M65-3] dragging the Thickness row sideways changes it ({C['t_plain']:.3f}); the row is the hot (yellow) one "
          f"({C['hot']} = row under the mouse {C['under']})",
          C["t_plain"] > 0.05 and C["hot"] == C["under"])


row_drag("m65_3_ctrl", "thickness", 20, mods={"ctrl": True})


@named("m65_3_ctrl_check")
def _m65_3_ctrl_check():
    C["t_ctrl"] = xrec().params["thickness"]
    with v3d_ctx():
        bpy.ops.allset.extrude_edit('EXEC_DEFAULT', True, thickness=0.0)


row_drag("m65_3_shift", "thickness", 20, mods={"shift": True})


@named("m65_3_shift_check")
def _m65_3_shift_check():
    t_shift = xrec().params["thickness"]
    check(f"[M65-3] Ctrl = finer, Shift = coarser (same 20 px: {C['t_ctrl']:.4f} / {C['t_plain']:.4f} / {t_shift:.4f})",
          abs(C["t_ctrl"] * 10 - C["t_plain"]) < 0.02 * C["t_plain"] + 1e-3
          and abs(t_shift - C["t_plain"] * 10) < 0.02 * t_shift + 1e-3)
    with v3d_ctx():
        bpy.ops.allset.extrude_edit('EXEC_DEFAULT', True, thickness=0.0)
    cls = mod("ui.in_view").ALLSET_OT_inview_type
    C["typed"] = []
    C["type_invoke"] = cls.__dict__["invoke"]

    def invoke(op, context, event):
        C["typed"].append(op.row)
        return C["type_invoke"](op, context, event)
    cls.invoke = invoke
    p = iv_rows()["divisions"]
    move_to(p)


@named("m65_3_click")
def _m65_3_click():
    p = iv_rows()["divisions"]
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y))
    ev('LEFTMOUSE', 'RELEASE', x=int(p.x), y=int(p.y))


@named("m65_3_click_check")
def _m65_3_click_check():
    mod("ui.in_view").ALLSET_OT_inview_type.invoke = C["type_invoke"]
    check(f"[M65-3] a click without dragging opens the value entry window ({C['typed']})",
          C["typed"] == [ex().FIELDS.index("divisions")])
    tap('ESC')


fresh("m65_3_keep", n_faces=2)


@named("m65_3_keep_drag")
def _m65_3_keep_drag():
    with v3d_ctx():
        bpy.ops.allset.extrude_edit('EXEC_DEFAULT', True, local_translate_z=0.5)
    C["together"] = ecounts()
    p = iv_rows()["keep_faces_together"]
    move_to(p)


@named("m65_3_keep_click")
def _m65_3_keep_click():
    p = iv_rows()["keep_faces_together"]
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y))
    ev('LEFTMOUSE', 'RELEASE', x=int(p.x), y=int(p.y))


@named("m65_3_keep_check")
def _m65_3_keep_check():
    r = xrec()
    check(f"[M65-3] clicking Keep Faces Together toggles it; two faces then extrude apart ({C['together']} -> {ecounts()}, "
          f"{r and r.params['keep_faces_together']})",
          r is not None and not r.params["keep_faces_together"] and ecounts() != C["together"])


# [M65-4] Channel Box INPUTS polyExtrudeFace1: five rows, 0.5 / +=0.25, the notice, Divisions 2, undo / redo, gone
# after another edit

fresh("m65_4")


@named("m65_4_check")
def _m65_4_check():
    ob = OB()
    rec = iv().cb_record(bpy.context, ob)
    lay = LayoutRecorder()
    with v3d_ctx():
        iv().draw_cb_node(lay, bpy.context, rec)
    # step 106: the 'Blender keeps no edit-mode history' notice is the node name's tooltip, not grey lines
    check(f"[M65-4] INPUTS: polyExtrudeFace1 with its five rows, the history notice as its tooltip "
          f"({lay.out[:1]}, {len(ex().FIELDS)} rows)",
          rec is not None and lay.out and lay.out[0].startswith("polyExtrudeFace") and len(ex().FIELDS) == 5
          and not any("keeps no edit-mode history" in t for t in lay.out)
          and "keeps no edit-mode history" in iv().HISTORY_TIP)
    z0 = top_z()
    hist().local_translate_z_text = "0.5"
    z1 = top_z()
    hist().local_translate_z_text = "+=0.25"
    check(f"[M65-4] typing 0.5 then +=0.25 in Local Translate Z ({z0:.3f} -> {z1:.3f} -> {top_z():.3f} cm)",
          abs(z1 - z0 - 0.5) < 1e-4 and abs(top_z() - z0 - 0.75) < 1e-4)
    hist().divisions_text = "2"   # set_params pushes its own undo step
    check(f"[M65-4] Divisions 2 = two rings on the sides ({ecounts()})", ecounts() == (16, 14))
    hover()
    key('Z', ctrl=True)


@named("m65_4_undo_check")
def _m65_4_undo_check():
    check(f"[M65-4] Ctrl+Z: the rows follow (Divisions {hist().divisions_text!r}, {ecounts()})",
          hist().divisions_text == "1" and ecounts() == (12, 10))
    hover()
    key('Z', shift=True)   # Maya redo


@named("m65_4_redo_check")
def _m65_4_redo_check():
    check(f"[M65-4] redo: the rows follow again (Divisions {hist().divisions_text!r}, {ecounts()})",
          hist().divisions_text == "2" and ecounts() == (16, 14))
    ob = OB()
    b = bmesh.from_edit_mesh(ob.data)
    b.verts.ensure_lookup_table()
    rec = iv().cb_record(bpy.context, ob)
    b.verts[rec.cap_verts[0]].co.x += 0.1 * k()      # a vertex of the extruded faces moved by hand
    bmesh.update_edit_mesh(ob.data)
    check(f"[M65-4] after moving its vertices by hand the rows are gone ({iv().cb_record(bpy.context, ob)})",
          iv().cb_record(bpy.context, ob) is None)


# [M65-5] another face selected: arrow / In-View go, the Move manipulator comes back (rows stay); Adjust Last
# Operation has the Maya names; Ctrl+E on edges / vertices = Blender's extrude + normal drag

fresh("m65_5")


@named("m65_5_other")
def _m65_5_other():
    ob = OB()
    set_tool("builtin.move")
    b = bmesh.from_edit_mesh(ob.data)
    for f in b.faces:
        f.select_set(False)
    side = next(f for f in b.faces if abs(f.normal.z) < 0.5)
    side.select_set(True)
    b.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    redraw_all()


@named("m65_5_other_check")
def _m65_5_other_check():
    with v3d_ctx():
        vis = iv().manip_visible(bpy.context)
        man = mod("ui.manipulator").ALLSET_GGT_xform.poll(bpy.context)
    rec = iv().cb_record(bpy.context, OB())
    check(f"[M65-5] another face selected: the arrow / In-View hide ({vis}), the Move manipulator is back ({man}), "
          f"INPUTS stays ({rec and rec.name})", not vis and man and rec is not None)
    labels = {p.identifier: p.name for p in bpy.ops.allset.extrude.get_rna_type().properties}
    want = [ex().LABELS[f] for f in ex().FIELDS]
    check(f"[M65-5] Adjust Last Operation shows the same Maya names ({[labels.get(f) for f in ex().FIELDS]})",
          [labels.get(f) for f in ex().FIELDS] == want)
    ts().mesh_select_mode = (False, True, False)
    b = bmesh.from_edit_mesh(OB().data)
    for e in b.edges:
        e.select_set(False)
    b.edges.ensure_lookup_table()
    b.edges[0].select_set(True)
    b.select_flush_mode()
    bmesh.update_edit_mesh(OB().data)
    C["n_edge"] = ecounts()
    hover()
    key('E', ctrl=True)


@named("m65_5_edge_check")
def _m65_5_edge_check():
    modal = [op.bl_idname for op in win().modal_operators]
    # step 139 (M4): Ctrl+E on an edge = polyExtrudeEdge at once, no mouse drag
    rec = mod("operators.extrude").current(OB())
    check(f"[M65-5] Ctrl+E on an edge = polyExtrudeEdge at once ({modal}, {rec and rec.name}, {C['n_edge']} -> {ecounts()})",
          not any(m.startswith(("TRANSFORM_OT", "MESH_OT_extrude")) for m in modal) and ecounts()[0] > C["n_edge"][0]
          and rec is not None and rec.name.startswith("polyExtrudeEdge"))
    tap('RET')


@named("m65_done")
def _m65_done():
    set_tool("builtin.select_box")
    object_mode()
    rv3d = view3d()[1].data
    rv3d.view_distance, rv3d.view_location = C["view0"]


# --- [M66-1] UV Editor entries, one window, F12 / Alt+F12 ---------------------------------------------------------
# --- [M66-3] in the UV Editor: Shift+X cut, Shift+S sew, Ctrl+U unfold, Ctrl+L layout ------------------------------

def uv_window():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.ui_type == 'UV':
                return w, a, next(r for r in a.regions if r.type == 'WINDOW')
    return None, None, None


def uv_windows():
    return [w for w in bpy.context.window_manager.windows if any(a.ui_type == 'UV' for a in w.screen.areas)]


def uv_ev(type, value, x=None, y=None, **kw):
    """sim.ev for the UV Editor window (keeps sim's simulated key state)."""
    import sim as _sim
    if value == 'PRESS':
        _sim._down.add(type)
    elif value == 'RELEASE':
        _sim._down.discard(type)
    w, _a, r = uv_window()
    if x is None:
        x, y = C.get("uvpos", (r.x + r.width // 2, r.y + r.height // 2))
    C["uvpos"] = (x, y)
    w.event_simulate(type=type, value=value, x=int(x), y=int(y), **kw)


def uv_key(type, **mods):
    uv_ev(type, 'PRESS', **mods)
    uv_ev(type, 'RELEASE', **mods)


def uv_centre():
    _w, _a, r = uv_window()
    return r.x + r.width // 2, r.y + r.height // 2


def ubm():
    b = bmesh.from_edit_mesh(OB().data)
    C["ubm"] = b
    return b


def uv_shells(selected_only=False):
    b = ubm()
    uv = b.loops.layers.uv.active
    faces = [f for f in b.faces if f.select] if selected_only else None
    return mod("operators.uv_tools").islands(b, uv, faces), uv


def close_uv_windows():
    for w in uv_windows():
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()


@named("m66_1_open")
def _m66_1_open():
    object_mode()
    clear()
    ob = create('CUBE')
    C["obname"] = ob.name
    select_only(ob)
    menu("UV/UV Editor")


@named("m66_1_open_check")
def _m66_1_open_check():
    ob = OB()
    check(f"[M66-1] UV > UV Editor: a UV Editor window, the cube in edit mode with its UVs ({len(uv_windows())} window, "
          f"{ob.mode}, {len(ob.data.uv_layers)} UV map)", len(uv_windows()) == 1 and ob.mode == 'EDIT' and len(ob.data.uv_layers) >= 1)
    menu("Windows/Modeling Editors/UV Editor")
    hover()
    tap('F12')


@named("m66_1_again_check")
def _m66_1_again_check():
    mm = mod("marking.menus")
    obj_e = None
    for name in dir(mm):
        m = getattr(mm, name)
        if isinstance(m, mm.MarkingMenu) and m.radial.get("E", (None, None))[0] == "UV":
            obj_e = m.radial["E"][1]
            if isinstance(obj_e, mm.Sub):      # step 151: Maya's UV submenu, UV at E
                obj_e = obj_e.radial["E"][1]
            break
    check(f"[M66-1] Windows > Modeling Editors > UV Editor and F12 again: still one UV Editor window ({len(uv_windows())}); "
          f"3D RMB E = UV ({obj_e})", len(uv_windows()) == 1 and obj_e == ("allset.uv_component", {"mode": 'UV'}))
    check(f"[M66-1] F12 = UV mode: sync off, vertex UVs ({ts().use_uv_select_sync}, {ts().uv_select_mode})",
          not ts().use_uv_select_sync and ts().uv_select_mode == 'VERTEX')
    hover()
    key('F12', alt=True)


@named("m66_1_shell_check")
def _m66_1_shell_check():
    b = ubm()
    # step 256: Alt+F12 = Maya's UV Shell mask (sync on, face mode, selection cleared; operators/uv_shell_select.py)
    check(f"[M66-1] Alt+F12 = UV Shell mask (sync {ts().use_uv_select_sync}, face mode "
          f"{tuple(ts().mesh_select_mode)}); selection cleared ({sum(f.select for f in b.faces)} of {len(b.faces)})",
          bpy.context.window_manager.allset_uv_shell_mask and ts().use_uv_select_sync
          and tuple(ts().mesh_select_mode) == (False, False, True) and not any(f.select for f in b.faces))
    # [M66-3] the top face's border edges in the 3D view, then the UV Editor keys
    ts().use_uv_select_sync = True
    ts().mesh_select_mode = (False, True, False)
    for el in (*b.verts, *b.edges, *b.faces):
        el.select = False
    for e in b.edges:
        e.select = all(v.co.z > 0 for v in e.verts)
    for v in b.verts:
        v.select = any(e.select for e in v.link_edges)
    bmesh.update_edit_mesh(OB().data)
    C["shells0"] = len(uv_shells()[0])
    w, a, r = uv_window()
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.image.view_all(fit_view=True)
    C["uvpos"] = uv_centre()
    uv_ev('MOUSEMOVE', 'NOTHING', *uv_centre())
    uv_key('X', shift=True)


@named("m66_3_cut_check")
def _m66_3_cut_check():
    isls, uv = uv_shells()
    b = ubm()
    seams = sum(e.seam for e in b.edges)
    check(f"[M66-3] Shift+X: red seams on the 4 edges, the shell splits ({C['shells0']} -> {len(isls)})",
          seams == 4 and len(isls) > C["shells0"])
    # step 129: Maya's cube UV layout is a cross strip, cutting the top splits the strip too (1 -> 3)
    C["shells_cut"] = len(isls)
    # island selection picks only one side now
    top = next(f for f in b.faces if f.normal.z > 0.9)
    isl = next(i for i in isls if top in i)
    check(f"[M66-3] island selection takes only one side (the top shell has {len(isl)} face)", len(isl) == 1)
    uv_key('S', shift=True)


@named("m66_3_sew_check")
def _m66_3_sew_check():
    isls, _uv = uv_shells()
    b = ubm()
    check(f"[M66-3] Shift+S sews the small shell back onto the edges ({len(isls)} shells, {sum(e.seam for e in b.edges)} seams)",
          len(isls) == C["shells0"] and sum(e.seam for e in b.edges) == 0)
    uv_key('X', shift=True)


@named("m66_3_unfold")
def _m66_3_unfold():
    isls, uv = uv_shells()
    C["centres"] = sorted(round(c, 3) for isl in isls for c in mod("operators.uv_tools").uv_centre(isl, uv))
    uv_key('U', ctrl=True)


@named("m66_3_unfold_check")
def _m66_3_unfold_check():
    isls, uv = uv_shells()
    after = sorted(round(c, 3) for isl in isls for c in mod("operators.uv_tools").uv_centre(isl, uv))
    check(f"[M66-3] ... in place (shell centres {C['centres']} -> {after})",
          len(after) == len(C["centres"]) and all(abs(a - b) < 0.05 for a, b in zip(after, C["centres"])))
    note = mod("operators.uv_tools").NOTICE_UNFOLD   # its Help Line report (Python can't read reports)
    check(f"[M66-3] Ctrl+U unfolds the shells where they are ({len(isls)} shells); the Help Line notes the shape "
          f"differs from Unfold3D ({note!r})", len(isls) == C["shells_cut"] and "Unfold3D" in note)
    b = ubm()
    for el in (*b.verts, *b.edges, *b.faces):
        el.select = False
    bmesh.update_edit_mesh(OB().data)
    uv_key('L', ctrl=True)


@named("m66_3_layout_check")
def _m66_3_layout_check():
    isls, uv = uv_shells()
    ut = mod("operators.uv_tools")
    us = [l[uv].uv for isl in isls for f in isl for l in f.loops]
    inside = all(-1e-5 <= u.x <= 1 + 1e-5 and -1e-5 <= u.y <= 1 + 1e-5 for u in us)
    from mathutils import geometry as _geo
    tris = []
    for i, isl in enumerate(isls):
        for f in isl:
            p = [l[uv].uv.copy() for l in f.loops]
            for j in range(1, len(p) - 1):
                tris.append((i, (p[0], p[j], p[j + 1])))
    overlap = any(tris[a][0] != tris[b][0] and _geo.intersect_tri_tri_2d(*tris[a][1], *tris[b][1])
                  for a in range(len(tris)) for b in range(a + 1, len(tris)))
    dens = [ut.density(isl, uv, OB().matrix_world, 1024, k()) for isl in isls]
    same = max(dens) - min(dens) < 0.02 * max(dens)
    check(f"[M66-3] Ctrl+L: all UVs inside 0-1, no overlapping shells, the same texel density "
          f"({inside}, overlap {overlap}, {[round(d, 1) for d in dens]})", inside and not overlap and same)
    close_uv_windows()
    object_mode()


# --- [M67-2] Hypershade browser previews, pick (graph + Property Editor, pin), Create (kept on save), Assign -----------
# --- [M67-3] AE map button: Create Render Node File / Ramp / Noise / Checker, connected rows, Break, Bump -------------
# --- [M67-4] F6 Render menu items, Batch Render greyed, Render Current Frame -> Render View header ----------------------
# --- [M67-5] Keep Image -> next render in a new slot, J / Alt+J between slots, Remove Image clears the slot -------------

def wait(fn, cond, limit=40):
    """Run ``fn`` again next tick until ``cond()`` or ``limit`` ticks; True = it was queued again."""
    import sim as _sim
    key = "wait_" + fn.__name__
    C.setdefault(key, 0)
    if not cond() and C[key] < limit:
        C[key] += 1
        _sim._steps.insert(0, fn)
        return True
    return False


class OpRecorder:
    """Stands in for a UILayout: records operators (idname, text, props), menus, labels and template_ID calls."""

    def __init__(self, out=None):
        self.out = out if out is not None else []

    def _sub(self, *_a, **_kw):
        return OpRecorder(self.out)

    row = column = box = split = grid_flow = _sub

    def __getattr__(self, name):
        return self._sub

    def separator(self, *_a, **_kw):
        pass

    def label(self, text="", **_kw):
        self.out.append(("label", text, None))

    def menu(self, idname, text="", **_kw):
        self.out.append(("menu", text, idname))

    def panel(self, *_a, **_kw):
        return OpRecorder(self.out), OpRecorder(self.out)

    def template_ID(self, data, prop, new="", open="", **_kw):
        self.out.append(("template_ID", prop, (new, open)))

    def operator(self, idname, text="", **_kw):
        rec = {}

        class _Props:
            def __setattr__(self, k, v):
                rec[k] = v
        self.out.append(("op", text, (idname, rec)))
        return _Props()

    operator_menu_hold = operator


def can_save_render(image):
    """True when the shown render slot holds an image (save_render fails on an empty slot)."""
    path = os.path.join(tempfile.gettempdir(), "allset_sweep_slot.png")
    try:
        image.save_render(path)
    except RuntimeError:
        return False
    ok = os.path.exists(path)
    if ok:
        os.remove(path)
    return ok


def window_with(ui_type):
    for w in bpy.context.window_manager.windows[1:]:
        for a in w.screen.areas:
            if a.ui_type == ui_type:
                return w, a
    return None, None


def hs_window():
    """(window, Graph area) of the Hypershade once its layout is complete (step 131), else (None, None)."""
    hs = mod("ui.hypershade")
    for w in bpy.context.window_manager.windows[1:]:
        if sum(1 for a in w.screen.areas if hs.pane(a)) == 4 and hs.graph_area(w.screen) is not None:
            return w, hs.graph_area(w.screen)
    return None, None


def hs_ctx():
    w, a = hs_window()
    ui = next(r for r in a.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(window=w, area=a, region=ui, space_data=a.spaces.active)


def close_extra_windows():
    for w in list(bpy.context.window_manager.windows)[1:]:
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()


@named("m67_2_setup")
def _m67_2_setup():
    object_mode()
    clear()
    sc = bpy.context.scene
    C["render0"] = (sc.render.engine, sc.render.resolution_percentage)
    sc.render.resolution_percentage = 25
    cam = create('CAMERA')
    cam.location = (0, -12 * k(), 4 * k())
    cam.rotation_euler = (math.radians(75), 0, 0)
    sc.camera = cam
    ob = create('SPHERE')
    C["obname"] = ob.name
    select_only(ob)
    with override():
        bpy.ops.allset.assign_new_material(kind='LAMBERT')
    C["onmat"] = ob.active_material.name
    menu("Windows/Rendering Editors/Hypershade")


@named("m67_2_open")
def _m67_2_open():
    w, a = hs_window()
    if wait(_m67_2_open, lambda: hs_window()[0] is not None):
        return
    w, a = hs_window()
    with hs_ctx():
        bpy.ops.allset.hs_create(kind='STANDARD_SURFACE')
    C["newmat"] = bpy.context.window_manager.allset_hs_material
    mat = bpy.data.materials.get(C["newmat"])
    check(f"[M67-2] Create = a new material, not assigned ({mat is not None}, users {mat.users if mat else None}, "
          f"slots {[s.material.name for s in OB().material_slots]})",
          mat is not None and C["newmat"] not in [s.material.name for s in OB().material_slots])
    for m in bpy.data.materials:
        m.preview_ensure()
    w.screen.areas[0].tag_redraw()
    for r in a.regions:
        r.tag_redraw()


@named("m67_2_previews")
def _m67_2_previews():
    mats = [bpy.data.materials[n] for n in (C["onmat"], C["newmat"])]

    def rendered():
        return all(m.preview is not None and any(list(m.preview.icon_pixels)[::97]) for m in mats)
    if wait(_m67_2_previews, rendered, limit=60):
        w, a = hs_window()
        for r in a.regions:
            r.tag_redraw()
        return
    check(f"[M67-2] the Browser swatches get rendered previews ({[m.name for m in mats]}: {rendered()})", rendered())
    w, a = window_with('ShaderNodeTree')
    with hs_ctx():
        bpy.ops.allset.hs_pick(material=C["newmat"])
    sp = a.spaces.active
    with hs_ctx():
        cur = mod("ui.hypershade").current(bpy.context)
    check(f"[M67-2] click a material the object doesn't have: graph + Property Editor show it, pin on "
          f"({cur.name if cur else None}, pin {sp.pin}, graph {sp.node_tree.name if sp.node_tree else None})",
          cur and cur.name == C["newmat"] and sp.pin and sp.node_tree == bpy.data.materials[C["newmat"]].node_tree)
    with hs_ctx():
        bpy.ops.allset.hs_pick(material=C["onmat"])
        cur = mod("ui.hypershade").current(bpy.context)
    check(f"[M67-2] click the object's material: it is shown, the graph follows the object (pin {sp.pin})",
          cur.name == C["onmat"] and not sp.pin)
    # Create keeps the material on save (Blender drops datablocks without users)
    path = os.path.join(tempfile.gettempdir(), "allset_sweep_m67.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    with bpy.data.libraries.load(path) as (src, _dst):
        saved = list(src.materials)
    os.remove(path)
    check(f"[M67-2] the created material is in the saved file ({C['newmat']} in {saved})", C["newmat"] in saved)


@named("m67_2_assign")
def _m67_2_assign():
    ob = OB()
    with hs_ctx():
        bpy.ops.allset.assign_material(material=C["newmat"])
    check(f"[M67-2] Assign Material To Selection: the object gets it ({[s.material.name for s in ob.material_slots]})",
          [s.material.name for s in ob.material_slots] == [C["newmat"]])
    # face selection mode: only the selected faces
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
    b = bmesh.from_edit_mesh(ob.data)
    for f in b.faces:
        f.select_set(f.calc_center_median().z > 0.6 * k())
    C["topfaces"] = sum(f.select for f in b.faces)
    bmesh.update_edit_mesh(ob.data)
    with hs_ctx():
        bpy.ops.allset.assign_material(material=C["onmat"])


@named("m67_2_faces")
def _m67_2_faces():
    ob = OB()
    object_mode()
    names = [s.material.name if s.material else None for s in ob.material_slots]
    on = names.index(C["onmat"]) if C["onmat"] in names else -1
    got = sum(p.material_index == on for p in ob.data.polygons)
    check(f"[M67-2] face selection mode: only the selected faces get it ({got} of {len(ob.data.polygons)}, "
          f"selected {C['topfaces']})", on >= 0 and got == C["topfaces"] > 0)


@named("m67_3_map")
def _m67_3_map():
    sm = mod("operators.shading_maps")
    mat = bpy.data.materials[C["newmat"]]
    with hs_ctx():
        res = bpy.ops.allset.ae_map('INVOKE_DEFAULT', material=mat.name, socket="Base Color")
    check(f"[M67-3] the map button opens Create Render Node with File / Ramp / Noise / Checker ({res}, "
          f"{[v[0] for v in sm.MAPS.values()]})", res == {'FINISHED'} and list(sm.MAPS) == ['FILE', 'RAMP', 'NOISE', 'CHECKER'])
    # the popup's rows run allset.ae_map_connect (one per texture kind)
    node = sm.principled(mat)
    for kind, socket in (('FILE', "Base Color"), ('RAMP', "Roughness"), ('NOISE', "Metallic"), ('CHECKER', "Alpha")):
        with hs_ctx():
            bpy.ops.allset.ae_map_connect(material=mat.name, socket=socket, kind=kind)
        inp = node.inputs[socket]
        src = inp.links[0].from_node if inp.is_linked else None
        check(f"[M67-3] {kind} on {socket}: a texture node left of the shader, linked "
              f"({src.type if src else None}, x {round(src.location.x) if src else None} < {round(node.location.x)})",
              src is not None and src.location.x < node.location.x)
    esc_modals()


@named("m67_3_rows")
def _m67_3_rows():
    sm = mod("operators.shading_maps")
    ae = mod("ui.attribute_editor")
    mat = bpy.data.materials[C["newmat"]]
    rec = OpRecorder()
    with override():
        ae.draw_row(rec, bpy.context, OB(), mat, ("socket", "Base Color", "Color"))
    labels = [t for kind, t, _x in rec.out if kind == "label"]
    tid = [x for kind, _t, x in rec.out if kind == "template_ID"]
    check(f"[M67-3] the connected row reads 'connected (…)', File gets the image New / Open ({labels}, {tid})",
          any("connected (" in t for t in labels) and tid == [("image.new", "image.open")])

    class _P:
        socket = "Base Color"
    tip = sm.ALLSET_OT_ae_map.description(bpy.context, _P())
    check(f"[M67-3] the button's tooltip names the Maya attribute ({tip!r})", tip.startswith("baseColor"))
    with hs_ctx():
        bpy.ops.allset.ae_map_break(material=mat.name, socket="Base Color")
    inp = sm.principled(mat).inputs["Base Color"]
    tex = [n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE']
    check(f"[M67-3] Break Connection: unlinked, the File node stays ({inp.is_linked}, {len(tex)} image node)",
          not inp.is_linked and len(tex) == 1)
    with hs_ctx():
        bpy.ops.allset.ae_map_connect(material=mat.name, socket="Normal", kind='NOISE')
    inp = sm.principled(mat).inputs["Normal"]
    src = inp.links[0].from_node if inp.is_linked else None
    via = src.inputs["Height"].links[0].from_node.type if src is not None and src.inputs["Height"].is_linked else None
    check(f"[M67-3] Normal goes through a Bump node ({src.type if src else None} <- {via})",
          src is not None and src.type == 'BUMP' and via == 'TEX_NOISE')


@named("m67_4_f6")
def _m67_4_f6():
    close_extra_windows()
    hover()
    tap('F6')


@named("m67_4_menu")
def _m67_4_menu():
    ms = mod("ui.menu_sets")
    check(f"[M67-4] F6 = Rendering menu set ({ms.current_set()})", ms.current_set() == 'renderingMenuSet')
    # material previews need the scene engine's preview support (Workbench has none): switch only for the renders
    bpy.context.scene.render.engine = 'BLENDER_WORKBENCH'
    cls = getattr(bpy.types, ms.menu_idname("mainRenderMenu"))
    rec = OpRecorder()

    class _M:
        layout = rec
    with override():
        cls.draw(_M(), bpy.context)
    # step 103: option-box items end with the box mark; step 108: right-aligned after a filler (+ Maya hotkey)
    rec.out = [(kind, t.replace(ms.HAIR, "").replace(ms.BOX_MARK.strip(), "").strip() if isinstance(t, str) else t, x)
               for kind, t, x in rec.out]
    texts = [t for kind, t, _x in rec.out if kind in ("op", "menu")]
    want = ["Render Settings...", "Render Using", "Render Current Frame", "Redo Previous Render",
            "IPR Render Current Frame", "Render Sequence", "Batch Render"]
    order = [texts.index(t) for t in want if t in texts]
    check(f"[M67-4] Render menu: {' / '.join(want)} in this order ({texts})",
          len(order) == len(want) and order == sorted(order))
    using = next(x for kind, t, x in rec.out if t == "Render Using")
    batch = next(x for kind, t, x in rec.out if t == "Batch Render" and kind == "op")
    tip = mod("ui.notices").tooltip("Render/Batch Render", False)
    # Batch Render runs Blender's Render Animation, its tooltip names the command-line way
    check(f"[M67-4] Render Using = engine list ({using}), Batch Render runs ({batch[0]}) with 'blender -b' "
          f"in its tooltip", using == "ALLSET_MT_render_using" and batch[0] == "allset.menu_item"
          and "blender -b" in tip)
    sc = bpy.context.scene
    if sc.camera is None:       # Blender renders through the scene camera
        sc.camera = next((o for o in sc.objects if o.type == 'CAMERA'), None)
    if sc.camera is None:
        cam = bpy.data.objects.new("camera1", bpy.data.cameras.new("cameraShape1"))
        sc.collection.objects.link(cam)
        cam.location = (28.0, -28.0, 21.0)
        cam.rotation_euler = (1.1, 0.0, 0.785)
        sc.camera = cam
    menu("Render/Render Current Frame")


@named("m67_4_rendered")
def _m67_4_rendered():
    if wait(_m67_4_rendered, lambda: not bpy.app.is_job_running('RENDER') and window_with('IMAGE_EDITOR')[0] is not None):
        return
    rv = mod("ui.render_view")
    w, a = window_with('IMAGE_EDITOR')
    image = rv.render_result()
    check(f"[M67-4] Render Current Frame: a Render Result window ({a is not None}, "
          f"{a.spaces.active.image.name if a and a.spaces.active.image else None})",
          a is not None and a.spaces.active.image == image)
    image[rv.KEPT_PROP] = []
    image.render_slots.active_index = 0
    rec = OpRecorder()
    with bpy.context.temp_override(window=w, area=a, space_data=a.spaces.active):
        rv.draw_header(rec, bpy.context)
    got = [(x[0] if kind == "op" else t) for kind, t, x in rec.out]
    check(f"[M67-4] its header starts Render · Keep Image · Remove Image · 'Slot N · k kept' ({got})",
          got[:3] == ["render.render", "allset.render_keep_image", "allset.render_remove_image"]
          and got[3].startswith("Slot 1") and got[3].endswith("0 kept"))
    C["rv"] = (w, a)
    with bpy.context.temp_override(window=w, area=a, space_data=a.spaces.active):
        bpy.ops.allset.render_keep_image()
    menu("Render/Render Current Frame")


@named("m67_5_rendered2")
def _m67_5_rendered2():
    if wait(_m67_5_rendered2, lambda: not bpy.app.is_job_running('RENDER')):
        return
    rv = mod("ui.render_view")
    image = rv.render_result()
    check(f"[M67-5] Keep Image -> render again: slot 1 kept, the new render in slot 2 "
          f"(kept {sorted(rv.kept(image))}, active {image.render_slots.active_index})",
          rv.kept(image) == {0} and image.render_slots.active_index == 1)
    w, a = C["rv"]
    r = next(r for r in a.regions if r.type == 'WINDOW')
    C["rvpos"] = (r.x + r.width // 2, r.y + r.height // 2)
    w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=C["rvpos"][0], y=C["rvpos"][1])
    w.event_simulate(type='J', value='PRESS', x=C["rvpos"][0], y=C["rvpos"][1])
    w.event_simulate(type='J', value='RELEASE', x=C["rvpos"][0], y=C["rvpos"][1])


@named("m67_5_j")
def _m67_5_j():
    image = mod("ui.render_view").render_result()
    C["after_j"] = image.render_slots.active_index
    w, _a = C["rv"]
    import sim as _sim
    x, y = C["rvpos"]
    w.event_simulate(type='LEFT_ALT', value='PRESS', x=x, y=y)
    _sim._down.add('LEFT_ALT')
    w.event_simulate(type='J', value='PRESS', x=x, y=y, alt=True)
    w.event_simulate(type='J', value='RELEASE', x=x, y=y, alt=True)
    w.event_simulate(type='LEFT_ALT', value='RELEASE', x=x, y=y)
    _sim._down.discard('LEFT_ALT')


@named("m67_5_alt_j")
def _m67_5_alt_j():
    rv = mod("ui.render_view")
    image = rv.render_result()
    check(f"[M67-5] J / Alt+J step between the rendered slots (2 -> {C['after_j'] + 1} -> "
          f"{image.render_slots.active_index + 1})", C["after_j"] == 0 and image.render_slots.active_index == 1)
    w, a = C["rv"]
    C["saved_before"] = can_save_render(image)
    with bpy.context.temp_override(window=w, area=a, space_data=a.spaces.active):
        bpy.ops.allset.render_remove_image()
    a.tag_redraw()


@named("m67_5_removed")
def _m67_5_removed():
    image = mod("ui.render_view").render_result()
    after = can_save_render(image)
    check(f"[M67-5] Remove Image empties the shown slot (its image saves before: {C['saved_before']}, after: {after})",
          C["saved_before"] and not after)
    close_extra_windows()
    sc = bpy.context.scene
    sc.render.engine, sc.render.resolution_percentage = C["render0"]
    hover()
    tap('F2')


# --- [M68-2] Emit from Object on two meshes, shelf Emitter / Add Emitter ----------------------------------------------
# --- [M68-4] FX creation runs Blender's own operators: no nucleus tab, the scene gravity is left alone -----------------
# --- [M68-5] nCache > Create New Cache > nObject (selection / whole scene), Delete Cache, greyed Enable / Disable -----
# --- [M68-6] Create Active Rigid Body on several meshes: they fall onto a Passive floor and stop (a metre scene) -------

def shelf_action(shelf, label):
    sh = mod("ui.shelf")
    return next(((i, a) for i, lab, a, _icon in sh.all_buttons(shelf) if lab == label), (None, None))


def run_shelf(shelf, label):
    i, _a = shelf_action(shelf, label)
    with override():
        return bpy.ops.allset.shelf_button(shelf=shelf, index=i)


def cloth_md(ob):
    return next(m for m in ob.modifiers if m.type == 'CLOTH')


def metre_scene(on):
    """FX works in metre scenes: the rigid body checks run with metres shown (one unit = 1 m)."""
    us = bpy.context.scene.unit_settings
    if on:
        C["units0"] = (us.system, us.length_unit, us.scale_length)
        us.system, us.length_unit, us.scale_length = 'METRIC', 'METERS', 1.0
    elif "units0" in C:
        us.system, us.length_unit, us.scale_length = C.pop("units0")


@named("m68_2_emit")
def _m68_2_emit():
    object_mode()
    clear()
    sc = bpy.context.scene
    C["frames0"] = (sc.frame_start, sc.frame_end)
    sc.frame_end = sc.frame_start + 80
    sc.frame_set(sc.frame_start)
    a = create('CUBE')
    b = create('SPHERE')
    b.location.x = 4 * k()
    select_only(a, b)
    menu("nParticles/Emit from Object")
    ok = all(len(o.particle_systems) == 1 for o in (a, b))
    check(f"[M68-2] Emit from Object with two meshes: both get a Blender particle system "
          f"({[(o.name, len(o.particle_systems)) for o in (a, b)]})", ok)
    _i, act = shelf_action("FX", "Emitter")
    check(f"[M68-2] shelf FX 'Emitter' is greyed like nParticles > Create Emitter ({act})", act is None)
    _i, act = shelf_action("FX", "Add Emitter")
    check(f"[M68-2] shelf FX 'Add Emitter' = Blender's particle system ({act})",
          isinstance(act, tuple) and act[0] == "object.modifier_add" and act[1].get("type") == 'PARTICLE_SYSTEM')
    select_only(a)
    run_shelf("FX", "Add Emitter")
    check(f"[M68-2] the shelf's Add Emitter adds an emitter to the selected mesh ({len(a.particle_systems)} systems)",
          len(a.particle_systems) == 2)


@named("m68_4_setup")
def _m68_4_setup():
    clear()
    sc = bpy.context.scene
    gravity0 = tuple(sc.gravity)
    cloth = create('PLANE')
    cloth.location.z = 20 * k()
    C["cloth"] = cloth.name
    select_only(cloth)
    menu("nCloth/Create nCloth")
    floor = create('PLANE')
    floor.scale = (10, 10, 10)
    C["floor"] = floor.name
    select_only(floor)
    menu("nCloth/Create Passive Collider")
    em = create('SPHERE')
    em.location.x = -6 * k()
    select_only(em)
    menu("nParticles/Emit from Object")
    C["emitter"] = em.name
    cube = create('CUBE')
    cube.location.x = 6 * k()
    C["rigid"] = cube.name
    select_only(cube)
    menu("Fields/Solvers/Create Active Rigid Body")
    names = [C[n] for n in ("cloth", "floor", "emitter", "rigid")]
    made = {"cloth": any(m.type == 'CLOTH' for m in cloth.modifiers),
            "collider": any(m.type == 'COLLISION' for m in floor.modifiers),
            "particles": bool(em.particle_systems), "rigid": cube.rigid_body is not None}
    check(f"[M68-4] nCloth / Passive Collider / Emit from Object / Active Rigid Body make Blender's own ({made})",
          all(made.values()))
    tabs = {n: [t[0] for t in mod("ui.attribute_editor").tabs(sc.objects[n])] for n in names}
    check(f"[M68-4] no nucleus tab in the AE ({tabs})", not any("NUC" in t for t in tabs.values()))
    check(f"[M68-4] the scene gravity is left alone ({gravity0} -> {tuple(sc.gravity)})", tuple(sc.gravity) == gravity0)
    tip = mod("ui.notices").tooltip("nCloth/Create nCloth", True)
    check(f"[M68-4] Create nCloth's tooltip says FX works in metre scenes ({tip[:60]!r}…)", "metre scenes" in tip)


@named("m68_5_selection")
def _m68_5_selection():
    sc = bpy.context.scene
    cloth = sc.objects[C["cloth"]]
    select_only(cloth)
    menu("nCache/Create New Cache/nObject")
    em = sc.objects[C["emitter"]]
    check(f"[M68-5] Create New Cache > nObject with the cloth selected: its cache is baked, the particles' not "
          f"({cloth_md(cloth).point_cache.is_baked}, {em.particle_systems[0].point_cache.is_baked})",
          cloth_md(cloth).point_cache.is_baked and not em.particle_systems[0].point_cache.is_baked)
    menu("nCache/Delete Cache")
    check(f"[M68-5] Delete Cache: simulated again ({cloth_md(cloth).point_cache.is_baked})",
          not cloth_md(cloth).point_cache.is_baked)
    for o in sc.objects:
        o.select_set(False)
    menu("nCache/Create New Cache/nObject")
    baked = {"cloth": cloth_md(cloth).point_cache.is_baked, "particles": em.particle_systems[0].point_cache.is_baked,
             "rigid": sc.rigidbody_world.point_cache.is_baked}
    check(f"[M68-5] nothing selected: the whole scene is cached ({baked})", all(baked.values()))
    menu("nCache/Delete Cache")
    gone = not any((cloth_md(cloth).point_cache.is_baked, em.particle_systems[0].point_cache.is_baked,
                    sc.rigidbody_world.point_cache.is_baked))
    check(f"[M68-5] Delete Cache with nothing selected frees them all ({gone})", gone)
    nt = mod("ui.notices")
    for item in ("Enable All Caches on Selected", "Disable All Caches on Selected"):
        path = f"nCache/{item}"
        spec = mod("ui.menu_map").spec(path)
        check(f"[M68-5] {item}: greyed with a notice ({spec}, {nt.tooltip(path, False)[:50]!r}…)",
              spec is None and "Delete Cache" in nt.tooltip(path, False))


@named("m68_6_rigid")
def _m68_6_rigid():
    clear()
    metre_scene(True)
    sc = bpy.context.scene
    if sc.rigidbody_world is not None:
        with override():
            bpy.ops.rigidbody.world_remove()
    floor = create('PLANE')
    floor.scale = (10, 10, 10)
    select_only(floor)
    menu("Fields/Solvers/Create Passive Rigid Body")
    cubes = []
    for i in range(3):
        c = create('CUBE')
        c.location = ((i - 1) * 3 * k(), 0, (4 + 2 * i) * k())
        cubes.append(c)
    select_only(*cubes)
    menu("Fields/Solvers/Create Active Rigid Body")
    kinds = [c.rigid_body.type if c.rigid_body else None for c in cubes]
    check(f"[M68-6] Create Active Rigid Body with three cubes selected: all active ({kinds}), the floor passive "
          f"({floor.rigid_body.type if floor.rigid_body else None})",
          kinds == ['ACTIVE'] * 3 and floor.rigid_body and floor.rigid_body.type == 'PASSIVE')
    C["cubes"] = [c.name for c in cubes]
    sc.frame_set(sc.frame_start)


@named("m68_6_fall")
def _m68_6_fall():
    sc = bpy.context.scene
    zs = {}
    for f in range(sc.frame_start, sc.frame_start + 73):
        sc.frame_set(f)
        if f - sc.frame_start in (60, 72):
            dg = bpy.context.evaluated_depsgraph_get()
            zs[f - sc.frame_start] = [sc.objects[n].evaluated_get(dg).matrix_world.translation.z / k() for n in C["cubes"]]
    end, before = zs[72], zs[60]
    check(f"[M68-6] three seconds: the cubes fell onto the floor and stay there (centre z {[round(z, 2) for z in end]}, "
          f"cube half size 0.5; half a second earlier {[round(z, 2) for z in before]})", all(0.3 < z < 0.8 for z in end) and all(abs(a - b) < 0.05 for a, b in zip(end, before)))
    clear()
    if sc.rigidbody_world is not None:
        with override():
            bpy.ops.rigidbody.world_remove()
    metre_scene(False)
    sc.frame_start, sc.frame_end = C["frames0"]
    sc.frame_set(sc.frame_start)


# --- [M69-2] with a project: Ctrl+O / Ctrl+Shift+S / first Ctrl+S / Status Line icons / File menu start in scenes, ----
#             render output //../images/ (a user path stays), a moved project's scene makes it current
# --- [M69-4] Ctrl+R Create Reference: browser in scenes + Namespace / Editable, prop:pCube1 under prop, movable and
#             keyable, source file unchanged, prop1: the second time; editors keep their own Ctrl+R
# --- [M69-5] File > Reference Editor: an Outliner window in Blender File view, the library row reloads ----------------

def proj():
    return mod("operators.project")


def file_browser():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == 'FILE_BROWSER' and a.spaces.active.params is not None:
                return w, a
    return None, None


def browser_dir():
    _w, a = file_browser()
    if a is None:
        return None
    d = a.spaces.active.params.directory
    d = d.decode() if isinstance(d, bytes) else d
    return os.path.normcase(os.path.normpath(bpy.path.abspath(d)))


def browser_op():
    _w, a = file_browser()
    return a.spaces.active.active_operator if a is not None else None


def close_browser():
    w, a = file_browser()
    if w is None:
        return
    r = next(r for r in a.regions if r.type == 'WINDOW')
    x, y = r.x + r.width // 2, r.y + r.height // 2
    w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    w.event_simulate(type='ESC', value='PRESS', x=x, y=y)
    w.event_simulate(type='ESC', value='RELEASE', x=x, y=y)


def scenes_dir():
    return os.path.normcase(os.path.join(C["proj"], "scenes"))


def browser_check(name, label, then):
    """A step: wait for the file browser, check it starts in <project>/scenes, close it, then ``then()``."""
    @named(name)
    def _check():
        if wait(_check, lambda: file_browser()[0] is not None, limit=12):
            return
        got = browser_dir()
        check(f"[M69-2] {label}: the file browser starts in <project>/scenes ({got})", got == scenes_dir())
        close_browser()

    @named(name + "_next")
    def _next():
        if wait(_next, lambda: file_browser()[0] is None, limit=12):
            return
        hover()
        then()


@named("m69_2_new")
def _m69_2_new():
    object_mode()
    load_maya_layout()   # an unsaved scene: the first Ctrl+S asks for a name


@named("m69_2_project")
def _m69_2_project():
    bpy.ops.allset.keymap_activate()
    C["proj_parent"] = tempfile.mkdtemp(prefix="allset_sweep_proj_")
    C["proj0"] = proj().current_root()
    bpy.ops.allset.project_window(name="proj97", location=C["proj_parent"])
    C["proj"] = os.path.join(C["proj_parent"], "proj97")
    check(f"[M69-2] a current project ({proj().current_root()})",
          os.path.normcase(proj().current_root()) == os.path.normcase(C["proj"]))
    bpy.data.objects.get("pCube1") or create('CUBE')
    hover()
    key('S', ctrl=True)


browser_check("m69_2_ctrl_s", "first Ctrl+S (unsaved scene)", lambda: key('O', ctrl=True))
browser_check("m69_2_ctrl_o", "Ctrl+O", lambda: key('S', ctrl=True, shift=True))


def _status_open():
    with override():
        bpy.ops.allset.open_scene('INVOKE_DEFAULT')


browser_check("m69_2_ctrl_shift_s", "Ctrl+Shift+S", _status_open)


def _status_save():
    with override():
        bpy.ops.allset.save_scene('INVOKE_DEFAULT')


browser_check("m69_2_status_open", "Status Line open icon (allset.open_scene)", _status_save)


def _menu_open():
    with override():
        mod("marking.modal").run_action(bpy.context, mod("ui.menu_map").MAP["File/Open Scene..."])


browser_check("m69_2_status_save", "Status Line save icon (allset.save_scene)", _menu_open)


def _menu_save_as():
    with override():
        mod("marking.modal").run_action(bpy.context, mod("ui.menu_map").MAP["File/Save Scene As..."])


browser_check("m69_2_menu_open", "File > Open Scene...", _menu_save_as)
browser_check("m69_2_menu_save_as", "File > Save Scene As...", lambda: None)


@named("m69_2_render_output")
def _m69_2_render_output():
    sc = bpy.context.scene
    sc.render.filepath = "/tmp\\"                   # Blender's default output
    C["shot"] = os.path.join(C["proj"], "scenes", "shot.blend")
    bpy.ops.wm.save_as_mainfile(filepath=C["shot"])
    check(f"[M69-2] saved in the project: render output = //../images/ ({sc.render.filepath})",
          sc.render.filepath == "//../images/")
    sc.render.filepath = "//my_renders/"
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(C["proj"], "scenes", "shot2.blend"))
    check(f"[M69-2] a path the user set stays ({sc.render.filepath})", sc.render.filepath == "//my_renders/")
    sc.render.filepath = "//../images/"
    bpy.ops.wm.save_as_mainfile(filepath=C["shot"])
    # "another computer": the project folder copied elsewhere, open its scene there
    import shutil
    C["moved"] = os.path.join(tempfile.mkdtemp(prefix="allset_sweep_moved_"), "proj97")
    shutil.copytree(C["proj"], C["moved"])
    proj().set_current(C["proj"])
    bpy.ops.wm.open_mainfile(filepath=os.path.join(C["moved"], "scenes", "shot.blend"))


@named("m69_2_moved")
def _m69_2_moved():
    check(f"[M69-2] opening a scene of the moved project makes that project current ({proj().current_root()})",
          os.path.normcase(proj().current_root()) == os.path.normcase(C["moved"]))
    proj().set_current(C["proj"])
    hover()
    key('R', ctrl=True)


@named("m69_4_browser")
def _m69_4_browser():
    if wait(_m69_4_browser, lambda: file_browser()[0] is not None, limit=12):
        return
    got = browser_dir()
    op = browser_op()
    props = {p.identifier for p in op.properties.bl_rna.properties} if op is not None else set()
    check(f"[M69-4] Ctrl+R = Create Reference: the browser starts in <project>/scenes ({got}), options Namespace / "
          f"Editable ({op.bl_idname if op else None})",
          got == scenes_dir() and op is not None and op.bl_idname == "ALLSET_OT_create_reference"
          and {"namespace", "editable"} <= props)
    close_browser()


@named("m69_4_reference")
def _m69_4_reference():
    if wait(_m69_4_reference, lambda: file_browser()[0] is None, limit=12):
        return
    src = os.path.join(C["proj"], "scenes", "prop_src.blend")
    # the source = this scene's cube saved on its own
    bpy.ops.wm.save_as_mainfile(filepath=src, copy=True)
    C["src"], C["src_mtime"] = src, os.path.getmtime(src)
    with override():
        bpy.ops.allset.create_reference(filepath=src, namespace="prop")
    ob = bpy.data.objects.get("prop:pCube1")
    coll = bpy.data.collections.get("prop")
    check(f"[M69-4] prop:pCube1 in the prop collection ({ob is not None}, "
          f"{[c.name for c in ob.users_collection] if ob else None}, prop collection {coll is not None})",
          ob is not None and coll is not None and (coll in ob.users_collection
                                                   or any(ob.name in c.all_objects for c in [coll])))
    ob.location.x += 3 * k()
    ok_key = ob.keyframe_insert("location", index=0)
    check(f"[M69-4] it moves and takes keys (x {ob.location.x / k():.1f}, key {ok_key}), the source file is unchanged "
          f"({os.path.getmtime(src) == C['src_mtime']})", ok_key and abs(ob.location.x / k() - 3) < 0.6
          and os.path.getmtime(src) == C["src_mtime"])
    with override():
        bpy.ops.allset.create_reference(filepath=src, namespace="prop")
    check(f"[M69-4] the same file again = prop1: ({[o.name for o in bpy.data.objects if o.name.startswith('prop1:')]})",
          bpy.data.objects.get("prop1:pCube1") is not None)
    # other editors keep their own Ctrl+R (Window items run after editor keymaps)
    kc = bpy.context.window_manager.keyconfigs.user
    own = {}
    for km_name, idname in (("File Browser", "file.refresh"), ("Image Generic", "image.read_viewlayers"),
                            ("Sequencer", "sequencer.reload")):
        km = kc.keymaps.get(km_name)
        own[km_name] = bool(km) and any(i.idname == idname and i.type == 'R' and i.ctrl and i.active
                                        for i in km.keymap_items)
    window_r = any(i.idname == "allset.create_reference" and i.type == 'R' and i.ctrl
                   for i in kc.keymaps["Window"].keymap_items)
    check(f"[M69-4] Ctrl+R = Create Reference in the Window keymap ({window_r}); File Browser / Image / Sequencer "
          f"keep their Ctrl+R refresh ({own})", window_r and all(own.values()))
    C["nwin"] = len(bpy.context.window_manager.windows)
    menu("File/Reference Editor")


@named("m69_5_editor")
def _m69_5_editor():
    w = bpy.context.window_manager.windows[-1]
    a = w.screen.areas[0]
    sp = a.spaces.active
    lib = os.path.basename(C["src"])
    # since step 209 the Reference Editor is the kit's Maya window (a marked Properties Tool tab, ui/reference_editor.py)
    check(f"[M69-5] File > Reference Editor: the kit's Reference Editor window, {lib} loaded "
          f"({len(bpy.context.window_manager.windows) - C['nwin']} new, {a.type})",
          len(bpy.context.window_manager.windows) == C["nwin"] + 1 and a.type == 'PROPERTIES'
          and lib in bpy.data.libraries)
    # the library row's context menu Reload (Blender's Outliner library operation = Library.reload)
    bpy.data.libraries[lib].reload()
    check(f"[M69-5] Reload keeps the referenced objects ({bpy.data.objects.get('prop:pCube1') is not None})",
          bpy.data.objects.get("prop:pCube1") is not None)
    for ww in list(bpy.context.window_manager.windows)[1:]:
        with bpy.context.temp_override(window=ww):
            bpy.ops.wm.window_close()
    if C["proj0"]:
        proj().set_current(C["proj0"])
    else:
        proj()._prefs().project_root = ""


# --- [M70-2] Shift+S hold + LMB = Keys (W) / Tangents (E) marking menu: Graph Editor = selected keys, 3D View and
#             timeline = the selection's keys at the current frame (the Time Slider range when there is one); Shift+S
#             tap does nothing; Stepped Next = Stepped + a notice ------------------------------------------------------

MM_D = 110      # px past the marking menu ring (Maya radius 55 x UI scale since step 151)
VEC = {"N": (0, 1), "E": (1, 0), "S": (0, -1), "W": (-1, 0), "SW": (-0.7071, -0.7071)}


def mm2(name, d1, d2, centre):
    """Register Shift+S held + LMB drag towards ``d1`` (opens the submenu in place) then ``d2``, release."""
    pts = {}

    @named(f"{name}_key")
    def _key():
        pts["c"] = Vector(centre())
        move_to(pts["c"])
        ev('S', 'PRESS', shift=True, x=int(pts["c"].x), y=int(pts["c"].y))

    @named(f"{name}_lmb")
    def _lmb():
        c = pts["c"]
        ev('LEFTMOUSE', 'PRESS', x=int(c.x), y=int(c.y), shift=True)

    @named(f"{name}_drag1")
    def _drag1():
        c, d = pts["c"], MM_D * bpy.context.preferences.system.ui_scale
        v = VEC[d1]
        # only the last sample is past the ring: a radial submenu opens centred where the pointer first passes it
        for f in (0.2, 0.4, 1.0):
            ev('MOUSEMOVE', 'NOTHING', x=int(c.x + v[0] * d * f), y=int(c.y + v[1] * d * f), shift=True)
        pts["sub"] = Vector((c.x + v[0] * d, c.y + v[1] * d))

    @named(f"{name}_drag2")
    def _drag2():
        s = mod("marking.draw").ACTIVE.get("session")
        pts["opened"] = s is not None and len(s.stack) == 2
        c, v = pts["sub"], VEC[d2]
        for f in (50, 100):
            ev('MOUSEMOVE', 'NOTHING', x=int(c.x + v[0] * f), y=int(c.y + v[1] * f), shift=True)
        pts["end"] = Vector((c.x + v[0] * 100, c.y + v[1] * 100))

    @named(f"{name}_release")
    def _release():
        e = pts["end"]
        ev('LEFTMOUSE', 'RELEASE', x=int(e.x), y=int(e.y), shift=True)

    @named(f"{name}_key_up")
    def _key_up():
        ev('S', 'RELEASE', shift=True)
        C[f"{name}_opened"] = pts.get("opened")


def xkeys():
    ob = bpy.data.objects[C["obname"]]
    fc = next(fc for fc in mod("operators.time_keys").node_fcurves(ob) if fc.data_path == "location" and fc.array_index == 0)
    return {int(round(kp.co.x)): kp for kp in fc.keyframe_points}


def kinds():
    return {f: kp.interpolation if kp.interpolation != 'BEZIER' else kp.handle_left_type for f, kp in xkeys().items()}


def v3d_centre():
    _a, r = view3d()
    return r.x + r.width * 0.4, r.y + r.height * 0.5


def timeline_area():
    return next(a for a in win().screen.areas if a.ui_type == 'TIMELINE')


def timeline_centre():
    a = timeline_area()
    r = next(r for r in a.regions if r.type == 'WINDOW')
    return r.x + r.width * 0.5, r.y + r.height * 0.5


def graph_centre():
    a, r = view3d_graph()
    return r.x + r.width * 0.45, r.y + r.height * 0.5


def view3d_graph():
    a = C["garea70"]
    return a, next(r for r in a.regions if r.type == 'WINDOW')


@named("m70_2_setup")
def _m70_2_setup():
    object_mode()
    clear()
    ob = create('CUBE')
    C["obname"] = ob.name
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 48
    for f, x in ((1, 0.0), (10, 3.0), (20, 0.0)):
        ob.location.x = x * k()
        ob.keyframe_insert("location", index=0, frame=f)
    select_only(ob)
    bpy.context.window_manager.allset_time_range_on = False
    sc.frame_set(10)
    C["k0"] = kinds()
    hover()


mm2("m70_2_v3d", "E", "S", v3d_centre)     # Tangents > Linear


@named("m70_2_v3d_check")
def _m70_2_v3d_check():
    got = kinds()
    check(f"[M70-2] 3D View Shift+S + LMB > Tangents > Linear: the current frame's key only ({C['k0']} -> {got}; "
          f"submenu opened {C['m70_2_v3d_opened']})",
          C["m70_2_v3d_opened"] and got[10] == 'LINEAR' and got[1] == C["k0"][1] and got[20] == C["k0"][20])
    wm = bpy.context.window_manager
    wm.allset_time_range = (1, 10)
    wm.allset_time_range_on = True


mm2("m70_2_range", "E", "E", v3d_centre)   # Tangents > Flat on the Shift range


@named("m70_2_range_check")
def _m70_2_range_check():
    got = kinds()
    flat = [f for f, kp in xkeys().items() if kp.interpolation == 'BEZIER' and kp.handle_left_type == 'ALIGNED'
            and abs(kp.handle_right.y - kp.co.y) < 1e-4]
    check(f"[M70-2] with a Time Slider range 1-10: Flat on the keys in it ({got}, flat {flat})", flat == [1, 10])
    bpy.context.window_manager.allset_time_range_on = False
    C["k1"] = kinds()


mm2("m70_2_timeline", "E", "N", timeline_centre)   # Tangents > Spline in the timeline


@named("m70_2_timeline_check")
def _m70_2_timeline_check():
    got = kinds()
    check(f"[M70-2] timeline Shift+S + LMB > Tangents > Spline: the current frame's key ({C['k1']} -> {got})",
          got[10] == 'AUTO' and got[1] == C["k1"][1] and got[20] == C["k1"][20])


mm2("m70_2_keys", "W", "N", v3d_centre)   # Keys > Delete Keys


@named("m70_2_keys_check")
def _m70_2_keys_check():
    got = sorted(xkeys())
    check(f"[M70-2] Keys (W) > Delete Keys: the current frame's key goes ({got})", got == [1, 20])
    C["k2"] = kinds()
    hover()
    ev('S', 'PRESS', shift=True)


@named("m70_2_tap")
def _m70_2_tap():
    ev('S', 'RELEASE', shift=True)


@named("m70_2_tap_check")
def _m70_2_tap_check():
    s = mod("marking.draw").ACTIVE.get("session")
    check(f"[M70-2] a Shift+S tap does nothing (keys {kinds()}, menu {s is not None}, modals "
          f"{[op.bl_idname for op in win().modal_operators]})", kinds() == C["k2"] and s is None)
    esc_modals()
    # Graph Editor: the selected keys only
    ob = bpy.data.objects[C["obname"]]
    ob.location.x = 2 * k()
    ob.keyframe_insert("location", index=0, frame=30)
    bpy.context.scene.frame_set(1)
    a, _r = view3d()
    C["garea70"] = a
    a.ui_type = 'FCURVES'


@named("m70_2_graph_select")
def _m70_2_graph_select():
    a, r = view3d_graph()
    with bpy.context.temp_override(window=win(), area=a, region=r):
        bpy.ops.graph.select_all(action='DESELECT')
    for f, kp in xkeys().items():
        kp.select_control_point = f == 20
    C["k3"] = kinds()
    move_to(Vector(graph_centre()))


mm2("m70_2_graph", "E", "SW", graph_centre)   # Tangents > Stepped Next


@named("m70_2_graph_check")
def _m70_2_graph_check():
    got = kinds()
    check(f"[M70-2] Graph Editor > Tangents > Stepped Next: the selected key only, as Stepped ({C['k3']} -> {got}); "
          f"the current frame's key (1) untouched", got[20] == 'CONSTANT' and got[1] == C["k3"][1] and got[30] == C["k3"][30])
    note = "Stepped Next isn't available in Blender: Stepped used"
    import inspect
    src = inspect.getsource(mod("operators.graph_keys").ALLSET_OT_set_tangent.execute)
    check("[M70-2] Stepped Next reports that Blender has none (INFO report)", note in src)
    C["garea70"].ui_type = 'VIEW_3D'
    hover()


# --- [M79-1] UV > 3D Cut and Sew UV Tool (menu / shelf / UV Toolkit / UV marking menu NW) = edit mode + edge mode +
#             the tool; shell borders drawn as thick white lines ------------------------------------------------------
# --- [M79-2] hover = red edge, drag along edges = yellow stroke, release cuts only those edges (not the side edge at a
#             corner); Ctrl+drag sews, Shift+drag selects ---------------------------------------------------------------

def cs():
    return mod("operators.cut_sew")


def cs_shells():
    b = bmesh.from_edit_mesh(OB().data)
    return len(mod("operators.uv_tools").islands(b, b.loops.layers.uv.verify()))


def cs_seams():
    b = bmesh.from_edit_mesh(OB().data)
    return sorted(e.index for e in b.edges if e.seam)


def cs_reset(from_object=True):
    if from_object:
        object_mode()
        clear()
        ob = create('CUBE')
        C["obname"] = ob.name
        select_only(ob)
        # frame it (Maya F): the strokes need edges long enough on screen for 4 px samples with 6 px corner
        # margins, and the view beside the solid dock (step 112) draws the cube smaller than the old overlapped one
        with override():
            bpy.ops.allset.frame()
    else:
        object_mode()
        select_only(OB())
    set_tool("builtin.move")


def cs_state():
    return (bpy.context.mode, tuple(ts().mesh_select_mode), tool_id())


CS_ON = ('EDIT_MESH', (False, True, False), "allset.cut_sew_tool")


def top_path():
    """Window points: three per top edge, going round the top face (closing at the first edge)."""
    b = bmesh.from_edit_mesh(OB().data)
    top = max(b.faces, key=lambda f: f.calc_center_median().z)
    mw = OB().matrix_world
    verts = [mw @ v.co for v in top.verts]
    pts = []
    for i in range(len(verts) + 1):
        a, c = verts[i % len(verts)], verts[(i + 1) % len(verts)]
        for t in (0.3, 0.5, 0.7):
            pts.append(screen(a + (c - a) * t))
    C["top_edges"] = sorted(e.index for e in top.edges)
    return pts


def cs_stroke(name, **mods):
    """Press, one move per path point (separate ticks), release."""
    @named(f"{name}_press")
    def _press():
        C["path"] = top_path()
        move_to(C["path"][0])
        ev('LEFTMOUSE', 'PRESS', x=int(C["path"][0].x), y=int(C["path"][0].y), **mods)

    for i in range(1, 15):
        @named(f"{name}_move{i}")
        def _move(i=i):
            if i < len(C["path"]):
                p = C["path"][i]
                ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y), **mods)
            if i == 6:
                C[f"{name}_mid"] = {k: set(v) for k, v in cs()._stroke["edges"].items()}

    @named(f"{name}_release")
    def _release():
        p = C["path"][-1]
        ev('LEFTMOUSE', 'RELEASE', x=int(p.x), y=int(p.y), **mods)


@named("m79_1_menu")
def _m79_1_menu():
    cs_reset()
    menu("UV/3D Cut and Sew UV Tool")
    check(f"[M79-1] UV > 3D Cut and Sew UV Tool: edit mode, edge mode, the tool ({cs_state()})", cs_state() == CS_ON)
    cs_reset(False)
    shelf = next(s for s, _l, buttons in mod("ui.shelf_data").SHELVES
                 if any(lab == "3D Cut and Sew UV Tool" for lab, _c in buttons))
    i = next(i for i, lab, _a, _ic in mod("ui.shelf").factory_buttons(shelf) if lab == "3D Cut and Sew UV Tool")
    with override():
        bpy.ops.allset.shelf_button(shelf=shelf, index=i)
    check(f"[M79-1] the {shelf} shelf button does the same ({cs_state()})", cs_state() == CS_ON)
    # the UV Toolkit button and the UV marking menus' NW item run the same operator
    rec = OpRecorder()
    panel = mod("ui.uv_toolkit").ALLSET_PT_uv_toolkit
    fake = type("P", (), {**{n: f for n, f in vars(panel).items() if callable(f) and not n.startswith("__")},
                          "layout": rec})()
    with override():
        panel.draw(fake, bpy.context) \
            if hasattr(mod("ui.uv_toolkit"), "ALLSET_PT_uv_toolkit") else None
    tk = [x[0] for kind, t, x in rec.out if kind == "op" and t == "3D Cut and Sew Tool"]
    mm = mod("marking.menus")
    nw = [m.radial["NW"][1] for m in (mm.SHIFT_UV, mm.SHIFT_UV_SHELL)] if hasattr(mm, "SHIFT_UV") else \
        [m.radial["NW"][1] for m in mm.MENUS.values() if m.radial.get("NW", (None,))[0] == "3D Cut and Sew UV Tool"]
    check(f"[M79-1] UV Toolkit button ({tk}) and UV marking menu NW ({nw}) = allset.cut_sew_tool_set",
          tk == ["allset.cut_sew_tool_set"] and len(nw) == 2 and set(nw) == {"allset.cut_sew_tool_set"})
    cs_reset(False)
    with override():
        bpy.ops.allset.cut_sew_tool_set()
    redraw_all()


@named("m79_1_borders")
def _m79_1_borders():
    b = bmesh.from_edit_mesh(OB().data)
    uv = b.loops.layers.uv.verify()
    n = len(list(cs().border_edges(b, uv)))
    lines = cs()._border_lines(OB())
    check(f"[M79-1] the shell borders are drawn: {len(lines) // 2} lines for {n} border edges, white "
          f"{cs().BORDER_RGB}, {cs().BORDER_PX} px", n > 0 and len(lines) == 2 * n
          and min(cs().BORDER_RGB) > 0.9 and cs().BORDER_PX >= 2)
    with override():
        bpy.ops.mesh.select_all(action='DESELECT')
    C["shells0"] = cs_shells()
    # hover the middle of a top edge
    p = top_path()[1]
    move_to(p)
    redraw_all()


@named("m79_2_hover")
def _m79_2_hover():
    gz = mod("operators.preselect").gizmo()
    tgt = gz.target if gz is not None else None
    check(f"[M79-2] hovering an edge highlights it red ({tgt}, {mod('operators.preselect').RGB})",
          tgt is not None and tgt[1] == 'EDGE' and tgt[2] in C["top_edges"] and mod("operators.preselect").RGB == (1.0, 0.0, 0.0))


cs_stroke("m79_2_cut")


@named("m79_2_cut_check")
def _m79_2_cut_check():
    mid = sum(len(v) for v in C["m79_2_cut_mid"].values())
    check(f"[M79-2] during the drag the stroke collects the edges passed (yellow {cs().STROKE_RGB}: {mid} edges halfway)",
          mid >= 2 and cs().STROKE_RGB[0] > 0.9 and cs().STROKE_RGB[2] < 0.3)
    check(f"[M79-2] release: only the 4 top edges are cut, not the side edges at the corners ({cs_seams()} vs "
          f"{C['top_edges']}), shells {C['shells0']} -> {cs_shells()}",
          cs_seams() == C["top_edges"] and cs_shells() > C["shells0"])


cs_stroke("m79_2_sew", ctrl=True)


@named("m79_2_sew_check")
def _m79_2_sew_check():
    check(f"[M79-2] Ctrl+drag sews the small shell back (shells {cs_shells()}, seams {cs_seams()})",
          cs_shells() == C["shells0"] and not cs_seams())


cs_stroke("m79_2_select", shift=True)


@named("m79_2_select_check")
def _m79_2_select_check():
    b = bmesh.from_edit_mesh(OB().data)
    sel = sorted(e.index for e in b.edges if e.select)
    check(f"[M79-2] Shift+drag only selects the edges ({sel}, shells {cs_shells()})",
          sel == C["top_edges"] and cs_shells() == C["shells0"])
    set_tool("builtin.move")
    object_mode()


# --- [M60-2] Ctrl+Alt+Shift+M switches from any editor; Blender mode Edit menu (F3 search) "Switch to Maya Mode", -----
#             Maya mode Windows > Switch to Blender
# --- [M60-3] the open file (objects, animation, path) stays; back in Blender the user's workspace returns and the Maya
#             one is gone, also from the saved file
# --- [M60-4] user keymap edit / theme / another add-on / rotation method set before Maya -> all back after Blender;
#             a setting changed during Maya mode that Maya doesn't touch stays
# (the switch runs from a timer: each step waits for it)

def sw():
    return mod("switch")


def area_centre(ui_types):
    for a in win().screen.areas:
        if a.ui_type in ui_types:
            r = next(r for r in a.regions if r.type == 'WINDOW')
            return a.ui_type, (r.x + r.width // 2, r.y + r.height // 2)
    return None, None


def switch_key(ui_types):
    kind, (x, y) = area_centre(ui_types)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('M', 'PRESS', x=x, y=y, ctrl=True, alt=True, shift=True)
    ev('M', 'RELEASE', x=x, y=y, ctrl=True, alt=True, shift=True)
    return kind


def file_state():
    obs = sorted((o.name, tuple(round(v, 5) for v in o.location), o.type) for o in bpy.data.objects)
    keys = sorted((fc.data_path, fc.array_index, len(fc.keyframe_points))
                  for o in bpy.data.objects for fc in mod("operators.time_keys").node_fcurves(o))
    return obs, keys, bpy.data.filepath


def user_km_item():
    km = bpy.context.window_manager.keyconfigs.user.keymaps["3D View"]
    return next(i for i in km.keymap_items if i.idname == "view3d.view_selected")


ADDON = "node_wrangler"   # a core add-on off by default in 4.5 and 5.x (copy_global_transform became built-in in 5.0)


@named("m60_new")
def _m60_new():
    object_mode()
    bpy.ops.wm.read_homefile(app_template="")      # a plain Blender file (Layout workspace)


@named("m60_setup")
def _m60_setup():
    bpy.ops.allset.keymap_activate()
    cube = bpy.data.objects.get("Cube")
    cube.location = (1.5, 0.25, 0.0)
    cube.keyframe_insert("location", frame=1)
    cube.location.x = 3.0
    cube.keyframe_insert("location", frame=10)
    path = os.path.join(tempfile.mkdtemp(prefix="allset_sweep_switch_"), "switch.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    C["file"] = file_state()
    C["ws"] = win().workspace.name
    check(f"[M60-2] start: Maya mode in a Blender file ({sw().is_on()}, workspace {C['ws']})", sw().is_on())
    C["from"] = switch_key({'OUTLINER'})


@named("m60_blender")
def _m60_blender():
    if wait(_m60_blender, lambda: not sw().is_on(), limit=12):
        return
    kcs = bpy.context.window_manager.keyconfigs
    check(f"[M60-2] Ctrl+Alt+Shift+M over the {C['from']} -> Blender mode (keymap {kcs.active.name})",
          not sw().is_on() and kcs.active.name == "Blender")
    check(f"[M60-3] the file is untouched, same workspace ({win().workspace.name})",
          file_state() == C["file"] and win().workspace.name == C["ws"])
    rec = OpRecorder()
    sw().draw_edit_menu(type("M", (), {"layout": rec})(), bpy.context)
    item = [(t, x[1]) for kind, t, x in rec.out if kind == "op"]
    check(f"[M60-2] Blender mode: Edit menu (found by F3 menu search) has {item}",
          item == [("Switch to Maya Mode", {"mode": 'MAYA'})])
    # [M60-4] the user's own settings in Blender mode
    p = bpy.context.preferences
    import addon_utils
    C["user0"] = (p.inputs.view_rotate_method, tuple(p.themes[0].view_3d.space.gradients.high_gradient),
                  user_km_item().active, addon_utils.check(ADDON)[1])
    p.inputs.view_rotate_method = 'TRACKBALL'
    p.themes[0].view_3d.space.gradients.high_gradient = (0.1, 0.5, 0.2)
    user_km_item().active = False
    addon_utils.enable(ADDON, default_set=True)
    C["user"] = ('TRACKBALL', (0.1, 0.5, 0.2), False, True)
    C["from"] = switch_key({'TIMELINE', 'DOPESHEET'})


def user_state():
    import addon_utils
    p = bpy.context.preferences
    return (p.inputs.view_rotate_method,
            tuple(round(c, 3) for c in p.themes[0].view_3d.space.gradients.high_gradient),
            user_km_item().active, addon_utils.check(ADDON)[1])


@named("m60_maya")
def _m60_maya():
    if wait(_m60_maya, lambda: sw().is_on(), limit=12):
        return
    kcs = bpy.context.window_manager.keyconfigs
    ws = win().workspace
    check(f"[M60-2] Ctrl+Alt+Shift+M over the {C['from']} -> Maya mode (keymap {kcs.active.name})",
          sys.modules["sim"].maya_keys())
    check(f"[M60-3] Maya mode: the Maya layout workspace ({ws.name}); the file untouched",
          ws.name == sw().WORKSPACE and file_state() == C["file"])
    C["tips0"] = bpy.context.preferences.view.show_tooltips_python
    bpy.context.preferences.view.show_tooltips_python = not C["tips0"]   # Maya doesn't touch it
    hover()
    menu("Windows/Switch to Blender")


@named("m60_back")
def _m60_back():
    # the Maya workspace goes once the window has left it (a timer, step 118)
    if wait(_m60_back, lambda: not sw().is_on() and sw().WORKSPACE not in bpy.data.workspaces, limit=20):
        return
    names = [w.name for w in bpy.data.workspaces]
    check(f"[M60-2] Windows > Switch to Blender -> Blender mode ({sw().is_on()})", not sw().is_on())
    check(f"[M60-3] back: the user's workspace again, the Maya one removed ({win().workspace.name}, {names}); "
          f"objects, keys and file path the same", win().workspace.name == C["ws"] and sw().WORKSPACE not in names
          and file_state() == C["file"])
    got = user_state()
    check(f"[M60-4] rotation method, theme colour, keymap edit, other add-on as the user left them ({got})",
          got[0] == C["user"][0] and all(abs(a - b) < 0.01 for a, b in zip(got[1], C["user"][1]))
          and got[2:] == C["user"][2:])
    tips = bpy.context.preferences.view.show_tooltips_python
    check(f"[M60-4] a setting changed during Maya mode that Maya doesn't touch stays ({tips})", tips != C["tips0"])
    bpy.ops.wm.save_mainfile()
    import shutil
    copy = bpy.data.filepath[:-6] + "_copy.blend"
    shutil.copy(bpy.data.filepath, copy)
    with bpy.data.libraries.load(copy) as (src, _dst):
        saved = list(src.workspaces)
    check(f"[M60-3] the saved file has no Maya workspace ({saved})", sw().WORKSPACE not in saved)
    # put the user's settings back
    import addon_utils
    p = bpy.context.preferences
    p.inputs.view_rotate_method = C["user0"][0]
    p.themes[0].view_3d.space.gradients.high_gradient = C["user0"][1]
    user_km_item().active = C["user0"][2]
    if not C["user0"][3]:
        addon_utils.disable(ADDON, default_set=True)
    p.view.show_tooltips_python = C["tips0"]


# --- development filter: ALLSET_SWEEP_ONLY="m59_,m72_" runs the setup steps + steps with those name prefixes ----

_ONLY = [x for x in os.environ.get("ALLSET_SWEEP_ONLY", "").split(",") if x]
if _ONLY:
    import sim as _sim
    _sim._steps[:] = [f for f in _sim._steps if f.__name__.startswith(("s_",) + tuple(_ONLY))]


run(interval=0.5)
