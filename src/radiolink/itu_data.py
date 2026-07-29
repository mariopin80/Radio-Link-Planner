from __future__ import annotations

import importlib.metadata
import importlib.util
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ProgressCallback = Callable[[str], None]


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


def package_directory(product: DigitalProduct) -> Path:
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


def ensure_itu_data(
    *,
    include_p1812: bool = True,
    include_p2001: bool = True,
    p1812_archive: Path | None = None,
    p2001_archive: Path | None = None,
    cleanup_source_maps: bool = False,
    progress: ProgressCallback | None = print,
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
) -> Path:
    package_dir = package_dir.resolve() if package_dir else package_directory(product)
    output = package_dir / product.output_filename
    if output.exists():
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
                urllib.request.urlretrieve(product.components_url, archive)
            maps_dir = package_dir / "maps"
            maps_dir.mkdir(parents=True, exist_ok=True)
            _extract_expected_files(product, archive, maps_dir)
            _build_numpy_product(product, maps_dir, output, progress)
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
            "o aplicativo não consegue gravar os dados ITU ao lado do "
            "executável; extraia o pacote para uma pasta gravável do usuário"
        ) from exc
    if not output.exists():
        raise RuntimeError(f"{product.output_filename} was not generated")
    _notify(progress, str(output))
    return output


def _extract_expected_files(
    product: DigitalProduct, archive: Path, maps_dir: Path
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
            with (
                bundle.open(members[basename]) as source,
                (maps_dir / basename).open("wb") as destination,
            ):
                shutil.copyfileobj(source, destination)


def _build_numpy_product(
    product: DigitalProduct,
    maps_dir: Path,
    output: Path,
    progress: ProgressCallback | None,
) -> None:
    arrays = {}
    for filename in sorted(product.expected_files):
        _notify(progress, f"Processing file {filename}")
        dtype = int if filename in product.integer_files else float
        arrays[product.key_for(filename)] = np.loadtxt(maps_dir / filename, dtype=dtype)
    if product.compressed:
        np.savez_compressed(output, **arrays)
    else:
        np.savez(output, **arrays)


def _notify(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)
