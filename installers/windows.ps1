# =====================================================================
# Universal Convert - Windows installer
# =====================================================================
# Installs the "Convert With..." right-click menu entry for the current
# user (HKCU - no admin rights needed), plus its Python dependencies.
#
#   install:            powershell -ExecutionPolicy Bypass -File windows.ps1
#   skip LibreOffice:   ... -File windows.ps1 -SkipLibreOffice
#   uninstall:          ... -File windows.ps1 -Uninstall
#
# The entry is registered for *all file types* via HKCU\Software\Classes\*.
# On Windows 11 it appears under "Show more options" (the classic menu),
# which is standard for registry-based context menu verbs.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$SkipLibreOffice
)

$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$MainPy     = Join-Path $ProjectDir 'main.py'
$MenuTitle  = 'Convert With...'
$RegKey     = 'HKCU:\Software\Classes\*\shell\ConvertWith'
# (used ONLY via -LiteralPath - see the registry section below)

function Info($m) { Write-Host $m -ForegroundColor Cyan }
function OK($m)   { Write-Host "  [OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!!] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  [XX] $m" -ForegroundColor Red; exit 1 }

# PowerShell 5.1 turns native-command stderr into a terminating error when
# $ErrorActionPreference='Stop'. Every native call must go through this.
function Invoke-Native([scriptblock]$Block) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Block; return $LASTEXITCODE } finally { $ErrorActionPreference = $prev }
}

function Test-Py($pythonExe) {
    # Candidate is usable only if tkinter AND Pillow import there.
    $out = Invoke-Native { & $pythonExe -c "import tkinter, PIL; print('UC_OK')" 2>$null }
    return ($out -contains 'UC_OK')
}

# ---------------------------------------------------------------- uninstall
if ($Uninstall) {
    Info "Removing the '$MenuTitle' context menu entry..."
    if (Test-Path -LiteralPath $RegKey) {
        Remove-Item -LiteralPath $RegKey -Recurse -Force
        OK "Removed $RegKey"
    } else {
        Warn "Entry not found (already uninstalled?)"
    }
    Info "Python packages and LibreOffice were left in place."
    Info "Done."
    exit 0
}

Write-Host ""
Info "Universal Convert installer"
Write-Host "Project: $ProjectDir"

if (-not (Test-Path -LiteralPath $MainPy)) {
    Fail "main.py not found at $MainPy - run this from the project folder."
}# ------------------------------------------------------------ 1. find Python
# Multiple Pythons are common (PATH, py launcher, Store). We don't just take
# the first - we take the FIRST THAT CAN ACTUALLY RUN THE APP (tkinter+PIL).
Info "Looking for a usable Python (tkinter + Pillow)..."
$candidates = @()
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pyCmd) { $candidates += $pyCmd.Source }
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $p = Invoke-Native { & py -3 -c "import sys; print(sys.executable)" 2>$null }
    if ($p -and (Test-Path -LiteralPath "$p")) { $candidates += "$p" }
}
$candidates += (Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
                                        "$env:LOCALAPPDATA\Microsoft\WindowsApps\python*.exe",
                                        'C:\Python3*\python.exe' -ErrorAction SilentlyContinue).FullName

$pyExe = $null
$tried = @()
foreach ($cand in ($candidates | Select-Object -Unique)) {
    if (-not $cand -or -not (Test-Path -LiteralPath $cand)) { continue }
    $tried += $cand
    if (Test-Py $cand) { $pyExe = $cand; break }
}
if (-not $pyExe) {
    $msg = "No usable Python was found. Tried: $($tried -join ', ')" + [Environment]::NewLine +
           "Install Python 3 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')," + [Environment]::NewLine +
           "then run: python -m pip install Pillow pypdf PyMuPDF - and re-run this installer."
    Fail $msg
}

# pythonw avoids a console flash on every right-click; fall back if absent.
$pyw = $pyExe -replace 'python\.exe$', 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pyw)) { $pyw = $pyExe }
OK "Python: $pyExe"

