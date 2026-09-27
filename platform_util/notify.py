"""Success notifications, per OS - no extra pip packages.

  Windows: PowerShell toast (Windows.UI.Notifications), works per-user
           without admin.
  macOS:   osascript "display notification"
  Linux:   notify-send (if installed)

Everything is spawned fire-and-forget: a notification never delays the
caller, and never blocks the app from exiting. Returns False only when
there is no notification mechanism to talk to.
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
    """Fire and forget: a notification must never delay the app exiting."""
    try:
        _spawn(cmd)
        return True
    except OSError as exc:
        get_logger().debug("notify failed to start: %s", exc)
        return False


def _spawn(cmd: list[str]) -> "subprocess.Popen[bytes]":
    kwargs: dict = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    return subprocess.Popen(cmd, **kwargs)


def _toast(title: str, body: str) -> bool:
    if not shutil.which("powershell") and not shutil.which("powershell.exe"):
        return False
    script = PS_TOAST_TMPL.format(title=_ps_quote(title), body=_ps_quote(body))
    try:
        # Not subprocess.run(): cold-starting PowerShell can take seconds and
        # the caller is usually about to exit.
        _spawn([
            "powershell", "-NoProfile", "-NonInteractive", "-WindowStyle",
            "Hidden", "-ExecutionPolicy", "Bypass", "-Command", script,
        ])
        return True
    except OSError as exc:
        get_logger().debug("toast failed to start: %s", exc)
        return False
