"""Hotbox and RMB marking menu as Maya 2022 shows them.
GUI: tests/gui/gui_step52_hotbox_rmb.py."""

from importlib import import_module

import math

import bpy

import kit

engine = import_module(kit.MODULE + ".marking.engine")
mm = import_module(kit.MODULE + ".marking.menus")
modal = import_module(kit.MODULE + ".marking.modal")
draw = import_module(kit.MODULE + ".marking.draw")

# Maya 2022 hotbox rows (top to bottom). MASH is a plug-in menu (no kit data).
MAYA_ABOVE = [["File", "Edit", "Create", "Select", "Modify", "Display", "Windows", "Cache", "Help"],
              ["View", "Shading", "Lighting", "Show", "Renderer", "Panels"]]
MAYA_SIDES = ["Recent Commands", "Hotbox Controls"]
MAYA_BELOW = [["Mesh", "Edit Mesh", "Mesh Tools", "Mesh Display", "Curves", "Surfaces", "Deform", "UV", "Generate"],
              ["Skeleton", "Skin", "Deform", "Constrain", "Control"],
              ["Key", "Playback", "Audio", "Visualize", "Deform", "Constrain", "MASH"],
              ["nParticles", "Fluids", "nCloth", "nHair", "nConstraint", "nCache", "Fields/Solvers", "Effects", "MASH"],
              ["Lighting/Shading", "Texturing", "Render", "Toon", "Stereo"]]
PLUGIN = {"MASH"}

# Maya 2026 RMB list over pCube1, "-" = divider.
MAYA_RMB = ["pCube1...", "-", "Select", "Select All", "Deselect All", "Select Hierarchy", "Invert Selection", "-",
            "Select Similar", "-", "Make Live", "-", "DG Traversal", "Inputs", "Outputs", "Paint", "Metadata",
            "Actions", "UV Sets", "Color Sets", "Time Editor", "-", "Scene Assembly"]
SUBMENUS = {"DG Traversal", "Inputs", "Outputs", "Paint", "Metadata", "Actions", "UV Sets", "Color Sets",
            "Time Editor", "Scene Assembly"}


def measure(text):
    return 7.0 * len(text)


def _labels(row):
    return [label for _key, label in row]


def test_hotbox_rows_are_maya_rows():
    above, sides, below = modal.hotbox_rows(bpy.context, area_type='VIEW_3D')
    assert [_labels(r) for r in above] == MAYA_ABOVE
    assert [label for _k, label in sides] == MAYA_SIDES
    assert [_labels(r) for r in below] == [[m for m in row if m not in PLUGIN] for row in MAYA_BELOW]
    # outside a 3D View there are no panel menus (Maya's pane-specific row)
    assert len(modal.hotbox_rows(bpy.context, area_type='OUTLINER')[0]) == 1


def test_hotbox_layout_like_maya():
    above, sides, below = modal.hotbox_rows(bpy.context, area_type='VIEW_3D')
    c = (800.0, 450.0)
    lay = engine.HotboxLayout(above, c, measure, below=below, side=sides, bounds=(0, 0, 1600, 900))
    assert lay.title == "Maya Workflow Kit" and abs((lay.center_rect[1] + lay.center_rect[3]) / 2 - c[1]) < 1e-6
    rows = {}
    for rect, _key, label in lay.labels:
        rows.setdefault(rect[1], []).append((rect[0], label))
    ys = sorted(rows, reverse=True)                      # top first
    order = [[label for _x, label in sorted(rows[y])] for y in ys]
    want = MAYA_ABOVE + [MAYA_SIDES] + [[m for m in row if m not in PLUGIN] for row in MAYA_BELOW]
    assert order == want, order
    pitch = [round(a - b, 3) for a, b in zip(ys, ys[1:])]
    assert set(pitch) == {35.0}, pitch                   # 26 px boxes, 9 px apart
    left, right = (r for r, k, _l in lay.labels if k in ("RECENT", "CONTROLS"))
    assert left[2] < lay.center_rect[0] and right[0] > lay.center_rect[2], "beside the centre box"
    assert len(lay.bands) == len(MAYA_ABOVE) + 2 + len(MAYA_BELOW)
    # four diagonal zone lines outside the rows
    assert len(lay.zone_lines) == 4
    top = max(r[3] for r, _k, _l in lay.labels)
    bottom = min(r[1] for r, _k, _l in lay.labels)
    for (x0, y0), (x1, y1) in lay.zone_lines:
        assert abs(abs(x0 - c[0]) - abs(y0 - c[1])) < 1e-6 and abs(abs(x1 - x0) - abs(y1 - y0)) < 1e-6
        assert min(y0, y1) > top or max(y0, y1) < bottom
    # zones still split on the diagonals
    assert lay.zone(c[0], c[1] + 300) == "N" and lay.zone(c[0] - 300, c[1]) == "W"


