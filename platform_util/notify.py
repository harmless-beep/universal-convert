"""Success notifications, per OS - no extra pip packages.

  Windows: PowerShell toast (Windows.UI.Notifications), works per-user
           without admin; silently returns False on failure so the caller
           can fall back to a Tk messagebox.
  macOS:   osascript "display notification"
  Linux:   notify-send (if installed)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import xml.sax.saxutils as sx

from core.errors import get_logger

# NOTE: everything after -Command is part of the command string (PowerShell
# docs), so title/body are injected as single-quoted PS literals - never as
# separate argv entries.
PS_TOAST_TMPL = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$title = {title}; $body = {body}
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template=`"ToastGeneric`"><text>$([Security.SecurityElement]::Escape($title))</text><text>$([Security.SecurityElement]::Escape($body))</text></binding></visual></toast>")
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Universal Convert").Show($toast)
"""


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def notify(title: str, body: str) -> bool:
    """Show a desktop notification. Returns False if unavailable."""
    log = get_logger()
    try:
        if sys.platform == "win32":
            return _toast(title, body)
        if sys.platform == "darwin":
            script = (
                f"display notification {sx.quotevalue(body)} "
                f"with title {sx.quotevalue(title)}"
            )
            return _run(["osascript", "-e", script])
        if shutil.which("notify-send"):
            return _run(["notify-send", "--app-name=Universal Convert",
                         title, body])
        log.debug("notify-send not available")
        return False
    except Exception as exc:  # noqa: BLE001 - notifications must never crash
        log.warning("notification failed: %s", exc)
        return False


def _run(cmd: list[str]) -> bool:
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=15, check=False
    )
    if proc.returncode != 0:
        get_logger().debug("notify rc=%s: %s", proc.returncode, proc.stderr)
        return False
    return True


def _toast(title: str, body: str) -> bool:
    if not shutil.which("powershell") and not shutil.which("powershell.exe"):
        return False
    script = PS_TOAST_TMPL.format(title=_ps_quote(title), body=_ps_quote(body))
    proc = subprocess.run(
        [
            "powershell", "-NoProfile", "-NonInteractive", "-WindowStyle",
            "Hidden", "-ExecutionPolicy", "Bypass", "-Command", script,
        ],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if proc.returncode != 0:
        get_logger().debug("toast failed rc=%s: %s",
                           proc.returncode, (proc.stderr or "")[:500])
        return False
    return True
