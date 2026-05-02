"""Supabase-backed access control for the desktop app and CLI entrypoints."""

from __future__ import annotations

import getpass
import hashlib
import os
import platform
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from supabase import create_client  # type: ignore

from scraper.config import PROJECT_ROOT

APP_NAME = "matloob-lead-scraper"
APP_VERSION = "1.0"
ACCESS_RPC_FUNCTION = "request_app_access"


@dataclass(frozen=True)
class AccessControlConfig:
    """Runtime configuration for the access-control Supabase client."""

    supabase_url: str
    supabase_key: str
    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    rpc_function: str = ACCESS_RPC_FUNCTION


@dataclass(frozen=True)
class AccessDecision:
    """Result returned by the remote access-control check."""

    allowed: bool
    status: str
    message: str
    device_id: str = ""
    request_id: str = ""
    technical_error: bool = False


def load_env_file(path: str | Path | None = None) -> None:
    """Load simple KEY=VALUE pairs from a .env file without extra dependencies."""
    env_path = Path(path or PROJECT_ROOT / ".env")
    if not env_path.exists():
        return

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for line in lines:
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#") or "=" not in cleaned:
            continue
        key, value = cleaned.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def build_default_identity() -> dict[str, str]:
    """Return user and machine metadata sent with an access request."""
    return {
        "os_user": getpass.getuser(),
        "machine_name": socket.gethostname(),
        "platform": platform.platform(),
    }


def build_default_device_id() -> str:
    """Build a stable opaque device identifier for this Windows/user profile."""
    explicit_device_id = os.environ.get("MATLOOB_DEVICE_ID", "").strip()
    if explicit_device_id:
        return explicit_device_id

    identity = build_default_identity()
    raw_value = "|".join(
        [
            identity["os_user"],
            identity["machine_name"],
            platform.machine(),
            platform.node(),
        ]
    )
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:32]


class AccessControlClient:
    """Check whether the current user/device is allowed to run the app."""

    def __init__(
        self,
        config: AccessControlConfig,
        *,
        supabase_client: Any | None = None,
        device_id_provider: Callable[[], str] = build_default_device_id,
        identity_provider: Callable[[], dict[str, str]] = build_default_identity,
    ) -> None:
        self.config = config
        self._supabase_client = supabase_client
        self._device_id_provider = device_id_provider
        self._identity_provider = identity_provider

    @classmethod
    def from_environment(cls) -> AccessControlClient:
        """Create a client from SUPABASE_URL and SUPABASE_KEY."""
        load_env_file()
        return cls(
            AccessControlConfig(
                supabase_url=os.environ.get("SUPABASE_URL", "").strip(),
                supabase_key=os.environ.get("SUPABASE_KEY", "").strip(),
            )
        )

    def _create_supabase_client(self) -> Any:
        """Create the Supabase client lazily so tests do not require the package."""
        if self._supabase_client is not None:
            return self._supabase_client

        self._supabase_client = create_client(
            self.config.supabase_url,
            self.config.supabase_key,
        )
        return self._supabase_client

    def check_access(self) -> AccessDecision:
        """Register this device and return whether it is allowed to continue."""
        device_id = ""
        try:
            if not self.config.supabase_url or not self.config.supabase_key:
                return AccessDecision(
                    allowed=False,
                    status="technical_error",
                    message="SUPABASE_URL and SUPABASE_KEY are required.",
                    technical_error=True,
                )

            device_id = self._device_id_provider()
            identity = self._identity_provider()
            payload = {
                "p_app_name": self.config.app_name,
                "p_device_id": device_id,
                "p_os_user": identity.get("os_user", ""),
                "p_machine_name": identity.get("machine_name", ""),
                "p_platform": identity.get("platform", ""),
                "p_app_version": self.config.app_version,
            }

            client = self._create_supabase_client()
            response = client.rpc(self.config.rpc_function, payload).execute()
            row = _first_response_row(getattr(response, "data", None))
            if not row:
                return AccessDecision(
                    allowed=False,
                    status="technical_error",
                    message="Supabase returned an empty access response.",
                    device_id=device_id,
                    technical_error=True,
                )

            status = str(row.get("status", "")).strip().lower()
            message = str(row.get("message", "")).strip()
            request_id = str(row.get("request_id", "") or "")
            allowed = status == "approved"
            if status not in {"approved", "pending", "rejected", "blocked"}:
                return AccessDecision(
                    allowed=False,
                    status="technical_error",
                    message=f"Unknown access status from Supabase: {status or '<empty>'}",
                    device_id=device_id,
                    request_id=request_id,
                    technical_error=True,
                )

            return AccessDecision(
                allowed=allowed,
                status=status,
                message=message or _default_status_message(status),
                device_id=device_id,
                request_id=request_id,
                technical_error=False,
            )
        except Exception as exc:
            return AccessDecision(
                allowed=False,
                status="technical_error",
                message=str(exc),
                device_id=device_id,
                technical_error=True,
            )


def _first_response_row(data: Any) -> dict[str, Any]:
    """Normalize Supabase RPC data into one dictionary row."""
    if isinstance(data, list):
        first = data[0] if data else {}
        return first if isinstance(first, dict) else {}
    if isinstance(data, dict):
        return data
    return {}


def _default_status_message(status: str) -> str:
    messages = {
        "approved": "Access approved.",
        "pending": "Access request sent. Waiting for admin approval.",
        "rejected": "Access request was rejected by admin.",
        "blocked": "This device/user is blocked by admin.",
    }
    return messages.get(status, "Access denied.")


def format_access_decision(decision: AccessDecision) -> str:
    """Return a user-facing access-control message."""
    if decision.allowed:
        return "Access approved."

    prefix = "Technical error" if decision.technical_error else "Access denied"
    details = decision.message or _default_status_message(decision.status)
    device_note = f"\nDevice ID: {decision.device_id}" if decision.device_id else ""
    request_note = f"\nRequest ID: {decision.request_id}" if decision.request_id else ""
    return f"{prefix}: {details}{device_note}{request_note}"


def require_app_access(logger: Callable[[str], None] = print) -> AccessDecision:
    """Stop the current process unless Supabase approves this device/user."""
    decision = AccessControlClient.from_environment().check_access()
    if not decision.allowed:
        logger(format_access_decision(decision))
        raise SystemExit(2 if decision.technical_error else 1)
    return decision
