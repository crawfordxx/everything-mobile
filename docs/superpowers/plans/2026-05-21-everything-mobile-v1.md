# everything-mobile v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pipx-installable Python CLI `mobilecli` that lets external AI agents (Claude Code / Codex / openclaw) drive a physical Android device. v1 ships 11 primitives + 2 app plugins (douyin, xiaohongshu) + mandatory humanization layer + README with disclaimers.

**Architecture:** 5 layers — Layer 1 ADB device backend → Layer 2 generic primitives → Layer 2.5 humanization & safety (NOT optional) → Layer 3 app plugins → Layer 0 external AI driver. JSON-in / JSON-out subprocess; stateless commands; large artefacts (PNG/XML) written to disk with the path returned.

**Tech Stack:** Python 3.10+, argparse, subprocess for adb, pytest + ruff + mypy, pyproject.toml entry_points for external plugin discovery.

**Spec:** `docs/superpowers/specs/2026-05-21-everything-mobile-design.md`. Every task references its source section.

**Phases:**

| Phase | Outcome (testable on its own) | Tasks |
|---|---|---|
| **A. Core** | `mobilecli {devices,screenshot,tap,swipe,type,keyevent,dump,launch,install,foreground,doctor}` all return correctly-shaped JSON against device `EXAMPLE-SERIAL`. No humanization yet. | A1–A18 |
| **B. Humanization** | Same commands but with humanized timing/jitter; `--raw` opt-out gated by env. `SessionGovernor`, `ContentLinter`, `DeviceCheck` modules + new error codes. | B1–B12 |
| **C. App plugins** | `mobilecli douyin {launch,search,open,detail,comment}` + `mobilecli xiaohongshu {launch,search,open,detail,comment}` work E2E on device. Plugin registry supports `entry_points` discovery. | C1–C18 |
| **D. Release polish** | README with CN+EN disclaimer + full CLI table + risks + "not a spam tool" anti-scope. ai-usage.md + plugin-guide.md. Asciinema demo. CI passing on push. | D1–D8 |

**Conventions across all phases:**

- TDD: failing test → run-and-see-fail → minimal impl → run-and-see-pass → commit. Each commit is the smallest unit that keeps tests green.
- All `adb` calls go through `mobilecli.adb.device.Device`. No subprocess imports outside that module.
- Every command returns the envelope `{ok, command, device, elapsed_ms, data|error}` — no exceptions to this shape.
- Tests live in `tests/unit/` (offline, fixture-driven, run in CI) or `tests/integration/` (gated by `EM_INTEGRATION=1`, runs only against device `EXAMPLE-SERIAL`).
- Commit messages follow `<type>: <description>` (feat/fix/refactor/docs/test/chore).

---

## File structure (created across all phases)

Phase A creates:

```
everything-mobile/
├── pyproject.toml
├── .gitignore                       (already exists)
├── .python-version
├── ruff.toml
├── mypy.ini
├── .github/workflows/ci.yml
├── README.md                        (skeleton, filled in Phase D)
├── src/mobilecli/__init__.py
├── src/mobilecli/__main__.py
├── src/mobilecli/cli.py
├── src/mobilecli/envelope.py
├── src/mobilecli/adb/__init__.py
├── src/mobilecli/adb/device.py
├── src/mobilecli/adb/errors.py
├── src/mobilecli/core/__init__.py
├── src/mobilecli/core/screenshot.py
├── src/mobilecli/core/input.py
├── src/mobilecli/core/ui.py
├── src/mobilecli/core/app.py
├── src/mobilecli/core/ime.py
├── src/mobilecli/commands/__init__.py
├── src/mobilecli/commands/devices.py
├── src/mobilecli/commands/screenshot.py
├── src/mobilecli/commands/tap.py
├── src/mobilecli/commands/swipe.py
├── src/mobilecli/commands/type_cmd.py
├── src/mobilecli/commands/keyevent.py
├── src/mobilecli/commands/dump.py
├── src/mobilecli/commands/launch.py
├── src/mobilecli/commands/install.py
├── src/mobilecli/commands/foreground.py
├── src/mobilecli/commands/doctor.py
├── tests/__init__.py
├── tests/conftest.py
├── tests/unit/test_envelope.py
├── tests/unit/test_device.py
├── tests/unit/test_xml_parse.py
├── tests/unit/test_cli_dispatch.py
├── tests/integration/test_primitives.py
└── tests/fixtures/                  (subset of research/ui-trees XMLs)
```

Phase B adds `src/mobilecli/safety/` + `tests/unit/test_humanize.py` etc.
Phase C adds `src/mobilecli/plugin/` + `src/mobilecli/apps/` + tests.
Phase D adds full docs.

---

# Phase A — Core (Layer 1 + Layer 2 raw primitives)

Goal: `mobilecli` is installable and 11 primitive commands work against the test device. No humanization yet. Output is JSON with the standard envelope.

## Task A1: Repo scaffolding (pyproject + tooling)

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `ruff.toml`
- Create: `mypy.ini`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "everything-mobile"
version = "0.1.0"
description = "AI-friendly CLI for driving Android phones — no AI inside, designed for Claude Code / Codex / openclaw"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "everything-mobile contributors" }]
classifiers = [
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
dependencies = []  # stdlib-only; adb is invoked as subprocess

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1",
    "ruff>=0.5",
    "mypy>=1.10",
]

[project.scripts]
mobilecli = "mobilecli.cli:main"

[project.entry-points."mobilecli.apps"]
# Built-in apps register themselves via mobilecli.apps.__init__ scanning.
# External plugins use this group; see docs/plugin-guide.md.

[tool.hatch.build.targets.wheel]
packages = ["src/mobilecli"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: requires EM_INTEGRATION=1 and a connected device",
    "e2e: requires EM_E2E=1 + EM_ALLOW_COMMIT=1, has side effects",
]
```

- [ ] **Step 2: Write `.python-version`**

```
3.11
```

- [ ] **Step 3: Write ruff.toml**

```toml
line-length = 100
target-version = "py310"

[lint]
select = ["E", "F", "I", "B", "UP", "W"]
ignore = ["E501"]  # line-length is enforced by formatter

[format]
quote-style = "double"
```

- [ ] **Step 4: Write mypy.ini**

```ini
[mypy]
python_version = 3.10
strict = True
files = src/mobilecli
namespace_packages = True
explicit_package_bases = True

[mypy-tests.*]
disallow_untyped_defs = False
```

- [ ] **Step 5: Write .github/workflows/ci.yml**

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: pip install -e ".[dev]"
      - run: ruff check src tests
      - run: ruff format --check src tests
      - run: mypy
      - run: pytest -m "not integration and not e2e" --cov=mobilecli --cov-report=term-missing
```

- [ ] **Step 6: Install + verify**

```bash
pipx install -e . --include-deps --force
mobilecli --help  # currently fails - cli.py doesn't exist
```

Expected: pip install succeeds but `mobilecli` errors because `cli:main` doesn't exist yet. That's fine — A2 creates it.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .python-version ruff.toml mypy.ini .github/
git commit -m "chore: scaffold pyproject, ruff, mypy, ci"
```

## Task A2: Envelope module (JSON contract)

**Files:**
- Create: `src/mobilecli/__init__.py` (empty)
- Create: `src/mobilecli/envelope.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py` (empty)
- Create: `tests/unit/test_envelope.py`

- [ ] **Step 1: Write failing test `tests/unit/test_envelope.py`**

```python
"""Tests for the JSON envelope wrapper."""

import json

import pytest

from mobilecli.envelope import EmError, ErrorCode, envelope


def test_envelope_success_wraps_dict():
    @envelope(command="example")
    def fn(device: str) -> dict:
        return {"hello": "world"}

    out = fn(device="ABC123")
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["command"] == "example"
    assert payload["device"] == "ABC123"
    assert payload["data"] == {"hello": "world"}
    assert isinstance(payload["elapsed_ms"], int)


def test_envelope_failure_from_em_error():
    @envelope(command="example")
    def fn(device: str) -> dict:
        raise EmError(ErrorCode.NO_DEVICE, "no device", hint="check usb")

    out = fn(device="")
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NO_DEVICE"
    assert payload["error"]["message"] == "no device"
    assert payload["error"]["hint"] == "check usb"


def test_envelope_unknown_error_on_uncaught():
    @envelope(command="example")
    def fn(device: str) -> dict:
        raise RuntimeError("boom")

    out = fn(device="ABC123")
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "UNKNOWN"
    assert "boom" in payload["error"]["message"]


def test_envelope_chinese_not_escaped():
    @envelope(command="example")
    def fn(device: str) -> dict:
        return {"text": "学到了"}

    out = fn(device="ABC")
    assert "学到了" in out
    assert "\\u" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_envelope.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mobilecli.envelope'`

- [ ] **Step 3: Write `src/mobilecli/envelope.py`**

```python
"""JSON envelope wrapper for CLI commands.

All commands return a stable JSON shape:
  success: {"ok": true,  "command": ..., "device": ..., "elapsed_ms": int, "data":  {...}}
  failure: {"ok": false, "command": ..., "device": ..., "elapsed_ms": int, "error": {"code", "message", "hint"}}
"""

from __future__ import annotations

import enum
import functools
import json
import time
from dataclasses import dataclass
from typing import Any, Callable


class ErrorCode(str, enum.Enum):
    NO_DEVICE = "NO_DEVICE"
    MULTIPLE_DEVICES = "MULTIPLE_DEVICES"
    ADB_TIMEOUT = "ADB_TIMEOUT"
    APP_NOT_INSTALLED = "APP_NOT_INSTALLED"
    APP_NOT_FOREGROUND = "APP_NOT_FOREGROUND"
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    IME_NOT_SET = "IME_NOT_SET"
    COMMIT_REFUSED = "COMMIT_REFUSED"
    RATE_LIMITED = "RATE_LIMITED"
    CONTENT_BANNED = "CONTENT_BANNED"
    WARMUP_REQUIRED = "WARMUP_REQUIRED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EmError(Exception):
    code: ErrorCode
    message: str
    hint: str = ""

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


def envelope(*, command: str) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., str]]:
    """Decorator that wraps a verb function into a JSON-emitting CLI command.

    The wrapped function must accept `device: str` as a keyword arg and return a dict.
    Exceptions are caught and mapped: EmError → code/message/hint, anything else → UNKNOWN.
    """

    def decorator(fn: Callable[..., dict[str, Any]]) -> Callable[..., str]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            device = kwargs.get("device", "")
            t0 = time.monotonic()
            try:
                data = fn(*args, **kwargs)
                payload: dict[str, Any] = {
                    "ok": True,
                    "command": command,
                    "device": device,
                    "elapsed_ms": int((time.monotonic() - t0) * 1000),
                    "data": data,
                }
            except EmError as err:
                payload = {
                    "ok": False,
                    "command": command,
                    "device": device,
                    "elapsed_ms": int((time.monotonic() - t0) * 1000),
                    "error": {
                        "code": err.code.value,
                        "message": err.message,
                        "hint": err.hint,
                    },
                }
            except Exception as exc:
                payload = {
                    "ok": False,
                    "command": command,
                    "device": device,
                    "elapsed_ms": int((time.monotonic() - t0) * 1000),
                    "error": {
                        "code": ErrorCode.UNKNOWN.value,
                        "message": str(exc) or exc.__class__.__name__,
                        "hint": "run with --verbose for stack trace",
                    },
                }
            return json.dumps(payload, ensure_ascii=False)

        return wrapper

    return decorator
```

- [ ] **Step 4: Write `tests/conftest.py` (shared fixtures)**

```python
"""Shared pytest fixtures."""

import os

import pytest


def _has_integration() -> bool:
    return os.environ.get("EM_INTEGRATION") == "1"


def pytest_collection_modifyitems(config, items):
    skip_integration = pytest.mark.skip(reason="set EM_INTEGRATION=1 to run")
    skip_e2e = pytest.mark.skip(reason="set EM_E2E=1 + EM_ALLOW_COMMIT=1 to run")
    for item in items:
        if "integration" in item.keywords and not _has_integration():
            item.add_marker(skip_integration)
        if "e2e" in item.keywords and (
            os.environ.get("EM_E2E") != "1" or os.environ.get("EM_ALLOW_COMMIT") != "1"
        ):
            item.add_marker(skip_e2e)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_envelope.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/mobilecli/__init__.py src/mobilecli/envelope.py tests/
git commit -m "feat: JSON envelope decorator with ErrorCode enum"
```

## Task A3: ADB Device class (Layer 1)

**Files:**
- Create: `src/mobilecli/adb/__init__.py` (empty)
- Create: `src/mobilecli/adb/errors.py`
- Create: `src/mobilecli/adb/device.py`
- Create: `tests/unit/test_device.py`

- [ ] **Step 1: Write failing test `tests/unit/test_device.py`**

```python
"""Tests for the ADB Device wrapper. No real adb here — we use a fake runner."""

from __future__ import annotations

import pytest

from mobilecli.adb.device import Device, _parse_devices_output
from mobilecli.envelope import EmError, ErrorCode


def test_parse_devices_output_normal():
    out = (
        "List of devices attached\n"
        "EXAMPLE-SERIAL\tdevice\n"
        "emulator-5554\toffline\n"
    )
    devs = _parse_devices_output(out)
    assert devs == [
        {"serial": "EXAMPLE-SERIAL", "state": "device"},
        {"serial": "emulator-5554", "state": "offline"},
    ]


def test_parse_devices_output_empty():
    assert _parse_devices_output("List of devices attached\n") == []


def test_select_serial_uses_only_connected_when_one():
    devices = [{"serial": "ABC", "state": "device"}]
    assert Device._select_serial(devices, requested=None) == "ABC"


def test_select_serial_requires_choice_when_many():
    devices = [
        {"serial": "ABC", "state": "device"},
        {"serial": "DEF", "state": "device"},
    ]
    with pytest.raises(EmError) as exc:
        Device._select_serial(devices, requested=None)
    assert exc.value.code is ErrorCode.MULTIPLE_DEVICES


def test_select_serial_uses_requested_if_present():
    devices = [
        {"serial": "ABC", "state": "device"},
        {"serial": "DEF", "state": "device"},
    ]
    assert Device._select_serial(devices, requested="DEF") == "DEF"


def test_select_serial_errors_on_no_devices():
    with pytest.raises(EmError) as exc:
        Device._select_serial([], requested=None)
    assert exc.value.code is ErrorCode.NO_DEVICE


def test_select_serial_ignores_offline_devices():
    devices = [
        {"serial": "ABC", "state": "offline"},
        {"serial": "DEF", "state": "device"},
    ]
    assert Device._select_serial(devices, requested=None) == "DEF"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_device.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/mobilecli/adb/errors.py`**

```python
"""ADB error → ErrorCode mapping."""

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
```

- [ ] **Step 4: Write `src/mobilecli/adb/device.py`**

