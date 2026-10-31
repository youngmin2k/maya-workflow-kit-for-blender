"""Lane TOOLBOX (#23): kit-drawn Maya icons for the Tool Box tools and quick layouts, the Layer Editor
toolbar and the Outliner rows the kit draws (ui/kit_icons.py).
GUI: tests/gui/gui_step131_toolbox_icons.py."""

from importlib import import_module

import bpy
import numpy as np

import kit

ki = import_module(kit.MODULE + ".ui.kit_icons")
toolbox = import_module(kit.MODULE + ".ui.toolbox")

AREAS = ("tool:", "layout:", "layer:", "outliner:")


def _names(prefix):
    return [n for n in ki.GLYPHS if n.startswith(prefix)]


def test_inventory_covers_the_maya_items():
    assert set(_names("tool:")) == {f"tool:{t}" for t in toolbox.MAYA_TOOLS}, _names("tool:")
    assert set(_names("layout:")) == {"layout:SINGLE", "layout:FOUR", "layout:FRONT_PERSP", "layout:OUTLINER"}
    assert set(_names("layer:")) == {"layer:UP", "layer:DOWN", "layer:NEW_EMPTY", "layer:NEW_SELECTED"}
    assert set(_names("outliner:")) == {"outliner:SET", "outliner:CAMERA"}
    assert set(ki.MAYA) == set(ki.GLYPHS), "every glyph names its Maya command"


def test_sizes_follow_the_ui_scale():
    # Blender shows button icons at 16 px x UI scale and toolbar tool icons at 32 px x UI scale
    for scale, small, tool in ((1.0, 16, 32), (1.25, 20, 40), (1.5, 24, 48), (2.0, 32, 64)):
        assert ki.size_for("layer:UP", scale) == small
        assert ki.size_for("tool:builtin.move", scale) == tool
    for name in ki.GLYPHS:
        for scale in (1.0, 1.25, 1.5):
            n = ki.size_for(name, scale)
            px = ki.pixels(name, n)
            assert px.shape == (n, n, 4), (name, px.shape)
            assert np.isfinite(px).all() and px.min() >= 0 and px.max() <= 1.0001, name
            cover = float((px[..., 3] > 0.5).mean())
            assert cover > 0.08 and (cover < 0.98 or name.startswith("layout:")), (name, n, cover)


