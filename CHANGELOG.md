## v0.02.00

### Map Marker
- In-game map destination marker now shows on MapGenie in real time (overlay and Chrome extension)
- Click the marker pin to open a popup with a Teleport button
- Automated CI/CD build via GitHub Actions on every release tag

### Known issues
- The marker pin stays visible after removing the destination marker in-game. The memory hook reads the last known position and does not yet detect when the marker is cleared. Working on a fix.

---

## v0.01.00 — Initial Release

### Core
- Real-time player position overlay on [MapGenie](https://mapgenie.io/crimson-desert) via memory reading (`pymem` + AOB scan)
- Single executable (`CD_Companion.exe`) — no console, auto UAC elevation
- WebSocket server on `ws://0.0.0.0:7891` broadcasting position at 60 Hz

### Overlay
- Always-on-top PyQt5 frameless window with resizable edges
- Follow player mode with **Shift** to pause temporarily
- Circular/oval window mode
- Transparency slider (0–90%)
- Map rotation by player heading or camera yaw
- Global hotkey `Ctrl+Shift+M` to show/hide

### Teleport
- Click anywhere on the map to teleport
- Teleport to in-game map marker (`F5`)
- Abort / return to pre-teleport position (`Shift+F5`)
- Personal waypoints (save, rename, delete, filter)
- `HEIGHT_BOOST +10` + 10s invulnerability after each teleport

### Direction arrow
- Three modes: `Auto` / `Entity vector` (works while standing) / `Position delta`

### Calibration
- Built-in affine calibration for Pywel and Abyss realms
- Custom calibration via reference points (3 or more points = full affine transform)

### Location sync
- Marks/unmarks on MapGenie propagate in real-time to all connected clients