def test_hotbox_rows_near_edges_stay_inside():
    above, sides, below = modal.hotbox_rows(bpy.context, area_type='VIEW_3D')
    b = (0, 0, 1600, 900)
    for c in ((800.0, 860.0), (800.0, 40.0), (40.0, 450.0), (1560.0, 450.0)):
        lay = engine.HotboxLayout(above, c, measure, below=below, side=sides, bounds=b)
        rects = [r for r, k, _l in lay.labels if k not in ("RECENT", "CONTROLS")]
        assert all(b[0] - 1e-6 <= r[0] and r[2] <= b[2] + 1e-6 and b[1] - 1e-6 <= r[1] and r[3] <= b[3] + 1e-6
                   for r in rects), c
        assert not any(r[0] < lay.center_rect[2] and lay.center_rect[0] < r[2] and r[1] < lay.center_rect[3]
                       and lay.center_rect[1] < r[3] for r in rects), ("rows clear of the centre box", c)


def test_rmb_list_is_maya_2026():
    menu = mm.with_object_name(mm.RMB_MESH, "pCube1")
    got = ["-" if e == mm.DIVIDER else e[0] for e in menu.items][:len(MAYA_RMB)]
    assert got == MAYA_RMB, got
    tail = [e[0] for e in menu.items[len(MAYA_RMB):] if e != mm.DIVIDER]
    assert tail == ["Material Attributes...", "Assign New Material", "Assign Favorite Material",
                    "Assign Existing Material"], tail                   # Maya 2026 RMB list end
    actions = {e[0]: e[1] for e in menu.items if e != mm.DIVIDER}
    # a Sub or a Blender menu (UV Sets / Color Sets list the mesh's sets) — both show ▸
    assert all(isinstance(actions[n], mm.Sub) or actions[n][0] == "menu" for n in SUBMENUS), "submenus show ▸"
    assert not mm.is_unavailable(actions["Paint"]) and mm.is_unavailable(actions["Metadata"])
    assert modal.poll_action(actions["Metadata"]) is False
    assert isinstance(actions["Inputs"], mm.NodeList) and modal.poll_action(actions["Inputs"])
    assert actions["Make Live"] == ("allset.mm_object_item", {"item": "Modify/Make Live"})
    assert "Select Similar" in menu.options, "Maya option box"
    assert mm.RMB_MESH.items[0][0] == mm.OBJECT_TITLE, "the shared definition keeps the placeholder"
    assert [e[0] for e in mm.RMB_CURVE.items[:7] if e != mm.DIVIDER] == [mm.OBJECT_TITLE, "Select", "Select All",
                                                                         "Deselect All", "Select Hierarchy",
                                                                         "Invert Selection"]


def test_rmb_list_under_or_beside_the_ring():
    """Maya keeps the list in one column under the ring and draws the whole menu
    higher only at the *screen* bottom. Blender can't draw outside its (smaller) window, so the kit keeps the ring
    at the press point — the marks keep working — and moves only the list: under the ring when it fits, else beside
    it in one column (on the side with no radial submenu), else above / pushed inside. Never over the ring, always inside."""
    b = (0.0, 0.0, 1600.0, 900.0)
    for origin in ((800.0, 680.0), (800.0, 450.0), (300.0, 380.0), (1500.0, 420.0), (800.0, 120.0)):
        s = engine.Session(mm.RMB_MESH, origin, 0.0, measure, None, None, b)
        assert s.center == origin and s.press == origin and s.pos == origin, (origin, "the ring stays at the press")
        rows = [it for it in s.layout.items if it.kind == "list"]
        assert len({round(it.rect[0], 3) for it in rows}) == 1, (origin, "one column")
        boxes = list(s.layout.radial.values())
        assert not any(r.rect[0] < x.rect[2] and x.rect[0] < r.rect[2] and r.rect[1] < x.rect[3] and
                       x.rect[1] < r.rect[3] for r in rows for x in boxes), (origin, "list over the ring")
        cx, cy = s.center
        absr = [(it.rect[0] + cx, it.rect[1] + cy, it.rect[2] + cx, it.rect[3] + cy) for it in rows]
        assert all(b[0] - 1e-6 <= r[0] and r[2] <= b[2] + 1e-6 and b[1] - 1e-6 <= r[1] and r[3] <= b[3] + 1e-6
                   for r in absr), origin
        top = max(rows, key=lambda it: it.rect[3])
        assert top.label == mm.OBJECT_TITLE, "the column starts with the title"
        order = [it.label for it in sorted(rows, key=lambda it: -it.rect[3])]
        assert order == [it.label for it in rows], (origin, "Maya order top-down")
        ring_bottom = min(it.rect[1] for it in boxes)
        under = all(it.rect[3] <= ring_bottom for it in rows)
        if origin[1] == 680.0:
            assert under, "room under the ring: the list hangs under it"
        if origin[1] == 450.0:
            beside_w = max(it.rect[2] for it in rows) <= min(it.rect[0] for it in boxes)
            assert not under and beside_w, "no room under: beside the ring, on the W side (E = UV opens on the way)"
    # room for everything: one column centred under the ring
    s = engine.Session(mm.RMB_MESH, (800.0, 880.0), 0.0, measure, None, None, (0.0, -2000.0, 1600.0, 900.0))
    rows = [it for it in s.layout.items if it.kind == "list"]
    assert len({it.rect[0] for it in rows}) == 1 and abs(rows[0].rect[0] + rows[0].rect[2]) < 1e-6


