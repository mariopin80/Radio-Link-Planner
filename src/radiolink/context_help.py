from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

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
    "fresnel": (
        "Fresnel livre (%)",
        "Fração do raio da primeira zona de Fresnel que se deseja manter livre de terreno ao longo do percurso. O padrão é 60%. Com 0%, o critério exige apenas visada direta.",
    ),
    "earth_k": (
        "Fator k",
        "Multiplica o raio da Terra para representar a refração no perfil geométrico. Um k menor aumenta a curvatura aparente e torna a folga mais exigente. O padrão é 4/3 (cerca de 1,33).",
    ),
    "height_step": (
        "Passo (m)",
        "Intervalo entre as alturas de antena testadas na busca. Um passo menor permite escolher a altura com mais precisão dentro dos limites informados.",
    ),
}


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
        command=lambda: messagebox.showinfo(tr(title), tr(explanation), parent=parent.winfo_toplevel()),
    )
    button.image = photo
    button.bind("<Return>", lambda event: button.invoke())
    button.pack(side="left", padx=(4, 0))
    return frame
