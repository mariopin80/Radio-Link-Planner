#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import sys
from pathlib import Path

from radiolink.itu_data import ensure_itu_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Install the official ITU digital products required by Py1812 and Py2001"
        )
    )
    parser.add_argument(
        "--archive",
        type=Path,
        help=(
            "backward-compatible alias for --p2001-archive; use an already "
            "downloaded official P.2001 components ZIP"
        ),
    )
    parser.add_argument(
        "--p1812-archive",
        type=Path,
        help="use an already downloaded official P.1812 components ZIP",
    )
    parser.add_argument(
        "--p2001-archive",
        type=Path,
        help="use an already downloaded official P.2001 components ZIP",
    )
    args = parser.parse_args(argv)
    try:
        ensure_itu_data(
            p1812_archive=args.p1812_archive,
            p2001_archive=args.p2001_archive or args.archive,
        )
    except (
        importlib.metadata.PackageNotFoundError,
        ModuleNotFoundError,
    ) as exc:
        print(
            'Py1812/Py2001 are not installed. Run: pip install -e ".[models]"',
            file=sys.stderr,
        )
        print(f"detail: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
