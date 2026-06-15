"""Spuk Settings window (Aurora glass look).

Opened on demand from the floating pill's ⚙ button (or the menu bar) — Spuk is
otherwise driven entirely from the pill. This window is where you manage the
things you change rarely: which languages you want available, your microphone,
and quitting the app.

Languages: the bundled Whisper model already understands ~99 languages with no
download, so "adding" a language just adds it to your curated set (see
languages.py / core.add_language). You pick from a searchable list; the chosen
languages then appear as quick-switch chips on the pill.

Shares one CoreSignals bus with the pill, so both stay in sync.
"""

from __future__ import annotations

import logging
import threading
import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import __version__, updates
from .config import Config
from .core import SpukCore
from .languages import all_languages
from .ui_bar import CoreSignals, _is_mac, _lang_label

log = logging.getLogger("spuk.window")

READY_DOT = "#86efac"
REC_DOT = "#fca5a5"
WARM_DOT = "#fde68a"


class SpukWindow(QWidget):
    """The Settings window. Closing hides it; the app keeps running via the pill."""

    # Emitted from the background update-check thread with an updates.UpdateResult,
    # so the dialog is shown back on the Qt main thread.
    _update_done = Signal(object)
    # Emitted when a self-update finishes staging: (ok, error_message).
    _self_update_done = Signal(bool, str)

    def __init__(self, config: Config, core: SpukCore, signals: CoreSignals) -> None:
        super().__init__()
        self._cfg = config
        self._core = core
        self._quit = None  # set by run_bar
        self.setWindowTitle("Spuk — Settings")
        self.setFixedSize(400, 600)
        self._build_ui()
        self._wire(signals)

    # --- layout ----------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scene = QFrame()
        scene.setObjectName("scene")
        root.addWidget(scene)
        scene_l = QVBoxLayout(scene)
        scene_l.setContentsMargins(18, 18, 18, 18)

        card = QFrame()
        card.setObjectName("card")
        scene_l.addWidget(card)
        c = QVBoxLayout(card)
        c.setContentsMargins(20, 18, 20, 18)
        c.setSpacing(12)

        # Header: ghost + title + live status pill.
        top = QHBoxLayout()
        top.setSpacing(12)
        ghost = QLabel("👻")
        ghost.setObjectName("ghost")
        ghost.setFixedSize(46, 46)
        ghost.setAlignment(Qt.AlignCenter)
        title = QLabel("Spuk")
        title.setObjectName("title")
        self._live = QLabel()
        self._live.setObjectName("live")
        self._set_live("Starting…", WARM_DOT)
        top.addWidget(ghost)
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self._live, 0, Qt.AlignVCenter)
        c.addLayout(top)

        # Shortcut (informational).
        combo = "⌃ Ctrl    ⌥ Option" if _is_mac() else "Ctrl    Alt"
        key = QLabel(f"{combo}        Hold & speak")
        key.setObjectName("key")
        c.addWidget(key)

        # --- Languages ---
        c.addWidget(_section("My languages"))

        self._langlist = QVBoxLayout()
        self._langlist.setSpacing(6)
        self._langlist.setContentsMargins(0, 0, 0, 0)
        holder = QWidget()
        holder.setObjectName("langlist")
        holder.setLayout(self._langlist)
        scroll = QScrollArea()
        scroll.setObjectName("scroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        scroll.setFixedHeight(150)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet("background: transparent;")
        c.addWidget(scroll)
        self._rebuild_langs()

        # Add-language searchable dropdown.
        self._add = QComboBox()
        self._add.setObjectName("add")
        self._add.setEditable(True)
        self._add.setInsertPolicy(QComboBox.NoInsert)
        self._add.lineEdit().setPlaceholderText("➕  Add a language…")
        self._add.addItem("➕  Add a language…", None)
        for code, name in all_languages():
            self._add.addItem(name, code)
        self._add.setCurrentIndex(0)
        completer = self._add.completer()
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self._add.activated.connect(self._on_add)
        c.addWidget(self._add)

        # --- Microphone ---
        c.addWidget(_section("Microphone"))
        self._mic = QComboBox()
        self._mic.setObjectName("mic")
        self._populate_mics()
        self._mic.currentIndexChanged.connect(self._mic_changed)
        c.addWidget(self._mic)

        c.addStretch(1)

        priv = QLabel("🔒 Free forever · runs entirely on your computer")
        priv.setObjectName("priv")
        priv.setAlignment(Qt.AlignCenter)
        c.addWidget(priv)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("ver")
        self._update_btn = QPushButton("Check for updates")
        self._update_btn.setObjectName("update")
        self._update_btn.setCursor(Qt.PointingHandCursor)
        self._update_btn.clicked.connect(self._on_check_updates)
        quit_btn = QPushButton("Quit Spuk")
        quit_btn.setObjectName("quit")
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.clicked.connect(self._on_quit)
        footer.addWidget(ver)
        footer.addStretch(1)
        footer.addWidget(self._update_btn)
        footer.addWidget(quit_btn)
        c.addLayout(footer)

        self._update_done.connect(self._show_update_result)
        self._self_update_done.connect(self._on_self_update_done)
        self.setStyleSheet(_QSS)

    def _populate_mics(self) -> None:
        self._mic.addItem("System default", None)
        try:
            import sounddevice as sd

            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_input_channels", 0) > 0:
                    self._mic.addItem(dev["name"], idx)
        except Exception:  # noqa: BLE001
            pass

    def _rebuild_langs(self) -> None:
        """(Re)build the 'My languages' rows from the curated set."""
        while self._langlist.count():
            item = self._langlist.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        active = self._core.language
        removable = len(self._core.languages) > 1
        for code in self._core.languages:
            row = QFrame()
            row.setObjectName("langrow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 0, 8, 0)
            name = QPushButton(("●  " if code == active else "○  ") + _lang_label(code))
            name.setObjectName("langname")
            name.setProperty("active", code == active)
            name.setCursor(Qt.PointingHandCursor)
            name.clicked.connect(lambda _checked, x=code: self._core.set_language(x))
            rl.addWidget(name, 1)
            if removable:
                rm = QPushButton("✕")
                rm.setObjectName("remove")
                rm.setFixedWidth(28)
                rm.setCursor(Qt.PointingHandCursor)
                rm.setToolTip("Remove")
                rm.clicked.connect(lambda _checked, x=code: self._core.remove_language(x))
                rl.addWidget(rm)
            self._langlist.addWidget(row)
        self._langlist.addStretch(1)

    # --- core wiring -----------------------------------------------------

    def _wire(self, signals: CoreSignals) -> None:
        signals.recording.connect(self._on_recording)
        signals.language.connect(lambda _l: self._rebuild_langs())
        signals.languages.connect(lambda _c: self._rebuild_langs())
        signals.ready.connect(lambda: self._set_live("Ready", READY_DOT))

    def _set_live(self, text: str, dot: str) -> None:
        self._live.setText(f'<span style="color:{dot}">●</span> {text}')

    def _on_recording(self, active: bool) -> None:
        self._set_live("Recording…" if active else "Ready", REC_DOT if active else READY_DOT)

    def _on_add(self, _index: int) -> None:
        code = self._add.currentData()
        if code:
            self._core.add_language(code)
        self._add.setCurrentIndex(0)
        self._add.clearEditText()

    def _mic_changed(self, _index: int) -> None:
        try:
            self._core.set_input_device(self._mic.currentData())
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not set microphone: %s", exc)

    # --- window behaviour ------------------------------------------------

    def set_quit(self, fn) -> None:
        self._quit = fn

    def _on_quit(self) -> None:
        if self._quit is not None:
            self._quit()

    # --- updates ---------------------------------------------------------

    def _on_check_updates(self) -> None:
        """Check GitHub for a newer release (off the UI thread so it can't hang)."""
        self._update_btn.setEnabled(False)
        self._update_btn.setText("Checking…")

        def worker() -> None:
            result = updates.check_for_update(__version__)
            self._update_done.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    def _show_update_result(self, result: "updates.UpdateResult") -> None:
        self._update_btn.setEnabled(True)
        self._update_btn.setText("Check for updates")

        if result.status == "current":
            QMessageBox.information(self, "Spuk", result.message)
            return
        if result.status != "available":
            QMessageBox.warning(self, "Check for updates", result.message)
            return

        box = QMessageBox(self)
        box.setWindowTitle("Update available")
        box.setText(result.message)

        # In the installed app we can download + replace + relaunch in one click.
        # Running from source (or an unsupported platform) → open the page instead.
        if updates.can_self_update() and result.asset_url:
            box.setInformativeText("Install it now? Spuk will download it and restart automatically.")
            install = box.addButton("Update now", QMessageBox.AcceptRole)
            box.addButton("Open page", QMessageBox.ActionRole)
            box.addButton("Later", QMessageBox.RejectRole)
            box.setDefaultButton(install)
            box.exec()
            clicked = box.clickedButton()
            if clicked is install:
                self._start_self_update(result.asset_url)
            elif clicked is not None and box.buttonRole(clicked) == QMessageBox.ActionRole:
                webbrowser.open(result.url)
        else:
            box.setInformativeText("Open the download page in your browser?")
            box.setStandardButtons(QMessageBox.Open | QMessageBox.Cancel)
            box.setDefaultButton(QMessageBox.Open)
            if box.exec() == QMessageBox.Open:
                webbrowser.open(result.url)

    def _start_self_update(self, asset_url: str) -> None:
        """Download the new build and stage the in-place swap (off the UI thread)."""
        self._update_btn.setEnabled(False)
        self._update_btn.setText("Updating…")

        def worker() -> None:
            try:
                updates.self_update(asset_url)
                self._self_update_done.emit(True, "")
            except Exception as exc:  # noqa: BLE001
                log.warning("Self-update failed: %s", exc)
                self._self_update_done.emit(False, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_self_update_done(self, ok: bool, message: str) -> None:
        if ok:
            # The detached helper is waiting for us to exit; quitting triggers the
            # swap + relaunch.
            if self._quit is not None:
                self._quit()
            return
        self._update_btn.setEnabled(True)
        self._update_btn.setText("Check for updates")
        box = QMessageBox(self)
        box.setWindowTitle("Update failed")
        box.setText("Couldn't install the update automatically.")
        box.setInformativeText("Open the download page to update manually?")
        box.setStandardButtons(QMessageBox.Open | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Open)
        if box.exec() == QMessageBox.Open:
            webbrowser.open(updates.RELEASES_PAGE)

    def present(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        # Background app: closing just hides Settings; the pill stays running.
        event.ignore()
        self.hide()


def _section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("section")
    return label


_QSS = """
#scene {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #8b5cf6, stop:0.5 #6d28d9, stop:1 #3b0764);
}
#card {
    background: rgba(255, 255, 255, 0.14);
    border: 1px solid rgba(255, 255, 255, 0.30);
    border-radius: 18px;
}
QLabel { color: #ffffff; }
#ghost {
    background: rgba(255, 255, 255, 0.20);
    border: 1px solid rgba(255, 255, 255, 0.35);
    border-radius: 14px; font-size: 23px;
}
#title { font-size: 18px; font-weight: 700; }
#live {
    color: #ffffff; font-size: 12px; font-weight: 600;
    background: rgba(255, 255, 255, 0.16);
    border: 1px solid rgba(255, 255, 255, 0.28);
    border-radius: 11px; padding: 4px 11px;
}
#key {
    color: rgba(255, 255, 255, 0.90); font-size: 13px; font-weight: 600;
    background: rgba(255, 255, 255, 0.12);
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 13px; padding: 12px 15px;
}
#section {
    color: rgba(255, 255, 255, 0.65); font-size: 11px; font-weight: 700;
    letter-spacing: 1px; padding: 2px 2px 0 2px;
}
#scroll, #langlist { background: transparent; }
#langrow {
    background: rgba(255, 255, 255, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 10px; min-height: 38px;
}
QPushButton#langname {
    color: rgba(255, 255, 255, 0.88); font-size: 13.5px; font-weight: 600;
    background: transparent; border: none; text-align: left; padding: 8px 2px;
}
QPushButton#langname[active="true"] { color: #ffffff; }
QPushButton#remove {
    color: rgba(255, 255, 255, 0.8); background: transparent; border: none;
    font-size: 13px; border-radius: 8px;
}
QPushButton#remove:hover { background: rgba(255, 90, 90, 0.45); color: #ffffff; }
QComboBox#add, QComboBox#mic {
    color: #ffffff; font-size: 13px;
    background: rgba(255, 255, 255, 0.12);
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 11px; padding: 10px 14px;
}
QComboBox#add QLineEdit, QComboBox#mic QLineEdit {
    color: #ffffff; background: transparent; border: none;
}
QComboBox#add QAbstractItemView, QComboBox#mic QAbstractItemView {
    background: #4c1d95; color: #ffffff; selection-background-color: #7c3aed;
}
#priv { color: rgba(255, 255, 255, 0.82); font-size: 12px; }
#ver { color: rgba(255, 255, 255, 0.6); font-size: 11px; }
QPushButton#update {
    color: #ffffff; font-size: 13px; font-weight: 600;
    background: rgba(255, 255, 255, 0.14);
    border: 1px solid rgba(255, 255, 255, 0.30);
    border-radius: 9px; padding: 7px 14px;
}
QPushButton#update:hover { background: rgba(255, 255, 255, 0.28); }
QPushButton#update:disabled { color: rgba(255, 255, 255, 0.6); background: rgba(255, 255, 255, 0.08); }
QPushButton#quit {
    color: #ffffff; font-size: 13px; font-weight: 600;
    background: rgba(255, 255, 255, 0.14);
    border: 1px solid rgba(255, 255, 255, 0.30);
    border-radius: 9px; padding: 7px 16px;
}
QPushButton#quit:hover { background: rgba(255, 90, 90, 0.45); }
"""
