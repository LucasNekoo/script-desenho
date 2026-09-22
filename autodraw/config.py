"""
Configurações centrais do AutoDraw.

Concentra em um único lugar todos os parâmetros ajustáveis pelo usuário e a
tradução deles (0-100, algo intuitivo na interface) para os valores técnicos
usados pelo processamento de imagem e pelo controle do mouse.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Dict

# Extensões aceitas na importação da imagem.
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg")

# Resolução interna usada para extrair os traços. Valores maiores geram mais
# detalhe e mais tempo de processamento.
PROCESSING_MAX_SIDE = 900

# Modos de traçado disponíveis.
MODE_OUTLINE = "contornos"
MODE_LEVELS = "níveis"
MODE_HATCH = "hachura"
MODES = (MODE_OUTLINE, MODE_LEVELS, MODE_HATCH)

MODE_HELP = {
    MODE_OUTLINE: "Detecta bordas e desenha apenas o contorno. Rápido e limpo.",
    MODE_LEVELS: "Separa a imagem em faixas de luminosidade e contorna cada faixa.",
    MODE_HATCH: "Preenche as regiões escuras com hachuras, criando sombreado.",
}

# Bibliotecas de envio de entrada ("auto" escolhe a melhor disponível).
BACKENDS = ("auto", "pydirectinput", "pyautogui")

# Campos na escala de usuário (0-100).
_USER_SCALE_FIELDS = ("detail", "precision", "color_tolerance", "speed", "smoothing", "naturalness")


def _lerp(value: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
    """Interpolação linear com recorte nos limites."""
    if in_max == in_min:
        return out_min
    t = (value - in_min) / (in_max - in_min)
    t = max(0.0, min(1.0, t))
    return out_min + t * (out_max - out_min)


@dataclass
class Settings:
    """Parâmetros de desenho. Todos os campos 0-100 são "escala de usuário"."""

    # ---- imagem / traçado -------------------------------------------------
    mode: str = MODE_OUTLINE
    detail: int = 55            # quantidade de detalhes (0 = só o essencial)
    precision: int = 55         # fidelidade das curvas (0 = muito simplificado)
    color_tolerance: int = 45   # tolerância de cor / agrupamento de tons
    invert: bool = False        # inverter claro/escuro
    min_segment_px: int = 4     # descarta traços menores que isto (px de tela)

    # ---- mouse ------------------------------------------------------------
    speed: int = 70             # velocidade do cursor
    smoothing: int = 60         # suavidade do movimento (0 = teleporte)
    naturalness: int = 25       # micro-variação humana aplicada ao trajeto
    backend: str = "auto"       # auto | pydirectinput | pyautogui

    # ---- segurança --------------------------------------------------------
    max_paths: int = 6000       # teto de traços para não travar o jogo

    # ------------------------------------------------------------------
    # Valores derivados usados internamente
    # ------------------------------------------------------------------
    @property
    def canny_low(self) -> int:
        return int(_lerp(self.detail, 0, 100, 160, 25))

    @property
    def canny_high(self) -> int:
        return int(min(255, self.canny_low * 2.6))

    @property
    def min_contour_points(self) -> int:
        """Contornos com menos pontos que isso são ruído."""
        return int(_lerp(self.detail, 0, 100, 12, 3))

    @property
    def min_contour_length(self) -> float:
        """Comprimento mínimo (px da imagem de processamento)."""
        return _lerp(self.detail, 0, 100, 45, 4)

    @property
    def epsilon(self) -> float:
        """Tolerância do Douglas-Peucker: quanto maior, menos pontos."""
        return _lerp(self.precision, 0, 100, 3.5, 0.25)

    @property
    def blur_kernel(self) -> int:
        k = int(_lerp(self.detail, 0, 100, 7, 1))
        return k if k % 2 == 1 else k + 1

    @property
    def levels(self) -> int:
        """Número de faixas de tom (modos níveis/hachura)."""
        return int(round(_lerp(self.color_tolerance, 0, 100, 6, 2)))

    @property
    def hatch_spacing(self) -> int:
        """Distância entre linhas de hachura, em px da imagem de trabalho."""
        return int(round(_lerp(self.detail, 0, 100, 14, 4)))

    @property
    def step_px(self) -> float:
        """Tamanho do passo do cursor durante o traçado, em px de tela."""
        return _lerp(self.speed, 0, 100, 2.5, 22.0)

    @property
    def step_delay(self) -> float:
        """Pausa entre passos, em segundos."""
        return _lerp(self.speed, 0, 100, 0.0045, 0.0)

    @property
    def travel_step_px(self) -> float:
        """Passo usado nos deslocamentos sem desenhar (caneta levantada)."""
        return max(self.step_px * 2.5, 12.0)

    @property
    def pen_delay(self) -> float:
        """Pausa após pressionar e após soltar o botão.

        Existe para o jogo registrar o clique. Em desenhos com muitos traços
        curtos essa pausa domina o tempo total, então ela acompanha a
        velocidade escolhida — nunca abaixo de 10 ms, que é o piso seguro.
        """
        return _lerp(self.speed, 0, 100, 0.045, 0.010)

    @property
    def smoothing_factor(self) -> float:
        return _lerp(self.smoothing, 0, 100, 0.0, 1.0)

    @property
    def jitter_px(self) -> float:
        return _lerp(self.naturalness, 0, 100, 0.0, 1.2)

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> Settings:
        """Constrói a partir de dados externos, descartando valores inválidos.

        Cada campo é validado isoladamente: um valor corrompido volta ao
        padrão sem invalidar o resto das preferências.
        """
        if not isinstance(data, dict):
            return cls()
        defaults = cls()
        clean: Dict[str, Any] = {}

        for name in _USER_SCALE_FIELDS:
            value = data.get(name)
            if _is_number(value):
                clean[name] = int(round(max(0.0, min(100.0, float(value)))))

        if data.get("mode") in MODES:
            clean["mode"] = data["mode"]
        if data.get("backend") in BACKENDS:
            clean["backend"] = data["backend"]
        if isinstance(data.get("invert"), bool):
            clean["invert"] = data["invert"]

        value = data.get("min_segment_px")
        if _is_number(value) and value >= 0:
            clean["min_segment_px"] = int(value)
        value = data.get("max_paths")
        if _is_number(value) and value >= 1:
            clean["max_paths"] = int(value)

        return replace(defaults, **clean)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Settings:
        if not path.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):  # JSONDecodeError e UnicodeDecodeError são ValueError
            return cls()


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


DEFAULT_SETTINGS_PATH = Path.home() / ".roblox_autodraw.json"
