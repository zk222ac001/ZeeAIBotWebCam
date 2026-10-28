#!/usr/bin/env python3
"""Compatibility entry point for the authoritative trusted production-readiness report.

Accepts the same CLI arguments and exit codes as production_readiness.py. This
read-only report never moves hardware or declares physical acceptance from a
software check. Use the supervised pilot and AEC procedures for that evidence.
"""
from pathlib import Path
from runpy import run_path

if __name__ == "__main__":
    run_path(str(Path(__file__).with_name("production_readiness.py")), run_name="__main__")
