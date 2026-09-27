#!/usr/bin/env bash
# =====================================================================
# Universal Convert - macOS installer
# =====================================================================
# Creates a Finder Quick Action ("Convert With...") that runs main.py
# out of a project-local .venv. Everything lives inside the project
# folder plus one wrapper in ~/.local/bin - no sudo, nothing in
# /usr/local, no prompts, and the system Python is never touched
# (pip's "externally managed environment" errors cannot happen here).
#
#   install:             bash installers/macos.sh
#   also LibreOffice:    bash installers/macos.sh --install-libreoffice
#   uninstall:           bash installers/macos.sh --uninstall
#   help:                bash installers/macos.sh --help
#
# The Quick Action appears under right-click -> Quick Actions (older
# macOS: Services) and passes the whole multi-selection to main.py in
# ONE invocation, so no IPC aggregation is needed on this OS.
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MAIN_PY="$PROJECT_DIR/main.py"
REQS="$PROJECT_DIR/requirements.txt"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"
WRAPPER="$HOME/.local/bin/universal-convert"

SERVICES_DIR="$HOME/Library/Services"
WORKFLOW_NAME="Convert With....workflow"
WORKFLOW_DIR="$SERVICES_DIR/$WORKFLOW_NAME"
PLACEHOLDER="@@UC_LAUNCHER@@"

info() { printf '\033[36m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m[OK]\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m[!!]\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m[XX]\033[0m %s\n' "$*"; exit 1; }

usage() {
  cat <<EOF
Universal Convert - macOS installer

  bash installers/macos.sh                   install (builds .venv, registers the
                                             Finder Quick Action)
  bash installers/macos.sh --install-libreoffice
                                             also install LibreOffice via Homebrew
                                             when it is missing
  bash installers/macos.sh --uninstall       remove the Quick Action + wrapper
  bash installers/macos.sh --help            this text
EOF
}

UNINSTALL=0
INSTALL_LO=0
for arg in "$@"; do
  case "$arg" in
    --uninstall)          UNINSTALL=1 ;;
    --install-libreoffice) INSTALL_LO=1 ;;
    -h|--help)            usage; exit 0 ;;
    *) fail "Unknown option: $arg (try --help)" ;;
  esac
done

[[ "$(uname -s)" == "Darwin" ]] || fail "This script is for macOS. You are on $(uname -s)."

# ---------------------------------------------------------------- uninstall
if [[ "$UNINSTALL" == 1 ]]; then
  info "Removing Quick Action..."
  rm -rf "$WORKFLOW_DIR"
  rm -f "$WRAPPER"
  /System/Library/CoreServices/pbs -flush 2>/dev/null || true
  # Files an older version of this installer may have left behind.
  if [[ -e /usr/local/bin/universal-convert || -e /usr/local/bin/universal-convert-python ]]; then
    rm -f /usr/local/bin/universal-convert /usr/local/bin/universal-convert-python 2>/dev/null \
      || warn "Old /usr/local/bin wrappers need sudo: sudo rm -f /usr/local/bin/universal-convert*"
  fi
  ok "Removed. (config kept; delete $VENV_DIR by hand if you want the space back)"
  exit 0
fi

[[ -f "$MAIN_PY" ]] || fail "main.py not found at $MAIN_PY - run this from the repository."

# ------------------------------------------------------------ 1. find python3
info "Looking for Python 3 (3.9+, tkinter, venv)..."
PY3=""
for cand in python3 /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$cand" >/dev/null 2>&1; then PY3="$(command -v "$cand")"; break; fi
done
[[ -n "$PY3" ]] || fail "Python 3 not found. Install it via 'xcode-select --install' or 'brew install python3', then re-run."
"$PY3" -c 'import sys; assert sys.version_info >= (3, 9)' 2>/dev/null \
  || fail "$PY3 is older than 3.9. Install a newer Python (python.org or brew), then re-run."
"$PY3" -c 'import tkinter' 2>/dev/null \
  || fail "tkinter is missing from $PY3, so the dialog could never open."$'\n'"         python.org builds include it - install from https://www.python.org/downloads/"
"$PY3" -c 'import venv' 2>/dev/null \
  || fail "The venv module is missing from $PY3 - install a full Python (python.org or brew), not a partial build."
ok "Python 3: $PY3"

# ------------------------------------------------------- 2. project-local venv
# Always rebuilt: idempotent, and a half-broken venv from an earlier run can
# never leak into a working install.
info "Creating $VENV_DIR ..."
rm -rf "$VENV_DIR"
"$PY3" -m venv "$VENV_DIR" >/dev/null \
  || fail "python -m venv failed - install a full Python from python.org and re-run."
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
LO="/Applications/LibreOffice.app/Contents/MacOS/soffice"
if [[ -x "$LO" ]]; then
  ok "LibreOffice found."
