## v0.03.04

Fixed an issue where the map destination marker (the in-game navigation marker) would stop showing up after closing and reopening the companion without restarting the game. The fix also covers cases where the camera rotation stops working after an unclean shutdown. Both should now recover automatically without requiring a full game restart.

If you had this issue before and it is still happening after updating, delete the hook cache file at %LOCALAPPDATA%\CD_Teleport\cd_hook_offsets.json and restart the game and companion once to rebuild it.
