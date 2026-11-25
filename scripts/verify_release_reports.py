"""Inspect reports produced by the packaged application, without importing it."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from pypdf import PdfReader

from radiolink.i18n import set_language, tr
from radiolink.version import APP_NAME


def verify(directory: Path) -> None:
    matrix = json.loads((directory / "validation.json").read_text(encoding="utf-8"))
    assert set(matrix) == {"pt", "en", "es", "fr", "de"}
    for language, values in matrix.items():
        set_language(language)
        for key in ("report_pdf", "coverage_pdf"):
            reader = PdfReader(values[key])
            text = "\n".join(page.extract_text() for page in reader.pages)
            assert reader.metadata.author == APP_NAME and APP_NAME in text, (language, key, "product name")
            assert tr("Configuração") in text, (language, key, "untranslated heading")
            assert "\u25a0" not in text, (language, key, "missing glyph")
            assert "Copernicus WorldDEM-30" in text, (language, key, "missing DEM credit")
            assert "Airbus Defence and Space" in text, (language, key, "missing DEM rights holder")
            fonts = [
                font.get_object()
                for page in reader.pages
                for font in page["/Resources"]["/Font"].values()
            ]
            assert fonts and all(
                "/FontDescriptor" in font and "/FontFile2" in font["/FontDescriptor"]
                for font in fonts
            ), (language, key, "PDF text fonts must be embedded")
            if key == "coverage_pdf":
                assert re.search(re.escape(tr("Células calculadas")) + r"\s+" + str(values["coverage_cells"]) + r"\b", text), (language, "incorrect cell count in PDF")
                assert tr("Modo RX") in text, (language, "missing RX mode")
            else:
                for model in ("ITM", "P1812", "P2001"):
                    assert model in text, (language, model)
                assert tr("Amostras que violam o critério de Fresnel (%)") in " ".join(text.split()), (language, "Fresnel label")
        for report in (directory / language).rglob("*.html"):
            body = report.read_text(encoding="utf-8")
            assert APP_NAME in body, (language, report, "product name")
            assert "https://www.openstreetmap.org/copyright" in body, (language, report, "missing OSM attribution link")
            assert "Copernicus WorldDEM-30" in body, (language, report, "missing DEM credit")
            for index, script in enumerate(re.findall(r"<script>(.*?)</script>", body, re.S)):
                path = report.with_name(f"verified-script-{index}.js")
                path.write_text(script, encoding="utf-8")
                subprocess.run(["node", "--check", str(path)], check=True)
                path.unlink()
    set_language("pt")
    print("All five languages: PDF contents, cell counts and map JavaScript verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    verify(parser.parse_args().directory)