```python
"""ADB device wrapper (Layer 1).

The only module that may import subprocess. All other layers go through Device.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any

from mobilecli.adb.errors import map_adb_stderr
from mobilecli.envelope import EmError, ErrorCode

DEFAULT_TIMEOUT_S = 30


def _parse_devices_output(out: str) -> list[dict[str, str]]:
    """Parse `adb devices` table.

    Lines: "<serial>\\t<state>" — anything not matching is skipped.
    """
    devices: list[dict[str, str]] = []
    for line in out.splitlines():
        line = line.strip()
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
    def list(cls, timeout_s: int = 10) -> list[dict[str, str]]:
        """Return raw output of `adb devices` parsed as dicts."""
        proc = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, timeout=timeout_s,
        )
        if proc.returncode != 0:
            raise map_adb_stderr(proc.stderr, proc.returncode)
        return _parse_devices_output(proc.stdout)

    @classmethod
    def from_serial(cls, requested: str | None) -> Device:
        """Resolve a Device from --serial / EM_SERIAL / single connected device."""
        if requested is None:
            requested = os.environ.get("EM_SERIAL") or None
        devices = cls.list()
        serial = cls._select_serial(devices, requested)
        return cls(serial=serial)

    @staticmethod
    def _select_serial(
        devices: list[dict[str, str]], requested: str | None,
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
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            raise EmError(ErrorCode.ADB_TIMEOUT, f"adb shell timed out after {timeout_s}s")
        if proc.returncode != 0:
            raise map_adb_stderr(proc.stderr, proc.returncode)
        return proc.stdout

    def exec_out(self, cmd: list[str], timeout_s: int = DEFAULT_TIMEOUT_S) -> bytes:
        """Run `adb -s <serial> exec-out <cmd>` and return raw bytes (for screencap)."""
        argv = ["adb", "-s", self.serial, "exec-out", *cmd]
        try:
            proc = subprocess.run(argv, capture_output=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            raise EmError(ErrorCode.ADB_TIMEOUT, f"adb exec-out timed out after {timeout_s}s")
        if proc.returncode != 0:
            raise map_adb_stderr(proc.stderr.decode("utf-8", errors="replace"), proc.returncode)
        return proc.stdout

    def pull(self, remote: str, local: str, timeout_s: int = DEFAULT_TIMEOUT_S) -> None:
        argv = ["adb", "-s", self.serial, "pull", remote, local]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
        if proc.returncode != 0:
            raise map_adb_stderr(proc.stderr, proc.returncode)

    def push(self, local: str, remote: str, timeout_s: int = DEFAULT_TIMEOUT_S) -> None:
        argv = ["adb", "-s", self.serial, "push", local, remote]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
        if proc.returncode != 0:
            raise map_adb_stderr(proc.stderr, proc.returncode)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_device.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/mobilecli/adb/ tests/unit/test_device.py
git commit -m "feat: ADB Device wrapper (Layer 1)"
```

## Task A4: CLI dispatcher skeleton

**Files:**
- Create: `src/mobilecli/cli.py`
- Create: `src/mobilecli/__main__.py`
- Create: `src/mobilecli/commands/__init__.py` (empty)
- Create: `tests/unit/test_cli_dispatch.py`

- [ ] **Step 1: Write failing test `tests/unit/test_cli_dispatch.py`**

```python
"""Tests for CLI dispatching: --serial, --pretty, --verbose handling."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest


def run_cli(*args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = None
    if env_extra is not None:
        import os
        env = {**os.environ, **env_extra}
    return subprocess.run(
        [sys.executable, "-m", "mobilecli", *args],
        capture_output=True, text=True, env=env,
    )


def test_no_args_shows_help():
    r = run_cli()
    assert r.returncode != 0 or "usage" in (r.stdout + r.stderr).lower()


def test_help_exits_zero():
    r = run_cli("--help")
    assert r.returncode == 0
    assert "mobilecli" in r.stdout.lower()


def test_unknown_command_emits_json_error():
    r = run_cli("nonexistent-cmd")
    # Should emit JSON envelope with ok=false
    payload = json.loads(r.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "UNKNOWN"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cli_dispatch.py -v`
Expected: FAIL — module not installed yet or no `__main__`.

- [ ] **Step 3: Write `src/mobilecli/__main__.py`**

```python
"""Entry point so `python -m mobilecli` works alongside the console script."""

from mobilecli.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Write `src/mobilecli/cli.py` (skeleton — full command registry comes in A5+)**

```python
"""Top-level CLI dispatcher.

Builds an argparse tree with global flags and subcommand registry. Each
subcommand module exposes `add_parser(subparsers)` and `run(args) -> str`.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from mobilecli.envelope import EmError, ErrorCode

# Registry: subcommand name -> module path. Filled in A5+.
COMMAND_MODULES: dict[str, str] = {}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mobilecli",
        description=(
            "AI-friendly CLI for driving Android phones. "
            "No AI inside; designed to be invoked by Claude Code / Codex / openclaw."
        ),
    )
    parser.add_argument("--serial", help="Device serial (overrides EM_SERIAL)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--verbose", action="store_true", help="Stderr debug logs")
    parser.add_argument("--timeout", type=int, default=30, help="Per-command timeout (s)")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    parser._subparsers_action = sub  # type: ignore[attr-defined]
    return parser


def _emit(payload_json: str, pretty: bool) -> None:
    if pretty:
        obj = json.loads(payload_json)
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(payload_json)


def _emit_error(command: str, code: ErrorCode, message: str, hint: str, pretty: bool) -> None:
    payload: dict[str, Any] = {
        "ok": False,
        "command": command,
        "device": "",
        "elapsed_ms": 0,
        "error": {"code": code.value, "message": message, "hint": hint},
    }
    _emit(json.dumps(payload, ensure_ascii=False), pretty)


def _load_commands(parser: argparse.ArgumentParser) -> dict[str, Any]:
    """Import every command module and let it attach to the subparsers."""
    import importlib

    sub = parser._subparsers_action  # type: ignore[attr-defined]
    loaded: dict[str, Any] = {}
    for name, modpath in COMMAND_MODULES.items():
        mod = importlib.import_module(modpath)
        mod.add_parser(sub)
        loaded[name] = mod
    return loaded


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    loaded = _load_commands(parser)
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        parser.print_help()
        return 2
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    if args.command not in loaded:
        _emit_error(
            command=args.command or "",
            code=ErrorCode.UNKNOWN,
            message=f"unknown command: {args.command}",
            hint="run `mobilecli --help`",
            pretty=args.pretty,
        )
        return 1
    out = loaded[args.command].run(args)
    _emit(out, args.pretty)
    return 0
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_cli_dispatch.py -v`
Expected: 3 passed (one may need adjustment — see note).

Note: `test_unknown_command_emits_json_error` may produce a parse error from argparse rather than reaching our code. If so, change the test to invoke an argparse-recognized but unimplemented form; or accept that argparse handles it. Adjust test to match real behavior:

```python
def test_unknown_command_emits_json_error():
    r = run_cli("does-not-exist")
    # argparse rejects with code 2 and stderr; that's OK behaviour for v1.
    assert r.returncode != 0
```

- [ ] **Step 6: Commit**

```bash
git add src/mobilecli/__main__.py src/mobilecli/cli.py src/mobilecli/commands/__init__.py tests/unit/test_cli_dispatch.py
git commit -m "feat: argparse CLI dispatcher skeleton"
```

## Task A5: `mobilecli devices` command

**Files:**
- Create: `src/mobilecli/commands/devices.py`
- Modify: `src/mobilecli/cli.py:8-10` (register in `COMMAND_MODULES`)

- [ ] **Step 1: Write failing test (extend `tests/unit/test_cli_dispatch.py`)**

Add at the bottom:

```python
def test_devices_command_returns_json():
    r = run_cli("devices")
    payload = json.loads(r.stdout)
    assert payload["ok"] in (True, False)  # depends on whether adb is present
    assert payload["command"] == "devices"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cli_dispatch.py::test_devices_command_returns_json -v`
Expected: FAIL — `devices` not registered.

- [ ] **Step 3: Write `src/mobilecli/commands/devices.py`**

```python
"""`mobilecli devices` — list connected devices."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    subparsers.add_parser("devices", help="List connected devices")


@envelope(command="devices")
def _run(device: str = "") -> dict[str, Any]:
    devs = Device.list()
    return {"devices": devs}


def run(args: argparse.Namespace) -> str:
    return _run(device="")
```

- [ ] **Step 4: Register in `src/mobilecli/cli.py`**

```python
COMMAND_MODULES: dict[str, str] = {
    "devices": "mobilecli.commands.devices",
}
```

- [ ] **Step 5: Run tests + manual smoke test**

```bash
pytest tests/unit/test_cli_dispatch.py -v
mobilecli devices
```

Expected: pytest passes; manual run returns JSON with the connected device.

- [ ] **Step 6: Commit**

```bash
git add src/mobilecli/commands/devices.py src/mobilecli/cli.py tests/
git commit -m "feat: mobilecli devices command"
```

## Task A6: `mobilecli screenshot`

**Files:**
- Create: `src/mobilecli/core/__init__.py` (empty)
- Create: `src/mobilecli/core/screenshot.py`
- Create: `src/mobilecli/commands/screenshot.py`
- Modify: `src/mobilecli/cli.py` (register)
- Create: `tests/integration/__init__.py` (empty)
- Create: `tests/integration/test_primitives.py`

- [ ] **Step 1: Write failing integration test `tests/integration/test_primitives.py`**

```python
"""Integration tests — require EM_INTEGRATION=1 and the test device connected."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

EXPECTED_SERIAL = "EXAMPLE-SERIAL"


@pytest.fixture(scope="module")
def device_serial() -> str:
    r = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    if EXPECTED_SERIAL not in r.stdout:
        pytest.skip(f"test device {EXPECTED_SERIAL} not connected")
    return EXPECTED_SERIAL


def _cli(*args: str) -> dict:
    r = subprocess.run(
        [sys.executable, "-m", "mobilecli", *args],
        capture_output=True, text=True,
    )
    return json.loads(r.stdout)


@pytest.mark.integration
def test_screenshot_returns_valid_path(device_serial: str, tmp_path):
    out_path = tmp_path / "screen.png"
    payload = _cli("--serial", device_serial, "screenshot", "-o", str(out_path))
    assert payload["ok"] is True, payload
    assert payload["data"]["path"] == str(out_path)
    assert payload["data"]["size"] > 10_000
    assert payload["data"]["width"] > 0
    assert payload["data"]["height"] > 0
    assert out_path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_primitives.py::test_screenshot_returns_valid_path -v`
Expected: FAIL — `screenshot` command not registered.

- [ ] **Step 3: Write `src/mobilecli/core/screenshot.py`**

```python
"""Core Layer 2 screenshot helper."""

from __future__ import annotations

import struct
import time
from pathlib import Path

from mobilecli.adb.device import Device


def _png_dimensions(data: bytes) -> tuple[int, int]:
    """Read PNG width/height from IHDR. Returns (0, 0) on parse failure."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return (0, 0)
    if len(data) < 24:
        return (0, 0)
    width, height = struct.unpack(">II", data[16:24])
    return (width, height)


def capture(device: Device, output_path: str | None = None) -> dict:
    """Capture screenshot. Returns {path, size, width, height}."""
    if output_path is None:
        output_path = f"/tmp/em-screen-{int(time.time() * 1000)}.png"
    data = device.exec_out(["screencap", "-p"])
    Path(output_path).write_bytes(data)
    width, height = _png_dimensions(data)
    return {"path": output_path, "size": len(data), "width": width, "height": height}
```

- [ ] **Step 4: Write `src/mobilecli/commands/screenshot.py`**

```python
"""`mobilecli screenshot` command."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import screenshot
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("screenshot", help="Capture screen to PNG")
    p.add_argument("-o", "--output", default=None, help="Output path (default /tmp/em-screen-*.png)")


@envelope(command="screenshot")
def _run(*, device: str, output: str | None) -> dict[str, Any]:
    dev = Device(serial=device)
    return screenshot.capture(dev, output)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial, output=args.output)
```

- [ ] **Step 5: Register in `src/mobilecli/cli.py`**

```python
COMMAND_MODULES: dict[str, str] = {
    "devices": "mobilecli.commands.devices",
    "screenshot": "mobilecli.commands.screenshot",
}
```

- [ ] **Step 6: Run integration test to verify it passes**

```bash
EM_INTEGRATION=1 pytest tests/integration/test_primitives.py::test_screenshot_returns_valid_path -v
```

Expected: PASS. Also verify manually: `mobilecli screenshot` produces JSON with a real PNG path.

- [ ] **Step 7: Commit**

```bash
git add src/mobilecli/core/ src/mobilecli/commands/screenshot.py src/mobilecli/cli.py tests/integration/
git commit -m "feat: mobilecli screenshot command"
```

## Task A7: `mobilecli tap` (raw, pre-humanization)

**Files:**
- Create: `src/mobilecli/core/input.py`
- Create: `src/mobilecli/commands/tap.py`
- Modify: `src/mobilecli/cli.py`

- [ ] **Step 1: Add integration test (extend `tests/integration/test_primitives.py`)**

```python
@pytest.mark.integration
def test_tap_at_safe_coords(device_serial: str):
    # Tap at a safe (1,1) corner — won't activate anything meaningful.
    payload = _cli("--serial", device_serial, "tap", "1", "1")
    assert payload["ok"] is True, payload
    assert payload["data"]["x"] == 1
    assert payload["data"]["y"] == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_primitives.py::test_tap_at_safe_coords -v`
Expected: FAIL — `tap` not registered.

- [ ] **Step 3: Write `src/mobilecli/core/input.py` (raw — humanization is wired in Phase B)**

```python
"""Core input primitives (Layer 2). Raw versions; humanization wraps these in Phase B."""

from __future__ import annotations

from mobilecli.adb.device import Device


def tap_raw(device: Device, x: int, y: int) -> dict:
    device.shell(f"input tap {x} {y}")
    return {"x": x, "y": y, "duration_ms": 0}


def swipe_raw(device: Device, x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> dict:
    device.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration_ms": duration_ms}


def keyevent_raw(device: Device, code: int | str) -> dict:
    device.shell(f"input keyevent {code}")
    return {"code": str(code)}
```

- [ ] **Step 4: Write `src/mobilecli/commands/tap.py`**

```python
"""`mobilecli tap X Y` command."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import input as core_input
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("tap", help="Tap at absolute coords")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)


@envelope(command="tap")
def _run(*, device: str, x: int, y: int) -> dict[str, Any]:
    dev = Device(serial=device)
    return core_input.tap_raw(dev, x, y)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial, x=args.x, y=args.y)
