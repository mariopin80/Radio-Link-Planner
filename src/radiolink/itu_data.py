from __future__ import annotations

import importlib
import importlib.metadata
import importlib.resources
import importlib.util
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import numpy as np

ProgressCallback = Callable[[str], None]
CancelCheck = Callable[[], bool]
_DIGITAL_PRODUCT_IMPORT_LOCK = threading.RLock()


@dataclass(frozen=True)
class DigitalProduct:
    recommendation: str
    distribution_name: str
    package_name: str
    output_filename: str
    components_url: str
    expected_files: frozenset[str]
    integer_files: frozenset[str] = frozenset()
    key_overrides: tuple[tuple[str, str], ...] = ()
    compressed: bool = False

    def key_for(self, filename: str) -> str:
        default = Path(filename).stem
        return dict(self.key_overrides).get(default, default)


P1812_PRODUCT = DigitalProduct(
    recommendation="P.1812-8",
    distribution_name="Py1812",
    package_name="Py1812",
    output_filename="P1812.npz",
    components_url=(
        "https://www.itu.int/dms_pubrec/itu-r/rec/p/"
        "R-REC-P.1812-8-202509-I%21%21ZIP-E.zip"
    ),
    expected_files=frozenset({"DN50.TXT", "N050.TXT"}),
)

P2001_PRODUCT = DigitalProduct(
    recommendation="P.2001-6",
    distribution_name="Py2001",
    package_name="Py2001",
    output_filename="P2001.npz",
    components_url=(
        "https://www.itu.int/dms_pubrec/itu-r/rec/p/"
        "R-REC-P.2001-6-202509-I%21%21ZIP-E.zip"
    ),
    expected_files=frozenset(
        {
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
    ),
    integer_files=frozenset({"TropoClim.txt"}),
    key_overrides=(("FoEs0.1", "FoEs0p1"),),
    compressed=True,
)


def default_data_directory() -> Path:
    """Return a persistent user-writable directory for ITU-R digital products."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data)
    else:
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        root = (
            Path(xdg_data_home)
            if xdg_data_home
            else Path.home() / ".local" / "share"
        )
    return root / "RadioLinkPlanner" / "ITU-R"


def product_data_directory(
    product: DigitalProduct,
    *,
    root: Path | None = None,
) -> Path:
    base = Path(root) if root is not None else default_data_directory()
    return base.expanduser().resolve() / product.package_name


def package_directory(product: DigitalProduct) -> Path:
    """Locate the installed implementation package, not its writable data."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).resolve() / product.package_name
    spec = importlib.util.find_spec(product.package_name)
    if spec is not None and spec.submodule_search_locations:
        directory = Path(next(iter(spec.submodule_search_locations))).resolve()
        if directory.is_dir():
            return directory
    distribution = importlib.metadata.distribution(product.distribution_name)
    for item in distribution.files or ():
        path = Path(str(item))
        if path.parts[-2:] == (product.package_name, "__init__.py"):
            return Path(distribution.locate_file(path)).resolve().parent
    raise FileNotFoundError(
        f"could not locate package directory for {product.distribution_name}"
    )


def load_digital_product_module(
    product: DigitalProduct,
    module_name: str,
    *,
    data_dir: Path | None = None,
) -> ModuleType:
    """Import an ITU implementation while resolving its maps from user data.

    Py1812 and Py2001 load their ``*.npz`` product through
    :func:`importlib.resources.files` at module import time. Their normal
    package location is read-only in an installed PyInstaller application, so
    resource resolution is redirected narrowly for that package during the
    first import.
    """
    directory = (
        Path(data_dir).expanduser().resolve()
        if data_dir is not None
        else product_data_directory(product)
    )
    product_path = directory / product.output_filename
    if not product_path.is_file():
        raise FileNotFoundError(
            f"dados {product.recommendation} não encontrados em {product_path}"
        )

    qualified_name = f"{product.package_name}.{module_name}"
    with _DIGITAL_PRODUCT_IMPORT_LOCK:
        loaded = sys.modules.get(qualified_name)
        if loaded is not None:
            return loaded

        importlib.import_module(product.package_name)
        original_files = importlib.resources.files

        def redirected_files(anchor=None):
            package_name = (
                anchor
                if isinstance(anchor, str)
                else getattr(anchor, "__name__", None)
            )
            if package_name == product.package_name:
                return directory
            if anchor is None:
                return original_files()
            return original_files(anchor)

        importlib.resources.files = redirected_files
        try:
            return importlib.import_module(qualified_name)
        finally:
            importlib.resources.files = original_files


def ensure_itu_data(
    *,
    include_p1812: bool = True,
    include_p2001: bool = True,
    p1812_archive: Path | None = None,
    p2001_archive: Path | None = None,
    cleanup_source_maps: bool = False,
    progress: ProgressCallback | None = print,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Path]:
    requested = []
    if include_p1812:
        requested.append((P1812_PRODUCT, p1812_archive))
    if include_p2001:
        requested.append((P2001_PRODUCT, p2001_archive))
    outputs: dict[str, Path] = {}
    for product, archive in requested:
        output = install_digital_product(
            product,
            archive_path=archive,
            cleanup_source_maps=cleanup_source_maps,
            progress=progress,
            cancel_check=cancel_check,
        )
        outputs[product.recommendation] = output
    return outputs


def install_digital_product(
    product: DigitalProduct,
    *,
    package_dir: Path | None = None,
    archive_path: Path | None = None,
    cleanup_source_maps: bool = False,
    progress: ProgressCallback | None = print,
    cancel_check: CancelCheck | None = None,
) -> Path:
    package_dir = (
        package_dir.expanduser().resolve()
        if package_dir is not None
        else product_data_directory(product)
    )
    output = package_dir / product.output_filename
    if output.exists():
        _check_cancelled(cancel_check)
        _notify(progress, str(output))
        return output

    prefix = product.recommendation.lower().replace(".", "").replace("-", "")
    try:
        with tempfile.TemporaryDirectory(prefix=f"radio-link-{prefix}-") as temp:
            temp_dir = Path(temp)
            archive = (
                archive_path.resolve() if archive_path else temp_dir / f"{prefix}.zip"
            )
            if archive_path is None:
                _notify(
                    progress,
                    f"Downloading official ITU-R "
                    f"{product.recommendation} components...",
                )
                _download_archive(
                    product,
                    archive,
                    progress,
                    cancel_check,
                )
            _check_cancelled(cancel_check)
            maps_dir = package_dir / "maps"
            maps_dir.mkdir(parents=True, exist_ok=True)
            _extract_expected_files(
                product,
                archive,
                maps_dir,
                cancel_check=cancel_check,
            )
            _build_numpy_product(
                product,
                maps_dir,
                output,
                progress,
                cancel_check=cancel_check,
            )
            if cleanup_source_maps:
                for filename in product.expected_files:
                    (maps_dir / filename).unlink(missing_ok=True)
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"não foi possível baixar os dados oficiais ITU-R "
            f"{product.recommendation}; verifique a conexão com a internet"
        ) from exc
    except PermissionError as exc:
        raise RuntimeError(
            f"o aplicativo não consegue gravar os dados ITU-R em "
            f"{package_dir}; verifique as permissões da pasta do usuário"
        ) from exc
    if not output.exists():
        raise RuntimeError(f"{product.output_filename} was not generated")
    _notify(progress, str(output))
    return output


