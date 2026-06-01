from __future__ import annotations
import mobilecli.plugin.ctx as ctxmod


class _Dev:
    def shell(self, *a, **k): return ""
    def exec_out(self, *a, **k): return b""


def test_pacing_disabled_via_env(monkeypatch):
    monkeypatch.setenv("EM_PACE", "0")
    slept = []
    monkeypatch.setattr(ctxmod.time, "sleep", lambda s: slept.append(s))
    im = ctxmod.InputModule(device=_Dev())
    im.keyevent("back"); im.keyevent("back")
    assert slept == []


def test_pacing_skips_first_then_paces(monkeypatch):
    monkeypatch.setenv("EM_PACE", "1")
    monkeypatch.setenv("EM_PACE_MIN", "2"); monkeypatch.setenv("EM_PACE_MAX", "10")
    slept = []
    monkeypatch.setattr(ctxmod.time, "sleep", lambda s: slept.append(s))
    im = ctxmod.InputModule(device=_Dev())
    im.keyevent("back")   # first → no pace
    im.keyevent("back")   # second → paced
    assert len(slept) == 1 and 2.0 <= slept[0] <= 10.0