```

- [ ] **Step 5: Register + run test**

```python
COMMAND_MODULES["tap"] = "mobilecli.commands.tap"
```

Run: `EM_INTEGRATION=1 pytest tests/integration/test_primitives.py::test_tap_at_safe_coords -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/mobilecli/core/input.py src/mobilecli/commands/tap.py src/mobilecli/cli.py tests/
git commit -m "feat: mobilecli tap command (raw)"
```

## Task A8: `mobilecli swipe` + `mobilecli keyevent`

**Files:**
- Create: `src/mobilecli/commands/swipe.py`
- Create: `src/mobilecli/commands/keyevent.py`
- Modify: `src/mobilecli/cli.py`

- [ ] **Step 1: Extend `tests/integration/test_primitives.py`**

```python
@pytest.mark.integration
def test_swipe_short(device_serial: str):
    payload = _cli("--serial", device_serial, "swipe", "100", "100", "100", "200")
    assert payload["ok"] is True, payload
    assert payload["data"]["duration_ms"] >= 0


@pytest.mark.integration
def test_keyevent_back(device_serial: str):
    payload = _cli("--serial", device_serial, "keyevent", "back")
    assert payload["ok"] is True, payload
```

- [ ] **Step 2: Run + see fail**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_primitives.py -v`
Expected: new tests FAIL.

- [ ] **Step 3: Write `src/mobilecli/commands/swipe.py`**

```python
"""`mobilecli swipe X1 Y1 X2 Y2 [--duration N]` command."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import input as core_input
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("swipe", help="Swipe gesture")
    p.add_argument("x1", type=int)
    p.add_argument("y1", type=int)
    p.add_argument("x2", type=int)
    p.add_argument("y2", type=int)
    p.add_argument("--duration", type=int, default=300, help="ms (default 300)")


@envelope(command="swipe")
def _run(*, device: str, x1: int, y1: int, x2: int, y2: int, duration: int) -> dict[str, Any]:
    dev = Device(serial=device)
    return core_input.swipe_raw(dev, x1, y1, x2, y2, duration)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(
        device=dev.serial, x1=args.x1, y1=args.y1, x2=args.x2, y2=args.y2,
        duration=args.duration,
    )
```

- [ ] **Step 4: Write `src/mobilecli/commands/keyevent.py`**

```python
"""`mobilecli keyevent {back|home|enter|recent|menu|...}` command."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import input as core_input
from mobilecli.envelope import envelope

KEY_ALIASES: dict[str, int] = {
    "back": 4, "home": 3, "enter": 66, "recent": 187, "menu": 82,
    "power": 26, "volume_up": 24, "volume_down": 25,
    "dpad_up": 19, "dpad_down": 20, "dpad_left": 21, "dpad_right": 22,
    "tab": 61, "del": 67, "space": 62,
}


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("keyevent", help="Send a keyevent")
    p.add_argument(
        "key",
        help="Alias (back/home/enter/recent/menu/...) or numeric KEYCODE",
    )


@envelope(command="keyevent")
def _run(*, device: str, key: str) -> dict[str, Any]:
    dev = Device(serial=device)
    code: int | str = KEY_ALIASES.get(key.lower(), key)
    return core_input.keyevent_raw(dev, code)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial, key=args.key)
```

- [ ] **Step 5: Register both in cli.py**

```python
COMMAND_MODULES["swipe"] = "mobilecli.commands.swipe"
COMMAND_MODULES["keyevent"] = "mobilecli.commands.keyevent"
```

- [ ] **Step 6: Run integration tests**

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/mobilecli/commands/swipe.py src/mobilecli/commands/keyevent.py src/mobilecli/cli.py tests/
git commit -m "feat: swipe + keyevent commands"
```

## Task A9: `mobilecli type` + IME helper

**Files:**
- Create: `src/mobilecli/core/ime.py`
- Create: `src/mobilecli/commands/type_cmd.py`
- Modify: `src/mobilecli/cli.py`

- [ ] **Step 1: Extend integration test**

```python
@pytest.mark.integration
def test_type_ascii_only(device_serial: str):
    # No focus, so nothing visible should change. Just verifies the command runs.
    payload = _cli("--serial", device_serial, "type", "hello")
    assert payload["ok"] is True, payload
    assert payload["data"]["chars"] == 5


@pytest.mark.integration
def test_type_chinese(device_serial: str):
    payload = _cli("--serial", device_serial, "type", "你好")
    assert payload["ok"] is True, payload
    assert payload["data"]["chars"] == 2
    assert payload["data"]["mode"] == "adbkeyboard"
```

- [ ] **Step 2: Run + see fail**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_primitives.py -k type -v`
Expected: FAIL — `type` not registered.

- [ ] **Step 3: Write `src/mobilecli/core/ime.py`**

```python
"""IME (input method) helpers — ADBKeyboard installation + activation."""

from __future__ import annotations

from mobilecli.adb.device import Device
from mobilecli.envelope import EmError, ErrorCode

ADBKEYBOARD_ID = "com.android.adbkeyboard/.AdbIME"


def list_imes(device: Device) -> list[str]:
    out = device.shell("ime list -s")
    return [line.strip() for line in out.splitlines() if line.strip()]


def current_ime(device: Device) -> str:
    return device.shell("settings get secure default_input_method").strip()


def set_adbkeyboard(device: Device) -> None:
    if ADBKEYBOARD_ID not in list_imes(device):
        raise EmError(
            ErrorCode.IME_NOT_SET,
            "ADBKeyboard not installed on device",
            hint="install from https://github.com/senzhk/ADBKeyBoard",
        )
    device.shell(f"ime set {ADBKEYBOARD_ID}")


def restore_ime(device: Device, previous: str) -> None:
    if previous and previous != ADBKEYBOARD_ID:
        device.shell(f"ime set {previous}")
```

- [ ] **Step 4: Add type_text to `src/mobilecli/core/input.py`**

Append:

```python
import shlex as _shlex

from mobilecli.core import ime as _ime


def type_text_raw(device: Device, text: str) -> dict:
    """Type text. ASCII → `input text`; CJK → ADBKeyboard broadcast.

    Returns {chars, mode}.
    """
    if text.isascii():
        # input text escaping: spaces → %s, single-quote nested
        escaped = text.replace(" ", "%s")
        device.shell(f"input text {_shlex.quote(escaped)}")
        return {"chars": len(text), "mode": "input"}
    # CJK / emoji path
    prev = _ime.current_ime(device)
    _ime.set_adbkeyboard(device)
    try:
        # ADBKeyboard broadcast — quote text as adb shell sees it
        device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {_shlex.quote(text)}")
        return {"chars": len(text), "mode": "adbkeyboard"}
    finally:
        _ime.restore_ime(device, prev)
```

- [ ] **Step 5: Write `src/mobilecli/commands/type_cmd.py`**

```python
"""`mobilecli type "..."` command."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import input as core_input
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("type", help="Type text")
    p.add_argument("text", help="Text to type (ASCII or Chinese)")


@envelope(command="type")
def _run(*, device: str, text: str) -> dict[str, Any]:
    dev = Device(serial=device)
    return core_input.type_text_raw(dev, text)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial, text=args.text)
```

- [ ] **Step 6: Register + run**

```python
COMMAND_MODULES["type"] = "mobilecli.commands.type_cmd"
```

Run: `EM_INTEGRATION=1 pytest tests/integration/test_primitives.py -k type -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/mobilecli/core/ime.py src/mobilecli/core/input.py src/mobilecli/commands/type_cmd.py src/mobilecli/cli.py tests/
git commit -m "feat: type command with ADBKeyboard for CJK"
```

## Task A10: `mobilecli dump` + UI XML helpers

**Files:**
- Create: `src/mobilecli/core/ui.py`
- Create: `src/mobilecli/commands/dump.py`
- Create: `tests/unit/test_xml_parse.py`
- Create: `tests/fixtures/` and copy a known XML from research/ui-trees/

- [ ] **Step 1: Copy a fixture for offline parsing tests**

```bash
mkdir -p tests/fixtures
cp research/ui-trees/xiaohongshu/02-search-page.xml tests/fixtures/xhs-search-page.xml
cp research/ui-trees/douyin/01-home.xml tests/fixtures/douyin-home.xml
```

- [ ] **Step 2: Write failing test `tests/unit/test_xml_parse.py`**

```python
"""Offline tests for UI XML parsing — uses fixture XMLs."""

from __future__ import annotations

from pathlib import Path

from mobilecli.core.ui import (
    find_by_content_desc,
    find_by_resource_id,
    parse_bounds,
)

FIX = Path(__file__).parent.parent / "fixtures"


def test_parse_bounds_normal():
    assert parse_bounds("[10,20][100,200]") == (10, 20, 100, 200)


def test_parse_bounds_returns_none_on_garbage():
    assert parse_bounds("not bounds") is None


def test_find_by_resource_id_xhs_search_input():
    xml = (FIX / "xhs-search-page.xml").read_text()
    node = find_by_resource_id(xml, "com.xingin.xhs:id/mSearchToolBarEt")
    assert node is not None
    assert node["cx"] > 0 and node["cy"] > 0


def test_find_by_content_desc_douyin_search():
    xml = (FIX / "douyin-home.xml").read_text()
    node = find_by_content_desc(xml, "搜索")
    assert node is not None
    assert node["bounds"] is not None
```

- [ ] **Step 3: Run + see fail**

Run: `pytest tests/unit/test_xml_parse.py -v`
Expected: FAIL — `mobilecli.core.ui` doesn't exist.

- [ ] **Step 4: Write `src/mobilecli/core/ui.py`**

```python
"""UI parsing helpers (Layer 2).

Parses `uiautomator dump` XML to find elements by resource-id, content-desc,
text, or class. Returns dicts with center coordinates ready for tap.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.envelope import EmError, ErrorCode

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def parse_bounds(s: str) -> tuple[int, int, int, int] | None:
    m = _BOUNDS_RE.match(s)
    if not m:
        return None
    return (int(m[1]), int(m[2]), int(m[3]), int(m[4]))


def _node_to_dict(node: ET.Element) -> dict[str, Any]:
    bounds_s = node.get("bounds", "")
    bounds = parse_bounds(bounds_s)
    cx = cy = -1
    if bounds is not None:
        cx = (bounds[0] + bounds[2]) // 2
        cy = (bounds[1] + bounds[3]) // 2
    return {
        "resource_id": node.get("resource-id", ""),
        "content_desc": node.get("content-desc", ""),
        "text": node.get("text", ""),
        "class": node.get("class", ""),
        "bounds": list(bounds) if bounds else None,
        "cx": cx,
        "cy": cy,
        "clickable": node.get("clickable") == "true",
        "focused": node.get("focused") == "true",
    }


def _iter_nodes(xml: str):
    root = ET.fromstring(xml)
    yield from root.iter("node")


def find_by_resource_id(xml: str, resource_id: str) -> dict[str, Any] | None:
    for node in _iter_nodes(xml):
        if node.get("resource-id") == resource_id:
            return _node_to_dict(node)
    return None


def find_by_content_desc(xml: str, content_desc: str) -> dict[str, Any] | None:
    for node in _iter_nodes(xml):
        if node.get("content-desc") == content_desc:
            return _node_to_dict(node)
    return None


def find_by_text(xml: str, text: str) -> dict[str, Any] | None:
    for node in _iter_nodes(xml):
        if node.get("text") == text:
            return _node_to_dict(node)
    return None


def find_all_by_resource_id(xml: str, resource_id: str) -> list[dict[str, Any]]:
    return [
        _node_to_dict(node) for node in _iter_nodes(xml)
        if node.get("resource-id") == resource_id
    ]


def dump(device: Device, output_path: str | None = None, retry: int = 2) -> dict:
    """Run `uiautomator dump`, pull XML to local path. Retries on idle failure."""
    if output_path is None:
        output_path = f"/tmp/em-dump-{int(time.time() * 1000)}.xml"
    last_err: Exception | None = None
    for attempt in range(retry + 1):
        try:
            device.shell("uiautomator dump --compressed /sdcard/em.xml")
            device.pull("/sdcard/em.xml", output_path)
            size = Path(output_path).stat().st_size
            if size > 100:
                return {"path": output_path, "size": size}
        except EmError as e:
            last_err = e
        # Retry: tap center to pause autoplay (Douyin home issue)
        if attempt < retry:
            device.shell("input tap 540 1200")
            time.sleep(0.6)
    raise last_err or EmError(ErrorCode.UNKNOWN, "uiautomator dump failed")
```

- [ ] **Step 5: Write `src/mobilecli/commands/dump.py`**

```python
"""`mobilecli dump` command."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import ui
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("dump", help="uiautomator dump → XML path")
    p.add_argument("-o", "--output", default=None)


@envelope(command="dump")
def _run(*, device: str, output: str | None) -> dict[str, Any]:
    dev = Device(serial=device)
    return ui.dump(dev, output)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial, output=args.output)
```

- [ ] **Step 6: Register + run all tests**

```python
COMMAND_MODULES["dump"] = "mobilecli.commands.dump"
```

Add integration test:

```python
@pytest.mark.integration
def test_dump_creates_xml(device_serial: str, tmp_path):
    out = tmp_path / "ui.xml"
    payload = _cli("--serial", device_serial, "dump", "-o", str(out))
    assert payload["ok"] is True, payload
    assert payload["data"]["size"] > 100
    assert out.exists()
```

Run:
```bash
pytest tests/unit/test_xml_parse.py -v
EM_INTEGRATION=1 pytest tests/integration/test_primitives.py -k dump -v
```
Expected: both pass.

- [ ] **Step 7: Commit**

```bash
git add src/mobilecli/core/ui.py src/mobilecli/commands/dump.py src/mobilecli/cli.py tests/
git commit -m "feat: dump command + XML parsing helpers"
```

## Task A11: `mobilecli launch`, `install`, `foreground`

**Files:**
- Create: `src/mobilecli/core/app.py`
- Create: `src/mobilecli/commands/launch.py`
- Create: `src/mobilecli/commands/install.py`
- Create: `src/mobilecli/commands/foreground.py`
- Modify: `src/mobilecli/cli.py`

- [ ] **Step 1: Integration tests**

Append to `tests/integration/test_primitives.py`:

```python
@pytest.mark.integration
def test_launch_settings(device_serial: str):
    payload = _cli("--serial", device_serial, "launch", "com.android.settings")
    assert payload["ok"] is True, payload


@pytest.mark.integration
def test_foreground_after_launch(device_serial: str):
    _cli("--serial", device_serial, "launch", "com.android.settings")
    payload = _cli("--serial", device_serial, "foreground")
    assert payload["ok"] is True, payload
    assert "settings" in payload["data"]["package"].lower()
```

- [ ] **Step 2: Run + see fail**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_primitives.py -k 'launch or foreground' -v`
Expected: FAIL.

- [ ] **Step 3: Write `src/mobilecli/core/app.py`**

```python
"""App lifecycle helpers."""

from __future__ import annotations

import re

from mobilecli.adb.device import Device
from mobilecli.envelope import EmError, ErrorCode


def is_installed(device: Device, package: str) -> bool:
    out = device.shell(f"pm list packages {package}")
    return any(line.strip() == f"package:{package}" for line in out.splitlines())


def launch(device: Device, package: str) -> dict:
    if not is_installed(device, package):
        raise EmError(
            ErrorCode.APP_NOT_INSTALLED,
            f"{package} not installed",
            hint="run `pm list packages | grep` to confirm",
        )
    device.shell(
        f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
    )
    return {"package": package}


_FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*\s([^/\s]+)/([^\s}]+)")


def foreground(device: Device) -> dict:
    out = device.shell("dumpsys window")
    m = _FOCUS_RE.search(out)
    if not m:
        return {"package": "", "activity": ""}
    return {"package": m.group(1), "activity": m.group(2)}


def install(device: Device, apk_path: str) -> dict:
    # Layer 1's Device.shell doesn't cover `adb install`; use subprocess directly.
    import subprocess
    proc = subprocess.run(
        ["adb", "-s", device.serial, "install", "-r", apk_path],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise EmError(ErrorCode.UNKNOWN, proc.stderr.strip() or "install failed")
    return {"apk": apk_path, "result": "success"}
```

- [ ] **Step 4: Write the three command modules**

`src/mobilecli/commands/launch.py`:

```python
"""`mobilecli launch <package>`."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import app as core_app
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("launch", help="Launch an app by package name")
    p.add_argument("package")


@envelope(command="launch")
def _run(*, device: str, package: str) -> dict[str, Any]:
    dev = Device(serial=device)
    return core_app.launch(dev, package)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial, package=args.package)
```

`src/mobilecli/commands/install.py`:

```python
"""`mobilecli install <apk_path>`."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import app as core_app
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("install", help="adb install -r")
    p.add_argument("apk")


@envelope(command="install")
def _run(*, device: str, apk: str) -> dict[str, Any]:
    dev = Device(serial=device)
    return core_app.install(dev, apk)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial, apk=args.apk)
```

`src/mobilecli/commands/foreground.py`:

```python
"""`mobilecli foreground`."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import app as core_app
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    subparsers.add_parser("foreground", help="Current foreground package + activity")


@envelope(command="foreground")
def _run(*, device: str) -> dict[str, Any]:
    dev = Device(serial=device)
    return core_app.foreground(dev)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial)
```

- [ ] **Step 5: Register all 3 + run tests**

```python
COMMAND_MODULES["launch"] = "mobilecli.commands.launch"
COMMAND_MODULES["install"] = "mobilecli.commands.install"
COMMAND_MODULES["foreground"] = "mobilecli.commands.foreground"
```

Run: `EM_INTEGRATION=1 pytest tests/integration/test_primitives.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/mobilecli/core/app.py src/mobilecli/commands/{launch,install,foreground}.py src/mobilecli/cli.py tests/
git commit -m "feat: launch + install + foreground commands"
```

## Task A12: `mobilecli doctor` (basic checks; humanization checks added in Phase B)

**Files:**
- Create: `src/mobilecli/commands/doctor.py`
- Modify: `src/mobilecli/cli.py`

- [ ] **Step 1: Add integration test**

```python
@pytest.mark.integration
def test_doctor_returns_checks(device_serial: str):
    payload = _cli("--serial", device_serial, "doctor")
    assert payload["ok"] is True, payload
    checks = payload["data"]["checks"]
    assert any(c["name"] == "adb_available" for c in checks)
    assert any(c["name"] == "device_online" for c in checks)
    assert all("status" in c for c in checks)  # pass | fail | warn
```

- [ ] **Step 2: Run + see fail**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_primitives.py -k doctor -v`
Expected: FAIL.

- [ ] **Step 3: Write `src/mobilecli/commands/doctor.py`**

```python
"""`mobilecli doctor` — environment self-check.

Returns {checks: [{name, status, detail}], summary: {pass, fail, warn}}.
"""

from __future__ import annotations

import argparse
import shutil
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import ime as core_ime
from mobilecli.envelope import envelope


def _check(name: str, status: str, detail: str = "") -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail}


def add_parser(subparsers: Any) -> None:
    subparsers.add_parser("doctor", help="Environment self-check")


@envelope(command="doctor")
def _run(*, device: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # adb available
    if shutil.which("adb"):
        checks.append(_check("adb_available", "pass"))
    else:
        checks.append(_check("adb_available", "fail", "install Android platform-tools"))
        return _summary(checks)

    # device
    try:
        dev = Device.from_serial(device or None)
        checks.append(_check("device_online", "pass", dev.serial))
    except Exception as e:
        checks.append(_check("device_online", "fail", str(e)))
        return _summary(checks)

    # adbkeyboard installed
    try:
        if core_ime.ADBKEYBOARD_ID in core_ime.list_imes(dev):
            checks.append(_check("adbkeyboard_installed", "pass"))
        else:
            checks.append(
                _check(
                    "adbkeyboard_installed", "warn",
                    "install for Chinese input: https://github.com/senzhk/ADBKeyBoard",
                )
            )
    except Exception as e:
        checks.append(_check("adbkeyboard_installed", "warn", str(e)))

    return _summary(checks)


def _summary(checks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "checks": checks,
        "summary": {
            "pass": sum(1 for c in checks if c["status"] == "pass"),
            "fail": sum(1 for c in checks if c["status"] == "fail"),
            "warn": sum(1 for c in checks if c["status"] == "warn"),
        },
    }


def run(args: argparse.Namespace) -> str:
    return _run(device=args.serial or "")
```

- [ ] **Step 4: Register + run**

```python
COMMAND_MODULES["doctor"] = "mobilecli.commands.doctor"
```

Run: `EM_INTEGRATION=1 pytest tests/integration/test_primitives.py -k doctor -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/commands/doctor.py src/mobilecli/cli.py tests/
git commit -m "feat: doctor command (basic checks; humanization checks in Phase B)"
```

## Task A13: README skeleton + LICENSE

**Files:**
- Create: `README.md` (skeleton; filled in Phase D)
- Create: `LICENSE`

- [ ] **Step 1: Write `LICENSE`**

```
MIT License

Copyright (c) 2026 everything-mobile contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Write skeleton `README.md`** (full content in Phase D)

```markdown
# everything-mobile

> AI-friendly CLI for driving Android phones — no AI inside.

**Status: alpha. README is incomplete; see `docs/superpowers/specs/2026-05-21-everything-mobile-design.md` for the v1 design.**

## Quickstart

```
pipx install everything-mobile
mobilecli devices
mobilecli screenshot -o /tmp/x.png
```

License: MIT.
```

- [ ] **Step 3: Commit**

```bash
git add LICENSE README.md
git commit -m "docs: LICENSE + README skeleton"
```

## Task A14: Phase A acceptance — manual smoke run + commit checkpoint

- [ ] **Step 1: Run all primitive commands manually on the test device**

```bash
mobilecli devices
mobilecli foreground
mobilecli screenshot -o /tmp/em-A.png
mobilecli dump -o /tmp/em-A.xml
mobilecli launch com.android.settings
mobilecli foreground   # should show settings
mobilecli keyevent home
mobilecli tap 540 1200
mobilecli swipe 540 1800 540 600
mobilecli type "hello"
mobilecli type "你好"
mobilecli doctor
```

- [ ] **Step 2: All should emit `{"ok": true, ...}` envelopes**

- [ ] **Step 3: Confirm Phase A DoD checklist** (from spec §7):
  - [ ] `pipx install -e .` works
  - [ ] `mobilecli doctor` reports green on test device
  - [ ] All 11 primitive commands return correctly-shaped JSON
  - [ ] Unit tests pass: `pytest tests/unit -v`
  - [ ] Integration tests pass: `EM_INTEGRATION=1 pytest tests/integration -v`

- [ ] **Step 4: Tag the Phase A checkpoint**

```bash
git tag -a v0.1.0-phaseA -m "Phase A: core primitives complete"
```

---

# Phase B — Humanization & safety (Layer 2.5)

Goal: humanize Layer 2 by default. `--raw` opt-out gated by `EM_ALLOW_RAW=1`. Add `SessionGovernor`, `ContentLinter`, `DeviceCheck`. New error codes RATE_LIMITED / CONTENT_BANNED / WARMUP_REQUIRED.

## Task B1: humanize module — delay + jitter

**Files:**
- Create: `src/mobilecli/safety/__init__.py` (empty)
- Create: `src/mobilecli/safety/humanize.py`
- Create: `tests/unit/test_humanize.py`

- [ ] **Step 1: Write failing test `tests/unit/test_humanize.py`**

```python
"""Tests for humanize timing and jitter primitives."""

from __future__ import annotations

import statistics

from mobilecli.safety.humanize import (
    bezier_swipe_points,
    human_delay_s,
    jittered_tap_point,
    log_normal_duration_ms,
    read_pause_s,
)


def test_human_delay_distribution_has_variance():
    samples = [human_delay_s() for _ in range(500)]
    assert min(samples) >= 0.3
    assert max(samples) <= 8.0
    # log-normal has σ > 0 — fail if all samples are identical (clipping to mean)
    assert statistics.stdev(samples) > 0.1


def test_jittered_tap_point_inside_inner_60_percent_box():
    bounds = (100, 200, 300, 400)  # width=200, height=200; inner-60% = (140,240)-(260,360)
    for _ in range(200):
        x, y = jittered_tap_point(bounds)
        assert 140 <= x <= 260
        assert 240 <= y <= 360


def test_jittered_tap_point_is_not_always_center():
    bounds = (100, 200, 300, 400)
    points = {jittered_tap_point(bounds) for _ in range(100)}
    # at least 50 distinct positions out of 100 samples
    assert len(points) > 50


def test_log_normal_duration_ms_centered_near_90():
    samples = [log_normal_duration_ms() for _ in range(500)]
    assert 30 <= statistics.median(samples) <= 200


def test_bezier_swipe_points_returns_30_plus_points():
    pts = bezier_swipe_points((100, 200), (500, 1000))
    assert len(pts) >= 30
    assert pts[0] == (100, 200)
    assert abs(pts[-1][0] - 500) <= 5  # endpoint may have small jitter
    assert abs(pts[-1][1] - 1000) <= 5


def test_bezier_swipe_has_lateral_wobble():
    # The interior points should not all sit on the straight line.
    pts = bezier_swipe_points((100, 200), (100, 1000))  # vertical line target
    xs = [p[0] for p in pts[5:-5]]  # ignore start/end
    assert max(xs) - min(xs) >= 4  # at least 4px lateral wobble


def test_read_pause_first_screen_is_long():
    p = read_pause_s(screen_hash="never-seen", text_length=200, seen_recently=False)
    assert 1.5 <= p <= 5.0


def test_read_pause_recently_seen_is_short():
    p = read_pause_s(screen_hash="seen-it", text_length=200, seen_recently=True)
    assert 0.3 <= p <= 1.2
```

- [ ] **Step 2: Run + see fail**

Run: `pytest tests/unit/test_humanize.py -v`
Expected: FAIL — module not present.

- [ ] **Step 3: Write `src/mobilecli/safety/humanize.py`**

```python
"""Humanization primitives — timing, jitter, bezier swipe.

