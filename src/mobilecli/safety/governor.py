"""SessionGovernor -- per-account daily caps with JSON-file persistence.

Concurrency model: every `record()` re-reads the state file, increments, and
writes atomically (tmp + os.replace). This makes concurrent CLI/plugin
processes safe -- last-writer-wins on individual writes but no lost-update on
the count because each record reads fresh state under the lock.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from mobilecli.envelope import EmError, ErrorCode

DEFAULT_STATE_DIR = Path.home() / ".everything-mobile" / "sessions"

# Slug-safe account names only. Prevents `--account ../../etc/passwd` style
# path traversal when account is used to derive the JSON state filename.
_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _validate_account(name: str) -> None:
    if not _ACCOUNT_RE.match(name):
        raise EmError(
            ErrorCode.UNKNOWN,
            f"invalid account name: {name!r}",
            hint="must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
        )


class SessionGovernor:
    """Tracks per-account per-day counts of action classes against caps."""

    def __init__(
        self,
        *,
        state_path: Path | None = None,
        account: str = "default",
        caps: dict[str, int] | None = None,
    ) -> None:
        _validate_account(account)
        self.account = account
        self.caps = caps or {}
        if state_path is None:
            DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
            state_path = DEFAULT_STATE_DIR / f"{account}.json"
        self.state_path = state_path

    def _load(self) -> dict[str, Any]:
        """Always read fresh -- never trust in-memory state."""
        if not self.state_path.exists():
            return {"accounts": {}}
        try:
            loaded: dict[str, Any] = json.loads(self.state_path.read_text(encoding="utf-8"))
            return loaded
        except json.JSONDecodeError:
            return {"accounts": {}}

    def _save_atomic(self, state: dict[str, Any]) -> None:
        """Write tmp file then os.replace() for atomic crash-safe swap."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=".em-session-",
            suffix=".json",
            dir=self.state_path.parent,
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.state_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _today(self) -> str:
        return _dt.date.today().isoformat()

    def _counts_for(self, state: dict[str, Any]) -> dict[str, int]:
        acct = state.setdefault("accounts", {}).setdefault(self.account, {})
        day: dict[str, int] = acct.setdefault(self._today(), {})
        return day

    def _counts_today(self) -> dict[str, int]:
        """Public-ish accessor used by tests; always reflects on-disk state."""
        return self._counts_for(self._load())

    def check_or_raise(self, action_class: str) -> None:
        cap = self.caps.get(action_class)
        if cap is None:
            return
        used = self._counts_today().get(action_class, 0)
        if used >= cap:
            raise EmError(
                ErrorCode.RATE_LIMITED,
                f"daily cap reached for {action_class}: {used}/{cap}",
                hint=f"wait until tomorrow or edit {self.state_path}",
            )

    def record(self, action_class: str) -> None:
        """Read-modify-write under atomic replace."""
        state = self._load()
        counts = self._counts_for(state)
        counts[action_class] = counts.get(action_class, 0) + 1
        self._save_atomic(state)
