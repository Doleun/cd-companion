## v0.02.02

### Internal
- Replace polling loop with `threading.Event` for server startup synchronization: overlay now wakes up the instant the WebSocket server is ready instead of probing the port every 200ms

## v0.02.01

### Fixes
- Translated all remaining Portuguese strings in the overlay UI to English
