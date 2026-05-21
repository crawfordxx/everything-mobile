"""ADB device wrapper (Layer 1).

The only module that may import subprocess. All other layers go through Device.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from mobilecli.adb.errors import map_adb_stderr
from mobilecli.envelope import EmError, ErrorCode

DEFAULT_TIMEOUT_S = 30


def _parse_devices_output(out: str) -> list[dict[str, str]]:
    """Parse `adb devices` table.

    Lines: "<serial>\\t<state>" -- anything not matching is skipped.
    """
    devices: list[dict[str, str]] = []
    for raw in out.splitlines():
        line = raw.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            devices.append({"serial": parts[0].strip(), "state": parts[1].strip()})
    return devices


@dataclass
class Device:
    """A connected Android device addressable via `adb -s <serial>`."""

    serial: str

    @classmethod
    def list_attached(cls, timeout_s: int = 10) -> list[dict[str, str]]:
        """Return raw output of `adb devices` parsed as dicts."""
        proc = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        if proc.returncode != 0:
            raise map_adb_stderr(proc.stderr, proc.returncode)
        return _parse_devices_output(proc.stdout)

    @classmethod
    def from_serial(cls, requested: str | None) -> Device:
        """Resolve a Device from --serial / EM_SERIAL / single connected device."""
        if requested is None:
            requested = os.environ.get("EM_SERIAL") or None
        devices = cls.list_attached()
        serial = cls._select_serial(devices, requested)
        return cls(serial=serial)

    @staticmethod
    def _select_serial(
        devices: list[dict[str, str]],
        requested: str | None,
    ) -> str:
        online = [d for d in devices if d["state"] == "device"]
        if requested:
            if any(d["serial"] == requested for d in online):
                return requested
            raise EmError(
                ErrorCode.NO_DEVICE,
                f"requested device {requested} not connected",
                hint="run `adb devices` to see online devices",
            )
        if not online:
            raise EmError(ErrorCode.NO_DEVICE, "no devices connected")
        if len(online) > 1:
            raise EmError(
                ErrorCode.MULTIPLE_DEVICES,
                f"{len(online)} devices connected",
                hint="pass --serial XXX or set EM_SERIAL",
            )
        return online[0]["serial"]

    def shell(self, cmd: str, timeout_s: int = DEFAULT_TIMEOUT_S) -> str:
        """Run `adb -s <serial> shell <cmd>` and return stdout."""
        argv = ["adb", "-s", self.serial, "shell", cmd]
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise EmError(
                ErrorCode.ADB_TIMEOUT,
                f"adb shell timed out after {timeout_s}s",
            ) from exc
        if proc.returncode != 0:
            raise map_adb_stderr(proc.stderr, proc.returncode)
        return proc.stdout

    def exec_out(self, cmd: list[str], timeout_s: int = DEFAULT_TIMEOUT_S) -> bytes:
        """Run `adb -s <serial> exec-out <cmd>` and return raw bytes (for screencap)."""
        argv = ["adb", "-s", self.serial, "exec-out", *cmd]
        try:
            proc = subprocess.run(argv, capture_output=True, timeout=timeout_s, check=False)
        except subprocess.TimeoutExpired as exc:
            raise EmError(
                ErrorCode.ADB_TIMEOUT,
                f"adb exec-out timed out after {timeout_s}s",
            ) from exc
        if proc.returncode != 0:
            raise map_adb_stderr(
                proc.stderr.decode("utf-8", errors="replace"),
                proc.returncode,
            )
        return proc.stdout

    def install_apk(self, apk_path: str, timeout_s: int = 120) -> None:
        """`adb -s <serial> install -r <apk>` -- stays inside Layer 1."""
        argv = ["adb", "-s", self.serial, "install", "-r", apk_path]
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise EmError(
                ErrorCode.ADB_TIMEOUT,
                f"adb install timed out after {timeout_s}s",
            ) from exc
        if proc.returncode != 0:
            raise map_adb_stderr(proc.stderr, proc.returncode)

    def pull(self, remote: str, local: str, timeout_s: int = DEFAULT_TIMEOUT_S) -> None:
        argv = ["adb", "-s", self.serial, "pull", remote, local]
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        if proc.returncode != 0:
            raise map_adb_stderr(proc.stderr, proc.returncode)

    def push(self, local: str, remote: str, timeout_s: int = DEFAULT_TIMEOUT_S) -> None:
        argv = ["adb", "-s", self.serial, "push", local, remote]
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        if proc.returncode != 0:
            raise map_adb_stderr(proc.stderr, proc.returncode)
