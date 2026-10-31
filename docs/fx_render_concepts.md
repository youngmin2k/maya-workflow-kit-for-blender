# Maya FX and Rendering in Blender

Maya Workflow Kit keeps Blender's own simulation and render engines. It does not rebuild nCloth, nCache, Bifrost
or Arnold: the Maya FX, Rendering and Hypershade menus run Blender's systems from the place a Maya user looks for
them, in Maya units. Every menu item's tooltip names the Blender feature it uses ("Maya: <item> → Blender: …");
items Blender has nothing for are greyed and their tooltip says what to use instead.

## Concepts

| Maya | Blender | Where the kit puts it |
|---|---|---|
| nucleus (gravity, Space Scale, substeps) | Scene gravity, each simulation's quality / substeps | Attribute Editor "nucleus1" tab; the kit scales gravity, stiffness and collision distances so one unit moves like Maya's |
| nCloth | Cloth modifier (Physics properties) | nCloth > Create nCloth / Remove nCloth |
| nCloth rest shape | Cloth > Shape > Rest Shape Key | nCloth > Rest Shape (the selected mesh becomes a shape key used as the rest shape) |
| nCloth per-vertex maps | Cloth vertex groups (Pin, Structural, Bending, Shrinking) | nCloth > Paint Vertex Properties (Input Attract, Stretch, Compression, Bend, Rest Length Scale) open Weight Paint on that group |
| Passive collider (nRigid) | Collision modifier | nCloth > Create Passive Collider |
| nConstraint Transform | Cloth Pin Group + Hook modifier to an empty | nConstraint > Transform Constraint (dynamicConstraint1 empty), Add / Remove / Replace / Select Members |
| nConstraint Disable Collision | Cloth collision vertex group | nConstraint > Disable Collision |
| nParticles emitter | Particle system on a mesh | nParticles > Create Emitter (a one-point mesh), Emit from Object, Fill Object (volume grid) |
| nParticles Create Options | Particle display (dots / circles), fluid particle physics | nParticles > Create Options (applies to new particles) |
| Instancer | Particle Render As Object / Collection | nParticles > Instancer |
| Fields (Air, Drag, Newton, Radial, Turbulence, Uniform, Vortex) | Force Field objects | Fields/Solvers; Gravity is a downward Wind field |
| Volume Curve, Curve Flow | Curve Guide force field | Fields/Solvers > Volume Curve; Effects > Flow > Create / Delete Selected Flow |
| Rigid bodies and solver | Rigid Body World (one per scene) | Create Active / Passive Rigid Body, Create Rigid Body Solver, Rigid Body Solver Attributes (Scene properties) |
| Set Active / Passive Key | Rigid body Animated checkbox, keyed | Fields/Solvers > Set Active Key / Set Passive Key |
| Initial State, Transfer Cache To Input Mesh | Simulated shape written into the mesh / transform | Fields/Solvers > Initial State > Set for Selected / Set for All Dynamic; nCache > Transfer Cache To Input Mesh |
| Clear Initial State, Set From Mesh | Mesh / transform from before the first Initial State; another mesh's shape written into the cloth | Fields/Solvers > Initial State > Clear Initial State / Set From Mesh |
| Rigid body interpenetration | Generic rigid body constraint with no limits and Disable Collisions on, one per pair | Fields/Solvers > Set Rigid Body Interpenetration / Set Rigid Body Collision |
| Fields connected to objects | Effector Collection of the cloth, soft body or particle settings | Fields/Solvers > Assign to Selected |
| Field source object | Force field on the object itself | Fields/Solvers > Use Selected as Source |
| nCache | Point cache Bake / Free Bake (Physics properties) | nCache > Create New Cache / Delete Cache, Create Particle Disk Cache |
| 3D fluid container, emitter | Mantaflow domain, Flow mesh | Fluids > 3D Container, Add/Edit Contents > Emitter, Edit Fluid Resolution |
| Fluid collision, Collide with Effect | Fluid modifier of type Effector | Fluids > Make Collide; Effects > Collide with Effect |
| Fire / Smoke effects | Quick Smoke (Mantaflow) | Effects > Fire / Smoke |
| Ocean | Ocean modifier | Fluids > Ocean |
| Bifrost Graph | Geometry Nodes | Windows > Bifrost Graph Editor |
| nHair | Curves hair object, Sculpt mode | nHair > Create Hair, Paint Hair Follicles, Modify Curves |
| Hypershade | Shader Editor + the kit's Hypershade sidebar | Windows > Rendering Editors > Hypershade |
| Shading group | Material slot | Lighting/Shading > Assign … Material |
| Toon fill shaders | Shader to RGB + constant Color Ramp (EEVEE) | Toon > Assign Fill Shader |
| Toon outline | Line Art (Grease Pencil) | Toon > Assign Outline |
| Camera background colour | World colour (one for every camera) | Toon > Set Camera Background Color |
| Transfer Maps | Cycles Bake, Selected to Active | Lighting/Shading > Transfer Maps |
| Volume Shader, Volume Fog, Light Fog | Principled Volume / Volume Scatter on the material's Volume output | Hypershade > Create > Volumetric Materials |
| Env Fog | Principled Volume on the World's Volume output | Hypershade > Create > Volumetric Materials > Env Fog |
| Hair Physical / Hair Tube Shader | Principled Hair BSDF | Hypershade > Create > Materials |
| USD Preview Surface | Principled BSDF (exported as UsdPreviewSurface) | Hypershade > Create > Materials |
| Render Settings | Render / Output properties | Windows > Rendering Editors > Render Settings |
| IPR | Viewport in Rendered shading | Render > IPR Render Current Frame |
| Render layers / passes | View Layers and their passes | Hypershade > Create > Rendering > Render Layer |
| Stereo camera | Camera + Render > Stereoscopy | Create > Cameras > Stereo Camera, Stereo > Create |
| Light linking | Light linking collections | Lighting/Shading > Light Linking Editor, Make / Break Light Links |

## What stays greyed

Blender has no counterpart for these, so they are greyed with a notice: nCloth texture maps and texture ↔ vertex
map conversion, output-space conversion, tearable / weld / slide nConstraints, merging or editing cache frames,
nHair follicles and hair system display modes, 2D fluid containers, ponds, boats and wakes, Fireworks / Lightning /
Shatter effects, toon line attributes painted as maps, PSD networks, and Maya-only Hypershade nodes (quaternion and
matrix utilities, switch utilities, Maya procedural textures without a Blender texture).
