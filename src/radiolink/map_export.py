from __future__ import annotations

import json

from .i18n import tr

LINK_MAP_PDF = "relatorio_enlace_com_mapa.pdf"
COVERAGE_MAP_PDF = "relatorio_cobertura_com_mapa.pdf"

MAP_EXPORT_SCRIPT = """
function enableMapExport(map, markers, endpoint, filename, drawLegend) {
  const button = document.getElementById("export-map-pdf");
  const status = document.getElementById("export-status");
  let osmTileRendered = false;
  map.on("sourcedata", event => {
    if (event.sourceId === "osm" && event.tile?.state === "loaded") {
      osmTileRendered = true;
    }
  });

  function captureMap() {
    const source = map.getCanvas();
    const canvas = document.createElement("canvas");
    canvas.width = source.width;
    canvas.height = source.height;
    const width = source.clientWidth;
    const height = source.clientHeight;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(canvas.width / width, 0, 0, canvas.height / height, 0, 0);
    ctx.drawImage(source, 0, 0, width, height);

    for (const marker of markers) {
      const point = map.project(marker.coordinates);
      if (point.x < 0 || point.y < 0 || point.x > width || point.y > height) continue;
      ctx.save();
      ctx.translate(point.x, point.y);
      ctx.fillStyle = marker.color;
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, 1);
      ctx.lineTo(-9, -14);
      ctx.arc(0, -16, 9, Math.PI, 0);
      ctx.lineTo(9, -14);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      if (marker.label) {
        ctx.font = "bold 12px Arial, sans-serif";
        ctx.textAlign = "center";
        ctx.lineWidth = 4;
        ctx.strokeText(marker.label, 0, -29, 160);
        ctx.fillStyle = "#17191d";
        ctx.fillText(marker.label, 0, -29, 160);
      }
      ctx.restore();
    }
    if (drawLegend) drawLegend(ctx, width, height);
    const credit = "© OpenStreetMap contributors — openstreetmap.org/copyright";
    ctx.font = "11px Arial, sans-serif";
    const creditWidth = Math.min(ctx.measureText(credit).width + 12, width);
    ctx.fillStyle = "rgba(255,255,255,0.9)";
    ctx.fillRect(width - creditWidth, height - 19, creditWidth, 19);
    ctx.fillStyle = "#17191d";
    ctx.fillText(credit, width - creditWidth + 6, height - 6, creditWidth - 12);
    return canvas;
  }

  if (location.protocol !== "http:") {
    status.textContent = exportMessages.openFromApp;
    return;
  }
  button.disabled = false;
  button.addEventListener("click", async () => {
    button.disabled = true;
    status.textContent = exportMessages.loading;
    try {
      await new Promise((resolve, reject) => {
        const onIdle = () => {
          clearTimeout(timer);
          resolve();
        };
        const timer = setTimeout(() => {
          map.off("idle", onIdle);
          reject(new Error(exportMessages.tiles));
        }, 15000);
        map.once("idle", onIdle);
        map.triggerRepaint();
      });
      if (!osmTileRendered) throw new Error(exportMessages.tiles);
      const blob = await new Promise((resolve, reject) => captureMap().toBlob(
        value => value ? resolve(value) : reject(new Error(exportMessages.tiles)),
        "image/png"
      ));
      status.textContent = exportMessages.generating;
      const response = await fetch(endpoint, {
        method: "POST", headers: {"Content-Type": "image/png"}, body: blob
      });
      if (response.status === 409) throw new Error(exportMessages.openFromApp);
      if (!response.ok) throw new Error("HTTP " + response.status);
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      status.textContent = exportMessages.saved;
    } catch (error) {
      status.textContent = exportMessages.failed + error.message;
    } finally {
      button.disabled = false;
    }
  });
}
"""


def map_export_script() -> str:
    messages = {
        "openFromApp": tr("Abra Mapa e relatório no aplicativo para exportar o PDF."),
        "loading": tr("Aguardando o mapa carregar…"),
        "tiles": tr("O fundo OpenStreetMap não carregou. Verifique a conexão e tente novamente."),
        "generating": tr("Gerando o PDF com mapa geográfico…"),
        "saved": tr("PDF com mapa geográfico salvo e baixado."),
        "failed": tr("Não foi possível exportar o mapa: "),
    }
    return "const exportMessages = " + json.dumps(messages, ensure_ascii=False) + ";\n" + MAP_EXPORT_SCRIPT
