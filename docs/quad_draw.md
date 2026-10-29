# Quad Draw

Activate **Mesh Tools > Quad Draw**, the shelf button or **Ctrl+Shift+Q**. The Modeling Toolkit opens with
**Quad Draw Options** below Tools. The Tool Settings dock shares the same settings.

- Auto-weld uses an actual screen-pixel tolerance and is disabled while Soft Selection is enabled. A dragged point
  snaps to an eligible retopology vertex with a green target marker before release. Dragging an edge can snap both
  endpoints together. Release performs the weld; Escape restores the original positions without changing topology.
  A small release margin keeps an acquired target from flickering as the mouse jitters near the tolerance boundary.
- Relax offers Auto-Lock, Interior Vertices, Border Vertices and All Vertices. Auto-Lock chooses the nearest
  vertex type at the start of a stroke and keeps it until release.
- Ctrl+Shift+click an interior edge dissolves its quad loop; on a boundary it removes the loop's adjacent
  face strip. Ctrl+Shift hover previews the complete loop in red. Hidden edges, corners, poles and non-quad
  junctions stop traversal; non-manifold edge targets are refused. Ctrl+Shift+MMB tweaks the same loop,
  including a straight boundary chain. Face deletion and loose-dot deletion remain available.
- Shift+LMB paints relaxation. Border / Auto-Lock border strokes stay on the continuous visible boundary
  where the stroke began, so a nearby disconnected border is not moved by the same stroke.
- With Soft Selection enabled (B), Relax uses its radius and Volume / Surface / projected mode. Hover shows
  a smooth red-to-yellow influence preview. Relax applies equal smoothing strength within the influence
  area; the falloff curve affects the preview rather than weighting the smoothing operation.
- Shift+MMB holds the component / Soft Selection area captured at press. Drag right to increase relaxation,
  left to reduce it; returning to the press position restores the original geometry. This reverses the
  current stroke, not older committed strokes. Without Soft Selection, it holds the highlighted component.
  Escape restores both brush and MMB strokes, including when symmetry is off. One Undo/Redo covers the
  complete accepted stroke. Points continue to project onto the live surface.
- Extend offers Edge, Loop (the boundary chain up to a corner/pole), and Border (the connected border).
- Quad Strip Width sets the width in pixels. Clear Dots removes unfinished dots; Reset Settings restores defaults.
- Hold Tab and middle-drag outside the retopo mesh to resize strips; Escape restores the previous width.
  Tab+MMB over a border edge still extends its loop. Ctrl+Shift+RMB opens the Quad Draw options pie menu;
  its Auto-weld, Extend, Relax and width controls share the Modeling Toolkit settings.
- Live Constraint Options controls the wire overlay/color, mesh tint, opacity, surface offset and backface snapping.
  The default base tint is display sRGB `#01ACFF`, stored as linear RGB
  `(0.000303527, 0.412543, 1)`. Display swatches and linear color values use different encodings.
  Opacity, the surface underneath and hover highlighting change the final blended face color. Existing custom
  scene colors remain available; Autodesk does not document a universal fixed RGB value.

Only Make Live meshes are reference surfaces. Without one, dots use the construction plane, even if other objects
are visible. Component drags preserve the initial screen offset; leaving a live surface keeps the last valid position.
Relax, inserted loops and extended points project onto the visible reference first, using nearest-surface projection
when no view ray hits. Surface Offset displaces points along the reference normal using the scene display length
unit, consistent with the other Maya-style length fields. For example, 0.10 in a centimetre scene means 0.10 cm,
including when the scene uses a different unit scale. Visibility and Auto-weld use the same converted distance.
Reprojection starts from the surface foot of an offset point; drags cache these anchors until release/cancel so
an already offset point does not shift again when grabbed or projected repeatedly.

