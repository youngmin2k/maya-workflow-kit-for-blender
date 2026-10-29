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
  The default cyan tint is chosen to match the supplied Maya reference; Autodesk does not document a fixed RGB value.

Only Make Live meshes are reference surfaces. Without one, dots use the construction plane, even if other objects
are visible. Component drags preserve the initial screen offset; leaving a live surface keeps the last valid position.
Relax, inserted loops and extended points project onto the visible reference first, using nearest-surface projection
when no view ray hits. Surface Offset is a world-space displacement along the reference normal.

To connect two strips in the same retopology mesh, hold Shift over their gap and click the quad preview, or Tab-drag
a boundary edge toward the other strip with Auto-weld enabled. Previews prefer existing boundary edges and reuse
their vertices. Existing faces, inconsistent shared-edge winding, skipped boundary vertices and edges already used
by two faces cannot be covered by a new face. Dots can still be combined with existing boundary vertices.
Snap targets come only from the edited mesh; hidden vertices and points behind the live surface are excluded.

Hover caches retain one mesh/view projection, while each drag owns a spatial target index and local topology
snapshot. These are released on tool exit or drag completion/cancellation. The live reference BVH remains shared.

The display tint is a cached GPU overlay, not a material assignment. Native retopology depth bias scales temporarily
with edited edge length so coarse quads remain visible on curved references. The previous overlay settings return
when the tool is left. This display bias is separate from Surface Offset and never moves vertices.

Mesh references are supported; Maya's NURBS/GPU-cache references are not. The options marking-menu gesture and
Tab+MMB strip resizing remain unavailable and are labelled in the shortcut list.

References: Autodesk Maya 2025 [Quad Draw Tool Options](https://help.autodesk.com/cloudhelp/2025/ENU/Maya-Modeling/files/GUID-35D650EE-C840-4E4B-8E5C-DC5FFE4DA53A.htm),
[Set a reference mesh](https://help.autodesk.com/cloudhelp/2024/ENU/Maya-Modeling/files/GUID-8917D2ED-8927-4FFF-8CA6-164906F6585F.htm).
