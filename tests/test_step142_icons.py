"""#54: kit-drawn icons for the Maya menu items that have no shelf button (ui/menu_drawings*.py, linked by
tools/gen_menu_icons.py into ui/menu_icon_data.py).

Checks: every drawing is linked and every linked drawing exists; the priority menus (Deform, Mesh Display, Effects,
Fields, Edit Mesh, Mesh Tools, Mesh) have an icon on every item Maya shows with one; drawings render at every
menu / shelf size; two different pictures in one menu look different (the shelf rule); the 2x picture is
the 1x drawing; the totals don't fall back.
"""

import collections
import itertools
from importlib import import_module

import numpy as np

import kit

data = import_module(kit.MODULE + ".ui.menu_icon_data")
mi = import_module(kit.MODULE + ".ui.menu_icons")
md = import_module(kit.MODULE + ".ui.menu_drawings")
ms = import_module(kit.MODULE + ".ui.menu_sets")

# Maya menu items that Maya shows with an icon and had none in the kit after the first menu icon pass,
# in the menus #54 asks for first. Labels only (no Maya icons in the repository).
PRIORITY = """
Deform/Display Intermediate Objects|Deform/Edit Membership Tool|Deform/Hide Intermediate Objects|Deform/Jiggle/Jiggle Deformer
Deform/Jiggle/Jiggle Disk Cache|Deform/Jiggle/Jiggle Disk Cache Attributes|Deform/Mirror Deformer Weights|Deform/Nonlinear/Bend
Deform/Nonlinear/Flare|Deform/Nonlinear/Sine|Deform/Nonlinear/Squash|Deform/Nonlinear/Twist|Deform/Nonlinear/Wave
Deform/Paint Weights/Blend Shape|Deform/Paint Weights/Cluster|Deform/Paint Weights/Jiggle|Deform/Paint Membership
Deform/Paint Weights/ShrinkWrap|Deform/Paint Weights/Texture Deformer|Deform/Paint Weights/Wire|Deform/Point On Curve
Deform/Pose Space Deformation/Create Pose Interpolator|Deform/Prune Membership/Cluster|Deform/Prune Membership/Lattice
Deform/Prune Membership/Sculpt|Deform/Prune Membership/Wire|Deform/Sculpt|Deform/ShrinkWrap|Deform/Soft Modification Tool
Deform/Texture|Deform/Wire|Deform/Wrap|Deform/Wrinkle
Edit Mesh/Add Divisions|Edit Mesh/Assign Invisible Faces|Edit Mesh/Average Vertices|Edit Mesh/Chamfer Vertices
Edit Mesh/Connect|Edit Mesh/Delete Edge/Vertex|Edit Mesh/Detach|Edit Mesh/Edit Edge Flow|Edit Mesh/Flip|Edit Mesh/Poke
Edit Mesh/Project Curve on Mesh|Edit Mesh/Reorder Vertices|Edit Mesh/Spin Edge Backward|Edit Mesh/Spin Edge Forward
Edit Mesh/Split Mesh with Projected Curve|Edit Mesh/Symmetrize|Edit Mesh/Transform|Edit Mesh/Wedge
Effects/Fire|Effects/Fireworks|Effects/Flow/Create Curve Flow|Effects/Flow/Create Surface Flow
Effects/Flow/Delete Selected Flow|Effects/Get Effects Asset...|Effects/Lightning|Effects/Shatter|Effects/Smoke
Fields/Solvers/Air|Fields/Solvers/Assign to Selected|Fields/Solvers/Create Active Rigid Body
Fields/Solvers/Create Barrier Constraint|Fields/Solvers/Create Hinge Constraint|Fields/Solvers/Create Nail Constraint
Fields/Solvers/Create Passive Rigid Body|Fields/Solvers/Create Pin Constraint|Fields/Solvers/Create Spring Constraint
Fields/Solvers/Drag|Fields/Solvers/Gravity|Fields/Solvers/Newton|Fields/Solvers/Radial|Fields/Solvers/Turbulence
Fields/Solvers/Uniform|Fields/Solvers/Use Selected as Source|Fields/Solvers/Volume Axis|Fields/Solvers/Volume Curve
Fields/Solvers/Vortex
Mesh Display/Apply Color|Mesh Display/Assign Existing Set|Mesh Display/Assign New Set|Mesh Display/Average
Mesh Display/Color Material Channel/Ambient|Mesh Display/Color Material Channel/Ambient+Diffuse
Mesh Display/Color Material Channel/Diffuse|Mesh Display/Color Material Channel/Emission
Mesh Display/Color Material Channel/None|Mesh Display/Color Material Channel/Specular|Mesh Display/Color Set Editor
Mesh Display/Conform|Mesh Display/Create Empty Set|Mesh Display/Delete Current Set|Mesh Display/Edit Assigned Set
Mesh Display/Harden Edge|Mesh Display/Lock Normals|Mesh Display/Material Blend Setting/Add
Mesh Display/Material Blend Setting/Average|Mesh Display/Material Blend Setting/Divide
Mesh Display/Material Blend Setting/Modulate 2x|Mesh Display/Material Blend Setting/Multiply
Mesh Display/Material Blend Setting/Overwrite|Mesh Display/Material Blend Setting/Subtract
Mesh Display/Modify Current Set|Mesh Display/Paint Vertex Color Tool
Mesh Display/Per Instance Sharing/Select Shared Instances|Mesh Display/Per Instance Sharing/Share Instances
Mesh Display/Prelight (Maya)|Mesh Display/Rename Current Set...|Mesh Display/Reverse
Mesh Display/Set Keyframe for Vertex Color|Mesh Display/Set Vertex Normal|Mesh Display/Set to Face
Mesh Display/Soften Edge|Mesh Display/Soften/Harden Edges|Mesh Display/Toggle Display Colors Attribute
Mesh Display/Unlock Normals|Mesh Display/Vertex Normal Edit Tool
Mesh Tools/Append to Polygon|Mesh Tools/Connect|Mesh Tools/Crease Tool|Mesh Tools/Create Polygon
Mesh Tools/Insert Edge Loop|Mesh Tools/Make Hole|Mesh Tools/Offset Edge Loop|Mesh Tools/Paint Reduce Weights
Mesh Tools/Paint Transfer Attributes|Mesh Tools/Slide Edge
Mesh/Booleans/Difference (A - B)|Mesh/Booleans/Intersection|Mesh/Booleans/Union|Mesh/Cleanup...
Mesh/Clipboard Actions/Clear Clipboard|Mesh/Clipboard Actions/Copy Attributes|Mesh/Clipboard Actions/Paste Attributes
Mesh/Fill Hole|Mesh/Quadrangulate|Mesh/Separate|Mesh/Smooth Proxy/Both Proxy and Subdiv Display
Mesh/Smooth Proxy/Crease Tool|Mesh/Smooth Proxy/Remove Subdiv Proxy Mirror|Mesh/Smooth Proxy/Subdiv Proxy
Mesh/Smooth Proxy/Toggle Proxy Display|Mesh/Transfer Attributes|Mesh/Transfer Shading Sets|Mesh/Transfer Vertex Order
Mesh/Triangulate
"""
PRIORITY_PATHS = [p for line in PRIORITY.strip().splitlines() for p in line.split("|")]

