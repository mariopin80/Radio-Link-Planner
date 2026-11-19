from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk

from .i18n import tr
from .propagation.p1812 import P1812_TIME_HELP


FIELD_HELP = {
    "availability": (
        "Meta (%)",
        "Percentual de tempo em que se deseja que o enlace funcione. É uma meta de projeto. O campo Tempo P.1812 (%) descreve a estatística de perda do modelo de cobertura.",
    ),
    "sensitivity": (
        "Sensibilidade RX (dBm)",
        "Nível mínimo de sinal que o receptor precisa para demodular o modo escolhido. Use a especificação do rádio para esse modo. Um valor mais negativo representa maior sensibilidade.",
    ),
    "polarization": (
        "Polarização",
        "Orientação do campo elétrico das antenas. Escolha vertical ou horizontal conforme a montagem. A previsão considera a mesma polarização nos dois extremos.",
    ),
    "runs": (
        "Monte Carlo",
        "Número de sorteios usados para estimar o efeito das incertezas na margem. Mais sorteios reduzem a variação estatística da estimativa e aumentam o tempo de processamento.",
    ),
    "p1812_time": ("Tempo P.1812 (%)", P1812_TIME_HELP),
    "resolution": (
        "Resolução",
        "O tamanho da célula é a distância entre pontos vizinhos da grade. Células menores detalham o mapa e aumentam a quantidade de percursos calculados. Em Personalizada, informe o tamanho em metros.",
    ),
    "antenna_pattern": (
        "Antena transmissora",
        "A opção omnidirecional usa o mesmo ganho em todos os azimutes. A direcional estima a variação de ganho conforme o ângulo em relação ao apontamento.",
    ),
    "beamwidth": (
        "Abertura a −3 dB (°)",
        "Ângulo total entre os dois lados do feixe onde o ganho cai 3 dB em relação ao máximo. Uma abertura de 60° corresponde a cerca de 30° para cada lado do eixo.",
    ),
    "front_to_back": (
        "Relação frente/costas (dB)",
        "Diferença entre o ganho no eixo da antena e o ganho na direção oposta. Um valor de 20 dB reduz em 20 dB o ganho previsto diretamente atrás da antena.",
    ),
    "azimuth": (
        "Azimute de apontamento (°)",
        "Direção do ganho máximo, medida em graus no sentido horário a partir do norte geográfico. 0° é norte e 90° é leste.",
    ),
    "height_step": (
        "Passo (m)",
        "Intervalo entre as alturas de antena testadas na busca. Um passo menor permite escolher a altura com mais precisão dentro dos limites informados.",
    ),
}


class _HelpCard:
    def __init__(self, anchor: tk.Button, title: str, explanation: str) -> None:
        self.anchor = anchor
        self.window = anchor.winfo_toplevel()
        self.frame = tk.Frame(
            self.window, background="#252d36", highlightbackground="#6ea8f2", highlightthickness=1,
        )
        self.heading = tk.Label(self.frame, text=title, background="#252d36", foreground="#ffffff",
                                font=("Segoe UI Semibold", 10), justify="left", anchor="w")
        self.body = tk.Label(self.frame, text=explanation, background="#252d36", foreground="#dce2e8",
                             font=("Segoe UI", 10), justify="left", anchor="w")
        self.heading.pack(fill="x", padx=12, pady=(9, 3))
        self.body.pack(fill="x", padx=12, pady=(0, 10))
        self.bindings = [
            (self.window, "<ButtonPress-1>", self.window.bind("<ButtonPress-1>", self._outside, add="+")),
            (self.window, "<Escape>", self.window.bind("<Escape>", self._escape, add="+")),
            (self.window, "<Configure>", self.window.bind("<Configure>", self._resized, add="+")),
            (self.anchor, "<Destroy>", self.anchor.bind("<Destroy>", self.close, add="+")),
        ]
        self._place()

    def _place(self) -> None:
        window = self.window
        width = min(round(window.winfo_fpixels("3.7i")), max(1, window.winfo_width() - 12))
        for label in (self.heading, self.body):
            label.configure(wraplength=max(1, width - 28))
        self.frame.update_idletasks()
        x = self.anchor.winfo_rootx() - window.winfo_rootx()
        anchor_y = self.anchor.winfo_rooty() - window.winfo_rooty()
        height = self.frame.winfo_reqheight()
        y = anchor_y + self.anchor.winfo_height() + 5
        if y + height > window.winfo_height() - 6:
            y = anchor_y - height - 5
        self.frame.place(
            x=max(6, min(x, window.winfo_width() - width - 6)),
            y=max(6, y), width=width,
        )
        self.frame.lift()

    def _outside(self, event: tk.Event) -> None:
        if event.widget is not self.anchor and not (
            event.widget is self.frame or str(event.widget).startswith(f"{self.frame}.")
        ):
            self.close()

    def _escape(self, _: tk.Event) -> str:
        self.close()
        return "break"

    def _resized(self, event: tk.Event) -> None:
        if event.widget is self.window:
            self._place()

    def close(self, _: tk.Event | None = None) -> None:
        if getattr(self.window, "_help_card", None) is self:
            self.window._help_card = None
        for widget, sequence, identifier in self.bindings:
            if widget.winfo_exists():
                widget.unbind(sequence, identifier)
        self.bindings.clear()
        if self.frame.winfo_exists():
            self.frame.destroy()


def label_with_help(
    parent: tk.Misc,
    text: str,
    help_key: str | None,
    *,
    label_style: str = "Panel.TLabel",
    frame_style: str = "Panel.TFrame",
) -> ttk.Label | ttk.Frame:
    if help_key is None:
        return ttk.Label(parent, text=text, style=label_style)

    title, explanation = FIELD_HELP[help_key]
    frame = ttk.Frame(parent, style=frame_style)
    ttk.Label(frame, text=text, style=label_style).pack(side="left")
    background = ttk.Style(frame).lookup(label_style, "background")
    size = max(14, round(parent.winfo_fpixels("0.14i")))
    pixels = size * 4
    icon = Image.new("RGBA", (pixels, pixels))
    draw = ImageDraw.Draw(icon)
    draw.ellipse((0, 0, pixels - 1, pixels - 1), fill="#2168aa")
    draw.text(
        (pixels / 2, pixels / 2), "?", anchor="mm", fill="white",
        font=ImageFont.load_default(size=round(pixels * 0.82)),
    )
    photo = ImageTk.PhotoImage(icon.resize((size, size), Image.Resampling.LANCZOS), master=frame)

    def toggle_help() -> None:
        window = button.winfo_toplevel()
        previous = getattr(window, "_help_card", None)
        if previous is not None:
            previous.close()
            if previous.anchor is button:
                return
        window._help_card = _HelpCard(button, tr(title), tr(explanation))

    button = tk.Button(
        frame,
        text=tr(title),
        image=photo,
        background=background,
        activebackground=background,
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=background,
        highlightcolor="#6ea8f2",
        padx=0,
        pady=0,
        relief="flat",
        cursor="hand2",
        takefocus=True,
        command=toggle_help,
    )
    button.image = photo
    button.bind("<Return>", lambda event: button.invoke())
    button.pack(side="left", padx=(4, 0))
    return frame
