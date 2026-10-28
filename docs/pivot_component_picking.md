# Custom pivot editing

With a mesh selected in Object Mode or mesh Edit Mode, tap **D** or **Insert**
to enter custom pivot editing. Tap either key again to finish. Holding **D**
and using the mouse keeps the existing temporary workflow: releasing **D** exits.
A tap is an unused press shorter than 0.3 seconds.

While editing, click a visible vertex, edge or face to place and align the pivot.
Vertices use their exact position, edges their midpoint, and faces their median
centre. Vertex and edge hits take priority near their screen positions.
The manipulator handles retain priority on their own pixels.

- **Click:** position and orientation, respecting Snap Pivot Position/Orientation.
- **Shift-click:** position only.
- **Ctrl-click:** orientation only.
- **Ctrl+Shift-click:** aim the active manipulator axis at the component.

Mesh Edit Mode temporarily enables vertex, edge and face picking together and
restores the original selection mode on exit. Picking leaves the selected
components and world geometry intact. The existing cursor tool can also drag the component pivot.
The resulting custom pivot remains available for transforms.
Object Mode preserves transform channels, world geometry and child positions.

The component frame uses X along an incident edge and Z along the surface normal.
At vertices or faces with several incident edges, the longest world-space edge
supplies X. This gives a stable right-handed frame under nonuniform object scale.

This follows Autodesk Maya 2026's documented D/Insert workflow and modifier clicks:

- [Activate custom pivot editing](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Basics/files/GUID-6BCE41D8-07CB-4A99-99CD-1D3986896157.htm)
- [Change the pivot point](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Basics/files/GUID-150B390E-840B-4FE3-B8E9-8DEBCE7CEC97.htm)
