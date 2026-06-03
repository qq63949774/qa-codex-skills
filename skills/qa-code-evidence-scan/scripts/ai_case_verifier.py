#!/usr/bin/env python3
"""Backward-compatible CLI wrapper for code scan module."""

from modules.code_scan import main


if __name__ == "__main__":
    raise SystemExit(main())
