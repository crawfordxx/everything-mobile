"""Top-level CLI dispatcher.

Builds an argparse tree with global flags and a subcommand registry. Each
subcommand module exposes `add_parser(subparsers)` and `run(args) -> str`.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from typing import Any

from mobilecli.envelope import ErrorCode

# Registry: subcommand name -> module path.
COMMAND_MODULES: dict[str, str] = {
    "devices": "mobilecli.commands.devices",
    "screenshot": "mobilecli.commands.screenshot",
    "tap": "mobilecli.commands.tap",
    "swipe": "mobilecli.commands.swipe",
    "type": "mobilecli.commands.type_cmd",
    "keyevent": "mobilecli.commands.keyevent",
    "dump": "mobilecli.commands.dump",
    "launch": "mobilecli.commands.launch",
    "install": "mobilecli.commands.install",
    "foreground": "mobilecli.commands.foreground",
    "doctor": "mobilecli.commands.doctor",
}


def _build_parser() -> tuple[argparse.ArgumentParser, Any]:
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
    return parser, sub


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


def _load_commands(sub: Any) -> dict[str, Any]:
    """Import every command module and let it attach to the subparsers."""
    loaded: dict[str, Any] = {}
    for name, modpath in COMMAND_MODULES.items():
        mod = importlib.import_module(modpath)
        mod.add_parser(sub)
        loaded[name] = mod
    return loaded


def main(argv: list[str] | None = None) -> int:
    parser, sub = _build_parser()
    loaded = _load_commands(sub)
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
