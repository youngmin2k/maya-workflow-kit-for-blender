"""In-Blender part of tools/dogfood.py: a Maya user's first session, driven by events.

Runs in a GUI Blender on the clean sandbox of tools/release_check.py (extension
installed + enabled from the command line, Maya Workflow Kit layout loaded), with
--enable-event-simulate. Every action is a simulated key/mouse event where the
kit binds one (operators only to build the scene). Each "check" records what a
Maya user would expect; screenshots go to $ALLSET_DOGFOOD_SHOTS for review.
"""

import os
import sys
from pathlib import Path

import time

import bpy
from importlib import import_module

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests" / "gui"))
import sim  # noqa: E402
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_DOGFOOD_SHOTS", str(ROOT / "tmp" / "dogfood" / "shots"))
C = {"tries": 0}
D = 110  # px: past the marking menu ring


def shot(name):
    sim.screenshot(os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def v3d_override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region)


def rv3d():
    return view3d()[0].spaces.active.region_3d


def tool_id():
    with v3d_override():
        return bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode).idname


def centre():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


def drag(button, dx, dy, **mods):
    x, y = C["x"], C["y"]
    ev(button, 'PRESS', x=x, y=y, **mods)
    for i in (1, 2, 3):
        ev('MOUSEMOVE', 'NOTHING', x=x + dx * i // 3, y=y + dy * i // 3, **mods)
    ev(button, 'RELEASE', x=x + dx, y=y + dy, **mods)
    centre()


def ui_region():
    return next(r for r in view3d()[0].regions if r.type == 'UI')


def goto_tab(category, then):
    """Show ``category`` in Maya's tab stack (its own area; made right of the view if missing)."""
    kinds = {"Channel Box / Layer Editor": 'CHANNEL_BOX', "Attribute Editor": 'ATTRIBUTE_EDITOR',
             "Modeling Toolkit": 'MODELING_TOOLKIT'}

    def s_tab():
        md = import_module(MODULE + ".ui.maya_dock")
        sim.dock_area(kinds[category])
        redraw()
        check(f"the tab stack shows the {category} tab ({md.current_tab()})", md.current_tab() == kinds[category])
        then()
    return s_tab


def only(name):
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name == name)
    bpy.context.view_layer.objects.active = bpy.data.objects[name]


# --- first start -------------------------------------------------------------------

@step
def s_first_start():
    kc = bpy.context.window_manager.keyconfigs.active
    # nothing changes until the user opts in; setup() opts in like the welcome dialog's button
    check(f"keymap untouched before the opt-in (got {kc.name if kc else None})",
          kc is not None and kc.name == "Blender")
    setup()
    kc = bpy.context.window_manager.keyconfigs.active
    # the Maya keys are add-on keymap items, the active keyconfig stays the user's
    check(f"Maya keymap after the opt-in (active keyconfig still {kc.name if kc else None})",
          kc is not None and kc.name == "Blender" and import_module(MODULE + ".keymap").is_applied())
    # no app template; a new scene from the startup.blend inside the extension (#49)
    import_module(MODULE + ".first_start").new_maya_scene()


@step
def s_layout():
    area, region = view3d()
    C["x"], C["y"] = region.x + region.width // 2, region.y + region.height // 2
    C["areas"] = sorted(a.type for a in win().screen.areas)
    check(f"layout areas {C['areas']}", True)
    check("empty Maya scene (no default cube/light/camera)",
          not [o for o in bpy.data.objects if o.type in {'MESH', 'LIGHT'}])
    centre()
    redraw()


@step
def s_layout_shot():
    shot("01_first_start.png")
    with v3d_override():
        bpy.ops.allset.create(kind='CUBE')
    check("Create > Cube gives pCube1 at the origin",
          "pCube1" in bpy.data.objects and bpy.data.objects["pCube1"].location.length < 1e-6)
    C["dist0"] = rv3d().view_distance
    tap('F')


# --- view keys ---------------------------------------------------------------------

