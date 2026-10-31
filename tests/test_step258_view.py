"""Issue #155: F frames Maya-style (viewFit, fit factor 0.95), the Status Line snap
toggles stay out of the undo queue, the Symmetry control opens Maya's drop-down.

Expected: unit polyCube, persp camera (35 mm, film 36 x 24:
hfov 54.4322, vfov 37.8493), viewFit -> camera 3.23226 from the cube centre (fitFactor 1.0: 3.11360, 0.9: 3.36412),
camera direction (1.94505, 1.45879, 1.94505), Maya axes."""

import math
from importlib import import_module

import bpy
from mathutils import Matrix, Vector

import kit

framing = import_module(kit.MODULE + ".operators.framing")


def _view():
    d = Vector((1.94505, -1.94505, 1.45879))           # Maya (x, y, z) -> Blender (x, -z, y)
    rot = (-d).to_track_quat('-Z', 'Y')
    tw, th = math.tan(math.radians(54.4322 / 2)), math.tan(math.radians(37.8493 / 2))
    win = Matrix.Identity(4)
    win[0][0], win[1][1] = 1.0 / tw, 1.0 / th
    win[2][2], win[2][3], win[3][2], win[3][3] = -1.0, -0.2, -1.0, 0.0
    size = (1000.0, 1000.0 * th / tw)
    return rot, win, size


def test_frame_sidebar_rect_keeps_margin():
    """A narrower visible rect (sidebar open): the box stays inside it with Maya's margin."""
    rot, win, size = _view()
    pts = [Vector((x, y, z)) for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)]
    rect = (0, 0, size[0] * 0.6, size[1])
    loc, dist = framing.fit(pts, rot, win, 10.0, False, size, rect)
    persp = win @ framing.view_matrix(loc, rot, dist)
    b = framing._bounds(persp, framing.box_corners(pts), size)
    assert b[0] > rect[0] and b[2] < rect[2] and b[1] > 0 and b[3] < size[1], b
    c = framing.project(persp, Vector((0.0, 0.0, 0.0)), size)      # Maya aims at the box centre
    assert abs(c.x - rect[2] / 2) < 0.5 and abs(c.y - size[1] / 2) < 0.5, (c, rect)


# --- Status Line ------------------------------------------------------------------------------------

status_line = import_module(kit.MODULE + ".ui.status_line")


class _Fake:
    def __init__(self, log):
        object.__setattr__(self, "log", log)

    def __getattr__(self, name):
        if name in ("row", "column"):
            return lambda *a, **k: _Fake(self.log)

        def add(*a, **kw):
            self.log.append((name, a, kw.get("text")))
            return type("P", (), {})()
        return add

    def __setattr__(self, name, value):
        pass


def test_symmetry_box_is_a_drop_down():
    """Maya's "Symmetry: Off" box opens the list on a click (Maya Status Line); it was a text field."""
    log = []
    status_line.draw_status_line(_Fake(log), bpy.context)
    props = [e for e in log if e[0] == "prop" and len(e[1]) > 1 and e[1][1] == "allset_symmetry_text"]
    assert not props, props
    menus = [e for e in log if e[0] == "menu" and e[1] and e[1][0] == status_line.ALLSET_MT_symmetry.bl_idname]
    assert any(m[2] == "Symmetry: Off" for m in menus), menus


def test_snap_toggle_is_no_undo_step_and_survives_undo():
    """Maya's snap toggles are not undoable (they push no undo step): Ctrl+Z after
    move -> toggle undoes the move and keeps the toggle."""
    assert 'UNDO' not in status_line.ALLSET_OT_snap_toggle.bl_options
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    ob = bpy.data.objects.new("pCube1", None)
    bpy.context.scene.collection.objects.link(ob)
    ts = bpy.context.scene.tool_settings
    ts.use_snap = False
    bpy.ops.ed.undo_push(message="start")
    ob.location.x = 3.0
    bpy.ops.ed.undo_push(message="Move")
    assert bpy.ops.allset.snap_toggle(snap='GRID') == {'FINISHED'}
    assert ts.use_snap and 'GRID' in set(ts.snap_elements)
    bpy.ops.ed.undo()
    status_line.restore_snap()                    # the 0 s timer the undo handlers start
    ts = bpy.context.scene.tool_settings
    assert bpy.data.objects["pCube1"].location.x == 0.0, "the move is undone"
    assert ts.use_snap and 'GRID' in set(ts.snap_elements), "the snap toggle stays like Maya's"
    bpy.ops.ed.redo()
    status_line.restore_snap()
    ts = bpy.context.scene.tool_settings
    assert bpy.data.objects["pCube1"].location.x == 3.0 and ts.use_snap


# --- redo panel / late layout fit ---------------------------------------------------------------------

toolbox = import_module(kit.MODULE + ".ui.toolbox")


def test_maya_layout_views_have_no_redo_panel():
    """Maya has no redo panel (QA 240 H1-9: Blender's "Move" panel after a manipulator drag): the Maya layout's 3D
    Views start with the HUD region off; the kit's "redo" option boxes open F9's popup instead
    (marking/modal._call -> screen.redo_last), which needs no HUD region."""
    from pathlib import Path
    path = Path(kit.__file__).resolve().parent.parent / "src" / "allset" / "app_template" / "Maya_Workflow_Kit" /         "startup.blend"
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=True)
    views = [a.spaces.active for ws in bpy.data.workspaces for sc in ws.screens for a in sc.areas
             if a.type == 'VIEW_3D']
    assert views and not any(sp.show_region_hud for sp in views), [ws.name for ws in bpy.data.workspaces]
    modal = import_module(kit.MODULE + ".marking.modal")
    import inspect
    assert "screen.redo_last('INVOKE_DEFAULT')" in inspect.getsource(modal._call)


def test_layout_fit_only_right_after_load():
    """A fit left pending (no cursor warp) must not run minutes later at the next area split (QA 240 H2-3)."""
    screen = bpy.data.screens[0]
    scale = bpy.context.preferences.system.ui_scale
    toolbox._state.pop(screen.name, None)
    assert toolbox._armed(screen, scale)
    toolbox._state[screen.name][3] -= toolbox.FIT_WINDOW + 1.0      # the screen was armed long ago
    assert not toolbox._armed(screen, scale)
    assert not toolbox._armed(screen, scale), "stays off"
    toolbox._state.pop(screen.name, None)