To connect two strips in the same retopology mesh, hold Shift over their gap and click the quad preview, or Tab-drag
a boundary edge toward the other strip with Auto-weld enabled. Previews prefer existing boundary edges and reuse
their vertices. Nearby border paths, corner quality, aspect ratio and continuation of adjacent edge flow guide
ambiguous proposals. A small preference for the previous valid proposal reduces flicker. Three-dimensional checks
reject folded triangles and proposals opposing adjacent face normals. Existing faces, inconsistent shared-edge winding,
skipped boundary vertices and edges already used by two faces cannot be covered by a new face. Dots can still be combined with existing boundary vertices.
Snap targets come only from the edited mesh; hidden vertices and points behind the live surface are excluded.

Fill ranking combines local cursor distance, corner shape, adjacent edge flow and shared border connections.
A distant three-edge proposal cannot automatically override a small dot-to-border quad, as can happen at eyelids.
Point queries use a cached spatial index; candidate searches and border traversal stay bounded. Preview and click
use the same proposal. Invalid fills report that no valid local face exists rather than silently adding dots.

Quad Draw follows the Status Line symmetry setting for its own mesh edits, including dots, fill, tweak, relax,
loop cuts, delete, extension and weld. Object X/Y/Z reflects about the target object's local origin; World X/Y/Z
uses the actual world plane even when the target is translated or rotated. Existing paired vertices are reused,
new faces reverse winding, and welding opposite dots creates one vertex on the seam. Changing symmetry does not
automatically copy geometry that was already drawn on one side. Escape and Undo restore both sides of a stroke.
With Object/World symmetry and Auto-weld enabled, dragging border points, an edge, or a Tab extension near the symmetry plane
captures the plane using the same pixel tolerance as Auto-weld. Both sides meet in the preview; release welds
their counterparts into shared seam vertices. Moving counterparts are excluded from the static target list,
so the preview cannot jump to their old positions. The target releases outside a small hysteresis margin.
Escape restores both sides. Auto-weld off or Soft Selection disables plane capture. A depth-distance cap
prevents a side view from pulling distant components through the live object.
Strip previews project onto the live surface and use the same plane capture and positions as the committed strip.
Extension toward a source edge's own mirror prefers the nearby center plane over that mirror's old position;
other stationary vertex targets retain precedence. Duplicated extension endpoints exclude the source anchors
from weld targets, so a short drag cannot collapse the new quad back into its source edge.
A Tab click without a drag creates no geometry.

Ctrl+click inserts a loop at the hovered edge position; Ctrl+MMB inserts it at the midpoint. With symmetry,
new points are paired by their source edges and cut factors before projection onto the live reference.
A loop that already crosses both halves is cut once, with shared seam vertices. Distinct mirrored paths
can make two cuts in one face; crossing paths reuse one intersection. World/Object mode projects the
clicked side and reflects its counterpart, preserving symmetry even when the reference is slightly
asymmetric. A cut needs matching existing edges/faces on the opposite side; unmatched or hidden topology
reports a warning and cancels before editing. Failed transactions restore the original mesh.

For Topology symmetry, use **Pick Seam** in Quad Draw Options, then click a manifold edge between matching halves.
An active selected seam edge can also be bound when entering Quad Draw. Stable vertex identities preserve the binding
across index changes, tool exit and file saving. The seam is yellow and a matched hovered component is green;
the primary preselection remains red. **Partial** is enabled by default: propagation stops at unmatched branches,
and operations outside the matched region report a warning. Turning Partial off requires the traversed region to match.
Editing a seam edge disables topology symmetry while retaining the actual edit; Undo/Redo restores this binding/state.
Seam vertices follow their original seam polyline, including on posed meshes away from a geometric axis.
Without an explicit binding, the active edge or an unambiguous local-axis seam can provide initial correspondence.
A posed live reference can map new dots through corresponding evaluated triangles. A reference without a
valid seam correspondence, or a disconnected target without a usable pairing, reports a warning and cancels the
unsupported operation. It does not silently substitute geometric symmetry. Establish the seam on matching topology
before using this mode; Object/World symmetry is simpler for new, geometrically symmetric retopology. New-point
reference correspondence currently requires a local-axis seam on the evaluated live reference; Pick Seam binds
the retopology target. Topology mode previews existing paired components; a mirrored new-face preview is currently
available for Object/World modes only.

