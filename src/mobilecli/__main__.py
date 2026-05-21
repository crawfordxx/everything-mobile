"""Entry point so `python -m mobilecli` works alongside the console script."""

from mobilecli.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
