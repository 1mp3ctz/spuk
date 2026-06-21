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

import logging
import threading

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QRect,
    Qt,
    QThread,
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
from .hotkey_format import combo_to_label
from .languages import display_name
from .screenshot_gesture import start_if_enabled as _start_screenshot

log = logging.getLogger("spuk.ui_bar")

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
    combo_captured = Signal(str)   # a Settings hotkey capture finished
    hotkey_changed = Signal()      # bindings changed -> refresh labels
    live_partial = Signal(str)     # partial Apple speech result (GCD → Qt main)
    live_final = Signal(str)       # final Apple speech result (GCD → Qt main)
    live_start = Signal()          # Fn pressed: start Apple engine
    live_stop = Signal()           # Fn released: stop Apple engine


class _MainThreadRunner(QObject):
    """Run a callable on the Qt main thread, blocking the caller until it finishes.

    macOS requires pynput's keyboard injection (it queries the keyboard layout via
    HIToolbox's Text Input Source Manager) to run on the main thread; calling it
    from the hotkey-listener thread or the UI's "Hold to talk" worker trips a
    main-queue assertion and the process dies with SIGTRAP. paste.py calls
    :meth:`run` to marshal that injection here. This object lives on the main
    thread, so its queued slot executes there even when emit() comes from a worker.
    """

    _submit = Signal(object)  # carries (fn, result-dict, done-event)

    def __init__(self) -> None:
        super().__init__()
        self._submit.connect(self._run_job)  # auto-queued across threads

    def _run_job(self, job) -> None:
        fn, result, done = job
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - surfaced to the caller
            result["error"] = exc
        finally:
            done.set()

    def run(self, fn):
        """Execute ``fn`` on the main thread; return its result (re-raising on error)."""
        if QThread.currentThread() is self.thread():
            return fn()  # already on the main thread — don't deadlock on done.wait()
        result: dict = {}
        done = threading.Event()
        self._submit.emit((fn, result, done))
        # Bounded wait: if the event loop has stopped (e.g. mid-quit) the daemon
        # worker must not hang forever — the paste is simply dropped.
        if not done.wait(timeout=10.0):
            raise RuntimeError("main-thread paste timed out")
        if "error" in result:
            raise result["error"]
        return result.get("value")


class SpukBar(QWidget):
    def __init__(self, config: Config, core: SpukCore, signals: "CoreSignals") -> None:
        super().__init__()
        self._cfg = config
        self._core = core
        self._sig = signals
        self._expanded = False
        self._recording = False  # tracks core recording state so a click can stop it
        self._open_window = None  # set by run_bar; clicking the pill opens the window

        # Fn live-dictation controller (macOS only). Owns the Apple engine
        # lifecycle so a hot mic can always be stopped exactly once (see
        # fn_dictation.FnDictationController).
        self._fn = None
        import platform as _plt
        if _plt.system() == "Darwin":
            from .fn_dictation import FnDictationController
            from .live_insert import LiveInserter

            def _make_engine():
                from .apple_speech import AppleSpeechEngine

                return AppleSpeechEngine(
                    on_partial=self._sig.live_partial.emit,
                    on_final=self._sig.live_final.emit,
                    on_error=lambda e: log.warning("Apple speech error: %s", e),
                )

            self._fn = FnDictationController(LiveInserter(), _make_engine)

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

        self._hint = QLabel(self._hint_text())
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
        self._sig.hotkey_changed.connect(self._on_hotkey_changed)
        # Apple speech live wiring (macOS Fn dictation).
        self._sig.live_partial.connect(self._on_live_partial)
        self._sig.live_final.connect(self._on_live_final)
        self._sig.live_start.connect(self._on_fn_press)
        self._sig.live_stop.connect(self._on_fn_release)

    def _on_recording(self, active: bool) -> None:
        self._recording = active
        self._dot.setStyleSheet(
            f"color:{'#fca5a5' if active else '#86efac'}; font-size:14px;"
        )
        # While recording, the pill doubles as a Stop button (see _on_pill_clicked).
        self._status.setText("recording… (click to stop)" if active else "ready")
        self.setCursor(Qt.PointingHandCursor if active else Qt.ArrowCursor)

    def _on_language(self, lang: str) -> None:
        self._lang_code.setText(lang.upper())
        for code, b in self._lang_buttons.items():
            b.setChecked(code == lang)

    def _hint_text(self) -> str:
        verb = "Hold" if self._core.hotkey.mode == "push_to_talk" else "Press"
        return f"{verb} {combo_to_label(self._core.hotkey.key)} to dictate · ⚙ for settings"

    def _on_hotkey_changed(self) -> None:
        self._hint.setText(self._hint_text())

    def _on_live_partial(self, text: str) -> None:
        if self._fn is not None:
            self._fn.on_partial(text)

    def _on_live_final(self, text: str) -> None:
        if self._fn is not None:
            self._fn.on_final(text)

    def _on_fn_press(self) -> None:
        enabled = getattr(self, "_apple_enabled", None)
        if enabled is not None:
            if not enabled[0]:
                return
        elif not self._cfg.apple_speech.enabled:
            return
        if self._fn is not None:
            self._fn.on_press()

    def _on_fn_release(self) -> None:
        if self._fn is not None:
            self._fn.on_release()

    def stop_fn_dictation(self) -> None:
        """Stop a live Fn-dictation engine if running (menu-bar toggle-off / quit)."""
        if self._fn is not None:
            self._fn.stop()

    def _dictate_released(self) -> None:
        # Transcribe+paste blocks ~1s — keep it off the UI thread.
        threading.Thread(target=self._core.finish_recording, daemon=True).start()

    def _on_pill_clicked(self) -> None:
        """Clicking the always-visible pill stops a recording in progress — the
        guaranteed escape hatch when the global hotkey can't (e.g. a hands-free
        latch wedged by a dropped modifier release). When idle, it opens Settings.
        """
        if self._recording:
            self._stop_recording()
        else:
            self._open_settings()

    def _stop_recording(self) -> None:
        # force_stop clears wedged hotkey state then transcribes+pastes; it can
        # block ~1s, so keep it off the UI thread.
        threading.Thread(target=self._core.force_stop, daemon=True).start()

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

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        # Clicks on child buttons (gear / Hold-to-talk / language chips) are
        # consumed by them; this fires only for clicks on the pill background.
        self._on_pill_clicked()
        super().mousePressEvent(event)

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