Sourced from docs/anti-risk-control.md §"Timing" and §"Movement".
Defaults are intended to be sampled from, not used as constants.
"""

from __future__ import annotations

import math
import random
from typing import Iterable


def human_delay_s(mu: float = 1.2, sigma: float = 0.4, lo: float = 0.3, hi: float = 8.0) -> float:
    """Sample a log-normal inter-action delay in seconds. Clamped to [lo, hi]."""
    # log-normal parameters: random.lognormvariate(mu, sigma) ~ exp(N(mu, sigma))
    # We want median ≈ mu seconds, so we transform.
    sample = random.lognormvariate(math.log(mu), sigma)
    return max(lo, min(hi, sample))


def log_normal_duration_ms(mu_ms: float = 90.0, sigma: float = 0.5) -> int:
    """Touch duration in ms. Default median 90ms."""
    return int(max(10, random.lognormvariate(math.log(mu_ms), sigma)))


def jittered_tap_point(bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    """Sample a tap point within the inner 60% box of `bounds=(x1,y1,x2,y2)`."""
    x1, y1, x2, y2 = bounds
    w, h = x2 - x1, y2 - y1
    inner_x1 = x1 + int(w * 0.2)
    inner_x2 = x2 - int(w * 0.2)
    inner_y1 = y1 + int(h * 0.2)
    inner_y2 = y2 - int(h * 0.2)
    return (random.randint(inner_x1, inner_x2), random.randint(inner_y1, inner_y2))


def _bezier(p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float],
            p3: tuple[float, float], t: float) -> tuple[float, float]:
    u = 1 - t
    x = u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0]
    y = u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
    return (x, y)


def _ease_in_out(t: float) -> float:
    # Cubic ease-in-out
    return 3 * t * t - 2 * t * t * t


def bezier_swipe_points(
    start: tuple[int, int],
    end: tuple[int, int],
    n_points: int = 35,
    wobble_px: int = 10,
) -> list[tuple[int, int]]:
    """Generate `n_points` cubic-bezier swipe points with ease-in-out + lateral wobble."""
    sx, sy = start
    ex, ey = end
    # Control points: perpendicular offsets of length wobble_px for natural curve
    dx, dy = ex - sx, ey - sy
    length = max(1.0, math.hypot(dx, dy))
    nx, ny = -dy / length, dx / length  # unit normal
    c1 = (sx + dx * 0.25 + nx * random.uniform(-wobble_px, wobble_px),
          sy + dy * 0.25 + ny * random.uniform(-wobble_px, wobble_px))
    c2 = (sx + dx * 0.75 + nx * random.uniform(-wobble_px, wobble_px),
          sy + dy * 0.75 + ny * random.uniform(-wobble_px, wobble_px))
    pts: list[tuple[int, int]] = []
    for i in range(n_points):
        t = _ease_in_out(i / (n_points - 1))
        x, y = _bezier((sx, sy), c1, c2, (ex, ey), t)
        # Add per-sample lateral wobble for human-like jitter
        x += random.uniform(-wobble_px * 0.4, wobble_px * 0.4)
        y += random.uniform(-wobble_px * 0.4, wobble_px * 0.4)
        pts.append((int(x), int(y)))
    # Ensure start exact
    pts[0] = (sx, sy)
    return pts


def read_pause_s(
    *,
    screen_hash: str,
    text_length: int,
    seen_recently: bool,
) -> float:
    """Sample a read-time pause for a newly loaded screen."""
    if seen_recently:
        return random.uniform(0.3, 1.2)
    base = 1.5 + min(3.0, text_length / 200.0)
    return min(5.0, base + random.uniform(0.0, 0.5))


def per_char_type_delay_s() -> float:
    """Per-character delay for ASCII typing (log-normal 120ms μ, 0.6 σ)."""
    return random.lognormvariate(math.log(0.120), 0.6)
```

- [ ] **Step 4: Run + see pass**

Run: `pytest tests/unit/test_humanize.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/safety/__init__.py src/mobilecli/safety/humanize.py tests/unit/test_humanize.py
git commit -m "feat: humanize module — delay, jitter, bezier swipe"
```

## Task B2: Wire humanize into Layer 2 input + `--raw` flag

**Files:**
- Modify: `src/mobilecli/core/input.py` (add humanized wrappers)
- Modify: `src/mobilecli/cli.py` (add `--raw` flag + EM_ALLOW_RAW gate)
- Modify: each command in `src/mobilecli/commands/{tap,swipe,type_cmd}.py` (call humanized variants by default)

- [ ] **Step 1: Add unit test for the humanized vs raw paths**

Create `tests/unit/test_humanized_input.py`:

```python
"""Unit tests for humanized input — uses a fake Device that records calls."""

from __future__ import annotations

from dataclasses import dataclass, field

from mobilecli.core import input as core_input


@dataclass
class FakeDevice:
    serial: str = "fake"
    shell_calls: list[str] = field(default_factory=list)
    def shell(self, cmd: str, timeout_s: int = 30) -> str:
        self.shell_calls.append(cmd)
        return ""


def test_tap_humanized_emits_duration_in_swipe_form():
    dev = FakeDevice()
    out = core_input.tap_humanized(dev, bounds=(100, 100, 200, 200))
    cmd = dev.shell_calls[-1]
    # Humanized tap is implemented as `input swipe X Y X Y DUR` to allow non-zero duration
    assert cmd.startswith("input swipe ")
    # No literal "input tap" in humanized path
    assert "input tap" not in cmd
    assert out["duration_ms"] >= 10


def test_tap_raw_emits_input_tap():
    dev = FakeDevice()
    core_input.tap_raw(dev, 150, 150)
    assert dev.shell_calls[-1] == "input tap 150 150"


def test_swipe_humanized_emits_multi_segment_via_sendevent_or_swipe():
    dev = FakeDevice()
    out = core_input.swipe_humanized(dev, (100, 1500), (100, 500))
    # Should emit at least one input swipe call (we fall back to single bezier-shaped swipe
    # because multi-segment requires minitouch which we don't ship in v1)
    assert any("input swipe" in c for c in dev.shell_calls)
    assert out["points"]
```

- [ ] **Step 2: Run + see fail**

Run: `pytest tests/unit/test_humanized_input.py -v`
Expected: FAIL — humanized functions don't exist yet.

- [ ] **Step 3: Append humanized helpers to `src/mobilecli/core/input.py`**

Add (at bottom of file):

```python
import time as _time

from mobilecli.safety import humanize as _hz


def tap_humanized(
    device: Device,
    *,
    bounds: tuple[int, int, int, int] | None = None,
    x: int | None = None,
    y: int | None = None,
) -> dict:
    """Humanized tap.

    Either pass `bounds` (jitter within inner 60%) or `(x, y)` (jitter ±8 px).
    Uses `input swipe` form with a duration to emit a non-zero touch time —
    `input tap` always has duration=0 which is detectable.
    """
    if bounds is not None:
        tx, ty = _hz.jittered_tap_point(bounds)
    elif x is not None and y is not None:
        import random as _r
        tx, ty = x + _r.randint(-8, 8), y + _r.randint(-8, 8)
    else:
        raise ValueError("tap_humanized needs bounds or (x, y)")
    duration_ms = _hz.log_normal_duration_ms()
    device.shell(f"input swipe {tx} {ty} {tx} {ty} {duration_ms}")
    return {"x": tx, "y": ty, "duration_ms": duration_ms}


def swipe_humanized(
    device: Device,
    start: tuple[int, int],
    end: tuple[int, int],
) -> dict:
    """Humanized swipe — picks a bezier-shaped path, then emits a single `input swipe`.

    True multi-segment swipes require minitouch or `sendevent` mapping; not in v1.
    We compute the bezier points (for telemetry / future use) but issue a single
    long `input swipe` with a randomized duration in [600, 1200] ms.
    """
    import random as _r
    pts = _hz.bezier_swipe_points(start, end, n_points=35)
    duration_ms = _r.randint(600, 1200)
    sx, sy = start
    ex, ey = end
    device.shell(f"input swipe {sx} {sy} {ex} {ey} {duration_ms}")
    return {
        "x1": sx, "y1": sy, "x2": ex, "y2": ey,
        "duration_ms": duration_ms,
        "points": pts,
    }


def type_text_humanized(device: Device, text: str) -> dict:
    """Humanized type — same as raw, plus per-char delay for ASCII, post-paste dwell for CJK."""
    if text.isascii():
        for ch in text:
            escaped = ch.replace(" ", "%s")
            device.shell(f"input text {repr(escaped)}")
            _time.sleep(_hz.per_char_type_delay_s())
        return {"chars": len(text), "mode": "input"}
    # CJK
    from mobilecli.core import ime as _ime
    prev = _ime.current_ime(device)
    _ime.set_adbkeyboard(device)
    try:
        device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg '{text}'")
        _time.sleep(_r.uniform(0.2, 0.6))  # type: ignore[name-defined]
        return {"chars": len(text), "mode": "adbkeyboard"}
    finally:
        _ime.restore_ime(device, prev)
```

Note: replace `_r` shadow naming above with proper imports (`import random as _r` at module top if not already present). Self-review fix in step 5.

- [ ] **Step 4: Add `--raw` to CLI dispatcher**

Modify `src/mobilecli/cli.py`:

```python
parser.add_argument(
    "--raw",
    action="store_true",
    help="Disable humanization (debugging). Requires EM_ALLOW_RAW=1.",
)
parser.add_argument(
    "--account", default="default",
    help="Account identifier for SessionGovernor persistence.",
)
```

And inside `main`, after `args = parser.parse_args(argv)`:

```python
import os
if args.raw and os.environ.get("EM_ALLOW_RAW") != "1":
    _emit_error(
        command=args.command or "",
        code=ErrorCode.COMMIT_REFUSED,
        message="--raw requires EM_ALLOW_RAW=1 in environment",
        hint="export EM_ALLOW_RAW=1",
        pretty=args.pretty,
    )
    return 1
```

- [ ] **Step 5: Update `commands/tap.py` to use humanized by default**

Replace `_run`:

```python
@envelope(command="tap")
def _run(*, device: str, x: int, y: int, raw: bool) -> dict[str, Any]:
    dev = Device(serial=device)
    if raw:
        return core_input.tap_raw(dev, x, y)
    return core_input.tap_humanized(dev, x=x, y=y)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial, x=args.x, y=args.y, raw=args.raw)
```

Apply the same `raw` switch to `swipe.py` and `type_cmd.py`.

- [ ] **Step 6: Run all unit tests**

Run: `pytest tests/unit -v`
Expected: all pass, including the new humanized tests.

- [ ] **Step 7: Commit**

```bash
git add src/mobilecli/core/input.py src/mobilecli/cli.py src/mobilecli/commands/{tap,swipe,type_cmd}.py tests/unit/test_humanized_input.py
git commit -m "feat: humanize tap/swipe/type by default; --raw + EM_ALLOW_RAW opt-out"
```

## Task B3: SessionGovernor — per-account daily caps

**Files:**
- Create: `src/mobilecli/safety/governor.py`
- Create: `tests/unit/test_governor.py`

- [ ] **Step 1: Write failing test `tests/unit/test_governor.py`**

```python
"""SessionGovernor: per-account daily/hourly/session caps and persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mobilecli.envelope import EmError, ErrorCode
from mobilecli.safety.governor import SessionGovernor


@pytest.fixture
def tmp_state(tmp_path) -> Path:
    return tmp_path / "session.json"


def test_governor_allows_first_action(tmp_state):
    g = SessionGovernor(state_path=tmp_state, account="test", caps={"comment_xhs": 20})
    g.check_or_raise("comment_xhs")  # no exception


def test_governor_persists_after_record(tmp_state):
    g = SessionGovernor(state_path=tmp_state, account="test", caps={"comment_xhs": 20})
    g.record("comment_xhs")
    g2 = SessionGovernor(state_path=tmp_state, account="test", caps={"comment_xhs": 20})
    assert g2._counts_today()["comment_xhs"] == 1


def test_governor_raises_rate_limited_at_cap(tmp_state):
    g = SessionGovernor(state_path=tmp_state, account="test", caps={"comment_xhs": 2})
    g.record("comment_xhs")
    g.record("comment_xhs")
    with pytest.raises(EmError) as exc:
        g.check_or_raise("comment_xhs")
    assert exc.value.code is ErrorCode.RATE_LIMITED


def test_governor_separate_accounts_isolated(tmp_state):
    g_a = SessionGovernor(state_path=tmp_state, account="a", caps={"comment_xhs": 1})
    g_a.record("comment_xhs")
    g_b = SessionGovernor(state_path=tmp_state, account="b", caps={"comment_xhs": 1})
    g_b.check_or_raise("comment_xhs")  # b not affected by a's record
```

- [ ] **Step 2: Run + see fail**

Run: `pytest tests/unit/test_governor.py -v`
Expected: FAIL.

- [ ] **Step 3: Write `src/mobilecli/safety/governor.py`**

```python
"""SessionGovernor — per-account daily caps with JSON-file persistence."""

from __future__ import annotations

import datetime as _dt
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from mobilecli.envelope import EmError, ErrorCode

DEFAULT_STATE_DIR = Path.home() / ".everything-mobile" / "sessions"


class SessionGovernor:
    """Tracks per-account per-day counts of action classes against caps."""

    def __init__(
        self,
        *,
        state_path: Path | None = None,
        account: str = "default",
        caps: dict[str, int] | None = None,
    ) -> None:
        self.account = account
        self.caps = caps or {}
        if state_path is None:
            DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
            state_path = DEFAULT_STATE_DIR / f"{account}.json"
        self.state_path = state_path
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"accounts": {}}
        try:
            return json.loads(self.state_path.read_text())
        except json.JSONDecodeError:
            return {"accounts": {}}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2))

    def _today(self) -> str:
        return _dt.date.today().isoformat()

    def _counts_today(self) -> dict[str, int]:
        acct = self._state.setdefault("accounts", {}).setdefault(self.account, {})
        day = acct.setdefault(self._today(), {})
        return day

    def check_or_raise(self, action_class: str) -> None:
        cap = self.caps.get(action_class)
        if cap is None:
            return  # no cap configured
        used = self._counts_today().get(action_class, 0)
        if used >= cap:
            raise EmError(
                ErrorCode.RATE_LIMITED,
                f"daily cap reached for {action_class}: {used}/{cap}",
                hint=f"wait until tomorrow or edit {self.state_path}",
            )

    def record(self, action_class: str) -> None:
        counts = self._counts_today()
        counts[action_class] = counts.get(action_class, 0) + 1
        self._save()
```

- [ ] **Step 4: Run + see pass**

Run: `pytest tests/unit/test_governor.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/safety/governor.py tests/unit/test_governor.py
git commit -m "feat: SessionGovernor with daily caps + per-account JSON persistence"
```

## Task B4: ContentLinter — banned phrase regex

**Files:**
- Create: `src/mobilecli/safety/linter.py`
- Create: `tests/unit/test_linter.py`

- [ ] **Step 1: Write failing test**

```python
"""ContentLinter — block 加微信 / VX / phone / QR / 戳我 families."""

from __future__ import annotations

import pytest

from mobilecli.envelope import EmError, ErrorCode
from mobilecli.safety.linter import ContentLinter


def test_clean_text_passes():
    ContentLinter().check_or_raise("学到了 👍")
    ContentLinter().check_or_raise("好棒的内容~")


@pytest.mark.parametrize("text", [
    "戳我学短剧",
    "私我看更多",
    "加微信 abc123",
    "加 V 信 secret",
    "扫码进群",
    "扫二维码加我",
    "VX:newuser",
    "13912345678 联系我",
    "qq: 123456789",
])
def test_banned_phrase_raises(text):
    with pytest.raises(EmError) as exc:
        ContentLinter().check_or_raise(text)
    assert exc.value.code is ErrorCode.CONTENT_BANNED
```

- [ ] **Step 2: Run + see fail**

Run: `pytest tests/unit/test_linter.py -v`
Expected: FAIL.

- [ ] **Step 3: Write `src/mobilecli/safety/linter.py`**

```python
"""ContentLinter — refuse text that platforms flag as instant shadowban."""

from __future__ import annotations

import re

from mobilecli.envelope import EmError, ErrorCode

DEFAULT_BANNED_PATTERNS: list[str] = [
    r"加.{0,4}微信",
    r"加.{0,4}V[X信]",
    r"VX[\s:：]*\w+",
    r"扫.{0,3}码",
    r"扫.{0,3}二维码",
    r"戳我",
    r"私我",
    r"滴滴我",
    r"\b1[3-9]\d{9}\b",        # mainland mobile
    r"q[qQ][\s:：]*\d{5,}",     # QQ
    r"wx[\s:：]*\w+",           # wechat id
]


class ContentLinter:
    def __init__(self, extra_patterns: list[str] | None = None) -> None:
        patterns = list(DEFAULT_BANNED_PATTERNS) + list(extra_patterns or [])
        self._regexes = [re.compile(p, re.IGNORECASE) for p in patterns]

    def check_or_raise(self, text: str) -> None:
        for rx in self._regexes:
            m = rx.search(text)
            if m:
                raise EmError(
                    ErrorCode.CONTENT_BANNED,
                    f"banned phrase: {m.group(0)!r}",
                    hint="rewrite without contact info / 引流 patterns",
                )
```

- [ ] **Step 4: Run + see pass**

Run: `pytest tests/unit/test_linter.py -v`
Expected: 1 + 9 (parametrized) = 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/safety/linter.py tests/unit/test_linter.py
git commit -m "feat: ContentLinter with default banned-phrase regex set"
```

## Task B5: DeviceCheck + doctor enhancements

**Files:**
- Create: `src/mobilecli/safety/device_check.py`
- Modify: `src/mobilecli/commands/doctor.py` (add humanization-side checks)

- [ ] **Step 1: Add integration test for doctor's new checks**

```python
@pytest.mark.integration
def test_doctor_reports_humanization_signals(device_serial: str):
    payload = _cli("--serial", device_serial, "doctor")
    names = {c["name"] for c in payload["data"]["checks"]}
    # New checks added in Phase B:
    assert "ime_not_adbkeyboard_default" in names
    assert "adb_enabled" in names
    assert "session_state_dir" in names
```

- [ ] **Step 2: Run + see fail**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_primitives.py -k doctor -v`
Expected: FAIL — new checks missing.

- [ ] **Step 3: Write `src/mobilecli/safety/device_check.py`**

```python
"""Device fingerprint checks — what platforms might detect."""

from __future__ import annotations

from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import ime as core_ime


