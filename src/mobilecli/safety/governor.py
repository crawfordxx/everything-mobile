"""SessionGovernor -- per-account daily caps with JSON-file persistence."""

from __future__ import annotations

import datetime as _dt
import json
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
        self._state: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"accounts": {}}
        try:
            loaded: dict[str, Any] = json.loads(self.state_path.read_text())
            return loaded
        except json.JSONDecodeError:
            return {"accounts": {}}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2))

    def _today(self) -> str:
        return _dt.date.today().isoformat()

    def _counts_today(self) -> dict[str, int]:
        acct = self._state.setdefault("accounts", {}).setdefault(self.account, {})
        day: dict[str, int] = acct.setdefault(self._today(), {})
        return day

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
        counts = self._counts_today()
        counts[action_class] = counts.get(action_class, 0) + 1
        self._save()
