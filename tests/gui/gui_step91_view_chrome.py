"""In a real UI (Maya Workflow Kit layout): no parent relationship lines in the template views, the RMB marking-menu
list draws over the Adjust Last Operation (HUD) panel, and the dock stays one panel when Ctrl+A shows the Attribute
Editor (the "Channel Box" sidebar tab no longer moves under "Item")."""

import os
import sys
import tempfile
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def key(type, **mods):
    names = {"alt": "LEFT_ALT", "ctrl": "LEFT_CTRL", "shift": "LEFT_SHIFT"}
    for m in mods:
        ev(names[m], 'PRESS')
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)
    for m in mods:
        ev(names[m], 'RELEASE')


def cube():
    return bpy.data.objects["pCube1"]


def hud():
    area, _r = view3d()
    return next((r for r in area.regions if r.type == 'HUD' and r.width > 1 and r.height > 1), None)


def shot_path(name):
    folder = SHOTS or tempfile.gettempdir()
    return os.path.join(folder, name)


def pixel(img, x, y):
    w = img.size[0]
    i = (y * w + x) * 4
    return tuple(round(c, 3) for c in img.pixels[i:i + 3])


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    lines = [sp.overlay.show_relationship_lines for scr in bpy.data.screens for a in scr.areas
             for sp in a.spaces if sp.type == 'VIEW_3D']
    check(f"template 3D views draw no relationship lines ({lines.count(True)} of {len(lines)} on)",
          lines and not any(lines))
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    # Put the cube low on the left of the view so its RMB list (under the ring) covers the HUD panel.
    target = (region.width * 0.30, region.height * 0.42)
    p = region_2d_to_location_3d(region, region.data, target, (0.0, 0.0, 0.0))
    p.z = 0.0
    cube().location = p
    for o in bpy.context.scene.objects:
        o.select_set(o.name == "pCube1")
    bpy.context.view_layer.objects.active = cube()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    C["place"] = p
    # the Maya layout views keep Blender's HUD region off (Maya has no redo panel); this test needs one to
    # check the marking menu draws over it (set under a window override: without one Blender crashes)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        area.spaces.active.show_region_hud = True
    # Alt+W (Blender's Clear Location, REGISTER + UNDO with a visible property) leaves its Adjust Last Operation panel
    # (the HUD). Kit display / visibility keys show none (#58, Maya has no redo panel; Shift+H
    # was used here before). The cube is put back where it was after the key: a Python edit doesn't close the HUD.
    key('W', alt=True)


@step
def s_hud():
    h = hud()
    check(f"the Adjust Last Operation panel is up ({h and (h.x, h.y, h.width, h.height)})", h is not None)
    _a, region = view3d()
    if h is not None:
        # with no room under the ring the list is one column left of it (RMB on a mesh: E = UV), its right
        # edge ~190 px left of the press point, ~215 px wide (it goes right when the left has no room); press ~300 px right of
        # the HUD so that column runs over the HUD panel
        # the ring stays at the press point; with no room under it the list goes beside it,
        # so press ~300 px right of the HUD and the column left of the ring runs over the HUD panel
        target = (h.x + h.width - region.x + 300, region.height * 0.42)
        p = region_2d_to_location_3d(region, region.data, target, (0.0, 0.0, 0.0))
        p.z = 0.0
        C["place"] = p
    cube().location = C["place"]
    bpy.context.view_layer.update()
    sp = location_3d_to_region_2d(region, region.data, cube().matrix_world.translation)
    C["press"] = (int(region.x + sp.x), int(region.y + sp.y))
    x, y = C["press"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y)


@step
def s_menu_wait():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_menu_shot():
    s = import_module(MODULE + ".marking.draw").ACTIVE.get("session")
    check("RMB hold on the cube shows the object marking menu", s is not None)
    C["session"] = s
    screenshot(shot_path("gui_step91_rmb_over_hud.png"))


@step
def s_menu_pixels():
    s, h = C.get("session"), hud()
    _a, region = view3d()
    points = []
    if s is not None and h is not None:
        cx, cy = s.center
        hx0, hy0, hx1, hy1 = h.x, h.y, h.x + h.width, h.y + h.height
        # The list body (one per column, the rows plus the gaps between them; rows step over area
        # borders, so the HUD may sit in such a gap) drawn over the HUD; sample free body pixels, not text.
        columns = {}
        for it in s.layout.items:
            if it.kind == "list":
                columns.setdefault(round(it.rect[0], 3), []).append(it)
        for rows in columns.values():
            x0, x1 = region.x + cx + rows[0].rect[0], region.x + cx + rows[0].rect[2]
            ox0, ox1 = max(x0, hx0), min(x1, hx1)
            if ox1 - ox0 <= 40:
                continue
            for yy in range(int(hy0) + 3, int(hy1) - 2, 3):
                ry = yy - region.y - cy
                body = min(r.rect[1] for r in rows) < ry < max(r.rect[3] for r in rows)
                # free body: inside a row above its text, or in a gap between rows (no divider line there)
                in_row = next((r for r in rows if r.rect[1] <= ry <= r.rect[3]), None)
                free = (in_row is not None and in_row is not s.hover[0]
                        and ry > in_row.rect[1] + (in_row.rect[3] - in_row.rect[1]) * 0.82) or in_row is None
                lines = [(a.rect[1] + b.rect[3]) / 2 for a, b in zip(rows, rows[1:]) if b.key - a.key > 1]
                if body and free and all(abs(ry - ly) > 2 for ly in lines):
                    points.append((int(ox0 + (ox1 - ox0) * 0.75), yy))
    check(f"the list body covers the HUD panel ({points[:4]})", bool(points))
    if points:
        bg = import_module(MODULE + ".marking.draw").BG[:3]
        img = bpy.data.images.load(shot_path("gui_step91_rmb_over_hud.png"))
        got = [pixel(img, x, y) for x, y in points]
        bpy.data.images.remove(img)
        check(f"inside the HUD panel the pixels are the list background {tuple(round(c, 3) for c in bg)} ({got})",
              all(all(abs(p - q) < 0.02 for p, q in zip(g, bg)) for g in got))
    x, y = C["press"]
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_esc():
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.group()
    p = cube().location.copy()
    cube().location = (p.x + 0.04, p.y, p.z + 0.02)     # away from group1's pivot at the origin
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    key('A')


@step
def s_group_shot():
    par = cube().parent
    check(f"pCube1 is under group1 ({par and par.name})", par is not None and par.name == "group1")
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_group_shot2():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step91_group_no_line.png"))
    _a, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    key('A', ctrl=True)           # Ctrl+A: the dock shows the Attribute Editor


@step
def s_ae():
    wm = bpy.context.window_manager
    check(f"Ctrl+A = Attribute Editor ({wm.allset_dock})", wm.allset_dock == 'ATTRIBUTE_EDITOR')
    # the AE is a tab of Maya's tab stack (its own area) or, with no stack in this layout, a floating window
    md = import_module(MODULE + ".ui.maya_dock")
    check(f"the Attribute Editor is shown ({md.current_tab()})", md.kind_visible(wm, 'ATTRIBUTE_EDITOR'))
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_ae_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step91_ae_tabs.png"))


run()