def test_rmb_marks_work_where_the_list_does_not_fit():
    """RMB west on pCube1 in the middle of a 1600 x 900 window must pick its box: every radial
    mark from the press point picks its box, drawn or not, wherever the list goes."""
    b = (0.0, 0.0, 1600.0, 900.0)
    for origin in ((800.0, 450.0), (800.0, 120.0), (300.0, 380.0)):
        for key in ("N", "S", "W", "NW", "SW"):
            action = mm.RMB_MESH.radial.get(key, (None, None))[1]
            if action is None or isinstance(action, mm.Sub):     # greyed / submenu boxes run nothing on release
                continue
            ang = {"N": 90, "S": 270, "W": 180, "NW": 135, "SW": 225}[key]
            dx, dy = 110 * math.cos(math.radians(ang)), 110 * math.sin(math.radians(ang))
            for t in (0.06, 0.6):       # a quick mark (menu not drawn yet) and a slow drag over the drawn ring
                s = engine.Session(mm.RMB_MESH, origin, 0.0, measure, None, None, b)
                s.move(origin[0] + dx / 2, origin[1] + dy / 2, t / 2)
                res = s.release(origin[0] + dx, origin[1] + dy, t)
                want = s.layout.radial[key]
                assert res is not None and res[0] == "RUN" and res[1] is want, (origin, key, t, res)
    # a quick click opens the menu in click mode
    s = engine.Session(mm.RMB_MESH, (800.0, 120.0), 0.0, measure, None, None, b)
    assert s.release(800.0, 120.0, 0.1) is None and s.mode == "CLICK"


def test_window_bounds_and_cover_handlers():
    region = type("R", (), {"x": 300, "y": 100, "width": 800, "height": 600})()
    area = lambda x, y, w, h: type("A", (), {"x": x, "y": y, "width": w, "height": h})()  # noqa: E731
    screen = type("S", (), {"areas": [area(0, 30, 300, 840), area(300, 30, 1300, 840)]})()
    window = type("W", (), {"screen": screen})()
    assert draw.window_bounds(window, region) == (-300, -70, 1300, 770)
    spaces = {space for space, _r, _h in draw._handles}
    assert {bpy.types.SpaceView3D, bpy.types.SpaceOutliner, bpy.types.SpaceProperties} <= spaces
    assert {r for space, r, _h in draw._handles if space is bpy.types.SpaceView3D} >= {'WINDOW', 'UI', 'TOOLS',
                                                                                       'HEADER'}


def test_object_attributes_operator():
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.window_manager.allset_mm_target = ob.name
    try:
        assert bpy.ops.allset.object_attributes.poll()
    finally:
        bpy.context.window_manager.allset_mm_target = ""


def test_submenu_arrow_measured_without_the_glyph():
    """A UI font without "▸" (Segoe UI, Maya Font) made blf report millions of px: the RMB list spanned the
    view. The arrow is a drawn triangle of fixed width."""
    w = draw.measure("Inputs")
    assert abs(draw.measure("Inputs" + draw.ARROW) - (w + draw._arrow_w())) < 1e-6
    assert draw.measure("Assign Existing Material" + draw.ARROW) < 400