def _install_menubar(
    app,
    on_open,
    on_quit,
    on_permissions=None,
    on_stop_recording=None,
    on_toggle_apple_speech=None,
    apple_speech_enabled_fn=None,
) -> "QSystemTrayIcon | None":
    """Add a menu-bar (system-tray) icon to stop a recording, open Settings, the
    macOS Permissions helper, or quit Spuk.

    The pill has no window chrome and Spuk runs with no Dock icon, so this is the
    user's way to reach Settings and to quit. ``on_stop_recording`` adds an
    always-available "Stop recording" item — a hotkey-independent way to shut the
    mic off if a hands-free recording can't be stopped from the keyboard.
    ``on_permissions`` adds a "Permissions…" item (macOS only) so the helper is
    always reachable. ``on_toggle_apple_speech`` and ``apple_speech_enabled_fn``
    add an "Apple Dictation (Fn)" checkbox item (macOS only).
    Returns the icon (kept alive by `app`) or None if the platform has no system tray.
    """
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None

    menu = QMenu()
    header = menu.addAction("Spuk")
    header.setEnabled(False)
    menu.addSeparator()
    if on_stop_recording is not None:
        stop_action = menu.addAction("Stop recording")
        stop_action.triggered.connect(lambda: on_stop_recording())
    open_action = menu.addAction("Settings…")
    open_action.triggered.connect(lambda: on_open())
    if on_toggle_apple_speech is not None:
        apple_action = menu.addAction("Apple Dictation (Fn)")
        apple_action.setCheckable(True)
        apple_action.setChecked(apple_speech_enabled_fn() if apple_speech_enabled_fn else False)
        apple_action.triggered.connect(lambda checked: on_toggle_apple_speech(checked))
    if on_permissions is not None:
        perms_action = menu.addAction("Permissions…")
        perms_action.triggered.connect(lambda: on_permissions())
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

    # macOS: route pynput's keyboard injection through the main thread. pynput
    # touches the main-thread-only Text Input Source Manager, so injecting the
    # paste keystroke from the hotkey-listener / UI worker thread crashes the
    # process with SIGTRAP. Installed before the hotkey backend starts so the very
    # first dictation is safe. No-op elsewhere (Windows/Linux don't need it).
    import platform

    if platform.system() == "Darwin":
        from .paste import set_main_thread_runner

        app._spuk_main_runner = _MainThreadRunner()  # type: ignore[attr-defined]  # strong ref
        set_main_thread_runner(app._spuk_main_runner.run)  # type: ignore[attr-defined]

    # One shared signal bus: the core fires these (from the hotkey thread) and
    # both the floating bar and the main window listen on them.
    signals = CoreSignals()
    core.on_recording_change = signals.recording.emit
    core.on_language_change = signals.language.emit
    core.on_languages_change = signals.languages.emit
    core.on_transcript = signals.transcript.emit
    core.on_combo_captured = signals.combo_captured.emit
    core.on_hotkey_change = signals.hotkey_changed.emit

    # The floating pill is the primary, always-on UI.
    bar = SpukBar(config, core, signals)
    bar.show()

    # The Settings window is created up front but stays hidden — it only appears
    # when the user clicks the pill's ⚙ button (or the menu-bar 'Settings…').
    from .ui_window import SpukWindow

    window = SpukWindow(config, core, signals)
    bar.set_open_window(window.present)

    # Start the global hotkey backend. Core owns the handle (pynput on
    # macOS/Windows, evdev on Linux) so it can swap it live when the user
    # changes a hotkey in Settings.
    core.start_input()

    # Apple Dictation (Fn) toggle: runtime flag so the menu-bar checkbox takes
    # effect immediately without a relaunch. Defined here (before the Fn callbacks)
    # so the closures below can reference it. Also stored on bar so _on_fn_press
    # can check it at runtime instead of the stale startup config value.
    _apple_enabled = [config.apple_speech.enabled]
    bar._apple_enabled = _apple_enabled  # type: ignore[attr-defined]

    # Fn dictation callbacks: marshal through Qt signals so engine start/stop
    # runs on the main thread (same as where pynput paste injection must run).
    # Always armed on Darwin — the _apple_enabled[0] runtime check inside each
    # callback means toggling the menu-bar checkbox takes effect immediately.
    _fn_press_cb = None
    _fn_release_cb = None
    if platform.system() == "Darwin":
        def _fn_press_cb() -> None:  # noqa: E306
            if _apple_enabled[0]:
                signals.live_start.emit()

        def _fn_release_cb() -> None:  # noqa: E306
            if _apple_enabled[0]:
                signals.live_stop.emit()

    _screenshot_tap = _start_screenshot(
        config,
        on_fn_press=_fn_press_cb,
        on_fn_release=_fn_release_cb,
    )

    def quit_app() -> None:
        # Quit cleanly: stop the Qt event loop and let the process shut down
        # normally. The pynput listener runs on a DAEMON thread, so nothing blocks
        # exit — and a clean shutdown (rather than a forced os._exit) lets Python
        # release faster-whisper's multiprocessing semaphore and tear the macOS
        # CGEventTap down in order, avoiding the "Python quit unexpectedly" trap
        # the hard exit caused.
        if _screenshot_tap:
            _screenshot_tap.stop()
        bar.stop_fn_dictation()
        app.quit()

    window.set_quit(quit_app)

    def stop_recording() -> None:
        # Always-available, hotkey-independent mic kill switch. force_stop clears
        # any wedged hotkey state then transcribes+pastes; it can block, so thread it.
        threading.Thread(target=core.force_stop, daemon=True).start()

    # macOS: a Permissions helper (deep links to the 3 Privacy panes with live
    # status). Auto-shown after an update / when a grant is missing, and always
    # reachable from the menu bar so "don't show again" is never a dead end. The
    # ad-hoc signature changes every update, so macOS drops the grants each time.
    open_permissions = None
    if platform.system() == "Darwin":
        from . import __version__
        from . import permissions as _perms
        from .settings_store import load_user_settings
        from .ui_permissions import PermissionsDialog

        def open_permissions() -> None:  # noqa: F811 - macOS-only definition
            app._spuk_perms_dialog = PermissionsDialog(on_quit=quit_app)  # type: ignore[attr-defined]
            app._spuk_perms_dialog.present()  # type: ignore[attr-defined]

    def toggle_apple_speech(checked: bool) -> None:
        from .settings_store import update_user_settings
        _apple_enabled[0] = checked
        update_user_settings(apple_speech_enabled=checked)
        if not checked:
            # Disabling while the mic is live must stop it now, not on the next
            # Fn press — otherwise the toggle can't shut off a streaming mic.
            bar.stop_fn_dictation()

    # Menu-bar icon (Stop recording / Settings / Apple Dictation / Permissions / Quit).
    # Held by the app so it isn't GC'd.
    app._spuk_tray = _install_menubar(  # type: ignore[attr-defined]
        app,
        window.present,
        quit_app,
        open_permissions,
        stop_recording,
        on_toggle_apple_speech=toggle_apple_speech if platform.system() == "Darwin" else None,
        apple_speech_enabled_fn=lambda: _apple_enabled[0] if platform.system() == "Darwin" else False,
    )
    app._spuk_window = window  # type: ignore[attr-defined]  # keep a strong ref

    # Auto-show the permissions helper ONLY when a grant is actually missing (first
    # run / fresh machine). Stable signing keeps grants across updates, so a version
    # bump alone no longer triggers it. Always reachable from the menu bar.
    if platform.system() == "Darwin":
        saved = load_user_settings()
        if _perms.should_show_permissions(
            statuses=_perms.permission_status(),
            dismissed_version=saved.get("perm_popup_dismissed_version"),
            current_version=__version__,
        ):
            app._spuk_perms_dialog = PermissionsDialog(on_quit=quit_app)  # type: ignore[attr-defined]
            app._spuk_perms_dialog.show()  # type: ignore[attr-defined]

    # Warm the model off the UI thread so the UI appears immediately.
    def _warm() -> None:
        core.warm()
        signals.ready.emit()

    threading.Thread(target=_warm, daemon=True).start()

    app.exec()
