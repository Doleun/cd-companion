## v0.07.00

### Added
- Waypoints panel: open/close via keyboard hotkey (default Shift+Y) and configurable controller combo (default DPad Down+A).
- Waypoints panel: controller navigation with D-pad Up/Down, A to teleport, Y to delete, B to close.
- Nearby popup: controller combo now configurable in Settings (default LB+Down).
- Nearby popup: "Stay in list" toggle that keeps focus in the current found/unfound list after marking a location, instead of following the item to the other list.
- Settings dialog reorganized into tabbed layout (Map, Window, Teleport, Nearby, Waypoints, Direction, Performance).
- All hotkey and controller combo inputs now have a Clear button to disable the binding.

### Fixed
- Closing the waypoints popup with controller B no longer triggers the B action in Crimson Desert (delayed focus return to game window).
- Keyboard navigation improvements in the waypoints popup.

## v0.06.02

### Fixed
- Closing the nearby popup while the overlay is hidden no longer exits the entire application.

## v0.06.01

### Added
- Freedom Flyer compatibility: teleport now works when using both mods together.
- Optional shared entity base: player detection can use Freedom Flyer's shared memory, reducing hook conflicts. Toggle in Settings → Teleport.

## v0.06.00

### Added
- Nearby popup now pans the map to the selected location while navigating, highlights it with a red Mapbox layer, and returns to the player position when the popup closes.
- Nearby popup can now respect the category visibility currently selected on the map, with a Settings toggle to show all categories instead.
- Overlay Settings now includes a map icon size slider for adjusting location marker scale.
- Nearby popup items can be filtered by found/unfound status via gamepad Back button, with found items sorted to the bottom. D-pad left/right navigates pages.
- Title bar now supports double-click to maximize/restore the overlay window and includes a maximize button (square mode only).

### Fixed
- Improved overlay map smoothness when following the player — camera rotation and position updates now match the Chrome extension responsiveness.
- Nearby popup controller navigation now only works while the popup window is the active foreground window, preventing D-pad/A/B from changing the popup while playing with the game focused.
- Nearby scan radius slider now supports a smaller minimum radius.
- Nearby scan radius is displayed as a simple 1-8 value in Settings while still saving the internal 0.001-0.008 map radius.

### Removed
- Calibration UI (button and click-to-add) disabled from the overlay panel.

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
