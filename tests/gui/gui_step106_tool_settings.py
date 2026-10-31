"""In a real UI: the Maya Workflow Kit layout, pCube1 with its top face extruded, Move tool. Windows > General Editors >
Tool Settings (ToggleToolSettings) opens the dock left of the viewport with Maya's Move Settings, a second toggle
closes it (the old popup stayed open: audit 7 c03), a third opens it again; Rotate / Scale show their sections;
the Attribute Editor shows the history / material tabs, menu bar, buttons and Notes (screenshots beside audit-7
pairs c02 / c03)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name):
    if SHOTS:
        with bpy.context.temp_override(window=win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def in_v3d(fn, *a, **kw):
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return fn(*a, **kw)


def menu(path):
    return in_v3d(bpy.ops.allset.menu_item, item=path)


def dock():
    return mod(".ui.tool_dock").find(win().screen)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    in_v3d(bpy.ops.allset.create, kind='CUBE')
    ob = bpy.context.active_object
    C["ob"] = ob.name
    in_v3d(bpy.ops.object.mode_set, mode='EDIT')
    import bmesh
    bm = bmesh.from_edit_mesh(ob.data)
    for f in bm.faces:
        f.select_set(False)
    for f in bm.faces:   # deselect first: a later face's select_set(False) would drop shared verts
        if f.normal.z > 0.9:
            f.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    in_v3d(bpy.ops.allset.extrude, local_translate_z=0.5)
    in_v3d(bpy.ops.wm.tool_set_by_id, name="builtin.move")
    C["areas"] = len(win().screen.areas)
    C["main_w"] = v3d()[0].width
    menu("Windows/General Editors/Tool Settings")


@step
def s_opened():
    redraw()


@step
def s_opened_check():
    d = dock()
    check("toggle 1: the Tool Settings dock is open", d is not None)
    if d is None:
        return
    sp = d.spaces.active
    nav = next((r for r in d.regions if r.type == 'NAVIGATION_BAR'), None)
    main = v3d()[0]
    check(f"dock = Properties Tool tab, no header / tab column, left of the viewport ({d.x}+{d.width} <= {main.x})",
          sp.context == 'TOOL' and not sp.show_region_header and (nav is None or nav.width <= 1)
          and d.x + d.width <= main.x + 2 and d.height == main.height)
    check(f"dock width {d.width} px (280 x UI scale, <= 35 % of the viewport)",
          150 <= d.width <= 0.36 * C["main_w"] + 4)
    ts = mod(".ui.tool_settings")
    with bpy.context.temp_override(window=win(), area=d, region=next(r for r in d.regions if r.type == 'WINDOW'),
                                   space_data=sp):
        kind = ts.tool_kind(bpy.context)
        hidden = ts.hides_blender_panels(bpy.context)
    check(f"Move tool: Maya sections ({kind}), Blender's tool panels hidden in the dock", kind == 'TRANSLATE' and hidden)
    shot("gui_step106_ts_move.png")


@step
def s_toggle2():
    menu("Windows/General Editors/Tool Settings")


@step
def s_toggle2_check():
    redraw()
    check(f"toggle 2: the dock is closed, the layout is back ({len(win().screen.areas)} areas vs {C['areas']}, viewport "
          f"{v3d()[0].width} px vs {C['main_w']})",
          dock() is None and len(win().screen.areas) == C["areas"] and v3d()[0].width >= C["main_w"] - 4)
    # (wider is fine: the Tool Box column may have been fitted to one toolbar column meanwhile, toolbox.settle)
    in_v3d(bpy.ops.allset.editor_toggle, editor='TOOL_SETTINGS')     # the Status Line button


@step
def s_toggle3_check():
    redraw()
    check("toggle 3 (Status Line button): open again", dock() is not None)
    # an option box of a tool (toolPropertyWindow) only shows it
    in_v3d(bpy.ops.allset.editor_toggle, editor='TOOL_SETTINGS', show=True)
    check("show-only (tool option box) keeps it open", dock() is not None)
    in_v3d(bpy.ops.wm.tool_set_by_id, name="builtin.rotate")
    redraw()


@step
def s_rotate_shot():
    shot("gui_step106_ts_rotate.png")
    in_v3d(bpy.ops.wm.tool_set_by_id, name="builtin.select_box")
    redraw()


@step
def s_select_shot():
    shot("gui_step106_ts_select.png")
    check("Select tool: dock still open (Blender's tool panels under the head row)", dock() is not None)
    in_v3d(bpy.ops.wm.tool_set_by_id, name="builtin.move")
    in_v3d(bpy.ops.object.mode_set, mode='OBJECT')
    in_v3d(bpy.ops.wm.tool_set_by_id, name="builtin.move")
    redraw()


@step
def s_object_move_shot():
    shot("gui_step106_ts_move_object.png")      # pair with audit-7 c02 (object mode Move tool)
    in_v3d(bpy.ops.allset.editor_toggle, editor='TOOL_SETTINGS')
    in_v3d(bpy.ops.allset.dock_show, dock='ATTRIBUTE_EDITOR')
    ae = mod(".ui.attribute_editor")
    ae.set_tab(bpy.context, "S")
    redraw()


@step
def s_ae_wait():
    redraw()


@step
def s_ae_shot():
    check("dock closed before the AE shot", dock() is None)
    shot("gui_step106_ae.png")        # pair with audit-7 c03
    ob = bpy.data.objects[C["ob"]]
    ae = mod(".ui.attribute_editor")
    tabs = [t[1] for t in ae.tabs(ob)]
    check(f"AE tabs {tabs}: transform, shape, initialShadingGroup, lambert1",
          tabs[:2] == [ob.name, ob.data.name] and "initialShadingGroup" in tabs and "lambert1" in tabs)
    in_v3d(bpy.ops.object.mode_set, mode='EDIT')
    redraw()


@step
def s_ae_edit_wait():
    redraw()


@step
def s_ae_edit_shot():
    ob = bpy.data.objects[C["ob"]]
    ae = mod(".ui.attribute_editor")
    tabs = [t[1] for t in ae.tabs(ob)]
    check(f"edit mode: the kit extrusion is a polyExtrudeFace1 tab ({tabs})", "polyExtrudeFace1" in tabs)
    ae.set_tab(bpy.context, "H")
    redraw()


@step
def s_ae_history_shot():
    shot("gui_step106_ae_history.png")
    in_v3d(bpy.ops.object.mode_set, mode='OBJECT')
    in_v3d(bpy.ops.allset.dock_show, dock='CHANNEL_BOX')
    check("session ran", True)


run()
