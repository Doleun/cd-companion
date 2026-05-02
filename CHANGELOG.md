## v0.04.00

### Added
- Nearby Locations popup (Shift+N): lists MapGenie locations near the player's current position. Navigate with arrow keys, press Enter to toggle found/unfound, Esc to close. Broadcasts the toggle to all connected clients in real time.
- Popup opens beside the overlay when there is screen space; falls back to the nearest screen corner. Position is remembered within the session.

### Fixed
- Hook chaining with OpenFlight (and similar ASI mods): companion now detects when another mod already hooked the physics delta point and chains through it instead of overwriting it. Both teleport and flight work simultaneously.