elif [[ "$INSTALL_LO" == 1 ]]; then
  if command -v brew >/dev/null 2>&1; then
    info "Running: brew install --cask libreoffice"
    brew install --cask libreoffice && ok "LibreOffice installed." \
      || warn "brew failed - install LibreOffice from libreoffice.org if you need Office conversions."
  else
    warn "Homebrew not found. Download LibreOffice from https://www.libreoffice.org/download/"
  fi
else
  warn "LibreOffice not found - only needed for Office/PDF document conversions."
  warn "  Images and PDFs work without it. To add it: bash installers/macos.sh --install-libreoffice"
fi

# ------------------------------------------------------- 4. stable wrapper
# The workflow calls a wrapper in ~/.local/bin (no sudo) instead of a venv
# path, so the Quick Action survives a venv rebuild and doubles as a CLI:
# ~/.local/bin/universal-convert photo.jpg
info "Creating launcher wrapper $WRAPPER ..."
mkdir -p "$(dirname "$WRAPPER")"
cat > "$WRAPPER" <<EOF
#!/bin/bash
exec "$VENV_PY" "$MAIN_PY" "\$@"
EOF
chmod +x "$WRAPPER"
ok "Wrapper created: $WRAPPER"

# ------------------------------------------------------------ 5. the workflow
info "Creating Quick Action bundle..."
mkdir -p "$WORKFLOW_DIR/Contents"

cat > "$WORKFLOW_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>NSServices</key>
  <array>
    <dict>
      <key>NSBackgroundColorName</key>
      <string>background</string>
      <key>NSIconName</key>
      <string>NSTouchBarColorPickerImages</string>
      <key>NSMenuItem</key>
      <dict>
        <key>default</key>
        <string>Convert With...</string>
      </dict>
      <key>NSMessage</key>
      <string>runWorkflowAsService</string>
      <key>NSRequiredContext</key>
      <dict>
        <key>NSApplicationIdentifier</key>
        <string>com.apple.finder</string>
      </dict>
    </dict>
  </array>
</dict>
</plist>
PLIST

