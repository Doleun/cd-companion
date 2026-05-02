"""
Widgets auxiliares do overlay — extraídos de overlay_app.py.
Contém: SettingsDialog, _PopupWebWindow, _InterceptPage, _LoginPrompt,
         HotkeySignals, TitleBar.
"""

import ctypes
import ctypes.wintypes
import json
import os

from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QCheckBox, QPushButton, QSlider,
                             QMainWindow, QShortcut, QWidget, QKeySequenceEdit)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage

# Importa SETTING_DEFAULTS do módulo de configuração
from overlay.config_defaults import SETTING_DEFAULTS

try:
    from server.main import set_nearby_hotkey_paused as _set_nearby_hotkey_paused
except Exception:
    _set_nearby_hotkey_paused = None

# ── Hotkey helpers ────────────────────────────────────────────────────
_SAVE_DIR = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'CD_Teleport')
_HOTKEY_SETTINGS_FILE = os.path.join(_SAVE_DIR, 'cd_hotkeys.json')
_OPEN_NEARBY_DEFAULT = {'vk': 0x4E, 'mod': 0x10}  # Shift+N

_VK_MAP = {f'F{i}': 0x6F + i for i in range(1, 13)}
_VK_MAP.update({chr(c): c for c in range(0x41, 0x5B)})   # A–Z
_VK_MAP.update({str(d): 0x30 + d for d in range(10)})     # 0–9
_MOD_MAP  = {'Shift': 0x10, 'Ctrl': 0x11, 'Alt': 0x12}
_VK_DISP  = {v: k for k, v in _VK_MAP.items()}
_MOD_DISP = {0x10: 'Shift', 0x11: 'Ctrl', 0x12: 'Alt'}


def _vk_to_seq_str(vk, mod):
    key = _VK_DISP.get(vk, f'VK{vk:#04x}')
    prefix = f'{_MOD_DISP[mod]}+' if mod in _MOD_DISP else ''
    return f'{prefix}{key}'


def _seq_str_to_vk(seq_str):
    """'Shift+N' → (vk, mod). Returns None se inválido."""
    parts = [p.strip() for p in seq_str.split('+')]
    key = parts[-1]
    vk = _VK_MAP.get(key.upper() if len(key) == 1 else key)
    if vk is None:
        return None
    mod = 0
    for m in parts[:-1]:
        mod = _MOD_MAP.get(m, mod)
    return vk, mod


def _find_process_window(exe_name):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    found = [None]
    pid = ctypes.wintypes.DWORD()
    target = exe_name.lower()

    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool,
                                   ctypes.wintypes.HWND,
                                   ctypes.wintypes.LPARAM)

    @EnumProc
    def _cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        hproc = kernel32.OpenProcess(0x1000, False, pid)
        if not hproc:
            return True
        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.wintypes.DWORD(260)
        ok = kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size))
        kernel32.CloseHandle(hproc)
        if ok and buf.value.lower().endswith(target):
            rc = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rc))
            if rc.right - rc.left > 200:
                found[0] = hwnd
                return False
        return True

    user32.EnumWindows(_cb, 0)
    return found[0]


def focus_game_window():
    hwnd = _find_process_window('crimsondesert.exe')
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    fg_hwnd = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
    my_tid = kernel32.GetCurrentThreadId()
    if fg_tid and fg_tid != my_tid:
        user32.AttachThreadInput(fg_tid, my_tid, True)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(fg_tid, my_tid, False)
    else:
        user32.SetForegroundWindow(hwnd)

# ── Estilos ──────────────────────────────────────────────────────────

