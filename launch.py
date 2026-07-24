#!/usr/bin/env python3
"""Start nesus_ai interactively. No daemon and no local LLM."""
from __future__ import annotations
import os, sys
from pathlib import Path

BIN = Path.home() / ".local/bin/nesus_ai"


def main() -> int:
    target = str(BIN) if BIN.exists() else str(Path(__file__).with_name("nesus_ai.py"))
    argv = [target, *sys.argv[1:]]
    if len(argv) == 1:
        argv += ["doctor"]
    os.execv(target, argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
