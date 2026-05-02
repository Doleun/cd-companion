## v0.05.00

### Added
- Nearby popup: category icon and name shown per location, sourced from MapGenie data.
- Nearby popup: found/unfound badge overlaid on category icon (bottom-right corner).
- Nearby popup: locations sorted by distance, with distance value displayed per item.
- Scan radius circle on the MapGenie map showing the nearby scan area (visible when nearby controls are enabled).
- Nearby scan radius configurable in Settings (0.003–0.008, default 0.005).
- Nearby popup hotkey configurable in Settings (saved to cd_hotkeys.json, restart required).

### Fixed
- Nearby popup no longer opens when pressing the assigned hotkey while editing it in Settings.

### Improved
- Nearby popup list no longer resets scroll on each refresh; skips render entirely when nothing changed.
