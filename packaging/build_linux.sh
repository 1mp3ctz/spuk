#!/usr/bin/env bash
# Build native Linux packages for Spuk (x86_64 / amd64 only).
#
#   bash packaging/build_linux.sh
#
# Runs ON a Linux x86_64 host (PyInstaller is NOT a cross-compiler — you cannot
# build this from macOS/Windows, exactly like build_macos.sh / build_windows.ps1).
# Produces, under dist/:
#   * Spuk/                                 the PyInstaller onedir bundle
#   * spuk_<ver>_amd64.deb                  Debian/Ubuntu package
#   * spuk-<ver>.x86_64.rpm                 Fedora/RHEL/openSUSE package
#   * spuk-<ver>-linux-x86_64.tar.gz        portable tarball + install.sh/uninstall.sh
#
# No AppImage / Flatpak: their sandboxes block the global hotkey (read /dev/input)
# and the uinput paste injection Spuk relies on. We ship FHS packages instead.
#
# Prereqs on the Linux build host:
#   * Python 3.11 + uv   (see AGENTS.md — the repo pins 3.11)
#   * fpm                (Ruby gem: `gem install --no-document fpm`)
#   * rpm / rpmbuild     (so fpm can emit the .rpm: `apt install rpm` / `dnf install rpm-build`)
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# ── Package metadata ────────────────────────────────────────────────────────
PKG_NAME="spuk"
MAINTAINER="Viktor Kotowski"
LICENSE="MIT"
HOMEPAGE="https://github.com/1mp3ctz/spuk"
DESCRIPTION="Private, local, free push-to-talk dictation (on-device Whisper)."
ARCH_DEB="amd64"
ARCH_RPM="x86_64"

# ── Runtime dependencies ────────────────────────────────────────────────────
# The PyInstaller bundle ships Python + PySide6 + Qt, but Qt's xcb platform
# plugin dynamically loads SYSTEM libraries that must be present on the user's
# box. Keep these here so they're trivial to adjust after the first real Linux
# test (a missing lib shows up as a Qt "could not load the xcb platform plugin"
# error at launch on a clean machine).
#
# .deb: comma-separated Depends. Clipboard tools are an alternative (either works
# for pyperclip); ydotool is a Wayland-only nicety -> Recommends.
DEB_DEPENDS="libportaudio2, libxkbcommon0, libegl1, libgl1, libfontconfig1, libxcb-cursor0, wl-clipboard | xclip"
DEB_RECOMMENDS="ydotool"

# .rpm: space/comma-separated Requires (rpm can't express the 'a | b' clipboard
# alternative cleanly, so the clipboard tools + ydotool go in weak deps instead).
RPM_REQUIRES="portaudio libxkbcommon mesa-libEGL mesa-libGL fontconfig xcb-util-cursor"
RPM_RECOMMENDS="wl-clipboard xclip ydotool"   # Recommends: weak deps, one per --rpm-tag

