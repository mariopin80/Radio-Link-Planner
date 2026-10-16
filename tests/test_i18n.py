from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from string import Formatter

import pytest

from radiolink.i18n import (
    CHOICES, LANGUAGES, choice_id, choice_label, get_language, load_language,
    set_language, tr,
)
from radiolink.translations import MESSAGES


@pytest.fixture(autouse=True)
def restore_language():
    original = get_language()
    set_language("pt")
    yield
    set_language(original)


def test_complete_catalog_and_preserved_numeric_formatting():
    def fields(message):
        return sorted((name, spec, conversion) for _, name, spec, conversion in Formatter().parse(message) if name)

    for message, translations in MESSAGES.items():
        assert len(translations) == 4
        assert all(value.strip() for value in translations)
        for value in translations:
            assert fields(value) == fields(message), (message, value)
    for source in CHOICES.values():
        assert source in MESSAGES
    root = Path(__file__).parents[1] / "src/radiolink"
    for source in root.rglob("*.py"):
        if source.name == "translations.py":
            continue
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr" and node.args and isinstance(node.args[0], ast.Constant):
                assert node.args[0].value in MESSAGES, (source.name, node.lineno, node.args[0].value)


@pytest.mark.parametrize("language", LANGUAGES)
def test_choices_keep_machine_ids_across_languages(language):
    set_language(language)
    for choices in (("quick", "recommended", "detailed", "custom"), ("vertical", "horizontal")):
        for value in choices:
            label = choice_label(value)
            assert choice_id(label, choices) == value
            assert choice_id(value, choices) == value
            for other in LANGUAGES:
                set_language(other)
                assert choice_id(label, choices) == value
            set_language(language)


def test_preferences_persist_and_corrupt_files_fall_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"other_setting": 123}', encoding="utf-8")
    set_language("de", persist=True, path=path)
    set_language("pt")
    assert load_language(path) == "de"
    assert json.loads(path.read_text())["other_setting"] == 123
    for invalid in ("bad json", "[]", '{"language": "zz"}'):
        path.write_text(invalid, encoding="utf-8")
        set_language("pt")
        assert load_language(path) == "pt"


def test_translated_html_preserves_user_names_and_styles(reference_project, reference_profile):
    from html.parser import HTMLParser
    from radiolink.engine import analyze_project
    from radiolink.report import build_html_report

    project = reference_project.model_copy(deep=True)
    project.name = "Station A & <Station B>"
    project.models.itm = project.models.p1812 = project.models.p2001 = False
    result, _ = analyze_project(project, reference_profile)
    set_language("de")
    markup = build_html_report(project, reference_profile, result, make_plots=False)
    class Title(HTMLParser):
        active = False
        text = ""
        def handle_starttag(self, tag, attrs):
            self.active = tag == "title"
        def handle_endtag(self, tag):
            if tag == "title":
                self.active = False
        def handle_data(self, text):
            if self.active:
                self.text += text
    title = Title()
    title.feed(markup)
    assert title.text == project.name + " — Radio Link Planner"
    assert "<Station B>" not in markup
    assert "&gt;" not in markup.split("<style>")[1].split("</style>")[0]


@pytest.mark.skipif(sys.platform != "win32" and not os.environ.get("DISPLAY"), reason="requires a display")
def test_ui_languages_projects_about_and_single_remaining_time(tmp_path, monkeypatch):
    import tkinter as tk

    from radiolink.coverage import CoverageProgress
    from radiolink.desktop import RadioLinkPlannerApp
    from radiolink.project_files import read_coverage_project
    from radiolink.version import __version__, CONTACT_EMAIL, CALLSIGN, DEVELOPER

    root = tk.Tk()
    root.withdraw()
    app = RadioLinkPlannerApp(root, load_preferences=False)
    filename = tmp_path / "coverage.rlp"
    monkeypatch.setattr("radiolink.desktop.filedialog.asksaveasfilename", lambda **_: str(filename))
    monkeypatch.setattr("radiolink.desktop.filedialog.askopenfilename", lambda **_: str(filename))
    try:
        for language in LANGUAGES:
            app._change_language(language, persist=False)
            root.update_idletasks()
            assert len(app.language_buttons) == 5
            app._open_mode("link")
            assert app._collect_editor_values().polarization == "vertical"
            assert app.notebook.tab(app.about_tab, "text") == tr("Sobre")
            def all_text(widget):
                result = []
                if "text" in widget.keys():
                    result.append(str(widget.cget("text")))
                return result + [text for child in widget.winfo_children() for text in all_text(child)]
            about = "\n".join(all_text(app.about_tab))
            for value in (__version__, DEVELOPER, CALLSIGN, CONTACT_EMAIL):
                assert value in about
            app._show_start_screen()
            app._open_mode("coverage")
            app.coverage_vars["resolution_preset"].set(choice_label("custom"))
            app.coverage_vars["custom_resolution"].set("1000")
            app.coverage_vars["polarization"].set(choice_label("horizontal"))
            app._save_coverage_project()
            saved = read_coverage_project(filename)
            assert saved["resolution_preset"] == "custom"
            assert saved["polarization"] == "horizontal"
            # Versions 0.4.x saved Portuguese display labels; keep accepting them.
            payload = json.loads(filename.read_text())
            payload["schema_version"] = "1.0"
            payload["values"]["resolution_preset"] = "Recomendada"
            payload["values"]["polarization"] = "Vertical"
            filename.write_text(json.dumps(payload), encoding="utf-8")
            app._select_coverage_project()
            request = app._collect_coverage_request(for_estimate=True)
            assert request.resolution_preset == "recommended"
            assert request.polarization == "vertical"
            app.events.put(("coverage_progress", CoverageProgress(
                42, "cells", tr("{x0:.0f}% — Calculando células: {x1:,} de {x2:,}", x0=42, x1=400, x2=1000),
                400, 1000, 60, 90,
            )))
            app._poll_events()
            assert app.coverage_progress_var.get().count("1 min 30 s") == 1
            assert "1 min 30 s" not in app.status_var.get()
            app._show_start_screen()
    finally:
        root.destroy()
