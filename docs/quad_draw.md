# Quad Draw

Activate **Mesh Tools > Quad Draw**, the shelf button or **Ctrl+Shift+Q**. The Modeling Toolkit opens with
**Quad Draw Options** below Tools. The Tool Settings dock shares the same settings.

- Auto-weld uses an actual screen-pixel tolerance and is disabled while Soft Selection is enabled. A dragged point
  snaps to an eligible retopology vertex with a green target marker before release. Dragging an edge can snap both
  endpoints together. Release performs the weld; Escape restores the original positions without changing topology.
  A small release margin keeps an acquired target from flickering as the mouse jitters near the tolerance boundary.
- Relax offers Auto-Lock, Interior Vertices, Border Vertices and All Vertices. Auto-Lock chooses the nearest
  vertex type at the start of a stroke and keeps it until release.
- Extend offers Edge, Loop (the boundary chain up to a corner/pole), and Border (the connected border).
- Quad Strip Width sets the width in pixels. Clear Dots removes unfinished dots; Reset Settings restores defaults.
- Live Constraint Options controls the wire overlay/color, mesh tint, opacity, surface offset and backface snapping.
  The default base tint matches the supplied Maya picker swatch, display sRGB `#008BD4`, stored as linear RGB
  `(0, 0.258183, 0.658375)`. The reference picker uses ACEScg; its HSV numbers are not Blender's RGB values.
  Opacity, the surface underneath and hover highlighting change the final blended face color. Existing custom
  scene colors remain available; Autodesk does not document a universal fixed RGB value.

Only Make Live meshes are reference surfaces. Without one, dots use the construction plane, even if other objects
are visible. Component drags preserve the initial screen offset; leaving a live surface keeps the last valid position.
Relax, inserted loops and extended points project onto the visible reference first, using nearest-surface projection
when no view ray hits. Surface Offset is a world-space displacement along the reference normal.

To connect two strips in the same retopology mesh, hold Shift over their gap and click the quad preview, or Tab-drag
a boundary edge toward the other strip with Auto-weld enabled. Previews prefer existing boundary edges and reuse
their vertices. Nearby border paths, corner quality, aspect ratio and continuation of adjacent edge flow guide
ambiguous proposals. A small preference for the previous valid proposal reduces flicker. Three-dimensional checks
reject folded triangles and proposals opposing adjacent face normals. Existing faces, inconsistent shared-edge winding,
skipped boundary vertices and edges already used by two faces cannot be covered by a new face. Dots can still be combined with existing boundary vertices.
Snap targets come only from the edited mesh; hidden vertices and points behind the live surface are excluded.

Hover caches retain one mesh/view projection, while each drag owns a spatial target index and local topology
snapshot. These are released on tool exit or drag completion/cancellation. The live reference BVH remains shared.

The display tint and antialiased pixel-width strokes use cached GPU batches. Temporary display clearance follows
nearby faces, so an unrelated long edge does not raise the entire mesh. Materials and theme are preserved.
During Quad Draw the native cage offset is limited to 0.01, while the compositor keeps the original saved offset.
This prevents a large offset retained by an older scene from clipping the custom strokes; the native offset returns
on tool exit. A workspace reopened with Quad Draw already active initializes the same display and cleanup state.
Depth-tested strokes are composed after native edit overlays to cover intermittent native cyan wires
on curved references; the Maya Tool Box column is excluded. Orbit/zoom update uniforms without rebuilding geometry.
Display clearance is separate from Surface Offset and never moves vertices.

Preselection uses a small red ring for a vertex, a thin red stroke for an edge, and a red outline with a lighter face
interior. Hover and press share a picker; vertex zones shrink around short projected edges to keep small faces and
edge midpoints accessible. Components behind the live reference are excluded. The hover marker clears while dragging.

Fill proposals are bounded local heuristics. Deep folds, disconnected sheets and ambiguous layouts can require
another view or explicit point placement. Autodesk publishes tool behavior and context options; its internal
inference algorithm is not publicly specified.

Mesh references are supported; Maya's NURBS/GPU-cache references are not. The options marking-menu gesture and
Tab+MMB strip resizing remain unavailable and are labelled in the shortcut list.

References: Autodesk Maya 2025 [Quad Draw Tool Options](https://help.autodesk.com/cloudhelp/2025/ENU/Maya-Modeling/files/GUID-35D650EE-C840-4E4B-8E5C-DC5FFE4DA53A.htm),
[Set a reference mesh](https://help.autodesk.com/cloudhelp/2024/ENU/Maya-Modeling/files/GUID-8917D2ED-8927-4FFF-8CA6-164906F6585F.htm).

Display references: [Maya preselection highlighting](https://help.autodesk.com/cloudhelp/2025/ENU/Maya-Customizing/files/GUID-8C8BA1F4-59EE-4A02-BFE7-9193C0D6F5BE.htm),
[viewport antialiasing](https://help.autodesk.com/cloudhelp/2025/ENU/Maya-Basics/files/GUID-9BBB6035-2A02-41BB-AF2D-99D9BEE580F1.htm),
and [Quad Draw context options](https://help.autodesk.com/cloudhelp/2022/ENU/Maya-Tech-Docs/PyMel/generated/functions/pymel.core.context/pymel.core.context.nexQuadDrawCtx.html).
[RetopoFlow](https://github.com/CGCookie/retopoflow) was studied for local topology, visibility and screen-space
interaction; the implementation here is independently written.