# ── Resolve version from pyproject.toml (do NOT hardcode) ───────────────────
VERSION="$(grep -m1 -E '^[[:space:]]*version[[:space:]]*=' "${ROOT}/pyproject.toml" \
    | sed -E 's/.*=[[:space:]]*"([^"]+)".*/\1/')"
if [ -z "${VERSION}" ]; then
    echo "ERROR: could not parse version from pyproject.toml" >&2
    exit 1
fi
echo "==> Spuk version: ${VERSION}"

# ── Required tooling check (actionable errors) ──────────────────────────────
missing=0
if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: 'uv' not found. Install it: https://docs.astral.sh/uv/  (the repo pins Python 3.11 via uv)." >&2
    missing=1
fi
if ! command -v fpm >/dev/null 2>&1; then
    echo "ERROR: 'fpm' not found. Install it:  gem install --no-document fpm   (needs Ruby)." >&2
    echo "       fpm also needs 'rpm'/'rpmbuild' on PATH to emit the .rpm:  apt install rpm  /  dnf install rpm-build" >&2
    missing=1
fi
if [ "${missing}" -ne 0 ]; then
    exit 1
fi
# rpmbuild is only needed for the .rpm; warn (don't abort) so the .deb + tarball
# still build on a host without it.
RPM_OK=1
if ! command -v rpmbuild >/dev/null 2>&1; then
    echo "WARNING: 'rpmbuild' not found — the .rpm will be SKIPPED. Install 'rpm' (Debian) / 'rpm-build' (Fedora) to enable it." >&2
    RPM_OK=0
fi

# ── 1. Clean previous artifacts ─────────────────────────────────────────────
# The repo lives on exFAT during dev, where macOS scatters AppleDouble "._*"
# sidecar files; strip them first so tar/fpm don't pick them up (mirrors
# build_macos.sh). Harmless no-op on a native Linux checkout.
echo "==> Cleaning previous build artifacts…"
find build dist pkgroot -name '._*' -delete 2>/dev/null || true
rm -rf build dist pkgroot

# ── 2. PyInstaller onedir bundle (dist/Spuk/) ───────────────────────────────
echo "==> Building dist/Spuk/ with PyInstaller (Python 3.11 env)…"
UV_LINK_MODE=copy uv run --with pyinstaller pyinstaller \
    --clean --noconfirm --workpath build/pyi --distpath dist \
    packaging/spuk.spec

if [ ! -x "dist/Spuk/Spuk" ]; then
    echo "ERROR: expected dist/Spuk/Spuk after PyInstaller, but it's missing." >&2
    exit 1
fi

# ── 3. Generate PNG icons from the 1024px master (pure Pillow, no sips) ─────
# hicolor sizes; 48/128/256 are the ticket minimum, the rest round out the set.
echo "==> Generating PNG icons from packaging/icon-1024.png…"
ICON_SIZES="16 32 48 64 128 256 512"
ICON_OUT_DIR="build/icons"
rm -rf "${ICON_OUT_DIR}"
mkdir -p "${ICON_OUT_DIR}"
SPUK_ICON_SIZES="${ICON_SIZES}" SPUK_ICON_OUT="${ICON_OUT_DIR}" \
UV_LINK_MODE=copy uv run --with pillow python - <<'PY'
import os
from pathlib import Path

from PIL import Image

here = Path("packaging")
master_path = here / "icon-1024.png"
if not master_path.exists():
    raise SystemExit(f"icon master not found: {master_path}")

out_dir = Path(os.environ["SPUK_ICON_OUT"])
sizes = [int(s) for s in os.environ["SPUK_ICON_SIZES"].split()]

master = Image.open(master_path).convert("RGBA")
for size in sizes:
    dest = out_dir / f"{size}.png"
    master.resize((size, size), Image.LANCZOS).save(dest)
    print(f"  ✓ {size}x{size} -> {dest}")
PY

# ── 4. Assemble the FHS staging root (pkgroot/) ─────────────────────────────
#   /opt/spuk/Spuk                                   (bundle exe + libs)
#   /usr/bin/spuk            -> /opt/spuk/Spuk        (relative symlink)
#   /usr/share/applications/spuk.desktop
#   /usr/share/icons/hicolor/<size>/apps/spuk.png
echo "==> Assembling FHS staging root pkgroot/…"
PKGROOT="${ROOT}/pkgroot"
rm -rf "${PKGROOT}"
mkdir -p "${PKGROOT}/opt" \
         "${PKGROOT}/usr/bin" \
         "${PKGROOT}/usr/share/applications"

cp -a "dist/Spuk" "${PKGROOT}/opt/spuk"

# Relative symlink so it stays valid regardless of install prefix.
ln -s "../../opt/spuk/Spuk" "${PKGROOT}/usr/bin/spuk"

cp "packaging/linux/spuk.desktop" "${PKGROOT}/usr/share/applications/spuk.desktop"

for size in ${ICON_SIZES}; do
    dest_dir="${PKGROOT}/usr/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "${dest_dir}"
    cp "${ICON_OUT_DIR}/${size}.png" "${dest_dir}/spuk.png"
done

# Strip any AppleDouble junk that may have ridden along from an exFAT checkout.
find "${PKGROOT}" -name '._*' -delete 2>/dev/null || true

# ── 5. Build the .deb and .rpm with fpm ─────────────────────────────────────
DEB_FILE="dist/${PKG_NAME}_${VERSION}_${ARCH_DEB}.deb"
RPM_FILE="dist/${PKG_NAME}-${VERSION}.${ARCH_RPM}.rpm"

# Shared fpm args (input is the staging dir; maps pkgroot/<path> -> /<path>).
fpm_common=(
    --input-type dir
    --chdir "${PKGROOT}"
    --name "${PKG_NAME}"
    --version "${VERSION}"
    --maintainer "${MAINTAINER}"
    --license "${LICENSE}"
    --url "${HOMEPAGE}"
    --description "${DESCRIPTION}"
    --after-install "packaging/linux/postinst"
    --after-remove "packaging/linux/postrm"
    --force
)

echo "==> Building ${DEB_FILE}…"
fpm "${fpm_common[@]}" \
    --output-type deb \
    --architecture "${ARCH_DEB}" \
    --depends "${DEB_DEPENDS}" \
    --deb-recommends "${DEB_RECOMMENDS}" \
    --package "${DEB_FILE}" \
    .

if [ "${RPM_OK}" -eq 1 ]; then
    echo "==> Building ${RPM_FILE}…"
    # rpm can't express 'a | b' alternatives, so clipboard tools + ydotool are
    # weak deps (Recommends) rather than hard Requires.
    rpm_weak_args=()
    for dep in ${RPM_RECOMMENDS}; do
        rpm_weak_args+=(--rpm-tag "Recommends: ${dep}")
    done
    fpm "${fpm_common[@]}" \
        --output-type rpm \
        --architecture "${ARCH_RPM}" \
        --depends "$(echo "${RPM_REQUIRES}" | tr ' ' '\n' | paste -sd, -)" \
        "${rpm_weak_args[@]}" \
        --package "${RPM_FILE}" \
        .
else
    echo "==> Skipping .rpm (rpmbuild missing)."
fi

# ── 6. Portable tarball with install.sh / uninstall.sh ──────────────────────
echo "==> Building the portable tarball…"
TARBALL="dist/${PKG_NAME}-${VERSION}-linux-x86_64.tar.gz"
STAGE="build/tarball/${PKG_NAME}-${VERSION}-linux-x86_64"
rm -rf "build/tarball"
mkdir -p "${STAGE}"

# Ship the bundle plus the same desktop entry + icons so install.sh can lay them
# out identically to the packages.
cp -a "dist/Spuk" "${STAGE}/Spuk"
mkdir -p "${STAGE}/share/applications" "${STAGE}/share/icons"
cp "packaging/linux/spuk.desktop" "${STAGE}/share/applications/spuk.desktop"
for size in ${ICON_SIZES}; do
    dest_dir="${STAGE}/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "${dest_dir}"
    cp "${ICON_OUT_DIR}/${size}.png" "${dest_dir}/spuk.png"
done

# install.sh — replicates the FHS layout into the live system (needs sudo).
cat > "${STAGE}/install.sh" <<'INSTALL_SH'
#!/usr/bin/env bash
# Install Spuk from this portable tarball into the system (FHS layout).
#   sudo ./install.sh
# Mirrors what the .deb/.rpm do: bundle in /opt/spuk, launcher symlink in
# /usr/bin, desktop entry + hicolor icons under /usr/share.
set -euo pipefail

PREFIX_OPT="/opt/spuk"
BIN_LINK="/usr/bin/spuk"
APP_DIR="/usr/share/applications"
ICON_ROOT="/usr/share/icons/hicolor"

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run with sudo:  sudo ./install.sh" >&2
    exit 1
fi

here="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing bundle to ${PREFIX_OPT}…"
rm -rf "${PREFIX_OPT}"
mkdir -p "${PREFIX_OPT}"
cp -a "${here}/Spuk/." "${PREFIX_OPT}/"

echo "==> Linking ${BIN_LINK} -> ${PREFIX_OPT}/Spuk…"
ln -sf "${PREFIX_OPT}/Spuk" "${BIN_LINK}"

echo "==> Installing desktop entry + icons…"
mkdir -p "${APP_DIR}"
cp "${here}/share/applications/spuk.desktop" "${APP_DIR}/spuk.desktop"
cp -a "${here}/share/icons/hicolor/." "${ICON_ROOT}/"

command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -f -t -q "${ICON_ROOT}" >/dev/null 2>&1 || true
command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database -q "${APP_DIR}" >/dev/null 2>&1 || true

# Offer to add the invoking user to the 'input' group (same as the package postinst).
target_user="${SUDO_USER:-}"
if [ -n "${target_user}" ] && [ "${target_user}" != "root" ] && getent group input >/dev/null 2>&1; then
    if id -nG "${target_user}" | tr ' ' '\n' | grep -qx "input"; then
        :
    else
        usermod -aG input "${target_user}" >/dev/null 2>&1 && \
            echo "==> Added '${target_user}' to the 'input' group." || true
    fi
fi

cat <<'NOTE'

────────────────────────────────────────────────────────────────────────────
 Spuk installed.  One-time Linux setup so the hotkey + paste work:

 Spuk reads your keyboard from /dev/input and injects paste via /dev/uinput,
 both of which require membership in the 'input' group:
     sudo usermod -aG input "$USER"
 then LOG OUT and back in (group changes only apply to new sessions).

 Wayland users may also install 'ydotool' (+ ydotoold) as an alternative paste
 path. A clipboard tool is required so text can be set:
     • Wayland:  wl-clipboard      • X11:  xclip  or  xsel

 Run with:  spuk
────────────────────────────────────────────────────────────────────────────
NOTE
INSTALL_SH
chmod +x "${STAGE}/install.sh"

# uninstall.sh — reverse of install.sh (leaves the 'input' group membership).
cat > "${STAGE}/uninstall.sh" <<'UNINSTALL_SH'
#!/usr/bin/env bash
# Remove a tarball-installed Spuk.  sudo ./uninstall.sh
# Does NOT touch your 'input' group membership (yours to manage).
set -euo pipefail

PREFIX_OPT="/opt/spuk"
BIN_LINK="/usr/bin/spuk"
APP_DIR="/usr/share/applications"
ICON_ROOT="/usr/share/icons/hicolor"

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run with sudo:  sudo ./uninstall.sh" >&2
    exit 1
fi

echo "==> Removing ${PREFIX_OPT}…"
rm -rf "${PREFIX_OPT}"

if [ -L "${BIN_LINK}" ]; then
    rm -f "${BIN_LINK}"
fi

rm -f "${APP_DIR}/spuk.desktop"
for size in 16 32 48 64 128 256 512; do
    rm -f "${ICON_ROOT}/${size}x${size}/apps/spuk.png"
done

command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -f -t -q "${ICON_ROOT}" >/dev/null 2>&1 || true
command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database -q "${APP_DIR}" >/dev/null 2>&1 || true

echo "==> Spuk removed. (Your 'input' group membership was left untouched.)"
UNINSTALL_SH
chmod +x "${STAGE}/uninstall.sh"

find "build/tarball" -name '._*' -delete 2>/dev/null || true
tar -czf "${TARBALL}" -C "build/tarball" "${PKG_NAME}-${VERSION}-linux-x86_64"

# ── 7. Report ───────────────────────────────────────────────────────────────
echo
echo "==> Done. Artifacts in dist/:"
ls -1 "${DEB_FILE}" 2>/dev/null && echo "    (Debian/Ubuntu:  sudo apt install ./${DEB_FILE##*/})"
if [ "${RPM_OK}" -eq 1 ]; then
    ls -1 "${RPM_FILE}" 2>/dev/null && echo "    (Fedora/RHEL:    sudo dnf install ./${RPM_FILE##*/})"
fi
ls -1 "${TARBALL}" 2>/dev/null && echo "    (Portable:       tar xzf ${TARBALL##*/} && cd ${PKG_NAME}-${VERSION}-linux-x86_64 && sudo ./install.sh)"
echo
echo "    First launch downloads the Whisper model (~480MB) to ~/.cache/huggingface."
echo "    Reminder: users must be in the 'input' group (then re-login) for the hotkey."
