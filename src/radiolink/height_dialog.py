from __future__ import annotations

import io
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import asdict
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from .domain import Project
from .engine import compare_height_designs
from .geometry import calculate_geometry
from .height_optimization import (
    HeightBounds,
    HeightSolution,
    height_comparison_table,
    height_summary_lines,
    optimize_antenna_heights,
    project_at_heights,
)
from .i18n import choice_id, choice_label, tr
from .report import render_profile_plot
from .terrain import TerrainProfile


def open_height_dialog(
    parent: tk.Tk, project: Project, profile: TerrainProfile,
    apply: Callable[[HeightSolution], None],
) -> tk.Toplevel:
    dialog = tk.Toplevel(parent)
    dialog.title(tr("Otimizar altura das antenas"))
    dialog.transient(parent)
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(1, weight=1)
    width = min(880, parent.winfo_screenwidth() - 80)
    height = min(640, parent.winfo_screenheight() - 84)
    dialog.geometry(f"{width}x{height}")

    form = ttk.Frame(dialog, padding=12)
    form.grid(row=0, column=0, sticky="ew")
    choices = ("elevate_a", "elevate_b", "elevate_both")
    selection = tk.StringVar(dialog, value=choice_label("elevate_both"))
    ttk.Label(form, text=tr("Elevar antenas")).grid(row=0, column=0, sticky="w")
    mode = ttk.Combobox(
        form, textvariable=selection, values=tuple(map(choice_label, choices)),
        state="readonly", width=16,
    )
    mode.grid(row=0, column=1, sticky="ew", padx=6)
    fields = {}
    entries = {}

    def field(key: str, label: str, number: float, row: int, column: int) -> None:
        fields[key] = tk.StringVar(dialog, value=str(number))
        ttk.Label(form, text=label).grid(row=row, column=column, sticky="w", padx=(0, 4), pady=4)
        entry = ttk.Entry(form, width=9, textvariable=fields[key])
        entry.grid(row=row, column=column + 1, sticky="w", padx=(0, 12), pady=4)
        entries[key] = entry

    a = project.terminal_a.antenna_height_m
    b = project.terminal_b.antenna_height_m
    field("min_a", tr("Mínimo A (m)"), a, 1, 0)
    field("max_a", tr("Máximo A (m)"), max(a, 100.0), 1, 2)
    field("min_b", tr("Mínimo B (m)"), b, 2, 0)
    field("max_b", tr("Máximo B (m)"), max(b, 100.0), 2, 2)
    field("fresnel", tr("Fresnel livre (%)"), 60.0, 0, 4)
    field("step", tr("Passo (m)"), 1.0, 1, 4)
    field("k", tr("Fator k"), project.environment.effective_earth_k, 2, 4)

    notebook = ttk.Notebook(dialog)
    notebook.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 6))
    summary_tab = ttk.Frame(notebook, padding=12)
    profile_tab = ttk.Frame(notebook, padding=6)
    model_tab = ttk.Frame(notebook, padding=8)
    notebook.add(summary_tab, text=tr("Alturas sugeridas"))
    notebook.add(profile_tab, text=tr("Perfil antes e depois"))
    notebook.add(model_tab, text=tr("Comparação de modelos"))
    summary = ttk.Label(summary_tab, justify="left", wraplength=width - 70)
    summary.pack(fill="both", expand=True, anchor="nw")
    profile_image = ttk.Label(profile_tab, anchor="center")
    profile_image.pack(fill="both", expand=True)
    tables = {}
    for direction, name in (
        ("a_to_b", f"{project.terminal_a.name} → {project.terminal_b.name}"),
        ("b_to_a", f"{project.terminal_b.name} → {project.terminal_a.name}"),
    ):
        ttk.Label(model_tab, text=name).pack(anchor="w", pady=(6, 2))
        table = ttk.Treeview(model_tab, columns=("model", "time", "loss", "margin"), show="headings", height=3)
        for column, label, column_width in zip(
            table["columns"], height_comparison_table([])[0], (80, 85, 160, 170)
        ):
            table.heading(column, text=label)
            table.column(column, width=column_width, anchor="center")
        table.pack(fill="x")
        tables[direction] = table

    actions = ttk.Frame(dialog, padding=(12, 4, 12, 12))
    actions.grid(row=2, column=0, sticky="ew")
    solution = None
    preview_image = None
    scheduled_poll = None

    def close() -> None:
        if scheduled_poll is not None:
            dialog.after_cancel(scheduled_poll)
        dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", close)
    ttk.Button(actions, text=tr("Fechar"), command=close).pack(side="right")

    def sync_fields(*_: object) -> None:
        nonlocal solution, preview_image
        chosen = choice_id(selection.get(), choices)
        for terminal in ("a", "b"):
            state = "normal" if chosen in {f"elevate_{terminal}", "elevate_both"} else "disabled"
            entries[f"min_{terminal}"].configure(state=state)
            entries[f"max_{terminal}"].configure(state=state)
        solution = None
        preview_image = None
        profile_image.configure(image="")
        for table in tables.values():
            table.delete(*table.get_children())
        summary.configure(text=tr("Defina os limites e calcule as alturas para visualizar a proposta."))
        apply_button.configure(state="disabled")
        simulation_button.configure(state="disabled")

    def calculate() -> None:
        nonlocal solution, preview_image
        chosen = choice_id(selection.get(), choices)

        def number(key: str) -> float:
            return float(fields[key].get().strip().replace(",", "."))

        def bounds(terminal: str) -> HeightBounds | None:
            if chosen in {f"elevate_{terminal}", "elevate_both"}:
                return HeightBounds(number(f"min_{terminal}"), number(f"max_{terminal}"))
            return None

        try:
            solution = optimize_antenna_heights(
                project, profile, bounds_a=bounds("a"), bounds_b=bounds("b"),
                step_m=number("step"), fresnel_percent=number("fresnel"), effective_earth_k=number("k"),
            )
            notebook.select(summary_tab)
            if solution is None:
                summary.configure(text=tr("Nenhuma combinação atende ao critério de Fresnel dentro dos limites e do passo informados."))
                return
            record = asdict(solution)
            updated = project_at_heights(project, solution.proposed_a_m, solution.proposed_b_m, solution.effective_earth_k)
            geometry, arrays = calculate_geometry(updated, profile)
            buffer = io.BytesIO()
            render_profile_plot(updated, profile, {"geometry": geometry.to_dict(), "height_optimization": record}, arrays, buffer)
            buffer.seek(0)
            with Image.open(buffer) as image:
                image.thumbnail((width - 64, max(170, height - 216)))
                preview_image = ImageTk.PhotoImage(image, master=dialog)
            profile_image.configure(image=preview_image)
            summary.configure(text="\n\n".join(height_summary_lines(record)))
            apply_button.configure(state="normal")
            simulation_button.configure(state="normal")
        except ValueError as exc:
            message = tr("Informe valores numéricos válidos.") if str(exc).startswith("could not convert") else str(exc)
            messagebox.showerror(dialog.title(), message, parent=dialog)
        except Exception as exc:  # GUI boundary: surface rendering and I/O errors.
            messagebox.showerror(dialog.title(), str(exc), parent=dialog)

    def simulate() -> None:
        nonlocal scheduled_poll
        current = solution
        if current is None:
            return
        before = project_at_heights(project, current.original_a_m, current.original_b_m, current.effective_earth_k)
        after = project_at_heights(project, current.proposed_a_m, current.proposed_b_m, current.effective_earth_k)
        pending = queue.Queue()
        summary.configure(text=tr("Calculando os modelos de propagação antes e depois…"))
        notebook.select(summary_tab)
        for widget in (mode, *entries.values(), calculate_button, apply_button, simulation_button):
            widget.configure(state="disabled")

        def worker() -> None:
            try:
                pending.put(compare_height_designs(before, after, profile))
            except Exception as exc:  # Report engine errors on the Tk thread.
                pending.put(exc)

        def poll() -> None:
            nonlocal scheduled_poll
            try:
                comparison = pending.get_nowait()
            except queue.Empty:
                scheduled_poll = dialog.after(80, poll)
                return
            scheduled_poll = None
            mode.configure(state="readonly")
            for key, widget in entries.items():
                enabled = not key.startswith(("min_", "max_")) or choice_id(selection.get(), choices) in {
                    f"elevate_{key[-1]}", "elevate_both",
                }
                widget.configure(state="normal" if enabled else "disabled")
            for button in (calculate_button, apply_button, simulation_button):
                button.configure(state="normal")
            summary.configure(text="\n\n".join(height_summary_lines(asdict(current))))
            if isinstance(comparison, Exception):
                messagebox.showerror(dialog.title(), str(comparison), parent=dialog)
                return
            for direction, rows in comparison.items():
                table = tables[direction]
                table.delete(*table.get_children())
                for row in height_comparison_table(rows)[1:]:
                    table.insert("", "end", values=row)
            notebook.select(model_tab)

        threading.Thread(target=worker, daemon=True).start()
        scheduled_poll = dialog.after(80, poll)

    def confirm() -> None:
        if solution is not None:
            apply(solution)
            close()

    calculate_button = ttk.Button(actions, text=tr("Calcular alturas"), command=calculate)
    calculate_button.pack(side="left", padx=(0, 6))
    simulation_button = ttk.Button(actions, text=tr("Simular antes e depois"), command=simulate)
    simulation_button.pack(side="left", padx=(0, 6))
    apply_button = ttk.Button(actions, text=tr("Aplicar alturas"), command=confirm)
    apply_button.pack(side="left")
    for variable in (selection, *fields.values()):
        variable.trace_add("write", sync_fields)
    sync_fields()
    dialog.grab_set()
    mode.focus_set()
    return dialog