cat > "$WORKFLOW_DIR/Contents/document.wflow" <<'WFLOW'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>AMApplicationBuild</key>
  <string>523</string>
  <key>AMDocumentVersion</key>
  <string>2</string>
  <key>actions</key>
  <array>
    <dict>
      <key>action</key>
      <dict>
        <key>AMAccepts</key>
        <dict>
          <key>Container</key>
          <string>List</string>
          <key>Optional</key>
          <true/>
          <key>Types</key>
          <array>
            <string>com.apple.cocoa.path</string>
          </array>
        </dict>
        <key>AMActionVersion</key>
        <string>2.0.3</string>
        <key>AMApplication</key>
        <array>
          <string>Automator</string>
        </array>
        <key>AMParameterProperties</key>
        <dict>
          <key>COMMAND_STRING</key>
          <dict/>
          <key>CheckedForUserDefaultShell</key>
          <dict/>
          <key>inputMethod</key>
          <dict/>
          <key>shell</key>
          <dict/>
          <key>source</key>
          <dict/>
        </dict>
        <key>AMProvides</key>
        <dict>
          <key>Container</key>
          <string>List</string>
          <key>Types</key>
          <array>
            <string>com.apple.cocoa.path</string>
          </array>
        </dict>
        <key>ActionBundlePath</key>
        <string>/System/Library/Automator/Run Shell Script.action</string>
        <key>ActionName</key>
        <string>Run Shell Script</string>
        <key>ActionParameters</key>
        <dict>
          <key>COMMAND_STRING</key>
          <string>"@@UC_LAUNCHER@@" "$@"</string>
          <key>CheckedForUserDefaultShell</key>
          <true/>
          <key>inputMethod</key>
          <integer>1</integer>
          <key>shell</key>
          <string>/bin/bash</string>
          <key>source</key>
          <string></string>
        </dict>
        <key>BundleIdentifier</key>
        <string>com.apple.RunShellScript</string>
        <key>CFBundleVersion</key>
        <string>2.0.3</string>
        <key>CanShowSelectedItemsWhenRun</key>
        <false/>
        <key>CanShowWhenRun</key>
        <true/>
        <key>Category</key>
        <array>
          <string>AMCategoryUtilities</string>
        </array>
        <key>Class Name</key>
        <string>RunShellScriptAction</string>
        <key>InputUUID</key>
        <string>6C3D34C6-9B2F-4F2A-9F55-2E4A1E0A9B01</string>
        <key>Keywords</key>
        <array>
          <string>Shell</string>
        </array>
        <key>OutputUUID</key>
        <string>6C3D34C6-9B2F-4F2A-9F55-2E4A1E0A9B02</string>
        <key>UUID</key>
        <string>6C3D34C6-9B2F-4F2A-9F55-2E4A1E0A9B03</string>
        <key>UnlocalizedApplications</key>
        <array>
          <string>Automator</string>
        </array>
        <key>arguments</key>
        <dict>
          <key>0</key>
          <dict>
            <key>default value</key>
            <integer>0</integer>
            <key>name</key>
            <string>inputMethod</string>
            <key>required</key>
            <string>0</string>
            <key>type</key>
            <string>0</string>
            <key>uuid</key>
            <string>0</string>
          </dict>
          <key>1</key>
          <dict>
            <key>default value</key>
            <false/>
            <key>name</key>
            <string>CheckedForUserDefaultShell</string>
            <key>required</key>
            <string>0</string>
            <key>type</key>
            <string>0</string>
            <key>uuid</key>
            <string>1</string>
          </dict>
          <key>2</key>
          <dict>
            <key>default value</key>
            <string></string>
            <key>name</key>
            <string>source</string>
            <key>required</key>
            <string>0</string>
            <key>type</key>
            <string>0</string>
            <key>uuid</key>
            <string>2</string>
          </dict>
          <key>3</key>
          <dict>
            <key>default value</key>
            <string></string>
            <key>name</key>
            <string>COMMAND_STRING</string>
            <key>required</key>
            <string>0</string>
            <key>type</key>
            <string>0</string>
            <key>uuid</key>
            <string>3</string>
          </dict>
          <key>4</key>
          <dict>
            <key>default value</key>
            <string>/bin/sh</string>
            <key>name</key>
            <string>shell</string>
            <key>required</key>
            <string>0</string>
            <key>type</key>
            <string>0</string>
            <key>uuid</key>
            <string>4</string>
          </dict>
        </dict>
        <key>isViewVisible</key>
        <integer>1</integer>
        <key>location</key>
        <string>309.000000:253.000000</string>
        <key>nibPath</key>
        <string>/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib</string>
      </dict>
      <key>isViewVisible</key>
      <integer>1</integer>
    </dict>
  </array>
  <key>connectors</key>
  <dict/>
  <key>workflowMetaData</key>
  <dict>
    <key>applicationBundleIDsByPath</key>
    <dict/>
    <key>applicationPaths</key>
    <array/>
    <key>inputTypeIdentifier</key>
    <string>com.apple.Automator.fileSystemObject</string>
    <key>outputTypeIdentifier</key>
    <string>com.apple.Automator.nothing</string>
    <key>presentationMode</key>
    <integer>11</integer>
    <key>processesInput</key>
    <integer>0</integer>
    <key>serviceInputTypeIdentifier</key>
    <string>com.apple.Automator.fileSystemObject</string>
    <key>serviceOutputTypeIdentifier</key>
    <string>com.apple.Automator.nothing</string>
    <key>serviceProcessesInput</key>
    <integer>0</integer>
    <key>systemImageName</key>
    <string>NSTouchBarColorPickerImages</string>
    <key>useAutomaticInputType</key>
    <integer>0</integer>
    <key>workflowTypeIdentifier</key>
    <string>com.apple.Automator.servicesMenu</string>
  </dict>
</dict>
</plist>
WFLOW

# The workflow plist is written verbatim (quoted heredoc) with a placeholder
# for the wrapper path, so a home directory with spaces or shell specials in
# it cannot break the quoting here. Substitution + validation both happen in
# Python: byte-exact replace (no sed metacharacter headaches) and the result
# must still parse as a plist before we tell the user it worked.
"$PY3" - "$WORKFLOW_DIR/Contents/document.wflow" "$WRAPPER" "$PLACEHOLDER" <<'PYEOF' \
  || fail "Could not write a valid workflow document."
import plistlib, sys

path, wrapper, placeholder = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, "rb") as fh:
    data = fh.read()
if placeholder.encode() not in data:
    raise SystemExit("placeholder missing from document.wflow")
data = data.replace(placeholder.encode(), wrapper.encode("utf-8"))
with open(path, "wb") as fh:
    fh.write(data)
plistlib.loads(data)  # must still be a well-formed plist
PYEOF
ok "Wrote $WORKFLOW_DIR"

# --------------------------------------------------- 6. refresh services DB
info "Refreshing the services cache..."
/System/Library/CoreServices/pbs -flush 2>/dev/null || true
killall Finder 2>/dev/null || true
ok "Done."

echo
info "Install complete."
echo "  Finder: select files -> right-click -> Quick Actions -> 'Convert With...'"
echo "  CLI:    $WRAPPER photo.jpg"
echo "  (First use may require confirming in System Settings -> Privacy & Security)"