Hover caches retain one mesh/view projection, while each drag owns a spatial target index and local topology
snapshot. These are released on tool exit or drag completion/cancellation. The live reference BVH remains shared.
Coordinate-only drags retain edge indices and display triangulation. They update changed world coordinates and
refresh the selection BVH lazily when a pick needs it. Topology operations, transforms, Undo and file loading
invalidate this path. Symmetry coordinate strokes find counterparts lazily; full topology snapshots are deferred
until an operation creates, deletes or welds components.
Large edited meshes copy coordinates/connectivity through bulk mesh arrays; temporary mesh IDs are immediately
released. Fill candidates use grouped polygon arrays instead of Python objects for every interior face.
Additive symmetry edits record detailed rings only around touched components and retain a native BMesh rollback
copy. Cut/delete use a conservative full snapshot; their cost can still grow with total mesh size.
Loop traversal is cached per geometry revision and target edge; hover, delete and loop tweak share its topology
rules. Relax uses numeric local one-ring kernels and vectorized brush queries rather than projecting every
vertex in Python per event. A reversible MMB stroke retains at most 17 local smoothing checkpoints, released
on completion/cancel; tool exit, Undo and file changes clear influence and loop display caches.

The display tint and antialiased pixel-width strokes use cached GPU batches. Temporary display clearance follows
nearby faces, so an unrelated long edge does not raise the entire mesh. Materials and theme are preserved.
During Quad Draw the native cage depth stays unshifted, while the compositor keeps the original saved offset.
This prevents the native depth prepass from clipping the custom strokes, including on centimetre-scale meshes
where even the normal 0.01 offset is large relative to the geometry. The native offset returns
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

Mesh references are supported; Maya's NURBS/GPU-cache references are not.

References: Autodesk Maya 2025 [Quad Draw Tool Options](https://help.autodesk.com/cloudhelp/2025/ENU/Maya-Modeling/files/GUID-35D650EE-C840-4E4B-8E5C-DC5FFE4DA53A.htm),
[Set a reference mesh](https://help.autodesk.com/cloudhelp/2024/ENU/Maya-Modeling/files/GUID-8917D2ED-8927-4FFF-8CA6-164906F6585F.htm).
Interaction references: [Extend](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Modeling/files/GUID-AD1DB294-3E91-4E91-8B8C-993F83634220.htm),
[Strips](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Modeling/files/GUID-868805BC-CED5-4262-826E-203EE914B71E.htm),
[Topological symmetry](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Modeling/files/GUID-EC3CCAFA-DBEB-4733-AF50-467B9EE8B65B.htm),
and [Partial symmetry](https://help.autodesk.com/cloudhelp/2023/ENU/Maya-Modeling/files/GUID-0CE4C064-EA74-4871-971F-08308DC60264.htm).
[Delete components](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Modeling/files/GUID-6A14EBB4-6770-48D9-9F42-EB4200971433.htm),
[Relax vertices](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Modeling/files/GUID-171B1A46-C616-4D92-83D8-C6440A51264C.htm),
and [Quad Draw hotkeys](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Modeling/files/GUID-ED28E6BC-6141-491C-8C1B-2AE6FC813284.htm).

Display references: [Maya preselection highlighting](https://help.autodesk.com/cloudhelp/2025/ENU/Maya-Customizing/files/GUID-8C8BA1F4-59EE-4A02-BFE7-9193C0D6F5BE.htm),
[viewport antialiasing](https://help.autodesk.com/cloudhelp/2025/ENU/Maya-Basics/files/GUID-9BBB6035-2A02-41BB-AF2D-99D9BEE580F1.htm),
and [Quad Draw context options](https://help.autodesk.com/cloudhelp/2022/ENU/Maya-Tech-Docs/PyMel/generated/functions/pymel.core.context/pymel.core.context.nexQuadDrawCtx.html).
[RetopoFlow](https://github.com/CGCookie/retopoflow) was studied for local topology, visibility and screen-space
interaction; the implementation here is independently written.
