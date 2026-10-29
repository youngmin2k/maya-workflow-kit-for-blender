# Quad Draw

Activate **Mesh Tools > Quad Draw**, the shelf button or **Ctrl+Shift+Q**. The Modeling Toolkit opens with
**Quad Draw Options** below Tools. The Tool Settings dock shares the same settings.

- Auto-weld uses a pixel tolerance and is disabled while Soft Selection is enabled.
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

The display tint is a cached GPU overlay, not a material assignment. Native retopology depth bias scales temporarily
with edited edge length so coarse quads remain visible on curved references. The previous overlay settings return
when the tool is left. This display bias is separate from Surface Offset and never moves vertices.

Mesh references are supported; Maya's NURBS/GPU-cache references are not. The options marking-menu gesture and
Tab+MMB strip resizing remain unavailable and are labelled in the shortcut list.

References: Autodesk Maya 2025 [Quad Draw Tool Options](https://help.autodesk.com/cloudhelp/2025/ENU/Maya-Modeling/files/GUID-35D650EE-C840-4E4B-8E5C-DC5FFE4DA53A.htm),
[Set a reference mesh](https://help.autodesk.com/cloudhelp/2024/ENU/Maya-Modeling/files/GUID-8917D2ED-8927-4FFF-8CA6-164906F6585F.htm).
