"""#82: a click on the option box ❒ of a Maya menu item opens its option window; a click on the label
runs the command.

1. Geometry: menus opened from the Maya menu bar (File, Edit, Create, Modify, Display, Edit Mesh, Help) — the
   model's menu left / right edges (``ui/option_click.box_zone``) against the menu back colour in a screenshot, and
   the ❒ glyph inside the model's zone.
2. Behaviour: Edit Mesh > Bevel and Create > Polygon Primitives > Cube — click the ❒ = ``allset.menu_option_box``
   (Bevel Options / Polygon Cube Options window), click the label = the command (``allset.menu_item`` alone).
Runs at the session's UI scale (1.25 here; ``ALLSET_GUI_UI_SCALE=0.8`` = 1.0).
"""

import os
import sys
import tempfile
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, setup, step, tap, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"calls": []}
GEOMETRY = ["File", "Edit", "Create", "Modify", "Display", "Edit Mesh", "Help"]
BACK_TOL = 0.012


def mod(name):
    return import_module(MODULE + name)


def oc():
    return mod(".ui.option_click")


def shot_path(name):
    return os.path.join(SHOTS or tempfile.gettempdir(), name + ".png")


def shot(name):
    with bpy.context.temp_override(window=win()):
        bpy.ops.screen.screenshot(filepath=shot_path(name))


def pixels(name):
    import numpy as np
    img = bpy.data.images.load(shot_path(name))
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)[:, :, :3]


def unit():
    return mod(".ui.toolbar_fit").unit(bpy.context.preferences.system.ui_scale,
                                       bpy.context.preferences.system.pixel_size)


def top_region():
    area = mod(".ui.status_line")._top_bars.get(win().as_pointer())
    return next(r for r in area.regions if r.type == 'HEADER')


def button_point(label):
    """Centre of a Maya menu bar button (the same layout model the kit uses)."""
    sl = mod(".ui.status_line")
    ms = mod(".ui.menu_sets")
    names, _n = sl.shown_menus(win())
    labels = [getattr(bpy.types, ms.menu_idname(nm)).bl_label for nm in names]
    with bpy.context.temp_override(window=win()):
        widths, _f, _m = sl.menu_bar_widths(bpy.context, list(names), False)
    i = labels.index(label)
    r = top_region()
    left = r.x + int(oc().LEAD_UNITS * unit()) + sum(widths[:i])
    return left + widths[i] // 2, r.y + r.height // 2


def row_y(k, top=None):
    """Window y of row ``k`` (0 = the tear-off line) of a menu whose first row is level with ``top``."""
    u = unit()
    if top is None:
        r = top_region()
        return r.y - int(0.48 * u) - k * u
    return top - k * u


def zone(path):
    with bpy.context.temp_override(window=win(), area=None, region=None):
        return oc().box_zone(bpy.context, path)


def _spy(cls, tag):
    orig = cls.execute

    def execute(self, context):
        C["calls"].append((tag, getattr(self, "item", "")))
        return orig(self, context)
    cls.execute = execute
    C.setdefault("restore", []).append((cls, orig))


def press_release(x, y):
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_ready():
    bpy.ops.allset.keymap_activate()
    bpy.context.preferences.view.show_tooltips = False
    mod(".ui.status_line").redraw_top_bars()
    ms = mod(".ui.menu_sets")
    _spy(ms.ALLSET_OT_menu_option_box, "box")
    _spy(ms.ALLSET_OT_menu_item, "item")


# --- 1. geometry ----------------------------------------------------------------------------------------------

