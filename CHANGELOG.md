## v0.03.00

### Features
- **Optional teleport**: new "Enable teleport" setting allows disabling teleport entirely. When off, the physics delta hook (hook_e) and invulnerability hook (hook_c) are not injected into the game, avoiding conflicts with other mods
- Teleport UI elements (waypoints button, center teleport button, Go to Marker, Abort, map marker teleport popup) hide automatically when teleport is disabled
- UI reacts immediately on settings save; hooks require restarting overlay and game
- Browser extensions (Chrome/Firefox) react to `engine_status.teleportEnabled` broadcast and hide teleport controls accordingly

### Protocol
- `engine_status` message now includes `teleportEnabled` boolean field
