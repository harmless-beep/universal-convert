#!/usr/bin/env bash
# =====================================================================
# Universal Convert - macOS installer
# =====================================================================
# Creates a Finder Quick Action ("Convert With...") that passes the
# selected files to main.py. Installs Python deps + LibreOffice when
# missing. No admin rights required.
#
#   install:    bash installers/macos.sh
#   uninstall:  bash installers/macos.sh --uninstall
#
# The Quick Action appears in Finder under right-click -> Quick Actions
# (older macOS: Services). It receives the full multi-selection in ONE
# invocation; no IPC aggregation is needed on this OS.
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MAIN_PY="$PROJECT_DIR/main.py"

SERVICES_DIR="$HOME/Library/Services"
WORKFLOW_NAME="Convert With....workflow"
WORKFLOW_DIR="$SERVICES_DIR/$WORKFLOW_NAME"
PY_IN_WORKFLOW="/usr/local/bin/universal-convert-python"
WRAPPER="/usr/local/bin/universal-convert"

info() { printf '\033[36m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m[OK]\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m[!!]\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m[XX]\033[0m %s\n' "$*"; exit 1; }

if [[ "${1:-}" == "--uninstall" ]]; then
  info "Removing Quick Action..."
  rm -rf "$WORKFLOW_DIR"
  rm -f "$WRAPPER" "$PY_IN_WORKFLOW"
  /System/Library/CoreServices/pbs -flush 2>/dev/null || true
  ok "Removed. (Config in ~/Library/Application Support/UniversalConvert kept.)"
  exit 0
fi

[[ "$(uname -s)" == "Darwin" ]] || fail "This script is for macOS. You are on $(uname -s)."
[[ -f "$MAIN_PY" ]] || fail "main.py not found at $MAIN_PY"

# ------------------------------------------------------------ 1. find python3
info "Looking for Python 3..."
PY3=""
for cand in python3 \
            /usr/bin/python3 \
            /opt/homebrew/bin/python3 \
            /usr/local/bin/python3 \
            "$HOME/Library/Python/3.x/bin/python3"; do
  if command -v "$cand" >/dev/null 2>&1; then PY3="$(command -v "$cand")"; break; fi
done
if [[ -z "$PY3" ]]; then
  fail "Python 3 not found. Install it via 'xcode-select --install' or brew install python3, then re-run."
fi
ok "Python 3: $PY3"

"$PY3" -c 'import tkinter' 2>/dev/null || warn "tkinter not importable - the dialog may fail. python.org installs include it."

# ------------------------------------------------------------ 2. pip deps
info "Checking Python packages..."
"$PY3" -m pip install --user --quiet pypdf PyMuPDF Pillow \
  || warn "pip install failed - PDF actions may be unavailable."
ok "Dependencies processed."

# ------------------------------------------------------------ 3. LibreOffice
info "Checking LibreOffice..."
LO="/Applications/LibreOffice.app/Contents/MacOS/soffice"
if [[ -x "$LO" ]]; then
  ok "LibreOffice found."
else
  warn "LibreOffice not found - needed for Office/PDF document conversions."
  if command -v brew >/dev/null 2>&1; then
    read -r -p "Install LibreOffice now via Homebrew? [Y/n] " answer || answer="Y"
    if [[ "${answer:-Y}" =~ ^[Yy]?$ ]]; then
      brew install --cask libreoffice && ok "LibreOffice installed."
    fi
  else
    warn "Homebrew not found. Download from https://www.libreoffice.org/download/ and re-run."
  fi
fi

# ------------------------------------------------- 4. stable launcher paths
# The .workflow plist should not embed a homebrew/venv path that may change,
# so we point it at tiny stable wrappers instead.
info "Creating launcher wrappers in /usr/local/bin (may ask for password)..."
sudo mkdir -p /usr/local/bin
sudo tee "$PY_IN_WORKFLOW" >/dev/null <<EOF
#!/bin/bash
exec "$PY3" "\$@"
EOF
sudo chmod +x "$PY_IN_WORKFLOW"
sudo tee "$WRAPPER" >/dev/null <<EOF
#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/local/sbin:\$PATH"
exec "$PY_IN_WORKFLOW" "$MAIN_PY" "\$@"
EOF
sudo chmod +x "$WRAPPER"
ok "Wrappers created: $WRAPPER"

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
          <string>/usr/local/bin/universal-convert "$@"</string>
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

ok "Wrote $WORKFLOW_DIR"

# --------------------------------------------------- 6. refresh services DB
info "Refreshing the services cache..."
/System/Library/CoreServices/pbs -flush 2>/dev/null || true
killall Finder 2>/dev/null || true
ok "Done."

echo
info "Install complete."
echo "  Finder: select files -> right-click -> Quick Actions -> 'Convert With...'"
echo "  (First use may require confirming in System Settings -> Privacy & Security)"
