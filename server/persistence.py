import json
import os

from server.memory.constants import SAVE_DIR
from shared.coord_math import (
    DEFAULT_CALIBRATIONS,
    is_calibration_usable as _is_calibration_usable,
)

CALIBRATION_FILES = {
    "pywel": os.path.join(SAVE_DIR, "cd_calibration_pywel.json"),
    "abyss": os.path.join(SAVE_DIR, "cd_calibration_abyss.json"),
}
_LEGACY_CALIBRATION_FILE = os.path.join(SAVE_DIR, "cd_calibration.json")

WAYPOINTS_FILE = os.path.join(SAVE_DIR, "cd_overlay_waypoints.json")

_cal_cache: dict = {}


def _load_calibration(realm="pywel"):
    cal_file = CALIBRATION_FILES[realm]
    try:
        with open(cal_file, 'r') as f:
            cal = json.load(f)
            if _is_calibration_usable(cal, realm):
                return cal
    except Exception:
        pass
    if realm == "pywel" and os.path.isfile(_LEGACY_CALIBRATION_FILE):
        try:
            with open(_LEGACY_CALIBRATION_FILE, 'r') as f:
                cal = json.load(f)
                if _is_calibration_usable(cal, realm):
                    return cal
        except Exception:
            pass
    return list(DEFAULT_CALIBRATIONS[realm])


def _save_calibration(realm: str, cal: list):
    os.makedirs(SAVE_DIR, exist_ok=True)
    with open(CALIBRATION_FILES[realm], 'w', encoding='utf-8') as f:
        json.dump(cal, f, indent=2)
    _cal_cache.pop(realm, None)


def _get_cal(realm):
    if realm not in _cal_cache:
        _cal_cache[realm] = _load_calibration(realm)
    return _cal_cache[realm]


def _load_waypoints():
    try:
        with open(WAYPOINTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save_waypoints(waypoints):
    os.makedirs(SAVE_DIR, exist_ok=True)
    with open(WAYPOINTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(waypoints, f, indent=2, ensure_ascii=False)
