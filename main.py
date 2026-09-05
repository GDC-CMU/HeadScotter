#!/usr/bin/env python
"""HeadScotter entrypoint.

The ArcadeLauncher spawns games as ``[sys.executable, "main.py"]`` with
``cwd`` set to this checkout, so this file must be runnable exactly as
is, with no command-line arguments, from any working directory.
"""
from __future__ import annotations

from headscotter.game import Game


def main() -> None:
    Game().run()


if __name__ == "__main__":
    main()
