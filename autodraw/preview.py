"""
Prévias visuais.

Os traços são desenhados com PIL (rápido, mesmo com milhares de linhas) e
depois exibidos como imagem no Tk, em vez de criar milhares de itens de canvas.
"""

from __future__ import annotations

from typing import Optional, Tuple

from PIL import Image, ImageDraw

from .path_generation import Drawing, fit_rect

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


def render_paths(drawing: Optional[Drawing],
                 area_size: Optional[Tuple[int, int]],
                 box: Tuple[int, int],
                 message: str = "") -> Image.Image:
    """Desenha os traços como ficarão dentro da área selecionada.

    `area_size` é a largura/altura da área da tela escolhida pelo usuário. Se
    for ``None``, usa a proporção da própria imagem.
    """
    bw, bh = box
    canvas = Image.new("RGB", (bw, bh), BACKGROUND)
    draw = ImageDraw.Draw(canvas)

    if drawing is None or not drawing.paths:
        if message:
            draw.text((14, bh // 2 - 6), message, fill=EMPTY_TEXT)
        return canvas

    aw, ah = area_size if area_size else (drawing.width, drawing.height)
    if aw <= 0 or ah <= 0:
        aw, ah = drawing.width, drawing.height

    # 1) a área selecionada, encaixada na caixa de prévia
    pad = 10
    area_box = fit_rect(aw, ah, (pad, pad, bw - 2 * pad, bh - 2 * pad))
    ax, ay, arw, arh = area_box
    draw.rectangle([ax, ay, ax + arw - 1, ay + arh - 1], outline=AREA_LINE)

    # 2) a imagem encaixada dentro da área, preservando a proporção
    fx, fy, fw, fh = fit_rect(drawing.width, drawing.height, area_box)
    if fw <= 0 or fh <= 0:
        return canvas
    if (fw, fh) != (arw, arh):
        draw.rectangle([fx, fy, fx + fw - 1, fy + fh - 1], outline=FIT_LINE)

    scale = fw / drawing.width
    for path in drawing.paths:
        if len(path) < 2:
            continue
        pts = [(fx + float(x) * scale, fy + float(y) * scale) for x, y in path]
        draw.line(pts, fill=STROKE, width=1)

    return canvas
