from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .coverage import (
    COVERAGE_RESOLUTION_M,
    CoverageCancelled,
    CoverageOutcome,
    CoverageProgress,
    CoverageRequest,
    run_coverage_analysis,
)
from .coverage_grid import (
    CoverageEstimate,
    available_memory_bytes,
    estimate_coverage,
    format_duration,
)
from .desktop_core import (
    APP_NAME,
    AnalysisOutcome,
    FormAnalysisRequest,
    build_desktop_summary,
    bundle_root,
    bundled_example_path,
    default_output_directory,
    run_form_analysis,
)
from .domain import Project, ReceiverSpec
from .map_picker import open_coordinate_picker
from .modes import MODE_PROFILES, threshold_dbm
from .project_editor import (
    ProjectEditorValues,
    TerminalEditorValues,
    editor_values_from_project,
    project_from_editor_values,
    project_slug,
    write_project_json,
)
from .project_files import read_coverage_project, write_coverage_project
from .report_server import open_report_in_browser
from .version import __version__

RESOLUTION_LABEL_TO_PRESET = {
    "Rápida": "quick",
    "Recomendada": "recommended",
    "Detalhada": "detailed",
    "Personalizada": "custom",
}


class RadioLinkPlannerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_outcome: AnalysisOutcome | None = None
        self.last_coverage: CoverageOutcome | None = None
        self.loaded_project: Project | None = None
        self.loaded_terrain_path: Path | None = None
        self.link_project_path: Path | None = None
        self.coverage_project_path: Path | None = None
        self.form_widgets: list[tk.Widget] = []
        self.current_mode: str | None = None
        self.coverage_cancel_event: threading.Event | None = None
        self.home_images: list[tk.PhotoImage] = []

        self.name_var = tk.StringVar()
        self.frequency_var = tk.StringVar()
        self.mode_var = tk.StringVar()
        self.polarization_var = tk.StringVar()
        self.availability_var = tk.StringVar()
        self.terminal_vars = {
            "a": self._new_terminal_vars(),
            "b": self._new_terminal_vars(),
        }
        self.output_var = tk.StringVar(value=str(default_output_directory()))
        self.runs_var = tk.StringVar(value="20000")
        self.plots_var = tk.BooleanVar(value=True)
        self.distance_var = tk.StringVar(value="Distância: —")
        self.terrain_status_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Carregando o caso de referência…")
        self.coverage_vars = {
            "name": tk.StringVar(value="Minha cobertura"),
            "latitude": tk.StringVar(),
            "longitude": tk.StringVar(),
            "frequency": tk.StringVar(value="146.000"),
            "polarization": tk.StringVar(value="Vertical"),
            "mode": tk.StringVar(value="FM"),
            "radius": tk.StringVar(value="50"),
            "resolution_preset": tk.StringVar(value="Recomendada"),
            "custom_resolution": tk.StringVar(value="500"),
            "time_percentage": tk.StringVar(value="50"),
            "tx_height": tk.StringVar(value="30"),
            "tx_gain": tk.StringVar(value="6"),
            "tx_line_loss": tk.StringVar(value="1"),
            "tx_power": tk.StringVar(value="50"),
            "rx_height": tk.StringVar(value="2"),
            "rx_gain": tk.StringVar(value="2"),
            "rx_line_loss": tk.StringVar(value="1"),
            "rx_sensitivity": tk.StringVar(value="-120"),
            "output": tk.StringVar(
                value=str(
                    Path.home()
                    / APP_NAME
                    / "Resultados"
                    / "Minha-cobertura"
                )
            ),
        }
        self.coverage_resolution_var = tk.StringVar()
        self.coverage_progress_var = tk.StringVar(
            value="Aguardando o início do cálculo."
        )

        self._configure_window()
        self._configure_styles()
        self._install_coordinate_traces()
        for variable in self.coverage_vars.values():
            variable.trace_add("write", self._coverage_radius_changed)
        self._coverage_radius_changed()
        self._show_start_screen()
        self.root.after(100, self._poll_events)

    @staticmethod
    def _new_terminal_vars() -> dict[str, tk.StringVar]:
        return {
            "name": tk.StringVar(),
            "latitude": tk.StringVar(),
            "longitude": tk.StringVar(),
            "height": tk.StringVar(),
            "gain": tk.StringVar(),
            "line_loss": tk.StringVar(),
            "power": tk.StringVar(),
            "sensitivity": tk.StringVar(),
        }

    def _configure_window(self) -> None:
        self.root.title(f"{APP_NAME} — {__version__}")
        icon_directory = bundle_root() / "assets"
        self.window_icons = [
            tk.PhotoImage(file=str(icon_directory / f"app-icon-{size}.png"))
            for size in (64, 32, 16)
        ]
        self.root.iconphoto(True, *self.window_icons)
        if sys.platform == "win32":
            self.root.iconbitmap(str(icon_directory / "app-icon.ico"))
        self._set_window_size(1280, 900, min_width=860, min_height=600)
        self.root.configure(background="#11151a")

    def _set_window_size(
        self,
        preferred_width: int,
        preferred_height: int,
        *,
        min_width: int,
        min_height: int,
    ) -> None:
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        available_width = max(640, screen_width - 80)
        available_height = max(480, screen_height - 100)
        width = min(preferred_width, available_width)
        height = min(preferred_height, available_height)
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(min(min_width, width), min(min_height, height))

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("App.TFrame", background="#11151a")
        style.configure("Panel.TFrame", background="#1a2027")
        style.configure("TNotebook", background="#11151a", borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background="#252d36",
            foreground="#cbd3db",
            padding=(18, 9),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#1a2027"), ("active", "#313b46")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Title.TLabel",
            background="#11151a",
            foreground="#f2f4f6",
            font=("Segoe UI Semibold", 22),
        )
        style.configure(
            "StartTitle.TLabel",
            background="#11151a",
            foreground="#f2f4f6",
            font=("Segoe UI Semibold", 30),
        )
        style.configure(
            "ModeTitle.TLabel",
            background="#1a2027",
            foreground="#f2f4f6",
            font=("Segoe UI Semibold", 17),
        )
        style.configure(
            "ModeText.TLabel",
            background="#1a2027",
            foreground="#aeb8c2",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Subtitle.TLabel",
            background="#11151a",
            foreground="#aeb8c2",
            font=("Segoe UI", 10),
        )
        style.configure(
            "PanelTitle.TLabel",
            background="#1a2027",
            foreground="#f2f4f6",
            font=("Segoe UI Semibold", 11),
        )
        style.configure("Panel.TLabel", background="#1a2027", foreground="#dce2e8")
        style.configure(
            "Hint.TLabel",
            background="#1a2027",
            foreground="#96a2ad",
            font=("Segoe UI", 9),
        )
        style.configure("Status.TLabel", background="#11151a", foreground="#aeb8c2")
        style.configure(
            "Panel.TLabelframe",
            background="#1a2027",
            bordercolor="#333e49",
            relief="solid",
        )
        style.configure(
            "Panel.TLabelframe.Label",
            background="#1a2027",
            foreground="#f2f4f6",
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "Accent.TButton",
            background="#d84a4a",
            foreground="#ffffff",
            padding=(18, 9),
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "Mode.TButton",
            background="#252d36",
            foreground="#ffffff",
            padding=(24, 13),
            font=("Segoe UI Semibold", 11),
        )
        style.map(
            "Mode.TButton",
            background=[("active", "#d84a4a")],
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#ec5a5a"), ("disabled", "#663737")],
        )
        style.configure("TButton", padding=(10, 7))
        style.configure(
            "TEntry",
            fieldbackground="#252d36",
            foreground="#f2f4f6",
            insertcolor="#f2f4f6",
            bordercolor="#36414c",
        )
        style.configure(
            "TCombobox",
            fieldbackground="#252d36",
            foreground="#f2f4f6",
            arrowcolor="#dce2e8",
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#252d36")],
            foreground=[("readonly", "#f2f4f6")],
            selectbackground=[("readonly", "#252d36")],
            selectforeground=[("readonly", "#f2f4f6")],
        )
        style.configure("TCheckbutton", background="#1a2027", foreground="#dce2e8")
        style.map(
            "TCheckbutton",
            background=[("active", "#1a2027")],
            foreground=[("disabled", "#6e7882")],
        )
        style.configure(
            "Horizontal.TProgressbar",
            background="#d84a4a",
            troughcolor="#252d36",
        )

    def _show_start_screen(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        self.current_mode = None
        self.form_widgets.clear()
        self.home_images.clear()
        self.root.unbind_all("<MouseWheel>")
        self.root.unbind_all("<Button-4>")
        self.root.unbind_all("<Button-5>")
        for child in self.root.winfo_children():
            child.destroy()
        self._set_window_size(1180, 760, min_width=900, min_height=600)

        outer = ttk.Frame(self.root, style="App.TFrame", padding=(54, 44))
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)
        ttk.Label(
            outer,
            text=APP_NAME,
            style="StartTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            outer,
            text=(
                "Planejamento científico local de enlaces e cobertura VHF/UHF"
            ),
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(5, 28))

        choices = ttk.Frame(outer, style="App.TFrame")
        choices.grid(row=2, column=0, sticky="nsew")
        choices.columnconfigure(0, weight=1)
        choices.columnconfigure(1, weight=1)
        choices.rowconfigure(0, weight=1)
        self._build_mode_card(
            choices,
            column=0,
            title="Enlace ponto a ponto",
            description=(
                "Compare ITM, P.1812 e P.2001, visualize o perfil do terreno "
                "e estime a confiabilidade por Monte Carlo."
            ),
            button_text="Planejar enlace",
            command=lambda: self._open_mode("link"),
            padding=(0, 10),
            image_asset="assets/home-link.png",
        )
        self._build_mode_card(
            choices,
            column=1,
            title="Mapa de cobertura",
            description=(
                "Calcule cada célula da cobertura P.1812 em grade métrica, "
                "com progresso real, retomada e contornos de margem."
            ),
            button_text="Calcular cobertura",
            command=lambda: self._open_mode("coverage"),
            padding=(10, 0),
            image_asset="assets/home-coverage.png",
        )
        ttk.Label(
            outer,
            text=(
                f"v{__version__} • processamento local • terreno Copernicus GLO-30"
            ),
            style="Subtitle.TLabel",
        ).grid(row=3, column=0, sticky="w", pady=(24, 0))

    def _build_mode_card(
        self,
        parent: ttk.Frame,
        *,
        column: int,
        title: str,
        description: str,
        button_text: str,
        command,
        padding: tuple[int, int],
        image_asset: str,
    ) -> None:
        card = ttk.Frame(parent, style="Panel.TFrame", padding=(24, 24))
        card.grid(row=0, column=column, sticky="nsew", padx=padding)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)
        image_path = bundle_root() / image_asset
        encoded_image_path = image_path.with_suffix(
            f"{image_path.suffix}.b64"
        )
        if image_path.is_file() or encoded_image_path.is_file():
            if image_path.is_file():
                source = tk.PhotoImage(file=str(image_path))
            else:
                source = tk.PhotoImage(
                    data=encoded_image_path.read_text(encoding="ascii")
                )
            photo = source.subsample(2, 2)
            self.home_images.append(photo)
            image_label = tk.Label(
                card,
                image=photo,
                background="#f4f5f6",
                borderwidth=0,
                cursor="hand2",
            )
            image_label.grid(row=0, column=0, sticky="n", pady=(0, 18))
            image_label.bind("<Button-1>", lambda _event: command())
        ttk.Label(card, text=title, style="ModeTitle.TLabel").grid(
            row=1, column=0, sticky="w"
        )
        ttk.Label(
            card,
            text=description,
            style="ModeText.TLabel",
            wraplength=350,
            justify="left",
        ).grid(row=2, column=0, sticky="nw", pady=(10, 18))
        ttk.Button(
            card,
            text=button_text,
            command=command,
            style="Mode.TButton",
        ).grid(row=3, column=0, sticky="ew")

    def _open_mode(self, mode: str) -> None:
        self.root.unbind_all("<MouseWheel>")
        self.root.unbind_all("<Button-4>")
        self.root.unbind_all("<Button-5>")
        for child in self.root.winfo_children():
            child.destroy()
        self.form_widgets.clear()
        self.current_mode = mode
        self._set_window_size(1280, 900, min_width=860, min_height=600)
        if mode == "link":
            self.status_var.set("Configure o enlace ou abra um projeto salvo.")
            self._build_layout()
            if self.loaded_project is None:
                self._load_project_file(bundled_example_path(), announce=False)
        elif mode == "coverage":
            self.status_var.set(
                "Configure o transmissor, o receptor de referência e o raio."
            )
            self._build_coverage_layout()
        else:
            raise ValueError(f"unknown application mode: {mode}")

    def _build_scrollable_content(self, parent: ttk.Frame) -> ttk.Frame:
        """Create a vertically scrollable form that still expands when space permits."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        canvas = tk.Canvas(
            parent,
            background="#1a2027",
            borderwidth=0,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        content = ttk.Frame(
            canvas,
            style="Panel.TFrame",
            padding=18,
        )
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scroll_region(_event: tk.Event[tk.Misc] | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_content(event: tk.Event[tk.Misc]) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        def on_mousewheel(event: tk.Event[tk.Misc]) -> str:
            widget: tk.Misc | None = event.widget
            while widget is not None and widget not in (content, canvas):
                parent_name = widget.winfo_parent()
                widget = (
                    widget.nametowidget(parent_name)
                    if parent_name
                    else None
                )
            if widget is None:
                return ""
            delta = int(getattr(event, "delta", 0))
            if delta:
                canvas.yview_scroll(-1 * int(delta / 120), "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(3, "units")
            return "break"

        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", resize_content)
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        canvas.bind_all("<Button-4>", on_mousewheel)
        canvas.bind_all("<Button-5>", on_mousewheel)
        return content

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=(24, 20))
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text=(
                "Planejamento científico local de enlaces VHF/UHF "
                "• ITM • P.1812 • P.2001 • Monte Carlo"
            ),
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Label(
            header,
            text=f"v{__version__}",
            style="Subtitle.TLabel",
        ).grid(row=0, column=2, rowspan=2, sticky="e")
        home_button = ttk.Button(
            header,
            text="Início",
            command=self._show_start_screen,
        )
        home_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 14))
        self._register(home_button)
        header.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(outer)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        self.editor_tab = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.results_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=18)
        self.notebook.add(self.editor_tab, text="Configurar enlace")
        self.notebook.add(self.results_tab, text="Análise e resultados")
        self._build_editor_tab()
        self._build_results_tab()

        footer = ttk.Frame(outer, style="App.TFrame")
        footer.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.analyze_button = ttk.Button(
            footer,
            text="Obter terreno e analisar",
            command=self._start_analysis,
            style="Accent.TButton",
        )
        self.analyze_button.grid(row=0, column=1, sticky="e")

    def _build_editor_tab(self) -> None:
        tab = self._build_scrollable_content(self.editor_tab)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        general = ttk.Frame(tab, style="Panel.TFrame")
        general.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        for column in (1, 3, 5):
            general.columnconfigure(column, weight=1)
        ttk.Label(general, text="Nome do enlace", style="Panel.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=5
        )
        name_entry = ttk.Entry(general, textvariable=self.name_var)
        name_entry.grid(row=0, column=1, columnspan=3, sticky="ew", pady=5)
        self._register(name_entry)
        ttk.Label(general, text="Frequência (MHz)", style="Panel.TLabel").grid(
            row=0, column=4, sticky="w", padx=(20, 8), pady=5
        )
        frequency_entry = ttk.Entry(general, textvariable=self.frequency_var, width=14)
        frequency_entry.grid(row=0, column=5, sticky="ew", pady=5)
        self._register(frequency_entry)

        ttk.Label(general, text="Modo", style="Panel.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=5
        )
        self.mode_combo = ttk.Combobox(
            general,
            textvariable=self.mode_var,
            values=tuple(MODE_PROFILES),
            state="readonly",
            width=15,
        )
        self.mode_combo.grid(row=1, column=1, sticky="ew", pady=5)
        self.mode_combo.bind("<<ComboboxSelected>>", self._mode_changed)
        self._register(self.mode_combo)
        ttk.Label(general, text="Polarização", style="Panel.TLabel").grid(
            row=1, column=2, sticky="w", padx=(20, 8), pady=5
        )
        polarization_combo = ttk.Combobox(
            general,
            textvariable=self.polarization_var,
            values=("Vertical", "Horizontal"),
            state="readonly",
            width=15,
        )
        polarization_combo.grid(row=1, column=3, sticky="ew", pady=5)
        self._register(polarization_combo)
        ttk.Label(general, text="Meta (%)", style="Panel.TLabel").grid(
            row=1, column=4, sticky="w", padx=(20, 8), pady=5
        )
        availability_entry = ttk.Entry(
            general, textvariable=self.availability_var, width=14
        )
        availability_entry.grid(row=1, column=5, sticky="ew", pady=5)
        self._register(availability_entry)

        terminals = ttk.Frame(tab, style="Panel.TFrame")
        terminals.grid(row=1, column=0, sticky="nsew")
        terminals.columnconfigure(0, weight=1)
        terminals.columnconfigure(1, weight=1)
        terminals.rowconfigure(0, weight=1)
        self._build_terminal_panel(
            terminals,
            column=0,
            title="Terminal A",
            variables=self.terminal_vars["a"],
            right_padding=8,
        )
        self._build_terminal_panel(
            terminals,
            column=1,
            title="Terminal B",
            variables=self.terminal_vars["b"],
            left_padding=8,
        )

        information = ttk.Frame(tab, style="Panel.TFrame")
        information.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        information.columnconfigure(0, weight=1)
        ttk.Label(
            information, textvariable=self.terrain_status_var, style="Hint.TLabel"
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            information, textvariable=self.distance_var, style="Hint.TLabel"
        ).grid(row=0, column=1, sticky="e", padx=(16, 0))

        actions = ttk.Frame(tab, style="Panel.TFrame")
        actions.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        actions.columnconfigure(4, weight=1)
        new_button = ttk.Button(actions, text="Novo projeto", command=self._new_link)
        new_button.grid(row=0, column=0, padx=(0, 6))
        self._register(new_button)
        open_button = ttk.Button(
            actions, text="Abrir projeto…", command=self._select_project
        )
        open_button.grid(row=0, column=1, padx=6)
        self._register(open_button)
        save_button = ttk.Button(
            actions,
            text="Salvar projeto…",
            command=self._save_link_project,
        )
        save_button.grid(row=0, column=2, padx=6)
        self._register(save_button)
        restore_button = ttk.Button(
            actions,
            text="Restaurar caso de referência",
            command=lambda: self._load_project_file(
                bundled_example_path(), announce=True
            ),
        )
        restore_button.grid(row=0, column=3, padx=6)
        self._register(restore_button)

    def _build_terminal_panel(
        self,
        parent: ttk.Frame,
        *,
        column: int,
        title: str,
        variables: dict[str, tk.StringVar],
        left_padding: int = 0,
        right_padding: int = 0,
    ) -> None:
        panel = ttk.LabelFrame(
            parent,
            text=title,
            style="Panel.TLabelframe",
            padding=14,
        )
        panel.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=(left_padding, right_padding),
        )
        panel.columnconfigure(1, weight=1)
        fields = (
            ("Nome", "name"),
            ("Latitude (°)", "latitude"),
            ("Longitude (°)", "longitude"),
            ("Altura da antena (m)", "height"),
            ("Ganho da antena (dBi)", "gain"),
            ("Perda no cabo (dB)", "line_loss"),
            ("Potência TX (W)", "power"),
            ("Sensibilidade RX (dBm)", "sensitivity"),
        )
        for row, (label, key) in enumerate(fields):
            ttk.Label(panel, text=label, style="Panel.TLabel").grid(
                row=row, column=0, sticky="w", padx=(0, 10), pady=4
            )
            entry = ttk.Entry(panel, textvariable=variables[key])
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            self._register(entry)
        map_button = ttk.Button(
            panel,
            text="Escolher coordenadas no mapa…",
            command=lambda: self._pick_coordinates(
                variables["latitude"],
                variables["longitude"],
                title,
            ),
        )
        map_button.grid(
            row=len(fields),
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(9, 2),
        )
        self._register(map_button)
        ttk.Label(
            panel,
            text="Altura sobre o solo; ganhos em dBi e perdas positivas.",
            style="Hint.TLabel",
        ).grid(row=len(fields) + 1, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_coverage_layout(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=(24, 20))
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text=(
                "Cobertura VHF/UHF • P.1812 • grade métrica direta • "
                "mapa de calor e contornos"
            ),
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        home_button = ttk.Button(
            header,
            text="Início",
            command=self._show_start_screen,
        )
        home_button.grid(row=0, column=1, rowspan=2, padx=(12, 14))
        self._register(home_button)
        ttk.Label(
            header,
            text=f"v{__version__}",
            style="Subtitle.TLabel",
        ).grid(row=0, column=2, rowspan=2, sticky="e")

        self.notebook = ttk.Notebook(outer)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        self.editor_tab = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.results_tab = ttk.Frame(
            self.notebook,
            style="Panel.TFrame",
            padding=18,
        )
        self.notebook.add(self.editor_tab, text="Configurar cobertura")
        self.notebook.add(self.results_tab, text="Mapa e resultados")
        self._build_coverage_editor_tab()
        self._build_coverage_results_tab()

        footer = ttk.Frame(outer, style="App.TFrame")
        footer.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(
            footer,
            textvariable=self.status_var,
            style="Status.TLabel",
        ).grid(row=0, column=0, sticky="w")
        self.analyze_button = ttk.Button(
            footer,
            text="Calcular cobertura",
            command=self._start_coverage_analysis,
            style="Accent.TButton",
        )
        self.cancel_button = ttk.Button(
            footer,
            text="Cancelar",
            command=self._cancel_coverage,
            state="disabled",
        )
        self.cancel_button.grid(row=0, column=1, sticky="e", padx=(0, 8))
        self.analyze_button.grid(row=0, column=2, sticky="e")

    def _build_coverage_editor_tab(self) -> None:
        tab = self._build_scrollable_content(self.editor_tab)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        variables = self.coverage_vars

        general = ttk.Frame(tab, style="Panel.TFrame")
        general.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        for column in (1, 3, 5):
            general.columnconfigure(column, weight=1)
        self._coverage_field(
            general,
            row=0,
            label="Nome da cobertura",
            variable=variables["name"],
            label_column=0,
            entry_column=1,
            columnspan=3,
        )
        self._coverage_field(
            general,
            row=0,
            label="Frequência (MHz)",
            variable=variables["frequency"],
            label_column=4,
            entry_column=5,
            left_padding=20,
        )
        ttk.Label(general, text="Modo", style="Panel.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=5
        )
        mode_combo = ttk.Combobox(
            general,
            textvariable=variables["mode"],
            values=tuple(MODE_PROFILES),
            state="readonly",
        )
        mode_combo.grid(row=1, column=1, sticky="ew", pady=5)
        mode_combo.bind("<<ComboboxSelected>>", self._coverage_mode_changed)
        self._register(mode_combo)
        ttk.Label(general, text="Polarização", style="Panel.TLabel").grid(
            row=1, column=2, sticky="w", padx=(20, 8), pady=5
        )
        polarization_combo = ttk.Combobox(
            general,
            textvariable=variables["polarization"],
            values=("Vertical", "Horizontal"),
            state="readonly",
        )
        polarization_combo.grid(row=1, column=3, sticky="ew", pady=5)
        self._register(polarization_combo)
        ttk.Label(general, text="Tempo P.1812 (%)", style="Panel.TLabel").grid(
            row=1, column=4, sticky="w", padx=(20, 8), pady=5
        )
        time_combo = ttk.Combobox(
            general,
            textvariable=variables["time_percentage"],
            values=("1", "10", "20", "50"),
            state="readonly",
        )
        time_combo.grid(row=1, column=5, sticky="ew", pady=5)
        self._register(time_combo)

        location = ttk.LabelFrame(
            tab,
            text="Local e extensão",
            style="Panel.TLabelframe",
            padding=12,
        )
        location.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        for column in (1, 3, 5):
            location.columnconfigure(column, weight=1)
        self._coverage_field(
            location,
            row=0,
            label="Latitude (°)",
            variable=variables["latitude"],
            label_column=0,
            entry_column=1,
        )
        self._coverage_field(
            location,
            row=0,
            label="Longitude (°)",
            variable=variables["longitude"],
            label_column=2,
            entry_column=3,
            left_padding=16,
        )
        map_button = ttk.Button(
            location,
            text="Escolher no mapa…",
            command=lambda: self._pick_coordinates(
                variables["latitude"],
                variables["longitude"],
                "Transmissor da cobertura",
            ),
        )
        map_button.grid(row=0, column=4, padx=(16, 8), pady=5)
        self._register(map_button)
        radius_combo = ttk.Combobox(
            location,
            textvariable=variables["radius"],
            values=tuple(str(value) for value in COVERAGE_RESOLUTION_M),
            state="readonly",
            width=8,
        )
        radius_combo.grid(row=0, column=5, sticky="ew", pady=5)
        self._register(radius_combo)
        ttk.Label(
            location,
            text="Raio (km)",
            style="Hint.TLabel",
        ).grid(row=1, column=5, sticky="w")
        ttk.Label(
            location,
            text="Resolução",
            style="Panel.TLabel",
        ).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 5))
        resolution_combo = ttk.Combobox(
            location,
            textvariable=variables["resolution_preset"],
            values=tuple(RESOLUTION_LABEL_TO_PRESET),
            state="readonly",
            width=16,
        )
        resolution_combo.grid(
            row=1,
            column=1,
            sticky="ew",
            pady=(8, 5),
        )
        self._register(resolution_combo)
        ttk.Label(
            location,
            text="Personalizada (m)",
            style="Panel.TLabel",
        ).grid(
            row=1,
            column=2,
            sticky="w",
            padx=(16, 8),
            pady=(8, 5),
        )
        self.custom_resolution_entry = ttk.Entry(
            location,
            textvariable=variables["custom_resolution"],
        )
        self.custom_resolution_entry.grid(
            row=1,
            column=3,
            sticky="ew",
            pady=(8, 5),
        )
        self._register(self.custom_resolution_entry)
        ttk.Label(
            location,
            textvariable=self.coverage_resolution_var,
            style="Hint.TLabel",
            wraplength=900,
        ).grid(
            row=2,
            column=0,
            columnspan=6,
            sticky="w",
            pady=(4, 0),
        )

        equipment = ttk.Frame(tab, style="Panel.TFrame")
        equipment.grid(row=2, column=0, sticky="nsew")
        equipment.columnconfigure(0, weight=1)
        equipment.columnconfigure(1, weight=1)
        equipment.rowconfigure(0, weight=1)
        transmitter = ttk.LabelFrame(
            equipment,
            text="Transmissor",
            style="Panel.TLabelframe",
            padding=14,
        )
        transmitter.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        receiver = ttk.LabelFrame(
            equipment,
            text="Receptor de referência",
            style="Panel.TLabelframe",
            padding=14,
        )
        receiver.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        for panel in (transmitter, receiver):
            panel.columnconfigure(1, weight=1)
        for row, (label, key) in enumerate(
            (
                ("Altura da antena (m)", "tx_height"),
                ("Ganho da antena (dBi)", "tx_gain"),
                ("Perda no cabo (dB)", "tx_line_loss"),
                ("Potência TX (W)", "tx_power"),
            )
        ):
            self._coverage_panel_field(
                transmitter, row, label, variables[key]
            )
        for row, (label, key) in enumerate(
            (
                ("Altura da antena (m)", "rx_height"),
                ("Ganho da antena (dBi)", "rx_gain"),
                ("Perda no cabo (dB)", "rx_line_loss"),
                ("Sensibilidade RX (dBm)", "rx_sensitivity"),
            )
        ):
            self._coverage_panel_field(receiver, row, label, variables[key])
        ttk.Label(
            receiver,
            text=(
                "Os mesmos parâmetros receptores são aplicados a todas as "
                "células do mapa."
            ),
            style="Hint.TLabel",
            wraplength=420,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        output = ttk.Frame(tab, style="Panel.TFrame")
        output.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        output.columnconfigure(1, weight=1)
        ttk.Label(output, text="Pasta de saída", style="Panel.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        output_entry = ttk.Entry(output, textvariable=variables["output"])
        output_entry.grid(row=0, column=1, sticky="ew")
        self._register(output_entry)
        output_button = ttk.Button(
            output,
            text="Selecionar…",
            command=self._select_coverage_output,
        )
        output_button.grid(row=0, column=2, padx=(8, 0))
        self._register(output_button)

        project_actions = ttk.Frame(tab, style="Panel.TFrame")
        project_actions.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        project_actions.columnconfigure(3, weight=1)
        new_button = ttk.Button(
            project_actions,
            text="Novo projeto",
            command=self._new_coverage,
        )
        new_button.grid(row=0, column=0, padx=(0, 6))
        self._register(new_button)
        open_button = ttk.Button(
            project_actions,
            text="Abrir projeto…",
            command=self._select_coverage_project,
        )
        open_button.grid(row=0, column=1, padx=6)
        self._register(open_button)
        save_button = ttk.Button(
            project_actions,
            text="Salvar projeto…",
            command=self._save_coverage_project,
        )
        save_button.grid(row=0, column=2, padx=6)
        self._register(save_button)
        self._coverage_radius_changed()

    def _coverage_field(
        self,
        parent: ttk.Frame,
        *,
        row: int,
        label: str,
        variable: tk.StringVar,
        label_column: int,
        entry_column: int,
        columnspan: int = 1,
        left_padding: int = 0,
    ) -> None:
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(
            row=row,
            column=label_column,
            sticky="w",
            padx=(left_padding, 8),
            pady=5,
        )
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(
            row=row,
            column=entry_column,
            columnspan=columnspan,
            sticky="ew",
            pady=5,
        )
        self._register(entry)

    def _coverage_panel_field(
        self,
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=5
        )
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        self._register(entry)

    def _build_coverage_results_tab(self) -> None:
        tab = self.results_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        header = ttk.Frame(tab, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Resultado", style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        actions = ttk.Frame(header, style="Panel.TFrame")
        actions.grid(row=0, column=1, sticky="e")
        self.report_button = ttk.Button(
            actions,
            text="Abrir mapa interativo",
            command=self._open_report,
            state="disabled",
        )
        self.report_button.grid(row=0, column=0, padx=(0, 6))
        self.pdf_button = ttk.Button(
            actions,
            text="Abrir relatório PDF",
            command=self._open_pdf_report,
            state="disabled",
        )
        self.pdf_button.grid(row=0, column=1, padx=6)
        self.profile_button = ttk.Button(
            actions,
            text="Abrir mapa técnico",
            command=self._open_heatmap,
            state="disabled",
        )
        self.profile_button.grid(row=0, column=2, padx=6)
        self.folder_button = ttk.Button(
            actions,
            text="Abrir pasta",
            command=self._open_output_directory,
            state="disabled",
        )
        self.folder_button.grid(row=0, column=3, padx=(6, 0))

        body = ttk.Frame(tab, style="Panel.TFrame")
        body.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)
        ttk.Label(
            body,
            textvariable=self.coverage_progress_var,
            style="Panel.TLabel",
            wraplength=980,
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.progress = ttk.Progressbar(
            body,
            mode="determinate",
            maximum=100.0,
            value=0.0,
        )
        self.progress.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.result_text = tk.Text(
            body,
            wrap="word",
            relief="flat",
            borderwidth=0,
            background="#12171d",
            foreground="#dce2e8",
            insertbackground="#f2f4f6",
            selectbackground="#485564",
            font=("Cascadia Mono", 10),
            padx=14,
            pady=12,
        )
        self.result_text.grid(row=2, column=0, sticky="nsew")
        self._set_result_text(
            "Configure a estação transmissora e o receptor de referência.\n\n"
            "A cobertura usa P.1812 e terreno Copernicus GLO-30. Cada célula "
            "da grade recebe seu próprio perfil e cálculo; não há "
            "interpolação de propagação entre radiais."
        )

    def _build_results_tab(self) -> None:
        tab = self.results_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        controls = ttk.Frame(tab, style="Panel.TFrame")
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="Pasta de saída", style="Panel.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=4
        )
        self.output_entry = ttk.Entry(controls, textvariable=self.output_var)
        self.output_entry.grid(row=0, column=1, sticky="ew", pady=4)
        self._register(self.output_entry)
        output_button = ttk.Button(
            controls, text="Selecionar…", command=self._select_output
        )
        output_button.grid(row=0, column=2, padx=(8, 0), pady=4)
        self._register(output_button)
        ttk.Label(controls, text="Monte Carlo", style="Panel.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=4
        )
        options = ttk.Frame(controls, style="Panel.TFrame")
        options.grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)
        self.runs_combo = ttk.Combobox(
            options,
            textvariable=self.runs_var,
            values=("500", "2000", "5000", "20000", "50000"),
            state="readonly",
            width=10,
        )
        self.runs_combo.grid(row=0, column=0, sticky="w")
        self._register(self.runs_combo)
        ttk.Label(options, text="execuções", style="Panel.TLabel").grid(
            row=0, column=1, sticky="w", padx=(6, 22)
        )
        self.plots_check = ttk.Checkbutton(
            options,
            text="Gerar perfil técnico e gráficos",
            variable=self.plots_var,
        )
        self.plots_check.grid(row=0, column=2, sticky="w")
        self._register(self.plots_check)

        result_header = ttk.Frame(tab, style="Panel.TFrame")
        result_header.grid(row=1, column=0, sticky="ew")
        result_header.columnconfigure(0, weight=1)
        ttk.Label(result_header, text="Resultado", style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        actions = ttk.Frame(result_header, style="Panel.TFrame")
        actions.grid(row=0, column=1, sticky="e")
        self.report_button = ttk.Button(
            actions,
            text="Mapa e relatório",
            command=self._open_report,
            state="disabled",
        )
        self.report_button.grid(row=0, column=0, padx=(0, 6))
        self.pdf_button = ttk.Button(
            actions,
            text="Abrir relatório PDF",
            command=self._open_pdf_report,
            state="disabled",
        )
        self.pdf_button.grid(row=0, column=1, padx=6)
        self.profile_button = ttk.Button(
            actions,
            text="Abrir perfil",
            command=self._open_profile,
            state="disabled",
        )
        self.profile_button.grid(row=0, column=2, padx=6)
        self.folder_button = ttk.Button(
            actions,
            text="Abrir pasta",
            command=self._open_output_directory,
            state="disabled",
        )
        self.folder_button.grid(row=0, column=3, padx=(6, 0))

        body = ttk.Frame(tab, style="Panel.TFrame")
        body.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.result_text = tk.Text(
            body,
            wrap="word",
            relief="flat",
            borderwidth=0,
            background="#12171d",
            foreground="#dce2e8",
            insertbackground="#f2f4f6",
            selectbackground="#485564",
            font=("Cascadia Mono", 10),
            padx=14,
            pady=12,
        )
        self.result_text.grid(row=1, column=0, sticky="nsew")
        self._set_result_text(
            "Configure os dois terminais na primeira aba.\n\n"
            "Ao analisar um enlace novo, o programa baixa apenas os blocos "
            "Copernicus GLO-30 necessários e os mantém em cache. O relatório "
            "inclui mapa interativo, perfil técnico, modelos e Monte Carlo."
        )

    def _register(self, widget: tk.Widget) -> None:
        self.form_widgets.append(widget)

    def _install_coordinate_traces(self) -> None:
        for terminal in self.terminal_vars.values():
            terminal["latitude"].trace_add("write", self._coordinates_changed)
            terminal["longitude"].trace_add("write", self._coordinates_changed)

    def _coordinates_changed(self, *_: object) -> None:
        try:
            values = self._coordinate_tuple()
            from .geodesy import great_circle_distance_m

            distance = great_circle_distance_m(*values) / 1000.0
            self.distance_var.set(f"Distância: {distance:.2f} km")
        except ValueError:
            self.distance_var.set("Distância: —")
        if self._can_reuse_loaded_terrain():
            self.terrain_status_var.set(
                "Terreno: o perfil rastreável do projeto carregado será reutilizado."
            )
        else:
            self.terrain_status_var.set(
                "Terreno: Copernicus GLO-30 automático; internet só para blocos "
                "ainda ausentes do cache."
            )

    def _pick_coordinates(
        self,
        latitude_var: tk.StringVar,
        longitude_var: tk.StringVar,
        title: str,
    ) -> None:
        try:
            initial_latitude = self._parse_float(
                latitude_var.get(),
                "Latitude",
            )
            initial_longitude = self._parse_float(
                longitude_var.get(),
                "Longitude",
            )
        except ValueError:
            initial_latitude = None
            initial_longitude = None

        def selected(latitude: float, longitude: float) -> None:
            def apply_selection() -> None:
                latitude_var.set(f"{latitude:.8f}")
                longitude_var.set(f"{longitude:.8f}")
                self.status_var.set(
                    f"Coordenadas escolhidas no mapa: "
                    f"{latitude:.6f}, {longitude:.6f}."
                )

            self.root.after(0, apply_selection)

        try:
            picker = open_coordinate_picker(
                title=f"Escolher local — {title}",
                initial_latitude=initial_latitude,
                initial_longitude=initial_longitude,
                on_selected=selected,
            )
            if getattr(picker, "display_mode", "browser") == "embedded":
                self.status_var.set(
                    "O mapa foi aberto em uma janela do programa. "
                    "Clique no local e confirme."
                )
            else:
                self.status_var.set(
                    "O mapa foi aberto no navegador porque o componente interno "
                    "não está disponível. Clique no local e confirme."
                )
        except Exception as exc:  # noqa: BLE001 - browser integration boundary
            messagebox.showerror(
                APP_NAME,
                f"Não foi possível abrir o seletor de mapa.\n\n{exc}",
            )

    def _coverage_radius_changed(self, *_: object) -> None:
        preset_label = self.coverage_vars["resolution_preset"].get()
        preset = RESOLUTION_LABEL_TO_PRESET.get(preset_label)
        if (
            hasattr(self, "custom_resolution_entry")
            and self.custom_resolution_entry.winfo_exists()
        ):
            self.custom_resolution_entry.configure(
                state="normal" if preset == "custom" else "disabled"
            )
        try:
            request = self._collect_coverage_request(for_estimate=True)
            estimate = estimate_coverage(request)
        except Exception as exc:  # noqa: BLE001 - live form estimate
            self.coverage_resolution_var.set(str(exc))
            return
        resume = (
            " • perda de propagação pronta: atualização sem recalcular a P.1812"
            if estimate.reusable_propagation_cells
            else
            f" • retomada disponível: {estimate.resumable_cells:,} células"
            if estimate.resumable_cells
            else ""
        )
        terrain = (
            f" • {estimate.uncached_terrain_tile_count} bloco(s) de terreno "
            "a baixar"
            if estimate.uncached_terrain_tile_count
            else " • terreno já disponível em cache"
        )
        self.coverage_resolution_var.set(
            f"Célula: {estimate.resolution_m} m • grade "
            f"{estimate.grid_width:,} × {estimate.grid_height:,} • "
            f"{estimate.valid_circle_cells:,} cálculos • previsão inicial "
            f"{format_duration(estimate.estimated_seconds_low)}–"
            f"{format_duration(estimate.estimated_seconds_high)} • "
            f"memória ~{estimate.estimated_memory_mb:,.0f} MB"
            f"{terrain}{resume}."
        )

    def _coverage_mode_changed(self, _: tk.Event[tk.Misc]) -> None:
        mode = self.coverage_vars["mode"].get()
        if mode not in MODE_PROFILES:
            return
        default, _ = threshold_dbm(ReceiverSpec(), mode)
        self.coverage_vars["rx_sensitivity"].set(f"{default:.2f}")

    def _coordinate_tuple(self) -> tuple[float, float, float, float]:
        terminal_a = self.terminal_vars["a"]
        terminal_b = self.terminal_vars["b"]
        return (
            self._parse_float(terminal_a["latitude"].get(), "Latitude A"),
            self._parse_float(terminal_a["longitude"].get(), "Longitude A"),
            self._parse_float(terminal_b["latitude"].get(), "Latitude B"),
            self._parse_float(terminal_b["longitude"].get(), "Longitude B"),
        )

    def _can_reuse_loaded_terrain(self) -> bool:
        if (
            self.loaded_project is None
            or self.loaded_terrain_path is None
            or not self.loaded_terrain_path.is_file()
        ):
            return False
        try:
            current = self._coordinate_tuple()
        except ValueError:
            return False
        original = (
            self.loaded_project.terminal_a.latitude_deg,
            self.loaded_project.terminal_a.longitude_deg,
            self.loaded_project.terminal_b.latitude_deg,
            self.loaded_project.terminal_b.longitude_deg,
        )
        return all(abs(left - right) <= 1e-8 for left, right in zip(current, original))

    def _new_link(self) -> None:
        self.loaded_project = None
        self.loaded_terrain_path = None
        self.link_project_path = None
        self.name_var.set("Meu enlace")
        self.frequency_var.set("146.000")
        self.mode_var.set("FM")
        self.polarization_var.set("Vertical")
        self.availability_var.set("70")
        defaults = {
            "a": ("Estação A", "10", "2", "1", "50", "-120"),
            "b": ("Estação B", "10", "2", "1", "50", "-120"),
        }
        for key, values in defaults.items():
            variables = self.terminal_vars[key]
            variables["name"].set(values[0])
            variables["latitude"].set("")
            variables["longitude"].set("")
            variables["height"].set(values[1])
            variables["gain"].set(values[2])
            variables["line_loss"].set(values[3])
            variables["power"].set(values[4])
            variables["sensitivity"].set(values[5])
        self.output_var.set(str(Path.home() / APP_NAME / "Resultados" / "Meu-enlace"))
        self.last_outcome = None
        self._disable_result_actions()
        self.status_var.set("Novo enlace. Informe as coordenadas dos terminais.")
        self.notebook.select(self.editor_tab)

    def _save_link_project(self) -> None:
        try:
            values = self._collect_editor_values()
            project = project_from_editor_values(
                values,
                template=self.loaded_project,
            )
        except Exception as exc:  # noqa: BLE001 - form validation boundary
            messagebox.showerror(
                APP_NAME,
                f"Não foi possível salvar o projeto.\n\n{exc}",
            )
            return
        selected = filedialog.asksaveasfilename(
            title="Salvar projeto de enlace",
            defaultextension=".rlp",
            initialfile=f"{project_slug(project.name)}.rlp",
            filetypes=(
                ("Projeto Radio Link Planner", "*.rlp"),
                ("Projeto JSON", "*.json"),
                ("Todos os arquivos", "*.*"),
            ),
        )
        if not selected:
            return
        try:
            destination = write_project_json(project, selected)
        except Exception as exc:  # noqa: BLE001 - filesystem boundary
            messagebox.showerror(
                APP_NAME,
                f"Não foi possível salvar o projeto.\n\n{type(exc).__name__}: {exc}",
            )
            return
        self.loaded_project = project
        self.link_project_path = destination
        self.status_var.set(f"Projeto salvo: {destination.name}.")

    def _select_project(self) -> None:
        selected = filedialog.askopenfilename(
            title="Abrir projeto de enlace",
            filetypes=(
                ("Projeto Radio Link Planner", "*.rlp"),
                ("Projeto JSON", "*.json"),
                ("Todos os arquivos", "*.*"),
            ),
        )
        if selected:
            self._load_project_file(Path(selected), announce=True)

    def _load_project_file(self, path: Path, *, announce: bool) -> None:
        try:
            project, base_dir = Project.from_json(path)
            terrain_path = project.resolved_terrain_path(base_dir)
            values = editor_values_from_project(project)
        except Exception as exc:  # noqa: BLE001 - GUI boundary reports invalid files
            messagebox.showerror(
                APP_NAME,
                f"Não foi possível abrir o projeto.\n\n{type(exc).__name__}: {exc}",
            )
            return
        self.loaded_project = project
        self.link_project_path = path.resolve()
        self.loaded_terrain_path = terrain_path if terrain_path.is_file() else None
        self._apply_editor_values(values)
        output_name = project_slug(project.name)
        self.output_var.set(str(Path.home() / APP_NAME / "Resultados" / output_name))
        self.runs_var.set(str(project.monte_carlo.runs))
        self.last_outcome = None
        self._disable_result_actions()
        self._coordinates_changed()
        self.status_var.set(f"Projeto carregado: {project.name}.")
        self.notebook.select(self.editor_tab)
        if announce:
            messagebox.showinfo(
                APP_NAME,
                "Projeto carregado. Todos os campos podem ser editados antes "
                "da análise.",
            )

    def _new_coverage(self) -> None:
        defaults = {
            "name": "Minha cobertura",
            "latitude": "",
            "longitude": "",
            "frequency": "146.000",
            "polarization": "Vertical",
            "mode": "FM",
            "radius": "50",
            "resolution_preset": "Recomendada",
            "custom_resolution": "500",
            "time_percentage": "50",
            "tx_height": "30",
            "tx_gain": "6",
            "tx_line_loss": "1",
            "tx_power": "50",
            "rx_height": "2",
            "rx_gain": "2",
            "rx_line_loss": "1",
            "rx_sensitivity": "-120",
            "output": str(
                Path.home()
                / APP_NAME
                / "Resultados"
                / "Minha-cobertura"
            ),
        }
        for key, value in defaults.items():
            self.coverage_vars[key].set(value)
        self.coverage_project_path = None
        self.last_coverage = None
        self._disable_result_actions()
        self.progress.configure(value=0.0)
        self.coverage_progress_var.set("Aguardando o início do cálculo.")
        self.status_var.set(
            "Novo projeto de cobertura. Informe o local do transmissor."
        )
        self.notebook.select(self.editor_tab)

    def _save_coverage_project(self) -> None:
        name = self.coverage_vars["name"].get().strip()
        if not name:
            messagebox.showerror(
                APP_NAME,
                "Informe um nome para a cobertura antes de salvar.",
            )
            return
        selected = filedialog.asksaveasfilename(
            title="Salvar projeto de cobertura",
            defaultextension=".rlp",
            initialfile=f"{project_slug(name)}.rlp",
            filetypes=(
                ("Projeto Radio Link Planner", "*.rlp"),
                ("Todos os arquivos", "*.*"),
            ),
        )
        if not selected:
            return
        values = {
            key: variable.get()
            for key, variable in self.coverage_vars.items()
        }
        try:
            destination = write_coverage_project(values, selected)
        except Exception as exc:  # noqa: BLE001 - filesystem boundary
            messagebox.showerror(
                APP_NAME,
                f"Não foi possível salvar o projeto.\n\n{type(exc).__name__}: {exc}",
            )
            return
        self.coverage_project_path = destination
        self.status_var.set(f"Projeto salvo: {destination.name}.")

    def _select_coverage_project(self) -> None:
        selected = filedialog.askopenfilename(
            title="Abrir projeto de cobertura",
            filetypes=(
                ("Projeto Radio Link Planner", "*.rlp"),
                ("Todos os arquivos", "*.*"),
            ),
        )
        if not selected:
            return
        try:
            values = read_coverage_project(selected)
        except Exception as exc:  # noqa: BLE001 - invalid project boundary
            messagebox.showerror(
                APP_NAME,
                f"Não foi possível abrir o projeto.\n\n{type(exc).__name__}: {exc}",
            )
            return
        for key, value in values.items():
            self.coverage_vars[key].set(value)
        self.coverage_project_path = Path(selected).resolve()
        self.last_coverage = None
        self._disable_result_actions()
        self.status_var.set(
            f"Projeto de cobertura carregado: "
            f"{self.coverage_vars['name'].get()}."
        )
        self.notebook.select(self.editor_tab)

    def _apply_editor_values(self, values: ProjectEditorValues) -> None:
        self.name_var.set(values.name)
        self.frequency_var.set(f"{values.frequency_mhz:.6f}".rstrip("0").rstrip("."))
        self.mode_var.set(values.primary_mode)
        self.polarization_var.set(values.polarization.capitalize())
        self.availability_var.set(
            f"{values.target_availability_percent:.3f}".rstrip("0").rstrip(".")
        )
        self._apply_terminal_values("a", values.terminal_a)
        self._apply_terminal_values("b", values.terminal_b)

    def _apply_terminal_values(
        self, terminal_id: str, values: TerminalEditorValues
    ) -> None:
        variables = self.terminal_vars[terminal_id]
        variables["name"].set(values.name)
        variables["latitude"].set(f"{values.latitude_deg:.8f}")
        variables["longitude"].set(f"{values.longitude_deg:.8f}")
        variables["height"].set(self._format_number(values.antenna_height_m))
        variables["gain"].set(self._format_number(values.antenna_gain_dbi))
        variables["line_loss"].set(self._format_number(values.line_loss_db))
        variables["power"].set(self._format_number(values.tx_power_w))
        variables["sensitivity"].set(self._format_number(values.receiver_threshold_dbm))

    @staticmethod
    def _format_number(value: float) -> str:
        return f"{value:.6f}".rstrip("0").rstrip(".")

    def _mode_changed(self, _: tk.Event[tk.Misc]) -> None:
        mode = self.mode_var.get()
        if mode not in MODE_PROFILES:
            return
        default, _ = threshold_dbm(ReceiverSpec(), mode)
        for terminal in self.terminal_vars.values():
            terminal["sensitivity"].set(f"{default:.2f}")

    def _select_output(self) -> None:
        selected = filedialog.askdirectory(title="Selecionar pasta de saída")
        if selected:
            self.output_var.set(selected)

    def _select_coverage_output(self) -> None:
        selected = filedialog.askdirectory(
            title="Selecionar pasta da cobertura"
        )
        if selected:
            self.coverage_vars["output"].set(selected)

    def _collect_editor_values(self) -> ProjectEditorValues:
        def terminal(terminal_id: str, label: str) -> TerminalEditorValues:
            variables = self.terminal_vars[terminal_id]
            return TerminalEditorValues(
                name=variables["name"].get().strip(),
                latitude_deg=self._parse_float(
                    variables["latitude"].get(), f"Latitude {label}"
                ),
                longitude_deg=self._parse_float(
                    variables["longitude"].get(), f"Longitude {label}"
                ),
                antenna_height_m=self._parse_float(
                    variables["height"].get(), f"Altura da antena {label}"
                ),
                antenna_gain_dbi=self._parse_float(
                    variables["gain"].get(), f"Ganho da antena {label}"
                ),
                line_loss_db=self._parse_float(
                    variables["line_loss"].get(), f"Perda no cabo {label}"
                ),
                tx_power_w=self._parse_float(
                    variables["power"].get(), f"Potência TX {label}"
                ),
                receiver_threshold_dbm=self._parse_float(
                    variables["sensitivity"].get(), f"Sensibilidade RX {label}"
                ),
            )

        return ProjectEditorValues(
            name=self.name_var.get().strip(),
            frequency_mhz=self._parse_float(self.frequency_var.get(), "Frequência"),
            polarization=self.polarization_var.get().lower(),
            primary_mode=self.mode_var.get(),
            target_availability_percent=self._parse_float(
                self.availability_var.get(), "Meta de disponibilidade"
            ),
            terminal_a=terminal("a", "A"),
            terminal_b=terminal("b", "B"),
        )

    @staticmethod
    def _parse_float(value: str, label: str) -> float:
        cleaned = value.strip().replace(",", ".")
        if not cleaned:
            raise ValueError(f"Informe o campo “{label}”.")
        try:
            return float(cleaned)
        except ValueError as exc:
            raise ValueError(f"O campo “{label}” não é um número válido.") from exc

    def _start_analysis(self) -> None:
        try:
            values = self._collect_editor_values()
            project = project_from_editor_values(
                values,
                template=self.loaded_project,
            )
            output_text = self.output_var.get().strip()
            if not output_text:
                raise ValueError("Selecione uma pasta de saída.")
            output_directory = Path(output_text)
            runs = int(self.runs_var.get())
        except Exception as exc:  # noqa: BLE001 - GUI boundary reports form errors
            messagebox.showerror(APP_NAME, str(exc))
            self.notebook.select(self.editor_tab)
            return

        request = FormAnalysisRequest(
            project=project,
            output_directory=output_directory,
            monte_carlo_runs=runs,
            make_plots=self.plots_var.get(),
            existing_terrain_path=(
                self.loaded_terrain_path if self._can_reuse_loaded_terrain() else None
            ),
        )
        self._set_running(True)
        self.notebook.select(self.results_tab)
        self.status_var.set("Preparando o terreno e os modelos…")
        self._set_result_text(
            "Análise em andamento.\n\n"
            "O perfil Copernicus, os modelos de propagação e o Monte Carlo são "
            "executados localmente. A interface continuará responsiva."
        )
        self.worker = threading.Thread(
            target=self._analysis_worker,
            args=(request,),
            daemon=True,
        )
        self.worker.start()

    def _collect_coverage_request(
        self,
        *,
        for_estimate: bool = False,
    ) -> CoverageRequest:
        values = self.coverage_vars
        output_text = values["output"].get().strip()
        if not output_text:
            raise ValueError("Selecione uma pasta de saída.")
        latitude_text = values["latitude"].get().strip()
        longitude_text = values["longitude"].get().strip()
        if for_estimate:
            latitude_text = latitude_text or "0"
            longitude_text = longitude_text or "0"
        preset = RESOLUTION_LABEL_TO_PRESET.get(
            values["resolution_preset"].get()
        )
        if preset is None:
            raise ValueError("Escolha uma resolução de cobertura válida.")
        custom_resolution = None
        if preset == "custom":
            custom_resolution = int(values["custom_resolution"].get())
        request = CoverageRequest(
            name=values["name"].get().strip(),
            latitude_deg=self._parse_float(
                latitude_text,
                "Latitude",
            ),
            longitude_deg=self._parse_float(
                longitude_text,
                "Longitude",
            ),
            frequency_mhz=self._parse_float(
                values["frequency"].get(),
                "Frequência",
            ),
            polarization=values["polarization"].get().lower(),
            mode=values["mode"].get(),
            radius_km=int(values["radius"].get()),
            transmitter_height_m=self._parse_float(
                values["tx_height"].get(),
                "Altura da antena transmissora",
            ),
            transmitter_gain_dbi=self._parse_float(
                values["tx_gain"].get(),
                "Ganho da antena transmissora",
            ),
            transmitter_line_loss_db=self._parse_float(
                values["tx_line_loss"].get(),
                "Perda no cabo transmissor",
            ),
            transmitter_power_w=self._parse_float(
                values["tx_power"].get(),
                "Potência transmissora",
            ),
            receiver_height_m=self._parse_float(
                values["rx_height"].get(),
                "Altura da antena receptora",
            ),
            receiver_gain_dbi=self._parse_float(
                values["rx_gain"].get(),
                "Ganho da antena receptora",
            ),
            receiver_line_loss_db=self._parse_float(
                values["rx_line_loss"].get(),
                "Perda no cabo receptor",
            ),
            receiver_threshold_dbm=self._parse_float(
                values["rx_sensitivity"].get(),
                "Sensibilidade receptora",
            ),
            output_directory=Path(output_text),
            time_percentage=self._parse_float(
                values["time_percentage"].get(),
                "Percentual de tempo P.1812",
            ),
            resolution_preset=preset,
            custom_resolution_m=custom_resolution,
        )
        request.validate()
        return request

    def _start_coverage_analysis(self) -> None:
        try:
            request = self._collect_coverage_request()
            estimate = estimate_coverage(request)
        except Exception as exc:  # noqa: BLE001 - GUI boundary reports form errors
            messagebox.showerror(APP_NAME, str(exc))
            self.notebook.select(self.editor_tab)
            return
        if not self._confirm_coverage_estimate(estimate):
            return
        self.coverage_cancel_event = threading.Event()
        self._set_running(True)
        self.notebook.select(self.results_tab)
        self.status_var.set("Preparando terreno e P.1812…")
        self.coverage_progress_var.set(
            "0% — Preparando dados científicos e terreno."
        )
        self._set_result_text(
            "Cálculo de cobertura em andamento.\n\n"
            f"A grade possui {estimate.valid_circle_cells:,} células de "
            f"{estimate.resolution_m} m. Cada célula terá cálculo próprio; "
            "os blocos concluídos são salvos para permitir cancelamento e "
            "retomada."
        )
        self.worker = threading.Thread(
            target=self._coverage_worker,
            args=(request,),
            daemon=True,
        )
        self.worker.start()

    def _coverage_worker(self, request: CoverageRequest) -> None:
        try:
            outcome = run_coverage_analysis(
                request,
                progress=lambda state: self.events.put(
                    ("coverage_progress", state)
                ),
                cancel_event=self.coverage_cancel_event,
            )
            self.events.put(("coverage_success", outcome))
        except CoverageCancelled as exc:
            self.events.put(("coverage_cancelled", exc))
        except Exception as exc:  # noqa: BLE001 - worker must return every failure
            self.events.put(
                (
                    "error",
                    {
                        "message": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(),
                    },
                )
            )

    def _confirm_coverage_estimate(
        self,
        estimate: CoverageEstimate,
    ) -> bool:
        available = available_memory_bytes()
        required_bytes = estimate.estimated_memory_mb * 1024.0**2
        if available is not None and required_bytes > available * 0.95:
            messagebox.showerror(
                APP_NAME,
                "A configuração estimada excede a memória disponível.\n\n"
                f"Necessária: ~{estimate.estimated_memory_mb:,.0f} MB\n"
                f"Disponível: ~{available / 1024.0**2:,.0f} MB\n\n"
                "Escolha uma resolução mais espaçada.",
            )
            return False

        needs_confirmation = (
            estimate.warning_level != "normal"
            or (
                available is not None
                and required_bytes > available * 0.60
            )
        )
        if not needs_confirmation:
            return True
        severity = (
            "Esta combinação pode levar várias horas."
            if estimate.warning_level == "red"
            else "Esta combinação pode levar mais de 10 minutos."
        )
        resume_text = (
            "\n\nSerá retomada uma execução anterior com "
            f"{estimate.resumable_cells:,} células prontas."
            if estimate.resumable_cells
            else ""
        )
        return bool(
            messagebox.askyesno(
                APP_NAME,
                f"{severity}\n\n"
                f"Grade: {estimate.grid_width:,} × "
                f"{estimate.grid_height:,}\n"
                f"Células: {estimate.valid_circle_cells:,}\n"
                f"Tempo previsto: "
                f"{format_duration(estimate.estimated_seconds_low)}–"
                f"{format_duration(estimate.estimated_seconds_high)}\n"
                f"Memória prevista: "
                f"~{estimate.estimated_memory_mb:,.0f} MB\n"
                f"Processos de cálculo: {estimate.worker_count}"
                f"{resume_text}\n\nDeseja iniciar?",
                icon="warning",
            )
        )

    def _cancel_coverage(self) -> None:
        if self.coverage_cancel_event is None:
            return
        self.coverage_cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status_var.set(
            "Cancelamento solicitado; concluindo a célula atual e salvando…"
        )
        self.coverage_progress_var.set(
            "Cancelamento solicitado — preservando os blocos concluídos."
        )

    def _analysis_worker(self, request: FormAnalysisRequest) -> None:
        try:
            outcome = run_form_analysis(
                request,
                progress=lambda message: self.events.put(("progress", message)),
            )
            self.events.put(("success", outcome))
        except Exception as exc:  # noqa: BLE001 - worker must return every failure
            self.events.put(
                (
                    "error",
                    {
                        "message": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(),
                    },
                )
            )

    def _poll_events(self) -> None:
        terminal_event: tuple[str, object] | None = None
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "progress":
                self.status_var.set(str(payload))
            elif event == "coverage_progress":
                if not isinstance(payload, CoverageProgress):
                    continue
                self.progress.configure(value=payload.overall_percent)
                detail = (
                    f"{payload.message} • decorrido "
                    f"{format_duration(payload.elapsed_seconds)}"
                )
                if payload.remaining_seconds is not None:
                    detail += (
                        " • restante "
                        f"{format_duration(payload.remaining_seconds)}"
                    )
                self.coverage_progress_var.set(detail)
                self.status_var.set(payload.message)
            else:
                terminal_event = (event, payload)
        if terminal_event is not None:
            self._finish_analysis(*terminal_event)
        self.root.after(100, self._poll_events)

    def _finish_analysis(self, event: str, payload: object) -> None:
        self._set_running(False)
        self.worker = None
        if event == "success":
            if not isinstance(payload, AnalysisOutcome):
                raise TypeError("unexpected analysis result")
            self.last_outcome = payload
            self.loaded_project = payload.project
            terrain_path = payload.paths.get("terrain_profile")
            self.loaded_terrain_path = terrain_path if terrain_path else None
            self._set_result_text(build_desktop_summary(payload))
            self.status_var.set("Análise concluída: mapa, perfil e relatório gerados.")
            self.report_button.configure(state="normal")
            self.pdf_button.configure(
                state=(
                    "normal"
                    if payload.paths.get("report_pdf", Path()).is_file()
                    else "disabled"
                )
            )
            self.folder_button.configure(state="normal")
            self.profile_button.configure(
                state=(
                    "normal"
                    if payload.paths.get("profile_plot", Path()).is_file()
                    else "disabled"
                )
            )
            return
        if event == "coverage_success":
            if not isinstance(payload, CoverageOutcome):
                raise TypeError("unexpected coverage result")
            self.last_coverage = payload
            self._set_result_text(self._build_coverage_summary(payload))
            self.status_var.set(
                "Cobertura concluída: mapa de calor e contornos gerados."
            )
            self.report_button.configure(state="normal")
            self.pdf_button.configure(
                state=(
                    "normal"
                    if payload.paths.get("report_pdf", Path()).is_file()
                    else "disabled"
                )
            )
            self.profile_button.configure(state="normal")
            self.folder_button.configure(state="normal")
            return
        if event == "coverage_cancelled":
            if not isinstance(payload, CoverageCancelled):
                raise TypeError("unexpected coverage cancellation")
            self.coverage_progress_var.set(
                "Cálculo cancelado; os blocos concluídos foram preservados."
            )
            self._set_result_text(
                "COBERTURA CANCELADA\n\n"
                f"{payload.completed_cells:,} de "
                f"{payload.total_cells:,} células concluídas.\n\n"
                "Execute novamente com os mesmos parâmetros e a mesma pasta "
                "de saída para retomar automaticamente."
            )
            self.status_var.set(
                "Cobertura cancelada com checkpoint disponível para retomada."
            )
            return

        error = payload
        if not isinstance(error, dict):
            error = {"message": str(error), "traceback": str(error)}
        self._set_result_text(
            "Não foi possível concluir a análise.\n\n"
            f"{error['message']}\n\nDETALHES\n{error['traceback']}"
        )
        self.status_var.set("A análise terminou com erro.")
        messagebox.showerror(
            APP_NAME,
            "Não foi possível concluir a análise.\n\n"
            f"{error['message']}\n\n"
            "Os detalhes foram mantidos no painel de resultado.",
        )

    def _set_running(self, running: bool) -> None:
        self.analyze_button.configure(state="disabled" if running else "normal")
        for widget in self.form_widgets:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="disabled" if running else "readonly")
            else:
                widget.configure(state="disabled" if running else "normal")
        if running:
            self._disable_result_actions()
            if self.current_mode == "coverage":
                self.progress.stop()
                self.progress.configure(
                    mode="determinate",
                    maximum=100.0,
                    value=0.0,
                )
                if hasattr(self, "cancel_button"):
                    self.cancel_button.configure(state="normal")
            else:
                self.progress.configure(mode="indeterminate")
                self.progress.start(12)
        else:
            self.progress.stop()
            if (
                self.current_mode == "coverage"
                and hasattr(self, "cancel_button")
            ):
                self.cancel_button.configure(state="disabled")
            if self.current_mode == "coverage":
                self._coverage_radius_changed()
            self.coverage_cancel_event = None

    def _disable_result_actions(self) -> None:
        self.report_button.configure(state="disabled")
        self.pdf_button.configure(state="disabled")
        self.profile_button.configure(state="disabled")
        self.folder_button.configure(state="disabled")

    def _set_result_text(self, value: str) -> None:
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", value)
        self.result_text.configure(state="disabled")

    @staticmethod
    def _build_coverage_summary(outcome: CoverageOutcome) -> str:
        request = outcome.request
        statistics = outcome.statistics
        return "\n".join(
            [
                request.name,
                (
                    f"{request.frequency_mhz:.3f} MHz • "
                    f"P.1812 a {request.time_percentage:.0f}% do tempo"
                ),
                "",
                (
                    f"Raio: {request.radius_km} km • "
                    f"célula: {request.resolution_m} m • "
                    f"perfil de terreno: {request.terrain_step_m:g} m"
                ),
                (
                    "Células calculadas diretamente: "
                    f"{statistics['calculated_cells']:,}"
                ),
                (
                    "Células P.1812: "
                    f"{statistics['p1812_cells']:,}"
                ),
                (
                    "Células < 250 m em espaço livre: "
                    f"{statistics['short_range_free_space_cells']:,}"
                ),
                (
                    "Pontos de terreno processados: "
                    f"{statistics['terrain_profile_points']:,}"
                ),
                (
                    f"Processos usados: {statistics['worker_count']} • "
                    "células interpoladas: 0"
                ),
                (
                    "Tempo acumulado da grade: "
                    f"{format_duration(statistics['compute_seconds'])} • "
                    f"retomadas: {statistics['resume_count']}"
                ),
                "",
                (
                    "Área com margem ≥ 0 dB: "
                    f"{statistics['covered_percent']:.1f}%"
                ),
                (
                    "Área com margem ≥ +3 dB: "
                    f"{statistics['margin_3_db_percent']:.1f}%"
                ),
                (
                    "Área com margem ≥ +6 dB: "
                    f"{statistics['margin_6_db_percent']:.1f}%"
                ),
                (
                    "Área com margem ≥ +12 dB: "
                    f"{statistics['margin_12_db_percent']:.1f}%"
                ),
                "",
                "Contornos: 0, +3, +6 e +12 dB.",
                (
                    "Cada célula possui cálculo próprio. Vegetação e "
                    "edificações ainda não estão representadas."
                ),
                "",
                f"Mapa: {outcome.paths['report_html']}",
            ]
        )

    def _open_report(self) -> None:
        if self.current_mode == "coverage" and self.last_coverage:
            open_report_in_browser(self.last_coverage.paths["report_html"])
        elif self.last_outcome:
            open_report_in_browser(self.last_outcome.paths["report_html"])

    def _open_profile(self) -> None:
        if self.last_outcome and "profile_plot" in self.last_outcome.paths:
            _open_path(self.last_outcome.paths["profile_plot"])

    def _open_pdf_report(self) -> None:
        if self.current_mode == "coverage" and self.last_coverage:
            report = self.last_coverage.paths.get("report_pdf")
            if report:
                _open_path(report)
        elif self.last_outcome:
            report = self.last_outcome.paths.get("report_pdf")
            if report:
                _open_path(report)

    def _open_heatmap(self) -> None:
        if self.last_coverage:
            _open_path(self.last_coverage.paths["heatmap"])

    def _open_output_directory(self) -> None:
        if self.current_mode == "coverage" and self.last_coverage:
            _open_path(self.last_coverage.paths["report_html"].parent)
        elif self.last_outcome:
            _open_path(self.last_outcome.paths["report_html"].parent)


def _open_path(path: str | Path) -> None:
    target = Path(path).resolve()
    if sys.platform == "win32":
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(target)], check=False)
    elif target.is_file():
        webbrowser.open(target.as_uri())
    else:
        subprocess.run(["xdg-open", str(target)], check=False)


def main() -> int:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MarioPin.RadioLinkPlanner")
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    RadioLinkPlannerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

