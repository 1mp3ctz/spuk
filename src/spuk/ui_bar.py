"""Wispr-Flow-style floating bar (Qt / PySide6).

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
    Signal,
)
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .config import Config
from .core import SpukCore

LANGUAGE_NAMES = {"en": "English", "de": "Deutsch", "pl": "Polski"}

COLLAPSED = (150, 44)
EXPANDED = (380, 188)
BOTTOM_MARGIN = 64
ACCENT = "#8b5cf6"


class CoreSignals(QObject):
    """Thread-safe bridge from SpukCore callbacks to the Qt main thread."""

    recording = Signal(bool)
    language = Signal(str)
    transcript = Signal(str)
    ready = Signal()


class SpukBar(QWidget):
    def __init__(self, config: Config, core: SpukCore) -> None:
        super().__init__()
        self._cfg = config
        self._core = core
        self._expanded = False

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._build_ui()
        self._wire_core()
        self._apply_geometry(expanded=False)

    # --- layout ----------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QFrame(self)
        self._card.setObjectName("card")
        self._card.setStyleSheet(
            "#card { background-color: rgba(24,24,28,235); border-radius: 18px; }"
            "QLabel { color: #f4f4f5; }"
            "QComboBox { color: #f4f4f5; background:#2a2a31; border:1px solid #3a3a42;"
            " border-radius:8px; padding:3px 8px; }"
            f"QPushButton#dictate {{ color:#fff; background:{ACCENT}; border:none;"
            " border-radius:10px; padding:8px; font-weight:600; }"
            "QPushButton#dictate:pressed { background:#7c3aed; }"
            "QPushButton.lang { color:#cfcfd4; background:#2a2a31; border:1px solid #3a3a42;"
            " border-radius:8px; padding:4px 10px; }"
            "QPushButton.lang:checked { color:#fff; background:" + ACCENT + "; border:none; }"
        )
        outer.addWidget(self._card)

        card = QVBoxLayout(self._card)
        card.setContentsMargins(14, 10, 14, 12)
        card.setSpacing(8)

        # Collapsed/header row: status dot + language code + hint.
        header = QHBoxLayout()
        self._dot = QLabel("●")
        self._dot.setStyleSheet("color:#6b7280; font-size:14px;")
        self._lang_code = QLabel(self._core.language.upper())
        self._lang_code.setFont(QFont("", 13, QFont.Bold))
        self._status = QLabel("starting…")
        self._status.setStyleSheet("color:#9ca3af;")
        header.addWidget(self._dot)
        header.addWidget(self._lang_code)
        header.addStretch(1)
        header.addWidget(self._status)
        card.addLayout(header)

        # --- expanded-only widgets ---
        self._dictate = QPushButton("Hold to talk")
        self._dictate.setObjectName("dictate")
        self._dictate.pressed.connect(self._core.begin_recording)
        self._dictate.released.connect(self._dictate_released)
        card.addWidget(self._dictate)

        lang_row = QHBoxLayout()
        self._lang_buttons: dict[str, QPushButton] = {}
        for code in self._core.languages:
            b = QPushButton(LANGUAGE_NAMES.get(code, code))
            b.setProperty("class", "lang")
            b.setCheckable(True)
            b.setChecked(code == self._core.language)
            b.clicked.connect(lambda _checked, c=code: self._core.set_language(c))
            self._lang_buttons[code] = b
            lang_row.addWidget(b)
        card.addLayout(lang_row)

        self._mic = QComboBox()
        self._populate_mics()
        self._mic.currentIndexChanged.connect(self._mic_changed)
        card.addWidget(self._mic)

        mod = "⌃⌥" if _is_mac() else "Ctrl+Alt"
        self._hint = QLabel(f"Hold {mod} to dictate · ⌃⇧L switches language")
        self._hint.setStyleSheet("color:#9ca3af; font-size:11px;")
        card.addWidget(self._hint)

        self._expanded_widgets = [self._dictate, self._mic, self._hint]
        for w in self._expanded_widgets:
            w.hide()
        for b in self._lang_buttons.values():
            b.hide()

    def _populate_mics(self) -> None:
        self._mic.addItem("System default", None)
        try:
            import sounddevice as sd

            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_input_channels", 0) > 0:
                    self._mic.addItem(dev["name"], idx)
        except Exception:  # noqa: BLE001
            pass

    # --- core wiring -----------------------------------------------------

    def _wire_core(self) -> None:
        self._sig = CoreSignals()
        self._sig.recording.connect(self._on_recording)
        self._sig.language.connect(self._on_language)
        self._sig.ready.connect(lambda: self._status.setText("ready"))
        self._core.on_recording_change = self._sig.recording.emit
        self._core.on_language_change = self._sig.language.emit

    def _on_recording(self, active: bool) -> None:
        self._dot.setStyleSheet(
            f"color:{'#ef4444' if active else '#22c55e'}; font-size:14px;"
        )
        self._status.setText("recording…" if active else "ready")

    def _on_language(self, lang: str) -> None:
        self._lang_code.setText(lang.upper())
        for code, b in self._lang_buttons.items():
            b.setChecked(code == lang)

    def _dictate_released(self) -> None:
        # Transcribe+paste blocks ~1s — keep it off the UI thread.
        threading.Thread(target=self._core.finish_recording, daemon=True).start()

    def _mic_changed(self, _index: int) -> None:
        self._core.set_input_device(self._mic.currentData())

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
        if not self._expanded:
            self._expanded = True
            for w in self._expanded_widgets:
                w.show()
            for b in self._lang_buttons.values():
                b.show()
            self._animate(expanded=True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._expanded:
            self._expanded = False
            for w in self._expanded_widgets:
                w.hide()
            for b in self._lang_buttons.values():
                b.hide()
            self._animate(expanded=False)
        super().leaveEvent(event)


def _is_mac() -> bool:
    import platform

    return platform.system() == "Darwin"


def run_bar(config: Config, core: SpukCore) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    bar = SpukBar(config, core)
    bar.show()

    # Start the global hotkey listener on a background thread.
    core.make_listener().start()

    # Warm the model off the UI thread so the bar appears immediately.
    def _warm() -> None:
        core.warm()
        bar._sig.ready.emit()

    threading.Thread(target=_warm, daemon=True).start()

    app.exec()