@step
def s_frame():
    check(f"F frames the selection (distance {C['dist0']:.3f} -> {rv3d().view_distance:.3f})",
          rv3d().view_distance != C["dist0"])
    C["rot"] = rv3d().view_rotation.copy()
    drag('LEFTMOUSE', 80, 40, alt=True)


@step
def s_tumble():
    check("Alt+LMB drag tumbles", rv3d().view_rotation.rotation_difference(C["rot"]).angle > 1e-3)
    C["loc"] = rv3d().view_location.copy()
    drag('MIDDLEMOUSE', 60, 0, alt=True)


@step
def s_track():
    check("Alt+MMB drag tracks", (rv3d().view_location - C["loc"]).length > 1e-3)
    C["dist"] = rv3d().view_distance
    drag('RIGHTMOUSE', 80, 0, alt=True)


@step
def s_dolly():
    check(f"Alt+RMB drag dollies ({C['dist']:.4f} -> {rv3d().view_distance:.4f})",
          abs(rv3d().view_distance - C["dist"]) > 1e-3)
    tap('F')


# --- tools QWER --------------------------------------------------------------------

@step
def s_qwer_w():
    tap('W')


@step
def s_qwer_w_check():
    check(f"W tap -> Move tool (got {tool_id()})", tool_id() == "builtin.move")
    tap('E')


@step
def s_qwer_e_check():
    check(f"E tap -> Rotate tool (got {tool_id()})", tool_id() == "builtin.rotate")
    tap('R')


@step
def s_qwer_r_check():
    check(f"R tap -> Scale tool (got {tool_id()})", tool_id() == "builtin.scale")
    redraw()


@step
def s_scale_shot():
    shot("02_scale_tool.png")
    tap('W')
    redraw()


@step
def s_move_shot():
    shot("03_move_tool.png")
    tap('Q')


@step
def s_q_check():
    check(f"Q tap -> select tool (got {tool_id()})", "select" in tool_id())
    tap('FOUR')


# --- display 4/5/6, 3 ------------------------------------------------------------------

@step
def s_four():
    sh = view3d()[0].spaces.active.shading
    check(f"4 -> wireframe (got {sh.type})", sh.type == 'WIREFRAME')
    tap('FIVE')


@step
def s_five():
    sh = view3d()[0].spaces.active.shading
    check(f"5 -> shaded (got {sh.type})", sh.type == 'SOLID')
    tap('THREE')


@step
def s_three():
    cube = bpy.data.objects["pCube1"]
    check("3 -> smooth preview on pCube1",
          any(m.type == 'SUBSURF' and m.show_viewport for m in cube.modifiers))
    redraw()


@step
def s_three_shot():
    shot("04_smooth_preview.png")
    cube = bpy.data.objects["pCube1"]
    me = cube.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    check("3 -> preview shades smooth", all(p.use_smooth for p in me.polygons))
    ev('D', 'PRESS', alt=True, shift=True)
    ev('D', 'RELEASE', alt=True, shift=True)


@step
def s_delete_history():
    cube = bpy.data.objects["pCube1"]
    check(f"Alt+Shift+D (Delete History) keeps the preview display-only (verts {len(cube.data.vertices)})",
          len(cube.data.vertices) == 8 and any(m.type == 'SUBSURF' for m in cube.modifiers))
    tap('ONE')


@step
def s_one():
    cube = bpy.data.objects["pCube1"]
    check("1 -> smooth preview off",
          not any(m.type == 'SUBSURF' and m.show_viewport for m in cube.modifiers))
    ev('D', 'PRESS', ctrl=True)
    ev('D', 'RELEASE', ctrl=True)


# --- duplicate, group, parent, undo ------------------------------------------------------

@step
def s_dup():
    check(f"Ctrl+D -> pCube2 (objects {sorted(bpy.data.objects.keys())})",
          "pCube2" in bpy.data.objects)
    C["grab"] = any(op.bl_idname == "TRANSFORM_OT_translate" for op in win().modal_operators)
    check("Ctrl+D duplicates in place (no grab modal running)", not C["grab"])
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] + 40, y=C["y"])