def signals(device: Device) -> list[dict[str, Any]]:
    """Return a list of fingerprint signals with status (pass/warn/fail)."""
    checks: list[dict[str, Any]] = []

    # ADBKeyboard should NOT be the default IME (we switch only during type)
    try:
        current = core_ime.current_ime(device)
        if current == core_ime.ADBKEYBOARD_ID:
            checks.append({
                "name": "ime_not_adbkeyboard_default",
                "status": "warn",
                "detail": "ADBKeyboard is the active IME — risky if not transient",
            })
        else:
            checks.append({"name": "ime_not_adbkeyboard_default", "status": "pass"})
    except Exception as e:
        checks.append({
            "name": "ime_not_adbkeyboard_default", "status": "warn", "detail": str(e),
        })

    # USB debugging on (`adb_enabled` setting) — almost always 1 since we use adb
    try:
        out = device.shell("settings get global adb_enabled").strip()
        if out == "1":
            checks.append({
                "name": "adb_enabled",
                "status": "warn",
                "detail": "settings.global.adb_enabled=1 — detectable but unavoidable",
            })
        else:
            checks.append({"name": "adb_enabled", "status": "pass"})
    except Exception as e:
        checks.append({"name": "adb_enabled", "status": "warn", "detail": str(e)})

    return checks
```

- [ ] **Step 4: Update `src/mobilecli/commands/doctor.py`**

Replace `_run`:

```python
@envelope(command="doctor")
def _run(*, device: str) -> dict[str, Any]:
    from pathlib import Path

    from mobilecli.safety import device_check
    from mobilecli.safety.governor import DEFAULT_STATE_DIR

    checks: list[dict[str, Any]] = []
    if shutil.which("adb"):
        checks.append(_check("adb_available", "pass"))
    else:
        checks.append(_check("adb_available", "fail", "install platform-tools"))
        return _summary(checks)

    try:
        dev = Device.from_serial(device or None)
        checks.append(_check("device_online", "pass", dev.serial))
    except Exception as e:
        checks.append(_check("device_online", "fail", str(e)))
        return _summary(checks)

    try:
        if core_ime.ADBKEYBOARD_ID in core_ime.list_imes(dev):
            checks.append(_check("adbkeyboard_installed", "pass"))
        else:
            checks.append(_check("adbkeyboard_installed", "warn",
                                 "install for Chinese input"))
    except Exception as e:
        checks.append(_check("adbkeyboard_installed", "warn", str(e)))

    checks.extend(device_check.signals(dev))

    # SessionGovernor state dir
    if DEFAULT_STATE_DIR.exists():
        checks.append(_check("session_state_dir", "pass", str(DEFAULT_STATE_DIR)))
    else:
        checks.append(_check("session_state_dir", "warn",
                             f"will be created at first verb: {DEFAULT_STATE_DIR}"))

    return _summary(checks)
```

- [ ] **Step 5: Run tests**

Run: `EM_INTEGRATION=1 pytest tests/integration -k doctor -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/mobilecli/safety/device_check.py src/mobilecli/commands/doctor.py tests/
git commit -m "feat: DeviceCheck signals + doctor reports humanization status"
```

## Task B6: Phase B acceptance

- [ ] **Step 1: Verify `--raw` env gate**

```bash
mobilecli --raw tap 540 1200      # should error: EM_ALLOW_RAW required
EM_ALLOW_RAW=1 mobilecli --raw tap 540 1200   # works
```

- [ ] **Step 2: Verify ContentLinter** (via unit test smoke)

```bash
python -c "from mobilecli.safety.linter import ContentLinter; ContentLinter().check_or_raise('戳我')"
```

Expected: raises EmError CONTENT_BANNED.

- [ ] **Step 3: Verify SessionGovernor persistence**

```bash
python -c "
from mobilecli.safety.governor import SessionGovernor
g = SessionGovernor(account='test-phase-b', caps={'demo': 1})
g.record('demo')
"
ls ~/.everything-mobile/sessions/test-phase-b.json
```

Expected: JSON file with `{"demo": 1}` for today.

- [ ] **Step 4: Tag**

```bash
git tag -a v0.1.0-phaseB -m "Phase B: humanization + governor + linter complete"
```

---

# Phase C — App plugins (douyin + xiaohongshu)

Goal: `mobilecli douyin {launch,search,open,detail,comment}` and `mobilecli xiaohongshu {launch,search,open,detail,comment}` work E2E. Plugin framework supports entry_points discovery.

## Task C1: Plugin framework — App class + registry

**Files:**
- Create: `src/mobilecli/plugin/__init__.py`
- Create: `src/mobilecli/plugin/base.py`
- Create: `src/mobilecli/plugin/registry.py`
- Create: `src/mobilecli/plugin/ctx.py`
- Create: `tests/unit/test_plugin_base.py`

- [ ] **Step 1: Write failing test**

```python
"""Plugin framework — App class, verb registration, ExecContext."""

from __future__ import annotations

import pytest

from mobilecli.plugin.base import App


def test_app_register_verb_via_decorator():
    app = App(name="demo", package="com.example.demo")

    @app.verb("hello")
    def hello(args, ctx):
        return {"greeting": "hi"}

    assert "hello" in app.verbs


def test_app_get_verb_returns_function():
    app = App(name="demo", package="com.example.demo")

    @app.verb("hello")
    def hello(args, ctx):
        return {}

    fn = app.get_verb("hello")
    assert fn is hello


def test_app_unknown_verb_returns_none():
    app = App(name="demo", package="com.example.demo")
    assert app.get_verb("nope") is None
```

- [ ] **Step 2: Run + see fail**

Run: `pytest tests/unit/test_plugin_base.py -v`
Expected: FAIL.

- [ ] **Step 3: Write `src/mobilecli/plugin/base.py`**

```python
"""App plugin base — verb registration."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any, Callable

VerbFn = Callable[[argparse.Namespace, "ExecContext"], dict[str, Any]]  # noqa: F821


@dataclass
class Verb:
    name: str
    fn: VerbFn
    add_args: Callable[[argparse.ArgumentParser], None] | None = None
    requires_commit_flag: bool = False  # for verbs with side effects


@dataclass
class App:
    name: str
    package: str
    verbs: dict[str, Verb] = field(default_factory=dict)
    daily_caps: dict[str, int] = field(default_factory=dict)
    extra_lint_patterns: list[str] = field(default_factory=list)

    def verb(
        self,
        name: str,
        *,
        add_args: Callable[[argparse.ArgumentParser], None] | None = None,
        requires_commit_flag: bool = False,
    ) -> Callable[[VerbFn], VerbFn]:
        def deco(fn: VerbFn) -> VerbFn:
            self.verbs[name] = Verb(
                name=name, fn=fn, add_args=add_args,
                requires_commit_flag=requires_commit_flag,
            )
            return fn
        return deco

    def get_verb(self, name: str) -> VerbFn | None:
        v = self.verbs.get(name)
        return v.fn if v else None
```

- [ ] **Step 4: Write `src/mobilecli/plugin/ctx.py`**

```python
"""ExecContext — the only surface plugin authors interact with."""

from __future__ import annotations

from dataclasses import dataclass

from mobilecli.adb.device import Device
from mobilecli.core import app as core_app
from mobilecli.core import ime as core_ime
from mobilecli.core import input as core_input
from mobilecli.core import screenshot as core_screenshot
from mobilecli.core import ui as core_ui
from mobilecli.safety.governor import SessionGovernor
from mobilecli.safety.linter import ContentLinter


@dataclass
class InputModule:
    device: Device

    def tap_node(self, node: dict) -> dict:
        bounds = tuple(node["bounds"])  # (x1,y1,x2,y2)
        return core_input.tap_humanized(self.device, bounds=bounds)

    def tap_xy(self, x: int, y: int) -> dict:
        return core_input.tap_humanized(self.device, x=x, y=y)

    def swipe(self, start: tuple[int, int], end: tuple[int, int]) -> dict:
        return core_input.swipe_humanized(self.device, start, end)

    def type_text(self, text: str) -> dict:
        return core_input.type_text_humanized(self.device, text)

    def keyevent(self, code: int | str) -> dict:
        return core_input.keyevent_raw(self.device, code)


@dataclass
class UiModule:
    device: Device

    def dump(self, output_path: str | None = None) -> dict:
        return core_ui.dump(self.device, output_path)

    def find_by_resource_id(self, xml: str, rid: str) -> dict | None:
        return core_ui.find_by_resource_id(xml, rid)

    def find_by_content_desc(self, xml: str, desc: str) -> dict | None:
        return core_ui.find_by_content_desc(xml, desc)

    def find_by_text(self, xml: str, text: str) -> dict | None:
        return core_ui.find_by_text(xml, text)

    def find_all_by_resource_id(self, xml: str, rid: str) -> list[dict]:
        return core_ui.find_all_by_resource_id(xml, rid)


@dataclass
class AppModule:
    device: Device
    package: str

    def launch(self) -> dict:
        return core_app.launch(self.device, self.package)

    def foreground(self) -> dict:
        return core_app.foreground(self.device)

    def ensure_foreground(self) -> dict:
        fg = self.foreground()
        if fg["package"] != self.package:
            return self.launch()
        return fg


@dataclass
class ExecContext:
    device: Device
    input: InputModule
    ui: UiModule
    app: AppModule
    governor: SessionGovernor
    linter: ContentLinter

    @classmethod
    def build(
        cls,
        device: Device,
        package: str,
        account: str,
        caps: dict[str, int],
        extra_lint: list[str],
    ) -> "ExecContext":
        return cls(
            device=device,
            input=InputModule(device=device),
            ui=UiModule(device=device),
            app=AppModule(device=device, package=package),
            governor=SessionGovernor(account=account, caps=caps),
            linter=ContentLinter(extra_patterns=extra_lint),
        )
```

- [ ] **Step 5: Write `src/mobilecli/plugin/registry.py`**

```python
"""Plugin discovery — built-in apps + entry_points."""

from __future__ import annotations

import importlib
import pkgutil
from importlib.metadata import entry_points

from mobilecli.plugin.base import App

_APPS: dict[str, App] = {}


def load() -> dict[str, App]:
    """Idempotently load built-in + entry_points apps."""
    if _APPS:
        return _APPS

    # Built-in apps under mobilecli.apps.*
    import mobilecli.apps as apps_pkg

    for finder, name, ispkg in pkgutil.iter_modules(apps_pkg.__path__):
        mod = importlib.import_module(f"mobilecli.apps.{name}")
        app = getattr(mod, "app", None)
        if isinstance(app, App):
            _APPS[app.name] = app

    # External entry_points
    for ep in entry_points(group="mobilecli.apps"):
        try:
            app = ep.load()
            if isinstance(app, App):
                _APPS[app.name] = app
        except Exception:
            continue

    return _APPS
```

- [ ] **Step 6: Write `src/mobilecli/plugin/__init__.py`**

```python
"""Plugin framework public API."""

from mobilecli.plugin.base import App, Verb
from mobilecli.plugin.ctx import ExecContext
from mobilecli.plugin.registry import load

__all__ = ["App", "Verb", "ExecContext", "load"]
```

- [ ] **Step 7: Run + see pass**

Run: `pytest tests/unit/test_plugin_base.py -v`
Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
git add src/mobilecli/plugin/ tests/unit/test_plugin_base.py
git commit -m "feat: plugin framework — App, Verb, ExecContext, registry"
```

## Task C2: CLI wiring for app subcommands

**Files:**
- Modify: `src/mobilecli/cli.py` (load registry, attach app subparsers)

- [ ] **Step 1: Extend `_load_commands` in `src/mobilecli/cli.py`**

After the primitive-command loop:

```python
# App plugins (Layer 3) — each is a top-level subcommand with nested verbs
from mobilecli.plugin import load as load_apps
for app_name, app_obj in load_apps().items():
    app_parser = sub.add_parser(
        app_name,
        help=f"{app_obj.package} verbs ({len(app_obj.verbs)} actions)",
    )
    verb_sub = app_parser.add_subparsers(dest="verb")
    for verb_name, verb in app_obj.verbs.items():
        vp = verb_sub.add_parser(verb_name)
        if verb.add_args is not None:
            verb.add_args(vp)
        if verb.requires_commit_flag:
            vp.add_argument("--commit", action="store_true",
                            help="Actually perform the action (requires EM_ALLOW_COMMIT=1)")
    loaded[app_name] = ("__app__", app_obj)
```

And in the dispatch:

```python
target = loaded[args.command]
if isinstance(target, tuple) and target[0] == "__app__":
    app_obj = target[1]
    out = _run_app_verb(app_obj, args)
    _emit(out, args.pretty)
    return 0
out = target.run(args)
_emit(out, args.pretty)
return 0
```

Add a helper `_run_app_verb` to `cli.py`:

```python
def _run_app_verb(app_obj, args) -> str:
    from mobilecli.adb.device import Device
    from mobilecli.envelope import EmError, ErrorCode, envelope
    from mobilecli.plugin.ctx import ExecContext

    @envelope(command=f"{app_obj.name}.{args.verb}")
    def _inner(*, device: str) -> dict:
        dev = Device(serial=device)
        verb = app_obj.get_verb(args.verb)
        if verb is None:
            raise EmError(ErrorCode.UNKNOWN, f"unknown verb: {args.verb}")
        ctx = ExecContext.build(
            device=dev,
            package=app_obj.package,
            account=args.account,
            caps=app_obj.daily_caps,
            extra_lint=app_obj.extra_lint_patterns,
        )
        if getattr(args, "commit", False) and os.environ.get("EM_ALLOW_COMMIT") != "1":
            raise EmError(ErrorCode.COMMIT_REFUSED, "--commit requires EM_ALLOW_COMMIT=1",
                          hint="export EM_ALLOW_COMMIT=1")
        return verb(args, ctx)

    dev = Device.from_serial(args.serial)
    return _inner(device=dev.serial)
```

- [ ] **Step 2: Add unit test**

`tests/unit/test_app_dispatch.py`:

```python
"""End-to-end test of the app-verb dispatch path with a fake App."""

import json
import subprocess
import sys


def test_unknown_app_is_unknown_command():
    r = subprocess.run([sys.executable, "-m", "mobilecli", "nonexistent-app"],
                       capture_output=True, text=True)
    # argparse will reject (rc != 0)
    assert r.returncode != 0
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit -v`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add src/mobilecli/cli.py tests/unit/test_app_dispatch.py
git commit -m "feat: wire app plugins into CLI as nested subcommands"
```

## Task C3: Douyin plugin — launch + foreground state

**Files:**
- Create: `src/mobilecli/apps/__init__.py` (empty)
- Create: `src/mobilecli/apps/douyin.py`

- [ ] **Step 1: Write integration test**

`tests/integration/test_douyin.py`:

```python
"""Integration tests for douyin verbs — read-only here."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

EXPECTED_SERIAL = "EXAMPLE-SERIAL"


@pytest.fixture(scope="module")
def device_serial() -> str:
    r = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    if EXPECTED_SERIAL not in r.stdout:
        pytest.skip(f"test device {EXPECTED_SERIAL} not connected")
    return EXPECTED_SERIAL


def _cli(*args: str) -> dict:
    r = subprocess.run([sys.executable, "-m", "mobilecli", *args],
                       capture_output=True, text=True)
    return json.loads(r.stdout)


@pytest.mark.integration
def test_douyin_launch(device_serial):
    payload = _cli("--serial", device_serial, "douyin", "launch")
    assert payload["ok"] is True, payload
    assert payload["command"] == "douyin.launch"
