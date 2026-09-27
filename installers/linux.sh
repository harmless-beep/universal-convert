#!/usr/bin/env bash
# =====================================================================
# Universal Convert - Linux installer
# =====================================================================
# Adds the "Convert With..." entry to:
#   - GNOME Files (Nautilus)  -> ~/.local/share/nautilus/scripts
#   - KDE Dolphin             -> kio/servicemenus (Plasma 6) and
#                                kservices5/ServiceMenus (Plasma 5)
#   - other file managers     -> ~/.local/share/applications .desktop
# All of them run main.py out of a project-local .venv, so:
#   - no sudo, nothing system-wide
#   - no 'pip install --user' (fails on Debian/Ubuntu 23.04+ with
#     "externally managed environment" - the venv sidesteps that)
# Both file managers pass the FULL multi-selection in ONE invocation.
#
#   install:    bash installers/linux.sh
#   uninstall:  bash installers/linux.sh --uninstall
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MAIN_PY="$PROJECT_DIR/main.py"
REQS="$PROJECT_DIR/requirements.txt"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"

NAUTILUS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/nautilus/scripts"
# KDE Plasma 6 moved service menus to kio/servicemenus; Plasma 5 reads
# kservices5/ServiceMenus. Write both - they are cheap files.
DOLPHIN_DIR_6="${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus"
DOLPHIN_DIR_5="${XDG_DATA_HOME:-$HOME/.local/share}/kservices5/ServiceMenus"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
NAUTILUS_SCRIPT="$NAUTILUS_DIR/Convert With..."
DOLPHIN_DESKTOP_6="$DOLPHIN_DIR_6/universal-convert.desktop"
DOLPHIN_DESKTOP_5="$DOLPHIN_DIR_5/universal-convert.desktop"
LAUNCHER_DESKTOP="$DESKTOP_DIR/universal-convert.desktop"

info() { printf '\033[36m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m[OK]\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m[!!]\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m[XX]\033[0m %s\n' "$*"; exit 1; }

usage() {
  cat <<EOF
Universal Convert - Linux installer

  bash installers/linux.sh            install (builds .venv, registers the
                                      menus for the current user)
  bash installers/linux.sh --uninstall remove the menu entries
  bash installers/linux.sh --help     this text
EOF
}

for arg in "$@"; do
  case "$arg" in
    --uninstall) UNINSTALL=1 ;;
    -h|--help)   usage; exit 0 ;;
    *) fail "Unknown option: $arg (try --help)" ;;
  esac
done

[[ "$(uname -s)" == "Linux" ]] || fail "This script is for Linux. You are on $(uname -s)."

# ---------------------------------------------------------------- uninstall
if [[ "${UNINSTALL:-0}" == 1 ]]; then
  info "Removing context menu entries..."
  rm -f "$NAUTILUS_SCRIPT" "$DOLPHIN_DESKTOP_6" "$DOLPHIN_DESKTOP_5" "$LAUNCHER_DESKTOP"
  ok "Removed. (config kept; delete $VENV_DIR by hand if you want the space back)"
  exit 0
fi

[[ -f "$MAIN_PY" ]] || fail "main.py not found at $MAIN_PY - run this from the repository."

# ------------------------------------------------------------ 1. python3
info "Looking for Python 3 (3.9+, tkinter, venv)..."
PY3=""
if command -v python3 >/dev/null 2>&1; then
  PY3="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PY3="$(command -v python)"
fi
[[ -n "$PY3" ]] || fail "python3 not found. Install it with your package manager (e.g. sudo apt install python3 python3-tk)."
"$PY3" -c 'import sys; assert sys.version_info >= (3, 9)' 2>/dev/null \
  || fail "$PY3 is older than 3.9 - install a newer Python, then re-run."
"$PY3" -c 'import tkinter' 2>/dev/null \
  || fail "tkinter is missing, so the dialog could never open."$'\n'"         Debian/Ubuntu: sudo apt install python3-tk   |   Fedora: sudo dnf install python3-tkinter   |   Arch: sudo pacman -S tk"
"$PY3" -c 'import venv' 2>/dev/null \
  || fail "The venv module is missing - Debian/Ubuntu: sudo apt install python3-venv, then re-run."
ok "Python 3: $PY3"

# ------------------------------------------------------- 2. project-local venv
# Always rebuilt: idempotent, and a half-broken venv from an earlier run can
# never leak into a working install.
info "Creating $VENV_DIR ..."
rm -rf "$VENV_DIR"
if ! "$PY3" -m venv "$VENV_DIR"; then
  fail "python3 -m venv failed - Debian/Ubuntu: sudo apt install python3-venv, then re-run."
