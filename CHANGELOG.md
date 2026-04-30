## v0.02.02

### Fixes
- Fix camera rotation setting not applying without overlay restart: `__cdApplyRotationSettings` now pre-extracts values before calling setters, preventing `setRotateWithPlayer` from writing a stale `rotateWithCamera` back to `window.__cdSettings` before `setRotateWithCamera` runs

### Internal
- Replace polling loop with `threading.Event` for server startup synchronization: overlay now wakes up the instant the WebSocket server is ready instead of probing the port every 200ms
- If the server fails to start (e.g. port already in use), the overlay no longer waits the full 10-second timeout before continuing

