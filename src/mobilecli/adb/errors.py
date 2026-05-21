"""ADB error -> ErrorCode mapping."""

from __future__ import annotations

from mobilecli.envelope import EmError, ErrorCode


def map_adb_stderr(stderr: str, returncode: int) -> EmError:
    """Translate adb stderr text to an EmError. Best-effort heuristics."""
    s = stderr.lower()
    if "no devices/emulators found" in s or "device not found" in s:
        return EmError(ErrorCode.NO_DEVICE, "adb: no device", hint="run `adb devices`")
    if "more than one device" in s:
        return EmError(
            ErrorCode.MULTIPLE_DEVICES,
            "adb: more than one device",
            hint="pass --serial or set EM_SERIAL",
        )
    if "killed" in s and returncode < 0:
        return EmError(ErrorCode.ADB_TIMEOUT, "adb command timed out")
    return EmError(ErrorCode.UNKNOWN, stderr.strip() or f"adb exited {returncode}")
