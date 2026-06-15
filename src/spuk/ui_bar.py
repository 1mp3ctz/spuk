"""Floating dictation bar (Qt / PySide6).

A small, frameless, always-on-top pill anchored at the bottom-center of the
screen. It expands on hover to show the current language, a hold-to-talk button,
language buttons, a microphone picker, and the keyboard shortcuts. The global
hotkey still drives dictation; this bar is the visible UI + quick settings.

Threading note: SpukCore's callbacks fire from the hotkey-listener thread. Qt
widgets may only be touched on the main thread, so we bounce every callback
through Qt signals (queued automatically across threads).
"""

from __future__ import annotations

import threading

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .config import Config
from .core import SpukCore
from .languages import display_name

# Native display names for the three first-class languages; anything else falls
# back to the English language name from languages.display_name().
LANGUAGE_NAMES = {"en": "English", "de": "Deutsch", "pl": "Polski"}


def _lang_label(code: str) -> str:
    return LANGUAGE_NAMES.get(code, display_name(code))

COLLAPSED = (64, 22)
EXPANDED = (300, 168)
BOTTOM_MARGIN = 56
ACCENT = "#8b5cf6"


class CoreSignals(QObject):
    """Thread-safe bridge from SpukCore callbacks to the Qt main thread."""

    recording = Signal(bool)
    language = Signal(str)
    languages = Signal(tuple)  # the curated set changed (add/remove)
    transcript = Signal(str)
    ready = Signal()


