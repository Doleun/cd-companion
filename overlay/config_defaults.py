"""Constantes de configuração compartilhadas entre overlay_app.py e overlay_widgets.py."""

SETTING_DEFAULTS = {
    'restoreLastPosition':  True,
    'autoHideFound':        True,
    'autoHideLeftSidebar':  False,
    'autoHideRightSidebar': False,
    'transparency':         0,      # 0–90 %
    'roundWindow':          False,
    'followGameWindow':     False,
    'headingSource':        'auto', # 'auto'|'entity'|'delta'
    'rotateWithPlayer':     False,
    'rotateWithCamera':     False,
    'centerTeleportY':       1000.0,
    'disableGpuVsync':       False,
    'teleportEnabled':       True,
    'nearbyControlsEnabled': False,
    'nearbyThreshold':       0.005,
    'nearbyRespectMapVisibility': True,
    'mapIconScale':          1.0,
}
