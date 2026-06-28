from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from typing import Sequence


class NetworkBlockedError(OSError):
    """Raised when runtime code attempts to open a network connection."""


_installed = False
_original_create_connection = socket.create_connection
_original_socket_connect = socket.socket.connect
_original_socket_connect_ex = socket.socket.connect_ex
_original_socket_send = socket.socket.send
_original_socket_sendall = socket.socket.sendall
_original_socket_sendto = socket.socket.sendto
_original_popen = subprocess.Popen
_original_sendmsg = getattr(socket.socket, "sendmsg", None)

ALLOWED_SUBPROCESS_NAMES = {
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "explorer",
    "explorer.exe",
}


def _raise_blocked(*_args, **_kwargs):
    raise NetworkBlockedError("Network access is disabled by OfflinePhotoSorter.")


def _connect_ex_blocked(*_args, **_kwargs) -> int:
    raise NetworkBlockedError("Network access is disabled by OfflinePhotoSorter.")


def _extract_process_name(args) -> str:
    if isinstance(args, (str, bytes)):
        return ""
    if not isinstance(args, Sequence) or not args:
        return ""
    return Path(str(args[0])).name.lower()


def _guarded_popen(args, *popen_args, **popen_kwargs):
    if popen_kwargs.get("shell"):
        raise NetworkBlockedError("Shell subprocesses are disabled by OfflinePhotoSorter.")

    process_name = _extract_process_name(args)
    if process_name not in ALLOWED_SUBPROCESS_NAMES:
        raise NetworkBlockedError(f"Subprocess is not allowed: {process_name or 'unknown'}")

    if process_name in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        parts = [str(part) for part in args]
        if any(part.lower() in {"-encodedcommand", "-enc", "-e"} for part in parts):
            raise NetworkBlockedError("Encoded PowerShell commands are disabled.")
        command_text = " ".join(parts[1:])
        for index, part in enumerate(parts):
            if part.lower() in {"-command", "-c"} and index + 1 < len(parts):
                command_text = parts[index + 1]
                break
        from .core import scan_forbidden_powershell

        problems = scan_forbidden_powershell(command_text)
        if problems:
            raise NetworkBlockedError(
                "PowerShell subprocess contains forbidden command: " + ", ".join(problems)
            )

    return _original_popen(args, *popen_args, **popen_kwargs)


def install_network_guard() -> None:
    global _installed
    if _installed:
        return
    socket.create_connection = _raise_blocked
    socket.socket.connect = _raise_blocked
    socket.socket.connect_ex = _connect_ex_blocked
    socket.socket.send = _raise_blocked
    socket.socket.sendall = _raise_blocked
    socket.socket.sendto = _raise_blocked
    if _original_sendmsg is not None:
        socket.socket.sendmsg = _raise_blocked
    subprocess.Popen = _guarded_popen
    _installed = True


def uninstall_network_guard_for_tests() -> None:
    global _installed
    socket.create_connection = _original_create_connection
    socket.socket.connect = _original_socket_connect
    socket.socket.connect_ex = _original_socket_connect_ex
    socket.socket.send = _original_socket_send
    socket.socket.sendall = _original_socket_sendall
    socket.socket.sendto = _original_socket_sendto
    if _original_sendmsg is not None:
        socket.socket.sendmsg = _original_sendmsg
    subprocess.Popen = _original_popen
    _installed = False