def _extract_expected_files(
    product: DigitalProduct,
    archive: Path,
    maps_dir: Path,
    *,
    cancel_check: CancelCheck | None = None,
) -> None:
    with zipfile.ZipFile(archive) as bundle:
        members = {
            Path(name).name: name for name in bundle.namelist() if Path(name).name
        }
        missing = product.expected_files - members.keys()
        if missing:
            raise RuntimeError(
                f"official {product.recommendation} archive is missing "
                f"expected files: {sorted(missing)}"
            )
        for basename in product.expected_files:
            _check_cancelled(cancel_check)
            with (
                bundle.open(members[basename]) as source,
                (maps_dir / basename).open("wb") as destination,
            ):
                while chunk := source.read(1024 * 1024):
                    _check_cancelled(cancel_check)
                    destination.write(chunk)


def _build_numpy_product(
    product: DigitalProduct,
    maps_dir: Path,
    output: Path,
    progress: ProgressCallback | None,
    *,
    cancel_check: CancelCheck | None = None,
) -> None:
    arrays = {}
    for filename in sorted(product.expected_files):
        _check_cancelled(cancel_check)
        _notify(progress, f"Processing file {filename}")
        dtype = int if filename in product.integer_files else float
        arrays[product.key_for(filename)] = np.loadtxt(maps_dir / filename, dtype=dtype)
    _check_cancelled(cancel_check)
    if product.compressed:
        np.savez_compressed(output, **arrays)
    else:
        np.savez(output, **arrays)


def _download_archive(
    product: DigitalProduct,
    destination: Path,
    progress: ProgressCallback | None,
    cancel_check: CancelCheck | None,
) -> None:
    _check_cancelled(cancel_check)
    request = urllib.request.Request(
        product.components_url,
        headers={
            "User-Agent": (
                "RadioLinkPlanner/0.4 "
                "(+https://github.com/mariopin80/radio-link-planner)"
            )
        },
    )
    with (
        urllib.request.urlopen(request, timeout=90) as response,
        destination.open("wb") as handle,
    ):
        total = int(response.headers.get("Content-Length", "0") or 0)
        downloaded = 0
        next_report = 10
        while chunk := response.read(1024 * 1024):
            _check_cancelled(cancel_check)
            handle.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                percentage = int(100 * downloaded / total)
                if percentage >= next_report:
                    _notify(
                        progress,
                        f"Downloading {product.recommendation}: "
                        f"{min(percentage, 100)}%...",
                    )
                    next_report += 10


def _check_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise InterruptedError("ITU-R data installation cancelled")


def _notify(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)
