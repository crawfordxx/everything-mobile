"""Push host media into the device gallery so apps' album pickers see it."""
from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.envelope import EmError, ErrorCode

_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_EXT = {".mp4", ".mov"}
_ALLOWED = _IMAGE_EXT | _VIDEO_EXT
_GALLERY_DIR = "/sdcard/DCIM"


def _is_image(path: str) -> bool:
    return Path(path).suffix.lower() in _IMAGE_EXT


def push_to_gallery(
    device: Device, local_paths: list[str], subdir: str = "em-publish"
) -> dict[str, Any]:
    """Push each local file to /sdcard/DCIM/<subdir>/, set mtime to 'now' (so
    pushed media sorts to the front of the date-sorted album), trigger a
    single-file media scan, and verify each is indexed in MediaStore.

    Raises INVALID_ARG (bad ext / missing) or MEDIA_NOT_INDEXED.
    """
    for p in local_paths:
        if not Path(p).is_file():
            raise EmError(ErrorCode.INVALID_ARG, f"media not found: {p}")
        if Path(p).suffix.lower() not in _ALLOWED:
            raise EmError(
                ErrorCode.INVALID_ARG,
                f"unsupported media type: {p}",
                hint=f"allowed: {sorted(_ALLOWED)}",
            )

    remote_dir = f"{_GALLERY_DIR}/{subdir}"
    device.shell(f"mkdir -p {shlex.quote(remote_dir)}")
    pushed: list[dict[str, Any]] = []
    for local in local_paths:
        name = Path(local).name
        remote = f"{remote_dir}/{name}"
        device.push(local, remote)
        device.shell(f"touch {shlex.quote(remote)}")
        scan_uri = f"file://{remote}"
        device.shell(
            f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
            f"-d {shlex.quote(scan_uri)}"
        )
        coll = "video" if not _is_image(local) else "images"
        # MediaStore stores _data as /storage/emulated/0/... but `remote` uses the
        # /sdcard/... symlink — exact match would miss. Match on the dir/name tail.
        where = shlex.quote(f"_data LIKE '%/{subdir}/{name}'")
        q = device.shell(
            f"content query --uri content://media/external/{coll}/media "
            f"--projection _id --where {where}"
        )
        indexed = "Row:" in q
        if not indexed:
            raise EmError(
                ErrorCode.MEDIA_NOT_INDEXED,
                f"pushed but MediaStore did not index: {remote}",
                hint="device may block legacy media scan; check Android version",
            )
        pushed.append({"local": local, "remote": remote, "indexed": True})
    return {"count": len(pushed), "pushed": pushed}
