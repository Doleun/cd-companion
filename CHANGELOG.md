## v0.04.00

### Added
- Nearby Locations popup: lists MapGenie locations near the player's current position and refreshes while the player moves.
- Optional nearby shortcuts setting. When enabled: Shift+N or LB+A opens the popup; arrows, W/S, or D-pad navigate; Enter, Space, or A toggles found/unfound; Esc or B closes.
- Popup opens beside the overlay when there is screen space; falls back to the nearest screen corner. Position is remembered within the session.

### Fixed
- Hook chaining with OpenFlight (and similar ASI mods): companion now detects when another mod already hooked the physics delta point and chains through it instead of overwriting it. Both teleport and flight work simultaneously.
- Nearby popup toggle sync no longer replays back into the overlay that triggered it.
- Closing the nearby popup with the window close button no longer requires pressing the shortcut twice to reopen.
- Nearby popup now opens directly at its final position and returns focus to Crimson Desert when closed.