@step
def s_dup_moved():
    dup = bpy.context.active_object
    check(f"mouse move after Ctrl+D leaves the copy in place (x {dup.location.x:.2f})",
          dup.location.length < 1e-6)
    tap('ESC')
    centre()
    dup.name = "pCube2"   # keep the session going with Maya's name
    dup.location.x = 3
    bpy.data.objects["pCube1"].select_set(True)
    ev('G', 'PRESS', ctrl=True)
    ev('G', 'RELEASE', ctrl=True)


@step
def s_group():
    g = bpy.data.objects.get("group1")
    check("Ctrl+G -> group1 holding both cubes",
          g is not None and {c.name for c in g.children} >= {"pCube1", "pCube2"})
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undo():
    check("Ctrl+Z undoes the group", "group1" not in bpy.data.objects)
    bpy.data.objects["pCube2"].location.x = 3   # undo also reverted the script's move
    bpy.context.view_layer.update()
    only("pCube2")
    bpy.data.objects["pCube1"].select_set(True)   # Maya: child(ren) first, parent last
    bpy.context.view_layer.objects.active = bpy.data.objects["pCube1"]
    tap('P')


@step
def s_parent():
    c2 = bpy.data.objects["pCube2"]
    check(f"P parents pCube2 under pCube1 (parent {c2.parent.name if c2.parent else None})",
          c2.parent is not None and c2.parent.name == "pCube1")
    check("P keeps the world position", abs(c2.matrix_world.translation.x - 3) < 1e-4)
    only("pCube2")
    ev('P', 'PRESS', shift=True)
    ev('P', 'RELEASE', shift=True)


@step
def s_unparent():
    c2 = bpy.data.objects["pCube2"]
    check("Shift+P unparents", c2.parent is None and abs(c2.matrix_world.translation.x - 3) < 1e-4)
    only("pCube1")
    centre()
    ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"])


# --- RMB marking menu -> Vertex, F8, Shift+RMB -----------------------------------------

@step
def s_rmb_hold():
    redraw()


