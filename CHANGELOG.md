## v0.03.07

### Fixed
- Hook chaining with OpenFlight (and similar ASI mods): companion now detects when another mod already hooked the physics delta point and chains through it, instead of overwriting it. Both teleport and flight work simultaneously.

---

## v0.03.06

### Fixed
- Off-screen map marker indicator now hugs the overlay border
- Oval window mode: indicator follows elliptical boundary instead of rectangular
- Round window now forces 1:1 aspect ratio on load even if config has different width/height
- Window size is now saved to config after resizing, not only on close
