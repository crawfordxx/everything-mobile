"""Plugin discovery -- built-in apps + entry_points."""

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

    import mobilecli.apps as apps_pkg

    for _finder, name, _ispkg in pkgutil.iter_modules(apps_pkg.__path__):
        mod = importlib.import_module(f"mobilecli.apps.{name}")
        app = getattr(mod, "app", None)
        if isinstance(app, App):
            _APPS[app.name] = app

    eps = entry_points(group="mobilecli.apps")
    for ep in eps:
        try:
            app = ep.load()
            if isinstance(app, App):
                _APPS[app.name] = app
        except Exception:  # noqa: BLE001
            continue

    return _APPS