fi
[[ -x "$VENV_PY" ]] || fail "venv was created but $VENV_PY is missing."
ok "Virtual environment created"

info "Installing Pillow, pypdf, PyMuPDF into .venv ..."
if [[ -f "$REQS" ]]; then
  "$VENV_PY" -m pip install --quiet --disable-pip-version-check -r "$REQS" \
    || fail "pip install failed. Try: $VENV_PY -m pip install Pillow pypdf PyMuPDF"
else
  "$VENV_PY" -m pip install --quiet --disable-pip-version-check Pillow pypdf PyMuPDF \
    || fail "pip install failed."
fi
"$VENV_PY" -c 'import tkinter, PIL, pypdf, fitz' 2>/dev/null \
  || fail "The environment is still missing packages after install."$'\n'"         Try: $VENV_PY -m pip install Pillow pypdf PyMuPDF"
ok "Dependencies ready (Pillow, pypdf, PyMuPDF)"

# ------------------------------------------------------------ 3. LibreOffice
info "Checking LibreOffice..."
if command -v soffice >/dev/null 2>&1 || command -v libreoffice >/dev/null 2>&1; then
  ok "LibreOffice found."
else
  warn "LibreOffice not found - only needed for Office/PDF document conversions."
  warn "  Images and PDFs work without it. To add it: sudo apt install libreoffice"
fi

# ------------------------------------------------------- 4. Nautilus script
# The script file contains the venv python by absolute path; no PATH
# guessing happens at click time.
info "Installing Nautilus (GNOME Files) script..."
mkdir -p "$NAUTILUS_DIR"
cat > "$NAUTILUS_SCRIPT" <<EOF
#!/usr/bin/env bash
# Generated by the Universal Convert installer - passes the whole
# selection (as arguments) to the converter.
exec "$VENV_PY" "$MAIN_PY" "\$@"
EOF
chmod +x "$NAUTILUS_SCRIPT"
ok "Installed: $NAUTILUS_SCRIPT"

# ------------------------------------------------- 5. Dolphin service menus
DOLPHIN_CONTENT="[Desktop Entry]
Type=Service
X-KDE-ServiceTypes=KonqPopupMenu/Plugin
MimeType=application/pdf;image/jpeg;image/png;image/webp;image/gif;image/bmp;image/tiff;application/vnd.openxmlformats-officedocument.wordprocessingml.document;application/vnd.openxmlformats-officedocument.presentationml.presentation;application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;application/vnd.oasis.opendocument.text;application/vnd.oasis.opendocument.presentation;application/vnd.oasis.opendocument.spreadsheet;
Actions=universalConvert;
X-KDE-Priority=TopLevel

[Desktop Action universalConvert]
Name=Convert With...
Icon=convert
Exec=\"$VENV_PY\" \"$MAIN_PY\" %F"

info "Installing KDE Dolphin service menu..."
mkdir -p "$DOLPHIN_DIR_6" "$DOLPHIN_DIR_5"
printf '%s\n' "$DOLPHIN_CONTENT" > "$DOLPHIN_DESKTOP_6"
printf '%s\n' "$DOLPHIN_CONTENT" > "$DOLPHIN_DESKTOP_5"
ok "Installed: $DOLPHIN_DESKTOP_6 (Plasma 6)"
ok "Installed: $DOLPHIN_DESKTOP_5 (Plasma 5)"

# ---------------------------------------------------- 6. generic launcher
info "Installing a .desktop launcher (for other file managers / menus)..."
mkdir -p "$DESKTOP_DIR"
cat > "$LAUNCHER_DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Universal Convert
Comment=Convert images, PDFs and Office documents
Exec="$VENV_PY" "$MAIN_PY" %F
Icon=convert
Terminal=false
Categories=Utility;Graphics;
MimeType=application/pdf;image/jpeg;image/png;image/webp;image/gif;image/bmp;image/tiff;
EOF
ok "Installed: $LAUNCHER_DESKTOP"

# ------------------------------------------------------------- 7. refresh
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi
if command -v kbuildsycoca5 >/dev/null 2>&1; then
  kbuildsycoca5 --noincremental >/dev/null 2>&1 || true
elif command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi
if command -v nautilus >/dev/null 2>&1; then
  warn "Restart Nautilus to see the new script:  nautilus -q"
fi

echo
info "Install complete."
echo "  GNOME Files: right-click -> Scripts -> 'Convert With...'"
echo "  Dolphin:     right-click -> Convert With..."
echo "  CLI:         $VENV_PY $MAIN_PY photo.jpg"