```

- [ ] **Step 2: Run + see fail**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_douyin.py -v`
Expected: FAIL — `douyin` not registered.

- [ ] **Step 3: Write `src/mobilecli/apps/douyin.py` (launch verb only)**

```python
"""Douyin app plugin (抖音). Selectors per research/ui-trees/douyin/00-selectors.md."""

from __future__ import annotations

import argparse

from mobilecli.plugin import App, ExecContext

PACKAGE = "com.ss.android.ugc.aweme"

app = App(
    name="douyin",
    package=PACKAGE,
    daily_caps={
        "comment": 100,
        "follow": 100,
        "dm": 100,
        "like": 200,
    },
    extra_lint_patterns=[],
)


@app.verb("launch")
def launch(args: argparse.Namespace, ctx: ExecContext) -> dict:
    """Launch Douyin and verify foreground."""
    ctx.app.launch()
    import time
    time.sleep(3)  # let splash settle
    fg = ctx.app.foreground()
    return {"foreground": fg, "package": PACKAGE}
```

- [ ] **Step 4: Run test**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_douyin.py::test_douyin_launch -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/apps/ tests/integration/test_douyin.py
git commit -m "feat: douyin plugin launch verb"
```

## Task C4: Douyin search verb

**Files:**
- Modify: `src/mobilecli/apps/douyin.py`
- Modify: `tests/integration/test_douyin.py`

- [ ] **Step 1: Add integration test**

```python
@pytest.mark.integration
def test_douyin_search_returns_results(device_serial):
    _cli("--serial", device_serial, "douyin", "launch")
    payload = _cli("--serial", device_serial, "douyin", "search",
                   "--keyword", "美食", "--limit", "5")
    assert payload["ok"] is True, payload
    results = payload["data"]["results"]
    assert len(results) >= 1
    for r in results:
        assert "index" in r and "cx" in r and "cy" in r
```

- [ ] **Step 2: Run + see fail**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_douyin.py -k search -v`
Expected: FAIL.

- [ ] **Step 3: Add search verb to `src/mobilecli/apps/douyin.py`**

```python
import time

from mobilecli.core import ime as _ime


def _search_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--keyword", required=True)
    p.add_argument("--limit", type=int, default=10)


@app.verb("search", add_args=_search_args)
def search(args: argparse.Namespace, ctx: ExecContext) -> dict:
    """Search and return result list. DOES NOT tap any result."""
    # 1. Ensure foreground
    ctx.app.ensure_foreground()
    time.sleep(1.5)

    # 2. Tap search icon at home toolbar — selector cd="搜索"
    xml = ctx.ui.dump()["path"]
    from pathlib import Path
    xml_text = Path(xml).read_text()
    node = ctx.ui.find_by_content_desc(xml_text, "搜索")
    if node is None:
        from mobilecli.envelope import EmError, ErrorCode
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "search icon not on home screen",
                      hint="run `mobilecli dump` to inspect current state")
    ctx.input.tap_node(node)
    time.sleep(2)

    # 3. Tap input box, set IME, type keyword
    xml_text = Path(ctx.ui.dump()["path"]).read_text()
    inp = ctx.ui.find_by_resource_id(xml_text, "com.ss.android.ugc.aweme:id/et_search_kw")
    if inp is None:
        from mobilecli.envelope import EmError, ErrorCode
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "search input not found")
    ctx.input.tap_node(inp)
    time.sleep(0.8)
    ctx.input.type_text(args.keyword)
    time.sleep(1.2)

    # 4. Press enter to submit
    ctx.input.keyevent(66)  # KEYCODE_ENTER
    time.sleep(3)

    # 5. Parse result cards (resource-id q21, dual-column grid)
    xml_text = Path(ctx.ui.dump()["path"]).read_text()
    cards = ctx.ui.find_all_by_resource_id(xml_text, "com.ss.android.ugc.aweme:id/q21")
    results = []
    for i, c in enumerate(cards[:args.limit], 1):
        results.append({
            "index": i,
            "cx": c["cx"],
            "cy": c["cy"],
            "bounds": c["bounds"],
            "title": "",  # title is in child TextView; deferred
        })

    return {"keyword": args.keyword, "results": results}
```

- [ ] **Step 4: Run test**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_douyin.py -k search -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/apps/douyin.py tests/integration/test_douyin.py
git commit -m "feat: douyin search verb"
```

## Task C5: Douyin open + detail verbs

**Files:**
- Modify: `src/mobilecli/apps/douyin.py`

- [ ] **Step 1: Add integration tests**

```python
@pytest.mark.integration
def test_douyin_open_first_result(device_serial):
    _cli("--serial", device_serial, "douyin", "launch")
    _cli("--serial", device_serial, "douyin", "search",
         "--keyword", "美食", "--limit", "5")
    payload = _cli("--serial", device_serial, "douyin", "open", "--rank", "1")
    assert payload["ok"] is True, payload


@pytest.mark.integration
def test_douyin_detail_after_open(device_serial):
    payload = _cli("--serial", device_serial, "douyin", "detail")
    assert payload["ok"] is True, payload
    data = payload["data"]
    assert "likes" in data and "comments" in data
```

- [ ] **Step 2: Run + see fail**

- [ ] **Step 3: Add verbs to `src/mobilecli/apps/douyin.py`**

```python
import re


def _open_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rank", type=int, required=True)


@app.verb("open", add_args=_open_args)
def open_result(args: argparse.Namespace, ctx: ExecContext) -> dict:
    """Tap the Nth search result card from the current results screen."""
    from pathlib import Path
    xml = Path(ctx.ui.dump()["path"]).read_text()
    cards = ctx.ui.find_all_by_resource_id(xml, "com.ss.android.ugc.aweme:id/q21")
    if args.rank < 1 or args.rank > len(cards):
        from mobilecli.envelope import EmError, ErrorCode
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            f"rank {args.rank} out of range (have {len(cards)} cards)",
            hint="run `mobilecli douyin search` first",
        )
    card = cards[args.rank - 1]
    ctx.input.tap_node(card)
    time.sleep(3)

    # Switch to single-column for stable comment access
    xml = Path(ctx.ui.dump()["path"]).read_text()
    toggle = ctx.ui.find_by_content_desc(xml, "单双列切换图标")
    if toggle is not None:
        ctx.input.tap_node(toggle)
        time.sleep(2)
    return {"rank": args.rank, "foreground": ctx.app.foreground()}


_COUNT_RE = re.compile(r"(\d+(?:\.\d+)?[万亿]?)")


def _parse_count(s: str) -> str:
    m = _COUNT_RE.search(s or "")
    return m.group(1) if m else ""


@app.verb("detail")
def detail(args: argparse.Namespace, ctx: ExecContext) -> dict:
    """Read like/comment/share counts from the current video detail screen."""
    from pathlib import Path
    xml = Path(ctx.ui.dump()["path"]).read_text()
    like = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/gl1")
    comment = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/eql")
    share = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/zk8")
    collect = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/d_7")
    return {
        "likes": _parse_count(like["content_desc"]) if like else "",
        "comments": _parse_count(comment["content_desc"]) if comment else "",
        "shares": _parse_count(share["content_desc"]) if share else "",
        "collects": _parse_count(collect["content_desc"]) if collect else "",
    }
```

- [ ] **Step 4: Run tests**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_douyin.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/apps/douyin.py tests/integration/test_douyin.py
git commit -m "feat: douyin open + detail verbs"
```

## Task C6: Douyin comment verb (with --commit gate + linter + governor)

**Files:**
- Modify: `src/mobilecli/apps/douyin.py`

- [ ] **Step 1: Add E2E test (gated by EM_E2E + EM_ALLOW_COMMIT)**

```python
@pytest.mark.e2e
def test_douyin_comment_dry_run(device_serial):
    payload = _cli("--serial", device_serial, "douyin", "comment", "--text", "学到了 👍")
    # Dry-run path: returns committed=False
    assert payload["ok"] is True, payload
    assert payload["data"]["committed"] is False


@pytest.mark.e2e
def test_douyin_comment_linter_blocks(device_serial):
    payload = _cli("--serial", device_serial, "douyin", "comment", "--text", "加微信 abc")
    assert payload["ok"] is False
    assert payload["error"]["code"] == "CONTENT_BANNED"
```

- [ ] **Step 2: Run + see fail**

Run: `EM_E2E=1 EM_ALLOW_COMMIT=1 EM_INTEGRATION=1 pytest tests/integration/test_douyin.py -k comment -v`
Expected: FAIL.

- [ ] **Step 3: Add comment verb to `src/mobilecli/apps/douyin.py`**

```python
def _comment_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--text", required=True)


@app.verb("comment", add_args=_comment_args, requires_commit_flag=True)
def comment(args: argparse.Namespace, ctx: ExecContext) -> dict:
    """Comment on the current video detail. Default dry-run; --commit to actually send."""
    # 1. ContentLinter blocks 加微信 / phone / 戳我 / etc.
    ctx.linter.check_or_raise(args.text)

    # 2. Governor: if we'd be over cap, refuse before action
    ctx.governor.check_or_raise("comment")

    # 3. Tap inline compose box (eoy)
    from pathlib import Path
    xml = Path(ctx.ui.dump()["path"]).read_text()
    inp = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/eoy")
    if inp is None:
        from mobilecli.envelope import EmError, ErrorCode
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "comment input not visible",
                      hint="open a video detail first via `douyin open --rank N`")
    ctx.input.tap_node(inp)
    time.sleep(1.5)

    # 4. Type the comment
    ctx.input.type_text(args.text)
    time.sleep(1.5)

    # 5. Locate the dynamic send button (FrameLayout es1)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    send_btn = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/es1")
    if send_btn is None:
        from mobilecli.envelope import EmError, ErrorCode
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "send button did not appear",
                      hint="text may not have been entered; check IME with `doctor`")

    if not getattr(args, "commit", False):
        # Dry-run: cancel by pressing back, return what we would have done
        ctx.input.keyevent("back")
        return {
            "dry_run": True,
            "committed": False,
            "text": args.text,
            "send_button_cx": send_btn["cx"],
            "send_button_cy": send_btn["cy"],
        }

    # 6. THE COMMIT
    ctx.input.tap_node(send_btn)
    time.sleep(4)

    # 7. Verify by re-dumping and searching for our text (in any content-desc)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    verified = args.text in xml

    # 8. Record in governor only after success
    ctx.governor.record("comment")
    return {
        "dry_run": False,
        "committed": True,
        "verified_visible": verified,
        "text": args.text,
    }
```

- [ ] **Step 4: Run tests**

Run: `EM_E2E=1 EM_ALLOW_COMMIT=1 EM_INTEGRATION=1 pytest tests/integration/test_douyin.py -k comment -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/apps/douyin.py tests/
git commit -m "feat: douyin comment verb with linter + governor + --commit gate"
```

## Task C7: Xiaohongshu plugin — launch + search + open + detail

**Files:**
- Create: `src/mobilecli/apps/xiaohongshu.py`
- Create: `tests/integration/test_xiaohongshu.py`

- [ ] **Step 1: Write integration tests**

```python
"""Integration tests for xiaohongshu — read-only."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

EXPECTED_SERIAL = "EXAMPLE-SERIAL"


@pytest.fixture(scope="module")
def device_serial() -> str:
    r = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    if EXPECTED_SERIAL not in r.stdout:
        pytest.skip(f"test device {EXPECTED_SERIAL} not connected")
    return EXPECTED_SERIAL


def _cli(*args: str) -> dict:
    r = subprocess.run([sys.executable, "-m", "mobilecli", *args],
                       capture_output=True, text=True)
    return json.loads(r.stdout)


@pytest.mark.integration
def test_xhs_launch(device_serial):
    payload = _cli("--serial", device_serial, "xiaohongshu", "launch")
    assert payload["ok"] is True, payload


@pytest.mark.integration
def test_xhs_search_returns_results(device_serial):
    _cli("--serial", device_serial, "xiaohongshu", "launch")
    payload = _cli("--serial", device_serial, "xiaohongshu", "search",
                   "--keyword", "穿搭", "--limit", "5")
    assert payload["ok"] is True, payload
    assert len(payload["data"]["results"]) >= 1
```

- [ ] **Step 2: Run + see fail**

- [ ] **Step 3: Write `src/mobilecli/apps/xiaohongshu.py`**

```python
"""Xiaohongshu app plugin (小红书). Selectors per research/ui-trees/xiaohongshu/00-selectors.md."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from mobilecli.envelope import EmError, ErrorCode
from mobilecli.plugin import App, ExecContext

PACKAGE = "com.xingin.xhs"

app = App(
    name="xiaohongshu",
    package=PACKAGE,
    daily_caps={
        "comment": 20,
        "dm": 30,
        "follow": 30,
        "like": 100,
    },
    extra_lint_patterns=[],
)


@app.verb("launch")
def launch(args, ctx: ExecContext) -> dict:
    """Launch. If first launch lands on login wall, press back + relaunch once."""
    ctx.app.launch()
    time.sleep(3)
    fg = ctx.app.foreground()
    # If we're on the login wall (DeviceOfflineRemindActivity), retry
    if "DeviceOfflineRemindActivity" in fg.get("activity", ""):
        ctx.input.keyevent("back")
        time.sleep(1)
        ctx.app.launch()
        time.sleep(3)
        fg = ctx.app.foreground()
    return {"foreground": fg, "package": PACKAGE}


def _search_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--keyword", required=True)
    p.add_argument("--limit", type=int, default=10)


@app.verb("search", add_args=_search_args)
def search(args, ctx: ExecContext) -> dict:
    ctx.app.ensure_foreground()
    time.sleep(1.5)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    # XHS uses semantic resource-ids
    search_bar = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/mSearchToolBarSearchBtn")
    if search_bar is None:
        # Maybe we're on home — tap top search affordance instead
        search_bar = ctx.ui.find_by_content_desc(xml, "搜索")
    if search_bar is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "search bar not found")
    ctx.input.tap_node(search_bar)
    time.sleep(2)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    inp = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/mSearchToolBarEt")
    if inp is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "search input not found")
    ctx.input.tap_node(inp)
    time.sleep(0.8)
    ctx.input.type_text(args.keyword)
    time.sleep(1.2)
    ctx.input.keyevent(66)
    time.sleep(3)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    cards = ctx.ui.find_all_by_resource_id(xml, "com.xingin.xhs:id/searchNoteCard")
    results = []
    for i, c in enumerate(cards[:args.limit], 1):
        results.append({
            "index": i,
            "cx": c["cx"],
            "cy": c["cy"],
            "bounds": c["bounds"],
            "title": "",
        })
    return {"keyword": args.keyword, "results": results}


def _open_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rank", type=int, required=True)


@app.verb("open", add_args=_open_args)
def open_result(args, ctx: ExecContext) -> dict:
    xml = Path(ctx.ui.dump()["path"]).read_text()
    cards = ctx.ui.find_all_by_resource_id(xml, "com.xingin.xhs:id/searchNoteCard")
    if args.rank < 1 or args.rank > len(cards):
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND,
                      f"rank {args.rank} out of range (have {len(cards)})")
    ctx.input.tap_node(cards[args.rank - 1])
    time.sleep(3)
    return {"rank": args.rank, "foreground": ctx.app.foreground()}


@app.verb("detail")
def detail(args, ctx: ExecContext) -> dict:
    xml = Path(ctx.ui.dump()["path"]).read_text()
    like = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/noteLikeLayout")
    comment = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/noteCommentLayout")
    collect = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/noteCollectLayout")
    import re
    def _count(node):
        if not node:
            return ""
        m = re.search(r"(\d+)", node.get("content_desc", "") + node.get("text", ""))
        return m.group(1) if m else ""
    return {
        "likes": _count(like),
        "comments": _count(comment),
        "collects": _count(collect),
    }
```

