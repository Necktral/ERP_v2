#!/usr/bin/env python
"""Backward-compatible entrypoint that delegates to `config.manage`."""

from config.manage import main


if __name__ == "__main__":
    raise SystemExit(main())