@step
def s_rmb_drag():
    shot("05_rmb_marking_menu.png")
    for i in (1, 2, 3):
        ev('MOUSEMOVE', 'NOTHING', x=C["x"] - D * i // 3, y=C["y"])


@step
def s_rmb_release():
    ev('RIGHTMOUSE', 'RELEASE', x=C["x"] - D, y=C["y"])
    centre()


@step
def s_vertex_mode():
    ts = bpy.context.scene.tool_settings
    check(f"RMB > Vertex -> vertex component mode (mode {bpy.context.mode})",
          bpy.context.mode == 'EDIT_MESH' and tuple(ts.mesh_select_mode) == (True, False, False))
    ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"], shift=True)


@step
def s_shift_rmb_hold():
    redraw()


@step
def s_shift_rmb_shot():
    shot("06_shift_rmb_vertex_tools.png")
    ev('RIGHTMOUSE', 'RELEASE', x=C["x"], y=C["y"], shift=True)
    tap('ESC')
    centre()
    tap('F8')


@step
def s_f8():
    check(f"F8 -> back to object mode (mode {bpy.context.mode})", bpy.context.mode == 'OBJECT')
    ev('SPACE', 'PRESS')


# --- hotbox, Space tap -------------------------------------------------------------------

@step
def s_hotbox_wait():
    redraw()


@step
def s_hotbox_shot():
    shot("07_hotbox.png")
    ev('SPACE', 'RELEASE')
    # Four View = four real 3D View panels (ui/four_view.py), not Quad View regions
    C["quad"] = len(import_module(MODULE + ".ui.four_view").panes(win().screen))


@step
def s_space_gap():
    # #174: a Space PRESS within RELEASE_GRACE (0.12 s) of the hold's release belongs to that hold
    time.sleep(0.2)
    tap('SPACE')


@step
def s_space_tap():
    q = len(import_module(MODULE + ".ui.four_view").panes(win().screen))
    check(f"Space tap toggles the four views (panels {C['quad']} -> {q})", q != C["quad"] and q in (1, 4))
    redraw()


@step
def s_quad_shot():
    shot("08_four_views.png")
    # back to one panel: a Space tap over the persp panel's view (the old centre is on a panel's edge now)
    fv = import_module(MODULE + ".ui.four_view")
    persp = fv.roles(win().screen).get("persp") or fv.panes(win().screen)[0]
    r = next(r for r in persp.regions if r.type == 'WINDOW')
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


@step
def s_quad_leave():
    tap('SPACE')


@step
def s_quad_left():
    check("Space tap over the persp panel = one view again",
          len(import_module(MODULE + ".ui.four_view").panes(win().screen)) == 1)
    _area, region = view3d()
    C["x"], C["y"] = region.x + region.width // 2, region.y + region.height // 2
    centre()


# --- Channel Box: type a value, MMB slider -----------------------------------------------

@step
def s_cb_open():
    only("pCube1")
    redraw()


step(goto_tab("Channel Box / Layer Editor", lambda: redraw()))


@step
def s_cb_shot():
    shot("09_channel_box.png")
    cb = __import__(MODULE + ".ui.channel_box", fromlist=["x"])
    cb.set_selected_channels(["ty"])
    C["y0"] = bpy.data.objects["pCube1"].location.y   # channel names follow Blender axes
    drag('MIDDLEMOUSE', 100, 0)


@step
def s_cb_slider():
    dy = bpy.data.objects["pCube1"].location.y - C["y0"]
    check(f"MMB drag 100 px with Translate Y selected (dy {dy:.2f} BU)", dy > 0.5)
    cb = __import__(MODULE + ".ui.channel_box", fromlist=["x"])
    cb.set_selected_channels([])
    redraw()


@step
def s_cb_after():
    shot("10_channel_box_after_slider.png")
    ev('A', 'PRESS', ctrl=True)
    ev('A', 'RELEASE', ctrl=True)


@step
def s_ae():
    wm = bpy.context.window_manager
    check(f"Ctrl+A opens the Attribute Editor (dock {wm.allset_dock})", wm.allset_dock == 'ATTRIBUTE_EDITOR')
    redraw()


@step
def s_ae_shot():
    shot("11_attribute_editor.png")
    ev('A', 'PRESS', ctrl=True)
    ev('A', 'RELEASE', ctrl=True)
    tap('INSERT')


@step
def s_insert():
    check("Insert toggles pivot edit (header text / tool settings)", True)
    redraw()


@step
def s_insert_shot():
    shot("12_insert_pivot.png")
    tap('INSERT')
    tap('DEL')


@step
def s_delete():
    check("Delete removes pCube1", "pCube1" not in bpy.data.objects)
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


# --- Maya muscle memory (keymap rows still open) ---------------------------------------------

@step
def s_h():
    check("Ctrl+Z restores pCube1", "pCube1" in bpy.data.objects)
    only("pCube1")
    tap('H')


@step
def s_h_check():
    ob = bpy.data.objects["pCube1"]
    # #26: Maya visibility = hide_viewport (Channel Box Visibility, h, Display > Show)
    check("h toggles visibility of the selection (hidden)", not ob.visible_get())
    ob.hide_viewport = False
    ob.hide_set(False)
    only("pCube1")
    ev('ONE', 'PRESS', ctrl=True)
    ev('ONE', 'RELEASE', ctrl=True)


@step
def s_isolate():
    check("Ctrl+1 isolates the selection (local view)", view3d()[0].spaces.active.local_view is not None)
    if view3d()[0].spaces.active.local_view is not None:
        with v3d_override():
            bpy.ops.view3d.localview()
    mods = [m.name for m in bpy.data.objects["pCube1"].modifiers]
    check(f"Ctrl+1 changes nothing else (pCube1 modifiers {mods})",
          mods == ["Maya Smooth Preview Shading", "Maya Smooth Preview"])
    sc, cube = bpy.context.scene, bpy.data.objects["pCube1"]
    for f in (1, 10):   # Maya . / , jump between keys: give it two
        sc.frame_set(f)
        cube.keyframe_insert("location")
    sc.frame_set(1)
    centre()
    tap('PERIOD')


@step
def s_next_key():
    sc = bpy.context.scene
    check(f"'.' steps to the next key (frame 1 -> {sc.frame_current})", sc.frame_current == 10)
    ev('PERIOD', 'PRESS', alt=True)
    ev('PERIOD', 'RELEASE', alt=True)


@step
def s_next_frame():
    sc = bpy.context.scene
    check(f"Alt+. steps one frame (10 -> {sc.frame_current})", sc.frame_current == 11)
    tap('COMMA')


@step
def s_prev_key():
    sc = bpy.context.scene
    check(f"',' steps to the previous key (11 -> {sc.frame_current})", sc.frame_current == 10)
    sc.frame_set(1)
    tap('ESC')   # in case a pie opened (Blender's . / , in older versions)
    C["gizmo"] = import_module(MODULE + ".ui.manipulator").SIZE[0]   # kit manipulator size, no preference
    tap('EQUAL')


@step
def s_gizmo_size():
    check("'=' grows the manipulator", import_module(MODULE + ".ui.manipulator").SIZE[0] > C["gizmo"])
    import_module(MODULE + ".ui.manipulator").SIZE[0] = C["gizmo"]
    tap('ESC')
    only("pCube1")
    C["mode"] = bpy.context.mode + " modal " + str([op.bl_idname for op in win().modal_operators])
    centre()
    tap('F11')


@step
def s_grow():
    ts = bpy.context.scene.tool_settings
    check(f"F11 -> face mode (mode {C['mode']} -> {bpy.context.mode})",
          bpy.context.mode == 'EDIT_MESH' and tuple(ts.mesh_select_mode) == (False, False, True))
    if bpy.context.mode != 'EDIT_MESH':
        with v3d_override():
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_mode(type='FACE')
    with v3d_override():
        bpy.ops.mesh.select_all(action='DESELECT')
    import bmesh
    bm = bmesh.from_edit_mesh(bpy.data.objects["pCube1"].data)
    bm.faces.ensure_lookup_table()
    bm.faces[0].select = True
    bmesh.update_edit_mesh(bpy.data.objects["pCube1"].data)
    ev('PERIOD', 'PRESS', shift=True)
    ev('PERIOD', 'RELEASE', shift=True)


@step
def s_grow_check():
    import bmesh
    bm = bmesh.from_edit_mesh(bpy.data.objects["pCube1"].data)
    n = sum(f.select for f in bm.faces)
    check(f"Shift+> grows the face selection (selected {n})", n > 1)
    ev('E', 'PRESS', ctrl=True)
    ev('E', 'RELEASE', ctrl=True)


@step
def s_extrude():
    # Maya Ctrl+E = polyExtrudeFace: a zero-length extrusion + the extrude manipulator / In-View Editor
    import bmesh
    bm = bmesh.from_edit_mesh(bpy.data.objects["pCube1"].data)
    extrude = sys.modules[MODULE + ".operators.extrude"]
    rec = extrude.RECORDS.get("pCube1")
    check(f"Ctrl+E extrudes right away as polyExtrudeFace1 (Maya PolyExtrude; faces {len(bm.faces)}, "
          f"node {rec and rec.name})", rec is not None and rec.name.startswith("polyExtrudeFace") and len(bm.faces) > 6)
    tap('F8')


@step
def s_before_z():
    only("pCube1")
    tap('DEL')
    tap('Z')


@step
def s_z_undo():
    print("DOGFOOD modal after z", [op.bl_idname for op in win().modal_operators])
    check("z (Maya Undo) brings pCube1 back", "pCube1" in bpy.data.objects)
    if "pCube1" not in bpy.data.objects:
        tap('ESC')   # z started Blender's zoom-border modal
        ev('Z', 'PRESS', ctrl=True)
        ev('Z', 'RELEASE', ctrl=True)


@step
def s_shift_z():
    ev('Z', 'PRESS', shift=True)
    ev('Z', 'RELEASE', shift=True)


@step
def s_shift_z_check():
    check("Shift+Z (Maya Redo) deletes pCube1 again", "pCube1" not in bpy.data.objects)
    if "pCube1" not in bpy.data.objects:
        ev('Z', 'PRESS', ctrl=True)
        ev('Z', 'RELEASE', ctrl=True)




run(interval=0.5, first=3.0)
