"""macOS permissions helper window (Aurora glass look).

Spuk's builds are ad-hoc signed, so every update changes the code identity and
macOS drops the previous grants — the hotkey then goes silent until they're
re-granted, and the three toggles live in three *different* System Settings
panes. This dialog shows each permission's live status with a button that jumps
straight to the right pane, a Re-check, and a Quit & Reopen (a grant only applies
to a freshly started app). macOS only; the caller gates on platform.

Self-contained on purpose: it imports neither ui_bar nor ui_window (avoids an
import cycle, since ui_bar lazily imports this).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from . import __version__, permissions, updates
from .settings_store import update_user_settings

log = logging.getLogger("spuk.ui_permissions")

# (settings key, display name, why it's needed) — listed in the order to grant.
_PERMS = (
    ("microphone", "Microphone", "to hear your voice"),
    ("input_monitoring", "Input Monitoring", "to detect the hotkey"),
    ("accessibility", "Accessibility", "to paste the text"),
)

_OK = "#86efac"   # granted
_BAD = "#fca5a5"  # missing
_UNK = "#fde68a"  # unknown (check unavailable)


class PermissionsDialog(QDialog):
    """Shows the three macOS permissions with one-click deep links + live status."""

    def __init__(self, *, on_quit=None, parent=None) -> None:
        super().__init__(parent)
        self._on_quit = on_quit
        self._icons: dict[str, QLabel] = {}
        self._open_buttons: dict[str, QPushButton] = {}
        self.setWindowTitle("Spuk — Permissions")
        self.setModal(False)  # let the user touch the pill / Settings while granting
        self._build_ui()
        self.refresh()

    # --- layout ----------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scene = QFrame()
        scene.setObjectName("scene")
        root.addWidget(scene)
        v = QVBoxLayout(scene)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(10)
        ghost = QLabel("👻")
        ghost.setObjectName("ghost")
        ghost.setFixedSize(40, 40)
        ghost.setAlignment(Qt.AlignCenter)
        title = QLabel("Spuk needs macOS permissions")
        title.setObjectName("title")
        head.addWidget(ghost)
        head.addWidget(title, 1)
        v.addLayout(head)

        intro = QLabel(
            "macOS resets these after each update. Turn on all three, then "
            "quit & reopen Spuk — a grant only takes effect on a fresh start."
        )
        intro.setObjectName("intro")
        intro.setWordWrap(True)
        v.addWidget(intro)

        for key, name, why in _PERMS:
            row = QFrame()
            row.setObjectName("row")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 8, 10, 8)
            rl.setSpacing(10)
            icon = QLabel("●")
            icon.setObjectName("dot")
            icon.setFixedWidth(16)
            icon.setAlignment(Qt.AlignCenter)
            self._icons[key] = icon
            text = QLabel(f"<b>{name}</b> — {why}")
            text.setObjectName("rowtext")
            openb = QPushButton("Open")
            openb.setObjectName("open")
            openb.setCursor(Qt.PointingHandCursor)
            openb.clicked.connect(lambda _checked, k=key: permissions.open_privacy_pane(k))
            self._open_buttons[key] = openb
            rl.addWidget(icon)
            rl.addWidget(text, 1)
            rl.addWidget(openb)
            v.addWidget(row)

        self._dont = QCheckBox("Don't show this again")
        self._dont.setObjectName("dont")
        self._dont.toggled.connect(self._on_dont_toggled)
        v.addWidget(self._dont)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        recheck = QPushButton("Re-check")
        recheck.setObjectName("btn")
        recheck.setCursor(Qt.PointingHandCursor)
        recheck.clicked.connect(self.refresh)
        reopen = QPushButton("Quit & Reopen")
        reopen.setObjectName("btn")
        reopen.setCursor(Qt.PointingHandCursor)
        reopen.clicked.connect(self._quit_reopen)
        close = QPushButton("Close")
        close.setObjectName("btn")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.accept)
        foot.addWidget(recheck)
        foot.addStretch(1)
        foot.addWidget(reopen)
        foot.addWidget(close)
        v.addLayout(foot)

        self.setStyleSheet(_QSS)

    # --- behaviour -------------------------------------------------------

    def refresh(self) -> None:
        """Re-query macOS and update each row's ✓ / ✕ / ? status."""
        statuses = permissions.permission_status()
        for key, icon in self._icons.items():
            status = statuses.get(key)
            color = _OK if status is True else _BAD if status is False else _UNK
            mark = "✓" if status is True else "✕" if status is False else "?"
            icon.setText(mark)
            icon.setStyleSheet(f"color:{color}; font-weight:700;")

    def _on_dont_toggled(self, checked: bool) -> None:
        # Ticking suppresses the auto-popup for THIS version only; unticking clears
        # it so the window can show again. The menu-bar "Permissions…" item always
        # bypasses this, so it's never a dead end.
        update_user_settings(perm_popup_dismissed_version=__version__ if checked else "")

    def _quit_reopen(self) -> None:
        if updates.relaunch_macos_app():
            self.accept()
            if self._on_quit is not None:
                self._on_quit()  # quitting lets the detached helper reopen Spuk
        else:
            # Not a packaged app (dev / source) — nothing to relaunch; just close.
            self.accept()

    def present(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()


_QSS = """
#scene {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #8b5cf6, stop:0.5 #6d28d9, stop:1 #3b0764);
}
QLabel { color: #ffffff; }
#ghost {
    background: rgba(255, 255, 255, 0.20);
    border: 1px solid rgba(255, 255, 255, 0.35);
    border-radius: 13px; font-size: 21px;
}
#title { font-size: 16px; font-weight: 700; }
#intro { color: rgba(255, 255, 255, 0.82); font-size: 12px; }
#row {
    background: rgba(255, 255, 255, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 10px;
}
#rowtext { color: rgba(255, 255, 255, 0.90); font-size: 13px; }
#dot { font-size: 14px; }
QCheckBox#dont { color: rgba(255, 255, 255, 0.88); font-size: 12.5px; spacing: 8px; }
QPushButton#open, QPushButton#btn {
    color: #ffffff; font-size: 13px; font-weight: 600;
    background: rgba(255, 255, 255, 0.14);
    border: 1px solid rgba(255, 255, 255, 0.30);
    border-radius: 9px; padding: 6px 14px;
}
QPushButton#open:hover, QPushButton#btn:hover { background: rgba(255, 255, 255, 0.28); }
"""
