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
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Disable humanization (debugging only; requires EM_ALLOW_RAW=1)",
    )
    parser.add_argument(
        "--account",
        default="default",
        help="SessionGovernor account identifier",
    )
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
    """Import every command module + every app plugin and attach to subparsers."""
    from mobilecli.plugin import load as load_apps

    loaded: dict[str, Any] = {}
    for name, modpath in COMMAND_MODULES.items():
        mod = importlib.import_module(modpath)
        mod.add_parser(sub)
        loaded[name] = mod

    # Layer 3: app plugins -- each is a top-level subcommand with nested verbs
    for app_name, app_obj in load_apps().items():
        app_parser = sub.add_parser(
            app_name,
            help=f"{app_obj.package} ({len(app_obj.verbs)} verbs)",
        )
        verb_sub = app_parser.add_subparsers(dest="verb", metavar="VERB")
        for verb_name, verb in app_obj.verbs.items():
            vp = verb_sub.add_parser(verb_name)
            if verb.add_args is not None:
                verb.add_args(vp)
            if verb.requires_commit_flag:
                vp.add_argument(
                    "--commit",
                    action="store_true",
                    help="Actually perform the action (requires EM_ALLOW_COMMIT=1)",
                )
        loaded[app_name] = ("__app__", app_obj)
    return loaded


def _run_app_verb(app_obj: Any, args: argparse.Namespace) -> str:
    """Dispatch one app verb wrapped in @envelope so EmError -> JSON."""
    import os
    from typing import cast

    from mobilecli.adb.device import Device
    from mobilecli.envelope import EmError, ErrorCode, envelope
    from mobilecli.plugin.ctx import ExecContext

    @envelope(command=f"{app_obj.name}.{args.verb}")
    def _inner(*, device: str) -> dict[str, Any]:
        if args.verb is None:
            raise EmError(
                ErrorCode.UNKNOWN,
                f"no verb specified for {app_obj.name}",
                hint=f"available: {', '.join(app_obj.verbs.keys())}",
            )
        verb = app_obj.get_verb(args.verb)
        if verb is None:
            raise EmError(
                ErrorCode.UNKNOWN,
                f"unknown verb: {app_obj.name} {args.verb}",
                hint=f"available: {', '.join(app_obj.verbs.keys())}",
            )
        if getattr(args, "commit", False) and os.environ.get("EM_ALLOW_COMMIT") != "1":
            raise EmError(
                ErrorCode.COMMIT_REFUSED,
                "--commit requires EM_ALLOW_COMMIT=1",
                hint="export EM_ALLOW_COMMIT=1 (only for actions you actually intend)",
            )
        dev = Device.from_serial(device or None)
        ctx = ExecContext.build(
            device=dev,
            package=app_obj.package,
            account=args.account,
            caps=app_obj.daily_caps,
            extra_lint=app_obj.extra_lint_patterns,
        )
        return cast(dict[str, Any], verb(args, ctx))

    result: str = _inner(device=args.serial or "")
    return result


def main(argv: list[str] | None = None) -> int:
    import os

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
    if args.raw and os.environ.get("EM_ALLOW_RAW") != "1":
        _emit_error(
            command=args.command or "",
            code=ErrorCode.COMMIT_REFUSED,
            message="--raw requires EM_ALLOW_RAW=1",
            hint="export EM_ALLOW_RAW=1 (debugging only)",
            pretty=args.pretty,
        )
        return 1
    if args.command not in loaded:
        _emit_error(
            command=args.command or "",
            code=ErrorCode.UNKNOWN,
            message=f"unknown command: {args.command}",
            hint="run `mobilecli --help`",
            pretty=args.pretty,
        )
        return 1
    target = loaded[args.command]
    if isinstance(target, tuple) and target[0] == "__app__":
        out = _run_app_verb(target[1], args)
    else:
        out = target.run(args)
    _emit(out, args.pretty)
    return 0
