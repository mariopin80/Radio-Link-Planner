#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


P2001_COMPONENTS_URL = (
    "https://www.itu.int/dms_pubrec/itu-r/rec/p/"
    "R-REC-P.2001-6-202509-I%21%21ZIP-E.zip"
)
EXPECTED_FILES = {
    "DN_Median.txt",
    "DN_SubSlope.txt",
    "DN_SupSlope.txt",
    "dndz_01.txt",
    "Esarain_Mt_v5.txt",
    "Esarain_Pr6_v5.txt",
    "Esarain_Beta_v5.txt",
    "FoEs0.1.txt",
    "FoEs01.txt",
    "FoEs10.txt",
    "FoEs50.txt",
    "h0.txt",
    "surfwv_50_fixed.txt",
    "TropoClim.txt",
}


def package_directory(distribution_name: str, package_name: str) -> Path:
    distribution = importlib.metadata.distribution(distribution_name)
    for item in distribution.files or ():
        path = Path(str(item))
        if path.parts[-2:] == (package_name, f"{package_name}.py"):
            return Path(distribution.locate_file(path)).resolve().parent
    raise FileNotFoundError(
        f"could not locate package directory for {distribution_name}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install the ITU digital products required by Py2001"
    )
    parser.add_argument(
        "--archive",
        type=Path,
        help="use an already downloaded official P.2001 components ZIP",
    )
    args = parser.parse_args(argv)
    try:
        package_dir = package_directory("Py2001", "Py2001")
    except importlib.metadata.PackageNotFoundError:
        print(
            'Py2001 is not installed. Run: pip install -e ".[models]"',
            file=sys.stderr,
        )
        return 2
    output = package_dir / "P2001.npz"
    if output.exists():
        print(output)
        return 0

    with tempfile.TemporaryDirectory(prefix="radio-link-p2001-") as temp:
        temp_dir = Path(temp)
        archive = args.archive.resolve() if args.archive else temp_dir / "P2001.zip"
        if not args.archive:
            print("Downloading official ITU-R P.2001-6 components...")
            urllib.request.urlretrieve(P2001_COMPONENTS_URL, archive)
        maps_dir = package_dir / "maps"
        maps_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            names = {Path(name).name for name in bundle.namelist()}
            missing = EXPECTED_FILES - names
            if missing:
                raise RuntimeError(
                    f"official archive is missing expected files: {sorted(missing)}"
                )
            for name in bundle.namelist():
                basename = Path(name).name
                if basename in EXPECTED_FILES:
                    with bundle.open(name) as source, (
                        maps_dir / basename
                    ).open("wb") as destination:
                        shutil.copyfileobj(source, destination)
        subprocess.run(
            [sys.executable, str(package_dir / "initiate_digital_maps.py")],
            cwd=package_dir,
            check=True,
        )
    if not output.exists():
        print("P2001.npz was not generated.", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