# ------------------------------------------------------- 2. python packages
Info "Checking Python packages..."
$rc = Invoke-Native { & $pyExe -m pip install --quiet --disable-pip-version-check pypdf PyMuPDF 2>$null }
if ($rc -eq 0) { OK "pypdf + PyMuPDF ready" }
else { Warn "pip install reported a problem - PDF actions may be unavailable." }

# -------------------------------------------------------- 3. LibreOffice
if ($SkipLibreOffice) {
    Warn "Skipping LibreOffice setup (-SkipLibreOffice)."
} else {
    Info "Checking LibreOffice..."
    $loPaths = @(
        (Join-Path $env:ProgramFiles 'LibreOffice\program\soffice.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'LibreOffice\program\soffice.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\LibreOffice\program\soffice.exe')
    )
    $lo = $loPaths | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $lo) {
        $cmd = Get-Command soffice -ErrorAction SilentlyContinue
        if ($cmd) { $lo = $cmd.Source }
    }
    if ($lo) {
        OK "LibreOffice: $lo"
    } else {
        Warn "LibreOffice not found - needed for Office/PDF document conversions."
        $answer = Read-Host "Install LibreOffice now via winget? [Y/n]"
        if ($answer -match '^[Yy]?$') {
            Info "Running: winget install TheDocumentFoundation.LibreOffice"
            winget install --id TheDocumentFoundation.LibreOffice -e `
                --accept-source-agreements --accept-package-agreements --silent
            # refresh discovery
            $lo = $loPaths | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
            if ($lo) { OK "LibreOffice installed." }
            else { Warn "LibreOffice still not detected; you can install it later from libreoffice.org." }
        } else {
            Warn "Skipping. Image actions still work; Office/PDF actions will show a friendly 'install LibreOffice' message."
        }
    }
}

# ------------------------------------------------------- 4. registry entries
Info "Adding the '$MenuTitle' context menu entry (current user only)..."
# NOTE: the key path contains a literal '*' which PowerShell's *-Item cmdlets
# treat as a WILDCARD (-Path would expand it to every registered file class),
# and PS 5.1's New-Item has no -LiteralPath. So key creation goes through the
# .NET Registry API (purely literal) and values through -LiteralPath.
function New-RegKey([string]$subPath) {
    # $subPath is relative to HKEY_CURRENT_USER, e.g. 'Software\Classes\*\shell\ConvertWith'
    return [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($subPath)
}
$RegSub     = 'Software\Classes\*\shell\ConvertWith'
$RegSubCmd  = "$RegSub\command"

New-RegKey $RegSub   | Out-Null
New-RegKey $RegSubCmd | Out-Null

# MultiSelectModel=Document lets Explorer offer the menu for selections up to
# 100 files. The command runs pythonw (no console window) with %1 = the
# clicked file; sibling instances are merged by main.py's aggregator.
$cmd = ('"{0}" "{1}" "%1"' -f $pyw, $MainPy)

Set-ItemProperty -LiteralPath $RegKey -Name '(Default)'      -Value $MenuTitle
Set-ItemProperty -LiteralPath $RegKey -Name 'MUIVerb'        -Value $MenuTitle
Set-ItemProperty -LiteralPath $RegKey -Name 'MultiSelectModel' -Value 'Document'
Set-ItemProperty -LiteralPath $RegKey -Name 'Icon'           -Value "$pyw,0"
Set-ItemProperty -LiteralPath $RegKey -Name 'NeverDefault'   -Value '' -Type String
Set-ItemProperty -LiteralPath "$RegKey\command" -Name '(Default)' -Value $cmd
OK "Registry entries written."

# ---------------------------------------------------------------- 5. verify
$k = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($RegSubCmd)
$check = if ($k) { $k.GetValue('') } else { $null }
if ($k) { $k.Close() }
if ($check -ne $cmd) { Fail "Verification failed - registry value mismatch." }
OK "Verified: $check"

Write-Host ""
Write-Host "Install complete." -ForegroundColor Green
Write-Host "Right-click any image/PDF/Office file in Explorer and choose"
Write-Host "'$MenuTitle'. On Windows 11, look under 'Show more options'."
