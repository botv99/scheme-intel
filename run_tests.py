"""Convenience test runner for scheme-intel.

Usage:
    python run_tests.py                  # full suite, coverage + parallel
    python run_tests.py --no-coverage    # without coverage
    python run_tests.py -m unit          # only unit-marked tests
    python run_tests.py --tb-long        # full tracebacks
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_args(coverage: bool = True, parallel: bool = True,
               tb_long: bool = False, marker: str | None = None) -> list[str]:
    args: list[str] = ["tests/"]
    if coverage:
        args += [
            "--cov=src/scheme_intel",
            "--cov-report=term-missing",
            "--cov-report=xml",
            "--cov-report=html",
        ]
    args.append("-v")
    if parallel:
        args += ["-n", "auto"]
    args.append("--tb=long" if tb_long else "--tb=short")
    args.append("--strict-markers")
    if marker:
        args += ["-m", marker]
    return args


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scheme-intel test suite")
    parser.add_argument("--no-coverage", action="store_true", help="skip coverage reporting")
    parser.add_argument("--no-parallel", action="store_true", help="disable pytest-xdist parallelism")
    parser.add_argument("--tb-long", action="store_true", help="show full tracebacks")
    parser.add_argument("-m", "--marker", default=None, help="run only tests matching a marker")
    opts = parser.parse_args()
    import pytest
    return pytest.main(build_args(
        coverage=not opts.no_coverage,
        parallel=not opts.no_parallel,
        tb_long=opts.tb_long,
        marker=opts.marker,
    ))


if __name__ == "__main__":
    sys.exit(main())
