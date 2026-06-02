"""push_to_gallery: 校验/远端路径/扫描/回查 (mock device)。"""

from __future__ import annotations

import pytest

from mobilecli.core import media
from mobilecli.envelope import EmError, ErrorCode


class _FakeDevice:
    def __init__(self, indexed=True):
        self.pushed = []
        self.shell_cmds = []
        self._indexed = indexed

    def push(self, local, remote, timeout_s=30):
        self.pushed.append((local, remote))

    def shell(self, cmd, timeout_s=30):
        self.shell_cmds.append(cmd)
        if cmd.startswith("content query"):
            return "Row: 0 _id=1, _data=/x\n" if self._indexed else "No result found."
        return ""


def test_rejects_bad_extension(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(EmError) as e:
        media.push_to_gallery(_FakeDevice(), [str(f)])
    assert e.value.code == ErrorCode.INVALID_ARG


def test_rejects_missing_file():
    with pytest.raises(EmError) as e:
        media.push_to_gallery(_FakeDevice(), ["/nope/x.jpg"])
    assert e.value.code == ErrorCode.INVALID_ARG


def test_pushes_scans_and_verifies(tmp_path):
    f = tmp_path / "pic.jpg"
    f.write_bytes(b"\xff\xd8\xff")
    dev = _FakeDevice(indexed=True)
    res = media.push_to_gallery(dev, [str(f)], subdir="em-publish")
    assert res["count"] == 1
    assert res["pushed"][0]["remote"] == "/sdcard/DCIM/em-publish/pic.jpg"
    assert res["pushed"][0]["indexed"] is True
    assert any(c.startswith("touch") for c in dev.shell_cmds)
    assert any("MEDIA_SCANNER_SCAN_FILE" in c for c in dev.shell_cmds)


def test_raises_when_not_indexed(tmp_path):
    f = tmp_path / "pic.jpg"
    f.write_bytes(b"\xff\xd8\xff")
    with pytest.raises(EmError) as e:
        media.push_to_gallery(_FakeDevice(indexed=False), [str(f)])
    assert e.value.code == ErrorCode.MEDIA_NOT_INDEXED
