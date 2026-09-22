"""
Carregamento, validação e pré-processamento da imagem.

Este módulo não conhece a interface nem o mouse: recebe um caminho de arquivo
e devolve matrizes prontas para a extração de traços.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from .config import PROCESSING_MAX_SIDE, SUPPORTED_EXTENSIONS, Settings


class ImageError(Exception):
    """Erro de leitura ou validação da imagem."""


@dataclass
class LoadedImage:
    """Imagem já validada e pronta para uso."""

    path: Path
    pil: Image.Image          # RGB, resolução original
    gray: np.ndarray          # escala de cinza, reduzida para processamento
    work_size: Tuple[int, int]  # (largura, altura) da versão de trabalho

    @property
    def original_size(self) -> Tuple[int, int]:
        return self.pil.size

    @property
    def aspect(self) -> float:
        w, h = self.pil.size
        return w / h if h else 1.0


def load_image(path: str | Path) -> LoadedImage:
    """Abre a imagem, valida o formato e prepara a versão de trabalho.

    Levanta :class:`ImageError` com uma mensagem legível em caso de problema.
    """
    p = Path(path)

    if not p.exists():
        raise ImageError(f"Arquivo não encontrado: {p}")
    if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
        aceitos = ", ".join(SUPPORTED_EXTENSIONS)
        raise ImageError(f"Formato não suportado ({p.suffix or 'sem extensão'}). Use: {aceitos}")

    try:
        with Image.open(p) as probe:
            probe.verify()  # detecta arquivos corrompidos sem carregar tudo
        pil = Image.open(p)
        if pil.format not in ("PNG", "JPEG"):
            raise ImageError(f"O conteúdo do arquivo é {pil.format}, e não PNG ou JPEG.")
        pil = _flatten(pil)
    except UnidentifiedImageError as exc:
        raise ImageError("Não foi possível ler a imagem: arquivo inválido ou corrompido.") from exc
    except OSError as exc:
        raise ImageError(f"Falha ao abrir a imagem: {exc}") from exc

    if min(pil.size) < 8:
        raise ImageError("A imagem é pequena demais para ser desenhada (mínimo 8x8 px).")

    gray = _to_work_gray(pil)
    h, w = gray.shape
    return LoadedImage(path=p, pil=pil, gray=gray, work_size=(w, h))


def _flatten(img: Image.Image) -> Image.Image:
    """Converte para RGB, aplicando fundo branco sobre canais de transparência."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    return img.convert("RGB")


def _to_work_gray(img: Image.Image) -> np.ndarray:
    """Reduz a imagem para a resolução de trabalho e converte para cinza."""
    w, h = img.size
    scale = min(1.0, PROCESSING_MAX_SIDE / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    arr = np.asarray(img.convert("L"), dtype=np.uint8)
    return arr


# ----------------------------------------------------------------------
# Máscaras usadas pelos modos de traçado
# ----------------------------------------------------------------------

def prepare_gray(image: LoadedImage, settings: Settings) -> np.ndarray:
    """Aplica desfoque, normalização de contraste e inversão opcional."""
    gray = image.gray
    k = settings.blur_kernel
    if k > 1:
        gray = cv2.GaussianBlur(gray, (k, k), 0)
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    if settings.invert:
        gray = 255 - gray
    return gray


def edge_mask(gray: np.ndarray, settings: Settings) -> np.ndarray:
    """Mapa binário de bordas (modo contornos)."""
    edges = cv2.Canny(gray, settings.canny_low, settings.canny_high, L2gradient=True)
    # Fecha micro-falhas para que os contornos saiam contínuos.
    kernel = np.ones((2, 2), np.uint8)
    return cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)


def tone_masks(gray: np.ndarray, settings: Settings) -> list[np.ndarray]:
    """Divide a imagem em faixas de tom, da mais escura para a mais clara.

    Cada máscara acumula os pixels iguais ou mais escuros que o limiar, de modo
    que áreas escuras recebem mais camadas (e, na hachura, mais linhas).
    """
    n = max(2, settings.levels)
    masks: list[np.ndarray] = []
    for i in range(1, n + 1):
        limiar = int(255 * i / (n + 1))
        mask = (gray <= limiar).astype(np.uint8) * 255
        if cv2.countNonZero(mask) == 0:
            continue
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        masks.append(mask)
    return masks
