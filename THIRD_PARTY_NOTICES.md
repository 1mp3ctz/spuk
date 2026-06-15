# Third-Party Notices

Spuk's own source code is licensed under the **MIT License** (see [LICENSE](LICENSE)).

Spuk depends on, and its downloadable binaries (`Spuk.app` / `Spuk.exe`) bundle,
the third-party components below. Each remains under its own license; those
licenses are preserved here and apply to the bundled copies. This file is provided
to comply with their attribution and notice requirements.

| Component | License | Notes |
|-----------|---------|-------|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | Whisper inference |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | MIT | inference engine |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | MIT | microphone capture (PortAudio) |
| [PortAudio](http://www.portaudio.com/) | MIT-style | audio I/O (via sounddevice) |
| [NumPy](https://numpy.org/) | BSD-3-Clause | arrays |
| [tokenizers](https://github.com/huggingface/tokenizers) | Apache-2.0 | tokenizer |
| [huggingface-hub](https://github.com/huggingface/huggingface_hub) | Apache-2.0 | model download |
| [onnxruntime](https://github.com/microsoft/onnxruntime) | MIT | VAD inference |
| [Pillow](https://python-pillow.org/) | MIT-CMU (HPND) | icon generation |
| [pyperclip](https://github.com/asweigart/pyperclip) | BSD-3-Clause | clipboard |
| [PyAV](https://github.com/PyAV-Org/PyAV) | BSD-3-Clause | audio decoding |
| [FFmpeg](https://ffmpeg.org/) (bundled in PyAV) | **LGPL-2.1+** | media libraries |
| [pynput](https://github.com/moses-palmer/pynput) | **LGPL-3.0** | global hotkey + key injection |
| [pystray](https://github.com/moses-palmer/pystray) | **LGPL-3.0** | system-tray icon (optional `--tray`) |
| [PySide6 / Qt](https://www.qt.io/) | **LGPL-3.0** (or Qt commercial) | floating-bar UI |
| [shiboken6](https://wiki.qt.io/Qt_for_Python) | **LGPL-3.0** | PySide6 binding |
| [Whisper model weights](https://github.com/openai/whisper) (downloaded at first run) | MIT | speech model |

## About the LGPL components (Qt/PySide6, pynput, pystray, FFmpeg)

These libraries are licensed under the **LGPL**. Distributing them — including
inside the prebuilt `Spuk.app` / `Spuk.exe` — is permitted, and Spuk complies
because:

1. **The full source of Spuk is public** (MIT) at <https://github.com/1mp3ctz/spuk>,
   and anyone can rebuild the app with the build scripts in `packaging/`.
2. The binaries are **one-folder builds**, so the LGPL libraries ship as separate,
   replaceable files (`.dylib` / `.dll` / Qt frameworks) next to the executable —
   a user may substitute their own compatible build of those libraries.
3. This notice identifies each LGPL component and links to its source.

> **If you ever distribute Spuk as a *closed-source / proprietary* product**, the
> LGPL terms still apply to these libraries — you must keep them dynamically
> linked/replaceable and ship this notice + the LGPL license texts, **or** obtain a
> commercial Qt license from The Qt Company. This is the main thing to clear with a
> lawyer before any closed-source commercial sale. While Spuk stays open source
> under MIT, you are already compliant.

Full license texts for each component are available in their linked repositories
and within the installed Python packages' `*.dist-info/` metadata.