STEP131_ICONS = 202         # menu items showing a shelf / Status Line picture (Maya 2026 shelves)
MAYA_ICON_ITEMS = 898       # kit menu items Maya 2026 shows with an icon
MIN_ICONS = 675             # this step: 675 of 679 (the 4 left have no exported Maya picture to follow)

# Same uniqueness rule as tests/test_step131_icons.py (shelf / Status Line): enough pixels differ clearly.
MIN_DIFF = 0.04
PIXEL_DIFF = 0.25


def _premul(px):
    px = np.asarray(px, np.float32)
    return np.concatenate([px[..., :3] * px[..., 3:4], px[..., 3:4]], axis=-1)


def _diff_share(a, b):
    return float((np.abs(_premul(a) - _premul(b)).max(axis=-1) > PIXEL_DIFF).mean())


def _menu_pics():
    return {p: pic for p, pic in data.ICONS.items() if pic[0] == "menu"}


def test_priority_menus_complete():
    missing = [p for p in PRIORITY_PATHS if p not in data.ICONS]
    assert len(PRIORITY_PATHS) == 147, len(PRIORITY_PATHS)
    assert not missing, f"{len(missing)} priority items without an icon: {missing}"


def test_drawings_and_table_agree():
    pics = _menu_pics()
    for path, pic in pics.items():
        assert pic[1] in md.DRAWINGS, (path, pic)
    for path, name in md.PATHS.items():
        assert data.ICONS.get(path) == ("menu", name), (path, name, data.ICONS.get(path))
    unused = set(md.DRAWINGS) - {pic[1] for pic in pics.values()}
    assert not unused, f"drawings no menu item uses (rerun tools/gen_menu_icons.py): {sorted(unused)}"
    kit_paths = {p for p, _it in ms.iter_items()}
    stray = sorted(set(md.PATHS) - kit_paths)
    assert not stray, stray


