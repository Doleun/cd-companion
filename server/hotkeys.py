import ctypes
import ctypes.wintypes
import json
import os

from server.memory.constants import SAVE_DIR

HOTKEY_SETTINGS_FILE = os.path.join(SAVE_DIR, "cd_hotkeys.json")

DEFAULT_HOTKEYS = {
    "teleport_marker": {"vk": 0x74, "mod": 0,    "enabled": True},   # F5
    "abort":           {"vk": 0x74, "mod": 0x10,  "enabled": True},   # Shift+F5
    "open_nearby":     {"vk": 0x4E, "mod": 0x10,  "enabled": True},   # Shift+N
}

VK_NAMES = {
    0x70: "F1", 0x71: "F2", 0x72: "F3", 0x73: "F4", 0x74: "F5", 0x75: "F6",
    0x76: "F7", 0x77: "F8", 0x78: "F9", 0x79: "F10", 0x7A: "F11", 0x7B: "F12",
    0x4E: "N",
}
VK_MOD_SHIFT = 0x10
VK_MOD_CTRL  = 0x11
VK_MOD_ALT   = 0x12
MOD_NAMES = {VK_MOD_CTRL: "Ctrl", VK_MOD_ALT: "Alt", VK_MOD_SHIFT: "Shift"}

XINPUT_GAMEPAD_DPAD_UP    = 0x0001
XINPUT_GAMEPAD_DPAD_DOWN  = 0x0002
XINPUT_GAMEPAD_DPAD_LEFT  = 0x0004
XINPUT_GAMEPAD_DPAD_RIGHT = 0x0008
XINPUT_GAMEPAD_BACK       = 0x0020
XINPUT_GAMEPAD_LEFT_SHOULDER = 0x0100
XINPUT_GAMEPAD_A          = 0x1000
XINPUT_GAMEPAD_B          = 0x2000
XINPUT_OPEN_NEARBY_MASK   = XINPUT_GAMEPAD_LEFT_SHOULDER | XINPUT_GAMEPAD_DPAD_DOWN
XINPUT_NEARBY_INPUTS = {
    XINPUT_GAMEPAD_DPAD_UP:    "up",
    XINPUT_GAMEPAD_DPAD_DOWN:  "down",
    XINPUT_GAMEPAD_DPAD_LEFT:  "left",
    XINPUT_GAMEPAD_DPAD_RIGHT: "right",
    XINPUT_GAMEPAD_BACK:       "filter",
    XINPUT_GAMEPAD_A:          "toggle",
    XINPUT_GAMEPAD_B:          "close",
}


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons",      ctypes.wintypes.WORD),
        ("bLeftTrigger",  ctypes.wintypes.BYTE),
        ("bRightTrigger", ctypes.wintypes.BYTE),
        ("sThumbLX",      ctypes.wintypes.SHORT),
        ("sThumbLY",      ctypes.wintypes.SHORT),
        ("sThumbRX",      ctypes.wintypes.SHORT),
        ("sThumbRY",      ctypes.wintypes.SHORT),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.wintypes.DWORD),
        ("Gamepad",        XINPUT_GAMEPAD),
    ]


def _load_xinput_get_state():
    for dll_name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
        try:
            dll = ctypes.WinDLL(dll_name)
            fn = dll.XInputGetState
            fn.argtypes = [ctypes.wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
            fn.restype = ctypes.wintypes.DWORD
            return fn
        except Exception:
            continue
    return None


def _controller_buttons(get_state):
    if not get_state:
        return 0
    state = XINPUT_STATE()
    buttons = 0
    for idx in range(4):
        if get_state(idx, ctypes.byref(state)) == 0:
            buttons |= state.Gamepad.wButtons
    return buttons


def _load_hotkey_settings():
    try:
        with open(HOTKEY_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        result = {}
        for hk_id, default in DEFAULT_HOTKEYS.items():
            saved = data.get(hk_id)
            if saved and "vk" in saved:
                result[hk_id] = {
                    "vk": saved["vk"],
                    "mod": saved.get("mod", 0),
                    "enabled": saved.get("enabled", True),
                }
            else:
                result[hk_id] = dict(default)
        return result
    except Exception:
        return {k: dict(v) for k, v in DEFAULT_HOTKEYS.items()}


def _save_hotkey_settings(hotkeys):
    os.makedirs(SAVE_DIR, exist_ok=True)
    with open(HOTKEY_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(hotkeys, f, indent=2)


def _nearby_controls_enabled():
    return os.environ.get('CD_NEARBY_CONTROLS_ENABLED', '0') == '1'
