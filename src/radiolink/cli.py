from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .domain import Project
from .engine import analyze_project
from .report import write_outputs
from .terrain import TerrainProfile
from .version import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="radio-link",
        description="Radio Link Planner scientific engine",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser(
        "analyze", help="analyze a link project JSON"
    )
    analyze.add_argument("project", type=Path)
    analyze.add_argument(
        "--output", "-o", type=Path, default=Path("results/latest")
    )
    analyze.add_argument(
        "--runs",
        type=int,
        help="override Monte Carlo run count from the project",
    )
    analyze.add_argument(
        "--no-plots", action="store_true", help="skip PNG plot generation"
    )
    analyze.add_argument(
        "--print-json",
        action="store_true",
        help="also print the full result JSON to stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "analyze":
        parser.error("unknown command")
    try:
        project, base_dir = Project.from_json(args.project)
        if args.runs is not None:
            project.monte_carlo.runs = args.runs
        profile = TerrainProfile.from_csv(
            project.resolved_terrain_path(base_dir)
        )
        result, arrays = analyze_project(project, profile)
        paths = write_outputs(
            args.output,
            project,
            profile,
            result,
            arrays,
            make_plots=not args.no_plots,
        )
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    summary = {
        "engine_version": __version__,
        "project": project.name,
        "result_sha256": result["result_sha256"],
        "outputs": {name: str(path) for name, path in paths.items()},
        "assessments": {
            direction: values["assessment"]
            for direction, values in result["directions"].items()
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.print_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
