#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from radiolink.copernicus import default_cache_directory, extract_profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract a great-circle profile from Copernicus GLO-30"
    )
    parser.add_argument("lat_a", type=float)
    parser.add_argument("lon_a", type=float)
    parser.add_argument("lat_b", type=float)
    parser.add_argument("lon_b", type=float)
    parser.add_argument("--step-m", type=float, default=30.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cache",
        type=Path,
        default=default_cache_directory(),
    )
    args = parser.parse_args(argv)
    extract_profile(
        args.lat_a,
        args.lon_a,
        args.lat_b,
        args.lon_b,
        args.output,
        step_m=args.step_m,
        cache_dir=args.cache,
        progress=print,
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
