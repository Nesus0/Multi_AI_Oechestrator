#!/usr/bin/env python3
"""nesus_ai has no background service to stop."""
from __future__ import annotations


def main() -> int:
    print("nesus_ai is on-demand: no daemon or local LLM is running.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
