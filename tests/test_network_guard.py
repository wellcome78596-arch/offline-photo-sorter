from __future__ import annotations

import socket
import subprocess
from unittest.mock import Mock

import pytest

from photo_sorter.network_guard import (
    NetworkBlockedError,
    install_network_guard,
    _guarded_popen,
    uninstall_network_guard_for_tests,
)


def test_network_guard_blocks_socket_connections() -> None:
    install_network_guard()
    try:
        with pytest.raises(NetworkBlockedError):
            socket.create_connection(("example.com", 80), timeout=1)
        with pytest.raises(NetworkBlockedError):
            socket.socket().connect(("example.com", 80))
        with pytest.raises(NetworkBlockedError):
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("127.0.0.1", 9))
        with pytest.raises(NetworkBlockedError):
            subprocess.Popen(["curl", "https://example.test"])
        with pytest.raises(NetworkBlockedError):
            subprocess.Popen(["powershell", "-Command", "Invoke-WebRequest https://example.test"])
        with pytest.raises(NetworkBlockedError):
            subprocess.Popen(["powershell", "-EncodedCommand", "SQBFAFgA"])
    finally:
        uninstall_network_guard_for_tests()


def test_network_guard_allows_powershell_stdin_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_popen = Mock(return_value="process")
    monkeypatch.setattr("photo_sorter.network_guard._original_popen", fake_popen)

    result = _guarded_popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "-"])

    assert result == "process"
    fake_popen.assert_called_once()