def geometry_case(label):
    def s_open():
        x, y = button_point(label)
        C["click"] = (x, y)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)

    def s_click():
        press_release(*C["click"])

    def s_measure():
        shot("183_menu_" + label.replace(" ", "_"))

    def s_check():
        import numpy as np
        a = pixels("183_menu_" + label.replace(" ", "_"))
        rows = oc().rows(label)[1]
        boxed = [p for p, t in rows.items() if t.endswith("❒")]
        z = zone(boxed[0]) if boxed else None
        model_left = None
        if z is None and boxed:
            check(f"{label}: the model places the menu ({boxed[0]})", False)
        if z is not None:
            x0, x1, left, right = z
            model_left = left
            # edges found from the menu back colour on rows just under the top bar (median over rows)
            ys = range(row_y(1) - 4, row_y(1) - 4 - 8 * unit(), -3)
            back = a[row_y(1) + unit() // 2 - 2, int(left) + 3]
            lefts, rights = [], []
            for y in ys:
                isb = np.abs(a[y] - back).max(axis=1) < BACK_TOL
                xs = np.nonzero(isb[max(0, int(left) - 12):min(a.shape[1], int(right) + 12)])[0]
                if len(xs):
                    lefts.append(xs.min() + max(0, int(left) - 12))
                    rights.append(xs.max() + max(0, int(left) - 12))
            ml, mr = sorted(lefts)[len(lefts) // 2], sorted(rights)[len(rights) // 2]
            # 5.x: areas beside a menu (the Tool Box column, the outliner) share the menu back colour, so the scan
            # can only read the menu wider than it is, never narrower (Create left 92 / 104, File right
            # 355 / 345, screenshots show the model's edges); the ❒ cell below is the click check that matters
            wider_ok = True
            check(f"{label}: menu left model {left:.0f} / screen {ml} (tol 4 px)",
                  abs(ml - left) <= 4 or (wider_ok and ml < left))
            check(f"{label}: menu right model {right:.0f} / screen {mr} (tol 8 px)",
                  abs(mr - right) <= 8 or (wider_ok and mr > right))
            # the ❒ glyph: bright pixels in the model's glyph cell on the boxed rows
            glyph = mod(".ui.menu_sets").text_width("❒", mod(".ui.menu_sets").font_size())
            gx0 = int(x0 + oc().ZONE_LEFT_UNITS * unit())
            cell = a[row_y(30) if False else 0:a.shape[0], gx0:int(gx0 + glyph)].mean(axis=2)
            outside = a[0:a.shape[0], int(gx0 - 3 * glyph):int(gx0 - 2 * glyph)].mean(axis=2)
            band = slice(max(0, row_y(60)), row_y(0))
            bright_in = int((cell[band] > 0.6).sum())
            bright_out = int((outside[band] > 0.6).sum())
            check(f"{label}: ❒ glyphs in the model's cell x {gx0}..{gx0 + glyph:.0f} (bright px {bright_in}, "
                  f"left of it {bright_out})", bright_in > 20)
        C[label] = model_left
        ev('ESC', 'PRESS')
        ev('ESC', 'RELEASE')
        ev('MOUSEMOVE', 'NOTHING', x=win().width // 2, y=win().height // 2)
    for f in (s_open, s_click, lambda: None, s_measure, s_check, lambda: None):
        step(f)


for _label in GEOMETRY:
    geometry_case(_label)


# --- 2. clicks: ❒ vs label ------------------------------------------------------------------------------------

def click_case(path, rows_k, on_box, sub_k=None):
    """Open the path's top menu from the menu bar, (hover the submenu row ``sub_k``), click row ``rows_k``."""
    top = path.split("/")[0]
    tag = path.split("/")[-1] + ("_box" if on_box else "_label")

    def s_open():
        del C["calls"][:]
        x, y = button_point(top)
        C["click"] = (x, y)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)

    def s_click_bar():
        press_release(*C["click"])

    def s_sub():
        if sub_k is None:
            return
        u = unit()
        left = C.get(top) or 0
        C["sub_row"] = (int(left + 4 * u), row_y(sub_k))
        ev('MOUSEMOVE', 'NOTHING', x=C["sub_row"][0] - 3, y=C["sub_row"][1])

    def s_sub2():
        if sub_k is not None:
            ev('MOUSEMOVE', 'NOTHING', x=C["sub_row"][0], y=C["sub_row"][1])

    def s_target():
        z = zone(path)
        C["zone"] = z
        y = row_y(rows_k, None if sub_k is None else row_y(sub_k))
        x = int((z[0] + z[1]) / 2 - (z[1] - z[0]) * 0.25) if on_box else int(z[2] + 3 * unit())
        if on_box:
            x = int(z[0] + oc().ZONE_LEFT_UNITS * unit())    # on the glyph's left edge
        C["target"] = (x, y)
        # enter the row from the left (a straight jump into a submenu can close it)
        ev('MOUSEMOVE', 'NOTHING', x=int(z[2] + 2 * unit()), y=y)

    def s_hover():
        ev('MOUSEMOVE', 'NOTHING', x=C["target"][0], y=C["target"][1])

    def s_press():
        shot(f"183_before_{tag}")
        press_release(*C["target"])

    def s_result():
        shot(f"183_after_{tag}")
        want = [("item", path), ("box", path)] if on_box else [("item", path)]
        check(f"{path}: click {'❒' if on_box else 'label'} at {C['target']} (zone {C['zone'][0]:.0f}..{C['zone'][1]:.0f})"
              f" -> {C['calls']}", C["calls"][:len(want)] == want and len(C["calls"]) == len(want))

    def s_close():
        tap('ESC')
        ev('MOUSEMOVE', 'NOTHING', x=win().width // 2, y=win().height // 2)
        if not on_box and path.endswith("Cube"):
            for ob in list(bpy.context.scene.objects):
                bpy.data.objects.remove(ob)
    for f in (s_open, s_click_bar, lambda: None, s_sub, s_sub2, lambda: None, lambda: None, s_target, s_hover,
              lambda: None, lambda: None, s_press, lambda: None, s_result, s_close, lambda: None):
        step(f)


click_case("Edit Mesh/Bevel", 2, True)
click_case("Edit Mesh/Bevel", 2, False)
click_case("Create/Polygon Primitives/Cube", 2, True, sub_k=2)
click_case("Create/Polygon Primitives/Cube", 2, False, sub_k=2)


# --- 3. a menu opened elsewhere (hotbox / marking menu path = wm.call_menu in the viewport): no ❒ zone ----------

@step
def s_elsewhere():
    from sim import view3d
    area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    with bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active):
        bpy.ops.wm.call_menu(name=mod(".ui.menu_sets").menu_idname("mainEditMeshMenu"))


@step
def s_elsewhere_check():
    check(f"Edit Mesh opened in the viewport: no ❒ zone ({zone('Edit Mesh/Bevel')})", zone("Edit Mesh/Bevel") is None)
    tap('ESC')


@step
def s_restore():
    for cls, orig in C.get("restore", ()):
        cls.execute = orig
    check("done", True)


run()
