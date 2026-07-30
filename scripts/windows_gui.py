from __future__ import annotations

import multiprocessing
import sys
import traceback
from pathlib import Path

from radiolink.desktop_core import smoke_test


def run() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--smoke-test":
        output_directory = Path(sys.argv[2]).resolve()
        try:
            smoke_test(output_directory)
        except Exception:
            output_directory.mkdir(parents=True, exist_ok=True)
            (output_directory / "smoke-error.txt").write_text(
                traceback.format_exc(), encoding="utf-8"
            )
            return 2
        return 0
    from radiolink.desktop import main

    return main()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(run())
