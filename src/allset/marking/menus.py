# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya marking menus as plain data (step 8).

Positions and labels follow Maya's own marking menus. Re-implemented: only labels, radial
positions and the Blender action (same value forms as ``ui/menu_map.py``:
``"op.id"``, ``("op.id", {props})``, ``("v3d", ...)``, ``("tool", id, edit)``,
``("menu", id)``; ``None`` = greyed out). A radial ``Sub`` is a nested marking
menu, a list ``Sub`` a plain submenu.

Kept free of Blender UI so the step-9 marking-menu engine can draw the same
definitions.
"""

RADIALS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
DIVIDER = "-"


class Sub:
    """A submenu: ``radial`` {pos: (label, action)}, ``items`` [(label, action) | "-"].

    ``options``: labels whose Maya item has an option box ``[]``
    (Maya's option box items).
    """

    def __init__(self, radial=None, items=(), options=()):
        self.radial = dict(radial or {})
        self.items = list(items)
        self.options = frozenset(options)


class MarkingMenu(Sub):
    def __init__(self, name, label, source, radial=None, items=(), options=()):
        super().__init__(radial, items, options)
        self.name = name        # kit menu id
        self.label = label
        self.source = source    # where the Maya menu comes from (not read at run time)


def _mod(kind):
    return ("object.modifier_add", {"type": kind})


def _create(kind):
    # Maya name and size in Maya units (operators/create.py, step 21).
    return ("allset.create", {"kind": kind})


def _orient(kind, slot=0):
    # Not transform.select_orientation: invoked from a menu it opens its own enum popup (GUI test).
    # W/E/R menus set their own tool's slot (1 move, 2 rotate, 3 scale): Maya keeps one axis mode
    # per tool, Move = World and Rotate/Scale = Object by default (step 59).
    return ("wm.context_set_enum", {"data_path": f"scene.transform_orientation_slots[{slot}].type", "value": kind})


def _step(kind, mode='TOGGLE'):
    return ("allset.step_snap", {"kind": kind, "mode": mode})


def _comp(kind):
    return ("allset.mm_component", {"type": kind})


MULTI_CUT = ("tool", "allset.multi_cut_tool", True)     # step 129
MERGE_CENTER = ("mesh.merge", {"type": 'CENTER'})
TARGET_WELD = ("tool", "allset.target_weld_tool", True)   # step 64
CREASE = ("tool", "allset.crease_tool", True)
PRESERVE_UVS = ("wm.context_toggle", {"data_path": "scene.tool_settings.use_transform_correct_face_attributes"})
PRESERVE_CHILDREN = ("wm.context_toggle", {"data_path": "scene.tool_settings.use_transform_skip_children"})
TOOL_SETTINGS = ("allset.editor_toggle", {"editor": 'TOOL_SETTINGS'})
SMART_DUPLICATE = ("allset.manip_option", {"option": 'SMART_DUPLICATE'})  # step 22
SMART_EXTRUDE = ("allset.manip_option", {"option": 'SMART_EXTRUDE'})      # step 26


def _item(path):
    """Run Maya main-menu item ``path`` exactly like the menu (``allset.menu_item``: component / object mode rules,
    Maya warnings, option window as the option box); step 136."""
    return ("item", path)


def _on_object(path):
    """A main-menu item run on the object the RMB menu was opened on (Maya acts on the object under the pointer)."""
    return ("allset.mm_object_item", {"item": path})


def _overlay(prop):
    # Maya's Soft / Hard Edge and Normals display toggles = the 3D View's edit-mode overlays (check boxes, step 136).
    return ("wm.context_toggle", {"data_path": f"space_data.overlay.{prop}"})


SOFT_EDGE_DISPLAY = _overlay("show_edge_sharp")
# ArtPaintSelectTool: Maya paints a selection with a brush = Blender's circle select tool (edit mode).
PAINT_SELECT = ("tool", "builtin.select_circle", True)
CIRCULARIZE = _item("Edit Mesh/Circularize")


def _poly(kind):
    # Ctrl+RMB "convert, then act" items (CTRL_CONVERT) and Reverse Propagate: marking/rmb_items.py ALLSET_OT_mm_poly.
    return ("allset.mm_poly", {"kind": kind})


def _sym(mode):
    return ("allset.symmetry", {"mode": mode})


# Maya's Symmetry submenu, shown by the Move / Rotate / Scale
# option menus at N; every item is a check box (operators/symmetry.py, step 36).
SYMMETRY = ("Symmetry", Sub(radial={
    "N": ("Symmetry", _sym('ON')),
    "W": ("World", _sym('ABOUT_WORLD')),
    "E": ("Object", _sym('ABOUT_OBJECT')),
    "NE": ("Topology", _sym('TOPOLOGY')),
    "SW": ("X Axis", _sym('AXIS_X')),
    "S": ("Y Axis", _sym('AXIS_Y')),
    "SE": ("Z Axis", _sym('AXIS_Z')),
}))

# Material items at the end of the RMB object list (Maya builds them when the RMB marking menu opens,
# step 29). ``rmb``: with nothing selected
# they act on the object the menu was opened on, like Maya.
_FAVORITES = (("Lambert", 'LAMBERT'), ("Blinn", 'BLINN'), ("Phong", 'PHONG'),
              ("Standard Surface", 'STANDARD_SURFACE'))


def _material_items():
    """A fresh list per menu, so each menu gets its own submenu class."""
    favorites = [(label, ("allset.shelf_material", {"kind": kind, "rmb": True})) for label, kind in _FAVORITES]
    return [
        DIVIDER,
        ("Material Attributes...", ("allset.material_attributes", {"rmb": True})),
        DIVIDER,
        ("Assign New Material", Sub(items=[("New Material...", ("allset.assign_new_material", {"rmb": True}))])),
        ("Assign Favorite Material", Sub(items=favorites)),
        ("Assign Existing Material", ("menu", "ALLSET_MT_assign_existing_material_rmb")),
    ]


# --- RMB: RMB_MESH --------------------------
# Mesh radials follow Maya 2022's RMB marking menu over a mesh and its object select masks;
# NE "Object Mode".

# The list under the ring, Maya 2022 order
# (step 52). The first row is the object's name
# (``OBJECT_TITLE`` is replaced by it when the menu opens). An empty ``Sub`` is a greyed submenu: Maya's
# dependency-graph / metadata / set editors have no Blender counterpart here.
OBJECT_TITLE = "<object>..."


def unavailable():
    """A greyed submenu (▸) whose Maya contents Blender doesn't have."""
    return Sub()


class NodeList(Sub):
    """DG Traversal / Inputs / Outputs: filled from the object when the menu opens (``with_nodes``; Maya fills them
    when the submenu opens). Never greyed: Maya shows the header rows even with no node."""

    def __init__(self, kind):
        super().__init__()
        self.kind = kind        # TRAVERSAL / INPUTS / OUTPUTS


def is_unavailable(action):
    return isinstance(action, Sub) and not isinstance(action, NodeList) and not action.radial and not action.items


def _object_items(mesh=True):
    """The RMB list under the ring (Maya 2026 order). ``mesh``: meshes also list Paint / UV Sets / Color Sets."""
    return [
        (OBJECT_TITLE, ("allset.object_attributes", {"rmb": True})),
        DIVIDER,
        ("Select", ("allset.mm_component", {"type": 'NONE'})),
        # SelectAll / SelectNone / InvertSelection = the Select menu's runTimeCommands (Maya 2022 RMB menu):
        # the same items, so component mode follows menu_map.EDIT_MODE (#62)
        ("Select All", _item("Select/All")),
        ("Deselect All", _item("Select/Deselect All")),
        ("Select Hierarchy", ("allset.mm_select_hierarchy", {})),
        ("Invert Selection", _item("Select/Inverse")),
        DIVIDER,
        ("Select Similar", _item("Select/Similar")),
        DIVIDER,
        ("Make Live", _on_object("Modify/Make Live")),
        DIVIDER,
        ("DG Traversal", NodeList("TRAVERSAL")),
        ("Inputs", NodeList("INPUTS")),
        ("Outputs", NodeList("OUTPUTS")),
        *([("Paint", Sub(items=[("Paint Skin Weights", ("paint.weight_paint_toggle", {}))]))] if mesh else []),
        ("Metadata", unavailable()),
        ("Actions", Sub(items=[
            ("Template", _on_object("Display/Object Display/Template")),
            ("Untemplate", _on_object("Display/Object Display/Untemplate")),
            ("Unparent", _on_object("Edit/Unparent")),
            ("Bounding Box", ("allset.mm_bounding_box", {})),
        ])),
        *([("UV Sets", ("menu", "ALLSET_MT_uv_sets_rmb")),
           ("Color Sets", ("menu", "ALLSET_MT_color_sets_rmb"))] if mesh else []),
        ("Time Editor", unavailable()),
        DIVIDER,
        ("Scene Assembly", unavailable()),
        *_material_items(),
    ]


RMB_MESH = MarkingMenu(
    "RMB_MESH", "Object", "maya",
    radial={
        "N": ("Edge", _comp('EDGE')),
        "W": ("Vertex", _comp('VERT')),
        "S": ("Face", _comp('FACE')),
        # A submenu, like Maya 2022's: the component at its own position, UV Shell at S (like Maya 2022's
        # RMB marking menu); both open the UV Editor (step 66).
        "E": ("UV", Sub(radial={"E": ("UV", ("allset.uv_component", {"mode": 'UV'})),
                                "S": ("UV Shell", ("allset.uv_component", {"mode": 'SHELL'}))})),
        "SW": ("Vertex Face", None),
        "SE": ("Multi", _comp('MULTI')),
        "NE": ("Object Mode", ("object.mode_set", {"mode": 'OBJECT'})),
    },
    items=_object_items(),
    options=("Select Similar",))

# Curve: N curve point, W CV, S edit point, E hull (Maya 2022 RMB marking menu over a curve). Blender
# curves edit control points only.
RMB_CURVE = MarkingMenu(
    "RMB_CURVE", "Curve", "maya",
    radial={
        "N": ("Curve Point", None),
        "W": ("Control Vertex", _comp('CV')),
        "S": ("Edit Point", None),
        "E": ("Hull", None),
        "NE": ("Object Mode", ("object.mode_set", {"mode": 'OBJECT'})),
    },
    items=_object_items(mesh=False),
    options=("Select Similar",))


# Lattice (#227): Maya's RMB marking menu over a lattice has Lattice Point at N; the
# list is the object list of a curve.
RMB_LATTICE = MarkingMenu(
    "RMB_LATTICE", "Lattice", "maya",
    radial={
        "N": ("Lattice Point", _comp('LATTICE')),
        "NE": ("Object Mode", ("object.mode_set", {"mode": 'OBJECT'})),
    },
    items=_object_items(mesh=False),
    options=("Select Similar",))


def with_object_name(menu, name):
    """A copy of ``menu`` whose ``OBJECT_TITLE`` row shows ``name`` (Maya: "pCube1...")."""
    items = [(f"{name}...", e[1]) if e != DIVIDER and e[0] == OBJECT_TITLE else e for e in menu.items]
    if items == menu.items:
        return menu
    return MarkingMenu(menu.name, menu.label, menu.source, menu.radial, items, menu.options)


# --- DG Traversal / Inputs / Outputs (step 165) ------------------------
# ``nodes`` (marking/rmb_nodes.py builds it, bpy-free here): {"object": name, "inputs": [(type label, owner, key)],
# "outputs": [...], "history": [(node name, owner, key)], "future": [...]}; owner = the object holding the node,
# key = its Attribute Editor tab key. Maya's Inputs / Outputs submenus: Select / Enable / Disable All, the nodes by type nice name
# (option box = showEditor = Attribute Editor), All Inputs...; Maya's DG Traversal submenu:
# Select <object>, then History / Future node names, each a submenu.

TITLE_ROW = ("allset.mm_node_label", {})     # Maya's "History" / "Future" rows: plain items without a command


def _pick(owner, key, replace=False):
    return ("allset.mm_node", {"object": owner, "key": key, "replace": replace})


def _node_lines(entries):
    """(items, option labels) of node rows."""
    return [(label, _pick(owner, key)) for label, owner, key in entries], {e[0] for e in entries}


def _history_sub(nodes, future):
    word = "Outputs" if future else "Inputs"
    obj = nodes["object"]
    entries = nodes["outputs" if future else "inputs"]
    rows, options = _node_lines(entries)
    every = ("allset.mm_node_all", {"object": obj, "future": future})
    items = [(f"Select All {word}", (every[0], {**every[1], "action": 'SELECT'})),
             (f"Enable All {word}", (every[0], {**every[1], "action": 'ENABLE'})),
             (f"Disable All {word}", (every[0], {**every[1], "action": 'DISABLE'})),
             DIVIDER, *rows]
    if rows:
        items.append(DIVIDER)
    items.append((f"All {word}...", ("allset.mm_node_table", {"object": obj, "future": future})))
    return Sub(items=items, options=options)


def _traversal_node(name, owner, key, nodes):
    """A node's own traversal submenu: Select <node>; the shape also lists its neighbours (one level)."""
    items = [(f"Select {name}", _pick(owner, key, replace=True))]
    if key == "S":
        for title, entries in (("History", nodes["inputs_named"]), ("Future", nodes["future"][1:])):
            if entries:
                items += [DIVIDER, (title, TITLE_ROW)] + [(n, _pick(o, k, replace=True)) for n, o, k in entries]
    return Sub(items=items)


def _traversal_sub(nodes):
    obj = nodes["object"]
    items = [(f"Select {obj}", _pick(obj, "T", replace=True))]
    for title, entries in (("History", nodes["history"]), ("Future", nodes["future"])):
        if entries:
            items += [DIVIDER, (title, TITLE_ROW)]
            items += [(n, _traversal_node(n, o, k, nodes)) for n, o, k in entries]
    return Sub(items=items)


def fill(kind, nodes):
    """The filled submenu of NodeList ``kind`` from ``nodes``."""
    nodes = {"inputs": [], "outputs": [], "history": [], "future": [], "inputs_named": [], **nodes}
    if kind == "TRAVERSAL":
        return _traversal_sub(nodes)
    return _history_sub(nodes, kind == "OUTPUTS")


def with_nodes(menu, nodes):
    """A copy of ``menu`` with its NodeList submenus filled from ``nodes`` (None: unchanged)."""
    if not nodes:
        return menu
    items = []
    changed = False
    for e in menu.items:
        if e != DIVIDER and isinstance(e[1], NodeList):
            items.append((e[0], fill(e[1].kind, nodes)))
            changed = True
        else:
            items.append(e)
    if not changed:
        return menu
    return MarkingMenu(menu.name, menu.label, menu.source, menu.radial, items, menu.options)


# Nothing under the cursor: Select All at S, Complete Tool at N (Maya's RMB marking menu over empty space).
RMB_EMPTY = MarkingMenu(
    "RMB_EMPTY", "Select", "maya",
    radial={"S": ("Select All", _item("Select/All")),
            "N": ("Complete Tool", None)})

# Pivot edit (D / Insert): the menu Maya's RMB shows while a pivot is being edited.
# Maya treats it as a state of the RMB_EMPTY menu, so it has its own kit id like RMB_CURVE. Show Orientation Handle / Bake Pivot Orientation have no Blender counterpart (greyed).
def _pivot_option(option):
    return ("allset.pivot_option", {"option": option})


def _pivot_reset(position=True, orientation=True):
    return ("allset.pivot_reset", {"position": position, "orientation": orientation})


PIVOT_EDIT = MarkingMenu(
    "PIVOT_EDIT", "Pivot", "maya",
    radial={
        "N": ("Pin Component Pivot", _pivot_option("PIN")),
        "S": ("Reset Pivot", _pivot_reset()),
        "NW": ("Snap Pivot Orientation", _pivot_option("SNAP_ORI")),
        "NE": ("Snap Pivot Position", _pivot_option("SNAP_POS")),
        "SW": ("Reset Pivot Orientation", _pivot_reset(position=False)),
        "SE": ("Reset Pivot Position", _pivot_reset(orientation=False)),
        "W": ("Show Orientation Handle", None),
        "E": ("Exit", ("allset.pivot_exit", {})),
    },
    items=[("Bake Pivot Orientation", _item("Modify/Bake Pivot")),  # Blender bakes the orientation
           DIVIDER,
           ("Center Position on Reset", _pivot_option("RESET_CENTER")),
           ("Zero Position on Reset", _pivot_option("RESET_ZERO"))])

# --- Shift+RMB: Maya's polygon tool marking menus -------------------------------------

SOFT_HARD = Sub(radial={  # Maya 2022 Shift+RMB object / edge marking menus
    "S": ("Toggle Soft Edge Display", SOFT_EDGE_DISPLAY),
    "SE": ("Harden Edge", "mesh.mark_sharp"),
    "E": ("Soften/Harden", _item("Mesh Display/Soften/Harden Edges")),   # PolygonSoftenHarden
    "NE": ("Soften Edge", ("mesh.mark_sharp", {"clear": True})),
}, options={"Soften/Harden"})

# Maya's Polygon Display submenus (Shift+RMB lists): the Display > Polygons check boxes of the 3D View.
_PD = {
    "Toggle Backface Culling": _item("Display/Polygons/Backface Culling"),
    "Toggle Border Edges": None,
    "Toggle Texture Border Edges": _item("Display/Polygons/Texture Border Edges"),
    "Toggle Face Normals": _item("Display/Polygons/Face Normals"),
    "Toggle Vertex Normals": _item("Display/Polygons/Vertex Normals"),
    "Toggle Face Centers": _item("Display/Polygons/Face Centers"),
    "Toggle Hidden Triangles": None,
    "Toggle Hidden Triangle Edges": None,
    "Toggle Vertices": None,
    "Toggle Vertex Numbers": None,
    "Toggle Face Numbers": None,
    "Reset Polygon Display": _item("Display/Polygons/Reset Display"),
}


def _poly_display(*labels, radial=None):
    return ("Polygon Display", Sub(radial=radial, items=[(label, _PD[label]) for label in labels]))


def _culling(on):
    return ("wm.context_set_boolean", {"data_path": "space_data.shading.show_backface_culling", "value": on})


POLY_DISPLAY_ALL = ("Polygon Display All", Sub(items=[
    ("Backface Culling on for All Polys", _culling(True)),
    ("Backface Culling off for All Polys", _culling(False)),
    ("Toggle All Geometry Border Edges", None),
    ("Toggle All Texture Border Edges", _item("Display/Polygons/Texture Border Edges")),
    ("Toggle All Face Normals", _item("Display/Polygons/Face Normals")),
    ("Toggle All Vertex Normals", _item("Display/Polygons/Vertex Normals")),
    ("Toggle All Face Centers", _item("Display/Polygons/Face Centers")),
    ("Toggle All Hidden Triangles", None),
    ("Toggle All Vertices", None),
    ("Reset Display for All Polys", _item("Display/Polygons/Reset Display")),
]))


def _planar_axis(axis):
    return ("allset.uv_planar", {"axis": axis})


def _mapping():
    """Maya's Mapping submenu (Shift+RMB object / face lists)."""
    return ("Mapping", Sub(items=[
        ("Planar Map X", _planar_axis('X')),
        ("Planar Map Y", _planar_axis('Y')),
        ("Planar Map Z", _planar_axis('Z')),
        ("Planar Map", _item("UV/Planar")),
        ("Cylindrical Map", _item("UV/Cylindrical")),
        ("Spherical Map", _item("UV/Spherical")),
        ("Automatic Map", _item("UV/Automatic")),
        ("Camera-Based Map", _item("UV/Camera-based")),
        ("Normal-Based Map", _item("UV/Normal-Based")),
    ], options={"Planar Map", "Cylindrical Map", "Spherical Map", "Automatic Map", "Camera-Based Map",
                "Normal-Based Map"}))


TRANSFORM_COMPONENT = _item("Edit Mesh/Transform")
CONNECT_TOOL = _item("Mesh Tools/Connect")

SHIFT_OBJECT = MarkingMenu(
    "SHIFT_OBJECT", "Object Tools", "maya",
    radial={
        "S": ("Extrude", _item("Edit Mesh/Extrude")),
        "SW": ("Insert Edge Loop Tool", _item("Mesh Tools/Insert Edge Loop")),
        "E": ("Append to Polygon Tool", _item("Mesh Tools/Append to Polygon")),
        "NE": ("Fill Holes", _item("Mesh/Fill Hole")),
        "N": ("Target Weld Tool", TARGET_WELD),
        "W": ("Multi-Cut", MULTI_CUT),
        "NW": ("Sculpt Tool", ("object.mode_set", {"mode": 'SCULPT'})),
        "SE": ("Soften/Harden Edges", Sub(radial={  # object level
            "S": ("Toggle Soft Edge Display", SOFT_EDGE_DISPLAY),
            "SE": ("Harden Edge", "object.shade_flat"),
            "E": ("Soften/Harden", "object.shade_auto_smooth"),
            "NE": ("Soften Edge", "object.shade_smooth"),
        }, options={"Soften/Harden"})),
    },
    items=[
        ("Offset Edge Loop Tool", _item("Mesh Tools/Offset Edge Loop")),
        ("Smooth", _mod('SUBSURF')),
        ("Unsmooth", _item("Mesh/Unsmooth")),
        ("Subdiv Proxy", _mod('SUBSURF')),
        ("Crease Tool", CREASE),
        DIVIDER,
        ("Project Curve on mesh", None),
        ("Split mesh with projected curve", _item("Edit Mesh/Split Mesh with Projected Curve")),
        DIVIDER,
        ("Mirror", "allset.mirror"),
        _mapping(),
        DIVIDER,
        ("Triangulate", _mod('TRIANGULATE')),
        ("Quadrangulate", _item("Mesh/Quadrangulate")),
        ("Reduce", _mod('DECIMATE')),
        ("Remesh", _item("Mesh/Remesh")),
        ("Retopologize", _item("Mesh/Retopologize")),
        DIVIDER,
        ("Transfer Vertex Order", None),
        DIVIDER,
        ("Separate", "allset.separate"),
        ("Combine", "allset.combine"),
        ("Booleans", Sub(items=[("Union", _item("Mesh/Booleans/Union")),
                                ("Difference (A - B)", _item("Mesh/Booleans/Difference (A - B)")),
                                ("Difference (B - A)", _item("Mesh/Booleans/Difference (B - A)")),
                                ("Intersection", _item("Mesh/Booleans/Intersection")),
                                ("Slice", None), ("Hole Punch", None), ("Cut Out", None), ("Split Edges", None)],
                         options={"Union", "Difference (A - B)", "Difference (B - A)", "Intersection", "Slice",
                                  "Hole Punch", "Cut Out", "Split Edges"})),
        DIVIDER,
        ("Cleanup...", _item("Mesh/Cleanup...")),
        ("Connect Tool", CONNECT_TOOL),
        ("Quad Draw Tool", _item("Mesh Tools/Quad Draw")),
        DIVIDER,
        _poly_display("Toggle Backface Culling", "Toggle Border Edges", "Toggle Texture Border Edges",
                      "Toggle Face Normals", "Toggle Vertex Normals", "Toggle Face Centers", "Toggle Hidden Triangles",
                      "Toggle Vertices", "Reset Polygon Display"),
    ],
    options=['Append to Polygon Tool', 'Combine', 'Connect Tool', 'Crease Tool', 'Insert Edge Loop Tool', 'Mirror',
             'Multi-Cut', 'Offset Edge Loop Tool', 'Project Curve on mesh', 'Quad Draw Tool', 'Quadrangulate',
             'Reduce', 'Remesh', 'Retopologize', 'Sculpt Tool', 'Smooth', 'Split mesh with projected curve',
             'Subdiv Proxy', 'Target Weld Tool', 'Unsmooth'])

SHIFT_VERTEX = MarkingMenu(
    "SHIFT_VERTEX", "Vertex Tools", "maya",
    radial={
        "S": ("Extrude Vertex", ("v3d", "mesh.extrude_vertices_move", {})),
        "E": ("Chamfer Vertex", _item("Edit Mesh/Chamfer Vertices")),  # step 139
        "SW": ("Delete Vertex", "mesh.dissolve_verts"),
        "SE": ("Vertex Normals", Sub(radial={
            "S": ("Toggle Vertex Normal Display", _overlay("show_vertex_normals")),
            "NE": ("Average Normals", "mesh.average_normals"),
            "E": ("Vertex Normal Edit Tool", _item("Mesh Display/Vertex Normal Edit Tool")),
            "SE": ("Set Normals to Face", "mesh.set_normals_from_faces"),
        }, options={"Average Normals", "Set Normals to Face"})),
        "N": ("Merge Vertices", Sub(radial={
            "NE": ("Merge Vertices", _item("Edit Mesh/Merge")),        # polyMergeVert (step 139)
            "N": ("Merge Vertices To Center", MERGE_CENTER),
            "S": ("Target Weld Tool", TARGET_WELD),
        }, options={"Merge Vertices", "Target Weld Tool"})),
        "NE": ("Average Vertices", "mesh.vertices_smooth"),
        "W": ("Multi-Cut", MULTI_CUT),
        "NW": ("Paint Select Vertices", PAINT_SELECT),
    },
    items=[
        ("Crease Tool", CREASE),
        ("Connect Components", _item("Edit Mesh/Connect")),  # step 139
        ("Detach Components", _item("Edit Mesh/Detach")),
        ("Transform Component", TRANSFORM_COMPONENT),
        ("Connect Tool", CONNECT_TOOL),
        DIVIDER,
        ("Circularize Vertices", CIRCULARIZE),
        ("Reorder Vertices", None),
        DIVIDER,
        ("Apply Color", _item("Mesh Display/Apply Color")),
        DIVIDER,
        _poly_display("Toggle Backface Culling", "Toggle Vertices", "Toggle Vertex Normals", "Toggle Vertex Numbers",
                      "Reset Polygon Display"),
    ],
    options=['Apply Color', 'Chamfer Vertex', 'Circularize Vertices', 'Connect Components', 'Connect Tool',
             'Crease Tool', 'Extrude Vertex', 'Multi-Cut', 'Transform Component'])

SHIFT_EDGE = MarkingMenu(
    "SHIFT_EDGE", "Edge Tools", "maya",
    radial={
        "S": ("Extrude Edge", ("v3d", "mesh.extrude_edges_move", {})),
        "SW": ("Delete Edge", "mesh.dissolve_edges"),
        "E": ("Bevel Edge", _item("Edit Mesh/Bevel")),  # step 139
        "SE": ("Soften/Harden Edges", SOFT_HARD),
        "N": ("Merge/Collapse Edges", Sub(radial={
            "NE": ("Merge Border Edges", "mesh.remove_doubles"),
            "S": ("Target Weld Tool", TARGET_WELD),
            "E": ("Collapse Edge", "mesh.edge_collapse"),
            "N": ("Merge Edges To Center", MERGE_CENTER),
        }, options={"Merge Border Edges", "Target Weld Tool"})),
        "NE": ("Flip/Spin Edge", Sub(radial={
            "N": ("Flip Triangle Edge", "mesh.edge_rotate"),
            "E": ("Spin Forward", ("mesh.edge_rotate", {"use_ccw": False})),
            "W": ("Spin Backward", ("mesh.edge_rotate", {"use_ccw": True})),
        })),
        "W": ("Multi-Cut", MULTI_CUT),
        "NW": ("Paint Select Edges", PAINT_SELECT),
    },
    items=[
        ("Crease Tool", CREASE),
        ("Offset Edge Loop Tool", _item("Mesh Tools/Offset Edge Loop")),
        ("Insert Edge Loop Tool", _item("Mesh Tools/Insert Edge Loop")),
        ("Slide Edge Tool", _item("Mesh Tools/Slide Edge")),
        ("Circularize Components", CIRCULARIZE),
        ("Edit Edge Flow", _item("Edit Mesh/Edit Edge Flow")),
        DIVIDER,
        ("Add Divisions To Edge", "mesh.subdivide"),
        ("Bridge", "mesh.bridge_edge_loops"),
        ("Fill Hole", "mesh.fill_holes"),
        DIVIDER,
        ("Connect Components", _item("Edit Mesh/Connect")),  # step 139
        ("Detach Components", "mesh.edge_split"),
        ("Transform Component", TRANSFORM_COMPONENT),
        ("Connect Tool", CONNECT_TOOL),
        DIVIDER,
        _poly_display("Toggle Backface Culling", "Toggle Border Edges", "Toggle Texture Border Edges",
                      "Toggle Hidden Triangle Edges", "Reset Polygon Display",
                      radial={"S": ("Toggle Soft Edge Display", SOFT_EDGE_DISPLAY)}),
    ],
    options=['Add Divisions To Edge', 'Bevel Edge', 'Bridge', 'Circularize Components', 'Connect Components',
             'Connect Tool', 'Crease Tool', 'Edit Edge Flow', 'Extrude Edge', 'Insert Edge Loop Tool', 'Multi-Cut',
             'Offset Edge Loop Tool', 'Slide Edge Tool', 'Transform Component'])

SHIFT_FACE = MarkingMenu(
    "SHIFT_FACE", "Face Tools", "maya",
    radial={
        "N": ("Merge Faces To Center", MERGE_CENTER),
        "S": ("Extrude Face", ("v3d", "allset.extrude", {})),  # step 65
        "SW": ("Wedge Face", _item("Edit Mesh/Wedge")),
        "NE": ("Poke Face", "mesh.poke"),
        "E": ("Bevel Face", _item("Edit Mesh/Bevel")),  # step 139
        "SE": ("Face Normals", Sub(radial={
            "S": ("Toggle Face Normal Display", _overlay("show_face_normals")),
            "NE": ("Reverse Propagate", _poly('REVERSE_PROPAGATE')),     # polyNormal -normalMode 4
            "SE": ("Conform Normals", "mesh.normals_make_consistent"),
            "E": ("Reverse Normals", _item("Mesh Display/Reverse")),
        }, options={"Reverse Normals"})),
        "W": ("Multi-Cut", MULTI_CUT),
        "NW": ("Paint Select Faces", PAINT_SELECT),
    },
    items=[
        DIVIDER,
        ("Smart Extrude", _item("Edit Mesh/Smart Extrude")),
        ("Smooth Faces", ("mesh.subdivide", {"smoothness": 1.0})),
        ("Assign Invisible Faces", None),
        ("Add Divisions To Faces", "mesh.subdivide"),
        ("Circularize Components", CIRCULARIZE),
        ("Connect Components", _item("Edit Mesh/Connect")),
        ("Detach Components", _item("Edit Mesh/Detach")),
        ("Triangulate Faces", "mesh.quads_convert_to_tris"),
        ("Quadrangulate Faces", _item("Mesh/Quadrangulate")),
        ("Reduce Faces", _item("Mesh/Reduce")),
        ("Remesh", _item("Mesh/Remesh")),
        ("Bridge Faces", "mesh.bridge_edge_loops"),
        DIVIDER,
        ("Mirror", "allset.mirror"),
        ("Extract Faces", ("mesh.separate", {"type": 'SELECTED'})),
        ("Duplicate Face", ("v3d", "mesh.duplicate_move", {})),
        ("Transform Component", TRANSFORM_COMPONENT),
        ("Connect Tool", CONNECT_TOOL),
        ("Target Weld Tool", TARGET_WELD),  # step 64
        DIVIDER,
        _mapping(),
        DIVIDER,
        _poly_display("Toggle Backface Culling", "Toggle Face Centers", "Toggle Face Normals", "Toggle Face Numbers",
                      "Toggle Hidden Triangles", "Reset Polygon Display"),
    ],
    options=['Add Divisions To Faces', 'Assign Invisible Faces', 'Bevel Face', 'Bridge Faces',
             'Circularize Components', 'Connect Components', 'Connect Tool', 'Duplicate Face', 'Extract Faces',
             'Extrude Face', 'Mirror', 'Multi-Cut', 'Poke Face', 'Quadrangulate Faces', 'Reduce Faces', 'Remesh',
             'Smooth Faces', 'Target Weld Tool', 'Transform Component', 'Wedge Face'])

SHIFT_DEFAULT = MarkingMenu(
    "SHIFT_DEFAULT", "Create", "maya",
    radial={
        "N": ("Create Polygon Tool", _item("Mesh Tools/Create Polygon")),
        "NE": ("Disc", _create('DISC')),
        "E": ("Sphere", _create('SPHERE')),
        "SE": ("Torus", _create('TORUS')),
        "S": ("Cube", _create('CUBE')),
        "SW": ("Cone", _create('CONE')),
        "W": ("Cylinder", _create('CYLINDER')),
        "NW": ("Plane", _create('PLANE')),
    },
    items=[
        ("Platonic Solid", _create('PLATONIC')),
        ("Pyramid", _create('PYRAMID')),
        ("Prism", _create('PRISM')),
        ("Pipe", _create('PIPE')), ("Helix", _create('HELIX')), ("Gear", _create('GEAR')),   # step 190
        ("Soccer Ball", _item("Create/Polygon Primitives/Soccer Ball")),
        DIVIDER,
        ("Super Ellipse", _item("Create/Polygon Primitives/Super Ellipse")),
        ("Spherical Harmonics", _item("Create/Polygon Primitives/Spherical Harmonics")),
        ("Ultra Shape", _item("Create/Polygon Primitives/Ultra Shape")),
        ("Type", _create('TEXT')),
        ("SVG", _item("Create/SVG")),
        ("Quad Draw Tool", _item("Mesh Tools/Quad Draw")),
        DIVIDER,
        ("Interactive Creation", _item("Create/Polygon Primitives/Interactive Creation")),
        ("Exit On Completion", _item("Create/Polygon Primitives/Exit On Completion")),
        DIVIDER,
        POLY_DISPLAY_ALL,
    ],
    options=['Cone', 'Create Polygon Tool', 'Cube', 'Cylinder', 'Disc', 'Gear', 'Helix', 'Pipe', 'Plane',
             'Platonic Solid', 'Prism', 'Pyramid', 'Quad Draw Tool', 'Soccer Ball', 'Sphere', 'Spherical Harmonics',
             'Super Ellipse', 'Torus', 'Ultra Shape'])

# --- Ctrl+RMB: CTRL_CONVERT -----------------------------------------------

_CS = "Select/Convert Selection/"

CTRL_CONVERT = MarkingMenu(
    "CTRL_CONVERT", "Convert Selection", "maya",
    # Every convert entry runs the Select menu item with the same runTimeCommand (step 141: menu and marking menu
    # agree); the convert-then-act items stay allset.mm_poly.
    radial={
        "N": ("To Edges", Sub(radial={
            "N": ("To Edges", _item(_CS + "To Edges")),
            "S": ("To Contained Edges", _item(_CS + "To Contained Edges")),
            "NW": ("To Contiguous Edges", _item("Select/Contiguous Edges")),
            "NE": ("To Edge Perimeter", _item(_CS + "To Edge Perimeter")),
        }, options={"To Contiguous Edges"})),
        "NW": ("Shrink Selection", Sub(radial={
            "NW": ("Shrink", _item("Select/Shrink")),
            "N": ("Shrink Selection Along Loop", _item("Select/Shrink Along Loop")),
        })),
        "E": ("To UVs", Sub(radial={
            "E": ("To UVs", _item(_CS + "To UVs")),                         # UV selection = the UV Editor (step 66)
            "NE": ("To UV Perimeter", _item(_CS + "To UV Perimeter")),
        })),
        "SE": ("Edge Loop Utilities", Sub(radial={
            "SE": ("To Edge Loop", _item(_CS + "To Edge Loop")),
            "NE": ("To Edge Loop and Delete", _poly('LOOP_DELETE')),
            "SW": ("To Edge Loop and Duplicate", _poly('LOOP_DUPLICATE')),
        })),
        "SW": ("Edge Ring Utilities", Sub(radial={
            "SW": ("To Edge Ring", _item(_CS + "To Edge Ring")),
            "SE": ("To Edge Ring and Split", _poly('RING_SPLIT')),
            "NW": ("To Edge Ring and Collapse", _poly('RING_COLLAPSE')),
        })),
        "S": ("To Faces", Sub(radial={
            "S": ("To Faces", _item(_CS + "To Faces")),
            "N": ("To Contained Faces", _item(_CS + "To Contained Faces")),
            "SE": ("To Face Perimeter", _item(_CS + "To Face Perimeter")),
        })),
        "W": ("To Vertices", Sub(radial={
            "W": ("To Vertices", _item(_CS + "To Vertices")),
            "NW": ("To Vertex Perimeter", _item(_CS + "To Vertex Perimeter")),
        })),
        "NE": ("Grow Selection", Sub(radial={
            "NE": ("Grow", _item("Select/Grow")),
            "N": ("Grow Along Loop", _item("Select/Grow Along Loop")),
        })),
    },
    items=[
        ("To Face Path", _item(_CS + "To Face Path")),
        ("To UV Shell", _item(_CS + "To UV Shell")),
        ("To Shell", _item(_CS + "To Shell")),
        ("To Shell Border", _item(_CS + "To Shell Border")),
        DIVIDER,
        # Maya's tool picks a border edge and takes the whole border = Blender's edge loop select on a border edge
        ("Select Border Edge Tool", _item(_CS + "To Edge Loop")),
        DIVIDER,
        ("Selection Boundary", "mesh.region_to_loop"),
        ("Selection Constraints...", None),
    ])

# --- Tool options: q/w/e/r hold + LMB, Ctrl+Shift+RMB -----------------------
# Maya manip modes -> Blender transform orientations (Object = Local, Component = Normal).

def _toggle(path):
    return ("wm.context_toggle", {"data_path": path})


def _select_prefs():
    """Maya's Select submenu (S) of the Move / Rotate / Scale / Select tool option menus: selection preferences."""
    return ("Select", Sub(radial={
        "N": ("Preselection Highlight", _toggle("window_manager.allset_mtk_nearest")),
        "NE": ("Highlight Nearest Component", _toggle("window_manager.allset_mtk_nearest")),
        "E": ("Highlight Backfaces", None),
        "SE": ("Asset Centric", None),
        "NW": ("Marquee", ("tool", "builtin.select_box", False)),
        "W": ("Camera-Based Selection", ("allset.mm_camera_based", {})),
        "SW": ("Clear Selection", "allset.mm_clear_selection"),
        "S": ("Soft Select", Sub(radial={
            "N": ("Object", None),
            "S": ("Soft Select", _toggle("scene.allset_soft_select")),
            "SW": ("Volume", ("allset.soft_falloff_mode", {"surface": False})),
            "W": ("Surface", ("allset.soft_falloff_mode", {"surface": True})),
            "NW": ("Global", None),
            "E": ("Color Feedback", None),
        })),
    }, items=[("Automatic Camera-Based Selection", None)]))


def _constraints():
    """Maya's Selection / Transform Constraints submenus of the tool option menus: no Blender selection
    constraint; Transform Constraints = the kit's Move-tool slide setting (operators/xform_constraint.py)."""
    def tc(mode):
        return ("allset.xform_constraint", {"mode": mode})
    return [("Selection Constraints", unavailable()),
            ("Transform Constraints", Sub(items=[("Off", tc('NONE')), ("Edge Slide", tc('EDGE')),
                                                 ("Surface Slide", tc('SURFACE')), ("Along Normals", None)]))]


def _custom_axis(slot):
    """Maya's Custom axis submenu: use it, set it from the selection (component / point / edge / face) or the
    object, reset the tool's axis (operators/pivot_menu.py)."""
    def ax(action):
        return ("allset.custom_axis", {"slot": slot, "action": action})
    return Sub(radial={
        "E": ("Custom", ax("USE")),
        "W": ("Set to Component", ax("SELECTION")),
        "SW": ("Set To Point", ax("SELECTION")),
        "S": ("Set To Edge", ax("SELECTION")),
        "SE": ("Set To Face", ax("SELECTION")),
        "N": ("Set To Object", ax("OBJECT")),
        "NW": ("Reset", ax("RESET")),
    })


def _pivot_point(mode):
    # Maya Rotate / Scale Center = the transform pivot point
    return ("wm.context_set_enum", {"data_path": "scene.tool_settings.transform_pivot_point", "value": mode})


def _center(selection=True):
    items = [("Default", _pivot_point('MEDIAN_POINT')), ("Object", _pivot_point('INDIVIDUAL_ORIGINS')),
             ("Manip", _pivot_point('CURSOR'))]   # the kit's edited component pivot is the 3D cursor
    if selection:
        items.append(("Selection", _pivot_point('BOUNDING_BOX_CENTER')))
    return Sub(items=items)


# Maya Tweak Mode: dragging a component moves it = Blender's Tweak tool
TWEAK_MODE = ("tool", "builtin.select", False)
SHIFT_EXTRUDE = ("Shift Extrude", SMART_EXTRUDE)
SHIFT_DUPLICATE = ("Shift Duplicate", SMART_DUPLICATE)

OPT_MOVE = MarkingMenu(
    "OPT_MOVE", "Move Options", "maya",
    radial={
        "NE": ("Component", _orient('NORMAL', 1)),
        "W": ("World", _orient('GLOBAL', 1)),
        "NW": ("Object", _orient('LOCAL', 1)),
        "SE": ("Keep Spacing", None),
        "N": SYMMETRY,
        "S": _select_prefs(),
        "E": ("Snap", Sub(radial={
            "E": ("Discrete Move", _step('TRANSLATE')),
            "SE": ("Vertex", ("allset.snap_toggle", {"snap": 'POINT'})),
            "SW": ("Face Center", None),
        }, items=[("Relative Mode", _step('TRANSLATE', 'RELATIVE'))])),
        "SW": ("Axis", Sub(radial={
            "NW": ("Normal", _orient('NORMAL', 1)),
            "W": ("Parent", _orient('PARENT', 1)),
            "NE": ("Along Rotation Axis", _orient('GIMBAL', 1)),
            "N": ("Live Object Axis", None),
            "SW": ("Custom", _custom_axis(1)),
        })),
    },
    items=[
        *_constraints(),
        DIVIDER,
        SHIFT_EXTRUDE, SHIFT_DUPLICATE,
        DIVIDER,
        ("Preserve UVs", PRESERVE_UVS),
        ("Preserve Children", PRESERVE_CHILDREN),
        ("Tweak Mode", TWEAK_MODE),
        ("Update Triad", None),
        DIVIDER,
        ("Move Options", TOOL_SETTINGS),
    ])

OPT_ROTATE = MarkingMenu(
    "OPT_ROTATE", "Rotate Options", "maya",
    radial={
        "NW": ("Object", _orient('LOCAL', 2)),
        "W": ("World", _orient('GLOBAL', 2)),
        "SW": ("Custom", _custom_axis(2)),
        "SE": ("Discrete Rotate", _step('ROTATE')),  # 15 degrees, S3
        "NE": ("Component", _orient('NORMAL', 2)),
        "E": ("Gimbal", _orient('GIMBAL', 2)),
        "N": SYMMETRY,
        "S": _select_prefs(),
    },
    items=[
        *_constraints(),
        DIVIDER,
        SHIFT_EXTRUDE, SHIFT_DUPLICATE,
        DIVIDER,
        ("Rotate Center", _center()),
        ("Free Rotate", None),
        ("Preserve UVs", PRESERVE_UVS),
        ("Preserve Children", PRESERVE_CHILDREN),
        ("Tweak Mode", TWEAK_MODE),
        ("Relative", _step('ROTATE', 'RELATIVE')),
        DIVIDER,
        ("Rotate Options", TOOL_SETTINGS),
    ])

OPT_SCALE = MarkingMenu(
    "OPT_SCALE", "Scale Options", "maya",
    radial={
        "W": ("World", _orient('GLOBAL', 3)),
        "NW": ("Object", _orient('LOCAL', 3)),
        "NE": ("Component", _orient('NORMAL', 3)),
        "SW": ("Axis", Sub(radial={
            "W": ("Parent", _orient('PARENT', 3)),
            "NW": ("Normal", _orient('NORMAL', 3)),
            "N": ("Live Object Axis", None),
            "NE": ("Along Rotation Axis", _orient('GIMBAL', 3)),
            "SW": ("Custom", _custom_axis(3)),
        })),
        "E": ("Snap Scale", _step('RESIZE')),
        "SE": ("Relative", _step('RESIZE', 'RELATIVE')),
        "N": SYMMETRY,
        "S": _select_prefs(),
    },
    items=[
        *_constraints(),
        DIVIDER,
        SHIFT_EXTRUDE, SHIFT_DUPLICATE,
        DIVIDER,
        ("Scale Center", _center(selection=False)),
        ("Prevent Negative Scale", ("allset.prevent_negative_scale", {})),
        ("Preserve UVs", PRESERVE_UVS),
        ("Preserve Children", PRESERVE_CHILDREN),
        ("Tweak Mode", TWEAK_MODE),
        DIVIDER,
        ("Scale Options", TOOL_SETTINGS),
    ])

OPT_SELECT = MarkingMenu(
    "OPT_SELECT", "Select Options", "maya",
    radial={
        "W": ("Paint Select", ("tool", "builtin.select_circle", False)),
        "E": ("Lasso", ("tool", "builtin.select_lasso", False)),
        "N": SYMMETRY,
        "S": _select_prefs(),
    },
    items=_constraints())

def _qd(prop, value=None):
    """A Quad Draw setting: a check item (``value`` None) or a radio item."""
    path = f"scene.allset_poly_tools.{prop}"
    if value is None:
        return ("wm.context_toggle", {"data_path": path})
    return ("wm.context_set_enum", {"data_path": path, "value": value})


# Quad Draw's Ctrl+Shift+RMB options menu (Maya's layout).
OPT_QUAD_DRAW = MarkingMenu(
    "OPT_QUAD_DRAW", "Quad Draw Options", "maya",
    radial={
        "N": ("Multi-Cut Tool", MULTI_CUT),
        "W": ("Auto-weld", _qd("qd_auto_weld")),
        "E": ("Clear Dots", "allset.quad_draw_clear_dots"),
        "NE": ("Soften/Harden Edges", ("allset.soften_harden", {"whole": True})),
        "NW": ("Relax", Sub(radial={
            "N": ("All vertices", _qd("qd_relax", 'ALL')),
            "NW": ("Auto-Lock", _qd("qd_relax", 'AUTO_LOCK')),
            "SW": ("Interior vertices", _qd("qd_relax", 'INTERIOR')),
            "W": ("Border vertices", _qd("qd_relax", 'BORDER')),
        })),
        "SW": ("Extend", Sub(radial={
            "W": ("Border", _qd("qd_extend", 'BORDER')),
            "SW": ("Edge", _qd("qd_extend", 'EDGE')),
            "S": ("Loop", _qd("qd_extend", 'LOOP')),
        })),
    },
    items=[
        ("Snap to Backfaces", _qd("qd_snap_backfaces")),
        DIVIDER,
        ("Reset Settings", ("allset.poly_tools_reset", {"kind": 'QUAD_DRAW'})),
    ],
    options={"Soften/Harden Edges"})

# --- A hold + LMB: SELECT_ALL -------------
# Inputs/outputs = history in Maya; the Blender history equivalent (modifiers) has no
# up/downstream selection, so W/E/N/S stay greyed (step 10).

SELECT_ALL = MarkingMenu(
    "SELECT_ALL", "Select All / History", "maya",
    radial={
        "W": ("Select All Inputs", None),
        "E": ("Select All Outputs", None),
        "N": ("Enable All Outputs", None),
        "S": ("Disable All Outputs", None),
        "NW": ("Delete History", "allset.delete_history"),
        "NE": ("Delete Non-Deformer History", ("allset.delete_history", {"non_deformer": True})),
        "SE": ("Freeze Transforms", "allset.freeze_transform"),
        "SW": ("Reset Transforms", _item("Modify/Reset Transformations")),
    },
    options={"Freeze Transforms", "Reset Transforms"})

# --- Shift+S hold + LMB: KEY_TANGENT (Maya's Keyframe / Tangent marking menu, Maya hotkey) --------------------
# Maya shows the same layout inside and outside the Graph Editor; the actions pick the
# Graph Editor's selected keys or the current-time keys themselves (operators/graph_keys.py, step 70).

def _tan(kind):
    return ("allset.set_tangent", {"kind": kind})


def _key(action):
    return ("allset.key_edit", {"action": action})


KEY_TANGENT = MarkingMenu(
    "KEY_TANGENT", "Keyframe / Tangents", "maya",
    radial={
        "W": ("Keys", Sub(radial={
            "N": ("Delete Keys", _key("DELETE")),
            "NE": ("Convert to Key", _key("TO_KEY")),
            "E": ("Paste Keys", _key("PASTE")),
            "NW": ("Convert to Breakdown", _key("TO_BREAKDOWN")),
            "S": ("Copy Keys", _key("COPY")),
            "SW": ("Remove Inbetween", _key("REMOVE_INBETWEEN")),
            "W": ("Cut Keys", _key("CUT")),
            "SE": ("Add Inbetween", _key("ADD_INBETWEEN")),
        })),
        "E": ("Tangents", Sub(radial={
            "N": ("Spline", _tan("SPLINE")),
            "E": ("Flat", _tan("FLAT")),
            "S": ("Linear", _tan("LINEAR")),
            "W": ("Clamped", _tan("CLAMPED")),
            "NW": ("Stepped", _tan("STEPPED")),
            "SW": ("Stepped Next", _tan("STEPPED_NEXT")),
            "SE": ("Plateau", _tan("PLATEAU")),
            "NE": ("Fixed", _tan("FIXED")),
        })),
    })

# --- Shift+Q / Alt+Q hold + LMB (Maya hotkeys) ----------------------------------------------------------------
# SELECT_COMPONENT (Maya's Shift+Q hold menu) = the component pick mask; Blender's mask is the
# mesh select mode, so only Poly Vertices / Poly Edges / Faces / All Components on / Select Objects do something.
# SELECT_POLYGON (Maya's Alt+Q hold menu) = F9 / F10 / F11 / F12.

def _mask(kind):
    return ("allset.component_mask", {"kind": kind})


SELECT_COMPONENT = MarkingMenu(
    "SELECT_COMPONENT", "Component Pick Mask", "maya",
    radial={
        "N": ("Points", Sub(radial={
            "N": ("All Points", None),
            "E": ("CVs", None),
            "SE": ("Poly Vertices", _mask("VERT")),
            "S": ("Lattice Points", None),
            "W": ("Particles", None),
            "SW": ("Subdiv Mesh Points", None),
        })),
        "NE": ("Parm Points", Sub(radial={
            "NE": ("All Parm Points", None),
            "E": ("Edit Points", None),
            "S": ("Curve Points", None),
            "W": ("Surface Points", None),
            "SW": ("Subdiv Mesh UVs", None),
        })),
        "E": ("Lines", Sub(radial={
            "E": ("All Lines", None),
            "S": ("Poly Edges", _mask("EDGE")),
            "W": ("Isoparms", None),
            "N": ("Trim Edges", None),
            "SE": ("Springs", None),
        })),
        "SE": ("Faces", _mask("FACE")),
        "S": ("Hulls", None),
        "SW": ("Pivots", Sub(radial={
            "SW": ("All Pivots", None),
            "NW": ("Rotate Pivots", None),
            "NE": ("Scale Pivots", None),
            "SE": ("Joint Pivots", None),
        })),
        "W": ("Handles", None),
        "NW": ("Misc.", Sub(radial={
            "NW": ("All Misc", None),
            "E": ("Local Rotation Axes", None),
            "S": ("Image Planes", None),
        })),
    },
    items=[("All Components on", _mask("ALL")), ("All Components off", None), DIVIDER,
           ("Save to shelf", None), DIVIDER, ("Select Objects", ("object.mode_set", {"mode": 'OBJECT'}))])


def _component(kind):
    return ("allset.component_mode", {"type": kind})


SELECT_POLYGON = MarkingMenu(
    "SELECT_POLYGON", "Polygon Components", "maya",
    radial={
        "N": ("Vertices", _component("VERT")),
        "E": ("Edges", _component("EDGE")),
        "S": ("Faces", _component("FACE")),
        "W": ("UVs", ("allset.uv_component", {"mode": 'UV'})),
    })

# --- Hotbox zones ------

def _pane(ui_type):
    return ("allset.hb_pane", {"ui_type": ui_type})


def _ui(element):
    return ("allset.hb_ui", {"element": element})


def _mask(preset):
    return ("allset.hb_mask", {"preset": preset})


def _view(view):
    return ("allset.hb_view", {"view": view})


SHADING_WS = ("allset.hb_workspace", {"name": "Shading"})
ANIMATION_WS = ("allset.hb_workspace", {"name": "Animation"})

HB_NORTH = MarkingMenu(
    "HB_NORTH", "Panel Layouts", "maya",
    radial={
        "N": ("Single Perspective", ("allset.hb_single", {})),          # Maya hotbox North zone
        "NE": ("Hypershade/Render/Persp", SHADING_WS),
        "SE": ("Hypershade/Outliner/Persp", SHADING_WS),
        "E": ("Hypershade/Persp", SHADING_WS),
        "S": ("Toggle Outliner", _item("Windows/Outliner")),
        "SW": ("Persp/Graph/Outliner", ANIMATION_WS),
        "W": ("Persp/Graph", ANIMATION_WS),
        "NW": ("Persp/Relationship Editor", None),
    })

HB_SOUTH = MarkingMenu(
    "HB_SOUTH", "Panel Types", "maya",
    radial={
        "N": ("Outliner", _pane('OUTLINER')),                              # Maya hotbox South zone
        "E": ("Graph Editor", _pane('FCURVES')),
        "SE": ("Dope Sheet", _pane('DOPESHEET')),
        "S": ("Hypergraph", ("allset.hypergraph", {})),   # the kit's Hypergraph: Hierarchy window
        "SW": ("Node Editor", _pane('ShaderNodeTree')),
        "W": ("Hypershade", _pane('ShaderNodeTree')),
        "NW": ("Render View", _pane('IMAGE_EDITOR')),
        "NE": ("Sets", _pane('OUTLINER')),  # kit sets = Outliner rows
    })

HB_EAST = MarkingMenu(
    "HB_EAST", "UI Elements", "maya",
    radial={
        "N": ("Help Line", _ui('HELP_LINE')),                              # Maya hotbox East zone
        "NE": ("Status Line", _ui('STATUS_LINE')),
        "E": ("Attributes", Sub(radial={
            "E": ("Channel Box", _ui('CHANNEL_BOX')),
            "S": ("Layer Editor", _ui('CHANNEL_BOX')),
            "W": ("Attribute Editor", _ui('ATTRIBUTE')),
            "N": ("Tool Settings", _ui('TOOL_SETTINGS')),
        })),
        "SE": ("Tool Box", _ui('TOOLBOX')),
        "S": ("Time Slider", None),
        "SW": ("Range Slider", None),
        "W": ("Shelf", ("allset.shelf_strip_toggle", {})),                 # Windows > UI Elements > Shelf
        "NW": ("Command Line", _ui('COMMAND_LINE')),
    })

HB_WEST = MarkingMenu(
    "HB_WEST", "Selection Masks", "maya",
    radial={
        "N": ("NURBS Mask", _mask('NURBS')),
        "NE": ("Hierarchy", None),
        "E": ("Animation Mask", _mask('ANIMATION')),
        "SE": ("Deformations Mask", _mask('DEFORMATIONS')),
        "S": ("Dynamics Mask", None),
        "SW": ("Polygons Mask", _mask('POLYGONS')),
        "W": ("Rendering Mask", _mask('RENDERING')),
        "NW": ("Object/Components", "object.editmode_toggle"),
    })

HB_CENTER = MarkingMenu(
    "HB_CENTER", "Views", "maya",
    radial={
        "N": ("Perspective View", _view('PERSP')),                         # Maya hotbox centre zone
        "E": ("Right View", _view('RIGHT')),
        "NE": ("New Camera", ("allset.camera_from_view", {})),
        "S": ("Front View", _view('FRONT')),
        "W": ("Top View", _view('TOP')),
        "NW": ("Left View", _view('LEFT')),
        "SW": ("Back View", _view('BACK')),
        "SE": ("Bottom View", _view('BOTTOM')),
    },
    items=[("Hotbox Style", Sub(items=[
        ("Zones and Menu Rows", ("allset.hb_style", {"style": 'ALL'})),
        ("Zones Only", ("allset.hb_style", {"style": 'ZONES'})),
        ("Center Zone Only", ("allset.hb_style", {"style": 'CENTER'})),
    ]))])

HOTBOX_ZONES = {"N": HB_NORTH, "S": HB_SOUTH, "E": HB_EAST, "W": HB_WEST, "C": HB_CENTER}

# --- UV Editor (step 66) ------------------------------------------------------------------------

def _uvc(mode):
    return ("allset.uv_component", {"mode": mode})


# RMB in the UV Editor: Maya 2026's UV Editor marking menu (polygon version); the list under it is a copy of the UV
# Editor menu bar.
UV_EDITOR_RMB = MarkingMenu(
    "UV_EDITOR_RMB", "UV Editor", "maya",
    radial={
        "S": ("Face", _uvc('FACE')),
        "N": ("Edge", _uvc('EDGE')),
        "E": ("UV", _uvc('UV')),
        "W": ("Vertex", _uvc('VERTEX')),
        "NW": ("UV Shell", _uvc('SHELL')),
    },
    # Maya's list = the UV Editor menu bar (without Help), each opening that menu
    items=[(title, ("menu", f"ALLSET_MT_ed_UvEditor_{i}")) for i, title in enumerate(
        ("Edit", "Create", "Select", "Cut/Sew", "Modify", "Tools", "View", "Image", "Textures", "UV Sets"))])

# Shift+RMB in the UV Editor: Maya's UV / UV Shell tool marking menus,
# Mapping = Maya's UV mapping submenu.
UV_MAPPING = Sub(radial={
    "N": ("Planar", "allset.uv_planar"),
    "NE": ("Normal-Based", "allset.uv_planar"),
    "E": ("Camera-Based", ("v3d", "uv.project_from_view", {})),
    "SE": ("Cylindrical", ("v3d", "uv.cylinder_project", {})),
    "S": ("Best Plane", _item("UV/Best Plane")),
    "SW": ("Spherical", ("v3d", "uv.sphere_project", {})),
    "W": ("Contour Stretch", _item("UV/Contour Stretch")),
    "NW": ("Automatic", _item("UV/Automatic")),               # polyAutoProj (step 139)
}, options={"Planar", "Normal-Based", "Camera-Based", "Cylindrical", "Spherical", "Contour Stretch", "Automatic"})
# SetMeshGrabUVTool: Maya grabs UVs from the 3D View; these menus open in the UV Editor, whose Grab tool does it.
GRAB_UV = _item("UV Editor/Tools/Grab")
_UV_TAIL = [("Texture Borders", ("allset.uv_display", {"mode": 'TEXTURE_BORDERS'})), DIVIDER, ("UV Editor", ("allset.uv_component", {"mode": 'OPEN'})),
            ("UV Set Editor", _item("UV/UV Set Editor"))]

SHIFT_UV = MarkingMenu(
    "SHIFT_UV", "UV Tools", "maya",
    radial={
        "N": ("Mapping", UV_MAPPING),
        "NE": ("3D Grab UV Tool", GRAB_UV),
        "E": ("Sew UVs", "allset.uv_sew"),
        "SE": ("Create UV Shell", "allset.uv_create_shell"),  # step 155
        "S": ("Merge UVs", "allset.uv_merge"),
        "SW": ("Delete UVs", "allset.uv_delete"),  # step 155
        "W": ("Cut UVs", "allset.uv_cut"),
        "NW": ("3D Cut and Sew UV Tool", "allset.cut_sew_tool_set"),  # step 79
    },
    items=[("Auto Seams", _item("UV/Auto Seams")), *_UV_TAIL],
    options={"3D Grab UV Tool", "Merge UVs", "3D Cut and Sew UV Tool", "Auto Seams"})

SHIFT_UV_SHELL = MarkingMenu(
    "SHIFT_UV_SHELL", "UV Shell Tools", "maya",
    radial={
        "N": ("Mapping", UV_MAPPING),
        "NE": ("3D Grab UV Tool", GRAB_UV),
        "E": ("Optimize", "uv.minimize_stretch"),
        "SE": ("Flip", ("transform.mirror", {"constraint_axis": (True, False, False)})),  # Flip U
        "S": ("Auto Seams", _item("UV/Auto Seams")),
        "SW": ("Layout", "allset.uv_layout"),
        "W": ("Unfold", "allset.uv_unfold"),
        "NW": ("3D Cut and Sew UV Tool", "allset.cut_sew_tool_set"),  # step 79
    },
    items=list(_UV_TAIL),
    options={"3D Grab UV Tool", "Optimize", "Flip", "Auto Seams", "Layout", "Unfold", "3D Cut and Sew UV Tool"})

MENUS = {m.name: m for m in (RMB_MESH, RMB_CURVE, RMB_LATTICE, RMB_EMPTY, PIVOT_EDIT, SHIFT_OBJECT, SHIFT_VERTEX,
                             SHIFT_EDGE, SHIFT_FACE, SHIFT_DEFAULT, CTRL_CONVERT,
                             OPT_MOVE, OPT_ROTATE, OPT_SCALE, OPT_SELECT, OPT_QUAD_DRAW, SELECT_ALL,
                             HB_NORTH, HB_SOUTH, HB_EAST, HB_WEST, HB_CENTER,
                             UV_EDITOR_RMB, SHIFT_UV, SHIFT_UV_SHELL, KEY_TANGENT,
                             SELECT_COMPONENT, SELECT_POLYGON)}
# The kit's own menus. MENUS is what opens: user_menus.apply (Marking Menu Editor) puts rebuilt copies of the
# menus the user changed and the user's own menus into it; these factory objects are never changed.
FACTORY = dict(MENUS)

# Active tool -> its options marking menu (Maya's tool hold menus).
TOOL_OPTIONS = {"builtin.move": "OPT_MOVE", "builtin.rotate": "OPT_ROTATE",
                "builtin.scale": "OPT_SCALE", "builtin.transform": "OPT_MOVE",
                "allset.quad_draw_tool": "OPT_QUAD_DRAW"}
SELECT_OPTIONS = "OPT_SELECT"


def walk(sub, path):
    """Yield (path, label, action) for every entry, depth first; Sub actions included."""
    for pos in RADIALS:
        if pos in sub.radial:
            label, action = sub.radial[pos]
            yield f"{path}/{pos}", label, action
            if isinstance(action, Sub):
                yield from walk(action, f"{path}/{pos}")
    for i, entry in enumerate(sub.items):
        if entry == DIVIDER:
            continue
        label, action = entry
        yield f"{path}/{i}", label, action
        if isinstance(action, Sub):
            yield from walk(action, f"{path}/{i}")


def label_walk(sub, path):
    """Like ``walk`` with label paths ("SHIFT_FACE/Face Normals/Reverse Propagate"): the keys of
    ``ui/notices.MARKING`` (step 136)."""
    for pos in RADIALS:
        if pos in sub.radial:
            label, action = sub.radial[pos]
            yield f"{path}/{label}", label, action
            if isinstance(action, Sub):
                yield from label_walk(action, f"{path}/{label}")
    for entry in sub.items:
        if entry == DIVIDER:
            continue
        label, action = entry
        yield f"{path}/{label}", label, action
        if isinstance(action, Sub):
            yield from label_walk(action, f"{path}/{label}")


def is_greyed(action):
    """Drawn greyed whatever the context: no action, or an empty submenu."""
    return action is None or is_unavailable(action)


def greyed_entries():
    """[(label path, label)] of every greyed entry of every menu."""
    return [(p, label) for name, menu in MENUS.items() for p, label, a in label_walk(menu, name) if is_greyed(a)]


def sub_label_path(menu, sub):
    """Label path of submenu ``sub`` inside ``menu`` ("" for the menu itself), or None."""
    if sub is menu:
        return ""
    for path, _label, action in label_walk(menu, ""):
        if action is sub:
            return path.lstrip("/")
    return None
