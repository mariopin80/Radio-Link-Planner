"""Desktop form-state regressions without requiring a graphical display."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest

from radiolink.antenna import COVERAGE_ANTENNA_DEFAULTS
from radiolink.desktop import RadioLinkPlannerApp, _ReceiverThresholdInput
from radiolink.desktop_core import suggested_output_directory
from radiolink.domain import Project, ReceiverSpec
from radiolink.i18n import get_language, set_language
from radiolink.modes import MODE_PROFILES, threshold_dbm
from radiolink.project_editor import editor_values_from_project


@pytest.fixture(autouse=True)
def portuguese_labels():
    previous = get_language()
    set_language("pt", persist=False)
    try:
        yield
    finally:
        set_language(previous, persist=False)


def make_editor():
    tcl = tk.Tcl()
    variable = lambda: tk.StringVar(master=tcl)
    app = object.__new__(RadioLinkPlannerApp)
    app._automatic_output = {"link": True, "coverage": True}
    app._writing_output = False
    app.link_form_initialized = False
    app.name_var = variable()
    app.frequency_var = variable()
    app.mode_var = variable()
    app.polarization_var = variable()
    app.availability_var = variable()
    app.allow_mode_change_var = tk.BooleanVar(master=tcl)
    app.output_var = variable()
    app.status_var = variable()
    app.coverage_progress_var = variable()
    app.terminal_vars = {
        key: {name: variable() for name in (
            "name", "latitude", "longitude", "height", "gain", "line_loss", "power", "sensitivity",
        )} for key in ("a", "b")
    }
    app.link_thresholds = {
        key: _ReceiverThresholdInput(tcl, vals["sensitivity"])
        for key, vals in app.terminal_vars.items()
    }
    app.coverage_vars = {
        key: variable() for key in (
            "name", "latitude", "longitude", "frequency", "polarization", "mode", "radius",
            "resolution_preset", "custom_resolution", "time_percentage", "tx_height",
            "tx_gain", "tx_line_loss", "tx_power", "rx_height", "rx_gain", "rx_line_loss",
            "rx_sensitivity", "output", *COVERAGE_ANTENNA_DEFAULTS,
        )
    }
    app.coverage_threshold = _ReceiverThresholdInput(tcl, app.coverage_vars["rx_sensitivity"])
    app.notebook = SimpleNamespace(select=lambda _: None)
    app.editor_tab = object()
    app.progress = SimpleNamespace(configure=lambda **_: None)
    app._disable_result_actions = lambda: None
    app._register_output_callbacks()
    return app


def test_new_link_starts_blank_and_updates_only_automatic_output():
    app = make_editor()
    app._new_link()
    assert app.name_var.get() == "Novo Enlace"
    assert app.link_form_initialized
    assert app.frequency_var.get() == ""
    assert app.availability_var.get() == "50"
    for station in app.terminal_vars.values():
        for field in ("latitude", "longitude", "height", "gain", "line_loss", "power"):
            assert station[field].get() == ""
        assert station["sensitivity"].get() == "-115.03"
    assert app.output_var.get() == str(suggested_output_directory("Novo Enlace"))
    with pytest.raises(ValueError):
        app._collect_editor_values()

    app.name_var.set("Boituva - Pico do Urubu")
    assert Path(app.output_var.get()).name == "boituva-pico-do-urubu"
    custom = Path("custom") / "link-output"
    app.output_var.set(str(custom))
    app.name_var.set("Outra estação")
    assert app.output_var.get() == str(custom)
    app._new_link()
    assert Path(app.output_var.get()).name == "novo-enlace"


def test_new_coverage_starts_with_empty_equipment_and_presets_for_analysis():
    app = make_editor()
    app._new_coverage()
    v = app.coverage_vars
    assert v["name"].get() == "Nova Cobertura"
    assert v["radius"].get() == "50"
    assert v["time_percentage"].get() == "50"
    assert v["rx_sensitivity"].get() == "-115.03"
    for field in (
        "latitude", "longitude", "frequency", "tx_height", "tx_gain", "tx_line_loss",
        "tx_power", "rx_height", "rx_gain", "rx_line_loss",
        "tx_hpbw", "tx_front_to_back", "tx_azimuth",
    ):
        assert v[field].get() == ""
    assert Path(v["output"].get()).name == "nova-cobertura"
    with pytest.raises(ValueError):
        app._collect_coverage_request()
    v["name"].set("Cobertura VHF Boituva")
    assert Path(v["output"].get()).name == "cobertura-vhf-boituva"
    v["output"].set(str(Path("custom") / "coverage-output"))
    v["name"].set("Outra cobertura")
    assert Path(v["output"].get()).name == "coverage-output"


def test_new_projects_offer_the_preset_for_every_mode():
    app = make_editor()
    app._new_link()
    app._new_coverage()
    for mode in MODE_PROFILES:
        app.mode_var.set(mode)
        app._mode_changed(None)
        app.coverage_vars["mode"].set(mode)
        app._coverage_mode_changed(None)
        expected, _ = threshold_dbm(ReceiverSpec(), mode)
        for control in (*app.link_thresholds.values(), app.coverage_threshold):
            assert control.value.get() == f"{expected:.2f}"
            assert control.source.get() == "Limiar do preset"

    app.coverage_threshold.value.set("-138")
    assert app.coverage_threshold.source.get() == "Limiar informado"
    app._new_coverage()
    assert app.coverage_threshold.overrides == {}
    assert app.coverage_threshold.value.get() == "-115.03"


def test_link_sensitivity_overrides_round_trip_by_mode_and_terminal(
    reference_project, tmp_path, monkeypatch,
):
    app = make_editor()
    app._new_link()
    app._apply_editor_values(editor_values_from_project(reference_project))
    a, b = app.link_thresholds["a"], app.link_thresholds["b"]
    app.mode_var.set("FM")
    app._mode_changed(None)
    a.value.set("-117.5")
    b.value.set("-120")
    app.mode_var.set("SSB")
    app._mode_changed(None)
    a.value.set("-131")
    b.value.set("-132")
    app.mode_var.set("FM")
    app._mode_changed(None)
    assert (float(a.value.get()), float(b.value.get())) == (-117.5, -120)
    assert a.source.get() == b.source.get() == "Limiar informado"

    filename = tmp_path / "sensitivities.rlp"
    monkeypatch.setattr("radiolink.desktop.filedialog.asksaveasfilename", lambda **_: str(filename))
    app._save_link_project()
    saved, _ = Project.from_json(filename)

    app._new_link()
    assert a.overrides == b.overrides == {}
    app._apply_editor_values(editor_values_from_project(saved))
    assert (float(a.value.get()), float(b.value.get())) == (-117.5, -120)
    app.mode_var.set("SSB")
    app._mode_changed(None)
    assert (float(a.value.get()), float(b.value.get())) == (-131, -132)
    a.value.set("")
    assert a.source.get() == "Limiar do preset"
    assert "SSB" not in app._collect_editor_values().terminal_a.receiver.threshold_overrides_dbm


def test_saving_changed_coordinates_invalidates_previous_profile(
    reference_project, reference_profile, tmp_path, monkeypatch,
):
    from radiolink.desktop import filedialog

    app = make_editor()
    app._new_link()
    app.loaded_project = reference_project
    app.loaded_terrain_path = reference_profile.source_path
    values = editor_values_from_project(reference_project)
    app.name_var.set("Boituva - Pico do Jaraguá")
    app.frequency_var.set(str(values.frequency_mhz))
    app.availability_var.set(str(values.target_availability_percent))
    for key, terminal in (("a", values.terminal_a), ("b", values.terminal_b)):
        vars = app.terminal_vars[key]
        vars["name"].set(terminal.name)
        for field, data in (
            ("latitude", terminal.latitude_deg), ("longitude", terminal.longitude_deg),
            ("height", terminal.antenna_height_m), ("gain", terminal.antenna_gain_dbi),
            ("line_loss", terminal.line_loss_db), ("power", terminal.tx_power_w),
        ):
            vars[field].set(str(data))
        app.link_thresholds[key].load("FM", ReceiverSpec())
    app.terminal_vars["a"]["latitude"].set("-23.27873714")
    app.terminal_vars["a"]["longitude"].set("-47.67702601")
    app.terminal_vars["b"]["latitude"].set("-23.45842360")
    app.terminal_vars["b"]["longitude"].set("-46.76704776")
    assert not app._can_reuse_loaded_terrain()
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **_: str(tmp_path / "new-link.rlp"))
    app._save_link_project()
    assert app.link_project_path == (tmp_path / "new-link.rlp").resolve()
    assert app.loaded_terrain_path is None