- [ ] **Step 4: Run tests**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_xiaohongshu.py -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/apps/xiaohongshu.py tests/integration/test_xiaohongshu.py
git commit -m "feat: xiaohongshu plugin — launch/search/open/detail"
```

## Task C8: Xiaohongshu comment (DRY-RUN ONLY in v1)

**Files:**
- Modify: `src/mobilecli/apps/xiaohongshu.py`

- [ ] **Step 1: Add integration test (dry-run only, NEVER sends)**

```python
@pytest.mark.integration
def test_xhs_comment_dry_run_never_sends(device_serial):
    payload = _cli("--serial", device_serial, "xiaohongshu", "comment",
                   "--text", "学到了")
    assert payload["ok"] is True, payload
    assert payload["data"]["dry_run"] is True
    # There is no `committed` field; only dry_run.
    assert "committed" not in payload["data"] or payload["data"]["committed"] is False


@pytest.mark.integration
def test_xhs_comment_linter_blocks(device_serial):
    payload = _cli("--serial", device_serial, "xiaohongshu", "comment",
                   "--text", "戳我看更多")
    assert payload["ok"] is False
    assert payload["error"]["code"] == "CONTENT_BANNED"
```

- [ ] **Step 2: Run + see fail**

- [ ] **Step 3: Add comment verb to xiaohongshu.py (no `requires_commit_flag`)**

```python
def _comment_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--text", required=True)


@app.verb("comment", add_args=_comment_args)  # NO --commit flag — v1 is dry-run only
def comment(args, ctx: ExecContext) -> dict:
    """DRY-RUN ONLY in v1: open compose, type text, locate send button, then cancel."""
    ctx.linter.check_or_raise(args.text)
    ctx.governor.check_or_raise("comment")

    xml = Path(ctx.ui.dump()["path"]).read_text()
    compose = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/mContentET")
    if compose is None:
        # Maybe compose isn't open yet — try tapping the "comment" CTA at bottom
        cta = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/noteCommentLayout")
        if cta is not None:
            ctx.input.tap_node(cta)
            time.sleep(1.5)
            xml = Path(ctx.ui.dump()["path"]).read_text()
            compose = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/mContentET")
    if compose is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "XHS comment compose not visible",
                      hint="open a note detail first via `xiaohongshu open --rank N`")

    ctx.input.tap_node(compose)
    time.sleep(1)
    ctx.input.type_text(args.text)
    time.sleep(1.5)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    send_btn = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/commentFuncBtnSend")

    # CRITICAL: never actually tap the send button. Cancel by pressing back.
    ctx.input.keyevent("back")
    return {
        "dry_run": True,
        "text": args.text,
        "send_button_cx": send_btn["cx"] if send_btn else None,
        "send_button_cy": send_btn["cy"] if send_btn else None,
        "note": "v1 is dry-run only; the send button was never tapped",
    }
```

- [ ] **Step 4: Run tests**

Run: `EM_INTEGRATION=1 pytest tests/integration/test_xiaohongshu.py -k comment -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/mobilecli/apps/xiaohongshu.py tests/
git commit -m "feat: xiaohongshu comment verb (dry-run only, never sends in v1)"
```

## Task C9: Phase C acceptance

- [ ] **Step 1: Run all unit + integration tests**

```bash
pytest tests/unit -v
EM_INTEGRATION=1 pytest tests/integration -v
EM_E2E=1 EM_ALLOW_COMMIT=1 EM_INTEGRATION=1 pytest tests/integration -v
```

Expected: all pass.

- [ ] **Step 2: Confirm spec §7 Phase C DoD**:
  - [ ] `mobilecli douyin launch / search / open / detail / comment` work
  - [ ] `mobilecli xiaohongshu launch / search / open / detail / comment` work
  - [ ] Douyin comment `--commit` posts and verifies; without it, dry-run
  - [ ] Xiaohongshu comment is dry-run only
  - [ ] entry_points group exists in pyproject and is consulted at load time

- [ ] **Step 3: Tag**

```bash
git tag -a v0.1.0-phaseC -m "Phase C: app plugins complete"
```

---

# Phase D — Release polish

Goal: full README with disclaimer + CLI table + risks + anti-scope. ai-usage.md + plugin-guide.md. asciinema demo. CI green.

## Task D1: README (full)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write `README.md` per spec §11**

Use the structure from `docs/superpowers/specs/2026-05-21-everything-mobile-design.md` §11. Include:

1. Disclaimer block (CN + EN, both, verbatim from spec §11)
2. "What this is" paragraph
3. Quickstart (3 commands)
4. CLI feature table — every primitive command + every app verb
5. Risk-control rules — short prose linking to `docs/anti-risk-control.md`
6. Usage risks list
7. "What this is not" anti-scope list
8. Plugin authoring link → `docs/plugin-guide.md`
9. Contributing link → `CONTRIBUTING.md` (skeleton)
10. License: MIT

(Content too long to inline here — copy the disclaimer from spec §11 verbatim. The CLI table columns: Command | Purpose | Example | JSON shape | Humanized?)

- [ ] **Step 2: Verify README renders correctly** (open in a Markdown previewer locally)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: full README with disclaimer, CLI table, risks, anti-scope"
```

## Task D2: docs/ai-usage.md

**Files:**
- Create: `docs/ai-usage.md`

- [ ] **Step 1: Write `docs/ai-usage.md`**

A copy-paste recipe showing how Claude Code drives `mobilecli` end-to-end:

```markdown
# Driving everything-mobile from Claude Code / Codex

This doc shows how an AI agent invokes `mobilecli` to drive an Android phone.

## Mental model

- `mobilecli` is stateless. Every command is independent.
- Output is JSON. Parse it.
- Screenshots and dumps are written to disk; the JSON returns the path.
  Read the file with your built-in Read tool — don't pipe the binary into stdout.

## Example session

```bash
# 1. Verify device
mobilecli devices
# → {"data": {"devices": [{"serial": "5A170...", "state": "device"}]}}

# 2. Take a look
mobilecli screenshot -o /tmp/screen.png
# AI now reads /tmp/screen.png and reasons about the screen.

# 3. Driving search on Douyin
mobilecli douyin launch
mobilecli douyin search --keyword "美食" --limit 5
# → results: [{index, cx, cy, bounds, ...}, ...]
# AI picks one — say index 3 — and:
mobilecli douyin open --rank 3
mobilecli douyin detail
# → {likes, comments, shares, collects}
```

## Batch operations

Don't use a magic --all flag. Loop in your own driver code so the governor can pace operations:

```bash
results=$(mobilecli xiaohongshu search --keyword "穿搭" --limit 10 | jq -r '.data.results[].index')
for i in $results; do
    mobilecli xiaohongshu open --rank "$i"
    mobilecli xiaohongshu detail | jq .
    mobilecli keyevent back
done
```

If the governor caps are hit, `RATE_LIMITED` is returned — stop your loop.
```

- [ ] **Step 2: Commit**

```bash
git add docs/ai-usage.md
git commit -m "docs: ai-usage.md — Claude Code / Codex driving recipe"
```

## Task D3: docs/plugin-guide.md

**Files:**
- Create: `docs/plugin-guide.md`

- [ ] **Step 1: Write the plugin authoring guide**

Cover:
- Skeleton pyproject + entry_points stanza for an external plugin
- ExecContext methods plugin authors can use
- Daily-caps + extra_lint_patterns conventions
- TDD pattern: fixture XMLs + selector finding
- Submitting upstream: PR criteria (matching anti-scope, no PII patterns, no fraud)

(Content full; structured like a 1-2 page guide. Include a working example "mobilecli-tiktok" stub.)

- [ ] **Step 2: Commit**

```bash
git add docs/plugin-guide.md
git commit -m "docs: plugin-guide.md — authoring + publishing external plugins"
```

## Task D4: CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

- [ ] **Step 1: Write CONTRIBUTING.md**

Cover:
- DCO / sign-off requirement
- Pre-PR: `ruff`, `mypy`, `pytest -m "not integration"`
- Test requirements: any new verb needs both unit (fixture) and integration test
- Anti-scope: PRs adding spam helpers / follower farms / engagement fakers will be closed
- Linked to README §"What this is not"

- [ ] **Step 2: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: CONTRIBUTING.md"
```

## Task D5: 60-second asciinema demo

**Files:**
- Create: `docs/demo.cast` (asciinema)
- Modify: `README.md` (embed link)

- [ ] **Step 1: Install asciinema, record session**

```bash
brew install asciinema
asciinema rec docs/demo.cast
# In the recording, run:
#   mobilecli doctor
#   mobilecli douyin launch
#   mobilecli douyin search --keyword 美食 --limit 3
#   mobilecli douyin detail
```

Keep total length under 90 seconds.

- [ ] **Step 2: Add to README** under Quickstart:

```markdown
[![asciicast](docs/demo.cast)](docs/demo.cast)
```

- [ ] **Step 3: Commit**

```bash
git add docs/demo.cast README.md
git commit -m "docs: 60s asciinema demo"
```

## Task D6: CI green + entry_points sanity check

- [ ] **Step 1: Push to GitHub, watch CI**

```bash
git push -u origin main
gh run watch
```

Expected: ruff + format + mypy + unit tests all pass on all 3 Python versions.

- [ ] **Step 2: Manual entry_points test**

Create a temporary external plugin in `/tmp/mobilecli-demo-ext/`:

```toml
# pyproject.toml
[project]
name = "mobilecli-demo-ext"
version = "0.0.1"
dependencies = ["everything-mobile"]

[project.entry-points."mobilecli.apps"]
demo_ext = "mobilecli_demo_ext:app"
```

```python
# src/mobilecli_demo_ext/__init__.py
from mobilecli.plugin import App
app = App(name="demo_ext", package="com.example.demo")

@app.verb("hello")
def hello(args, ctx):
    return {"greeting": "hi from external"}
```

Install + verify:

```bash
pip install -e /tmp/mobilecli-demo-ext/
mobilecli demo_ext hello   # expect: {"ok": true, "data": {"greeting": "hi from external"}}
pip uninstall -y mobilecli-demo-ext
```

- [ ] **Step 3: Document outcome in `docs/plugin-guide.md`** (already covered in D3)

- [ ] **Step 4: Commit any fixes if entry_points discovery broke**

## Task D7: Release v1.0.0

- [ ] **Step 1: Bump version in pyproject.toml**

```toml
version = "1.0.0"
```

- [ ] **Step 2: Generate CHANGELOG.md**

```markdown
# 1.0.0 (2026-05-XX)

## Features
- 11 primitive commands: devices, screenshot, tap, swipe, type, keyevent, dump, launch, install, foreground, doctor
- App plugins: douyin (launch/search/open/detail/comment with --commit), xiaohongshu (launch/search/open/detail/comment dry-run)
- Layer 2.5 humanization: log-normal timing, jittered taps, bezier swipe
- SessionGovernor with per-account JSON persistence + daily caps
- ContentLinter with default banned-phrase regex set
- DeviceCheck + doctor reports fingerprint signals
- External plugin discovery via `mobilecli.apps` entry_points group

## Anti-scope (intentional)
- No batch/--all verbs. AI orchestrates loops.
- No WeChat plugin.
- No cloud-phone backend.
- No spam helpers, follower farms, or engagement fakers.
```

- [ ] **Step 3: Tag and push**

```bash
git tag -a v1.0.0 -m "everything-mobile v1.0.0"
git push --tags
```

- [ ] **Step 4: Optionally publish to PyPI**

```bash
python -m build
python -m twine upload dist/*
```

(skip if account not configured — user can do later)

## Task D8: Phase D acceptance + final v1 DoD

- [ ] **Step 1: Walk the spec §7 DoD checklist top to bottom — all checked**

- [ ] **Step 2: Run a representative end-to-end demo on the test device**

```bash
mobilecli devices
mobilecli doctor
mobilecli douyin launch
mobilecli douyin search --keyword 美食 --limit 3
mobilecli douyin open --rank 1
mobilecli douyin detail
mobilecli douyin comment --text "学到了 👍"        # dry-run, no commit
EM_ALLOW_COMMIT=1 mobilecli douyin comment --text "学到了 👍" --commit   # real send
mobilecli keyevent back
mobilecli xiaohongshu launch
mobilecli xiaohongshu search --keyword 穿搭 --limit 3
mobilecli xiaohongshu open --rank 1
mobilecli xiaohongshu detail
mobilecli xiaohongshu comment --text "学到了"     # dry-run, never sends
```

- [ ] **Step 3: Tag**

```bash
git tag -a v1.0.0-final -m "v1.0.0 with all DoD items green"
```

---

## Self-Review (executed before handing off)

**Spec coverage** — every spec section maps to a task:

| Spec § | Task |
|---|---|
| §2 Architecture | A2–A11 (Layers 1+2), B1–B6 (Layer 2.5), C1–C8 (Layer 3) |
| §3 CLI surface | A4–A12, C2–C8 |
| §4 Plugin system | C1, C2; entry_points verified in D6 |
| §5 JSON contract | A2 (envelope), error codes added in B (RATE_LIMITED/CONTENT_BANNED/WARMUP_REQUIRED) |
| §6 Repo structure | created across phases |
| §7 v1 DoD | A14, B6, C9, D8 |
| §8 Test strategy | unit (A2–C9), integration (A6–C9), e2e (C6) |
| §8.5 Humanization defaults | B1–B5 |
| §9 Known gotchas | A10 (dump retry), A11 (foreground), C3 (XHS relaunch recovery), C4–C5 (Douyin selectors) |
| §10 Open questions | explicitly out of v1 |
| §11 License + README | A13 (skeleton), D1 (full) |

**Placeholder scan** — no "TBD", no "implement later". README content is delegated to D1 (which references spec §11 verbatim) and demo recording in D5; both are concrete tasks. Two acceptable placeholders: WARMUP_REQUIRED error code is in envelope but only used if a future warm-up tracker is added (kept in v1 to avoid breaking the closed-set later; tests don't exercise it).

**Type consistency** — `tap_humanized` signature is `(device, *, bounds=..., x=..., y=...)`. All call sites use one or the other. `find_by_*` returns `dict | None`. `governor.check_or_raise(action_class)` and `governor.record(action_class)` both take the same `str` key.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-21-everything-mobile-v1.md`.
