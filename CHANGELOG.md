## v0.03.01

### Fixes
- **Camera heading recovery after unclean shutdown**: closing the overlay without a clean shutdown left the camera hook JMP patch installed in game memory. On re-open, the AOB scan failed to find the original bytes and the cache validation rejected the address as stale, resulting in "Camera heading AOB not found" until the game was restarted. The companion now detects that its own hook is still installed and recovers the address without requiring a game restart
