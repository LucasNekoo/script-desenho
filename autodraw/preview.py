"""
Prévias visuais.

Os traços são desenhados com PIL (rápido, mesmo com milhares de linhas) e
depois exibidos como imagem no Tk, em vez de criar milhares de itens de canvas.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from .path_generation import FittedDrawing, fit_rect
from .screen import Rect

BACKGROUND = (250, 250, 250)
AREA_LINE = (120, 150, 200)
FIT_LINE = (205, 215, 230)
STROKE = (26, 32, 44)
EMPTY_TEXT = (140, 145, 155)


def thumbnail(img: Image.Image, box: Tuple[int, int]) -> Image.Image:
    """Miniatura centralizada em um fundo neutro, sem distorcer a imagem."""
    bw, bh = box
    canvas = Image.new("RGB", (bw, bh), BACKGROUND)
    copy = img.copy()
    copy.thumbnail((max(1, bw - 8), max(1, bh - 8)), Image.LANCZOS)
    canvas.paste(copy, ((bw - copy.width) // 2, (bh - copy.height) // 2))
    return canvas


def render_paths(fitted: Optional[FittedDrawing],
                 area: Optional[Rect],
                 box: Tuple[int, int],
                 message: str = "") -> Image.Image:
    """Desenha os traços exatamente como o mouse vai percorrê-los.

    `fitted` está em pixels de tela e `area` é o retângulo de tela usado no
    encaixe; ambos são reduzidos juntos para caber em `box`.
    """
    bw, bh = box
    canvas = Image.new("RGB", (bw, bh), BACKGROUND)
    draw = ImageDraw.Draw(canvas)

    if fitted is None or not fitted.paths or area is None or area[2] <= 0 or area[3] <= 0:
        if message:
            draw.text((14, bh // 2 - 6), message, fill=EMPTY_TEXT)
        return canvas

    ax, ay, aw, ah = area

    # 1) a área selecionada, encaixada na caixa de prévia
    pad = 10
    bx, by, bw_area, bh_area = fit_rect(aw, ah, (pad, pad, bw - 2 * pad, bh - 2 * pad))
    if bw_area <= 0 or bh_area <= 0:
        return canvas
    draw.rectangle([bx, by, bx + bw_area - 1, by + bh_area - 1], outline=AREA_LINE)

    scale = bw_area / aw
    origin = np.array([ax, ay], dtype=np.float32)
    offset = np.array([bx, by], dtype=np.float32)

    # 2) a parte da área realmente ocupada pela imagem
    fx, fy, fw, fh = fitted.rect
    if (fw, fh) != (aw, ah):
        x0, y0 = (np.array([fx, fy]) - origin) * scale + offset
        draw.rectangle([x0, y0, x0 + fw * scale - 1, y0 + fh * scale - 1], outline=FIT_LINE)

    for path in fitted.paths:
        if len(path) < 2:
            continue
        pts = ((path - origin) * scale + offset).tolist()
        draw.line([tuple(p) for p in pts], fill=STROKE, width=1)

    return canvas
