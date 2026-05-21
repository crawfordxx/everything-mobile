"""App plugin base -- verb registration."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mobilecli.plugin.ctx import ExecContext

VerbFn = Callable[[argparse.Namespace, "ExecContext"], dict[str, Any]]


@dataclass
class Verb:
    name: str
    fn: VerbFn
    add_args: Callable[[argparse.ArgumentParser], None] | None = None
    requires_commit_flag: bool = False


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
                name=name,
                fn=fn,
                add_args=add_args,
                requires_commit_flag=requires_commit_flag,
            )
            return fn

        return deco

    def get_verb(self, name: str) -> VerbFn | None:
        v = self.verbs.get(name)
        return v.fn if v else None
