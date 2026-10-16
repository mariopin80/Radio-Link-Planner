"""Application text and stable choices, shared by Tk, workers and reports."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .translations import MESSAGES

LANGUAGES = {
    "pt": ("Português", "br"),
    "en": ("English", "gb"),
    "es": ("Español", "es"),
    "fr": ("Français", "fr"),
    "de": ("Deutsch", "de"),
}
_language = os.environ.get("RADIOLINK_LANGUAGE", "pt")
if _language not in LANGUAGES:
    _language = "pt"

CHOICES = {
    "quick": "Rápida", "recommended": "Recomendada",
    "detailed": "Detalhada", "custom": "Personalizada",
    "vertical": "Vertical", "horizontal": "Horizontal",
    "robust": "robusto", "viable": "viável", "marginal": "marginal",
    "improbable": "improvável", "indeterminate": "indeterminado",
    "high": "alta", "medium": "média", "low": "baixa",
    "ok": "OK", "unavailable": "indisponível", "error": "erro",
    "unsupported": "não suportado",
    "outside_scope": "fora do escopo",
}


def get_language() -> str:
    return _language


def html_language() -> str:
    return "pt-BR" if _language == "pt" else _language


def map_locale() -> dict[str, str]:
    return {
        "NavigationControl.ZoomIn": tr("Aproximar"),
        "NavigationControl.ZoomOut": tr("Afastar"),
        "NavigationControl.ResetBearing": tr("Restaurar norte"),
        "AttributionControl.ToggleAttribution": tr("Alternar atribuição"),
    }


def settings_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "RadioLinkPlanner" / "settings.json"


def set_language(language: str, *, persist: bool = False, path: Path | None = None) -> None:
    if language not in LANGUAGES:
        raise ValueError(f"unsupported language: {language}")
    global _language
    _language = language
    # Windows multiprocessing uses spawn. Children inherit this explicit choice.
    os.environ["RADIOLINK_LANGUAGE"] = language
    if persist:
        destination = path or settings_path()
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = json.loads(destination.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            data["language"] = language
            temporary = destination.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            temporary.replace(destination)
        except OSError:
            # Read-only profiles still allow using the selected language.
            pass


def load_language(path: Path | None = None) -> str:
    try:
        data = json.loads((path or settings_path()).read_text(encoding="utf-8"))
        language = data.get("language") if isinstance(data, dict) else None
        if language in LANGUAGES:
            set_language(language)
    except (OSError, ValueError, TypeError):
        pass
    return _language


def tr(message: str, **values: object) -> str:
    translated = message
    if _language != "pt" and message in MESSAGES:
        translated = MESSAGES[message][("en", "es", "fr", "de").index(_language)]
    return translated.format(**values) if values else translated


def choice_label(value: str) -> str:
    return tr(CHOICES.get(value, value))


def choice_id(label: str, allowed: tuple[str, ...]) -> str:
    """Accept machine IDs and labels from existing projects in every language."""
    for value in allowed:
        source = CHOICES[value]
        labels = (value, source, *MESSAGES.get(source, ()))
        if label.casefold() in (text.casefold() for text in labels):
            return value
    raise ValueError(f"invalid choice: {label}")


def validation_message(error: Exception) -> str:
    """Show localized field validation without library diagnostics in dialogs."""
    from pydantic import ValidationError

    if not isinstance(error, ValidationError):
        return str(error)
    fields = {
        "name": "Nome", "frequency_mhz": "Frequência (MHz)",
        "latitude_deg": "Latitude (°)", "longitude_deg": "Longitude (°)",
        "antenna_height_m": "Altura da antena (m)", "antenna_gain_dbi": "Ganho da antena (dBi)",
        "line_loss_db": "Perda no cabo (dB)", "tx_power_w": "Potência TX (W)",
        "target_availability_percent": "Meta (%)", "polarization": "Polarização",
        "runs": "Monte Carlo", "bandwidth_hz": "Largura de banda (Hz)",
    }
    messages = []
    for issue in error.errors(include_url=False):
        field = tr(fields.get(str(issue["loc"][-1]), str(issue["loc"][-1]))) if issue["loc"] else tr("Projeto Radio Link Planner")
        context = issue.get("ctx", {})
        bound = next((context[key] for key in ("ge", "gt", "le", "lt") if key in context), None)
        template = {
            "greater_than_equal": "O campo {field} deve ser maior ou igual a {bound}.",
            "greater_than": "O campo {field} deve ser maior que {bound}.",
            "less_than_equal": "O campo {field} deve ser menor ou igual a {bound}.",
            "less_than": "O campo {field} deve ser menor que {bound}.",
        }.get(issue["type"])
        messages.append(tr(template, field=field, bound=bound) if template else tr("Verifique o valor do campo {field}.", field=field))
    return "\n".join(messages)