def test_pixel_hinting():
    """Rectangle edges land on whole pixels: the layout frames are fully opaque one-pixel lines, the pixel inside the
    frame (outside its rim) is not light grey."""
    for scale in (1.0, 1.25, 1.5):
        n = ki.size_for("layout:OUTLINER", scale)
        px = ki.pixels("layout:OUTLINER", n)
        edge = px[n // 2, 0]
        assert edge[3] > 0.99 and edge[0] > 0.7, (scale, edge)
        # the move tool's centre square: crisp, a fully opaque light pixel next to a fully dark-rim pixel
        n = ki.size_for("tool:builtin.move", scale)
        px = ki.pixels("tool:builtin.move", n)
        row = px[n // 2]
        light = [i for i in range(n) if row[i][3] > 0.99 and row[i][0] > 0.7]
        assert light, scale
        left = light[0]
        assert row[left - 1][0] < 0.3, (scale, row[left - 1])   # the rim / background, no half-tone edge


def test_distinct_within_each_area():
    """Neighbours must read differently: every pair of glyphs of one area differs clearly (alpha-weighted)."""
    for prefix in AREAS:
        names = _names(prefix)
        n = ki.size_for(names[0], 1.0)
        imgs = {k: ki.pixels(k, n) for k in names}
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                pa, pb = imgs[a], imgs[b]
                d = np.abs(pa[..., :3] * pa[..., 3:] - pb[..., :3] * pb[..., 3:]).max(axis=2)
                differing = int((d > 0.25).sum())
                assert differing >= 0.05 * n * n, (a, b, differing)


def test_maya_palette():
    """Maya icon colours: light grey line art with teal accents."""
    for name in ("tool:builtin.move", "tool:builtin.rotate", "layer:UP", "outliner:SET"):
        px = ki.pixels(name, ki.size_for(name, 1.0))
        solid = px[px[..., 3] > 0.99][:, :3]
        teal = np.abs(solid - np.array(ki.TEAL)).max(axis=1) < 0.03
        grey = np.abs(solid - np.array(ki.LIGHT)).max(axis=1) < 0.03
        assert teal.any() and grey.any(), name


def test_previews_and_toolbar_cache():
    from bl_ui import space_toolsystem_common as stc
    from bl_ui.space_toolsystem_toolbar import _defs_transform
    ctx = bpy.context
    for name in ki.GLYPHS:
        n = ki.size_for(name, ctx.preferences.system.ui_scale)
        ki.make(name, n)      # icon ids are 0 in -b; the preview itself exists
        pv = ki._collection()[ki._key(name, n)]
        assert tuple(pv.icon_size) == (n, n) and tuple(pv.image_size) == (n, n), (name, tuple(pv.icon_size))
        assert len(pv.icon_pixels_float) == n * n * 4
    move = _defs_transform.translate
    items = toolbox.kit_icons_on([move, None], ctx)
    assert items[1] is None
    assert items[0].idname == move.idname and items[0].icon.startswith("allset.tool:builtin.move@"), items[0].icon
    v = ki.geom_icon("tool:builtin.move", ctx)
    assert v > 0 and stc._icon_cache.get(items[0].icon) == v
    assert stc.ToolSelectPanelHelper._icon_value_from_icon_handle(items[0].icon) == v
    # every Maya tool has a vector icon; a tool without a kit glyph keeps Blender's icon
    for t in toolbox.MAYA_TOOLS:
        coords, cols = ki.triangles(f"tool:{t}")
        assert len(coords) % 6 == 0 and len(cols) == len(coords) * 2 and len(coords) >= 6 * 4, t
    # Blender desaturates toolbar vector icons by the theme's Icon Saturation: the kit colours are pre-compensated
    for sat in (0.5, 0.8):
        back = ki.compensate(ki.TEAL, sat)
        luma = 0.3 * back[0] + 0.59 * back[1] + 0.11 * back[2]
        shown = [sat * c + (1 - sat) * luma for c in back]
        assert max(abs(a - b) for a, b in zip(shown, ki.TEAL)) < 0.01, (sat, shown)
    assert max(abs(a - b) for a, b in zip(ki.compensate(ki.LIGHT, 0.5), ki.LIGHT)) < 1e-6   # grey stays grey
    other = toolbox.kit_icons_on([_defs_transform.transform], ctx)[0]
    assert other.icon == _defs_transform.transform.icon
    key = items[0].icon
    kit.disable()
    try:
        assert key not in stc._icon_cache, "disable must take the kit icons out of Blender's toolbar cache"
        assert not ki._pcoll, "disable must free the preview collection"
        assert not ki._geom_ids, "disable must release the vector icons"
    finally:
        kit.enable()


def test_vector_icons_free_cleanly():
    """Blender 4.5 crashes freeing a ``new_triangles`` icon (release or quit; every GUI test crashed on quit and ran
    into its timeout): the kit's vector icons are .dat files read by ``new_triangles_from_file``, which free cleanly
    — this test would kill the process before writing its result."""
    import os
    name = "tool:builtin.move"
    v = ki.geom_icon(name)
    sat = round(ki.icon_saturation(), 3)
    path = ki._dat_path(name, sat)
    assert v and os.path.isfile(path), (v, path)
    with open(path, "rb") as fh:
        head = fh.read(8)
    assert head == b"VCO\x00" + bytes((255, 255, 0, 0)), head
    bpy.app.icons.release(v)
    ki._geom_ids.pop((name, sat), None)
    v2 = ki.geom_icon(name)
    assert v2
