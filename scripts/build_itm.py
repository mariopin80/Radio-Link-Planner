#!/usr/bin/env python3
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "ntia-itm"
INCLUDE = VENDOR / "include"
SOURCE = VENDOR / "src"
BUILD = VENDOR / "build"


def main() -> int:
    BUILD.mkdir(parents=True, exist_ok=True)
    sources = sorted(str(path) for path in SOURCE.glob("*.cpp"))
    if not sources:
        print("No ITM sources found.", file=sys.stderr)
        return 2

    system = platform.system()
    if system == "Windows":
        compiler = shutil.which("cl")
        if compiler is None:
            print(
                "MSVC compiler 'cl' was not found. Run from a Developer "
                "Command Prompt or provide the official NTIA itm.dll.",
                file=sys.stderr,
            )
            return 2
        output = BUILD / "itm.dll"
        command = [
            compiler,
            "/nologo",
            "/LD",
            "/EHsc",
            "/MT",
            "/O2",
            "/std:c++17",
            f"/I{INCLUDE}",
            *sources,
            f"/Fe:{output}",
        ]
    elif system == "Darwin":
        compiler = shutil.which("clang++") or shutil.which("g++")
        if compiler is None:
            print("No C++ compiler was found.", file=sys.stderr)
            return 2
        output = BUILD / "libitm.dylib"
        command = [
            compiler,
            "-O2",
            "-std=c++17",
            "-fPIC",
            "-dynamiclib",
            f"-I{INCLUDE}",
            *sources,
            "-o",
            str(output),
        ]
    else:
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            print("No C++ compiler was found.", file=sys.stderr)
            return 2
        output = BUILD / "libitm.so"
        command = [
            compiler,
            "-O2",
            "-std=c++17",
            "-fPIC",
            "-shared",
            f"-I{INCLUDE}",
            *sources,
            "-o",
            str(output),
        ]
    subprocess.run(command, check=True)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
