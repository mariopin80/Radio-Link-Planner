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

from .desktop_core import (
    APP_NAME,
    AnalysisOutcome,
    AnalysisRequest,
    build_desktop_summary,
    bundled_example_path,
    default_output_directory,
    run_analysis,
)
from .version import __version__


class RadioLinkPlannerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_outcome: AnalysisOutcome | None = None

        self.project_var = tk.StringVar(value=str(bundled_example_path()))
        self.output_var = tk.StringVar(value=str(default_output_directory()))
        self.runs_var = tk.StringVar(value="20000")
        self.plots_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Pronto para analisar o caso de exemplo.")

        self._configure_window()
        self._configure_styles()
        self._build_layout()
        self.root.after(100, self._poll_events)

    def _configure_window(self) -> None:
        self.root.title(f"{APP_NAME} — MVP {__version__}")
        self.root.geometry("980x720")
        self.root.minsize(820, 620)
        self.root.configure(background="#11151a")

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("App.TFrame", background="#11151a")
        style.configure("Panel.TFrame", background="#1a2027")
        style.configure(
            "Title.TLabel",
            background="#11151a",
            foreground="#f2f4f6",
            font=("Segoe UI Semibold", 22),
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
        style.configure("Status.TLabel", background="#11151a", foreground="#aeb8c2")
        style.configure(
            "Accent.TButton",
            background="#d84a4a",
            foreground="#ffffff",
            padding=(18, 9),
            font=("Segoe UI Semibold", 10),
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

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=24)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        header = ttk.Frame(outer, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text=(
                "Protótipo científico local para enlaces terrestres VHF/UHF "
                "• sem servidor"
            ),
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        inputs = ttk.Frame(outer, style="Panel.TFrame", padding=18)
        inputs.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        inputs.columnconfigure(1, weight=1)
        ttk.Label(
            inputs, text="Configuração da análise", style="PanelTitle.TLabel"
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        ttk.Label(inputs, text="Projeto JSON", style="Panel.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=5
        )
        self.project_entry = ttk.Entry(inputs, textvariable=self.project_var)
        self.project_entry.grid(row=1, column=1, sticky="ew", pady=5)
        self.project_button = ttk.Button(
            inputs, text="Selecionar…", command=self._select_project
        )
        self.project_button.grid(row=1, column=2, padx=(8, 0), pady=5)

        ttk.Label(inputs, text="Pasta de saída", style="Panel.TLabel").grid(
            row=2, column=0, sticky="w", padx=(0, 12), pady=5
        )
        self.output_entry = ttk.Entry(inputs, textvariable=self.output_var)
        self.output_entry.grid(row=2, column=1, sticky="ew", pady=5)
        self.output_button = ttk.Button(
            inputs, text="Selecionar…", command=self._select_output
        )
        self.output_button.grid(row=2, column=2, padx=(8, 0), pady=5)

        ttk.Label(inputs, text="Monte Carlo", style="Panel.TLabel").grid(
            row=3, column=0, sticky="w", padx=(0, 12), pady=5
        )
        controls = ttk.Frame(inputs, style="Panel.TFrame")
        controls.grid(row=3, column=1, columnspan=2, sticky="ew", pady=5)
        self.runs_combo = ttk.Combobox(
            controls,
            textvariable=self.runs_var,
            values=("500", "2000", "5000", "20000", "50000"),
            width=10,
            state="readonly",
        )
        self.runs_combo.grid(row=0, column=0, sticky="w")
        ttk.Label(controls, text="execuções", style="Panel.TLabel").grid(
            row=0, column=1, sticky="w", padx=(6, 22)
        )
        self.plots_check = ttk.Checkbutton(
            controls, text="Gerar gráficos técnicos", variable=self.plots_var
        )
        self.plots_check.grid(row=0, column=2, sticky="w")
        ttk.Button(
            controls,
            text="Restaurar exemplo",
            command=self._restore_example,
        ).grid(row=0, column=3, sticky="e", padx=(22, 0))
        controls.columnconfigure(3, weight=1)

        results = ttk.Frame(outer, style="Panel.TFrame", padding=18)
        results.grid(row=2, column=0, sticky="nsew")
        results.columnconfigure(0, weight=1)
        results.rowconfigure(2, weight=1)
        ttk.Label(results, text="Resultado", style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        action_bar = ttk.Frame(results, style="Panel.TFrame")
        action_bar.grid(row=0, column=1, sticky="e")
        self.report_button = ttk.Button(
            action_bar,
            text="Abrir relatório",
            command=self._open_report,
            state="disabled",
        )
        self.report_button.grid(row=0, column=0, padx=(0, 6))
        self.folder_button = ttk.Button(
            action_bar,
            text="Abrir pasta",
            command=self._open_output_directory,
            state="disabled",
        )
        self.folder_button.grid(row=0, column=1)

        self.progress = ttk.Progressbar(results, mode="indeterminate")
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 10))
        self.result_text = tk.Text(
            results,
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
        self.result_text.grid(row=2, column=0, columnspan=2, sticky="nsew")
        self._set_result_text(
            "O caso Morro do Jacu–Palmira já está selecionado.\n"
            "Clique em “Analisar enlace” para executar ITM, P.1812, P.2001 "
            "e Monte Carlo.\n\n"
            "Na primeira análise, os dados integrais dos modelos ITU serão "
            "baixados diretamente do site oficial."
        )

        footer = ttk.Frame(outer, style="App.TFrame")
        footer.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.analyze_button = ttk.Button(
            footer,
            text="Analisar enlace",
            command=self._start_analysis,
            style="Accent.TButton",
        )
        self.analyze_button.grid(row=0, column=1, sticky="e")

    def _select_project(self) -> None:
        selected = filedialog.askopenfilename(
            title="Selecionar projeto de enlace",
            filetypes=(("Projeto JSON", "*.json"), ("Todos os arquivos", "*.*")),
        )
        if selected:
            self.project_var.set(selected)

    def _select_output(self) -> None:
        selected = filedialog.askdirectory(title="Selecionar pasta de saída")
        if selected:
            self.output_var.set(selected)

    def _restore_example(self) -> None:
        self.project_var.set(str(bundled_example_path()))
        self.output_var.set(str(default_output_directory()))
        self.runs_var.set("20000")
        self.plots_var.set(True)
        self.status_var.set("Caso de exemplo restaurado.")

    def _start_analysis(self) -> None:
        project_path = Path(self.project_var.get().strip())
        output_directory = Path(self.output_var.get().strip())
        if not project_path.is_file():
            messagebox.showerror(
                APP_NAME, "O arquivo de projeto selecionado não existe."
            )
            return
        try:
            runs = int(self.runs_var.get())
        except ValueError:
            messagebox.showerror(
                APP_NAME, "A quantidade de execuções Monte Carlo é inválida."
            )
            return
        request = AnalysisRequest(
            project_path=project_path,
            output_directory=output_directory,
            monte_carlo_runs=runs,
            make_plots=self.plots_var.get(),
        )
        self._set_running(True)
        self.status_var.set(
            "Analisando. Na primeira execução, os dados ITU serão baixados…"
        )
        self._set_result_text(
            "Análise em andamento.\n\n"
            "A interface continuará responsiva enquanto o motor executa os "
            "modelos de propagação e o Monte Carlo."
        )
        self.worker = threading.Thread(
            target=self._analysis_worker, args=(request,), daemon=True
        )
        self.worker.start()

    def _analysis_worker(self, request: AnalysisRequest) -> None:
        try:
            outcome = run_analysis(request)
            self.events.put(("success", outcome))
        except Exception as exc:
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
        try:
            event, payload = self.events.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_events)
            return
        self._set_running(False)
        if event == "success":
            outcome = payload
            if not isinstance(outcome, AnalysisOutcome):
                raise TypeError("unexpected analysis result")
            self.last_outcome = outcome
            self._set_result_text(build_desktop_summary(outcome))
            self.status_var.set("Análise concluída e relatório gerado.")
            self.report_button.configure(state="normal")
            self.folder_button.configure(state="normal")
        else:
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
        self.root.after(100, self._poll_events)

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.analyze_button.configure(state=state)
        self.project_entry.configure(state=state)
        self.output_entry.configure(state=state)
        self.project_button.configure(state=state)
        self.output_button.configure(state=state)
        self.runs_combo.configure(state="disabled" if running else "readonly")
        self.plots_check.configure(state=state)
        if running:
            self.report_button.configure(state="disabled")
            self.folder_button.configure(state="disabled")
            self.progress.start(12)
        else:
            self.progress.stop()

    def _set_result_text(self, value: str) -> None:
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", value)
        self.result_text.configure(state="disabled")

    def _open_report(self) -> None:
        if self.last_outcome:
            _open_path(self.last_outcome.paths["report_html"])

    def _open_output_directory(self) -> None:
        if self.last_outcome:
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
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    RadioLinkPlannerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
