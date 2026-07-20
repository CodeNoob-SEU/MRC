"""PnP device reset for wedged capture drivers (requires administrator).

A thread stuck in an uncancellable kernel call of the capture driver keeps
the device occupied and cannot be killed by taskkill. Disabling and
re-enabling the device forces the driver to cancel its outstanding I/O,
which releases the wedge (zombie processes then exit on their own).
"""

from __future__ import annotations

import ctypes
import json
import logging
import platform
import re
import subprocess
from typing import Any, Dict, List

_LOGGER = logging.getLogger("mrc_backend.device_reset")
_CREATE_NO_WINDOW = 0x08000000


def is_windows() -> bool:
    return platform.system() == "Windows"


def pnp_pattern_from_device_name(device_name: str) -> str:
    """Build a PnP FriendlyName ``-like`` pattern from a DirectShow device name.

    The vendor SDK's ``DXGetDeviceName`` appends an instance suffix (e.g.
    ``ZhongAn US2000 Video Capture 0#``) that the Windows PnP FriendlyName
    (``ZhongAn US2000 Video Capture``) does not carry. Matching on the raw name
    therefore never finds the device, so the device-reset escape hatch silently
    fails. Strip that trailing `` N#`` suffix so the pattern matches.
    """
    name = (device_name or "").strip()
    # Strip a trailing, space-separated instance index (" 0#", " 1", "#") only;
    # never bare trailing digits that are part of the name itself (e.g. US2000).
    base = re.sub(r"(\s+\d+\s*#?|\s*#)\s*$", "", name).strip()
    base = base or name
    return f"*{base}*" if base else ""


def is_admin() -> bool:
    if not is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _run_powershell(script: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        # PowerShell error text on a Chinese Windows is GBK/mbcs, not UTF-8;
        # without errors="replace" the decode raises and cascades into a bogus
        # "list index out of range" that masks the real reset failure.
        errors="replace",
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW if is_windows() else 0,
    )


def find_devices(name_like: str) -> List[Dict[str, str]]:
    """List present PnP devices whose FriendlyName matches the -like pattern."""
    if not is_windows():
        return []
    escaped = name_like.replace("'", "''")
    script = (
        "Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -like '"
        + escaped
        + "' } | Select-Object -Property InstanceId, FriendlyName, Status | ConvertTo-Json -Compress"
    )
    try:
        completed = _run_powershell(script)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("PnP device enumeration failed: %s", exc)
        return []
    output = (completed.stdout or "").strip()
    if completed.returncode != 0 or not output:
        return []
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    return [
        {
            "instance_id": str(entry.get("InstanceId", "")),
            "friendly_name": str(entry.get("FriendlyName", "")),
            "status": str(entry.get("Status", "")),
        }
        for entry in data
        if entry.get("InstanceId")
    ]


def reset_device(instance_id: str, settle_seconds: float = 2.0) -> Dict[str, Any]:
    """Disable then re-enable one device; returns {'ok': bool, 'error'?: str}."""
    if not is_windows():
        return {"ok": False, "error": "device reset is only available on Windows"}
    escaped = instance_id.replace("'", "''")
    script = (
        f"Disable-PnpDevice -InstanceId '{escaped}' -Confirm:$false -ErrorAction Stop; "
        f"Start-Sleep -Seconds {settle_seconds}; "
        f"Enable-PnpDevice -InstanceId '{escaped}' -Confirm:$false -ErrorAction Stop"
    )
    try:
        completed = _run_powershell(script, timeout=90.0)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "device reset timed out"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    if completed.returncode != 0:
        return {"ok": False, "error": (completed.stderr or completed.stdout or "").strip()[-400:]}
    return {"ok": True}
