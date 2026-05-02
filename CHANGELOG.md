## v0.05.02

### Added
- Nearby popup now pans the map to the selected location while navigating, highlights it with a red Mapbox layer, and returns to the player position when the popup closes.
- Nearby popup can now respect the category visibility currently selected on the map, with a Settings toggle to show all categories instead.
- Overlay Settings now includes a map icon size slider for adjusting location marker scale.

### Fixed
- Nearby popup controller navigation now only works while the popup window is the active foreground window, preventing D-pad/A/B from changing the popup while playing with the game focused.
- Nearby scan radius slider now supports a smaller minimum radius.
- Nearby scan radius is displayed as a simple 1-8 value in Settings while still saving the internal 0.001-0.008 map radius.

## v0.05.00

### Added
- Nearby popup: category icon and name shown per location, sourced from MapGenie data.
- Nearby popup: found/unfound badge overlaid on category icon (bottom-right corner).
- Nearby popup: locations sorted by distance, with distance value displayed per item.
- Nearby popup: details panel showing MapGenie image, title, category, description, and found state for the selected location.
- Description links to other MapGenie locations now pan all connected clients to that location instead of opening a browser page.
- Scan radius circle on the MapGenie map showing the nearby scan area (visible when nearby controls are enabled).
- Nearby scan radius configurable in Settings (0.003–0.008, default 0.005).
- Nearby popup hotkey configurable in Settings (saved to cd_hotkeys.json, restart required).

### Fixed
- Nearby popup no longer opens when pressing the assigned hotkey while editing it in Settings.

### Improved
- Nearby popup list no longer resets scroll on each refresh; skips render entirely when nothing changed.
- Nearby popup refresh is lighter while open: location details are cached, the details panel only re-renders when selection/found state changes, and the radius circle skips unchanged updates.
