"""Canonical Django CLI entrypoint for packaged backend execution.

Usage:
    python -m config.manage <command>
"""

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    from django.core.management import execute_from_command_line

    execute_from_command_line(argv or sys.argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