def test_counts():
    n = len(data.ICONS)
    drawn = len(_menu_pics())
    print(f"menu items with an icon: {n} of {MAYA_ICON_ITEMS} Maya icon items ({STEP131_ICONS}); "
          f"menu drawings: {len(md.DRAWINGS)} pictures on {drawn} items")
    assert n >= MIN_ICONS, n
    assert n <= MAYA_ICON_ITEMS, n
    assert n - drawn == STEP131_ICONS, (n, drawn)        # the earlier links are untouched


def test_sizes():
    for name in md.DRAWINGS:
        for n in (16, 20, 24, 32, 64):
            px = md.draw(name, n)
            assert px.shape == (n, n, 4) and px.dtype == np.float32, (name, n, px.shape)
            assert 0.0 <= px.min() and px.max() <= 1.0, (name, n)
            alpha = px[..., 3]
            assert alpha.max() > 0.9 and (alpha > 0.5).sum() >= n * n // 10, (name, n, "nearly empty")
        assert mi.picture(("menu", name), 16).shape == (16, 16, 4)


def test_2x_is_the_1x_drawing():
    for name in md.DRAWINGS:
        a = md.draw(name, 32)
        b = md.draw(name, 64).reshape(32, 2, 32, 2, 4).mean(axis=(1, 3))
        assert _diff_share(a, b) < MIN_DIFF, name


def test_distinct_within_each_menu():
    """Two different pictures in one menu differ clearly (32 px, the shelf rule); one picture on two items only
    where the generator linked them (Maya shows the same icon file, or the same drawing on purpose)."""
    by_menu = collections.defaultdict(dict)
    for path, pic in data.ICONS.items():
        by_menu[path.rsplit("/", 1)[0]].setdefault(pic, path)
    cache = {}

    def px(pic):
        if pic not in cache:
            cache[pic] = mi.picture(pic, 32)
        return cache[pic]

    bad = []
    for menu, pics in by_menu.items():
        if not any(p[0] == "menu" for p in pics):
            continue
        for a, b in itertools.combinations(pics, 2):
            if _diff_share(px(a), px(b)) < MIN_DIFF:
                bad.append((pics[a], pics[b]))
    assert not bad, f"{len(bad)} menu icon pairs look alike: {bad}"


def test_drawings_distinct_overall():
    """No two menu drawings are the same picture (a drawing on several items is registered once)."""
    names = sorted(md.DRAWINGS)
    imgs = np.stack([_premul(md.draw(n, 32)).ravel() for n in names])
    bad = []
    for i in range(len(names) - 1):
        d = np.abs(imgs[i + 1:] - imgs[i]).reshape(len(names) - i - 1, -1, 4).max(axis=-1)
        share = (d > PIXEL_DIFF).mean(axis=1)
        bad += [(names[i], names[i + 1 + j]) for j in np.nonzero(share < MIN_DIFF)[0]]
    assert not bad, f"{len(bad)} drawings look alike: {bad}"
