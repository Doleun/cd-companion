## v0.03.03

### Fixes
- **Map marker recovery after companion restart**: the game module has multiple occurrences of the map marker AOB pattern. When the companion closed without cleanup, the JMP patch remained at the correct address and a subsequent AOB scan would find a different (wrong) occurrence, silently hooking the wrong code path. The fix prioritizes the cached RVA over a fresh scan, ensuring the correct hook address is always used
- **Map marker and camera heading recovery after unclean shutdown**: both hooks now accept a stale JMP at the cached address as valid, recovering without a game restart