SETTINGS_STYLE = """
QDialog  { background:#0f0f1a; color:#e2e8f0; }
QLabel   { color:#e2e8f0; font:13px 'Segoe UI'; }
QCheckBox { color:#e2e8f0; font:13px 'Segoe UI'; spacing:8px; }
QCheckBox::indicator { width:18px; height:18px; border-radius:4px;
                       border:1px solid #334155; background:#1a1a2e; }
QCheckBox::indicator:checked { background:#1db954; border-color:#1db954; }
QPushButton { background:#1a1a2e; color:#e2e8f0; border:1px solid #2d2d44;
              border-radius:6px; padding:6px 18px; font:13px 'Segoe UI'; }
QPushButton:hover { background:#252540; }
QPushButton#save { background:#1db954; color:#fff; border:none; }
QPushButton#save:hover { background:#17a84a; }
QSlider::groove:horizontal { height:4px; background:#2d2d44; border-radius:2px; }
QSlider::handle:horizontal { width:14px; height:14px; margin:-5px 0;
    background:#ffd060; border-radius:7px; }
QSlider::sub-page:horizontal { background:#ffd060; border-radius:2px; }
"""


# ── Diálogo de configurações ─────────────────────────────────────────

class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(SETTINGS_STYLE)
        self.setFixedWidth(340)
        self._cfg = cfg
        self._original_opacity = parent.windowOpacity() if parent else 1.0

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(20, 20, 20, 20)

        def section(text):
            lbl = QLabel(text.upper())
            lbl.setStyleSheet('color:#7c8db5; font:10px "Segoe UI"; margin-top:10px; margin-bottom:4px;')
            layout.addWidget(lbl)

        def option(key, label, description):
            cb = QCheckBox(label)
            cb.setChecked(cfg.get(key, SETTING_DEFAULTS[key]))
            cb.setToolTip(description)
            cb.setObjectName(key)
            layout.addWidget(cb)
            self._checkboxes[key] = cb

        self._checkboxes = {}

        section('On map load')
        option('restoreLastPosition',  'Restore last position',
               'Returns to the location and zoom from your last visit')
        option('autoHideFound',        'Hide Found Locations',
               'Automatically disables "Found Locations" when the map opens')
        option('autoHideLeftSidebar',  'Hide Left Panel',
               'Automatically closes the left sidebar')
        option('autoHideRightSidebar', 'Hide Right Panel',
               'Automatically closes the right sidebar')

        section('Window')
        option('roundWindow', 'Circular/oval window',
               'Applies an elliptical mask to the window')
        option('followGameWindow', 'Follow game window',
               'Moves the overlay automatically when the game window is moved')

        # Transparência
        transp_row = QHBoxLayout()
        transp_row.setSpacing(10)
        transp_lbl = QLabel('Transparency')
        transp_val = QLabel(f'{cfg.get("transparency", SETTING_DEFAULTS["transparency"])}%')
        transp_val.setStyleSheet('color:#ffd060; font:12px "Segoe UI"; min-width:32px;')

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 90)
        self._slider.setValue(cfg.get('transparency', SETTING_DEFAULTS['transparency']))
        self._slider.setTickInterval(10)

        def on_slider(v):
            transp_val.setText(f'{v}%')
            if parent:
                parent.setWindowOpacity(1.0 - v / 100)

        self._slider.valueChanged.connect(on_slider)
        transp_row.addWidget(transp_lbl)
        transp_row.addWidget(self._slider, 1)
        transp_row.addWidget(transp_val)
        layout.addLayout(transp_row)

        # Teleport
        section('Teleport')
        option('teleportEnabled', 'Enable teleport (restart overlay and game)',
               'When disabled, the physics delta hook (hook_e) and invulnerability hook (hook_c) '
               'are not injected into the game. Useful to avoid conflicts with other mods.')
        center_y_row = QHBoxLayout()
        center_y_row.setSpacing(10)
        center_y_lbl = QLabel('Center TP Y')
        self._center_y_value = QLabel()
        self._center_y_value.setStyleSheet(
            "color:#ffd060; font:13px 'Consolas'; min-width:48px;")
        self._center_y = QSlider(Qt.Horizontal)
        self._center_y.setRange(-5000, 5000)
        self._center_y.setSingleStep(10)
        self._center_y.setPageStep(100)
        self._center_y.setValue(int(float(cfg.get(
            'centerTeleportY', SETTING_DEFAULTS['centerTeleportY']))))
        self._center_y.setToolTip(
            'Absolute Y used when teleporting to the center of the screen')
        self._center_y_value.setText(str(self._center_y.value()))
        self._center_y.valueChanged.connect(
            lambda value: self._center_y_value.setText(str(value)))
        center_y_row.addWidget(center_y_lbl)
        center_y_row.addWidget(self._center_y, 1)
        center_y_row.addWidget(self._center_y_value)
        layout.addLayout(center_y_row)

        section('Nearby')
        option('nearbyControlsEnabled', 'Enable nearby popup shortcuts',
               'Shift+N or LB+Down opens the nearby popup. In the popup: Up/Down, W/S, or D-pad moves, '
               'Enter, Space, or A toggles found, Esc or B closes.')
        nearby_help = QLabel('LB+Down / Shift+N open. Up/Down, W/S, D-pad navigate. Enter/Space/A toggles. Esc/B closes.')
        nearby_help.setWordWrap(True)
        nearby_help.setStyleSheet('color:#7c8db5; font:11px "Segoe UI"; margin-left:26px;')
        layout.addWidget(nearby_help)

        # Scan radius
        radius_row = QHBoxLayout()
        radius_row.setSpacing(10)
        radius_lbl = QLabel('Scan radius')
        self._nearby_radius_val = QLabel()
        self._nearby_radius_val.setStyleSheet(
            "color:#ffd060; font:13px 'Consolas'; min-width:40px;")
        self._nearby_radius = QSlider(Qt.Horizontal)
        self._nearby_radius.setRange(1, 8)
        self._nearby_radius.setSingleStep(1)
        raw = cfg.get('nearbyThreshold', SETTING_DEFAULTS['nearbyThreshold'])
        self._nearby_radius.setValue(round(float(raw) * 1000))
        self._nearby_radius_val.setText(str(self._nearby_radius.value()))
        self._nearby_radius.valueChanged.connect(
            lambda v: self._nearby_radius_val.setText(str(v)))
        radius_row.addWidget(radius_lbl)
        radius_row.addWidget(self._nearby_radius, 1)
        radius_row.addWidget(self._nearby_radius_val)
        layout.addLayout(radius_row)

        # Hotkey configurável
        hk_row = QHBoxLayout()
        hk_row.setSpacing(10)
        hk_lbl = QLabel('Open hotkey')
        self._nearby_hk = QKeySequenceEdit()
        self._nearby_hk.setFixedHeight(28)
        self._nearby_hk.setToolTip('Restart overlay for the new hotkey to take effect')
        # Impede acúmulo de múltiplos atalhos: ao teclar de novo após finalizar, limpa primeiro
        self._nearby_hk._hk_finalized = False

        def _on_seq_changed(seq):
            first = seq.toString().split(', ')[0]
            if first != seq.toString():
                self._nearby_hk.setKeySequence(QKeySequence(first))
            self._nearby_hk._hk_finalized = True

        def _hk_key_press(e):
            if self._nearby_hk._hk_finalized:
                self._nearby_hk.clear()
                self._nearby_hk._hk_finalized = False
            QKeySequenceEdit.keyPressEvent(self._nearby_hk, e)

        self._nearby_hk.keySequenceChanged.connect(_on_seq_changed)
        self._nearby_hk.keyPressEvent = _hk_key_press
        # Pausar hotkey enquanto o campo está em foco
        def _on_hk_focus_in():
            if _set_nearby_hotkey_paused: _set_nearby_hotkey_paused(True)
        def _on_hk_focus_out():
            if _set_nearby_hotkey_paused: _set_nearby_hotkey_paused(False)
        def _hk_focus_in(e):
            _on_hk_focus_in()
            QKeySequenceEdit.focusInEvent(self._nearby_hk, e)
        def _hk_focus_out(e):
            _on_hk_focus_out()
            QKeySequenceEdit.focusOutEvent(self._nearby_hk, e)
        self._nearby_hk.focusInEvent  = _hk_focus_in
        self._nearby_hk.focusOutEvent = _hk_focus_out
        # Carregar binding atual
        hk_vk  = _OPEN_NEARBY_DEFAULT['vk']
        hk_mod = _OPEN_NEARBY_DEFAULT['mod']
        try:
            with open(_HOTKEY_SETTINGS_FILE, 'r', encoding='utf-8') as _f:
                _hk_data = json.load(_f).get('open_nearby', {})
                hk_vk  = _hk_data.get('vk',  hk_vk)
                hk_mod = _hk_data.get('mod', hk_mod)
        except Exception:
            pass
        self._nearby_hk.setKeySequence(QKeySequence(_vk_to_seq_str(hk_vk, hk_mod)))
        hk_row.addWidget(hk_lbl)
        hk_row.addWidget(self._nearby_hk, 1)
        layout.addLayout(hk_row)
        hk_note = QLabel('Restart required to apply hotkey change.')
        hk_note.setStyleSheet('color:#555; font:10px "Segoe UI"; margin-left:0;')
        layout.addWidget(hk_note)

        # Direction arrow
        section('Performance')
        option('disableGpuVsync', 'Disable GPU vsync (multi-monitor fix)',
               'Fixes FPS cap when using the overlay on a secondary monitor with a different refresh rate. Requires restart.')

        section('Direction arrow')
        option('rotateWithPlayer', 'Rotate map with player',
               'The map rotates to always show the player\'s forward direction at the top')
        option('rotateWithCamera', 'Rotate map with camera',
               'The map rotates using the camera heading received via WebSocket')
        self._checkboxes['rotateWithPlayer'].toggled.connect(
            lambda checked: checked and self._checkboxes['rotateWithCamera'].setChecked(False))
        self._checkboxes['rotateWithCamera'].toggled.connect(
            lambda checked: checked and self._checkboxes['rotateWithPlayer'].setChecked(False))
        heading_row = QHBoxLayout()
        heading_row.setSpacing(10)
        heading_row.addWidget(QLabel('Source'))
        from PyQt5.QtWidgets import QComboBox
        self._heading_combo = QComboBox()
        self._heading_combo.addItem('Auto (entity → delta)',  'auto')
        self._heading_combo.addItem('Forward vector (entity)', 'entity')
        self._heading_combo.addItem('Position delta',           'delta')
        current_src = cfg.get('headingSource', SETTING_DEFAULTS['headingSource'])
        idx = self._heading_combo.findData(current_src)
        if idx >= 0:
            self._heading_combo.setCurrentIndex(idx)
        self._heading_combo.setToolTip(
            'auto: uses forward vector when available, falls back to delta\n'
            'entity: uses entity+0x80/0x88 only (works while standing still)\n'
            'delta: always computes from position difference')
        heading_row.addWidget(self._heading_combo, 1)
        layout.addLayout(heading_row)

        layout.addSpacing(14)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self._on_cancel)
        save_btn = QPushButton('Save')
        save_btn.setObjectName('save')
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _on_cancel(self):
        if self.parent():
            self.parent().setWindowOpacity(self._original_opacity)
        self.reject()

    def get_settings(self):
        result = {key: cb.isChecked() for key, cb in self._checkboxes.items()}
        result['transparency'] = self._slider.value()
        result['centerTeleportY'] = float(self._center_y.value())
        result['headingSource'] = self._heading_combo.currentData()
        result['nearbyThreshold'] = self._nearby_radius.value() / 1000.0
        self._save_nearby_hotkey()
        return result

    def _save_nearby_hotkey(self):
        seq_str = self._nearby_hk.keySequence().toString()
        parsed = _seq_str_to_vk(seq_str)
        if parsed is None:
            return
        vk, mod = parsed
        try:
            try:
                with open(_HOTKEY_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
            data['open_nearby'] = {'vk': vk, 'mod': mod, 'enabled': True}
            os.makedirs(os.path.dirname(_HOTKEY_SETTINGS_FILE), exist_ok=True)
            with open(_HOTKEY_SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass


# ── Janelas WebEngine auxiliares ─────────────────────────────────────

class PopupWebWindow(QMainWindow):
    closed_with_pos = pyqtSignal(object)  # emits QPoint when window closes

    def __init__(self, parent=None, title='CD Overlay'):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(300, 560)
        self._view = QWebEngineView(self)
        self._page = QWebEnginePage(self._view)
        self._view.setPage(self._page)
        self.setCentralWidget(self._view)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self.close)

    def closeEvent(self, event):
        self.closed_with_pos.emit(self.pos())
        super().closeEvent(event)
        QTimer.singleShot(50, focus_game_window)

    def page(self):
        return self._page


class InterceptPage(QWebEnginePage):
    login_needed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_windows = []
        self._last_popup_pos = None   # persists popup position within the session

    def createWindow(self, window_type):
        overlay = self.view().window() if self.view() else None
        popup = PopupWebWindow(overlay, 'CD Overlay')
        self._popup_windows.append(popup)
        popup.destroyed.connect(lambda _=None, p=popup: self._forget_popup(p))
        popup.closed_with_pos.connect(lambda pos: setattr(self, '_last_popup_pos', pos))
        popup._page.windowCloseRequested.connect(popup.close)
        popup._page.geometryChangeRequested.connect(
            lambda rect, p=popup: p.resize(rect.width(), rect.height()))
        self._position_popup(popup, overlay)
        popup.show()
        QTimer.singleShot(0, lambda: self._activate_popup(popup))
        return popup.page()

    def _activate_popup(self, popup):
        if not popup or not popup.isVisible():
            return
        popup.raise_()
        hwnd = int(popup.winId())
        fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
        fg_tid = ctypes.windll.user32.GetWindowThreadProcessId(fg_hwnd, None)
        my_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        if fg_tid and fg_tid != my_tid:
            ctypes.windll.user32.AttachThreadInput(fg_tid, my_tid, True)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.AttachThreadInput(fg_tid, my_tid, False)
        else:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        popup._view.setFocus()

    def _position_popup(self, popup, overlay):
        # If user already moved the popup this session, reuse that position
        if self._last_popup_pos is not None:
            popup.move(self._last_popup_pos)
            return

        if overlay is None:
            return

        screen = QApplication.screenAt(overlay.geometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return

        sg = screen.availableGeometry()
        pw, ph = popup.width(), popup.height()
        ox, oy = overlay.x(), overlay.y()
        ow, oh = overlay.width(), overlay.height()
        margin = 8

        sr = sg.x() + sg.width()   # screen right
        sb = sg.y() + sg.height()  # screen bottom

        def cy(y):  # clamp y inside screen
            return max(sg.y(), min(y, sb - ph))

        def cx(x):  # clamp x inside screen
            return max(sg.x(), min(x, sr - pw))

        # Right of overlay
        if ox + ow + margin + pw <= sr:
            popup.move(QPoint(ox + ow + margin, cy(oy)))
            return
        # Left of overlay
        if ox - margin - pw >= sg.x():
            popup.move(QPoint(ox - margin - pw, cy(oy)))
            return
        # Below overlay
        if oy + oh + margin + ph <= sb:
            popup.move(QPoint(cx(ox), oy + oh + margin))
            return
        # Above overlay
        if oy - margin - ph >= sg.y():
            popup.move(QPoint(cx(ox), oy - margin - ph))
            return

        # No space on any side — use the screen corner nearest the overlay
        ocx = ox + ow // 2
        ocy = oy + oh // 2
        x = sr - pw if ocx > sg.x() + sg.width() // 2 else sg.x()
        y = sb - ph if ocy > sg.y() + sg.height() // 2 else sg.y()
        popup.move(QPoint(x, y))

    def _forget_popup(self, popup):
        try:
            self._popup_windows.remove(popup)
        except ValueError:
            pass
        self.runJavaScript('waypointPopup = null; nearbyPopup = null; nearbyInputHandler = null;')

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() == 'cdcompanion' and url.host() == 'login-needed':
            self.login_needed.emit()
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class LoginPrompt(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Login required')
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setStyleSheet("""
            QDialog   { background:#0f0f1a; border:1px solid #2d2d44; border-radius:8px; }
            QLabel    { color:#e2e8f0; font:13px 'Segoe UI'; }
            QPushButton { border-radius:5px; padding:6px 18px; font:13px 'Segoe UI'; }
            QPushButton#yes { background:#1db954; color:#fff; border:none; }
            QPushButton#yes:hover { background:#17a84a; }
            QPushButton#no  { background:#1a1a2e; color:#aaa; border:1px solid #2d2d44; }
            QPushButton#no:hover  { background:#252540; }
        """)
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        icon = QLabel('🔒')
        icon.setStyleSheet('font:28px; background:transparent;')
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        msg = QLabel('You need to log in\nto access the map.')
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet('color:#e2e8f0; font:13px "Segoe UI"; background:transparent;')
        layout.addWidget(msg)

        row = QHBoxLayout()
        no_btn  = QPushButton('Not now')
        no_btn.setObjectName('no')
        no_btn.clicked.connect(self.reject)
        yes_btn = QPushButton('Go to login')
        yes_btn.setObjectName('yes')
        yes_btn.clicked.connect(self.accept)
        row.addWidget(no_btn)
        row.addWidget(yes_btn)
        layout.addLayout(row)


# ── Sinal para toggle thread-safe ────────────────────────────────────

class HotkeySignals(QObject):
    toggle = pyqtSignal()


# ── Barra customizada (arrastável, sem decoração do Windows) ──────────

class TitleBar(QWidget):
    HEIGHT = 30

    def __init__(self, parent):
        super().__init__(parent)
        self._drag_pos = None
        self.setFixedHeight(self.HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            QWidget   { background:#0f0f1a; }
QPushButton { background:transparent; border:none;
                          color:#666; font:13px; padding:0 6px; min-width:24px; }
            QPushButton:hover#btn_back     { color:#aaa; }
            QPushButton:hover#btn_settings { color:#ffd060; }
            QPushButton:hover#btn_hide     { color:#60b4ff; }
            QPushButton:hover#btn_close    { color:#ff6060; }
        """)

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 4, 0)
        row.setSpacing(2)

        self._lbl = QLabel('🗺')
        self._lbl.setStyleSheet('font:14px; background:transparent;')
        row.addWidget(self._lbl)
        row.addStretch(1)

        def icon_btn(name, text, tip):
            b = QPushButton(text)
            b.setObjectName(name)
            b.setToolTip(tip)
            b.setFixedSize(26, 26)
            row.addWidget(b)
            return b

        self.btn_back     = icon_btn('btn_back',     '◀', 'Back')
        self.btn_settings = icon_btn('btn_settings', '⚙', 'Settings')
        self.btn_hide     = icon_btn('btn_hide',     '–', 'Hide  (Ctrl+Shift+M)')
        self.btn_close    = icon_btn('btn_close',    '✕', 'Close')

    def set_compact(self, compact):
        self._lbl.setVisible(not compact)
        self.btn_back.setVisible(not compact)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            import ctypes
            hwnd = int(self.window().winId())
            ctypes.windll.user32.ReleaseCapture()
            ctypes.windll.user32.SendMessageW(hwnd, 0x0112, 0xF012, 0)  # WM_SYSCOMMAND, SC_MOVE|HTCAPTION
