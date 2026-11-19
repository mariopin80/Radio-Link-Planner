from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


@contextmanager
def result_run(output_directory: str | Path) -> Iterator[tuple[Path, Path]]:
    """Publish a complete set of files with one directory rename."""
    runs = Path(output_directory).expanduser().resolve() / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=runs, prefix=".pending-") as temporary:
        staging = Path(temporary)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        final = runs / f"{timestamp}-{staging.name.removeprefix('.pending-')}"
        yield staging, final
        staging.rename(final)


def published_paths(paths: dict[str, Path], staging: Path, final: Path) -> dict[str, Path]:
    return {name: final / path.relative_to(staging) for name, path in paths.items()}
