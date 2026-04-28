"""Automatic device identity helpers for admin access control."""

import hashlib
import os
import platform
import socket
import sys
import uuid

if sys.platform == "win32":
    import winreg as WINREG
else:
    WINREG = None

DEVICE_ID_ENV_VAR = "MATLOOB_DEVICE_ID"


def normalize_device_id(value: str | None) -> str:
    """Normalize a device identity for stable MongoDB lookups."""
    raw_value = str(value or "").strip().upper()
    if not raw_value:
        return ""

    normalized = []
    previous_dash = False
    for char in raw_value:
        if char.isalnum():
            normalized.append(char)
            previous_dash = False
        elif not previous_dash:
            normalized.append("-")
            previous_dash = True
    return "".join(normalized).strip("-")


def _windows_machine_guid() -> str:
    """Return the Windows machine GUID when available."""
    if WINREG is None:
        return ""
    try:
        with WINREG.OpenKey(
            WINREG.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            machine_guid, _ = WINREG.QueryValueEx(key, "MachineGuid")
            return str(machine_guid)
    except OSError:
        return ""


def _machine_seed_parts() -> tuple[str, ...]:
    """Collect local machine facts used only to derive a hashed device ID."""
    return (
        platform.node(),
        socket.gethostname(),
        platform.system(),
        platform.machine(),
        str(uuid.getnode()),
        _windows_machine_guid(),
    )


def get_device_id(seed_parts: tuple[str, ...] | None = None) -> str:
    """Return the current machine's admin access identity."""
    if seed_parts is None:
        override = normalize_device_id(os.environ.get(DEVICE_ID_ENV_VAR))
        if override:
            return override
        seed_parts = _machine_seed_parts()

    seed = "|".join(str(part).strip() for part in seed_parts if str(part).strip())
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest().upper()[:16]
    return f"DEVICE-{digest}"