class SpukBar(QWidget):
    def __init__(self, config: Config, core: SpukCore, signals: "CoreSignals") -> None:
        super().__init__()
        self._cfg = config
        self._core = core
        self._sig = signals
        self._expanded = False
        self._open_window = None  # set by run_bar; clicking the pill opens the window

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # Don't steal focus from the user's text field when the bar appears.
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        # Keep the Tool window visible even when another app is frontmost (macOS).
        always_show = getattr(Qt, "WA_MacAlwaysShowToolWindow", None)
        if always_show is not None:
            self.setAttribute(always_show, True)

        self._build_ui()
        self._wire_core()
        self._apply_geometry(expanded=False)

    # --- layout ----------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QFrame(self)
        self._card.setObjectName("card")
        # Start fully rounded (capsule / "tic-tac"): radius = half the pill height.
        self._card.setStyleSheet(self._card_qss(COLLAPSED[1] // 2))
        outer.addWidget(self._card)

        card = QVBoxLayout(self._card)
        card.setContentsMargins(10, 3, 10, 5)
        card.setSpacing(6)

        # Collapsed/header row: status dot + language code (+ status when expanded).
        header = QHBoxLayout()
        header.setSpacing(6)
        self._dot = QLabel("●")
        self._dot.setStyleSheet("color:rgba(255,255,255,0.7); font-size:11px;")
        self._lang_code = QLabel(self._core.language.upper())
        self._lang_code.setFont(QFont("", 11, QFont.Bold))
        self._status = QLabel("starting…")
        self._status.setStyleSheet("color:rgba(255,255,255,0.85); font-size:11px;")
        self._gear = QPushButton("⚙")
        self._gear.setObjectName("gear")
        self._gear.setToolTip("Settings")
        self._gear.setCursor(Qt.PointingHandCursor)
        self._gear.clicked.connect(self._open_settings)
        header.addWidget(self._dot)
        header.addWidget(self._lang_code)
        header.addStretch(1)
        header.addWidget(self._status)
        header.addWidget(self._gear)
        card.addLayout(header)

        # --- expanded-only widgets ---
        self._dictate = QPushButton("Hold to talk")
        self._dictate.setObjectName("dictate")
        self._dictate.pressed.connect(self._core.begin_recording)
        self._dictate.released.connect(self._dictate_released)
        card.addWidget(self._dictate)

        # Language quick-switch chips (rebuilt when the curated set changes).
        self._lang_row = QHBoxLayout()
        self._lang_buttons: dict[str, QPushButton] = {}
        self._rebuild_langs()
        card.addLayout(self._lang_row)

        mod = "⌃⌥" if _is_mac() else "Ctrl+Alt"
        self._hint = QLabel(f"Hold {mod} to dictate · ⚙ for languages & settings")
        self._hint.setStyleSheet("color:rgba(255,255,255,0.8); font-size:11px;")
        card.addWidget(self._hint)

        # Status + gear only show when expanded so the collapsed pill stays tiny.
        self._expanded_widgets = [self._status, self._gear, self._dictate, self._hint]
        for w in self._expanded_widgets:
            w.hide()
        for b in self._lang_buttons.values():
            b.hide()

        # Delayed collapse so a brief cursor wobble doesn't snap the bar shut.
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.setInterval(280)
        self._collapse_timer.timeout.connect(self._maybe_collapse)

    @staticmethod
    def _card_qss(radius: int) -> str:
        # Same Aurora purple/glass scheme as the main window (ui_window.py).
        return (
            f"#card {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            f" stop:0 #8b5cf6, stop:0.5 #7c3aed, stop:1 #6d28d9);"
            f" border-radius: {radius}px; border:1px solid rgba(255,255,255,0.25); }}"
            "QLabel { color: #ffffff; }"
            "QComboBox { color:#ffffff; background:rgba(255,255,255,0.12);"
            " border:1px solid rgba(255,255,255,0.25); border-radius:9px; padding:3px 8px; }"
            "QComboBox QAbstractItemView { background:#4c1d95; color:#ffffff;"
            " selection-background-color:#7c3aed; }"
            "QPushButton#dictate { color:#6d28d9; background:rgba(255,255,255,0.92);"
            " border:none; border-radius:10px; padding:8px; font-weight:700; }"
            "QPushButton#dictate:pressed { background:#ffffff; }"
            "QPushButton.lang { color:rgba(255,255,255,0.85); background:rgba(255,255,255,0.12);"
            " border:1px solid rgba(255,255,255,0.22); border-radius:9px; padding:4px 10px; }"
            "QPushButton.lang:checked { color:#6d28d9; background:rgba(255,255,255,0.92); border:none; }"
            "QPushButton#gear { color:#ffffff; background:rgba(255,255,255,0.14);"
            " border:1px solid rgba(255,255,255,0.25); border-radius:8px; padding:1px 6px; font-size:13px; }"
            "QPushButton#gear:hover { background:rgba(255,255,255,0.28); }"
        )

    def _rebuild_langs(self) -> None:
        """(Re)build the language quick-switch chips from the curated set."""
        for b in self._lang_buttons.values():
            self._lang_row.removeWidget(b)
            b.deleteLater()
        self._lang_buttons = {}
        for code in self._core.languages:
            b = QPushButton(_lang_label(code))
            b.setProperty("class", "lang")
            b.setCheckable(True)
            b.setChecked(code == self._core.language)
            b.clicked.connect(lambda _checked, c=code: self._core.set_language(c))
            self._lang_buttons[code] = b
            self._lang_row.addWidget(b)
        if not self._expanded:
            for b in self._lang_buttons.values():
                b.hide()

    def _open_settings(self) -> None:
        if self._open_window is not None:
            self._open_window()

    # --- core wiring -----------------------------------------------------

    def _wire_core(self) -> None:
        # The shared CoreSignals bus is created and connected to the core in
        # run_bar(); the bar just listens on it (so the window can listen too).
        self._sig.recording.connect(self._on_recording)
        self._sig.language.connect(self._on_language)
        self._sig.languages.connect(lambda _codes: self._rebuild_langs())
        self._sig.ready.connect(lambda: self._status.setText("ready"))

    def _on_recording(self, active: bool) -> None:
        self._dot.setStyleSheet(
            f"color:{'#fca5a5' if active else '#86efac'}; font-size:14px;"
        )
        self._status.setText("recording…" if active else "ready")

    def _on_language(self, lang: str) -> None:
        self._lang_code.setText(lang.upper())
        for code, b in self._lang_buttons.items():
            b.setChecked(code == lang)

    def _dictate_released(self) -> None:
        # Transcribe+paste blocks ~1s — keep it off the UI thread.
        threading.Thread(target=self._core.finish_recording, daemon=True).start()

    # --- open the settings window ---------------------------------------

    def set_open_window(self, fn) -> None:
        self._open_window = fn

    # --- hover expand / collapse ----------------------------------------

    def _apply_geometry(self, expanded: bool) -> None:
        w, h = EXPANDED if expanded else COLLAPSED
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - w) // 2
        y = screen.y() + screen.height() - h - BOTTOM_MARGIN
        self.setGeometry(QRect(x, y, w, h))

    def _animate(self, expanded: bool) -> None:
        w, h = EXPANDED if expanded else COLLAPSED
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - w) // 2
        y = screen.y() + screen.height() - h - BOTTOM_MARGIN
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setEndValue(QRect(x, y, w, h))
        anim.start()
        self._anim = anim  # keep a reference so it isn't GC'd

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._collapse_timer.stop()
        if not self._expanded:
            self._expanded = True
            self._card.setStyleSheet(self._card_qss(18))  # softer rounding when open
            for w in self._expanded_widgets:
                w.show()
            for b in self._lang_buttons.values():
                b.show()
            self._animate(expanded=True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        # Defer collapse briefly; cancelled if the cursor returns or a popup is open.
        self._collapse_timer.start()
        super().leaveEvent(event)

    def _maybe_collapse(self) -> None:
        # Don't collapse while the cursor is back on us.
        if self.underMouse():
            self._collapse_timer.start()
            return
        if self._expanded:
            self._expanded = False
            self._card.setStyleSheet(self._card_qss(COLLAPSED[1] // 2))  # back to capsule
            for w in self._expanded_widgets:
                w.hide()
            for b in self._lang_buttons.values():
                b.hide()
            self._animate(expanded=False)


def _is_mac() -> bool:
    import platform

    return platform.system() == "Darwin"


def _menubar_icon() -> QIcon:
    """A tiny purple ghost drawn at runtime (no binary asset to ship)."""
    size = 22  # macOS menu-bar icons render around this size
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(ACCENT))
    p.drawRoundedRect(1, 1, size - 2, size - 2, 5, 5)
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(6, 4, 10, 10)
    p.drawRect(6, 9, 10, 8)
    p.end()
    return QIcon(pm)


def _install_menubar(app, on_open, on_quit) -> "QSystemTrayIcon | None":
    """Add a menu-bar (system-tray) icon to open Settings or quit Spuk.

    The pill has no window chrome and Spuk runs with no Dock icon, so this is the
    user's way to reach Settings and to quit. Returns the icon (kept alive by
    `app`) or None if the platform has no system tray.
    """
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None

    menu = QMenu()
    header = menu.addAction("Spuk")
    header.setEnabled(False)
    menu.addSeparator()
    open_action = menu.addAction("Settings…")
    open_action.triggered.connect(lambda: on_open())
    menu.addSeparator()
    quit_action = menu.addAction("Quit Spuk")
    quit_action.triggered.connect(lambda: on_quit())

    tray = QSystemTrayIcon(_menubar_icon(), app)
    tray.setToolTip("Spuk")
    tray.setContextMenu(menu)
    # Clicking/double-clicking the icon (Windows tray) also opens the window.
    tray.activated.connect(
        lambda reason: on_open()
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick)
        else None
    )
    tray.show()
    return tray


def run_bar(config: Config, core: SpukCore) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    # One shared signal bus: the core fires these (from the hotkey thread) and
    # both the floating bar and the main window listen on them.
    signals = CoreSignals()
    core.on_recording_change = signals.recording.emit
    core.on_language_change = signals.language.emit
    core.on_languages_change = signals.languages.emit
    core.on_transcript = signals.transcript.emit

    # The floating pill is the primary, always-on UI.
    bar = SpukBar(config, core, signals)
    bar.show()

    # The Settings window is created up front but stays hidden — it only appears
    # when the user clicks the pill's ⚙ button (or the menu-bar 'Settings…').
    from .ui_window import SpukWindow

    window = SpukWindow(config, core, signals)
    bar.set_open_window(window.present)

    # Start the global hotkey listener on a background thread.
    listener = core.make_listener().start()

    def quit_app() -> None:
        # Stop the background hotkey listener so the process actually exits.
        try:
            if listener is not None:
                listener.stop()
        finally:
            app.quit()

    window.set_quit(quit_app)

    # Menu-bar icon (Settings / Quit). Held by the QApplication so it isn't GC'd.
    app._spuk_tray = _install_menubar(app, window.present, quit_app)  # type: ignore[attr-defined]
    app._spuk_window = window  # type: ignore[attr-defined]  # keep a strong ref

    # Warm the model off the UI thread so the UI appears immediately.
    def _warm() -> None:
        core.warm()
        signals.ready.emit()

    threading.Thread(target=_warm, daemon=True).start()

    app.exec()
